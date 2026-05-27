import math, random
from collections import defaultdict, deque

# Basic undirected weighted graph utilities without external deps

class Graph:
    def __init__(self, n):
        self.n = n
        self.adj = [[] for _ in range(n)]  # list of (neighbor, weight)
    def add_edge(self, u, v, w):
        self.adj[u].append((v, w))
        self.adj[v].append((u, w))


def kruskal_mst(n, edges):
    # edges: list of (w, u, v) with u < v
    parent = list(range(n))
    rank = [0] * n
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        if rank[ra] < rank[rb]:
            parent[ra] = rb
        elif rank[ra] > rank[rb]:
            parent[rb] = ra
        else:
            parent[rb] = ra
            rank[ra] += 1
        return True
    edges_sorted = sorted(edges, key=lambda e: e[0])
    T = Graph(n)
    used = 0
    for w, u, v in edges_sorted:
        if union(u, v):
            T.add_edge(u, v, w)
            used += 1
            if used == n - 1:
                break
    return T


def tree_all_pairs_distances(T: Graph):
    # T must be a tree (connected or possibly forest). Return list of all pair distances
    n = T.n
    dists = []
    for s in range(n):
        # compute distances to nodes > s to avoid duplicates
        # Use DFS since unique paths and positive weights
        seen = [False] * n
        stack = [(s, -1, 0.0)]
        while stack:
            u, p, du = stack.pop()
            if seen[u]:
                continue
            seen[u] = True
            if u > s:
                dists.append(du)
            for v, w in T.adj[u]:
                if v == p:
                    continue
                stack.append((v, u, du + float(w)))
    return dists


def tree_betweenness_centrality(T: Graph, normalized=True):
    n = T.n
    if n <= 2:
        return [0.0] * n
    btw = [0.0] * n
    # For each node, removing it splits tree into components for each neighbor
    for v in range(n):
        comp_sizes = []
        for nei, _ in T.adj[v]:
            # count size of component reachable from nei without passing v
            size = 0
            stack = [nei]
            parent = {nei: v}
            while stack:
                u = stack.pop()
                size += 1
                for w, _ in T.adj[u]:
                    if w != parent.get(u, -1) and w != v:
                        parent[w] = u
                        stack.append(w)
            comp_sizes.append(size)
        # sum over unordered pairs of components: size_i * size_j
        s = 0
        prefix = 0
        for size in comp_sizes:
            s += size * prefix
            prefix += size
        btw[v] = float(s)
    if normalized:
        norm = (n - 1) * (n - 2) / 2.0
        if norm > 0:
            btw = [b / norm for b in btw]
    return btw


def power_iteration_eigenvector_centrality(n, adj, weight_key=True, max_iter=100, tol=1e-6):
    # adj: list of lists (neighbor, weight)
    x = [1.0 / n] * n
    for _ in range(max_iter):
        x_new = [0.0] * n
        for i in range(n):
            s = 0.0
            for j, w in adj[i]:
                s += (w if weight_key else 1.0) * x[j]
            x_new[i] = s
        # normalize
        norm = sum(abs(v) for v in x_new)
        if norm == 0:
            return x
        x_new = [v / norm for v in x_new]
        # check convergence
        diff = sum(abs(x_new[i] - x[i]) for i in range(n))
        x = x_new
        if diff < tol:
            break
    return x


def label_propagation_communities(n, adj, weight_key=True, max_iter=50):
    # Simple weighted label propagation
    labels = list(range(n))
    for _ in range(max_iter):
        changed = False
        nodes = list(range(n))
        random.shuffle(nodes)
        for i in nodes:
            score = defaultdict(float)
            for j, w in adj[i]:
                score[labels[j]] += (w if weight_key else 1.0)
            if not score:
                continue
            best_label = max(score.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if best_label != labels[i]:
                labels[i] = best_label
                changed = True
        if not changed:
            break
    # relabel communities to 0..K-1
    remap = {}
    next_id = 0
    for lab in labels:
        if lab not in remap:
            remap[lab] = next_id
            next_id += 1
    return {i: remap[labels[i]] for i in range(n)}


def participation_coefficients(n, adj, partition):
    # adj with weights 'w' on edges; partition: dict node->comm
    part = [0.0] * n
    for i in range(n):
        k_i = 0.0
        by_comm = defaultdict(float)
        for j, w in adj[i]:
            k_i += w
            by_comm[partition.get(j, -1)] += w
        if k_i <= 0:
            part[i] = 0.0
        else:
            s = 0.0
            for c, wsum in by_comm.items():
                frac = wsum / k_i
                s += frac * frac
            part[i] = 1.0 - s
    return part
