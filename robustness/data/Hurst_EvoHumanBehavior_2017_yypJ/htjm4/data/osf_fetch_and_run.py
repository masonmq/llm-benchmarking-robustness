import os
import json
import sys
from htjm4_osf_util import osf_find_and_download_csv

DATA_DIR = "/app/data"
TASK1_OUT = os.path.join(DATA_DIR, "htjm4_task1_results.json")
TASK2_OUT = os.path.join(DATA_DIR, "htjm4_task2_results.json")

NODE_ID = "vhmgc"  # extracted from https://osf.io/vhmgc/
VIEW_ONLY = "5c6bedb36b2549a88ac137d6c746bcb8"

REQUIRED1 = ["DSM5_Total", "MiniK_Total", "HKSS_Total"]
REQUIRED2 = ["DSM5_Total", "MiniK_Total"]


def main():
    # Try to find and download a CSV with Task1 columns
    path, err = osf_find_and_download_csv(NODE_ID, VIEW_ONLY, DATA_DIR, required_columns=REQUIRED1)
    if path is None:
        # Try Task2 requirements
        path, err = osf_find_and_download_csv(NODE_ID, VIEW_ONLY, DATA_DIR, required_columns=REQUIRED2)
    if path is None:
        # Write failure markers and exit nonzero to surface the issue
        msg = {"error": "osf_download_failed", "detail": err}
        with open(TASK1_OUT, 'w') as f:
            json.dump(msg, f, indent=2)
        with open(TASK2_OUT, 'w') as f:
            json.dump(msg, f, indent=2)
        return 2

    # If data was fetched, run the original scripts which will pick it up
    # No direct invocation here; the container plan will run them next.
    with open(os.path.join(DATA_DIR, "osf_download_result.json"), 'w') as f:
        json.dump({"status": "success", "path": path}, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
