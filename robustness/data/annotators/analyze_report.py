"""Data for the simplified annotation report: one analysis per review part, for the chosen weeks.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/analyze_report.py --weeks 1

Part 2 (the proposed analysis) gets a deeper dive: combined verdicts, agreement, and the themes behind every
non-"Yes" answer, from the hand coding in part2_theme_codes.csv (one row per coded explanation). The script
checks that the coding covers exactly the non-"Yes" answers in the data, so a new response can't slip through
uncoded. Writes rpt_*.json datasets to data/annotators/report/.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analyze_round1 import (HERE, OUT, PAPERS_DIR, TEST_ACCOUNTS, extract_paper, fetch_responses, run_label, unify, verdict)

QUESTIONS = [("claim_alignment", "Tests the claim"), ("method_validity", "Method defensible"),
             ("restriction_compliance", "Follows the Task 2 restriction")]
VERDICTS = ["Yes, all agree", "Yes, majority", "Unclear", "Insufficient information", "No, majority", "No, all agree", "Split"]
THEMES = {  # code -> (label, what reviewers pointed to)
    "changes_question": ("Tests a different outcome or comparison than the claim", "E.g. manufacturing GDP growth instead of total GDP growth; bias vs. no-bias groups instead of bias strength; comparing correlations, or a subgroup correlation, instead of testing the interaction; an interaction without the simple slopes the claim needs; a single average effect instead of the group comparison the claim makes; a median instead of a mean effect."),
    "discards_information": ("Continuous variable split into groups", "Mean splits, binning, or keeping only participants below the mean, instead of using the variable as continuous."),
    "model_assumptions": ("Model assumptions don't fit the data", "Repeated decisions per participant treated as independent (no random effects or clustered SEs); linear regression for a count or binary outcome (Poisson or logistic suggested); a non-parametric test requested."),
    "departs_from_original": ("Model not used in the original paper", "Fixed effects combined with propensity score matching; overlap weighting."),
    "inconsistent": ("Plan contradicts itself", "The plan's description doesn't match its own variables, model formula or preprocessing (all visible in Part 2), e.g. it says manufacturing GDP growth but lists total GDP growth; it says a -1 SD cut-off but the model uses the mean; its preprocessing builds the outcome from trial position."),
    "unfamiliar_method": ("Reviewer unfamiliar with the model", "Ordered-score trend test; non-parametric trend test."),
    "data_limitation": ("Limitation of the original study", "Too few participants per cell to control order effects; observational cross-sectional data and unclear measures for a causal claim. About the original data, not the agent's choice."),
    "unjustified_choice": ("Method choice not justified", "An unusual approach without a stated reason, e.g. a non-parametric binned trend test, or a weighting design."),
    "restriction_not_followed": ("Task 2 restriction not followed", "The model leaves out something the restriction requires, e.g. required interaction terms."),
    "omitted_control": ("Leaves out a control the original authors considered important", "E.g. dropping attitude extremity, which the authors controlled for because it correlates with both predictors."),
    "unclear_plan": ("Plan not clear enough to judge", "The reviewer could not tell whether the specification matches the claim, or a variable is not explained."),
}
THEMES_P3 = {  # Part 3 (code fidelity) code -> (label, what reviewers pointed to); coded from Part 3 explanations only
    "decision_rule": ("Code's decision rule differs from the plan", "The code classifies the result differently from the plan's rule, e.g. p between .05 and .055 counted as support instead of borderline; extra confidence-interval cut-offs; one-sided or two-sided p accepted (effective alpha .10)."),
    "unstated_choice": ("Code makes a choice the plan doesn't state", "E.g. a one-sided test, bootstrapped confidence intervals, or coding one answer option as correct for everyone."),
    "cannot_verify": ("Reviewer could not fully verify the code", "Custom estimation code (GMM), covariance handling or weights too complex to check in the time available."),
    "overly_complex": ("Implementation more complicated than needed", "Custom code where an existing library implementation would do."),
    "minor_technical": ("Minor technical or reporting issue", "A hard-coded data path; an exclusion missing from the sample-flow table."),
    "no_issue_stated": ("No issue stated", "Rated 4 without naming a problem."),
}
MIN_ANALYSES = 3  # a theme is reported only if it appears in at least this many different analyses
MIN_REVIEWERS = 2  # ... and was raised by at least this many different reviewers
QUOTE_CHARS = 260


def shorten(text: str) -> str:
    text = " ".join(str(text).split())
    if len(text) <= QUOTE_CHARS:
        return text
    cut = text[:QUOTE_CHARS].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + " …"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", required=True, help="Comma-separated weeks to include, e.g. 1 or 1,2")
    parser.add_argument("--responses", type=Path, help="A saved D1 export (JSON) instead of fetching")
    parser.add_argument("--part2-min-reviewers", type=int, default=1,
                        help="Use only analyses with at least this many finished reviews for Part 2 (verdicts, themes, headline)")
    args = parser.parse_args()
    weeks = {int(w) for w in args.weeks.split(",")}

    rows = json.loads(args.responses.read_text())[0]["results"] if args.responses else fetch_responses()
    plan = pd.read_excel(HERE / "round1_assignment.xlsx", sheet_name="Round 1 - by paper")
    plan = plan[plan.Week.isin(weeks)]
    roster = pd.read_excel(HERE / "annotator_roster.xlsx")
    who = {r.username: str(r["name"]).replace("ID ", "ID") for _, r in roster.iterrows() if isinstance(r["name"], str)}
    packets = {pid: extract_paper(PAPERS_DIR / pid) for pid in plan["Paper ID"]}
    assignments = sum(len(__import__("re").findall(r"\(([a-z]{2}-[a-z0-9]+)\)", " ".join(str(r[c]) for c in ("Code reviewer 1", "Code reviewer 2", "Annotator(s)"))))
                      for _, r in plan.iterrows())

    done = []
    for r in rows:
        payload = json.loads(r["payload"])
        if (r["paper_id"] in packets and r["annotator"] not in TEST_ACCOUNTS and r["analysis_id"] != "_paper_review"
                and payload.get("part4_submitted")):
            done.append({"paper_id": r["paper_id"], "paper": r["paper_id"].split("_")[0], "analysis_id": r["analysis_id"],
                         "user": r["annotator"], "reviewer": who.get(r["annotator"], r["annotator"]), "p": payload})
    if not done:
        raise SystemExit("No completed ratings for these weeks.")
    OUT.mkdir(exist_ok=True)

    def write(name: str, data: list[dict]) -> None:
        (OUT / f"rpt_{name}.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")

    agent = {(pid, a["id"]): (a["execution"]["conclusion"] or {}).get("conclusion_class") for pid, pk in packets.items() for a in pk["analyses"]}
    by_analysis: dict[tuple, list[dict]] = {}
    for d in done:
        by_analysis.setdefault((d["paper_id"], d["analysis_id"]), []).append(d)

    # Part 2 uses only analyses with enough finished reviews (e.g. all three), so every verdict has the same footing.
    p2_analyses = {k: ds for k, ds in by_analysis.items() if len(ds) >= args.part2_min_reviewers}

    # Part 2: combined verdict per analysis and question
    verdicts, per_paper, agreement = Counter(), Counter(), []
    for key, label in QUESTIONS:
        agree = total = 0
        for (pid, aid), ds in p2_analyses.items():
            answers = [d["p"].get(key) for d in ds if d["p"].get(key)]
            if not answers:
                continue  # e.g. the restriction question on Task 1 analyses
            v = verdict(*unify(answers))
            verdicts[(label, v)] += 1
            if key in ("claim_alignment", "method_validity"):
                per_paper[(label, pid.split("_")[0], v)] += 1
            if len(answers) >= 2:
                total += 1
                agree += len(set(answers)) == 1
        agreement.append({"question": label, "all_agree": agree, "analyses": total, "share": round(agree / total, 4) if total else None})
    write("p2_verdicts", [{"question": q, "verdict": v, "count": verdicts.get((q, v), 0)} for _, q in QUESTIONS for v in VERDICTS])
    write("p2_by_paper", [{"question": q, "paper": p, "verdict": v, "count": per_paper.get((q, p, v), 0)}
                          for _, q in QUESTIONS[:2] for p in sorted({k[0].split("_")[0] for k in p2_analyses}) for v in VERDICTS])
    write("p2_agreement", agreement)

    # Part 2: themes behind every non-"Yes" answer
    with (HERE / "part2_theme_codes.csv").open() as f:
        codes = {(r["paper_id"], r["analysis_id"], r["annotator"], r["question"]): r["themes"].split(";") for r in csv.DictReader(f)}
    non_yes_all = {(d["paper_id"], d["analysis_id"], d["user"], key): d for d in done for key, _ in QUESTIONS
                   if d["p"].get(key) and d["p"].get(key) != "Yes"}
    uncoded, stale = sorted(set(non_yes_all) - set(codes)), sorted(set(codes) - set(non_yes_all))
    if uncoded or stale:
        raise SystemExit(f"Theme coding is out of date. Uncoded answers: {uncoded}\nCodes with no matching answer: {stale}")
    # Coding covers every answer; reporting uses only the Part 2 analyses.
    non_yes = {k: d for k, d in non_yes_all.items() if (k[0], k[1]) in p2_analyses}
    codes = {k: v for k, v in codes.items() if k in non_yes}
    # Part 2: when a reviewer answered "Unclear" or "Insufficient information", what did the other reviewers of
    # the same analysis answer to the same question?
    others, unsure_by, unsure_papers = Counter(), defaultdict(set), defaultdict(Counter)
    for (pid, aid, user, key), d in non_yes.items():
        own = d["p"][key]
        if own not in ("Unclear", "Insufficient information"):
            continue
        others[(own, dict(QUESTIONS)[key], "_answers")] += 1
        unsure_by[(own, dict(QUESTIONS)[key])].add(d["reviewer"])
        unsure_papers[(own, dict(QUESTIONS)[key])][d["paper"]] += 1
        for o in by_analysis[(pid, aid)]:
            if o["user"] != user and o["p"].get(key):
                others[(own, dict(QUESTIONS)[key], o["p"][key])] += 1
    write("p2_unsure_others", [{"own_answer": own, "question": q, "other_answer": other, "count": n}
                               for (own, q, other), n in sorted(others.items()) if other != "_answers"]
          + [{"own_answer": own, "question": q, "other_answer": "(answers)", "count": n,
              "reviewers": ", ".join(sorted(unsure_by[(own, q)])),
              "papers": ", ".join(f"{p} {k}" for p, k in sorted(unsure_papers[(own, q)].items()))}
             for (own, q, other), n in sorted(others.items()) if other == "_answers"])

    theme_rows, quotes = [], []
    unknown = {c for themes in codes.values() for c in themes} - set(THEMES)
    if unknown:
        raise SystemExit(f"Unknown theme codes in part2_theme_codes.csv: {sorted(unknown)}")
    for code, (label, description) in THEMES.items():
        hits = [k for k, themes in codes.items() if code in themes]
        n_analyses = len({(k[0], k[1]) for k in hits})
        n_reviewers = len({k[2] for k in hits})
        if n_analyses < MIN_ANALYSES or n_reviewers < MIN_REVIEWERS:
            print(f"Not reported ({n_analyses} analyses, {n_reviewers} reviewers): {label}")
            continue
        theme_rows.append({"theme": label, "description": description, "answers": len(hits), "analyses": n_analyses,
                           "on_claim": sum(1 for k in hits if k[3] == "claim_alignment"),
                           "on_method": sum(1 for k in hits if k[3] == "method_validity"),
                           "reviewers": len({k[2] for k in hits}), "papers": len({k[0] for k in hits})})
        # Rank examples so each theme's first quotes come from different reviewers (rank 1 = first from each reviewer).
        seen: Counter = Counter()
        for k in sorted(hits, key=lambda k: (k[0], k[1], k[2], k[3])):
            d = non_yes[k]
            seen[k[2]] += 1
            quotes.append({"theme": label, "paper": d["paper"], "analysis": run_label(d["analysis_id"]), "reviewer": d["reviewer"],
                           "question": dict(QUESTIONS)[k[3]], "answer": d["p"][k[3]], "rank": seen[k[2]],
                           "quote": shorten(d["p"].get(k[3] + "_explanation"))})
    write("p2_themes", sorted(theme_rows, key=lambda r: (-r["analyses"], -r["answers"])))
    write("p2_quotes", quotes)

    # Part 3: themes behind every code-fidelity rating below 5, coded separately in part3_theme_codes.csv (only from
    # Part 3 explanations, which reviewers write after seeing the code). Same reporting rule as Part 2.
    with (HERE / "part3_theme_codes.csv").open() as f:
        codes3 = {(r["paper_id"], r["analysis_id"], r["annotator"], r["question"]): r["themes"].split(";") for r in csv.DictReader(f)}
    below5 = {(d["paper_id"], d["analysis_id"], d["user"], "implementation_fidelity"): d for d in done
              if str(d["p"].get("implementation_fidelity", "")).isdigit() and int(d["p"]["implementation_fidelity"]) < 5}
    uncoded, stale = sorted(set(below5) - set(codes3)), sorted(set(codes3) - set(below5))
    if uncoded or stale:
        raise SystemExit(f"Part 3 theme coding is out of date. Uncoded answers: {uncoded}\nCodes with no matching answer: {stale}")
    unknown = {c for themes in codes3.values() for c in themes} - set(THEMES_P3)
    if unknown:
        raise SystemExit(f"Unknown theme codes in part3_theme_codes.csv: {sorted(unknown)}")
    theme_rows3, quotes3 = [], []
    for code, (label, description) in THEMES_P3.items():
        hits = [k for k, themes in codes3.items() if code in themes]
        n_analyses, n_reviewers = len({(k[0], k[1]) for k in hits}), len({k[2] for k in hits})
        if n_analyses < MIN_ANALYSES or n_reviewers < MIN_REVIEWERS:
            print(f"Part 3 not reported ({n_analyses} analyses, {n_reviewers} reviewers): {label}")
            continue
        theme_rows3.append({"theme": label, "description": description, "answers": len(hits), "analyses": n_analyses,
                            "reviewers": n_reviewers, "papers": len({k[0] for k in hits})})
        seen = Counter()
        for k in sorted(hits):
            d = below5[k]
            seen[k[2]] += 1
            quotes3.append({"theme": label, "paper": d["paper"], "analysis": run_label(d["analysis_id"]), "reviewer": d["reviewer"],
                            "question": "Code fidelity", "answer": d["p"]["implementation_fidelity"], "rank": seen[k[2]],
                            "quote": shorten(d["p"].get("implementation_fidelity_explanation"))})
    write("p3_themes", sorted(theme_rows3, key=lambda r: (-r["analyses"], -r["answers"])))
    write("p3_quotes", quotes3)

    # Part 3: code fidelity, by paper
    p3, p3_summary = [], []
    for paper in sorted({d["paper"] for d in done}):
        scores = [int(d["p"]["implementation_fidelity"]) for d in done if d["paper"] == paper and str(d["p"].get("implementation_fidelity", "")).isdigit()]
        counts = Counter(scores)
        p3 += [{"paper": paper, "score": s, "count": counts.get(s, 0)} for s in range(1, 6)]
        p3_summary.append({"paper": paper, "ratings": len(scores), "mean": round(st.mean(scores), 2) if scores else None,
                           "share_4_or_5": round(sum(s >= 4 for s in scores) / len(scores), 4) if scores else None})
    write("p3_scores", p3)
    write("p3_summary", p3_summary)

    # Part 4: conclusion justified, by what the agent concluded
    p4 = Counter((agent[(d["paper_id"], d["analysis_id"])], int(d["p"]["conclusion_validity"])) for d in done if str(d["p"].get("conclusion_validity", "")).isdigit())
    write("p4_scores", [{"agent_conclusion": c, "score": s, "count": p4.get((c, s), 0)} for c in sorted({k[0] for k in p4}) for s in range(1, 6)])
    conclusions = [int(d["p"]["conclusion_validity"]) for d in done if str(d["p"].get("conclusion_validity", "")).isdigit()]

    code_scores = {k: [int(d["p"]["implementation_fidelity"]) for d in ds if str(d["p"].get("implementation_fidelity", "")).isdigit()]
                   for k, ds in p2_analyses.items()}
    code_scores = {k: v for k, v in code_scores.items() if v}

    def high_majority(key: str) -> tuple[int, int]:
        """(analyses where more than half the ratings are 4 or 5, analyses with any rating) for a 1-5 question.
        Uses the same analyses as Part 2, so the headline compares all four questions on one set of analyses."""
        high = total = 0
        for ds in p2_analyses.values():
            scores = [int(d["p"][key]) for d in ds if str(d["p"].get(key, "")).isdigit()]
            if scores:
                total += 1
                high += sum(x >= 4 for x in scores) * 2 > len(scores)
        return high, total

    write("overview", [{"as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "weeks": args.weeks,
                        "papers": len(packets), "analyses": sum(pk["analysis_count"] for pk in packets.values()),
                        "ratings": len(done), "reviewer_assignments": assignments,
                        "reviewers_finished": sum(1 for pid in packets for u in {d["user"] for d in done if d["paper_id"] == pid}
                                                  if sum(1 for d in done if d["paper_id"] == pid and d["user"] == u) >= packets[pid]["analysis_count"]),
                        "non_yes_part2_answers": len(non_yes), "below5_part3_answers": len(below5),
                        "p2_analyses": len(p2_analyses), "p2_min_reviewers": args.part2_min_reviewers,
                        "conclusion_share_5": round(sum(c == 5 for c in conclusions) / len(conclusions), 4),
                        "method_all_agree": agreement[1]["all_agree"], "method_analyses": agreement[1]["analyses"],
                        # Majority-vote "Yes" (unanimous or majority) per Part 2 question
                        "claim_yes_majority": verdicts[("Tests the claim", "Yes, all agree")] + verdicts[("Tests the claim", "Yes, majority")],
                        "method_yes_majority": verdicts[("Method defensible", "Yes, all agree")] + verdicts[("Method defensible", "Yes, majority")],
                        # Parts 3 and 4: analyses where a majority (more than half) of reviewers rated 4 or 5
                        "code_high_majority": high_majority("implementation_fidelity")[0], "code_analyses": high_majority("implementation_fidelity")[1],
                        # Code has only 2 reviewers per analysis, so "most" would mean both; use the per-analysis average instead.
                        "code_avg4": sum(st.mean(v) >= 4 for v in code_scores.values()),
                        "code_mean_p2": round(st.mean([x for v in code_scores.values() for x in v]), 2),
                        "conclusion_high_majority": high_majority("conclusion_validity")[0], "conclusion_analyses": high_majority("conclusion_validity")[1],
                        # Analyses by number of reviewers who finished them
                        "analyses_3_reviewers": sum(len(ds) == 3 for ds in by_analysis.values()),
                        "analyses_2_reviewers": sum(len(ds) == 2 for ds in by_analysis.values()),
                        "analyses_other_reviewers": sum(len(ds) not in (2, 3) for ds in by_analysis.values())}])
    print(f"Report data for week(s) {args.weeks}: {len(done)} ratings, {len(non_yes)} coded Part 2 answers.")


if __name__ == "__main__":
    main()
