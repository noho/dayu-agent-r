# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Controller Validation

## Scope

- Batch: C1 - Host wait expiry / supervisor / claim-release owner.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-implementation-codex.md`
- Accepted findings:
  - `144159-01` / `145711-12` wait deadline / expiry owner drift.
  - `150304-01` WaitPollerSupervisor one transient exception permanently fails.
  - `150304-02` `_resolve_claimed_wait` read-back recovery can crash supervisor.
  - `150304-22` cancelled abandon `CAS_LOST` path does not release claim.
  - `150304-23` wait resolution bypasses injected `EventLogStore`.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/fins/test_fins_ingestion_tools.py -q`
  - Result: `126 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/host/test_wait_cancel_late_result.py tests/host/test_phase7_waiting_integration.py -q`
  - Result: `8 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.

## Controller Decision

Batch C1 is ready for code review. No controller-side validation blocker found.

## Residual Risk

- Existing third-party `edgar` deprecation warnings remain unrelated.
- Expired waits now fail closed at Host wait owner and remain `WAITING` with diagnostics/backoff. A future product decision may choose a terminal expired policy, but that is a separate Host wait policy work item.
- Batch C2 remains unstarted.

