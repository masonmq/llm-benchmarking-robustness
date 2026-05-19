import importlib
import subprocess
import sys

def ensure(pkg):
    if importlib.util.find_spec(pkg) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

# Ensure dependencies
for p in ["pandas==2.2.2", "numpy==1.26.4", "scipy==1.13.1", "statsmodels==0.14.2", "patsy==0.5.6"]:
    pkg_name = p.split("==")[0]
    try:
        __import__(pkg_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", p])
for p in ["pandas==2.2.2", "numpy==1.26.4", "scipy==1.13.1", "statsmodels==0.14.2", "patsy==0.5.6"]:
    pkg_name = p.split("==")[0]
    try:
        __import__(pkg_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", p])

# Ensure user site-packages is on sys.path and refresh importer caches
import site
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)
import importlib as _il
_il.invalidate_caches()

import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from patsy import dmatrices

# Paths
DATA_PATH = "/app/data/AEJApp-2009-0289-data/household.dta"

# Load data
df = pd.read_stata(DATA_PATH)

# Drop missing domlow
df = df[df["domlow"].notna()].copy()

# Ensure categorical variables are treated as categorical in formulas
# We'll use C(var) in formulas for: caste, borrow, electric

# Create log income
df["log_totinc"] = np.log(df["totinc"])

# Task 1: One-sided t-test (greater) for mean log(totinc) by domlow
low_group = df.loc[df["domlow"] == 1, "log_totinc"].astype(float)
high_group = df.loc[df["domlow"] == 0, "log_totinc"].astype(float)
res = stats.ttest_ind(low_group, high_group, equal_var=False, nan_policy='omit')
# Convert to one-sided (greater) p-value: H1: mean_low > mean_high
if np.nanmean(low_group) > np.nanmean(high_group):
    p_one_sided = res.pvalue / 2.0
else:
    p_one_sided = 1.0 - res.pvalue / 2.0
print("T-TEST (one-sided, greater): log_totinc (domlow==1) > (domlow==0)")
print({"t_stat": float(res.statistic), "p_value_one_sided": float(p_one_sided), "mean_low": float(np.nanmean(low_group)), "mean_high": float(np.nanmean(high_group))})

# Regression models with robust (HC0) SEs
# Model 1 mirrors the R script's full specification
model1_formula = (
    "log_totinc ~ bihar + literate + C(borrow) + totland + landirr + "
    "dist1 + dist2 + dist3 + dist4 + dist5 + dist6 + dist8 + dist9 + dist10 + dist11 + "
    "dist12 + dist13 + dist14 + dist16 + dist17 + dist18 + dist19 + dist20 + dist21 + "
    "dist22 + dist23 + dist24 + dist25 + area + pmixdominant + tolaparea + "
    "gwdevelopment + rainfall + gwavailability + river + canal + noalkal + "
    "nolog + nosoil + noflood + paddy + wheat + cereal + pulse + bulb + seed + cash + "
    "bus3 + tele3 + ps3 + pds3 + bank3 + pps3 + ms3 + ss3 + phc3 + hosp3 + C(electric) + hhelec + "
    "C(caste) + domlow"
)

m1 = smf.ols(model1_formula, data=df).fit(cov_type='HC0')
print("MODEL 1 RESULTS (robust HC0): domlow coefficient")
if 'domlow' in m1.params.index:
    print({
        "coef": float(m1.params['domlow']),
        "se_robust": float(m1.bse['domlow']),
        "t": float(m1.tvalues['domlow']),
        "p": float(m1.pvalues['domlow'])
    })
else:
    print("domlow not in model1 (possibly collinear)")

# Model 2: drop some predictors with sparse data (mirrors R model2)
model2_formula = (
    "log_totinc ~ bihar + literate + C(borrow) + totland + landirr + "
    "dist1 + dist2 + dist3 + dist4 + dist5 + dist6 + dist8 + dist9 + dist11 + "
    "dist12 + dist13 + dist14 + dist16 + dist17 + dist18 + dist19 + dist20 + dist21 + "
    "dist22 + dist23 + dist24 + area + pmixdominant + tolaparea + "
    "river + canal + noalkal + nolog + nosoil + noflood + paddy + wheat + cereal + pulse + bulb + seed + cash + "
    "bus3 + tele3 + ps3 + pds3 + bank3 + pps3 + ms3 + ss3 + phc3 + hosp3 + C(electric) + hhelec + "
    "C(caste) + domlow"
)

m2 = smf.ols(model2_formula, data=df).fit(cov_type='HC0')
print("MODEL 2 RESULTS (robust HC0): domlow coefficient")
if 'domlow' in m2.params.index:
    print({
        "coef": float(m2.params['domlow']),
        "se_robust": float(m2.bse['domlow']),
        "t": float(m2.tvalues['domlow']),
        "p": float(m2.pvalues['domlow'])
    })
else:
    print("domlow not in model2 (possibly collinear)")

# Model 3: restricted model via manual selection (mirrors R model3)
model3_formula = (
    "log_totinc ~ bihar + literate + totland + landirr + "
    "dist1 + dist2 + dist3 + dist4 + dist5 + dist6 + dist8 + dist9 + dist11 + "
    "dist12 + dist13 + dist14 + dist16 + dist17 + dist18 + dist19 + dist20 + dist21 + dist22 + dist23 + dist24 + area + "
    "river + canal + nolog + nosoil + paddy + wheat + pulse + bulb + seed + cash + ps3 + pds3 + pps3 + ms3 + ss3 + "
    "phc3 + C(electric) + hhelec + C(caste) + domlow"
)

m3 = smf.ols(model3_formula, data=df).fit(cov_type='HC0')
print("MODEL 3 RESULTS (robust HC0): domlow coefficient")
if 'domlow' in m3.params.index:
    print({
        "coef": float(m3.params['domlow']),
        "se_robust": float(m3.bse['domlow']),
        "t": float(m3.tvalues['domlow']),
        "p": float(m3.pvalues['domlow'])
    })
else:
    print("domlow not in model3 (possibly collinear)")

# Blinder-Oaxaca decomposition (Reimers weights = 0.5)
# Using the variable set from the R script's oaxaca call
ox_formula_rhs = (
    "bihar + literate + totland + landirr + area + canal + nolog + nosoil + "
    "paddy + wheat + pulse + bulb + seed + cash + ps3 + pds3 + pps3 + ms3 + ss3 + phc3 + C(electric) + hhelec + C(caste)"
)

# Build design matrices once (full sample), then subset rows for groups to ensure same columns
y, X = dmatrices("log_totinc ~ " + ox_formula_rhs, df, return_type='dataframe')
mask_low = df["domlow"] == 1
mask_high = df["domlow"] == 0

X1 = X.loc[mask_low].copy()
X0 = X.loc[mask_high].copy()
y1 = y.loc[mask_low].iloc[:, 0].copy()
y0 = y.loc[mask_high].iloc[:, 0].copy()

# Fit OLS (no robust needed for coefficient estimates in Oaxaca)
res1 = sm.OLS(y1, X1, missing='drop').fit()
res0 = sm.OLS(y0, X0, missing='drop').fit()

b1 = res1.params.values
b0 = res0.params.values
b_star = 0.5 * (b1 + b0)

X1bar = X1.mean(axis=0).values
X0bar = X0.mean(axis=0).values

D = float(y1.mean() - y0.mean())
Explained = float(np.dot((X1bar - X0bar), b_star))
Unexplained = float(np.dot(X1bar, (b1 - b_star)) + np.dot(X0bar, (b_star - b0)))

print("OAXACA (twofold, Reimers weights=0.5):")
print({"D_mean_diff": D, "Explained": Explained, "Unexplained": Unexplained})
