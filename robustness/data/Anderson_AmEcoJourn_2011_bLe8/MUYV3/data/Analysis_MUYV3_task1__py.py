import json
import warnings
import os
import sys

# Ensure required packages are available inside the container even if image deps failed
user_site = os.path.expanduser("~/.local/lib/python3.10/site-packages")
if os.path.isdir(user_site) and user_site not in sys.path:
    sys.path.append(user_site)

try:
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.regression.mixed_linear_model import MixedLM
except ModuleNotFoundError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "statsmodels==0.14.1", "pandas==2.0.3", "numpy==1.24.4", "scipy==1.10.1", "pyreadstat==1.2.2"])  # noqa: E501
    if os.path.isdir(user_site) and user_site not in sys.path:
        sys.path.append(user_site)
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.regression.mixed_linear_model import MixedLM

warnings.filterwarnings("ignore")


def load_data():
    hh_path = "/app/data/AEJApp-2009-0289-data/household.dta"
    vil_path = "/app/data/AEJApp-2009-0289-data/village.dta"
    hh = pd.read_stata(hh_path, convert_categoricals=True)
    vil = pd.read_stata(vil_path, convert_categoricals=True)
    return hh, vil


def preprocess_task1(hh: pd.DataFrame) -> pd.DataFrame:
    df = hh.copy()
    # 1) Create district id from dist1:dist25 as in R code (weighted sum)
    dist_cols = [f"dist{i}" for i in range(1, 26) if f"dist{i}" in df.columns]
    if len(dist_cols) == 25:
        weights = np.arange(1, 26, dtype=float)
        df["district"] = (df[dist_cols].values * weights).sum(axis=1)
    else:
        # Fallback: if not all dist dummies present, set district to NaN
        df["district"] = np.nan

    # 2) Crop controls average
    crop_vars = ["paddy", "wheat", "cereal", "pulse", "bulb", "seed", "cash"]
    present_crops = [c for c in crop_vars if c in df.columns]
    if len(present_crops) == 7:
        df["cropcontrol"] = df[present_crops].mean(axis=1)
    else:
        df["cropcontrol"] = np.nan

    # Keep only complete cases as in R (complete.cases on entire data frame)
    df_cc = df.dropna(axis=0, how="any").copy()

    # Log-transform totinc and remove outliers using 1.5*IQR on log(totinc)
    df_cc = df_cc[df_cc["totinc"] > 0].copy()
    df_cc["log_totinc"] = np.log(df_cc["totinc"].astype(float))
    q1 = df_cc["log_totinc"].quantile(0.25)
    q3 = df_cc["log_totinc"].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    df_filt = df_cc[(df_cc["log_totinc"] >= lower) & (df_cc["log_totinc"] <= upper)].copy()

    # Ensure categorical coding similar to R
    if "caste" in df_filt.columns:
        df_filt["caste"] = df_filt["caste"].astype("category")
    for col in ["bihar", "district", "village"]:
        if col in df_filt.columns:
            df_filt[col] = df_filt[col].astype("category")

    return df_filt


def fit_mixedlm(formula: str, data: pd.DataFrame, random_top: str, vc_components: dict):
    # MixedLM with variance components to emulate nested random effects
    model = MixedLM.from_formula(formula, groups=data[random_top], vc_formula=vc_components, data=data, re_formula="1")
    res = model.fit(method="lbfgs", disp=False)
    return res


def main():
    hh, vil = load_data()
    df = preprocess_task1(hh)

    results = {"task": "Task1", "n_after_filtering": int(df.shape[0])}

    # Model 1: base model with domlow only, random effects bihar/district/village
    vc = {}
    if "district" in df.columns:
        vc["district"] = "0 + C(district)"
    if "village" in df.columns:
        vc["village"] = "0 + C(village)"
    formula1 = "log_totinc ~ domlow"
    try:
        res1 = fit_mixedlm(formula1, df, random_top="bihar", vc_components=vc)
        coef = float(res1.params.get("domlow", np.nan))
        se = float(res1.bse.get("domlow", np.nan))
        zval = coef / se if (se is not None and se != 0 and not np.isnan(se)) else np.nan
        pval = float(res1.pvalues.get("domlow", np.nan))
        results["model1"] = {"formula": formula1, "coef_domlow": coef, "se_domlow": se, "z_domlow": zval, "p_domlow": pval}
    except Exception as e:
        results["model1_error"] = str(e)

    # Model 2: full controls as in R code
    controls = [
        "literate", "totland", "C(caste)", "cropcontrol",
        "bus3", "tele3", "ps3", "pds3", "bank3", "pps3", "ms3", "ss3", "phc3", "hosp3",
        "gwdevelopment", "rainfall", "gwavailability", "river", "canal",
        "noalkal", "nolog", "nosoil", "noflood", "area", "pmixdominant", "tolaparea"
    ]
    present_controls = [c for c in controls if (c.startswith("C(") or c in df.columns)]
    rhs = " + ".join(present_controls + ["domlow"]) if present_controls else "domlow"
    formula2 = f"log_totinc ~ {rhs}"
    try:
        res2 = fit_mixedlm(formula2, df, random_top="bihar", vc_components=vc)
        coef = float(res2.params.get("domlow", np.nan))
        se = float(res2.bse.get("domlow", np.nan))
        zval = coef / se if (se is not None and se != 0 and not np.isnan(se)) else np.nan
        pval = float(res2.pvalues.get("domlow", np.nan))
        results["model2"] = {"formula": formula2, "coef_domlow": coef, "se_domlow": se, "z_domlow": zval, "p_domlow": pval}
    except Exception as e:
        results["model2_error"] = str(e)

    # Output JSON results
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
