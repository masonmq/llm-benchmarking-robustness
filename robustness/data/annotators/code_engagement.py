"""How deeply each code reviewer engages with the code, from their Part 3 (code fidelity) explanations only. Read-only.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/code_engagement.py --weeks 1,2,3

Signals per finished analysis: explanation length; quoting or naming specific code (code syntax, snake_case or dotted
identifiers, operators like <= or ==); naming a concrete code-vs-plan discrepancy; saying they ran the code; and
whether they found the main Part 3 issue (the decision rule differing from the plan). These are rough text signals,
meant to shortlist people for a closer read, not to score quality.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
from collections import defaultdict

import pandas as pd

from analyze_round1 import HERE, TEST_ACCOUNTS, fetch_responses

CODE_SYNTAX = re.compile(r"(==|<=|>=|!=|\belif\b|\bdef\b|\breturn\b|\bpd\.|\bnp\.|\w+\(|\[[^\]]*\]|=\s*\w)")
IDENTIFIER = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")  # snake_case names such as conclusion_class, low_p
DISCREPANCY = re.compile(r"\b(not (specified|mentioned|stated|in the plan|consistent)|inconsistent|contradict|differs?|instead of|"
                         r"rather than|does not match|doesn't match|omits?|missing|but the code|the code (uses|classifies|treats|considers))\b", re.I)
RAN_CODE = re.compile(r"\b(I ran|when I run|my run|running the code|re-?ran|I executed|my (own )?estimate)\b", re.I)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", required=True)
    weeks = {int(w) for w in parser.parse_args().weeks.split(",")}
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    papers = set(plan[plan.Week.isin(weeks)]["Paper ID"])
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}
    with (HERE / "part3_theme_codes.csv").open() as f:
        decision_rule = {(r["paper_id"], r["analysis_id"], r["annotator"]) for r in csv.DictReader(f) if "decision_rule" in r["themes"]}

    stats = defaultdict(lambda: defaultdict(list))
    for r in fetch_responses():
        p = json.loads(r["payload"])
        if (r["paper_id"] not in papers or r["annotator"] in TEST_ACCOUNTS or not r["annotator"].startswith("cr-")
                or r["analysis_id"] == "_paper_review" or not p.get("part4_submitted")):
            continue
        text = " ".join(str(p.get("implementation_fidelity_explanation") or "").split())
        s = stats[r["annotator"]]
        s["papers"].append(r["paper_id"].split("_")[0])
        s["words"].append(len(text.split()))
        s["quotes_code"].append(bool(CODE_SYNTAX.search(text) or IDENTIFIER.search(text)))
        s["discrepancy"].append(bool(DISCREPANCY.search(text)))
        s["ran_code"].append(bool(RAN_CODE.search(text)))
        s["below5"].append(str(p.get("implementation_fidelity")) not in ("5",))
        s["decision_rule"].append((r["paper_id"], r["analysis_id"], r["annotator"]) in decision_rule)

    rows = []
    for user, s in stats.items():
        n = len(s["words"])
        rows.append({"reviewer": who.get(user, user), "analyses": n, "papers": ", ".join(sorted(set(s["papers"]))),
                     "median_words": round(st.median(s["words"])),
                     "quotes_or_names_code": f"{sum(s['quotes_code'])}/{n}",
                     "names_discrepancy": f"{sum(s['discrepancy'])}/{n}",
                     "ran_code": sum(s["ran_code"]), "rated_below_5": f"{sum(s['below5'])}/{n}",
                     "found_decision_rule_issue": sum(s["decision_rule"]),
                     "_score": sum(s["quotes_code"]) / n + sum(s["discrepancy"]) / n})
    out = pd.DataFrame(rows).sort_values("_score", ascending=False).drop(columns="_score")
    pd.set_option("display.width", 250)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
