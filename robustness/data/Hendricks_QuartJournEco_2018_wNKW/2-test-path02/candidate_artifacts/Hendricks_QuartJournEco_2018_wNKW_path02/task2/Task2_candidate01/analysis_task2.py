#!/usr/bin/env python3
"""
Task 2 candidate analysis for Hendricks & Schoellman (2018).
Robustness path: median (q=0.5) regression using the pooled poor-country
immigrant sample in wage_gain_table.xlsx, retaining Mexico and not controlling
for sector or rural/urban region. The focal result is the no-high-school versus
college-degree contrast in log wage gain.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

DATA_PATH = Path("data/wage_gain_table.xlsx")
OUTPUT_PATH = Path("candidate_artifacts/Hendricks_QuartJournEco_2018_wNKW_path02/task2/Task2_candidate01/task2_results.json")
REQUIRED_COLUMNS = ["edyrs", "lastHomeWageAdjusted", "lastUsWageAdjusted", "country"]


def classify_education(edyrs):
    if pd.isna(edyrs):
        return np.nan
    if edyrs <= 8:
        return "no_high_school"
    if edyrs < 12:
        return "some_high_school"
    if edyrs < 16:
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
    sample_flow.append({"step": "drop_missing_required_columns", "rows": int(len(df)), "removed": int(before - len(df))})

    before = len(df)
    df = df[(df["lastHomeWageAdjusted"] > 0) & (df["lastUsWageAdjusted"] > 0)].copy()
    sample_flow.append({"step": "drop_nonpositive_adjusted_wages", "rows": int(len(df)), "removed": int(before - len(df))})

    # The supplied file is treated as the authorized pooled poor-country sample;
    # Mexico is explicitly retained by imposing no country exclusion.
    df["log_wage_gain"] = np.log(df["lastUsWageAdjusted"]) - np.log(df["lastHomeWageAdjusted"])
    df["edu_group"] = df["edyrs"].apply(classify_education)

    model_vars = ["log_wage_gain", "edu_group"]
    before = len(df)
    df = df.dropna(subset=model_vars).copy()
    sample_flow.append({"step": "drop_missing_constructed_model_variables", "rows": int(len(df)), "removed": int(before - len(df))})

    df["edu_group"] = pd.Categorical(
        df["edu_group"],
        categories=["college_degree", "no_high_school", "some_high_school", "high_school_some_college"],
        ordered=False,
    )

    formula = 'log_wage_gain ~ C(edu_group, Treatment(reference="college_degree"))'
    result = smf.quantreg(formula, df).fit(q=0.5, max_iter=10000)
    focal_term = 'C(edu_group, Treatment(reference="college_degree"))[T.no_high_school]'
    coef = float(result.params[focal_term])
    pval = float(result.pvalues[focal_term])
    ci_low, ci_high = [float(x) for x in result.conf_int().loc[focal_term].tolist()]

    conclusion_class = "support" if coef > 0 else ("opposite" if (coef < 0 and pval < 0.05 and ci_high < 0) else "inconclusive")
    strength = "strong" if (coef > 0 and pval < 0.05) else ("weak_directional" if coef > 0 else "not_directionally_supportive")

    output = {
        "task": "Task2",
        "analysis": "median_quantile_regression_unadjusted_no_sector_no_region_controls",
        "sample_flow": sample_flow,
        "final_analytic_n": int(len(df)),
        "country_counts_retaining_mexico": {str(k): int(v) for k, v in df["country"].value_counts(dropna=False).items()},
        "education_group_counts": {str(k): int(v) for k, v in df["edu_group"].value_counts(dropna=False).items()},
        "focal_result": {
            "metric": "no_high_school_vs_college_degree_median_log_wage_gain_coefficient",
            "term": focal_term,
            "estimate": coef,
            "p_value": pval,
            "confidence_interval_95": [ci_low, ci_high],
            "exp_estimate_percent_difference": float((np.exp(coef) - 1) * 100),
            "expected_direction": "positive",
            "conclusion_class": conclusion_class,
            "statistical_strength": strength,
        },
        "model_formula": formula,
        "model_summary_text": result.summary().as_text(),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
