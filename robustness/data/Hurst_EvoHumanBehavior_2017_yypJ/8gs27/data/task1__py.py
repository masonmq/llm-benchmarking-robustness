import os
import json
import math
import sys
import subprocess
import site

# Ensure required Python packages are available at runtime (fallback if image misses them)

def add_site_paths():
    try:
        user_site = site.getusersitepackages()
        if user_site and user_site not in sys.path:
            sys.path.append(user_site)
    except Exception:
        pass
    try:
        getsp = getattr(site, "getsitepackages", None)
        if callable(getsp):
            for p in getsp() or []:
                if p and p not in sys.path:
                    sys.path.append(p)
    except Exception:
        pass


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
        add_site_paths()
    else:
        add_site_paths()


ensure_deps()

import numpy as np
import pandas as pd
from scipy import stats

# IO paths
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DATA_FILE = os.path.join(DATA_DIR, "1-s2.0-S1090513816301118-mmc1.csv")
OUT_FILE = os.path.join(DATA_DIR, "results_task1.json")

# Load data
_df = pd.read_csv(DATA_FILE)

# Columns of interest
cols = {
    "mini": "MiniK_Total",
    "hkss": "HKSS_Total",
    "dsm": "DSM5_Total",
    "age": "Age",
}
missing_cols = [v for v in cols.values() if v not in _df.columns]
if missing_cols:
    raise ValueError(f"Missing required columns in dataset: {missing_cols}")

# Drop rows with missing in required columns
use_df = _df[list(cols.values())].dropna().copy()

# Descriptive statistics
summary = {
    "MiniK_Total": {
        "mean": float(use_df[cols["mini"]].mean()),
        "sd": float(use_df[cols["mini"]].std(ddof=1)),
        "n": int(use_df[cols["mini"]].shape[0])
    },
    "HKSS_Total": {
        "mean": float(use_df[cols["hkss"]].mean()),
        "sd": float(use_df[cols["hkss"]].std(ddof=1)),
        "n": int(use_df[cols["hkss"]].shape[0])
    },
    "DSM5_Total": {
        "mean": float(use_df[cols["dsm"]].mean()),
        "sd": float(use_df[cols["dsm"]].std(ddof=1)),
        "n": int(use_df[cols["dsm"]].shape[0])
    },
}

# Helper: partial correlation r_xy.z controlling for Age (one covariate)

def partial_corr_one_control(x, y, z):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    if not (x.shape == y.shape == z.shape):
        raise ValueError("x, y, z must have the same shape")
    n = x.size
    # regress out z from x and y (with intercept)
    Z = np.column_stack([np.ones(n), z])
    bx, _, _, _ = np.linalg.lstsq(Z, x, rcond=None)
    by, _, _, _ = np.linalg.lstsq(Z, y, rcond=None)
    rx = x - Z @ bx
    ry = y - Z @ by
    # Pearson r between residuals
    r = np.corrcoef(rx, ry)[0, 1]
    # degrees of freedom for partial corr with 1 control: df = n - 3
    df = n - 3
    # guard for edge cases
    r = max(min(r, 0.999999), -0.999999)
    t_stat = r * math.sqrt(df / (1.0 - r * r))
    p = 2.0 * stats.t.sf(abs(t_stat), df)
    return float(r), float(t_stat), int(df), float(p)

# Compute partial correlations controlling for Age
r_mini, t_mini, df_mini, p_mini = partial_corr_one_control(use_df[cols["mini"]], use_df[cols["dsm"]], use_df[cols["age"]])
r_hkss, t_hkss, df_hkss, p_hkss = partial_corr_one_control(use_df[cols["hkss"]], use_df[cols["dsm"]], use_df[cols["age"]])

results = {
    "descriptives": summary,
    "partial_correlations": {
        "MiniK_Total_with_DSM5_Total_ctrl_Age": {
            "r": r_mini,
            "t": t_mini,
            "df": df_mini,
            "p": p_mini
        },
        "HKSS_Total_with_DSM5_Total_ctrl_Age": {
            "r": r_hkss,
            "t": t_hkss,
            "df": df_hkss,
            "p": p_hkss
        }
    }
}

# Print to stdout
print(json.dumps(results, indent=2))

# Write to file
with open(OUT_FILE, "w") as f:
    json.dump(results, f, indent=2)
