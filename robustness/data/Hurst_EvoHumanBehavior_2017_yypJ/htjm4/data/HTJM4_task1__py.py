import os
import sys
import csv
import json
import math
import zipfile
import io

DATA_DIR = "/app/data"
TASK1_OUT = os.path.join(DATA_DIR, "htjm4_task1_results.json")
EXTRACTED_CSV = os.path.join(DATA_DIR, "htjm4_extracted.csv")

REQUIRED_COLS_TASK1 = ["DSM5_Total", "MiniK_Total", "HKSS_Total"]


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
    debug_out = os.path.join(DATA_DIR, os.path.basename(jasp_path) + "__namelist.json")
    try:
        with zipfile.ZipFile(jasp_path, 'r') as zf:
            names = zf.namelist()
            # Write debug listing
            try:
                with open(debug_out, 'w', encoding='utf-8') as dbg:
                    json.dump({"files": names}, dbg, indent=2)
            except Exception:
                pass
            # Prefer CSV inside archive
            for name in names:
                if name.lower().endswith('.csv'):
                    with zf.open(name) as fh:
                        data = fh.read()
                        text = data.decode('utf-8', errors='replace')
                        with open(EXTRACTED_CSV, 'w', encoding='utf-8', newline='') as out:
                            out.write(text)
                        if csv_has_columns(EXTRACTED_CSV, REQUIRED_COLS_TASK1):
                            return EXTRACTED_CSV
            # Fallback: JSON-based dataset
            for name in names:
                if name.lower().endswith('.json'):
                    try:
                        with zf.open(name) as fh:
                            js_text = fh.read().decode('utf-8', errors='replace')
                            js = json.loads(js_text)
                        rows = []
                        if isinstance(js, dict):
                            if 'data' in js and isinstance(js['data'], list) and js['data'] and isinstance(js['data'][0], dict):
                                rows = js['data']
                            elif 'columns' in js and isinstance(js['columns'], list):
                                cols = js['columns']
                                names2 = []
                                data_arrays = []
                                for c in cols:
                                    nm = c.get('name') or c.get('columnName') or c.get('label')
                                    vals = c.get('data') or c.get('values') or c.get('columnData')
                                    if nm is not None and vals is not None:
                                        names2.append(str(nm))
                                        data_arrays.append(vals)
                                if names2 and data_arrays and all(len(a) == len(data_arrays[0]) for a in data_arrays):
                                    for i in range(len(data_arrays[0])):
                                        row = {names2[j]: data_arrays[j][i] for j in range(len(names2))}
                                        rows.append(row)
                        if rows:
                            # Write to CSV
                            fieldnames = list({k for r in rows for k in r.keys()})
                            with open(EXTRACTED_CSV, 'w', newline='', encoding='utf-8') as out:
                                writer = csv.DictWriter(out, fieldnames=fieldnames)
                                writer.writeheader()
                                for r in rows:
                                    writer.writerow(r)
                            if csv_has_columns(EXTRACTED_CSV, REQUIRED_COLS_TASK1):
                                return EXTRACTED_CSV
                    except Exception:
                        continue
    except Exception as e:
        try:
            with open(debug_out, 'w', encoding='utf-8') as dbg:
                json.dump({"error": str(e)}, dbg, indent=2)
        except Exception:
            pass
    return None


def extract_dataset_to_csv():
    # Try existing CSVs first
    p = find_csv_with_required(REQUIRED_COLS_TASK1)
    if p is not None:
        return p
    # Try to extract from any JASP file in DATA_DIR
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
    # Compute ranks with average for ties
    n = len(values)
    sorted_idx = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[sorted_idx[j+1]] == values[sorted_idx[i]]:
            j += 1
        # average rank from i..j (1-based ranks)
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
    # Find or extract dataset
    data_path = extract_dataset_to_csv()
    if data_path is None:
        fail = {"error": "no_dataset_found", "message": "Could not locate CSV with required columns nor extract from JASP in /app/data"}
        with open(TASK1_OUT, 'w') as f:
            json.dump(fail, f, indent=2)
        return 3

    data = read_columns(data_path, REQUIRED_COLS_TASK1 + ["Age", "Sex"])  # Age/Sex may not exist; handled as None

    res = {
        "task": "Task1",
        "analyses": {
            "spearman": {
                "DSM5_vs_MiniK": spearman(data.get("DSM5_Total", []), data.get("MiniK_Total", [])),
                "DSM5_vs_HKSS": spearman(data.get("DSM5_Total", []), data.get("HKSS_Total", []))
            },
            "kendall_tau": {
                "DSM5_vs_MiniK": kendall_tau_b(data.get("DSM5_Total", []), data.get("MiniK_Total", [])),
                "DSM5_vs_HKSS": kendall_tau_b(data.get("DSM5_Total", []), data.get("HKSS_Total", []))
            }
        },
        "partial_sensitivity": None,
        "notes": "Alpha=0.005 threshold; p-values not computed due to minimal environment; Bayes factors not computed."
    }

    with open(TASK1_OUT, 'w') as f:
        json.dump(res, f, indent=2)

    return 0


if __name__ == '__main__':
    sys.exit(main())
