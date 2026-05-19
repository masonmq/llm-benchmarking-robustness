import os
import pandas as pd
import numpy as np
from scipy import stats

# Paths
DEFAULT_CONTAINER_DATA = "/app/data"
LOCAL_DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = DEFAULT_CONTAINER_DATA if os.path.exists(DEFAULT_CONTAINER_DATA) else LOCAL_DATA_DIR
IN_FILE = os.path.join(DATA_DIR, "AEJApp-2009-0289-data", "household.dta")
OUT_DIR = os.path.join(DATA_DIR, "outputs")
OUT_FILE = os.path.join(OUT_DIR, "results_12hio.txt")

os.makedirs(OUT_DIR, exist_ok=True)

# Load data
try:
    df = pd.read_stata(IN_FILE)
except Exception as e:
    with open(OUT_FILE, "w") as f:
        f.write(f"ERROR: Failed to read dataset {IN_FILE}: {e}\n")
    raise

# Columns of interest
income_col = "totinc"  # Total household income; falls back to cropinc if needed
village_dom_col = "domlow"  # 1 = BAC dominated (lower caste dominated), 0 = upper-caste dominated
caste_col = "caste"       # categorical with lower-caste categories in this dataset

# Basic checks
missing_cols = [c for c in [income_col, village_dom_col] if c not in df.columns]
if missing_cols:
    with open(OUT_FILE, "w") as f:
        f.write(f"ERROR: Missing required columns: {missing_cols}\n")
    raise SystemExit(1)

# Focus on low-caste households as per focal claim
# The dataset's 'caste' column contains only lower-caste categories in this file, but we'll still filter robustly
if caste_col in df.columns:
    lower_castes = set(["ST/SC", "Back agr", "Back oth"])  # observed categories in the dataset
    if pd.api.types.is_categorical_dtype(df[caste_col]):
        levels = set([str(x) for x in df[caste_col].cat.categories])
    else:
        levels = set(df[caste_col].astype(str).unique())
    # If any of the known lower-caste labels are present, filter to them; else do not filter
    if lower_castes & levels:
        df = df[df[caste_col].astype(str).isin(lower_castes)].copy()

# Drop rows with missing village dominance or income
work = df[[income_col, village_dom_col]].dropna().copy()

# Ensure village_dom_col is binary 0/1
# Some datasets may store it as float; round to nearest int if close
work[village_dom_col] = work[village_dom_col].astype(float).round().astype(int)

# Split groups
grp1 = work.loc[work[village_dom_col] == 1, income_col].astype(float)
grp0 = work.loc[work[village_dom_col] == 0, income_col].astype(float)

n1, n0 = grp1.shape[0], grp0.shape[0]
mean1, mean0 = grp1.mean(), grp0.mean()
std1, std0 = grp1.std(ddof=1), grp0.std(ddof=1)

diff = mean1 - mean0

# Welch's t-test (unequal variances)
if n1 > 1 and n0 > 1:
    t_stat, p_val = stats.ttest_ind(grp1, grp0, equal_var=False, nan_policy='omit')
    # Welch-Satterthwaite df approximation
    s1 = std1**2 / n1 if n1 > 0 else np.nan
    s0 = std0**2 / n0 if n0 > 0 else np.nan
    df_denom = (s1 + s0)**2
    df_num = (s1**2) / (n1 - 1) + (s0**2) / (n0 - 1)
    dof = df_denom / df_num if df_num > 0 else np.nan
else:
    t_stat, p_val, dof = np.nan, np.nan, np.nan

# Write results
with open(OUT_FILE, "w") as f:
    f.write("Robustness Reanalysis (12hio)\n")
    f.write(f"Dataset: {IN_FILE}\n")
    f.write(f"Outcome: {income_col}\n")
    f.write(f"Grouping: {village_dom_col} (1=low-caste dominated, 0=upper-caste dominated)\n")
    f.write(f"Sample size after filtering: N1={n1}, N0={n0}, N={n1+n0}\n")
    f.write(f"Group means: mean1={mean1:.4f}, mean0={mean0:.4f}, diff={diff:.4f}\n")
    f.write(f"Welch t-test: t={t_stat:.4f}, df~{dof:.1f}, p={p_val:.4g}\n")
    # Simple interpretation aligned with the focal claim direction
    if not np.isnan(p_val) and p_val < 0.05:
        direction = "higher" if diff > 0 else "lower"
        f.write(f"Conclusion: Statistically significant difference; income is {direction} in low-caste dominated villages.\n")
    else:
        f.write("Conclusion: No statistically significant difference detected at the 5% level.\n")

print("Analysis complete. Results written to:", OUT_FILE)
