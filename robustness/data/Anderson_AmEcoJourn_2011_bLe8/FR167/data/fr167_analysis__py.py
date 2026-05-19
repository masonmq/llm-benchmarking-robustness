import json
import os
import warnings
import importlib
import site
import sys

import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis, chi2

# Robust import for statsmodels with runtime installation if missing

def ensure_statsmodels():
    try:
        sm = importlib.import_module("statsmodels.api")
        ols_mod = importlib.import_module("statsmodels.formula.api")
        mixed_mod = importlib.import_module("statsmodels.regression.mixed_linear_model")
        return sm, ols_mod.ols, mixed_mod.MixedLM
    except Exception as e:
        print(f"statsmodels not available ({e}); installing at runtime...", flush=True)
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "statsmodels==0.14.1", "patsy>=0.5.3"])  # Patsy for formulas
        except Exception as ie:
            print(f"Runtime install failed: {ie}", flush=True)
            raise
        # Ensure user site-packages is on sys.path
        try:
            user_paths = []
            try:
                user_paths = site.getusersitepackages()
            except Exception:
                user_paths = [site.USER_SITE]
            if isinstance(user_paths, str):
                user_paths = [user_paths]
            for p in user_paths:
                if p and p not in sys.path:
                    sys.path.append(p)
        except Exception:
            pass
        sm = importlib.import_module("statsmodels.api")
        ols_mod = importlib.import_module("statsmodels.formula.api")
        mixed_mod = importlib.import_module("statsmodels.regression.mixed_linear_model")
        return sm, ols_mod.ols, mixed_mod.MixedLM

sm, ols, MixedLM = ensure_statsmodels()

# Ensure data root
DATA_ROOT = os.environ.get("APP_DATA", "/app/data")
HOUSEHOLD_PATH = os.path.join(DATA_ROOT, "AEJApp-2009-0289-data", "household.dta")
TABLE2_PATH = os.path.join(DATA_ROOT, "AEJApp-2009-0289-data", "table2.dta")
OUT_PATH = os.path.join(DATA_ROOT, "results_fr167.json")

np.set_printoptions(suppress=True)
pd.set_option('display.width', 200)


def read_stata(path):
    return pd.read_stata(path, convert_categoricals=False)


def compute_mahalanobis(df, cols):
    X = df[cols].astype(float).dropna()
    if X.shape[0] == 0:
        return pd.DataFrame(index=df.index, columns=['Mahalnobis', 'pvalue'])
    mu = X.mean().values
    S = np.cov(X.values, rowvar=False)
    S_inv = np.linalg.pinv(S)
    diff = X.values - mu
    md = np.einsum('ij,jk,ik->i', diff, S_inv, diff)
    # Mirror R script's df=1 choice though k=2
    pvals = chi2.sf(md, df=1)
    res = pd.DataFrame({'Mahalnobis': md, 'pvalue': pvals}, index=X.index)
    return res


def fit_mixedlm(df, formula, group_col):
    # Build a clean dataset with aligned endog, exog, and groups
    try:
        lhs, rhs = [s.strip() for s in formula.split('~')]
        y = lhs
        xs = [c.strip() for c in rhs.split('+')]
        cols = [y] + xs
    except Exception:
        cols = ['totinc', 'domlow']
    needed = list(set(cols + [group_col]))
    dd = df[needed].copy()
    for c in cols:
        dd[c] = pd.to_numeric(dd[c], errors='coerce')
    dd[group_col] = pd.to_numeric(dd[group_col], errors='coerce')
    dd = dd.dropna(subset=cols + [group_col]).reset_index(drop=True)
    if dd.empty or dd[group_col].nunique() < 2:
        return None, None
    # Use from_formula with aligned groups
    try:
        mdf = MixedLM.from_formula(formula, groups=dd[group_col].values, data=dd, missing='drop')
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("ignore")
            mfit = mdf.fit(reml=False, method='lbfgs', disp=False, maxiter=200)
        return mfit, int(mfit.nobs)
    except Exception as e:
        print(f"MixedLM failed: {e}")
        return None, int(dd.shape[0])


def fit_ols(df, formula):
    dd = df.copy()
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("ignore")
        mfit = ols(formula, data=dd).fit()
    n = int(mfit.nobs)
    return mfit, n


def ci_from_res(res, param, alpha=0.05):
    try:
        ci = res.conf_int(alpha=alpha).loc[param].tolist()
        return [float(ci[0]), float(ci[1])]
    except Exception:
        return [None, None]


