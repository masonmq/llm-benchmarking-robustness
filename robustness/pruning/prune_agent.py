"""
Pruning Agent.

Mirrors robustness/executor/execute_agent.py (run_execute) but for the review-and-route
stage: it consumes the filled prune_in_schema.json (produced by the helper extractor or,
later, by the Planning Agent), performs a deep review (original paper, dataset, analysis
code) against the pruning policy via a ReAct loop, and emits prune_out_schema.json with a
high-quality/low-quality decision and routing.

It follows the executor's validation approach exactly: the output template is embedded in
the prompt and the final Answer is parsed as JSON by the shared ReAct loop. The agent uses
a leakage-safe subset of tools: guarded readers that block human analysis / review
documents, dataset inspection tools, and no file writers.
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
    "read_pdf": "2. Read Original Paper",
    "load_dataset": "3. Explore Dataset",
    "get_dataset_columns": "3. Explore Dataset",
    "get_dataset_info": "3. Explore Dataset",
    "get_dataset_shape": "3. Explore Dataset",
    "get_dataset_head": "3. Explore Dataset",
    "get_dataset_description": "3. Explore Dataset",
    "get_dataset_variable_summary": "3. Explore Dataset",
    "read_txt": "4. Review Analysis Code",
    "read_file": "4. Review Analysis Code",
    "ask_human_input": "5. Human Input",
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
Your goal is to REVIEW exactly one candidate analysis path (plan + analysis code) for a single focal claim, decide whether it is high-quality or low-quality, and ROUTE it (high-quality -> execution, otherwise -> back to planning). You review and route only. Do not run, modify, or create an analysis path.

Your AUTHORIZED inputs are:
1. The prune_in JSON below (candidate path, case info, Task1/Task2 instructions, shared memory, planning self-check).
2. The original paper PDF in the study folder (original_paper.pdf) - you MUST read it to understand the claim, the study design, and the data collection.
3. The authorized original dataset(s) in case_reference.authorized_datasets - you MUST explore them in depth (shape, focal variables, dependence structure), not just load them.
4. The candidate path's analysis code files listed in planning_output.description.codebase - you MUST read every file end to end.

FORBIDDEN inputs: the human analysis / review PDF (e.g., files ending in "_review.pdf"), human analytical reports, and any expected or ground-truth results. Do not open them; doing so is cheating and invalidates the benchmark.

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
- decision is "high-quality" or "low-quality" only; fill path_signature.task_decisions for Task1 and Task2 and overall_decision; next_step follows the decision rule above.
- Every task decision reason must cite the specific rule number(s) that triggered, or the positive evidence supporting high-quality.
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
            iteration = 1,
        )
        write_memory_update_with_confirmation(resolved_memory_path, current_memory, memory_record)

    return final_answer

