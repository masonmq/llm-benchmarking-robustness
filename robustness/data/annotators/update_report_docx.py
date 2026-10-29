"""Refresh a hand-edited report .docx with the latest numbers, keeping its wording, layout and structure.

  robustness/annotation_app/.venv/bin/python robustness/data/annotators/analyze_report.py --weeks 1,2 --responses ...
  robustness/annotation_app/.venv/bin/python robustness/data/annotators/analyze_agreement.py --weeks 1,2 --responses ...
  robustness/annotation_app/.venv/bin/python robustness/data/annotators/make_report_docx.py     # redraws the charts
  robustness/annotation_app/.venv/bin/python robustness/data/annotators/update_report_docx.py \
      report/round1_week1_report.docx report/round1_week1-2_report_edited.docx

Only numbers, charts, data tables, the theme quotes and the dated notes change; every sentence keeps the template's
wording. Every number comes from the rpt_*.json / agreement_*.json files. The template file is never modified.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

OUT = Path(__file__).resolve().parent / "report"
ALL_RATINGS_NOTE = " These charts include every rating so far, including analyses still missing a review."  # Part 3 and 4 charts use every rating; the headline uses the Part 2 analyses
FIGURES = ["p2_verdicts", "p2_by_paper", "p2_themes", "p3_scores", "p4_scores"]  # order of the charts in the report


def load(name: str):
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def set_text(paragraph: Paragraph, text: str) -> None:
    """Replace a paragraph's text but keep the first run's formatting."""
    runs = paragraph.runs
    runs[0].text = text
    for run in runs[1:]:
        run._r.getparent().remove(run._r)


def find(doc: Document, start: str) -> Paragraph:
    return next(p for p in doc.paragraphs if p.text.startswith(start))


def fill_table(table, rows: list[list]) -> None:
    """Replace the data rows, copying the first data row's formatting."""
    template = copy.deepcopy(table.rows[1]._tr)
    for row in list(table.rows)[1:]:
        table._tbl.remove(row._tr)
    for values in rows:
        tr = copy.deepcopy(template)
        table._tbl.append(tr)
        for cell, value in zip(table.rows[-1].cells, values):
            set_text(cell.paragraphs[0], str(value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("template", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    assert args.template.resolve() != args.out.resolve(), "write to a new file; the template is kept as is"

    ov = load("rpt_overview")[0]
    themes, quotes = load("rpt_p2_themes"), load("rpt_p2_quotes")
    themes3, quotes3 = load("rpt_p3_themes"), load("rpt_p3_quotes")
    agreement = load(f"agreement_week{ov['weeks'].replace(',', '-')}")["overall"]
    _w = [int(x) for x in ov["weeks"].split(",")]
    weeks = f"{_w[0]}–{_w[-1]}" if len(_w) > 1 and _w == list(range(_w[0], _w[-1] + 1)) else ov["weeks"].replace(",", "–")
    doc = Document(args.template)

    P3_HEADING = "Why code reviewers didn't give a 5"
    existing = next((x for x in doc.paragraphs if x.text == P3_HEADING), None)
    if existing is not None:
        stop, el = find(doc, "Part 4:")._p, existing._p
        while el is not None and el is not stop:
            nxt = el.getnext(); el.getparent().remove(el); el = nxt

    set_text(find(doc, "Week"), f"Week{'s' if ',' in ov['weeks'] else ''} {weeks} results. Data as of {ov['as_of']}. "
             "Only finished analyses count; test and pilot accounts are excluded.")
    set_text(find(doc, "By majority vote"),
             f"By majority vote, reviewers judged that the agent's plan tests the claim for {ov['claim_yes_majority']} of {ov.get('p2_analyses', ov['analyses'])} analyses "
             f"and that its method is defensible for {ov['method_yes_majority']} of {ov.get('p2_analyses', ov['analyses'])}. "
             f"Code reviewers rated the code faithful to the plan (average 4 or higher of 5) for {ov['code_avg4']} of {ov['code_analyses']}, "
             f"and most reviewers rated the conclusion justified (4 or 5 of 5) for {ov['conclusion_high_majority']} of {ov['conclusion_analyses']}.")
    fill_table(doc.tables[0], [
        ["Papers", ov["papers"]],
        ["Agent analyses reviewed", f"{ov['analyses']} ({ov['analyses_3_reviewers']} by 3 reviewers, {ov['analyses_2_reviewers']} by 2 so far)"],
        ["Completed reviews (one reviewer finishing one analysis)", ov["ratings"]],
        ["Reviewers who finished every analysis of their paper", f"{ov['reviewers_finished']} of {ov['reviewer_assignments']}"],
    ])
    p2_note = (f" Part 2 uses only the {ov['p2_analyses']} analyses that all {ov['p2_min_reviewers']} reviewers have finished."
               if ov.get("p2_min_reviewers", 1) > 1 else "")
    intro2 = find(doc, "Each analysis's reviews are combined by majority vote")
    set_text(intro2, intro2.text.split(" Part 2 uses only")[0] + p2_note)
    p = find(doc, "Every explanation behind")
    set_text(p, p.text.split("(")[0] + f"({ov['non_yes_part2_answers']} in all) was read and coded into themes. One answer can carry more than one theme.")
    p = find(doc, "A theme is listed only if")
    set_text(p, "A theme is listed only if it appears in at least 3 different analyses and comes from at least 2 reviewers.")
    theme_table = next(t for t in doc.tables if t.rows[0].cells[0].text == "Theme")
    fill_table(theme_table, [[t["theme"], t["description"], t["analyses"], t["reviewers"], t["papers"]] for t in themes])
    p = find(doc, "Rated 1 (not justified)")
    set_text(p, f"Rated 1 (not justified) to 5 (fully justified). {ov['conclusion_share_5']:.0%} of all ratings are a 5, "
             "so this question separates analyses very little." + ALL_RATINGS_NOTE.replace("These charts include", "This chart includes"))
    p = find(doc, "Code reviewers only, rated 1")
    set_text(p, p.text.split(ALL_RATINGS_NOTE)[0] + ALL_RATINGS_NOTE
             + f" On the {ov['code_analyses']} analyses used in the summary at the top, the average code rating is {ov['code_mean_p2']:.2f}.")
    agree_table = next(t for t in doc.tables if [c.text for c in t.rows[0].cells] == ["Question", "Analyses", "Agreement"])
    fill_table(agree_table, [[r["question"], r["analyses"],
                              f"{(r['within_1'] if r['level'] == 'ordinal' else r['exact_agreement_yes_vs_not']):.0%}"] for r in agreement])

    # Dated notes under "Reading these results" (same wording style; facts that changed since the template).
    set_text(find(doc, "This is early data"),
             f"This is early data: {ov['papers']} papers, each analysis reviewed by two or three people. Three code reviewers have "
             "not finished a paper yet (Jiang, Wilde and Grose, and Clark), so Part 2 leaves out the "
             f"{ov['analyses'] - ov.get('p2_analyses', ov['analyses'])} analyses without all three reviews; they will be added "
             "once those reviews are in.")
    # Drop a note about a theme that is no longer listed under the reporting rule.
    listed = {t["theme"] for t in themes}
    for para in list(doc.paragraphs):
        quoted = para.text.split('"')[1] if para.text.startswith('"') and para.text.count('"') >= 2 else None
        if para.style.name == "List Bullet" and quoted and quoted not in listed and quoted.startswith("Model not used"):
            para._p.getparent().remove(para._p)
    p = next((x for x in doc.paragraphs if x.text.startswith("One theme, ") or x.text.startswith("Themes raised by a single")), None)
    if p is not None:
        set_text(p, "Themes raised by a single reviewer are not listed. The main one left out, \"Limitation of the original study\" "
                 "(small samples, observational data), is about the original studies rather than the agent's choices; round 2's "
                 "instructions will ask reviewers to judge the agent's choices given the data.")

    # Quotes: one Heading 3 per listed theme and up to two examples, rebuilt from the template's own paragraphs.
    intro = find(doc, "Up to two examples per theme")
    part3 = find(doc, "Part 3:")
    block, el = [], intro._p.getnext()
    while el is not None and el is not part3._p:
        block.append(el)
        el = el.getnext()
    heading_tpl = next(copy.deepcopy(e) for e in block if Paragraph(e, intro._parent).style.name == "Heading 3")
    bullet_tpl = next(copy.deepcopy(e) for e in block if Paragraph(e, intro._parent).style.name == "List Bullet")
    for e in block:
        e.getparent().remove(e)
    by_theme = defaultdict(list)
    for q in quotes:
        if q["rank"] == 1:
            by_theme[q["theme"]].append(q)
    for t in themes:
        examples = by_theme[t["theme"]][:2]
        if not examples:
            continue
        h = copy.deepcopy(heading_tpl)
        part3._p.addprevious(h)
        set_text(Paragraph(h, intro._parent), t["theme"])
        for q in examples:
            b = copy.deepcopy(bullet_tpl)
            part3._p.addprevious(b)
            runs = Paragraph(b, intro._parent).runs
            runs[0].text = f"“{q['quote']}”"
            runs[1].text = f"  ({q['reviewer']}, {q['paper']} {q['analysis']}, {q['question']}: {q['answer']})"

    # Charts: swap in the redrawn images, keeping each one's width and fixing its height to the new aspect ratio.
    from PIL import Image
    drawings = list(doc.element.body.iter(qn("w:drawing")))
    assert len(drawings) == len(FIGURES), f"expected {len(FIGURES)} charts, found {len(drawings)}"
    for drawing, name in zip(drawings, FIGURES):
        path = OUT / "_docx_figures" / f"{name}.png"
        rid = drawing.find(".//" + qn("a:blip")).get(qn("r:embed"))
        doc.part.related_parts[rid]._blob = path.read_bytes()
        w, h = Image.open(path).size
        for ext in (drawing.find(".//" + qn("wp:extent")), drawing.find(".//" + qn("a:ext"))):
            ext.set("cy", str(int(int(ext.get("cx")) * h / w)))

    # Part 3 themes: a new section built from the template's own Part 2 elements, so it matches their style.
    from docx.table import Table
    part4 = find(doc, "Part 4:")._p
    tpl = lambda start: copy.deepcopy(find(doc, start)._p)
    def put(el, text=None):
        part4.addprevious(el)
        if text is not None:
            set_text(Paragraph(el, intro._parent), text)
        return el
    put(tpl("Why reviewers didn't say"), P3_HEADING)
    put(tpl("Every explanation behind"),
        f"Every explanation behind a code fidelity rating below 5 ({ov['below5_part3_answers']} in all) was read and coded into themes, "
        "separately from Part 2. Reviewers write these after seeing the code. One answer can carry more than one theme.")
    put(tpl("A theme is listed only if"), "A theme is listed only if it appears in at least 3 different analyses and comes from at least 2 reviewers.")
    chart = copy.deepcopy(drawings[FIGURES.index("p2_themes")].getparent().getparent())  # the paragraph holding the Part 2 themes chart
    rid, _ = doc.part.get_or_add_image(str(OUT / "_docx_figures" / "p3_themes.png"))
    chart.find(".//" + qn("a:blip")).set(qn("r:embed"), rid)
    w, h = Image.open(OUT / "_docx_figures" / "p3_themes.png").size
    for ext in (chart.find(".//" + qn("wp:extent")), chart.find(".//" + qn("a:ext"))):
        ext.set("cy", str(int(int(ext.get("cx")) * h / w)))
    ids = [int(x.get("id")) for x in doc.element.body.iter(qn("wp:docPr"))]
    chart.find(".//" + qn("wp:docPr")).set("id", str(max(ids) + 1))
    put(chart)
    table_el = copy.deepcopy(theme_table._tbl)
    put(table_el)
    fill_table(Table(table_el, theme_table._parent), [[t["theme"], t["description"], t["analyses"], t["reviewers"], t["papers"]] for t in themes3])
    put(tpl("In reviewers' words"))
    put(tpl("Up to two examples per theme"))
    by_theme3 = defaultdict(list)
    for q in quotes3:
        if q["rank"] == 1:
            by_theme3[q["theme"]].append(q)
    for t in themes3:
        put(copy.deepcopy(heading_tpl), t["theme"])
        for q in by_theme3[t["theme"]][:2]:
            runs = Paragraph(put(copy.deepcopy(bullet_tpl)), intro._parent).runs
            runs[0].text = f"\u201c{q['quote']}\u201d"
            runs[1].text = f"  ({q['reviewer']}, {q['paper']} {q['analysis']}, rated {q['answer']})"

    doc.save(args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
