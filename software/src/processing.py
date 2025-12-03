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
from zoneinfo import ZoneInfo
from dateutil import parser
import pytz
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

def datetime_string_to_seconds_since_1970(timestr):
    eastern = pytz.timezone("America/New_York")
    dt_naive = datetime.strptime(timestr, "%Y-%m-%d %H:%M:%S")
    dt_eastern = eastern.localize(dt_naive)
    # Get UTC timestamp (seconds since 1970-01-01 UTC)
    epoch_seconds = dt_eastern.timestamp()
    return epoch_seconds

def convert_utc_to_est(date_str):
    # Parse as naive datetime
    dt_naive = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    # Attach UTC timezone
    dt_utc = dt_naive.replace(tzinfo=ZoneInfo('UTC'))
    # Convert to Eastern Time
    dt_est = dt_utc.astimezone(ZoneInfo("America/New_York"))
    return dt_est.strftime('%Y-%m-%d %H:%M:%S')

def get_code_time_bounds(subject, code_csv_path):
    # Load and filter CSV for this subject
    code_df = pd.read_csv(code_csv_path)
    df_subj = code_df[code_df['UUID'] == subject]

    def _get_timestamps(column):
        vals = df_subj[column].dropna().unique()
        # Remove empty strings if present
        vals = [v for v in vals if str(v).strip() != ""]
        return [strip_nanoseconds(v) for v in vals if v is not None]

    # Gather timestamps for each field
    signal_starts = _get_timestamps('signal_start')
    signal_ends = _get_timestamps('signal_end')
    print(f'nonconverted start:{signal_starts}')
    print(f'nonconverted end:{signal_ends}')
    # Change from UTC to EST
    signal_starts = [convert_utc_to_est(t) for t in signal_starts if t]
    signal_ends = [convert_utc_to_est(t) for t in signal_ends if t]
    print(f'converted start:{signal_starts}')
    print(f'converted end:{signal_ends}')
    code_starts   = _get_timestamps('CODE_START')
    code_ends     = _get_timestamps('CODE_END')

    signal_start_secs = [datetime_string_to_seconds_since_1970(t) for t in signal_starts if t]
    signal_ends_secs = [datetime_string_to_seconds_since_1970(t) for t in signal_ends if t]
    code_start_secs   = [datetime_string_to_seconds_since_1970(t) for t in code_starts   if t]
    code_end_secs     = [datetime_string_to_seconds_since_1970(t) for t in code_ends     if t]

    # Print warnings if multiple distinct values for any time field
    if len(set(signal_start_secs)) > 1:
        print(f"WARNING: Multiple unique signal_start times for subject [{subject}]: {sorted(signal_start_secs)}")
    if len(set(signal_ends_secs)) > 1:
        print(f"WARNING: Multiple unique signal_end times for subject [{subject}]: {sorted(signal_ends_secs)}")
    if len(set(code_start_secs)) > 1:
        print(f"WARNING: Multiple unique CODE_START times for subject [{subject}]: {sorted(code_start_secs)}")
    if len(set(code_end_secs)) > 1:
        print(f"WARNING: Multiple unique CODE_END times for subject [{subject}]: {sorted(code_end_secs)}")

    # Earliest start/rec start, earliest code start, latest code end
    recording_start_sec = min(signal_start_secs) if signal_start_secs else None
    recording_end_sec = max(signal_ends_secs) if signal_ends_secs else None
    code_start_sec = min(code_start_secs) if code_start_secs else None
    code_stop_sec  = max(code_end_secs)  if code_end_secs   else None

    print("Recording start Date:", signal_starts)
    print("Recording start Sec:", recording_start_sec)
    print("Recording End Date:", signal_ends)
    print("Recording End Sec:", recording_end_sec)

    print("Code start Date:", code_starts)
    print("Code start Sec:", code_start_sec)
    print("Code stop Date:", code_ends)
    print("Code stop Sec:", code_stop_sec)

    return recording_start_sec, recording_end_sec, code_start_sec, code_stop_sec

