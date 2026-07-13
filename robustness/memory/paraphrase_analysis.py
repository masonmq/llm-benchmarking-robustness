import os
import json
import re
from core.constants import PLAN_ANALYSIS_CONSTANTS
import sys

from replicatorbench.info_extractor.file_utils import read_json # Keep save_output here if the agent orchestrates saving
from core.prompts import PREAMBLE_ROBUSTNESS, EXAMPLE_ROBUSTNESS, GENERATE_GOLD_ANALYSIS, ROBUSTNESS_DESIGN_CODE_MODE_POLICY, ROBUSTNESS_EXTRACT_POLICY
from core.agent import Agent, run_react_loop, save_output
from core.utils import build_file_description, configure_file_logging, get_logger
from core.actions import base_known_actions, get_tool_definitions, read_file, read_pdf
import pandas as pd
from pathlib import Path
logger, formatter = get_logger(name="robustness")
action_re = re.compile(r'^Action: (\w+): (.*)$', re.MULTILINE) # Use re.MULTILINE for multiline parsing
known_actions = base_known_actions()

def build_system_prompt(code_mode: str) -> str:
    # Put the policy in SYSTEM prompt
    return "\n\n".join([PREAMBLE_ROBUSTNESS, GENERATE_GOLD_ANALYSIS, EXAMPLE_ROBUSTNESS])

def run_paraphrase_analysis(study_path, tier: str = "easy", code_mode: str = "python", model_name: str = "gpt-5", paper_id: str = ""):
    configure_file_logging(logger, study_path, f"gen_gold_analysis.log")
    # Load json template
    logger.info(f"Starting gold analysis extraction for study path: {study_path}")
    analysis_schema =  read_file(PLAN_ANALYSIS_CONSTANTS['analysis_schema'])
    task_description_data =  pd.read_excel(PLAN_ANALYSIS_CONSTANTS['task_description_data'])
    

    code_policy = ROBUSTNESS_DESIGN_CODE_MODE_POLICY.get(code_mode, ROBUSTNESS_DESIGN_CODE_MODE_POLICY["native"])
    extract_input_rules = ROBUSTNESS_EXTRACT_POLICY.get("input", "")
    
    system_prompt = build_system_prompt(code_mode)
    
    question = f"""
You are a researcher specialized in analytical robustness evaluation in the social and behavioral sciences.
You will be given the following information:
1. original_paper.pdf: A published paper containing the focal claim.
2. analysis_info.json: A planned robustness analysis path. This path comes from an independent reanalysis of the same focal claim using the same original data. It may use different reasonable analysis choices from the original paper, but it must still test the same focal claim.
3. data/: This folder contains the original data used for the robustness reanalysis. It may also contain analysis code or supporting files needed to execute the planned analysis.

Your task is to paraphrase the given analysis_info.json such that it changes the original wording significantly while preserving the semantics of the original analysis and will yield the same results as the given analysis.
In doing so, you are also expected to paraphrase the associated analysis code so that, despite differences in syntax, naming of variables, etc., it will yield the exact same results as the given analysis code.
DO NOT introduce new OR remove existing statistical tests and OR models from the current analysis. The semantics (variables, model type, preproprocessing choices, tests) of the analysis must be preserved in your paraphrased version.
Remember that you are to paraphrase the reanalysis ("analysis_info.json"), NOT the original methodology in original_paper.pdf.
Any new files created in this session must be written into {study_path+ "/X7q9" }.
Finally, fill out this template for the paraphrased analysis:
=== START OF JSON OUTPUT===
{analysis_schema}
=== END OF JSON OUTPUT ===

IMPORTANT: IN ALL OF YOUR GENERATED OUTPUTS, DO NOT INDICATE OR GIVE AWAY IN ANY FORM THAT THIS IS A REWRITTEN ANALYSIS/PARAPHRASED ANALYIS. TREAT IT AS IF YOU ARE PROPOSING A NEW RE-ANALYSIS.

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
        stage_name="paraphrase-analysis",
    	on_final=lambda ans: save_output(ans, study_path + "/X7q9", "analysis_info.json", "paraphrase-analysis"),
    	model_name=model_name,
        logger=logger
    )