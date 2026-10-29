"""Safe, bounded browser previews for research files."""

from __future__ import annotations

import csv
import html
import io
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MAX_ROWS = 100
MAX_COLUMNS = 100
MAX_TEXT_BYTES = 2_000_000


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _table(columns, rows, total_rows=None, metadata=None, page=1):
    columns = [str(c) for c in list(columns)[:MAX_COLUMNS]]
    clean_rows = [[_clean(v) for v in list(row)[:len(columns)]] for row in list(rows)[:MAX_ROWS]]
    profile = []
    for index, name in enumerate(columns):
        values = [row[index] for row in clean_rows if index < len(row)]
        present = [v for v in values if v not in (None, "")]
        profile.append({
            "name": name,
            "type": type(present[0]).__name__ if present else "unknown",
            "missing_in_preview": len(values) - len(present),
            "unique_in_preview": len({str(v) for v in present}),
            "example": present[0] if present else None,
            "label": (metadata or {}).get("column_labels", {}).get(name),
            "value_labels": (metadata or {}).get("value_labels", {}).get(name),
        })
    return {"viewer": "table", "columns": columns, "rows": clean_rows,
            "total_rows": total_rows, "shown_rows": len(clean_rows),
            "page": page, "page_size": MAX_ROWS,
            "column_profile": profile, "metadata": metadata or {}}


def _docx(path: Path):
    """Convert DOCX semantics to HTML; use a minimal fallback without Mammoth."""
    try:
        import mammoth

        with path.open("rb") as stream:
            converted = mammoth.convert_to_html(stream)
        return {
            "viewer": "html",
            "html": converted.value,
            "conversion_warnings": [message.message for message in converted.messages],
        }
    except ImportError:
        pass

    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(ns + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(ns + "t"))
        if text.strip():
            paragraphs.append(f"<p>{html.escape(text)}</p>")
    return {
        "viewer": "html",
        "html": "".join(paragraphs),
        "conversion_warnings": ["Install mammoth for full document formatting."],
    }


def _pandas_table(path: Path, extension: str, page: int):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Install pandas and the reader package for this format") from exc
    if extension in {".xlsx", ".xls"}:
        book = pd.ExcelFile(path); name = book.sheet_names[0]; offset = (page - 1) * MAX_ROWS
        frame = pd.read_excel(path, sheet_name=name, nrows=MAX_ROWS, skiprows=(range(1, offset + 1) if offset else None))
        return _table(frame.columns, frame.itertuples(index=False, name=None), metadata={"sheet": name, "available_sheets": book.sheet_names}, page=page)
    if extension in {".sav", ".por", ".dta", ".sas7bdat", ".xpt"}:
        try:
            import pyreadstat
            reader = {".sav": pyreadstat.read_sav, ".por": pyreadstat.read_por,
                      ".dta": pyreadstat.read_dta, ".sas7bdat": pyreadstat.read_sas7bdat,
                      ".xpt": pyreadstat.read_xport}[extension]
            _, full_meta = reader(str(path), metadataonly=True)
            frame, meta = reader(str(path), row_offset=(page - 1) * MAX_ROWS, row_limit=MAX_ROWS)
            if extension == ".dta":
                frame = frame.map(_fix_legacy_text)
            labels = dict(zip(meta.column_names, meta.column_labels))
            metadata = {"column_labels": labels, "value_labels": meta.variable_value_labels,
                        "file_label": meta.file_label}
            return _table(frame.columns, frame.itertuples(index=False, name=None), full_meta.number_rows, metadata, page)
        except ImportError as exc:
            raise RuntimeError("Install pyreadstat to preview this statistical format") from exc
    else:
        raise RuntimeError(f"No pandas reader configured for {extension}")


def _r_table(path: Path, page: int):
    try:
        import pyreadr
    except ImportError as exc:
        raise RuntimeError("Install pyreadr to preview R data files") from exc
    objects = pyreadr.read_r(str(path))
    if not objects:
        raise RuntimeError("No tabular objects found in the R data file")
    name, frame = next(iter(objects.items()))
    offset = (page - 1) * MAX_ROWS
    return _table(frame.columns, frame.iloc[offset:offset + MAX_ROWS].itertuples(index=False, name=None), len(frame), {"object": name or "unnamed", "available_objects": [k or "unnamed" for k in objects]}, page)


