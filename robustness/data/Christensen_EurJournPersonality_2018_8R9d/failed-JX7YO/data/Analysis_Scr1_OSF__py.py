import csv, json, math
from collections import Counter, defaultdict
from graph_utils import Graph, kruskal_mst, tree_all_pairs_distances, tree_betweenness_centrality, label_propagation_communities, participation_coefficients

DATA_PATH = "/app/data/FINAL demo open fluency.csv"
OUT_PATH = "/app/data/task1_results.json"


def to_float(s):
    try:
        return float(s)
    except Exception:
        return None


def clean_word(x):
    s = (x or '').strip().lower()
    if s in ('', 'nan', 'na', '-1', 'none'):
        return None
    return s


def load_words_and_traits(path):
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        word_cols = [c for c in reader.fieldnames if c.startswith('vf_an_')]
        rows = []
        for row in reader:
            words = [clean_word(row.get(c)) for c in word_cols]
            words = [w for w in words if w is not None]
            o_ffi = to_float(row.get('o_ffi'))
            oi_bfas = to_float(row.get('oi_bfas'))
            o_bfas = to_float(row.get('o_bfas'))
            i_bfas = to_float(row.get('i_bfas'))
            traits = [v for v in [o_ffi, oi_bfas, o_bfas, i_bfas] if v is not None]
            openness_avg = sum(traits) / len(traits) if traits else None
            rows.append({'words': list(set(words)), 'openness_average': openness_avg})
    return rows


def build_vocab_and_counts(rows):
    vocab_counter = Counter()
    rows_words = []
    for r in rows:
        uw = r['words']
        rows_words.append(uw)
        vocab_counter.update(uw)
    vocab = sorted(vocab_counter.keys())
    wid = {w: i for i, w in enumerate(vocab)}
    counts = defaultdict(Counter)
    for uw in rows_words:
        for i, wa in enumerate(uw):
            ia = wid[wa]
            for j in range(i + 1, len(uw)):
                wb = uw[j]
                ib = wid[wb]
                counts[ia][ib] += 1
                counts[ib][ia] += 1
    return vocab, wid, rows_words, counts


def entropy_from_p(p):
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return - (p * math.log(p, 2.0) + (1.0 - p) * math.log(1.0 - p, 2.0))


def compute_metrics_for_words(nn_idx, counts, N_rows):
    n = len(nn_idx)
    if n < 2:
        return dict(cpl=None, betw_mean=None, betw_max=None, part_mean=None)

    def entropy(i, j):
        c = counts[i].get(j, 0)
        p = c / float(N_rows)
        H = entropy_from_p(p)
        return 0.99 if H == 0.0 else H

    # Build edge list for MST on distance graph
    edges = []  # (weight, u, v)
    for a in range(n):
        ia = nn_idx[a]
        for b in range(a + 1, n):
            ib = nn_idx[b]
            w = float(entropy(ia, ib))
            if math.isfinite(w):
                edges.append((w, a, b))

    # Build strength adjacency for participation (1/entropy)
    strength_adj = [[] for _ in range(n)]
    for a in range(n):
        ia = nn_idx[a]
        for b in range(a + 1, n):
            ib = nn_idx[b]
            e = float(entropy(ia, ib))
            w = 1.0 / max(e, 1e-9)
            if math.isfinite(w):
                strength_adj[a].append((b, w))
                strength_adj[b].append((a, w))

    if not edges:
        return dict(cpl=None, betw_mean=None, betw_max=None, part_mean=None)

    # Minimum Spanning Tree via Kruskal
    T = kruskal_mst(n, edges)

    # CPL median from all-pairs distances on MST
    dists = tree_all_pairs_distances(T)
    cpl = None
    if dists:
        dists_sorted = sorted([d for d in dists if d > 0])
        if dists_sorted:
            m = len(dists_sorted)
            mid = m // 2
            if m % 2 == 1:
                cpl = dists_sorted[mid]
            else:
                cpl = 0.5 * (dists_sorted[mid - 1] + dists_sorted[mid])

    # Betweenness on MST
    btw_vals = tree_betweenness_centrality(T, normalized=True)
    betw_mean = sum(btw_vals) / len(btw_vals) if btw_vals else None
    betw_max = max(btw_vals) if btw_vals else None

    # Participation coefficient via simple label propagation partition
    part_mean = None
    try:
        partition = label_propagation_communities(n, strength_adj, weight_key=True)
        p_list = participation_coefficients(n, strength_adj, partition)
        if p_list:
            # mode via 0.02 bins
            bins = defaultdict(int)
            for v in p_list:
                bins[round(v, 2)] += 1
            mode_bin = max(bins.items(), key=lambda kv: kv[1])[0]
            filtered = [v for v in p_list if v > mode_bin]
            part_mean = (sum(filtered) / len(filtered)) if filtered else (sum(p_list) / len(p_list))
    except Exception:
        part_mean = None

    return dict(cpl=cpl, betw_mean=betw_mean, betw_max=betw_max, part_mean=part_mean)