def summarize_mixedlm(res, n, param='domlow'):
    if res is None:
        return None
    coef = None; se = None; zval = None; pval = None
    try:
        coef = float(res.params.get(param, np.nan))
    except Exception:
        pass
    try:
        se = float(res.bse.get(param, np.nan))
    except Exception:
        pass
    try:
        zval = float(res.tvalues.get(param, np.nan))
    except Exception:
        pass
    try:
        pval = float(res.pvalues.get(param, np.nan))
    except Exception:
        pass
    out = {
        'n': int(n) if n is not None else None,
        'coef': coef,
        'se': se,
        'z': zval,
        'pvalue': pval,
        'ci95': ci_from_res(res, param)
    }
    return out


def summarize_ols(res, n, param='domlow'):
    out = {
        'n': int(n),
        'coef': float(res.params.get(param, np.nan)),
        'se': float(res.bse.get(param, np.nan)),
        't': float(res.tvalues.get(param, np.nan)),
        'pvalue': float(res.pvalues.get(param, np.nan)),
        'ci95': ci_from_res(res, param)
    }
    return out


def main():
    # Load data
    d = read_stata(HOUSEHOLD_PATH)
    table2 = read_stata(TABLE2_PATH)

    # Merge selected dominance indicators for cross-checks
    t2_small = table2[['hhcode', 'domhigh', 'domlow']].copy()
    t2_small = t2_small.rename(columns={'domhigh': 'domhigh_from_table2', 'domlow': 'domlow_from_table2'})
    d = d.merge(t2_small, on='hhcode', how='left')

    # Normality metrics for totinc
    ti = pd.to_numeric(d['totinc'], errors='coerce')
    totinc_skew = float(skew(ti.dropna())) if ti.notna().any() else None
    totinc_kurt = float(kurtosis(ti.dropna(), fisher=True)) if ti.notna().any() else None

    # Standardize totinc (grand-mean z)
    d['grand_z_totinc'] = (ti - ti.mean()) / ti.std(ddof=0)

    # Mahalanobis on domlow and totinc
    md_input = d[['domlow', 'totinc', 'hhcode']].dropna(subset=['domlow', 'totinc', 'hhcode']).copy()
    if not md_input.empty:
        md_vals = compute_mahalanobis(md_input, ['domlow', 'totinc'])
        md_input = md_input.join(md_vals)
        md_input['Outlier'] = (md_input['pvalue'] < 0.001).astype(int)
        d = d.merge(md_input[['hhcode', 'Mahalnobis', 'pvalue', 'Outlier']], on='hhcode', how='left')

    # Define outlier villages
    outlier_villages = {70, 61, 60, 84, 59, 58}
    d['village_num'] = pd.to_numeric(d['village'], errors='coerce')

    full_df = d.copy()
    nooutliers_df = d[~d['village_num'].isin(list(outlier_villages))].copy()

    results = {
        'normality': {
            'totinc': {
                'skewness': totinc_skew,
                'kurtosis_fisher': totinc_kurt
            }
        },
        'task1': {
            'full': {},
            'no_outliers': {}
        },
        'task2': {
            'full': {},
            'no_outliers': {}
        }
    }

    # MixedLM: totinc ~ domlow + (1|village)
    mix_full_res, mix_full_n = fit_mixedlm(full_df, 'totinc ~ domlow', 'village_num')
    mix_no_res, mix_no_n = fit_mixedlm(nooutliers_df, 'totinc ~ domlow', 'village_num')

    results['task1']['full']['mixedlm'] = summarize_mixedlm(mix_full_res, mix_full_n)
    results['task1']['no_outliers']['mixedlm'] = summarize_mixedlm(mix_no_res, mix_no_n)

    # OLS as robustness
    ols_full_res, ols_full_n = fit_ols(full_df.dropna(subset=['totinc', 'domlow']), 'totinc ~ domlow')
    ols_no_res, ols_no_n = fit_ols(nooutliers_df.dropna(subset=['totinc', 'domlow']), 'totinc ~ domlow')

    results['task1']['full']['ols'] = summarize_ols(ols_full_res, ols_full_n)
    results['task1']['no_outliers']['ols'] = summarize_ols(ols_no_res, ols_no_n)

    # Task2 mirrors Task1
    results['task2'] = results['task1']

    # Print brief summary
    print("FR167 MixedLM full (domlow):", results['task1']['full']['mixedlm'])
    print("FR167 MixedLM no_outliers (domlow):", results['task1']['no_outliers']['mixedlm'])
    print("FR167 OLS full (domlow):", results['task1']['full']['ols'])
    print("FR167 OLS no_outliers (domlow):", results['task1']['no_outliers']['ols'])

    # Save results
    with open(OUT_PATH, 'w') as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
