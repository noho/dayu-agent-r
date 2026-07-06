# WU-CLI-SMOKE-01 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-CLI-SMOKE-01 dayu-cli Core Usability Smoke and Behavior Validation`
- Gate: aggregate deepreview
- Date: 2026-07-06
- Base: `github/main`
- Aggregate review artifacts:
  - `docs/reviews/code-review-20260706-171635.md` (AgentDS)
  - `docs/reviews/code-review-20260706-171806.md` (AgentMiMo)

## Review Summary

Both aggregate deepreviews passed. The reviewers independently checked the full WU diff against `github/main`, including goal confirmation, plan, plan reviews, plan fix, re-reviews, Slice S1 implementation, Slice S1 code reviews, controller adjudications, accepted commits, README updates, tests, and the current control document.

Both reviewers concluded:

- The WU remains scoped to dayu-cli core usability and does not claim dayu-cli full completion.
- The idle `dayu-cli interactive` Ctrl+C root cause is fixed in CLI-local REPL state without changing composer, Service, Host, Engine, durable schema, EventLog, wait lifecycle, or Fins storage.
- Automatic validation is sufficient for the automated portion of this WU, including focused CLI tests, real PTY idle Ctrl+C probe, broader CLI / Service tests, public awaiting smoke, `git diff --check`, and pyright.
- Manual evidence has clear owner and remains pending for final closeout.
- README and `tests/README.md` updates match their documented boundaries.
- There is no unadjudicated finding, orphan residual risk, control-doc drift, or artifact-chain break.

## Findings Adjudication

| Finding | Source | Controller decision | Reason | Required action |
|---|---|---|---|---|
| No material issue | AgentDS | accepted as pass | The review follows the full WU artifact and code chain and found no blocking issue. | None. |
| No material issue | AgentMiMo | accepted as pass | The review follows the full WU artifact and code chain and found no blocking issue. | None. |

## Residual Risks

| Residual risk | Decision | Owner / next action |
|---|---|---|
| Real provider `dayu-cli prompt` evidence remains pending. | deferred-with-owner | User provides MANUAL-01 evidence before final closeout. |
| Real provider `dayu-cli interactive` running-state Ctrl+C evidence remains pending. | deferred-with-owner | User provides MANUAL-02 evidence before final closeout. |
| Optional real Fins download / process evidence remains pending. | deferred-with-owner | User may provide MANUAL-03 evidence; optional unless the user widens the WU. |
| PTY Ctrl+C helper is work-unit evidence under `workspace/tmp/`, not a maintained test entry. | accepted risk | Current maintained regression coverage is through focused CLI tests; future CLI test hardening can migrate PTY coverage if needed. |
| Empty-line reset behavior has no dedicated assertion. | accepted risk | Existing tests cover the material first / second / normal-input reset behavior; empty-line reset is non-blocking and matches expected terminal UX. |

## Controller Decision

Aggregate deepreview is accepted. WU-CLI-SMOKE-01 can move to manual validation collection. No AgentCodex fix gate is required before manual validation.
