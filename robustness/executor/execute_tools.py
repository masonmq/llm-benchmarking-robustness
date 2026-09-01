import base64
from openai import OpenAI
import os
import json
import pandas as pd
from core.constants import API_KEY
from typing import Dict, Any, Optional, Tuple
import io # Add this import at the top of your file
import shlex
import subprocess

from core.human_intervention import request_approval

SHELL_COMMAND_TIMEOUT_SECONDS = 120


def run_shell_command(command: str) -> str:
    """
    Executes a shell command in the local terminal after any configured confirmation.

    Args:
        command (str): The complete shell command to execute (e.g., "python3 my_script.py --arg value").

    Returns:
        str: The combined standard output and standard error from the command, or a rejection message.
    """
    print(f"Agent wants to execute the command: `{command}`")

    if not request_approval("Do you approve? (yes/no): "):
        print("❌ User denied execution.")
        return "Command execution denied by the user."

    print(f"✅ User approved. Executing command...")
    try:
        result = subprocess.run(
            ["/bin/bash", "-lc", command],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=SHELL_COMMAND_TIMEOUT_SECONDS,
        )
    
        # 4. Return the full output to the agent
        output = f"Exit Code: {result.returncode}\n---STDOUT---\n{result.stdout}\n---STDERR---\n{result.stderr}"
        return output.strip()

    except subprocess.TimeoutExpired:
        return (
            f"Error: Command timed out after {SHELL_COMMAND_TIMEOUT_SECONDS} seconds "
            "and was stopped."
        )
    except FileNotFoundError:
        return "Error: /bin/bash was not found."
    except Exception as e:
        return f"An error occurred while executing the command: {e}"

def run_stata_do_file(file_path: str) -> str:
    """
    Executes a Stata .do file in batch mode after any configured confirmation,
    captures the output from the corresponding .log file, and returns it as a string.

    Args:
        file_path (str): The path to the Stata .do file.

    Returns:
        str: The full content of the generated .log file, or an error message.
    """
    # 1. Determine the expected log file path from the do-file path
    base_name, _ = os.path.splitext(file_path)
    log_path = base_name.split("/")[-1] + ".log"

    # NOTE: The Stata executable might have a different name on your system (e.g., 'stata-se', 'stata')
    command = f"stata-mp -b do {file_path}"

    print(f"Agent wants to execute the Stata script: `{file_path}`")

    if not request_approval(f"This will run the command: `{command}`\nDo you approve? (yes/no): "):
        return "Command execution denied by the user."
    
    try:
        # 3. Execute the Stata command
        print(f"✅ User approved. Executing Stata script...")
        args = shlex.split(command)
        result = subprocess.run(args, capture_output=True, text=True, check=False)

        # If Stata itself threw an error, return that for debugging
        if result.returncode != 0:
            return f"Stata execution failed.\n---STDERR---\n{result.stderr}"

        # 4. Read the entire contents of the generated log file
        print(f"Execution finished. Reading output from '{log_path}'...")
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as log_file:
            log_content = log_file.read()

        # 5. (Good practice) Clean up the log file
        os.remove(log_path)
        
        return log_content

    except FileNotFoundError:
        return f"Error: Could not find the generated log file at '{log_path}'. Make sure Stata is installed and the do-file path is correct."
    except Exception as e:
        return f"An unexpected error occurred: {e}"
