#!/usr/bin/env python3
"""Task 2 candidate analysis for Powell_CompPolitStu_2009_0PZl.

Required by Task2: use data from 1945-2003 and use the Manifesto Method
instead of Cit-Expert/other methods. The authorized dataset contains a
Manifesto-method plurality-party distance variable, pldist1.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


def classify(estimate, p_value, ci_low, ci_high):
    """Apply fixed conclusion rules. Expected direction is negative."""
    if np.isnan(estimate) or np.isnan(p_value):
        return "inconclusive"
    if estimate < 0 and p_value <= 0.05:
        return "support"
    if estimate < 0 and 0.05 < p_value <= 0.055 and ci_high > 0:
        return "support"
    if estimate > 0 and p_value < 0.05 and ci_low > 0:
        return "opposite"
    return "inconclusive"


def main():
    script_path = Path(__file__).resolve()
    study_root = script_path.parents[4]
    data_path = study_root / "data" / "powell_original.dta"
    out_dir = script_path.parent
    out_json = out_dir / "task2_results.json"
    out_txt = out_dir / "task2_results.txt"

    required = ["pldist1", "smd", "year"]
    df = pd.read_stata(data_path)
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    sample_flow = []
    sample_flow.append({"step": "starting_rows", "rows": int(len(df)), "removed": 0})

    work = df.copy()
    before = len(work)
    work = work[(work["year"] >= 1945) & (work["year"] <= 2003)]
    sample_flow.append({
        "step": "keep years 1945 through 2003 inclusive as instructed",
        "rows": int(len(work)),
        "removed": int(before - len(work))
    })

    work["smd_clean"] = work["smd"].astype(str).str.strip().str.lower()
    before = len(work)
    work = work[work["smd_clean"].isin(["smd", "pr"])]
    sample_flow.append({
        "step": "keep rows with election rule coded smd or pr",
        "rows": int(len(work)),
        "removed": int(before - len(work))
    })

    before = len(work)
    work = work.dropna(subset=["pldist1", "smd_clean", "year"])
    sample_flow.append({
        "step": "drop missing Manifesto-method plurality distance, election rule, or year",
        "rows": int(len(work)),
        "removed": int(before - len(work))
    })

    work["smd_bin"] = (work["smd_clean"] == "smd").astype(int)

    # Comparable single result: raw Manifesto-method SMD-vs-PR difference in
    # plurality winner distance from the median voter for 1945-2003.
    model = smf.ols("pldist1 ~ smd_bin", data=work).fit(cov_type="HC1")

    term = "smd_bin"
    estimate = float(model.params[term])
    se = float(model.bse[term])
    p_value = float(model.pvalues[term])
    ci_low, ci_high = [float(x) for x in model.conf_int().loc[term].tolist()]
    conclusion = classify(estimate, p_value, ci_low, ci_high)

    group_summary = (
        work.groupby("smd_clean", observed=True)["pldist1"]
        .agg(["count", "mean", "median", "std", "min", "max"])
        .reset_index()
        .to_dict(orient="records")
    )

    results = {
        "task_id": "Task2",
        "analysis": "Manifesto-method 1945-2003 OLS comparison of plurality-winner distance from median voter under SMD versus PR rules",
        "data_file": str(data_path.relative_to(study_root)),
        "sample_flow": sample_flow,
        "final_n": int(model.nobs),
        "outcome": "pldist1",
        "main_predictor": "smd_bin (1=smd, 0=pr)",
        "controls": [],
        "group_summary": group_summary,
        "focal_result": {
            "term": term,
            "estimate": estimate,
            "std_error": se,
            "p_value": p_value,
            "conf_int_95": [ci_low, ci_high],
            "expected_direction": "negative: SMD plurality winners are closer to the median voter than PR plurality winners",
            "conclusion_class": conclusion
        },
        "model_r_squared": float(model.rsquared),
        "model_summary_text": model.summary().as_text()
    }

    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    out_txt.write_text(model.summary().as_text(), encoding="utf-8")
    print(json.dumps(results["focal_result"], indent=2))


if __name__ == "__main__":
    sys.exit(main())
