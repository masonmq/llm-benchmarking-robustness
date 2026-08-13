#!/usr/bin/env python3
"""
Task1 robustness analysis for Hendricks & Schoellman QJE 2018 focal claim.

Planned analysis only: when executed, this script uses the authorized
wage_gain_table.xlsx file to estimate whether immigrants with no high school
(edyrs <= 8) have larger log wage gains at migration than immigrants with a
college degree (edyrs >= 16). Task1 is unrestricted, so this robustness path
uses an adjusted OLS specification and trims the most extreme 1% tails of the
constructed log wage gain before estimation.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

DATA_PATH = Path("data/wage_gain_table.xlsx")
OUTPUT_PATH = Path("candidate_artifacts/Hendricks_QuartJournEco_2018_wNKW_path03/task1/Task1_candidate01/task1_results.json")

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


def make_education_group(edyrs: pd.Series) -> pd.Series:
    """Map years of schooling to the education groups described in the paper."""
    conditions = [
        edyrs <= 8,
        (edyrs >= 9) & (edyrs <= 11),
        edyrs == 12,
        (edyrs >= 13) & (edyrs <= 15),
        edyrs >= 16,
    ]
    choices = [
        "no_high_school",
        "some_high_school",
        "high_school",
        "some_college",
        "college_degree",
    ]
    out = np.select(conditions, choices, default=pd.NA)
    cat = pd.Categorical(
        out,
        categories=[
            "college_degree",
            "no_high_school",
            "some_high_school",
            "high_school",
            "some_college",
        ],
    )
    return pd.Series(cat, index=edyrs.index, name="edu_group")


def main() -> None:
    sample_flow = []
    df = pd.read_excel(DATA_PATH)
    sample_flow.append({"step": "starting_rows", "rows": int(len(df)), "removed": 0})

    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    before = len(df)
    df = df.dropna(subset=REQUIRED_COLUMNS).copy()
    sample_flow.append({"step": "drop_missing_required_columns", "rows": int(len(df)), "removed": int(before - len(df))})

    before = len(df)
    df = df[(df["lastHomeWageAdjusted"] > 0) & (df["lastUsWageAdjusted"] > 0)].copy()
    sample_flow.append({"step": "require_positive_adjusted_wages", "rows": int(len(df)), "removed": int(before - len(df))})

    df["log_wage_gain"] = np.log(df["lastUsWageAdjusted"]) - np.log(df["lastHomeWageAdjusted"])
    df["edu_group"] = make_education_group(df["edyrs"])
    df["age_home_job"] = df["yearLastHomeJob"] - df["yrborn"]
    df["age_home_job_sq"] = df["age_home_job"] ** 2

    before = len(df)
    constructed_required = ["log_wage_gain", "edu_group", "age_home_job", "age_home_job_sq"]
    df = df.dropna(subset=constructed_required).copy()
    sample_flow.append({"step": "drop_missing_constructed_variables", "rows": int(len(df)), "removed": int(before - len(df))})

    # Prespecified symmetric trimming of the constructed outcome to reduce the
    # influence of extreme adjusted wage ratios while preserving the education contrast.
    lower = df["log_wage_gain"].quantile(0.01)
    upper = df["log_wage_gain"].quantile(0.99)
    before = len(df)
    df = df[(df["log_wage_gain"] >= lower) & (df["log_wage_gain"] <= upper)].copy()
    sample_flow.append({
        "step": "trim_log_wage_gain_outside_1st_99th_percentiles",
        "rows": int(len(df)),
        "removed": int(before - len(df)),
        "lower_cutoff": float(lower),
        "upper_cutoff": float(upper),
    })

    formula = (
        "log_wage_gain ~ C(edu_group, Treatment(reference='college_degree')) "
        "+ C(country) + C(sex) + age_home_job + age_home_job_sq "
        "+ yearLastHomeJob + yearLastUsJob"
    )
    model = smf.ols(formula=formula, data=df).fit(cov_type="HC1")

    coef_name = "C(edu_group, Treatment(reference='college_degree'))[T.no_high_school]"
    estimate = float(model.params[coef_name])
    p_value = float(model.pvalues[coef_name])
    conf_low, conf_high = [float(x) for x in model.conf_int().loc[coef_name]]
    percent_difference = float(np.exp(estimate) - 1.0)

    if estimate > 0:
        conclusion = "support"
        strength = "strong" if p_value < 0.05 else "weak_directional"
    else:
        conclusion = "opposite" if (p_value < 0.05 and conf_high < 0) else "inconclusive"
        strength = "affirmative_opposite" if conclusion == "opposite" else "not_affirmative"

    result = {
        "task": "Task1",
        "model": "adjusted OLS with HC1 robust standard errors after 1%/99% log-wage-gain trimming",
        "formula": formula,
        "sample_flow": sample_flow,
        "trim_cutoffs": {"lower_log_wage_gain": float(lower), "upper_log_wage_gain": float(upper)},
        "education_group_counts": df["edu_group"].value_counts(dropna=False).to_dict(),
        "focal_result": {
            "metric": "no_high_school_vs_college_degree_log_wage_gain_coefficient",
            "estimate": estimate,
            "percent_difference_exp_coef_minus_1": percent_difference,
            "p_value": p_value,
            "confidence_interval_95": [conf_low, conf_high],
            "direction": "positive" if estimate > 0 else ("negative" if estimate < 0 else "zero"),
            "conclusion_class": conclusion,
            "statistical_strength": strength,
        },
        "n_final": int(model.nobs),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
