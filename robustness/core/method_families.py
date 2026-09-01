import re
from typing import Any


_COVERED_STATUSES = {"high-quality", "executed_success", "execution_failed"}
_DECISION_FIELDS = (
    "estimand_quantity",
    "outcome",
    "outcome_scale",
    "contrast",
    "target_population",
    "sample_restriction",
    "missing_data_rule",
    "variable_construction",
    "controls",
)
_DIVERSITY_FIELDS = (
    "estimand_quantity",
    "outcome_scale",
    "target_population",
    "sample_restriction",
    "missing_data_rule",
    "variable_construction",
    "controls",
)
_FAMILY_PATTERNS = (
    ("simultaneous_equation", ("simultaneous", "cdsimeq", "joint equation")),
    (
        "endogeneity_corrected_two_stage",
        ("two-stage", "two stage", "2sls", "instrumental variable", "ivreg", "control function"),
    ),
    ("panel_or_fixed_effects", ("fixed effect", "random effect", "within estimator", "panel model")),
    ("multilevel_or_hierarchical", ("multilevel", "hierarchical", "mixed effect")),
    ("difference_in_differences", ("difference-in-differences", "difference in differences")),
    ("regression_discontinuity", ("regression discontinuity",)),
    ("matching_or_weighting", ("matching", "propensity score", "inverse probability weight")),
    ("survival_or_event_history", ("survival", "event history", "cox proportional")),
)
# Other potential families that could be added in the future:
# factor_analysis_or_scale_model
# latent_variable_model
# bayesian_model
# nonparametric_or_permutation_test
# machine_learning_prediction
# structural_equation_model
# time_series_model
# spatial_model
# survey_weighted_design

_SINGLE_EQUATION_TERMS = (
    "single_equation",
    "regression",
    "probit",
    "logit",
    "logistic",
    "cloglog",
    "linear_probability",
    "glm",
    "generalized_linear",
    "ols",
    "ordinary_least_squares",
    "poisson",
    "negative_binomial",
)


