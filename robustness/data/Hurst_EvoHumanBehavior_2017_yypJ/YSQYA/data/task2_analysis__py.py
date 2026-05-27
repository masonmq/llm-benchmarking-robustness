import json
from task_common_nolib import read_csv_columns, get_float_column, partial_corr_xy_z

DATA_PATH = "/app/data/1-s2.0-S1090513816301118-mmc1.csv"
OUTPUT_PATH = "/app/data/task2_results.json"


def main():
    data = read_csv_columns(DATA_PATH)

    age = get_float_column(data, "Age")
    dsm5_total = get_float_column(data, "DSM5_Total")
    minik_total = get_float_column(data, "MiniK_Total")

    if age is None or dsm5_total is None or minik_total is None:
        raise RuntimeError("Required columns missing: Age, DSM5_Total, MiniK_Total.")

    r, p, n, df = partial_corr_xy_z(minik_total, dsm5_total, age)
    results = {
        "notes": "Task2: partial correlation between MiniK_Total and DSM5_Total controlling Age (no external libs).",
        "partial_corr_minik_dsm5_age": {"r": r, "p": p, "n": n, "df": df}
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
