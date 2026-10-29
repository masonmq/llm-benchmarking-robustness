"""Local annotation web server with SQLite autosave."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from extract import extract_paper
from preview import preview_file

APP_DIR = Path(__file__).resolve().parent

# Answers locked once each part is submitted. Keep in sync with deployment/cloudflare/worker.js.
PART_FIELDS = {
    2: ("claim_alignment", "claim_alignment_explanation", "method_validity", "method_validity_explanation",
        "restriction_compliance", "restriction_compliance_explanation"),
    3: ("implementation_fidelity", "implementation_fidelity_explanation"),
    4: ("conclusion_validity", "conclusion_validity_explanation", "additional_comments"),
}


def is_code_reviewer(annotator: str) -> bool:
    """Annotators issued an `an-` username skip Part 3 (code review); everyone else reviews code."""
    return not annotator.casefold().startswith("an-")


def stages(payload: dict) -> tuple[bool, bool, bool]:
    return (
        payload.get("part2_submitted") is True,
        payload.get("part3_submitted") is True,
        payload.get("part4_submitted") is True,
    )


def unlocked(payload: dict, code_reviewer: bool) -> tuple[bool, bool]:
    """Return whether the code and the execution results may be shown."""
    plan_done, implementation_done, _ = stages(payload)
    return code_reviewer and plan_done, implementation_done if code_reviewer else plan_done


def payload_error(old: dict, new: dict, task_id: str, code_reviewer: bool) -> str | None:
    if not isinstance(new, dict):
        return "invalid response payload"
    for part, fields in PART_FIELDS.items():
        flag = f"part{part}_submitted"
        if old.get(flag) is True and (new.get(flag) is not True or any(old.get(key) != new.get(key) for key in fields)):
            return f"Part {part} has already been submitted and cannot be changed."
    explained = lambda key: bool(new.get(key)) and bool(str(new.get(f"{key}_explanation", "")).strip())
    rated = lambda key: str(new.get(key, "")) in {"1", "2", "3", "4", "5"} and bool(str(new.get(f"{key}_explanation", "")).strip())
    if new.get("part2_submitted") is True and not (explained("claim_alignment") and explained("method_validity")):
        return "Complete every Part 2 answer and explanation before submitting."
    # Only enforced on first submission so Task 2 answers submitted before this question existed stay valid.
    if (new.get("part2_submitted") is True and old.get("part2_submitted") is not True
            and task_id == "Task2" and not explained("restriction_compliance")):
        return "Complete every Part 2 answer and explanation before submitting."
    if new.get("part3_submitted") is True and not code_reviewer:
        return "Part 3 is not assigned to this annotator."
    if new.get("part3_submitted") is True and not (new.get("part2_submitted") is True and rated("implementation_fidelity")):
        return "Complete and submit Part 2, then complete every Part 3 answer and explanation."
    preceding = "part3_submitted" if code_reviewer else "part2_submitted"
    if new.get("part4_submitted") is True and not (new.get(preceding) is True and rated("conclusion_validity")):
        return f"Complete and submit Part {3 if code_reviewer else 2}, then complete every required Part 4 answer."
    return None


def database(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS responses (
        paper_id TEXT NOT NULL, annotator TEXT NOT NULL, analysis_id TEXT NOT NULL,
        payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (paper_id, annotator, analysis_id))""")
    return db


