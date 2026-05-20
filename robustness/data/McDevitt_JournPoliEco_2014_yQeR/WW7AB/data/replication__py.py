import os
import json
import numpy as np
import pandas as pd
from scipy import stats
# Ensure statsmodels is available; if not, install it on the fly# Ensure statsmodels is available; if not, install it on the fly
try:
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    from statsmodels.discrete.count_model import ZeroInflatedPoisson
except Exception:
    import sys, subprocess, site
    subprocess.check_call([sys.executable, "-m", "pip", "install", "statsmodels==0.14.1", "patsy==0.5.6"])  
    # Ensure user site-packages is on sys.path
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    from statsmodels.discrete.count_model import ZeroInflatedPoisson

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



def load_data(path):
    # Pandas can read Stata .dta directly
    df = pd.read_stata(path)
    return df


def summarize_groups_ttest(df):
    # Two-sample t-test of complaints_2008 by first_A (unequal variances)
    g0 = df.loc[df["first_A"] == 0, "complaints_2008"].dropna().astype(float)
    g1 = df.loc[df["first_A"] == 1, "complaints_2008"].dropna().astype(float)
    t_stat, p_val = stats.ttest_ind(g1, g0, equal_var=False, nan_policy="omit")
    return {
        "t_stat": float(t_stat) if np.isfinite(t_stat) else None,
        "p_value": float(p_val) if np.isfinite(p_val) else None,
        "n_group0": int(g0.shape[0]),
        "n_group1": int(g1.shape[0]),
        "mean_group0": float(np.mean(g0)) if g0.shape[0] > 0 else None,
        "mean_group1": float(np.mean(g1)) if g1.shape[0] > 0 else None,
    }


def chi_square_test(df):
    # Chi-square test for association between complaints_2008_bin and first_A
    ct = pd.crosstab((df["complaints_2008"] > 0).astype(int), df["first_A"]).fillna(0)
    chi2, p, dof, expected = stats.chi2_contingency(ct.values, correction=False)
    return {
        "chi2": float(chi2),
        "p_value": float(p),
        "dof": int(dof),
        "table": ct.to_dict()
    }


