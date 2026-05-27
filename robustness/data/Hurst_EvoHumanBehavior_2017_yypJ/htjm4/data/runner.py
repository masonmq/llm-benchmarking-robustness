import os
import json
import zipfile
from io import BytesIO
import pandas as pd
import numpy as np
from scipy import stats
import pingouin as pg

DATA_DIR = "/app/data"
TASK1_OUT = os.path.join(DATA_DIR, "htjm4_task1_results.json")
TASK2_OUT = os.path.join(DATA_DIR, "htjm4_task2_results.json")
EXTRACTED_CSV = os.path.join(DATA_DIR, "htjm4_extracted.csv")


def find_jasp_files(base_dir):
    jasp_files = []
    for fn in os.listdir(base_dir):
        if fn.lower().endswith('.jasp'):
            jasp_files.append(os.path.join(base_dir, fn))
    return jasp_files


def try_extract_csv_from_jasp(jasp_path):
    with zipfile.ZipFile(jasp_path, 'r') as zf:
        names = zf.namelist()
        # 1) Try any embedded CSV
        csv_candidates = [n for n in names if n.lower().endswith('.csv')]
        for name in csv_candidates:
            try:
                with zf.open(name) as f:
                    df = pd.read_csv(f)
                if not df.empty and df.shape[1] > 0:
                    return df
            except Exception:
                pass
        # 2) Try JSON-based dataset formats commonly used by JASP
        json_candidates = [n for n in names if n.lower().endswith('.json')]
        for name in json_candidates:
            try:
                with zf.open(name) as f:
                    js = json.load(f)
                # Heuristic 1: columns list with 'name' and 'data' or 'values'
                if isinstance(js, dict):
                    if 'columns' in js and isinstance(js['columns'], list):
                        cols = js['columns']
                        col_names = []
                        data_arrays = []
                        for c in cols:
                            nm = c.get('name') or c.get('columnName') or c.get('label')
                            vals = c.get('data') or c.get('values') or c.get('columnData')
                            if nm is not None and vals is not None:
                                col_names.append(str(nm))
                                data_arrays.append(vals)
                        if col_names and data_arrays and all(len(a) == len(data_arrays[0]) for a in data_arrays):
                            df = pd.DataFrame({col_names[i]: data_arrays[i] for i in range(len(col_names))})
                            if not df.empty:
                                return df
                    # Heuristic 2: top-level 'data' is a list of records
                    if 'data' in js and isinstance(js['data'], list) and len(js['data']) > 0 and isinstance(js['data'][0], dict):
                        df = pd.DataFrame(js['data'])
                        if not df.empty:
                            return df
            except Exception:
                continue
    return None


def extract_dataset_to_csv():
    # If a CSV already exists in DATA_DIR with required columns, keep it
    existing_csvs = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.lower().endswith('.csv')]
    required_any = {'DSM5_Total'}  # minimal check
    for path in existing_csvs:
        try:
            head = pd.read_csv(path, nrows=5)
            if required_any.issubset(set(head.columns)):
                return path
        except Exception:
            continue

    # Try JASP files
    jasp_files = find_jasp_files(DATA_DIR)
    for jasp in jasp_files:
        df = try_extract_csv_from_jasp(jasp)
        if df is not None and not df.empty:
            # Write to CSV
            df.to_csv(EXTRACTED_CSV, index=False)
            return EXTRACTED_CSV

    return None


def coerce_sex_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    mapping = {
        'male': 1, 'm': 1, 1: 1,
        'female': 0, 'f': 0, 0: 0,
        'man': 1, 'boy': 1,
        'woman': 0, 'girl': 0
    }
    return series.astype(str).str.strip().str.lower().map(lambda x: mapping.get(x, np.nan))


def spearman_corr(x, y):
    df = pd.concat([x, y], axis=1).dropna()
    if df.shape[0] < 3:
        return {"n": int(df.shape[0]), "r_s": None, "p": None}
    r, p = stats.spearmanr(df.iloc[:, 0], df.iloc[:, 1])
    return {"n": int(df.shape[0]), "r_s": float(r), "p": float(p)}


