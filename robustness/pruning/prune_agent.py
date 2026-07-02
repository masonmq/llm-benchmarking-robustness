"""
Pruning Agent.

Mirrors robustness/executor/execute_agent.py (run_execute) but for the review-and-route
stage: it consumes the filled prune_in_schema.json (produced by the helper extractor or,
later, by the Planning Agent), runs the seven required checks via a ReAct loop, and emits
prune_out_schema.json with an accept/reject decision and routing.

It follows the executor's validation approach exactly: the output template is embedded in
the prompt and the final Answer is parsed as JSON by the shared ReAct loop. The agent uses
a leakage-safe subset of tools (no PDF / free-text readers, no file writers).
"""
import os
import json

from core.constants import ROBUSTNESS_PRUNE_CONSTANTS, PRUNE_PROMPT_VERSION
from core.actions import prune_known_actions, get_prune_tool_definitions
from core.agent import run_react_loop, save_output
from core.prompts import PREAMBLE_PRUNE, EXAMPLE_PRUNE, PRUNE_CHECKS_POLICY
from core.utils import configure_file_logging, get_logger
from replicatorbench.info_extractor.file_utils import read_json
from robustness.memory.shared_memory import (
    build_memory_record_from_prune_output,
    ensure_memory_file,
    get_prune_case_id,
    get_prune_path_id,
    load_case_memory,
    write_memory_update_with_confirmation,
)

logger, formatter = get_logger(name="robustness")
system_prompt = "\n\n".join([PREAMBLE_PRUNE, EXAMPLE_PRUNE])

known_actions = prune_known_actions()

CHECKPOINT_MAP = {
    "list_files_in_folder": "1. Inspect Inputs",
    "read_json": "1. Inspect Inputs",
    "load_dataset": "2. Verify Dataset",
    "get_dataset_columns": "2. Verify Dataset",
    "get_dataset_info": "2. Verify Dataset",
    "get_dataset_shape": "2. Verify Dataset",
    "get_dataset_head": "2. Verify Dataset",
    "get_dataset_description": "2. Verify Dataset",
    "get_dataset_variable_summary": "2. Verify Dataset",
    "ask_human_input": "3. Human Input",
}


def _load_json_object(file_path: str):
    loaded = read_json(file_path)
    if isinstance(loaded, dict):
        return loaded
    if isinstance(loaded, str):
        return json.loads(loaded)
    raise TypeError(f"Unsupported JSON payload type from {file_path}: {type(loaded).__name__}")


def run_prune(study_path: str, show_prompt: bool = False, templates_dir: str = "./templates",
              tier: str = "easy", code_mode: str = "python", model_name: str = "gpt-5"):
    configure_file_logging(logger, study_path, "prune.log")
    logger.info(f"[agent] pruning review loop for: {study_path}")
    # Reproducibility: log model and prompt version for every run.
    logger.info(
        f"[repro] stage=prune model={model_name} prompt_version={PRUNE_PROMPT_VERSION} "
        f"temperature=0_or_reasoning_default seed=NA(controlled by temperature=0/reasoning model)"
    )

    # Load the Pruning Agent input produced by the helper extractor (or the Planning Agent).
    prune_in_path = os.path.join(study_path, "prune_in_schema.json")
    if not os.path.exists(prune_in_path):
        msg = (
            f"prune_in_schema.json not found in {study_path}. "
            f"Run the helper extractor first (make robustness-pruning-helper STUDY=...)."
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    prune_in = _load_json_object(prune_in_path)
    case_id = get_prune_case_id(prune_in)
    path_id = get_prune_path_id(prune_in)
    ensure_memory_file(case_id)

    out_schema_path = os.path.join(templates_dir, "prune_out_schema.json")
    prune_out_template = _load_json_object(out_schema_path)

    instruction = f"""
Your goal is to REVIEW exactly one candidate analysis path and ROUTE it (accept -> execution, reject -> planning) for a single focal claim. You review and route only. Do not run, modify, or create an analysis path.

The complete, AUTHORIZED input is the prune_in JSON below. Use ONLY this input (plus, if useful, inspection of the authorized original dataset listed in case_reference.authorized_datasets). Read the original paper PDF, the proposed-analysis / review PDF, human reports, human code, or any expected results.

=== START OF PRUNE INPUT (prune_in_schema.json) ===
{json.dumps(prune_in, indent=2)}
=== END OF PRUNE INPUT ===

{PRUNE_CHECKS_POLICY}

When you are done, output the Answer as a single JSON object following this Pruning Agent output schema:
=== START OF JSON OUTPUT ===
{json.dumps(prune_out_template, indent=2)}
=== END OF JSON OUTPUT ===

Output Requirements:
- Return a valid JSON object only (no markdown, no commentary).
- pruning_output.case_id and pruning_output.planned_id must match the candidate path in the input.
- check_results must contain the six schema check fields. Fold the planning_self_check result into decision_summary.
- decision is "accepted" or "rejected" only; next_step follows the decision rule above.
- memory_record.status must equal decision, and memory_record.source_agent must be "pruning_agent".

Current Study Path: "{study_path}"

Remember, every response needs to have one of the two following formats:
----- FORMAT 1 (to call an action) -------
Thought: [your reasoning]
Action: [the next action]
PAUSE
----- FORMAT 2 (final response) -------
Thought: [your reasoning]
Answer: [the final JSON]
""".strip()

    if show_prompt:
        logger.info("\n\n===== Pruning Agent Input (truncated) =====\n" + instruction[:2000])
    print(f"\n\nmodel name for pruning agent: {model_name}\n\n")

    tool_definitions = get_prune_tool_definitions()
    final_answer = run_react_loop(
        system_prompt,
        known_actions,
        tool_definitions,
        instruction,
        session_state={"analyzers": {}},
        study_path=study_path,
        stage_name="robustness-prune",
        checkpoint_map=CHECKPOINT_MAP,
        on_final=lambda ans: save_output(
            ans,
            study_path=study_path,
            filename="prune_out_schema.json",
            stage_name="prune",
        ),
        model_name=model_name,
        logger=logger,
        code_mode=code_mode,
    )

    if isinstance(final_answer, dict):
        current_memory, resolved_memory_path = load_case_memory(case_id)
        memory_record = build_memory_record_from_prune_output(
            prune_in,
            final_answer,
            iteration=_get_next_iteration(current_memory, path_id),
        )
        write_memory_update_with_confirmation(resolved_memory_path, current_memory, memory_record)

    return final_answer

