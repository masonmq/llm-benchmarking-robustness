import os
import json
import re
from core.constants import PLAN_ANALYSIS_CONSTANTS
import sys

from replicatorbench.info_extractor.file_utils import read_json # Keep save_output here if the agent orchestrates saving
from core.prompts import PREAMBLE_ROBUSTNESS, EXAMPLE_ROBUSTNESS, GENERATE_GOLD_ANALYSIS, ROBUSTNESS_DESIGN_CODE_MODE_POLICY, ROBUSTNESS_PLAN_POLICY
from core.agent import Agent, run_react_loop, save_output
from core.utils import build_file_description, configure_file_logging, get_logger
from core.actions import base_known_actions, get_tool_definitions, read_file, read_pdf
import pandas as pd
from pathlib import Path
from robustness.memory.shared_memory import load_case_memory

logger, formatter = get_logger(name="robustness")
action_re = re.compile(r'^Action: (\w+): (.*)$', re.MULTILINE) # Use re.MULTILINE for multiline parsing
known_actions = base_known_actions()

def build_system_prompt(code_mode: str) -> str:
    # Put the policy in SYSTEM prompt
    return "\n\n".join([PREAMBLE_ROBUSTNESS, GENERATE_GOLD_ANALYSIS, EXAMPLE_ROBUSTNESS])

def run_plan_analysis(study_path, tier: str = "easy", code_mode: str = "python", model_name: str = "gpt-5", paper_id: str = ""):
    configure_file_logging(logger, study_path, f"gen_gold_analysis.log")
    # Load json template
    logger.info(f"Starting gold analysis extraction for study path: {study_path}")
    analysis_schema =  read_file(PLAN_ANALYSIS_CONSTANTS['analysis_schema'])
    task_description_data =  pd.read_excel(PLAN_ANALYSIS_CONSTANTS['task_description_data'])
    
    example_paper =  read_pdf(PLAN_ANALYSIS_CONSTANTS['example_paper'])
    example_good_analysis =  read_pdf(PLAN_ANALYSIS_CONSTANTS['example_good_analysis'])
    example_bad_analysis =  read_pdf(PLAN_ANALYSIS_CONSTANTS['example_bad_analysis'])
    try:
        focal_claim = task_description_data.loc[(task_description_data['paper_id'].str.lower() == paper_id.lower() ), 'the claim /the re-analysts saw/'].iloc[0]
        task_2_desc = task_description_data.loc[(task_description_data['paper_id'].str.lower() == paper_id.lower() ), 'instructions_for_task_2'].iloc[0]
        task_1_desc = """In Task 1, the analyst was asked to conduct the analysis without any restrictions."""
    except:
        return "cannot find claim and task descriptions related to the provided study path."

    shared_memory, memory_path = load_case_memory(paper_id)
    logger.info(f"[memory] loaded shared memory for planning: {memory_path}")
    
    code_policy = ROBUSTNESS_DESIGN_CODE_MODE_POLICY.get(code_mode, ROBUSTNESS_DESIGN_CODE_MODE_POLICY["native"])
    plan_input_rules = ROBUSTNESS_PLAN_POLICY.get("input", "")

    system_prompt = build_system_prompt(code_mode)
    
    question = f"""
You are a researcher specialized in analytical robustness evaluation in the social and behavioral sciences.
In other words, given a research paper and a focal claim from the paper, your tasks is to conduct statistical analyses to validate the robustness of the claim.
HERE IS AN EXAMPLE OF THE TYPE OF ANALYSES THAT YOU SHOULD CONDUCT AND SHOULD AVOID

## Given the following EXAMPLE PAPER: 
{example_paper}

### The following is an example of a high-quality analysis to validate the focal claim made by the paper.
{example_good_analysis}

### The following is an example of a low-quality analysis to validate the focal claim made by the paper.
{example_bad_analysis}

Based on the above examples on how other researchers conduct robustness analyses, you will be given another paper and claim to conduct robustness analyses:
=== === === === === MAIN SESSION === === === === 
Your task is to plan analysis tasks to help investigate the robustness of the following research claim.
== START OF FOCAL CLAIM ==
{focal_claim}
== END OF FOCAL CLAIM ==
1. original_paper.pdf: A published paper containing the focal claim.
2. data/: This folder contains the original data used by the paper.
3. shared_memory: Read-only path history for this case. Use it to avoid generating a duplicate path. Do not update it.

== START OF SHARED MEMORY (READ ONLY) ==
{json.dumps(shared_memory, indent=2)}
== END OF SHARED MEMORY ==




BELOW IS THE CLAIM WHERE YOU WILL BE DOING YOUR ANALYSIS:

You can choose to deviate from the methodology reported in the original paper if you believe there is a more/similarly justifiable alternative to test the same claim. If the original methodlog has some ambiguous design choice, you can make the choice based on your own educated judgment.
Additionally, you must adhere to constraints provided for each task described below.
== TASK 1 CONSTRAINT ==
{task_1_desc}
== END OF TASK 1 CONSTRAINT ==

== TASK 2 CONSTRAINT ==
{task_2_desc}
== END OF TASK 2 CONSTRAINT ==

Other rules:
{plan_input_rules}

Shared-memory rules:
- Treat every memory_records item as a previous path, regardless of status.
- Compare your proposed path against path_summary, path_signature, and task_signatures when present.
- Your proposed path must be meaningfully different in model family, variables, sample restriction, variable construction, inference rule, or another analytically important choice.
- Do not write, modify, or request updates to shared memory. The Planning Agent only reads it.
- In your final self_check, explain why the new path is not a duplicate and name the closest_memory_path_id if any previous path is similar.

Your final goal is to fill out this template:
=== START OF JSON OUTPUT===
{analysis_schema}
=== END OF JSON OUTPUT ===

You can use any tools and inspect any documents available to you to help you accomplish the task, if need be.

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
        stage_name="plan-analysis",
    	on_final=lambda ans: save_output(ans, study_path, "analysis_info.json", "plan-analysis"),
    	model_name=model_name,
        logger=logger
    )
