import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.suite import EvalCase, EvalSuite, InvalidSuite

RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Assessment:
    case_id: str
    satisfied_criteria: frozenset[str]
    triggered_failure_conditions: frozenset[str]


@dataclass(frozen=True)
class BaselineCase:
    passed: bool
    score: int


@dataclass(frozen=True)
class Baseline:
    schema_version: int
    baseline_id: str
    baseline_kind: str
    suite_id: str
    overall_score: int
    cases: dict[str, BaselineCase]


def load_assessments(path: Path, suite: EvalSuite) -> tuple[Assessment, ...]:
    document = _load_json(path, "assessments")
    _exact_fields(
        document,
        {"schema_version", "suite_id", "assessments"},
        "assessments",
    )
    _validate_document_header(document, suite.suite_id, "assessments")
    raw_assessments = document["assessments"]
    if not isinstance(raw_assessments, list):
        raise InvalidSuite("assessments.assessments must be a list")
    cases_by_id = {case.id: case for case in suite.cases}
    assessments = tuple(
        _parse_assessment(raw, cases_by_id, index)
        for index, raw in enumerate(raw_assessments)
    )
    assessment_ids = [assessment.case_id for assessment in assessments]
    if len(assessment_ids) != len(set(assessment_ids)):
        raise InvalidSuite("assessments contains duplicate case ids")
    if set(assessment_ids) != set(cases_by_id):
        missing = sorted(set(cases_by_id) - set(assessment_ids))
        extra = sorted(set(assessment_ids) - set(cases_by_id))
        raise InvalidSuite(
            f"assessments must cover every suite case; missing={missing}, extra={extra}"
        )
    return assessments


def load_baseline(path: Path, suite: EvalSuite) -> Baseline:
    document = _load_json(path, "baseline")
    _exact_fields(
        document,
        {
            "schema_version",
            "baseline_id",
            "baseline_kind",
            "suite_id",
            "overall_score",
            "cases",
        },
        "baseline",
    )
    _validate_document_header(document, suite.suite_id, "baseline")
    baseline_id = _nonempty_string(document["baseline_id"], "baseline.baseline_id")
    baseline_kind = document["baseline_kind"]
    if baseline_kind not in {"deterministic_fixture", "live_liftwing"}:
        raise InvalidSuite(
            "baseline.baseline_kind must be deterministic_fixture or live_liftwing"
        )
    raw_cases = document["cases"]
    if not isinstance(raw_cases, dict):
        raise InvalidSuite("baseline.cases must be an object keyed by case id")
    suite_case_ids = {case.id for case in suite.cases}
    if set(raw_cases) != suite_case_ids:
        missing = sorted(suite_case_ids - set(raw_cases))
        extra = sorted(set(raw_cases) - suite_case_ids)
        raise InvalidSuite(
            f"baseline must cover every suite case; missing={missing}, extra={extra}"
        )
    cases = {
        case_id: _parse_baseline_case(raw_case, f"baseline.cases.{case_id}")
        for case_id, raw_case in raw_cases.items()
    }
    overall_score = _score(document["overall_score"], "baseline.overall_score")
    calculated_score = round(sum(case.score for case in cases.values()) / len(cases))
    if overall_score != calculated_score:
        raise InvalidSuite(
            f"baseline.overall_score must equal calculated score {calculated_score}"
        )
    return Baseline(
        RESULT_SCHEMA_VERSION,
        baseline_id,
        baseline_kind,
        suite.suite_id,
        overall_score,
        cases,
    )


def score_run(
    suite: EvalSuite,
    assessments: tuple[Assessment, ...],
    baseline: Baseline,
) -> dict[str, Any]:
    if baseline.suite_id != suite.suite_id:
        raise InvalidSuite("baseline suite id does not match eval suite")
    assessments_by_id = {assessment.case_id: assessment for assessment in assessments}
    if set(assessments_by_id) != {case.id for case in suite.cases}:
        raise InvalidSuite("assessments do not cover every eval case exactly once")

    case_results = [
        _score_case(case, assessments_by_id[case.id], baseline.cases[case.id])
        for case in suite.cases
    ]
    overall_score = round(
        sum(case_result["score"] for case_result in case_results) / len(case_results)
    )
    has_regression = any(case_result["regression"] for case_result in case_results)
    passed = all(case_result["passed"] for case_result in case_results)
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "suite_id": suite.suite_id,
        "baseline_id": baseline.baseline_id,
        "baseline_kind": baseline.baseline_kind,
        "passed": passed and not has_regression,
        "regression": has_regression,
        "overall_score": overall_score,
        "baseline_overall_score": baseline.overall_score,
        "cases": case_results,
    }


