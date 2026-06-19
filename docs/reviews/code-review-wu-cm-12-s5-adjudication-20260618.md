# WU-CM-12 Slice S5 Code Review Adjudication

## Scope

- Work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- Slice: S5 Public Smoke Reconciliation, Regression Matrix, README Decision
- Implementation artifact: `docs/reviews/wu-cm-12-s5-implementation-codex-20260618.md`
- Review artifacts:
  - `docs/reviews/code-review-wu-cm-12-s5-mimo-20260618.md`
  - `docs/reviews/code-review-wu-cm-12-s5-ds-20260618.md`

## Decision

S5 is accepted.

Both reviewers passed the implementation with no findings. The accepted behavior is:

- Proactive fallback keeps tier 4 recent-window / floor / caps semantics. The fallback provider rebuilds the EventLog-backed frozen material view used by the selector, and RunInput fallback rendering uses that same view when present.
- The S3 selected-id, source-ref, digest and protected-group guards remain fail-closed.
- `_facts_from_accepted_event` now drops only the invalid fact candidate with empty evidence labels and preserves earlier valid facts.
- Overlong current input is not silently truncated or previewed for compact input. It does not call the compactor or write compact artifacts, and dispatch proceeds through fallback.
- README updates are not required.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py -q`
  - Result: `312 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py::test_deterministic_two_turn_request_contains_prior_final_answer tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q`
  - Result: `2 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
  - Result: `11 passed, 1 skipped`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: PASS

## Residuals

- `WU-CLI-ACTIVITY-01-PR-R1`: closed by passing public continuity smokes.
- `WU-CM-12-S1-R1`: closed by root-cause fix and focused regression coverage.
- `WU-CM-12-S4-R1`: deferred as a future reactive compact recovery follow-up. S5 does not add schema, EventLog, Engine role or public API changes, and reactive tier 1-3 recovery would require separate Engine ingest recovery sequencing and cancellation/commit guards.
