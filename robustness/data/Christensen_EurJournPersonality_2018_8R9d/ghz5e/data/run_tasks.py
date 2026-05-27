#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys


def run(task, extra_args=None):
    if extra_args is None:
        extra_args = []
    base = ["python", "data/ghz5e_analysis__py.py", "--task", task, "--data_file", "/app/data/FINAL fluency.csv", "--id_col", "id", "--openness_col", "latent", "--response_prefix", "vf_an_", "--iters", "200", "--knn_k", "8", "--merge_file", "/app/data/All samples merged and totaled_shared.sav", "--merge_on", "id:id", "--openness_regex", "open"]
    cmd = base + extra_args
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        sys.exit(p.returncode)
    try:
        obj = json.loads(p.stdout.strip())
    except Exception:
        print(p.stdout)
        raise
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", choices=["Task1", "Task2", "both"], default="both")
    args = ap.parse_args()

    outputs = {}
    if args.run in ("Task1", "both"):
        outputs["Task1"] = run("Task1")
    if args.run in ("Task2", "both"):
        outputs["Task2"] = run("Task2", extra_args=["--bootstrap_prop", "0.9"])  # explicit per spec

    print(json.dumps(outputs))


if __name__ == "__main__":
    main()
