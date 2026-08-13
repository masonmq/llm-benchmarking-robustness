import ast
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from robustness.memory.shared_memory import (
    accumulate_prune_output,
    apply_pruning_decisions,
    build_memory_record_from_execution_results,
    build_memory_record_from_prune_output,
    build_prune_audit_update,
    candidate_artifact_dir,
    extract_pruning_decisions,
    load_case_memory,
    missing_analysis_code_files,
    normalize_planning_output,
    route_after_pruning,
    update_memory_record,
    validate_execution_ready,
)


CASE_ID = "Example_Paper_2026_abcd"
PRUNE_CHECKS = (
    "same_focal_claim",
    "same_dataset",
    "not_duplicate",
    "task_completeness",
    "estimand_alignment",
    "variable_support",
    "sample_audit",
    "restriction_justification",
    "control_justification",
    "focal_variable_structure",
    "plan_code_consistency",
    "method_justification",
    "executable_in_principle",
)


def make_anchor(task_id):
    return {
        "task_id": task_id,
        "estimand": {
            "outcome": "outcome",
            "outcome_scale": "raw outcome units",
            "contrast": "one-unit predictor contrast",
            "target_population": "authorized sample",
            "time_scope": "NA",
        },
        "sample_definition": {
            "scope": "full_sample",
            "inclusion_rules": ["Use authorized rows."],
            "exclusion_rules": [],
        },
        "reference_specification": {
            "model_family": "linear_regression",
            "variable_construction": "Use verified outcome and predictor columns.",
            "controls": [],
            "fixed_effects": [],
            "uncertainty_method": "ordinary standard errors",
        },
        "conclusion_rule": {
            "expected_direction": "positive",
            "statistical_threshold": "not_stated",
            "support_rule": "Classify by direction and report uncertainty separately.",
        },
        "evidence": {
            "paper": "Focal claim section.",
            "dataset_mapping": "Verified outcome and predictor columns.",
        },
        "uncertainties": [],
    }


def make_task(task_id, description):
    return {
        "task_id": task_id,
        "task_role": "conclusion_oriented_reanalysis" if task_id == "Task1" else "comparable_result_oriented_reanalysis",
        "analysis_path": {
            "path_name": description,
            "path_description": description,
            "model_family": "linear_regression",
            "key_choices": {
                "outcome_measure": "outcome",
                "main_predictor_measure": "predictor",
                "control_variables": [],
                "sample_restriction": None,
                "missing_data_rule": "complete cases",
                "data_processing": description,
                "inference_rule": (
                    "Support when the estimate follows the expected direction; "
                    "p < 0.05 means strong support."
                ),
            },
            "variables": {
                "outcome": {"name": "outcome"},
                "main_predictor": {"name": "predictor"},
                "controls": [],
            },
        },
        "analysis_code": {
            "available": "true",
            "code_files": [f"{task_id.lower()}.py"],
            "entry_file": f"{task_id.lower()}.py",
            "run_command": f"python {task_id.lower()}.py",
        },
        "method_quality": {
            "estimand": {
                "quantity": "predictor coefficient",
                "outcome_scale": "raw outcome units",
                "contrast": "one-unit predictor contrast",
                "target_population": "authorized sample",
                "time_scope": "NA",
                "claim_mapping": "Directly estimates the focal association.",
            },
            "anchor_alignment": {
                dimension: {
                    "status": "aligned",
                    "note": f"The candidate {dimension} follows the task anchor.",
                }
                for dimension in ("outcome", "contrast", "sample", "model", "inference")
            } | {"deviations": []},
            "evidence_basis": {
                "outcome": "Focal claim and verified outcome column.",
                "main_predictor": "Focal claim and verified predictor column.",
                "controls": [],
                "restrictions": [],
            },
            "sample_audit": {
                "starting_sample_size": "not_stated",
                "inclusion_rules": ["Use authorized rows."],
                "exclusion_rules": [],
                "code_reports_sample_flow": True,
            },
            "focal_variable_structure": {
                "source_structure": "continuous",
                "analysis_structure": "continuous",
                "information_loss": "none",
                "justification": "Preserves the measured structure.",
            },
            "code_preflight": {
                "referenced_columns": ["outcome", "predictor"],
                "missing_columns": [],
                "plan_code_consistency": "pass",
                "preflight_note": "Columns and model match the plan.",
            },
        },
    }


