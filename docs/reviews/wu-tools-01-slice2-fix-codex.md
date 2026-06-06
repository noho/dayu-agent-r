# WU-TOOLS-01 Slice S2 Fix

Gate: fix  
Work unit: WU-TOOLS-01  
Slice: S2 Tool Adapter And Typed Provider Config  
Agent: AgentCodex  
Controller adjudication: docs/reviews/wu-tools-01-slice2-code-review-controller-adjudication.md  
Fix artifact: docs/reviews/wu-tools-01-slice2-fix-codex.md

## Scope

本次 fix 只处理 Controller adjudication 接受的 4 项 S2 adapter finding。未新增 Doc / Fins / Web provider 或业务工具，未修改 `ToolDefinition`、`ToolRuntime`、Engine public contract，未迁移 OLD `ToolRegistry`、OLD `TruncationManager`、OLD `fetch_more` 或 OLD projection owner。

## Files Changed

- `dayu/tools/_legacy_adapter/definition_adapter.py`
- `tests/tools/test_legacy_tool_adapter.py`
- `docs/reviews/wu-tools-01-slice2-fix-codex.md`

## Findings Fixed

### M1 Batch `fetch_more` Handling Consistency

Status: fixed in current slice.

`adapt_collected_tools(...)` now fails fast with `ValueError` when any collected declaration is named reserved `fetch_more`, matching `adapt_collected_tool(...)`. The previous silent skip path was removed so provider declaration mistakes are visible.

Test updated: `test_fetch_more_is_not_emitted_as_business_tool` now expects batch fail-fast behavior.

### M2 Missing Tests For Implemented Paths

Status: fixed in current slice.

Added coverage for:

- `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER`: `test_serial_per_provider_shares_lock_across_tool_names` proves different tool names share one provider-wide lock and do not enter sync callables concurrently.
- Generic exception projection: `test_generic_exception_projects_to_execution_error_failure` proves a plain `RuntimeError` maps to current `ToolFailedOutcome` with `error="execution_error"`.

### D1 Strict OLD Envelope Detection

Status: fixed in current slice.

`project_legacy_return(...)` now treats success as an OLD envelope only when `ok is True` and the `value` key is present. Plain business dictionaries with an `ok` field fall through to normal success projection.

Test added: `test_plain_business_dict_with_ok_field_is_preserved`.

### D2 Path Policy Coverage Fail-Closed

Status: fixed in current slice.

When `ToolPathValidationPolicy` is provided, `_project_paths(...)` now verifies that `path_policy.file_path_params` covers every `declaration.file_path_params` entry. Incomplete coverage returns a current `ToolFailedOutcome` with `permission_denied` before the migrated callable is invoked.

Test added: `test_incomplete_path_policy_coverage_fails_before_calling_migrated_function`.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py
```

Result: 93 passed.

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
git diff --check
```

Result: passed with no output.

## README Decision

No README update was needed. The fix only hardens existing S2 adapter behavior and adds tests; it does not change user-facing config schema, package responsibilities, test layer conventions, developer reading order, CLI usage, or public commands.

## Residual Risks

- Provider-specific typed config parsing remains covered by later approved S3 / S4 / S5 slices.
- Provider-specific Doc path whitelist behavior remains covered by later approved S3.
- Concrete migrated truncating tools remain covered by later approved S3 / S4 / S5.
- Combined ToolRuntime accept path remains covered by later approved S6.

No unclassified residual risk or blocker remains for this S2 fix gate.

## Completion Status

Fix gate complete. Changes are left uncommitted as requested. No commit, push, PR, or re-review gate was entered.
