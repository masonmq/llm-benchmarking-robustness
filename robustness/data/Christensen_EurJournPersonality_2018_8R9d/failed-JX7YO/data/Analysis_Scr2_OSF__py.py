import csv, json, math
from collections import Counter, defaultdict
from graph_utils import Graph, kruskal_mst, tree_all_pairs_distances, tree_betweenness_centrality, power_iteration_eigenvector_centrality, label_propagation_communities, participation_coefficients

DATA_PATH = "/app/data/FINAL demo open fluency.csv"
OUT_PATH = "/app/data/task2_results.json"


def clean_word(x):
    s = (x or '').strip().lower()
    if s in ('', 'nan', 'na', '-1', 'none'):
        return None
    return s


def load_rows(path):
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        word_cols = [c for c in reader.fieldnames if c.startswith('vf_an_')]
        rows = []
        for row in reader:
            words = [clean_word(row.get(c)) for c in word_cols]
            words = [w for w in words if w is not None and w != '99']
            d_gender = row.get('d_gender')
            rows.append({'words': list(set(words)), 'd_gender': d_gender})
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
        if H == 0.0:
            return 0.99
        if H > 49:
            return 0.0
        return H

    # Build edges and strength adjacency
    edges = []  # (weight, u, v)
    strength_adj = [[] for _ in range(n)]
    for a in range(n):
        ia = nn_idx[a]
        for b in range(a + 1, n):
            ib = nn_idx[b]
            e = float(entropy(ia, ib))
            if math.isfinite(e):
                edges.append((e, a, b))
                w = 1.0 / max(e, 1e-9)
                strength_adj[a].append((b, w))
                strength_adj[b].append((a, w))

    if not edges:
        return dict(cpl=None, betw_mean=None, betw_max=None, part_mean=None)

    # Remove top 10% eigenvector centrality nodes (using power iteration)
    try:
        ec = power_iteration_eigenvector_centrality(n, strength_adj, weight_key=True)
        vals = sorted(ec)
        cutoff_idx = int(0.9 * len(vals)) - 1
        cutoff = vals[max(0, cutoff_idx)] if vals else 0
        nodes_to_remove = [i for i, v in enumerate(ec) if v > cutoff]
        keep = [i for i in range(n) if i not in nodes_to_remove]
        index_map = {old: new for new, old in enumerate(keep)}
        edges = [(w, index_map[u], index_map[v]) for (w, u, v) in edges if u in index_map and v in index_map]
        new_strength = [[] for _ in keep]
        for old_u in keep:
            u = index_map[old_u]
            for old_v, w in strength_adj[old_u]:
                if old_v in index_map:
                    v = index_map[old_v]
                    new_strength[u].append((v, w))
        strength_adj = new_strength
        n = len(keep)
    except Exception:
        pass

    # MST via Kruskal
    T = kruskal_mst(n, edges)

    # CPL median
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

    # Participation coefficient using label propagation partition on strength_adj
    part_mean = None
    try:
        partition = label_propagation_communities(n, strength_adj, weight_key=True)
        p_list = participation_coefficients(n, strength_adj, partition)
        if p_list:
            bins = defaultdict(int)
            for v in p_list:
                bins[round(v, 2)] += 1
            mode_bin = max(bins.items(), key=lambda kv: kv[1])[0]
            filtered = [v for v in p_list if v > mode_bin]
            part_mean = (sum(filtered) / len(filtered)) if filtered else (sum(p_list) / len(p_list))
    except Exception:
        part_mean = None

    return dict(cpl=cpl, betw_mean=betw_mean, betw_max=betw_max, part_mean=part_mean)


def main():
    rows = load_rows(DATA_PATH)
    vocab, wid, rows_words, counts = build_vocab_and_counts(rows)
    N_rows = len(rows_words)

    out = []
    for r, uw in zip(rows, rows_words):
        nn_idx = [wid[w] for w in uw]
        m = compute_metrics_for_words(nn_idx, counts, N_rows)
        out.append({'d_gender': r['d_gender'], 'cpl': m['cpl'], 'betw_mean': m['betw_mean'], 'betw_max': m['betw_max'], 'part_mean': m['part_mean']})

    analysis = [o for o in out if (o['cpl'] is not None and o['cpl'] < 10 and o['d_gender'] is not None and o['d_gender'] != '-1' and o['part_mean'] is not None)]

    a = [o['part_mean'] for o in analysis if o['d_gender'] == '1']
    b = [o['part_mean'] for o in analysis if o['d_gender'] == '2']

    t_stat = None
    t_p = None
    if len(a) >= 2 and len(b) >= 2:
        ma = sum(a) / len(a)
        mb = sum(b) / len(b)
        va = sum((v - ma) ** 2 for v in a) / (len(a) - 1)
        vb = sum((v - mb) ** 2 for v in b) / (len(b) - 1)
        se = math.sqrt(va / len(a) + vb / len(b))
        if se > 0:
            t_stat = (ma - mb) / se
            from math import erf, sqrt
            t_p = 2 * (1 - 0.5 * (1 + erf(abs(t_stat) / sqrt(2))))

    results = {
        't_stat_gender': None if t_stat is None else float(t_stat),
        't_p_gender': None if t_p is None else float(t_p),
        'n_gender_1': len(a),
        'n_gender_2': len(b)
    }

    with open(OUT_PATH, 'w') as f:
        json.dump(results, f, indent=2)


if __name__ == '__main__':
    main()
