import json
import math
import os
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
import sys, site, importlib
# Ensure system site-packages is on path (for globally installed libs inside container)
sys.path.insert(0, f"/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
try:
    import networkx as nx
except ModuleNotFoundError:
    # Try adding site/user site paths explicitly then import
    try:
        for p in (site.getsitepackages() + [site.getusersitepackages()]):
            if p not in sys.path:
                sys.path.append(p)
        nx = importlib.import_module("networkx")
    except Exception as e:
        raise ImportError(f"Failed to import networkx after adjusting sys.path: {e}")
from scipy import stats

# Robust import for Louvain
try:
    import community as community_louvain  # pip package: python-louvain
except Exception:
    from community import community_louvain

DATA_PATH = "/app/data/FINAL demo open fluency.csv"
OUT_PATH = "/app/data/task1_results.json"

np.seterr(all="ignore")


def clean_word(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        # Treat negative or sentinel values as missing
        if x == -1:
            return None
        x = str(x)
    s = str(x).strip().lower()
    if s in ("", "nan", "na", "-1", "none", "missing"):
        return None
    # Basic cleanup: collapse spaces
    s = " ".join(s.split())
    return s if s else None


def get_vf_columns(df):
    cols = []
    for c in df.columns:
        cl = c.lower()
        if cl.startswith("vf_an_"):
            cols.append(c)
    return cols


def build_global_cooccurrence(df, vf_cols):
    pair_counts = Counter()
    n_rows_used = 0
    for _, row in df[vf_cols].iterrows():
        words = [clean_word(row[c]) for c in vf_cols]
        words = [w for w in words if w]
        if len(words) < 2:
            continue
        n_rows_used += 1
        uniq = sorted(set(words))
        for a, b in combinations(uniq, 2):
            pair_counts[(a, b)] += 1
    n_rows_used = max(n_rows_used, 1)
    return pair_counts, n_rows_used


def binary_entropy(p):
    if p <= 0.0 or p >= 1.0:
        return 0.0
    # natural log base; scale does not affect ordering, only magnitude
    return -(p * math.log(p) + (1 - p) * math.log(1 - p))


def participant_graphs(words, pair_counts, denom_rows):
    # Build complete graphs over participant word set
    Gd = nx.Graph()
    Gs = nx.Graph()
    for w in words:
        Gd.add_node(w)
        Gs.add_node(w)
    if len(words) < 2:
        return Gd, Gs
    for a, b in combinations(sorted(words), 2):
        cnt = pair_counts.get((a, b), 0)
        p = cnt / float(denom_rows)
        H = binary_entropy(p)
        dist = H if H > 0 else 0.99  # replace zero-entropy edges with 0.99 (long distance)
        strength = 1.0 / dist if dist > 0 else 0.0
        Gd.add_edge(a, b, weight=dist)
        Gs.add_edge(a, b, weight=strength)
    return Gd, Gs


def compute_mst_cpl(Gd):
    # Minimum spanning tree over distance graph
    if Gd.number_of_nodes() < 2:
        return np.nan
    try:
        T = nx.minimum_spanning_tree(Gd, weight="weight")
    except Exception:
        return np.nan
    # Shortest path lengths on MST using distance weights
    dists = []
    for source in T.nodes:
        lengths = nx.single_source_dijkstra_path_length(T, source, weight="weight")
        for target, L in lengths.items():
            if target <= source:
                continue
            dists.append(L)
    if not dists:
        return np.nan
    return float(np.median(dists))


def compute_betweenness_mst(Gd):
    if Gd.number_of_nodes() < 2:
        return (np.nan, np.nan)
    try:
        T = nx.minimum_spanning_tree(Gd, weight="weight")
        bc = nx.betweenness_centrality(T, weight="weight", normalized=True)
        vals = list(bc.values())
        if not vals:
            return (np.nan, np.nan)
        return (float(np.mean(vals)), float(np.max(vals)))
    except Exception:
        return (np.nan, np.nan)


def louvain_participation_mean(Gs):
    if Gs.number_of_nodes() < 2 or Gs.number_of_edges() == 0:
        return np.nan
    try:
        # Robust import usage
        partition = community_louvain.best_partition(Gs, weight="weight", random_state=42)
        # Compute participation coefficient per node
        # P_i = 1 - sum_c (k_i_c / k_i)^2
        part = {}
        for i in Gs.nodes():
            k_i = 0.0
            comm_strength = defaultdict(float)
            for j, data in Gs[i].items():
                w = data.get("weight", 1.0)
                k_i += w
                cj = partition.get(j, -1)
                comm_strength[cj] += w
            if k_i <= 0:
                part[i] = 0.0
            else:
                s = 0.0
                for c, kic in comm_strength.items():
                    s += (kic / k_i) ** 2
                part[i] = 1.0 - s
        vals = np.array(list(part.values()), dtype=float)
        if vals.size == 0:
            return np.nan
        # Mode approximation by rounding to 2 decimals
        rounded = np.round(vals, 2)
        if rounded.size == 0:
            return float(np.mean(vals))
        uniq, counts = np.unique(rounded, return_counts=True)
        mode_val = float(uniq[np.argmax(counts)])
        sel = vals[vals > mode_val]
        if sel.size >= 1:
            return float(np.mean(sel))
        else:
            return float(np.mean(vals))
    except Exception:
        return np.nan


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df = pd.read_csv(DATA_PATH)

    # Prepare columns
    vf_cols = get_vf_columns(df)
    if len(vf_cols) == 0:
        raise RuntimeError("No verbal fluency columns starting with 'vf_an_' found.")

    # Global co-occurrence across dataset
    pair_counts, denom_rows = build_global_cooccurrence(df, vf_cols)

    # Compute per-participant metrics
    metrics = []
    for idx, row in df.iterrows():
        words = [clean_word(row[c]) for c in vf_cols]
        words = [w for w in words if w]
        words = sorted(set(words))
        Gd, Gs = participant_graphs(words, pair_counts, denom_rows)
        cpl = compute_mst_cpl(Gd)
        betw_mean, betw_max = compute_betweenness_mst(Gd)
        part_mean = louvain_participation_mean(Gs)
        metrics.append({
            "cpl": cpl,
            "betw_mean": betw_mean,
            "betw_max": betw_max,
            "part_mean": part_mean,
        })

    met = pd.DataFrame(metrics)

    # Openness measures
    for col in ["o_ffi", "oi_bfas", "o_bfas", "i_bfas"]:
        if col not in df.columns:
            df[col] = np.nan
    df["openness_average"] = df[["o_ffi", "oi_bfas", "o_bfas", "i_bfas"]].astype(float).mean(axis=1, skipna=True)

    out = pd.concat([df, met], axis=1)

    # Filter: cpl < 10
    filt = out["cpl"].astype(float) < 10
    ana = out.loc[filt & out["part_mean"].notna() & out["openness_average"].notna(), ["openness_average", "part_mean"]].copy()

    # Spearman correlation
    if len(ana) >= 3:
        rho, pval = stats.spearmanr(ana["openness_average"], ana["part_mean"], nan_policy="omit")
        n_corr = int(np.sum(ana[["openness_average", "part_mean"]].notna().all(axis=1)))
    else:
        rho, pval, n_corr = (np.nan, np.nan, int(len(ana)))

    # Median split and Welch t-test
    tstat = np.nan
    tpval = np.nan
    n_low = n_high = 0
    if len(ana) >= 3:
        med = float(ana["openness_average"].median())
        low = ana.loc[ana["openness_average"] <= med, "part_mean"].astype(float).values
        high = ana.loc[ana["openness_average"] > med, "part_mean"].astype(float).values
        # Ensure both groups have at least 2 obs
        if len(low) >= 2 and len(high) >= 2:
            t_res = stats.ttest_ind(low, high, equal_var=False, nan_policy="omit")
            tstat = float(t_res.statistic)
            tpval = float(t_res.pvalue)
            n_low = int(np.sum(~np.isnan(low)))
            n_high = int(np.sum(~np.isnan(high)))

    results = {
        "spearman": {
            "rho": None if pd.isna(rho) else float(rho),
            "p_value": None if pd.isna(pval) else float(pval),
            "n": int(n_corr),
            "direction": "positive" if (not pd.isna(rho) and rho > 0) else ("negative" if (not pd.isna(rho) and rho < 0) else "zero")
        },
        "t_test_median_split": {
            "t_value": None if pd.isna(tstat) else float(tstat),
            "p_value": None if pd.isna(tpval) else float(tpval),
            "n_low": int(n_low),
            "n_high": int(n_high)
        },
        "notes": {
            "filter": "cpl < 10",
            "data_rows": int(len(df)),
            "vf_columns": len(vf_cols),
            "denominator_rows_for_cooccurrence": int(denom_rows)
        }
    }

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
