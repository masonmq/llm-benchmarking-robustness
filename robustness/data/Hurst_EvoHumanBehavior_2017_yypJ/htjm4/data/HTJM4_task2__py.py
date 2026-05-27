import os
import sys
import csv
import json
import math
import zipfile

DATA_DIR = "/app/data"
TASK2_OUT = os.path.join(DATA_DIR, "htjm4_task2_results.json")
EXTRACTED_CSV = os.path.join(DATA_DIR, "htjm4_extracted.csv")

REQUIRED_COLS_TASK2 = ["DSM5_Total", "MiniK_Total"]


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "" or s.lower() in {"na", "nan", "null", "none"}:
        return None
    try:
            return float(s)
    except Exception:
            return None


def list_csv_files():
    try:
        return [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.lower().endswith('.csv')]
    except Exception:
        return []


def csv_has_columns(path, cols):
    try:
        with open(path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            if header is None:
                return False
            header_set = set(h.strip() for h in header)
            return all(c in header_set for c in cols)
    except Exception:
        return False


def find_csv_with_required(required_cols):
    for p in list_csv_files():
        if csv_has_columns(p, required_cols):
            return p
    return None


def try_extract_csv_from_jasp(jasp_path):
    try:
        with zipfile.ZipFile(jasp_path, 'r') as zf:
            names = zf.namelist()
            for name in names:
                if name.lower().endswith('.csv'):
                    with zf.open(name) as fh:
                        data = fh.read().decode('utf-8', errors='replace')
                        with open(EXTRACTED_CSV, 'w', encoding='utf-8', newline='') as out:
                            out.write(data)
                        if csv_has_columns(EXTRACTED_CSV, REQUIRED_COLS_TASK2):
                            return EXTRACTED_CSV
    except Exception:
        pass
    return None


def extract_dataset_to_csv():
    p = find_csv_with_required(REQUIRED_COLS_TASK2)
    if p is not None:
        return p
    try:
        for fn in os.listdir(DATA_DIR):
            if fn.lower().endswith('.jasp'):
                p = try_extract_csv_from_jasp(os.path.join(DATA_DIR, fn))
                if p is not None:
                    return p
    except Exception:
        pass
    return None


def read_columns(path, cols):
    data = {c: [] for c in cols}
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for c in cols:
                v = to_float(row.get(c))
                data[c].append(v)
    return data


def pairwise_complete(x_list, y_list):
    pairs = []
    for x, y in zip(x_list, y_list):
        if x is None or y is None:
            continue
        pairs.append((x, y))
    return pairs


def rankdata_avg(values):
    n = len(values)
    sorted_idx = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[sorted_idx[j+1]] == values[sorted_idx[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[sorted_idx[k]] = avg_rank
        i = j + 1
    return ranks


def pearson_corr(x, y):
    n = len(x)
    if n < 3:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    vx = sum((xi - mx) ** 2 for xi in x)
    vy = sum((yi - my) ** 2 for yi in y)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def spearman(x_list, y_list):
    pairs = pairwise_complete(x_list, y_list)
    n = len(pairs)
    if n < 3:
        return {"n": n, "r_s": None, "p": None}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    rx = rankdata_avg(xs)
    ry = rankdata_avg(ys)
    r = pearson_corr(rx, ry)
    return {"n": n, "r_s": None if r is None else float(r), "p": None}


def kendall_tau_b(x_list, y_list):
    pairs = pairwise_complete(x_list, y_list)
    n = len(pairs)
    if n < 3:
        return {"n": n, "tau_b": None, "p": None}
    C = 0
    D = 0
    T_x = 0
    T_y = 0
    for i in range(n - 1):
        xi, yi = pairs[i]
        for j in range(i + 1, n):
            xj, yj = pairs[j]
            if xi == xj and yi == yj:
                T_x += 1
                T_y += 1
            elif xi == xj:
                T_x += 1
            elif yi == yj:
                T_y += 1
            else:
                s = (1 if xi > xj else -1) * (1 if yi > yj else -1)
                if s > 0:
                    C += 1
                elif s < 0:
                    D += 1
    denom = math.sqrt((C + D + T_x) * (C + D + T_y))
    if denom == 0:
        tau = None
    else:
        tau = (C - D) / denom
    return {"n": n, "tau_b": None if tau is None else float(tau), "p": None}


def main():
    data_path = extract_dataset_to_csv()
    if data_path is None:
        fail = {"error": "no_dataset_found", "message": "Could not locate CSV with required columns nor extract from JASP in /app/data"}
        with open(TASK2_OUT, 'w') as f:
            json.dump(fail, f, indent=2)
        return 3

    data = read_columns(data_path, REQUIRED_COLS_TASK2)

    res = {
        "task": "Task2",
        "analyses": {
            "kendall_tau": {
                "DSM5_vs_MiniK": kendall_tau_b(data.get("DSM5_Total", []), data.get("MiniK_Total", []))
            },
            "spearman": {
                "DSM5_vs_MiniK": spearman(data.get("DSM5_Total", []), data.get("MiniK_Total", []))
            }
        },
        "alpha": 0.005,
        "notes": "P-values not computed due to minimal environment."
    }

    with open(TASK2_OUT, 'w') as f:
        json.dump(res, f, indent=2)

    return 0


if __name__ == '__main__':
    sys.exit(main())