def _score_case(
    case: EvalCase,
    assessment: Assessment,
    baseline: BaselineCase,
) -> dict[str, Any]:
    score = round(100 * len(assessment.satisfied_criteria) / len(case.rubric.criteria))
    passed = (
        score >= case.rubric.pass_threshold
        and not assessment.triggered_failure_conditions
    )
    regression = score < baseline.score or (baseline.passed and not passed)
    return {
        "case_id": case.id,
        "capability": case.capability,
        "passed": passed,
        "score": score,
        "pass_threshold": case.rubric.pass_threshold,
        "triggered_failure_conditions": sorted(assessment.triggered_failure_conditions),
        "baseline_passed": baseline.passed,
        "baseline_score": baseline.score,
        "regression": regression,
    }


def _parse_assessment(
    raw_assessment: Any,
    cases_by_id: dict[str, EvalCase],
    index: int,
) -> Assessment:
    label = f"assessments.assessments[{index}]"
    assessment = _mapping(raw_assessment, label)
    _exact_fields(
        assessment,
        {"case_id", "satisfied_criteria", "triggered_failure_conditions"},
        label,
    )
    case_id = _nonempty_string(assessment["case_id"], f"{label}.case_id")
    case = cases_by_id.get(case_id)
    if case is None:
        raise InvalidSuite(f"{label}.case_id {case_id!r} is not in the eval suite")
    satisfied = _string_set(
        assessment["satisfied_criteria"], f"{label}.satisfied_criteria"
    )
    allowed_criteria = {criterion.id for criterion in case.rubric.criteria}
    unknown_criteria = sorted(satisfied - allowed_criteria)
    if unknown_criteria:
        raise InvalidSuite(f"{label} has unknown criteria {unknown_criteria}")
    triggered = _string_set(
        assessment["triggered_failure_conditions"],
        f"{label}.triggered_failure_conditions",
    )
    allowed_failures = {condition.id for condition in case.rubric.failure_conditions}
    unknown_failures = sorted(triggered - allowed_failures)
    if unknown_failures:
        raise InvalidSuite(f"{label} has unknown failure conditions {unknown_failures}")
    return Assessment(case_id, satisfied, triggered)


def _parse_baseline_case(raw_case: Any, label: str) -> BaselineCase:
    case = _mapping(raw_case, label)
    _exact_fields(case, {"passed", "score"}, label)
    if not isinstance(case["passed"], bool):
        raise InvalidSuite(f"{label}.passed must be a boolean")
    return BaselineCase(case["passed"], _score(case["score"], f"{label}.score"))


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidSuite(f"cannot load {label} {path}: {exc}") from exc
    return _mapping(document, label)


def _validate_document_header(
    document: dict[str, Any], suite_id: str, label: str
) -> None:
    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or schema_version != RESULT_SCHEMA_VERSION:
        raise InvalidSuite(f"{label}.schema_version must be {RESULT_SCHEMA_VERSION}")
    if document["suite_id"] != suite_id:
        raise InvalidSuite(f"{label}.suite_id must match {suite_id}")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidSuite(f"{label} must be an object")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise InvalidSuite(
            f"{label} fields are invalid; missing={missing}, extra={extra}"
        )


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidSuite(f"{label} must be a non-empty string")
    return value


def _string_set(value: Any, label: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise InvalidSuite(f"{label} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise InvalidSuite(f"{label} contains duplicates")
    return frozenset(value)


def _score(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise InvalidSuite(f"{label} must be an integer between 0 and 100")
    return value
