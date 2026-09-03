from __future__ import annotations

import copy
import json
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.human_intervention import request_approval
from core.method_families import canonical_structural_method_family


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "shared_memory.json"
TASK_IDS = ("Task1", "Task2")
PRUNE_CHECK_NAMES = (
    "same_focal_claim",
    "same_dataset",
    "not_duplicate",
    "task_completeness",
    "estimand_alignment",
    "variable_support",
    "sample_audit",
    "restriction_justification",
    "control_justification",
    "focal_variable_structure",
    "plan_code_consistency",
    "method_justification",
    "executable_in_principle",
)
METHOD_QUALITY_SECTIONS = (
    "estimand",
    "anchor_alignment",
    "evidence_basis",
    "sample_audit",
    "focal_variable_structure",
    "code_preflight",
)
ANCHOR_DIMENSIONS = ("outcome", "contrast", "sample", "model", "inference")
ANCHOR_DIMENSION_ALIASES = {
    "estimand_scale": "outcome",
    "outcome_scale": "outcome",
    "target_population": "sample",
    "sample_restriction": "sample",
    "missing_data": "sample",
    "missing_data_handling": "sample",
    "focal_variable_construction": "contrast",
    "controls": "model",
}
ANCHOR_ALIGNMENT_STATUSES = {"aligned", "justified_deviation"}
PRUNE_STATUSES = {"high-quality", "low-quality"}
EXECUTION_STATUSES = {"executed_success", "execution_failed"}
TASK_STATUSES = {None, *PRUNE_STATUSES, *EXECUTION_STATUSES}


def load_execute_spec(study_path: str) -> Tuple[Dict[str, Any], Path]:
    study_dir = Path(study_path).resolve()
    spec_path = study_dir / "universal_schema.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"Execution input file not found: {spec_path}")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    _validate_universal_schema(payload)
    return payload, spec_path


def get_case_id(payload: Dict[str, Any]) -> str:
    case = payload.get("case", {})
    case_id = case.get("case_id") or case.get("paper_id")
    if not case_id:
        raise ValueError("Universal schema is missing case.case_id.")
    return str(case_id)


def get_path_id(payload: Dict[str, Any]) -> str:
    planned_id = payload.get("plan", {}).get("planned_id")
    if not planned_id:
        raise ValueError("Universal schema is missing plan.planned_id.")
    return str(planned_id)


def get_prune_case_id(prune_in: Dict[str, Any]) -> str:
    return get_case_id(prune_in)


def get_prune_path_id(prune_in: Dict[str, Any]) -> str:
    return get_path_id(prune_in)


def get_case_memory_path(case_id: str, study_path: str | Path) -> Path:
    return Path(study_path).resolve() / f"shared_memory_{case_id}.json"


def ensure_memory_file(case_id: str, study_path: str | Path) -> Path:
    memory_path = get_case_memory_path(case_id, study_path)
    if not memory_path.exists():
        memory_data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        memory_data["case_id"] = case_id
        memory_data["memory_records"] = []
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        save_case_memory(memory_path, memory_data)
    return memory_path


def load_case_memory(case_id: str, study_path: str | Path) -> Tuple[Dict[str, Any], Path]:
    memory_path = ensure_memory_file(case_id, study_path)
    memory_data = json.loads(memory_path.read_text(encoding="utf-8"))
    memory_data = _compact_memory(memory_data)
    _validate_memory(memory_data, case_id)
    return memory_data, memory_path


def save_case_memory(memory_path: Path, memory_data: Dict[str, Any]) -> None:
    memory_path.write_text(json.dumps(_compact_memory(memory_data), indent=2), encoding="utf-8")


def get_memory_record(memory_data: Dict[str, Any], path_id: str) -> Dict[str, Any] | None:
    for record in memory_data.get("memory_records", []):
        if record.get("path_id") == path_id:
            return record
    return None


