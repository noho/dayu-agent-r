# WU-SEMANTIC-OWNERSHIP-01 P1-B Code Re-review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: fix re-review adjudication
- Code review adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-codex.md`
- Fix controller validation: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-controller-validation.md`
- AgentMiMo re-review: `docs/reviews/code-review-20260709-p1-b-rereview-mimo.md`
- AgentDS re-review: `docs/reviews/code-review-20260709-p1-b-rereview-ds.md`

## Re-review Results

- AgentMiMo: `pass`
- AgentDS: `pass`

Both reviewers confirmed:

- `P1B-CODE-ACCEPTED-F01` closed: watchdog helper docstrings now point to typed Run row cancel link and same-Run `CANCEL_REQUESTED` validation.
- `P1B-CODE-ACCEPTED-F02` closed: schema/state regression covers missing `cancel_request_event_id` for `CANCELLING` / `CANCELLED`.
- `P1B-CODE-ACCEPTED-F03` closed: implementation artifact documents `tool_trace.py` full Host lifecycle event-set convergence.
- `P1B-CODE-ACCEPTED-F04` closed: `cancel_cancelling_run_row` documents preserving the typed link fixed at `CANCELLING` entry.

No new blocking finding was raised.

## Controller Decision

Decision: `accepted-slice`.

P1-B is accepted after final controller validation and commit. This does not close `WU-SEMANTIC-OWNERSHIP-01`; after the P1-B accepted commit, continue to P1-C, then P2-A, P2-B and P2-C, followed by additional full-repository deepreview rounds as required by the umbrella WU.

## Final Controller Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_open_host_runtime.py` -> 197 passed.
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py tests/host/test_projection_read_model.py tests/host/test_public_host_event.py tests/host/test_context_compact_events.py tests/host/test_tool_trace*.py tests/host/test_outbox*.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py` -> 287 passed.
- `source .venv/bin/activate && rg -n "_TERMINAL_STATUS_BY_EVENT_TYPE|_TERMINAL_EVENT_TYPES|_cancel_request_event_id_from_cancelling|payload\\.get\\(\"cancel_request_event_id\"\\)|event_payload_object\\(.*RUN_CANCELLING" dayu/host tests/host` -> only classified lifecycle helper / derived helper / deferred stress-test support matches.
- `source .venv/bin/activate && pyright` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> passed.

## Residual Risks

- `tests/host/stress_support.py` retains stress-test terminal tuples. This is deferred test support outside P1-B focused migration.
- `read_api.py` still mixes shared terminal enum use with private non-terminal lifecycle constants. This is deferred because P1-B did not promise repo-wide migration of all non-terminal lifecycle constants.
- No old Host DB schema compatibility was added, by explicit schema policy.
