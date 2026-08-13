import json
import os
from typing import Any, Dict

from core.actions import base_known_actions, get_execute_tool_definitions
from core.agent import run_react_loop, save_output
from core.constants import (
    CONCLUSION_CLASSIFICATION_RULES,
    EXECUTION_RULES,
    ROBUSTNESS_EXECUTE_CONSTANTS,
)
from core.prompts import (
    EXAMPLE_ROBUSTNESS,
    EXECUTE,
    PREAMBLE_ROBUSTNESS,
    ROBUSTNESS_EXECUTE_CODE_MODE_POLICY,
)
from core.utils import configure_file_logging, get_logger
from replicatorbench.info_extractor.file_utils import read_json
from robustness.executor.execute_tools import run_shell_command, run_stata_do_file
from robustness.executor.orchestrator_tool import (
    orchestrator_build_image,
    orchestrator_execute_entry,
    orchestrator_generate_dockerfile,
    orchestrator_plan,
    orchestrator_preview_entry,
    orchestrator_run_container,
    orchestrator_stop_container,
)
from robustness.memory.shared_memory import (
    build_memory_record_from_execution_results,
    get_case_id,
    get_path_id,
    load_case_memory,
    load_execute_spec,
    save_case_memory,
    update_memory_record,
    validate_execution_ready,
)
# from robustness.validator.execute_feedback import run_evaluate_execute_feedback


logger, formatter = get_logger(name="robustness")
system_prompt = "\n\n".join([PREAMBLE_ROBUSTNESS, EXECUTE, EXAMPLE_ROBUSTNESS])

known_actions = {
    **base_known_actions(),
    "run_shell_command": run_shell_command,
    "run_stata_do_file": run_stata_do_file,
    "orchestrator_generate_dockerfile": orchestrator_generate_dockerfile,
    "orchestrator_build_image": orchestrator_build_image,
    "orchestrator_run_container": orchestrator_run_container,
    "orchestrator_plan": orchestrator_plan,
    "orchestrator_preview_entry": orchestrator_preview_entry,
    "orchestrator_execute_entry": orchestrator_execute_entry,
    "orchestrator_stop_container": orchestrator_stop_container,
}

CHECKPOINT_MAP = {
    "orchestrator_generate_dockerfile": "1. Generate Dockerfile",
    "orchestrator_build_image": "2. Build Image",
    "orchestrator_run_container": "3. Start Container",
    "orchestrator_plan": "4. Plan & Preview",
    "orchestrator_preview_entry": "4. Plan & Preview",
    "ask_human_input": "5. Human Approval",
    "orchestrator_execute_entry": "6. Execute Code",
    "orchestrator_stop_container": "7. Stop Container",
}


