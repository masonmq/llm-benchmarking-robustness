#!/usr/bin/env python3
"""Task 1 candidate analysis for Powell_CompPolitStu_2009_0PZl.

Tests whether SMD election rules are associated with a plurality vote winner
closer to the median voter, using the Manifesto-method distance variable
available in the authorized original dataset. Planning code only; not executed
by the Planning Agent.
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
    out_json = out_dir / "task1_results.json"
    out_txt = out_dir / "task1_results.txt"

    required = ["pldist1", "smd", "decade", "country", "year"]
    df = pd.read_stata(data_path)
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    sample_flow = []
    sample_flow.append({"step": "starting_rows", "rows": int(len(df)), "removed": 0})

    work = df.copy()
    work["smd_clean"] = work["smd"].astype(str).str.strip().str.lower()
    before = len(work)
    work = work[work["smd_clean"].isin(["smd", "pr"])]
    sample_flow.append({
        "step": "keep rows with election rule coded smd or pr",
        "rows": int(len(work)),
        "removed": int(before - len(work))
    })

    before = len(work)
    work = work.dropna(subset=["pldist1", "decade", "country"])
    sample_flow.append({
        "step": "drop missing pldist1, decade, or country needed for Task1 model",
        "rows": int(len(work)),
        "removed": int(before - len(work))
    })

    work["smd_bin"] = (work["smd_clean"] == "smd").astype(int)
    work["decade_cat"] = work["decade"].astype("category")

    # Decade fixed effects reflect the paper's emphasis that period differences
    # are central when assessing electoral-rule congruence patterns.
    model = smf.ols("pldist1 ~ smd_bin + C(decade_cat)", data=work).fit(
        cov_type="cluster", cov_kwds={"groups": work["country"]}
    )

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
        "task_id": "Task1",
        "analysis": "OLS of Manifesto-method plurality-winner distance from median voter on SMD indicator with decade fixed effects and country-clustered SEs",
        "data_file": str(data_path.relative_to(study_root)),
        "sample_flow": sample_flow,
        "final_n": int(model.nobs),
        "outcome": "pldist1",
        "main_predictor": "smd_bin (1=smd, 0=pr)",
        "controls": ["C(decade_cat)"],
        "cluster_variable": "country",
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
