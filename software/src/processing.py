import os
import glob
from typing import List, Dict, Tuple, Optional, Union
import scipy.io
import numpy as np
import pandas as pd
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
import h5py
import hdf5storage
import time
import re
from datetime import datetime, timedelta
# ---- Constants ----
WAVEFORM_PLOT_ORDER = ["I", "II", "III", "V", "AVF", "AVL", "AVR"]  # Order to display waveforms in stack

# ---- Data Structures ----
class SubjectInfo(Dict):
    """
    Contains metadata for one subject (for display in subject drop-downs).
    """
    name: str
    n_annotations: int
    has_annotations: bool

# ---- Helper Function ----
def safe_h5_value(f, v):
    """
    Fully dereferences any h5py field, turning everything into a numpy array, float, or string.
    Must be called within open h5py.File context.
    """
    import h5py
    import numpy as np

    # Handle direct references (object refs, region refs)
    if isinstance(v, h5py.Reference):
        if not v:  # null reference
            return None
        return safe_h5_value(f, f[v])

    # Handle datasets
    if isinstance(v, h5py.Dataset):
        data = v[()]
        if isinstance(data, bytes):
            return data.decode()
        # If scalar
        if not hasattr(data, "shape") or data.shape == ():
            return data
        # If 1-element array
        if np.size(data) == 1:
            return data.item()
        # If array of objects (e.g., cell array of references)
        if data.dtype == object or data.dtype.kind == 'O':
            # Recursively deref each entry
            return np.array([safe_h5_value(f, d) for d in data.flat])
        return data

    # Handle numpy arrays (may be object or bytes)
    if isinstance(v, np.ndarray):
        if v.dtype == object:
            return np.array([safe_h5_value(f, d) for d in v.flat])
        if v.dtype.kind == 'S' or v.dtype.kind == 'U':
            # Convert bytes/strings
            return np.array([elem.decode() if isinstance(elem, bytes) else elem for elem in v.flat])
        if v.shape == ():
            return v.item()
        return v

    # Handle bytes
    if isinstance(v, bytes):
        return v.decode()

    # Anything else is likely a scalar
    return v

# ---- Base Folder/Subject/Annotation Logic ----

def list_subjects(base_folder: str) -> List[Dict]:
    """
    Scan the base_folder for subject directories. For each, count annotation CSVs (annotations*.csv).
    Returns a list of dicts: [{'name': subj, 'n_annotations': N, 'has_annotations': (N > 0)}]
    """
    subjects = []
    if not os.path.isdir(base_folder):
        return []
    for name in sorted(os.listdir(base_folder)):
        subj_path = os.path.join(base_folder, name)
        if not os.path.isdir(subj_path) or name.startswith('.'):
            continue
        annot_csvs = glob.glob(os.path.join(subj_path, 'annotation*.csv'))
        n_annot = len(annot_csvs)
        subjects.append({
            'name': name,
            'n_annotations': n_annot,
            'has_annotations': n_annot > 0,
        })
    return subjects

def list_subject_names(base_folder: str) -> List[str]:
    """
    Simpler version — just subject folder names, not metadata.
    """
    return [subj['name'] for subj in list_subjects(base_folder)]

def list_annotation_files(subject_folder: str) -> List[str]:
    """
    Returns list of annotation csvs in the subject folder.
    """
    return glob.glob(os.path.join(subject_folder, 'annotations*.csv'))

# ---- .mat Waveform Loading ----
def strip_nanoseconds(timestr):
    # Remove everything after :SS (including .micro, +00:00, etc.)
    match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', timestr)
    return match.group(1) if match else timestr  # fallback if no match

def datetime_string_to_seconds_since_1840(timestr):
    # Parse the date/time string (assume format is '%Y-%m-%d %H:%M:%S')
    dt = datetime.strptime(str(timestr), "%Y-%m-%d %H:%M:%S")
    # Your reference epoch ("zero") is 1840-12-31 00:00:00
    epoch = datetime(1840, 12, 31, 0, 0, 0)
    # Compute total seconds difference
    return (dt - epoch).total_seconds()

