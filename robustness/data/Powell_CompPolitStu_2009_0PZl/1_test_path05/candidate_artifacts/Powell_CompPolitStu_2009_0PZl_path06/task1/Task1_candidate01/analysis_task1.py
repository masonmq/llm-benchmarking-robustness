#!/usr/bin/env python3
"""Task 1 robustness analysis for Powell_CompPolitStu_2009_0PZl.

Tests whether plurality-vote winners are closer to the median voter under SMD
than under PR using the Manifesto-method distance variable pldist1. The focal
estimand is the SMD-minus-PR mean difference in pldist1; a negative value is
consistent with the claim. Inference uses a fixed-seed randomization/permutation
test rather than a regression model.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def clean_smd(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def two_sided_permutation_p(y: np.ndarray, g: np.ndarray, n_perm: int = 100000, seed: int = 20250306) -> float:
    """Two-sided permutation p-value for SMD-minus-PR mean difference."""
    rng = np.random.default_rng(seed)
    observed = y[g == 1].mean() - y[g == 0].mean()
    n_smd = int(g.sum())
    n = len(y)
    extreme = 0
    for _ in range(n_perm):
        idx = rng.permutation(n)
        smd_idx = idx[:n_smd]
        pr_idx = idx[n_smd:]
        diff = y[smd_idx].mean() - y[pr_idx].mean()
        if abs(diff) >= abs(observed) - 1e-15:
            extreme += 1
    return (extreme + 1) / (n_perm + 1)


def bootstrap_ci(y: np.ndarray, g: np.ndarray, n_boot: int = 20000, seed: int = 20250307, alpha: float = 0.05):
    """Percentile bootstrap CI resampling within election-rule groups."""
    rng = np.random.default_rng(seed)
    smd_y = y[g == 1]
    pr_y = y[g == 0]
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        smd_b = rng.choice(smd_y, size=len(smd_y), replace=True)
        pr_b = rng.choice(pr_y, size=len(pr_y), replace=True)
        diffs[b] = smd_b.mean() - pr_b.mean()
    return [float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))]


def classify(estimate: float, p_value: float, ci_low: float, ci_high: float) -> str:
    if estimate < 0 and p_value <= 0.05:
        return "support"
    if estimate < 0 and 0.05 < p_value <= 0.055 and ci_low < 0 < ci_high:
        return "support"
    if estimate > 0 and p_value < 0.05 and ci_low > 0:
        return "opposite"
    return "inconclusive"


def main():
    artifact_dir = Path(__file__).resolve().parent
    project_root = Path(__file__).resolve().parents[4]
    data_path = project_root / "data" / "powell_original.dta"

    df = pd.read_stata(data_path, convert_categoricals=True)
    starting_rows = int(len(df))
    required_columns = ["smd", "pldist1"]
    missing_columns = [c for c in required_columns if c not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    work = df.copy()
    work["smd_clean"] = clean_smd(work["smd"])

    flow = []
    before = len(work)
    work = work[work["smd_clean"].isin(["smd", "pr"])].copy()
    flow.append({"rule": "retain rows with smd coded as 'smd' or 'pr'", "rows_before": int(before), "rows_after": int(len(work)), "rows_removed": int(before - len(work))})

    before = len(work)
    work = work[pd.notna(work["pldist1"])].copy()
    flow.append({"rule": "drop rows with missing pldist1", "rows_before": int(before), "rows_after": int(len(work)), "rows_removed": int(before - len(work))})

    work["smd_bin"] = (work["smd_clean"] == "smd").astype(int)
    y = work["pldist1"].astype(float).to_numpy()
    g = work["smd_bin"].to_numpy()

    estimate = float(y[g == 1].mean() - y[g == 0].mean())
    p_value = float(two_sided_permutation_p(y, g))
    ci_low, ci_high = bootstrap_ci(y, g)
    conclusion = classify(estimate, p_value, ci_low, ci_high)

    sample_flow = {
        "starting_rows": starting_rows,
        "rules": flow,
        "final_analytic_rows": int(len(work)),
        "group_counts": {"smd": int((g == 1).sum()), "pr": int((g == 0).sum())},
    }
    result = {
        "task_id": "Task1",
        "metric": "permutation_test_mean_difference_smd_minus_pr_pldist1",
        "estimate": estimate,
        "direction": "negative" if estimate < 0 else "positive" if estimate > 0 else "zero",
        "p_value_two_sided_permutation": p_value,
        "confidence_interval_bootstrap_percentile_95": [ci_low, ci_high],
        "sample_size": int(len(work)),
        "group_counts": sample_flow["group_counts"],
        "conclusion": conclusion,
        "inference_rule": "Expected direction is negative. Support requires a negative SMD-minus-PR mean difference with p <= 0.05, or borderline support for 0.05 < p <= 0.055 only when the estimate is substantively meaningful and the uncertainty interval narrowly crosses zero. A positive estimate is opposite only with affirmative p < 0.05 evidence and a confidence interval above zero; otherwise inconclusive.",
        "sample_flow": sample_flow,
    }

    (artifact_dir / "sample_flow_task1.json").write_text(json.dumps(sample_flow, indent=2))
    (artifact_dir / "result_task1.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
