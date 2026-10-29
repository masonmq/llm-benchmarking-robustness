"""Export Cloudflare D1 annotation responses to a flat CSV file."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path


def run_wrangler_json(command: list[str]) -> object:
    """Run Wrangler, tolerating a transient successful response with no JSON."""
    attempts = []
    for attempt in range(2):
        print(f"Querying Cloudflare D1 (attempt {attempt + 1}/2)…", flush=True)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(
                "Wrangler did not respond within 60 seconds. Check your internet connection "
                "and run `npx wrangler login` if your Cloudflare session has expired."
                + (f"\n{detail}" if detail else "")
            ) from exc
        attempts.append(result)
        if result.returncode == 0:
            for output in (result.stdout, result.stderr):
                output = output.strip()
                if not output:
                    continue
                try:
                    return json.loads(output)
                except json.JSONDecodeError:
                    # Wrangler warnings can occasionally precede the JSON.
                    starts = [i for i, char in enumerate(output) if char in "[{"]
                    for start in starts:
                        try:
                            return json.loads(output[start:])
                        except json.JSONDecodeError:
                            continue
        if attempt == 0:
            time.sleep(1)

    last = attempts[-1]
    detail = (last.stderr or last.stdout or "Wrangler returned no output").strip()
    raise RuntimeError(
        f"Could not read the D1 response after two attempts (exit {last.returncode}).\n{detail}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "exports/annotation_responses.csv",
    )
    parser.add_argument("--paper", help="Only export one paper ID")
    parser.add_argument("--database", default="robustness-annotations")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "deployment/cloudflare/wrangler.toml",
    )
    args = parser.parse_args()

    conditions = ["analysis_id <> '_paper_review'"]
    if args.paper:
        safe_paper = args.paper.replace("'", "''")
        conditions.append(f"paper_id = '{safe_paper}'")
    where = " WHERE " + " AND ".join(conditions)
    sql = (
        "SELECT paper_id, annotator, analysis_id, payload, updated_at "
        f"FROM responses{where} ORDER BY paper_id, annotator, analysis_id"
    )
    command = [
        "npx", "--yes", "wrangler", "d1", "execute", args.database,
        "--remote", "--json", "--command", sql, "--config", str(args.config.resolve()),
    ]
    response = run_wrangler_json(command)
    query = response[0] if isinstance(response, list) else response
    records = query.get("results", [])

    rows = []
    answer_fields = set()
    for record in records:
        try:
            answers = json.loads(record.pop("payload"))
        except (TypeError, json.JSONDecodeError):
            answers = {}
        answer_fields.update(answers)
        rows.append((record, answers))

    fixed = ["paper_id", "annotator", "analysis_id", "updated_at"]
    fields = fixed + sorted(answer_fields)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record, answers in rows:
            writer.writerow({**record, **answers})
    print(f"Exported {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
