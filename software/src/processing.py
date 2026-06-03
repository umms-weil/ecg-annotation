import os
import glob
import re
from typing import List, Dict, Tuple, Optional, Union

os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

import numpy as np
import pandas as pd
import h5py

from datetime import datetime
from zoneinfo import ZoneInfo
import pytz


# =============================================================================
# Constants
# =============================================================================

WAVEFORM_PLOT_ORDER = ["I", "II", "III", "V", "AVF", "AVL", "AVR"]

H5_TIME_DATASET = "time_epoch_s"
H5_SIGNALS_GROUP = "signals"

DESIRED_FS_DEFAULT = 120.0

SIGNAL_ALIASES = {
    "I": ["I", "LEAD I", "ECG I"],
    "II": ["II", "LEAD II", "ECG II"],
    "III": ["III", "LEAD III", "ECG III"],
    "V": ["V", "LEAD V", "ECG V"],
    "AVF": ["AVF", "aVF", "LEAD AVF", "LEAD aVF"],
    "AVL": ["AVL", "aVL", "LEAD AVL", "LEAD aVL"],
    "AVR": ["AVR", "aVR", "LEAD AVR", "LEAD aVR"],
}


# =============================================================================
# Data structures
# =============================================================================

class SubjectInfo(Dict):
    """
    Contains metadata for one subject or waveform record.

    This is used for display in the subject dropdown.
    """
    name: str
    n_annotations: int
    has_annotations: bool


# =============================================================================
# General helpers
# =============================================================================

def normalize_signal_key(value: str) -> str:
    """
    Normalize a signal name for robust matching.

    Examples
    --------
    ``"Lead aVF"`` -> ``"LEADAVF"``
    ``"aVF"`` -> ``"AVF"``
    """
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def normalize_epoch_seconds(time_values: np.ndarray) -> np.ndarray:
    """
    Normalize epoch timestamps to seconds.

    Some input files may contain epoch milliseconds even when the variable name
    implies seconds. This detects milliseconds by magnitude.

    Parameters
    ----------
    time_values : np.ndarray
        Numeric timestamp vector.

    Returns
    -------
    np.ndarray
        Epoch timestamps in seconds.
    """
    t = np.asarray(time_values, dtype="float64")
    finite = t[np.isfinite(t)]

    if finite.size == 0:
        return t

    median_val = np.nanmedian(finite)

    # Epoch seconds are around 1.7e9. Epoch milliseconds are around 1.7e12.
    if median_val > 1e11:
        t = t / 1000.0

    return t


def h5_attr_to_str(attrs, key: str, default: str = "") -> str:
    """
    Safely read string-like HDF5 attributes.
    """
    if key not in attrs:
        return default

    val = attrs[key]

    if isinstance(val, bytes):
        return val.decode()

    return str(val)


def h5_attr_to_float(attrs, key: str, default: Optional[float] = None) -> Optional[float]:
    """
    Safely read float-like HDF5 attributes.
    """
    if key not in attrs:
        return default

    try:
        return float(attrs[key])
    except Exception:
        return default


def _estimate_fs_from_time(time_axis: np.ndarray, default_fs: float = 240.0) -> float:
    """
    Estimate sampling frequency from a time vector.
    """
    if time_axis is None or len(time_axis) < 2:
        return default_fs

    dt = np.nanmedian(np.diff(time_axis))

    if not np.isfinite(dt) or dt <= 0:
        return default_fs

    return float(1.0 / dt)


def _empty_waveform_result(desired_waveforms: List[str]) -> Dict:
    """
    Return an empty waveform result compatible with plotting callbacks.
    """
    return {
        "times_ds": np.array([]),
        "leads_ds": [np.array([]) for _ in desired_waveforms],
        "lead_names": list(desired_waveforms),
        "units": ["" for _ in desired_waveforms],
        "Fs": None,
    }


def _is_annotation_csv(path: str) -> bool:
    """
    Return True if a CSV appears to be an annotation or manifest file rather
    than waveform data.
    """
    name = os.path.basename(path).lower()
    return (
        name.startswith("annotation")
        or name.startswith("annotations")
        or name.endswith("_complete.csv")
        or "waveform_manifest" in name
    )


def _count_annotations_in_output(output_path: str) -> Tuple[int, int]:
    """
    Count total and complete annotation CSVs inside an output directory.

    Supports both:

    - ``output/*.csv``
    - ``output/user/*.csv``

    Parameters
    ----------
    output_path : str
        Path to output folder.

    Returns
    -------
    tuple[int, int]
        ``(total_annotations, complete_annotations)``
    """
    total_annotations = 0
    complete_annotations = 0

    if not os.path.isdir(output_path):
        return total_annotations, complete_annotations

    # Direct annotation files.
    direct_csvs = [
        f for f in os.listdir(output_path)
        if f.endswith(".csv") and f.startswith("annotations")
    ]

    total_annotations += len(direct_csvs)
    complete_annotations += sum(1 for f in direct_csvs if f.endswith("_COMPLETE.csv"))

    # User subfolders.
    for child in os.listdir(output_path):
        child_path = os.path.join(output_path, child)

        if not os.path.isdir(child_path):
            continue

        csvs = [
            f for f in os.listdir(child_path)
            if f.endswith(".csv") and f.startswith("annotations")
        ]

        total_annotations += len(csvs)
        complete_annotations += sum(1 for f in csvs if f.endswith("_COMPLETE.csv"))

    return total_annotations, complete_annotations


