import os
import sys
import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
import statsmodels.api as sm
import scipy.stats as st

# Configure data path to use /app/data as required
DATA_PATH = os.environ.get("APP_DATA", "/app/data")
DATA_FILE = os.path.join(DATA_PATH, "wage_gain_table.xlsx")


def linear_hypothesis_f_test(model, R_terms):
    """
    Approximate R's car::linearHypothesis for a set of equality constraints of the form 'var = 0'.
    R_terms: list of strings like ["vSHS", "vHSD", "vSC"] indicating coefficients to test equal to 0.
    Returns F statistic and p-value.
    """
    # Build restriction matrix R and q (zeros)
    params = model.params
    cov = model.cov_params()

    # Identify positions for the requested terms
    keep_terms = []
    for t in R_terms:
        if t in params.index:
            keep_terms.append(t)
        else:
            print(f"WARNING: term '{t}' not in model. Skipping in joint test.")

    if not keep_terms:
        return np.nan, np.nan

    R = np.zeros((len(keep_terms), len(params)))
    for i, t in enumerate(keep_terms):
        j = list(params.index).index(t)
        R[i, j] = 1.0

    q = np.zeros(len(keep_terms))

    # Wald test W = (R*b - q)' [R*Var(b)*R']^{-1} (R*b - q)
    Rb = R.dot(params.values) - q
    RVRT = R.dot(cov).dot(R.T)

    # Numerical stability: pseudo-inverse
    try:
        inv_RVRT = np.linalg.inv(RVRT)
    except np.linalg.LinAlgError:
        inv_RVRT = np.linalg.pinv(RVRT)

    W = float(Rb.T.dot(inv_RVRT).dot(Rb))

    # Convert Wald chi-square to F with df1 = r, df2 = n - k (standard linear model)
    r = len(keep_terms)
    df_resid = model.df_resid  # n - k
    F_stat = W / r
    # Upper tail p-value for F distribution
    p_value = 1 - st.f.cdf(F_stat, r, df_resid)
    return F_stat, p_value


def main():
    # Load data
    try:
        df = pd.read_excel(DATA_FILE)
    except Exception as e:
        print(f"ERROR: Failed to read data file at {DATA_FILE}: {e}")
        sys.exit(1)

    required_cols = [
        "edyrs", "country", "lastUsWageAdjusted", "lastHomeWageAdjusted"
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"ERROR: Missing required columns in dataset: {missing}")
        sys.exit(1)

    # Construct variables following the R code
    df = df.copy()
    vSchool = df["edyrs"]

    # Schooling dummies
    df["vNS"] = (vSchool < 9).astype(int)
    df["vSHS"] = vSchool.isin([9, 10, 11]).astype(int)
    df["vHSD"] = (vSchool == 12).astype(int)
    df["vSC"] = vSchool.isin([13, 14, 15]).astype(int)
    df["vGRAD"] = (vSchool >= 16).astype(int)  # not used in the model but created in R

    # Country dummies (explicitly defined as in the R script)
    for ccode in ["COL", "DOM", "ECU", "GTM", "HTI", "MEX", "NIC", "PER", "SLV"]:
        df[f"v{ccode}"] = (df["country"] == ccode).astype(int)

    # Dependent variable: absolute difference between US adjusted wage and home adjusted wage
    df["vWage"] = (df["lastUsWageAdjusted"] - df["lastHomeWageAdjusted"]).abs()

    # Keep only rows without missing values in used columns
    used_cols = [
        "vWage", "vNS", "vSHS", "vHSD", "vSC",
        "vCOL", "vDOM", "vGTM", "vHTI", "vMEX", "vNIC", "vSLV"
    ]
    dfx = df[used_cols].dropna()

    # Task2 model includes an intercept
    formula = "vWage ~ vNS + vSHS + vHSD + vSC + vCOL + vDOM + vGTM + vHTI + vMEX + vNIC + vSLV"

    model = smf.ols(formula=formula, data=dfx).fit()

    print("=== Task2: OLS with intercept ===")
    print(model.summary())

    # Joint F-test for vSHS = vHSD = vSC = 0
    F_stat, p_val = linear_hypothesis_f_test(model, ["vSHS", "vHSD", "vSC"])
    print("Joint F-test for vSHS = vHSD = vSC = 0:")
    print(f"F = {F_stat}, p = {p_val}")

    # Reduced model as in R (vWage ~ 1 + vNS + country dummies except PER)
    formula_reduced = "vWage ~ vNS + vCOL + vDOM + vGTM + vHTI + vMEX + vNIC + vSLV"
    model_reduced = smf.ols(formula=formula_reduced, data=dfx).fit()
    print("=== Reduced model (Task2 final) ===")
    print(model_reduced.summary())

    # Save outputs
    out_base = os.path.join(DATA_PATH, "Task2_543X6__py")
    os.makedirs(out_base, exist_ok=True)

    pd.DataFrame({
        "term": model.params.index,
        "estimate": model.params.values,
        "std_error": model.bse.values,
        "t_value": model.tvalues.values,
        "p_value": model.pvalues.values
    }).to_csv(os.path.join(out_base, "full_model_coef.csv"), index=False)

    with open(os.path.join(out_base, "joint_test.txt"), "w") as f:
        f.write(f"F = {F_stat}\n")
        f.write(f"p = {p_val}\n")

    pd.DataFrame({
        "term": model_reduced.params.index,
        "estimate": model_reduced.params.values,
        "std_error": model_reduced.bse.values,
        "t_value": model_reduced.tvalues.values,
        "p_value": model_reduced.pvalues.values
    }).to_csv(os.path.join(out_base, "reduced_model_coef.csv"), index=False)

    print(f"Saved Task2 outputs under {out_base}")


if __name__ == "__main__":
    main()
