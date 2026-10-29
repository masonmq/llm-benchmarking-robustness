"""How detailed each reviewer's written explanations are, for finished analyses in the chosen weeks (read-only).

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/explanation_depth.py --weeks 1,2

Words per finished analysis across the explanation boxes (Parts 2-4), and how many analyses mention running the code
themselves. Code reviewers answer one more part (Part 3) than annotators, so compare within role.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
from collections import defaultdict

import pandas as pd

from analyze_round1 import HERE, TEST_ACCOUNTS, fetch_responses

QUESTIONS = ["claim_alignment", "method_validity", "restriction_compliance", "implementation_fidelity", "conclusion_validity"]
RAN_CODE = re.compile(r"\b(I ran|when I run|my run|running the code|re-?ran|I executed|my (own )?estimate)\b", re.I)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", required=True)
    weeks = {int(w) for w in parser.parse_args().weeks.split(",")}
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    papers = set(plan[plan.Week.isin(weeks)]["Paper ID"])
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}

    words, ran = defaultdict(list), defaultdict(int)
    for r in fetch_responses():
        p = json.loads(r["payload"])
        if r["paper_id"] not in papers or r["annotator"] in TEST_ACCOUNTS or r["analysis_id"] == "_paper_review" or not p.get("part4_submitted"):
            continue
        text = " ".join(str(p.get(q + "_explanation") or "") for q in QUESTIONS)
        words[r["annotator"]].append(len(text.split()))
        ran[r["annotator"]] += bool(RAN_CODE.search(text))

    rows = [{"reviewer": who.get(u, u), "role": u[:2], "analyses": len(w), "median_words": round(st.median(w)),
             "mean_words": round(st.mean(w)), "mentions_running_code": ran[u]} for u, w in words.items()]
    out = pd.DataFrame(rows).sort_values(["role", "median_words"], ascending=[False, False])
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
