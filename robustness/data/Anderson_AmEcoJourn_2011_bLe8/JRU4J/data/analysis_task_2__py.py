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

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm

# I/O base directory (must be mounted to /app/data)
BASE_DIR = "/app/data/AEJApp-2009-0289-data"
RESULTS_PATH = "/app/data/results_task_2.txt"

# Load data
household_path = os.path.join(BASE_DIR, "household.dta")
village_path = os.path.join(BASE_DIR, "village.dta")

hh = pd.read_stata(household_path, convert_categoricals=True)
vg = pd.read_stata(village_path, convert_categoricals=True)

# Prepare keys and variables for merge
hh['village'] = hh['village'].astype('Int64').astype(str)
vg['village'] = vg['village'].astype('Int64').astype(str)

hh_sub = hh[['hhcode', 'village', 'caste', 'totinc']].copy()
vg_sub = vg[['village', 'domhigh']].copy()

# Merge
dat = hh_sub.merge(vg_sub, on='village', how='left')

# Filter domhigh 0/1
dat['domhigh_num'] = pd.to_numeric(dat['domhigh'], errors='coerce')
dat = dat[dat['domhigh_num'].isin([0.0, 1.0])].copy()
dat['domhigh'] = dat['domhigh_num']

# Categorical caste
if not pd.api.types.is_categorical_dtype(dat['caste']):
    dat['caste'] = dat['caste'].astype(str)

# Fit mixed model identical to Task1
model = smf.mixedlm("totinc ~ C(caste) + domhigh + C(caste):domhigh", data=dat, groups=dat["village"]) 
res = model.fit(reml=True, method='lbfgs')

# There is no direct anova for MixedLM in statsmodels like lmerTest::anova; we instead report Wald tests per term
# Compute Wald tests for domhigh and interactions
from patsy import dmatrix

# Fixed effect names
fe_names = res.model.exog_names
params = res.fe_params
bse = res.bse_fe
zvals = params / bse

# Write results
with open(RESULTS_PATH, 'w') as f:
    f.write("Linear Mixed Effects Model (random intercept for village)\n")
    f.write("Formula: totinc ~ C(caste) + domhigh + C(caste):domhigh\n\n")
    f.write(str(res.summary()))
    f.write("\n\nFixed effects coefficients:\n")
    f.write(str(res.fe_params))
    f.write("\n\nZ-values (fixed effects):\n")
    f.write(str(zvals))

print(f"Task2 results written to {RESULTS_PATH}")