def next_path_id(case_id: str, memory_data: Dict[str, Any]) -> str:
    pattern = re.compile(rf"^{re.escape(case_id)}_path(\d+)$")
    numbers = []
    for record in memory_data.get("memory_records", []):
        match = pattern.match(str(record.get("path_id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"{case_id}_path{max(numbers, default=0) + 1:02d}"


def next_candidate_id(memory_data: Dict[str, Any], path_id: str, task_id: str) -> str:
    _validate_task_id(task_id)
    record = get_memory_record(memory_data, path_id) or {}
    task_memory = record.get("tasks", {}).get(task_id, {})
    pattern = re.compile(rf"^{re.escape(task_id)}_candidate(\d+)$")
    numbers = []
    for candidate in task_memory.get("candidates", []):
        match = pattern.match(str(candidate.get("candidate_id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"{task_id}_candidate{max(numbers, default=0) + 1:02d}"


def candidate_artifact_dir(path_id: str, task_id: str, candidate_id: str) -> str:
    _validate_task_id(task_id)
    safe_path_id = _safe_artifact_part(path_id, "path_id")
    safe_candidate_id = _safe_artifact_part(candidate_id, "candidate_id")
    return (Path("candidate_artifacts") / safe_path_id / task_id.lower() / safe_candidate_id).as_posix()


def normalize_planning_output(
    plan_output: Dict[str, Any],
    *,
    case_id: str,
    memory_data: Dict[str, Any],
    iteration: int,
    previous_schema: Dict[str, Any] | None = None,
    study_path: str | Path | None = None,
) -> Dict[str, Any]:
    if not isinstance(plan_output, dict):
        raise ValueError("Planning output must be a JSON object.")

    normalized = copy.deepcopy(plan_output)
    plan = normalized.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("Planning output is missing plan.")

    proposed_tasks = _tasks_by_id(normalized)
    normalized["iteration"] = iteration
    normalized.setdefault("case", {})["case_id"] = case_id

    generated_task_ids = []
    if previous_schema is None:
        path_id = next_path_id(case_id, memory_data)
        normalized_tasks = []
        for task_id in TASK_IDS:
            task = copy.deepcopy(proposed_tasks.get(task_id))
            if task is None:
                raise ValueError(f"Planning output is missing {task_id}.")
            task["candidate_id"] = f"{task_id}_candidate01"
            task["status"] = None
            normalized_tasks.append(task)
            generated_task_ids.append(task_id)
    else:
        _validate_universal_schema(previous_schema)
        path_id = get_path_id(previous_schema)
        normalized["case"] = copy.deepcopy(previous_schema["case"])
        normalized["tasks_info"] = copy.deepcopy(previous_schema.get("tasks_info", []))
        normalized["datasets"] = copy.deepcopy(previous_schema.get("datasets", {}))
        previous_tasks = _tasks_by_id(previous_schema)
        previous_anchors = {
            anchor["task_id"]: anchor for anchor in previous_schema["analysis_anchors"]
        }
        proposed_anchors = {
            anchor.get("task_id"): anchor
            for anchor in normalized.get("analysis_anchors", [])
            if isinstance(anchor, dict)
        }
        normalized_tasks = []
        normalized_anchors = []

        for task_id in TASK_IDS:
            previous_task = previous_tasks[task_id]
            previous_status = previous_task.get("status")
            if previous_status == "high-quality":
                normalized_tasks.append(copy.deepcopy(previous_task))
                normalized_anchors.append(copy.deepcopy(previous_anchors[task_id]))
                continue
            if previous_status != "low-quality":
                raise ValueError(
                    f"Planning can regenerate only a low-quality candidate; "
                    f"{task_id} has status {previous_status!r}."
                )
            task = copy.deepcopy(proposed_tasks.get(task_id))
            if task is None:
                raise ValueError(f"Planning output is missing regenerated {task_id}.")
            task["candidate_id"] = next_candidate_id(memory_data, path_id, task_id)
            task["status"] = None
            normalized_tasks.append(task)
            generated_task_ids.append(task_id)
            anchor = proposed_anchors.get(task_id)
            if anchor is None:
                raise ValueError(f"Planning output is missing regenerated {task_id} analysis anchor.")
            normalized_anchors.append(copy.deepcopy(anchor))

        normalized["analysis_anchors"] = normalized_anchors

    plan["planned_id"] = path_id
    plan["task_scope"] = list(TASK_IDS)
    plan["tasks"] = normalized_tasks
    for task in normalized_tasks:
        analysis_path = task.get("analysis_path", {})
        analysis_path["structural_method_family"] = canonical_structural_method_family(
            analysis_path.get("structural_method_family")
        )
        _normalize_anchor_deviation_dimensions(task)
    if study_path is not None:
        _normalize_task_code_paths(
            normalized_tasks,
            study_path,
            path_id=path_id,
            generated_task_ids=generated_task_ids,
        )
    _validate_universal_schema(normalized)
    return normalized


def missing_analysis_code_files(
    universal_schema: Dict[str, Any],
    study_path: str | Path,
) -> List[str]:
    _validate_universal_schema(universal_schema)
    study_dir = Path(study_path).resolve()
    missing = []

    for task in _tasks_by_id(universal_schema).values():
        analysis_code = task.get("analysis_code", {})
        declared_paths = [analysis_code.get("entry_file")]
        declared_paths.extend(analysis_code.get("code_files", []) or [])

        for declared_path in declared_paths:
            if not declared_path:
                continue
            path = Path(str(declared_path))
            full_path = path.resolve() if path.is_absolute() else (study_dir / path).resolve()
            try:
                full_path.relative_to(study_dir)
            except ValueError:
                missing.append(str(declared_path))
                continue
            if not full_path.is_file():
                missing.append(str(declared_path))

    return list(dict.fromkeys(missing))


def get_task_statuses(universal_schema: Dict[str, Any]) -> Dict[str, str | None]:
    tasks = _tasks_by_id(universal_schema)
    return {task_id: tasks[task_id].get("status") for task_id in TASK_IDS}


def route_after_pruning(
    universal_schema: Dict[str, Any],
    completed_loops: int,
    max_planning_pruning_loops: int,
) -> str:
    if max_planning_pruning_loops < 1:
        raise ValueError("max_planning_pruning_loops must be a positive integer.")
    statuses = get_task_statuses(universal_schema)
    if all(statuses[task_id] == "high-quality" for task_id in TASK_IDS):
        return "execution"
    if not all(statuses[task_id] in PRUNE_STATUSES for task_id in TASK_IDS):
        raise ValueError(f"Pruning returned invalid active candidate statuses: {statuses}")
    if completed_loops >= max_planning_pruning_loops:
        return "planning_pruning_limit_reached"
    return "planning"


def extract_pruning_decisions(
    prune_output: Dict[str, Any],
    universal_schema: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    pruning_output = prune_output.get("pruning_output", {})
    records = pruning_output.get("task_pair_records")
    if not isinstance(records, list):
        raise ValueError("Pruning output is missing pruning_output.task_pair_records.")

    path_id = get_path_id(universal_schema)
    pair_record = next((record for record in records if record.get("path_id") == path_id), None)
    if pair_record is None:
        raise ValueError(f"Pruning output is missing task-pair record {path_id}.")

    active_tasks = _tasks_by_id(universal_schema)
    task_outputs = pair_record.get("tasks", {})
    decisions: Dict[str, Dict[str, Any]] = {}
    for task_id in TASK_IDS:
        task = active_tasks[task_id]
        if task.get("status") == "high-quality":
            continue
        if task.get("status") is not None:
            raise ValueError(f"Pruning cannot review {task_id} with status {task.get('status')!r}.")

        output_key = task_id.lower()
        candidates = task_outputs.get(output_key, {}).get("candidates", [])
        candidate_id = task["candidate_id"]
        candidate_output = next(
            (item for item in candidates if item.get("candidate_id") == candidate_id),
            None,
        )
        if candidate_output is None:
            raise ValueError(f"Pruning output is missing decision for {candidate_id}.")
        decision = str(candidate_output.get("decision", "")).strip().lower()
        if decision not in PRUNE_STATUSES:
            raise ValueError(f"Unsupported pruning decision for {candidate_id}: {decision!r}")
        check_results = candidate_output.get("check_results")
        if not isinstance(check_results, dict):
            raise ValueError(f"Pruning output is missing check_results for {candidate_id}.")
        missing_checks = [name for name in PRUNE_CHECK_NAMES if name not in check_results]
        if missing_checks:
            raise ValueError(
                f"Pruning output for {candidate_id} is missing checks: {', '.join(missing_checks)}."
            )
        invalid_checks = []
        failed_checks = []
        for name in PRUNE_CHECK_NAMES:
            check = check_results[name]
            status = check.get("status") if isinstance(check, dict) else None
            if status not in {"pass", "fail"}:
                invalid_checks.append(name)
            elif status == "fail":
                failed_checks.append(name)
        if invalid_checks:
            raise ValueError(
                f"Pruning output for {candidate_id} has invalid check status: "
                f"{', '.join(invalid_checks)}."
            )
        if decision == "high-quality" and failed_checks:
            raise ValueError(
                f"Pruning cannot mark {candidate_id} high-quality with failed checks: "
                f"{', '.join(failed_checks)}."
            )
        evidence_failures = _method_quality_gate_failures(task)
        if decision == "high-quality" and evidence_failures:
            raise ValueError(
                f"Pruning cannot mark {candidate_id} high-quality because method-quality "
                f"evidence failed: {', '.join(evidence_failures)}."
            )
        if decision == "low-quality" and not failed_checks:
            raise ValueError(
                f"Pruning must identify at least one failed check for low-quality {candidate_id}."
            )
        decisions[task_id] = {
            "candidate_id": candidate_id,
            "decision": decision,
            "decision_summary": candidate_output.get("decision_summary", ""),
            "check_results": copy.deepcopy(check_results),
        }
    return decisions


def apply_pruning_decisions(
    universal_schema: Dict[str, Any],
    decisions: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    updated = copy.deepcopy(universal_schema)
    for task_id, task in _tasks_by_id(updated).items():
        if task.get("status") == "high-quality":
            continue
        decision = decisions.get(task_id)
        if not decision or decision.get("candidate_id") != task.get("candidate_id"):
            raise ValueError(f"No matching pruning decision for active {task_id} candidate.")
        task["status"] = decision["decision"]
    return updated


def build_memory_record_from_prune_output(
    prune_in: Dict[str, Any],
    prune_out: Dict[str, Any],
    *,
    iteration: int,
) -> Dict[str, Any]:
    decisions = extract_pruning_decisions(prune_out, prune_in)
    path_id = get_path_id(prune_in)
    plan = prune_in["plan"]
    tasks = _tasks_by_id(prune_in)
    task_updates: Dict[str, Any] = {}

    for task_id in TASK_IDS:
        task = tasks[task_id]
        task_update: Dict[str, Any] = {"active_candidate_id": task["candidate_id"]}
        decision = decisions.get(task_id)
        if decision:
            task_update["candidates"] = [{
                "candidate_id": task["candidate_id"],
                "status": decision["decision"],
                "planned_path": _planned_path_from_task(plan, task),
                "pruning_review": {
                    "decision": decision["decision"],
                    "issues": _failed_pruning_checks(decision["check_results"]),
                    "planning_pruning_iteration": iteration,
                },
                "executor_fixed_path": None,
                "execution_result": None,
            }]
        task_updates[task_id] = task_update

    return {
        "path_id": path_id,
        "planning_pruning_iteration": iteration,
        "tasks": task_updates,
        "execution_runs": [],
    }


def build_prune_audit_update(
    universal_schema: Dict[str, Any],
    decisions: Dict[str, Dict[str, Any]],
    *,
    iteration: int,
) -> Dict[str, Any]:
    case_id = get_case_id(universal_schema)
    path_id = get_path_id(universal_schema)
    plan = universal_schema["plan"]
    tasks = _tasks_by_id(universal_schema)
    anchors = {
        anchor["task_id"]: anchor for anchor in universal_schema["analysis_anchors"]
    }
    task_records: Dict[str, Any] = {}

    for task_id in TASK_IDS:
        candidates = []
        decision = decisions.get(task_id)
        if decision:
            task = tasks[task_id]
            candidates.append({
                "candidate_id": task["candidate_id"],
                "planning_pruning_iteration": iteration,
                "candidate_snapshot": _candidate_snapshot_from_task(plan, task, anchors[task_id]),
                "decision": decision["decision"],
                "decision_summary": decision["decision_summary"],
                "check_results": decision["check_results"],
            })
        task_records[task_id.lower()] = {"candidates": candidates}

    updated_schema = apply_pruning_decisions(universal_schema, decisions)
    statuses = get_task_statuses(updated_schema)
    pair_high_quality = all(status == "high-quality" for status in statuses.values())
    pair_assessment = {
        "decision": "high-quality" if pair_high_quality else "low-quality",
        "task1_candidate_id": tasks["Task1"]["candidate_id"] if statuses["Task1"] == "high-quality" else None,
        "task2_candidate_id": tasks["Task2"]["candidate_id"] if statuses["Task2"] == "high-quality" else None,
        "reason": (
            "Both tasks have a high-quality candidate selected for Execution."
            if pair_high_quality
            else "One or both tasks do not yet have a high-quality candidate."
        ),
    }
    return {
        "pruning_output": {
            "case_id": case_id,
            "paper_id": case_id,
            "task_pair_records": [{
                "path_id": path_id,
                "tasks": task_records,
                "task_pair_assessment": pair_assessment,
            }],
        }
    }


def accumulate_prune_output(
    current_output: Dict[str, Any] | None,
    audit_update: Dict[str, Any],
) -> Dict[str, Any]:
    update_root = audit_update["pruning_output"]
    if not isinstance(current_output, dict) or not isinstance(
        current_output.get("pruning_output", {}).get("task_pair_records"), list
    ):
        accumulated = {
            "pruning_output": {
                "case_id": update_root["case_id"],
                "paper_id": update_root["paper_id"],
                "task_pair_records": [],
            }
        }
    else:
        accumulated = copy.deepcopy(current_output)

    records = accumulated["pruning_output"]["task_pair_records"]
    for update_record in update_root["task_pair_records"]:
        path_id = update_record["path_id"]
        record = next((item for item in records if item.get("path_id") == path_id), None)
        if record is None:
            records.append(copy.deepcopy(update_record))
            continue

        for task_key in ("task1", "task2"):
            candidates = record.setdefault("tasks", {}).setdefault(task_key, {}).setdefault("candidates", [])
            for update_candidate in update_record["tasks"][task_key]["candidates"]:
                existing = next(
                    (item for item in candidates if item.get("candidate_id") == update_candidate["candidate_id"]),
                    None,
                )
                if existing is None:
                    candidates.append(copy.deepcopy(update_candidate))
                else:
                    existing.update(copy.deepcopy(update_candidate))
        record["task_pair_assessment"] = copy.deepcopy(update_record["task_pair_assessment"])
    return accumulated


def validate_execution_ready(
    execute_spec: Dict[str, Any],
    memory_data: Dict[str, Any] | None = None,
) -> None:
    _validate_universal_schema(execute_spec)
    statuses = get_task_statuses(execute_spec)
    if any(status != "high-quality" for status in statuses.values()):
        raise ValueError(f"Execution requires two high-quality active candidates; got {statuses}.")

    if memory_data is None:
        return
    record = get_memory_record(memory_data, get_path_id(execute_spec))
    if record is None:
        raise ValueError("Shared memory does not contain the approved path.")
    for task_id, task in _tasks_by_id(execute_spec).items():
        task_memory = record.get("tasks", {}).get(task_id, {})
        if task_memory.get("active_candidate_id") != task.get("candidate_id"):
            raise ValueError(f"Shared memory active candidate does not match {task_id}.")
        candidate = _find_candidate(task_memory, task["candidate_id"])
        if not candidate or candidate.get("status") != "high-quality":
            raise ValueError(f"Shared memory does not mark {task_id} active candidate high-quality.")


def build_memory_record_from_execution_results(
    execute_spec: Dict[str, Any],
    execution_results: Dict[str, Any],
) -> Dict[str, Any]:
    path_id = get_path_id(execute_spec)
    tasks = _tasks_by_id(execute_spec)
    outputs = execution_results.get("task_outputs", [])
    if not isinstance(outputs, list):
        outputs = []

    task_updates: Dict[str, Any] = {}
    final_statuses = []
    for task_id in TASK_IDS:
        task = tasks[task_id]
        task_output = next((item for item in outputs if item.get("task_id") == task_id), {})
        if task_output and task_output.get("candidate_id") != task["candidate_id"]:
            raise ValueError(
                f"Execution output candidate for {task_id} does not match the active candidate."
            )
        succeeded = task_output.get("execution_status") == "success"
        status = "executed_success" if succeeded else "execution_failed"
        final_statuses.append(status)

        failure_reason = task_output.get("failure", {}).get("failure_reason")
        fidelity_note = task_output.get("method_fidelity", {}).get("fidelity_note")
        status_reason = (
            fidelity_note
            or failure_reason
            or ("Task completed successfully." if succeeded else "Task did not produce a successful output.")
        )
        deviations = task_output.get("method_fidelity", {}).get("deviations", []) or []
        changes = [
            item.get("description")
            for item in deviations
            if isinstance(item, dict) and item.get("description")
        ]
        fixed_path = None
        if changes:
            fixed_path = {
                "path_summary": status_reason,
                "path_signature": _task_signature(task),
                "changes": changes,
                "executed_analysis": copy.deepcopy(task_output.get("executed_analysis", {})),
            }

        task_updates[task_id] = {
            "active_candidate_id": task["candidate_id"],
            "candidates": [{
                "candidate_id": task["candidate_id"],
                "status": status,
                "executor_fixed_path": fixed_path,
                "execution_result": {
                    "status_reason": status_reason,
                    "output": copy.deepcopy(task_output),
                },
            }],
        }

    run_status = (
        "executed_success"
        if all(status == "executed_success" for status in final_statuses)
        else "execution_failed"
    )
    return {
        "path_id": path_id,
        "planning_pruning_iteration": int(execute_spec.get("iteration", 1)),
        "tasks": task_updates,
        "execution_runs": [{
            "task1_candidate_id": tasks["Task1"]["candidate_id"],
            "task2_candidate_id": tasks["Task2"]["candidate_id"],
            "status": run_status,
        }],
    }


def derive_execution_status(execution_results: Dict[str, Any]) -> Tuple[str, str]:
    overview = execution_results.get("execution_overview", {})
    status = (
        "executed_success"
        if overview.get("overall_execution_status") == "success"
        else "execution_failed"
    )
    reason = overview.get("overall_summary") or "Execution finished without a summary."
    return status, reason


def update_memory_record(memory_data: Dict[str, Any], new_record: Dict[str, Any]) -> Dict[str, Any]:
    updated_memory = copy.deepcopy(memory_data)
    records = updated_memory.setdefault("memory_records", [])
    path_id = new_record.get("path_id")
    if not path_id:
        raise ValueError("Shared-memory update is missing path_id.")

    record = next((item for item in records if item.get("path_id") == path_id), None)
    if record is None:
        record = {
            "path_id": path_id,
            "planning_pruning_iteration": new_record.get("planning_pruning_iteration", 1),
            "tasks": {
                task_id: {"active_candidate_id": None, "candidates": []}
                for task_id in TASK_IDS
            },
            "execution_runs": [],
        }
        records.append(record)

    record["planning_pruning_iteration"] = new_record.get(
        "planning_pruning_iteration", record.get("planning_pruning_iteration", 1)
    )
    for task_id, task_update in new_record.get("tasks", {}).items():
        _validate_task_id(task_id)
        task_memory = record.setdefault("tasks", {}).setdefault(
            task_id, {"active_candidate_id": None, "candidates": []}
        )
        if "active_candidate_id" in task_update:
            task_memory["active_candidate_id"] = task_update["active_candidate_id"]
        candidates = task_memory.setdefault("candidates", [])
        for candidate_update in task_update.get("candidates", []):
            candidate_id = candidate_update.get("candidate_id")
            if not candidate_id:
                raise ValueError(f"Shared-memory update for {task_id} is missing candidate_id.")
            existing = _find_candidate(task_memory, candidate_id)
            if existing is None:
                candidates.append(copy.deepcopy(candidate_update))
            else:
                for key, value in candidate_update.items():
                    if key == "candidate_id":
                        continue
                    existing[key] = copy.deepcopy(value)

    runs = record.setdefault("execution_runs", [])
    for run_update in new_record.get("execution_runs", []):
        run_key = (run_update.get("task1_candidate_id"), run_update.get("task2_candidate_id"))
        existing_run = next(
            (
                item for item in runs
                if (item.get("task1_candidate_id"), item.get("task2_candidate_id")) == run_key
            ),
            None,
        )
        if existing_run is None:
            runs.append(copy.deepcopy(run_update))
        else:
            existing_run.update(copy.deepcopy(run_update))
    compact_memory = _compact_memory(updated_memory)
    _validate_memory(compact_memory, str(compact_memory.get("case_id", "")))
    return compact_memory


def write_memory_update_with_confirmation(
    memory_path: Path,
    current_memory: Dict[str, Any],
    new_record: Dict[str, Any],
) -> bool:
    proposed = update_memory_record(current_memory, new_record)
    print("\nShared memory update proposal:")
    print(json.dumps(new_record, indent=2))
    if not request_approval(f"Write this update to {memory_path.name}? (yes/no): "):
        print("Shared memory update skipped.")
        return False
    save_case_memory(memory_path, proposed)
    print(f"Shared memory updated at {memory_path}")
    return True


def _validate_universal_schema(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Universal schema must be a JSON object.")
    get_case_id(payload)
    get_path_id(payload)
    _validate_analysis_anchors(payload)
    tasks = _tasks_by_id(payload)
    for task_id in TASK_IDS:
        task = tasks[task_id]
        if not task.get("candidate_id"):
            raise ValueError(f"Universal schema {task_id} is missing candidate_id.")
        if task.get("status") not in TASK_STATUSES:
            raise ValueError(f"Universal schema {task_id} has unsupported status {task.get('status')!r}.")
        analysis_path = task.get("analysis_path")
        if not isinstance(analysis_path, dict) or not analysis_path.get("structural_method_family"):
            raise ValueError(
                f"Universal schema {task_id} is missing analysis_path.structural_method_family."
            )
        if analysis_path.get("family_novelty") not in {
            "untried",
            "reused_no_defensible_alternative",
        }:
            raise ValueError(
                f"Universal schema {task_id} has unsupported analysis_path.family_novelty."
            )
        if not analysis_path.get("family_selection_reason"):
            raise ValueError(
                f"Universal schema {task_id} is missing analysis_path.family_selection_reason."
            )
        _validate_method_quality(task, task_id)


def _validate_analysis_anchors(payload: Dict[str, Any]) -> None:
    anchors = payload.get("analysis_anchors")
    if not isinstance(anchors, list):
        raise ValueError("Universal schema is missing analysis_anchors.")

    anchor_ids = [anchor.get("task_id") for anchor in anchors if isinstance(anchor, dict)]
    if len(anchors) != len(TASK_IDS) or set(anchor_ids) != set(TASK_IDS):
        raise ValueError("Universal schema analysis_anchors must contain Task1 and Task2 exactly once.")

    for anchor in anchors:
        task_id = anchor["task_id"]
        estimand = anchor.get("estimand")
        if not isinstance(estimand, dict) or any(
            not estimand.get(name)
            for name in ("outcome", "outcome_scale", "contrast", "target_population", "time_scope")
        ):
            raise ValueError(f"Universal schema {task_id} analysis anchor has an incomplete estimand.")

        sample = anchor.get("sample_definition")
        if not isinstance(sample, dict) or not sample.get("scope"):
            raise ValueError(f"Universal schema {task_id} analysis anchor has an incomplete sample definition.")
        for name in ("inclusion_rules", "exclusion_rules"):
            if not isinstance(sample.get(name), list):
                raise ValueError(
                    f"Universal schema {task_id} analysis anchor sample_definition.{name} must be a list."
                )

        specification = anchor.get("reference_specification")
        required_specification = (
            "model_family",
            "variable_construction",
            "uncertainty_method",
        )
        if not isinstance(specification, dict) or any(
            not specification.get(name) for name in required_specification
        ):
            raise ValueError(
                f"Universal schema {task_id} analysis anchor has an incomplete reference specification."
            )
        for name in ("controls", "fixed_effects"):
            if not isinstance(specification.get(name), list):
                raise ValueError(
                    f"Universal schema {task_id} analysis anchor reference_specification.{name} "
                    "must be a list."
                )

        conclusion_rule = anchor.get("conclusion_rule")
        if not isinstance(conclusion_rule, dict) or any(
            not conclusion_rule.get(name)
            for name in ("expected_direction", "statistical_threshold", "support_rule")
        ):
            raise ValueError(f"Universal schema {task_id} analysis anchor has an incomplete conclusion rule.")

        evidence = anchor.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("paper") or not evidence.get(
            "dataset_mapping"
        ):
            raise ValueError(f"Universal schema {task_id} analysis anchor has incomplete evidence.")
        if not isinstance(anchor.get("uncertainties"), list):
            raise ValueError(f"Universal schema {task_id} analysis anchor uncertainties must be a list.")


def _validate_method_quality(task: Dict[str, Any], task_id: str) -> None:
    method_quality = task.get("method_quality")
    if not isinstance(method_quality, dict):
        raise ValueError(f"Universal schema {task_id} is missing method_quality.")
    missing_sections = [
        section for section in METHOD_QUALITY_SECTIONS
        if not isinstance(method_quality.get(section), dict)
    ]
    if missing_sections:
        raise ValueError(
            f"Universal schema {task_id}.method_quality is missing sections: "
            f"{', '.join(missing_sections)}."
        )

    estimand = method_quality["estimand"]
    estimand_fields = (
        "quantity",
        "outcome_scale",
        "contrast",
        "target_population",
        "time_scope",
        "claim_mapping",
    )
    missing_estimand = [name for name in estimand_fields if not estimand.get(name)]
    if missing_estimand:
        raise ValueError(
            f"Universal schema {task_id}.method_quality.estimand is missing: "
            f"{', '.join(missing_estimand)}."
        )

    _validate_anchor_alignment(method_quality["anchor_alignment"], task_id)

    evidence = method_quality["evidence_basis"]
    if not evidence.get("outcome") or not evidence.get("main_predictor"):
        raise ValueError(
            f"Universal schema {task_id}.method_quality.evidence_basis must support "
            "the outcome and main predictor."
        )
    for name in ("controls", "restrictions"):
        if not isinstance(evidence.get(name), list):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.evidence_basis.{name} must be a list."
            )
    for control in evidence["controls"]:
        if not isinstance(control, dict) or any(
            not control.get(name) for name in ("name", "role", "evidence")
        ):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.evidence_basis.controls "
                "contains an incomplete entry."
            )
    for restriction in evidence["restrictions"]:
        if not isinstance(restriction, dict) or any(
            not restriction.get(name) for name in ("rule", "evidence")
        ):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.evidence_basis.restrictions "
                "contains an incomplete entry."
            )

    sample_audit = method_quality["sample_audit"]
    if "starting_sample_size" not in sample_audit:
        raise ValueError(
            f"Universal schema {task_id}.method_quality.sample_audit is missing "
            "starting_sample_size."
        )
    for name in ("inclusion_rules", "exclusion_rules"):
        if not isinstance(sample_audit.get(name), list):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.sample_audit.{name} must be a list."
            )
    if "code_reports_sample_flow" not in sample_audit:
        raise ValueError(
            f"Universal schema {task_id}.method_quality.sample_audit is missing "
            "code_reports_sample_flow."
        )
    if not isinstance(sample_audit["code_reports_sample_flow"], bool):
        raise ValueError(
            f"Universal schema {task_id}.method_quality.sample_audit."
            "code_reports_sample_flow must be a Boolean."
        )

    structure = method_quality["focal_variable_structure"]
    structure_fields = (
        "source_structure",
        "analysis_structure",
        "information_loss",
        "justification",
    )
    if any(not structure.get(name) for name in structure_fields):
        raise ValueError(
            f"Universal schema {task_id}.method_quality.focal_variable_structure is incomplete."
        )

    preflight = method_quality["code_preflight"]
    for name in ("referenced_columns", "missing_columns"):
        if not isinstance(preflight.get(name), list):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.code_preflight.{name} must be a list."
            )
    if not preflight.get("plan_code_consistency") or not preflight.get("preflight_note"):
        raise ValueError(
            f"Universal schema {task_id}.method_quality.code_preflight is incomplete."
        )


def _validate_anchor_alignment(alignment: Dict[str, Any], task_id: str) -> None:
    deviation_dimensions = set()
    deviations = alignment.get("deviations")
    if not isinstance(deviations, list):
        raise ValueError(
            f"Universal schema {task_id}.method_quality.anchor_alignment.deviations must be a list."
        )
    for deviation in deviations:
        if not isinstance(deviation, dict) or any(
            not deviation.get(name)
            for name in ("dimension", "anchor_choice", "candidate_choice", "justification")
        ):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.anchor_alignment contains an "
                "incomplete deviation."
            )
        dimension = deviation["dimension"]
        if dimension not in ANCHOR_DIMENSIONS:
            raise ValueError(
                f"Universal schema {task_id}.method_quality.anchor_alignment has unsupported "
                f"dimension {dimension!r}."
            )
        deviation_dimensions.add(dimension)

    for dimension in ANCHOR_DIMENSIONS:
        assessment = alignment.get(dimension)
        if not isinstance(assessment, dict):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.anchor_alignment is missing {dimension}."
            )
        status = assessment.get("status")
        if status not in ANCHOR_ALIGNMENT_STATUSES or not assessment.get("note"):
            raise ValueError(
                f"Universal schema {task_id}.method_quality.anchor_alignment.{dimension} "
                "is incomplete."
            )
        if status == "justified_deviation" and dimension not in deviation_dimensions:
            raise ValueError(
                f"Universal schema {task_id}.method_quality.anchor_alignment.{dimension} "
                "requires a matching deviation record."
            )


def _normalize_anchor_deviation_dimensions(task: Dict[str, Any]) -> None:
    alignment = task.get("method_quality", {}).get("anchor_alignment")
    if not isinstance(alignment, dict):
        return

    deviations = alignment.get("deviations")
    if not isinstance(deviations, list):
        return

    for deviation in deviations:
        if not isinstance(deviation, dict):
            continue
        dimension = deviation.get("dimension")
        if not isinstance(dimension, str):
            continue
        normalized_name = re.sub(r"[^a-z0-9]+", "_", dimension.strip().lower()).strip("_")
        canonical_dimension = ANCHOR_DIMENSION_ALIASES.get(normalized_name, normalized_name)
        deviation["dimension"] = canonical_dimension

        assessment = alignment.get(canonical_dimension)
        if canonical_dimension in ANCHOR_DIMENSIONS and isinstance(assessment, dict):
            assessment["status"] = "justified_deviation"


def _method_quality_gate_failures(task: Dict[str, Any]) -> List[str]:
    method_quality = task["method_quality"]
    sample_flow = method_quality["sample_audit"].get("code_reports_sample_flow")
    preflight = method_quality["code_preflight"]
    failures = []
    if sample_flow is not True:
        failures.append("sample_audit")
    if preflight.get("missing_columns"):
        failures.append("variable_support")
    if str(preflight.get("plan_code_consistency", "")).strip().lower() != "pass":
        failures.append("plan_code_consistency")
    return failures


def _validate_memory(memory_data: Dict[str, Any], case_id: str) -> None:
    if memory_data.get("case_id") != case_id:
        raise ValueError(
            f"Shared memory case_id {memory_data.get('case_id')!r} does not match {case_id!r}."
        )
    records = memory_data.get("memory_records")
    if not isinstance(records, list):
        raise ValueError("Shared memory memory_records must be a list.")
    path_ids = [record.get("path_id") for record in records]
    if len(path_ids) != len(set(path_ids)):
        raise ValueError("Shared memory contains duplicate path_id values.")
    for record in records:
        if not isinstance(record.get("tasks"), dict):
            raise ValueError(
                f"Shared memory record {record.get('path_id')!r} does not use the task-candidate format."
            )
        for task_id in TASK_IDS:
            task_memory = record["tasks"].get(task_id)
            if not isinstance(task_memory, dict):
                raise ValueError(f"Shared memory record is missing tasks.{task_id}.")
            if not isinstance(task_memory.get("candidates"), list):
                raise ValueError(f"Shared memory tasks.{task_id}.candidates must be a list.")
            candidates = task_memory["candidates"]
            candidate_ids = [candidate.get("candidate_id") for candidate in candidates]
            if len(candidate_ids) != len(set(candidate_ids)):
                raise ValueError(f"Shared memory {task_id} contains duplicate candidate_id values.")
            for candidate in candidates:
                if not candidate.get("candidate_id"):
                    raise ValueError(f"Shared memory {task_id} candidate is missing candidate_id.")
                if candidate.get("status") not in TASK_STATUSES:
                    raise ValueError(
                        f"Shared memory candidate {candidate.get('candidate_id')} has an unsupported status."
                    )
            active_candidate_id = task_memory.get("active_candidate_id")
            if active_candidate_id and active_candidate_id not in candidate_ids:
                raise ValueError(
                    f"Shared memory tasks.{task_id}.active_candidate_id does not identify a candidate."
                )


def _normalize_task_code_paths(
    tasks: List[Dict[str, Any]],
    study_path: str | Path,
    *,
    path_id: str,
    generated_task_ids: List[str],
) -> None:
    study_dir = Path(study_path).resolve()
    for task in tasks:
        task_id = task.get("task_id")
        if task_id not in generated_task_ids:
            continue
        analysis_code = task.get("analysis_code")
        if not isinstance(analysis_code, dict):
            continue

        artifact_dir = candidate_artifact_dir(path_id, task_id, task["candidate_id"])
        #(study_dir / artifact_dir).mkdir(parents=True, exist_ok=True)
        analysis_code["artifact_dir"] = artifact_dir

        entry_file = _normalize_code_path(
            analysis_code.get("entry_file"),
            study_dir,
            artifact_dir=artifact_dir,
        )
        if entry_file:
            analysis_code["entry_file"] = entry_file
            analysis_code["run_command"] = _run_command_for_entry(entry_file)

        normalized_files = []
        for code_file in analysis_code.get("code_files", []) or []:
            normalized = _normalize_code_path(
                code_file,
                study_dir,
                artifact_dir=artifact_dir,
            )
            if normalized and normalized not in normalized_files:
                normalized_files.append(normalized)
        if entry_file and entry_file not in normalized_files:
            normalized_files.insert(0, entry_file)
        if normalized_files:
            analysis_code["code_files"] = normalized_files


def _normalize_code_path(
    path_value: Any,
    study_dir: Path,
    *,
    artifact_dir: str,
) -> str | None:
    if not path_value:
        return None
    raw_path = str(path_value).strip().replace("\\", "/")
    if not raw_path:
        return None

    path = Path(raw_path)
    if path.is_absolute():
        try:
            relative_path = path.resolve().relative_to(study_dir)
        except ValueError:
            relative_path = Path(path.name)
    else:
        relative_path = Path(raw_path.lstrip("./"))

    artifact_path = Path(artifact_dir)
    if relative_path == artifact_path or artifact_path in relative_path.parents:
        return relative_path.as_posix()
    return (artifact_path / relative_path.name).as_posix()


def _safe_artifact_part(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text or text in {".", ".."} or Path(text).name != text:
        raise ValueError(f"Invalid {field_name} for candidate artifact directory: {value!r}")
    return text


def _run_command_for_entry(entry_file: str) -> str:
    quoted_entry = shlex.quote(entry_file)
    suffix = Path(entry_file).suffix.lower()
    if suffix in {".r", ".rscript"}:
        return f"Rscript {quoted_entry}"
    if suffix == ".py":
        return f"python {quoted_entry}"
    if suffix == ".sh":
        return f"bash {quoted_entry}"
    return quoted_entry


def _tasks_by_id(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    tasks = payload.get("plan", {}).get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Universal schema is missing plan.tasks.")
    result: Dict[str, Dict[str, Any]] = {}
    for task in tasks:
        if isinstance(task, dict) and task.get("task_id") in TASK_IDS:
            result[task["task_id"]] = task
    missing = [task_id for task_id in TASK_IDS if task_id not in result]
    if missing:
        raise ValueError(f"Universal schema is missing tasks: {', '.join(missing)}.")
    return result


def _validate_task_id(task_id: str) -> None:
    if task_id not in TASK_IDS:
        raise ValueError(f"Unsupported task ID: {task_id!r}")


def _find_candidate(task_memory: Dict[str, Any], candidate_id: str) -> Dict[str, Any] | None:
    return next(
        (
            candidate for candidate in task_memory.get("candidates", [])
            if candidate.get("candidate_id") == candidate_id
        ),
        None,
    )


def _task_signature(task: Dict[str, Any]) -> Dict[str, Any]:
    analysis_path = task.get("analysis_path", {})
    key_choices = analysis_path.get("key_choices", {})
    variables = analysis_path.get("variables", {})
    estimand = task.get("method_quality", {}).get("estimand", {})
    controls = key_choices.get("control_variables")
    if controls is None:
        controls = [
            item.get("name", item) if isinstance(item, dict) else item
            for item in variables.get("controls", [])
        ]
    return {
        "structural_method_family": canonical_structural_method_family(
            analysis_path.get("structural_method_family")
        ),
        "family_novelty": analysis_path.get("family_novelty", "not_stated"),
        "family_selection_reason": analysis_path.get("family_selection_reason", ""),
        "model_family": analysis_path.get("model_family", "not_stated"),
        "outcome": variables.get("outcome", {}).get("name", key_choices.get("outcome_measure")),
        "main_predictor": variables.get("main_predictor", {}).get(
            "name", key_choices.get("main_predictor_measure")
        ),
        "controls": controls or [],
        "sample_restriction": key_choices.get("sample_restriction"),
        "missing_data_rule": key_choices.get("missing_data_rule"),
        "variable_construction": key_choices.get("data_processing"),
        "inference_rule": key_choices.get("inference_rule"),
        "estimand_quantity": estimand.get("quantity"),
        "outcome_scale": estimand.get("outcome_scale"),
        "contrast": estimand.get("contrast"),
        "target_population": estimand.get("target_population"),
        "time_scope": estimand.get("time_scope"),
    }


def _planned_path_from_task(
    plan: Dict[str, Any],
    task: Dict[str, Any],
) -> Dict[str, Any]:
    analysis_path = task.get("analysis_path", {})
    method_quality = task.get("method_quality", {})
    return {
        "path_summary": analysis_path.get("path_description") or plan.get("path_summary") or "",
        "path_signature": _task_signature(task),
        "anchor_alignment": _compact_anchor_alignment(method_quality.get("anchor_alignment", {})),
        "analysis_code": _compact_analysis_code(task.get("analysis_code", {})),
    }


def _candidate_snapshot_from_task(
    plan: Dict[str, Any],
    task: Dict[str, Any],
    analysis_anchor: Dict[str, Any],
) -> Dict[str, Any]:
    analysis_path = task.get("analysis_path", {})
    return {
        "path_summary": analysis_path.get("path_description") or plan.get("path_summary") or "",
        "path_signature": _task_signature(task),
        "analysis_anchor": copy.deepcopy(analysis_anchor),
        "analysis_path": copy.deepcopy(analysis_path),
        "method_quality": copy.deepcopy(task.get("method_quality", {})),
        "analysis_code": copy.deepcopy(task.get("analysis_code", {})),
    }


def _compact_memory(memory_data: Dict[str, Any]) -> Dict[str, Any]:
    compact = copy.deepcopy(memory_data)
    for record in compact.get("memory_records", []):
        for task_memory in record.get("tasks", {}).values():
            for candidate in task_memory.get("candidates", []):
                if isinstance(candidate.get("planned_path"), dict):
                    candidate["planned_path"] = _compact_planned_path(candidate["planned_path"])
                if isinstance(candidate.get("pruning_review"), dict):
                    candidate["pruning_review"] = _compact_pruning_review(candidate["pruning_review"])
                if isinstance(candidate.get("executor_fixed_path"), dict):
                    candidate["executor_fixed_path"] = _compact_fixed_path(candidate["executor_fixed_path"])
                if isinstance(candidate.get("execution_result"), dict):
                    candidate["execution_result"] = _compact_execution_result(candidate["execution_result"])
    return compact


def _compact_planned_path(planned_path: Dict[str, Any]) -> Dict[str, Any]:
    alignment = planned_path.get("anchor_alignment")
    if not isinstance(alignment, dict):
        alignment = planned_path.get("method_quality", {}).get("anchor_alignment", {})
    analysis_code = planned_path.get("analysis_code", {})
    return {
        "path_summary": planned_path.get("path_summary", ""),
        "path_signature": copy.deepcopy(planned_path.get("path_signature", {})),
        "anchor_alignment": _compact_anchor_alignment(alignment),
        "analysis_code": _compact_analysis_code(analysis_code),
    }


def _compact_anchor_alignment(alignment: Dict[str, Any]) -> Dict[str, Any]:
    compact = {
        dimension: (
            alignment.get(dimension, {}).get("status")
            if isinstance(alignment.get(dimension), dict)
            else alignment.get(dimension)
        )
        for dimension in ANCHOR_DIMENSIONS
    }
    compact["deviations"] = [
        {
            key: deviation.get(key)
            for key in ("dimension", "candidate_choice", "justification")
            if deviation.get(key) is not None
        }
        for deviation in alignment.get("deviations", [])
        if isinstance(deviation, dict)
    ]
    return compact


def _compact_analysis_code(analysis_code: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: copy.deepcopy(analysis_code.get(key))
        for key in ("artifact_dir", "entry_file")
        if analysis_code.get(key) is not None
    }


def _failed_pruning_checks(check_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"check": name, "note": result.get("note")}
        for name, result in check_results.items()
        if isinstance(result, dict) and result.get("status") == "fail"
    ]


def _compact_pruning_review(review: Dict[str, Any]) -> Dict[str, Any]:
    issues = review.get("issues")
    if not isinstance(issues, list):
        issues = _failed_pruning_checks(review.get("check_results", {}))
    return {
        "decision": review.get("decision"),
        "issues": copy.deepcopy(issues),
        "planning_pruning_iteration": review.get("planning_pruning_iteration"),
    }


def _compact_fixed_path(fixed_path: Dict[str, Any]) -> Dict[str, Any]:
    executed = fixed_path.get("executed_analysis", {})
    return {
        "path_summary": fixed_path.get("path_summary"),
        "changes": copy.deepcopy(fixed_path.get("changes", [])),
        "executed_analysis": {
            key: copy.deepcopy(executed.get(key))
            for key in ("path_name", "model_family", "software", "code_source")
            if executed.get(key) is not None
        },
    }


def _compact_execution_result(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    output = execution_result.get("output", {})
    existing_result = execution_result.get("result", {})
    result_raw = output.get("result_raw", {})
    statistics = result_raw.get("test_statistics", {})
    conclusion = output.get("conclusion", {})
    failure = output.get("failure", {})
    return {
        "status_reason": execution_result.get("status_reason"),
        "result": {
            "metric": result_raw.get("metric", existing_result.get("metric")),
            "value": result_raw.get("value", existing_result.get("value")),
            "direction": result_raw.get("direction", existing_result.get("direction")),
            "p_value": statistics.get("p_value", existing_result.get("p_value")),
            "confidence_interval": statistics.get(
                "confidence_interval", existing_result.get("confidence_interval")
            ),
            "sample_size": statistics.get("sample_size", existing_result.get("sample_size")),
            "conclusion": conclusion.get("conclusion_class", existing_result.get("conclusion")),
        },
        "repair_attempts_used": failure.get(
            "repair_attempts_used", execution_result.get("repair_attempts_used")
        ),
    }
