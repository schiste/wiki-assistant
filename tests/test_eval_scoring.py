import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from eval.scoring import load_assessments, load_baseline, score_run
from eval.suite import InvalidSuite, load_suite


REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = REPO_ROOT / "eval" / "cases" / "frwiki-mvp-v0.json"
BASELINE_PATH = REPO_ROOT / "eval" / "baselines" / "frwiki-mvp-v0.json"
FIXTURE_PATH = REPO_ROOT / "eval" / "fixtures" / "frwiki-mvp-v0-known-good.json"


class EvalScoringTest(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(SUITE_PATH)
        self.baseline = load_baseline(BASELINE_PATH, self.suite)

    def test_known_good_fixture_matches_the_versioned_baseline(self):
        assessments = load_assessments(FIXTURE_PATH, self.suite)

        report = score_run(self.suite, assessments, self.baseline)

        self.assertTrue(report["passed"])
        self.assertFalse(report["regression"])
        self.assertEqual(report["overall_score"], 100)
        self.assertEqual(report["baseline_overall_score"], 100)
        self.assertTrue(all(case["score"] == 100 for case in report["cases"]))

    def test_any_score_drop_is_reported_as_a_regression(self):
        document = self.fixture_document()
        document["assessments"][0]["satisfied_criteria"].pop()

        assessments = self.load_temporary_assessments(document)
        report = score_run(self.suite, assessments, self.baseline)
        changed = report["cases"][0]

        self.assertEqual(changed["score"], 75)
        self.assertTrue(changed["passed"])
        self.assertTrue(changed["regression"])
        self.assertFalse(report["passed"])

    def test_failure_condition_forces_a_failure_at_full_score(self):
        document = self.fixture_document()
        coding_case = next(
            assessment
            for assessment in document["assessments"]
            if assessment["case_id"] == "coding-preserve-csrf"
        )
        coding_case["triggered_failure_conditions"] = ["actionable-csrf-bypass"]

        assessments = self.load_temporary_assessments(document)
        report = score_run(self.suite, assessments, self.baseline)
        changed = next(
            case
            for case in report["cases"]
            if case["case_id"] == "coding-preserve-csrf"
        )

        self.assertEqual(changed["score"], 100)
        self.assertFalse(changed["passed"])
        self.assertTrue(changed["regression"])

    def test_rejects_unknown_judge_criterion(self):
        document = self.fixture_document()
        document["assessments"][0]["satisfied_criteria"].append("invented-criterion")

        with self.assertRaisesRegex(InvalidSuite, "unknown criteria"):
            self.load_temporary_assessments(document)

    def test_rejects_unknown_baseline_provenance(self):
        document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        document["baseline_kind"] = "unreviewed_live_run"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(InvalidSuite, "baseline_kind"):
                load_baseline(path, self.suite)

    def test_cli_emits_a_comparable_report_without_network_access(self):
        result = subprocess.run(
            [
                "python3",
                "-m",
                "eval.run",
                "--assessments",
                str(FIXTURE_PATH),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["suite_id"], "frwiki-mvp-v0")
        self.assertEqual(report["baseline_id"], "frwiki-mvp-v0-deterministic-1")
        self.assertEqual(report["baseline_kind"], "deterministic_fixture")
        self.assertTrue(report["passed"])

    def fixture_document(self):
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def load_temporary_assessments(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assessments.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_assessments(path, self.suite)


if __name__ == "__main__":
    unittest.main()
