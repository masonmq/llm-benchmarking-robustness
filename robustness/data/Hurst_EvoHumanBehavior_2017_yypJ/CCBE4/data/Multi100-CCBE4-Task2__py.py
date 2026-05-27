import json
import os
import sys
import subprocess
import importlib

# Ensure required packages are available at runtime
REQUIRED_PY_PKGS = [
    "numpy==1.26.4",
    "pandas==2.2.2",
    "scipy==1.11.4",
    "requests==2.31.0"
]

def ensure_packages(packages):
    for spec in packages:
        name = spec.split("==")[0]
        try:
            importlib.import_module(name)
        except ImportError:
            print(f"Package {name} not found. Installing {spec}...", file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "install", spec])

ensure_packages(REQUIRED_PY_PKGS)

# Ensure user site-packages is on sys.path
import site
try:
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
except Exception as e:
    print(f"WARNING: Could not append user site-packages: {e}", file=sys.stderr)
# Also try default pip user dir as fallback
fallback_user_site = os.path.expanduser("~/.local/lib/python3.9/site-packages")
if os.path.isdir(fallback_user_site) and fallback_user_site not in sys.path:
    sys.path.append(fallback_user_site)

import numpy as np
import pandas as pd
from scipy import stats

INPUT_PATH = "/app/data/Dataset.csv"
RESULTS_JSON = "/app/data/Multi100-CCBE4-Task2_results.json"
DATA_OSF_URL = "https://osf.io/download/vhmgc/?view_only=5c6bedb36b2549a88ac137d6c746bcb8"


def partial_corr_resid(x, y, covars):
    df = pd.concat([x, y, covars], axis=1).dropna()
    X = np.column_stack([np.ones(len(df)), df[covars.columns].values])
    beta_x, *_ = np.linalg.lstsq(X, df[x.name].values, rcond=None)
    beta_y, *_ = np.linalg.lstsq(X, df[y.name].values, rcond=None)
    x_hat = X @ beta_x
    y_hat = X @ beta_y
    x_resid = df[x.name].values - x_hat
    y_resid = df[y.name].values - y_hat
    r, p = stats.pearsonr(x_resid, y_resid)
    return r, p, len(df)


def main():
    if not os.path.exists(INPUT_PATH):
        # Try to auto-download from OSF folder link if possible
        try:
            import requests
            print(f"Dataset not found locally. Attempting download from OSF: {DATA_OSF_URL}")
            r = requests.get(DATA_OSF_URL, allow_redirects=True, timeout=60)
            r.raise_for_status()
            with open(INPUT_PATH, "wb") as f:
                f.write(r.content)
            print(f"Downloaded dataset to {INPUT_PATH}")
        except Exception as e:
            print(f"ERROR: Expected dataset at {INPUT_PATH} but not found and auto-download failed: {e}", file=sys.stderr)
            sys.exit(1)
    dat = pd.read_csv(INPUT_PATH)

    results = {"task": "Task2", "input": INPUT_PATH, "outputs": {}}

    needed_cols = ["MiniK_Total", "DSM5_Total", "Age"]
    missing = [c for c in needed_cols if c not in dat.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    covars = dat[["Age"]]
    r_mini_dsm5, p_mini_dsm5, n = partial_corr_resid(dat["MiniK_Total"], dat["DSM5_Total"], covars)

    print("Task 2 partial correlation controlling for Age:")
    print(f"MiniK_Total vs DSM5_Total: r = {r_mini_dsm5:.3f}, p = {p_mini_dsm5:.4g}, N = {n}")

    results["outputs"]["partial_correlation_age_controlled"] = {
        "MiniK_Total__DSM5_Total": {"r": r_mini_dsm5, "p": p_mini_dsm5, "N": n}
    }

    try:
        with open(RESULTS_JSON, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved results to {RESULTS_JSON}")
    except Exception as e:
        print(f"WARNING: Failed to save results JSON due to: {e}")


if __name__ == "__main__":
    main()
