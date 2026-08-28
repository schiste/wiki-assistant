# Eval suite v0

This directory implements the deterministic half of architecture §11 and rollout Phase 5. The
fixed `frwiki-mvp-v0` suite covers policy navigation, template help, coding help, and tool
discovery. Each case has a structured LLM-judge rubric; the code-safety cases separately test
CSRF, origin/CORS, and permission-check weakening.

Run the network-free known-good fixture with:

```sh
python3 -m eval.run --assessments eval/fixtures/frwiki-mvp-v0-known-good.json
```

The runner validates structured judge assessments, calculates pass/fail and a 0–100 score for
each case, and compares every result with the versioned baseline. Any score decrease or lost pass
is a regression. Unit tests run this path in GitHub Actions without contacting LiftWing.

The checked-in baseline is deliberately marked `deterministic_fixture`; it proves the scoring
and regression contract, not model quality. A `live_liftwing` last-known-good baseline may only
supersede it as the default after a reviewed run from Toolforge. That job must execute inside
Hermes's maintenance tier and emit the same assessment schema. It must not call the public
interactive proxy or add an attestation bypass: public `POST /chat` remains restricted to
verified Wikipedia gadget requests under architecture §12 and issues #63–#64.
