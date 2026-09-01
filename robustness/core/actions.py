# core/actions.py
import os

from replicatorbench.info_extractor.file_utils import read_txt, read_csv, read_json, read_pdf, read_docx
from core.human_intervention import human_intervention_enabled
from core.tools import (
    list_files_in_folder,
    ask_human_input,
    read_image,
    read_file,
    edit_file,
    write_file,
    load_dataset,
    get_dataset_head,
    get_dataset_shape,
    get_dataset_description,
    get_dataset_info,
    get_dataset_columns,
    get_dataset_variable_summary,
    read_and_summarize_pdf,
    search_pdf,
    read_pdf_pages,
    read_html
)

def base_known_actions() -> dict:
    """
    Generic actions available to ALL agents.
    Stage-specific agents can extend this with their own entries.
    """
    actions = {
        "list_files_in_folder": list_files_in_folder,

        "read_txt": read_txt,
        "read_csv": read_csv,
        #"read_pdf": read_pdf,
        "read_pdf": read_and_summarize_pdf,
        "search_pdf": search_pdf,
        "read_pdf_pages": read_pdf_pages,
        "read_json": read_json,
        "read_docx": read_docx,

        "read_image": read_image,

        "load_dataset": load_dataset,
        "get_dataset_head": get_dataset_head,
        "get_dataset_shape": get_dataset_shape,
        "get_dataset_description": get_dataset_description,
        "get_dataset_info": get_dataset_info,
        "get_dataset_columns": get_dataset_columns,
         "get_dataset_variable_summary": get_dataset_variable_summary,

        # file manipulating 
        "read_file": read_file,
        "edit_file": edit_file,
        "write_file": write_file,
        "read_html": read_html
    }
    if human_intervention_enabled():
        actions["ask_human_input"] = ask_human_input
    return actions

