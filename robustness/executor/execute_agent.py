
from ast import If
import os
import json
import logging
from typing import Dict, Any

from core.constants import ROBUSTNESS_EXECUTE_CONSTANTS
from core.actions import base_known_actions, get_execute_tool_definitions
from core.agent import run_react_loop, save_output
from core.prompts import PREAMBLE_ROBUSTNESS, EXECUTE, EXAMPLE_ROBUSTNESS, ROBUSTNESS_EXECUTE_CODE_MODE_POLICY
from core.utils import configure_file_logging, get_logger
from replicatorbench.info_extractor.file_utils import read_json
from robustness.validator.execute_feedback import run_evaluate_execute_feedback
from robustness.memory.shared_memory import (
    build_memory_record_from_execute_spec,
    derive_execution_status,
    ensure_memory_file,
    get_case_id,
    get_case_memory_path,
    get_path_id,
    load_case_memory,
    load_execute_spec,
    write_memory_update_with_confirmation,
)

# Execute-stage-only tools
from robustness.executor.execute_tools import (
    run_shell_command, run_stata_do_file
)
from robustness.executor.orchestrator_tool import (
    orchestrator_generate_dockerfile,
    orchestrator_build_image,
    orchestrator_run_container,
    orchestrator_plan,
    orchestrator_preview_entry,
    orchestrator_execute_entry,
    orchestrator_stop_container,
)

logger, formatter = get_logger(name="robustness")
system_prompt = "\n\n".join([PREAMBLE_ROBUSTNESS, EXECUTE, EXAMPLE_ROBUSTNESS])

# Map action names to their functions
known_actions = {
    **base_known_actions(),
    "run_shell_command": run_shell_command,
    "run_stata_do_file": run_stata_do_file,

    # Orchestrator tools
    "orchestrator_generate_dockerfile": orchestrator_generate_dockerfile,
    "orchestrator_build_image": orchestrator_build_image,
    "orchestrator_run_container": orchestrator_run_container,
    "orchestrator_plan": orchestrator_plan,
    "orchestrator_preview_entry": orchestrator_preview_entry,
    "orchestrator_execute_entry": orchestrator_execute_entry,
    "orchestrator_stop_container": orchestrator_stop_container,
}

CHECKPOINT_MAP = {
    # PHASE 1
    "orchestrator_generate_dockerfile": "1. Generate Dockerfile",
    "orchestrator_build_image":         "2. Build Image",
    
    # PHASE 2
    "orchestrator_run_container":       "3. Start Container",
    "orchestrator_plan":                "4. Plan & Preview",
    "orchestrator_preview_entry":       "4. Plan & Preview",
    
    # PHASE 3
    "ask_human_input":                  "5. Human Approval",
    
    # PHASE 4
    "orchestrator_execute_entry":       "6. Execute Code",
    
    # PHASE 5
    "orchestrator_stop_container":      "7. Stop Container"
}