def get_code_time_bounds(subject, code_csv_path):
    # Load and filter the CSV for this subject
    code_df = pd.read_csv(code_csv_path)
    row = code_df[code_df['UUID'] == subject].iloc[0]

    recording_start = strip_nanoseconds(row['signal_start'])
    print(recording_start)
    code_start_time = strip_nanoseconds(row['CODE_START'])
    print(code_start_time)
    code_stop_time  = strip_nanoseconds(row['CODE_END'])
    print(code_stop_time)
    recording_start_sec = datetime_string_to_seconds_since_1840(recording_start)
    code_start_sec = datetime_string_to_seconds_since_1840(code_start_time)
    code_stop_sec  = datetime_string_to_seconds_since_1840(code_stop_time)

    return recording_start_sec, code_start_sec, code_stop_sec

def load_mat_data(filename: str) -> dict:
    """
    Loads MATLAB .mat file with hdf5storage (handles v7.3+ and older).
    Returns a dict as from loadmat: {fieldname: value, ...}
    """
    data = hdf5storage.loadmat(filename)
    # Remove MATLAB __header__ etc fields
    return {k: v for k, v in data.items() if not k.startswith("__")}

def load_waveforms_for_subject(
    base_folder: str, 
    subject: str,
    recording_start_sec: float = None,
    code_start_sec: float = None,
    code_stop_sec: float = None,
    desired_waveforms: list = ["I", "II", "III", "V", "AVF", "AVL", "AVR"]
):
    subj_path = os.path.join(base_folder, subject)
    mat_files = glob.glob(os.path.join(subj_path, "*.mat"))
    wf_files = {}
    for f in mat_files:
        name = os.path.basename(f)
        parts = name.replace(".mat", "").split("_")
        if len(parts) < 2:
            continue
        wf_short = parts[-1]
        wf_files[wf_short] = f

    times_list = []
    leads = []
    lead_names = []
    available_units = []
    lead_ranges = []
    start_secs = []  # keep in Epic seconds for alignment
    fs_list = []

    for wf in desired_waveforms:
        f = wf_files.get(wf, None)
        if f is None:
            leads.append(None)
            lead_names.append(wf)
            available_units.append("")
            times_list.append(np.array([]))
            lead_ranges.append((None, None))
            fs_list.append(None)
            start_secs.append(None)
            continue
        try:
            mat_data = load_mat_data(f)
            data = mat_data.get('data', None)
            Fs = mat_data.get('Fs', 1.0)
            UNIT = mat_data.get('UNIT', '')
            try:
                Fs = float(np.array(Fs).flatten()[0]) if Fs is not None else 1.0
            except Exception:
                Fs = 1.0
            try:
                if isinstance(UNIT, (np.ndarray, list)) and len(UNIT) > 0:
                    u = UNIT[0] if isinstance(UNIT, (list, np.ndarray)) else UNIT
                    UNIT = u.decode() if isinstance(u, bytes) else str(u)
                elif isinstance(UNIT, bytes):
                    UNIT = UNIT.decode()
                else:
                    UNIT = str(UNIT)
            except Exception:
                UNIT = str(UNIT)
            if data is not None:
                sig = np.array(data).flatten()
                # Get recording start Epic seconds:
                mat_start_val = mat_data.get('start_time', 0)
                if isinstance(mat_start_val, np.ndarray):
                    mat_start_sec = float(mat_start_val.flatten()[0])
                else:
                    mat_start_sec = float(mat_start_val)
                # use provided recording_start_sec if given, else use from mat
                rec_start_sec = float(recording_start_sec) if recording_start_sec is not None else mat_start_sec
                start_secs.append(rec_start_sec)
                fs_list.append(Fs)
                # For times array, just for ref (not used for slicing now)
                times = rec_start_sec + np.arange(len(sig)) / Fs
                lead_ranges.append((times[0], times[-1]))
            else:
                sig = None
                times = np.array([])
                lead_ranges.append((None, None))
                start_secs.append(None)
                fs_list.append(None)
            leads.append(sig)
            lead_names.append(wf)
            available_units.append(UNIT)
            times_list.append(times)
        except Exception as e:
            print(f"Error loading {f}: {e}")
            leads.append(None)
            lead_names.append(wf)
            available_units.append("")
            times_list.append(np.array([]))
            lead_ranges.append((None, None))
            start_secs.append(None)
            fs_list.append(None)

    # Subset range calculation in Epic seconds
    # Find the required range: intersection of available and desired
    valid_ranges = [(s, e) for s, e in lead_ranges if s is not None and e is not None]
    intersection_start = None
    intersection_end = None

    candidate_starts = [r[0] for r in valid_ranges]
    candidate_ends = [r[1] for r in valid_ranges]
    if code_start_sec is not None:
        candidate_starts.append(code_start_sec)
    if code_stop_sec is not None:
        candidate_ends.append(code_stop_sec)
    if candidate_starts:
        intersection_start = max(candidate_starts)
    if candidate_ends:
        intersection_end = min(candidate_ends)

    if intersection_start is None or intersection_end is None or intersection_end <= intersection_start:
        # return empty if no valid window
        return [np.array([]) for _ in desired_waveforms], [None for _ in desired_waveforms], lead_names, available_units

    # Now extract the correct segment for each available waveform
    for idx, (sig, rec_start_sec, Fs) in enumerate(zip(leads, start_secs, fs_list)):
        print(f'signal {idx}')
        if sig is None or rec_start_sec is None or Fs is None or len(sig) == 0:
            print('No Signal')
            times_list[idx] = np.array([])
            leads[idx] = None
            continue
        # start_sec and stop_sec RELATIVE TO EACH WAVEFORM'S START
        rel_start_offset = (intersection_start - rec_start_sec)
        rel_end_offset = (intersection_end - rec_start_sec)
        start_idx = int(np.floor(rel_start_offset * Fs))
        end_idx = int(np.ceil(rel_end_offset * Fs))
        n = len(sig)
        print(f'sig len {n}')
        start_idx = max(0, start_idx)
        print(f'start {start_idx}')
        end_idx = min(n, end_idx)
        print(f'start {end_idx}')
        if end_idx <= 0 or start_idx >= n or end_idx <= start_idx:
            times_list[idx] = np.array([])
            leads[idx] = None
        else:
            leads[idx] = sig[start_idx:end_idx]
            print(len(leads[idx]))
            times_list[idx] = rec_start_sec + np.arange(start_idx, end_idx) / Fs
            print(len(times_list[idx]))

    return times_list, leads, lead_names, available_units

