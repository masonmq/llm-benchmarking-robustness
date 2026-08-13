#!/usr/bin/env python3
"""
Task 1 robustness analysis for Hendricks & Schoellman (2018) focal claim:
immigrants who have never been to high school gain more on migration to the
United States than immigrants with a college degree.

This script does not rely on any human reanalysis code. It reads the authorized
wage_gain_table.xlsx file, constructs log wage gains, bins education to preserve
all observed education groups while estimating the focal contrast, and estimates
an adjusted OLS model with HC1 robust standard errors.
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
    "edyrs", "yearLastHomeJob", "yearLastUsJob", "sex", "yrborn",
    "lastHomeWageAdjusted", "lastUsWageAdjusted", "country"
]


def education_group(edyrs):
    """Map years of education to claim-relevant categories.
    Never high school is operationalized as <=8 completed years; college degree
    as >=16 years. Intermediate groups remain in the model rather than being
    dropped from the analytic sample.
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

    before = len(df)
    df = df[(df["lastHomeWageAdjusted"] > 0) & (df["lastUsWageAdjusted"] > 0)]
    sample_flow.append({
        "step": "drop_nonpositive_adjusted_wages_for_logs",
        "rows": int(len(df)),
        "removed": int(before - len(df))
    })

    df["log_wage_gain"] = np.log(df["lastUsWageAdjusted"]) - np.log(df["lastHomeWageAdjusted"])
    df["edu_group"] = df["edyrs"].apply(education_group)
    df["age_home_job"] = df["yearLastHomeJob"] - df["yrborn"]

    before = len(df)
    df = df.dropna(subset=["log_wage_gain", "edu_group", "age_home_job"])
    sample_flow.append({
        "step": "drop_missing_constructed_variables",
        "rows": int(len(df)),
        "removed": int(before - len(df))
    })

    # Keep implausible age values visible rather than silently excluding them.
    age_flags = int(((df["age_home_job"] < 10) | (df["age_home_job"] > 80)).sum())

    # Adjusted Task 1 specification: focal education contrast plus demographic,
    # timing, and country controls. Occupation/sector and rural/urban controls are
    # intentionally not used in this candidate.
    formula = (
        "log_wage_gain ~ C(edu_group, Treatment(reference='college_degree')) "
        "+ C(country) + C(sex) + age_home_job + I(age_home_job ** 2) "
        "+ yearLastHomeJob + yearLastUsJob"
    )
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
        "task": "Task1",
        "data_path": str(DATA_PATH.relative_to(ROOT)),
        "required_columns": REQUIRED_COLUMNS,
        "sample_flow": sample_flow,
        "final_analytic_n": int(len(df)),
        "age_home_job_implausible_count_not_excluded": age_flags,
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

    (OUT_DIR / "task1_results.json").write_text(json.dumps(results, indent=2))
    (OUT_DIR / "task1_model_summary.txt").write_text(model.summary().as_text())
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
