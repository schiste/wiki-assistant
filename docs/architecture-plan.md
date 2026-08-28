# WAIT — architecture plan

**WAIT** = Wiki Aware Intelligent Tool (full name spelled out once here; **WAIT** used
throughout everywhere else, including the rest of this document).

**Date:** 2026-08-28 · **Status:** building; patch-proposer credential model still open · **Supersedes:** all prior
versions of this document

## Decision

An agent that helps Wikipedia editors navigate policy/rules and templates, assists with small
JS/CSS/Lua (Scribunto) coding, and helps editors discover existing tools before building new
ones — runs on Hermes (the actual runtime), deployed on Toolforge. A read-only, text-only chat
interface, hosted on-wiki first (user subpages, later an official gadget), plus a maintenance
tier (eval, watchdog, feedback, plus a V1 patch proposer once its separate credential/trigger
model is decided) using Hermes's real agent loop.

---

## 1. Architecture

### 1.1 Interactive tier

**Interface: hosted on-wiki.** The script itself lives in user subpages first (e.g.
`User:X/WAIT.js`), graduating later to an official `MediaWiki:Gadget-*.js`. **This is
same-origin, not cross-origin resource loading** — meaningfully better than the "gadget fetches
a script from Toolforge" pattern originally assumed. It resolves most of the Third-Party
Resources Policy risk flagged earlier (§9): that policy targets *external resource loading*, and
the script content never leaves wikipedia.org. What remains cross-origin is only the *runtime*
API calls from that on-wiki script out to WAIT's proxy (§12) — the same narrower,
already-precedented pattern `gitlab-content` uses. Track the policy's status regardless (§16),
but this is a materially safer starting point than assumed.

- Read-only chat, text-only rendering (§9.2–9.3, unchanged).
- Session/toolset: empty toolset (§5), backed by `llm-qwen36-27b`/`llm-qwen3-14b`.
- Access is independent of Wikipedia login state. The proxy receives no Wikimedia identity and
  uses no MediaWiki OAuth credential.
- Rollout path is now explicit and staged: personal userscript → official gadget. Each stage has
  its own review bar (self-review → gadget-admin community review).

### 1.2 Maintenance tier

Eval, watchdog, and feedback run as `cron.provider=builtin` entries inside the same gateway
process. The patch proposer remains a V1 target but stays disabled until §6's credential/trigger
decision is recorded. Specs in §11.

## 2. Platform: Toolforge (not Cloud VPS)

Unchanged. Toolforge's default quota fits Hermes's measured footprint; Cloud VPS was rejected.

## 3. LiftWing / Qwen — confirmed facts

| | `llm-qwen3-14b` | `llm-qwen36-27b` |
|---|---|---|
| Model | Qwen3-14B, FP8 | Qwen3.6-27B, FP8 — "largest available" |
| Context | 16K | 32K |

- OpenAI-compatible chat completions, no API key required. **No tool-calling.** **No safety
  layer** — WMF's own moderation classifiers are internal-only, not available to Toolforge. **No
  data retention** on LiftWing's side. **Rate limit:** 100/hr public, effectively unlimited for
  WMCS traffic. **Latency degrades hard under concurrency** (~3.6s at concurrency 1, p50 ≈18s at
  concurrency 64). No SLA, experimental, model set may change.

## 4. Deployment shape on Toolforge

- Hermes's own Docker image can't run on Toolforge (Build Service is buildpack-only; the image
  needs `USER root` + `network_mode: host`). Doesn't block WAIT — `hermes gateway run` is
  one plain foreground process, confirmed running bare (non-root, no container) already.
- `dashboard` skipped. `cron.provider=builtin` runs eval, watchdog, and feedback in-process;
  patch-proposer scheduling is added only after §6's decision.
- **Everything deploys on Toolforge** (confirmed). Hermes runs as an internal continuous job;
  the proxy backend (§12) is the tool's single public webservice, built through Build Service.
  The browser never receives a route or credential for Hermes.
