"""Write the team report as a Word document (for the shared Drive record), from the rpt_*.json files.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/analyze_report.py --weeks 1
  robustness/annotation_app/.venv/bin/python robustness/data/annotators/make_report_docx.py

Every number comes from analyze_report.py's output; this script only lays it out as headings, sentences, charts and tables.
Writes report/round1_week<weeks>_report.docx.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUT = Path(__file__).resolve().parent / "report"
VERDICTS = ["Yes, all agree", "Yes, majority", "Unclear", "Insufficient information", "No, majority", "No, all agree", "Split"]
GREY = RGBColor(0x59, 0x59, 0x59)
# Verdict colors: greens for Yes, greys for unsure, reds for No, hatched for Split
VERDICT_STYLE = {"Yes, all agree": ("#2e7d4f", ""), "Yes, majority": ("#9fd1b0", ""), "Unclear": ("#bdbdbd", ""),
                 "Insufficient information": ("#e0e0e0", ""), "No, majority": ("#efa3a3", ""), "No, all agree": ("#c0392b", ""),
                 "Split": ("#ffffff", "///")}
SCORE_COLORS = ["#e8f3ec", "#c4e2cf", "#8cc7a1", "#4fa874", "#2e7d4f"]  # ratings 1-5
CLAIM, METHOD = "#7b61a8", "#c99a2e"  # neutral purple/gold: no good/bad reading
FIG_DIR = OUT / "_docx_figures"


def stacked_chart(doc: Document, name: str, labels: list[str], series: list[tuple[str, list[int], str, str]], xlabel: str) -> None:
    """Horizontal stacked bars, one per label, with each segment's count printed inside; saved as PNG and added to doc."""
    FIG_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(labels) + 1.4))
    left = [0] * len(labels)
    for sname, values, color, hatch in series:
        if not any(values):
            continue
        bars = ax.barh(labels, values, left=left, color=color, hatch=hatch, edgecolor="#555555", linewidth=0.6, label=sname)
        for bar, v in zip(bars, values):
            if v:
                dark = color in ("#2e7d4f", "#c0392b", "#4fa874", CLAIM)
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2, str(v), ha="center", va="center",
                        fontsize=9, color="white" if dark else "black")
        left = [a + b for a, b in zip(left, values)]
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, frameon=False, fontsize=8)
    fig.tight_layout()
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    doc.add_picture(str(path), width=Inches(6.5))


def load(name: str) -> list[dict]:
    return json.loads((OUT / f"rpt_{name}.json").read_text(encoding="utf-8"))


def pct(x: float) -> str:
    return f"{x:.0%}"