# =============================================================================
# Time parsing helpers
# =============================================================================

def strip_nanoseconds(timestr):
    """
    Remove fractional seconds, timezone suffixes, or nanosecond components from
    a timestamp string.

    Keeps only ``YYYY-MM-DD HH:MM:SS`` when possible.
    """
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", str(timestr))
    return match.group(1) if match else timestr


def datetime_string_to_seconds_since_1970(timestr):
    """
    Convert a naive Eastern Time datetime string to UTC epoch seconds.

    Expected format
    ---------------
    ``YYYY-MM-DD HH:MM:SS``
    """
    eastern = pytz.timezone("America/New_York")
    dt_naive = datetime.strptime(str(timestr), "%Y-%m-%d %H:%M:%S")
    dt_eastern = eastern.localize(dt_naive)
    return dt_eastern.timestamp()


def convert_utc_to_est(date_str):
    """
    Convert a UTC datetime string to America/New_York local time string.

    Expected input format
    ---------------------
    ``YYYY-MM-DD HH:MM:SS``
    """
    dt_naive = datetime.strptime(str(date_str), "%Y-%m-%d %H:%M:%S")
    dt_utc = dt_naive.replace(tzinfo=ZoneInfo("UTC"))
    dt_est = dt_utc.astimezone(ZoneInfo("America/New_York"))
    return dt_est.strftime("%Y-%m-%d %H:%M:%S")


def _extract_time_epoch_s(df: pd.DataFrame) -> Tuple[np.ndarray, str]:
    """
    Extract per-sample UTC epoch seconds vector from a DataFrame.

    Preference:

    1. Use ``time`` column if present.
    2. Otherwise use numeric index.

    Returns
    -------
    tuple[np.ndarray, str]
        ``(time_epoch_s, source)`` where source is ``"column"`` or ``"index"``.
    """
    if "time" in df.columns:
        s = pd.to_numeric(df["time"], errors="coerce")
        return s.to_numpy(dtype="float64"), "column"

    s = pd.to_numeric(pd.Series(df.index), errors="coerce")
    return s.to_numpy(dtype="float64"), "index"


# =============================================================================
# Subject / waveform discovery
# =============================================================================

def list_subjects(base_folder: str) -> List[Dict]:
    """
    Discover loadable waveform records in a base folder.

    Supports recursive H5 layout such as:

        base_folder/
            mrnnumber/
                <NA>/
                    GEVITAL/
                        file1.h5
                        file2.h5
                    metadata_*.json

    Each H5 file becomes one selectable dropdown item.

    Also supports old MAT layout:

        base_folder/
            subject/
                *_I.mat
                *_II.mat

    Returns
    -------
    list[dict]
        Each dict represents one selectable waveform file/session.

        Common keys:
        - name
        - subject
        - encounter
        - namespace
        - file_tag
        - kind
        - h5_path
        - subject_path
        - encounter_path
        - output_path
        - n_annotations
        - n_complete_annotations
        - has_annotations
    """
    records: List[Dict] = []

    if not os.path.isdir(base_folder):
        return records

    for subject_name in sorted(os.listdir(base_folder)):
        if subject_name.startswith("."):
            continue

        subject_path = os.path.join(base_folder, subject_name)

        if not os.path.isdir(subject_path):
            continue

        # ------------------------------------------------------------------
        # Recursive H5 discovery
        # ------------------------------------------------------------------
        for root, dirs, files in os.walk(subject_path):
            # Do not search annotation output folders or hidden/system folders.
            dirs[:] = [
                d for d in dirs
                if d not in {"output", "__pycache__"} and not d.startswith(".")
            ]

            h5_files = sorted(
                f for f in files
                if f.lower().endswith(".h5") and not f.startswith(".")
            )

            for h5_file in h5_files:
                h5_path = os.path.join(root, h5_file)
                h5_stem = os.path.splitext(h5_file)[0]

                # Relative path under subject.
                # Example:
                #   root = base/mrnnumber/<NA>/GEVITAL
                #   rel_dir = <NA>/GEVITAL
                rel_dir = os.path.relpath(root, subject_path)
                rel_parts = rel_dir.split(os.sep)

                # For your current structure:
                #   rel_parts[0] -> <NA>
                #   rel_parts[-1] -> GEVITAL
                encounter = rel_parts[0] if len(rel_parts) >= 1 and rel_parts[0] != "." else ""
                namespace = rel_parts[-1] if len(rel_parts) >= 1 and rel_parts[-1] != "." else ""

                # Default metadata if H5 attrs are unavailable.
                patient_label = subject_name
                encounter_label = encounter
                window_tag = ""
                file_tag = h5_stem

                # Read only lightweight H5 attrs. Do not load waveform arrays.
                try:
                    with h5py.File(h5_path, "r", locking=False) as f:
                        patient_label = h5_attr_to_str(
                            f.attrs,
                            "patient_label",
                            subject_name,
                        )
                        encounter_label = h5_attr_to_str(
                            f.attrs,
                            "encounter_label",
                            encounter,
                        )
                        namespace = h5_attr_to_str(
                            f.attrs,
                            "namespace",
                            namespace,
                        )
                        window_tag = h5_attr_to_str(
                            f.attrs,
                            "window_tag",
                            "",
                        )
                        file_tag = h5_attr_to_str(
                            f.attrs,
                            "file_tag",
                            h5_stem,
                        )
                except Exception as e:
                    print(f"WARNING: Could not read attrs from {h5_path}: {e}")

                # Use a per-H5 output folder so multiple H5 files for the same
                # subject/encounter/namespace do not collide.
                #
                # Example:
                #   .../<NA>/GEVITAL/output/<h5_stem>/<user>/annotations...
                output_path = os.path.join(root, "output", h5_stem)

                total_annotations, complete_annotations = _count_annotations_in_output(
                    output_path
                )

                label_parts = [
                    subject_name,
                    encounter_label,
                    namespace,
                    file_tag,
                ]

                display_name = " | ".join(
                    str(x) for x in label_parts if str(x).strip()
                )

                records.append(
                    {
                        "name": display_name,
                        "subject": subject_name,
                        "encounter": encounter_label,
                        "namespace": namespace,
                        "window_tag": window_tag,
                        "file_tag": file_tag,
                        "kind": "h5",
                        "h5_path": h5_path,
                        "subject_path": subject_path,
                        "encounter_path": root,
                        "output_path": output_path,
                        "n_annotations": total_annotations,
                        "n_complete_annotations": complete_annotations,
                        "has_annotations": total_annotations > 0,
                    }
                )

        # ------------------------------------------------------------------
        # Old MAT fallback
        # ------------------------------------------------------------------
        mat_files = sorted(glob.glob(os.path.join(subject_path, "*.mat")))

        if mat_files:
            subject_output_path = os.path.join(subject_path, "output")
            total_annotations, complete_annotations = _count_annotations_in_output(
                subject_output_path
            )

            records.append(
                {
                    "name": subject_name,
                    "subject": subject_name,
                    "encounter": "",
                    "namespace": "",
                    "window_tag": "",
                    "file_tag": "",
                    "kind": "mat",
                    "subject_path": subject_path,
                    "encounter_path": subject_path,
                    "output_path": subject_output_path,
                    "n_annotations": total_annotations,
                    "n_complete_annotations": complete_annotations,
                    "has_annotations": total_annotations > 0,
                }
            )

    return records


