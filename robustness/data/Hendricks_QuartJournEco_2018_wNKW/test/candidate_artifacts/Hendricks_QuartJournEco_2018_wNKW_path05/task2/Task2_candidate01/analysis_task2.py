#!/usr/bin/env python3
"""
Task2 analysis for Hendricks_QuartJournEco_2018_wNKW_path05.
Planning script only: use the pooled sample of immigrants from poor countries in
NIS and Migration Projects, including Mexico, and do not control for sector or
rural/urban region.

Method: Tukey biweight robust linear regression (RLM) of individual log wage gain
on education groups only. This preserves the required pooled sample and prohibits
sector/region adjustment while reducing influence of extreme wage-gain values.
"""
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from scipy import stats


def classify_result(estimate, p_value):
    if estimate > 0:
        strength = "strong" if (p_value is not None and p_value < 0.05) else "weak_directional"
        return "support", strength
    if estimate < 0 and p_value is not None and p_value < 0.05:
        return "opposite", "strong_contrary"
    return "inconclusive", "not_statistically_established"


def add_education_group(edyrs):
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
    script_path = Path(__file__).resolve()
    study_dir = script_path.parents[4]
    data_path = study_dir / "data" / "wage_gain_table.xlsx"
    out_dir = script_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    required_columns = ["edyrs", "lastHomeWageAdjusted", "lastUsWageAdjusted", "country"]
    df0 = pd.read_excel(data_path)
    sample_flow = []
    sample_flow.append({"step": "start_authorized_pooled_poor_country_dataset_including_mexico", "rows": int(len(df0))})

    missing_columns = [c for c in required_columns if c not in df0.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    # The authorized file is treated as the pooled poor-country NIS/Migration Projects sample.
    # Mexico is retained; no country, sector, agriculture/nonagriculture, or rural/urban region
    # controls are introduced.
    df = df0.copy()
    sample_flow.append({
        "step": "retain_authorized_countries_including_mexico",
        "rows_removed": 0,
        "rows_remaining": int(len(df))
    })

    before = len(df)
    df = df.dropna(subset=required_columns)
    sample_flow.append({
        "step": "drop_missing_required_raw_columns",
        "rows_removed": int(before - len(df)),
        "rows_remaining": int(len(df))
    })

    before = len(df)
    positive_mask = (df["lastHomeWageAdjusted"] > 0) & (df["lastUsWageAdjusted"] > 0)
    df = df.loc[positive_mask].copy()
    sample_flow.append({
        "step": "drop_nonpositive_adjusted_wages_for_log_transform",
        "rows_removed": int(before - len(df)),
        "rows_remaining": int(len(df))
    })

    df["log_wage_gain"] = np.log(df["lastUsWageAdjusted"]) - np.log(df["lastHomeWageAdjusted"])
    df["edu_group"] = df["edyrs"].apply(add_education_group)

    before = len(df)
    constructed_required = ["log_wage_gain", "edu_group"]
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=constructed_required)
    sample_flow.append({
        "step": "drop_missing_or_nonfinite_constructed_variables",
        "rows_removed": int(before - len(df)),
        "rows_remaining": int(len(df))
    })

    edu_order = ["college_degree", "no_high_school", "some_high_school", "high_school", "some_college"]
    df["edu_group"] = pd.Categorical(df["edu_group"], categories=edu_order, ordered=False)

    formula = 'log_wage_gain ~ C(edu_group, Treatment(reference="college_degree"))'
    model = smf.rlm(formula=formula, data=df, M=sm.robust.norms.TukeyBiweight())
    fit = model.fit()

    term = 'C(edu_group, Treatment(reference="college_degree"))[T.no_high_school]'
    coef = float(fit.params[term])
    se = float(fit.bse[term])
    z_value = coef / se if se > 0 else float("nan")
    p_value = float(2 * stats.norm.sf(abs(z_value))) if math.isfinite(z_value) else None
    ci_low = float(coef - 1.96 * se)
    ci_high = float(coef + 1.96 * se)
    pct_diff = float(np.exp(coef) - 1)
    conclusion, strength = classify_result(coef, p_value)

    results = {
        "task_id": "Task2",
        "model": "Unadjusted Tukey biweight robust linear regression (statsmodels RLM)",
        "formula": formula,
        "sample_flow": sample_flow,
        "final_analytic_n": int(len(df)),
        "referenced_columns": required_columns,
        "excluded_controls_by_instruction": ["occGroupLastHomeJob", "agriculture_nonagriculture_sector", "rural_urban_region", "country", "sex", "age_home_job", "yearLastHomeJob", "yearLastUsJob"],
        "focal_term": term,
        "metric": "no_high_school_vs_college_degree_tukey_rlm_log_wage_gain_coefficient",
        "estimate_log_points": coef,
        "standard_error_normal_approx": se,
        "z_value": z_value,
        "p_value_normal_approx": p_value,
        "confidence_interval_95_normal_approx": [ci_low, ci_high],
        "exponentiated_proportional_difference": pct_diff,
        "direction": "positive" if coef > 0 else "negative" if coef < 0 else "zero",
        "conclusion_class": conclusion,
        "statistical_strength": strength,
        "conclusion_rule": "Support if the no-high-school minus college-degree coefficient is positive; p < 0.05 describes strong statistical evidence, while a positive estimate with p >= 0.05 is weak directional support. A negative estimate is opposite only if p < 0.05, otherwise inconclusive."
    }

    with open(out_dir / "results_task2.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with open(out_dir / "model_summary_task2.txt", "w", encoding="utf-8") as f:
        f.write(str(fit.summary()))
        f.write("\n\nSample flow:\n")
        f.write(json.dumps(sample_flow, indent=2))
        f.write("\n\nFocal result:\n")
        f.write(json.dumps(results, indent=2))

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
