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

from core.constants import ROBUSTNESS_PRUNE_CONSTANTS, PRUNE_PROMPT_VERSION, PRUNING_RULES
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


def _is_universal_schema(payload: dict) -> bool:
    """The Planning Agent emits the universal schema (case/tasks_info/datasets/plan).
    The legacy helper extractor emits the prune_in shape (case_reference/planning_output)."""
    return "planning_output" not in payload and "plan" in payload


def _legacy_to_universal(payload: dict) -> dict:
    """Lift a legacy prune_in_schema.json (helper-extractor output) into the universal shape.

    Only the section names change: case_reference -> case / tasks_info / datasets, and
    planning_output.description -> plan. The candidate path's own content is carried over
    verbatim so the standalone `make robustness-pruning` flow keeps working.
    """
    case_reference = payload.get("case_reference", {}) or {}
    plan = dict(payload.get("planning_output", {}).get("description", {}) or {})
    if "analysis_code" not in plan and "codebase" in plan:
        plan["analysis_code"] = plan.pop("codebase")

    files = []
    for entry in case_reference.get("authorized_datasets", []) or []:
        if isinstance(entry, dict):
            files.append(entry)

    return {
        "iteration": payload.get("iteration", 1),
        "case": {
            "case_id": case_reference.get("case_id"),
            "paper_title": case_reference.get("paper_title"),
            "paper_file": case_reference.get("paper_file"),
            "focal_claim": case_reference.get("focal_claim"),
            "hypothesis": case_reference.get("hypothesis"),
            "study_type": case_reference.get("study_type"),
        },
        "tasks_info": case_reference.get("tasks_info", []),
        "datasets": {"authorized_only": "true", "files": files},
        "plan": plan,
    }


def _build_prune_input(payload: dict, shared_memory: dict) -> dict:
    """Build the Pruning Agent's input: the universal schema plus the two sections that the
    pipeline owns rather than any agent.

    shared_memory is loaded from the case memory file, and pruning_rules come from
    core.constants.PRUNING_RULES so they are identical on every run.
    """
    universal = payload if _is_universal_schema(payload) else _legacy_to_universal(payload)
    return {
        **universal,
        "shared_memory": shared_memory,
        "pruning_rules": PRUNING_RULES,
    }


def run_prune(study_path: str, show_prompt: bool = False, templates_dir: str = "./templates",
              tier: str = "easy", code_mode: str = "python", model_name: str = "gpt-5",
              plan_output: dict = None, run_execution: bool = False):
    configure_file_logging(logger, study_path, "prune.log")
    logger.info(f"[agent] pruning review loop for: {study_path}")
    # Reproducibility: log model and prompt version for every run.
    logger.info(
        f"[repro] stage=prune model={model_name} prompt_version={PRUNE_PROMPT_VERSION} "
        f"temperature=0_or_reasoning_default seed=NA(controlled by temperature=0/reasoning model)"
    )

    # Input: either the Planning Agent's universal-schema output handed over in memory
    # (make robustness-plan), or the prune_in_schema.json written by the helper extractor
    # (make robustness-pruning-helper / make robustness-pruning).
    if plan_output is not None:
        raw_input = plan_output
        logger.info("[agent] pruning input received directly from the Planning Agent (universal schema)")
    else:
        prune_in_path = os.path.join(study_path, "prune_in_schema.json")
        if not os.path.exists(prune_in_path):
            msg = (
                f"prune_in_schema.json not found in {study_path}. "
                f"Run the helper extractor first (make robustness-pruning-helper STUDY=...)."
            )
            logger.error(msg)
            raise FileNotFoundError(msg)
        raw_input = _load_json_object(prune_in_path)

    # Shared memory and the pruning rules are supplied by the pipeline, not by an agent.
    # The agent READS shared memory here (it is embedded in its input) and later WRITES one
    # record back, subject to the same human confirmation as before.
    case_id = get_prune_case_id(_build_prune_input(raw_input, {}))
    path_id = get_prune_path_id(_build_prune_input(raw_input, {}))
    shared_memory, _ = load_case_memory(case_id)
    logger.info(f"[memory] loaded shared memory for pruning: case={case_id} path={path_id}")

    prune_in = _build_prune_input(raw_input, shared_memory)

    out_schema_path = os.path.join(templates_dir, "prune_out_schema.json")
    prune_out_template = _load_json_object(out_schema_path)

    instruction = f"""
Your goal is to REVIEW exactly one candidate analysis path (plan + analysis code) for a single focal claim, decide whether it is high-quality or low-quality, and ROUTE it (high-quality -> execution, otherwise -> back to planning). You review and route only. Do not run, modify, or create an analysis path.

Your AUTHORIZED inputs are:
1. The prune_in JSON below (candidate path, case info, Task1/Task2 instructions, shared memory, planning self-check).
2. The original paper PDF in the study folder (original_paper.pdf) - you MUST read it to understand the claim, the study design, and the data collection.
3. The authorized original dataset(s) in datasets.files - you MUST explore them in depth (shape, focal variables, dependence structure), not just load them.
4. The candidate path's analysis code files listed in plan.tasks[].analysis_code - you MUST read every file end to end.

FORBIDDEN inputs: the human analysis / review PDF (e.g., files ending in "_review.pdf"), human analytical reports, and any expected or ground-truth results. Do not open them; doing so is cheating and invalidates the benchmark.

=== START OF PRUNE INPUT (universal_schema.json) ===
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
        # Write the agent's memory_record back to the case memory file, still gated on the
        # same human yes/no confirmation as before.
        current_memory, resolved_memory_path = load_case_memory(case_id)
        memory_record = build_memory_record_from_prune_output(
            prune_in,
            final_answer,
            iteration=prune_in.get("iteration", 1),
        )
        write_memory_update_with_confirmation(resolved_memory_path, current_memory, memory_record)

    if not run_execution:
        return final_answer

    execution_output = None
    decision = ""
    if isinstance(final_answer, dict):
        decision = str(
            final_answer.get("pruning_output", {}).get("decision", "")
        ).strip().lower()

    if decision == "high-quality":
        logger.info("[prune->execute] high-quality path approved; starting execution")
        print("\npruning approved the path; starting execution\n")
        from robustness.executor.execute_agent import run_execute
        execution_output = run_execute(
            study_path=study_path,
            show_prompt=show_prompt,
            templates_dir=templates_dir,
            tier=tier,
            code_mode=code_mode,
            model_name=model_name,
        )
    else:
        logger.info(
            "[prune->execute] execution skipped because pruning decision was %r",
            decision or "missing/invalid",
        )

    return {
        "prune_output": final_answer,
        "execution_output": execution_output,
    }
