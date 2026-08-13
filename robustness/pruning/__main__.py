import argparse

from core.constants import DEFAULT_CODE_MODE, CODE_MODE_CHOICES


def main():
    p = argparse.ArgumentParser("pruning")
    p.add_argument("--stage", choices=["prune"], required=True)
    p.add_argument("--tier", choices=["easy", "medium", "hard"], default="easy")
    p.add_argument("--study-path", required=True)
    p.add_argument("--templates-dir", default="./templates")
    p.add_argument("--show-prompt", action="store_true", default=False)
    p.add_argument(
        "--run-execution",
        action="store_true",
        default=False,
        help="Execute immediately after pruning only when the path is high-quality.",
    )
    p.add_argument(
        "--code-mode",
        choices=CODE_MODE_CHOICES,
        default=DEFAULT_CODE_MODE,
        help="Code execution mode: 'native' (run original language) or 'python' (translate all to Python).",
    )
    p.add_argument("--model-name", help="Please specify the OpenAI model to be used.")
    args = p.parse_args()

    if args.stage == "prune":
        # Pruning Agent: review the candidate path and route accept/reject.
        from robustness.pruning.prune_agent import run_prune
        run_prune(
            study_path=args.study_path,
            show_prompt=args.show_prompt,
            templates_dir=args.templates_dir,
            tier=args.tier,
            code_mode=args.code_mode,
            model_name=args.model_name,
            run_execution=args.run_execution,
        )

if __name__ == "__main__":
    main()
