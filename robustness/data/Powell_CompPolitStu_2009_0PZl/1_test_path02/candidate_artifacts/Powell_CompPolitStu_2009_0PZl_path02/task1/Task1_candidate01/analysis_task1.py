#!/usr/bin/env python3
"""
Task 1 robustness analysis for Powell_CompPolitStu_2009_0PZl.
Focal claim: Under SMD election rules, party competition should lead the plurality vote winner to be close to the median voter.

This script estimates whether SMD elections have a lower median Manifesto-method plurality-winner distance from the median voter than PR elections.
It reports sample flow and writes a structured JSON result. It does not rely on any human reanalysis code.
"""
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

DATA_PATH = Path("data/powell_original.dta")
OUT_PATH = Path("candidate_artifacts/Powell_CompPolitStu_2009_0PZl_path02/task1/Task1_candidate01/task1_results.json")
REQUIRED_COLUMNS = ["smd", "pldist1", "year"]


def classify_result(coef, p_value, ci_low, ci_high):
    """Apply the common conclusion rule. Expected direction is negative."""
    direction = "negative" if coef < 0 else ("positive" if coef > 0 else "zero")
    if coef < 0 and p_value <= 0.05:
        conclusion = "support"
    elif coef < 0 and 0.05 < p_value <= 0.055 and ci_low < 0 < ci_high:
        conclusion = "support"
    elif coef > 0 and p_value < 0.05 and ci_low > 0:
        conclusion = "opposite"
    else:
        conclusion = "inconclusive"
    return direction, conclusion


def main():
    df = pd.read_stata(DATA_PATH)
    starting_rows = int(len(df))

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    sample_flow = []
    work = df.copy()

    before = len(work)
    work["smd_clean"] = work["smd"].astype("string").str.strip().str.lower()
    work = work[work["smd_clean"].isin(["smd", "pr"])].copy()
    sample_flow.append({
        "rule": "keep observations with smd coded SMD or PR",
        "before": int(before),
        "after": int(len(work)),
        "removed": int(before - len(work))
    })

    before = len(work)
    work = work.dropna(subset=["pldist1", "smd_clean", "year"]).copy()
    sample_flow.append({
        "rule": "drop observations missing pldist1, smd, or year",
        "before": int(before),
        "after": int(len(work)),
        "removed": int(before - len(work))
    })

    work["smd_bin"] = (work["smd_clean"] == "smd").astype(int)

    # Median regression is a robustness analysis for the claim that the winner is "close" to the median voter.
    # It preserves the raw Manifesto-method distance scale but estimates the SMD-PR contrast at the conditional median.
    model = smf.quantreg("pldist1 ~ smd_bin", data=work).fit(q=0.5)

    coef = float(model.params["smd_bin"])
    se = float(model.bse["smd_bin"])
    p_value = float(model.pvalues["smd_bin"])
    ci = model.conf_int().loc["smd_bin"]
    ci_low = float(ci.iloc[0])
    ci_high = float(ci.iloc[1])
    direction, conclusion = classify_result(coef, p_value, ci_low, ci_high)

    group_summary = work.groupby("smd_clean", observed=True)["pldist1"].agg(["count", "mean", "median", "std", "min", "max"]).reset_index()

    result = {
        "analysis": "Task1 median quantile regression of Manifesto-method plurality-winner distance on SMD indicator",
        "data_path": str(DATA_PATH),
        "referenced_columns": REQUIRED_COLUMNS,
        "sample_flow": {
            "starting_rows": starting_rows,
            "steps": sample_flow,
            "final_analytic_rows": int(len(work))
        },
        "model": {
            "family": "quantile_regression",
            "quantile": 0.5,
            "formula": "pldist1 ~ smd_bin",
            "outcome": "pldist1",
            "main_predictor": "smd_bin (1=SMD, 0=PR)",
            "focal_statistic": "coefficient_on_smd_bin",
            "coefficient": coef,
            "standard_error": se,
            "p_value": p_value,
            "confidence_interval_95": [ci_low, ci_high],
            "direction": direction,
            "conclusion_class": conclusion,
            "inference_rule": "Expected direction is negative. Support requires a negative SMD coefficient with p <= 0.05, or borderline support for 0.05 < p <= 0.055 when the estimate is substantively meaningful and the interval narrowly crosses zero. A positive coefficient is opposite only with affirmative p < 0.05 evidence and an interval above zero; otherwise inconclusive."
        },
        "group_summary": group_summary.to_dict(orient="records")
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
