"""Build the round 1 assignment workbook (screening IDs only) and sync the roster.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/build_round1.py

Edit PAPERS below to change the plan; weeks 1-2 are live and must not change.
2026-10-15: swapped ID17 <-> ID7 (Grose wk3 / Wlezien wk4) and ID35 <-> ID38 (Alves wk3 / Wlezien wk4) because
ID17 had not finished week 1 and ID35 had not started week 2.
2026-10-15: Clark replaced Alves in week 3 (same reviewers). Alves's agent output was the single-run sequential format;
Hertel and Lu were tried next but some runs lack execution_result.json.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1] / "annotation_app"
sys.path.insert(0, str(APP))
from roster import DEFAULT_ROSTER, read_rows, write_rows  # noqa: E402

SCREENING = APP / "LLM Agent Benchmarking Project Annotator Screening (Responses) - Annotation Round 1 - Assignment.csv"
CLAIMS = HERE.parent / "_robustness" / "all_claims.xlsx"
OUT = HERE / "round1_assignment.xlsx"
SITE = json.loads((HERE / "local_accounts.json").read_text(encoding="utf-8"))["site"]  # private, not in git
CODE_REVIEWERS = {1, 6, 7, 11, 17, 30, 35, 38, 42, 43, 46, 48}
LATE_CONFIRMED = {42}  # joined 2026-10-18 via the PM (replaces ID17); not marked responded in the screening export
ANNOTATORS = {12, 14, 15, 20}
# Usernames already issued, read from the private roster (never written in code), so nothing changes for these people.
ISSUED = {int(str(r["name"]).split()[-1]): r["username"] for r in read_rows(DEFAULT_ROSTER) if str(r.get("name") or "").startswith("ID ")}

PAPERS = [  # week, paper_id, discipline, agent vs humans, code reviewers, annotators (week 1 is live and fixed)
    (1, "Zunick_JournExpSocPsych_2017_zlw", "Psychology", "Agree", (46, 11), (14,)),
    (1, "Jiang_AmJourPoliSci_2018_Rjp9", "Political science", "Agree", (7, 17), (15,)),
    (1, "Bruner_ExpEco_2017_amYY", "Economics", "Agree", (1, 38), (20,)),
    (2, "Wilde_AmSocioRev_2010_4XLv", "Sociology", "Disagree", (6, 30), (20,)),
    (2, "Bartels_JournConsRes_2015_mrZ", "Marketing/org behavior", "Agree", (43, 46), (12,)),
    (2, "Sliwka_JournLabEco_2017_VDJV", "Economics", "Disagree", (35, 38), (15,)),
    (3, "Grose_AmJourPoliSci_2015_E0Q3", "Political science", "Disagree", (7, 6), (20,)),
    (3, "Luttrell_JournExpSocPsych_2016_rjb", "Psychology", "Disagree", (11, 48), (14,)),
    (3, "Clark_JournPoliEco_2009_e5rW", "Economics", "Disagree", (1, 38), (12,)),  # replaced Alves (sequential-format output), then Hertel/Lu (runs missing recorded output)
    (4, "Cingranelli_BritJournPoliSci_2014_qg47", "Political science", "Disagree", (7, 35), (15,)),  # replaced Wlezien (run 1 output empty); ID7 replaces ID17
    (4, "Brough_JournConsRes_2016_9ey", "Marketing/org behavior", "Agree", (43, 48), (12,)),  # replaced Liu (5 code files missing)
    (4, "Petersen_Cognition_2017_yJwG", "Psychology", "Agree", (11, 30), (14,)),  # ID11 replaces ID1, who does the code pilot that week
]
HOURS = {"Code reviewer": 2.5, "Annotator": 2.0}  # rough per-paper estimates
# Non-paper tasks shown in the by-annotator tab only (not papers: never written to the roster or the D1 assignments).
EXTRA_TASKS = {42: {4: "Code pilot"}, 46: {4: "Code pilot"}}

screen = pd.read_csv(SCREENING)
screen = screen[(screen["responded"] == "yes") | screen["ID"].isin(LATE_CONFIRMED)].set_index("ID")
col = lambda prefix: next(c for c in screen.columns if c.startswith(prefix))
claims = pd.read_excel(CLAIMS).set_index("paper_id")

roster = read_rows(DEFAULT_ROSTER)
by_username = {r["username"]: r for r in roster}
pool = [r["username"] for r in roster if r["username"].startswith("cr-") and r.get("status") == "available"
        and r["username"] not in ISSUED.values()]

people = {}
for sid in screen.index:
    info = screen.loc[sid]
    role = "Code reviewer" if sid in CODE_REVIEWERS else "Annotator" if sid in ANNOTATORS else "Pending screening"
    username = ISSUED.get(sid) or (pool.pop(0) if role == "Code reviewer" else "")
    value = lambda prefix: info[col(prefix)] if pd.notna(info[col(prefix)]) else "Not answered"
    people[sid] = {"role": role, "username": username, "papers": {},
                   "primary": value("Primary discipline"),
                   "assigned": str(info["assigned discipline"]).strip() if pd.notna(info["assigned discipline"]) else "",
                   "python": str(value("How comfortable are you running")).split(" — ")[0]}

for week, paper, _, _, reviewers, annotators in PAPERS:
    assert len(reviewers) == 2 and len(annotators) == 1, paper
    assert paper in claims.index, f"{paper} not in all_claims.xlsx"
    for sid in (*reviewers, *annotators):
        expected = "Code reviewer" if sid in reviewers else "Annotator"
        assert people[sid]["role"] == expected, (sid, paper)
        assert week not in people[sid]["papers"], (sid, week)
        people[sid]["papers"][week] = paper

for row in roster:  # only update people in this plan; leave issue dates of existing usernames alone
    row.setdefault("status", "available")
for sid, person in people.items():
    if person["username"]:
        row = by_username[person["username"]]
        row.update(name=f"ID {sid}", email=None, status="issued",
                   assigned_papers="; ".join(person["papers"][w] for w in sorted(person["papers"])))
        row["date_issued"] = row.get("date_issued") or date.today().isoformat()
write_rows(DEFAULT_ROSTER, roster)

label = lambda sid: f"ID {sid} ({people[sid]['username']})"
bold, wrap, fill = Font(bold=True), Alignment(wrap_text=True, vertical="top"), PatternFill("solid", fgColor="DDE6F0")


def sheet(book, title, header, rows, widths):
    ws = book.create_sheet(title)
    ws.append(header)
    for cell in ws[1]:
        cell.font, cell.fill, cell.alignment = bold, fill, wrap
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = wrap
    for column, width in zip("ABCDEFGHIJKLMNOP", widths):
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "A2"
    return ws


book = Workbook()
book.remove(book.active)
ws = sheet(book, "Round 1 - by annotator",
           ["ID", "Username", "Role", "Primary discipline", "Assigned discipline", "Python comfort", "Instructions",
            "Week 1 paper", "Week 2 paper", "Week 3 paper", "Week 4 paper", "Papers", "Est. hours", "Status", "Notes"],
           [[sid, p["username"] or "TBD", p["role"], p["primary"], p["assigned"], p["python"],
             {"Code reviewer": "INSTRUCTIONS_code_reviewer", "Annotator": "INSTRUCTIONS_annotator"}.get(p["role"], ""),
             *[p["papers"].get(w) or EXTRA_TASKS.get(sid, {}).get(w, "") for w in (1, 2, 3, 4)], len(p["papers"]),
             round(len(p["papers"]) * HOURS.get(p["role"], 0), 1) or "", "Not started" if p["papers"] else "", ""]
            for sid in sorted(people) for p in [people[sid]]],
           [6, 12, 15, 22, 18, 16, 26, 32, 32, 32, 32, 8, 9, 13, 30])
status = DataValidation(type="list", formula1='"Not started,In progress,Completed,Withdrawn"', allow_blank=True)
ws.add_data_validation(status)
status.add(f"N2:N{len(people) + 1}")
sheet(book, "Round 1 - by paper",
      ["Week", "Paper ID", "Discipline", "Agent vs. human reanalyses", "Task 2 restriction", "Review link",
       "Code reviewer 1", "Code reviewer 2", "Annotator(s)"],
      [[week, paper, discipline, agree, str(claims.loc[paper, "instructions_for_task_2"]).strip(), SITE.format(paper),
        label(reviewers[0]), label(reviewers[1]), ", ".join(label(a) for a in annotators)]
       for week, paper, discipline, agree, reviewers, annotators in PAPERS],
      [7, 36, 20, 14, 50, 45, 22, 22, 22])
book.save(OUT)
print(OUT)
