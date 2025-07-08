import os
import pandas as pd
from datetime import datetime

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "annotations.csv")

def save_annotation(start, end, label):
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    entry = {
        'start_time': float(start),
        'end_time': float(end),
        'label': label,
        'saved_at': now
    }
    df = pd.DataFrame([entry])
    if not os.path.exists(OUTPUT_FILE):
        df.to_csv(OUTPUT_FILE, index=False)
    else:
        df.to_csv(OUTPUT_FILE, mode='a', header=False, index=False)
    return entry