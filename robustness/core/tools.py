import base64
from openai import OpenAI
import os
import json
import pandas as pd
import pyreadr
from core.constants import API_KEY
from typing import Dict, Any, Optional, Tuple
import io # Add this import at the top of your file
from pathlib import Path
import difflib
import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from core.human_intervention import human_intervention_enabled, request_approval
from core.pdf_retrieval import (
    read_pdf_overview,
    read_pdf_pages as read_selected_pdf_pages,
    search_pdf as search_pdf_pages,
)

client = OpenAI(api_key=API_KEY)

class DataFrameAnalyzer:
    """
    A class to load and analyze a tabular dataset from a file.

    Loads a DataFrame once upon initialization and provides methods
    to perform common exploratory analysis tasks.
    """
    def __init__(self, file_path: str):
        """
        Initializes the analyzer and loads the data.

        Args:
            file_path (str): The path to the CSV file.
        """
        self.file_path = file_path
        self.df: Optional[pd.DataFrame] = self._load_data()

    def _load_data(self) -> Optional[pd.DataFrame]:
        """
        Private method to load data from the file_path.
        Handles both .csv, .xlsx, .dta, .rds, .sav files and potential errors.
        """
        # Get the file extension from the file path
        _, file_extension = os.path.splitext(self.file_path)
        
        try:
            print(f"Loading data from {self.file_path}...")
            
            # Choose the correct pandas function based on the extension
            if file_extension == '.csv':
                return pd.read_csv(self.file_path)
            elif file_extension in ['.xlsx', '.xls']:
                # You might need to install openpyxl: pip install openpyxl
                return pd.read_excel(self.file_path)
            elif file_extension == '.dta':
                return pd.read_stata(self.file_path)
            elif file_extension.lower() == '.rds':
                return pyreadr.read_r(self.file_path)[None]
            elif file_extension.lower() == ".sav":
                return pd.read_spss(self.file_path)
            else:
                print(f"Error: Unsupported file type '{file_extension}'.")
                return None

        except FileNotFoundError:
            print(f"Error: The file at {self.file_path} was not found.")
            return None
        except (pd.errors.ParserError, ValueError, Exception) as e:
            # Catch pandas parsing errors and other potential issues
            print(f"An error occurred while reading the file: {e}")
            return None

    def get_head(self, n: int = 5) -> Optional[pd.DataFrame]:
        """Returns the first n rows of the DataFrame."""
        if self.df is not None:
            return self.df.head(n)
        return None

    def get_shape(self) -> Optional[Tuple[int, int]]:
        """Returns the shape (rows, columns) of the DataFrame."""
        if self.df is not None:
            # .shape is an attribute, not a function
            return self.df.shape
        return None

    def get_info(self) -> str: # Change the return type hint to str
        """
        Returns a concise summary of the DataFrame as a string.
        """
        if self.df is not None:
            # Create an in-memory text buffer
            buffer = io.StringIO()
            
            # Tell df.info() to write its output to the buffer instead of the console
            self.df.info(buf=buffer)
            
            # Get the string from the buffer and return it
            return buffer.getvalue()
        return "Error: DataFrame not loaded."

    def get_description(self) -> Optional[pd.DataFrame]:
        """Returns descriptive statistics of the DataFrame."""
        if self.df is not None:
            return self.df.describe()
        return None
    
    def get_variable_summary(self, variable_name) -> str:
        """
        Rreturns summary statistics for a specific variable.
        - Numeric: Returns the 5-number summary (Min, Q1, Median, Q3, Max).
        - Categorical: Returns counts of unique categories (capped at top 20).
        """
        
        # 1. Load the Data

        # 2. Check if variable exists
        if variable_name not in self.df.columns:
            available_cols = ", ".join(self.df.columns[:5]) # Show first 5 as hint
            return f"Error: Variable '{variable_name}' not found. (First few columns: {available_cols}...)"

        series = self.df[variable_name]
        
        # 3. Handle Numeric Variables (5-number summary)
        if pd.api.types.is_numeric_dtype(series):
            # clean data (drop NAs for accurate stats)
            clean_series = series.dropna()
            
            if clean_series.empty:
                return f"Variable '{variable_name}' contains only NaN values."

            quartiles = clean_series.quantile([0.25, 0.5, 0.75])
            
            summary = (
                f"--- Numeric Summary for '{variable_name}' ---\n"
                f"Min:    {clean_series.min()}\n"
                f"Q1:     {quartiles[0.25]}\n"
                f"Median: {quartiles[0.5]}\n"
                f"Q3:     {quartiles[0.75]}\n"
                f"Max:    {clean_series.max()}\n"
                f"missing_values: {series.isna().sum()}"
            )
            return summary

        # 4. Handle Categorical/Character Variables
        else:
            # Get value counts
            counts = series.value_counts(dropna=False)
            unique_count = len(counts)
            
            # Guardrail: Don't print 10,000 rows if it's high cardinality
            top_n = 20
            truncated = unique_count > top_n
            display_counts = counts.head(top_n)
            
            output_lines = [f"--- Categorical Summary for '{variable_name}' ---",
                            f"Total Unique Categories: {unique_count}"]
            
            for cat, count in display_counts.items():
                output_lines.append(f"- {cat}: {count}")
                
            if truncated:
                output_lines.append(f"... (and {unique_count - top_n} more categories)")
                
            return "\n".join(output_lines)
    
    
