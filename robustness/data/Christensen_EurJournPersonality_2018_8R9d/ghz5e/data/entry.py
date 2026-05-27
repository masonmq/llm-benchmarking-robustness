#!/usr/bin/env python3
"""
Entry point for GHZ5E semantic network analysis (Python).
Implements Task1 and Task2 as specified in analysis_info.json.
- Loads verbal fluency responses from /app/data/FINAL fluency.csv
- Merges openness scores from /app/data/FINAL open.csv (uses LATENT if available, else AVERAGE, else no_int)
- Splits participants into Low vs High openness halves
- Constructs binary response-by-node matrices (nodes are cleaned unique animal strings)
- Removes nodes endorsed by fewer than 2 participants in EACH group and equates nodes across groups
- Builds cosine-similarity graphs (KNN with k=8 by default)
- Computes network measures: ASPL (using distance=1-weight), mean weighted clustering coefficient, and modularity Q (Louvain)
- Runs partial node-retention bootstraps for specified proportions
Outputs JSON to stdout and writes /app/data/execution_result.json for the orchestrator to consume.
"""

import os
import sys
import json
import argparse
import re
# Lightweight dependency bootstrap in case image lacks packages
import importlib, subprocess
REQUIRED = {
    "numpy": "numpy==1.24.4",
    "pandas": "pandas==2.0.3",
    "sklearn": "scikit-learn==1.3.2",
    "networkx": "networkx==3.2.1",
    "community": "python-louvain==0.16",
}
_missing = []
for _mod, _pkg in REQUIRED.items():
    try:
        importlib.import_module(_mod)
    except Exception:
        _missing.append(_pkg)
if _missing:
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user"] + _missing, check=False)
        # ensure user site on path
        try:
            import site as _site
            _us = _site.getusersitepackages()
            if _us and _us not in sys.path:
                sys.path.append(_us)
        except Exception:
            pass
    except Exception:
        pass
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx

try:
    import community as community_louvain  # python-louvain
    HAS_LOUVAIN = True
except Exception:
    HAS_LOUVAIN = False

# ---------------------- Data loading and merging ----------------------

