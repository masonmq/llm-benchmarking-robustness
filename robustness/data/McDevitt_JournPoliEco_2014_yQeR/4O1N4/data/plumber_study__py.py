import json
import importlib, subprocess, sys, site
# Ensure required packages are available when running inside minimal containers
required_packages = ["pandas", "numpy", "statsmodels", "scipy"]

def ensure_package(pkg):
    try:
        return importlib.import_module(pkg)
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", pkg])
        except Exception:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        importlib.invalidate_caches()
        # Add user site-packages to path in case pip installed there
        try:
            user_site = site.getusersitepackages()
            if user_site not in sys.path:
                sys.path.append(user_site)
        except Exception:
            pass
        return importlib.import_module(pkg)

for pkg in required_packages:
    ensure_package(pkg)
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.discrete.discrete_model import NegativeBinomial

# IO paths
DATA_PATH = "/app/data/final_data.dta"
OUT_JSON = "/app/data/task1_results.json"

# Load data
try:
    df = pd.read_stata(DATA_PATH, convert_categoricals=False)
except Exception as e:
    raise RuntimeError(f"Failed to read Stata file at {DATA_PATH}: {e}")

# Preprocess: create centered and effect-coded variables analogous to R code
# Safe utilities

def center(x):
    return x - np.nanmean(x)

# Create transformed columns if they exist
cols_needed = {
    'first_A', 'ad_spending', 'complaints_2008', 'firm_age', 'emp_size',
    'num_names_2008', 'multiple_names', 'chicago', 'on_google'
}
missing = [c for c in cols_needed if c not in df.columns]
if missing:
    raise KeyError(f"Missing required columns in data: {missing}")

# Ensure numeric for continuous vars
for c in ['ad_spending', 'complaints_2008', 'firm_age', 'emp_size', 'num_names_2008']:
    df[c] = pd.to_numeric(df[c], errors='coerce')

# Effect coding for binary indicators: -0.5 (reference) and 0.5 (target)
# Assuming 1 indicates membership in the category (e.g., first_A == 1)
for cat in ['first_A', 'chicago', 'multiple_names', 'on_google']:
    if df[cat].dropna().isin([0,1]).all():
        df[f"{cat}_ec"] = np.where(df[cat] == 1, 0.5, -0.5)
    else:
        # If not strictly 0/1, map the most frequent unique values to two levels
        uniq = df[cat].dropna().unique()
        if len(uniq) == 2:
            high = uniq[0]
            df[f"{cat}_ec"] = np.where(df[cat] == high, 0.5, -0.5)
        else:
            # Fallback: treat nonzero as 1
            df[f"{cat}_ec"] = np.where(df[cat] != 0, 0.5, -0.5)

# Centered continuous covariates
# Log-transform emp_size and ad_spending where appropriate, mirroring R code usage
with np.errstate(divide='ignore'):
    df['emp_size_log'] = np.log(df['emp_size'])
    df['ad_spending_log'] = np.log(df['ad_spending'])

for c, newc in [
    ('ad_spending', 'ad_spendingC'),
    ('firm_age', 'firm_ageC'),
    ('emp_size_log', 'emp_sizeC'),
    ('num_names_2008', 'num_names_2008C')
]:
    df[newc] = center(df[c])

# Drop rows with missing values in model variables
model_vars = ['complaints_2008', 'first_A_ec', 'firm_ageC', 'emp_sizeC', 'num_names_2008C', 'multiple_names_ec', 'chicago_ec', 'ad_spendingC', 'on_google_ec']
df_model = df[model_vars].dropna().copy()

# Design matrices
y = df_model['complaints_2008']
X = df_model.drop(columns=['complaints_2008'])
X = sm.add_constant(X, has_constant='add')

results_out = {"poisson_robust": None, "negative_binomial": None}

