import json
from pathlib import Path

import pandas as pd

from core.actions import base_known_actions, get_tool_definitions, read_file, read_pdf
from core.agent import run_react_loop, save_output
from core.constants import (
    CONCLUSION_CLASSIFICATION_RULES,
    PLAN_ANALYSIS_CONSTANTS,
    PLANNING_RULES,
)
from core.prompts import (
    PREAMBLE_PLAN,
    ROBUSTNESS_DESIGN_CODE_MODE_POLICY,
    ROBUSTNESS_PLAN_POLICY,
)
from core.utils import configure_file_logging, get_logger
from robustness.memory.shared_memory import (
    candidate_artifact_dir,
    get_path_id,
    get_task_statuses,
    load_case_memory,
    missing_analysis_code_files,
    next_candidate_id,
    next_path_id,
    normalize_planning_output,
    route_after_pruning,
)


logger, formatter = get_logger(name="robustness")
known_actions = base_known_actions()


def build_system_prompt(_code_mode: str) -> str:
    return PREAMBLE_PLAN


def run_plan_analysis(
    study_path,
    tier: str = "easy",
    code_mode: str = "python",
    model_name: str = "gpt-5",
    paper_id: str = "",
    templates_dir: str = "./templates",
    show_prompt: bool = False,
    run_pruning: bool = True,
    run_execution: bool = False,
    max_planning_pruning_loops: int = 5,
):
    if run_execution and not run_pruning:
        raise ValueError("run_execution=True requires run_pruning=True.")
    if max_planning_pruning_loops < 1:
        raise ValueError("max_planning_pruning_loops must be a positive integer.")

    configure_file_logging(logger, study_path, "gen_gold_analysis.log")
    logger.info(f"Starting analysis planning for study path: {study_path}")
    analysis_schema = read_file(PLAN_ANALYSIS_CONSTANTS["analysis_schema"])
    task_description_data = pd.read_excel(PLAN_ANALYSIS_CONSTANTS["task_description_data"])
    example_paper = read_pdf(PLAN_ANALYSIS_CONSTANTS["example_paper"])
    example_good_analysis = read_pdf(PLAN_ANALYSIS_CONSTANTS["example_good_analysis"])
    example_bad_analysis = read_pdf(PLAN_ANALYSIS_CONSTANTS["example_bad_analysis"])

    matching_rows = task_description_data[
        task_description_data["paper_id"].str.lower() == paper_id.lower()
    ]
    if matching_rows.empty:
        return "cannot find claim and task descriptions related to the provided study path."
    focal_claim = matching_rows["the claim /the re-analysts saw/"].iloc[0]
    task_1_desc = "In Task 1, the analyst was asked to conduct the analysis without any restrictions."
    task_2_desc = matching_rows["instructions_for_task_2"].iloc[0]

    system_prompt = build_system_prompt(code_mode)
    code_policy = ROBUSTNESS_DESIGN_CODE_MODE_POLICY.get(
        code_mode,
        ROBUSTNESS_DESIGN_CODE_MODE_POLICY["native"],
    )
    plan_input_rules = ROBUSTNESS_PLAN_POLICY.get("input", "")
    current_schema = None
    latest_prune_output = None

    for planning_pruning_loop in range(1, max_planning_pruning_loops + 1):
        shared_memory, memory_path = load_case_memory(paper_id, study_path)
        logger.info(
            "[memory] loaded shared memory for planning loop %s: %s",
            planning_pruning_loop,
            memory_path,
        )

        expected_path_id, expected_candidates, tasks_to_generate = _expected_planning_ids(
            paper_id,
            shared_memory,
            current_schema,
        )
        question = _build_planning_question(
            focal_claim=focal_claim,
            task_1_desc=task_1_desc,
            task_2_desc=task_2_desc,
            example_paper=example_paper,
            example_good_analysis=example_good_analysis,
            example_bad_analysis=example_bad_analysis,
            shared_memory=shared_memory,
            current_schema=current_schema,
            planning_pruning_loop=planning_pruning_loop,
            expected_path_id=expected_path_id,
            expected_candidates=expected_candidates,
            tasks_to_generate=tasks_to_generate,
            code_policy=code_policy,
            plan_input_rules=plan_input_rules,
            analysis_schema=analysis_schema,
            study_path=study_path,
        )

        if show_prompt:
            logger.info("\n\n===== Planning Agent Input (truncated) =====\n" + question[:2000])
        print(f"starting planning loop {planning_pruning_loop} with {model_name}\n")
        raw_plan_output = run_react_loop(
            system_prompt,
            known_actions,
            get_tool_definitions(),
            question,
            session_state={"analyzers": {}},
            study_path=study_path,
            stage_name="plan-analysis",
            model_name=model_name,
            logger=logger,
        )
        if not isinstance(raw_plan_output, dict):
            return {
                "plan_output": raw_plan_output,
                "prune_output": latest_prune_output,
                "execution_output": None,
                "pipeline_outcome": "invalid_planning_output",
                "planning_pruning_loops": planning_pruning_loop,
            }

        plan_output = normalize_planning_output(
            raw_plan_output,
            case_id=paper_id,
            memory_data=shared_memory,
            iteration=planning_pruning_loop,
            previous_schema=current_schema,
            study_path=study_path,
        )
        missing_code_files = missing_analysis_code_files(plan_output, study_path)
        planning_attempt = 1
        while missing_code_files and planning_attempt < max_planning_pruning_loops:
            planning_attempt += 1
            logger.info(
                "[plan] code generation attempt %s of %s for %s missing file(s)",
                planning_attempt,
                max_planning_pruning_loops,
                len(missing_code_files),
            )
            run_react_loop(
                system_prompt,
                known_actions,
                get_tool_definitions(),
                _build_code_completion_question(
                    study_path=study_path,
                    plan_output=plan_output,
                    missing_code_files=missing_code_files,
                    planning_attempt=planning_attempt,
                    max_planning_attempts=max_planning_pruning_loops,
                ),
                session_state={"analyzers": {}},
                study_path=study_path,
                stage_name="plan-code-completion",
                model_name=model_name,
                logger=logger,
            )
            missing_code_files = missing_analysis_code_files(plan_output, study_path)

        save_output(plan_output, study_path, "universal_schema.json", "plan-analysis")

        if missing_code_files:
            logger.error(
                "[plan] code generation attempt limit reached with missing files: %s",
                missing_code_files,
            )
            return {
                "plan_output": plan_output,
                "prune_output": latest_prune_output,
                "execution_output": None,
                "pipeline_outcome": "planning_code_attempt_limit_reached",
                "planning_pruning_loops": planning_pruning_loop,
                "planning_attempts": planning_attempt,
                "missing_code_files": missing_code_files,
            }

        if not run_pruning:
            return {
                "plan_output": plan_output,
                "prune_output": None,
                "execution_output": None,
                "pipeline_outcome": "planning_complete",
                "planning_pruning_loops": planning_pruning_loop,
            }

        logger.info("[plan->prune] handing active candidates to the Pruning Agent")
        print("\nplanning complete; starting pruning review\n")
        from robustness.pruning.prune_agent import run_prune

        prune_result = run_prune(
            study_path=study_path,
            show_prompt=show_prompt,
            templates_dir=templates_dir,
            tier=tier,
            code_mode=code_mode,
            model_name=model_name,
            plan_output=plan_output,
            run_execution=False,
        )
        latest_prune_output = prune_result.get("prune_output")
        current_schema = prune_result.get("universal_output")
        if not prune_result.get("memory_updated"):
            return {
                "plan_output": current_schema or plan_output,
                "prune_output": latest_prune_output,
                "execution_output": None,
                "pipeline_outcome": prune_result.get("pipeline_outcome", "pruning_stopped"),
                "planning_pruning_loops": planning_pruning_loop,
            }

        route = route_after_pruning(
            current_schema,
            completed_loops=planning_pruning_loop,
            max_planning_pruning_loops=max_planning_pruning_loops,
        )
        if route == "planning":
            logger.info(
                "[prune->plan] active statuses %s; returning low-quality tasks to Planning",
                get_task_statuses(current_schema),
            )
            continue

        if route == "planning_pruning_limit_reached":
            logger.info("[pipeline] maximum Planning-Pruning loop count reached")
            return {
                "plan_output": current_schema,
                "prune_output": latest_prune_output,
                "execution_output": None,
                "pipeline_outcome": route,
                "planning_pruning_loops": planning_pruning_loop,
                "active_statuses": get_task_statuses(current_schema),
            }

        if not run_execution:
            return {
                "plan_output": current_schema,
                "prune_output": latest_prune_output,
                "execution_output": None,
                "pipeline_outcome": "ready_for_execution",
                "planning_pruning_loops": planning_pruning_loop,
            }

        logger.info("[prune->execute] both active candidates are high-quality")
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
        return {
            "plan_output": current_schema,
            "prune_output": latest_prune_output,
            "execution_output": execution_output,
            "pipeline_outcome": execution_output.get("pipeline_outcome", "execution_complete"),
            "planning_pruning_loops": planning_pruning_loop,
        }

    raise RuntimeError("Planning-Pruning loop ended without a route.")