def load_dataset(session_state: Dict[str, Any], file_path: str) -> str:
    """
    Loads a dataset and stores its analyzer in the session state.
    """
    analyzers = session_state["analyzers"]
    if file_path in analyzers:
        return f"Dataset '{file_path}' is already loaded."
    
    analyzer = DataFrameAnalyzer(file_path)
    if analyzer.df is not None:
        analyzers[file_path] = analyzer
        return f"Successfully loaded dataset '{file_path}'."
    else:
        return f"Failed to load dataset from '{file_path}'."

def get_dataset_shape(session_state: Dict[str, Any], file_path: str) -> str:
    """
    Gets the shape from an analyzer in the session state.
    """
    analyzers = session_state["analyzers"]
    if file_path not in analyzers:
        return "Error: Dataset not loaded. Please call load_dataset() first."
    return str(analyzers[file_path].get_shape())

def get_dataset_head(session_state: Dict[str, Any], file_path: str) -> str:
    analyzers = session_state["analyzers"]
    if file_path not in analyzers:
        return "Error: Dataset not loaded. Please call load_dataset() first."
    return str(analyzers[file_path].get_head())

def get_dataset_info(session_state: Dict[str, Any], file_path: str) -> str:
    analyzers = session_state["analyzers"]
    if file_path not in analyzers:
        return "Error: Dataset not loaded. Please call load_dataset() first."
    return str(analyzers[file_path].get_info())

def get_dataset_description(session_state: Dict[str, Any], file_path: str) -> str:
    analyzers = session_state["analyzers"]
    if file_path not in analyzers:
        return "Error: Dataset not loaded. Please call load_dataset() first."
    return str(analyzers[file_path].get_description())

def get_dataset_columns(session_state: Dict[str, Any], file_path: str) -> str:
    analyzers = session_state["analyzers"]
    if file_path not in analyzers:
        return "Error: Dataset not loaded. Please call load_dataset() first."
    return str(list(analyzers[file_path].df.columns))

def get_dataset_variable_summary(session_state: Dict[str, Any], file_path: str, variable_name: str) -> str:
    analyzers = session_state["analyzers"]
    if file_path not in analyzers:
        return "Error: Dataset not loaded. Please call load_dataset() first."
    return str(analyzers[file_path].get_variable_summary(variable_name))

def read_image(file_path):
    # Function to encode the image
    def encode_image(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    base64_image = encode_image(file_path)
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    { "type": "text", "text": "Describe this image in details." },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ])
    return completion.choices[0].message.content



def ask_human_input(question: str) -> str:
    """
    Prompts the human user for input in the terminal.

    Use this tool when you are stuck, need clarification, or require 
    information that you cannot find or deduce from the available files.

    Args:
        question_to_ask (str): The clear, specific question to ask the human user.

    Returns:
        str: The human's response from the terminal.
    """
    if not human_intervention_enabled():
        return (
            "Human intervention is disabled. Continue with the authorized evidence, "
            "or return a clear failure if the missing information is required."
        )

    # Print a clear message to the user indicating the agent needs help
    print("\n🤔 [AGENT NEEDS HUMAN INPUT] 🤔")
    print(f"Agent's Question: {question}")
    
    # Get input from the user
    human_response = input("Your Response: ")
    
    return human_response


