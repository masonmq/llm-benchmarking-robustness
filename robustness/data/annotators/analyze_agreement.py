"""Inter-reviewer agreement for the chosen weeks: Krippendorff's alpha, raw agreement, and agreement by reviewer and role.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/analyze_agreement.py --weeks 1 [--responses report/_responses.json]

Units are analyses; raters are the reviewers who finished that analysis. Part 2 questions are nominal (Yes / No / Unclear /
Insufficient information), also collapsed to Yes vs. not Yes. Parts 3 and 4 are 1-5 ratings (ordinal alpha, plus exact and
within-1 agreement). 95% intervals are a bootstrap over analyses. Writes report/agreement_week<weeks>.json.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from itertools import combinations

import pandas as pd

from analyze_round1 import HERE, OUT, TEST_ACCOUNTS, fetch_responses

QUESTIONS = [("claim_alignment", "Tests the claim", "nominal"), ("method_validity", "Method defensible", "nominal"),
             ("restriction_compliance", "Follows the Task 2 restriction", "nominal"),
             ("implementation_fidelity", "Code fidelity (Part 3)", "ordinal"), ("conclusion_validity", "Conclusion justified (Part 4)", "ordinal")]
BOOT = 2000


def alpha(units: list[list], level: str) -> float | None:
    """Krippendorff's alpha from the coincidence matrix; units with fewer than 2 values are ignored."""
    units = [u for u in units if len(u) >= 2]
    o = Counter()
    for u in units:
        for a, b in ((u[i], u[j]) for i in range(len(u)) for j in range(len(u)) if i != j):
            o[(a, b)] += 1 / (len(u) - 1)
    n_c = Counter()
    for (a, _), w in o.items():
        n_c[a] += w
    n = sum(n_c.values())
    cats = sorted(n_c)
    if n < 2 or len(cats) < 2:
        return None
    if level == "nominal":
        d = lambda a, b: float(a != b)
    else:  # ordinal: squared distance in cumulative marginal frequencies
        def d(a, b):
            lo, hi = sorted((cats.index(a), cats.index(b)))
            return (sum(n_c[cats[g]] for g in range(lo, hi + 1)) - (n_c[cats[lo]] + n_c[cats[hi]]) / 2) ** 2
    d_o = sum(w * d(a, b) for (a, b), w in o.items()) / n
    d_e = sum(n_c[a] * n_c[b] * d(a, b) for a in cats for b in cats) / (n * (n - 1))
    return 1 - d_o / d_e if d_e else None


def boot_ci(units: list[list], level: str) -> tuple[float | None, float | None]:
    rng = random.Random(0)
    vals = [alpha([rng.choice(units) for _ in units], level) for _ in range(BOOT)]
    vals = sorted(v for v in vals if v is not None)
    if len(vals) < BOOT * 0.9:
        return None, None
    return round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals)) - 1], 3)


