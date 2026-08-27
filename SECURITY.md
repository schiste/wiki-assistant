# Security policy

WAIT is a public-facing tool that operates on Wikimedia infrastructure and, from Phase 4
onward, is reachable directly by editors' browsers. Security reports are taken seriously and
handled privately until a fix is available.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.** Instead, use
[GitHub's private vulnerability reporting](https://github.com/schiste/wiki-assistant/security/advisories/new)
for this repository (Security tab → "Report a vulnerability"). This creates a private advisory
visible only to maintainers until it's resolved.

Please include:

- What you found and why it's a security issue, not a bug report.
- Steps to reproduce, or a proof of concept if applicable.
- The affected component (see the `area:*` label taxonomy in
  [`docs/rollout-plan.md`](docs/rollout-plan.md) — gateway, proxy, gadget, etc.) if known.

## Scope

Particularly interested in reports touching:

- The link-allowlist and output-rendering logic in the on-wiki script (XSS-adjacent issues).
- The proxy backend's auth model, session handling, and rate limiting.
- Prompt-injection vectors that escalate beyond content quality into an actual security
  boundary (credential exposure, cross-session data leakage, unintended tool execution).
- Anything in the maintenance tier's toolset or guardrails that could let a proposal bypass
  human review before reaching a real repo/issue tracker.

See [`docs/architecture-plan.md`](docs/architecture-plan.md) §9 for the current threat model —
useful context for judging whether something is already a known, tracked risk versus a new
finding.

## Response

This is currently a single-maintainer project — response times won't match a funded security
team's SLA, but reports will be acknowledged and triaged as a priority over other work.
