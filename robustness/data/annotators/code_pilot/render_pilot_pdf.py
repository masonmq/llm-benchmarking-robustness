"""Render pilot_instructions.md to PDF with the weekly instructions' style, plus table support, and copy it into both
reviewers' Week 4 folders.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/code_pilot/render_pilot_pdf.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "annotation_app" / "instructions"))
from make_instructions import CHROME, CSS  # noqa: E402

TABLE_CSS = """
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9.5pt; }
th, td { border: 1px solid #cfdbe6; padding: 5pt 7pt; text-align: left; vertical-align: top; }
th { background: #f2f6fa; }
td:nth-child(2), th:nth-child(2) { white-space: nowrap; }
"""

contact = json.loads((HERE.parent / "local_accounts.json").read_text(encoding="utf-8"))["contact"]  # private, not in git
body = markdown.markdown((HERE / "pilot_instructions.md").read_text(encoding="utf-8").replace("{{CONTACT}}", contact), extensions=["toc", "sane_lists", "tables"])
html = HERE / "out" / "Week4_code_review_instructions.html"
pdf = HERE / "out" / "Week4_code_review_instructions.pdf"
html.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}{TABLE_CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
try:
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html.resolve().as_uri()],
                   check=True, capture_output=True)
finally:
    html.unlink(missing_ok=True)
for folder in (HERE / "out").glob("for_*/Week 4"):
    shutil.copy2(pdf, folder / pdf.name)
print(pdf)
