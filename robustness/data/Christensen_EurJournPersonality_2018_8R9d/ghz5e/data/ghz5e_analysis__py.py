#!/usr/bin/env python3
"""
GHZ5E semantic network analysis (Python translation).
Runs Task1 (50-90% partial node bootstraps) and Task2 (90% only) comparing High vs Low openness groups.
If invoked without CLI args, it will run both tasks using defaults and print a JSON object with both results.
"""

import sys
import os
import json
import argparse
import subprocess
import importlib
from typing import Dict, List, Tuple

# -------- Dependency bootstrap (for runtimes where pip packages are missing) --------
REQUIRED = {
    "numpy": "numpy==1.24.4",
    "pandas": "pandas==2.0.3",
    "sklearn": "scikit-learn==1.3.2",
    "networkx": "networkx==3.2.1",
    "community": "python-louvain==0.16",
    "pyreadstat": "pyreadstat==1.2.6",
}


def ensure_deps():
    missing = []
    for mod, pkg in REQUIRED.items():
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    if missing:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--user"] + missing, check=False)
            # add usersite to sys.path
            try:
                import site as _site
                _user_site = _site.getusersitepackages()
                if _user_site and _user_site not in sys.path:
                    sys.path.append(_user_site)
            except Exception:
                pass
        except Exception:
            pass


ensure_deps()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity  # noqa: E402
import networkx as nx  # noqa: E402
try:  # noqa: E402
    import community as community_louvain  # python-louvain package
    HAS_LOUVAIN = True
except Exception:  # noqa: E402
    HAS_LOUVAIN = False


# -------- Data helpers --------

