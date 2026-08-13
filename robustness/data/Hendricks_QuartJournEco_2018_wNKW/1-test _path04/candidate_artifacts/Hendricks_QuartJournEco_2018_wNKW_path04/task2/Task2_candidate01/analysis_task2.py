#!/usr/bin/env python3
"""
Task2 candidate analysis for Hendricks & Schoellman (QJE 2018) focal claim.
Task2 instruction: use the pooled sample of immigrants from poor countries in the NIS and Migration Projects,
including Mexico; do not control for sector (agriculture/nonagriculture) or region (rural/urban upbringing).

This script does not execute during planning. It is intended to be run from the study root with:
python candidate_artifacts/Hendricks_QuartJournEco_2018_wNKW_path04/task2/Task2_candidate01/analysis_task2.py
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

SCRIPT_PATH = Path(__file__).resolve()
STUDY_ROOT = SCRIPT_PATH.parents[4]
DATA_PATH = STUDY_ROOT / "data" / "wage_gain_table.xlsx"
OUT_DIR = SCRIPT_PATH.parent

REQUIRED_COLUMNS = [
    "edyrs", "lastHomeWageAdjusted", "lastUsWageAdjusted", "country"
]


def add_flow(flow, step, before, after):
    flow.append({
        "step": step,
        "rows_before": int(before),
        "rows_after": int(after),
        "rows_removed": int(before - after)
    })


def education_group(edyrs):
    if pd.isna(edyrs):
        return np.nan
    if edyrs < 9:
        return "never_high_school"
    if edyrs < 12:
        return "some_high_school"
    if edyrs < 16:
        return "high_school_some_college"
    return "college_degree"


def main():
    df = pd.read_excel(DATA_PATH)
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    flow = []
    start_n = len(df)
    work = df.copy()
    add_flow(flow, "starting rows in pooled wage_gain_table.xlsx", start_n, len(work))

    # The provided authorized file is treated as the pooled poor-country NIS/MP sample including Mexico.
    # No sector/agriculture or rural/urban region controls are constructed or included.
    before = len(work)
    work = work[np.isfinite(work["lastHomeWageAdjusted"]) & np.isfinite(work["lastUsWageAdjusted"])]
    add_flow(flow, "keep finite adjusted home and U.S. wages", before, len(work))

    before = len(work)
    work = work[(work["lastHomeWageAdjusted"] > 0) & (work["lastUsWageAdjusted"] > 0)]
    add_flow(flow, "keep positive adjusted home and U.S. wages for logarithms", before, len(work))

    work["log_wage_gain"] = np.log(work["lastUsWageAdjusted"]) - np.log(work["lastHomeWageAdjusted"])
    work["edu_group"] = work["edyrs"].apply(education_group)

    before = len(work)
    work = work.dropna(subset=["log_wage_gain", "edu_group"])
    add_flow(flow, "drop missing focal outcome or education group", before, len(work))

    work["edu_group"] = pd.Categorical(
        work["edu_group"],
        categories=["college_degree", "never_high_school", "some_high_school", "high_school_some_college"]
    )

    formula = 'log_wage_gain ~ C(edu_group, Treatment(reference="college_degree"))'
    model = smf.ols(formula=formula, data=work).fit(cov_type="HC3")

    focal_terms = [name for name in model.params.index if "never_high_school" in name]
    if len(focal_terms) != 1:
        raise RuntimeError(f"Could not uniquely identify focal coefficient; found {focal_terms}")
    term = focal_terms[0]
    ci = model.conf_int().loc[term].tolist()
    coef = float(model.params[term])
    result = {
        "analysis": "Task2_candidate01_pooled_all_education_groups_no_sector_region_controls_HC3",
        "dataset": str(DATA_PATH.relative_to(STUDY_ROOT)),
        "formula": formula,
        "covariance": "HC3 robust",
        "focal_term": term,
        "metric": "OLS coefficient: log wage gain difference, never_high_school versus college_degree",
        "coefficient_log_points": coef,
        "percent_difference_exp_coef_minus_1": float(100 * (np.exp(coef) - 1)),
        "std_error": float(model.bse[term]),
        "t_value": float(model.tvalues[term]),
        "p_value_two_sided": float(model.pvalues[term]),
        "confidence_interval_95_log_points": [float(ci[0]), float(ci[1])],
        "nobs": int(model.nobs),
        "r_squared": float(model.rsquared),
        "education_group_counts": {str(k): int(v) for k, v in work["edu_group"].value_counts(dropna=False).to_dict().items()},
        "country_counts_descriptive_only": {str(k): int(v) for k, v in work["country"].value_counts(dropna=False).to_dict().items()} if "country" in work.columns else {},
        "sample_flow": flow,
        "support_rule": "clear support if focal coefficient is positive and two-sided p < 0.05; inconclusive if same direction but p >= 0.05; opposite if negative with p < 0.05"
    }

    with open(OUT_DIR / "task2_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    pd.DataFrame(flow).to_csv(OUT_DIR / "task2_sample_flow.csv", index=False)
    with open(OUT_DIR / "task2_model_summary.txt", "w", encoding="utf-8") as f:
        f.write(model.summary().as_text())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