def spearman_rho_p(x, y):
    # rank-based correlation, normal approx p-value
    def ranks(vals):
        pairs = sorted((v, i) for i, v in enumerate(vals))
        r = [0.0] * len(vals)
        i = 0
        while i < len(pairs):
            j = i
            while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
                j += 1
            rank = (i + j + 2) / 2.0
            for k in range(i, j + 1):
                r[pairs[k][1]] = rank
            i = j + 1
        return r
    n = len(x)
    if n < 3:
        return None, None
    rx = ranks(x)
    ry = ranks(y)
    mx = sum(rx) / n
    my = sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    sx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    sy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if sx == 0 or sy == 0:
        return None, None
    rho = cov / (sx * sy)
    t = abs(rho) * math.sqrt((n - 2) / max(1e-9, 1 - rho * rho))
    # normal approx
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(t / sqrt(2))))
    return rho, p


def welch_t(high, low):
    if len(high) < 2 or len(low) < 2:
        return None, None
    mh = sum(high) / len(high)
    ml = sum(low) / len(low)
    vh = sum((v - mh) ** 2 for v in high) / (len(high) - 1)
    vl = sum((v - ml) ** 2 for v in low) / (len(low) - 1)
    se = math.sqrt(vh / len(high) + vl / len(low))
    if se == 0:
        return None, None
    t = (mh - ml) / se
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    return t, p


def main():
    rows = load_words_and_traits(DATA_PATH)
    vocab, wid, rows_words, counts = build_vocab_and_counts(rows)
    N_rows = len(rows_words)

    out = []
    for r, uw in zip(rows, rows_words):
        nn_idx = [wid[w] for w in uw]
        m = compute_metrics_for_words(nn_idx, counts, N_rows)
        out.append({'openness_average': r['openness_average'], 'cpl': m['cpl'], 'betw_mean': m['betw_mean'], 'betw_max': m['betw_max'], 'part_mean': m['part_mean']})

    # Filter cpl < 10 and non-missing vars
    filt = [o for o in out if (o['cpl'] is not None and o['cpl'] < 10 and o['openness_average'] is not None and o['part_mean'] is not None)]

    x = [o['openness_average'] for o in filt]
    y = [o['part_mean'] for o in filt]
    rho, pval = spearman_rho_p(x, y) if len(filt) >= 3 else (None, None)

    # median split groups
    n = len(x)
    if n > 0:
        med = sorted(x)[n // 2]
        high = [y[i] for i in range(n) if x[i] > med and y[i] is not None]
        low = [y[i] for i in range(n) if x[i] <= med and y[i] is not None]
    else:
        high, low = [], []
    t_stat, t_p = welch_t(high, low)

    results = {
        'spearman_rho': None if rho is None else float(rho),
        'spearman_p': None if pval is None else float(pval),
        'n_used_spearman': len(filt),
        't_stat': None if t_stat is None else float(t_stat),
        't_p': None if t_p is None else float(t_p),
        'n_high': len(high),
        'n_low': len(low)
    }

    with open(OUT_PATH, 'w') as f:
        json.dump(results, f, indent=2)


if __name__ == '__main__':
    main()