def get_tool_definitions() -> list:
    """
    Returns the OpenAI tool definitions as JSON schemas for the base actions.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_files_in_folder",
                "description": "Lists all files within a specified folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder_path": {"type": "string", "description": "The path to the folder to list files from."}
                    },
                    "required": ["folder_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_txt",
                "description": "Reads the plain text content of a file (e.g., .txt, .do).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the text file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_pdf",
                "description": "Returns exact text for a short PDF or a bounded opening-page overview for a long PDF. Use search_pdf and read_pdf_pages for exact evidence from long PDFs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the PDF file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_pdf",
                "description": "Searches a PDF locally and returns ranked page numbers with bounded text snippets. Use focused queries for methods, variables, models, restrictions, or result tables.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the PDF file."},
                        "query": {"type": "string", "description": "Focused words or phrase to locate in the PDF."},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5}
                    },
                    "required": ["file_path", "query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_pdf_pages",
                "description": "Reads exact text from selected 1-based PDF pages. At most 8 pages and 30000 characters are returned per call.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the PDF file."},
                        "page_numbers": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 1,
                            "maxItems": 8,
                            "description": "One-based page numbers to read."
                        },
                        "max_chars": {"type": "integer", "minimum": 1, "maximum": 30000, "default": 30000}
                    },
                    "required": ["file_path", "page_numbers"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_json",
                "description": "Reads and parses a JSON file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the JSON file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_docx",
                "description": "Extracts text from a Word (.docx) file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the .docx file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_image",
                "description": "Analyzes an image file (.png, .jpg, etc.) and provides a natural language description.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the image file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
         {
            "type": "function",
            "function": {
                "name": "read_html",
                "description": "Extracts content from an html file into text under Markdown format. Any images found in the html will be saved separately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the .html file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "load_dataset",
                "description": "Loads a dataset (CSV, Excel, DTA, RDS, SAV) into memory for analysis. Must be called before other dataset tools.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the dataset file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dataset_head",
                "description": "Retrieves the first 5 rows of a loaded dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the already loaded dataset file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dataset_shape",
                "description": "Gets the dimensions (rows, columns) of a loaded dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the already loaded dataset file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dataset_description",
                "description": "Calculates descriptive statistics (count, mean, std, etc.) for numerical columns.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the already loaded dataset file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dataset_info",
                "description": "Provides a technical summary (column names, types, non-null counts) of the dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the already loaded dataset file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dataset_columns",
                "description": "Retrieves the list of all column names in the dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the already loaded dataset file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dataset_variable_summary",
                "description": "Calculates detailed summary statistics for a specific variable/column (Numeric or Categorical).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the dataset file."},
                        "variable_name": {"type": "string", "description": "Name of the variable to analyze."}
                    },
                    "required": ["file_path", "variable_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ask_human_input",
                "description": "Ask a clarifying question to the user if blocked or needing external info.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "The question to ask the user."}
                    },
                    "required": ["question"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Creates a NEW file. Fails if file exists unless overwrite=True. Use edit_file for modifications.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path where the file will be created."},
                        "file_content": {"type": "string", "description": "The content to write to the file."},
                        "overwrite": {"type": "boolean", "description": "Whether to overwrite if the file exists (default False)."}
                    },
                    "required": ["file_path", "file_content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "Modifies an existing file using search and replace or insertion.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file to edit."},
                        "edit_type": {
                            "type": "string", 
                            "enum": ["replace", "insert_after", "replace_between", "append"],
                            "description": "Type of edit to perform."
                        },
                        "old_text": {"type": "string", "description": "Text to search for (for 'replace')."},
                        "new_text": {"type": "string", "description": "Text to insert or replace with."},
                        "anchor": {"type": "string", "description": "Text to find to insert after (for 'insert_after')."},
                        "start_marker": {"type": "string", "description": "Start marker for 'replace_between'."},
                        "end_marker": {"type": "string", "description": "End marker for 'replace_between'."}
                    },
                    "required": ["file_path", "edit_type"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Generic file reader for observing content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file."}
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]
    if not human_intervention_enabled():
        tools = [
            tool for tool in tools
            if tool.get("function", {}).get("name") != "ask_human_input"
        ]
    return tools

def get_execute_tool_definitions() -> list:
    """
    Returns schemas for ALL tools available in the Execution phase:
    Base tools + Shell/Stata tools + Orchestrator tools.
    """
    base_tools = get_tool_definitions()
    
    execute_tools = [
        {
            "type": "function",
            "function": {
                "name": "run_shell_command",
                "description": (
                    "Executes a shell command in the local terminal."
                    + (" Requires human confirmation." if human_intervention_enabled() else "")
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The full shell command to run (e.g. 'python script.py')."}
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_stata_do_file",
                "description": "Executes a Stata .do file using the local Stata installation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the .do file."}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "orchestrator_plan",
                "description": "Define the execution plan (sequence of steps) for the replication.",
                "parameters": {
                    "type": "object",
                    "properties": {
                            "study_path": {"type": "string", "description": "Path to the current study directory"}
                    },
                    "required": ["study_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "orchestrator_generate_dockerfile",
                "description": "Generates a Dockerfile for the replication environment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                       "study_path": {"type": "string", "description": "Path to the current study directory"}
                    },
                    "required": ["study_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "orchestrator_build_image",
                "description": "Builds the Docker image from the generated Dockerfile.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_path": {"type": "string", "description": "Path to the current study directory"},
                        "image_name": {"type": "string", "description": "Tag for the image."}
                    },
                    "required": ["study_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "orchestrator_run_container",
                "description": "Starts the Docker container.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_path": {"type": "string", "description": "Path to the current study directory"},
                    },
                    "required": ["study_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "orchestrator_execute_entry",
                "description": "Executes a specific step from the plan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_path": {"type": "string", "description": "Path to the current study directory"},
                    },
                    "required": ["study_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "orchestrator_preview_entry",
                "description": "Previews the entry file and command that will run inside the container.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_path": {"type": "string", "description": "Path to the current study directory"},
                    },
                    "required": ["study_path"]
                }
            }
        },
         {
            "type": "function",
            "function": {
                "name": "orchestrator_stop_container",
                "description": "Stops and removes the running container.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "study_path": {"type": "string", "description": "Path to the current study directory"},
                    },
                    "required": ["study_path"]
                }
            }
        }
    ]
    
    return base_tools + execute_tools

PRUNE_ALLOWED_ACTIONS = [
    "read_json",
    "read_pdf",
    "search_pdf",
    "read_pdf_pages",
    "read_txt",
    "read_file",
    "list_files_in_folder",
    "load_dataset",
    "get_dataset_head",
    "get_dataset_shape",
    "get_dataset_description",
    "get_dataset_info",
    "get_dataset_columns",
    "get_dataset_variable_summary",
    "ask_human_input",
]

# Readers the Pruning Agent may use only on non-leakage files: the original paper,
# the candidate path's analysis code, and plain config/readme files.
PRUNE_GUARDED_READERS = (
    "read_pdf",
    "search_pdf",
    "read_pdf_pages",
    "read_txt",
    "read_file",
)

# File-name tokens that identify leakage sources for the Pruning Agent
PRUNE_BLOCKED_NAME_TOKENS = (
    "review",
    "human_analysis",
    "human_report",
    "proposed_analysis",
    "planned_analysis_summary",
)


def _prune_guard(tool_name: str, reader):
    """Wrap a reader so it refuses files whose names mark them as leakage sources."""
    def guarded(file_path: str, **kwargs):
        basename = os.path.basename(str(file_path)).lower()
        if any(token in basename for token in PRUNE_BLOCKED_NAME_TOKENS):
            return (
                f"BLOCKED: {tool_name} refused to read '{file_path}'. Human analysis / review "
                "documents and expected results are forbidden inputs for the Pruning Agent. "
                "Decide from the original paper, the authorized dataset, and the analysis code only."
            )
        return reader(file_path, **kwargs)
    return guarded


def prune_known_actions() -> dict:
    """
    Leakage-safe subset of base_known_actions() for the Pruning Agent.
    Includes the readers needed for a deep review (original paper PDF, analysis code,
    dataset inspection) but guards them against human analysis / review documents,
    and excludes all file writers so the agent cannot modify the proposed path.
    """
    base = base_known_actions()
    actions = {name: base[name] for name in PRUNE_ALLOWED_ACTIONS if name in base}
    for name in PRUNE_GUARDED_READERS:
        if name in actions:
            actions[name] = _prune_guard(name, actions[name])
    return actions


def get_prune_tool_definitions() -> list:
    """
    OpenAI tool schemas for the Pruning Agent: the leakage-safe subset of the base
    tool definitions (guarded readers, list_files_in_folder, dataset inspection,
    ask_human_input).
    """
    base_tools = get_tool_definitions()
    return [
        t for t in base_tools
        if t.get("function", {}).get("name") in PRUNE_ALLOWED_ACTIONS
    ]


def get_interpret_tool_definitions() -> list:
    """
    Returns schemas for tools available in the Interpret phase:
    Base tools + read_log.
    """
    base_tools = get_tool_definitions()
    
    interpret_tools = [
        {
            "type": "function",
            "function": {
                "name": "read_log",
                "description": "Reads a potentially very long log file. Automatically summarizes it if it exceeds token limits to fit in context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the log file."}
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]
    
    return base_tools + interpret_tools
