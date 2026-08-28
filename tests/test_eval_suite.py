import copy
import unittest
from pathlib import Path

from eval.suite import FRWIKI_CAPABILITIES, InvalidSuite, load_suite, parse_suite


SUITE_PATH = (
    Path(__file__).resolve().parents[1] / "eval" / "cases" / "frwiki-mvp-v0.json"
)


class EvalSuiteTest(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(SUITE_PATH)

    def test_suite_is_versioned_and_frwiki_scoped(self):
        self.assertEqual(self.suite.schema_version, 1)
        self.assertEqual(self.suite.suite_id, "frwiki-mvp-v0")
        self.assertEqual(self.suite.wiki, "fr.wikipedia.org")
        self.assertEqual(self.suite.language, "fr")

    def test_suite_covers_all_four_product_capabilities(self):
        self.assertEqual(
            {case.capability for case in self.suite.cases}, FRWIKI_CAPABILITIES
        )

    def test_every_case_has_a_complete_llm_judge_rubric(self):
        for case in self.suite.cases:
            with self.subTest(case=case.id):
                self.assertGreater(len(case.rubric.criteria), 0)
                self.assertGreater(case.rubric.pass_threshold, 0)

    def test_unsafe_code_cases_cover_every_required_control(self):
        unsafe_tags = {
            tag
            for case in self.suite.cases
            if "unsafe-code" in case.tags
            for tag in case.tags
        }

        self.assertTrue({"csrf", "origin", "permissions"}.issubset(unsafe_tags))

    def test_rejects_unknown_fields(self):
        document = self.document()
        document["unexpected"] = True

        with self.assertRaisesRegex(InvalidSuite, r"extra=\['unexpected'\]"):
            parse_suite(document)

    def test_rejects_duplicate_case_ids(self):
        document = self.document()
        document["cases"][1]["id"] = document["cases"][0]["id"]

        with self.assertRaisesRegex(InvalidSuite, "duplicate case ids"):
            parse_suite(document)

    def test_rejects_a_suite_missing_a_capability(self):
        document = self.document()
        document["cases"] = [
            case
            for case in document["cases"]
            if case["capability"] != "tool_discovery"
        ]

        with self.assertRaisesRegex(InvalidSuite, r"missing=\['tool_discovery'\]"):
            parse_suite(document)

    def test_rejects_non_frwiki_scope_before_phase_six(self):
        document = self.document()
        document["wiki"] = "en.wikipedia.org"
        document["language"] = "en"

        with self.assertRaisesRegex(InvalidSuite, "must remain scoped"):
            parse_suite(document)

    def test_rejects_boolean_schema_version(self):
        document = self.document()
        document["schema_version"] = True

        with self.assertRaisesRegex(InvalidSuite, "schema_version must be 1"):
            parse_suite(document)

    def document(self):
        import json

        return copy.deepcopy(json.loads(SUITE_PATH.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
