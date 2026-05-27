import os
import json
import sys
import subprocess

# Ensure required Python packages are available at runtime (fallback if image misses them)

def ensure_deps():
    pkgs = [
        ("numpy", "numpy==1.26.4"),
        ("pandas", "pandas==2.2.2"),
        ("scipy", "scipy==1.11.4"),
    ]
    to_install = []
    for mod_name, pkg_spec in pkgs:
        try:
            __import__(mod_name)
        except ModuleNotFoundError:
            to_install.append(pkg_spec)
    if to_install:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", *to_install])

ensure_deps()

import numpy as np
import pandas as pd
from scipy import stats

# IO paths
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DATA_FILE = os.path.join(DATA_DIR, "1-s2.0-S1090513816301118-mmc1.csv")
OUT_FILE = os.path.join(DATA_DIR, "results_task2.json")

# Load data
_df = pd.read_csv(DATA_FILE)

# Variables
MINI = "MiniK_Total"
DSM = "DSM5_Total"

if MINI not in _df.columns or DSM not in _df.columns:
    raise ValueError("Required columns not found in dataset.")

# Create groups based on MiniK sum score
# fast: <= -1 -> 0, slow: >= 1 -> 1, exclude [-1,1] interior
mask_fast = _df[MINI] <= -1
mask_slow = _df[MINI] >= 1
fast = _df.loc[mask_fast, DSM].dropna()
slow = _df.loc[mask_slow, DSM].dropna()

# Descriptives
desc = {
    "n_fast": int(fast.shape[0]),
    "n_slow": int(slow.shape[0]),
    "median_fast": float(np.median(fast)) if fast.shape[0] > 0 else None,
    "median_slow": float(np.median(slow)) if slow.shape[0] > 0 else None,
}

# Levene's test for equal variances
if fast.shape[0] > 1 and slow.shape[0] > 1:
    lev_stat, lev_p = stats.levene(fast, slow)
else:
    lev_stat, lev_p = np.nan, np.nan

# Shapiro-Wilk normality tests
def safe_shapiro(a):
    try:
        if len(a) < 3:
            return np.nan, np.nan
        w, p = stats.shapiro(a)
        return float(w), float(p)
    except Exception:
        return np.nan, np.nan

w_fast, p_fast = safe_shapiro(fast.values)
w_slow, p_slow = safe_shapiro(slow.values)

# Mann-Whitney U test (nonparametric)
if fast.shape[0] > 0 and slow.shape[0] > 0:
    u_stat, p_u = stats.mannwhitneyu(fast, slow, alternative="two-sided")
else:
    u_stat, p_u = np.nan, np.nan

results = {
    "grouping_rule": "fast <= -1, slow >= 1, exclude -1 < MiniK < 1",
    "descriptives": desc,
    "levene_equal_var": {"stat": float(lev_stat) if not np.isnan(lev_stat) else None, "p": float(lev_p) if not np.isnan(lev_p) else None},
    "shapiro": {
        "fast": {"W": w_fast if not np.isnan(w_fast) else None, "p": p_fast if not np.isnan(p_fast) else None},
        "slow": {"W": w_slow if not np.isnan(w_slow) else None, "p": p_slow if not np.isnan(p_slow) else None}
    },
    "mann_whitney_u": {"U": float(u_stat) if not np.isnan(u_stat) else None, "p": float(p_u) if not np.isnan(p_u) else None}
}

print(json.dumps(results, indent=2))
with open(OUT_FILE, "w") as f:
    json.dump(results, f, indent=2)