def get_available_waveforms_for_subject(base_folder: str, subject: str) -> List[str]:
    """
    Returns a list of available waveform short names in the folder.
    """
    subj_path = os.path.join(base_folder, subject)
    mat_files = glob.glob(os.path.join(subj_path, "*.mat"))
    names = []
    for f in mat_files:
        parts = os.path.basename(f).replace(".mat", "").split("_")
        if len(parts) >= 2:
            names.append(parts[-1])
    return sorted(names)

# ---- Annotation loading/saving ----

def load_annotations_csv(subject_folder: str) -> Optional[pd.DataFrame]:
    """
    Loads the first annotations CSV in a subject folder.
    Returns a DataFrame, or None if not found.
    """
    csvs = list_annotation_files(subject_folder)
    if not csvs:
        return None
    return pd.read_csv(csvs[0])

def save_annotations_csv(
    subject_folder: str, data: List[Dict], name_prefix: str = "annotations"
) -> str:
    """
    Save annotations as a CSV file in the subject folder. Returns the file path.
    """
    import datetime
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{name_prefix}_{now}.csv"
    fpath = os.path.join(subject_folder, fname)
    pd.DataFrame(data).to_csv(fpath, index=False)
    return fpath

# ---- Utility ----
def subject_folder(base_folder: str, subject: str) -> str:
    """Returns full path to the subject's folder given base and name."""
    return os.path.join(base_folder, subject)