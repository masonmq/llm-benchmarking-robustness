"""Live progress per paper and reviewer for the chosen weeks (finished analyses / total). Read-only; changes no report.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/progress.py --weeks 1,2
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter

import pandas as pd

from analyze_round1 import HERE, PAPERS_DIR, TEST_ACCOUNTS, extract_paper, fetch_responses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", required=True)
    weeks = {int(w) for w in parser.parse_args().weeks.split(",")}
    rows = fetch_responses()
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}
    done, last = Counter(), {}
    for r in rows:
        if r["annotator"] in TEST_ACCOUNTS or r["analysis_id"] == "_paper_review":
            continue
        k = (r["paper_id"], r["annotator"])
        done[k] += bool(json.loads(r["payload"]).get("part4_submitted"))
        last[k] = max(last.get(k, ""), r.get("updated_at") or "")
    for _, p in plan[plan.Week.isin(weeks)].iterrows():
        pid = p["Paper ID"]
        n = extract_paper(PAPERS_DIR / pid)["analysis_count"]
        users = re.findall(r"\(([a-z]{2}-[a-z0-9]+)\)", " ".join(str(p[c]) for c in ("Code reviewer 1", "Code reviewer 2", "Annotator(s)")))
        print(f"Week {p.Week} {pid.split('_')[0]} ({n} analyses): " + "; ".join(
            f"{who.get(u, u)} {u[:2]} {done[(pid, u)]}/{n}"
            + (f" (last {last[(pid, u)][5:16]})" if (pid, u) in last and done[(pid, u)] < n else "") for u in users))


if __name__ == "__main__":
    main()
