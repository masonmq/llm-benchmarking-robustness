import os
import math
import json
import sys
from typing import Tuple, List, Dict

# Runtime dependency bootstrap to avoid missing modules in some environments
try:
    import numpy as np
    import pandas as pd
    import networkx as nx
    from scipy import stats
    import statsmodels.api as sm  # may be used in approach2
except Exception:
    import subprocess, site, importlib
    pkgs = [
        "numpy==1.26.4",
        "pandas==2.0.3",
        "scipy==1.11.4",
        "networkx==3.2.1",
        "statsmodels==0.14.1"
    ]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-input"] + pkgs)
    try:
        sys.path.append(site.getusersitepackages())
    except Exception:
        pass
    importlib.invalidate_caches()
    import numpy as np
    import pandas as pd
    import networkx as nx
    from scipy import stats
    import statsmodels.api as sm

# IO root for all data
DATA_DIR = os.environ.get("APP_DATA_DIR", "/app/data")

# Utility: replicate the R vectorLength bug/definition: sqrt(sum((v*v)^2)) = sqrt(sum(v^4))
def vector_length(v: np.ndarray) -> float:
    return float(np.sqrt(np.sum(np.power(v * v, 2.0))))

# Compute cosine similarity matrix across columns of a 2D array (rows: observations, cols: variables)
def cosine_similarity_columns(X: np.ndarray) -> np.ndarray:
    n_vars = X.shape[1]
    S = np.zeros((n_vars, n_vars), dtype=float)
    norms = np.array([vector_length(X[:, i]) for i in range(n_vars)])
    for i in range(n_vars):
        for j in range(n_vars):
            denom = norms[i] * norms[j]
            if denom == 0.0:
                S[i, j] = 0.0
            else:
                S[i, j] = float(np.dot(X[:, i], X[:, j]) / denom)
    return S

# Planar (PMFG-like) filtering: greedily add edges from largest weights while keeping the graph planar
# This approximates TMFG/PMFG behavior to preserve a planar, triangulated-like sparse backbone.
def planar_maximally_filtered_adjacency(S: np.ndarray) -> np.ndarray:
    n = S.shape[0]
    # zero diagonal
    W = S.copy()
    np.fill_diagonal(W, 0.0)
    # List edges with weights (i < j)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            w = W[i, j]
            if np.isfinite(w):
                edges.append((i, j, float(w)))
    # sort by descending weight
    edges.sort(key=lambda x: x[2], reverse=True)
    G = nx.Graph()
    G.add_nodes_from(range(n))
    max_edges = max(0, 3 * n - 6)  # planar graph edge upper bound
    for (i, j, w) in edges:
        if G.number_of_edges() >= max_edges:
            break
        G.add_edge(i, j, weight=w)
        is_planar, _ = nx.check_planarity(G, counterexample=False)
        if not is_planar:
            G.remove_edge(i, j)
    # adjacency matrix
    A = np.zeros((n, n), dtype=int)
    for (u, v) in G.edges():
        A[u, v] = 1
        A[v, u] = 1
    return A

# Compute ASPL on the largest connected component of an unweighted graph adjacency matrix
# If no edges, return NaN
def average_shortest_path_length_lcc(A: np.ndarray) -> float:
    G = nx.from_numpy_array(A)
    if G.number_of_edges() == 0:
        return float('nan')
    # largest connected component
    components = list(nx.connected_components(G))
    if len(components) == 0:
        return float('nan')
    lcc_nodes = max(components, key=len)
    H = G.subgraph(lcc_nodes).copy()
    try:
        return float(nx.average_shortest_path_length(H))
    except Exception:
        return float('nan')

# Load data

