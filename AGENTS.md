# Agent instructions

This repo is built primarily by AI coding agents. This file is the equivalent of onboarding
docs for a human hire — read it, and the two docs it points to, before making changes.

## Read first

1. [`docs/architecture-plan.md`](docs/architecture-plan.md) — the technical decisions (Hermes on
   Toolforge, LiftWing/Qwen facts, security threat model, product scope) with the reasoning and
   source citations behind each one. Sections are numbered (`§N`) and cross-referenced — treat a
   `§` reference elsewhere as a pointer to read, not a number to ignore.
2. [`docs/rollout-plan.md`](docs/rollout-plan.md) — the phased execution plan. Every issue in
   this repo maps to a phase/checklist item in this document.

## Conventions

- **Small, scoped PRs.** One rollout-plan checklist item per PR where feasible, not a batch of
  unrelated items.
- **Cite what you're implementing.** Reference the architecture-plan `§` section and rollout-plan
  phase in the PR description — this is how a reviewer (human or another agent session) checks
  the implementation against the decision, not just against "does it look reasonable."
- **Don't silently resolve an open decision.** The architecture and rollout plans both flag
  several items as explicitly undecided (e.g. rate-limit numbers as "starting points, not
  measured," the BYK provider choice, alerting channel). If your task touches one, either use
  the documented placeholder value and flag it in the PR, or raise it as a `status:needs-decision`
  issue rather than picking a value and moving on.
- **Security-sensitive surfaces get extra scrutiny.** Anything touching the link allowlist,
  injection scanning, the proxy's auth model, or the maintenance tier's toolset/guardrails
  (architecture §9) should note that explicitly in the PR — run a `/security-review`-equivalent
  pass on it before considering it done, not just the standard review.
- **No comments explaining what code does** — code should be self-explanatory via naming; a
  comment is for a non-obvious *why* (a constraint, a workaround, a citation to the architecture
  plan's reasoning), not a restatement of the code.
- **Don't add speculative abstraction.** The rollout plan is deliberately sequenced so
  composability work (Phase 6) happens once, when V1 actually needs it — building
  wiki-agnostic or provider-agnostic abstractions during Phase 2–5 (MVP) ahead of that plan is
  scope creep, not foresight.

## Automated gates

Once Phase 1 lands: pre-commit (lint, format, secret scanning) runs locally, CI mirrors the same
checks plus tests remotely. Both are load-bearing — this project doesn't have a standing human
reviewer for every change, so these checks are the actual quality bar, not a formality on top of
one.
