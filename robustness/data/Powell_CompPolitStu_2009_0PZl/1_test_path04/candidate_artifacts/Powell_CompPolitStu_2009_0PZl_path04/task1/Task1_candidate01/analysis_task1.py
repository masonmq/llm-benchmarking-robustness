#!/usr/bin/env python3
"""
Task1 robustness analysis for Powell_CompPolitStu_2009_0PZl.
Focal claim: Under SMD election rules, party competition should lead the plurality vote winner to be close to the median voter.
This script uses the authorized original Stata data and compares Manifesto-method plurality-winner distance from the median voter (pldist1)
between SMD and PR elections using a rank-based Mann-Whitney test plus a Hodges-Lehmann SMD-minus-PR location estimate.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DATA_PATH = Path("data/powell_original.dta")
OUT_DIR = Path("candidate_artifacts/Powell_CompPolitStu_2009_0PZl_path04/task1/Task1_candidate01")
REQUIRED_COLUMNS = ["country", "year", "smd", "pldist1"]


def classify_result(estimate, p_value, ci_low=None, ci_high=None):
    """Classify according to the fixed PaperRobust conclusion rules; expected estimate is negative."""
    if estimate < 0 and p_value <= 0.05:
        return "support"
    if estimate < 0 and 0.05 < p_value <= 0.055:
        # Borderline support only if the interval narrowly crosses the null. Use a simple narrow-crossing check if CI exists.
        if ci_low is not None and ci_high is not None and ci_low < 0 < ci_high and abs(ci_high) <= max(1e-12, 0.10 * abs(ci_low)):
            return "support"
        return "inconclusive"
    if estimate > 0 and p_value < 0.05:
        if ci_low is None or ci_low > 0:
            return "opposite"
    return "inconclusive"


def bootstrap_ci_hl(smd_values, pr_values, reps=2000, seed=202409):
    """Bootstrap percentile CI for Hodges-Lehmann pairwise difference median."""
    rng = np.random.default_rng(seed)
    n_smd = len(smd_values)
    n_pr = len(pr_values)
    boot = np.empty(reps, dtype=float)
    for i in range(reps):
        s = rng.choice(smd_values, size=n_smd, replace=True)
        p = rng.choice(pr_values, size=n_pr, replace=True)
        boot[i] = np.median((s[:, None] - p[None, :]).ravel())
    return [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]


def main():
    if not DATA_PATH.exists():
        sys.exit(f"Data file not found: {DATA_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_stata(DATA_PATH)
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        sys.exit("Missing required columns: " + ", ".join(missing_cols))

    sample_flow = []
    start_n = int(len(df))
    sample_flow.append({"step": "start_authorized_dataset", "rows": start_n, "removed": 0})

    work = df.copy()
    work["smd_clean"] = work["smd"].astype("string").str.strip().str.lower()

    before = len(work)
    work = work[work["smd_clean"].isin(["smd", "pr"])].copy()
    sample_flow.append({"step": "keep_smd_or_pr_election_rule", "rows": int(len(work)), "removed": int(before - len(work))})

    before = len(work)
    work = work.dropna(subset=["pldist1", "smd_clean"]).copy()
    sample_flow.append({"step": "drop_missing_pldist1_or_smd", "rows": int(len(work)), "removed": int(before - len(work))})

    work["smd_bin"] = (work["smd_clean"] == "smd").astype(int)
    smd_values = work.loc[work["smd_bin"] == 1, "pldist1"].astype(float).to_numpy()
    pr_values = work.loc[work["smd_bin"] == 0, "pldist1"].astype(float).to_numpy()
    if len(smd_values) == 0 or len(pr_values) == 0:
        sys.exit("Both SMD and PR groups must contain observations after filtering.")

    # Mann-Whitney U tests equality/stochastic dominance in raw pldist1 ranks; two-sided p is used for the fixed classification rule.
    mw = stats.mannwhitneyu(smd_values, pr_values, alternative="two-sided", method="auto")
    pairwise_diff = (smd_values[:, None] - pr_values[None, :]).ravel()
    hl_estimate = float(np.median(pairwise_diff))
    ci = bootstrap_ci_hl(smd_values, pr_values)
    prob_smd_less_pr = float(np.mean(smd_values[:, None] < pr_values[None, :]))
    conclusion = classify_result(hl_estimate, float(mw.pvalue), ci[0], ci[1])

    group_stats = work.groupby("smd_clean", observed=True)["pldist1"].agg(["count", "mean", "median", "std", "min", "max"]).reset_index()

    result = {
        "analysis": "Task1 nonparametric rank-based comparison of Manifesto plurality-winner distance by election rule",
        "data_file": str(DATA_PATH),
        "required_columns": REQUIRED_COLUMNS,
        "sample_flow": sample_flow,
        "group_stats": group_stats.to_dict(orient="records"),
        "focal_result": {
            "metric": "hodges_lehmann_median_pairwise_difference_smd_minus_pr_pldist1",
            "value": hl_estimate,
            "direction": "negative" if hl_estimate < 0 else "positive" if hl_estimate > 0 else "zero",
            "p_value": float(mw.pvalue),
            "test": "Mann-Whitney U two-sided rank-sum test comparing SMD and PR pldist1 distributions",
            "test_statistic_U": float(mw.statistic),
            "confidence_interval": ci,
            "sample_size": int(len(work)),
            "n_smd": int(len(smd_values)),
            "n_pr": int(len(pr_values)),
            "common_language_probability_smd_distance_less_than_pr": prob_smd_less_pr,
            "conclusion": conclusion,
            "expected_direction_for_claim": "negative SMD-minus-PR distance, meaning SMD plurality winners are closer to the median voter than PR plurality winners"
        }
    }

    print(json.dumps(result, indent=2))
    with open(OUT_DIR / "task1_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
