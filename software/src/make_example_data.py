import os
import numpy as np
import pandas as pd

os.makedirs("data", exist_ok=True)
fs = 500
duration = 60  # 1 minute data!
t = np.linspace(0, duration, int(fs * duration))
signal = 1.5 * np.sin(2 * np.pi * 1.2 * t) + 0.2 * np.random.randn(len(t))
df = pd.DataFrame({"time": t, "lead1": signal})
df.to_csv("data/example_lead6.csv", index=False)