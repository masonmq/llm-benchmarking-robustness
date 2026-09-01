import json
from pathlib import Path

from core.actions import get_prune_tool_definitions, prune_known_actions
from core.agent import run_react_loop, save_output
from core.constants import (
    CONCLUSION_CLASSIFICATION_RULES,
    PRUNE_PROMPT_VERSION,
    PRUNING_RULES,
)
from core.human_intervention import agent_intervention_instruction
from core.prompts import EXAMPLE_PRUNE, PREAMBLE_PRUNE, PRUNE_CHECKS_POLICY
from core.utils import configure_file_logging, get_logger
from robustness.memory.shared_memory import (
    accumulate_prune_output,
    apply_pruning_decisions,
    build_memory_record_from_prune_output,
    build_prune_audit_update,
    extract_pruning_decisions,
    get_case_id,
    get_path_id,
    get_task_statuses,
    load_case_memory,
    load_execute_spec,
    write_memory_update_with_confirmation,
)


logger, formatter = get_logger(name="robustness")
system_prompt = "\n\n".join([PREAMBLE_PRUNE, EXAMPLE_PRUNE, agent_intervention_instruction()])
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


def run_prune(
    study_path: str,
    show_prompt: bool = False,
    templates_dir: str = "./templates",
    tier: str = "easy",
    code_mode: str = "python",
    model_name: str = "gpt-5",
    plan_output: dict | None = None,
    run_execution: bool = False,
):
    configure_file_logging(logger, study_path, "prune.log")
    logger.info(f"[agent] pruning review loop for: {study_path}")
    logger.info(
        f"[repro] stage=prune model={model_name} prompt_version={PRUNE_PROMPT_VERSION} "
        "temperature=0_or_reasoning_default seed=NA(controlled by temperature=0/reasoning model)"
    )

    universal_input = plan_output
    if universal_input is None:
        universal_input, _ = load_execute_spec(study_path)
    if not isinstance(universal_input, dict):
        raise ValueError("Pruning input must be a universal-schema JSON object.")

    case_id = get_case_id(universal_input)
    path_id = get_path_id(universal_input)
    shared_memory, memory_path = load_case_memory(case_id, study_path)
    logger.info(f"[memory] loaded shared memory for pruning: case={case_id} path={path_id}")

    statuses = get_task_statuses(universal_input)
    review_task_ids = [task_id for task_id, status in statuses.items() if status is None]
    invalid_statuses = {
        task_id: status
        for task_id, status in statuses.items()
        if status not in {None, "high-quality"}
    }
    if invalid_statuses:
        raise ValueError(f"Pruning received candidates with invalid review statuses: {invalid_statuses}")
    if not review_task_ids:
        raise ValueError("Pruning has no new active candidate to review.")

    prune_in = {
        **universal_input,
        "shared_memory": shared_memory,
        "pruning_rules": PRUNING_RULES,
    }
    schema_path = Path(templates_dir) / "prune_out_schema.json"
    prune_out_template = json.loads(schema_path.read_text(encoding="utf-8"))
    iteration = int(universal_input.get("iteration", 1))

    instruction = f"""
Review the active analytical candidates for one paper. Review only these tasks: {json.dumps(review_task_ids)}.

An active task with status null is new and must receive a high-quality or low-quality decision. An active task already marked high-quality has passed an earlier review: preserve it, do not review it again, and do not add another candidate record for it.

Your authorized inputs are:
1. The universal-schema candidate document below.
2. original_paper.pdf in the study folder.
3. The authorized datasets listed in datasets.files.
4. The source-code files listed for the candidates being reviewed.
5. Case Shared Memory, supplied read-only inside the input.

Never read a human analysis/review PDF or expected or ground-truth results. Do not run, modify, or create an analytical path.
Verify each reviewed candidate against its task-specific analysis anchor. A method is not high-quality merely because it is statistically conventional; its outcome, contrast, sample, model, and inference choices must align with the anchor or have a documented, evidence-based deviation that still answers the task.
For a long original paper, use search_pdf and read_pdf_pages to verify the exact paper evidence. Do not approve or reject a candidate from the opening-page overview alone.

=== START OF PRUNING INPUT ===
{json.dumps(prune_in, indent=2)}
=== END OF PRUNING INPUT ===

{PRUNE_CHECKS_POLICY}

Fixed conclusion classification rules:
{json.dumps(CONCLUSION_CLASSIFICATION_RULES, indent=2)}

Use these rules when checking the candidate's planned inference rule. Keep qualifying borderline evidence under conclusion_class support, but require clearly weak aligned evidence to be inconclusive.

Return one task_pair_records entry for path_id {path_id}. Under task1.candidates and task2.candidates, include exactly one entry for each task in {json.dumps(review_task_ids)} and an empty candidates list for any retained high-quality task. Copy each reviewed candidate_id exactly from plan.tasks. Judge Task1 and Task2 independently. The task-pair assessment is high-quality only if both active candidates are high-quality after this review.

Use this required output structure:
=== START OF JSON OUTPUT ===
{json.dumps(prune_out_template, indent=2)}
=== END OF JSON OUTPUT ===

Output a valid JSON object only. Do not wrap it in markdown or add commentary.

Current Study Path: "{study_path}"

Every response must use one of these formats:
Thought: [short reasoning]
Action: [next action]
PAUSE

or, when finished:

Thought: [short reasoning]
Answer: [final JSON object]
""".strip()

    if show_prompt:
        logger.info("\n\n===== Pruning Agent Input (truncated) =====\n" + instruction[:2000])
    print(f"\n\nmodel name for pruning agent: {model_name}\n\n")

    final_answer = run_react_loop(
        system_prompt,
        known_actions,
        get_prune_tool_definitions(),
        instruction,
        session_state={"analyzers": {}},
        study_path=study_path,
        stage_name="robustness-prune",
        checkpoint_map=CHECKPOINT_MAP,
        model_name=model_name,
        logger=logger,
        code_mode=code_mode,
    )
    if not isinstance(final_answer, dict) or not isinstance(
        final_answer.get("pruning_output"), dict
    ):
        error = final_answer.get("error") if isinstance(final_answer, dict) else None
        if error:
            logger.error("[prune] agent output could not be parsed: %s", error)
        return {
            "prune_output": final_answer,
            "universal_output": universal_input,
            "memory_updated": False,
            "pipeline_outcome": "invalid_pruning_output",
            "execution_output": None,
        }

    decisions = extract_pruning_decisions(final_answer, universal_input)
    updated_universal = apply_pruning_decisions(universal_input, decisions)
    audit_update = build_prune_audit_update(
        universal_input,
        decisions,
        iteration=iteration,
    )

    prune_out_path = Path(study_path) / "prune_out_schema.json"
    current_audit = None
    if prune_out_path.exists():
        current_audit = json.loads(prune_out_path.read_text(encoding="utf-8"))
    accumulated_audit = accumulate_prune_output(current_audit, audit_update)
    save_output(accumulated_audit, study_path, "prune_out_schema.json", "prune")
    save_output(updated_universal, study_path, "universal_schema.json", "prune-handoff")

    memory_record = build_memory_record_from_prune_output(
        universal_input,
        final_answer,
        iteration=iteration,
    )
    memory_updated = write_memory_update_with_confirmation(
        memory_path,
        shared_memory,
        memory_record,
    )
    if not memory_updated:
        logger.info("[prune] shared-memory update declined; stopping pipeline")
        return {
            "prune_output": accumulated_audit,
            "universal_output": updated_universal,
            "memory_updated": False,
            "pipeline_outcome": "memory_update_declined",
            "execution_output": None,
        }

    active_statuses = get_task_statuses(updated_universal)
    both_high_quality = all(status == "high-quality" for status in active_statuses.values())
    execution_output = None
    if run_execution and both_high_quality:
        logger.info("[prune->execute] both active candidates are high-quality; starting execution")
        print("\nboth active candidates passed pruning; starting execution\n")
        from robustness.executor.execute_agent import run_execute

        execution_output = run_execute(
            study_path=study_path,
            show_prompt=show_prompt,
            templates_dir=templates_dir,
            tier=tier,
            code_mode=code_mode,
            model_name=model_name,
        )
    elif run_execution:
        logger.info("[prune->execute] execution skipped because active statuses are %s", active_statuses)

    return {
        "prune_output": accumulated_audit,
        "universal_output": updated_universal,
        "memory_updated": True,
        "pipeline_outcome": "ready_for_execution" if both_high_quality else "return_to_planning",
        "execution_output": execution_output,
    }
