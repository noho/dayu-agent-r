# WU-TOOLS-01-F01-02-R1 Slice 3 Re-Review Fix (AgentCodex)

## Scope

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 3 narrow re-review fix
- target finding: `S3-RR-F01`
- input review: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-ds.md`
- controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-controller-adjudication.md`
- modified files:
  - `dayu/service/host_assembly.py`
  - `tests/service/test_host_assembly.py`

No commit, push, PR, plan/control document change, or next-gate action was performed.

## Fix

`S3-RR-F01` accepted root cause was valid: `_tool_discovery_specs(...)` no longer belonged to the production discovery path. Production discovery already uses `_tool_discovery_bindings(...)`, which calls `_tool_discovery_spec(...)` per provider. Keeping the plural helper only for tests preserved obsolete production code.

Implemented fix:

- Deleted `_tool_discovery_specs(...)` from `dayu/service/host_assembly.py`.
- Replaced test import `_tool_discovery_specs` with `_tool_discovery_spec`.
- Migrated affected tests to call `_tool_discovery_spec(...)` directly because their assertions target one provider-to-spec mapping at a time:
  - missing provider location fail-fast
  - entry point mapping
  - loader config passthrough
  - web config passthrough
  - Fins effective `workspace_root` injection, preservation, and relative-root resolution

No compatibility wrapper, new abstraction, or production discovery behavior change was added.

## Validation

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
  - passed: `52 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - passed: `159 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - passed: `0 errors, 0 warnings, 0 informations`
  - pyright also printed a version update notice from `v1.1.409` to `v1.1.410`; this is not a type-check failure.
- `git diff --check`
  - passed

The pytest warnings are existing third-party `edgar` deprecation warnings.

## README / Docs Judgment

- `tests/service/test_host_assembly.py` changed, so `tests/README.md` was checked.
- The README constraint requires updates when a new test layer or maintained testing fact changes. This fix only retargets existing Service tests from the deleted plural helper to the current single-spec helper; it does not add a test layer, command, fixture category, or documented workflow.
- No README update was needed.
- No plan/control document was modified.

## Residual Risk

- No `S3-RR-F01`-specific uncovered behavior remains: the deleted helper has no remaining references, and production discovery continues through `_tool_discovery_bindings(...)`.
- Broader Slice 3 residual risks documented by the previous review remain out of scope for this narrow fix.
