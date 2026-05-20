import os
import json
import numpy as np
import pandas as pd
from scipy import stats
# Ensure statsmodels is available; if not, install it on the fly# Ensure statsmodels is available; if not, install it on the fly
try:
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
except Exception:
    import sys, subprocess, site
    subprocess.check_call([sys.executable, "-m", "pip", "install", "statsmodels==0.14.1", "patsy==0.5.6"])  
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

# Resolve data path robustly
CANDIDATE_DATA_PATHS = [
    "/app/data/data/final_data.dta",
    "/workspace/data/final_data.dta",
    os.path.join(os.path.dirname(__file__), "final_data.dta"),
]
DATA_PATH = None
for p in CANDIDATE_DATA_PATHS:
    if os.path.exists(p):
        DATA_PATH = p
        break
if DATA_PATH is None:
    raise FileNotFoundError("Could not locate final_data.dta in expected paths: " + ", ".join(CANDIDATE_DATA_PATHS))



def main():
    df = pd.read_stata(DATA_PATH)

    # Task 2: produce a single main result in terms of z-/t-/F-/chi^2; use overall complaints; Illinois firms only are already in the dataset
    # t-test of complaints_2008 by first_A
    g0 = df.loc[df["first_A"] == 0, "complaints_2008"].dropna().astype(float)
    g1 = df.loc[df["first_A"] == 1, "complaints_2008"].dropna().astype(float)
    t_stat, p_val = stats.ttest_ind(g1, g0, equal_var=False, nan_policy="omit")

    # Negative binomial: complaints_2008 ~ first_A
    nb = smf.glm("complaints_2008 ~ first_A", data=df, family=sm.families.NegativeBinomial()).fit()
    # Extract z for first_A = coef / se
    coef = float(nb.params.get("first_A"))
    se = float(nb.bse.get("first_A"))
    z_stat = coef / se if se > 0 else None
    df_m = int(nb.df_model)

    result = {
        "ttest": {"t_stat": float(t_stat) if np.isfinite(t_stat) else None, "p_value": float(p_val) if np.isfinite(p_val) else None, "n0": int(g0.shape[0]), "n1": int(g1.shape[0])},
        "nbreg": {"coef_first_A": coef, "se_first_A": se, "z_first_A": z_stat, "df_model": df_m, "p_first_A": float(nb.pvalues.get("first_A"))}
    }

    print(json.dumps(result))
    # Also write to file
    try:
        from utils_result_writer import write_execution_result
        write_execution_result(result, fname="task2_results.json")
    except Exception:
        pass


if __name__ == "__main__":
    main()