- `HERMES_HOME` on NFS-backed `/data/project/...`.

## 5. Tool-calling handling (interactive tier)

Empty toolset (`"tools": [], "includes": []`), config-level, not a Hermes patch — **default**.

**One deliberate, narrow exception: tool discovery (§10.4).** When an end user supplies a
compatible BYK credential for a tool-calling-capable model, the tool-discovery path gets a
dedicated toolset containing
*only* an MCP binding to `toolhub-evolved`'s four read-only functions (`search_tools`,
`facet_tools`, `list_facet_values`, `get_tool`) — nothing else from `_HERMES_CORE_TOOLS`. This
doesn't undermine the "no tools" posture in §9: every one of those four calls is a read-only,
side-effect-free catalog lookup — no wiki edit, no file/terminal/browser access, no state
mutation. The realistic worst case of a successfully-injected tool call here is "it searched a
public catalog," not "it took an action." Bound it anyway: cap tool calls per conversation turn
(a handful, not unlimited) so this narrow surface can't become a resource-abuse vector against
`toolhub-evolved`'s own 60 req/min limit (§10.4).

Bonus, not the reason for the design but worth noting: because this goes through Hermes's *real*
agent loop (unlike the proxy's context-stuffing path for wiki content), tool-call **results**
here automatically pass through Hermes's own `tool_dispatch_helpers.py` injection scanning
(Appendix A) — no extra wiring needed, unlike §9.5's manual scan for proxy-fetched content.

## 6. BYK and maintenance-tier model backing

**BYK means an end user brings their own provider credential.** It applies to the interactive
tool-discovery tier only. WAIT passes the credential transiently from the on-wiki client through
the proxy to the provider-capable Hermes session. It is never stored in Toolforge envvars,
session state, files, logs, analytics, or public audit records. Provider billing and provider
quota belong to that user, so WAIT has no BYK spend budget or cost-center tracking.

The automated patch proposer is different: scheduled work has no end user present and therefore
cannot consume an arbitrary user's BYK credential. Its trigger and credential model is an
explicit open decision: either it becomes a maintainer-triggered action using a transient
maintainer-supplied key, or it receives a dedicated operator credential with separately approved
cost controls. Until that decision is recorded, the patch proposer remains disabled. Do not call
an operator credential “BYK.”

## 7. Maintenance-tier toolset — curated, not default

**Include:** `read_file`, `write_file`, `patch`, `search_files`, `terminal`, `process`,
`web_search`, `web_extract`, `todo`, `memory`, `skills_list`, `skill_view`, `session_search`,
`clarify`.
**Exclude:** all `browser_*`, all `ha_*`, `text_to_speech`, `image_generate`, `vision_analyze`,
`cronjob`, `delegate_task`, `skill_manage`, `execute_code`.
**Guardrail:** write access terminates at "open a proposal for human review," enforced by
credential scope, not prompting. Credentials: dedicated, least-privilege, scoped to WAIT's
own repo/issue tracker.

**Add `toolhub-evolved`'s `toolhub-creation` skill** (§10.4) — a portable agent skill for
creating/validating a repo-owned `toolinfo.json`, copied directly into the maintenance tier's
skills directory. Complements the interactive tier's discovery mode: discovery helps an editor
find out something already exists *before* building; this skill helps register it properly
*after* they've decided to build.

## 8. Public auditability and privacy

Publish WAIT's own config layer (toolsets, prompts, cron/eval config) openly (§15). Pin
and publish the exact Hermes version/commit; document the upgrade-review process. Public
maintenance-tier activity log, scrubbed of private data. Toolforge privacy statement required
before the gadget goes live (§10's product scope makes this concrete now — see §16). Short-TTL,
non-identifying abuse counters are preferred over raw IP storage. The interface does not depend
on Wikipedia login state and forwards no Wikimedia username or identity. User-supplied BYK
credentials are request secrets and must be excluded from every storage and observability path.

## 9. Security — interactive-tier threat model

### 9.1–9.7 (unchanged from prior version)

No tool-calling kills LLM-autonomous-action risk but not output-integrity, confused-deputy,
information-disclosure, misinformation, or resource-abuse risk. Confused-deputy and output-XSS
are closed by product decisions (read-only chat, text-only rendering). Link allowlist (hostname
+ scheme + path, exact Wikimedia domain list, excludes wmcloud/wmflabs/toolforge). Input-side
`scan_for_threats()` call on every externally retrieved context item, including wiki content and
tier-1 Toolhub records, before it enters the prompt; warn-and-log by default.
`api_server`'s single global `API_SERVER_KEY` can't be embedded in public client-side JS — fixed
by the proxy backend (§12), which now also gets a concrete contract, not just a mandate.
Misinformation/reputational risk flagged as real, unsolved, separate from security.

### 9.8 New, from the coding-assistance scope: code-suggestion supply-chain risk

Distinct from and more severe than general misinformation. WAIT suggests JS/CSS/Lua
snippets for gadgets and Scribunto modules. If prompt injection (or a plain model error)
produces subtly malicious or backdoored code, and an editor — trusting a tool built to help with
exactly this — copies it into a **published, wiki-wide gadget or template module**, that code
then runs in every reader's browser or every page transclusion. This isn't "the assistant said
something wrong to one person"; it's "the assistant's output became live code with a
much larger blast radius than the conversation it came from."

Mitigations, layered rather than relying on any single one:
- Every code suggestion should carry a **visible, un-skippable disclaimer**: AI-suggested code,
  review before use, especially before publishing to a shared gadget/module — not just a
  one-time notice, present on every code block.
- **Never suggest code that disables or weakens a security-relevant MediaWiki mechanism**
  (CSRF token handling, origin checks, permission checks) — worth an explicit system-prompt
  instruction and an eval case (§11) that checks for this specifically, not just general
  code-quality.
- The same input-side injection scan (§9.5) applies here: if the conversation includes
  fetched wiki/template content (e.g., "help me fix this existing module"), that content is
  exactly as untrusted as any other wiki content and should be scanned before reaching the model.
- This risk is a strong argument for keeping the gadget-graduation review bar real (§1.1) — a
  community gadget-admin review step is a genuine second pair of eyes on exactly the kind of
  code this tool produces, not just process overhead.

## 10. Product scope — what WAIT actually does

Four capabilities, which define the corpus this tier needs to fetch:

1. **Policy/rules navigation** — helping editors understand and locate the relevant policy,
   guideline, or notability rule for their situation. Corpus: policy/guideline wiki pages via
   the public MediaWiki API (read-only, no auth needed).
2. **Template help** — finding and understanding templates. Corpus: template documentation
   pages, same public API.
3. **Small JS/CSS/Lua (Scribunto) coding assistance** — for userscripts, gadgets, and template
   modules. See §9.8 for the risk this specifically introduces.
4. **Tool discovery** — pointing editors at existing tools/gadgets/scripts before they build a
   new one. See §10.4 — v1, using `toolhub-evolved`, not the raw Toolhub API.

All four are read-only, public-data lookups — **no MediaWiki bot credential or OAuth consumer
is needed for v1**, since nothing here requires authenticated access or makes edits. Worth
stating explicitly since it simplifies §13's secrets inventory.

### 10.4 Tool discovery — `toolhub-evolved`, two-tier design, v1

Verified, not assumed: [`toolhub-evolved`](https://toolhub-evolved.toolforge.org/) (maintained
by this project's team, evolvable if these primitives prove insufficient) already exposes
catalog discovery as a stateless HTTP MCP server (`https://toolhub-evolved.toolforge.org/mcp`),
purpose-built for exactly this use case:

- **Four read-only, no-auth tools:** `search_tools(query, limit)`, `facet_tools(...)`,
  `list_facet_values(type)`, `get_tool(name)`.
- **A `prior-art-review` prompt** — a guided, multi-step "build vs. reuse vs. differentiate"
  workflow, closer to what §10 point 4 actually wants than a single search call.
- A companion **`toolhub-creation` skill** for scaffolding a proper `toolinfo.json` once someone
  decides to build (§7).
- Rate-limited to 60 req/min per client IP, stateless, no session state.

**Two tiers, gated by tool-calling availability — v1 for both:**

1. **Default (LiftWing Qwen, no tool-calling — everyone gets this).** Qwen can't call the MCP
   server itself (§3/§5 — a server-side vLLM gate, unrelated to WAIT's own config).
   WAIT's **proxy** calls `toolhub-evolved` server-side (plain HTTP, no MCP client library
   needed — it's a documented access path) and stuffs relevant results into the model's context
   as text — the same corpus-fetch pattern used for policy/template content. Works for every
   user, no BYK cost.
2. **Enhanced (end-user BYK tool-calling model).** When a user supplies a compatible provider,
   model, and credential for the request, the interactive tier's discovery-mode session (§5)
   gets real, narrow MCP tool access — the model itself calls
   `search_tools`/`facet_tools` iteratively, closer to what the `prior-art-review` prompt
   enables. The credential is transient per §6. Missing credentials, provider rejection/quota,
   or provider unavailability fall back to tier 1 automatically (§14).

Because the proxy is the caller in tier 1, `toolhub-evolved`'s 60 req/min is effectively a
shared request quota across all of WAIT's users, not per-user — cache frequent searches
proxy-side rather than hitting it on every mention of "is there a tool for X."

## 11. Maintenance-tier worker specs

- **Eval** — a fixed, versioned benchmark suite spanning all four product capabilities (§10),
  each case with either a reference answer or an LLM-judge rubric (correctness, no fabricated
  policy citations, no unsafe/backdoored code per §9.8). Runs on a schedule and before any
  prompt/config change is promoted. Produces pass/fail + score per case; any regression vs. the
  last-known-good baseline is the signal the patch proposer consumes.
- **Watchdog** — infrastructure health, not output quality: gateway process alive, `api_server`
  responding, LiftWing reachable within acceptable latency, Toolforge resource usage within
  quota, NFS/SQLite health. Runs frequently. **Alerting channel still undecided** — needs one
  (email, Phabricator task, or similar) before this is more than a dashboard nobody watches.
- **Feedback** — a lightweight in-UI signal (e.g. 👍/👎 on a response) — compatible with
  "read-only chat," since it's UI-local interaction with the proxy, not a wiki edit or a Hermes
  tool call — plus implicit signals (immediate rephrasing/correction as a proxy for "that didn't
  help"). Aggregated and surfaced to maintainers; the main purpose is **minting new eval cases**
  from real friction, so eval's fixed set grows from actual usage instead of staying static.
- **Patch proposer** — triggered by eval regressions or triaged feedback, drafts a proposal
  (prompt/config change, new eval case, or code fix) for human review. Never auto-merges (§7).

The first three operate without a paid provider key: watchdog keeps the service running, eval
catches known-case regressions, and feedback surfaces new real-world cases. If §6's separate
decision enables the patch proposer, it can then propose fixes without becoming a prerequisite
for those three workers.

## 12. Proxy backend — API contract

Sits between the on-wiki script and Hermes's `api_server`, holding the real `API_SERVER_KEY`
server-side. Enforces the link allowlist (§9.4) and injection scan (§9.5) **server-side**, not
just in client JS — a client-side-only check is inspectable and bypassable, so defense belongs
on the server that actually talks to the model.

**Caller boundary: exact-origin allowlist, not a wildcard.** Browsers call the proxy, never
Hermes directly — Hermes has no public route at all (§4). CORS and server-side `Origin`
validation both live on the proxy. For MVP the only allowed origin is exactly
`https://fr.wikipedia.org` — not `*` and not the pattern `*.wikipedia.org` used in earlier drafts
of this plan. Add exact origins one at a time as wikis are onboarded (§10.4's composability
work). This boundary is independent of Wikipedia login state and must not introduce OAuth or
identity forwarding. `Origin` validation is a browser-caller boundary, not cryptographic client
attestation — a custom non-browser client can forge the header; direct (non-browser) clients are
simply unsupported, and requests without an allowed origin are rejected before any model work
starts. Rate limiting (below) is a separate, independent abuse control, not a substitute for
this check.

- `POST /chat` — request: `{ message, session_id?, context?: { page_title?, page_lang? },
  byk?: { provider, model, api_key } }`.
  Response: `{ session_id, reply, links?: [{title, url}] }` — links returned as **structured,
  pre-validated data** (already filtered per §9.4), not raw text the client has to parse and
  re-validate itself.
- **BYK handling:** `byk` is optional, request-scoped secret material. The proxy must redact the
  key before request logging and must not place it in the opaque session, Hermes persistence,
  traces, metrics, errors, or feedback. Supported providers/models remain an explicit V1
  compatibility decision (§6); no arbitrary endpoint URL is accepted from the browser.
- **Session handling:** the proxy mints its own opaque session token for the browser to hold —
  Hermes's own session/memory-scoping headers (`X-Hermes-Session-Id`/`X-Hermes-Session-Key`)
  stay server-side, never exposed to the client.
- **Rate limiting** (proposed starting point, tune against real usage — not a researched number):
  per-session/IP request cap (e.g. tens per hour, generous for a help tool, not spam-friendly),
  plus a global in-flight concurrency cap at the proxy to protect the shared LiftWing latency
  curve (§3) regardless of Toolforge's own elevated quota.
- **Error responses:** structured `{ error: { code, message } }`, with distinct codes for
  rate-limited, upstream-unavailable (§14), and content-blocked (§9.5 hard-block cases).

## 13. Secrets and environment inventory

- `API_SERVER_KEY` — Hermes gateway's internal secret, generated once during operator
  provisioning and injected into both Hermes and the proxy through Toolforge envvars (§4).
- **End-user BYK credentials are not service secrets** — they arrive only in an opted-in request
  (§6, §12) and are never provisioned through Toolforge envvars or retained server-side.
- Patch-proposer credential — not provisioned until §6's separate trigger/credential decision is
  recorded; if an operator credential is chosen, it becomes a normal Toolforge secret with its
  own approved controls.
- Watchdog alerting-channel credential — depends on the channel chosen (§11), not yet picked.
- **Not needed for v1:** any MediaWiki bot/OAuth credential (§10 — everything is public,
  read-only lookups).
- Service-owned secrets are stored via
  [Toolforge envvars](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Envvars), private to
  maintainers and injected at runtime. End-user BYK is explicitly excluded from this inventory.

## 14. Degradation and resilience plan

Composable, config-driven rather than a single hardcoded path — a list the proxy walks in order:

1. **Retry with backoff** — one or two retries within a tight timeout budget, for transient
   blips.
2. **Model fallback chain** — an ordered, config-defined list of model IDs to try (e.g.
   `llm-qwen36-27b` → `llm-qwen3-14b`, with a request-scoped BYK model selected only when the
   user supplies one) — adding a supported provider/model is a compatibility change, not a
   project spending decision. **The same mechanism governs §10.4's tier switch:** no BYK,
   rejected/exhausted user quota, or unavailable provider → discovery mode falls back to tier 1
   (proxy-side context stuffing), not a separate code path.
3. **Visible wait state** — if latency is within §3's known concurrency-curve range, show a
   "thinking, this may take a moment" state rather than erroring immediately.
4. **Graceful failure message** as the last resort — explicit, honest unavailability, not a
   silent hang or a cryptic error. Necessary given LiftWing's no-SLA status (§3).

## 15. Repository and deployment

- Repo hosted on **GitHub as primary, mirrored to GitLab** (Wikimedia's own GitLab instance is
  the natural target, strengthening §8's auditability goal — a WMF-affiliated mirror is more
  discoverable/trusted within the movement than GitHub alone; confirm the exact GitLab target
  during setup).
- **Everything deploys on Toolforge** (§4) — Hermes as an internal continuous job and the proxy
  backend (§12) as the single public Build Service webservice.

## 16. Known risks (tracked, not blocking)

- **SQLite over NFS** — accepted risk, single-writer pattern, worth an early smoke test.
- **LiftWing: experimental, no SLA, no tool-calling roadmap** — §14 exists because of this.
- **CSP/Third-Party Resources Policy** — meaningfully de-risked by on-wiki script hosting
  (§1.1), but the proxy API calls remain cross-origin; track the policy's status regardless.
- **Gadget-admin community review timing** is now a real, staged dependency (userscript → gadget,
  §1.1) rather than an undecided rollout question.
- **End-user BYK secret handling** (§6, §12) — credentials cross the proxy by design and require
  strict redaction, no persistence, session isolation, and provider allowlisting.
- **Patch-proposer credential/trigger model is undecided** (§6) — the worker remains disabled
  until a maintainer-triggered or operator-credential model is explicitly selected.
- **Watchdog alerting channel undecided** (§11).
- **`toolhub-evolved`'s 60 req/min limit is a new shared dependency** (§10.4) — same shape of
  risk as LiftWing's concurrency curve (§3), smaller blast radius, still worth caching against.
- **Wikimedia community process (BAG/BRFA)** — still entirely outside this document's scope.
- **Code-suggestion supply-chain risk (§9.8)** — mitigated, not eliminated; the strongest
  backstop is the gadget-admin review step at graduation, which is now a confirmed part of the
  rollout plan rather than a nice-to-have.

## 17. Build checklist

1. First-boot init (non-root): scaffolding, seed config, validate the provisioned
   `API_SERVER_KEY`, sync skills.
2. Internal Toolforge continuous job running `hermes gateway run`, NFS `HERMES_HOME`,
   `cron.provider=builtin` driving eval/watchdog/feedback (§11).
3. Single public proxy webservice (§12) via Build Service: exact Wikipedia-origin enforcement,
   session minting, server-side link allowlist + injection scanning, rate limiting, and the
   degradation chain (§14).
4. Interactive-tier session: empty toolset and LiftWing Qwen; no browser-facing Hermes CORS —
   origin enforcement lives entirely on the proxy (§12), exact-origin allowlist, MVP:
   `https://fr.wikipedia.org` only, not a wildcard.
5. On-wiki script (user subpage first): text-only rendering, calls only the proxy, never
   `api_server` directly.
6. Eval suite (§11): benchmark cases across all four product capabilities (§10), including
   unsafe-code-suggestion checks (§9.8).
7. Watchdog: pick an alerting channel; wire health checks.
8. Feedback affordance in the UI; pipeline into eval-case creation.
9. Decide the patch-proposer trigger/credential model (§6); only then enable its curated toolset
   (§7), `toolhub-creation` skill (§7, §10.4), and propose-only guardrail.
9a. Discovery-mode session (§5, §10.4): tier-1 proxy-side `toolhub-evolved` integration first
    (works for everyone, no BYK); tier-2 narrow MCP toolset gated on transient end-user BYK,
    bounded tool calls per turn, and falling back to tier 1 via the same chain as §14.
10. Repo setup: GitHub primary + GitLab mirror (§15); publish WAIT's own config layer and
    pinned Hermes version (§8).
11. Draft the Toolforge privacy statement before any public launch (§8).
12. Smoke-test SQLite under NFS (§16).
13. Implement and security-review transient BYK handling: provider allowlist, redaction,
    no persistence, session isolation, and quota/unavailability fallback (§6, §12).
14. Wire `toolhub-evolved` tier 1 (proxy → MCP server, plain HTTP) and tier 2 (narrow MCP
    toolset, BYK-gated) per §10.4.
15. Separately track: BAG/BRFA bot approval, gadget-admin review for the graduation step (§1.1).

---

## Appendix A — Hermes source citations (tool-calling degradation)

- `agent/bedrock_adapter.py:615,1257–1273` — only adapter with proactive capability stripping.
- `agent/transports/chat_completions.py:541–547` — generic transport (used by LiftWing), sends
  `tools` unconditionally.
- `agent/models_dev.py` — capability flag tracked but never read by the orchestrator.
- `agent/error_classifier.py` — `llama_cpp_grammar_pattern` is the one reactive fix; generic
  `format_error` is usually non-retryable.
- `toolsets.py` — `_HERMES_CORE_TOOLS` default; `context_engine` shows the empty-toolset pattern.
- `tools/threat_patterns.py`, `agent/prompt_builder.py`, `agent/tool_dispatch_helpers.py` —
  injection-scan library and its actual (narrow) coverage.

## Appendix B — Toolforge platform citations

- [Help:Toolforge/Running jobs](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Running_jobs) ·
  [Help:Toolforge/Kubernetes](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Kubernetes) ·
  [Help:Toolforge/Envvars](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Envvars) ·
  [Help:Toolforge/Build Service](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Build_Service) ·
  [Help:Cloud VPS](https://wikitech.wikimedia.org/wiki/Help:Cloud_VPS) ·
  [Portal:Toolforge/Admin/Kubernetes/RBAC and Pod security/PSP migration](https://wikitech.wikimedia.org/wiki/Portal:Toolforge/Admin/Kubernetes/RBAC_and_Pod_security/PSP_migration) ·
  [T388092](https://phabricator.wikimedia.org/T388092) · [T348755](https://phabricator.wikimedia.org/T348755)

## Appendix C — LiftWing citations

- [Machine Learning/LiftWing/Large Language Models/Wikimania 2026](https://wikitech.wikimedia.org/wiki/Machine_Learning/LiftWing/Large_Language_Models/Wikimania_2026) ·
  [Machine Learning/LiftWing/Large Language Models](https://wikitech.wikimedia.org/wiki/Machine_Learning/LiftWing/Large_Language_Models)

## Appendix D — Gadget/CSP citations

- [Manual:CORS — MediaWiki](https://www.mediawiki.org/wiki/Manual:CORS) ·
  [Talk:2023 Third-party resources policy draft — Meta-Wiki](https://meta.wikimedia.org/wiki/Talk:Third-party_resources_policy) ·
  [Tool:Gitlab-content — Wikitech](https://wikitech.wikimedia.org/wiki/Tool:Gitlab-content)

## Appendix E — Wikimedia project domain citations

- [Complete list of Wikimedia projects — Meta-Wiki](https://meta.wikimedia.org/wiki/Complete_list_of_Wikimedia_projects) ·
  [Wikimedia wikis — Meta-Wiki](https://meta.wikimedia.org/wiki/Wikimedia_wikis)

## Appendix F — toolhub-evolved

- [toolhub-evolved.toolforge.org](https://toolhub-evolved.toolforge.org/) ·
  [MCP server guide](https://toolhub-evolved.toolforge.org/mcp-server) — read directly from the
  project's own repo/README (local checkout), not web-fetched: four read-only MCP tools
  (`search_tools`, `facet_tools`, `list_facet_values`, `get_tool`), the `prior-art-review`
  prompt, the `toolhub-creation` skill, 60 req/min per client IP, no authentication on the
  read/discovery path. Maintained within this project's own team — evolvable on request (§10.4).