def run_execute(study_path: str, show_prompt: bool = False, templates_dir: str = "./templates", tier="easy", code_mode: str = "python", model_name: str="gpt-5"):
    """
    it loads execute_in_schema.json up front.
    Gets case_id and path_id.
    Ensures the case memory file exists.
    Adds the execution input and memory file to the agent context.
    After the run, derives the shared-memory status from the final execution result.
    Shows the proposed memory update to the human and writes it only if confirmed.
    If the status is execution_failed_retryable, it reruns up to the retry cap.
    """
    configure_file_logging(logger, study_path, f"execute_{tier}__{code_mode}.log")
    logger.info(f"[agent] dynamic orchestrator run loop for: {study_path}")

    schema_path = os.path.join(templates_dir, "execute_out_schema.json")
    execute_spec, execute_spec_path = load_execute_spec(study_path)
    case_id = get_case_id(execute_spec)
    path_id = get_path_id(execute_spec)
    ensure_memory_file(case_id)
    memory_path = get_case_memory_path(case_id)
    prev_files = ROBUSTNESS_EXECUTE_CONSTANTS.get("files", {}).copy()
    prev_template = ROBUSTNESS_EXECUTE_CONSTANTS.get("json_template")

    try:
        # Update available files context
        ROBUSTNESS_EXECUTE_CONSTANTS["files"] = {
            execute_spec_path.name: "Execution input specification for the current case.",
            memory_path.name: "Case-scoped shared memory file. Read-only for the execution agent prompt; updates happen after execution with human confirmation.",
            "execution_result.json": "Output generated after running 'orchestrator_execute_entry'. Contains stdout/stderr. Read this to debug build errors.",
            "_runtime/Dockerfile": "The generated Dockerfile.",
        }
        ROBUSTNESS_EXECUTE_CONSTANTS["json_template"] = schema_path

        code_policy = ROBUSTNESS_EXECUTE_CODE_MODE_POLICY.get(code_mode, ROBUSTNESS_EXECUTE_CODE_MODE_POLICY["native"])
        max_execution_attempts = _get_max_execution_attempts(execute_spec)

        instruction = f"""
Your goal is to successfully execute the analysis of a given claim in social science inside a Docker container.
You are operating in a DEBUG LOOP. You must assess the result of every action. 

{code_policy}

Input files:
 - Primary execution input: `{execute_spec_path.name}`
 - Shared memory file for this case: `{memory_path.name}`

File operations policy:
 - To modify existing files: ALWAYS call read_file first, then use edit_file for targeted changes.
 - write_file is for creating new files. It will refuse to overwrite unless overwrite=True.
 - Only use write_file(overwrite=True) when you intend to replace the entire file contents.

If an action fails (e.g., Docker build error, Missing Dependency, Code crash), you MUST:
1. Analyze the error message in the Observation.
2. Use `write_file` to FIX the issue (e.g., rewrite `{execute_spec_path.name}` to add packages, or rewrite the code files). Remember that write_file will overwrite any existing content in the provided file_path if existing. When you use the tool, the provided path file_path to the tool MUST be the study path given to you. But to access other files within the file_content argument, you MUST use the container's directories "app/data". 
3. RETRY the failed step.

**Phases of Execution:**

PHASE 1: BUILD ENVIRONMENT
1. `orchestrator_generate_dockerfile`: Creates _runtime/Dockerfile from `{execute_spec_path.name}`.
2. `orchestrator_build_image`: Builds the image.
   * IF BUILD FAILS: Read the error log. It usually means a missing system package or R/Python library. Edit `{execute_spec_path.name}` to add the missing dependency, regenerate the Dockerfile, and rebuild.

PHASE 2: PREPARE RUNTIME
3. `orchestrator_run_container`: Mounts the code and data and starts the container.
4. `orchestrator_plan` & `orchestrator_preview_entry`: Verify what will run.

PHASE 3: HUMAN APPROVAL (Strict Check)
5. Before running the actual analysis code, you MUST Ask the human:
   Action: ask_human_input: "Ready to execute command: <COMMAND>. Approve? (yes/no)"
   * If they say "no", stop the container and fill the output JSON with status "cancelled".
   * If they say "yes", proceed to Phase 4.

PHASE 4: EXECUTE & DEBUG
6. `orchestrator_execute_entry`: Runs the code.
   * IF EXECUTION FAILS (exit_code != 0): 
     - Read the `stderr` in the observation.
     - Identify if it is a code error or missing library.
     - Use `write_file` to fix the script or `{execute_spec_path.name}`.
     - If you changed dependencies, you must go back to Phase 1 (Rebuild).
     - If you only changed code, you can retry `orchestrator_execute_entry`.

PHASE 5: FINALIZE
7. `orchestrator_stop_container`: Cleanup.
8. Parse `execution_result.json` and output the Answer in the following required JSON schema. You must also fill the `shared_memory_update` section, where `recommended_status` is one of `executed_success`, `execution_failed_retryable`, or `abandoned`.
{json.dumps(read_json(schema_path))}

Current Study Path: "{study_path}"
Start by generating the Dockerfile.

Remember, every response needs to have one of the two following formats:
----- FORMAT 1 (For when you need to call actions to help accomplish the given task) -------
Thought: [Your thinking/planning process for completing the task based on interactions so far]
Action: [call next action to help you solve the task]
PAUSE
----- FORMAT 2 (For when you are ready to give a final response)-------
Thought: [Your thinking/planning process for completing the task based on interactions so far]
Answer: [Execute necessary next action to help you solve the task]
""".strip()

        if show_prompt:
            logger.info("\n\n===== Agent Input (truncated) =====\n" + instruction[:2000])
        print(f"\n\nmodel name for execute agent: {model_name}\n\n")
        tool_definitions = get_execute_tool_definitions()

        final_answer = None
        for attempt in range(1, max_execution_attempts + 1):
            logger.info(f"[agent] execution attempt {attempt} of {max_execution_attempts} for path {path_id}")
            final_answer = run_react_loop(
                system_prompt,
                known_actions,
                tool_definitions,
                instruction,
                session_state={"analyzers": {}},
                study_path=study_path,
                stage_name="generate-execute",
                checkpoint_map=CHECKPOINT_MAP,
                on_final=lambda ans: save_output(
                    ans,
                    study_path=study_path,
                    filename="execution_results.json",
                    stage_name="execute"
                ),
                model_name=model_name,
                logger=logger,
                code_mode=code_mode,
                feedback_function=run_evaluate_execute_feedback
            )

            if not isinstance(final_answer, dict):
                return final_answer

            current_memory, resolved_memory_path = load_case_memory(case_id)
            recommended_status, status_reason = derive_execution_status(final_answer)
            memory_record = build_memory_record_from_execute_spec(
                execute_spec,
                status=recommended_status,
                status_reason=status_reason,
                iteration=_get_next_iteration(current_memory, path_id),
            )
            write_memory_update_with_confirmation(resolved_memory_path, current_memory, memory_record)

            if recommended_status != "execution_failed_retryable":
                return final_answer

            if attempt >= max_execution_attempts:
                logger.info("[agent] retryable execution status reached maximum attempts; stopping.")
                return final_answer

            logger.info("[agent] execution marked retryable; rerunning the execution agent.")

        return final_answer
    finally:
        ROBUSTNESS_EXECUTE_CONSTANTS["files"] = prev_files
        if prev_template:
            ROBUSTNESS_EXECUTE_CONSTANTS["json_template"] = prev_template


def _get_max_execution_attempts(execute_spec: Dict[str, Any]) -> int:
    debugging_rule = execute_spec.get("analysis", {}).get("debugging_rule", {})
    try:
        configured = int(debugging_rule.get("max_repair_attempts", 1))
    except (TypeError, ValueError):
        configured = 1
    return max(1, min(configured, 3))


def _get_next_iteration(memory_data: Dict[str, Any], path_id: str) -> int:
    for record in memory_data.get("memory_records", []):
        if record.get("path_id") == path_id:
            try:
                return int(record.get("iteration", 0)) + 1
            except (TypeError, ValueError):
                return 1
    return 1