def list_subject_names(base_folder: str) -> List[str]:
    """
    Return display names for discovered waveform records.
    """
    return [subj["name"] for subj in list_subjects(base_folder)]


def list_annotation_files(subject_folder: str) -> List[str]:
    """
    Returns annotation CSV files in a subject folder.
    """
    return glob.glob(os.path.join(subject_folder, "annotations*.csv"))


# =============================================================================
# Code / event bounds
# =============================================================================

def get_events_for_window(manifest_path, subject, window_start, window_end):
    """
    Load and return flowsheet/event rows for the given subject.

    Parameters
    ----------
    manifest_path : str
        Path to manifest CSV.
    subject : str
        Subject UUID.
    window_start : float
        Start timestamp in epoch seconds.
    window_end : float
        End timestamp in epoch seconds.

    Returns
    -------
    pd.DataFrame
        Subject-specific event rows with ``event_sec`` column.
    """
    df = pd.read_csv(manifest_path)
    df_subj = df[df["UUID"] == subject].copy()
    df_subj["event_sec"] = df_subj["RECORDED_TIME"].apply(
        datetime_string_to_seconds_since_1970
    )

    # Uncomment if you want strict event filtering:
    # df_subj = df_subj[
    #     (df_subj["event_sec"] >= window_start)
    #     & (df_subj["event_sec"] <= window_end)
    # ]

    return df_subj


