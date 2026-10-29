"""Round 1 annotation analysis: every number in the report comes from here.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/analyze_round1.py --through-week 2

Fetches all responses from the live database (read-only, via wrangler) unless --responses points at a saved
export, then writes one JSON dataset per report section to data/annotators/report/. The dashboard draws
straight from those files, so nothing is tallied by hand.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1] / "annotation_app"
sys.path.insert(0, str(APP))
from extract import extract_paper  # noqa: E402

PAPERS_DIR = HERE.parent / "Annotator-Test"
OUT = HERE / "report"
# Test, pilot and staff usernames are private: kept in local_accounts.json next to this file (not in git).
_ACCOUNTS = json.loads((HERE / "local_accounts.json").read_text(encoding="utf-8"))
TEST_ACCOUNTS = set(_ACCOUNTS["test_accounts"])
STAFF_ACCOUNTS = list(_ACCOUNTS["staff_accounts"])
BREAK_MINUTES = 60          # gaps longer than this between finished analyses count as breaks
SETUP_MINUTES = 30          # untimed source review + first analysis, from the pilot
QUESTIONS = {"claim_alignment": "Tests the claim", "method_validity": "Method defensible",
             "restriction_compliance": "Follows Task 2 restriction"}
ANSWERS = ["Yes", "Unclear", "Insufficient information", "No"]
VERDICTS = ["Yes, all agree", "Yes, majority", "Unclear", "Insufficient information", "No, majority", "No, all agree", "Split"]


def fetch_responses() -> list[dict]:
    command = ["npx", "--yes", "wrangler", "d1", "execute", "robustness-annotations", "--remote", "--json",
               "--command", "SELECT paper_id, annotator, analysis_id, payload, updated_at FROM responses"]
    for attempt in range(3):  # Cloudflare occasionally returns a transient authorization error
        result = subprocess.run(command, cwd=APP / "deployment" / "cloudflare", capture_output=True, text=True, timeout=180)
        try:
            return json.loads(result.stdout)[0]["results"]
        except (json.JSONDecodeError, KeyError, IndexError):
            time.sleep(3)
    raise SystemExit(f"Could not read responses from D1:\n{result.stdout[-500:]}\n{result.stderr[-500:]}")


def run_label(analysis_id: str) -> str:
    run, task = analysis_id.split(":")
    return f"Run {re.search(r'(\d+)$', run).group(1).lstrip('0')} · Task {task[-1]}"


def unify(values: list[str]) -> tuple[str | None, str | None]:
    """Majority label and how strong it is ('all agree', 'majority', or 'split')."""
    values = [v for v in values if v]
    if not values:
        return None, None
    top, n = Counter(values).most_common(1)[0]
    if n == len(values):
        return top, "all agree"
    if n > len(values) / 2:
        return top, "majority"
    return "Split", "split"


def verdict(label: str | None, strength: str | None) -> str | None:
    if label is None:
        return None
    if label == "Split":
        return "Split"
    if label in ("Yes", "No") and strength:
        return f"{label}, {strength}"
    return label


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--through-week", type=int, required=True, help="Last week whose papers have been released")
    parser.add_argument("--responses", type=Path, help="A saved D1 export (JSON) instead of fetching")
    args = parser.parse_args()

    rows = json.loads(args.responses.read_text())[0]["results"] if args.responses else fetch_responses()
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    plan = plan[plan.Week <= args.through_week]
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}

    assigned, packets = [], {}
    for _, r in plan.iterrows():
        packets[r["Paper ID"]] = extract_paper(PAPERS_DIR / r["Paper ID"])
        for column in ("Code reviewer 1", "Code reviewer 2", "Annotator(s)"):
            for user in re.findall(r"\(([a-z]{2}-[a-z0-9]+)\)", str(r[column])):
                assigned.append({"week": int(r.Week), "paper_id": r["Paper ID"], "user": user})

    responses = [r for r in rows if r["annotator"] not in TEST_ACCOUNTS and r["paper_id"] in packets]
    done = []
    for r in responses:
        payload = json.loads(r["payload"])
        if r["analysis_id"] != "_paper_review" and payload.get("part4_submitted"):
            done.append({"paper_id": r["paper_id"], "paper": r["paper_id"].split("_")[0], "analysis_id": r["analysis_id"],
                         "user": r["annotator"], "reviewer": who.get(r["annotator"], r["annotator"]),
                         "role": "Code reviewer" if r["annotator"].startswith("cr-") else "Annotator",
                         "at": datetime.fromisoformat(r["updated_at"]), "p": payload})
    if not done:
        raise SystemExit("No completed ratings yet.")
    OUT.mkdir(exist_ok=True)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def write(name: str, data: list[dict]) -> None:
        (OUT / f"{name}.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")

    # Progress per reviewer and paper
    progress = []
    for a in assigned:
        mine = [r for r in responses if r["paper_id"] == a["paper_id"] and r["annotator"] == a["user"]]
        total = packets[a["paper_id"]]["analysis_count"]
        n = sum(1 for d in done if d["paper_id"] == a["paper_id"] and d["user"] == a["user"])
        progress.append({"week": a["week"], "paper": a["paper_id"].split("_")[0], "reviewer": who.get(a["user"], a["user"]),
                         "role": "Code reviewer" if a["user"].startswith("cr-") else "Annotator", "done": n, "total": total,
                         "status": "Done" if n >= total else "In progress" if mine else "Not started",
                         "last_activity": max((r["updated_at"] for r in mine), default="")[:16]})
    write("progress", progress)

    # Answers to the Part 2 questions by paper
    part2 = []
    for paper, group in pd.DataFrame(done).groupby("paper"):
        for key, question in QUESTIONS.items():
            answers = [d["p"].get(key) for d in group.to_dict("records") if d["p"].get(key)]
            for answer in ANSWERS:
                part2.append({"paper": paper, "question": question, "answer": answer, "count": answers.count(answer),
                              "share": round(answers.count(answer) / len(answers), 4) if answers else 0})
    write("part2", part2)

    # 1–5 rating distributions
    ratings = []
    for key, item in (("implementation_fidelity", "Code fidelity"), ("conclusion_validity", "Conclusion justified")):
        scores = Counter(int(d["p"][key]) for d in done if str(d["p"].get(key, "")).isdigit())
        ratings += [{"item": item, "score": s, "count": scores.get(s, 0)} for s in range(1, 6)]
    write("ratings", ratings)

    # Reviewer patterns, with time estimated from finish times
    reviewers = []
    for (reviewer, paper), group in pd.DataFrame(done).groupby(["reviewer", "paper"]):
        records = group.sort_values("at").to_dict("records")
        gaps = [(b["at"] - a["at"]).total_seconds() / 60 for a, b in zip(records, records[1:])]
        worked = [g for g in gaps if g <= BREAK_MINUTES]
        per = st.median(worked) if worked else None
        method = [r["p"].get("method_validity") for r in records]
        words = [len(str(r["p"].get(k) or "").split()) for r in records
                 for k in ("claim_alignment_explanation", "method_validity_explanation", "conclusion_validity_explanation")]
        reviewers.append({"reviewer": reviewer, "paper": paper, "role": records[0]["role"], "ratings": len(records),
                          "method_yes": method.count("Yes"), "method_yes_share": round(method.count("Yes") / len(method), 4),
                          "avg_words": round(st.mean(words), 1),
                          "minutes_per_analysis": round(per, 1) if per is not None else None,
                          "est_hours": round((sum(worked) + SETUP_MINUTES + (per or 0)) / 60, 1) if per is not None else None})
    write("reviewers", reviewers)

    # Unified label per analysis
    unified, agreement_counts = [], Counter()
    for paper_id, packet in packets.items():
        for analysis in packet["analyses"]:
            ratings_here = [d["p"] for d in done if d["paper_id"] == paper_id and d["analysis_id"] == analysis["id"]]
            if not ratings_here:
                continue
            claim, claim_strength = unify([p.get("claim_alignment") for p in ratings_here])
            method, method_strength = unify([p.get("method_validity") for p in ratings_here])
            numbers = {}
            for key in ("implementation_fidelity", "conclusion_validity"):
                vals = [int(p[key]) for p in ratings_here if str(p.get(key, "")).isdigit()]
                numbers[key] = (st.median(vals), max(vals) - min(vals), len(vals)) if vals else (None, None, 0)
            unified.append({"paper": paper_id.split("_")[0], "analysis": run_label(analysis["id"]), "reviewers": len(ratings_here),
                            "claim": verdict(claim, claim_strength), "method": verdict(method, method_strength),
                            "code_median": numbers["implementation_fidelity"][0], "code_spread": numbers["implementation_fidelity"][1],
                            "conclusion_median": numbers["conclusion_validity"][0], "conclusion_spread": numbers["conclusion_validity"][1],
                            "agent_conclusion": (analysis["execution"]["conclusion"] or {}).get("conclusion_class")})
            if len(ratings_here) >= 2:
                for key, label in (("claim_alignment", "Tests the claim: all agree"), ("method_validity", "Method defensible: all agree")):
                    agreement_counts[(label, "total")] += 1
                    agreement_counts[(label, "agree")] += len({p.get(key) for p in ratings_here}) == 1
                for key, label, n in (("implementation_fidelity", "Code fidelity: within 1 point", numbers["implementation_fidelity"]),
                                      ("conclusion_validity", "Conclusion: within 1 point", numbers["conclusion_validity"])):
                    if n[2] >= 2:
                        agreement_counts[(label, "total")] += 1
                        agreement_counts[(label, "agree")] += n[1] <= 1
    write("unified", unified)
    labels = ["Tests the claim: all agree", "Method defensible: all agree", "Code fidelity: within 1 point", "Conclusion: within 1 point"]
    write("agreement", [{"measure": m, "agree": agreement_counts[(m, "agree")], "total": agreement_counts[(m, "total")],
                         "share": round(agreement_counts[(m, "agree")] / agreement_counts[(m, "total")], 4) if agreement_counts[(m, "total")] else None}
                        for m in labels])
    verdict_counts = Counter((u["paper"], u["method"]) for u in unified)
    write("unified_summary", [{"paper": p, "verdict": v, "count": verdict_counts.get((p, v), 0)}
                              for p in sorted({u["paper"] for u in unified}) for v in VERDICTS])

    # Comments worth reading (skip "none"/"n/a"-style replies)
    comments = [{"paper": d["paper"], "analysis": run_label(d["analysis_id"]), "reviewer": d["reviewer"],
                 "comment": str(d["p"].get("additional_comments")).strip()}
                for d in done if len(str(d["p"].get("additional_comments") or "").split()) >= 6]
    write("comments", comments)

    method_all = [d["p"].get("method_validity") for d in done]
    conclusion_all = [int(d["p"]["conclusion_validity"]) for d in done if str(d["p"].get("conclusion_validity", "")).isdigit()]
    write("overview", [{"as_of": as_of, "through_week": args.through_week, "ratings": len(done),
                        "papers_with_ratings": len({d["paper_id"] for d in done}), "papers_released": len(packets),
                        "reviewers_done": sum(1 for p in progress if p["status"] == "Done"), "reviewer_assignments": len(progress),
                        "method_yes_share": round(method_all.count("Yes") / len(method_all), 4),
                        "conclusion_mean": round(st.mean(conclusion_all), 2),
                        "analyses_with_all_agree_method": agreement_counts[("Method defensible: all agree", "agree")],
                        "analyses_rated_by_two_plus": agreement_counts[("Method defensible: all agree", "total")]}])
    print(f"Wrote {len([p for p in OUT.glob('*.json') if not p.name.startswith('_')])} datasets to {OUT} ({len(done)} ratings, as of {as_of}).")


if __name__ == "__main__":
    main()
