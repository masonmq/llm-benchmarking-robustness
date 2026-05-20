import json
import os
import numpy as np
import pandas as pd

# Attempt to import statsmodels; install if missing# Import statsmodels (preinstalled via Docker image)# Try to import statsmodels; if unavailable, install compatible versions for this interpreter# Try to import minimal statsmodels components to avoid heavy API import
import sys
try:
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant
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
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant

# IO paths# IO paths# IO paths# IO paths
DATA_PATH = os.environ.get("DATA_PATH", "/app/data")
INPUT_FILE = os.path.join(DATA_PATH, "final_data.dta")
OUT_JSON = os.path.join(DATA_PATH, "task1_results.json")

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

# Standardize outcome and num_names_2008 to mirror R's scale() (uses ddof=1)
def zscore(x):
    return (x - x.mean()) / x.std(ddof=1)

df_model["y_z"] = zscore(df_model["complaints_2008"])  # scaled outcome
df_model["num_names_z"] = zscore(df_model["num_names_2008"])  # scaled covariate

# Build design matrix: y_z ~ first_A + num_names_z
X = df_model[["first_A", "num_names_z"]]
X = add_constant(X)
y = df_model["y_z"]

model = OLS(y, X, missing="drop").fit()

# Extract primary results for first_A
coef_first_A = float(model.params.get("first_A", np.nan))
p_first_A = float(model.pvalues.get("first_A", np.nan))
coef_num_names = float(model.params.get("num_names_z", np.nan))
p_num_names = float(model.pvalues.get("num_names_z", np.nan))

results = {
    "model": "OLS",
    "formula": "scale(complaints_2008) ~ first_A + scale(num_names_2008)",
    "n_obs": int(model.nobs),
    "r_squared": float(model.rsquared),
    "coef_first_A": coef_first_A,
    "p_first_A": p_first_A,
    "coef_num_names_z": coef_num_names,
    "p_num_names_z": p_num_names,
}

# Print concise output and save JSON
print("Task1 OLS results (standardized outcome):")
print({k: v for k, v in results.items() if k not in ["model", "formula"]})

with open(OUT_JSON, "w") as f:
    json.dump(results, f, indent=2)

print(f"Saved Task1 results to {OUT_JSON}")