def kendall_tau(x, y):
    df = pd.concat([x, y], axis=1).dropna()
    if df.shape[0] < 3:
        return {"n": int(df.shape[0]), "tau_b": None, "p": None}
    tau, p = stats.kendalltau(df.iloc[:, 0], df.iloc[:, 1], variant='b')
    return {"n": int(df.shape[0]), "tau_b": float(tau), "p": float(p)}


def partial_spearman(df, x, y, covars):
    cols = [x, y] + covars
    sub = df[cols].dropna()
    if sub.shape[0] < 5:
        return {"n": int(sub.shape[0]), "r_s_partial": None, "p": None}
    try:
        res = pg.partial_corr(data=sub, x=x, y=y, covar=covars, method='spearman')
        out = {
            "n": int(res.loc[0, 'n'] if 'n' in res.columns else sub.shape[0]),
            "r_s_partial": float(res.loc[0, 'r']),
            "p": float(res.loc[0, 'p-val'])
        }
        return out
    except Exception as e:
        return {"n": int(sub.shape[0]), "r_s_partial": None, "p": None, "error": str(e)}


def run_task1(df: pd.DataFrame):
    required = ['DSM5_Total', 'MiniK_Total', 'HKSS_Total']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"error": "missing_columns", "missing": missing}

    covars = []
    if 'Age' in df.columns:
        covars.append('Age')
    if 'Sex' in df.columns:
        df['Sex_num'] = coerce_sex_numeric(df['Sex'])
        if df['Sex_num'].notna().sum() >= 3:
            covars.append('Sex_num')

    results = {
        "task": "Task1",
        "analyses": {
            "spearman": {
                "DSM5_vs_MiniK": spearman_corr(df['DSM5_Total'], df['MiniK_Total']),
                "DSM5_vs_HKSS": spearman_corr(df['DSM5_Total'], df['HKSS_Total'])
            },
            "kendall_tau": {
                "DSM5_vs_MiniK": kendall_tau(df['DSM5_Total'], df['MiniK_Total']),
                "DSM5_vs_HKSS": kendall_tau(df['DSM5_Total'], df['HKSS_Total'])
            }
        },
        "partial_sensitivity": None,
        "notes": "Alpha=0.005 threshold; Bayes factors not computed."
    }

    if covars:
        results["partial_sensitivity"] = {
            "covariates": covars,
            "DSM5_vs_MiniK": partial_spearman(df, 'DSM5_Total', 'MiniK_Total', covars),
            "DSM5_vs_HKSS": partial_spearman(df, 'DSM5_Total', 'HKSS_Total', covars)
        }

    return results


def run_task2(df: pd.DataFrame):
    required = ['DSM5_Total', 'MiniK_Total']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"error": "missing_columns", "missing": missing}

    results = {
        "task": "Task2",
        "analyses": {
            "kendall_tau": {
                "DSM5_vs_MiniK": kendall_tau(df['DSM5_Total'], df['MiniK_Total'])
            },
            "spearman": {
                "DSM5_vs_MiniK": spearman_corr(df['DSM5_Total'], df['MiniK_Total'])
            }
        },
        "alpha": 0.005,
        "notes": "Bayesian Kendall's tau not computed; frequentist Kendall's tau reported as per plan."
    }
    return results


def main():
    # Prepare dataset
    data_path = extract_dataset_to_csv()
    if data_path is None:
        # Write failure JSONs to aid debugging
        fail_msg = {
            "error": "no_dataset_found",
            "message": "Could not find a CSV under /app/data with DSM5_Total, nor extract data from any .jasp files in /app/data."
        }
        with open(TASK1_OUT, 'w') as f:
            json.dump(fail_msg, f, indent=2)
        with open(TASK2_OUT, 'w') as f:
            json.dump(fail_msg, f, indent=2)
        return 3

    df = pd.read_csv(data_path)

    # Run Task1 and Task2
    res1 = run_task1(df)
    res2 = run_task2(df)

    with open(TASK1_OUT, 'w') as f:
        json.dump(res1, f, indent=2)
    with open(TASK2_OUT, 'w') as f:
        json.dump(res2, f, indent=2)

    return 0


if __name__ == "__main__":
    code = main()
    raise SystemExit(code)
