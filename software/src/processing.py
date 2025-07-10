import os
import pandas as pd

# Always use a robust root for references!
SRC_ROOT = os.path.dirname(os.path.abspath(__file__))  # <--- src/ folder
DATA_ROOT = os.path.abspath(os.path.join(SRC_ROOT, "..", "data"))

def list_subjects(data_root=DATA_ROOT):
    print("Looking for subjects in", data_root)
    print("Folders here:", os.listdir(data_root))
    return sorted([
        f for f in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, f)) and not f.startswith('.')
    ])

def load_all_leads(subject_name):
    subject_path = os.path.join(DATA_ROOT, subject_name)
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
            times = df.iloc[:, 0].values  # first column: time
        lead_signal = df.iloc[:, 1].values  # second column: value
        leads.append(lead_signal)
        lead_names.append(os.path.splitext(file)[0])
    return times, leads, lead_names