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
        annot_csvs = glob.glob(os.path.join(subj_path, 'annotations*.csv'))
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
    desired_waveforms: list = ["I", "II", "III", "V", "AVF", "AVL", "AVR"]
):
    import glob
    import numpy as np
    import os

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

    for wf in desired_waveforms:
        f = wf_files.get(wf, None)
        if f is None:
            leads.append(None)
            lead_names.append(wf)
            available_units.append("")
            continue
        try:
            start_wf = time.time()
            print(f"Loading waveform {wf}: file={f}")
            mat_data = load_mat_data(f)
            data = mat_data.get('data', None)  # Should already be a numpy array
            Fs = mat_data.get('Fs', 1.0)
            UNIT = mat_data.get('UNIT', '')
            # Convert Fs and UNIT as in the previous robust version
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
                times = np.arange(len(sig)) / Fs
            else:
                sig = None
                times = np.array([])
            times_list.append(times)
            leads.append(sig)
            lead_names.append(wf)
            available_units.append(UNIT)
            print(f"Finished waveform {wf} in {time.time() - start_wf:.2f} seconds")
        except Exception as e:
            print(f"Error loading {f}: {e}")
            leads.append(None)
            lead_names.append(wf)
            available_units.append("")
    default_times = next((t for t in times_list if len(t)), np.array([0]))
    return default_times, leads, lead_names, available_units

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