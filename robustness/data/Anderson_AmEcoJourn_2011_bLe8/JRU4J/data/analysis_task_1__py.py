import os
import subprocess
import sys

# Attempt to import required libraries; install if missing
required = [
    ("pandas", "pandas==2.2.2"),
    ("numpy", "numpy==1.26.4"),
    ("statsmodels", "statsmodels==0.14.2"),
    ("patsy", "patsy==0.5.6"),
]
for mod, spec in required:
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", spec])

# Ensure user site-packages is on sys.path (pip may install there for non-root)
import site, importlib
user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.append(user_site)
importlib.invalidate_caches()

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf

# I/O base directory (must be mounted to /app/data)
BASE_DIR = "/app/data/AEJApp-2009-0289-data"
RESULTS_PATH = "/app/data/results_task_1.txt"

# Load data
household_path = os.path.join(BASE_DIR, "household.dta")
village_path = os.path.join(BASE_DIR, "village.dta")

hh = pd.read_stata(household_path, convert_categoricals=True)
vg = pd.read_stata(village_path, convert_categoricals=True)

# Prepare keys and variables for merge
# Convert village IDs to strings for consistent join behavior (mirroring R code)
hh['village'] = hh['village'].astype('Int64').astype(str)
vg['village'] = vg['village'].astype('Int64').astype(str)

# Keep only variables needed
hh_sub = hh[['hhcode', 'village', 'caste', 'totinc']].copy()
vg_sub = vg[['village', 'domhigh']].copy()

# Merge household with domhigh from village
dat = hh_sub.merge(vg_sub, on='village', how='left')

# Keep observations where domhigh is 0 or 1
# domhigh can be float or object depending on Stata labels; coerce to numeric safely
# Keep values exactly 0 or 1

dat['domhigh_num'] = pd.to_numeric(dat['domhigh'], errors='coerce')
dat = dat[dat['domhigh_num'].isin([0.0, 1.0])].copy()

# For modeling, use numeric 0/1 for domhigh
dat['domhigh'] = dat['domhigh_num']

# Ensure caste is treated categorically (string labels ok)
if not pd.api.types.is_categorical_dtype(dat['caste']):
    dat['caste'] = dat['caste'].astype(str)

# Mixed effects model: totinc ~ caste + domhigh + caste:domhigh + (1|village)
# statsmodels MixedLM supports formula with categorical terms via patsy
# By default, MixedLM.fit uses REML=True

model = smf.mixedlm("totinc ~ C(caste) + domhigh + C(caste):domhigh", data=dat, groups=dat["village"]) 
res = model.fit(reml=True, method='lbfgs')

# Write results to file
with open(RESULTS_PATH, 'w') as f:
    f.write("Linear Mixed Effects Model (random intercept for village)\n")
    f.write("Formula: totinc ~ C(caste) + domhigh + C(caste):domhigh\n\n")
    f.write(str(res.summary()))
    f.write("\n\nFixed effects coefficients:\n")
    f.write(str(res.fe_params))
    f.write("\n\nP-values (fixed effects):\n")
    try:
        f.write(str(res.pvalues))
    except Exception as e:
        f.write(f"P-values not available due to: {e}")

print(f"Task1 results written to {RESULTS_PATH}")
