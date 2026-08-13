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
    "analysis_schema": "templates/universal_schema.json",
}

PLAN_ANALYSIS_CONSTANTS = {
    "analysis_schema": "templates/universal_schema.json",
    "task_description_data": "data/_robustness/all_claims.xlsx",
    "example_paper": "data/_robustness/plan_few_shots/Bartels_JournConsRes_2015_mrZ.pdf",
    "example_good_analysis": "data/_robustness/plan_few_shots/Bartels_JournConsRes_2015_mrZ_50PCE.pdf",
    "example_bad_analysis": "data/_robustness/plan_few_shots/Bartels_JournConsRes_2015_mrZ_0HC9H.pdf"
}


ROBUSTNESS_EXECUTE_CONSTANTS = {
    "files": {
        "original_paper.pdf": "The pdf file containing the full text of the original paper",
        "universal_schema.json": "A structured document with plans for proposed analysis of the claim.",
        "data": "The folder containing the data and code that can be used for the replication.",
    },
    "json_template": "templates/universal_schema.json"
}

# Pruning Agent: reviews active candidates in universal_schema.json.
ROBUSTNESS_PRUNE_CONSTANTS = {
    "files": {
        "universal_schema.json": "The active Task1 and Task2 candidates produced by Planning.",
    },
    "json_template": "templates/prune_out_schema.json",
}

# Prompt versions are logged on every run for reproducibility.
PRUNE_PROMPT_VERSION = "pruning_agent.v2"


CONCLUSION_CLASSIFICATION_RULES = {
    "support": (
        "The focal result is in the direction expected by the focal claim and provides affirmative or borderline "
        "evidence. For a frequentist result, p less than or equal to 0.05 is affirmative evidence. A result with "
        "p greater than 0.05 and less than or equal to 0.055 is borderline support only when the estimate is "
        "substantively meaningful and its uncertainty interval only narrowly crosses the null. Borderline support "
        "uses conclusion_class support; do not create another conclusion class."
    ),
    "opposite": (
        "The focal result materially contradicts the direction or substantive relationship in the focal claim "
        "and provides affirmative evidence for that contrary result. An opposite-signed point estimate alone is "
        "not enough. For a frequentist coefficient-based result, require p less than 0.05, a confidence interval "
        "excluding the null in the contrary direction, or another case-appropriate criterion demonstrating "
        "material contrary evidence."
    ),
    "inconclusive": (
        "A valid focal direction cannot be determined, the required focal results are mixed or ambiguous, or an "
        "aligned result lacks affirmative or borderline evidence. For a frequentist result in the expected direction, "
        "p greater than 0.055 is inconclusive unless another case-appropriate criterion supplies affirmative evidence. "
        "An opposite-signed result without affirmative evidence of a material contrary effect is also inconclusive."
    ),
    "statistical_strength": (
        "For a frequentist result in the expected direction, p less than or equal to 0.05 is support. When p is "
        "greater than 0.05 and less than or equal to 0.055, use conclusion_class support only if the estimate is "
        "substantively meaningful and the uncertainty interval narrowly crosses the null, and describe it as "
        "borderline. Clearly weak aligned evidence is inconclusive. Report uncertainty separately. An "
        "opposite-signed estimate that does not meet the affirmative-evidence requirement is inconclusive, not opposite."
    ),
}


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
        "Propose one active candidate for each task that requires Planning.",
        "Reconstruct the paper analysis anchor for each task before proposing a candidate.",
        "Identify the focal estimand before choosing variables or a model.",
        "Keep candidates aligned with the paper analysis anchor or document each justified deviation.",
        "When avoiding a duplicate, change only the minimum analytical dimensions needed.",
        "Verify proposed variables against the authorized data.",
        "Document sample exclusions and require the code to report sample flow.",
        "Justify every restriction, control, transformation, and variable collapse.",
        "Check that the analysis code implements the declared path.",
    ],
    "not_allowed_actions": [
        "Do not change the focal claim.",
        "Do not change the dataset.",
        "Do not run analysis.",
        "Do not generate a replacement for a retained high-quality task.",
        "Do not propose a path that repeats shared memory.",
        "Do not choose a path because it is expected to support the focal claim.",
        "Do not invent variables, restrictions, or controls without authorized evidence.",
    ],
}

PRUNING_RULES = {
    "allowed_actions": [
        "Read the candidate path.",
        "Read the original paper PDF.",
        "Explore the authorized dataset.",
        "Read the candidate path's analysis code.",
        "Read shared memory.",
        "Decide whether each new active task candidate is high-quality or low-quality.",
        "Check each candidate against its task-specific paper analysis anchor.",
        "Verify estimand alignment and evidence for analytical choices.",
        "Verify sample-flow reporting and plan-code consistency.",
    ],
    "not_allowed_actions": [
        "Do not modify a proposed task candidate.",
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
