#!/usr/bin/env python3
"""Task 1 analysis for Powell_CompPolitStu_2009_0PZl_path07.

Robustness analysis: country fixed-effects OLS of Manifesto-method
plurality-winner distance from the median voter (pldist1) on an SMD indicator.
The fixed effect is implemented by within-country demeaning to avoid ambiguity
from collinear dummy variables. This script reports complete sample flow and a
structured JSON result. It does not require human reanalysis materials.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm


def classify_result(coef, p_value, ci_low, ci_high):
    """Classify evidence for the claim that SMD lowers pldist1."""
    if np.isfinite(coef) and np.isfinite(p_value):
        if coef < 0 and p_value <= 0.05:
            return "support"
        if coef < 0 and 0.05 < p_value <= 0.055:
            return "support"
        if coef > 0 and p_value < 0.05 and ci_low > 0:
            return "opposite"
    return "inconclusive"


def main():
    script_path = Path(__file__).resolve()
    study_root = script_path.parents[4]
    data_path = study_root / "data" / "powell_original.dta"
    output_path = script_path.with_name("results_task1.json")

    df0 = pd.read_stata(data_path, convert_categoricals=True)
    required_columns = ["pldist1", "smd", "country"]
    missing_columns = [col for col in required_columns if col not in df0.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    sample_flow = []
    df = df0.copy()
    sample_flow.append({"step": "starting_rows", "rows": int(len(df))})

    before = len(df)
    df = df[df["pldist1"].notna()].copy()
    sample_flow.append({"step": "remove_missing_pldist1", "removed": int(before - len(df)), "remaining": int(len(df))})

    df["smd_clean"] = df["smd"].astype("object")
    df["smd_clean"] = df["smd_clean"].where(pd.notna(df["smd_clean"]), np.nan)
    df["smd_clean"] = df["smd_clean"].astype("string").str.strip().str.lower()
    before = len(df)
    df = df[df["smd_clean"].notna()].copy()
    sample_flow.append({"step": "remove_missing_smd", "removed": int(before - len(df)), "remaining": int(len(df))})

    before = len(df)
    df = df[df["smd_clean"].isin(["smd", "pr"])].copy()
    sample_flow.append({"step": "keep_smd_or_pr", "removed": int(before - len(df)), "remaining": int(len(df))})

    before = len(df)
    df = df[df["country"].notna()].copy()
    sample_flow.append({"step": "remove_missing_country", "removed": int(before - len(df)), "remaining": int(len(df))})

    df["smd_bin"] = (df["smd_clean"] == "smd").astype(float)
    df["pldist1"] = pd.to_numeric(df["pldist1"], errors="coerce")
    before = len(df)
    df = df[df["pldist1"].notna() & df["smd_bin"].notna()].copy()
    sample_flow.append({"step": "remove_missing_constructed_model_variables", "removed": int(before - len(df)), "remaining": int(len(df))})

    df["y_dm"] = df["pldist1"] - df.groupby("country", observed=True)["pldist1"].transform("mean")
    df["x_dm"] = df["smd_bin"] - df.groupby("country", observed=True)["smd_bin"].transform("mean")
    within_sd = float(df["x_dm"].std(ddof=1)) if len(df) > 1 else 0.0
    if not np.isfinite(within_sd) or within_sd <= 0:
        raise ValueError("No within-country variation in SMD indicator after applying sample rules.")

    model = sm.OLS(df["y_dm"].astype(float), df[["x_dm"]].astype(float))
    fit = model.fit(cov_type="cluster", cov_kwds={"groups": df["country"].astype(str), "use_correction": True})

    coef = float(fit.params["x_dm"])
    se = float(fit.bse["x_dm"])
    p_value = float(fit.pvalues["x_dm"])
    ci_low, ci_high = [float(v) for v in fit.conf_int().loc["x_dm"].tolist()]
    direction = "negative" if coef < 0 else "positive" if coef > 0 else "zero"
    conclusion = classify_result(coef, p_value, ci_low, ci_high)

    result = {
        "task_id": "Task1",
        "analysis": "country_fixed_effects_within_ols_clustered_by_country",
        "dataset": str(data_path.relative_to(study_root)),
        "sample_flow": sample_flow,
        "final_analytic_rows": int(len(df)),
        "countries": int(df["country"].nunique()),
        "countries_with_within_smd_variation": int(df.groupby("country", observed=True)["smd_bin"].nunique().gt(1).sum()),
        "smd_count": int((df["smd_bin"] == 1).sum()),
        "pr_count": int((df["smd_bin"] == 0).sum()),
        "metric": "country_fixed_effect_coefficient_smd_minus_pr_pldist1",
        "estimate": coef,
        "std_error": se,
        "p_value": p_value,
        "confidence_interval_95": [ci_low, ci_high],
        "direction": direction,
        "conclusion": conclusion,
        "inference_rule": "Support requires a negative SMD-minus-PR coefficient with p <= 0.05, or borderline support for 0.05 < p <= 0.055 when substantively meaningful and narrowly crossing zero; opposite requires affirmative positive evidence with p < 0.05 and CI above zero; otherwise inconclusive."
    }
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
