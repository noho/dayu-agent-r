# WU-TOOLS-01-F01-02-R1 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-02-R1`
- Gate: aggregate deepreview / final validation
- Aggregate review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-ds.md`
- Fix artifact:
  - `docs/reviews/wu-tools-01-f01-02-r1-aggregate-fix-codex.md`
- Fix re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-ds.md`

## Controller Judgment

Aggregate deepreview passes after the AGG-F01 fix and narrow re-review.

AgentMiMo and AgentDS both found no blocking issue in the full WU implementation. MiMo raised one actionable low-risk finding: `build_fins_wait_activation_registry(...)` used `workspace_root` and created its own runtime, while Fins prepared observations are process-local runtime state. The controller accepted this as AGG-F01 because the builder's old signature could mislead non-Service callers and conflicted with the no-dead-helper / no-misleading-wiring constraint.

AgentCodex fixed AGG-F01 by making `build_fins_wait_activation_registry(...)` accept the shared `FinsObservationRuntime`, deleting `FinsIngestionWaitActivationAdapter.from_workspace_root(...)`, and making production Service assembly use the same builder with the shared `FinsIngestionRuntime`. MiMo and DS re-reviewed the fix and both returned pass.

## Finding Status

- `AGG-F01`: closed. Activation registry construction no longer creates a hidden runtime. Production Service assembly and standalone builder now share the same explicit runtime-based construction path.
- MiMo observation 02 (`created_at` rebuilt during activation): not accepted for current fix. `activate_observation(...)` uses `handle_id` for lookup; `created_at` does not participate in activation semantics.
- DS re-review residual about `WaitPollAdapterRegistry`: not accepted as a current blocker. `build_fins_wait_adapter_registry(...)` currently returns Host wait binding metadata, not a `WaitPollAdapterRegistry` containing a `FinsIngestionWaitPollAdapter` instance. Production poller scheduling and adapter instance assembly remain owned by the deferred production poller work, GitHub Issue #90. This WU must not add an unused `HostToolingOptions` field or a no-consumer poll adapter registry ahead of #90.

## Verification

Controller reproduced the relevant final validation after the fix:

- `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q`: `103 passed`, with upstream `edgar` deprecation warnings.
- `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`: `159 passed`, with upstream `edgar` deprecation warnings.
- `pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: no whitespace errors.
- Static search confirmed no remaining `build_fins_wait_activation_registry(workspace_root=...)`, no `FinsIngestionWaitActivationAdapter.from_workspace_root(...)`, and no `_require_distinct_fins_awaiting_tool_names` production helper.

## Residual Risk

- Production poller loop, poll adapter instance scheduling, retry/backoff/fencing, and process-restart behavior remain deferred to GitHub Issue #90.
- Callback endpoint / auth / replay remains deferred to GitHub Issue #89.
- External job physical cancel / revoke / abandon remains deferred to GitHub Issue #92.

No unowned residual risk remains for this WU.
