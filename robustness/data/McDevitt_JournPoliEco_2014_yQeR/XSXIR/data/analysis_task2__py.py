import json
import os
import numpy as np
import pandas as pd

# Attempt to import statsmodels; install if missing# Import statsmodels (preinstalled via Docker image)# Try to import statsmodels; if unavailable, install compatible versions for this interpreter
import sys
try:
    import statsmodels.api as sm
except Exception:
    import subprocess, site
    pkgs = [
        "statsmodels==0.14.1",
        "numpy==1.26.4",
        "patsy==0.5.6",
        "pandas==2.0.3"
    ]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + pkgs)
    try:
        sys.path.append(site.getusersitepackages())
    except Exception:
        pass
    import statsmodels.api as sm

# IO paths# IO paths# IO paths
DATA_PATH = os.environ.get("DATA_PATH", "/app/data")
INPUT_FILE = os.path.join(DATA_PATH, "final_data.dta")
OUT_JSON = os.path.join(DATA_PATH, "task2_results.json")

# Load data
if not os.path.exists(INPUT_FILE):
    raise FileNotFoundError(f"Data file not found at {INPUT_FILE}. Ensure final_data.dta is available under /app/data.")

df = pd.read_stata(INPUT_FILE)

# Ensure numeric types
for col in ["complaints_2008", "num_names_2008", "first_A"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        raise KeyError(f"Required column '{col}' not found in dataset.")

# Drop rows with missing required fields
df_model = df[["complaints_2008", "first_A", "num_names_2008"]].dropna().copy()

# Standardize variables to mirror R code

def zscore(x):
    return (x - x.mean()) / x.std(ddof=1)

# Outcome and covariate scaling
df_model["y_z"] = zscore(df_model["complaints_2008"])  # outcome
df_model["num_names_z"] = zscore(df_model["num_names_2008"])  # covariate

# Fit OLS: y_z ~ first_A + num_names_z
X = df_model[["first_A", "num_names_z"]]
X = sm.add_constant(X)
y = df_model["y_z"]
model = sm.OLS(y, X, missing="drop").fit()

coef_first_A = float(model.params.get("first_A", np.nan))
p_first_A = float(model.pvalues.get("first_A", np.nan))
coef_num_names = float(model.params.get("num_names_z", np.nan))
p_num_names = float(model.pvalues.get("num_names_z", np.nan))

# For an ANOVA-like F test on first_A (equivalent to t^2 for single coefficient)
t_value = float(model.tvalues.get("first_A", np.nan))
F_first_A = t_value ** 2 if np.isfinite(t_value) else np.nan

results = {
    "model": "OLS",
    "formula": "scale(complaints_2008) ~ first_A + scale(num_names_2008)",
    "n_obs": int(model.nobs),
    "r_squared": float(model.rsquared),
    "coef_first_A": coef_first_A,
    "t_first_A": float(t_value) if np.isfinite(t_value) else np.nan,
    "F_first_A": float(F_first_A) if np.isfinite(F_first_A) else np.nan,
    "p_first_A": p_first_A,
    "coef_num_names_z": coef_num_names,
    "p_num_names_z": p_num_names,
}

print("Task2 OLS results (standardized outcome) with F-test for first_A:")
print({k: v for k, v in results.items() if k not in ["model", "formula"]})

with open(OUT_JSON, "w") as f:
    json.dump(results, f, indent=2)

print(f"Saved Task2 results to {OUT_JSON}")
