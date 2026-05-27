import os
import json
import re
import sys
import subprocess
import site

# Ensure required packages are available at runtime
PKGS = [
    "numpy==1.25.2",
    "pandas==2.0.3",
    "scipy==1.11.1",
    "scikit-learn==1.3.0",
    "networkx==3.1",
    "python-louvain==0.16"
]

def ensure_packages():
    try:
        import numpy as _np  # noqa: F401
        import pandas as _pd  # noqa: F401
        from sklearn.preprocessing import StandardScaler as _SS  # noqa: F401
        from sklearn.decomposition import PCA as _PCA  # noqa: F401
        import networkx as _nx  # noqa: F401
        from scipy import stats as _stats  # noqa: F401
        return
    except Exception:
        pass
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir"] + PKGS)
    except Exception as e:
        print(f"Package installation failed: {e}")
        raise
    try:
        user_site = site.getusersitepackages()
        if user_site not in sys.path:
            sys.path.append(user_site)
    except Exception:
        pass

ensure_packages()

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import networkx as nx
from scipy import stats

try:
    import community as community_louvain  # python-louvain
    HAS_COMMUNITY = True
except Exception:
    HAS_COMMUNITY = False

RANDOM_SEED = 12345
np.random.seed(RANDOM_SEED)

DATA_PATH = os.environ.get("APP_DATA", "/app/data")
INPUT_CSV = os.path.join(DATA_PATH, "FINAL demo open fluency.csv")
OUTPUT_JSON = os.path.join(DATA_PATH, "task1_results.json")

# --------------------- Utility functions ---------------------

def clean_token(x: str) -> str:
    if x is None:
        return ""
    s = str(x).strip().lower()
    # remove punctuation and extra spaces
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def build_participant_words(df, vf_cols):
    part_words = []
    for _, row in df.iterrows():
        words = []
        for c in vf_cols:
            val = row.get(c, None)
            if pd.isna(val) or str(val).strip() == "":
                continue
            tok = clean_token(str(val))
            if tok != "":
                words.append(tok)
        part_words.append(set(words))
    return part_words


def get_equated_nodes(part_words_low, part_words_high, min_participants=2):
    # frequency by participants per group
    from collections import Counter
    def freq_map(part_words):
        cnt = Counter()
        for ws in part_words:
            for w in set(ws):
                cnt[w] += 1
        return cnt
    f_low = freq_map(part_words_low)
    f_high = freq_map(part_words_high)
    nodes_low = {w for w, f in f_low.items() if f >= min_participants}
    nodes_high = {w for w, f in f_high.items() if f >= min_participants}
    nodes = sorted(list(nodes_low.intersection(nodes_high)))
    return nodes


def build_binary_matrix(nodes, part_words):
    node_index = {w: i for i, w in enumerate(nodes)}
    n_nodes = len(nodes)
    n_parts = len(part_words)
    M = np.zeros((n_nodes, n_parts), dtype=float)
    for j, ws in enumerate(part_words):
        for w in ws:
            i = node_index.get(w)
            if i is not None:
                M[i, j] = 1.0
    return M


def corr_from_binary_matrix(M):
    if M.shape[1] < 2 or M.shape[0] < 2:
        return np.full((M.shape[0], M.shape[0]), 0.0)
    with np.errstate(invalid='ignore'):
        C = np.corrcoef(M, rowvar=True)
    # replace NaNs (zero variance rows) with 0
    C = np.where(np.isnan(C), 0.0, C)
    # zero self-correlations
    np.fill_diagonal(C, 0.0)
    return C


def graph_from_corr(C):
    G = nx.Graph()
    n = C.shape[0]
    G.add_nodes_from(range(n))
    # Only positive associations as edges
    edges = np.where(C > 0)
    for i, j in zip(edges[0], edges[1]):
        if i < j:
            w = float(C[i, j])
            if w > 0:
                G.add_edge(i, j, weight=w)
    return G


def largest_component(G):
    if G.number_of_nodes() == 0:
        return G
    if nx.is_connected(G):
        return G
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    return G.subgraph(comps[0]).copy()


def compute_metrics(G):
    if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
        return {"ASPL": np.nan, "CC": np.nan, "Q": np.nan}
    # work on largest connected component
    H = largest_component(G)
    if H.number_of_nodes() < 2 or H.number_of_edges() == 0:
        return {"ASPL": np.nan, "CC": np.nan, "Q": np.nan}
    # ASPL using inverse weight as distance
    H2 = H.copy()
    for u, v, d in H2.edges(data=True):
        w = d.get("weight", 1.0)
        # avoid division by zero
        dist = 1.0 / w if w > 0 else 1e6
        d["distance"] = dist
    try:
        aspl = nx.average_shortest_path_length(H2, weight="distance")
    except Exception:
        aspl = np.nan
    try:
        cc = nx.average_clustering(H, weight="weight")
    except Exception:
        cc = np.nan
    q = np.nan
    if HAS_COMMUNITY:
        try:
            part = community_louvain.best_partition(H, weight="weight", random_state=RANDOM_SEED)
            q = community_louvain.modularity(part, H, weight="weight")
        except Exception:
            q = np.nan
    return {"ASPL": aspl, "CC": cc, "Q": q}


