import json
import math
import os
import numpy as np
import pandas as pd
from scipy import stats

# All IO must use /app/data
DATA_PATH = "/app/data/final_data.dta"
OUTPUT_JSON = "/app/data/task2_output.json"


def welch_ttest(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    # Welch's t-test (unequal variances), two-sided p-value
    t_stat, p_val = stats.ttest_ind(x, y, equal_var=False, nan_policy='omit')
    return float(t_stat), float(p_val)


def main():
    # Load data
    df = pd.read_stata(DATA_PATH)

    # Use overall complaints and first_A as instructed
    cols = ["complaints_2008", "first_A"]
    for c in cols:
        if c not in df.columns:
            raise ValueError(f"Required column '{c}' not found in dataset.")
    d = df[cols].dropna(subset=cols).copy()

    # Ensure grouping is binary 0/1
    d["first_A_bin"] = (d["first_A"] != 0).astype(int)

    grp0 = d.loc[d["first_A_bin"] == 0, "complaints_2008"].astype(float)
    grp1 = d.loc[d["first_A_bin"] == 1, "complaints_2008"].astype(float)

    n0, n1 = int(grp0.shape[0]), int(grp1.shape[0])
    mean0 = float(grp0.mean()) if n0 > 0 else float("nan")
    mean1 = float(grp1.mean()) if n1 > 0 else float("nan")
    sd0 = float(grp0.std(ddof=1)) if n0 > 1 else float("nan")
    sd1 = float(grp1.std(ddof=1)) if n1 > 1 else float("nan")

    t_stat, p_val = welch_ttest(grp1, grp0)

    result = {
        "task": "Task2",
        "analysis": "Welch two-sample t-test: complaints_2008 ~ first_A",
        "dataset": os.path.basename(DATA_PATH),
        "groups": {
            "first_A==0": {"n": n0, "mean": mean0, "sd": sd0},
            "first_A==1": {"n": n1, "mean": mean1, "sd": sd1}
        },
        "test": {
            "test_family": "t_test",
            "alternative": "two-sided",
            "statistic": t_stat,
            "p_value": p_val
        }
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
