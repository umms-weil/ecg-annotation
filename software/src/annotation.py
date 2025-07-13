import os
import pandas as pd
from datetime import datetime

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def save_all_annotations(annotations, subject=None):
    """
    Save all annotation dicts in a single CSV file.
    Each annotation should at least have: 'start', 'end', 'label'
    Optionally, include subject name in filename.
    """
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    if subject:
        filename = f"annotations_{subject}_{now}.csv"
    else:
        filename = f"annotations_{now}.csv"
    outpath = os.path.join(OUTPUT_DIR, filename)
    df = pd.DataFrame(annotations)
    df.to_csv(outpath, index=False)
    return outpath