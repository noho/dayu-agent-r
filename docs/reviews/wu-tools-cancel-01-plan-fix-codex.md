# WU-TOOLS-CANCEL-01 Plan Fix — AgentCodex

## Scope

- Work unit: `WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening`
- Gate: plan fix
- Fixed artifact: `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- Review inputs:
  - `docs/reviews/wu-tools-cancel-01-plan-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-controller-adjudication.md`

## Fix Summary

- DS F1 fixed: the plan now selects the default local worker event stream `close()` path for `LocalWorkerHandle.on_cancel(...)`, including active `anext` cancellation, async generator close, idempotency, `_consume_worker_events(...)` finally cleanup, and tolerated `CancelledError` propagation.
- DS F2 and MiMo 001 fixed: the plan now requires typed execution modes `async_direct`, `thread_backed`, and `process_backed`, with per-mode interrupt semantics and an explicit statement that thread-backed execution cannot satisfy production-grade non-cooperative blocking cancellation.
- Process-backed feasibility fixed: the plan now includes a migration matrix for Doc, Fins read tools, Web sync HTTP/search/fetch, async HTTP/httpx, and Playwright, with picklability risks, fallback strategies, and a design-gate stop condition for key production paths.
- DS F3 fixed: the plan defines a small internal worker close cleanup grace, such as `local_worker_close_grace_seconds = 3.0`, and states it is not a second cancel timeout and must not extend `tool_execution_timeout_seconds`.
- DS F4 fixed: Slice S3 now requires a public or Host-public smoke where Run A uses a non-cooperative blocking fixture, is cancelled, and Run B advances in the same Session.
- DS F5 fixed: the plan defaults to no `dayu.contracts` change; if provider declarations prove necessary, implementation stops for design / contract update.
- DS F6 fixed: the validation matrix now includes cooperative async path regression coverage.
- MiMo 002 fixed: the plan retains three slices but requires S2 to report per-tool-family migration assessment and stop/defer classification.
- MiMo 003 fixed: async HTTP/httpx now uses `async_direct` semantics or an explicit adapter abort hook, with response/client cleanup validation.

## Validation

- `git diff --check`: passed.
- `git diff --no-index --check /dev/null docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`: no whitespace findings; command returned 1 because the file is untracked and differs from `/dev/null`.
- `git diff --no-index --check /dev/null docs/reviews/wu-tools-cancel-01-plan-fix-codex.md`: no whitespace findings; command returned 1 because the file is untracked and differs from `/dev/null`.

## Open Questions

No blocking open question introduced by this plan fix.
