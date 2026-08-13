#!/usr/bin/env python3
"""
Task 2 comparable-result analysis for Hendricks & Schoellman (2018) focal claim.
Instruction: use the pooled sample of immigrants from poor countries in the NIS
and the Migration Projects, including Mexico. Do not control for sector
(agriculture/nonagriculture) or region (rural/urban).

The authorized file wage_gain_table.xlsx is treated as the pooled poor-country
wage-gain table supplied for this task. Mexico is retained. The focal result is
an unadjusted education-category contrast in log wage gains, with all education
categories retained in the model and college-degree immigrants as the reference.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[4]
DATA_PATH = ROOT / "data" / "wage_gain_table.xlsx"
OUT_DIR = Path(__file__).resolve().parent

REQUIRED_COLUMNS = [
    "edyrs", "lastHomeWageAdjusted", "lastUsWageAdjusted", "country"
]
PROHIBITED_CONTROLS = ["occGroupLastHomeJob", "occGroupLastUsJob"]


def education_group(edyrs):
    """Claim-relevant schooling categories.
    Never high school is edyrs <= 8; college degree is edyrs >= 16.
    Intermediate categories are retained to avoid restricting the analysis only
    to the two focal endpoint groups.
    """
    if pd.isna(edyrs):
        return np.nan
    if edyrs <= 8:
        return "no_high_school"
    if edyrs <= 11:
        return "some_high_school"
    if edyrs <= 15:
        return "high_school_some_college"
    return "college_degree"


def main():
    df0 = pd.read_excel(DATA_PATH)
    sample_flow = []
    sample_flow.append({"step": "starting_rows", "rows": int(len(df0)), "removed": 0})

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df0.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    df = df0.copy()
    before = len(df)
    df = df.dropna(subset=REQUIRED_COLUMNS)
    sample_flow.append({
        "step": "drop_missing_required_columns",
        "rows": int(len(df)),
        "removed": int(before - len(df))
    })

    # Task instruction requires Mexico to be included. No country is dropped from
    # the authorized pooled poor-country table; report whether MEX is present.
    mexico_rows = int((df["country"] == "MEX").sum())

    before = len(df)
    df = df[(df["lastHomeWageAdjusted"] > 0) & (df["lastUsWageAdjusted"] > 0)]
    sample_flow.append({
        "step": "drop_nonpositive_adjusted_wages_for_logs",
        "rows": int(len(df)),
        "removed": int(before - len(df))
    })

    df["log_wage_gain"] = np.log(df["lastUsWageAdjusted"]) - np.log(df["lastHomeWageAdjusted"])
    df["edu_group"] = df["edyrs"].apply(education_group)

    before = len(df)
    df = df.dropna(subset=["log_wage_gain", "edu_group"])
    sample_flow.append({
        "step": "drop_missing_constructed_variables",
        "rows": int(len(df)),
        "removed": int(before - len(df))
    })

    # No sector/agriculture and no rural/urban controls are included. Occupation
    # group variables, while present in the file, are deliberately excluded.
    formula = "log_wage_gain ~ C(edu_group, Treatment(reference='college_degree'))"
    model = smf.ols(formula=formula, data=df).fit(cov_type="HC1")

    focal_terms = [name for name in model.params.index if "no_high_school" in name]
    if len(focal_terms) != 1:
        raise ValueError(f"Could not uniquely identify focal coefficient; found {focal_terms}")
    focal = focal_terms[0]

    coef = float(model.params[focal])
    se = float(model.bse[focal])
    pvalue = float(model.pvalues[focal])
    ci_low, ci_high = [float(x) for x in model.conf_int().loc[focal]]
    percent_more = float(np.exp(coef) - 1.0)

    group_summary = (
        df.groupby("edu_group", dropna=False)
          .agg(n=("log_wage_gain", "size"), mean_log_gain=("log_wage_gain", "mean"),
               median_log_gain=("log_wage_gain", "median"), mean_edyrs=("edyrs", "mean"))
          .reset_index()
          .to_dict(orient="records")
    )

    country_summary = df["country"].value_counts(dropna=False).to_dict()
    conclusion_class = "support" if coef > 0 else "inconclusive"
    statistical_strength = "strong" if (coef > 0 and pvalue < 0.05) else ("weak_directional" if coef > 0 else "not_directionally_supportive")

    results = {
        "task": "Task2",
        "data_path": str(DATA_PATH.relative_to(ROOT)),
        "required_columns": REQUIRED_COLUMNS,
        "prohibited_controls_not_used": PROHIBITED_CONTROLS,
        "sample_flow": sample_flow,
        "final_analytic_n": int(len(df)),
        "mexico_rows_before_wage_log_filter": mexico_rows,
        "mexico_included": bool(mexico_rows > 0),
        "education_group_rule": {
            "no_high_school": "edyrs <= 8",
            "some_high_school": "9 <= edyrs <= 11",
            "high_school_some_college": "12 <= edyrs <= 15",
            "college_degree": "edyrs >= 16 (reference group)"
        },
        "model_formula": formula,
        "covariance": "HC1 robust standard errors",
        "focal_contrast": "no_high_school minus college_degree in log wage gain",
        "focal_coefficient_name": focal,
        "estimate_log_points": coef,
        "std_error": se,
        "p_value": pvalue,
        "conf_int_95_log_points": [ci_low, ci_high],
        "multiplicative_percent_more_gain": percent_more,
        "group_summary": group_summary,
        "country_counts": country_summary,
        "model_nobs": int(model.nobs),
        "r_squared": float(model.rsquared),
        "conclusion_class_direction_only": conclusion_class,
        "statistical_strength": statistical_strength,
        "conclusion_rule": "Support if the no_high_school coefficient is positive; p<0.05 denotes strong statistical evidence, otherwise positive estimates are weak directional support. Negative estimates are inconclusive unless later evaluated as affirmative contrary evidence."
    }

    (OUT_DIR / "task2_results.json").write_text(json.dumps(results, indent=2))
    (OUT_DIR / "task2_model_summary.txt").write_text(model.summary().as_text())
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