def _decode(raw: bytes) -> str:
    """Decode text from replication packages, which are often not UTF-8 (e.g. GB18030 for Chinese data).
    A Chinese reading is accepted only when most non-ASCII characters it yields are CJK."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    for encoding in ("gb18030", "big5", "shift_jis"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        non_ascii = [ch for ch in text if ord(ch) > 127]
        cjk = sum(1 for ch in non_ascii if "\u3000" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef")
        if non_ascii and cjk / len(non_ascii) > 0.6:
            return text
    return raw.decode("cp1252", errors="replace")


def _fix_legacy_text(value: Any) -> Any:
    """Old Stata files carry no encoding, so non-ASCII text arrives read as Latin-1; re-decode it properly."""
    if isinstance(value, str) and any("\x80" <= ch <= "\xff" for ch in value):
        try:
            return _decode(value.encode("latin-1"))
        except UnicodeEncodeError:
            return value
    return value


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _markdown(path: Path) -> dict[str, Any]:
    import markdown

    # Escape raw HTML so a file cannot inject markup into the viewer; Markdown formatting still renders.
    source = _decode(path.read_bytes()).replace("&", "&amp;").replace("<", "&lt;")
    return {"viewer": "html", "html": markdown.markdown(source, extensions=["tables", "sane_lists"])}


def _plain_document(text: str) -> dict[str, Any]:
    return {"viewer": "html", "html": f'<pre class="plain-text">{_escape(text)}</pre>'}


def _tab_rows(text: str) -> list[list[str]]:
    return [line.rstrip("\r").rstrip("\t").split("\t") for line in text.splitlines() if line.strip()]


def _ztree_tables(text: str) -> dict[str, Any] | None:
    """z-Tree session exports (saved as .xls but really tab-separated text) hold several tables, one per
    z-Tree table name in column 3, each preceded by a header row. Show each as its own table."""
    rows = _tab_rows(text)
    if len(rows) < 2 or any(len(row) < 4 or not row[2].isalpha() for row in rows):
        return None
    tables: dict[str, dict[str, Any]] = {}
    for row in rows:
        table = tables.setdefault(row[2], {"header": row[3:], "rows": []})
        if row[3:] != table["header"]:
            table["rows"].append(row[3:])
    parts = []
    for name, table in tables.items():
        head = "".join(f"<th>{_escape(cell)}</th>" for cell in table["header"])
        body = "".join("<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in row) + "</tr>" for row in table["rows"][:MAX_ROWS])
        parts.append(f"<h3>{_escape(name)} table ({len(table['rows'])} rows)</h3>"
                     f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
    note = "<p>z-Tree session export. Each z-Tree table is shown separately; repeated header rows are omitted.</p>"
    return {"viewer": "html", "html": note + "".join(parts)}


def _ztree_subjects(text: str, page: int) -> dict[str, Any] | None:
    """z-Tree subject files (.sbj) store one questionnaire item per row and one participant per column;
    transpose them to one row per participant."""
    rows = [row for row in _tab_rows(text) if len(row) > 1]
    if len(rows) < 2:
        return None
    width = max(len(row) for row in rows)
    columns = [row[0] for row in rows]
    participants = [[row[i] if i < len(row) else "" for row in rows] for i in range(1, width)]
    offset = (page - 1) * MAX_ROWS
    return _table(columns, participants[offset:offset + MAX_ROWS], len(participants), page=page)


CODEBOOK_VALUES_SHOWN = 40
_VARIABLE_LINE = re.compile(r"^(\d+)\) (\S+)\s*$")


def _codebook(text: str) -> dict[str, Any] | None:
    """SDA-style codebooks ("Data File: ...Codebook"): one block per variable, with tab-separated value tables.
    Render each variable as a heading, its description, and its values as a small table."""
    lines = [line.rstrip("\r") for line in text.splitlines()]
    if not lines or not lines[0].startswith("Data File:") or "codebook" not in lines[0].lower():
        return None
    blocks, current = [], None
    for line in lines[1:]:
        match = _VARIABLE_LINE.match(line)
        if match:
            current = {"name": f"{match.group(1)}) {match.group(2)}", "text": [], "rows": []}
            blocks.append(current)
        elif current is not None and line.strip():
            (current["rows"] if "\t" in line else current["text"]).append(line)
    if not blocks:
        return None
    parts = [f"<p>{_escape(lines[0])} &middot; {len(blocks)} variables</p>"]
    for block in blocks:
        parts.append(f"<h3>{_escape(block['name'])}</h3>" + "".join(f"<p>{_escape(t)}</p>" for t in block["text"]))
        if block["rows"]:
            rows = [row.split("\t") for row in block["rows"]]
            width = max(len(row) for row in rows)
            shown = rows[:CODEBOOK_VALUES_SHOWN]
            body = "".join("<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in row + [""] * (width - len(row))) + "</tr>" for row in shown)
            more = f"<p>&hellip; {len(rows) - len(shown)} more values not shown; download the original for the full list.</p>" if len(rows) > len(shown) else ""
            parts.append(f'<div class="table-scroll"><table><tbody>{body}</tbody></table></div>{more}')
    return {"viewer": "html", "html": "".join(parts)}


def _fixed_width(path: Path, page: int) -> dict[str, Any] | None:
    """Fixed-width data (.dat) described by a sibling .col file of lines like "2) IAPYEAR: 17-20"."""
    specs = sorted(path.parent.glob(path.stem + "*.col")) or sorted(path.parent.glob("*.col"))
    if not specs:
        return None
    names, colspecs = [], []
    for line in _decode(specs[0].read_bytes()).splitlines():
        match = re.match(r"^\s*\d+\)\s*(\S+):\s*(\d+)(?:-(\d+))?", line)
        if match:
            start = int(match.group(2)) - 1
            names.append(match.group(1)); colspecs.append((start, int(match.group(3) or match.group(2))))
    if not names:
        return None
    import pandas as pd

    offset = (page - 1) * MAX_ROWS
    total = sum(1 for line in path.open("rb") if line.strip())
    frame = pd.read_fwf(path, colspecs=colspecs, names=names, header=None, skiprows=offset, nrows=MAX_ROWS, dtype=str)
    rows = [["" if pd.isna(value) else value for value in row] for row in frame.itertuples(index=False, name=None)]
    return _table(names, rows, total, metadata={"layout": f"fixed-width columns from {specs[0].name}"}, page=page)


_SAFE_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li", "table", "thead", "tbody", "tr",
              "th", "td", "b", "strong", "i", "em", "code", "pre", "blockquote", "a", "span", "div", "sup", "sub"}
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math", "head", "title"}


def _safe_html(source: str) -> dict[str, Any]:
    """Render an HTML file as a plain document: keep structural tags, drop scripts, styles, attributes
    (except http(s) link targets) and anything executable, and escape all text."""
    from html.parser import HTMLParser

    class Cleaner(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self.skip = [], 0

        def handle_starttag(self, tag, attrs):
            if tag in _DROP_WITH_CONTENT:
                self.skip += 1
            elif not self.skip and tag in _SAFE_TAGS:
                href = dict(attrs).get("href") or ""
                link = f' href="{_escape(href)}" target="_blank" rel="noopener"' if tag == "a" and href.startswith(("http://", "https://")) else ""
                self.out.append(f"<{tag}{link}>")

        def handle_endtag(self, tag):
            if tag in _DROP_WITH_CONTENT:
                self.skip = max(0, self.skip - 1)
            elif not self.skip and tag in _SAFE_TAGS and tag != "br":
                self.out.append(f"</{tag}>")

        def handle_data(self, data):
            if not self.skip:
                self.out.append(_escape(data))

    cleaner = Cleaner()
    cleaner.feed(source)
    return {"viewer": "html", "html": "".join(cleaner.out)}


_SMCL_CHARS = {"|": "│", "-": "─", "+": "┼", "TT": "┬", "BT": "┴", "TLC": "┌", "TRC": "┐", "BLC": "└", "BRC": "┘",
               "LT": "├", "RT": "┤"}
_SMCL_STYLES = {"com": "smcl-com", "res": "smcl-res", "err": "smcl-err", "txt": "", "text": "", "inp": "smcl-com",
                "input": "smcl-com", "result": "smcl-res", "error": "smcl-err"}


def _smcl(text: str) -> dict[str, Any]:
    """Render a Stata SMCL log the way Stata displays it: rules, table borders, column alignment, and
    commands/results styled differently. Unknown tags are dropped."""
    out_lines = []
    for raw in text.splitlines():
        line, column, style, parts = raw.rstrip("\r"), 0, "", []

        def emit(chunk: str):
            nonlocal column
            if chunk:
                parts.append(f'<span class="{style}">{_escape(chunk)}</span>' if style else _escape(chunk))
                column += len(chunk)

        for token in re.split(r"(\{[^{}]*\})", line):
            match = re.fullmatch(r"\{([^{}]*)\}", token or "")
            if not match:
                emit(token)
                continue
            name, _, arg = match.group(1).partition(" ")
            if name in _SMCL_STYLES:
                style = _SMCL_STYLES[name]
                if arg:
                    emit(arg)
            elif name in ("hline", ".-"):
                emit("─" * (int(arg) if arg.strip().isdigit() else 80 if name == ".-" else 12))
            elif name == "c":
                emit(_SMCL_CHARS.get(arg.strip(), ""))
            elif name in ("col", "column") and arg.strip().isdigit():
                emit(" " * max(0, int(arg) - 1 - column))
            elif name == "space" and arg.strip().isdigit():
                emit(" " * int(arg))
            elif name in ("ralign", "lalign", "center") and arg:
                width, _, label = arg.partition(":")
                label, width = label.strip(), int(width) if width.isdigit() else len(label.strip())
                emit(label.rjust(width) if name == "ralign" else label.ljust(width) if name == "lalign" else label.center(width))
        out_lines.append("".join(parts))
    return {"viewer": "html", "html": f'<pre class="plain-text smcl">{chr(10).join(out_lines)}</pre>'}


def _text_file(path: Path, text: str, extension: str, page: int) -> dict[str, Any]:
    """Best readable view of a plain-text file: tables for tab-separated data, otherwise a readable document."""
    if extension == ".smcl" or text.lstrip().startswith("{smcl}"):
        return _smcl(text)
    if extension == ".dat" and (result := _fixed_width(path, page)):
        return result
    if (result := _codebook(text)):
        return result
    if extension == ".sbj" and (result := _ztree_subjects(text, page)):
        return result
    if extension == ".xls" and (result := _ztree_tables(text)):
        return result
    rows = _tab_rows(text)
    if rows and sum("\t" in line for line in text.splitlines()[:50]) >= min(len(rows), 50) * 0.8:
        return _delimited(path, "\t", page)
    return _plain_document(text)


def _sniff_text(path: Path) -> str | None:
    """Return the file's leading text if it looks like plain text (no NUL bytes), else None."""
    head = path.read_bytes()[:MAX_TEXT_BYTES]
    if b"\x00" in head[:8192]:
        return None
    return _decode(head)