def make_plan(task1_description="task1 initial", task2_description="task2 initial"):
    return {
        "case": {"case_id": CASE_ID, "focal_claim": "Example claim"},
        "tasks_info": [
            {"task_id": "Task1", "task_instruction": "Task 1 instruction"},
            {"task_id": "Task2", "task_instruction": "Task 2 instruction"},
        ],
        "datasets": {"authorized_only": True, "files": [{"file_path": "data/example.csv"}]},
        "analysis_anchors": [make_anchor("Task1"), make_anchor("Task2")],
        "plan": {
            "planned_id": "agent-placeholder",
            "path_summary": "combined path",
            "path_signature": {},
            "tasks": [
                make_task("Task1", task1_description),
                make_task("Task2", task2_description),
            ],
        },
        "execution_directives": {"debugging_rule": {"max_repair_attempts": 2}},
    }


def make_prune_output(schema, decisions):
    tasks = {task["task_id"]: task for task in schema["plan"]["tasks"]}
    task_records = {}
    for task_id in ("Task1", "Task2"):
        candidates = []
        if task_id in decisions:
            candidates.append({
                "candidate_id": tasks[task_id]["candidate_id"],
                "planning_pruning_iteration": schema["iteration"],
                "candidate_snapshot": {},
                "decision": decisions[task_id],
                "decision_summary": f"{task_id} was {decisions[task_id]}",
                "check_results": {
                    name: {
                        "status": (
                            "fail"
                            if decisions[task_id] == "low-quality" and name == "method_justification"
                            else "pass"
                        ),
                        "note": "ok",
                    }
                    for name in PRUNE_CHECKS
                },
            })
        task_records[task_id.lower()] = {"candidates": candidates}
    return {
        "pruning_output": {
            "case_id": CASE_ID,
            "paper_id": CASE_ID,
            "task_pair_records": [{
                "path_id": schema["plan"]["planned_id"],
                "tasks": task_records,
                "task_pair_assessment": {},
            }],
        }
    }


def initial_schema():
    return normalize_planning_output(
        make_plan(),
        case_id=CASE_ID,
        memory_data={"case_id": CASE_ID, "memory_records": []},
        iteration=1,
    )


