# Contributing to WAIT

WAIT is built in the open. This document is the practical "how" — see
[`docs/architecture-plan.md`](docs/architecture-plan.md) for what's being built and why, and
[`docs/rollout-plan.md`](docs/rollout-plan.md) for the phased plan this repo's issues and
milestones track directly.

## Before you start

- Read the architecture plan and rollout plan first — most design questions have already been
  worked through there, with reasoning, not just conclusions.
- Check open issues and the [project board](https://github.com/users/schiste/projects/2) for
  what's already in flight before starting something adjacent.
- If a change touches security-relevant surface (the link allowlist, injection scanning, the
  proxy's auth model, or the maintenance tier's toolset/guardrails — see architecture §9), say so
  explicitly in the PR description, even if you're confident it's fine.

## Development model

This project is currently built primarily via AI coding agents, operated by the maintainer.
That shapes a few conventions:

- Keep PRs small and scoped to one rollout-plan checklist item where possible.
- Reference the architecture-plan section (`§N`) and rollout-plan phase a change implements in
  the PR description.
- Automated gates (pre-commit, pre-push, CI) substitute for a second human reviewer that mostly
  isn't there day-to-day — treat a failing check as blocking, not advisory.
- See [`AGENTS.md`](AGENTS.md) for conventions specific to AI-agent contributors.

## Workflow

1. Open or claim an issue — every issue is labeled by `phase:*`, `area:*`, `type:*`, and
   `priority:*`; milestones map 1:1 to rollout-plan phases.
2. Branch from `main`, work, commit. Install the repository hooks after cloning with
   `pre-commit install`, then run the complete local check set at any time with
   `pre-commit run --all-files`. The installed pre-push hook runs the fast Python and JavaScript
   unit suites followed by the same local checks; it deliberately excludes live model evals.
3. Open a PR against `main`. CI must pass. Self-merge is fine once checks are green — the point
   of requiring a PR is the audit trail and the CI gate, not a mandatory second approver, given
   the current team size.
4. Link the PR to the issue(s) it closes.

## Reporting bugs vs. security issues

Regular bugs: open a GitHub issue using the bug report template.
Security vulnerabilities: **do not** open a public issue — see [`SECURITY.md`](SECURITY.md).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

Contributions to code are under Apache-2.0; contributions to documentation, prompts, and other
non-code content are under CC BY-SA 4.0 (see [`docs/LICENSE-CONTENT.md`](docs/LICENSE-CONTENT.md)).
By contributing, you agree your contribution is made under the license applicable to the files
you're changing.