def get_code_time_bounds(subject, code_csv_path, manifest_path=None):
    """
    Determine recording/code time bounds for a subject.

    Rules
    -----
    - Normally use CODE_START and CODE_END.
    - If CODE_END is missing, use CODE_START + 2 hours.
    - If CODE_START is missing, use first flowsheet event.
    - If both are missing, use first flowsheet event and 2 hours.
    - If none are available, return None code bounds.
    - Add 30 minutes before and after the selected code window.

    Returns
    -------
    tuple
        ``(recording_start_sec, recording_end_sec, final_start, final_end)``
    """
    code_df = pd.read_csv(code_csv_path)
    df_subj = code_df[code_df["UUID"] == subject]

    def _get_timestamps(column):
        vals = df_subj[column].dropna().unique()
        vals = [v for v in vals if str(v).strip() != ""]
        return [strip_nanoseconds(v) for v in vals if v is not None]

    signal_starts = _get_timestamps("signal_start")
    signal_ends = _get_timestamps("signal_end")

    print(f"nonconverted start:{signal_starts}")
    print(f"nonconverted end:{signal_ends}")

    signal_starts = [convert_utc_to_est(t) for t in signal_starts if t]
    signal_ends = [convert_utc_to_est(t) for t in signal_ends if t]

    print(f"converted start:{signal_starts}")
    print(f"converted end:{signal_ends}")

    code_starts = _get_timestamps("CODE_START")
    code_ends = _get_timestamps("CODE_END")

    signal_start_secs = [
        datetime_string_to_seconds_since_1970(t) for t in signal_starts if t
    ]
    signal_ends_secs = [
        datetime_string_to_seconds_since_1970(t) for t in signal_ends if t
    ]
    code_start_secs = [
        datetime_string_to_seconds_since_1970(t) for t in code_starts if t
    ]
    code_end_secs = [
        datetime_string_to_seconds_since_1970(t) for t in code_ends if t
    ]

    if len(set(signal_start_secs)) > 1:
        print(
            f"WARNING: Multiple unique signal_start times for subject [{subject}]: "
            f"{sorted(signal_start_secs)}"
        )
    if len(set(signal_ends_secs)) > 1:
        print(
            f"WARNING: Multiple unique signal_end times for subject [{subject}]: "
            f"{sorted(signal_ends_secs)}"
        )
    if len(set(code_start_secs)) > 1:
        print(
            f"WARNING: Multiple unique CODE_START times for subject [{subject}]: "
            f"{sorted(code_start_secs)}"
        )
    if len(set(code_end_secs)) > 1:
        print(
            f"WARNING: Multiple unique CODE_END times for subject [{subject}]: "
            f"{sorted(code_end_secs)}"
        )

    recording_start_sec = min(signal_start_secs) if signal_start_secs else None
    recording_end_sec = max(signal_ends_secs) if signal_ends_secs else None
    code_start_sec = min(code_start_secs) if code_start_secs else None
    code_stop_sec = max(code_end_secs) if code_end_secs else None

    print("Recording start Date:", signal_starts)
    print("Recording start Sec:", recording_start_sec)
    print("Recording End Date:", signal_ends)
    print("Recording End Sec:", recording_end_sec)

    print("Code start Date:", code_starts)
    print("Code start Sec:", code_start_sec)
    print("Code stop Date:", code_ends)
    print("Code stop Sec:", code_stop_sec)

    if code_start_sec is not None and code_stop_sec is None:
        print("No CODE_END found, using 2 hours after CODE_START.")
        code_stop_sec = code_start_sec + 2 * 3600

    flowsheet_first_sec = None

    if code_start_sec is None and manifest_path is not None:
        events_df = get_events_for_window(
            manifest_path, subject, window_start=0, window_end=float("inf")
        )

        if not events_df.empty:
            flowsheet_first_sec = events_df["event_sec"].min()
            print(
                "No CODE_START found, using first flowsheet event as CODE_START: "
                f"{flowsheet_first_sec}"
            )
            code_start_sec = flowsheet_first_sec

            if code_stop_sec is None:
                print(
                    "No CODE_END found, using 2 hours after first flowsheet event as CODE_END."
                )
                code_stop_sec = code_start_sec + 2 * 3600
        else:
            print("No CODE_START or flowsheet events found for subject:", subject)

    if code_start_sec is None or code_stop_sec is None:
        if flowsheet_first_sec is None and manifest_path is not None:
            events_df = get_events_for_window(
                manifest_path, subject, window_start=0, window_end=float("inf")
            )

            if not events_df.empty:
                flowsheet_first_sec = events_df["event_sec"].min()
                print(f"Using first flowsheet event as CODE_START: {flowsheet_first_sec}")
                code_start_sec = flowsheet_first_sec
                code_stop_sec = code_start_sec + 2 * 3600
            else:
                print(
                    f"ERROR: Could not find CODE_START, CODE_END, or any flowsheet "
                    f"events for subject {subject}."
                )
                return recording_start_sec, recording_end_sec, None, None
        else:
            print(
                f"ERROR: Could not find CODE_START, CODE_END, or any flowsheet "
                f"events for subject {subject}."
            )
            return recording_start_sec, recording_end_sec, None, None

    final_start = code_start_sec - 1800
    final_end = code_stop_sec + 1800

    print("Final code window (with buffer):")
    print("  Code+buffer Start:", final_start)
    print("  Code+buffer End  :", final_end)

    return recording_start_sec, recording_end_sec, final_start, final_end


# =============================================================================
# MATLAB/HDF5 MAT helpers
# =============================================================================

def safe_h5_value(f, v):
    """
    Fully dereference HDF5/MATLAB values into Python/numpy objects.

    Must be called inside an open ``h5py.File`` context.
    """
    if isinstance(v, h5py.Reference):
        if not v:
            return None
        return safe_h5_value(f, f[v])

    if isinstance(v, h5py.Dataset):
        data = v[()]

        if isinstance(data, bytes):
            return data.decode()

        if not hasattr(data, "shape") or data.shape == ():
            return data

        if np.size(data) == 1:
            return data.item()

        if data.dtype == object or data.dtype.kind == "O":
            return np.array([safe_h5_value(f, d) for d in data.flat])

        return data

    if isinstance(v, np.ndarray):
        if v.dtype == object:
            return np.array([safe_h5_value(f, d) for d in v.flat])

        if v.dtype.kind in {"S", "U"}:
            return np.array(
                [elem.decode() if isinstance(elem, bytes) else elem for elem in v.flat]
            )

        if v.shape == ():
            return v.item()

        return v

    if isinstance(v, bytes):
        return v.decode()

    return v


def load_mat_data(filename: str) -> dict:
    """
    Load a MATLAB v7.3+ MAT file using h5py.

    Returns a nested dict mapping field names to values.
    """

    def extract_dataset(item, file_reference):
        val = item[()]

        if item.dtype == object:
            deref_vals = [file_reference[ref][()] for ref in val.flat]
            deref_vals = [v.item() if hasattr(v, "item") else v for v in deref_vals]
            val = np.array(deref_vals, dtype=object).reshape(val.shape)

            if val.size == 1:
                val = val.item()

        else:
            if hasattr(val, "item") and getattr(val, "shape", None) == ():
                val = val.item()

        return val

    def recursively_load(group, file_reference):
        out = {}

        for key in group:
            if key.startswith("__"):
                continue

            item = group[key]

            if isinstance(item, h5py.Dataset):
                out[key] = extract_dataset(item, file_reference)
            elif isinstance(item, h5py.Group):
                out[key] = recursively_load(item, file_reference)

        return out

    with h5py.File(filename, "r", locking=False) as f:
        data = {}

        for key in f:
            if key.startswith("__"):
                continue

            item = f[key]

            if isinstance(item, h5py.Dataset):
                data[key] = extract_dataset(item, f)
            elif isinstance(item, h5py.Group):
                data[key] = recursively_load(item, f)

    return data