def _expected_planning_ids(case_id, shared_memory, current_schema):
    if current_schema is None:
        return (
            next_path_id(case_id, shared_memory),
            {"Task1": "Task1_candidate01", "Task2": "Task2_candidate01"},
            ["Task1", "Task2"],
        )

    path_id = get_path_id(current_schema)
    statuses = get_task_statuses(current_schema)
    tasks = {task["task_id"]: task for task in current_schema["plan"]["tasks"]}
    expected_candidates = {}
    tasks_to_generate = []
    for task_id, status in statuses.items():
        if status == "high-quality":
            expected_candidates[task_id] = tasks[task_id]["candidate_id"]
        elif status == "low-quality":
            expected_candidates[task_id] = next_candidate_id(shared_memory, path_id, task_id)
            tasks_to_generate.append(task_id)
        else:
            raise ValueError(f"Planning received {task_id} with status {status!r}.")
    return path_id, expected_candidates, tasks_to_generate


def _build_planning_question(**context):
    current_schema = context["current_schema"]
    if current_schema is None:
        round_instructions = """
This is the initial Planning round. Reconstruct one analysis anchor for each task before generating one Task1 candidate and one Task2 candidate. Both candidate statuses must be null.
""".strip()
        current_document = "No prior universal schema exists for this path lineage."
    else:
        statuses = get_task_statuses(current_schema)
        round_instructions = f"""
This path is returning from Pruning with active statuses {json.dumps(statuses)}.
Regenerate only the tasks listed in tasks_to_generate. Copy every high-quality task and its analysis anchor from the current universal schema unchanged, including its candidate_id, status, analysis_path, analysis_code, and notes. Preserve a low-quality task's anchor unless the Pruning evidence identifies the anchor itself as unsupported or incomplete; when correcting it, cite the paper and dataset evidence. A regenerated candidate must have status null.
""".strip()
        current_document = json.dumps(current_schema, indent=2)

    artifact_directories = {
        task_id: candidate_artifact_dir(
            context["expected_path_id"],
            task_id,
            context["expected_candidates"][task_id],
        )
        for task_id in context["tasks_to_generate"]
    }
    artifact_write_directories = {
        task_id: str((Path(context["study_path"]).resolve() / artifact_dir).resolve())
        for task_id, artifact_dir in artifact_directories.items()
    }

    return f"""
You are the Planning Agent for an analytical robustness study. Plan Task1 and Task2 for the focal claim without running the analysis.

Before proposing a method, read the relevant parts of original_paper.pdf and inspect every authorized dataset's shape, columns, and focal-variable summaries. Use that evidence to identify the estimand and available variables. After writing each task's code, read it back and complete the plan-code preflight. Do not return the universal schema before these steps are complete.

Here is an example paper:
{context['example_paper']}

Here is an example of a high-quality analysis:
{context['example_good_analysis']}

Here is an example of a low-quality analysis:
{context['example_bad_analysis']}

Focal claim:
{context['focal_claim']}

Task1 instruction:
{context['task_1_desc']}

Task2 instruction:
{context['task_2_desc']}

Planning-Pruning loop: {context['planning_pruning_loop']}
Required path_id: {context['expected_path_id']}
Required active candidate IDs: {json.dumps(context['expected_candidates'])}
tasks_to_generate: {json.dumps(context['tasks_to_generate'])}
Required candidate artifact directories for universal_schema.json: {json.dumps(artifact_directories)}
Absolute candidate artifact directories for write_file: {json.dumps(artifact_write_directories)}

{round_instructions}

=== CURRENT UNIVERSAL SCHEMA ===
{current_document}
=== END CURRENT UNIVERSAL SCHEMA ===

Shared Memory is read-only. It contains every earlier planned candidate and any executor-fixed path for this case. Compare each new proposal against all candidates for the same task and do not repeat an earlier analytical path.

=== SHARED MEMORY (READ ONLY) ===
{json.dumps(context['shared_memory'], indent=2)}
=== END SHARED MEMORY ===

Current study directory: {Path(context['study_path']).resolve()}
Use original_paper.pdf and only the authorized files under data/. For each task in tasks_to_generate, pass an absolute target path under its required directory to write_file. In universal_schema.json, use the matching study-relative paths in analysis_code.artifact_dir, code_files, entry_file, and run_command. Do not inspect or reuse code from other candidate artifact directories or loose analysis scripts from earlier runs; Shared Memory is the source for prior-path comparison. Do not change the focal claim, task instructions, or dataset. Do not write or request a Shared Memory update.

For each generated task, use its analysis anchor as the starting specification and complete every anchor_alignment dimension. If Shared Memory already contains that path, change the fewest dimensions needed to produce a substantively distinct robustness analysis and preserve all other anchor choices. Record every changed dimension under deviations. Also identify the exact estimand and its claim mapping; cite authorized evidence for every focal variable, control, restriction, transformation, and cutoff; preserve the focal variable structure unless a collapse is justified; require the code to report sample attrition; set code_reports_sample_flow to the JSON Boolean true only when the code reports the starting rows, rows removed by each material rule, and final analytic rows; and verify that every referenced column exists and the code matches the declared analysis. Do not use expected results or anticipated support when choosing a method.

Code policy:
{context['code_policy']}

Other planning rules:
{context['plan_input_rules']}

Fixed Planning Agent rules:
{json.dumps(PLANNING_RULES, indent=2)}

Fixed conclusion classification rules:
{json.dumps(CONCLUSION_CLASSIFICATION_RULES, indent=2)}

For every generated task, apply these conclusion rules in analysis_anchors.conclusion_rule, plan.path_signature.inference_rule, analysis_path.key_choices.inference_rule, and each model's inference_criteria. Use the focal claim's expected direction or result pattern rather than assuming that support always means a positive coefficient. Keep borderline support under conclusion_class support and classify clearly weak aligned evidence as inconclusive.

Return the complete universal schema, including both active tasks. Use this template:
=== START OF JSON OUTPUT ===
{context['analysis_schema']}
=== END OF JSON OUTPUT ===

Return a valid JSON object only, with no markdown or commentary.
""".strip()


def _build_code_completion_question(
    *,
    study_path,
    plan_output,
    missing_code_files,
    planning_attempt,
    max_planning_attempts,
):
    study_dir = Path(study_path).resolve()
    target_paths = []
    for file_path in missing_code_files:
        target = (study_dir / file_path).resolve()
        try:
            target.relative_to(study_dir)
        except ValueError:
            continue
        target_paths.append(str(target))

    return f"""
The analytical plan below is complete, but its declared code files were not created.
Use write_file to create every missing file at the exact target paths listed below. Implement the existing Task1 and Task2 analytical paths without changing the methods or filenames. You may inspect original_paper.pdf and the authorized files under data/ when writing the code. After all files exist, return the same JSON plan.

Planning attempt: {planning_attempt} of {max_planning_attempts}

Study directory:
{study_dir}

Missing file targets:
{json.dumps(target_paths, indent=2)}

Existing analytical plan:
{json.dumps(plan_output, indent=2)}
""".strip()