def load_fluency(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fluency data file not found: {path}")
    df = pd.read_csv(path)
    return df


def load_openness(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Openness data file not found: {path}")
    df = pd.read_csv(path)
    return df


def pick_openness_column(df_open: pd.DataFrame) -> str:
    # Preference order
    candidates = ["LATENT", "LATENT2", "AVERAGE", "no_int", "o_neo", "o_bfas", "o_ffi"]
    for c in candidates:
        if c in df_open.columns and pd.api.types.is_numeric_dtype(df_open[c]):
            return c
    # Fallback: any numeric column with 'open' in name
    num_cols = [c for c in df_open.columns if pd.api.types.is_numeric_dtype(df_open[c])]
    openish = [c for c in num_cols if "open" in str(c).lower() or "o_" == str(c).lower()[:2]]
    if openish:
        return openish[0]
    # Final fallback: highest-variance numeric col
    if num_cols:
        var_series = pd.Series({c: df_open[c].var(skipna=True) for c in num_cols})
        return var_series.idxmax()
    raise KeyError("No suitable openness column found in openness dataset.")


def merge_openness(df_flu: pd.DataFrame, df_open: pd.DataFrame, id_col: str = "id") -> Tuple[pd.DataFrame, str]:
    if id_col not in df_flu.columns:
        raise KeyError(f"id column '{id_col}' not found in fluency data")
    # try infer right id key
    right_key = "id" if "id" in df_open.columns else None
    if right_key is None:
        cand_r = [c for c in df_open.columns if "id" in str(c).lower()]
        if cand_r:
            right_key = cand_r[0]
    if right_key is None:
        raise KeyError("Could not infer id key in openness data for merging.")
    open_col = pick_openness_column(df_open)
    merged = pd.merge(df_flu, df_open[[right_key, open_col]], left_on=id_col, right_on=right_key, how="left")
    if merged[open_col].isna().all():
        raise ValueError("All openness scores are missing after merge; check id alignment.")
    return merged, open_col

# ---------------------- Text processing ----------------------

def clean_token(x: str) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    # Replace non-letters with space, collapse spaces
    s = re.sub(r"[^a-z]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_vocab(df: pd.DataFrame, resp_cols: List[str]) -> List[str]:
    vocab = set()
    for c in resp_cols:
        if c not in df.columns:
            continue
        col = df[c].astype(str)
        for val in col:
            tok = clean_token(val)
            if tok:
                vocab.add(tok)
    vocab = sorted(vocab)
    return vocab


def strings_to_binary(df: pd.DataFrame, resp_cols: List[str], vocab: List[str]) -> np.ndarray:
    idx = {w: i for i, w in enumerate(vocab)}
    n = df.shape[0]
    p = len(vocab)
    M = np.zeros((n, p), dtype=np.float32)
    for r, (_, row) in enumerate(df.iterrows()):
        seen = set()
        for c in resp_cols:
            if c not in df.columns:
                continue
            tok = clean_token(row[c])
            if tok and tok in idx and tok not in seen:
                M[r, idx[tok]] = 1.0
                seen.add(tok)
    return M

# ---------------------- Grouping and node filtering ----------------------

def split_low_high(df: pd.DataFrame, open_col: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    sub = df[[open_col]].copy()
    sub = sub.assign(__row=np.arange(sub.shape[0]))
    sub = sub.dropna()
    # sort by openness
    sub = sub.sort_values(open_col, ascending=True)
    n = sub.shape[0]
    half = n // 2
    low_idx = sub.iloc[:half]["__row"].values
    high_idx = sub.iloc[-half:]["__row"].values
    low_df = df.iloc[low_idx]
    high_df = df.iloc[high_idx]
    return low_df, high_df


def filter_nodes_common(low_bin: np.ndarray, high_bin: np.ndarray, min_count: int = 2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    # keep nodes with at least min_count endorsements in EACH group
    low_counts = low_bin.sum(axis=0)
    high_counts = high_bin.sum(axis=0)
    keep = (low_counts >= min_count) & (high_counts >= min_count)
    if keep.sum() < 3:
        # fallback: relax to union
        keep = (low_counts + high_counts) >= min_count
    return low_bin[:, keep], high_bin[:, keep], keep

# ---------------------- Graph construction and measures ----------------------

def cosine_from_binary(M: np.ndarray) -> np.ndarray:
    # node vectors are columns (participants x nodes) -> transpose to nodes x participants
    X = M.T
    S = cosine_similarity(X)
    # zero diagonal
    np.fill_diagonal(S, 0.0)
    # clip numerical noise
    S = np.clip(S, 0.0, 1.0)
    return S


def build_graph_knn(S: np.ndarray, k: int = 8) -> nx.Graph:
    n = S.shape[0]
    G = nx.Graph()
    G.add_nodes_from(range(n))
    for i in range(n):
        # get top-k neighbors by similarity
        sim = S[i].copy()
        idx = np.argsort(sim)[::-1]  # descending
        added = 0
        for j in idx:
            if i == j:
                continue
            w = sim[j]
            if w <= 0:
                continue
            G.add_edge(i, j, weight=float(w), distance=float(1.0 - w))
            added += 1
            if added >= k:
                break
    # make undirected symmetric by ensuring edges in both directions exist already handled by Graph
    return G


def build_graph_complete(S: np.ndarray) -> nx.Graph:
    n = S.shape[0]
    G = nx.Graph()
    for i in range(n):
        G.add_node(i)
    for i in range(n):
        for j in range(i + 1, n):
            w = float(S[i, j])
            if w > 0:
                G.add_edge(i, j, weight=w, distance=float(1.0 - w))
    return G


def compute_measures(G: nx.Graph) -> Dict[str, float]:
    out = {"ASPL": None, "CC": None, "Q": None}
    if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
        return out
    # Work on largest connected component for path length
    if not nx.is_connected(G):
        components = list(nx.connected_components(G))
        largest = max(components, key=len)
        H = G.subgraph(largest).copy()
    else:
        H = G
    try:
        aspl = nx.average_shortest_path_length(H, weight="distance")
    except Exception:
        aspl = None
    try:
        cc_vals = nx.clustering(G, weight="weight")  # dictionary per node
        if len(cc_vals) > 0:
            cc = float(np.mean(list(cc_vals.values())))
        else:
            cc = None
    except Exception:
        cc = None
    q = None
    if HAS_LOUVAIN:
        try:
            part = community_louvain.best_partition(G, weight="weight")
            q = community_louvain.modularity(part, G, weight="weight")
        except Exception:
            q = None
    out["ASPL"] = None if aspl is None else float(aspl)
    out["CC"] = None if cc is None else float(cc)
    out["Q"] = None if q is None else float(q)
    return out

# ---------------------- Bootstrap ----------------------

def bootstrap_node_retention(low_bin: np.ndarray, high_bin: np.ndarray, prop: float, iters: int, k: int, method: str = "knn") -> Dict:
    rng = np.random.default_rng(12345)
    n_nodes = low_bin.shape[1]
    m = max(2, int(round(prop * n_nodes)))
    diffs_aspl = []
    diffs_cc = []
    diffs_q = []
    for _ in range(iters):
        cols = rng.choice(n_nodes, size=m, replace=False)
        lb = low_bin[:, cols]
        hb = high_bin[:, cols]
        S_low = cosine_from_binary(lb)
        S_high = cosine_from_binary(hb)
        if method == "knn":
            G_low = build_graph_knn(S_low, k=k)
            G_high = build_graph_knn(S_high, k=k)
        else:
            G_low = build_graph_complete(S_low)
            G_high = build_graph_complete(S_high)
        m_low = compute_measures(G_low)
        m_high = compute_measures(G_high)
        # differences High - Low
        def diff(a, b):
            if a is None or b is None:
                return None
            return float(a) - float(b)
        diffs_aspl.append(diff(m_high["ASPL"], m_low["ASPL"]))
        diffs_cc.append(diff(m_high["CC"], m_low["CC"]))
        diffs_q.append(diff(m_high["Q"], m_low["Q"]))
    def summarize(arr: List[float]) -> Dict[str, float]:
        vals = [x for x in arr if x is not None and not np.isnan(x)]
        n = len(vals)
        if n == 0:
            return {"mean": None, "sd": None, "t_like": None}
        mu = float(np.mean(vals))
        sd = float(np.std(vals, ddof=1)) if n > 1 else 0.0
        t_like = None
        if sd > 0 and n > 1:
            t_like = float(mu / (sd / np.sqrt(n)))
        return {"mean": mu, "sd": sd, "t_like": t_like, "n": n}
    return {
        "prop": float(prop),
        "ASPL": summarize(diffs_aspl),
        "CC": summarize(diffs_cc),
        "Q": summarize(diffs_q),
    }

# ---------------------- Orchestration ----------------------

def run_analysis(data_file: str, open_file: str, id_col: str = "id", response_prefix: str = "vf_an_", iters: int = 200, k: int = 8, method: str = "knn", props: List[float] = None) -> Dict:
    if props is None:
        props = [0.5, 0.6, 0.7, 0.8, 0.9]
    flu = load_fluency(data_file)
    opn = load_openness(open_file)
    merged, open_col = merge_openness(flu, opn, id_col=id_col)
    # response columns
    resp_cols = [c for c in merged.columns if c.startswith(response_prefix)]
    if len(resp_cols) == 0:
        raise ValueError(f"No response columns found with prefix '{response_prefix}' in {data_file}")
    # split groups
    low_df, high_df = split_low_high(merged, open_col)
    # vocabulary and binary matrices on full merged for consistent vocab
    vocab = build_vocab(merged, resp_cols)
    low_bin = strings_to_binary(low_df, resp_cols, vocab)
    high_bin = strings_to_binary(high_df, resp_cols, vocab)
    # filter and equate nodes
    low_eq, high_eq, keep = filter_nodes_common(low_bin, high_bin, min_count=2)
    # similarity and graphs on full nodes
    S_low = cosine_from_binary(low_eq)
    S_high = cosine_from_binary(high_eq)
    if method == "knn":
        G_low = build_graph_knn(S_low, k=k)
        G_high = build_graph_knn(S_high, k=k)
    else:
        G_low = build_graph_complete(S_low)
        G_high = build_graph_complete(S_high)
    m_low = compute_measures(G_low)
    m_high = compute_measures(G_high)
    # bootstraps
    boots = []
    for p in props:
        boots.append(bootstrap_node_retention(low_eq, high_eq, prop=p, iters=iters, k=k, method=method))
    return {
        "group_measures": {"Low": m_low, "High": m_high},
        "bootstrap": boots,
        "diagnostics": {
            "n_low": int(low_df.shape[0]),
            "n_high": int(high_df.shape[0]),
            "n_nodes_common": int(low_eq.shape[1]),
            "openness_col": open_col,
        }
    }


def run_tasks(task: str) -> Dict:
    data_file = "/app/data/FINAL fluency.csv"
    open_file = "/app/data/FINAL open.csv"
    if task == "Task1":
        props = [0.5, 0.6, 0.7, 0.8, 0.9]
    else:
        props = [0.9]
    res = run_analysis(data_file=data_file, open_file=open_file, id_col="id", response_prefix="vf_an_", iters=200, k=8, method="knn", props=props)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["Task1", "Task2", "both"], default="both")
    args = ap.parse_args()
    outputs: Dict[str, Dict] = {}
    tasks = ["Task1", "Task2"] if args.task == "both" else [args.task]
    for t in tasks:
        try:
            outputs[t] = run_tasks(t)
        except Exception as e:
            outputs[t] = {"status": "error", "message": str(e)}
    # write execution result file for orchestrator
    out_path = "/app/data/execution_result.json"
    try:
        with open(out_path, "w") as f:
            json.dump(outputs, f)
    except Exception:
        pass
    print(json.dumps(outputs))


if __name__ == "__main__":
    main()
