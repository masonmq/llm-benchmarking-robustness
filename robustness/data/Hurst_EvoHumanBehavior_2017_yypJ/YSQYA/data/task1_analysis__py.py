import json
from task_common_nolib import read_csv_columns, get_float_column, partial_corr_xy_z, ols_y_on_x_z

DATA_PATH = "/app/data/1-s2.0-S1090513816301118-mmc1.csv"
OUTPUT_PATH = "/app/data/task1_results.json"


def main():
    data = read_csv_columns(DATA_PATH)

    age = get_float_column(data, "Age")
    dsm5_total = get_float_column(data, "DSM5_Total")
    minik_total = get_float_column(data, "MiniK_Total")
    hkss_total = get_float_column(data, "HKSS_Total")

    if age is None or dsm5_total is None or minik_total is None:
        raise RuntimeError("Required columns missing: need Age, DSM5_Total, MiniK_Total.")

    results = {"notes": "Task1: partial correlations controlling for Age and OLS with Age as control (no external libs)."}

    r_mk, p_mk, n_mk, df_mk = partial_corr_xy_z(minik_total, dsm5_total, age)
    results["partial_corr_minik_dsm5_age"] = {
        "r": r_mk,
        "p": p_mk,
        "n": n_mk,
        "df": df_mk
    }

    reg_mk = ols_y_on_x_z(dsm5_total, minik_total, age)
    results["ols_dsm5_minik_age"] = reg_mk

    if hkss_total is not None:
        r_hk, p_hk, n_hk, df_hk = partial_corr_xy_z(hkss_total, dsm5_total, age)
        results["partial_corr_hkss_dsm5_age"] = {
            "r": r_hk,
            "p": p_hk,
            "n": n_hk,
            "df": df_hk
        }
        reg_hk = ols_y_on_x_z(dsm5_total, hkss_total, age)
        results["ols_dsm5_hkss_age"] = reg_hk

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
