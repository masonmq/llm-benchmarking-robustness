"""
Pruning Agent helper extractor.

Mirrors robustness/executor/produce_structure_analysis.py (run_gen_gold_analysis):
a ReAct extraction agent that reads the original paper PDF, the proposed-analysis
(review) PDF, and the data folder for a case, and fills out prune_in_schema.json so
the Pruning Agent has a structured candidate path to review.

The Planning Agent is not available yet, so this helper bootstraps its output the
same way the gold-analysis helper bootstrapped the executor's input.
"""
import os

from core.constants import GEN_PRUNE_INPUT_PROMPT_VERSION
from core.prompts import (
    PREAMBLE_ROBUSTNESS,
    EXAMPLE_ROBUSTNESS,
    GENERATE_PRUNE_INPUT,
    PRUNE_INPUT_EXTRACT_POLICY,
    ROBUSTNESS_DESIGN_CODE_MODE_POLICY,
)
from core.agent import run_react_loop, save_output
from core.utils import configure_file_logging, get_logger
from core.actions import base_known_actions, get_tool_definitions, read_file

logger, formatter = get_logger(name="robustness")
known_actions = base_known_actions()


def build_system_prompt(code_mode: str) -> str:
    return "\n\n".join([PREAMBLE_ROBUSTNESS, GENERATE_PRUNE_INPUT, EXAMPLE_ROBUSTNESS])


def run_gen_prune_input(study_path, tier: str = "easy", code_mode: str = "python",
                        model_name: str = "gpt-5", templates_dir: str = "./templates"):
    configure_file_logging(logger, study_path, "gen_prune_input.log")
    logger.info(f"Starting prune-input extraction for study path: {study_path}")
    # Reproducibility: log the model and prompt version used for this run.
    logger.info(
        f"[repro] stage=prune-gen_input model={model_name} prompt_version={GEN_PRUNE_INPUT_PROMPT_VERSION} "
        f"code_mode={code_mode} temperature=0_or_reasoning_default seed=NA(controlled by temperature=0/reasoning model)"
    )

    template_path = os.path.join(templates_dir, "prune_in_schema.json")
    prune_in_template = read_file(template_path)
    code_policy = ROBUSTNESS_DESIGN_CODE_MODE_POLICY.get(
        code_mode, ROBUSTNESS_DESIGN_CODE_MODE_POLICY["native"]
    )
    extract_input_rules = PRUNE_INPUT_EXTRACT_POLICY.get("input", "")

    system_prompt = build_system_prompt(code_mode)

    question = f"""
You are a researcher specialized in analytical robustness evaluation in the social and behavioral sciences.
You will be given the following information:
1. original_paper.pdf: A published paper containing the focal claim.
2. proposed_analysis.pdf: A planned robustness analysis path. This path comes from an independent reanalysis of the same focal claim using the same original data. It may use different reasonable analysis choices from the original paper, but it must still test the same focal claim.
3. data/: This folder contains the original data used for the robustness reanalysis. It may also contain analysis code or supporting files needed to execute the planned analysis.

Your task is to extract relevant information about proposed analysis following the input rules:
{extract_input_rules}

Then fill out this template:
=== START OF JSON OUTPUT===
{prune_in_template}
=== END OF JSON OUTPUT ===

You can use any tools and inspect any documents available to you to help you accomplish the task, if need be.

{code_policy}

Output Requirements:
- Return a valid JSON object only.
- Do NOT wrap the output in markdown (no ```json).
- Do NOT include extra text, commentary, or notes.
- Ensure accuracy and completeness. Strictly use provided sources as specified.

Current Study Path: "{study_path}"
""".strip()

    print(f"starting prune-input extraction with {model_name}\n")
    tool_definitions = get_tool_definitions()
    return run_react_loop(
        system_prompt,
        known_actions,
        tool_definitions,
        question,
        session_state={"analyzers": {}},
        study_path=study_path,
        stage_name="prune-gen_input",
        on_final=lambda ans: save_output(ans, study_path, "prune_in_schema.json", "prune-gen_input"),
        model_name=model_name,
        logger=logger,
    )
