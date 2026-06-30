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

<<<<<<< HEAD
.PHONY: check-deps install-dev test test-extractor test-generator test-all design-easy execute-easy
=======
.PHONY: check-deps install-dev test test-extractor test-generator test-all design-easy execute-easy robustness-prunning-helper robustness-prunning test-prunning
>>>>>>> 303a243 (Inital prunning agent implementation)

check-deps:
	$(PYTHON) core/check_deps.py $(REQ)

install-deps:
	pip install -r requirements-dev.txt

check-docker:
	@command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not in PATH"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "ERROR: docker daemon not reachable (is it running? do you have permissions?)"; exit 1; }
	@echo "Docker: OK"


# Generate structured analysis from human documentation
robustness-execute-gen_gold_analysis: check-deps
	python -m robustness.executor --tier easy --study-path $(STUDY) --model-name $(MODEL) --stage execute-gen_gold_analysis --code-mode $(CODE_MODE)

# Execute analysis
robustness-execute: check-deps
	python -m robustness.executor --stage execute --tier easy --study-path $(STUDY) --code-mode $(CODE_MODE) --model-name $(MODEL)


# Helper extractor: paper PDF + proposed-analysis (review) PDF + data -> prune_in_schema.json
robustness-prunning-helper: check-deps
	python -m robustness.prunning --stage prune-gen_input --tier easy --study-path $(STUDY) --model-name $(MODEL) --code-mode $(CODE_MODE)

# Pruning Agent: prune_in_schema.json -> prune_out_schema.json (accept/reject + routing)
robustness-prunning: check-deps
	python -m robustness.prunning --stage prune --tier easy --study-path $(STUDY) --code-mode $(CODE_MODE) --model-name $(MODEL)


evaluate-execute-capability: check-deps
	python -m robustness.validator --stage evaluate-execute-capability  --study-path $(STUDY)  --model-name $(EVAL_MODEL)



evaluate-execute-feedback: check-deps
	python -m robustness.validator --stage evaluate-execute-feedback  --study-path $(STUDY)  --model-name $(EVAL_MODEL)