# Poisson GLM with robust SE (HC0)
try:
    poisson_model = sm.GLM(y, X, family=sm.families.Poisson())
    poisson_res = poisson_model.fit()
    # Robust covariance
    poisson_rob = poisson_model.fit(cov_type='HC0')

    # Extract key stats for first_A effect-coded regressor
    coef = poisson_rob.params.get('first_A_ec', np.nan)
    se = poisson_rob.bse.get('first_A_ec', np.nan)
    zval = coef / se if np.isfinite(coef) and np.isfinite(se) and se != 0 else np.nan
    pval = 2 * (1 - sm.distributions.norm.cdf(abs(zval))) if np.isfinite(zval) else np.nan
    ci_low = coef - 1.96 * se if np.isfinite(coef) and np.isfinite(se) else np.nan
    ci_high = coef + 1.96 * se if np.isfinite(coef) and np.isfinite(se) else np.nan

    irr = float(np.exp(coef)) if np.isfinite(coef) else np.nan
    irr_ci_low = float(np.exp(ci_low)) if np.isfinite(ci_low) else np.nan
    irr_ci_high = float(np.exp(ci_high)) if np.isfinite(ci_high) else np.nan

    results_out['poisson_robust'] = {
        'coef_first_A_ec': float(coef) if np.isfinite(coef) else np.nan,
        'se_first_A_ec': float(se) if np.isfinite(se) else np.nan,
        'z_first_A_ec': float(zval) if np.isfinite(zval) else np.nan,
        'p_first_A_ec': float(pval) if np.isfinite(pval) else np.nan,
        'ci_first_A_ec': [float(ci_low) if np.isfinite(ci_low) else np.nan, float(ci_high) if np.isfinite(ci_high) else np.nan],
        'irr_first_A_ec': irr,
        'irr_ci_first_A_ec': [irr_ci_low, irr_ci_high]
    }
except Exception as e:
    results_out['poisson_robust'] = {'error': f'Poisson model failed: {e}'}

# Negative Binomial (NB2) using discrete model
try:
    nb_model = NegativeBinomial(y, X)
    nb_res = nb_model.fit(disp=False)
    coef = nb_res.params.get('first_A_ec', np.nan)
    se = nb_res.bse.get('first_A_ec', np.nan)
    zval = coef / se if np.isfinite(coef) and np.isfinite(se) and se != 0 else np.nan
    pval = 2 * (1 - sm.distributions.norm.cdf(abs(zval))) if np.isfinite(zval) else np.nan
    ci_low = coef - 1.96 * se if np.isfinite(coef) and np.isfinite(se) else np.nan
    ci_high = coef + 1.96 * se if np.isfinite(coef) and np.isfinite(se) else np.nan

    irr = float(np.exp(coef)) if np.isfinite(coef) else np.nan
    irr_ci_low = float(np.exp(ci_low)) if np.isfinite(ci_low) else np.nan
    irr_ci_high = float(np.exp(ci_high)) if np.isfinite(ci_high) else np.nan

    results_out['negative_binomial'] = {
        'coef_first_A_ec': float(coef) if np.isfinite(coef) else np.nan,
        'se_first_A_ec': float(se) if np.isfinite(se) else np.nan,
        'z_first_A_ec': float(zval) if np.isfinite(zval) else np.nan,
        'p_first_A_ec': float(pval) if np.isfinite(pval) else np.nan,
        'ci_first_A_ec': [float(ci_low) if np.isfinite(ci_low) else np.nan, float(ci_high) if np.isfinite(ci_high) else np.nan],
        'irr_first_A_ec': irr,
        'irr_ci_first_A_ec': [irr_ci_low, irr_ci_high],
        'alpha': float(nb_res.params.get('alpha', np.nan)) if 'alpha' in nb_res.params.index else None
    }
except Exception as e:
    results_out['negative_binomial'] = {'error': f'Negative binomial model failed: {e}'}

# Write results JSON
with open(OUT_JSON, 'w') as f:
    json.dump(results_out, f, indent=2)

print(json.dumps(results_out, indent=2))
