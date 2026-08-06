from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

MEMORY_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "shared_memory.json"
EXECUTE_SPEC_FILENAMES = ("execute_in_schema.json", "analysis_info.json")
EXECUTION_STATUSES = {"executed_success", "execution_failed_retryable", "abandoned"}
PRUNE_STATUSES = {"high-quality", "low-quality"}
# The Pruning Agent reports quality decisions and shared_memory.json records them with the
# same vocabulary. accepted/rejected are kept as legacy aliases for older memory files.
PRUNE_DECISION_TO_STATUS = {
    "high-quality": "high-quality",
    "low-quality": "low-quality",
    "accepted": "high-quality",
    "rejected": "low-quality",
}

# Reads execute_in_schema.json first.
def load_execute_spec(study_path: str) -> Tuple[Dict[str, Any], Path]:
    study_dir = Path(study_path).resolve()
    for filename in EXECUTE_SPEC_FILENAMES:
        candidate = study_dir / filename
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8")), candidate
    expected = ", ".join(EXECUTE_SPEC_FILENAMES)
    raise FileNotFoundError(f"No execution input file found in {study_dir}. Expected one of: {expected}")

def _execute_plan(execute_spec: Dict[str, Any]) -> Dict[str, Any]:
    plan = execute_spec.get("plan")
    if isinstance(plan, dict):
        return plan
    planned_method = execute_spec.get("planned_method")
    if isinstance(planned_method, dict):
        return planned_method
    return {}


# Extract stable IDs from the execution spec so the memory file name and record ID are consistent.
def get_case_id(execute_spec: Dict[str, Any]) -> str:
    case = execute_spec.get("case", {})
    if case.get("case_id"):
        return str(case["case_id"])
    if case.get("paper_id"):
        return str(case["paper_id"])

    legacy_case_id = (
        execute_spec.get("analysis_study", {})
        .get("metadata", {})
        .get("original_paper_id")
    )
    if legacy_case_id:
        return str(legacy_case_id)

    planned = _execute_plan(execute_spec)
    if planned.get("planned_id"):
        planned_id = str(planned["planned_id"])
        return planned_id.rsplit("_path", 1)[0].rsplit("_plan", 1)[0]

    raise ValueError("Execution spec is missing case.case_id/case.paper_id and plan.planned_id/planned_method.planned_id.")


def get_path_id(execute_spec: Dict[str, Any]) -> str:
    planned = _execute_plan(execute_spec)
    planned_id = planned.get("planned_id")
    if planned_id:
        return str(planned_id)
    return f"{get_case_id(execute_spec)}_path01"

# Builds robustness/memory/shared_memory_<case_id>.json
def get_case_memory_path(case_id: str) -> Path:
    return MEMORY_DIR / f"shared_memory_{case_id}.json"


def _load_template() -> Dict[str, Any]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

# If the file does not exist, it creates one from the template with an empty memory_records list.
def ensure_memory_file(case_id: str) -> Path:
    memory_path = get_case_memory_path(case_id)
    if memory_path.exists():
        return memory_path

    template = _load_template()
    template["case_id"] = case_id
    template["memory_records"] = []
    memory_path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    return memory_path


def load_case_memory(case_id: str) -> Tuple[Dict[str, Any], Path]:
    memory_path = ensure_memory_file(case_id)
    return json.loads(memory_path.read_text(encoding="utf-8")), memory_path


