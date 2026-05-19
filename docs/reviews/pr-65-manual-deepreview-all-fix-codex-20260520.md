# PR 65 Manual Deepreview-All Fix - 2026-05-20

## Scope

- Gate: PR 65 manual post-draft `deepreview --all` fix loop.
- Fix agent: AgentCodex.
- Input review artifacts:
  - `docs/reviews/repo-review-20260520-060834.md`
  - `docs/reviews/repo-review-20260520-060858.md`

## Current-Fix Items

The controller accepted the following items for current fix:

- Startup recovery must wake `ACCEPTED` / `QUEUED` Runs after reopening so pre-start governance can resume or terminally close them.
- Tool awaiting accept timeout diagnostic refs must stay type-coherent.
- Compaction quality must not treat `CLEAR` plus empty summary open questions as retained.
- Duplicate governance `ALLOW` must not append a spurious governed event.
- Non-429 `Retry-After` must be capped.
- Non-stream HTTP 200 provider error objects must preserve provider error information.
- `ATTACH_ACTIVE` must attach to an `ACCEPTED` active Run without side effects.

## Changes

- `dayu/host/recovery.py`: `StartupRecoveryScanResult` now carries post-commit queue-promotion wakeups. `StartupRecoveryScanner` collects `ACCEPTED` / `QUEUED` session ids with set-backed de-duplication and calls `wake_queue_promotion(...)` only after the scan write transaction commits.
- `dayu/host/tool_runtime.py`: awaiting timeout diagnostics remain `tuple[str, ...]`; duplicate `ALLOW` no longer triggers `TOOL_CALL_GOVERNED`.
- `dayu/host/context_governance.py`: open-question retention now requires summary questions or non-empty `REPLACE`; `MISSING` and `CLEAR` return not retained.
- `dayu/engine/runners/openai/retry_policy.py`: non-429 `Retry-After` is capped at the stable 120s retry-after limit.
- `dayu/engine/runners/openai/non_stream_parser.py`: top-level provider `error` objects produce protocol error plus `runner_done(error)` before generic `choices` validation.
- `dayu/host/admission.py`: `attach_active` returns the existing `ACCEPTED` Run with no idempotency record, attempt, dispatch record, or event side effect.
- `dayu/host/README.md` and `dayu/engine/README.md`: stable behavior descriptions were synchronized.
- Focused tests were added or updated for each changed behavior.
- `tests/host/test_phase6_toolruntime_integration.py`: full host validation exposed two stale duplicate-`ALLOW` expectations; those integration assertions now match the accepted event-stream semantics.

## Validation

- `source .venv/bin/activate && python -m pytest tests/host/test_recovery_scan.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compaction_contract.py tests/engine/runners/openai/test_retry_backoff.py tests/engine/runners/openai/test_protocol_error.py tests/host/test_admission_queue.py tests/host/test_public_run_api.py -q`: 128 passed.
- `source .venv/bin/activate && python -m pyright dayu/host dayu/engine tests/host tests/engine`: 0 errors.
- `source .venv/bin/activate && python -m pytest tests/engine/runners/openai -q`: 214 passed.
- `source .venv/bin/activate && python -m pytest tests/host -q`: 795 passed, 1 skipped.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: 0 errors.
- `git diff --check`: clean.

## Non-Goals

- PID `start_token` / `boot_id` probe hardening.
- `_AsyncAgent` or dispatch structural refactor.
- EventLog physical corruption tolerance.
- Compaction budget estimator redesign.
- Recovery dispatch count semantic change.
- Host public interface change.
