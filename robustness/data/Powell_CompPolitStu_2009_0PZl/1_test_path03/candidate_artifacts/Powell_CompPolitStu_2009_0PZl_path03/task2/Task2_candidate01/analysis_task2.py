#!/usr/bin/env python3
"""
Task 2 comparable-result analysis for Powell_CompPolitStu_2009_0PZl.
Instruction: use the data from 1945-2003 and the Manifesto Method instead of
Cit-Expert and Method.

This script uses the authorized original dataset only. The Manifesto-method
plurality-winner distance from the median voter is pldist1. It estimates a Gamma
GLM with log link for positive pldist1, comparing SMD to PR election-rule
observations during 1945-2003 inclusive.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm

DATA_PATH = Path("data/powell_original.dta")
OUTPUT_PATH = Path("candidate_artifacts/Powell_CompPolitStu_2009_0PZl_path03/task2/Task2_candidate01/task2_results.json")

REQUIRED_COLUMNS = ["pldist1", "smd", "year"]
START_YEAR = 1945
END_YEAR = 2003


def clean_smd(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip().lower()
    if text in {"smd", "pr"}:
        return text
    return np.nan


def classify_result(coef, p_value, ci_low, ci_high):
    # Claim-supporting direction: SMD should be closer than PR, so the SMD-vs-PR
    # coefficient on log mean distance should be negative.
    if np.isfinite(coef) and coef < 0:
        if p_value <= 0.05:
            return "support"
        if p_value <= 0.055 and ci_low < 0 and ci_high > 0:
            return "support"
        return "inconclusive"
    if np.isfinite(coef) and coef > 0 and p_value < 0.05 and ci_low > 0:
        return "opposite"
    return "inconclusive"


def main():
    df = pd.read_stata(DATA_PATH)
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    sample_flow = []
    n0 = len(df)
    sample_flow.append({"step": "starting_rows_authorized_dataset", "rows": int(n0), "removed": 0})

    work = df.copy()
    before = len(work)
    work = work[(work["year"] >= START_YEAR) & (work["year"] <= END_YEAR)].copy()
    sample_flow.append({"step": "keep_year_1945_to_2003_inclusive", "rows": int(len(work)), "removed": int(before - len(work))})

    work["smd_clean"] = work["smd"].apply(clean_smd)
    before = len(work)
    work = work[work["smd_clean"].isin(["smd", "pr"])].copy()
    sample_flow.append({"step": "keep_election_rule_smd_or_pr", "rows": int(len(work)), "removed": int(before - len(work))})

    before = len(work)
    work = work.dropna(subset=["pldist1", "smd_clean", "year"])
    sample_flow.append({"step": "drop_missing_pldist1_smd_or_year", "rows": int(len(work)), "removed": int(before - len(work))})

    before = len(work)
    work = work[work["pldist1"] > 0].copy()
    sample_flow.append({"step": "keep_positive_pldist1_required_for_gamma", "rows": int(len(work)), "removed": int(before - len(work))})

    work["smd_bin"] = (work["smd_clean"] == "smd").astype(int)

    y = work["pldist1"].astype(float)
    X = sm.add_constant(work[["smd_bin"]].astype(float), has_constant="add")
    model = sm.GLM(y, X, family=sm.families.Gamma(link=sm.families.links.Log()))
    fit = model.fit(cov_type="HC1")

    coef = float(fit.params["smd_bin"])
    se = float(fit.bse["smd_bin"])
    p_value = float(fit.pvalues["smd_bin"])
    ci = fit.conf_int().loc["smd_bin"].astype(float).tolist()
    ratio = float(np.exp(coef))
    ratio_ci = [float(np.exp(ci[0])), float(np.exp(ci[1]))]
    conclusion = classify_result(coef, p_value, ci[0], ci[1])

    group_summary = work.groupby("smd_clean", observed=True)["pldist1"].agg(["count", "mean", "median", "std", "min", "max"]).reset_index()

    result = {
        "analysis": "Task2 Gamma GLM with log link: pldist1 ~ smd_bin, years 1945-2003",
        "data_file": str(DATA_PATH),
        "required_columns": REQUIRED_COLUMNS,
        "sample_flow": sample_flow,
        "final_n": int(len(work)),
        "model": {
            "family": "Gamma",
            "link": "log",
            "formula": "pldist1 ~ smd_bin",
            "covariance": "HC1 robust"
        },
        "focal_result": {
            "metric": "coefficient_on_smd_bin_log_mean_distance",
            "estimate": coef,
            "std_error": se,
            "p_value": p_value,
            "confidence_interval_95": [float(ci[0]), float(ci[1])],
            "mean_distance_ratio_smd_vs_pr": ratio,
            "mean_distance_ratio_ci_95": ratio_ci,
            "expected_direction": "negative coefficient / ratio below 1",
            "conclusion_class": conclusion
        },
        "group_summary_raw_pldist1": group_summary.to_dict(orient="records")
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
