import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from extract import extract_paper
from server import database, handler_factory, payload_error, unlocked

FOLDER = Path(__file__).parents[1] / "data" / "Annotator-Test" / "Zunick_JournExpSocPsych_2017_zlw"
PART2 = {"claim_alignment": "Yes", "claim_alignment_explanation": "x", "method_validity": "Yes", "method_validity_explanation": "x"}
RESTRICTION = {"restriction_compliance": "Yes", "restriction_compliance_explanation": "x"}
PART3 = {"implementation_fidelity": "4", "implementation_fidelity_explanation": "x"}
PART4 = {"conclusion_validity": "5", "conclusion_validity_explanation": "x"}


class PayloadRulesTest(unittest.TestCase):
    def test_task2_requires_restriction_answer(self):
        self.assertIsNotNone(payload_error({}, {**PART2, "part2_submitted": True}, "Task2", True))
        self.assertIsNone(payload_error({}, {**PART2, **RESTRICTION, "part2_submitted": True}, "Task2", True))
        self.assertIsNone(payload_error({}, {**PART2, "part2_submitted": True}, "Task1", True))

    def test_task2_submitted_before_restriction_question_stays_valid(self):
        old = {**PART2, "part2_submitted": True}
        self.assertIsNone(payload_error(old, {**old, **PART3, "part3_submitted": True}, "Task2", True))

    def test_restriction_answer_locks_with_part2(self):
        old = {**PART2, **RESTRICTION, "part2_submitted": True}
        self.assertIn("cannot be changed", payload_error(old, {**old, "restriction_compliance": "No"}, "Task2", True))

    def test_part3_no_longer_needs_sample_question(self):
        old = {**PART2, "part2_submitted": True}
        self.assertIsNone(payload_error(old, {**old, **PART3, "part3_submitted": True}, "Task1", True))

    def test_code_reviewer_needs_part3_before_part4(self):
        old = {**PART2, "part2_submitted": True}
        self.assertIsNotNone(payload_error(old, {**old, **PART4, "part4_submitted": True}, "Task1", True))

    def test_non_reviewer_skips_part3(self):
        old = {**PART2, "part2_submitted": True}
        self.assertIsNone(payload_error(old, {**old, **PART4, "part4_submitted": True}, "Task1", False))
        self.assertIsNotNone(payload_error(old, {**old, **PART3, "part3_submitted": True}, "Task1", False))
        self.assertIsNotNone(payload_error({}, {**PART4, "part4_submitted": True}, "Task1", False))

    def test_unlocked(self):
        self.assertEqual(unlocked({}, True), (False, False))
        self.assertEqual(unlocked({"part2_submitted": True}, True), (True, False))
        self.assertEqual(unlocked({"part2_submitted": True, "part3_submitted": True}, True), (True, True))
        self.assertEqual(unlocked({"part2_submitted": True}, False), (False, True))


class ServerRoleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        db = Path(cls.temp.name) / "test.sqlite3"
        database(db).close()
        cls.packet = extract_paper(FOLDER)
        handler = handler_factory(cls.packet, db, "pw", "secret", "cr-aaaaaa,an-bbbbbb")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def request(self, path, body=None, cookie=None):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read()), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def login(self, name):
        status, _, headers = self.request("/api/login", {"annotator": name, "password": "pw"})
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";")[0]

    def save(self, cookie, analysis_id, payload):
        return self.request("/api/responses", {"annotator": "", "analysis_id": analysis_id, "payload": payload}, cookie)

    def analysis(self, cookie, analysis_id):
        _, packet, _ = self.request("/api/packet", cookie=cookie)
        return packet, next(a for a in packet["analyses"] if a["id"] == analysis_id)

    def file_status(self, cookie, relative, analysis_id):
        req = urllib.request.Request(f"{self.base}/files/{relative}?analysis={analysis_id}", headers={"Cookie": cookie})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def test_code_reviewer_flow(self):
        cookie = self.login("CR-AAAAAA")
        analysis_id = "1_test_02:Task2"
        code_path = next(a for a in self.packet["analyses"] if a["id"] == analysis_id)["files"]["code"]
        packet, analysis = self.analysis(cookie, analysis_id)
        self.assertTrue(packet["code_reviewer"])
        self.assertIsNone(analysis["files"]["code"])
        self.assertEqual(self.file_status(cookie, code_path, analysis_id), 403)

        self.assertEqual(self.save(cookie, analysis_id, {**PART2, "part2_submitted": True})[0], 409)
        self.assertEqual(self.save(cookie, analysis_id, {**PART2, **RESTRICTION, "part2_submitted": True})[0], 200)
        _, analysis = self.analysis(cookie, analysis_id)
        self.assertEqual(analysis["files"]["code"], code_path)
        self.assertEqual(analysis["execution"], {})
        self.assertEqual(self.file_status(cookie, code_path, analysis_id), 200)

        done = {**PART2, **RESTRICTION, "part2_submitted": True}
        self.assertEqual(self.save(cookie, analysis_id, {**done, **PART4, "part4_submitted": True})[0], 409)
        done = {**done, **PART3, "part3_submitted": True}
        self.assertEqual(self.save(cookie, analysis_id, done)[0], 200)
        _, analysis = self.analysis(cookie, analysis_id)
        self.assertNotEqual(analysis["execution"], {})
        self.assertEqual(self.save(cookie, analysis_id, {**done, **PART4, "part4_submitted": True})[0], 200)

    def test_non_reviewer_flow(self):
        cookie = self.login("an-bbbbbb")
        analysis_id = "1_test_01:Task1"
        code_path = next(a for a in self.packet["analyses"] if a["id"] == analysis_id)["files"]["code"]
        packet, analysis = self.analysis(cookie, analysis_id)
        self.assertFalse(packet["code_reviewer"])

        done = {**PART2, "part2_submitted": True}
        self.assertEqual(self.save(cookie, analysis_id, done)[0], 200)
        _, analysis = self.analysis(cookie, analysis_id)
        self.assertIsNone(analysis["files"]["code"])
        self.assertNotEqual(analysis["execution"], {})
        self.assertEqual(self.file_status(cookie, code_path, analysis_id), 403)
        self.assertEqual(self.save(cookie, analysis_id, {**done, **PART3, "part3_submitted": True})[0], 409)
        self.assertEqual(self.save(cookie, analysis_id, {**done, **PART4, "part4_submitted": True})[0], 200)


if __name__ == "__main__":
    unittest.main()