def _task_list(execute_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _execute_plan(execute_spec).get("tasks", [])


def _pick_signature_task(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    for task in tasks:
        if task.get("task_role") == "conclusion_oriented_reanalysis":
            return task
    return tasks[0] if tasks else {}


# The Pruning Agent's input is the universal schema: case / tasks_info / datasets / plan.
def _prune_plan(prune_in: Dict[str, Any]) -> Dict[str, Any]:
    plan = prune_in.get("plan")
    if isinstance(plan, dict):
        return plan
    # Legacy prune_in_schema.json shape.
    return prune_in.get("planning_output", {}).get("description", {}) or {}


def get_prune_case_id(prune_in: Dict[str, Any]) -> str:
    case = prune_in.get("case") or prune_in.get("case_reference") or {}
    if case.get("case_id"):
        return str(case["case_id"])
    planned_id = _prune_plan(prune_in).get("planned_id")
    if planned_id:
        return str(planned_id).rsplit("_path", 1)[0].rsplit("_plan", 1)[0]
    raise ValueError("Prune input is missing case.case_id and plan.planned_id.")


def get_prune_path_id(prune_in: Dict[str, Any]) -> str:
    planned_id = _prune_plan(prune_in).get("planned_id")
    if planned_id:
        return str(planned_id)
    return f"{get_prune_case_id(prune_in)}_plan"


def _prune_tasks(prune_in: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = _prune_plan(prune_in)
    # Legacy prune_in nests tasks under planned_method; the universal schema's
    # "plan" section carries them directly.
    planned_method = plan.get("planned_method")
    if isinstance(planned_method, dict) and planned_method.get("tasks"):
        return planned_method["tasks"]
    return plan.get("tasks", [])


def _task_value(task: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = task
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def build_memory_record_from_prune_output(
    prune_in: Dict[str, Any],
    prune_out: Dict[str, Any],
    *,
    iteration: int,
) -> Dict[str, Any]:
    if not isinstance(prune_out, dict):
        raise ValueError("Prune output must be a JSON object.")

    pruning_output = prune_out.get("pruning_output", {})
    decision = pruning_output.get("decision")
    status = PRUNE_DECISION_TO_STATUS.get(str(decision).strip().lower() if decision else "")
    if status is None:
        raise ValueError(f"Unsupported pruning status: {decision}")

    case_id = get_prune_case_id(prune_in)
    path_id = get_prune_path_id(prune_in)
    plan = _prune_plan(prune_in)
    # Legacy prune_in keeps the path-level signature under planned_method; the
    # universal schema's "plan" section keeps it under path_signature.
    planned_method = plan.get("planned_method") or plan.get("path_signature", {})
    tasks = _prune_tasks(prune_in)

    # The agent's own memory_record is the primary source: it carries the per-task decisions
    # and overall_decision that cannot be derived from the plan. Fields it leaves out are
    # filled in from the candidate path below.
    agent_record = pruning_output.get("memory_record", {})
    if not isinstance(agent_record, dict):
        agent_record = {}
    agent_signature = agent_record.get("path_signature", {})
    if not isinstance(agent_signature, dict):
        agent_signature = {}

    task_scope = agent_record.get("task_scope") or [task.get("task_id", "Task") for task in tasks] \
        or [item.get("task_id") for item in prune_in.get("tasks_info", []) if isinstance(item, dict)]
    path_summary = agent_record.get("path_summary") or plan.get("path_summary") or "Pruning review record."

    first_task = tasks[0] if tasks else {}
    analysis_path = first_task.get("analysis_path", {}) if isinstance(first_task, dict) else {}
    key_choices = analysis_path.get("key_choices", {}) if isinstance(analysis_path, dict) else {}
    variables = analysis_path.get("variables", {}) if isinstance(analysis_path, dict) else {}
    controls = key_choices.get("control_variables")
    if not controls and isinstance(variables.get("controls"), list):
        controls = [item.get("name", item) if isinstance(item, dict) else item for item in variables["controls"]]

    derived_signature = {
        "model_family": _task_value(first_task, "analysis_path", "model_family", default=planned_method.get("model_family", "not_stated")),
        "outcome": variables.get("outcome", {}).get("name", key_choices.get("outcome_measure")),
        "main_predictor": variables.get("main_predictor", {}).get("name", key_choices.get("main_predictor_measure")),
        "controls": controls or [],
        "sample_restriction": key_choices.get("sample_restriction"),
        "missing_data_rule": key_choices.get("missing_data_rule"),
        "variable_construction": key_choices.get("data_processing"),
        "inference_rule": key_choices.get("inference_rule"),
    }
    # The universal schema states the path-level signature directly under plan.path_signature;
    # it is more authoritative than anything reconstructed from the first task.
    plan_signature = plan.get("path_signature", {})
    if not isinstance(plan_signature, dict):
        plan_signature = {}

    # Keep everything the agent reported (task_decisions, overall_decision) and backfill any
    # signature field it omitted from the candidate path.
    path_signature = {
        **derived_signature,
        **{k: v for k, v in plan_signature.items() if v is not None},
        **{k: v for k, v in agent_signature.items() if v is not None},
    }

    return {
        "path_id": path_id,
        "case_id": case_id,
        "status": status,
        "task_scope": task_scope,
        "path_summary": path_summary,
        "path_signature": path_signature,
        "status_reason": pruning_output.get("decision_summary") or agent_record.get("status_reason") or "Pruning decision recorded.",
        "source_agent": "pruning_agent",
        "iteration": iteration,
    }

# Converts the execution spec into one shared-memory record.
# Pulls out task scope, model family, outcome, predictor, controls, and status reason.
def build_memory_record_from_execute_spec(
    execute_spec: Dict[str, Any],
    *,
    status: str,
    status_reason: str,
    iteration: int,
    source_agent: str = "execution_agent",
) -> Dict[str, Any]:
    if status not in EXECUTION_STATUSES and status not in {"accepted", "rejected"}:
        raise ValueError(f"Unsupported shared memory status: {status}")

    case_id = get_case_id(execute_spec)
    path_id = get_path_id(execute_spec)
    plan = _execute_plan(execute_spec)
    tasks = _task_list(execute_spec)
    signature_task = _pick_signature_task(tasks)
    analysis_path = signature_task.get("analysis_path", {})
    key_choices = analysis_path.get("key_choices", {})
    variables = analysis_path.get("variables", {})

    path_descriptions = [
        task.get("analysis_path", {}).get("path_description")
        for task in tasks
        if task.get("analysis_path", {}).get("path_description")
    ]
    if plan.get("path_summary"):
        path_summary = plan["path_summary"]
    elif path_descriptions:
        path_summary = " | ".join(path_descriptions)
    else:
        path_summary = "Execution path record."

    controls = key_choices.get("control_variables")
    if not controls and isinstance(variables.get("controls"), list):
        controls = [item.get("name", item) if isinstance(item, dict) else item for item in variables["controls"]]

    task_signature = {
        "model_family": analysis_path.get("model_family", "not_stated"),
        "outcome": variables.get("outcome", {}).get("name", key_choices.get("outcome_measure")),
        "main_predictor": variables.get("main_predictor", {}).get("name", key_choices.get("main_predictor_measure")),
        "controls": controls or [],
        "sample_restriction": key_choices.get("sample_restriction"),
        "missing_data_rule": key_choices.get("missing_data_rule"),
        "variable_construction": key_choices.get("data_processing"),
        "inference_rule": key_choices.get("inference_rule"),
    }
    plan_signature = plan.get("path_signature", {})
    if not isinstance(plan_signature, dict):
        plan_signature = {}

    return {
        "path_id": path_id,
        "case_id": case_id,
        "status": status,
        "task_scope": [task.get("task_id", "Task") for task in tasks] or plan.get("task_scope", []),
        "path_summary": path_summary,
        "path_signature": {
            **task_signature,
            **{k: v for k, v in plan_signature.items() if v is not None},
        },
        "status_reason": status_reason,
        "source_agent": source_agent,
        "iteration": iteration,
    }

# Adds a new record or replaces an existing one with the same path_id
def update_memory_record(memory_data: Dict[str, Any], new_record: Dict[str, Any]) -> Dict[str, Any]:
    updated_memory = copy.deepcopy(memory_data)
    records = updated_memory.setdefault("memory_records", [])

    for index, record in enumerate(records):
        if record.get("path_id") == new_record.get("path_id"):
            merged = dict(record)
            merged.update(new_record)
            records[index] = merged
            return updated_memory

    records.append(new_record)
    return updated_memory


def save_case_memory(memory_path: Path, memory_data: Dict[str, Any]) -> None:
    memory_path.write_text(json.dumps(memory_data, indent=2), encoding="utf-8")

# Shows the proposed update in terminal and asks for confirmation.
def write_memory_update_with_confirmation(memory_path: Path, current_memory: Dict[str, Any], new_record: Dict[str, Any]) -> bool:
    proposed = update_memory_record(current_memory, new_record)
    print("\nShared memory update proposal:")
    print(json.dumps(new_record, indent=2))
    response = input(f"Write this update to {memory_path.name}? (yes/no): ").strip().lower()
    if response != "yes":
        print("Shared memory update skipped.")
        return False

    save_case_memory(memory_path, proposed)
    print(f"Shared memory updated at {memory_path}")
    return True

# derive the path status for updating the shared memory record based on the execution results.
def derive_execution_status(execution_results: Dict[str, Any]) -> Tuple[str, str]:
    memory_update = execution_results.get("shared_memory_update", {})
    recommended_status = memory_update.get("recommended_status")
    if recommended_status in EXECUTION_STATUSES:
        reason = memory_update.get("status_reason") or memory_update.get("update_summary") or "Execution agent provided a memory update."
        return recommended_status, reason

    overview = execution_results.get("execution_overview", {})
    overall_status = overview.get("overall_execution_status")
    if overall_status == "success":
        return "executed_success", overview.get("overall_summary", "Execution completed successfully.")

    failed_tasks = execution_results.get("task_outputs", [])
    failure_reasons = []
    retryable = False
    for task in failed_tasks:
        failure = task.get("failure", {})
        reason = failure.get("failure_reason")
        stage = failure.get("failure_stage")
        status = task.get("execution_status")
        if status == "failure" and reason:
            failure_reasons.append(f"{task.get('task_id', 'Task')}: {reason}")
            lowered = reason.lower()
            if any(token in lowered for token in ("path", "dependency", "package", "runtime", "import", "docker", "mount")):
                retryable = True
        if stage in {"setup", "data_loading", "code_execution"} and status == "failure":
            retryable = True

    summary = "; ".join(failure_reasons) if failure_reasons else overview.get("overall_summary", "Execution did not finish successfully.")
    if retryable:
        return "execution_failed_retryable", summary
    return "abandoned", summary
