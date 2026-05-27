#!/usr/bin/env python3
"""
Standalone Python analysis for PH39A using only the standard library.
Computes Spearman correlation between MiniK_Total and DSM5_Total and
reports an approximate p-value (two-sided via normal approximation),
plus a one-sided p-value for the 'less' alternative (rho < 0).

Reads:  /app/data/data.csv
Writes: /app/data/results_ph39a.json
Prints: JSON summary to stdout
"""
import csv
import json
import math
import sys
from pathlib import Path
from typing import List, Tuple


def read_two_columns(csv_path: Path, x_name: str, y_name: str) -> Tuple[List[float], List[float]]:
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        raise RuntimeError("CSV file is empty")
    header = rows[0]
    try:
        xi = header.index(x_name)
    except ValueError:
        raise RuntimeError(f"Missing expected column: {x_name}")
    try:
        yi = header.index(y_name)
    except ValueError:
        raise RuntimeError(f"Missing expected column: {y_name}")

    xs: List[float] = []
    ys: List[float] = []
    for r in rows[1:]:
        if xi >= len(r) or yi >= len(r):
            continue
        xv = r[xi].strip()
        yv = r[yi].strip()
        # Treat empty or non-numeric as missing
        try:
            xval = float(xv)
            yval = float(yv)
        except Exception:
            continue
        if math.isnan(xval) or math.isnan(yval):
            continue
        xs.append(xval)
        ys.append(yval)
    return xs, ys


def average_ranks(values: List[float]) -> List[float]:
    # Returns 1-based average ranks with ties averaged
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    current_rank = 1
    while i < n:
        j = i + 1
        # group ties
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        # average rank for positions i..j-1
        avg_rank = (current_rank + (current_rank + (j - i) - 1)) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        current_rank += (j - i)
        i = j
    return ranks


def pearson_corr(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n != len(y) or n < 2:
        raise RuntimeError("Vectors must have same length >= 2")
    mx = sum(x) / n
    my = sum(y) / n
    num = 0.0
    sx = 0.0
    sy = 0.0
    for i in range(n):
        dx = x[i] - mx
        dy = y[i] - my
        num += dx * dy
        sx += dx * dx
        sy += dy * dy
    if sx <= 0.0 or sy <= 0.0:
        return float('nan')
    return num / math.sqrt(sx * sy)


def normal_cdf(z: float) -> float:
    # Standard normal CDF using math.erf
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def approximate_p_values_from_rho(rho: float, n: int) -> Tuple[float, float]:
    # Approximate two-sided p-value using large-sample normal approximation.
    # Use t-like transform commonly used for Pearson as an approximation for Spearman when n is large.
    # t = r * sqrt((n-2)/(1-r^2)) ; then approximate with normal: p = 2*(1-Phi(|t|)).
    if n <= 3 or math.isnan(rho):
        return float('nan'), float('nan')
    denom = max(1e-12, 1.0 - rho * rho)
    t_like = rho * math.sqrt(max(1.0, n - 2) / denom)
    p_two = 2.0 * (1.0 - normal_cdf(abs(t_like)))
    # One-sided 'less'
    if rho < 0:
        p_one_less = p_two / 2.0
    else:
        p_one_less = 1.0 - (p_two / 2.0)
    # Clamp to [0,1]
    p_two = max(0.0, min(1.0, p_two))
    p_one_less = max(0.0, min(1.0, p_one_less))
    return p_two, p_one_less


def main():
    data_path = Path("/app/data/data.csv")
    if not data_path.exists():
        print(f"ERROR: Expected data at {data_path} but it was not found.", file=sys.stderr)
        sys.exit(1)

    x_var = "MiniK_Total"
    y_var = "DSM5_Total"

    try:
        x_vals, y_vals = read_two_columns(data_path, x_var, y_var)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    n = len(x_vals)
    if n < 3:
        print("ERROR: Insufficient non-missing observations to compute correlation.", file=sys.stderr)
        sys.exit(3)

    # Spearman: correlate ranks
    rx = average_ranks(x_vals)
    ry = average_ranks(y_vals)
    rho = pearson_corr(rx, ry)

    # Approximate p-values
    p_two, p_one_less = approximate_p_values_from_rho(rho, n)

    results = {
        "n": n,
        "x_var": x_var,
        "y_var": y_var,
        "spearman_rho": None if (rho is None or (isinstance(rho, float) and math.isnan(rho))) else float(rho),
        "p_value_two_sided": None if (p_two is None or (isinstance(p_two, float) and math.isnan(p_two))) else float(p_two),
        "p_value_one_sided_less": None if (p_one_less is None or (isinstance(p_one_less, float) and math.isnan(p_one_less))) else float(p_one_less),
        "alternative": "less",
        "hypothesis": "rho < 0 (MiniK_Total negatively correlated with DSM5_Total)",
        "p_value_note": "P-values are large-sample normal approximations for Spearman's rho."
    }

    payload = {"analysis": "PH39A_spearman_minik_dsm5", "results": results}
    print(json.dumps(payload, indent=2))

    out_path = Path("/app/data/results_ph39a.json")
    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"WARNING: Failed to write results to {out_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