def _normalize_family(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "not_stated"


def canonical_structural_method_family(value: Any) -> str:
    normalized = _normalize_family(value)
    text = normalized.replace("_", " ")
    for family, terms in _FAMILY_PATTERNS:
        if any(term in text for term in terms):
            return family
    if any(term.replace("_", " ") in text for term in _SINGLE_EQUATION_TERMS):
        return "single_equation_regression"
    return normalized


def infer_structural_method_family(path: dict[str, Any]) -> str:
    signature = path.get("path_signature", path)
    explicit = signature.get("structural_method_family") or path.get("structural_method_family")
    if explicit:
        return canonical_structural_method_family(explicit)

    text = " ".join(
        str(value or "")
        for value in (
            signature.get("model_family"),
            signature.get("variable_construction"),
            path.get("path_summary"),
        )
    ).lower()
    for family, terms in _FAMILY_PATTERNS:
        if any(term in text for term in terms):
            return family
    if any(term in text for term in _SINGLE_EQUATION_TERMS):
        return "single_equation_regression"
    return _normalize_family(signature.get("model_family"))


def covered_method_families(memory_data: dict[str, Any]) -> dict[str, list[str]]:
    coverage = {"Task1": set(), "Task2": set()}
    for record in memory_data.get("memory_records", []):
        for task_id, task_memory in record.get("tasks", {}).items():
            if task_id not in coverage:
                continue
            for candidate in task_memory.get("candidates", []):
                if candidate.get("status") not in _COVERED_STATUSES:
                    continue
                planned_path = candidate.get("planned_path")
                if isinstance(planned_path, dict):
                    coverage[task_id].add(infer_structural_method_family(planned_path))
                fixed_path = candidate.get("executor_fixed_path")
                if isinstance(fixed_path, dict):
                    coverage[task_id].add(infer_structural_method_family(fixed_path))
    return {task_id: sorted(families) for task_id, families in coverage.items()}


def analysis_decision_signature(path: dict[str, Any]) -> dict[str, Any]:
    signature = path.get("path_signature", path)
    return {
        field: _normalize_decision_value(signature.get(field))
        for field in _DECISION_FIELDS
    }


def task_analysis_decision_signature(task: dict[str, Any]) -> dict[str, Any]:
    analysis_path = task.get("analysis_path", {})
    key_choices = analysis_path.get("key_choices", {})
    variables = analysis_path.get("variables", {})
    estimand = task.get("method_quality", {}).get("estimand", {})
    controls = key_choices.get("control_variables")
    if controls is None:
        controls = [
            item.get("name", item) if isinstance(item, dict) else item
            for item in variables.get("controls", [])
        ]
    return analysis_decision_signature({
        "estimand_quantity": estimand.get("quantity"),
        "outcome": variables.get("outcome", {}).get(
            "name", key_choices.get("outcome_measure")
        ),
        "outcome_scale": estimand.get("outcome_scale"),
        "contrast": estimand.get("contrast"),
        "target_population": estimand.get("target_population"),
        "sample_restriction": key_choices.get("sample_restriction"),
        "missing_data_rule": key_choices.get("missing_data_rule"),
        "variable_construction": key_choices.get("data_processing"),
        "controls": controls or [],
    })


def covered_analysis_decisions(
    memory_data: dict[str, Any],
) -> dict[str, dict[str, list[Any]]]:
    coverage = {
        task_id: {field: [] for field in _DIVERSITY_FIELDS}
        for task_id in ("Task1", "Task2")
    }
    seen = {
        task_id: {field: set() for field in _DIVERSITY_FIELDS}
        for task_id in coverage
    }
    for record in memory_data.get("memory_records", []):
        for task_id, task_memory in record.get("tasks", {}).items():
            if task_id not in coverage:
                continue
            for candidate in task_memory.get("candidates", []):
                planned_path = candidate.get("planned_path")
                if not isinstance(planned_path, dict):
                    continue
                decision = analysis_decision_signature(planned_path)
                for field in _DIVERSITY_FIELDS:
                    value = decision[field]
                    if value in (None, [], ""):
                        continue
                    marker = repr(value)
                    if marker not in seen[task_id][field]:
                        coverage[task_id][field].append(value)
                        seen[task_id][field].add(marker)
    return coverage


def changed_analysis_decisions(
    task: dict[str, Any],
    prior_decisions: dict[str, list[Any]],
) -> list[str]:
    current = task_analysis_decision_signature(task)
    if not any(prior_decisions.values()):
        return list(_DIVERSITY_FIELDS)
    return [
        field
        for field in _DIVERSITY_FIELDS
        if current[field] not in prior_decisions.get(field, [])
    ]


def _normalize_decision_value(value: Any) -> Any:
    if isinstance(value, list):
        normalized = [_normalize_decision_value(item) for item in value]
        return sorted(normalized, key=repr)
    if isinstance(value, dict):
        return {
            key: _normalize_decision_value(item)
            for key, item in sorted(value.items())
        }
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value).strip().lower())


def normalize_family_novelty(
    plan_output: dict[str, Any],
    prior_coverage: dict[str, list[str]],
    generated_task_ids: list[str],
) -> list[tuple[str, str | None, str]]:
    corrections = []
    tasks = {task["task_id"]: task for task in plan_output["plan"]["tasks"]}
    for task_id in generated_task_ids:
        analysis_path = tasks[task_id]["analysis_path"]
        family = canonical_structural_method_family(
            analysis_path.get("structural_method_family")
        )
        expected = (
            "reused_no_defensible_alternative"
            if family in prior_coverage.get(task_id, [])
            else "untried"
        )
        current = analysis_path.get("family_novelty")
        if current != expected:
            analysis_path["family_novelty"] = expected
            corrections.append((task_id, current, expected))
    return corrections
