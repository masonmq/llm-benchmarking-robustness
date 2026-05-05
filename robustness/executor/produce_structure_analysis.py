import os
import json
import re
from core.constants import GEN_GOLD_ANALYSIS_CONSTANTS
import sys

from info_extractor.file_utils import read_json # Keep save_output here if the agent orchestrates saving
from core.prompts import PREAMBLE, EXAMPLE, GENERATE_GOLD_ANALYSIS, ROBUSTNESS_DESIGN_CODE_MODE_POLICY
from core.agent import Agent, run_react_loop, save_output
from core.utils import build_file_description, configure_file_logging, get_logger
from core.actions import base_known_actions, get_tool_definitions, read_file

logger, formatter = get_logger(name="robustness")
action_re = re.compile(r'^Action: (\w+): (.*)$', re.MULTILINE) # Use re.MULTILINE for multiline parsing
known_actions = base_known_actions()

def build_system_prompt(code_mode: str) -> str:
    # Put the policy in SYSTEM prompt
    return "\n\n".join([PREAMBLE, GENERATE_GOLD_ANALYSIS, EXAMPLE])

def run_gen_gold_analysis(study_path, tier: str = "easy", code_mode: str = "python", model_name: str = "gpt-5"):
    configure_file_logging(logger, study_path, f"gen_gold_analysis.log")
    # Load json template
    logger.info(f"Starting gold analysis extraction for study path: {study_path}")
    analysis_schema =  read_file(GEN_GOLD_ANALYSIS_CONSTANTS['analysis_schema'])
    code_policy = ROBUSTNESS_DESIGN_CODE_MODE_POLICY.get(code_mode, ROBUSTNESS_DESIGN_CODE_MODE_POLICY["python"])
    
    system_prompt = build_system_prompt(code_mode)
    
    question = f"""
You are a researcher specialized in research reproduction and validation in the social sciences.
You will be given the following information:
1. original_paper.pdf: A published paper in the social and behaviorial sciences domain.
2. initial_details.txt: A focal claim made in the original_paper.pdf whose validity is being tested.
3. proposed_analysis.pdf: A proposed analysis, from an independent researcher different from the original authors of original_paper.pdf, to validate the claim in initial_details.txt. This analysis can have DIFFERENT design choices from those in the original paper, but can still validate the focal claim.
4. data/: This folder contains original data file used in original_paper.pdf AND possibly a code file based on the proposed_analysis.pdf


Your task is to extract relevant information about proposed analysis and fill out this template:
=== START OF JSON OUTPUT===
{analysis_schema}
=== END OF JSON OUTPUT ===

You can use any tools and inspect any documents available to you to help you accomplish the task, if need be. 

{code_policy}

Output Requirements:\n- Return a valid JSON object only.\n- Do NOT wrap the output in markdown (no ```json).\n- Do NOT include extra text, commentary, or notes.\n\n Ensure accuracy and completeness.\n- Strictly use provided sources as specified.
""".strip()
    print(f"starting design phase with {model_name}\n")
    tool_definitions = get_tool_definitions()
    return run_react_loop(
    	system_prompt,
    	known_actions,
    	tool_definitions,
    	question,
    	session_state={"analyzers": {}},
    	study_path=study_path,
        stage_name="execute-gen_gold_analysis",
    	on_final=lambda ans: save_output(ans, study_path, "analysis_info.json", "execute-gen_gold_analysis"),
    	model_name=model_name
    )