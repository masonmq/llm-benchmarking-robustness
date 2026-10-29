import tempfile
import unittest
from pathlib import Path

from extract import extract_paper
from preview import preview_file
from build_pages import build


class ExtractRealFixtureTest(unittest.TestCase):
    def test_zunick_has_five_runs_and_drops_duplicate_task1(self):
        folder = Path(__file__).parents[1] / "data" / "Annotator-Test" / "Zunick_JournExpSocPsych_2017_zlw"
        packet = extract_paper(folder)
        # Runs 4 and 5 give identical Task 1 and Task 2 results; Task 1 is dropped (Task 2 keeps the restriction question).
        self.assertEqual(packet["analysis_count"], 8)
        self.assertEqual([d["dropped"] for d in packet["dropped_duplicates"]], ["1_test_04:Task1", "1_test_05:Task1"])
        self.assertEqual({a["task_id"] for a in packet["analyses"]}, {"Task1", "Task2"})
        self.assertEqual(packet["analyses"][0]["display_name"], "Analysis A — Task 1")
        self.assertEqual(packet["analyses"][1]["display_name"], "Analysis A — Task 2")
        self.assertEqual(packet["analyses"][-1]["display_name"], "Analysis E — Task 2")
        for analysis in packet["analyses"]:
            self.assertIn("automated_checks", analysis)
            self.assertIn("conclusion", analysis["execution"])
            self.assertTrue(analysis["execution"]["runner_ok"])
            self.assertEqual(analysis["execution"]["runner_exit_code"], 0)
            self.assertIsNotNone(analysis["execution"]["runner_stdout"])
            self.assertIn("consistency_checks", analysis["execution"])
            self.assertIsInstance(analysis["execution"]["potential_result_mismatch"], bool)
            review = analysis["plan"]["review"]
            self.assertIsNotNone(review["quantity"])
            self.assertIsNotNone(review["outcome"])
            self.assertIsNotNone(review["model_type"])
            self.assertIsNotNone(review["formula"])
        mismatches = [analysis for analysis in packet["analyses"] if analysis["execution"]["potential_result_mismatch"]]
        self.assertEqual([analysis["id"] for analysis in mismatches], ["1_test_03:Task2"])
        failed_fields = [check["field"] for check in mismatches[0]["execution"]["consistency_checks"] if check["status"] == "fail"]
        self.assertEqual(failed_fields, ["standard error"])

    def test_json_and_code_previews(self):
        folder = Path(__file__).parents[1] / "data" / "Annotator-Test" / "Zunick_JournExpSocPsych_2017_zlw" / "1_test_01"
        self.assertEqual(preview_file(folder / "universal_schema.json")["viewer"], "json")
        code = next((folder / "candidate_artifacts").rglob("*.py"))
        self.assertEqual(preview_file(code)["viewer"], "code")

    def test_pages_build_keeps_research_files_private(self):
        folder = Path(__file__).parents[1] / "data" / "Annotator-Test" / "Zunick_JournExpSocPsych_2017_zlw"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build(folder, root / "site", root / "private", "https://api.example", 1)
            self.assertTrue((root / "site" / "index.html").is_file())
            self.assertFalse(any((root / "site").rglob("*.sav")))
            self.assertTrue(any((root / "private").rglob("*.sav")))


if __name__ == "__main__":
    unittest.main()