def list_files_in_folder(study_path, folder_path: str = None, strs2avoid = []) -> str:
    """
    Recursively lists all files within a specified folder and its subfolders.
    Automatically adapts to both OpenAI JSON tool calls and ReAct text parsers.
    """

    # If folder_path is None, this was called by the ReAct text parser in evaluate_execute.py, 
    # which dumped the single string into the first argument (study_path).
    if folder_path is None:
        folder_path = str(study_path).strip(' "\'')
        
        # Dynamically infer the actual study_path from the folder string
        # e.g., converts "data/original/2/input" -> "data/original/2"
        path_parts = folder_path.replace("\\", "/").split("/")
        study_path_parts = []
        for part in path_parts:
            study_path_parts.append(part)
            if part.isdigit(): # Stops when it hits the experiment number
                break
        study_path = os.path.join(*study_path_parts) if study_path_parts else "."
    else:
        # Normal execution by the Generative Agent!
        folder_path = str(folder_path).strip(' "\'')
        study_path = str(study_path).strip(' "\'')

    abs_folder = os.path.abspath(folder_path)
    abs_study = os.path.abspath(study_path)
    
    # Check if abs_folder is inside abs_study
    try:
        if os.path.commonpath([abs_folder, abs_study]) != abs_study:
            return f"Error: Access denied. '{folder_path}' is outside of the study directory. You can only search within {study_path}"
    except ValueError:
        return "Error: Paths are on different drives."
    
    # Check if the provided path exists
    if not os.path.exists(folder_path):
        return f"Error: Folder '{folder_path}' does not exist."

    # Check if the provided path is actually a directory
    if not os.path.isdir(folder_path):
        return f"Error: Path '{folder_path}' is not a directory."

    file_paths = []
    # evals added to avoid cheating
    # strs2avoid = ["human_preregistration", "metadata.json", "human_report", "llm_eval", "expected_post_registration", "evals"]
    strs2avoid.extend(["human_preregistration", "metadata.json", "human_report", "llm_eval", "expected_post_registration", "evals"])

    # Walk through all directories and subdirectories
    for current_root, _, files in os.walk(folder_path):
        for file in files:
            full_path = os.path.join(current_root, file)
            relative_path = os.path.relpath(full_path, folder_path)
            if not any(s in relative_path for s in strs2avoid): 
                file_paths.append(relative_path)

    if not file_paths:
        return f"Folder path: {folder_path}\nNo files found."

    file_paths.sort()

    file_info = f"Folder path: {folder_path}\nAll files:\n" + "\n".join(file_paths)
    return file_info

from pathlib import Path

def _resolve_write_path(file_path: str, study_path: str = None) -> Path:
    """
    Resolve an agent write target.

    When study_path is supplied by the agent runner, relative paths are anchored
    to that study directory and all writes are restricted to stay inside it.
    Without study_path, preserve the legacy Path.cwd() behavior for direct callers.
    """
    raw_path = Path(str(file_path))

    if study_path is None:
        return Path.cwd() / raw_path

    study_dir = Path(study_path).resolve()

    if raw_path.is_absolute():
        full_path = raw_path.resolve()
    else:
        # Some callers already provide a cwd-relative path that includes the
        # study directory (for example, data/original/1/...). Preserve it when
        # it already resolves inside the study; otherwise treat the path as
        # study-relative (for example, candidate_artifacts/...).
        cwd_candidate = (Path.cwd() / raw_path).resolve()
        try:
            cwd_candidate.relative_to(study_dir)
            full_path = cwd_candidate
        except ValueError:
            full_path = (study_dir / raw_path).resolve()

    try:
        full_path.relative_to(study_dir)
    except ValueError as exc:
        raise ValueError(
            f"Write path '{file_path}' is outside the study directory '{study_dir}'."
        ) from exc

    return full_path


def write_file(
    file_path: str,
    file_content: str,
    overwrite: bool = False,
    study_path: str = None,
) -> str:
    """
    Create a NEW file (default) or overwrite an existing file only if overwrite=True.

    Agent calls may supply study_path internally so relative paths are anchored
    to the current study and cannot create files elsewhere in the repository.
    Direct callers that omit study_path retain the previous cwd-relative behavior.
    """
    try:
        full_path = _resolve_write_path(file_path, study_path=study_path)
    except ValueError as e:
        error_message = f"❌ Error resolving write path: {e}"
        print(error_message)
        return error_message

    file_exists = full_path.exists()

    print("\n📝 [AGENT ASKS TO WRITE FILE] 📝")
    print(f"FULL PATH: {full_path}")
    print(f"EXISTS ALREADY?: {file_exists}")
    print(f"OVERWRITE FLAG?: {overwrite}")
    print(f"FILE CONTENT:\n---\n{file_content}\n---")

    if file_exists and not overwrite:
        msg = (
            "❌ Refusing to overwrite an existing file. "
            "Use edit_file(...) for targeted edits, or call write_file(..., overwrite=True)."
        )
        print(msg)
        return msg

    if not request_approval("Do you approve? (yes/no): "):
        print("❌ User denied execution.")
        return "Command execution denied by the user."

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(file_content)
        success_message = f"✅ Successfully wrote content to {full_path}"
        print(success_message)
        return success_message
    except Exception as e:
        error_message = f"❌ Error writing file to {full_path}: {e}"
        print(error_message)
        return error_message


