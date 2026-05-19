import json
import warnings
import numpy as np
import pandas as pd

# Ensure required packages are available inside the container even if image deps failed
try:
    import statsmodels.api as sm
    from statsmodels.regression.mixed_linear_model import MixedLM
except ModuleNotFoundError:
    import sys, subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "statsmodels==0.14.1", "pandas==2.0.3", "numpy==1.24.4", "scipy==1.10.1", "pyreadstat==1.2.2"])  # noqa: E501
    import statsmodels.api as sm
    from statsmodels.regression.mixed_linear_model import MixedLM

warnings.filterwarnings("ignore")


def load_data():
    hh_path = "/app/data/AEJApp-2009-0289-data/household.dta"
    vil_path = "/app/data/AEJApp-2009-0289-data/village.dta"
    hh = pd.read_stata(hh_path, convert_categoricals=True)
    vil = pd.read_stata(vil_path, convert_categoricals=True)
    return hh, vil


def preprocess_task2(hh: pd.DataFrame) -> pd.DataFrame:
    df = hh.copy()
    # Only complete cases overall, as in R code
    df = df.dropna(axis=0, how="any").copy()
    # Log-transform totinc and remove outliers using 1.5*IQR on log(totinc)
    df = df[df["totinc"] > 0].copy()
    df["log_totinc"] = np.log(df["totinc"].astype(float))
    q1 = df["log_totinc"].quantile(0.25)
    q3 = df["log_totinc"].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    df_filt = df[(df["log_totinc"] >= lower) & (df["log_totinc"] <= upper)].copy()

    # Cast grouping variables to categorical
    for col in ["bihar", "village"]:
        if col in df_filt.columns:
            df_filt[col] = df_filt[col].astype("category")
    if "caste" in df_filt.columns:
        df_filt["caste"] = df_filt["caste"].astype("category")

    return df_filt


def fit_mixedlm(formula: str, data: pd.DataFrame, random_top: str, vc_components: dict):
    model = MixedLM.from_formula(formula, groups=data[random_top], vc_formula=vc_components, data=data, re_formula="1")
    res = model.fit(method="lbfgs", disp=False)
    return res


def main():
    hh, vil = load_data()
    df = preprocess_task2(hh)

    results = {"task": "Task2", "n_after_filtering": int(df.shape[0])}

    # Model 1: base model with domlow only, random effects bihar/village
    vc = {"village": "0 + C(village)"} if "village" in df.columns else {}
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

    # Model 2: with allowed controls and their interactions: literate * totland * caste * domlow
    rhs = "literate * totland * C(caste) * domlow"
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

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
