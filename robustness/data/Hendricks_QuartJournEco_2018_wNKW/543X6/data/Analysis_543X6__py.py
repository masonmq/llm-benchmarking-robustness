import os
import sys
import pandas as pd
import numpy as np
import statsmodels.formula.api as smf

# Configure data path to use /app/data as required
DATA_PATH = os.environ.get("APP_DATA", "/app/data")
DATA_FILE = os.path.join(DATA_PATH, "wage_gain_table.xlsx")

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

    # Replicate R formula without intercept (-1)
    formula = "vWage ~ vNS + vSHS + vHSD + vSC + vCOL + vDOM + vGTM + vHTI + vMEX + vNIC + vSLV - 1"

    model = smf.ols(formula=formula, data=dfx).fit()

    # Print summary to stdout
    print("=== Task1: OLS without intercept (matching R '-1') ===")
    print(model.summary())

    # Save coefficients to /app/data for downstream collection
    out_csv = os.path.join(DATA_PATH, "Analysis_543X6__py_results.csv")
    coef_df = (
        pd.DataFrame({
            "term": model.params.index,
            "estimate": model.params.values,
            "std_error": model.bse.values,
            "t_value": model.tvalues.values,
            "p_value": model.pvalues.values
        })
    )
    coef_df.to_csv(out_csv, index=False)
    print(f"Saved coefficient table to {out_csv}")

if __name__ == "__main__":
    main()