def run_execute(
    study_path: str,
    show_prompt: bool = False,
    templates_dir: str = "./templates",
    tier: str = "easy",
    code_mode: str = "python",
    model_name: str = "gpt-5",
):
    configure_file_logging(logger, study_path, f"execute_{tier}__{code_mode}.log")
    logger.info(f"[agent] dynamic orchestrator run loop for: {study_path}")

    schema_path = os.path.join(templates_dir, "execute_out_schema.json")
    execute_spec, execute_spec_path = load_execute_spec(study_path)
    case_id = get_case_id(execute_spec)
    path_id = get_path_id(execute_spec)
    current_memory, memory_path = load_case_memory(case_id, study_path)
    validate_execution_ready(execute_spec, current_memory)

    previous_files = ROBUSTNESS_EXECUTE_CONSTANTS.get("files", {}).copy()
    previous_template = ROBUSTNESS_EXECUTE_CONSTANTS.get("json_template")
    try:
        ROBUSTNESS_EXECUTE_CONSTANTS["files"] = {
            execute_spec_path.name: "Approved Task1 and Task2 candidates for this execution run.",
            memory_path.name: "Case Shared Memory. Read-only to the agent.",
            "execution_result.json": "Raw output from orchestrator_execute_entry, including stdout and stderr.",
            "_runtime/Dockerfile": "Generated Dockerfile.",
        }
        ROBUSTNESS_EXECUTE_CONSTANTS["json_template"] = schema_path

        code_policy = ROBUSTNESS_EXECUTE_CODE_MODE_POLICY.get(
            code_mode,
            ROBUSTNESS_EXECUTE_CODE_MODE_POLICY["native"],
        )
        max_repair_attempts = _get_max_execution_attempts(execute_spec)
        active_candidates = {
            task["task_id"]: task["candidate_id"]
            for task in execute_spec["plan"]["tasks"]
        }
        instruction = f"""
Execute the two approved active candidates together inside a Docker container.

Path ID: {path_id}
Active candidates: {json.dumps(active_candidates)}
Maximum repair attempts: {max_repair_attempts}

{code_policy}

Fixed Execution Agent rules:
{json.dumps(EXECUTION_RULES, indent=2)}

Fixed conclusion classification rules:
{json.dumps(CONCLUSION_CLASSIFICATION_RULES, indent=2)}

Input files:
- {execute_spec_path.name}: the approved universal schema.
- {memory_path.name}: read-only case history.

Execute only the two active candidates marked high-quality. Do not change the analytical method, focal claim, task instructions, or dataset. You may make at most {max_repair_attempts} implementation repairs involving dependencies, file paths, code defects, or result extraction. Record every repair in the affected task's method_fidelity.deviations. Do not create a new candidate ID.

For each conclusion, apply the fixed conclusion classification rules together with the focal direction or pattern in the matching analysis anchor. The fixed rules control conclusion_class if a planned inference rule conflicts with them. For a frequentist result, expected direction with p <= 0.05 is support. A result with 0.05 < p <= 0.055 remains support only when the estimate is substantively meaningful and its uncertainty interval narrowly crosses the null; describe it as borderline. Clearly weak aligned evidence is inconclusive. Report uncertainty separately and record the rule actually applied in the output.

Process:
1. Generate the Dockerfile from {execute_spec_path.name}.
2. Build the image and start the container.
3. Plan and preview both task entries.
4. Ask the human to approve the exact execution command before running it.
5. Execute Task1 and Task2 as one run. Inspect execution_result.json after each attempt.
6. Apply only allowed implementation repairs, up to the limit, and retry as needed.
7. Stop the container.
8. Return execution_results.json using the required schema below.

For each task output and shared_memory_update.task_updates entry, copy task_id and candidate_id from the universal schema. A successful task has execution_status success and recommended_status executed_success. Any task that remains unsuccessful after the repair limit has execution_status failure and recommended_status execution_failed. Set shared_memory_update.execution_run_status to executed_success only if both tasks succeed; otherwise set it to execution_failed. Do not use retryable, abandoned, accepted, or rejected statuses.

=== START OF JSON OUTPUT ===
{json.dumps(read_json(schema_path))}
=== END OF JSON OUTPUT ===

Current Study Path: "{study_path}"
Start by generating the Dockerfile.

Every response must use one of these formats:
Thought: [short reasoning]
Action: [next action]
PAUSE

or, when finished:

Thought: [short reasoning]
Answer: [final JSON object]
""".strip()

        if show_prompt:
            logger.info("\n\n===== Execution Agent Input (truncated) =====\n" + instruction[:2000])
        print(f"\n\nmodel name for execute agent: {model_name}\n\n")

        final_answer = run_react_loop(
            system_prompt,
            known_actions,
            get_execute_tool_definitions(),
            instruction,
            session_state={"analyzers": {}},
            study_path=study_path,
            stage_name="generate-execute",
            checkpoint_map=CHECKPOINT_MAP,
            on_final=lambda answer: save_output(
                answer,
                study_path=study_path,
                filename="execution_results.json",
                stage_name="execute",
            ),
            model_name=model_name,
            logger=logger,
            code_mode=code_mode,
            # feedback_function=run_evaluate_execute_feedback,
        )
        if (
            not isinstance(final_answer, dict)
            or not isinstance(final_answer.get("execution_overview"), dict)
            or not isinstance(final_answer.get("task_outputs"), list)
        ):
            return {
                "execution_results": final_answer,
                "memory_updated": False,
                "pipeline_outcome": "invalid_execution_output",
            }

        execution_results = final_answer
        memory_record = build_memory_record_from_execution_results(
            execute_spec,
            execution_results,
        )
        # Temporarily write without human confirmation so Shared Memory stays synced with execution_results.json.
        updated_memory = update_memory_record(current_memory, memory_record)
        save_case_memory(memory_path, updated_memory)
        logger.info("[memory] execution shared memory updated at %s", memory_path)
        return {
            "execution_results": execution_results,
            "memory_updated": True,
            "pipeline_outcome": "execution_complete",
        }
    finally:
        ROBUSTNESS_EXECUTE_CONSTANTS["files"] = previous_files
        if previous_template is not None:
            ROBUSTNESS_EXECUTE_CONSTANTS["json_template"] = previous_template


def _get_max_execution_attempts(execute_spec: Dict[str, Any]) -> int:
    execution_config = execute_spec.get("execution_directives", {})
    debugging_rule = execution_config.get("debugging_rule", {})
    try:
        configured = int(debugging_rule.get("max_repair_attempts", 1))
    except (TypeError, ValueError):
        configured = 1
    return max(1, min(configured, 3))
