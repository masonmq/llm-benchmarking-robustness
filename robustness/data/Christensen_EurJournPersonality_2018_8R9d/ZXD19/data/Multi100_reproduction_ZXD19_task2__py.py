import os
import math
import json
import sys
# Runtime dependency bootstrap to avoid missing modules in some environments
try:
    import numpy as np
    import pandas as pd
    import networkx as nx
    from scipy import stats
except Exception:
    import subprocess
    pkgs = ["numpy==1.26.4","pandas==2.0.3","scipy==1.11.4","networkx==3.2.1","statsmodels==0.14.1"]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-input"] + pkgs)
    import numpy as np
    import pandas as pd
    import networkx as nx
    from scipy import stats
from typing import Tuple, List, Dict

DATA_DIR = os.environ.get("APP_DATA_DIR", "/app/data")

# replicate the R vectorLength definition

def vector_length(v: np.ndarray) -> float:
    return float(np.sqrt(np.sum(np.power(v * v, 2.0))))


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


def planar_maximally_filtered_adjacency(S: np.ndarray) -> np.ndarray:
    n = S.shape[0]
    W = S.copy()
    np.fill_diagonal(W, 0.0)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            w = W[i, j]
            if np.isfinite(w):
                edges.append((i, j, float(w)))
    edges.sort(key=lambda x: x[2], reverse=True)
    G = nx.Graph()
    G.add_nodes_from(range(n))
    max_edges = max(0, 3 * n - 6)
    for (i, j, w) in edges:
        if G.number_of_edges() >= max_edges:
            break
        G.add_edge(i, j, weight=w)
        is_planar, _ = nx.check_planarity(G, counterexample=False)
        if not is_planar:
            G.remove_edge(i, j)
    A = np.zeros((n, n), dtype=int)
    for (u, v) in G.edges():
        A[u, v] = 1
        A[v, u] = 1
    return A


def average_shortest_path_length_lcc(A: np.ndarray) -> float:
    G = nx.from_numpy_array(A)
    if G.number_of_edges() == 0:
        return float('nan')
    components = list(nx.connected_components(G))
    if len(components) == 0:
        return float('nan')
    lcc_nodes = max(components, key=len)
    H = G.subgraph(lcc_nodes).copy()
    try:
        return float(nx.average_shortest_path_length(H))
    except Exception:
        return float('nan')


def load_open_and_fluency(data_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    fluency_path = os.path.join(data_dir, "FINAL fluency.csv")
    open_path = os.path.join(data_dir, "FINAL open.csv")
    fluency = pd.read_csv(fluency_path, encoding='utf-8-sig')
    open_df = pd.read_csv(open_path, encoding='utf-8-sig')
    return open_df, fluency


def build_binary_matrix(fluency: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    cols = [c for c in fluency.columns if c != 'id']
    vocab_set = set()
    for _, row in fluency.iterrows():
        for c in cols:
            val = str(row.get(c, "")).strip().lower()
            if val and val != '99' and val != 'nan':
                vocab_set.add(val)
    vocab = sorted(list(vocab_set))
    word_index = {w: i for i, w in enumerate(vocab)}
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


def task2(open_df: pd.DataFrame, X: np.ndarray, seed: int = 42,
          num_boots: int = 1000, sub_frac: float = 0.9) -> Dict:
    median_latent = float(np.median(open_df['LATENT'].values))
    group_mask = (open_df['LATENT'].values > median_latent)
    # common words (>=2 in each group)
    X1 = X[group_mask, :]
    X2 = X[~group_mask, :]
    counts1 = X1.sum(axis=0)
    counts2 = X2.sum(axis=0)
    mask = (counts1 >= 2) & (counts2 >= 2)
    X1c = X1[:, mask]
    X2c = X2[:, mask]
    # cosine similarity by words
    S1 = cosine_similarity_columns(X1c)
    S2 = cosine_similarity_columns(X2c)
    # planar backbone
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
    valid = ~np.isnan(arr1) & ~np.isnan(arr2)
    t_stat, p_val = stats.ttest_rel(arr1[valid], arr2[valid])
    return {
        'mean_aspl_high': float(np.nanmean(arr1)),
        'mean_aspl_low': float(np.nanmean(arr2)),
        't_stat': float(t_stat),
        'p_value': float(p_val),
        'n_boot': int(np.sum(valid))
    }


def main():
    open_df, fluency = load_open_and_fluency(DATA_DIR)
    X, vocab = build_binary_matrix(fluency)
    res = task2(open_df, X)
    out = {'task': 'Task2', 'approach1_only': res}
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
