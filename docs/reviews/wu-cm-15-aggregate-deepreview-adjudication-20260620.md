# WU-CM-15 Aggregate Deepreview Adjudication

## Gate

- Work unit: WU-CM-15.
- Gate: aggregate deepreview and aggregate-fix focused re-review.
- Base: `0439cd80`.
- Accepted implementation slice commit: `572a88df`.
- Aggregate deepreview:
  - AgentMiMo: `docs/reviews/deepreview-wu-cm-15-aggregate-mimo-20260620.md`.
  - AgentDS: `docs/reviews/deepreview-wu-cm-15-aggregate-ds-20260620.md`.
- Aggregate fix artifact: `docs/reviews/wu-cm-15-aggregate-fix-codex-20260620.md`.
- Aggregate-fix focused re-review:
  - AgentMiMo: `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-mimo-20260620.md`.
  - AgentDS: `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-ds-20260620.md`.

## Decision

Result: PASS after fix.

AgentMiMo aggregate deepreview found no blocker. AgentDS aggregate deepreview also concluded PASS, but raised medium and low non-blocking findings. Controller accepted the low-risk closeout fixes and rejected broader refactors for this WU.

Accepted fixes:

- Reactive acceptance now rejects proactive requested / compacted / failed activity.
- `memory-compact --pressure-mode auto` now has startup pressure bounds using the real-provider reserve.
- Fallback acceptance now has a semantic guard before reading `failed_events[-1]`.
- The compactor runner hook now converts missing `_run_agent_request` into a semantic `RuntimeError`.
- Control doc gate wording and WU-CM-15 plan review artifact chain are now synchronized.

Deferred residuals:

- Do not extract shared `run_smoke(...)` / `_run_deterministic_compact_smoke(...)` flow in this WU.
- Do not split the smoke script module in this WU.
- Real-provider `memory-compact` still requires a valid compactor provider key.
- The question of also rejecting `rejected_proactive` in reactive acceptance is deferred as future smoke hardening, because the accepted aggregate-fix finding specifically covered requested / compacted / failed proactive activity and both focused re-reviews passed.

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Passed: `20 passed`.
  - Warnings: existing third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL`
  - Passed.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL`
  - Passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors`.
- `git diff --check`
  - Passed.

## Closeout Entry

WU-CM-15 may proceed to local final closeout and ready-to-open-draft-PR state. Push, draft PR creation, mark-ready, reviewer requests, merge, branch deletion, and issue closure still require separate user authorization.
