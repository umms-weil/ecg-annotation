import os
import h5py
import numpy as np
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
DATA_ROOT = "/Users/pwalczyk/Documents/Projects/Uconn-CPR/AnnotationSoftware/ecg-annotation/software/src/data/FAKE_DATA"
SUBJECTS = [f"testsubject{i+1:02d}" for i in range(3)]
LEAD_NAMES = ["I", "II", "III", "V", "AVF", "AVL", "AVR"]
FS = 240  # samples/sec
DURATION_SEC = 24*60*60  # 24 hours

EPOCH_1840 = datetime(1840, 12, 31, 0, 0, 0)
START_DATE = datetime(2024, 6, 1, 0, 0, 0)  # arbitrary

def datetime_to_epoch1840(dt):
    return (dt - EPOCH_1840).total_seconds()

def save_fake_lead_mat(filename, lead_name, start_seconds, length_seconds=DURATION_SEC, fs=FS, unit="mV"):
    n_points = int(length_seconds * fs)
    # Fake ECG-like waveform
    t = np.arange(n_points) / fs
    fake_data = (
        2 * np.sin(2 * np.pi * 1.2 * t)
        + 0.2 * np.random.randn(n_points) +
        np.linspace(0, 0.1, n_points)
    )
    with h5py.File(filename, "w") as f:
        f.create_dataset("data", data=fake_data, compression="gzip")
        f.create_dataset("Fs", data=np.array([fs]))
        f.create_dataset("unit", data=np.bytes_(unit))
        f.create_dataset("start_time", data=np.array([start_seconds]))

def make_test_subject(subject_path, subject_name, start_seconds, length_seconds=DURATION_SEC):
    os.makedirs(subject_path, exist_ok=True)
    for lead in LEAD_NAMES:
        mat_path = os.path.join(subject_path, f"{subject_name}_{lead}.mat")
        save_fake_lead_mat(mat_path, lead, start_seconds, length_seconds)

def generate_manifest(manifest_path, subjects, rec_start_dt, durations_mins=[1, 5, 15, 60, 120, 240]):
    rows = []
    for subj in subjects:
        for window_min in durations_mins:
            # signal_start is always 0 for simplicity (start of full trace)
            signal_start = rec_start_dt
            code_start = signal_start + timedelta(minutes=0)
            code_end = code_start + timedelta(minutes=window_min)
            rows.append({
                "UUID": subj,
                "signal_start": signal_start.strftime("%Y-%m-%d %H:%M:%S"),
                "CODE_START": code_start.strftime("%Y-%m-%d %H:%M:%S"),
                "CODE_END": code_end.strftime("%Y-%m-%d %H:%M:%S"),
            })
    df = pd.DataFrame(rows)
    df.to_csv(manifest_path, index=False)
    print(f"Created manifest: {manifest_path}")

def main():
    print("Generating test .mat files...")
    # Reference start for all files (same for all, matches signal_start in manifest)
    rec_start_dt = START_DATE
    rec_start_sec = datetime_to_epoch1840(rec_start_dt)
    # Make 3 subjects
    for subj in SUBJECTS:
        subj_folder = os.path.join(DATA_ROOT, subj)
        make_test_subject(subj_folder, subj, start_seconds=rec_start_sec, length_seconds=DURATION_SEC)
    # Manifest with code intervals
    manifest_path = os.path.join(DATA_ROOT, "waveform_manifest.csv")
    generate_manifest(manifest_path, SUBJECTS, rec_start_dt, durations_mins=[1, 5, 15, 30, 60, 120, 240])
    print("Done.")

if __name__ == "__main__":
    main()