def _text_view(path: Path, text: str, language: str = "text") -> dict[str, Any]:
    return {"viewer": "code", "language": language, "text": text, "truncated": path.stat().st_size > MAX_TEXT_BYTES}


def _delimited(path: Path, delimiter: str, page: int) -> dict[str, Any]:
    reader = csv.reader(io.StringIO(_decode(path.read_bytes()), newline=""), delimiter=delimiter)
    columns = next(reader, [])
    all_rows = list(reader); offset = (page - 1) * MAX_ROWS
    return _table(columns, all_rows[offset:offset + MAX_ROWS], len(all_rows), page=page)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}  # e.g. experiment stimuli


def is_previewable(path: Path) -> bool:
    """Whether the viewer can show this file; files it cannot show are left out of the review packet."""
    return preview_file(path)["viewer"] not in {"download", "error"}


def preview_file(path: Path, page: int = 1) -> dict[str, Any]:
    page = max(1, page)
    extension = path.suffix.lower()
    base = {"name": path.name, "extension": extension, "size_bytes": path.stat().st_size}
    with path.open("rb") as handle:
        head = handle.read(4)
    try:
        if head in (b"$FL2", b"$FL3"):  # SPSS system file saved under another extension (e.g. Alves's Exp2.dat)
            result = _pandas_table(path, ".sav", page)
        elif extension in IMAGE_EXTENSIONS:
            result = {"viewer": "image"}
        elif extension == ".pdf":
            result = {"viewer": "pdf"}
        elif extension == ".json":
            result = {"viewer": "json", "data": json.loads(path.read_text(encoding="utf-8"))}
        elif extension in {".html", ".htm"}:
            result = _safe_html(_decode(path.read_bytes()))
        elif extension == ".md":
            result = _markdown(path)
        elif extension in {".txt", ".log"}:
            text = _sniff_text(path) or ""
            result = _codebook(_decode(path.read_bytes())) or _plain_document(text)
        elif extension == ".sbj":
            raise RuntimeError("handled as text below")
        elif extension in {".py", ".r", ".do", ".ado", ".sas"}:
            text = _decode(path.read_bytes()[:MAX_TEXT_BYTES])
            result = _text_view(path, text, extension.lstrip("."))
        elif extension in {".csv", ".tsv"}:
            result = _delimited(path, "," if extension == ".csv" else "\t", page)
        elif extension == ".docx":
            result = _docx(path)
        elif extension in {".xlsx", ".xls", ".sav", ".por", ".dta", ".sas7bdat", ".xpt"}:
            result = _pandas_table(path, extension, page)
        elif extension in {".rds", ".rdata", ".rda"}:
            result = _r_table(path, page)
        else:
            raise RuntimeError("No integrated preview is available for this format.")
    except Exception as exc:
        # Some files are plain text under another extension (e.g. z-Tree exports saved as .xls or .sbj).
        text = _sniff_text(path)
        result = (_text_file(path, text, extension, page) if text is not None
                  else {"viewer": "download", "message": f"No integrated preview is available for this file ({exc})."})
    return {**base, **result}