BINARY_DATASET_EXTENSIONS = {".xls", ".xlsx", ".dta", ".sav", ".rds"}


def _read_text_content(full_path: Path) -> str:
    try:
        return full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return full_path.read_text(encoding="latin-1")


def search_txt(
    file_path: str,
    query: str,
    max_results: int = 5,
    context_lines: int = 3,
    max_chars: int = 12_000,
) -> str:
    """
    Search a text file locally and return bounded matching line windows.

    This is deterministic and makes no LLM/API calls. It is intended for large
    codebooks, documentation, and other text files where reading the whole file
    would waste context/tokens.
    """
    full_path = Path.cwd() / file_path

    if not full_path.exists():
        return f"Error: File not found: {full_path}"
    if full_path.is_dir():
        return f"Error: Path is a directory: {full_path}"
    if full_path.suffix.lower() in BINARY_DATASET_EXTENSIONS:
        return (
            f"Error: '{file_path}' is a binary dataset file. Use load_dataset and "
            "the dataset inspection tools instead of search_txt."
        )

    query = str(query or "").strip()
    if not query:
        return "Error: search_txt requires a non-empty query."

    try:
        max_results = max(1, min(int(max_results), 8))
        context_lines = max(0, min(int(context_lines), 8))
        max_chars = max(1_000, min(int(max_chars), 15_000))
    except (TypeError, ValueError):
        return "Error: max_results, context_lines, and max_chars must be integers."

    try:
        content = _read_text_content(full_path)
    except Exception as e:
        return f"Error reading text file '{file_path}': {e}"

    lines = content.splitlines()
    query_lower = query.lower()
    terms = [
        term
        for term in re.findall(r"[A-Za-z0-9_$.-]+", query_lower)
        if len(term) >= 2
    ]

    scored = []
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        phrase_match = query_lower in line_lower
        matched_terms = sum(1 for term in terms if term in line_lower)
        if phrase_match or matched_terms:
            score = (10 if phrase_match else 0) + matched_terms
            scored.append((score, idx))

    if not scored:
        return f"No matches for '{query}' in '{file_path}'."

    scored.sort(key=lambda item: (-item[0], item[1]))
    windows = []
    for _, idx in scored:
        start = max(0, idx - context_lines)
        end = min(len(lines), idx + context_lines + 1)
        if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end in windows):
            continue
        windows.append((start, end))
        if len(windows) >= max_results:
            break

    output = [
        f"Search results for '{query}' in '{file_path}' "
        f"({len(lines)} lines; showing {len(windows)} bounded match window(s))."
    ]
    for match_no, (start, end) in enumerate(windows, 1):
        output.append(f"\n--- Match {match_no}: lines {start + 1}-{end} ---")
        for line_no in range(start, end):
            output.append(f"{line_no + 1}: {lines[line_no]}")

    result = "\n".join(output)
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n... [TRUNCATED TO {max_chars} CHARACTERS] ..."
    return result


def read_file(file_path: str, max_chars: int = 20000) -> str:
    """
    Read a text file (truncated) so the agent can make targeted edits.
    Binary dataset formats are rejected to prevent accidental binary dumps.
    """
    full_path = Path.cwd() / file_path

    if not full_path.exists():
        return f"Error: File not found: {full_path}"
    if full_path.is_dir():
        return f"Error: Path is a directory: {full_path}"
    if full_path.suffix.lower() in BINARY_DATASET_EXTENSIONS:
        return (
            f"Error: '{file_path}' is a binary dataset file. Use load_dataset and "
            "the dataset inspection tools instead of read_file."
        )

    try:
        content = _read_text_content(full_path)
    except Exception as e:
        return f"Error reading file '{file_path}': {e}"

    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n... [TRUNCATED {len(content)-max_chars} chars] ..."
    return content



