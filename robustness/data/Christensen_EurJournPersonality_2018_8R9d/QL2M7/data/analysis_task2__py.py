import os
import json
import re

# Robust import block with on-the-fly installation if needed
try:
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
except ModuleNotFoundError:
    import sys, subprocess
    pkgs = [
        "numpy==1.25.2",
        "pandas==2.0.3",
        "scipy==1.11.1",
        "scikit-learn==1.3.0",
        "networkx==3.1",
        "python-louvain==0.16"
    ]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir"] + pkgs)
    except Exception as e:
        print(f"Package installation failed: {e}")
        raise
    # retry imports
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
try:
    import community as community_louvain  # python-louvain
    HAS_COMMUNITY = True
except Exception:
    HAS_COMMUNITY = False

RANDOM_SEED = 12345
np.random.seed(RANDOM_SEED)

DATA_PATH = os.environ.get("APP_DATA", "/app/data")
INPUT_CSV = os.path.join(DATA_PATH, "FINAL demo open fluency.csv")
OUTPUT_JSON = os.path.join(DATA_PATH, "task2_results.json")

# --------------------- Utility functions ---------------------

def clean_token(x: str) -> str:
    if x is None:
        return ""
    s = str(x).strip().lower()
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
    C = np.where(np.isnan(C), 0.0, C)
    np.fill_diagonal(C, 0.0)
    return C


def graph_from_corr(C):
    G = nx.Graph()
    n = C.shape[0]
    G.add_nodes_from(range(n))
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


def compute_aspl(G):
    if G.number_of_nodes() == 0 or G.number_of_edges() == 0:
        return np.nan
    H = largest_component(G)
    if H.number_of_nodes() < 2 or H.number_of_edges() == 0:
        return np.nan
    H2 = H.copy()
    for u, v, d in H2.edges(data=True):
        w = d.get("weight", 1.0)
        dist = 1.0 / w if w > 0 else 1e6
        d["distance"] = dist
    try:
        aspl = nx.average_shortest_path_length(H2, weight="distance")
    except Exception:
        aspl = np.nan
    return aspl


# --------------------- Main analysis (Task 2) ---------------------

def main():
    os.makedirs(DATA_PATH, exist_ok=True)
    df = pd.read_csv(INPUT_CSV)
    vf_cols = [c for c in df.columns if c.startswith("vf_an_")]
    openness_cols = [c for c in ["o_ffi", "o_bfas", "o_neo"] if c in df.columns]

    if len(openness_cols) == 0:
        raise ValueError("No openness total score columns found (expected one of: o_ffi, o_bfas, o_neo)")
    X = df[openness_cols].apply(pd.to_numeric, errors='coerce')
    X_impute = X.fillna(X.mean())
    scaler = StandardScaler()
    Xz = scaler.fit_transform(X_impute.values)
    pca = PCA(n_components=1, random_state=RANDOM_SEED)
    comp = pca.fit_transform(Xz).ravel()
    df["openness_latent"] = comp

    med = np.nanmedian(df["openness_latent"].values)
    df["openness_group"] = np.where(df["openness_latent"] >= med, "high", "low")

    df_low = df[df["openness_group"] == "low"].reset_index(drop=True)
    df_high = df[df["openness_group"] == "high"].reset_index(drop=True)

    part_words_low = build_participant_words(df_low, vf_cols)
    part_words_high = build_participant_words(df_high, vf_cols)

    nodes = get_equated_nodes(part_words_low, part_words_high, min_participants=2)

    # Build full binary matrices
    M_low_full = build_binary_matrix(nodes, part_words_low)
    M_high_full = build_binary_matrix(nodes, part_words_high)

    n_nodes = len(nodes)
    if n_nodes == 0:
        raise ValueError("No equated nodes across groups; cannot run Task 2")

    retain_rate = 0.90
    k = max(1, int(round(n_nodes * retain_rate)))

    B = 1000  # node-wise bootstrap iterations (without replacement)
    rng = np.random.default_rng(RANDOM_SEED)

    aspl_low = []
    aspl_high = []

    for b in range(B):
        sel = rng.choice(n_nodes, size=k, replace=False)
        # Low group
        M_low = M_low_full[sel, :]
        C_low = corr_from_binary_matrix(M_low)
        G_low = graph_from_corr(C_low)
        aspl_l = compute_aspl(G_low)
        aspl_low.append(aspl_l)
        # High group
        M_high = M_high_full[sel, :]
        C_high = corr_from_binary_matrix(M_high)
        G_high = graph_from_corr(C_high)
        aspl_h = compute_aspl(G_high)
        aspl_high.append(aspl_h)

    a = np.array(aspl_high, dtype=float)
    b_ = np.array(aspl_low, dtype=float)
    a = a[~np.isnan(a)]
    b_ = b_[~np.isnan(b_)]

    if len(a) > 1 and len(b_) > 1:
        t_stat, p_val = stats.ttest_ind(a, b_, equal_var=False, nan_policy='omit')
        # Cohen's d (Hedges g approximation not applied)
        na, nb = len(a), len(b_)
        sa2, sb2 = np.var(a, ddof=1), np.var(b_, ddof=1)
        sp = np.sqrt(((na - 1) * sa2 + (nb - 1) * sb2) / (na + nb - 2)) if (na + nb - 2) > 0 else np.nan
        d = (np.mean(a) - np.mean(b_)) / sp if sp and sp > 0 else np.nan
    else:
        t_stat, p_val, d = np.nan, np.nan, np.nan

    payload = {
        "random_seed": RANDOM_SEED,
        "n_participants": int(df.shape[0]),
        "n_nodes_equated": int(n_nodes),
        "retain_rate": retain_rate,
        "retain_k": int(k),
        "aspl": {
            "high_mean": float(np.nanmean(a)) if len(a) > 0 else np.nan,
            "low_mean": float(np.nanmean(b_)) if len(b_) > 0 else np.nan,
            "t_stat": float(t_stat) if not np.isnan(t_stat) else np.nan,
            "p_value": float(p_val) if not np.isnan(p_val) else np.nan,
            "cohens_d": float(d) if not np.isnan(d) else np.nan,
            "n_boot_high": int(len(a)),
            "n_boot_low": int(len(b_))
        },
        "notes": "Approximate Python translation. TMFG filtering and small-world model test not implemented. Node-wise bootstrap with 90% nodes retained; edges from positive Pearson correlations."
    }

    with open(OUTPUT_JSON, 'w') as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
