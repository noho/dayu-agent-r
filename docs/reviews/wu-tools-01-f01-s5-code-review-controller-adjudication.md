# WU-TOOLS-01-F01 Slice S5 Code Review Controller Adjudication

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Slice: S5, Fins wait adapter and Service assembly wiring
- Gate: code review adjudication
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s5-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-s5-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s5-code-review-ds.md`

## Verdict

fix-required

Both reviewers agree that the S5 production design is aligned with the accepted plan: no Host or Engine public contract changed, Fins poll mapping is correct, Service assembly detects Fins awaiting providers from explicit provider config, and workspace root mismatch fails before `open_host`.

The accepted review findings are focused test coverage gaps at the S5 contract boundary. They should be fixed before accepting the slice because S5 is the first bridge from Fins durable job state into Host wait-resume.

## Accepted Findings

| ID | Source | Severity | Controller decision |
|---|---|---|---|
| F01-S5-001 | MiMo F1 | medium | Accept. Add direct tests that `RUNNING` and `CANCELLING` Fins job states map to `WaitPollNotReady`. The production mapping is correct today, but the plan explicitly requires active state mapping and future regressions should be caught. |
| F01-S5-002 | MiMo F2 | medium | Accept. Add an explicit Service assembly test for no Fins awaiting provider configs, asserting `HostToolingOptions.wait_adapter_registry is None` while normal non-Fins tools still assemble. |
| F01-S5-003 | DS F1 / MiMo F3 | low | Accept. Add a corrupt job evidence test for `poll_wait`, proving unreadable job evidence maps to `WaitPollLost` / `ResolveWaitLostOutcome` instead of adapter error. |
| F01-S5-004 | MiMo F3/F4 | low | Accept. Add focused `abandon_wait` defensive tests for missing `external_job_ref` and missing/corrupt job evidence. The expected behavior is no exception and no business-data deletion; corrupt/missing evidence may be ignored because Host wait cancellation already happened. |
| F01-S5-005 | MiMo F5 | low | Accept. Add Service assembly tests for missing and relative `config.workspace_root`, both failing before `open_host` with bounded `ValueError`. |

## Rejected Or Deferred Findings

| Source | Controller decision |
|---|---|
| MiMo F6 unreachable fallback branch | Reject as no-action. The final fallback in `poll_wait` is defensive for future enum expansion. Replacing it with `assert_never` would make unknown future Fins job states adapter errors instead of Host lost outcomes and is not required by S5. |
| DS F2 provider detection OR logic | Reject as no-action for S5. The accepted plan explicitly allows Service assembly to detect Fins awaiting providers from configured `provider_id`, `import_path`, and `source_id`. The current source ids are stable and specific. A stricter multi-field confirmation would be a design change, not a review fix. |
| DS F3 import boundary allowlist observation | Reject as no-action. The allowlist is intentionally narrow (`dayu.fins.ingestion`) and keeps Service out of Fins storage/runtime/tool internals. |
| Production poller loop, default config closeout, real network adapters | Deferred to existing owners. These are already recorded as later-work residuals and are outside S5. |

## Fix Scope

Fix should be limited to tests unless a tiny test helper is needed. Do not change Host/Engine contracts, Fins production mapping, Service detection semantics, or README text unless tests reveal a real production defect.

Required validation after fix:

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py`
- `source .venv/bin/activate && pytest tests/service -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`
