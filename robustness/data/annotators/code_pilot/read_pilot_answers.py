"""Read the reviewers' saved week 4 code review notebooks back into tables.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/code_pilot/read_pilot_answers.py FOLDER [FOLDER ...]

Each FOLDER holds one reviewer's saved notebooks (downloaded from their Week 4 Drive folder); the folder name is used as
the reviewer label. Answers are read from the answer cells' source, so they count even if a cell was not re-run. Time per
part comes from the timestamps printed by the start_part / finish cells. Writes, next to this script:
  review_plan_map.csv   one row per reviewer x analysis x plan item (lines, valid, note)
  review_summary.csv    one row per reviewer x analysis (run check, unplanned code, problems, rating, minutes per part)
  review_feedback.csv   the one-time feedback answers
and prints anything blank or malformed.
"""

from __future__ import annotations

import ast
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ("run_check", "plan_map", "unplanned", "overall", "feedback")
ANSWER_CELL = re.compile(r"(?:\s*#[^\n]*\n)*\s*(" + "|".join(NAMES) + r")\s*=")
STAMP = re.compile(r"(Part (\d) started|Finished) (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)")
VALID = {"Valid", "Partly", "Not valid", "Not implemented", "Can't tell"}


def read_notebook(path: Path) -> tuple[dict, dict, list[str]]:
    nb = json.loads(path.read_text(encoding="utf-8"))
    answers, stamps, problems = {}, {}, []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        for out in cell.get("outputs", []):
            for m in STAMP.finditer("".join(out.get("text", []))):
                stamps["finish" if m.group(1) == "Finished" else int(m.group(2))] = datetime.fromisoformat(m.group(3))
        src = "".join(cell["source"])
        if not ANSWER_CELL.match(src):  # only answer cells are parsed (other cells use Colab-only syntax)
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            problems.append(f"an answer cell cannot be read ({exc.msg}, line {exc.lineno})")
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) in NAMES:
                try:
                    answers[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    problems.append(f"{node.targets[0].id}: contains something other than plain text or numbers")
    order = [k for k in (1, 2, 3, 4, "finish") if k in stamps]
    minutes = {}
    for n in (1, 2, 3, 4):
        nxt = next((k for k in order if k == "finish" or k > n), None) if n in stamps else None
        minutes[n] = round((stamps[nxt] - stamps[n]).total_seconds() / 60, 1) if nxt else None
    return answers, minutes, problems


def clean(v):
    return v.strip() if isinstance(v, str) else v


def main() -> None:
    map_rows, summary, feedback, problems = [], [], [], []
    for folder in map(Path, sys.argv[1:]):
        for nb_path in sorted(folder.glob("*.ipynb")):
            analysis = nb_path.stem.replace("Bruner_", "")
            where = f"{folder.name} / {analysis}"
            a, minutes, errs = read_notebook(nb_path)
            problems += [f"{where}: {e}" for e in errs]
            for i, row in enumerate(a.get("plan_map", []), 1):
                map_rows.append({"reviewer": folder.name, "analysis": analysis, "item_no": i, **{k: clean(v) for k, v in row.items()}})
                if row.get("valid") not in VALID or not str(row.get("lines", "")).strip():
                    problems.append(f"{where}: plan item {i} incomplete (lines / valid)")
                elif row["valid"] != "Valid" and not str(row.get("note", "")).strip():
                    problems.append(f"{where}: plan item {i} is '{row['valid']}' but has no note")
            run, extra, overall = a.get("run_check", {}), a.get("unplanned", {}), a.get("overall", {})
            summary.append({"reviewer": folder.name, "analysis": analysis,
                            **{f"run_{k}": clean(v) for k, v in run.items()},
                            **{f"unplanned_{k}": clean(v) for k, v in extra.items()},
                            **{k: clean(v) for k, v in overall.items()},
                            **{f"minutes_part{n}": m for n, m in minutes.items()}})
            if overall.get("rating") not in (1, 2, 3, 4, 5):
                problems.append(f"{where}: overall rating missing")
            fb = a.get("feedback", {})
            if any(v not in (None, "", "\n") for v in fb.values()):
                feedback.append({"reviewer": folder.name, "notebook": analysis, **{k: clean(v) for k, v in fb.items()}})
    if not summary:
        raise SystemExit("No notebooks found.")
    for name, rows in (("review_plan_map", map_rows), ("review_summary", summary), ("review_feedback", feedback)):
        if rows:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            with (HERE / f"{name}.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"{len(summary)} notebooks, {len(map_rows)} plan-item rows, {len(feedback)} feedback entries")
    print("\n".join(problems) if problems else "No blank or malformed answers.")


if __name__ == "__main__":
    main()
