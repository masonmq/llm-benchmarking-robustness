import csv
import json
import math
from typing import List, Tuple, Optional, Dict

# Utility: read CSV into dict of columns -> list of values (strings)
def read_csv_columns(path: str) -> Dict[str, List[Optional[str]]]:
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return {}
    header = rows[0]
    data = {h: [] for h in header}
    for r in rows[1:]:
        for i, h in enumerate(header):
            val = r[i] if i < len(r) else ''
            data[h].append(val)
    return data

# Convert column of strings to floats with None for missing/non-numeric
def to_float_series(values: List[Optional[str]]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        s = str(v).strip()
        if s == '' or s.lower() in {'na', 'nan', 'null', 'none'}:
            out.append(None)
            continue
        try:
            out.append(float(s))
        except Exception:
            out.append(None)
    return out

# Filter rows where all provided series have non-None

def filter_complete_rows(series_list: List[List[Optional[float]]]) -> List[Tuple[float, ...]]:
    n = len(series_list[0]) if series_list else 0
    out: List[Tuple[float, ...]] = []
    for i in range(n):
        row = []
        ok = True
        for s in series_list:
            vi = s[i]
            if vi is None or (isinstance(vi, float) and (math.isnan(vi) or math.isinf(vi))):
                ok = False
                break
            row.append(float(vi))
        if ok:
            out.append(tuple(row))
    return out

# Basic stats ignoring None, on complete paired rows only

def mean_std(x: List[float]) -> Tuple[float, float]:
    n = len(x)
    if n == 0:
        return float('nan'), float('nan')
    mu = sum(x) / n
    var = sum((xi - mu) ** 2 for xi in x) / n if n > 0 else float('nan')
    return mu, math.sqrt(var)


def pearsonr_from_pairs(x: List[float], y: List[float]) -> Tuple[float, int]:
    n = len(x)
    if n == 0 or n != len(y):
        return float('nan'), 0
    mx, sx = mean_std(x)
    my, sy = mean_std(y)
    if sx == 0 or sy == 0 or math.isnan(sx) or math.isnan(sy):
        return float('nan'), n
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / n
    r = cov / (sx * sy)
    # numerical safety
    r = max(-1.0, min(1.0, r))
    return r, n

# Normal CDF using error function

def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

# Approximate two-sided p-value for correlation using Fisher z transform

def p_value_from_r_fisherz(r: float, n_eff: int) -> float:
    # When r is exactly +/-1, p ~ 0
    if abs(r) >= 1.0 or n_eff <= 3:
        return 1.0 if n_eff <= 3 else 0.0
    try:
        z = 0.5 * math.log((1 + r) / (1 - r)) * math.sqrt(max(1, n_eff - 3))
    except Exception:
        return float('nan')
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return max(0.0, min(1.0, p))

# Partial correlation r(x,y|z) via correlation matrix formula, using rows with all three present

def partial_corr_xy_z(x_series: List[Optional[float]], y_series: List[Optional[float]], z_series: List[Optional[float]]):
    rows = filter_complete_rows([x_series, y_series, z_series])
    n = len(rows)
    if n < 4:
        return float('nan'), float('nan'), n, n - 3
    x = [r[0] for r in rows]
    y = [r[1] for r in rows]
    z = [r[2] for r in rows]
    r_xy, _ = pearsonr_from_pairs(x, y)
    r_xz, _ = pearsonr_from_pairs(x, z)
    r_yz, _ = pearsonr_from_pairs(y, z)
    denom = math.sqrt(max(1e-12, (1 - r_xz ** 2) * (1 - r_yz ** 2)))
    r_partial = (r_xy - r_xz * r_yz) / denom
    r_partial = max(-1.0, min(1.0, r_partial))
    df = n - 3
    p = p_value_from_r_fisherz(r_partial, n)
    return r_partial, p, n, df

# OLS with two predictors (intercept, x, z). Returns stats for x.

def ols_y_on_x_z(y_series: List[Optional[float]], x_series: List[Optional[float]], z_series: List[Optional[float]]):
    rows = filter_complete_rows([y_series, x_series, z_series])
    n = len(rows)
    if n < 3:
        return {
            'n': n,
            'coef': float('nan'),
            'se': float('nan'),
            't': float('nan'),
            'p': float('nan'),
            'beta_std': float('nan'),
            'r2': float('nan'),
            'adj_r2': float('nan')
        }
    # Build X'X and X'y for intercept, x, z
    s = {
        '1': n,
        'x': sum(r[1] for r in rows),
        'z': sum(r[2] for r in rows),
        'x2': sum(r[1] ** 2 for r in rows),
        'z2': sum(r[2] ** 2 for r in rows),
        'xz': sum(r[1] * r[2] for r in rows),
        'y': sum(r[0] for r in rows),
        'xy': sum(r[0] * r[1] for r in rows),
        'yz': sum(r[0] * r[2] for r in rows)
    }
    XtX = [
        [s['1'], s['x'], s['z']],
        [s['x'], s['x2'], s['xz']],
        [s['z'], s['xz'], s['z2']]
    ]
    Xty = [s['y'], s['xy'], s['yz']]

    # Invert 3x3 matrix XtX
    def det3(m):
        return (
            m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
            - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
            + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0])
        )
    D = det3(XtX)
    if abs(D) < 1e-12:
        coef = [float('nan'), float('nan'), float('nan')]
        invXtX = None
    else:
        # adjugate / cofactor matrix transpose
        invXtX = [[0.0]*3 for _ in range(3)]
        invXtX[0][0] =  (XtX[1][1]*XtX[2][2] - XtX[1][2]*XtX[2][1]) / D
        invXtX[0][1] = -(XtX[0][1]*XtX[2][2] - XtX[0][2]*XtX[2][1]) / D
        invXtX[0][2] =  (XtX[0][1]*XtX[1][2] - XtX[0][2]*XtX[1][1]) / D
        invXtX[1][0] = -(XtX[1][0]*XtX[2][2] - XtX[1][2]*XtX[2][0]) / D
        invXtX[1][1] =  (XtX[0][0]*XtX[2][2] - XtX[0][2]*XtX[2][0]) / D
        invXtX[1][2] = -(XtX[0][0]*XtX[1][2] - XtX[0][2]*XtX[1][0]) / D
        invXtX[2][0] =  (XtX[1][0]*XtX[2][1] - XtX[1][1]*XtX[2][0]) / D
        invXtX[2][1] = -(XtX[0][0]*XtX[2][1] - XtX[0][1]*XtX[2][0]) / D
        invXtX[2][2] =  (XtX[0][0]*XtX[1][1] - XtX[0][1]*XtX[1][0]) / D
        # beta = inv(X'X) X'y
        coef = [
            invXtX[0][0]*Xty[0] + invXtX[0][1]*Xty[1] + invXtX[0][2]*Xty[2],
            invXtX[1][0]*Xty[0] + invXtX[1][1]*Xty[1] + invXtX[1][2]*Xty[2],
            invXtX[2][0]*Xty[0] + invXtX[2][1]*Xty[1] + invXtX[2][2]*Xty[2]
        ]

    # Compute fit stats
    y = [r[0] for r in rows]
    x = [r[1] for r in rows]
    z = [r[2] for r in rows]
    if any(math.isnan(c) for c in coef):
        se_x = float('nan'); t_x = float('nan'); p_x = float('nan'); r2 = float('nan'); adj_r2 = float('nan')
    else:
        # predictions and residuals
        yhat = [coef[0] + coef[1]*x[i] + coef[2]*z[i] for i in range(n)]
        resid = [y[i] - yhat[i] for i in range(n)]
        rss = sum(r*r for r in resid)
        ybar, _ = mean_std(y)
        tss = sum((yi - ybar)**2 for yi in y)
        r2 = 1.0 - (rss / tss if tss > 0 else float('nan'))
        p = 3  # intercept + 2 predictors
        df = max(1, n - p)
        s2 = rss / df
        # Var(b) = s2 * inv(X'X)
        if invXtX is None:
            se_x = float('nan')
        else:
            var_b1 = s2 * invXtX[1][1]
            se_x = math.sqrt(var_b1) if var_b1 >= 0 else float('nan')
        t_x = coef[1] / se_x if se_x and se_x != 0 and not math.isnan(se_x) else float('nan')
        # Approximate p via normal
        p_x = 2.0 * (1.0 - norm_cdf(abs(t_x))) if t_x == t_x else float('nan')
        adj_r2 = 1.0 - (1 - r2) * (n - 1) / (n - p) if n > p else float('nan')

    # Standardized beta for x
    _, sd_y = mean_std(y)
    _, sd_x = mean_std(x)
    beta_std = coef[1] * (sd_x / sd_y) if sd_y and sd_y != 0 and sd_x and sd_x != 0 else float('nan')

    return {
        'n': n,
        'coef': float(coef[1]) if coef[1] == coef[1] else float('nan'),
        'se': float(se_x) if se_x == se_x else float('nan'),
        't': float(t_x) if t_x == t_x else float('nan'),
        'p': float(p_x) if p_x == p_x else float('nan'),
        'beta_std': float(beta_std) if beta_std == beta_std else float('nan'),
        'r2': float(r2) if r2 == r2 else float('nan'),
        'adj_r2': float(adj_r2) if adj_r2 == adj_r2 else float('nan')
    }

# Convenience to get a column by name as float series

def get_float_column(data: Dict[str, List[Optional[str]]], name: str) -> Optional[List[Optional[float]]]:
    if name in data:
        return to_float_series(data[name])
    return None
