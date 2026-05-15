# Gateflow Controller Adjudication: Host P5-S6 Integration, Docs And Validation Closeout

## Metadata

- Controller: AgentController
- Date: 2026-05-15
- Gate: Host Phase 5 P5-S6 Integration, Docs And Validation Closeout
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s6-integration-docs-validation-20260515.md`
- Code review artifacts:
  - `docs/reviews/gateflow-code-review-host-p5-s6-integration-docs-validation-mimo-20260515.md`
  - `docs/reviews/gateflow-code-review-host-p5-s6-integration-docs-validation-ds-20260515.md`

## Controller Decision

Verdict: accepted.

P5-S6 is accepted. The implementation closes the local no-tool execution validation gate and documents current Phase 5 behavior without describing future capabilities as current facts.

Two controlled scope expansions are accepted:

1. `dayu/host/dispatch.py` was added to P5-S6 because endpoint tests exposed a production gap: scheduler worker streams handled explicit `EngineEvent` values, but clean EOF and stream exceptions did not call `EngineEventIngestor.close_clean_eof` / `close_worker_lost`. This was not a test-only issue. The fix is correctly owned by dispatch scheduler stream consumption.
2. `tests/host/test_admission_queue.py`, `tests/host/test_durable_schema.py`, and `tests/host/test_run_attempt_transitions.py` were added because full P5-S6 validation exposed Phase 3-era assertions that conflicted with already accepted Phase 5 truth: schema version 3, Attempt `RUNNING` terminal closeout, and active worker cancel to `CANCELLING`.

## Review Adjudication

Both MiMo and DS returned PASS with no blocking findings.

| Review focus | Controller adjudication |
|---|---|
| Worker event stream clean EOF / crash closeout | Accepted. `clean EOF -> FAILED`, stream exception -> `LOST`, `CancelledError` passthrough, and terminal double-close prevention are implemented in scheduler stream consumption. |
| Lane token and active registry cleanup | Accepted. `unregister`, `handle.close`, and lane release remain in `finally`; cancel path does not directly release lane token. |
| P5-S6 endpoint tests | Accepted. Tests use public `start_run`, real `HostDispatchScheduler`, runtime lane, and fake local workers via `LocalEngineWorkerFactory` / `LocalWorkerHandle`. |
| Import boundary tests | Accepted. Runtime and Engine reverse dependencies are guarded; Host -> Engine imports remain restricted to boundary modules. |
| Phase 3 test migration | Accepted. Changes update obsolete assertions to current Phase 5 truth and do not add production compatibility code. |
| README sync | Accepted. README updates describe current capabilities and deferred owners only. |

## Validation

Controller reran validation:

```bash
source .venv/bin/activate && pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_import_boundary.py -q
```

Result: 14 passed.

```bash
source .venv/bin/activate && pytest tests/host/test_admission_queue.py::test_cancel_terminal_run_returns_current_terminal_without_new_facts tests/host/test_admission_queue.py::test_cancel_attempt_running_enters_cancelling_with_cancel_facts tests/host/test_durable_schema.py::test_fresh_db_creates_foundation_and_phase5_tables tests/host/test_run_attempt_transitions.py::test_terminal_closeout_accepts_attempt_running_in_phase5 -q
```

Result: 4 passed.

```bash
source .venv/bin/activate && pytest tests/host tests/runtime -q
```

Result: 334 passed.

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
git diff --check
```

Result: passed.

## Residual Risks

- Real provider / external API smoke remains out of Phase 5 scope. Current coverage uses fake local workers and Engine public event contracts to validate Host state-machine behavior.
- Active cancel watchdog and post-cancel timeout policy remain deferred to later lifecycle / recovery hardening.
- ToolRuntime / `fetch_more` remains Phase 6; `WAITING` / `resolve_wait` remains Phase 7; Memory remains Phase 9; Context Governance remains Phase 10; Recovery remains Phase 11; Observer / Sink remains Phase 13; RemoteProxy remains Phase 14.

## Next Gate

Proceed to P5-S6 accepted slice commit, update `docs/host/implementation-control.md`, then run Phase 5 aggregate review before marking ready-to-create-PR.