# =============================================================================
# H5 bundle loading
# =============================================================================

def build_h5_signal_lookup(h5_file: h5py.File) -> Dict[str, str]:
    """
    Build lookup from normalized signal names to stored H5 signal IDs.
    """
    lookup: Dict[str, str] = {}

    if H5_SIGNALS_GROUP not in h5_file:
        return lookup

    signals_group = h5_file[H5_SIGNALS_GROUP]

    for stored_signal_id in signals_group.keys():
        signal_group = signals_group[stored_signal_id]

        lookup[normalize_signal_key(stored_signal_id)] = stored_signal_id

        attr_signal_id = h5_attr_to_str(signal_group.attrs, "signal_id", "")

        if attr_signal_id:
            lookup[normalize_signal_key(attr_signal_id)] = stored_signal_id

        display_name = h5_attr_to_str(signal_group.attrs, "display_name", "")

        if display_name:
            lookup[normalize_signal_key(display_name)] = stored_signal_id

    return lookup


def resolve_signal_id(desired_name: str, lookup: Dict[str, str]) -> Optional[str]:
    """
    Resolve desired app lead name to stored signal identifier.
    """
    desired_norm = normalize_signal_key(desired_name)

    if desired_norm in lookup:
        return lookup[desired_norm]

    for alias in SIGNAL_ALIASES.get(desired_name, []):
        alias_norm = normalize_signal_key(alias)

        if alias_norm in lookup:
            return lookup[alias_norm]

    return None


def load_waveforms_from_h5(
    h5_path: str,
    code_start_sec: Optional[float] = None,
    code_stop_sec: Optional[float] = None,
    desired_waveforms: List[str] = WAVEFORM_PLOT_ORDER,
    desired_fs: float = DESIRED_FS_DEFAULT,
) -> Dict:
    """
    Load waveform data from bundled H5 format.

    Expected H5 structure
    ---------------------
    ::

        /time_epoch_s
        /signals/<signal_id>/values
    """
    if not os.path.exists(h5_path):
        raise FileNotFoundError(f"H5 file not found: {h5_path}")

    with h5py.File(h5_path, "r", locking=False) as f:
        if H5_TIME_DATASET not in f:
            raise KeyError(f"Missing dataset '/{H5_TIME_DATASET}' in {h5_path}")

        time_axis = normalize_epoch_seconds(f[H5_TIME_DATASET][:])

        if time_axis.size == 0:
            return _empty_waveform_result(desired_waveforms)

        sort_idx = None

        if np.any(np.diff(time_axis) < 0):
            print(f"WARNING: time vector not sorted in {h5_path}; sorting.")
            sort_idx = np.argsort(time_axis)
            time_axis = time_axis[sort_idx]

        file_start = float(time_axis[0])
        file_stop = float(time_axis[-1])

        window_start = float(code_start_sec) if code_start_sec is not None else file_start
        window_stop = float(code_stop_sec) if code_stop_sec is not None else file_stop

        window_start = max(window_start, file_start)
        window_stop = min(window_stop, file_stop)

        if window_stop <= window_start:
            return _empty_waveform_result(desired_waveforms)

        i0 = int(np.searchsorted(time_axis, window_start, side="left"))
        i1 = int(np.searchsorted(time_axis, window_stop, side="right"))

        i0 = max(0, i0)
        i1 = min(time_axis.size, i1)

        if i1 <= i0:
            return _empty_waveform_result(desired_waveforms)

        time_window = time_axis[i0:i1]

        fs_est = _estimate_fs_from_time(time_window, default_fs=240.0)
        downsample_factor = max(1, int(np.round(fs_est / desired_fs)))

        time_ds = time_window[::downsample_factor]

        signal_lookup = build_h5_signal_lookup(f)

        leads_ds: List[np.ndarray] = []
        lead_names: List[str] = []
        units: List[str] = []

        for desired in desired_waveforms:
            stored_signal_id = resolve_signal_id(desired, signal_lookup)

            if stored_signal_id is None:
                leads_ds.append(np.array([]))
                lead_names.append(desired)
                units.append("")
                continue

            signal_group = f[H5_SIGNALS_GROUP][stored_signal_id]

            if "values" not in signal_group:
                leads_ds.append(np.array([]))
                lead_names.append(desired)
                units.append("")
                continue

            values_ds = signal_group["values"]

            if sort_idx is None:
                sig_window = values_ds[i0:i1]
            else:
                full_sig = values_ds[:]
                full_sig = full_sig[sort_idx]
                sig_window = full_sig[i0:i1]

            sig_ds = np.asarray(sig_window, dtype="float32")[::downsample_factor]

            unit = h5_attr_to_str(signal_group.attrs, "units", "")

            leads_ds.append(sig_ds)
            lead_names.append(desired)
            units.append(unit)

        return {
            "times_ds": time_ds,
            "leads_ds": leads_ds,
            "lead_names": lead_names,
            "units": units,
            "Fs": fs_est,
            "source_type": "h5",
            "source_path": h5_path,
        }