class SequentialPipelineTests(unittest.TestCase):
    def test_conclusion_classification_supports_only_affirmative_or_borderline_evidence(self):
        constants_path = Path(__file__).parents[1] / "core" / "constants.py"
        module = ast.parse(constants_path.read_text(encoding="utf-8"))
        conclusion_rules = next(
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "CONCLUSION_CLASSIFICATION_RULES"
                for target in node.targets
            )
        )
        self.assertIn(
            "p greater than 0.05 and less than or equal to 0.055",
            conclusion_rules["support"],
        )
        self.assertIn(
            "p greater than 0.055 is inconclusive",
            conclusion_rules["inconclusive"],
        )
        self.assertIn(
            "An opposite-signed point estimate alone is not enough",
            conclusion_rules["opposite"],
        )
        self.assertIn(
            "describe it as borderline",
            conclusion_rules["statistical_strength"],
        )

    def test_all_agent_prompts_receive_fixed_conclusion_rules(self):
        project_dir = Path(__file__).parents[1]
        for relative_path in (
            "planner/plan_agent.py",
            "pruning/prune_agent.py",
            "executor/execute_agent.py",
        ):
            source = (project_dir / relative_path).read_text(encoding="utf-8")
            self.assertIn("CONCLUSION_CLASSIFICATION_RULES", source)

        execution_source = (project_dir / "executor/execute_agent.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "0.05 < p <= 0.055 remains support",
            execution_source,
        )

    def test_initial_planning_assigns_ids_and_null_statuses(self):
        schema = initial_schema()
        tasks = {task["task_id"]: task for task in schema["plan"]["tasks"]}
        self.assertEqual(schema["plan"]["planned_id"], f"{CASE_ID}_path01")
        self.assertEqual(tasks["Task1"]["candidate_id"], "Task1_candidate01")
        self.assertEqual(tasks["Task2"]["candidate_id"], "Task2_candidate01")
        self.assertIsNone(tasks["Task1"]["status"])
        self.assertIsNone(tasks["Task2"]["status"])

    def test_planning_requires_task_analysis_anchors(self):
        plan = make_plan()
        del plan["analysis_anchors"]
        with self.assertRaisesRegex(ValueError, "missing analysis_anchors"):
            normalize_planning_output(
                plan,
                case_id=CASE_ID,
                memory_data={"case_id": CASE_ID, "memory_records": []},
                iteration=1,
            )

    def test_planning_code_files_are_isolated_by_candidate(self):
        with TemporaryDirectory() as temp_dir:
            schema = normalize_planning_output(
                make_plan(),
                case_id=CASE_ID,
                memory_data={"case_id": CASE_ID, "memory_records": []},
                iteration=1,
                study_path=temp_dir,
            )
            tasks = {task["task_id"]: task for task in schema["plan"]["tasks"]}
            task1_dir = candidate_artifact_dir(
                schema["plan"]["planned_id"], "Task1", "Task1_candidate01"
            )
            task2_dir = candidate_artifact_dir(
                schema["plan"]["planned_id"], "Task2", "Task2_candidate01"
            )
            self.assertEqual(tasks["Task1"]["analysis_code"]["artifact_dir"], task1_dir)
            self.assertEqual(tasks["Task2"]["analysis_code"]["artifact_dir"], task2_dir)
            self.assertEqual(tasks["Task1"]["analysis_code"]["entry_file"], f"{task1_dir}/task1.py")
            self.assertEqual(tasks["Task2"]["analysis_code"]["entry_file"], f"{task2_dir}/task2.py")
            self.assertEqual(
                missing_analysis_code_files(schema, temp_dir),
                [f"{task1_dir}/task1.py", f"{task2_dir}/task2.py"],
            )

            Path(temp_dir, task1_dir, "task1.py").write_text("print('task1')\n", encoding="utf-8")
            Path(temp_dir, task2_dir, "task2.py").write_text("print('task2')\n", encoding="utf-8")
            self.assertEqual(missing_analysis_code_files(schema, temp_dir), [])

    def test_all_pruning_routes_and_loop_limit(self):
        scenarios = [
            ("high-quality", "high-quality", 1, "execution"),
            ("high-quality", "low-quality", 1, "planning"),
            ("low-quality", "high-quality", 1, "planning"),
            ("low-quality", "low-quality", 1, "planning"),
            ("high-quality", "low-quality", 5, "planning_pruning_limit_reached"),
            ("low-quality", "high-quality", 5, "planning_pruning_limit_reached"),
            ("low-quality", "low-quality", 5, "planning_pruning_limit_reached"),
        ]
        for task1_status, task2_status, completed_loops, expected in scenarios:
            with self.subTest(task1=task1_status, task2=task2_status, loops=completed_loops):
                schema = initial_schema()
                for task in schema["plan"]["tasks"]:
                    task["status"] = task1_status if task["task_id"] == "Task1" else task2_status
                self.assertEqual(route_after_pruning(schema, completed_loops, 5), expected)

    def test_only_low_quality_task_is_regenerated(self):
        with TemporaryDirectory() as temp_dir:
            schema = normalize_planning_output(
                make_plan(),
                case_id=CASE_ID,
                memory_data={"case_id": CASE_ID, "memory_records": []},
                iteration=1,
                study_path=temp_dir,
            )
            self._assert_only_task2_is_regenerated(schema, temp_dir)

    def _assert_only_task2_is_regenerated(self, schema, temp_dir):
        first_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "low-quality"})
        decisions = extract_pruning_decisions(first_output, schema)
        reviewed = apply_pruning_decisions(schema, decisions)
        memory = update_memory_record(
            {"case_id": CASE_ID, "memory_records": []},
            build_memory_record_from_prune_output(schema, first_output, iteration=1),
        )
        old_tasks = {task["task_id"]: copy.deepcopy(task) for task in reviewed["plan"]["tasks"]}
        replacement_plan = make_plan("agent tried to replace task1", "task2 replacement")
        replacement_plan["analysis_anchors"][0]["estimand"]["outcome"] = "changed anchor"
        replacement_plan["analysis_anchors"][1]["estimand"]["outcome"] = "corrected task2 anchor"
        regenerated = normalize_planning_output(
            replacement_plan,
            case_id=CASE_ID,
            memory_data=memory,
            iteration=2,
            previous_schema=reviewed,
            study_path=temp_dir,
        )
        new_tasks = {task["task_id"]: task for task in regenerated["plan"]["tasks"]}
        new_anchors = {
            anchor["task_id"]: anchor for anchor in regenerated["analysis_anchors"]
        }
        old_anchors = {
            anchor["task_id"]: anchor for anchor in schema["analysis_anchors"]
        }
        self.assertEqual(new_tasks["Task1"], old_tasks["Task1"])
        self.assertEqual(new_anchors["Task1"], old_anchors["Task1"])
        self.assertEqual(
            new_anchors["Task2"]["estimand"]["outcome"],
            "corrected task2 anchor",
        )
        self.assertEqual(new_tasks["Task2"]["candidate_id"], "Task2_candidate02")
        self.assertIsNone(new_tasks["Task2"]["status"])
        self.assertEqual(new_tasks["Task2"]["analysis_path"]["path_description"], "task2 replacement")
        self.assertEqual(
            new_tasks["Task1"]["analysis_code"],
            old_tasks["Task1"]["analysis_code"],
        )
        expected_dir = candidate_artifact_dir(
            schema["plan"]["planned_id"], "Task2", "Task2_candidate02"
        )
        self.assertEqual(new_tasks["Task2"]["analysis_code"]["artifact_dir"], expected_dir)
        self.assertTrue(Path(temp_dir, expected_dir).is_dir())

    def test_pruning_audit_accumulates_once_per_candidate(self):
        schema = initial_schema()
        first_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "low-quality"})
        first_decisions = extract_pruning_decisions(first_output, schema)
        accumulated = accumulate_prune_output(
            None,
            build_prune_audit_update(schema, first_decisions, iteration=1),
        )
        memory = update_memory_record(
            {"case_id": CASE_ID, "memory_records": []},
            build_memory_record_from_prune_output(schema, first_output, iteration=1),
        )
        task1_memory = memory["memory_records"][0]["tasks"]["Task1"]["candidates"][0]
        task2_memory = memory["memory_records"][0]["tasks"]["Task2"]["candidates"][0]
        self.assertEqual(task1_memory["pruning_review"]["issues"], [])
        self.assertEqual(
            task2_memory["pruning_review"]["issues"],
            [{"check": "method_justification", "note": "ok"}],
        )
        self.assertNotIn("reason", task2_memory["pruning_review"])
        self.assertNotIn("check_results", task2_memory["pruning_review"])
        reviewed = apply_pruning_decisions(schema, first_decisions)
        regenerated = normalize_planning_output(
            make_plan("ignored", "task2 replacement"),
            case_id=CASE_ID,
            memory_data=memory,
            iteration=2,
            previous_schema=reviewed,
        )
        second_output = make_prune_output(regenerated, {"Task2": "high-quality"})
        second_decisions = extract_pruning_decisions(second_output, regenerated)
        second_audit = build_prune_audit_update(regenerated, second_decisions, iteration=2)
        accumulated = accumulate_prune_output(accumulated, second_audit)
        accumulated = accumulate_prune_output(accumulated, second_audit)
        record = accumulated["pruning_output"]["task_pair_records"][0]
        self.assertEqual(len(accumulated["pruning_output"]["task_pair_records"]), 1)
        self.assertEqual(len(record["tasks"]["task1"]["candidates"]), 1)
        self.assertEqual(len(record["tasks"]["task2"]["candidates"]), 2)
        self.assertEqual(record["task_pair_assessment"]["decision"], "high-quality")
        self.assertEqual(record["task_pair_assessment"]["task2_candidate_id"], "Task2_candidate02")
        self.assertEqual(
            record["tasks"]["task2"]["candidates"][1]["candidate_snapshot"]["analysis_anchor"]["task_id"],
            "Task2",
        )

    def test_execution_preserves_plans_and_records_fixed_path(self):
        schema = initial_schema()
        prune_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "high-quality"})
        decisions = extract_pruning_decisions(prune_output, schema)
        approved = apply_pruning_decisions(schema, decisions)
        memory = update_memory_record(
            {"case_id": CASE_ID, "memory_records": []},
            build_memory_record_from_prune_output(schema, prune_output, iteration=1),
        )
        validate_execution_ready(approved, memory)
        execution_results = {
            "execution_overview": {"overall_execution_status": "partial_success"},
            "task_outputs": [
                {
                    "task_id": "Task1",
                    "candidate_id": "Task1_candidate01",
                    "execution_status": "success",
                    "executed_analysis": {"path_name": "task1 fixed"},
                    "method_fidelity": {
                        "fidelity_note": "Fixed a file path without changing the method.",
                        "deviations": [{"description": "Used the mounted data path."}],
                    },
                    "failure": {"failure_reason": None},
                },
                {
                    "task_id": "Task2",
                    "candidate_id": "Task2_candidate01",
                    "execution_status": "failure",
                    "method_fidelity": {"deviations": []},
                    "failure": {"failure_reason": "Failed after repairs."},
                },
            ],
        }
        execution_update = build_memory_record_from_execution_results(approved, execution_results)
        updated = update_memory_record(memory, execution_update)
        updated = update_memory_record(updated, execution_update)
        record = updated["memory_records"][0]
        task1 = record["tasks"]["Task1"]["candidates"][0]
        task2 = record["tasks"]["Task2"]["candidates"][0]
        self.assertEqual(task1["status"], "executed_success")
        self.assertEqual(task2["status"], "execution_failed")
        self.assertEqual(task1["planned_path"]["path_summary"], "task1 initial")
        self.assertEqual(task1["planned_path"]["anchor_alignment"]["outcome"], "aligned")
        self.assertNotIn("analysis_anchor", task1["planned_path"])
        self.assertNotIn("analysis_path", task1["planned_path"])
        self.assertNotIn("method_quality", task1["planned_path"])
        self.assertEqual(task1["executor_fixed_path"]["changes"], ["Used the mounted data path."])
        self.assertIsNone(task2["executor_fixed_path"])
        self.assertEqual(
            task2["execution_result"]["status_reason"],
            "Failed after repairs.",
        )
        self.assertNotIn("output", task2["execution_result"])
        self.assertEqual(len(record["execution_runs"]), 1)
        self.assertEqual(record["execution_runs"][0]["status"], "execution_failed")

    def test_run_execute_writes_final_results_to_case_memory(self):
        from robustness.executor import execute_agent

        schema = initial_schema()
        prune_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "high-quality"})
        decisions = extract_pruning_decisions(prune_output, schema)
        approved = apply_pruning_decisions(schema, decisions)
        memory = update_memory_record(
            {"case_id": CASE_ID, "memory_records": []},
            build_memory_record_from_prune_output(schema, prune_output, iteration=1),
        )
        execution_results = {
            "execution_overview": {"overall_execution_status": "success"},
            "task_outputs": [
                {
                    "task_id": task_id,
                    "candidate_id": f"{task_id}_candidate01",
                    "execution_status": "success",
                    "executed_analysis": {"path_name": f"{task_id} executed"},
                    "method_fidelity": {
                        "fidelity_note": f"{task_id} completed after a code repair.",
                        "deviations": [{"description": f"Repaired {task_id} code."}],
                    },
                    "failure": {"failure_reason": None},
                }
                for task_id in ("Task1", "Task2")
            ],
        }

        with TemporaryDirectory() as temp_dir:
            study_dir = Path(temp_dir)
            templates_dir = study_dir / "templates"
            templates_dir.mkdir()
            (study_dir / "universal_schema.json").write_text(
                json.dumps(approved), encoding="utf-8"
            )
            (study_dir / f"shared_memory_{CASE_ID}.json").write_text(
                json.dumps(memory), encoding="utf-8"
            )
            (templates_dir / "execute_out_schema.json").write_text("{}", encoding="utf-8")

            captured = {}

            def finish_execution(*args, on_final, **kwargs):
                captured["instruction"] = args[3]
                on_final(execution_results)
                return execution_results

            with (
                patch.object(execute_agent, "configure_file_logging"),
                patch.object(execute_agent, "run_react_loop", side_effect=finish_execution),
            ):
                result = execute_agent.run_execute(
                    str(study_dir),
                    templates_dir=str(templates_dir),
                )

            saved_memory = json.loads(
                (study_dir / f"shared_memory_{CASE_ID}.json").read_text(encoding="utf-8")
            )
            record = saved_memory["memory_records"][0]
            self.assertTrue(result["memory_updated"])
            self.assertEqual(result["pipeline_outcome"], "execution_complete")
            self.assertEqual(
                record["tasks"]["Task1"]["candidates"][0]["status"],
                "executed_success",
            )
            self.assertEqual(
                record["tasks"]["Task2"]["candidates"][0]["status"],
                "executed_success",
            )
            self.assertEqual(record["execution_runs"][0]["status"], "executed_success")
            self.assertIn(
                "0.05 < p <= 0.055 remains support",
                captured["instruction"],
            )
            self.assertIn(
                "Clearly weak aligned evidence is inconclusive",
                captured["instruction"],
            )

    def test_case_memory_rejects_flat_records(self):
        with TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / f"shared_memory_{CASE_ID}.json"
            memory_path.write_text(
                json.dumps({
                    "case_id": CASE_ID,
                    "memory_records": [{"path_id": f"{CASE_ID}_path01", "status": "high-quality"}],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "task-candidate format"):
                load_case_memory(CASE_ID, temp_dir)

    def test_pruning_requires_all_method_quality_checks(self):
        schema = initial_schema()
        prune_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "high-quality"})
        candidate = prune_output["pruning_output"]["task_pair_records"][0]["tasks"]["task1"]["candidates"][0]
        del candidate["check_results"]["not_duplicate"]
        with self.assertRaisesRegex(ValueError, "missing checks: not_duplicate"):
            extract_pruning_decisions(prune_output, schema)

    def test_pruning_rejects_high_quality_when_a_check_fails(self):
        schema = initial_schema()
        prune_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "high-quality"})
        candidate = prune_output["pruning_output"]["task_pair_records"][0]["tasks"]["task1"]["candidates"][0]
        candidate["check_results"]["estimand_alignment"]["status"] = "fail"
        with self.assertRaisesRegex(ValueError, "high-quality with failed checks: estimand_alignment"):
            extract_pruning_decisions(prune_output, schema)

    def test_pruning_rejects_high_quality_when_preflight_evidence_fails(self):
        schema = initial_schema()
        schema["plan"]["tasks"][0]["method_quality"]["code_preflight"]["missing_columns"] = [
            "invented_control"
        ]
        prune_output = make_prune_output(schema, {"Task1": "high-quality", "Task2": "high-quality"})
        with self.assertRaisesRegex(ValueError, "method-quality evidence failed: variable_support"):
            extract_pruning_decisions(prune_output, schema)

    def test_planning_requires_method_quality_evidence(self):
        plan = make_plan()
        del plan["plan"]["tasks"][0]["method_quality"]
        with self.assertRaisesRegex(ValueError, "Task1 is missing method_quality"):
            normalize_planning_output(
                plan,
                case_id=CASE_ID,
                memory_data={"case_id": CASE_ID, "memory_records": []},
                iteration=1,
            )

    def test_planning_requires_boolean_sample_flow_evidence(self):
        plan = make_plan()
        sample_audit = plan["plan"]["tasks"][0]["method_quality"]["sample_audit"]
        sample_audit["code_reports_sample_flow"] = "true only when code reports sample flow"
        with self.assertRaisesRegex(ValueError, "code_reports_sample_flow must be a Boolean"):
            normalize_planning_output(
                plan,
                case_id=CASE_ID,
                memory_data={"case_id": CASE_ID, "memory_records": []},
                iteration=1,
            )

    def test_planning_requires_a_record_for_each_anchor_deviation(self):
        plan = make_plan()
        alignment = plan["plan"]["tasks"][0]["method_quality"]["anchor_alignment"]
        alignment["sample"] = {
            "status": "justified_deviation",
            "note": "Use a supported subgroup.",
        }
        with self.assertRaisesRegex(ValueError, "requires a matching deviation record"):
            normalize_planning_output(
                plan,
                case_id=CASE_ID,
                memory_data={"case_id": CASE_ID, "memory_records": []},
                iteration=1,
            )

    def test_planning_accepts_a_documented_anchor_deviation(self):
        plan = make_plan()
        alignment = plan["plan"]["tasks"][0]["method_quality"]["anchor_alignment"]
        alignment["sample"] = {
            "status": "justified_deviation",
            "note": "Use the paper-defined subgroup for this robustness path.",
        }
        alignment["deviations"].append({
            "dimension": "sample",
            "anchor_choice": "full authorized sample",
            "candidate_choice": "paper-defined subgroup",
            "justification": "The subgroup is explicitly tied to the task instruction.",
        })
        schema = normalize_planning_output(
            plan,
            case_id=CASE_ID,
            memory_data={"case_id": CASE_ID, "memory_records": []},
            iteration=1,
        )
        task1 = next(task for task in schema["plan"]["tasks"] if task["task_id"] == "Task1")
        self.assertEqual(
            task1["method_quality"]["anchor_alignment"]["sample"]["status"],
            "justified_deviation",
        )

    def test_execution_rejects_wrong_candidate_id(self):
        schema = initial_schema()
        for task in schema["plan"]["tasks"]:
            task["status"] = "high-quality"
        execution_results = {
            "task_outputs": [
                {
                    "task_id": "Task1",
                    "candidate_id": "Task1_candidate99",
                    "execution_status": "success",
                    "method_fidelity": {"deviations": []},
                    "failure": {"failure_reason": None},
                },
                {
                    "task_id": "Task2",
                    "candidate_id": "Task2_candidate01",
                    "execution_status": "success",
                    "method_fidelity": {"deviations": []},
                    "failure": {"failure_reason": None},
                },
            ]
        }
        with self.assertRaisesRegex(ValueError, "does not match the active candidate"):
            build_memory_record_from_execution_results(schema, execution_results)


if __name__ == "__main__":
    unittest.main()
