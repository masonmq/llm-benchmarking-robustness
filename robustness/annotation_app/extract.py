"""Build compact, human-reviewable records from robustness pipeline outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from preview import IMAGE_EXTENSIONS, is_previewable

CLAIMS_PATH = Path(__file__).resolve().parents[1] / "data" / "_robustness" / "all_claims.xlsx"
# The original authors' analysis code stays available as optional reference, listed apart from data.
# Includes Stata logs (.smcl/.log of the authors' runs), which are their analysis output, not data.
ORIGINAL_CODE_EXTENSIONS = {".r", ".do", ".ado", ".sas", ".sps", ".m", ".py", ".ipynb", ".jl", ".smcl"}
# Archives and similar containers are never previewable; skip them without reading them.
ARCHIVE_EXTENSIONS = {".zip", ".gz", ".tgz", ".tar", ".7z", ".rar"}


def _evaluation_assignment(case_id: str) -> dict[str, str]:
    """Load curator-provided claim and Task 2 instruction from the claims workbook."""
    try:
        import pandas as pd
        frame = pd.read_excel(CLAIMS_PATH)
        rows = frame[frame["paper_id"].astype(str).str.casefold() == case_id.casefold()]
        if rows.empty:
            return {}
        row = rows.iloc[0]
        return {
            "focal_claim": str(row["the claim from SCORE collection"]),
            "task2_instruction": str(row["instructions_for_task_2"]),
        }
    except (FileNotFoundError, ImportError, KeyError):
        return {}


def _by_id(items: list[dict[str, Any]], key: str = "task_id") -> dict[str, dict[str, Any]]:
    return {str(item.get(key)): item for item in items if item.get(key)}


def _value(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _find_code(run_dir: Path, declared: str | None) -> str | None:
    if not declared:
        return None
    direct = run_dir / declared
    if direct.is_file():
        return direct.relative_to(run_dir).as_posix()
    matches = list(run_dir.rglob(Path(declared).name))
    return matches[0].relative_to(run_dir).as_posix() if len(matches) == 1 else None


def _check(label: str, passed: bool | None, detail: str) -> dict[str, Any]:
    return {"label": label, "status": "pass" if passed else "fail" if passed is False else "review", "detail": detail}


def _planned_variable_names(variables: Any) -> list[str]:
    names: list[str] = []
    if isinstance(variables, dict):
        if isinstance(variables.get("name"), str):
            names.append(variables["name"])
        for value in variables.values():
            names.extend(_planned_variable_names(value))
    elif isinstance(variables, list):
        for value in variables:
            names.extend(_planned_variable_names(value))
    return list(dict.fromkeys(names))


def _all_numbers(value: Any) -> list[float]:
    """Collect finite numeric values from parsed runner output."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)] if math.isfinite(float(value)) else []
    if isinstance(value, dict):
        return [number for item in value.values() for number in _all_numbers(item)]
    if isinstance(value, (list, tuple)):
        return [number for item in value for number in _all_numbers(item)]
    return []


def _reported_numbers(value: Any) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)] if math.isfinite(float(value)) else []
    if isinstance(value, (list, tuple)):
        return [number for item in value for number in _reported_numbers(item)]
    if isinstance(value, str):
        without_percentages = re.sub(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)\s*%", "", value)
        return [float(match) for match in re.findall(r"(?<![A-Za-z_])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", without_percentages)]
    return []


def _parse_runner_stdout(stdout: Any) -> tuple[Any, str]:
    """Parse the runner's JSON result. Some runs print library warnings before the JSON; split those off
    so the result can be read and the warnings shown separately. Returns (result, leading_text)."""
    if not isinstance(stdout, str):
        return stdout, ""
    try:
        return json.loads(stdout), ""
    except json.JSONDecodeError:
        pass
    for start in (i for i, ch in enumerate(stdout) if ch in "{["):
        try:
            value, end = json.JSONDecoder().raw_decode(stdout, start)
        except json.JSONDecodeError:
            continue
        if not stdout[end:].strip():
            return value, stdout[:start].strip()
    return stdout, ""


def _decimals(number: float) -> int:
    text = repr(number)
    return len(text.split(".")[1].split("e")[0]) if "." in text and "e" not in text.lower() else 0


