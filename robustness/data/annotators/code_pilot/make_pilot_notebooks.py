"""Build the week 4 in-depth code review notebooks (one per analysis) plus the shared files folder.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/code_pilot/make_pilot_notebooks.py

Writes data/annotators/code_pilot/out/. The analysis code is copied verbatim into each notebook (never edited, and
checked byte for byte); the notebook recreates the run's folder layout in Colab so the code finds its data exactly as
when it ran. The review is a plan-to-code map: each plan item (taken from the plan itself) gets the code line(s) that
implement it and a validity judgment. Answers are typed into answer cells and read back by read_pilot_answers.py; the
start cells print timestamps, which give the time per part.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # robustness/
sys.path.insert(0, str(ROOT / "annotation_app"))
from extract import extract_paper  # noqa: E402

PAPER = ROOT / "data" / "Annotator-Test" / "Bruner_ExpEco_2017_amYY"
ANALYSES = ["test_01:Task2", "test_03:Task1", "test_05:Task1"]
DATA_FILES = ["RiskData.dta"]  # the data file(s) the analysis code reads (placed in data/ next to the run)
OUT = HERE / "out"
WORKDIR = "/content/pilot"  # Colab working folder that stands in for the run folder
VALID = ["Valid", "Partly", "Not valid", "Not implemented", "Can't tell"]

PLAN_FIELDS = [("claim_mapping", "Plain-language claim mapping"), ("outcome", "Outcome"), ("main_predictor", "Main predictor"),
               ("additional_variables", "Other variable"), ("model_type", "Model"), ("formula", "Formula"),
               ("planned_estimation", "Estimation"), ("expected_direction", "Expected direction"),
               ("preprocessing_steps", "Preprocessing steps"), ("decision_rule", "Decision rule")]
VARIABLE_LABELS = [("definition", "Definition"), ("variable_construction", "How it's built"),
                   ("missing_data_handling", "Missing data"), ("qualification", "Note")]  # internal fields are left out

HELPERS = '''# Helpers: run me first.
import datetime

def show_code(start=1, end=None):
    """Print the analysis code with line numbers (optionally only lines start..end)."""
    lines = open(SCRIPT).read().splitlines()
    for n, text in enumerate(lines[start - 1:end], start):
        print(f"{n:4d}  {text}")

def start_part(n):
    print(f"Part {n} started {datetime.datetime.now().isoformat(timespec='seconds')}")

VALID = ''' + repr(VALID) + '''

def finish():
    problems = []
    run = globals().get("run_check")
    if run is None or run.get("ran") not in ("Yes", "No", "Ran after a small fix", "Did not run it"):
        problems.append("Part 1: 'ran' must be 'Yes', 'No', 'Ran after a small fix' or 'Did not run it'")
    for row in globals().get("plan_map", []):
        if row["valid"] not in VALID:
            problems.append(f"Part 2: '{row['item'][:50]}...': 'valid' must be one of {VALID}")
        if not str(row["lines"]).strip():
            problems.append(f"Part 2: '{row['item'][:50]}...': 'lines' is empty (write 'none' if no line implements it)")
        if row["valid"] in VALID and row["valid"] != "Valid" and not str(row["note"]).strip():
            problems.append(f"Part 2: '{row['item'][:50]}...': please add a note explaining '{row['valid']}'")
    extra = globals().get("unplanned")
    if extra is None or extra.get("any") not in ("Yes", "No"):
        problems.append("Part 3: 'any' must be 'Yes' or 'No'")
    overall = globals().get("overall")
    if overall is None or overall.get("changes_conclusion") not in ("Yes", "No", "Can't tell", "No problems found"):
        problems.append("Part 4: 'changes_conclusion' must be 'Yes', 'No', 'Can't tell' or 'No problems found'")
    if overall is None or overall.get("rating") not in (1, 2, 3, 4, 5):
        problems.append("Part 4: 'rating' must be a number from 1 to 5")
    print("\\n".join(problems) if problems else "All answers recorded. Now save: File > Save (Ctrl/Cmd+S).")
    print(f"Finished {datetime.datetime.now().isoformat(timespec='seconds')}")
'''

RUN_CHECK = '''run_check = {
    "ran": "",                  # "Yes", "No", "Ran after a small fix" or "Did not run it"
    "matches_recorded": "",     # "Yes", "No" or "Can't tell" (leave blank if you did not run it)
    "notes": """
""",                            # anything that went wrong, or which numbers you compared
}
'''
UNPLANNED = '''unplanned = {
    "any": "",                  # does the code do anything the plan does not mention? "Yes" or "No"
    "details": """
""",                            # one per line: lines | what the code does | does it matter?
}
'''
OVERALL = '''overall = {
    "problems": """