# =============================================================================
# CSV waveform loading
# =============================================================================

def build_csv_signal_lookup(df: pd.DataFrame) -> Dict[str, str]:
    """
    Build lookup from normalized CSV column names to actual columns.
    """
    lookup: Dict[str, str] = {}

    for col in df.columns:
        col_str = str(col).strip()

        if not col_str:
            continue

        if col_str in {"time", "time_str"}:
            continue

        lookup[normalize_signal_key(col_str)] = col_str

    return lookup


def load_waveforms_from_csv(
    csv_path: str,
    code_start_sec: Optional[float] = None,
    code_stop_sec: Optional[float] = None,
    desired_waveforms: List[str] = WAVEFORM_PLOT_ORDER,
    desired_fs: float = DESIRED_FS_DEFAULT,
) -> Dict:
    """
    Load waveform data from a CSV bundle.

    Expected CSV structure
    ----------------------
    ::

        time, I, II, III, V, AVF, AVL, AVR, ...

    If no ``time`` column exists, the numeric index is used.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV waveform file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    time_axis, _time_source = _extract_time_epoch_s(df)
    time_axis = normalize_epoch_seconds(time_axis)

    if time_axis.size == 0:
        return _empty_waveform_result(desired_waveforms)

    if np.any(np.diff(time_axis) < 0):
        print(f"WARNING: time vector not sorted in {csv_path}; sorting.")
        sort_idx = np.argsort(time_axis)
        time_axis = time_axis[sort_idx]
        df = df.iloc[sort_idx].reset_index(drop=True)

    file_start = float(time_axis[0])
    file_stop = float(time_axis[-1])

    window_start = float(code_start_sec) if code_start_sec is not None else file_start
    window_stop = float(code_stop_sec) if code_stop_sec is not None else file_stop

    window_start = max(window_start, file_start)
    window_stop = min(window_stop, file_stop)

    if window_stop <= window_start:
        return _empty_waveform_result(desired_waveforms)

    i0 = int(np.searchsorted(time_axis, window_start, side="left"))
    i1 = int(np.searchsorted(time_axis, window_stop, side="right"))

    i0 = max(0, i0)
    i1 = min(time_axis.size, i1)

    if i1 <= i0:
        return _empty_waveform_result(desired_waveforms)

    time_window = time_axis[i0:i1]

    fs_est = _estimate_fs_from_time(time_window, default_fs=240.0)
    downsample_factor = max(1, int(np.round(fs_est / desired_fs)))

    time_ds = time_window[::downsample_factor]

    signal_lookup = build_csv_signal_lookup(df)

    leads_ds: List[np.ndarray] = []
    lead_names: List[str] = []
    units: List[str] = []

    for desired in desired_waveforms:
        col = resolve_signal_id(desired, signal_lookup)

        if col is None or col not in df.columns:
            leads_ds.append(np.array([]))
            lead_names.append(desired)
            units.append("")
            continue

        sig_window = pd.to_numeric(
            df[col].iloc[i0:i1],
            errors="coerce",
        ).to_numpy(dtype="float32")

        sig_ds = sig_window[::downsample_factor]

        leads_ds.append(sig_ds)
        lead_names.append(desired)
        units.append("")

    return {
        "times_ds": time_ds,
        "leads_ds": leads_ds,
        "lead_names": lead_names,
        "units": units,
        "Fs": fs_est,
        "source_type": "csv",
        "source_path": csv_path,
    }


# =============================================================================
# Old MAT waveform loading
# =============================================================================

def load_waveforms_from_mat_subject(
    base_folder: str,
    subject: str,
    recording_start_sec: float = None,
    code_start_sec: float = None,
    code_stop_sec: float = None,
    desired_waveforms: list = WAVEFORM_PLOT_ORDER,
    desired_fs: float = DESIRED_FS_DEFAULT,
) -> Dict:
    """
    Load waveforms using the old per-lead MAT structure.

    This preserves previous behavior for backwards compatibility.
    """
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

            data = mat_data.get("data", None)
            fs = mat_data.get("Fs", 240.0)
            unit = mat_data.get("unit", "")

            try:
                fs = float(np.array(fs).flatten()[0]) if fs is not None else 240.0
            except Exception:
                print("sampling exception")
                fs = 240.0

            try:
                if isinstance(unit, (np.ndarray, list)) and len(unit) > 0:
                    u = unit[0] if isinstance(unit, (list, np.ndarray)) else unit
                    unit = u.decode() if isinstance(u, bytes) else str(u)
                elif isinstance(unit, bytes):
                    unit = unit.decode()
                else:
                    unit = str(unit)
            except Exception:
                unit = "NoUnitSpecified"

            if data is not None:
                sig = np.array(data).flatten()

                mat_start_val = mat_data.get("start_time", 0)

                if isinstance(mat_start_val, np.ndarray):
                    mat_start_sec = float(mat_start_val.flatten()[0])
                else:
                    mat_start_sec = float(mat_start_val)

                rec_start_sec = (
                    float(recording_start_sec)
                    if recording_start_sec is not None
                    else mat_start_sec
                )

                start_secs.append(rec_start_sec)
                fs_list.append(fs)

                times = rec_start_sec + np.arange(len(sig)) / fs
                lead_ranges.append((times[0], times[-1]))
            else:
                sig = None
                times = np.array([])
                lead_ranges.append((None, None))
                start_secs.append(None)
                fs_list.append(None)

            leads.append(sig)
            lead_names.append(wf)
            available_units.append(unit)
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

    valid_ranges = [(s, e) for s, e in lead_ranges if s is not None and e is not None]

    candidate_starts = [r[0] for r in valid_ranges]
    candidate_ends = [r[1] for r in valid_ranges]

    if code_start_sec is not None:
        candidate_starts.append(code_start_sec)

    if code_stop_sec is not None:
        candidate_ends.append(code_stop_sec)

    intersection_start = max(candidate_starts) if candidate_starts else None
    intersection_end = min(candidate_ends) if candidate_ends else None

    if (
        intersection_start is None
        or intersection_end is None
        or intersection_end <= intersection_start
    ):
        return _empty_waveform_result(desired_waveforms)

    for idx, (sig, rec_start_sec, fs) in enumerate(zip(leads, start_secs, fs_list)):
        if sig is None or rec_start_sec is None or fs is None or len(sig) == 0:
            times_list[idx] = np.array([])
            leads[idx] = None
            continue

        rel_start_offset = intersection_start - rec_start_sec
        rel_end_offset = intersection_end - rec_start_sec

        start_idx = int(np.floor(rel_start_offset * fs))
        end_idx = int(np.ceil(rel_end_offset * fs))

        n = len(sig)

        start_idx = max(0, start_idx)
        end_idx = min(n, end_idx)

        if end_idx <= 0 or start_idx >= n or end_idx <= start_idx:
            times_list[idx] = np.array([])
            leads[idx] = None
        else:
            leads[idx] = sig[start_idx:end_idx]
            times_list[idx] = rec_start_sec + np.arange(start_idx, end_idx) / fs

    canonical_time = np.array([])

    for tarr in times_list:
        if tarr is not None and len(tarr) > 0:
            canonical_time = tarr
            break

    if canonical_time.size == 0:
        return _empty_waveform_result(desired_waveforms)

    first_fs = next((fs for fs in fs_list if fs is not None), 240.0)
    downsample_factor = max(1, int(np.round(first_fs / desired_fs)))

    time_axis_ds = canonical_time[::downsample_factor]

    leads_ds = []

    for sig in leads:
        if sig is not None and len(sig) > 0:
            leads_ds.append(sig[::downsample_factor])
        else:
            leads_ds.append(np.array([]))

    return {
        "times_ds": time_axis_ds,
        "leads_ds": leads_ds,
        "lead_names": lead_names,
        "units": available_units,
        "Fs": first_fs,
        "source_type": "mat",
        "source_path": subj_path,
    }


# =============================================================================
# Unified public waveform loader
# =============================================================================

def load_waveforms_for_subject(
    base_folder: str,
    subject: Union[str, Dict],
    recording_start_sec: float = None,
    code_start_sec: float = None,
    code_stop_sec: float = None,
    desired_waveforms: list = WAVEFORM_PLOT_ORDER,
) -> Dict:
    """
    Unified waveform loader.

    Supports:

    - H5 bundle records returned by ``list_subjects()``
    - CSV bundle records returned by ``list_subjects()``
    - old MAT subject folders
    - string subject names for backwards compatibility
    """
    if isinstance(subject, dict):
        kind = subject.get("kind")

        if kind == "h5":
            return load_waveforms_from_h5(
                h5_path=subject["h5_path"],
                code_start_sec=code_start_sec,
                code_stop_sec=code_stop_sec,
                desired_waveforms=desired_waveforms,
                desired_fs=DESIRED_FS_DEFAULT,
            )

        if kind == "csv":
            return load_waveforms_from_csv(
                csv_path=subject["csv_path"],
                code_start_sec=code_start_sec,
                code_stop_sec=code_stop_sec,
                desired_waveforms=desired_waveforms,
                desired_fs=DESIRED_FS_DEFAULT,
            )

        if kind == "mat":
            return load_waveforms_from_mat_subject(
                base_folder=base_folder,
                subject=subject["subject"],
                recording_start_sec=recording_start_sec,
                code_start_sec=code_start_sec,
                code_stop_sec=code_stop_sec,
                desired_waveforms=desired_waveforms,
                desired_fs=DESIRED_FS_DEFAULT,
            )

        raise ValueError(f"Unknown waveform record kind: {kind}")

    subject_name = str(subject)
    subj_path = os.path.join(base_folder, subject_name)

    h5_files = find_waveform_files_recursive(subj_path, ".h5")

    if h5_files:
        if len(h5_files) > 1:
            print(
                f"WARNING: Multiple H5 files found for subject {subject_name}. "
                f"Using first: {h5_files[0]}"
            )

        return load_waveforms_from_h5(
            h5_path=h5_files[0],
            code_start_sec=code_start_sec,
            code_stop_sec=code_stop_sec,
            desired_waveforms=desired_waveforms,
            desired_fs=DESIRED_FS_DEFAULT,
        )

    csv_files = [
        f for f in find_waveform_files_recursive(subj_path, ".csv")
        if not _is_annotation_csv(f)
    ]

    if csv_files:
        if len(csv_files) > 1:
            print(
                f"WARNING: Multiple CSV waveform files found for subject {subject_name}. "
                f"Using first: {csv_files[0]}"
            )

        return load_waveforms_from_csv(
            csv_path=csv_files[0],
            code_start_sec=code_start_sec,
            code_stop_sec=code_stop_sec,
            desired_waveforms=desired_waveforms,
            desired_fs=DESIRED_FS_DEFAULT,
        )

    mat_files = sorted(glob.glob(os.path.join(subj_path, "*.mat")))

    if mat_files:
        return load_waveforms_from_mat_subject(
            base_folder=base_folder,
            subject=subject_name,
            recording_start_sec=recording_start_sec,
            code_start_sec=code_start_sec,
            code_stop_sec=code_stop_sec,
            desired_waveforms=desired_waveforms,
            desired_fs=DESIRED_FS_DEFAULT,
        )

    raise FileNotFoundError(
        f"No supported waveform files found for subject {subject_name}. "
        f"Expected .h5, .csv, or .mat files."
    )


def get_available_waveforms_for_subject(
    base_folder: str,
    subject: Union[str, Dict],
) -> List[str]:
    """
    Return available waveform identifiers for H5, CSV, or MAT data.
    """
    if isinstance(subject, dict):
        kind = subject.get("kind")

        if kind == "h5":
            h5_path = subject.get("h5_path")

            if not h5_path or not os.path.exists(h5_path):
                return []

            with h5py.File(h5_path, "r", locking=False) as f:
                if H5_SIGNALS_GROUP not in f:
                    return []
                return sorted(list(f[H5_SIGNALS_GROUP].keys()))

        if kind == "csv":
            csv_path = subject.get("csv_path")

            if not csv_path or not os.path.exists(csv_path):
                return []

            df = pd.read_csv(csv_path, nrows=1)
            return sorted(
                [
                    str(c)
                    for c in df.columns
                    if str(c).strip() and str(c) not in {"time", "time_str"}
                ]
            )

        if kind == "mat":
            return get_available_waveforms_for_subject(base_folder, subject["subject"])

    subject_name = str(subject)
    subj_path = os.path.join(base_folder, subject_name)

    h5_files = sorted(glob.glob(os.path.join(subj_path, "*.h5")))
    h5_files += sorted(glob.glob(os.path.join(subj_path, "*", "*.h5")))

    if h5_files:
        with h5py.File(h5_files[0], "r", locking=False) as f:
            if H5_SIGNALS_GROUP not in f:
                return []
            return sorted(list(f[H5_SIGNALS_GROUP].keys()))

    csv_files = sorted(
        f for f in glob.glob(os.path.join(subj_path, "*.csv"))
        if not _is_annotation_csv(f)
    )
    csv_files += sorted(
        f for f in glob.glob(os.path.join(subj_path, "*", "*.csv"))
        if not _is_annotation_csv(f)
    )

    if csv_files:
        df = pd.read_csv(csv_files[0], nrows=1)
        return sorted(
            [
                str(c)
                for c in df.columns
                if str(c).strip() and str(c) not in {"time", "time_str"}
            ]
        )

    mat_files = glob.glob(os.path.join(subj_path, "*.mat"))
    names = []

    for f in mat_files:
        parts = os.path.basename(f).replace(".mat", "").split("_")
        if len(parts) >= 2:
            names.append(parts[-1])

    return sorted(names)


# =============================================================================
# Annotation helper paths / old annotation helpers
# =============================================================================

def annotation_output_folder_for_record(record: Dict, user_name: str) -> str:
    """
    Return annotation output folder for a discovered waveform record.

    Preferred new location
    ----------------------
    ::

        encounter_path/output/user/

    For old MAT/root records
    ------------------------
    ::

        subject_path/output/user/
    """
    if record.get("output_path"):
        return os.path.join(record["output_path"], user_name)

    if record.get("encounter_path"):
        return os.path.join(record["encounter_path"], "output", user_name)

    if record.get("subject_path"):
        return os.path.join(record["subject_path"], "output", user_name)

    raise ValueError("Record does not contain output_path, encounter_path, or subject_path.")


def load_annotations_csv(subject_folder: str) -> Optional[pd.DataFrame]:
    """
    Load the first annotations CSV in a subject folder.

    Returns
    -------
    pd.DataFrame or None
    """
    csvs = list_annotation_files(subject_folder)

    if not csvs:
        return None

    return pd.read_csv(csvs[0])


def save_annotations_csv(
    subject_folder: str,
    data: List[Dict],
    name_prefix: str = "annotations",
) -> str:
    """
    Save annotations as a timestamped CSV file in the subject folder.

    Returns
    -------
    str
        Saved file path.
    """
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{name_prefix}_{now}.csv"
    fpath = os.path.join(subject_folder, fname)

    pd.DataFrame(data).to_csv(fpath, index=False)

    return fpath


def subject_folder(base_folder: str, subject: Union[str, Dict]) -> str:
    """
    Return full subject folder path.

    Supports old string subject names and new ``list_subjects()`` records.
    """
    if isinstance(subject, dict):
        return subject.get("subject_path", "")

    return os.path.join(base_folder, str(subject))


# =============================================================================
# Windows Helpers
# =============================================================================

def find_waveform_files_recursive(root_folder: str, extension: str) -> List[str]:
    """
    Recursively find waveform files while skipping annotation output folders.
    """
    matches = []

    if not os.path.isdir(root_folder):
        return matches

    extension = extension.lower()

    for root, dirs, files in os.walk(root_folder):
        dirs[:] = [
            d for d in dirs
            if d.lower() not in {"output", "__pycache__"} and not d.startswith(".")
        ]

        for fname in files:
            if fname.startswith("."):
                continue

            if fname.lower().endswith(extension):
                matches.append(os.path.join(root, fname))

    return sorted(matches)