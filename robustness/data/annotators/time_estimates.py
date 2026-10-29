"""Rough time-on-task per reviewer and paper, from the save timestamps in the live responses (read-only).

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/time_estimates.py --weeks 1,2

The app does not time anything. Each response row keeps only its *last* save time, so we sort a reviewer's rows on a
paper and treat gaps of at most SESSION_GAP minutes between consecutive saves as working time; longer gaps are breaks.
The first analysis of each sitting (and Part 1 reading before the first save) cannot be timed, so these are lower bounds.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
from collections import defaultdict
from datetime import datetime

import pandas as pd

from analyze_round1 import HERE, TEST_ACCOUNTS, fetch_responses

SESSION_GAP = 90  # minutes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", required=True)
    weeks = {int(w) for w in parser.parse_args().weeks.split(",")}
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    papers = set(plan[plan.Week.isin(weeks)]["Paper ID"])
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}

    saves, finished, done_at = defaultdict(list), defaultdict(int), {}
    for r in fetch_responses():
        if r["paper_id"] not in papers or r["annotator"] in TEST_ACCOUNTS:
            continue
        key = (r["paper_id"].split("_")[0], r["annotator"])
        saves[key].append(datetime.fromisoformat(r["updated_at"]))
        if r["analysis_id"] != "_paper_review" and json.loads(r["payload"]).get("part4_submitted"):
            finished[key] += 1
            done_at[key] = max(done_at.get(key, ""), r["updated_at"])

    rows = []
    for (paper, user), times in sorted(saves.items()):
        times.sort()
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
        inside = [g for g in gaps if g <= SESSION_GAP]
        rows.append({"paper": paper, "reviewer": who.get(user, user), "role": user[:2], "finished": finished[(paper, user)],
                     "sittings": 1 + sum(g > SESSION_GAP for g in gaps),
                     "median_min_per_analysis": round(st.median(inside)) if inside else None,
                     "timed_hours": round(sum(inside) / 60, 1),
                     "first_save": times[0].strftime("%m-%d %H:%M"), "last_finished": (done_at.get((paper, user)) or "")[5:16]})
    print(pd.DataFrame(rows).to_string(index=False))
    for role in ("cr", "an"):
        meds = [r["median_min_per_analysis"] for r in rows if r["role"] == role and r["median_min_per_analysis"]]
        if meds:
            print(f"{role}: median of reviewers' typical minutes per analysis = {st.median(meds)} (n={len(meds)}, range {min(meds)}-{max(meds)})")


if __name__ == "__main__":
    main()
