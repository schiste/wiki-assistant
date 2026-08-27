# WAIT — Rollout plan to V1

**Companion to:** the WAIT architecture plan (Hermes/Toolforge/LiftWing/security decisions —
referenced below by `§` section numbers). This document is the *how and when*; the architecture
plan is the *what*.

**Delivery model:** built primarily by AI coding agents, operated by the project lead first.
Every gate in this plan (pre-commit, pre-push, CI, review) exists to substitute for a second
human pair of eyes that mostly isn't there day-to-day — treat the automated gates as load-bearing,
not boilerplate.

**Licensing:** dual — **Apache-2.0** for code (gateway config, proxy, scripts, eval harness),
**CC BY-SA 4.0** for documentation, prompts, and other non-code content, mirroring Wikipedia's
own content license. Apply per-directory (e.g. a `LICENSE` at repo root for code, a
`CC-BY-SA-4.0.txt` + a note in `docs/`/`prompts/` directories) rather than one blanket file —
confirm the exact split in Phase 1's alignment session.

---

## Epics

### Epic 1 — MVP
Full agent, but deliberately narrow: **frwiki only, LiftWing/Qwen only** — no BYK, no other
model providers, no other wikis. This scoping has a direct architectural consequence worth
stating up front: **the patch proposer and tool-discovery tier 2 are out of MVP scope**, because
both require a tool-calling-capable model and LiftWing's Qwen can't tool-call (architecture §3,
§5, §6). MVP's maintenance tier is eval + watchdog + feedback only — no patch proposer. Ships as
a personal userscript on frwiki (architecture §1.1) — not yet an official gadget.

### Epic 2 — V1
Composable: onboard additional wikis, enable BYK for other providers, turn on the patch proposer
and discovery-mode tier 2, graduate from userscript to official gadget. Built on abstractions
Epic 1 should already leave in place (the model-fallback chain in §14 and the tier-1/tier-2 split
in §5/§10.4 were designed config-driven from the start specifically so this doesn't require
re-architecture).

---

## Phase 0 — Foundation

**Goal:** the repo and its surrounding scaffolding exist and are usable, before any product code.

**Tasks**

- [ ] Create the GitHub repo (primary). Confirm exact org/repo name in Phase 1 alignment if not
      already fixed.
- [ ] Set up GitLab mirroring (Wikimedia's GitLab instance is the natural target per architecture
      §15 — confirm the exact instance/namespace in Phase 1). Push-mirror on every push to
      `main`, not a manual/periodic sync.
- [ ] Repo structure skeleton:
  ```
  /gateway/        — Hermes config: toolsets, cron/eval config, first-boot init script
  /proxy/          — proxy backend (session minting, link-allowlist + injection-scan enforcement)
  /gadget/         — on-wiki script (userscript first, gadget later)
  /eval/           — benchmark suite (Phase 5+)
  /skills/         — maintenance-tier skills (incl. toolhub-creation, §7)
  /docs/           — architecture plan, this rollout plan, ADRs
  /.github/        — Actions workflows, issue/PR templates
  ```
- [ ] Issue/label taxonomy (GitHub Issues):
  - Epic: `epic:mvp`, `epic:v1`
  - Phase: `phase:0-foundation` … `phase:8-multiwiki` (one per phase below)
  - Area: `area:gateway`, `area:proxy`, `area:gadget`, `area:eval`, `area:watchdog`,
    `area:feedback`, `area:patch-proposer`, `area:security`, `area:docs`, `area:ci`
  - Type: `type:feature`, `type:bug`, `type:chore`, `type:security`, `type:discussion`
  - Priority: `priority:p0`, `priority:p1`, `priority:p2`
  - Status: `status:blocked`, `status:needs-decision`, `status:needs-review`
- [ ] GitHub Projects (v2) board: a Roadmap view grouped by `phase:*`, a Kanban view
      (Todo/In Progress/Review/Done) for the active phase, a filtered view on `type:security`.
- [ ] Milestones: one per phase (nine total), each linked to its epic.
- [ ] Branch protection on `main`: required status checks (CI, once it exists in Phase 1), no
      force-push, PR required before merge (self-merge after green CI is fine given the solo/
      AI-agent delivery model — the point is CI gates the merge, not that a second human must
      click approve).