def get_events_for_window(manifest_path, subject, window_start, window_end):
    """
    Loads and returns a DataFrame of rows for the given subject and window.
        - window_start, window_end: seconds since origin (EPIC or relative to data; match x axis)
    """
    df = pd.read_csv(manifest_path)
    df_subj = df[df['UUID'] == subject].copy()
    df_subj['event_sec'] = df_subj['RECORDED_TIME'].apply(datetime_string_to_seconds_since_1970)
    # # Filter to the correct window
    # df_subj = df_subj[(df_subj['event_sec'] >= window_start) & (df_subj['event_sec'] <= window_end)]
    return df_subj

def load_mat_data(filename: str) -> dict:
    """
    Loads a MATLAB v7.3+ .mat file using h5py.
    Returns a dict mapping {fieldname: value, ...},
    dereferencing cell arrays automatically,
    and excluding MATLAB fields starting with "__".
    """

    def extract_dataset(item, file_reference):
        # Handle standard arrays
        val = item[()]
        # If it's a cell array (object references)
        if item.dtype == object:
            # Dereference all object refs within the cell array
            deref_vals = [file_reference[ref][()] for ref in val.flat]
            # Convert each dereferenced value to a scalar if possible
            deref_vals = [v.item() if hasattr(v, "item") else v for v in deref_vals]
            val = np.array(deref_vals, dtype=object).reshape(val.shape)
            # Squeeze if it's a single value (1x1 cell)
            if val.size == 1:
                val = val.item()
        else:
            # For standard arrays, if shape is (), convert to scalar
            if hasattr(val, "item") and val.shape == ():
                val = val.item()
        return val

    def recursively_load(group, file_reference):
        out = {}
        for key in group:
            if key.startswith("__"):  # skip MATLAB private fields
                continue
            item = group[key]
            if isinstance(item, h5py.Dataset):
                out[key] = extract_dataset(item, file_reference)
            elif isinstance(item, h5py.Group):
                out[key] = recursively_load(item, file_reference)
        return out

    # Do all extraction in the same open file context
    with h5py.File(filename, "r", locking=False) as f:
        data = {}
        for key in f:
            if key.startswith("__"):  # skip MATLAB private fields
                continue
            item = f[key]
            if isinstance(item, h5py.Dataset):
                data[key] = extract_dataset(item, f)
            elif isinstance(item, h5py.Group):
                data[key] = recursively_load(item, f)
    return data

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
    start_secs = []
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
            data = mat_data['data']
            Fs = mat_data['Fs']
            UNIT = mat_data['unit']
            try:
                Fs = float(np.array(Fs).flatten()[0]) if Fs is not None else 240
            except Exception:
                print('sampling exception')
                Fs = 240.0
            try:
                if isinstance(UNIT, (np.ndarray, list)) and len(UNIT) > 0:
                    u = UNIT[0] if isinstance(UNIT, (list, np.ndarray)) else UNIT
                    UNIT = u.decode() if isinstance(u, bytes) else str(u)
                elif isinstance(UNIT, bytes):
                    UNIT = UNIT.decode()
                else:
                    UNIT = str(UNIT)
            except Exception:
                UNIT = 'NoUnitSpecified'
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
        return {
            'times_ds': [np.array([]) for _ in desired_waveforms],   # or just np.array([]) depending on context
            'leads_ds': [None for _ in desired_waveforms],
            'lead_names': lead_names,
            'units': available_units,
            'Fs': None
        }

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

    for tarr in times_list:
        if tarr is not None and len(tarr) > 0:
            canonical_time = tarr
            break
    else:
        canonical_time = np.array([])

    # Downsampling settings
    desired_fs = 120.0
    downsample_factor = int(np.round(Fs / desired_fs))

    # Downsample the canonical time axis
    time_axis_ds = canonical_time[::downsample_factor] if canonical_time.size else np.array([])

    # Downsample each lead to 80 Hz
    leads_ds = []
    for sig in leads:
        if sig is not None and len(sig) > 0:
            leads_ds.append(sig[::downsample_factor])
        else:
            leads_ds.append(np.array([]))
    
    print('Return values from Loading...')
    print(time_axis_ds)
    print(leads_ds)
    print(lead_names)
    print(available_units)
    print(Fs)
    result = {
        'times_ds': time_axis_ds,
        'leads_ds': leads_ds,
        'lead_names': lead_names,
        'units': available_units,
        'Fs': Fs
    }
    # return time_axis_ds, leads_ds, lead_names, available_units, Fs
    return result

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