""",                            # one per line: plan item or lines | the problem | changes this conclusion? Yes / No / Can't tell
    "changes_conclusion": "",   # would any problem change this analysis's conclusion? "Yes", "No", "Can't tell" or "No problems found"
    "rating": None,             # how faithfully the code implements the plan: 1 (does not follow it) to 5 (faithful)
    "rating_explanation": """
""",
}
'''
FEEDBACK = '''feedback = {
    "total_hours": None,                  # about how many hours all three analyses took, incl. reading the paper
    "most_useful_part": None,             # 1-4: which part was most useful for finding problems
    "unclear_or_hard": """
""",                                      # anything unclear or hard to do in the time; what would help
    "colab_problems": "",                 # "No", "Yes, minor" or "Yes, it cost significant time"
    "colab_details": """
""",
    "sustainable_3_per_week": "",         # could you do about 3 like this per week? "Yes", "Maybe" or "No"
    "why": """
""",
    "compared_with_quick_review": """
""",                                      # did mapping the plan to the code change what you noticed?
}
'''


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.splitlines(keepends=True)}


def variable(value: dict, title: str) -> str:
    """One variable as a short bold heading and readable bullets."""
    lines = [f"**{title}: {value.get('name', '')}**"] if value.get("name") else [f"**{title}**"]
    lines += [f"- **{label}:** {value[key]}" for key, label in VARIABLE_LABELS if value.get(key) not in (None, "", [])]
    return "\n".join(lines)


def section(key: str, title: str, value) -> str:
    if isinstance(value, dict):
        return variable(value, title)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return "\n\n".join(variable(v, f"{title} {i}") for i, v in enumerate(value, 1))
    if isinstance(value, list):
        return f"**{title}:**\n" + "\n".join(f"{i}. {v}" for i, v in enumerate(value, 1))
    return f"**{title}:** {value}"


def plan_items(plan: dict, restriction: str | None) -> list[str]:
    """The plan broken into the items reviewers map to code, in the plan's own words: its numbered steps (which cover
    data, sample, variables, model and reporting), then the decision rule and, for Task 2, the restriction."""
    items = [f"Plan step {i}: {step}" for i, step in enumerate(plan.get("preprocessing_steps") or [], 1)]
    if plan.get("decision_rule"):
        items.append(f"Decision rule: {plan['decision_rule']}")
    if restriction:
        items.append(f"Task 2 restriction: {restriction}")
    return items


def main() -> None:
    packet = extract_paper(PAPER)
    by_id = {a["id"]: a for a in packet["analyses"]}
    claim = packet["case"].get("focal_claim", "")
    shared = OUT / "shared_files"
    shared.mkdir(parents=True, exist_ok=True)
    for name in DATA_FILES:
        shutil.copy2(PAPER / "data" / name, shared / name)
    shutil.copy2(PAPER / packet["source_materials"]["paper"], shared / "original_paper.pdf")
    if (PAPER / "data" / "README.txt").is_file():
        shutil.copy2(PAPER / "data" / "README.txt", shared / "data_README.txt")

    for aid in ANALYSES:
        a = by_id[aid]
        label = a["display_name"].replace("—", "-")
        rel_code = Path(a["files"]["code"]).relative_to(a["run"])  # path inside the run folder
        source = (PAPER / a["files"]["code"]).read_text(encoding="utf-8")
        plan = a["plan"].get("review") or {}
        restriction = a["task"].get("instruction") if a["task_id"] == "Task2" else None
        recorded = a["execution"].get("runner_stdout") or "(no recorded output)"
        if not isinstance(recorded, str):  # the run printed JSON, which extract.py already parsed
            recorded = json.dumps(recorded, indent=2, ensure_ascii=False)
        rows = ",\n".join(f'    {{"item": {json.dumps(item, ensure_ascii=False)},\n     "lines": "", "valid": "", "note": ""}}'
                          for item in plan_items(plan, restriction))
        plan_map = ("# For each plan item: \"lines\" = the line number(s) that implement it (e.g. \"64-71\", or \"none\"),\n"
                    f"# \"valid\" = one of {VALID}, \"note\" = why (required unless Valid).\n"
                    f"plan_map = [\n{rows},\n]\n")
        scratch = ("# Scratch space: explore the data or try out a line you question.\n"
                   "import pandas as pd\n"
                   f"df = pd.read_stata('{WORKDIR}/data/{DATA_FILES[0]}')\n"
                   "df.head()\n")
        cells = [
            md(f"# In-depth code review: Bruner (2017), {label}\n\n"
               "**Your question for this analysis: does the code faithfully implement the plan?** Take the plan as given; "
               "you are not judging whether the plan is a good analysis. Code style does not matter.\n\n"
               "The review has four parts (about **60 minutes** in total). At the start of each part, run its **start** "
               "cell (it records the time). Type your answers into the answer cells and run them.\n\n"
               "Do **not** edit the analysis code cell. **Save often** (File → Save, or Ctrl/Cmd+S) and check that Colab "
               "shows *All changes saved*: your answers reach us only through the saved notebook in your Week 4 folder.\n"),
            md(f"## The claim\n\n> {claim}\n\n**Task 2 restriction:** {restriction or 'None (Task 1: any defensible analysis).'}\n"),
            md("## The plan\n\n" + "\n\n".join(
                section(key, title, plan[key]) for key, title in PLAN_FIELDS if plan.get(key) not in (None, "", []))),
            md("## Setup (about 2 min)\n\nRun the next three cells **every time you open or reopen this notebook** "
               "(Colab forgets uploaded files when it disconnects; your typed answers are kept). "
               f"The second cell asks you to upload the data file (`{', '.join(DATA_FILES)}`, from your Week 4 folder)."),
            code(HELPERS),
            code("import os, shutil\n"
                 f"os.makedirs('{WORKDIR}/data', exist_ok=True)\n"
                 f"os.makedirs('{WORKDIR}/{rel_code.parent.as_posix()}', exist_ok=True)\n"
                 "from google.colab import files\n"
                 "for name in files.upload():\n"
                 f"    shutil.move(name, '{WORKDIR}/data/' + name)\n"
                 f"print(os.listdir('{WORKDIR}/data'))\n"
                 f"SCRIPT = '{WORKDIR}/{rel_code.as_posix()}'\n"),
            code(f"%%writefile {WORKDIR}/{rel_code.as_posix()}\n" + source),
            # Part 1
            md("## Part 1: Run the code (about 10 min)\n\n"
               "Run the code and compare its output with the recorded output below (estimate, standard error or p-value, "
               "interval, sample size, conclusion). Running it is strongly encouraged: it also lets you test lines in the "
               "scratch cells later."),
            code("start_part(1)\n"),
            code(f"%cd {WORKDIR}\n!python {rel_code.as_posix()}\n"),
            md("**Recorded output when the analysis was originally run:**\n\n```\n" + recorded.strip() + "\n```"),
            code(RUN_CHECK),
            # Part 2
            md("## Part 2: Map the plan to the code (about 30 min)\n\n"
               "The plan is split into items below, in the plan's own words. For **each item**:\n\n"
               "1. Find the line(s) of code that implement it (`show_code()` prints the code with line numbers).\n"
               "2. Judge whether those lines are a **valid implementation** of that item: "
               + ", ".join(f"*{v}*" for v in VALID) + ".\n"
               "3. Add a short note, required unless the item is *Valid*.\n\n"
               "If you are unsure whether some lines do what the item says, **try them out**: load the data in the scratch "
               "cell, copy the lines in, and look at the result (for example the number of rows after a filter, or a few "
               "values of a constructed variable)."),
            code("start_part(2)\n"),
            code("show_code()\n"),
            code(plan_map),
            code(scratch),
            # Part 3
            md("## Part 3: Code the plan does not mention (about 5 min)\n\n"
               "Does the code do anything the plan does not state, for example an extra filter, a different test, or a "
               "hard-coded value? List the lines and say whether it matters."),
            code("start_part(3)\n"),
            code(UNPLANNED),
            # Part 4
            md("## Part 4: Severity and overall rating (about 10 min)\n\n"
               "For each problem you found in Parts 1–3, decide whether it would change **this** analysis's conclusion "
               "(use the actual numbers from the output). A problem can be real even if it does not change this result. "
               "Then give your overall rating."),
            code("start_part(4)\n"),
            code(OVERALL),
            md("## Finish this analysis\n\nRun the cell below. It checks that every answer is filled in. "
               "Then **save** (File → Save, or Ctrl/Cmd+S) and check that Colab shows *All changes saved*."),
            code("finish()\n"),
            md("## Feedback (fill in **once**, in whichever notebook you finish last)\n\nLeave this blank in the other two notebooks."),
            code(FEEDBACK),
        ]
        # Guard: the code cell must hold the analysis file byte for byte (after the one %%writefile line).
        written = next("".join(c["source"]) for c in cells if "".join(c["source"]).startswith("%%writefile"))
        assert written.split("\n", 1)[1] == source, f"{aid}: code cell differs from {a['files']['code']}"
        nb = {"cells": cells, "metadata": {"colab": {"provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                                            "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 0}
        path = OUT / f"Bruner_{label.replace(' ', '_')}.ipynb"
        path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
        print(path.name, "|", len(plan_items(plan, restriction)), "plan items |", len(source.splitlines()), "lines of code")


if __name__ == "__main__":
    main()
