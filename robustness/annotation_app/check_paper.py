"""Pre-launch check of paper folders: run this before building a paper's site.

  python check_paper.py PAPER_FOLDER [PAPER_FOLDER ...]

Flags anything that would block or confuse annotators: missing analyses or code, missing source
materials, a missing Task 2 restriction, and an oversized packet. Also lists Task 1 analyses dropped because
their run's Task 2 gives the identical result, and appends them to the duplicates record.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from extract import _evaluation_assignment, extract_paper
from preview import preview_file

# Each human reanalyst corresponds to one agent run (Task 1 + Task 2), so expected analyses = 2 x human count.
RESULTS_TABLE = Path(__file__).resolve().parents[1] / "data" / "Annotator-Test" / "58_results - Sheet1.csv"
MAX_PACKET_BYTES = 1_000_000  # keeps the Cloudflare worker well under its CPU limit per request
# Latin-1 high characters in a row, replacement characters, or UTF-8 read as Latin-1: signs of a wrong text encoding.
GARBLED = re.compile(r"[\x80-\xff]{2,}|\ufffd|Ã.")
DUPLICATES_RECORD = Path(__file__).resolve().parents[1] / "data" / "annotators" / "dropped_duplicates.csv"


def record_duplicates(case_id: str, duplicates: list[dict]) -> None:
    """Keep one row per dropped analysis in a shared CSV, replacing this paper's earlier rows."""
    fields = ["paper_id", "dropped", "kept", "estimate", "p_value", "sample_size"]
    rows = []
    if DUPLICATES_RECORD.exists():
        with DUPLICATES_RECORD.open(encoding="utf-8") as stream:
            rows = [row for row in csv.DictReader(stream) if row["paper_id"] != case_id]
    rows += [{"paper_id": case_id, **duplicate} for duplicate in duplicates]
    DUPLICATES_RECORD.parent.mkdir(parents=True, exist_ok=True)
    with DUPLICATES_RECORD.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["paper_id"], row["dropped"])))


def expected_analyses(case_id: str) -> int | None:
    """2 x the number of human reanalyses listed for this paper, or None if the paper isn't in the table."""
    if not RESULTS_TABLE.exists():
        return None
    with RESULTS_TABLE.open(encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            name = row["Paper"].replace("*", "").strip().casefold()
            if case_id.split("_")[0].casefold() == name:
                return 2 * sum(int(n) for n in re.findall(r"(\d+)\s+(?:Support|Inconclusive|Opposite)", row["Human reanalyses"]))
    return None


def check(folder: Path) -> bool:
    packet = extract_paper(folder)
    analyses = packet["analyses"]
    case_id = packet["case"].get("case_id", folder.name)
    problems, notes = [], []

    if case_id != folder.name:
        problems.append(f"case_id {case_id!r} does not match folder name")
    duplicates = packet["dropped_duplicates"]
    expected = expected_analyses(case_id)
    if expected is None:
        notes.append("paper not in the results table; cannot check the number of analyses")
    elif len(analyses) + len(duplicates) != expected:
        problems.append(f"{len(analyses) + len(duplicates)} analyses before dropping duplicates "
                        f"(expected {expected}: 2 per human reanalysis)")
    for analysis in analyses:
        failed = [check["label"] for check in analysis["automated_checks"] if check["status"] != "pass"]
        if failed:
            problems.append(f"{analysis['display_name']}: {', '.join(failed)}")
        if analysis["execution"]["potential_result_mismatch"]:
            notes.append(f"{analysis['display_name']}: result-mismatch warning will show to annotators")

    if not packet["source_materials"]["paper"]:
        problems.append("original paper PDF missing")
    data_files = [f for f in packet["source_materials"]["support_files"] if f["kind"] == "data"]
    if not data_files:
        problems.append("no data files for annotators to inspect (expected a data/ folder in the first run)")
    for support in packet["source_materials"]["support_files"]:
        shown = preview_file(folder / support["path"])
        text = " ".join(str(cell) for row in shown.get("rows", [])[:100] for cell in row)
        text += " ".join(map(str, shown.get("columns", []))) + shown.get("text", "") + shown.get("html", "")
        if GARBLED.search(text):
            notes.append(f"{support['name']}: preview may show garbled characters (check the text encoding)")
    for excluded in packet["source_materials"]["excluded_files"]:
        if excluded["used_by_agent"]:
            problems.append(f"{excluded['name']} is used by the agent's code but cannot be previewed")
        else:
            notes.append(f"left out (no preview available): {excluded['name']}")
    if not _evaluation_assignment(case_id).get("task2_instruction"):
        problems.append("no Task 2 restriction found in all_claims.xlsx")

    size = len(json.dumps(packet, ensure_ascii=False).encode())
    if size > MAX_PACKET_BYTES:
        problems.append(f"packet is {size / 1e6:.2f} MB (limit {MAX_PACKET_BYTES / 1e6:.0f} MB)")

    for duplicate in duplicates:
        notes.append(f"dropped {duplicate['dropped']} (same result as {duplicate['kept']})")
    record_duplicates(case_id, duplicates)

    print(f"\n{'FAIL' if problems else 'OK  '} {case_id}")
    kinds = [f["kind"] for f in packet["source_materials"]["support_files"]]
    print(f"     {len(analyses)} analyses shown, {kinds.count('data')} data, {kinds.count('documentation')} doc, "
          f"{kinds.count('code')} original-code file(s), packet {size / 1e3:.0f} KB")
    for line in problems:
        print(f"     PROBLEM: {line}")
    for line in notes:
        print(f"     note: {line}")
    return not problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folders", nargs="+", type=Path)
    args = parser.parse_args()
    results = [check(folder) for folder in args.folders]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
