import json
import math
import os
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
import sys, site, importlib
sys.path.insert(0, f"/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
try:
    import networkx as nx
except ModuleNotFoundError:
    try:
        for p in (site.getsitepackages() + [site.getusersitepackages()]):
            if p not in sys.path:
                sys.path.append(p)
        nx = importlib.import_module("networkx")
    except Exception as e:
        raise ImportError(f"Failed to import networkx after adjusting sys.path: {e}")
from scipy import stats

try:
    import community as community_louvain
except Exception:
    from community import community_louvain

DATA_PATH = "/app/data/FINAL demo open fluency.csv"
OUT_PATH = "/app/data/task2_results.json"

np.seterr(all="ignore")


def clean_word(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        if x == -1:
            return None
        x = str(x)
    s = str(x).strip().lower()
    if s in ("", "nan", "na", "-1", "none", "missing"):
        return None
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
    return -(p * math.log(p) + (1 - p) * math.log(1 - p))


def participant_graphs(words, pair_counts, denom_rows):
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
        dist = H if H > 0 else 0.99
        strength = 1.0 / dist if dist > 0 else 0.0
        Gd.add_edge(a, b, weight=dist)
        Gs.add_edge(a, b, weight=strength)
    return Gd, Gs


def louvain_participation_mean(Gs):
    if Gs.number_of_nodes() < 2 or Gs.number_of_edges() == 0:
        return np.nan
    try:
        partition = community_louvain.best_partition(Gs, weight="weight", random_state=42)
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


def top_k_by_eigenvector(Gs, frac_remove=0.10):
    if Gs.number_of_nodes() == 0:
        return []
    try:
        ev = nx.eigenvector_centrality_numpy(Gs, weight="weight")
    except Exception:
        # Fallback to uniform if eigenvector fails
        ev = {n: 1.0 for n in Gs.nodes()}
    k = max(1, int(math.floor(frac_remove * Gs.number_of_nodes())))
    ranked = sorted(ev.items(), key=lambda x: x[1], reverse=True)
    remove_nodes = [n for n, _ in ranked[:k]]
    return remove_nodes


def compute_mst_cpl(Gd):
    if Gd.number_of_nodes() < 2:
        return np.nan
    try:
        T = nx.minimum_spanning_tree(Gd, weight="weight")
    except Exception:
        return np.nan
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


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df = pd.read_csv(DATA_PATH)

    vf_cols = get_vf_columns(df)
    if len(vf_cols) == 0:
        raise RuntimeError("No verbal fluency columns starting with 'vf_an_' found.")

    pair_counts, denom_rows = build_global_cooccurrence(df, vf_cols)

    rows = []
    for idx, row in df.iterrows():
        words = [clean_word(row[c]) for c in vf_cols]
        words = [w for w in words if w]
        words = sorted(set(words))
        # Build graphs
        Gd, Gs = participant_graphs(words, pair_counts, denom_rows)
        # Remove top 10% nodes by eigenvector centrality
        remove_nodes = top_k_by_eigenvector(Gs, frac_remove=0.10)
        Gd_p = Gd.copy()
        Gs_p = Gs.copy()
        Gd_p.remove_nodes_from(remove_nodes)
        Gs_p.remove_nodes_from(remove_nodes)
        # Compute metrics
        cpl = compute_mst_cpl(Gd_p)
        part_mean = louvain_participation_mean(Gs_p)
        rows.append({
            "cpl": cpl,
            "part_mean": part_mean
        })

    met = pd.DataFrame(rows)

    # Openness and gender
    for col in ["o_ffi", "oi_bfas", "o_bfas", "i_bfas"]:
        if col not in df.columns:
            df[col] = np.nan
    df["openness_average"] = df[["o_ffi", "oi_bfas", "o_bfas", "i_bfas"]].astype(float).mean(axis=1, skipna=True)

    if "d_gender" not in df.columns:
        df["d_gender"] = np.nan

    out = pd.concat([df, met], axis=1)

    # Filters
    mask_valid = (out["cpl"].astype(float) < 10) & (out["part_mean"].notna()) & (out["d_gender"].astype(str) != "-1")
    dat = out.loc[mask_valid, ["part_mean", "d_gender"]].copy()
    dat["d_gender"] = dat["d_gender"].astype(str)

    groups = {g: vals["part_mean"].astype(float).values for g, vals in dat.groupby("d_gender")}

    tstat = np.nan
    pval = np.nan
    ns = {g: int(np.sum(~np.isnan(v))) for g, v in groups.items()}

    if len(groups) >= 2:
        # Choose the two largest groups for Welch t-test
        top2 = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:2]
        a = top2[0][1]
        b = top2[1][1]
        if len(a) >= 2 and len(b) >= 2:
            res = stats.ttest_ind(a, b, equal_var=False, nan_policy="omit")
            tstat = float(res.statistic)
            pval = float(res.pvalue)

    results = {
        "welch_t_by_gender": {
            "t_value": None if pd.isna(tstat) else float(tstat),
            "p_value": None if pd.isna(pval) else float(pval),
            "group_sizes": ns,
            "groups_compared": sorted(list(groups.keys()))[:2]
        },
        "notes": {
            "filter": "cpl < 10 and d_gender != '-1'",
            "data_rows": int(len(df)),
            "vf_columns": len(vf_cols),
            "denominator_rows_for_cooccurrence": int(denom_rows),
            "node_retention": "90% (removed top 10% by eigenvector centrality)"
        }
    }

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
