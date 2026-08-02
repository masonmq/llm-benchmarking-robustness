"""
LLM_Benchmarking__
|
constants.py
Created on Mon Jun  9 15:36:52 2025
@authors: Rochana Obadage, Bang Nguyen
"""

import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")

# Run configuration:
# - "native": run original-language code (R/.do/etc.), no Python translation
# - "python": translate all non-Python scripts to Python and run Python
CODE_MODE_CHOICES = ["native", "python"]
DEFAULT_CODE_MODE = os.getenv("CODE_MODE", "python")

TEMPLATE_PATHS = {
    "post_registration_template": "templates/post_registration_schema.json",
    "pre_registration_template": "templates/pre_registration_schema.json",
    "info_extractor_instructions": "templates/info_extractor_instructions.json",
    "extract_eval_prompt_template": "templates/prompts/extract_eval.txt",
    "generate_design_eval_prompt_template": "templates/prompts/generate_design_eval.txt"
}


FILE_SELECTION_RULES = {
    "info_extractor": {
        "easy": {
            "stage_1": {
                "files": ["initial_details_easy.txt", "original_paper.pdf"],
                "folders": {
                    "original_data": {},
                    "original_code": {}
                }
            },
            "stage_2": {
                "files": ["initial_details_easy.txt", "post_registration.json"],
                "folders": {
                    "data": {},
                    "replication_data": {},
                    "replication_code": {},
                    "execution_outputs": {}
                }
            }
        },
        "medium": {
            "stage_1": {
                "files": ["initial_details_medium_hard.txt", "original_paper.pdf"],
                "folders": {
                    "original_data": {},
                    "original_code": {}
                }
            },
            "stage_2": {
                "files": ["initial_details_easy.txt", "post_registration.json"],
                "folders": {
                    "data": {},
                    "replication_data": {},
                    "replication_code": {},
                    "execution_outputs": {}
                }
            }
        },
        "hard": {
            "stage_1": {
                "files": ["initial_details_medium_hard.txt", "original_paper.pdf"],
                "folders": {
                    "original_data": {},
                    "original_code": {}
                }
            },
            "stage_2": {
                "files": ["initial_details_easy.txt", "post_registration.json"],
                "folders": {
                    "data": {},
                    "replication_data": {},
                    "replication_code": {},
                    "execution_outputs": {}
                }
            }
        }
    }
}


GENERATE_REACT_CONSTANTS = {
    "files": {
        "original_paper.pdf": "The pdf file containing the full text of the original paper",
        "initial_details.txt": "Details about the claim from the original paper to be replicated",
        "post_registration.json": "A structured document with key extracted information about the original paper and the claim to be replicated.",
        "replication_data": "The folder containing the data that can potentially be used for the replication. There may also be useful code to help you with the replication. But if not, you have to generate the replication code yourself in Python.",
    },
    "json_template_python": "templates/pre_registration_schema_python.json",
    "json_template_native": "templates/pre_registration_schema_native.json"
}

GENERATE_EXECUTE_REACT_CONSTANTS = {
    "files": {
        "original_paper.pdf": "The pdf file containing the full text of the original paper",
        "initial_details.txt": "Details about the claim from the original paper to be replicated",
        "post_registration.json": "A structured document with key extracted information about the original paper and the claim to be replicated.",
        "replication_preregistration.json": "A structured document with plans for your replication of the claim.",
        "replication_data_code": "The folder containing the data and code that can be used for the replication.",
    },
    "json_template": "templates/execute_schema.json"
}

EVALUATE_GENERATE_EXECUTE_CONSTANTS = {
    "prompt_template": "templates/prompts/execute_eval.txt",
    "claim_files": {
        # "input/original_paper.pdf": "The pdf file containing the full text of the original paper",
        "input/initial_details.txt": "Details about the claim from the original paper to be replicated",
        "input/replication_data": "The folder containing the data and code that the agent used and generated during the execution process.",
    },
    "agent_files": {
        "input/post_registration.json": "A structured document with key extracted information about the original paper and the claim to be replicated.",
        "input/replication_info.json": "Structured report of the design stage (where agent plans for the replication) by the agent.",
        "input/execution_results.json": "Structured report of the execution stage (happening after design stage where agent runs and debugs code) by the agent.",
        "input/_log/": "Folder contain the logs of the agent replication attempt. Focus on the log files of the design and the execute stage for this evaluation.",
    },
    "json_template": "templates/evaluate_execute_schema.json"
}


INTERPRET_CONSTANTS = {
    "prompt_template": "templates/prompts/interpret.txt",
    "claim_files": {
        "original_paper.pdf": "The pdf file containing the full text of the original paper",
        "initial_details.txt": "Details about the claim from the original paper to be replicated",
    },
    "agent_files": {
        "post_registration.json": "A structured document with key extracted information about the original paper and the claim to be replicated.",
        "replication_info.json": "Structured report of the agent at the PLANNING stage for the replication of the given claim.",
        "replication_data": "The folder containing the data and code that were used for the replication, along with any output files generated after running the code. You MUST examine any additional execution result files not reported in execution_results.json before making your interpretataions.",
        "execution_results.json": "Final structured report of the execution stage by the agent. If the report doesn't have any results, look for output files generated by the code to find the execution results before making conclusions.",
    },
    "json_template": "templates/interpret_schema.json"
}