def edit_file(
    file_path: str,
    edit_type: str,
    *,
    old_text: str = None,
    new_text: str = None,
    start_marker: str = None,
    end_marker: str = None,
    anchor: str = None,
    insert_text: str = None,
    count: int = 1,
) -> str:
    """
    Targeted edits WITHOUT overwriting the whole file.
    Shows a unified diff and requests approval when human intervention is enabled.

    edit_type:
      - "replace"
      - "replace_between" (markers kept; content between replaced)
      - "insert_after"
      - "insert_before"
      - "append"
      - "prepend"
    """
    full_path = Path.cwd() / file_path

    if not full_path.exists():
        return f"Error: File not found: {full_path}"
    if full_path.is_dir():
        return f"Error: Path is a directory: {full_path}"

    try:
        original = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        original = full_path.read_text(encoding="latin-1")

    edited = original

    if edit_type == "replace":
        if old_text is None or new_text is None:
            return "Error: replace requires old_text and new_text."
        if old_text not in edited:
            return "Error: old_text not found."
        edited = edited.replace(old_text, new_text, count)

    elif edit_type == "replace_between":
        if start_marker is None or end_marker is None or new_text is None:
            return "Error: replace_between requires start_marker, end_marker, and new_text."
        s = edited.find(start_marker)
        if s == -1:
            return "Error: start_marker not found."
        e = edited.find(end_marker, s + len(start_marker))
        if e == -1:
            return "Error: end_marker not found (after start_marker)."
        between_start = s + len(start_marker)
        between_end = e
        edited = edited[:between_start] + new_text + edited[between_end:]

    elif edit_type in ("insert_after", "insert_before"):
        if anchor is None or insert_text is None:
            return f"Error: {edit_type} requires anchor and insert_text."
        idx = edited.find(anchor)
        if idx == -1:
            return "Error: anchor not found."
        insert_at = idx + len(anchor) if edit_type == "insert_after" else idx
        edited = edited[:insert_at] + insert_text + edited[insert_at:]

    elif edit_type == "append":
        if insert_text is None:
            return "Error: append requires insert_text."
        if edited and not edited.endswith("\n"):
            edited += "\n"
        edited += insert_text

    elif edit_type == "prepend":
        if insert_text is None:
            return "Error: prepend requires insert_text."
        edited = insert_text + ("" if insert_text.endswith("\n") else "\n") + edited

    else:
        return f"Error: Unknown edit_type '{edit_type}'."

    if edited == original:
        return "No changes made."

    diff = "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            edited.splitlines(),
            fromfile=str(full_path) + " (before)",
            tofile=str(full_path) + " (after)",
            lineterm="",
        )
    )

    print("\n✍️ [AGENT PROPOSES A FILE EDIT] ✍️")
    print(f"FULL PATH: {full_path}")
    print(f"DIFF:\n---\n{diff}\n---")

    if not request_approval("Do you approve this edit? (yes/no): "):
        print("❌ User denied edit.")
        return "Edit denied by the user."

    try:
        full_path.write_text(edited, encoding="utf-8")
        msg = f"✅ Successfully edited {full_path}"
        print(msg)
        return msg
    except Exception as e:
        return f"❌ Error writing edited file to {full_path}: {e}"

def read_and_summarize_pdf(file_path: str, summarizer_model: str="gpt-4o", for_data: bool=False) -> str:
    del summarizer_model, for_data
    return read_pdf_overview(file_path)


def search_pdf(file_path: str, query: str, max_results: int = 5) -> str:
    return search_pdf_pages(file_path, query, max_results)


def read_pdf_pages(file_path: str, page_numbers: list[int], max_chars: int = 30_000) -> str:
    return read_selected_pdf_pages(file_path, page_numbers, max_chars)
    
    

def read_html(study_path, file_path):
    # 1. Load the HTML
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    # 2. Setup image directory
    img_dir = os.path.join(study_path, "replication_data", "extracted_images")
    if not os.path.exists(img_dir):
        os.makedirs(img_dir)

    # 3. Find all images with base64 data
    img_tags = soup.find_all('img')
    print(f"Found {len(img_tags)} images. Processing...")

    for i, img in enumerate(img_tags):
        src = img.get('src', '')
        
        # Check if it's a base64 string
        if src.startswith('data:image'):
            try:
                # Split the header from the actual base64 data
                # Format is usually: data:image/png;base64,iVBOR...
                header, encoded = src.split(",", 1)
                
                # Determine file extension (png, jpeg, etc)
                ext = header.split('/')[1].split(';')[0]
                img_filename = f"image_{i}.{ext}"
                img_path = os.path.join(img_dir, img_filename)

                # Decode and save the file
                with open(img_path, "wb") as f_img:
                    f_img.write(base64.b64decode(encoded))
                
                # IMPORTANT: Replace the giant string in the HTML 
                # with the local filename before converting to Markdown
                img['src'] = img_path
                print(f"Saved: {img_path}")
                
            except Exception as e:
                print(f"Could not process image {i}: {e}")

    # 4. Convert the "cleaned" HTML to Markdown
    # This will now use the local file paths we just created
    markdown_text = md(str(soup), heading_style="ATX")

    # 5. Save the Markdown file
    # with open(output_md_file, 'w', encoding='utf-8') as f_out:
    #     f_out.write(markdown_text)
    return markdown_text
