# WU-TOOLS-01-F01 Aggregate Final Review Controller Adjudication

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Gate: aggregate final review adjudication
- Inputs:
  - `docs/reviews/wu-tools-01-f01-aggregate-final-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-aggregate-final-review-ds.md`

## Verdict

fix-required

Both reviewers reported aggregate `pass`, agreed that `WU-TOOLS-01-S4-R1` should remain closed, and confirmed the S1-S6 target shape is complete. Controller accepts one low-severity correctness finding for fix before entering ready-to-open-draft-PR because it is a real job state-machine race in the shared Fins runtime.

## Accepted Finding

| ID | Source | Severity | Controller decision |
|---|---|---|---|
| F01-AGG-001 | AgentDS final review; corroborated by Controller code check | low | Accept. `_mark_job_running_or_cancelled` reads a queued job and later saves `RUNNING` through separate lock acquisitions. A concurrent `request_cancel` can set `CANCELLING` in between and then be overwritten. Fix by adding an atomic job-store operation that claims `RUNNING` or returns `CANCELLED` under one store lock, then route `_mark_job_running_or_cancelled` through that operation. Add a regression test that simulates a cancel arriving during the claim window. |

## Rejected Or Deferred Observations

| Observation | Controller decision |
|---|---|
| File-lock pressure/stress coverage | Defer. Existing tests cover atomic write and lock semantics at functional level; a stress suite belongs with later CI/performance hardening, not this closeout. |
| Real SEC/CN/HK network download adapters | Defer to later Fins adapter owners. Unsupported-source failed terminal behavior is the accepted F01 scope. |
| `ingestion_runtime.py` module size | Defer as maintainability observation. Current boundaries are still coherent; splitting during closeout would add churn without closing a correctness gap. |

## Required Fix Validation

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

## Residual Closure

`WU-TOOLS-01-S4-R1` remains closed. F01-AGG-001 is a low-probability cancellation race within the already implemented shared runtime, not evidence that the shared runtime/provider/wait-adapter objective is incomplete.
