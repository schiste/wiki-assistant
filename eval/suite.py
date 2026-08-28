import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
FRWIKI_CAPABILITIES = frozenset(
    {"policy_navigation", "template_help", "coding_help", "tool_discovery"}
)
CASE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class InvalidSuite(ValueError):
    pass


@dataclass(frozen=True)
class RubricItem:
    id: str
    description: str


@dataclass(frozen=True)
class JudgeRubric:
    pass_threshold: int
    criteria: tuple[RubricItem, ...]
    failure_conditions: tuple[RubricItem, ...]


@dataclass(frozen=True)
class EvalCase:
    id: str
    capability: str
    tags: tuple[str, ...]
    prompt: str
    rubric: JudgeRubric


@dataclass(frozen=True)
class EvalSuite:
    schema_version: int
    suite_id: str
    wiki: str
    language: str
    cases: tuple[EvalCase, ...]


def load_suite(path: Path) -> EvalSuite:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidSuite(f"cannot load eval suite {path}: {exc}") from exc
    return parse_suite(document)


def parse_suite(document: Any) -> EvalSuite:
    suite = _mapping(document, "suite")
    _exact_fields(
        suite,
        {"schema_version", "suite_id", "wiki", "language", "cases"},
        "suite",
    )
    schema_version = suite["schema_version"]
    if isinstance(schema_version, bool) or schema_version != SCHEMA_VERSION:
        raise InvalidSuite(
            f"suite.schema_version must be {SCHEMA_VERSION}, got {schema_version!r}"
        )
    suite_id = _nonempty_string(suite["suite_id"], "suite.suite_id")
    wiki = _nonempty_string(suite["wiki"], "suite.wiki")
    language = _nonempty_string(suite["language"], "suite.language")
    if wiki != "fr.wikipedia.org" or language != "fr":
        raise InvalidSuite("eval suite v0 must remain scoped to fr.wikipedia.org/fr")

    raw_cases = suite["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise InvalidSuite("suite.cases must be a non-empty list")
    cases = tuple(
        _parse_case(raw_case, index) for index, raw_case in enumerate(raw_cases)
    )
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise InvalidSuite("suite.cases contains duplicate case ids")
    capabilities = {case.capability for case in cases}
    if capabilities != FRWIKI_CAPABILITIES:
        missing = sorted(FRWIKI_CAPABILITIES - capabilities)
        extra = sorted(capabilities - FRWIKI_CAPABILITIES)
        raise InvalidSuite(
            f"suite.cases must cover exactly the MVP capabilities; missing={missing}, extra={extra}"
        )
    return EvalSuite(schema_version, suite_id, wiki, language, cases)


def _parse_case(raw_case: Any, index: int) -> EvalCase:
    label = f"suite.cases[{index}]"
    case = _mapping(raw_case, label)
    _exact_fields(case, {"id", "capability", "tags", "prompt", "judge_rubric"}, label)
    case_id = _identifier(case["id"], f"{label}.id")
    capability = _nonempty_string(case["capability"], f"{label}.capability")
    tags = _string_tuple(case["tags"], f"{label}.tags")
    prompt = _nonempty_string(case["prompt"], f"{label}.prompt")
    rubric = _parse_rubric(case["judge_rubric"], f"{label}.judge_rubric")
    return EvalCase(case_id, capability, tags, prompt, rubric)


def _parse_rubric(raw_rubric: Any, label: str) -> JudgeRubric:
    rubric = _mapping(raw_rubric, label)
    _exact_fields(rubric, {"pass_threshold", "criteria", "failure_conditions"}, label)
    pass_threshold = rubric["pass_threshold"]
    if isinstance(pass_threshold, bool) or not isinstance(pass_threshold, int):
        raise InvalidSuite(f"{label}.pass_threshold must be an integer")
    if not 0 <= pass_threshold <= 100:
        raise InvalidSuite(f"{label}.pass_threshold must be between 0 and 100")
    criteria = _rubric_items(rubric["criteria"], f"{label}.criteria", allow_empty=False)
    failure_conditions = _rubric_items(
        rubric["failure_conditions"],
        f"{label}.failure_conditions",
        allow_empty=True,
    )
    return JudgeRubric(pass_threshold, criteria, failure_conditions)


def _rubric_items(
    raw_items: Any, label: str, *, allow_empty: bool
) -> tuple[RubricItem, ...]:
    if not isinstance(raw_items, list) or (not raw_items and not allow_empty):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise InvalidSuite(f"{label} must be {qualifier}")
    items = []
    for index, raw_item in enumerate(raw_items):
        item_label = f"{label}[{index}]"
        item = _mapping(raw_item, item_label)
        _exact_fields(item, {"id", "description"}, item_label)
        items.append(
            RubricItem(
                _identifier(item["id"], f"{item_label}.id"),
                _nonempty_string(item["description"], f"{item_label}.description"),
            )
        )
    item_ids = [item.id for item in items]
    if len(item_ids) != len(set(item_ids)):
        raise InvalidSuite(f"{label} contains duplicate ids")
    return tuple(items)


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


def _identifier(value: Any, label: str) -> str:
    identifier = _nonempty_string(value, label)
    if CASE_ID_PATTERN.fullmatch(identifier) is None:
        raise InvalidSuite(f"{label} must be a lowercase kebab-case identifier")
    return identifier


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidSuite(f"{label} must be a list")
    items = tuple(_identifier(item, f"{label} item") for item in value)
    if len(items) != len(set(items)):
        raise InvalidSuite(f"{label} contains duplicates")
    return items
