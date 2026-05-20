import json
import importlib, subprocess, sys
# Ensure required packages are available when running inside minimal containers
required_packages = ["pandas", "numpy", "statsmodels", "scipy"]
for pkg in required_packages:
    try:
        importlib.import_module(pkg)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
import numpy as np
import pandas as pd
import statsmodels.api as sm

# IO paths
DATA_PATH = "/app/data/final_data.dta"
OUT_JSON = "/app/data/task2_results.json"

# Load data
try:
    df = pd.read_stata(DATA_PATH, convert_categoricals=False)
except Exception as e:
    raise RuntimeError(f"Failed to read Stata file at {DATA_PATH}: {e}")

# Preprocess and construct variables analogous to the R Task2 path

def center(x):
    return x - np.nanmean(x)

required = ['first_A', 'complaints_2008', 'firm_age', 'emp_size', 'num_names_2008', 'ad_spending']
for c in required:
    if c not in df.columns:
        raise KeyError(f"Missing required column: {c}")

for c in ['complaints_2008', 'firm_age', 'emp_size', 'num_names_2008', 'ad_spending']:
    df[c] = pd.to_numeric(df[c], errors='coerce')

# Effect-code first_A (-0.5, 0.5)
if df['first_A'].dropna().isin([0,1]).all():
    df['first_A_ec'] = np.where(df['first_A'] == 1, 0.5, -0.5)
else:
    uniq = df['first_A'].dropna().unique()
    if len(uniq) == 2:
        df['first_A_ec'] = np.where(df['first_A'] == uniq[0], 0.5, -0.5)
    else:
        df['first_A_ec'] = np.where(df['first_A'] != 0, 0.5, -0.5)

# Create centered covariates (log employee size as in the R scripts)
with np.errstate(divide='ignore'):
    df['emp_size_log'] = np.log(df['emp_size'])

df['firm_ageC'] = center(df['firm_age'])
df['emp_sizeC'] = center(df['emp_size_log'])
df['num_names_2008C'] = center(df['num_names_2008'])
df['ad_spendingC'] = center(df['ad_spending'])

# Build model matrices matching the "including all controls" Poisson spec in Task2 Rmd# Build model matrices matching the "including all controls" Poisson spec in Task2 Rmd
# Add effect-coded controls: multiple_names, chicago, on_google
for cat in ['multiple_names', 'chicago', 'on_google']:
    if cat in df.columns:
        if df[cat].dropna().isin([0,1]).all():
            df[f'{cat}_ec'] = np.where(df[cat] == 1, 0.5, -0.5)
        else:
            uniq = df[cat].dropna().unique()
            if len(uniq) == 2:
                df[f'{cat}_ec'] = np.where(df[cat] == uniq[0], 0.5, -0.5)
            else:
                df[f'{cat}_ec'] = np.where(df[cat] != 0, 0.5, -0.5)
    else:
        raise KeyError(f"Missing required categorical control: {cat}")

model_vars = ['complaints_2008', 'first_A_ec', 'firm_ageC', 'emp_sizeC', 'num_names_2008C', 'ad_spendingC',
              'multiple_names_ec', 'chicago_ec', 'on_google_ec']
df_model = df[model_vars].dropna().copy()

# Dependent and predictors
y = df_model['complaints_2008']
X = df_model.drop(columns=['complaints_2008'])
X = sm.add_constant(X, has_constant='add')

# Fit Poisson GLM and compute robust (HC0) SEs
results = {}
try:
    poisson_model = sm.GLM(y, X, family=sm.families.Poisson())
    poisson_rob = poisson_model.fit(cov_type='HC0')

    coef = poisson_rob.params.get('first_A_ec', np.nan)
    se = poisson_rob.bse.get('first_A_ec', np.nan)
    zval = coef / se if np.isfinite(coef) and np.isfinite(se) and se != 0 else np.nan
    # Use normal approximation for two-sided p-value
    from scipy.stats import norm
    pval = 2 * (1 - norm.cdf(abs(zval))) if np.isfinite(zval) else np.nan

    ci_low = coef - 1.96 * se if np.isfinite(coef) and np.isfinite(se) else np.nan
    ci_high = coef + 1.96 * se if np.isfinite(coef) and np.isfinite(se) else np.nan

    irr = float(np.exp(coef)) if np.isfinite(coef) else np.nan
    irr_ci_low = float(np.exp(ci_low)) if np.isfinite(ci_low) else np.nan
    irr_ci_high = float(np.exp(ci_high)) if np.isfinite(ci_high) else np.nan

    results = {
        'poisson_robust': {
            'coef_first_A_ec': float(coef) if np.isfinite(coef) else np.nan,
            'se_first_A_ec': float(se) if np.isfinite(se) else np.nan,
            'z_first_A_ec': float(zval) if np.isfinite(zval) else np.nan,
            'p_first_A_ec': float(pval) if np.isfinite(pval) else np.nan,
            'ci_first_A_ec': [float(ci_low) if np.isfinite(ci_low) else np.nan, float(ci_high) if np.isfinite(ci_high) else np.nan],
            'irr_first_A_ec': irr,
            'irr_ci_first_A_ec': [irr_ci_low, irr_ci_high]
        }
    }
except Exception as e:
    results = {'error': f'Poisson robust model failed: {e}'}

with open(OUT_JSON, 'w') as f:
    json.dump(results, f, indent=2)

print(json.dumps(results, indent=2))
