"""Build a GitHub Pages site and a separate private Cloudflare upload bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from extract import extract_paper
from preview import MAX_ROWS, preview_file

APP_DIR = Path(__file__).resolve().parent


def json_safe(value):
    """Replace float NaN/Infinity with None anywhere in a JSON-like structure."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def preview_key(relative: str, page: int) -> str:
    digest = hashlib.sha256(relative.encode()).hexdigest()
    return f"previews/{digest}/{page}.json"


def build(paper_folder: Path, site_dir: Path, private_dir: Path, api_base: str, max_pages: int):
    packet = extract_paper(paper_folder)
    paper_id = packet["case"]["case_id"]
    shutil.copytree(APP_DIR / "static", site_dir, dirs_exist_ok=True)
    (site_dir / "config.js").write_text(
        "window.APP_CONFIG=" + json.dumps({"apiBase": api_base.rstrip("/"), "paperId": paper_id}) + ";\n",
        encoding="utf-8",
    )
    destination = private_dir / paper_id
    destination.mkdir(parents=True, exist_ok=True)
    root = Path(packet["paper_dir"])
    packet["paper_dir"] = None
    # NaN/Infinity (e.g. an ANOVA residual row's F and p) are not valid JSON and break the Cloudflare worker's JSON.parse;
    # write them as null, and let json.dumps fail loudly on anything else invalid.
    (destination / "packet.json").write_text(json.dumps(json_safe(packet), ensure_ascii=False, allow_nan=False), encoding="utf-8")

    paths = {packet["source_materials"].get("paper")}
    paths.update(item["path"] for item in packet["source_materials"].get("support_files", []))
    for analysis in packet["analyses"]:
        paths.update(value for value in analysis["files"].values() if value)
    for relative in sorted(path for path in paths if path):
        source = root / relative
        file_target = destination / "files" / relative
        file_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, file_target)
        for page in range(1, max_pages + 1):
            preview = preview_file(source, page)
            preview["preview_capped"] = False
            target = destination / preview_key(relative, page)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(json_safe(preview), ensure_ascii=False, allow_nan=False), encoding="utf-8")
            if preview.get("viewer") != "table" or preview.get("shown_rows", 0) < MAX_ROWS:
                break
            if page == max_pages:
                preview["preview_capped"] = True
                target.write_text(json.dumps(json_safe(preview), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"Pages site: {site_dir}\nPrivate bundle: {private_dir}\nPaper: {paper_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_folder", type=Path)
    parser.add_argument("--site-dir", type=Path, default=APP_DIR / "dist" / "site")
    parser.add_argument("--private-dir", type=Path, default=APP_DIR / "dist" / "private")
    parser.add_argument("--api-base", required=True, help="Cloudflare Worker URL")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum 100-row preview pages per data file")
    args = parser.parse_args()
    build(args.paper_folder.resolve(), args.site_dir, args.private_dir, args.api_base, max(1, args.max_pages))


if __name__ == "__main__":
    main()