EVALUATE_INTERPRET_CONSTANTS = {
    "prompt_template": "templates/prompts/interpret_eval.txt",
    "interpret_results": "input/interpret_results.json",
    "json_template": "templates/interpret_schema.json"
}

### ROBUSTNESS CONSTANTS

GEN_GOLD_ANALYSIS_CONSTANTS = {
    "analysis_schema": "templates/execute_in_schema.json",
}

PLAN_ANALYSIS_CONSTANTS = {
    # The Planning Agent now emits the universal schema. The same document is the
    # Pruning Agent's input (prune_in), so the two agents share one contract.
    "analysis_schema": "templates/universal_schema.json",
    "task_description_data": "data/_robustness/all_claims.xlsx",
    "example_paper": "data/_robustness/plan_few_shots/Bartels_JournConsRes_2015_mrZ.pdf",
    "example_good_analysis": "data/_robustness/plan_few_shots/Bartels_JournConsRes_2015_mrZ_50PCE.pdf",
    "example_bad_analysis": "data/_robustness/plan_few_shots/Bartels_JournConsRes_2015_mrZ_0HC9H.pdf"
}


ROBUSTNESS_EXECUTE_CONSTANTS = {
    "files": {
        "original_paper.pdf": "The pdf file containing the full text of the original paper",
        "execute_in_schema.json": "A structured document with plans for proposed analysis of the claim.",
        "data": "The folder containing the data and code that can be used for the replication.",
    },
    "json_template": "templates/execute_out_schema.json"    
}

# Pruning Agent helper extractor: paper PDF + proposed-analysis (review) PDF + data
# are extracted into a filled prune_in_schema.json (the Pruning Agent's input).
GEN_PRUNE_INPUT_CONSTANTS = {
    "prune_in_template": "templates/prune_in_schema.json",
}

# Pruning Agent: reviews the filled prune_in_schema.json and routes
# high-quality/low-quality, emitting prune_out_schema.json.
ROBUSTNESS_PRUNE_CONSTANTS = {
    "files": {
        "prune_in_schema.json": "The structured Pruning Agent input: case reference, the single candidate analysis path to review (planning_output), shared memory, and the fixed pruning rules.",
    },
    "json_template": "templates/prune_out_schema.json",
}

# Prompt versions are logged on every run for reproducibility.
GEN_PRUNE_INPUT_PROMPT_VERSION = "prune_input_extractor.v1"
PRUNE_PROMPT_VERSION = "pruning_agent.v2"


# ---------------------------------------------------------------------------
# Fixed per-agent role rules.
#
# These are NOT agent-generated content: they define what each agent in the
# pipeline is allowed and not allowed to do, and they must stay identical across
# every run and every case. They therefore live here as constants instead of in
# the universal schema (an agent must never be able to author its own rules).
# ---------------------------------------------------------------------------

PLANNING_RULES = {
    "allowed_actions": [
        "Read the original paper.",
        "Inspect the original dataset metadata.",
        "Inspect original paper source code if available.",
        "Use shared memory to avoid repeated paths.",
        "Propose exactly one new analysis path.",
    ],
    "not_allowed_actions": [
        "Do not change the focal claim.",
        "Do not change the dataset.",
        "Do not run analysis.",
        "Do not output multiple candidate paths.",
        "Do not propose a path that repeats shared memory.",
    ],
}

PRUNING_RULES = {
    "allowed_actions": [
        "Read the candidate path.",
        "Read the original paper PDF.",
        "Explore the authorized dataset.",
        "Read the candidate path's analysis code.",
        "Read shared memory.",
        "Decide whether the candidate path is high-quality or low-quality.",
        "Write a memory update instruction.",
    ],
    "not_allowed_actions": [
        "Do not modify the proposed path.",
        "Do not run analysis.",
        "Do not change the focal claim.",
        "Do not change the dataset.",
        "Do not create a new analysis path.",
        "Do not read the human analysis or review PDF, or any expected or ground-truth result.",
    ],
}

EXECUTION_RULES = {
    "allowed_actions": [
        "Inspect data files.",
        "Inspect code files.",
        "Run provided code.",
        "Make bounded implementation fixes.",
        "Write compact result-extraction scripts.",
    ],
    "not_allowed_actions": [
        "Do not change the focal claim.",
        "Do not change the dataset.",
        "Do not replace the planned path with a different analysis path.",
        "Do not choose a more favorable result.",
    ],
}

# Convenience lookup keyed the same way the schema used to key them.
AGENT_RULES = {
    "planning_rules": PLANNING_RULES,
    "pruning_rules": PRUNING_RULES,
    "execution_rules": EXECUTION_RULES,
}
