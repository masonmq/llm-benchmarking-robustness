import importlib
import subprocess
import sys

def ensure(pkg):
    if importlib.util.find_spec(pkg) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

# Ensure dependencies
for p in ["pandas==2.2.2", "numpy==1.26.4", "statsmodels==0.14.2", "patsy==0.5.6"]:
    pkg_name = p.split("==")[0]
    try:
        __import__(pkg_name)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", p])

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf

DATA_PATH = "/app/data/AEJApp-2009-0289-data/household.dta"

df = pd.read_stata(DATA_PATH)

# Drop missing domlow
df = df[df["domlow"].notna()].copy()

# Create log income
df["log_totinc"] = np.log(df["totinc"])

# Task 2: Restricted regression without the excluded predictors
model_formula = (
    "log_totinc ~ bihar + literate + totland + cash + C(electric) + C(caste) + domlow"
)

m = smf.ols(model_formula, data=df).fit(cov_type='HC0')

print("TASK 2 MODEL (robust HC0): domlow coefficient")
if 'domlow' in m.params.index:
    print({
        "coef": float(m.params['domlow']),
        "se_robust": float(m.bse['domlow']),
        "t": float(m.tvalues['domlow']),
        "p": float(m.pvalues['domlow'])
    })
else:
    print("domlow not in model (possibly collinear)")