- [ ] Toolforge tool registration: create the tool account, confirm the exact tool name (Phase 1
      alignment item), request initial quota if the default (2 vCPU/8GB, architecture §2) needs
      raising, scaffold a `jobs.yaml` (empty/placeholder is fine at this stage).
- [ ] Basic tooling: `LICENSE` (Apache-2.0) + CC BY-SA 4.0 notice for docs/prompts, `README.md`
      linking the architecture plan, `CODEOWNERS`, `CONTRIBUTING.md` skeleton, `SECURITY.md`
      (responsible-disclosure contact — non-optional for a public Wikimedia-facing tool),
      `CODE_OF_CONDUCT.md`, `.gitignore`.

**Exit criteria:** repo exists on GitHub, mirrors to GitLab on push, has the label/milestone/
project scaffolding above, and the Toolforge tool account exists with a placeholder job config.
No product code yet — this phase produces structure, not features.

---

## Phase 1 — Core repo tooling & team alignment

**Goal:** the repo enforces quality gates from the first real commit, and the team has a single,
recorded set of decisions closing the open items the architecture plan flagged rather than
carrying ambiguity into implementation.

**Tasks — tooling**

- [ ] `.pre-commit-config.yaml` (using the `pre-commit` framework), minimum set:
  - `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, `check-merge-conflict`
  - Secret scanning: `gitleaks` — reuse/adapt Hermes's own `.gitleaks.toml` as a starting
    baseline rather than writing rules from scratch.
  - Python (proxy, gateway config, eval harness): `ruff` (lint + format).
  - JS/CSS (gadget/userscript): `eslint` + `prettier`.
- [ ] Pre-push hook: fast unit test suite + a final lint pass. **Deliberately excludes eval**
      (decided) — eval hits LiftWing, a shared, latency-variable, no-SLA resource (architecture
      §3); keeping it out of the local pre-push path means a developer's push speed never
      depends on LiftWing's mood. Eval runs in CI only, from Phase 5 onward.
- [ ] GitHub Actions CI mirrors every pre-commit check server-side (local hooks are
      bypassable with `--no-verify`; CI is the actual gate) plus runs the unit test suite.
- [ ] `AGENTS.md` (or `CLAUDE.md`) at repo root: conventions for AI-coding-agent contributors —
      small scoped PRs, mandatory reference to the architecture plan section a change implements,
      a note that anything touching `/proxy/` or `/gateway/` security logic (link allowlist,
      injection scan, auth) should go through a `/security-review`-style pass before merge given
      the delivery model has no default second reviewer.
- [ ] PR template requiring: which architecture-plan section this implements, which phase/epic
      it belongs to, and a checkbox confirming pre-commit passed locally.

**Tasks — alignment session (internal, not with an external audience)**

A structured internal discussion to close every item the architecture plan left open, before
Phase 2 starts building against them. Recommended agenda, one row = one decision to record:

- [ ] Exact GitHub org/repo name and GitLab mirror target (Phase 0 placeholders).
- [ ] Exact Toolforge tool account name.
- [ ] Watchdog alerting channel (architecture §11: email / Phabricator task / IRC / other).
- [ ] BYK provider/model choice for V1 (patch proposer, §6; discovery-mode tier 2, §10.4) — can
      be deferred in detail to Phase 6/7, but naming a default candidate now avoids relitigating
      it later.
- [ ] Rate-limit numbers in §12 (derived starting points, not measured) — confirm as the v0
      defaults or adjust before they're hardcoded anywhere.
- [ ] Privacy statement ownership and drafting timeline (architecture §8) — who writes it, due
      by which phase (must land before Phase 5's launch).
- [ ] BAG/BRFA engagement timing — when to start that community process relative to Phase 5's
      userscript release (it's slow and independent of engineering; starting early is usually
      right even though it's tracked outside this plan).
- [ ] Gadget-graduation criteria (Phase 8) — what "ready to propose as an official gadget" means
      concretely (usage volume? eval pass rate? time-in-userscript-stage minimum?), decided now
      so Phase 8 isn't a judgment call made under launch pressure.
- [ ] Dual-license split mechanics (Apache-2.0 vs CC BY-SA 4.0 boundaries) — confirm per-directory
      application from Phase 0.

**Exit criteria:** every commit from this point forward passes pre-commit locally and CI
remotely; a recorded decision (an ADR-style entry in `docs/`, one per bullet above) exists for
every alignment-session item — no open questions carried silently into Phase 2.

---

## Phase 2 — Infrastructure & deployment skeleton (Epic 1: MVP)

**Goal:** Hermes runs on Toolforge, end to end, before any product behavior is layered on.

**Tasks**

- [ ] First-boot init script (non-root): directory scaffolding, seed config, generate
      `API_SERVER_KEY`, sync bundled skills (architecture §4).
- [ ] Toolforge `webservice` running `hermes gateway run`, `HERMES_HOME` on NFS-backed
      `/data/project/...`, `cron.provider=builtin`.
- [ ] Proxy backend skeleton via Build Service (architecture §4, §12): session minting endpoint,
      `POST /chat` stub proxying to `api_server` with no logic yet beyond the round trip.
- [ ] Secrets: provision `API_SERVER_KEY` via Toolforge envvars (§13). **No BYK secret yet** —
      MVP is LiftWing-only.
- [ ] CORS configured on `api_server` for `*.wikipedia.org` (even though MVP only targets
      frwiki — configuring the whole family now costs nothing and avoids revisiting it in
      Phase 8).

**Exit criteria:** a request through the proxy reaches Hermes's `api_server`, reaches LiftWing's
Qwen, and a response comes back — no security hardening, no product logic, just the pipe working.

---

## Phase 3 — Security & guardrails (Epic 1: MVP)

**Goal:** the pipe from Phase 2 is safe to put in front of real editors before any product
feature is built on top of it.

**Tasks**

- [ ] Text-only rendering enforced gadget-side (§9.3) — no HTML pipeline, no auto-linkification
      outside the allowlist.
- [ ] Link allowlist implemented **server-side in the proxy** (§9.4, §12): hostname parsing with
      dot-boundary matching, `https:`-only scheme check, the full Wikimedia domain list, path
      restriction to `/wiki/<Title>`.
- [ ] Input-side injection scan (§9.5): proxy calls Hermes's `scan_for_threats()` on any
      wiki-sourced content before it enters the prompt; warn-and-log by default, hard-block only
      the clearest patterns; content framed as untrusted data in the prompt itself.
- [ ] Rate limiting at the proxy (§12): global in-flight concurrency cap (~8, per §3's
      concurrency curve), per-session/IP burst + sustained caps (values confirmed in Phase 1).
- [ ] Degradation chain (§14), MVP scope: retry-with-backoff → `llm-qwen36-27b` →
      `llm-qwen3-14b` → graceful failure message. No BYK rung yet — that's Phase 7.
- [ ] Code-suggestion disclaimer (§9.8) wired into every code block the gadget renders, even
      though MVP's coding-assistance corpus is frwiki-scoped.
- [ ] A `/security-review`-style pass over `/proxy/` and `/gateway/` before Phase 4 starts
      building product behavior on top.

**Exit criteria:** the security section of the architecture plan (§9) is implemented and
reviewed, not just designed — this phase produces working code, not another round of analysis.

---

## Phase 4 — Interactive tier build, frwiki-only (Epic 1: MVP)

**Goal:** the four product capabilities (§10), scoped to frwiki, actually work.

**Tasks**

- [ ] System prompt/persona: French-first (frwiki is French-language; MVP should not assume
      English as the default working language), scoped explicitly to frwiki policy/content.
- [ ] Corpus fetch: policy/guideline pages and template documentation via the public MediaWiki
      API, scoped to `fr.wikipedia.org` for MVP (§10 points 1–2).
- [ ] Coding assistance (§10 point 3, §9.8): JS/CSS/Lua help, frwiki gadget/module conventions.
- [ ] Tool discovery, **tier 1 only** (§10.4): proxy calls `toolhub-evolved` server-side, results
      stuffed into context as text. Tier 2 (BYK-gated MCP tool-calling) is explicitly Phase 7.
- [ ] On-wiki script: `User:<maintainer>/WAIT.js` on frwiki, calling only the proxy (never
      `api_server` directly), rendering per Phase 3's text-only rule.

**Exit criteria:** a maintainer can use the userscript on frwiki and get real, useful answers
across all four capabilities, tier-1 discovery included.

---

## Phase 5 — Eval, launch readiness, userscript release (Epic 1: MVP — done here)

**Goal:** ship MVP with enough of a safety net that regressions are caught, not discovered by
editors.

**Tasks**

- [ ] Eval suite v0 (§11): benchmark cases across all four capabilities, frwiki-scoped, including
      the unsafe-code-suggestion checks from §9.8. Runs in CI (Phase 1's decision) and on
      `cron.provider=builtin`'s schedule in production.
- [ ] Watchdog wired to the alerting channel decided in Phase 1; dead-man's-switch-style heartbeat
      pattern for semantic failures (LiftWing unreachable, NFS/SQLite broken) that Kubernetes'
      own crash-restart can't catch.
- [ ] Feedback affordance (👍/👎) in the gadget UI, piped to the proxy, feeding future eval-case
      creation (§11) — collection starts in MVP even though the eval-authoring loop matures in V1.
- [ ] Publish the config layer (toolsets, prompts, cron/eval config) and the pinned Hermes
      version/commit (§8) — the auditability commitment starts at MVP launch, not later.
- [ ] Privacy statement live (Phase 1 owner/timeline) before any release beyond the maintainer's
      own testing.
- [ ] SQLite-over-NFS smoke test (§16) — one of the few items in the architecture plan explicitly
      flagged as "verify, don't just trust."

**Exit criteria — MVP is done when:**
- The userscript is live and usable on frwiki by real testers (not just the maintainer).
- Eval, watchdog, and feedback are all running in production.
- The privacy statement and published config/version pin are live.
- No BYK, no other wikis, no patch proposer, no discovery tier 2 — confirming MVP stayed
  in scope, not scope-crept into V1 territory.

---

## Phase 6 — Composability foundations (Epic 2: V1)

**Goal:** turn MVP's frwiki/Qwen-only hardcoding into config, before adding any new capability —
composability is infrastructure work, not a feature, and should land before Phase 7's features
are built on top of it.

**Tasks**

- [ ] Wiki-scoping abstraction: corpus fetch, system prompt, and eval cases take a wiki/language
      parameter instead of assuming frwiki. (The link allowlist in §9.4 was already built
      wiki-family-wide, not frwiki-specific — nothing to change there.)
- [ ] Provider-scoping abstraction: the model-fallback chain (§14) already treats models as an
      ordered config list — this phase is mostly about confirming that holds, not rebuilding it.
- [ ] Cost-tracking scaffolding for the two BYK cost centers (§6, §13) that Phase 7 will start
      spending against.

**Exit criteria:** adding a second wiki or a second model provider is a config change, verified
by actually doing it once in a non-production/staging path before Phase 7 depends on it.

---

## Phase 7 — BYK-gated features (Epic 2: V1)

**Goal:** turn on the capabilities MVP deliberately deferred.

**Tasks**

- [ ] BYK secret provisioned via Toolforge envvars (§13), provider/model confirmed from Phase 1's
      alignment session.
- [ ] Patch proposer (§6, §7, §11): real agent loop, curated toolset, propose-only guardrail
      enforced by credential scope. Now genuinely testable, since eval (Phase 5) exists to feed
      it real regressions.
- [ ] Discovery-mode tier 2 (§5, §10.4): narrow MCP toolset bound to `toolhub-evolved`, gated on
      BYK availability/budget, bounded tool-calls-per-turn, falling back to tier 1 via the same
      degradation chain as §14.
- [ ] Budget alerts on both BYK cost centers — this is the phase where an unbounded cost
      surface actually turns on, so the tracking from Phase 6 needs to be live, not scaffolded.

**Exit criteria:** patch proposer has produced at least one real, human-reviewed proposal from an
actual eval regression; discovery tier 2 is live and falls back cleanly when BYK is unavailable.

---

## Phase 8 — Multi-wiki onboarding & gadget graduation (Epic 2: V1 — done here)

**Goal:** the composable system in Phase 6 actually carries a second wiki, and the userscript
graduates to an official, community-reviewed gadget.

**Tasks**

- [ ] Onboard at least one additional wiki using Phase 6's abstraction — this is the real test
      that "composable" wasn't just a design intention.
- [ ] Gadget-admin community review process, using the graduation criteria decided in Phase 1.
- [ ] BAG/BRFA engagement resolved (started back in Phase 1/5 per the timing decision).
- [ ] Re-run the full security review (§9) against the gadget-hosted version specifically — the
      CSP/Third-Party-Resources risk profile (§16) changes slightly once it's a community-wide
      gadget rather than a personal script, even though the code itself doesn't change.

**Exit criteria — V1 is done when:** WAIT is an official gadget on at least two wikis, with
patch proposer and discovery tier 2 both live in production, and composability has been
exercised for real, not just designed.
