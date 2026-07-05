# WU-TOOLS-CANCEL-01 Residual Hardening Aggregate Fix

## Gate / Scope

- Work unit: `WU-TOOLS-CANCEL-01 residual hardening reopen`
- Gate: aggregate review fix
- Agent: AgentCodex
- Scope: only controller-accepted aggregate review test fixes.
- Non-goals: no production code changes, no README expansion, no commit, no push, no PR state change.

## First-Principles Judgment

The accepted findings are valid test gaps, not behavior defects. Current code already rejects unknown fields in `host_runtime.json.process_capsule_interrupt_policy` and already wires `ProcessCapsuleInterruptPolicy` through the default ToolRuntime factory path. The useful fix is regression coverage that locks those properties against future drift.

## Changed

- Added `tests/runtime/test_config_loader.py::test_host_runtime_process_capsule_policy_rejects_unknown_fields` to assert unknown fields inside `process_capsule_interrupt_policy` fail with `ConfigFieldError` and an `unknown fields` signal.
- Added `tests/host/test_toolruntime_executor.py::test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy` to prove a custom `ToolRuntimeBuildRequest.process_capsule_interrupt_policy` reaches the process-backed capsule close path through `DefaultToolRuntimeFactory` and declared `ProcessBackedToolExecutionCapability`, without direct `ProcessBackedToolExecutionCapsule` construction or a test capsule factory override.

## Docs Decision

- `tests/README.md` checked by trigger rule. No update needed: this fix adds focused regression tests inside existing Runtime config-loader and Host ToolRuntime executor categories, with no new fixture category, marker, or test running rule.

## Rejected / No Current Fix

- MiMo-003 / DS Doc generic hint: no change; hint remains optional and no concrete recovery hint was identified.
- DS-01 `_web_process_failed_envelope` blank-input fallback: no change; fallback still creates a valid envelope.
- DS-02 `_require_non_negative_finite_number` accepting `int`: no change; finite non-negative integer input remains acceptable numeric behavior for float grace fields.

## Verified

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/host/test_toolruntime_executor.py -q`: `114 passed`
- `source .venv/bin/activate && pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed.
- `git status --short`: modified `tests/host/test_toolruntime_executor.py` and `tests/runtime/test_config_loader.py`; untracked artifact files are `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-fix-codex.md`, `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-review-ds.md`, and `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-review-mimo.md`.

## Residual Risks / Blockers

- No blocking open question.
- Remaining live browser environment residual from prior S4 artifact is unchanged and not part of this aggregate fix.

## Completion Status

READY_FOR_CONTROLLER

Artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-fix-codex.md`