def pair_stats(units: list[list[tuple[str, object]]], close: bool) -> tuple[int, int, int]:
    """(pairs, exact matches, matches within 1 point) over all reviewer pairs on the same analysis."""
    pairs = exact = near = 0
    for u in units:
        for (_, a), (_, b) in combinations(u, 2):
            pairs += 1
            exact += a == b
            near += close and abs(a - b) <= 1
    return pairs, exact, near


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", required=True)
    parser.add_argument("--responses", type=__import__("pathlib").Path)
    parser.add_argument("--part2-min-reviewers", type=int, default=2, help="Part 2 questions: only analyses with this many reviews")
    args = parser.parse_args()
    weeks = {int(w) for w in args.weeks.split(",")}

    rows = json.loads(args.responses.read_text())[0]["results"] if args.responses else fetch_responses()
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    papers = set(plan[plan.Week.isin(weeks)]["Paper ID"])
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}

    by_analysis: dict[tuple, list] = defaultdict(list)
    for r in rows:
        p = json.loads(r["payload"])
        if r["paper_id"] in papers and r["annotator"] not in TEST_ACCOUNTS and r["analysis_id"] != "_paper_review" and p.get("part4_submitted"):
            by_analysis[(r["paper_id"], r["analysis_id"])].append((r["annotator"], p))

    out = {"overall": [], "role_pairs": [], "reviewers": []}
    print(f"Weeks {args.weeks}: {len(by_analysis)} analyses\n")
    print(f"{'Question':34} {'units':>5} {'pairs':>5} {'exact':>6} {'±1':>6}  {'alpha':>6}  95% CI          {'alpha Yes/notYes':>16}")
    for key, label, level in QUESTIONS:
        units = []
        for (pid, aid), ds in sorted(by_analysis.items()):
            vals = [(u, int(p[key]) if level == "ordinal" else p[key]) for u, p in ds
                    if p.get(key) not in (None, "") and (level == "nominal" or str(p.get(key)).isdigit())]
            # Every question uses the same analyses (those with all reviews), so the rows of the table are comparable.
            if len(vals) >= 2 and len(ds) >= args.part2_min_reviewers:
                units.append(vals)
        values = [[v for _, v in u] for u in units]
        a = alpha(values, level)
        lo, hi = boot_ci(values, level)
        pairs, exact, near = pair_stats(units, level == "ordinal")
        binary = [[v == "Yes" for v in u] for u in values] if level == "nominal" else None
        a_bin = alpha(binary, "nominal") if binary else None
        bin_pairs = [(a1 == b1) for u in binary for a1, b1 in combinations(u, 2)] if binary else []
        dist = Counter(v for u in values for v in u)
        row = {"question": label, "level": level, "analyses": len(units), "pairs": pairs, "exact_agreement": round(exact / pairs, 3),
               "within_1": round(near / pairs, 3) if level == "ordinal" else None, "alpha": round(a, 3) if a is not None else None,
               "alpha_ci": [lo, hi], "alpha_yes_vs_not": round(a_bin, 3) if a_bin is not None else None,
               "exact_agreement_yes_vs_not": round(sum(bin_pairs) / len(bin_pairs), 3) if bin_pairs else None,
               "answer_distribution": {str(k): v for k, v in sorted(dist.items(), key=lambda kv: str(kv[0]))}}
        out["overall"].append(row)
        within = f"{row['within_1']:.0%}" if row["within_1"] is not None else ""
        print(f"{label:34} {len(units):5} {pairs:5} {row['exact_agreement']:6.0%} {within:>6}  "
              f"{(f'{a:.2f}' if a is not None else 'n/a'):>6}  [{lo}, {hi}]  {(f'{a_bin:.2f}' if a_bin is not None else ''):>16}")
        print(f"{'':34} answers: {row['answer_distribution']}")

        # Agreement by role pair (cr = code reviewer, an = annotator) and per reviewer
        role = Counter(); role_hit = Counter(); rev = Counter(); rev_hit = Counter()
        for u in units:
            for (ua, a1), (ub, b1) in combinations(u, 2):
                kind = "-".join(sorted((ua[:2], ub[:2])))
                role[kind] += 1; role_hit[kind] += a1 == b1
                for x in (ua, ub):
                    rev[x] += 1; rev_hit[x] += a1 == b1
        for kind in sorted(role):
            out["role_pairs"].append({"question": label, "pair": kind, "pairs": role[kind], "exact_agreement": round(role_hit[kind] / role[kind], 3)})
        # For 1-5 ratings: each reviewer's mean, and mean difference from the other reviewers of the same analyses
        offset = defaultdict(list); own = defaultdict(list)
        if level == "ordinal":
            for u in units:
                for x, v in u:
                    own[x].append(v)
                    offset[x].append(v - sum(w for y, w in u if y != x) / (len(u) - 1))
        for x in sorted(rev, key=lambda x: who.get(x, x)):
            out["reviewers"].append({"question": label, "reviewer": who.get(x, x), "role": x[:2], "pairs": rev[x],
                                     "exact_agreement": round(rev_hit[x] / rev[x], 3),
                                     "mean_rating": round(sum(own[x]) / len(own[x]), 2) if own[x] else None,
                                     "offset_vs_others": round(sum(offset[x]) / len(offset[x]), 2) if offset[x] else None})

    print("\nExact agreement by role pair (cr = code reviewer, an = annotator)")
    for r in out["role_pairs"]:
        print(f"  {r['question']:34} {r['pair']:6} {r['pairs']:4} pairs  {r['exact_agreement']:.0%}")
    print("\nExact agreement of each reviewer with the others on the same analyses")
    for r in out["reviewers"]:
        extra = f"  mean {r['mean_rating']:.2f}, {r['offset_vs_others']:+.2f} vs. co-reviewers" if r["mean_rating"] is not None else ""
        print(f"  {r['question']:34} {r['reviewer']:6} ({r['role']}) {r['pairs']:4} pairs  {r['exact_agreement']:.0%}{extra}")

    (OUT / f"agreement_week{args.weeks.replace(',', '-')}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
