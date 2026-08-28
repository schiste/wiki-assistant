import argparse
import json
from pathlib import Path

from eval.scoring import load_assessments, load_baseline, score_run
from eval.suite import load_suite

EVAL_ROOT = Path(__file__).resolve().parent
DEFAULT_SUITE = EVAL_ROOT / "cases" / "frwiki-mvp-v0.json"
DEFAULT_BASELINE = EVAL_ROOT / "baselines" / "frwiki-mvp-v0.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assessments", type=Path, required=True)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    arguments = parser.parse_args()

    suite = load_suite(arguments.suite)
    baseline = load_baseline(arguments.baseline, suite)
    assessments = load_assessments(arguments.assessments, suite)
    report = score_run(suite, assessments, baseline)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
