import argparse, os, sys
from core.constants import DEFAULT_CODE_MODE, CODE_MODE_CHOICES

def main():
    p = argparse.ArgumentParser("plan-analysis")
    p.add_argument("--stage", choices=["plan-analysis"], required=True)
    p.add_argument("--tier", choices=["easy", "medium", "hard"], default="easy")
    p.add_argument("--study-path", required=True)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--templates-dir", default="./templates")
    p.add_argument("--show-prompt", action="store_true", default=False)
    p.add_argument("--no-pruning", action="store_true", default=False,
                   help="Stop after planning instead of chaining into the Pruning Agent.")
    p.add_argument("--code-mode",choices=CODE_MODE_CHOICES,default=DEFAULT_CODE_MODE,help="Code execution mode: 'native' (run original language) or 'python' (translate all to Python and run Python).",)
    p.add_argument("--model-name", help="Please specify the OpenAI model to be used.")
    args = p.parse_args()

    if args.stage == "plan-analysis":
        from planner.plan_agent import run_plan_analysis
        # run helper agent to generate input analysis for executor
        # Planning runs first and the Pruning Agent runs right after on its output,
        # so a single command covers plan -> prune.
        run_plan_analysis(args.study_path,
        	tier=args.tier,
        	code_mode=args.code_mode,
        	model_name=args.model_name,
            paper_id=args.paper_id,
            templates_dir=args.templates_dir,
            show_prompt=args.show_prompt,
            run_pruning=not args.no_pruning,
        )

    else:
        sys.exit(f"Stage/tier not implemented yet: {args.stage}/{args.tier}")

if __name__ == "__main__":
    main()