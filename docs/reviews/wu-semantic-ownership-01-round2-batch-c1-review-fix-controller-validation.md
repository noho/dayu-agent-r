# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Review Fix Controller Validation

## Scope

- Batch: C1 - Host wait expiry / supervisor / claim-release owner.
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-codex.md`
- Accepted review findings fixed:
  - `DS-C1-01`
  - `C1-REVIEW-01`
  - `DS-C1-02`
  - `C1-REVIEW-02` / `DS-C1-03`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_record_state.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/service/test_wait_callback_endpoint.py -q`
  - Result: `288 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.

## Controller Decision

Batch C1 review-fix is ready for re-review.

## Residual Risk

- Existing third-party `edgar` deprecation warnings remain unrelated.
- Expired waits still remain `WAITING` with retry/backoff after Host boundary rejection; any terminal expired policy remains a separate Host wait policy decision.
- Batch C2 remains untouched.