def shade(cell, hex_fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    fill = OxmlElement("w:shd")
    fill.set(qn("w:val"), "clear"); fill.set(qn("w:color"), "auto"); fill.set(qn("w:fill"), hex_fill)
    props.append(fill)


def table(doc: Document, header: list[str], rows: list[list], widths_first: bool = False) -> None:
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for cell, text in zip(t.rows[0].cells, header):
        cell.text = ""
        run = cell.paragraphs[0].add_run(text); run.bold = True
        shade(cell, "EDEDED")
    for row in rows:
        cells = t.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = "" if value is None else str(value)
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                for r in p.runs:
                    r.font.size = Pt(10)
    doc.add_paragraph()


def note(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text); run.italic = True; run.font.color.rgb = GREY; run.font.size = Pt(10)


def main() -> None:
    ov = load("overview")[0]
    verdicts, agreement, by_paper = load("p2_verdicts"), load("p2_agreement"), load("p2_by_paper")
    themes, quotes, unsure = load("p2_themes"), load("p2_quotes"), load("p2_unsure_others")
    p3, p3_summary, p4 = load("p3_scores"), load("p3_summary"), load("p4_scores")

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    doc.add_heading("Robustness annotation, round 1", level=0)
    note(doc, f"Week{'s' if ',' in ov['weeks'] else ''} {ov['weeks'].split(',')[0] + '–' + ov['weeks'].split(',')[-1] if ',' in ov['weeks'] else ov['weeks']} results. Data as of {ov['as_of']}. Only finished analyses count; test and pilot accounts are excluded.")
    p = doc.add_paragraph()
    run = p.add_run(
        f"By majority vote, reviewers judged that the agent's plan tests the claim for {ov['claim_yes_majority']} of {ov.get('p2_analyses', ov['analyses'])} analyses "
        f"and that its method is defensible for {ov['method_yes_majority']} of {ov.get('p2_analyses', ov['analyses'])}. "
        f"Code reviewers rated the code faithful to the plan (average 4 or higher of 5) for {ov['code_avg4']} of {ov['code_analyses']}, "
        f"and most reviewers rated the conclusion justified (4 or 5 of 5) for {ov['conclusion_high_majority']} of {ov['conclusion_analyses']}.")
    run.font.size = Pt(14)

    doc.add_heading("At a glance", level=1)
    table(doc, ["", "Count"], [
        ["Papers", ov["papers"]],
        ["Agent analyses reviewed", f"{ov['analyses']} ({ov['analyses_3_reviewers']} by 3 reviewers, {ov['analyses_2_reviewers']} by 2 so far)"],
        ["Completed reviews (one reviewer finishing one analysis)", ov["ratings"]],
        ["Reviewers who finished every analysis of their paper", f"{ov['reviewers_finished']} of {ov['reviewer_assignments']}"],
    ])

    # Part 2
    doc.add_heading("Part 2: Is the agent's plan a sound test of the claim?", level=1)
    doc.add_paragraph("Each analysis's reviews are combined by majority vote. \"All agree\" means every reviewer gave the same answer; "
                      "\"majority\" means more than half did; \"Split\" means no answer had a majority."
                      + (f" Part 2 uses only the {ov['p2_analyses']} analyses that all {ov['p2_min_reviewers']} reviewers have finished."
                         if ov.get("p2_min_reviewers", 1) > 1 else ""))
    doc.add_heading("Combined verdict by question", level=2)
    counts = {(r["question"], r["verdict"]): r["count"] for r in verdicts}
    questions = [a["question"] for a in agreement]
    shown = [v for v in VERDICTS if any(counts.get((q, v), 0) for q in questions)]
    stacked_chart(doc, "p2_verdicts", questions, [(v, [counts.get((q, v), 0) for q in questions], *VERDICT_STYLE[v]) for v in shown], "Analyses")
    table(doc, ["Question"] + shown + ["Analyses", "All reviewers agree"],
          [[a["question"]] + [counts.get((a["question"], v), 0) for v in shown] + [a["analyses"], f"{a['all_agree']} ({pct(a['share'])})"]
           for a in agreement])
    note(doc, "The restriction question only applies to Task 2 analyses.")

    doc.add_heading("By paper", level=2)
    pc = {(r["question"], r["paper"], r["verdict"]): r["count"] for r in by_paper}
    pairs = sorted({(r["question"], r["paper"]) for r in by_paper}, key=lambda k: (questions.index(k[0]), k[1]))
    shown = [v for v in VERDICTS if any(pc.get((q, p, v), 0) for q, p in pairs)]
    stacked_chart(doc, "p2_by_paper", [f"{q}: {p}" for q, p in pairs],
                  [(v, [pc.get((q, p, v), 0) for q, p in pairs], *VERDICT_STYLE[v]) for v in shown], "Analyses")
    table(doc, ["Question", "Paper"] + shown, [[q, p] + [pc.get((q, p, v), 0) for v in shown] for q, p in pairs])

    doc.add_heading("When a reviewer was unsure, what did the others say?", level=2)
    doc.add_paragraph("For every \"Unclear\" or \"Insufficient information\" answer, the answers the other reviewers of the same "
                      "analysis gave to the same question. Each other reviewer's answer is counted once per unsure answer, so when two "
                      "reviewers were both unsure, each is counted in the other's row.")
    heads = {(r["own_answer"], r["question"]): r for r in unsure if r["other_answer"] == "(answers)"}
    oc = {(r["own_answer"], r["question"], r["other_answer"]): r["count"] for r in unsure if r["other_answer"] != "(answers)"}
    keys = sorted(heads, key=lambda k: (k[0] != "Unclear", questions.index(k[1])))
    cols = ["Yes", "No", "Unclear", "Insufficient information"]
    rows = [[own, q, heads[(own, q)]["count"]] + [oc.get((own, q, c), 0) for c in cols] + [heads[(own, q)]["papers"], heads[(own, q)]["reviewers"]]
            for own, q in keys]
    rows.append(["Total", "", sum(r[2] for r in rows)] + [sum(r[3 + i] for r in rows) for i in range(len(cols))] + ["", ""])
    table(doc, ["Unsure answer", "Question", "Unsure answers"] + [f"Others: {c}" for c in cols] + ["Papers", "Reviewers"], rows)

    doc.add_heading("Why reviewers didn't say \"Yes\"", level=2)
    doc.add_paragraph(f"Every explanation behind a \"No\", \"Unclear\" or \"Insufficient information\" answer "
                      f"({ov['non_yes_part2_answers']} in all) was read and coded into themes. One answer can carry more than one theme.")
    note(doc, "A theme is listed only if it appears in at least 3 different analyses and comes from at least 2 reviewers.")
    stacked_chart(doc, "p2_themes", [t["theme"] for t in themes],
                  [("On \"tests the claim\"", [t["on_claim"] for t in themes], CLAIM, ""),
                   ("On \"method defensible\"", [t["on_method"] for t in themes], METHOD, "")], "Answers")
    table(doc, ["Theme", "What reviewers pointed to", "Analyses", "Answers", "On \"tests the claim\"", "On \"method defensible\"", "Reviewers", "Papers"],
          [[t["theme"], t["description"], t["analyses"], t["answers"], t["on_claim"], t["on_method"], t["reviewers"], t["papers"]] for t in themes])

    doc.add_heading("In reviewers' words", level=2)
    note(doc, "Up to two examples per theme, from different reviewers; long comments are shortened (…).")
    by_theme = defaultdict(list)
    for q in quotes:
        if q["rank"] == 1:
            by_theme[q["theme"]].append(q)
    for t in themes:
        examples = by_theme[t["theme"]][:2]
        if not examples:
            continue
        doc.add_paragraph(t["theme"], style="Heading 3")
        for q in examples:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"“{q['quote']}”")
            meta = p.add_run(f"  ({q['reviewer']}, {q['paper']} {q['analysis']}, {q['question']}: {q['answer']})")
            meta.font.color.rgb = GREY; meta.font.size = Pt(10)

    # Part 3
    doc.add_heading("Part 3: Does the code do what the plan says?", level=1)
    doc.add_paragraph("Code reviewers only, rated 1 (does not follow the plan) to 5 (faithful). These charts include every rating so far, including analyses still missing a review."
                      f" On the {ov['code_analyses']} analyses used in the summary at the top, the average code rating is {ov['code_mean_p2']:.2f}.")
    dist = {(r["paper"], r["score"]): r["count"] for r in p3}
    papers = [x["paper"] for x in p3_summary]
    stacked_chart(doc, "p3_scores", papers, [(f"Rated {k}", [dist.get((pp, k), 0) for pp in papers], SCORE_COLORS[k - 1], "") for k in range(1, 6)],
                  "Ratings (1 = does not follow the plan, 5 = faithful)")
    table(doc, ["Paper", "Ratings", "1", "2", "3", "4", "5", "Mean", "Rated 4 or 5"],
          [[s["paper"], s["ratings"]] + [dist.get((s["paper"], k), 0) for k in range(1, 6)] + [f"{s['mean']:.2f}", pct(s["share_4_or_5"])]
           for s in p3_summary])

    p3_themes, p3_quotes = load("p3_themes"), load("p3_quotes")
    doc.add_heading("Why code reviewers didn't give a 5", level=2)
    doc.add_paragraph(f"Every explanation behind a code fidelity rating below 5 ({ov['below5_part3_answers']} in all) was read and coded "
                      "into themes, separately from Part 2. Reviewers write these after seeing the code. One answer can carry more than one theme.")
    note(doc, "A theme is listed only if it appears in at least 3 different analyses and comes from at least 2 reviewers.")
    stacked_chart(doc, "p3_themes", [t["theme"] for t in p3_themes], [("Analyses", [t["analyses"] for t in p3_themes], METHOD, "")], "Analyses")
    table(doc, ["Theme", "What reviewers pointed to", "Analyses", "Reviewers", "Papers"],
          [[t["theme"], t["description"], t["analyses"], t["reviewers"], t["papers"]] for t in p3_themes])
    doc.add_heading("In reviewers' words", level=2)
    note(doc, "Up to two examples per theme, from different reviewers; long comments are shortened (…).")
    by_theme3 = defaultdict(list)
    for q in p3_quotes:
        if q["rank"] == 1:
            by_theme3[q["theme"]].append(q)
    for t in p3_themes:
        doc.add_paragraph(t["theme"], style="Heading 3")
        for q in by_theme3[t["theme"]][:2]:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"\u201c{q['quote']}\u201d")
            meta = p.add_run(f"  ({q['reviewer']}, {q['paper']} {q['analysis']}, rated {q['answer']})")
            meta.font.color.rgb = GREY; meta.font.size = Pt(10)

    # Part 4
    doc.add_heading("Part 4: Do the agent's conclusions follow from its results?", level=1)
    doc.add_paragraph(f"Rated 1 (not justified) to 5 (fully justified). {pct(ov['conclusion_share_5'])} of all ratings are a 5, "
                      "so this question separates analyses very little. This chart includes every rating so far, including analyses still missing a review.")
    d4 = {(r["agent_conclusion"], r["score"]): r["count"] for r in p4}
    concl = sorted({r["agent_conclusion"] for r in p4})
    stacked_chart(doc, "p4_scores", [c.capitalize() for c in concl],
                  [(f"Rated {k}", [d4.get((c, k), 0) for c in concl], SCORE_COLORS[k - 1], "") for k in range(1, 6)],
                  "Ratings (1 = not justified, 5 = fully justified)")
    table(doc, ["What the agent concluded", "1", "2", "3", "4", "5", "Ratings"],
          [[c.capitalize()] + [d4.get((c, k), 0) for k in range(1, 6)] + [sum(d4.get((c, k), 0) for k in range(1, 6))] for c in concl])

    doc.add_heading("Reading these results", level=1)
    for text in [
        f"This is early data: {ov['papers']} papers, each analysis reviewed by two or three people. Jiang's second code "
        "reviewer withdrew after 4 of 10 analyses, and one Wilde code reviewer has not started, so some analyses have two reviews.",
        "Report a combined verdict together with how strongly reviewers agreed on it; a 2–1 vote is weaker evidence than a unanimous one.",
        "Themes raised by a single reviewer are not listed (see the rule above). The main one left out is about limitations of "
        "the original studies (small samples, observational data), which round 2's instructions will address.",
        "\"Model not used in the original paper\" suggests some reviewers judged alternatives against the original method, although the task "
        "asks for alternative analyses. Also a candidate for clearer round 2 wording.",
    ]:
        doc.add_paragraph(text, style="List Bullet")

    path = OUT / f"round1_week{ov['weeks'].replace(',', '-')}_report.docx"
    doc.save(path)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