def fit_logit_models(df):
    # Binary outcome
    df = df.copy()
    df["complaints_2008_bin"] = (df["complaints_2008"] > 0).astype(int)

    results = {}

    # Simple: complaints_2008_bin ~ first_A
    model1 = smf.logit("complaints_2008_bin ~ first_A", data=df).fit(disp=False)
    results["logit_simple"] = {
        "params": model1.params.to_dict(),
        "bse": model1.bse.to_dict(),
        "pvalues": model1.pvalues.to_dict(),
        "nobs": int(model1.nobs),
        "llf": float(model1.llf)
    }

    # With controls
    controls = ["ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]
    formula2 = "complaints_2008_bin ~ first_A + " + " + ".join(controls)
    model2 = smf.logit(formula2, data=df).fit(disp=False)
    results["logit_controls"] = {
        "params": model2.params.to_dict(),
        "bse": model2.bse.to_dict(),
        "pvalues": model2.pvalues.to_dict(),
        "nobs": int(model2.nobs),
        "llf": float(model2.llf)
    }

    return results


def fit_poisson_models(df):
    results = {}

    # Simple Poisson: complaints_2008 ~ first_A
    model1 = smf.glm("complaints_2008 ~ first_A", data=df, family=sm.families.Poisson()).fit()
    # Overdispersion factor: Pearson chi2 / df_resid
    pearson_chi2 = np.sum(model1.resid_pearson**2)
    overdispersion = float(pearson_chi2 / model1.df_resid) if model1.df_resid > 0 else None

    results["poisson_simple"] = {
        "params": model1.params.to_dict(),
        "bse": model1.bse.to_dict(),
        "pvalues": model1.pvalues.to_dict(),
        "nobs": int(model1.nobs),
        "pearson_overdispersion": overdispersion
    }

    # With controls
    controls = ["ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]
    formula2 = "complaints_2008 ~ first_A + " + " + ".join(controls)
    model2 = smf.glm(formula2, data=df, family=sm.families.Poisson()).fit()
    pearson_chi2_2 = np.sum(model2.resid_pearson**2)
    overdispersion_2 = float(pearson_chi2_2 / model2.df_resid) if model2.df_resid > 0 else None

    results["poisson_controls"] = {
        "params": model2.params.to_dict(),
        "bse": model2.bse.to_dict(),
        "pvalues": model2.pvalues.to_dict(),
        "nobs": int(model2.nobs),
        "pearson_overdispersion": overdispersion_2
    }

    return results


def fit_zip_models(df):
    results = {}

    # Simple ZIP: complaints_2008 ~ first_A, inflate(first_A)
    exog = sm.add_constant(df[["first_A"]])
    exog_infl = sm.add_constant(df[["first_A"]])
    zip1 = ZeroInflatedPoisson(endog=df["complaints_2008"], exog=exog, exog_infl=exog_infl, inflation="logit").fit(disp=False, maxiter=200)
    results["zip_simple"] = {
        "params": {k: float(v) for k, v in zip1.params.items()},
        "bse": {k: float(v) for k, v in zip1.bse.items()},
        "pvalues": {k: float(v) for k, v in zip1.pvalues.items()},
        "nobs": int(zip1.nobs)
    }

    # With controls in both mean and inflation equations
    controls = ["ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]
    exog2 = sm.add_constant(df[["first_A"] + controls])
    exog_infl2 = sm.add_constant(df[["first_A"] + controls])
    zip2 = ZeroInflatedPoisson(endog=df["complaints_2008"], exog=exog2, exog_infl=exog_infl2, inflation="logit").fit(disp=False, maxiter=200)
    results["zip_controls"] = {
        "params": {k: float(v) for k, v in zip2.params.items()},
        "bse": {k: float(v) for k, v in zip2.bse.items()},
        "pvalues": {k: float(v) for k, v in zip2.pvalues.items()},
        "nobs": int(zip2.nobs)
    }

    # Margins at first_A = 0 and 1, at means of other regressors
    def margins_zip(model, exog_names, exog_infl_names, other_means, first_A_values=(0,1)):
        out = {}
        for val in first_A_values:
            x = other_means.copy()
            z = other_means.copy()
            x["first_A"] = val
            z["first_A"] = val
            # Build design rows
            X_row = [1.0] + [x[name] for name in exog_names if name != "const"]
            Z_row = [1.0] + [z[name] for name in exog_infl_names if name != "const"]
            mu = model.predict(exog=np.array([X_row]), exog_infl=np.array([Z_row]))[0]
            out[val] = float(mu)
        return out

    # Prepare means dict for controls
    mean_vals = {col: float(df[col].mean()) for col in ["first_A", "ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]}
    out_simple = margins_zip(zip1, list(exog.columns), list(exog_infl.columns), {"first_A": mean_vals["first_A"]}, (0,1))
    out_controls = margins_zip(zip2, list(exog2.columns), list(exog_infl2.columns), mean_vals, (0,1))

    results["zip_margins_atmeans_simple_first_A"] = out_simple
    results["zip_margins_atmeans_controls_first_A"] = out_controls

    return results


def fit_nb_models(df):
    results = {}

    # Simple NB: complaints_2008 ~ first_A
    nb1 = smf.glm("complaints_2008 ~ first_A", data=df, family=sm.families.NegativeBinomial()).fit()
    results["nb_simple"] = {
        "params": nb1.params.to_dict(),
        "bse": nb1.bse.to_dict(),
        "pvalues": nb1.pvalues.to_dict(),
        "nobs": int(nb1.nobs)
    }

    # With controls
    controls = ["ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]
    formula2 = "complaints_2008 ~ first_A + " + " + ".join(controls)
    nb2 = smf.glm(formula2, data=df, family=sm.families.NegativeBinomial()).fit()
    results["nb_controls"] = {
        "params": nb2.params.to_dict(),
        "bse": nb2.bse.to_dict(),
        "pvalues": nb2.pvalues.to_dict(),
        "nobs": int(nb2.nobs)
    }

    # Margins at means for first_A
    mean_vals = {col: float(df[col].mean()) for col in ["first_A", "ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]}
    cols_controls = ["first_A", "ad_spend_k", "firm_age", "chicago", "emp_size", "multiple_names"]
    margins_nb_controls = {}
    for val in (0,1):
        row = {**mean_vals, "first_A": float(val)}
        df_row = pd.DataFrame([row])[cols_controls]
        mu = float(nb2.predict(df_row)[0])
        margins_nb_controls[str(val)] = mu

    results["nb_margins_atmeans_controls_first_A"] = margins_nb_controls

    return results


def main():
    df = load_data(DATA_PATH)

    outputs = {}

    # Descriptive tests
    outputs["ttest_complaints_by_first_A"] = summarize_groups_ttest(df)
    outputs["chi2_complaints_bin_by_first_A"] = chi_square_test(df)

    # Models
    outputs["logit_models"] = fit_logit_models(df)
    outputs["poisson_models"] = fit_poisson_models(df)

    # ZIP can occasionally fail to converge; guard with try/except
    try:
        outputs["zip_models"] = fit_zip_models(df)
    except Exception as e:
        outputs["zip_models_error"] = str(e)

    outputs["nb_models"] = fit_nb_models(df)

    # Print a compact JSON summary to stdout
    print(json.dumps(outputs))
    # Also write to a file if helper is available
    try:
        from utils_result_writer import write_execution_result
        write_execution_result(outputs, fname="task1_results.json")
    except Exception:
        pass


if __name__ == "__main__":
    main()
