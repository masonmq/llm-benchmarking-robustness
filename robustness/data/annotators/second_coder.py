"""Make (and later score) a blind second-coder sheet for the Part 2 theme coding.

  # 1) make the sheet: a balanced sample of coded Part 2 explanations, without the first coder's codes
  robustness/annotation_app/.venv/bin/python robustness/data/annotators/second_coder.py make --responses report/_responses_2026-10-26.json --n 30
  # 2) after the second coder fills column "themes" in second_coder/second_coder_sheet.xlsx
  robustness/annotation_app/.venv/bin/python robustness/data/annotators/second_coder.py score

The sample takes up to 4 explanations per theme code (different reviewers first), then fills to n at random (fixed
seed), so every theme is represented. The answer key (first coder's codes) is written to a separate file that is not
shared. Scoring reports, per theme, how often both coders applied it (Cohen's kappa) and overall exact-set agreement.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

from analyze_report import THEMES
from analyze_round1 import run_label

HERE = Path(__file__).resolve().parent
OUT = HERE / "second_coder"
QUESTION = {"claim_alignment": "Does this analysis test the focal claim?", "method_validity": "Is the method defensible?",
            "restriction_compliance": "Does it follow the Task 2 restriction?"}


def make(args) -> None:
    rows = json.loads(args.responses.read_text())[0]["results"]
    payload = {(r["paper_id"], r["analysis_id"], r["annotator"]): json.loads(r["payload"]) for r in rows}
    with (HERE / "part2_theme_codes.csv").open() as f:
        coded = [r for r in csv.DictReader(f)]
    rng = random.Random(42)
    by_code = defaultdict(list)
    for r in coded:
        for c in r["themes"].split(";"):
            by_code[c].append(r)
    chosen, seen = [], set()
    for code in THEMES:
        pool = by_code.get(code, [])[:]
        rng.shuffle(pool)
        pool.sort(key=lambda r: r["annotator"] in {c["annotator"] for c in chosen})  # new reviewers first
        for r in pool:
            key = (r["paper_id"], r["analysis_id"], r["annotator"], r["question"])
            if key not in seen and sum(code in c["themes"].split(";") for c in chosen) < 4:
                chosen.append(r); seen.add(key)
    rest = [r for r in coded if (r["paper_id"], r["analysis_id"], r["annotator"], r["question"]) not in seen]
    rng.shuffle(rest)
    chosen += rest[: max(0, args.n - len(chosen))]
    rng.shuffle(chosen)
    chosen = chosen[: max(args.n, len(chosen))]

    sheet, key = [], []
    for i, r in enumerate(chosen, 1):
        p = payload[(r["paper_id"], r["analysis_id"], r["annotator"])]
        sheet.append({"item": i, "paper": r["paper_id"].split("_")[0], "analysis": run_label(r["analysis_id"]),
                      "question": QUESTION[r["question"]], "answer": p.get(r["question"]),
                      "explanation": " ".join(str(p.get(r["question"] + "_explanation") or "").split()),
                      "themes": "", "notes": ""})
        key.append({"item": i, **r})
    OUT.mkdir(exist_ok=True)
    codebook = pd.DataFrame([{"code": c, "theme": label, "what it means": desc} for c, (label, desc) in THEMES.items()]
                            + [{"code": "other", "theme": "Something else", "what it means": "None of the above; describe it in notes."}])
    instructions = pd.DataFrame({"How to code": [
        "Each row is one reviewer's explanation for answering No, Unclear or Insufficient information to a question about a proposed analysis.",
        "Reviewers answered these before seeing any code, so the explanations are about the plan.",
        "In column 'themes', write every code from the Codebook sheet that the explanation raises, separated by ';' (e.g. changes_question;unfamiliar_method).",
        "Use 'other' (and describe it in 'notes') if nothing fits. Code what the reviewer says, not whether you agree with them.",
        "Please code independently: do not look at anyone else's codes until you are done."]})
    with pd.ExcelWriter(OUT / "second_coder_sheet.xlsx") as w:
        instructions.to_excel(w, sheet_name="Instructions", index=False)
        pd.DataFrame(sheet).to_excel(w, sheet_name="Explanations", index=False)
        codebook.to_excel(w, sheet_name="Codebook", index=False)
    pd.DataFrame(key).to_csv(OUT / "first_coder_key_DO_NOT_SHARE.csv", index=False)
    per_code = {c: sum(c in r["themes"].split(";") for r in chosen) for c in THEMES}
    print(f"Wrote {len(sheet)} items to {OUT / 'second_coder_sheet.xlsx'}; per theme in the sample: {per_code}")


def score(args) -> None:
    sheet = pd.read_excel(OUT / "second_coder_sheet.xlsx", sheet_name="Explanations")
    key = pd.read_csv(OUT / "first_coder_key_DO_NOT_SHARE.csv")
    a = {r.item: set(str(r.themes).split(";")) for r in key.itertuples()}
    b = {r.item: {x.strip() for x in str(r.themes).split(";") if x.strip() and x.strip() != "nan"} for r in sheet.itertuples()}
    items = sorted(i for i in a if b.get(i))
    print(f"{len(items)} items coded by both; exact same set of themes: {sum(a[i] == b[i] for i in items)}/{len(items)}")
    for code in list(THEMES) + ["other"]:
        x = [code in a[i] for i in items]; y = [code in b[i] for i in items]
        n = len(items); po = sum(p == q for p, q in zip(x, y)) / n
        pa, pb = sum(x) / n, sum(y) / n
        pe = pa * pb + (1 - pa) * (1 - pb)
        kappa = (po - pe) / (1 - pe) if pe < 1 else None
        if sum(x) or sum(y):
            print(f"  {code:25} first {sum(x):2}  second {sum(y):2}  agree {po:.0%}  kappa {kappa if kappa is None else round(kappa, 2)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("--responses", type=Path, required=True); m.add_argument("--n", type=int, default=30)
    sub.add_parser("score")
    args = parser.parse_args()
    {"make": make, "score": score}[args.cmd](args)


if __name__ == "__main__":
    main()