def _statistic_presence_checks(reported: dict[str, Any], runner_output: Any) -> list[dict[str, Any]]:
    """Check that agent-reported numbers occur in runner-captured stdout."""
    # Text output (not JSON) is searched for numbers too.
    runner_numbers = _all_numbers(runner_output) if not isinstance(runner_output, str) else _reported_numbers(runner_output)
    checks = []
    for label, value in reported.items():
        expected = _reported_numbers(value)
        if not expected:
            continue
        # A reported value rounded to d decimals still matches the full-precision output.
        missing = [number for number in expected
                   if not any(math.isclose(number, seen, rel_tol=1e-6, abs_tol=max(1e-8, 0.5 * 10 ** -_decimals(number)) if _decimals(number) <= 4 else 1e-8)
                              for seen in runner_numbers)]
        checks.append({
            "field": label,
            "status": "fail" if missing else "pass",
            "reported": value,
            "missing_values": missing,
            "detail": "One or more reported numbers were not found in the recorded analysis output." if missing else "Reported number(s) found in the recorded analysis output.",
        })
    return checks


def extract_run(run_dir: Path, paper_dir: Path, run_number: int | None = None) -> list[dict[str, Any]]:
    universal_path = run_dir / "universal_schema.json"
    execution_path = run_dir / "execution_results.json"
    universal = json.loads(universal_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    runner_path = run_dir / "execution_result.json"
    runner = json.loads(runner_path.read_text(encoding="utf-8")) if runner_path.is_file() else {}

    tasks = _by_id(_value(universal, "plan", "tasks", default=[]))
    task_info = _by_id(universal.get("tasks_info", []))
    anchors = _by_id(universal.get("analysis_anchors", []))
    outputs = _by_id(execution.get("task_outputs", []))
    runner_steps = _by_id(runner.get("steps", []), key="name")
    path_id = str(_value(universal, "plan", "planned_id", default=run_dir.name))
    records: list[dict[str, Any]] = []

    for task_id in sorted(tasks):
        plan = tasks[task_id]
        info = task_info.get(task_id, {})
        anchor = anchors.get(task_id, {})
        output = outputs.get(task_id, {})
        analysis = plan.get("analysis_path", {})
        method_quality = plan.get("method_quality", {})
        estimand = method_quality.get("estimand", {})
        variables = analysis.get("variables", {})
        models = analysis.get("models", [])
        focal_model = models[0] if models else {}
        choices = analysis.get("key_choices", {})
        executed = output.get("executed_analysis", {})
        result = output.get("result_raw", {})
        stats = result.get("test_statistics", {})
        conclusion = output.get("conclusion", {})
        runner_step = runner_steps.get(task_id, {})
        runner_stdout = runner_step.get("stdout")
        runner_output, console_text = _parse_runner_stdout(runner_stdout)
        consistency_checks = _statistic_presence_checks({
            "sample size": stats.get("sample_size"),
            "estimate": result.get("value"),
            "standard error": stats.get("standard_error"),
            "p-value": stats.get("p_value"),
            "confidence interval": stats.get("confidence_interval"),
        }, runner_output)
        planned_candidate = str(plan.get("candidate_id", ""))
        executed_candidate = str(output.get("candidate_id", ""))
        declared_entry = _value(plan, "analysis_code", "entry_file")
        supplied_code = _find_code(run_dir, declared_entry)
        executed_files = executed.get("executed_files", []) or []
        executed_basename = Path(executed_files[0]).name if executed_files else None
        planned_basename = Path(declared_entry).name if declared_entry else None

        checks = [
            _check("Candidate identity", bool(planned_candidate) and planned_candidate == executed_candidate,
                   f"planned {planned_candidate or 'missing'}; executed {executed_candidate or 'missing'}"),
            _check("Execution succeeded", output.get("execution_status") == "success",
                   f"status: {output.get('execution_status', 'missing')}"),
            _check("Planned code supplied", supplied_code is not None,
                   supplied_code or f"could not uniquely locate {declared_entry or 'an entry file'}"),
            _check("Executed filename matches plan", bool(planned_basename) and planned_basename == executed_basename,
                   f"planned {planned_basename or 'missing'}; executed {executed_basename or 'missing'}"),
            _check("Path name matches", bool(analysis.get("path_name")) and analysis.get("path_name") == executed.get("path_name"),
                   f"planned {analysis.get('path_name', 'missing')}; executed {executed.get('path_name', 'missing')}"),
        ]

        task_number = re.sub(r"^Task", "", task_id, flags=re.IGNORECASE)
        records.append({
            "id": f"{run_dir.name}:{task_id}",
            "run": run_dir.name,
            "path_id": path_id,
            "task_id": task_id,
            "candidate_id": planned_candidate,
            # Neutral label from week 3 on ("Analysis A", not "Run 1"); weeks 1-2 packets were built with "Run N".
            "display_name": f"Analysis {chr(64 + run_number) if run_number is not None else run_dir.name} — Task {task_number}",
            "task": {"instruction": info.get("task_instruction"), "goal": info.get("task_goal")},
            "benchmark": {
                "estimand": anchor.get("estimand"),
                "sample": anchor.get("sample_definition"),
                "reference_specification": anchor.get("reference_specification"),
                "conclusion_rule": anchor.get("conclusion_rule"),
                "uncertainties": anchor.get("uncertainties"),
            },
            "plan": {
                "description": analysis.get("path_description"),
                "model_family": analysis.get("model_family"),
                "structural_method_family": analysis.get("structural_method_family"),
                "outcome": choices.get("outcome_measure"),
                "predictor": choices.get("main_predictor_measure"),
                "sample": choices.get("sample_restriction"),
                "controls": choices.get("control_variables"),
                "missing_data": choices.get("missing_data_rule"),
                "outliers": choices.get("outlier_rule"),
                "model": choices.get("model_choice"),
                "inference": choices.get("inference_rule"),
                "referenced_variables": _planned_variable_names(analysis.get("variables", {})),
                "review": {
                    "claim_mapping": estimand.get("claim_mapping"),
                    "quantity": estimand.get("quantity"),
                    "target_population": estimand.get("target_population"),
                    "time_scope": estimand.get("time_scope"),
                    "outcome": variables.get("outcome"),
                    "main_predictor": variables.get("main_predictor"),
                    "additional_variables": variables.get("controls", []),
                    "model_type": focal_model.get("type"),
                    "formula": focal_model.get("formula"),
                    "planned_estimation": focal_model.get("planned_estimation"),
                    "expected_direction": anchor.get("conclusion_rule", {}).get("expected_direction"),
                    "sample_audit": method_quality.get("sample_audit"),
                    "claimed_alignment": method_quality.get("anchor_alignment"),
                    "qualification": focal_model.get("qualification"),
                    "preprocessing_steps": analysis.get("preprocessing_steps"),
                    "decision_rule": choices.get("inference_rule"),
                    "method_selection_reason": analysis.get("family_selection_reason"),
                    "expected_outputs": analysis.get("expected_outputs"),
                    "evidence_basis": method_quality.get("evidence_basis"),
                },
            },
            "execution": {
                "runner_ok": runner_step.get("ok"),
                "runner_exit_code": runner_step.get("exit_code"),
                "runner_stdout": runner_output,
                "runner_stderr": "\n".join(part for part in (console_text, runner_step.get("stderr") or "") if part) or None,
                "consistency_checks": consistency_checks,
                "potential_result_mismatch": any(check["status"] == "fail" for check in consistency_checks),
                "status": output.get("execution_status"),
                "model_family": executed.get("model_family"),
                "executed_files": executed_files,
                "sample_size": stats.get("sample_size"),
                "estimate": result.get("value"),
                "direction": result.get("direction"),
                "standard_error": stats.get("standard_error"),
                "p_value": stats.get("p_value"),
                "confidence_interval": stats.get("confidence_interval"),
                "result_text": result.get("result_text"),
                "fidelity": output.get("method_fidelity"),
                "conclusion": conclusion,
            },
            "automated_checks": checks,
            "files": {
                "universal_schema": universal_path.relative_to(paper_dir).as_posix(),
                "execution_results": execution_path.relative_to(paper_dir).as_posix(),
                "code": f"{run_dir.relative_to(paper_dir).as_posix()}/{supplied_code}" if supplied_code else None,
            },
        })
    return records


def _same_result(task1: dict[str, Any], task2: dict[str, Any]) -> bool:
    keys = ("estimate", "standard_error", "p_value", "sample_size")
    first, second = ([record["execution"].get(key) for key in keys] for record in (task1, task2))
    return first[0] is not None and first[2] is not None and first == second


def _drop_duplicate_task1(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop a run's Task 1 when its Task 2 reproduces the same result, and record what was dropped.

    Task 2 is kept because only it carries the Task 2 restriction question.
    """
    task2 = {record["run"]: record for record in records if record["task_id"] == "Task2"}
    dropped = [record for record in records if record["task_id"] == "Task1" and record["run"] in task2
               and _same_result(record, task2[record["run"]])]
    duplicates = [{"dropped": record["id"], "kept": task2[record["run"]]["id"], "estimate": record["execution"]["estimate"],
                   "p_value": record["execution"]["p_value"], "sample_size": record["execution"]["sample_size"]}
                  for record in dropped]
    return [record for record in records if record not in dropped], duplicates


def extract_paper(paper_dir: Path) -> dict[str, Any]:
    paper_dir = paper_dir.resolve()
    run_dirs = sorted({p.parent for p in paper_dir.rglob("universal_schema.json") if (p.parent / "execution_results.json").is_file()})
    if not run_dirs:
        raise ValueError(f"No runs containing universal_schema.json and execution_results.json under {paper_dir}")
    first = json.loads((run_dirs[0] / "universal_schema.json").read_text(encoding="utf-8"))
    case = first.get("case", {})
    assignment = _evaluation_assignment(str(case.get("case_id", paper_dir.name)))
    if assignment.get("focal_claim"):
        case["focal_claim"] = assignment["focal_claim"]
    records = [record for run_number, run in enumerate(run_dirs, 1) for record in extract_run(run, paper_dir, run_number)]
    if assignment.get("task2_instruction"):
        for record in records:
            if record["task_id"] == "Task2":
                record["task"]["instruction"] = assignment["task2_instruction"]
    records, duplicates = _drop_duplicate_task1(records)
    first_run = run_dirs[0]
    paper_file = first_run / str(case.get("paper_file", "original_paper.pdf"))
    ignored = {"universal_schema.json", "execution_results.json", "execution_result.json", "metadata.json", "prune_out_schema.json"}
    # Source materials come from the first run, plus a paper-level data/ folder when one is supplied.
    candidates = [(first_run, path) for path in sorted(first_run.rglob("*"))]
    if (paper_dir / "data").is_dir():
        candidates += [(paper_dir, path) for path in sorted((paper_dir / "data").rglob("*"))]
    agent_code = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                            for path in paper_dir.rglob("*.py") if "candidate_artifacts" in path.parts)
    # Shallowest copy first, so when a package repeats a file (e.g. an unpacked archive) the top-level copy is kept.
    candidates.sort(key=lambda item: (len(item[1].relative_to(item[0]).parts), item[1].as_posix()))
    support_files, excluded_files, seen_content = [], [], set()
    for root, path in candidates:
        relative_parts = path.relative_to(root).parts
        if not path.is_file() or any(part.startswith(".") for part in relative_parts) or path.name in ignored or path.name.startswith("shared_memory_") or "candidate_artifacts" in path.parts or path.resolve() == paper_file.resolve():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_content:
            continue
        seen_content.add(digest)
        extension = path.suffix.lower()
        display_name = "/".join(relative_parts[1:] if relative_parts[0] == "data" and len(relative_parts) > 1 else relative_parts)
        # Only files the viewer can show are offered; the rest are listed in the packet so they can be reported.
        if extension in ARCHIVE_EXTENSIONS or not is_previewable(path):
            excluded_files.append({"name": display_name, "path": path.relative_to(paper_dir).as_posix(),
                                   "used_by_agent": path.name in agent_code})
            continue
        kind = ("code" if extension in ORIGINAL_CODE_EXTENSIONS
                else "documentation" if extension in {".pdf", ".doc", ".docx", ".txt", ".md", *IMAGE_EXTENSIONS} else "data")
        support_files.append({
            # Keep subfolders in the name so same-named files (e.g. two README.txt) stay distinguishable.
            "name": display_name,
            "path": path.relative_to(paper_dir).as_posix(),
            "kind": kind,
            "extension": extension or "none",
            "browser_preview": extension in {".pdf", ".txt", ".md", ".csv", ".json", ".py", ".r", ".do"},
            # Flags the data files the agent's analyses actually load, so annotators know where to start.
            "used_by_agent": kind == "data" and path.name in agent_code,
        })
    # Data the agent used, then documentation, then other data, then the original code.
    order = {"documentation": 1, "data": 2, "code": 3}
    support_files.sort(key=lambda f: (0 if f["used_by_agent"] else order[f["kind"]], f["name"].lower()))
    return {
        "paper_dir": str(paper_dir),
        "case": case,
        "source_materials": {
            "paper": paper_file.relative_to(paper_dir).as_posix() if paper_file.is_file() else None,
            "support_files": support_files,
            "excluded_files": excluded_files,
        },
        "analysis_count": len(records),
        "analyses": records,
        "dropped_duplicates": duplicates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_folder", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    packet = extract_paper(args.paper_folder)
    text = json.dumps(packet, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
