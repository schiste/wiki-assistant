# Two-lane parallel execution plan

WAIT is deployed with [Aethyme](https://github.com/schiste/Aethyme) (see the `chore: deploy
aethyme repository policy` commit) — a local broker that lets multiple agents work the same repo
concurrently in isolated worktrees, merge-simulates before promoting, and hands back precise
rebase steps on conflict. This document is the *task-level* pairing that sits on top of that
mechanism: which issues two agents should each own per phase, so both stay productively busy
without stepping on each other, while Aethyme's leasing/merge-simulation handles the mechanical
file-level conflict detection underneath.

**Labels:** every granular sub-issue carries `lane:a`, `lane:b`, or `lane:joint`. Phase-parent
tracking issues (#1–#11) are unlabeled by lane — they span both.

## The split logic

**Lane A** leans infra/ops/backend: Toolforge, the Hermes gateway (`gateway/`), eval/watchdog,
the maintenance tier (patch proposer), and the alignment/governance decisions that are
infra-flavored (Toolforge naming, watchdog channel, BYK provider, BAG/BRFA timing).

**Lane B** leans product/client-facing: the proxy (`proxy/`), the on-wiki gadget (`gadget/`),
the four interactive-tier product capabilities, and the alignment/governance decisions that are
product-flavored (rate limits, privacy statement, gadget-graduation criteria, licensing).

This isn't a rigid architectural law — it's a *task-grouping* heuristic chosen because `gateway/`
and `proxy/` are separate directories with a defined API contract between them (architecture
§12's `POST /chat`), so work on either side rarely touches the same files. Where a phase doesn't
naturally split that way (Phase 3 is proxy/gadget-only by construction — see below), the lanes
split by sub-task within the same area instead of forcing a fake architectural boundary.

**`lane:joint`** marks a convergence point: work that needs both lanes' output landed first (a
security review over what both lanes just built) or that's small enough to just do together
rather than split.

## Working the lanes with Aethyme

Each lane agent, at the start of a session:

```bash
aethyme broker status --json                              # see what the other lane is doing
aethyme broker start --task "<issue title, e.g. #33>"      # isolated worktree + branch
```

Work from the reported worktree. Commit early and small. On completion:

```bash
aethyme broker submit --session <id>
```

If `.aethyme/broker-action-required.md` appears, the two lanes' work overlapped somewhere —
read it, it names the exact conflicting files and rebase steps. Until `gates.toml` exists
(#61, blocked on #16), `submit` only checks for conflicts, not correctness — run tests locally
before submitting regardless.

## Per-phase lane assignment

### Phase 0 — Foundation
| Lane A | Lane B |
|---|---|
| #13 Toolforge tool registration | #12 GitLab push-mirror |

No dependency between them — both are external, one-off setup actions.

### Phase 1 — Core repo tooling & alignment (13 issues + #61)
| Lane A | Lane B |
|---|---|
| #14 `.pre-commit-config.yaml` | #15 pre-push hook |
| #16 CI workflow | #18 GH/GitLab naming decision |
| #17 branch protection required check *(after #16)* | #22 rate-limit numbers decision |
| #19 Toolforge tool name decision | #23 privacy-statement owner/deadline |
| #20 watchdog alerting channel decision | #25 gadget-graduation criteria |
| #21 BYK provider/model decision | #26 license-split confirmation |
| #24 BAG/BRFA timing decision | |
| #61 draft `gates.toml` *(after #16)* | |

**Sequencing:** #17 strictly after #16 (same lane). #61 strictly after #16. #15 should start once
#14's lint/format tool choices are settled — light cross-lane handoff, not a hard block (both
touch different files, so parallel drafting + reconcile-at-merge is fine if timing is tight).

### Phase 2 — Infrastructure & deployment skeleton (5 issues)
| Lane A | Lane B |
|---|---|
| #27 first-boot init script | #29 proxy backend skeleton |
| #28 Hermes as internal Toolforge continuous job | #31 Origin/CORS enforcement on the proxy |
| #30 provision `API_SERVER_KEY` via envvars | |

**Sequencing:** both lanes need #30's key to exist for an actual end-to-end round-trip test, but
each can build their own side first (init script / proxy skeleton) without it. Land #30 early.

### Phase 3 — Security & guardrails (7 issues)
| Lane A | Lane B |
|---|---|
| #32 text-only rendering (gadget) | #34 input-side injection scanning |
| #33 link allowlist, server-side | #35 rate limiting at the proxy |
| #37 code-suggestion disclaimer | #36 MVP degradation chain |

**`lane:joint`:** #38 security review pass — do after both columns land, not before.

Note: this phase is entirely proxy/gadget-scoped by construction (it's hardening the
already-built client-facing pipe from Phase 2) — there's no independent gateway-side work to
give Lane A here, so the split is by sub-task within the same area rather than by
architecture layer. If one lane finishes early, the honest options are: pick up slack from the
other lane's remaining issues, or pull forward Phase 5 groundwork that doesn't depend on Phase 3
finishing (#45 watchdog, #49 SQLite/NFS smoke test — both gateway-side, genuinely independent).

### Phase 4 — Interactive tier build, frwiki-only (5 issues)
| Lane A | Lane B |
|---|---|
| #39 frwiki system prompt/persona | #41 coding assistance (JS/CSS/Lua) |
| #40 corpus fetch (policy/template pages) | #42 tool discovery tier 1 |

**`lane:joint`:** #43 on-wiki script — the shell (calls proxy, text-only render, link allowlist)
can start early since Phase 3 already built what it wires together; finishing it cleanly wires
in whichever of #39–42 have landed, so treat it as a light integration task either lane can pick
up once its own column is done.

### Phase 5 — Eval, launch readiness, userscript release (6 issues — MVP done here)
| Lane A | Lane B |
|---|---|
| #45 watchdog + alerting | #44 eval suite v0 |
| #49 SQLite-over-NFS smoke test | #46 feedback affordance |
| #47 publish config layer + pinned Hermes version | #48 Toolforge privacy statement |

Balanced 3/3, no hard sequencing between the two columns.

### Phase 6 — Composability foundations (3 issues)
| Lane A | Lane B |
|---|---|
| #51 confirm model-fallback chain is provider-agnostic | #50 wiki-scoping abstraction |
| #52 cost-tracking scaffolding | |

Small phase — 2/1 is the natural balance, not forced.

### Phase 7 — BYK-gated features (4 issues)
| Lane A | Lane B |
|---|---|
| #53 provision BYK secret via envvars | #55 discovery-mode tier 2 (BYK-gated MCP) |
| #54 implement the patch proposer | #56 budget alerts (both cost centers) |

**Sequencing:** #54 needs #53's secret to actually test against a real model; #55 needs it too —
land #53 first, or stub/mock it briefly so both lanes can build their logic before the real key
exists.

### Phase 8 — Multi-wiki onboarding & gadget graduation (4 issues — V1 done here)
| Lane A | Lane B |
|---|---|
| #59 resolve BAG/BRFA engagement | #57 onboard a second wiki |
| #60 re-run full security review for gadget context | #58 gadget-admin community review |

## Rebalancing

This split is a starting point, not a contract. If one lane consistently finishes early, move
issues between `lane:a`/`lane:b` with `gh issue edit <n> --remove-label lane:a --add-label
lane:b` (or vice versa) rather than leaving an agent idle — check `aethyme broker status` first
to make sure nothing's already claimed against the old assignment.
