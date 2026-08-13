#!/usr/bin/env python3
"""
Task 1 analysis for Hendricks & Schoellman (2018) focal claim.
Candidate path: robust linear (Huber M-estimation) model of individual log wage gains
on education groups, adjusted for country, sex, age at last home job, age squared,
and timing of last home/U.S. jobs.

This script is intentionally self-contained and does not execute during planning.
"""
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.robust.norms import HuberT

REQUIRED_COLUMNS = [
    "edyrs",
    "yearLastHomeJob",
    "yearLastUsJob",
    "sex",
    "yrborn",
    "lastHomeWageAdjusted",
    "lastUsWageAdjusted",
    "country",
]


def classify_education(edyrs):
    """Paper-aligned education categories for the focal contrast."""
    if pd.isna(edyrs):
        return np.nan
    if edyrs <= 8:
        return "no_high_school"
    if edyrs <= 11:
        return "some_high_school"
    if edyrs == 12:
        return "high_school"
    if edyrs <= 15:
        return "some_college"
    return "college_degree"


def main():
    study_dir = Path(__file__).resolve().parents[4]
    data_path = study_dir / "data" / "wage_gain_table.xlsx"
    output_path = Path(__file__).resolve().with_name("task1_results.json")

    df0 = pd.read_excel(data_path)
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
        "removed": int(before - len(df)),
        "columns": REQUIRED_COLUMNS,
    })

    before = len(df)
    df = df[(df["lastHomeWageAdjusted"] > 0) & (df["lastUsWageAdjusted"] > 0)].copy()
    sample_flow.append({
        "step": "keep_positive_adjusted_wages_for_log_transform",
        "rows": int(len(df)),
        "removed": int(before - len(df)),
    })

    df["log_wage_gain"] = np.log(df["lastUsWageAdjusted"]) - np.log(df["lastHomeWageAdjusted"])
    df["edu_group"] = df["edyrs"].apply(classify_education)
    df["age_home_job"] = df["yearLastHomeJob"] - df["yrborn"]
    df["age_home_job_sq"] = df["age_home_job"] ** 2

    constructed_required = ["log_wage_gain", "edu_group", "age_home_job", "age_home_job_sq"]
    before = len(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=constructed_required)
    sample_flow.append({
        "step": "drop_missing_or_nonfinite_constructed_variables",
        "rows": int(len(df)),
        "removed": int(before - len(df)),
        "columns": constructed_required,
    })

    # Preserve all education groups but set college degree as the reference category.
    edu_order = ["college_degree", "no_high_school", "some_high_school", "high_school", "some_college"]
    df["edu_group"] = pd.Categorical(df["edu_group"], categories=edu_order, ordered=False)

    before = len(df)
    df = df.dropna(subset=["edu_group"])
    sample_flow.append({
        "step": "drop_rows_outside_defined_education_groups",
        "rows": int(len(df)),
        "removed": int(before - len(df)),
    })

    formula = (
        "log_wage_gain ~ C(edu_group, Treatment(reference='college_degree')) "
        "+ C(country) + C(sex) + age_home_job + age_home_job_sq "
        "+ yearLastHomeJob + yearLastUsJob"
    )

    model = smf.rlm(formula=formula, data=df, M=HuberT()).fit()
    focal_param = "C(edu_group, Treatment(reference='college_degree'))[T.no_high_school]"
    if focal_param not in model.params.index:
        raise ValueError(f"Focal coefficient not found. Available parameters: {list(model.params.index)}")

    estimate = float(model.params[focal_param])
    se = float(model.bse[focal_param])
    z_value = estimate / se if se != 0 else math.nan
    p_value = float(model.pvalues[focal_param])
    ci_low = float(estimate - 1.96 * se)
    ci_high = float(estimate + 1.96 * se)
    percent_difference = float(np.exp(estimate) - 1.0)

    if estimate > 0:
        conclusion_class = "support"
        statistical_strength = "strong" if p_value < 0.05 else "weak_directional"
    elif (estimate < 0) and (p_value < 0.05) and (ci_high < 0):
        conclusion_class = "opposite"
        statistical_strength = "strong_contrary"
    else:
        conclusion_class = "inconclusive"
        statistical_strength = "not_statistically_established"

    results = {
        "task": "Task1",
        "analysis": "Huber robust linear model of log wage gain with demographic, country, and timing controls",
        "data_file": str(data_path.relative_to(study_dir)),
        "referenced_columns": REQUIRED_COLUMNS,
        "sample_flow": sample_flow,
        "final_analytic_n": int(model.nobs),
        "formula": formula,
        "focal_parameter": focal_param,
        "metric": "no_high_school_vs_college_degree_robust_log_wage_gain_coefficient",
        "estimate_log_units": estimate,
        "standard_error": se,
        "z_value": float(z_value),
        "p_value": p_value,
        "confidence_interval_approx_95": [ci_low, ci_high],
        "exponentiated_percent_difference": percent_difference,
        "direction": "positive" if estimate > 0 else "negative" if estimate < 0 else "zero",
        "conclusion_class": conclusion_class,
        "statistical_strength": statistical_strength,
        "education_group_counts": df["edu_group"].value_counts(dropna=False).to_dict(),
        "model_parameters": {k: float(v) for k, v in model.params.items()},
    }

    print(json.dumps(results, indent=2, sort_keys=True))
    output_path.write_text(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