def load_open_and_fluency(data_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    fluency_path = os.path.join(data_dir, "FINAL fluency.csv")
    open_path = os.path.join(data_dir, "FINAL open.csv")
    fluency = pd.read_csv(fluency_path, encoding='utf-8-sig')
    open_df = pd.read_csv(open_path, encoding='utf-8-sig')
    return open_df, fluency

# Build binary word-by-participant matrix from fluency dataframe
# Columns: id, vf_an_01, vf_an_02, ...
# Cleaning: lowercase, strip, drop empty and '99'

def build_binary_matrix(fluency: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    cols = [c for c in fluency.columns if c != 'id']
    # collect vocabulary
    vocab_set = set()
    for _, row in fluency.iterrows():
        for c in cols:
            val = str(row.get(c, "")).strip().lower()
            if val and val != '99' and val != 'nan':
                vocab_set.add(val)
    vocab = sorted(list(vocab_set))
    word_index = {w: i for i, w in enumerate(vocab)}
    # build matrix (participants x words)
    X = np.zeros((fluency.shape[0], len(vocab)), dtype=int)
    for r, row in fluency.iterrows():
        seen = set()
        for c in cols:
            val = str(row.get(c, "")).strip().lower()
            if not val or val == '99' or val == 'nan':
                continue
            if val in word_index and val not in seen:
                X[r, word_index[val]] = 1
                seen.add(val)
    return X, vocab

# Filter common words that appear in at least 2 participants in each group

def common_words_mask(X: np.ndarray, group_mask: np.ndarray) -> np.ndarray:
    X1 = X[group_mask, :]
    X2 = X[~group_mask, :]
    counts1 = X1.sum(axis=0)
    counts2 = X2.sum(axis=0)
    mask = (counts1 >= 2) & (counts2 >= 2)
    return mask.astype(bool)

# Approach 1: pooled networks per group, bootstrap 90% nodes, paired t-test for ASPL

def approach1(open_df: pd.DataFrame, X: np.ndarray, vocab: List[str], seed: int = 42,
              num_boots: int = 1000, sub_frac: float = 0.9) -> Dict:
    # group split on LATENT median
    median_latent = float(np.median(open_df['LATENT'].values))
    group_mask = (open_df['LATENT'].values > median_latent)

    # restrict to common words
    mask = common_words_mask(X, group_mask)
    X1 = X[group_mask, :][:, mask]
    X2 = X[~group_mask, :][:, mask]
    # cosine similarity of word columns
    S1 = cosine_similarity_columns(X1)
    S2 = cosine_similarity_columns(X2)

    # TMFG/PMFG-like planar backbone and binarize
    A1 = planar_maximally_filtered_adjacency(S1)
    A2 = planar_maximally_filtered_adjacency(S2)

    rng = np.random.default_rng(seed)
    m = A1.shape[0]
    sub_size = max(1, int(round(sub_frac * m)))

    aspl1 = []
    aspl2 = []
    for _ in range(num_boots):
        boot_nodes = rng.choice(m, size=sub_size, replace=False)
        A1b = A1[np.ix_(boot_nodes, boot_nodes)]
        A2b = A2[np.ix_(boot_nodes, boot_nodes)]
        aspl1.append(average_shortest_path_length_lcc(A1b))
        aspl2.append(average_shortest_path_length_lcc(A2b))

    arr1 = np.array(aspl1, dtype=float)
    arr2 = np.array(aspl2, dtype=float)
    # paired t-test ignoring NaNs
    valid = ~np.isnan(arr1) & ~np.isnan(arr2)
    t_stat, p_val = stats.ttest_rel(arr1[valid], arr2[valid])
    result = {
        'mean_aspl_high': float(np.nanmean(arr1)),
        'mean_aspl_low': float(np.nanmean(arr2)),
        't_stat': float(t_stat),
        'p_value': float(p_val),
        'n_boot': int(np.sum(valid))
    }
    return result

# Approach 2: bootstrap subgroups of individuals, relate mean openness to ASPL

def approach2(open_df: pd.DataFrame, X: np.ndarray, seed: int = 42,
              num_boots: int = 1000, sub_n: int = 20) -> Dict:
    rng = np.random.default_rng(seed)
    n_part = X.shape[0]
    boots = []
    for bi in range(num_boots):
        boot_ids = rng.choice(n_part, size=sub_n, replace=False)
        subX = X[boot_ids, :]
        sub_open_mean = float(np.mean(open_df.iloc[boot_ids]['LATENT'].values))
        # common words (>=2 in subgroup)
        counts = subX.sum(axis=0)
        mask = (counts >= 2)
        subXc = subX[:, mask]
        if subXc.shape[1] < 4:
            # too few nodes for planar graph; skip
            boots.append({'boot': bi, 'open': sub_open_mean, 'aspl': float('nan'), 'num_words': int(subXc.shape[1])})
            continue
        S = cosine_similarity_columns(subXc)
        A = planar_maximally_filtered_adjacency(S)
        aspl = average_shortest_path_length_lcc(A)
        boots.append({'boot': bi, 'open': sub_open_mean, 'aspl': float(aspl), 'num_words': int(A.shape[0])})
    df = pd.DataFrame(boots)
    valid = df['aspl'].notna()
    # Pearson correlation
    if valid.sum() >= 3:
        r, p = stats.pearsonr(df.loc[valid, 'open'], df.loc[valid, 'aspl'])
    else:
        r, p = float('nan'), float('nan')
    # OLS regression aspl ~ open and aspl ~ open + num_words (via statsmodels)
    try:
        X1 = sm.add_constant(df.loc[valid, ['open']].values)
        y = df.loc[valid, 'aspl'].values
        mod1 = sm.OLS(y, X1, missing='drop').fit()
        beta_open = float(mod1.params[1])
        p_open = float(mod1.pvalues[1])
        # with num_words
        X2 = sm.add_constant(df.loc[valid, ['open', 'num_words']].values)
        mod2 = sm.OLS(y, X2, missing='drop').fit()
        beta_open2 = float(mod2.params[1])
        p_open2 = float(mod2.pvalues[1])
    except Exception:
        beta_open = p_open = beta_open2 = p_open2 = float('nan')
    return {
        'n_boot_valid': int(valid.sum()),
        'pearson_r': float(r),
        'pearson_p': float(p),
        'ols_beta_open': float(beta_open),
        'ols_p_open': float(p_open),
        'ols_beta_open_w_words': float(beta_open2),
        'ols_p_open_w_words': float(p_open2)
    }

# Approach 3: sliding bins over LATENT, relate bin mean openness to ASPL

def approach3(open_df: pd.DataFrame, X: np.ndarray, window_width: float = 0.10, min_n: int = 0) -> Dict:
    lat = open_df['LATENT'].values.astype(float)
    mn, mx = float(np.min(lat)), float(np.max(lat))
    step = window_width
    rows = []
    start = mn
    while start <= mx - window_width + 1e-9:
        inside = (lat >= start) & (lat < start + window_width)
        n_in = int(np.sum(inside))
        if n_in >= 2:
            subX = X[inside, :]
            counts = subX.sum(axis=0)
            mask = (counts >= 2)
            subXc = subX[:, mask]
            if subXc.shape[1] >= 4:
                S = cosine_similarity_columns(subXc)
                A = planar_maximally_filtered_adjacency(S)
                aspl = average_shortest_path_length_lcc(A)
            else:
                aspl = float('nan')
            rows.append({'bin_start': float(start), 'n': n_in, 'open_mean': float(np.mean(lat[inside])), 'aspl': float(aspl)})
        start += step
    df = pd.DataFrame(rows)
    if df.empty:
        return {'n_bins': 0, 'pearson_r': float('nan'), 'pearson_p': float('nan'), 'pearson_r_n_gt_20': float('nan'), 'pearson_p_n_gt_20': float('nan')}
    valid = df['aspl'].notna()
    if valid.sum() >= 3:
        r, p = stats.pearsonr(df.loc[valid, 'open_mean'], df.loc[valid, 'aspl'])
    else:
        r, p = float('nan'), float('nan')
    big = (df['n'] > 20) & valid
    if big.sum() >= 3:
        r2, p2 = stats.pearsonr(df.loc[big, 'open_mean'], df.loc[big, 'aspl'])
    else:
        r2, p2 = float('nan'), float('nan')
    return {'n_bins': int(df.shape[0]), 'pearson_r': float(r), 'pearson_p': float(p), 'pearson_r_n_gt_20': float(r2), 'pearson_p_n_gt_20': float(p2)}


def main():
    open_df, fluency = load_open_and_fluency(DATA_DIR)
    X, vocab = build_binary_matrix(fluency)
    # Run approaches
    res1 = approach1(open_df, X, vocab)
    res2 = approach2(open_df, X)
    res3 = approach3(open_df, X)
    out = {
        'task': 'Task1',
        'approach1': res1,
        'approach2': res2,
        'approach3': res3
    }
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