def read_dataset(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")
    if path.lower().endswith('.csv'):
        return pd.read_csv(path)
    if path.lower().endswith('.sav'):
        import pyreadstat  # ensured above
        df, _ = pyreadstat.read_sav(path)
        return df
    return pd.read_csv(path)


def split_groups(df: pd.DataFrame, openness_col: str, n_low: int = None, n_high: int = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if openness_col not in df.columns:if openness_col not in df.columns:
        # try regex or default heuristic and known aliases
        cols = list(df.columns)
        # prioritize known alias 'no_int' from original R code
        if 'no_int' in cols and pd.api.types.is_numeric_dtype(df['no_int']):
            openness_col = 'no_int'
            return df, openness_col
        candidates = []
        if openness_regex:
            import re
            pat = re.compile(openness_regex, flags=re.IGNORECASE)
            candidates = [c for c in cols if pat.search(c)]
        else:
            # broader heuristics
            keys = ['open', 'openness', 'latent', 'neo_o', 'neo-openness', 'big5_o', 'o_score']
            for c in cols:
                lc = str(c).lower()
                if any(k in lc for k in keys):
                    candidates.append(c)
        cand_num = [c for c in candidates if pd.api.types.is_numeric_dtype(df[c])]
        if len(cand_num) > 0:
            var_series = pd.Series({c: df[c].var(skipna=True) for c in cand_num})
            openness_col = var_series.idxmax()
        else:
            # final fallback: if right/merged has a single numeric column not in left, pick the highest variance numeric
            num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
            if len(num_cols) > 0:
                var_series = pd.Series({c: df[c].var(skipna=True) for c in num_cols})
                openness_col = var_series.idxmax()
            else:
                raise KeyError(f"Could not locate openness column '{openness_col}' and no suitable candidates found.")
    return df, openness_colreturn df, openness_col
    if merge_file:
        right = read_dataset(merge_file)
        # determine keys
        left_key = None
        right_key = None
        if merge_on:
            if ':' in merge_on:
                left_key, right_key = merge_on.split(':', 1)
            else:
                left_key = right_key = merge_on
        if left_key is None or right_key is None:
            # try 'id' in both, else any right col containing 'id'
            if 'id' in df.columns:
                rk = None
                if 'id' in right.columns:
                    rk = 'id'
                else:
                    cand_r = [c for c in right.columns if 'id' in str(c).lower()]
                    if cand_r:
                        rk = cand_r[0]
                if rk is not None:
                    left_key = 'id'
                    right_key = rk
        if left_key is None or right_key is None:
            raise KeyError("merge_on not specified and could not infer a common key between left and right datasets.")
        df = pd.merge(df, right, left_on=left_key, right_on=right_key, how='left')
    if openness_col not in df.columns:
        # try regex or default heuristic
        cols = list(df.columns)
        candidates = []
        if openness_regex:
            import re
            pat = re.compile(openness_regex, flags=re.IGNORECASE)
            candidates = [c for c in cols if pat.search(c)]
        else:
            candidates = [c for c in cols if 'open' in str(c).lower()]
        cand_num = [c for c in candidates if pd.api.types.is_numeric_dtype(df[c])]
        if len(cand_num) > 0:
            var_series = pd.Series({c: df[c].var(skipna=True) for c in cand_num})
            openness_col = var_series.idxmax()
        else:
            raise KeyError(f"Could not locate openness column '{openness_col}' and no suitable candidates found.")
    return df, openness_col


# -------- Orchestration --------

def run_task(df: pd.DataFrame, id_col: str, openness_col: str, response_prefix: str, iters: int, knn_k: int, bootstrap_props: List[float], graph_method: str = 'knn', merge_file: str = None, merge_on: str = None, openness_regex: str = None) -> Dict:
    df, openness_col = merge_if_needed(df, openness_col=openness_col, merge_file=merge_file, merge_on=merge_on, openness_regex=openness_regex)
    all_cols = list(df.columns)
    resp_cols = [c for c in all_cols if response_prefix and c.startswith(response_prefix)]
    if len(resp_cols) == 0:
        raise ValueError(f"No response columns found with prefix '{response_prefix}'.")
    low_df, high_df = split_groups(df, openness_col=openness_col)
    vocab = build_vocab_from_strings(df, resp_cols)
    low_bin = strings_to_binary(low_df, resp_cols, vocab)
    high_bin = strings_to_binary(high_df, resp_cols, vocab)
    fin_low = finalize_matrix(low_bin)
    fin_high = finalize_matrix(high_bin)
    eq_low, eq_high = equate_matrices(fin_low, fin_high)
    S_low = cosine_from_binary(eq_low)
    S_high = cosine_from_binary(eq_high)
    G_low = build_graph_from_similarity(S_low, method=graph_method, k=knn_k)
    G_high = build_graph_from_similarity(S_high, method=graph_method, k=knn_k)
    low_meas = compute_measures(G_low)
    high_meas = compute_measures(G_high)
    boot_summaries = []
    for p in bootstrap_props:
        res = partboot(eq_low, eq_high, prop=p, iters=iters, knn_k=knn_k, graph_method=graph_method)
        boot_summaries.append(res)
    return {
        "group_measures": {"Low": low_meas, "High": high_meas},
        "bootstrap": boot_summaries,
        "diagnostics": {
            "n_low": int(low_df.shape[0]),
            "n_high": int(high_df.shape[0]),
            "n_nodes_common": int(eq_low.shape[1]),
            "openness_col": openness_col
        }
    }


def main_execute(task: str, data_file: str, id_col: str, openness_col: str, response_prefix: str, iters: int, knn_k: int, graph_method: str, merge_file: str = None, merge_on: str = None, openness_regex: str = None, bootstrap_prop: float = None) -> Dict:
    df = read_dataset(data_file)
    if task == 'Task1':
        props = [0.5, 0.6, 0.7, 0.8, 0.9]
    else:
        p = 0.9 if bootstrap_prop is None else bootstrap_prop
        props = [float(p)]
    results = run_task(
        df=df,
        id_col=id_col,
        openness_col=openness_col,
        response_prefix=response_prefix,
        iters=iters,
        knn_k=knn_k,
        bootstrap_props=props,
        graph_method=graph_method,
        merge_file=merge_file,
        merge_on=merge_on,
        openness_regex=openness_regex
    )
    return {"status": "ok", "task": task, "results": results}


def run_with_defaults() -> Dict:
    base_file = "/app/data/FINAL fluency.csv"
    merge_file = "/app/data/All samples merged and totaled_shared.sav"
    out = {}
    try:
        out["Task1"] = main_execute(task='Task1', data_file=base_file, id_col='id', openness_col='latent', response_prefix='vf_an_', iters=200, knn_k=8, graph_method='knn', merge_file=merge_file, merge_on='id:id', openness_regex='open')
    except Exception as e:
        out["Task1"] = {"status": "error", "message": str(e)}
    try:
        out["Task2"] = main_execute(task='Task2', data_file=base_file, id_col='id', openness_col='latent', response_prefix='vf_an_', iters=200, knn_k=8, graph_method='knn', merge_file=merge_file, merge_on='id:id', openness_regex='open', bootstrap_prop=0.9)
    except Exception as e:
        out["Task2"] = {"status": "error", "message": str(e)}
    return out


def cli_main():
    if len(sys.argv) == 1:
        print(json.dumps(run_with_defaults()))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', type=str, required=True, choices=['Task1', 'Task2'])
    ap.add_argument('--data_file', type=str, required=True)
    ap.add_argument('--id_col', type=str, default=None)
    ap.add_argument('--openness_col', type=str, required=True)
    ap.add_argument('--response_prefix', type=str, default=None)
    ap.add_argument('--iters', type=int, default=200)
    ap.add_argument('--knn_k', type=int, default=8)
    ap.add_argument('--graph_method', type=str, default='knn', choices=['knn', 'complete'])
    ap.add_argument('--bootstrap_prop', type=float, default=None)
    ap.add_argument('--merge_file', type=str, default=None)
    ap.add_argument('--merge_on', type=str, default=None)
    ap.add_argument('--openness_regex', type=str, default=None)
    args = ap.parse_args()
    try:
        res = main_execute(
            task=args.task,
            data_file=args.data_file,
            id_col=args.id_col,
            openness_col=args.openness_col,
            response_prefix=args.response_prefix,
            iters=args.iters,
            knn_k=args.knn_k,
            graph_method=args.graph_method,
            merge_file=args.merge_file,
            merge_on=args.merge_on,
            openness_regex=args.openness_regex,
            bootstrap_prop=args.bootstrap_prop
        )
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    cli_main()
