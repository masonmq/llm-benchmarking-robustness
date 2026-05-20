import json
import math
import os
import pandas as pd

# All IO must use /app/data
DATA_PATH = "/app/data/final_data.dta"
OUTPUT_JSON = "/app/data/task1_output.json"


def main():
    # Load data
    df = pd.read_stata(DATA_PATH)

    # Keep only needed columns
    cols = ["complaints_2008", "first_A"]
    for c in cols:
        if c not in df.columns:
            raise ValueError(f"Required column '{c}' not found in dataset.")
    d = df[cols].dropna(subset=["complaints_2008", "first_A"]).copy()

    # Ensure grouping is binary 0/1
    # Treat any nonzero as 1
    d["first_A_bin"] = (d["first_A"] != 0).astype(int)

    grp0 = d.loc[d["first_A_bin"] == 0, "complaints_2008"].astype(float)
    grp1 = d.loc[d["first_A_bin"] == 1, "complaints_2008"].astype(float)

    n0, n1 = int(grp0.shape[0]), int(grp1.shape[0])
    mean0 = float(grp0.mean()) if n0 > 0 else float("nan")
    mean1 = float(grp1.mean()) if n1 > 0 else float("nan")
    std0 = float(grp0.std(ddof=1)) if n0 > 1 else float("nan")
    std1 = float(grp1.std(ddof=1)) if n1 > 1 else float("nan")

    ratio = (mean1 / mean0) if (mean0 is not None and not math.isclose(mean0, 0.0)) else None
    diff = mean1 - mean0 if (not math.isnan(mean1) and not math.isnan(mean0)) else None

    result = {
        "task": "Task1",
        "analysis": "Group means comparison of complaints_2008 by first_A",
        "dataset": os.path.basename(DATA_PATH),
        "groups": {
            "first_A==0": {"n": n0, "mean_complaints_2008": mean0, "sd": std0},
            "first_A==1": {"n": n1, "mean_complaints_2008": mean1, "sd": std1}
        },
        "contrast": {
            "difference_in_means": diff,
            "ratio_mean_firstA1_over_firstA0": ratio
        }
    }

    # Save and print
    with open(OUTPUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