# --------------------- Main analysis ---------------------

def main():
    os.makedirs(DATA_PATH, exist_ok=True)
    df = pd.read_csv(INPUT_CSV)

    # Identify columns
    vf_cols = [c for c in df.columns if c.startswith("vf_an_")]
    openness_cols = [c for c in ["o_ffi", "o_bfas", "o_neo"] if c in df.columns]

    # Build openness composite via PCA(1) on available measures (imputation with column mean for missing)
    if len(openness_cols) == 0:
        raise ValueError("No openness total score columns found (expected one of: o_ffi, o_bfas, o_neo)")
    X = df[openness_cols].apply(pd.to_numeric, errors='coerce')
    # Impute column means
    X_impute = X.fillna(X.mean())
    scaler = StandardScaler()
    Xz = scaler.fit_transform(X_impute.values)
    pca = PCA(n_components=1, random_state=RANDOM_SEED)
    comp = pca.fit_transform(Xz).ravel()
    df["openness_latent"] = comp

    # Median split
    med = np.nanmedian(df["openness_latent"].values)
    df["openness_group"] = np.where(df["openness_latent"] >= med, "high", "low")

    # Build participant word sets by group
    df_low = df[df["openness_group"] == "low"].reset_index(drop=True)
    df_high = df[df["openness_group"] == "high"].reset_index(drop=True)

    part_words_low = build_participant_words(df_low, vf_cols)
    part_words_high = build_participant_words(df_high, vf_cols)

    # Equated nodes across groups: words produced by at least 2 participants per group
    nodes = get_equated_nodes(part_words_low, part_words_high, min_participants=2)

    # Pre-build binary matrices on full groups (used in bootstrap sampling by selecting participant indices)
    M_low_full = build_binary_matrix(nodes, part_words_low)
    M_high_full = build_binary_matrix(nodes, part_words_high)

    n_low = M_low_full.shape[1]
    n_high = M_high_full.shape[1]

    B = 1000  # case-wise bootstrap iterations
    metrics_low = {"ASPL": [], "CC": [], "Q": []}
    metrics_high = {"ASPL": [], "CC": [], "Q": []}

    rng = np.random.default_rng(RANDOM_SEED)

    for b in range(B):
        # sample participants with replacement
        if n_low > 0:
            idx_low = rng.integers(low=0, high=n_low, size=n_low)
            M_low = M_low_full[:, idx_low]
            C_low = corr_from_binary_matrix(M_low)
            G_low = graph_from_corr(C_low)
            m_low = compute_metrics(G_low)
            for k in metrics_low:
                metrics_low[k].append(m_low[k])
        if n_high > 0:
            idx_high = rng.integers(low=0, high=n_high, size=n_high)
            M_high = M_high_full[:, idx_high]
            C_high = corr_from_binary_matrix(M_high)
            G_high = graph_from_corr(C_high)
            m_high = compute_metrics(G_high)
            for k in metrics_high:
                metrics_high[k].append(m_high[k])

    # T-tests high vs low for ASPL, CC, Q
    results = {}
    for metric in ["ASPL", "CC", "Q"]:
        a = np.array(metrics_high[metric], dtype=float)
        b_ = np.array(metrics_low[metric], dtype=float)
        # drop NaNs
        a = a[~np.isnan(a)]
        b_ = b_[~np.isnan(b_)]
        if len(a) > 1 and len(b_) > 1:
            t_stat, p_val = stats.ttest_ind(a, b_, equal_var=False, nan_policy='omit')
        else:
            t_stat, p_val = np.nan, np.nan
        results[metric] = {
            "high_mean": float(np.nanmean(a)) if len(a) > 0 else np.nan,
            "low_mean": float(np.nanmean(b_)) if len(b_) > 0 else np.nan,
            "t_stat": float(t_stat) if not np.isnan(t_stat) else np.nan,
            "p_value": float(p_val) if not np.isnan(p_val) else np.nan,
            "n_boot_high": int(len(a)),
            "n_boot_low": int(len(b_))
        }

    payload = {
        "random_seed": RANDOM_SEED,
        "n_participants": int(df.shape[0]),
        "n_nodes_equated": int(len(nodes)),
        "metrics": results,
        "notes": "Approximate Python translation. TMFG filtering and small-world model test not implemented. Networks built from positive Pearson correlations."
    }

    with open(OUTPUT_JSON, 'w') as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
