import os
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(PROJECT_ROOT, "data")

def list_subjects(data_root=DATA_ROOT):
    """
    Returns sorted list of subdirectories (subjects) in data_root.
    """
    return sorted([
        f for f in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, f)) and not f.startswith('.')
    ])


def load_all_leads(subject_path):
    """
    Load all CSVs in subject_path as separate leads.
    Each CSV: columns [time, value]. All time arrays should be identical.
    Returns: times (1D array), [leads...], [lead_names...]
    """
    leads = []
    times = None
    lead_names = []
    files = sorted([
        f for f in os.listdir(subject_path)
        if f.lower().endswith('.csv') and os.path.isfile(os.path.join(subject_path, f))
    ])
    for file in files:
        path = os.path.join(subject_path, file)
        df = pd.read_csv(path)
        if times is None:
            times = df.iloc[:, 0].values
        lead_signal = df.iloc[:, 1].values
        leads.append(lead_signal)
        lead_names.append(os.path.splitext(file)[0])
    return times, leads, lead_names