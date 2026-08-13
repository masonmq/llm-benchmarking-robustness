SHELL := /bin/bash
export PYTHONPATH := $(abspath ..):$(abspath .)
PYTHON ?= python3

# libs we need before running anything
REQ := pytest pytest_cov openai dotenv pymupdf pyreadr pandas numpy docker docx

STUDY ?= ./data/original/1
CODE_MODE ?= python
MODEL ?= gpt-5
EVAL_MODEL ?= gpt-5
TIER ?= easy
MAX_PLANNING_PRUNING_LOOPS ?= 5

.PHONY: check-deps install-dev test test-extractor test-generator test-all design-easy execute-easy robustness-plan robustness-pipeline robustness-pruning robustness-pruning-execute test-pruning

check-deps:
	$(PYTHON) core/check_deps.py $(REQ)

install-deps:
	pip install -r requirements-dev.txt

check-docker:
	@command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not in PATH"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "ERROR: docker daemon not reachable (is it running? do you have permissions?)"; exit 1; }
	@echo "Docker: OK"


# Generate structured analysis from human documentation
robustness-plan: check-deps
	python -m robustness.planner --tier easy --study-path $(STUDY) --model-name $(MODEL) --stage plan-analysis --code-mode $(CODE_MODE) --paper-id $(PAPER_ID) --max-planning-pruning-loops $(MAX_PLANNING_PRUNING_LOOPS)

# Opt-in continuous pipeline: plan -> prune -> execute (execution only after high-quality).
robustness-pipeline: check-deps
	python -m robustness.planner --tier easy --study-path $(STUDY) --model-name $(MODEL) --stage plan-analysis --code-mode $(CODE_MODE) --paper-id $(PAPER_ID) --run-execution --max-planning-pruning-loops $(MAX_PLANNING_PRUNING_LOOPS)

# Generate a universal execution input from human documentation
robustness-execute-gen_gold_analysis: check-deps
	python -m robustness.executor --tier easy --study-path $(STUDY) --model-name $(MODEL) --stage execute-gen_gold_analysis --code-mode $(CODE_MODE)

# Execute analysis
robustness-execute: check-deps
	python -m robustness.executor --stage execute --tier easy --study-path $(STUDY) --code-mode $(CODE_MODE) --model-name $(MODEL)


# Pruning Agent: universal_schema.json -> prune_out_schema.json + universal_schema.json
robustness-pruning: check-deps
	python -m robustness.pruning --stage prune --tier easy --study-path $(STUDY) --code-mode $(CODE_MODE) --model-name $(MODEL)

# Standalone prune -> execute path, still gated on a high-quality pruning decision.
robustness-pruning-execute: check-deps
	python -m robustness.pruning --stage prune --tier easy --study-path $(STUDY) --code-mode $(CODE_MODE) --model-name $(MODEL) --run-execution


evaluate-execute-capability: check-deps
	python -m robustness.validator --stage evaluate-execute-capability  --study-path $(STUDY)  --model-name $(EVAL_MODEL)



evaluate-execute-feedback: check-deps
	python -m robustness.validator --stage evaluate-execute-feedback  --study-path $(STUDY)  --model-name $(EVAL_MODEL)