def handler_factory(packet: dict, db_path: Path, password: str | None, session_secret: str | None = None,
                    allowed_annotators: str | None = None):
    paper_root = Path(packet["paper_dir"]).resolve()
    paper_id = packet["case"].get("case_id", paper_root.name)
    signing_key = session_secret.encode() if session_secret else secrets.token_bytes(32)
    allowed_names = [name.strip() for name in (allowed_annotators or "").split(",") if name.strip()]

    def canonical_name(value: str) -> str | None:
        entered = value.strip()
        if not entered:
            return None
        if not allowed_names:
            return entered
        return next((name for name in allowed_names if name.casefold() == entered.casefold()), None)

    def saved_payload(annotator: str, analysis_id: str) -> dict:
        with database(db_path) as db:
            row = db.execute("SELECT payload FROM responses WHERE paper_id=? AND annotator=? AND analysis_id=?", (paper_id, annotator, analysis_id)).fetchone()
        return json.loads(row[0]) if row else {}

    def gated_packet(annotator: str) -> dict:
        visible = copy.deepcopy(packet)
        visible["code_reviewer"] = is_code_reviewer(annotator)
        for analysis in visible["analyses"]:
            code_visible, results_visible = unlocked(saved_payload(annotator, analysis["id"]), visible["code_reviewer"])
            if not code_visible:
                analysis["automated_checks"] = []
                analysis["files"]["code"] = None
            if not results_visible:
                analysis["execution"] = {}
                analysis["files"]["execution_results"] = None
        return visible

    class Handler(BaseHTTPRequestHandler):
        def current_user(self):
            if not password:
                return None
            cookies = dict(part.strip().split("=", 1) for part in self.headers.get("Cookie", "").split(";") if "=" in part)
            token = cookies.get("annotation_session", "")
            try:
                encoded, signature = token.rsplit(".", 1)
                expected = hmac.new(signing_key, encoded.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    return None
                return canonical_name(base64.urlsafe_b64decode(encoded + "===").decode())
            except Exception:
                return None

        def require_user(self):
            user = self.current_user()
            if password and not user:
                self.send_json({"error": "authentication required"}, 401)
                return None
            return user or "local-annotator"

        def resolve_file(self, relative: str):
            requested = (paper_root / unquote(relative)).resolve()
            if paper_root not in requested.parents or not requested.is_file():
                return None
            return requested

        def send_bytes(self, body: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, value, status=200):
            self.send_bytes(json.dumps(value).encode(), "application/json; charset=utf-8", status)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/session":
                user = self.current_user()
                return self.send_json({"authenticated": bool(user) or not password, "annotator": user})
            if parsed.path == "/api/packet":
                user = self.require_user()
                if not user: return
                return self.send_json(gated_packet(user))
            if parsed.path.startswith("/api/responses/"):
                annotator = self.require_user()
                if not annotator: return
                with database(db_path) as db:
                    rows = db.execute("SELECT analysis_id,payload,updated_at FROM responses WHERE paper_id=? AND annotator=?", (paper_id, annotator)).fetchall()
                return self.send_json({row[0]: {"payload": json.loads(row[1]), "updated_at": row[2]} for row in rows})
            if parsed.path == "/api/preview":
                if not self.require_user(): return
                from urllib.parse import parse_qs
                relative = parse_qs(parsed.query).get("path", [""])[0]
                analysis_id = parse_qs(parsed.query).get("analysis", [""])[0]
                try: page = int(parse_qs(parsed.query).get("page", ["1"])[0])
                except ValueError: page = 1
                if not self.file_allowed(relative, analysis_id, self.current_user() or "local-annotator"):
                    return self.send_json({"error": "complete the preceding review stage before opening this file"}, 403)
                requested = self.resolve_file(relative)
                if not requested:
                    return self.send_json({"error": "file not found"}, 404)
                result = preview_file(requested, page)
                analysis = next((item for item in packet["analyses"] if item["id"] == analysis_id), None)
                result["used_variables"] = analysis.get("plan", {}).get("referenced_variables", []) if analysis else []
                return self.send_json(result)
            if parsed.path.startswith("/files/"):
                user = self.require_user()
                if not user: return
                from urllib.parse import parse_qs
                analysis_id = parse_qs(parsed.query).get("analysis", [""])[0]
                relative = unquote(parsed.path.removeprefix("/files/"))
                if not self.file_allowed(relative, analysis_id, user):
                    return self.send_json({"error": "complete the preceding review stage before downloading this file"}, 403)
                requested = self.resolve_file(relative)
                if not requested:
                    return self.send_json({"error": "file not found"}, 404)
                return self.send_bytes(requested.read_bytes(), mimetypes.guess_type(requested.name)[0] or "application/octet-stream")
            name = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            asset = (APP_DIR / "static" / name).resolve()
            if asset.parent != (APP_DIR / "static").resolve() or not asset.is_file():
                return self.send_json({"error": "not found"}, 404)
            self.send_bytes(asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or "text/plain")

        def do_POST(self):
            if self.path == "/api/login":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length))
                    annotator = canonical_name(str(body["annotator"]))
                    supplied = str(body["password"])
                    if not annotator or not password or not hmac.compare_digest(supplied, password):
                        raise ValueError("Use your assigned username and the study password.")
                    encoded = base64.urlsafe_b64encode(annotator.encode()).decode().rstrip("=")
                    signature = hmac.new(signing_key, encoded.encode(), hashlib.sha256).hexdigest()
                    response = json.dumps({"authenticated": True, "annotator": annotator}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Set-Cookie", f"annotation_session={encoded}.{signature}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Strict")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers(); self.wfile.write(response); return
                except (KeyError, ValueError, json.JSONDecodeError) as exc:
                    return self.send_json({"error": str(exc)}, 401)
            if self.path != "/api/responses":
                return self.send_json({"error": "not found"}, 404)
            try:
                authenticated_user = self.require_user()
                if not authenticated_user: return
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                annotator = authenticated_user if password else str(body["annotator"]).strip()
                analysis_id = str(body["analysis_id"])
                payload = body["payload"]
                tasks = {a["id"]: a["task_id"] for a in packet["analyses"]}
                if not annotator or (analysis_id not in tasks and analysis_id != "_paper_review") or not isinstance(payload, dict):
                    raise ValueError("invalid response")
                with database(db_path) as db:
                    row = db.execute("SELECT payload FROM responses WHERE paper_id=? AND annotator=? AND analysis_id=?", (paper_id, annotator, analysis_id)).fetchone()
                    old = json.loads(row[0]) if row else {}
                    error = None if analysis_id == "_paper_review" else payload_error(old, payload, tasks[analysis_id], is_code_reviewer(annotator))
                    if error:
                        return self.send_json({"error": error}, 409)
                    db.execute("""INSERT INTO responses(paper_id,annotator,analysis_id,payload)
                        VALUES(?,?,?,?) ON CONFLICT(paper_id,annotator,analysis_id)
                        DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP""",
                        (paper_id, annotator, analysis_id, json.dumps(payload)))
                self.send_json({"saved": True})
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, 400)

        def file_allowed(self, relative: str, analysis_id: str, user: str) -> bool:
            paper = packet.get("source_materials", {}).get("paper")
            if relative == paper:
                return True
            analysis = next((item for item in packet["analyses"] if item["id"] == analysis_id), None)
            if not analysis:
                return False
            saved = saved_payload(user, analysis_id)
            code_visible, results_visible = unlocked(saved, is_code_reviewer(user))
            if relative == analysis.get("files", {}).get("code"):
                return code_visible
            if relative == analysis.get("files", {}).get("universal_schema"):
                return stages(saved)[0]
            if relative == analysis.get("files", {}).get("execution_results"):
                return results_visible
            support = {item["path"] for item in packet.get("source_materials", {}).get("support_files", [])}
            return relative in support

        def log_message(self, format, *args):
            print(f"[annotation] {self.address_string()} {format % args}")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_folder", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", type=Path, default=APP_DIR / "annotations.sqlite3")
    parser.add_argument("--password", default=os.getenv("ANNOTATION_PASSWORD"), help="Shared pilot password; prefer the ANNOTATION_PASSWORD environment variable")
    parser.add_argument("--session-secret", default=os.getenv("ANNOTATION_SESSION_SECRET"), help="Persistent cookie-signing secret")
    parser.add_argument("--allowed-annotators", default=os.getenv("ALLOWED_ANNOTATORS"), help="Comma-separated assigned usernames")
    args = parser.parse_args()
    packet = extract_paper(args.paper_folder)
    database(args.database).close()
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(packet, args.database, args.password, args.session_secret, args.allowed_annotators))
    print(f"Reviewing {packet['analysis_count']} analyses at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
