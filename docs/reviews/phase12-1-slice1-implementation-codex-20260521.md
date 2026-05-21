# Phase 12.1 Slice 1 Implementation - AgentCodex - 2026-05-21

## Gate

- Current gate: Phase 12.1 Slice 1 implementation.
- Design truth: `docs/host/design.md`.
- Control truth: `docs/host/implementation-control.md`.
- Plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`.
- Plan review adjudication: `docs/reviews/phase12-1-plan-review-controller-adjudication-20260521.md`.

## Scope

- Objective: 修正 Host public policy dataclass typed shape 与 `ToolTruncateSpec` declaration/effective 语义，为后续 ConfigLoader / adapter 生成 typed Host input 提供稳定目标。
- Non-goals: 未修改 Host public handle methods、public request / response dataclass field names、`dayu.host` 包根 public exports、Engine execution loop、ToolRuntime accept barrier、财报工具、Fins storage、ConfigLoader、ScenePrepare、config assets、scene assets、smoke script。
- Public surface statement: `OpenHostOptions.context_budget_policy` 与 `OpenHostOptions.memory_projection_policy` 字段名未改变；`open_host(options)` public opener 字段名未改变；`fetch_more` 名称继续来自 `FrameworkToolName.FETCH_MORE`，未进入 config。

## Preflight Dirty-File Classification

Preflight commands run before edits:

- `git status --short`
- `git diff --name-status`
- `git diff --stat`

Observed pre-existing dirty files:

- Design/control refinement: `docs/host/design.md`, `docs/host/implementation-control.md`; 本 slice 只读取，不编辑。
- Pre-existing half-finished / out-of-scope work: `README.md`, `utils/smoke_host_public_multiturn.py`; 按 handoff 分类为 Slice 1 范围外，未编辑。
- Pre-existing untracked planning/review artifacts: `docs/host/phase12-1-runtime-assembly-correction-plan.md`, `docs/host/runtime-assembly-followup-discussion.md`, `docs/reviews/phase12-1-plan-review-controller-adjudication-20260521.md`, `docs/reviews/phase12-1-plan-review-ds-20260521.md`, `docs/reviews/phase12-1-plan-review-mimo-20260521.md`; 只读取 plan/adjudication。

Current slice intended edits:

- Source/contracts/runtime: `dayu/host/context_policy.py`, `dayu/host/context_budget.py`, `dayu/host/memory.py`, `dayu/contracts/tool_schema.py`, `dayu/host/tool_runtime.py`, `dayu/runtime/tool_truncation.py`, `dayu/runtime/__init__.py`.
- Narrow Host wiring required by migrated policy type: `dayu/host/api.py`, `dayu/host/command.py`, `dayu/host/open_host.py`.
- Tests: `tests/host/test_context_policy.py`, `tests/host/test_context_budget.py`, `tests/host/test_memory_projection.py`, `tests/host/test_toolruntime_truncation_fetch_more.py`, plus adjacent Host tests touched only because pyright over `tests/host` still referenced migrated contracts: `tests/host/test_dispatch_scheduler.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_public_compact_smoke.py`, `tests/host/test_public_contracts.py`, `tests/host/test_run_input_builder.py`.
- Docs: `dayu/host/README.md`, `dayu/README.md`, this artifact.

## Call-Site Audit Before Coding

Removed `ContextBudgetPolicy` fields found in direct policy/factory call sites:

- `dayu/host/context_policy.py`: dataclass/factory validation owned by this slice.
- `dayu/host/context_budget.py`: estimator read `reserved_output_tokens`, `safety_margin_ratio`, `hard_threshold_tokens`, `minimum_protection_tokens`.
- `dayu/host/api.py`, `dayu/host/command.py`, `dayu/host/open_host.py`: public command/open-host option wiring still uses frozen option field names and needed mapping into ratio-first policy without renaming those fields.
- `tests/host/test_context_policy.py`, `tests/host/test_context_budget.py`: owned tests for policy and estimator.
- Adjacent pyright/test callers: `tests/host/test_public_contracts.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_public_compact_smoke.py`.
- Other hits such as `BudgetEstimate.hard_threshold_tokens`, compaction request facts, command option fields, and `OpenHostOptions` fields are not removed policy dataclass fields and were intentionally kept.

Removed `MemoryProjectionPolicy` size-unit constructor fields found in direct call sites:

- `dayu/host/memory.py`: policy dataclass/factory and internal memory projection budget reads.
- `dayu/host/run_input.py`: reads stable layer effective units; kept working through internal derived property.
- `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py`: direct constructors migrated to ratio/floor/cap fields.

`ToolTruncateSpec` declaration/effective audit:

- `dayu/contracts/tool_schema.py`: constructor required exact limit key and lacked target-field ambiguity validation.
- `dayu/host/tool_runtime.py`: effective bundle previously passed declaration specs directly to truncation manager.
- `dayu/host/tool_runtime_schema_projection.py`: only projects declaration JSON; no behavior change required.
- Tests under `tests/host/test_toolruntime_truncation_fetch_more.py` and `tests/host/test_phase6_toolruntime_integration.py` covered ToolRuntime truncation/fetch_more path.

Expected file-level diff summary before coding:

- `context_policy.py`: replace reserved-output/safety-margin/min-protection/hard-token fields with context-window ratio fields and threshold-token mapping helper.
- `context_budget.py`: derive budget thresholds from context window ratios.
- `memory.py`: replace fixed size-unit constructor fields with context-window ratio/floor/cap fields and internal derived size-unit properties.
- `tool_schema.py`: allow missing enabled limit/TTL, validate target ambiguity, expose strategy limit-key helper.
- `tool_runtime.py`: default-fill declaration specs before ToolRuntime consumes them.
- `dayu.runtime`: add runtime-neutral default-fill helper because it only depends on `dayu.contracts` plus caller-supplied policy defaults.
- Tests/docs: update contract assertions and public documentation.

## Implementation Summary

- `ContextBudgetPolicy` now carries `context_window_size`, `soft_threshold_context_ratio`, `hard_threshold_context_ratio`, compaction attempt limits, and `policy_ref`; old policy fields are not dataclass fields.
- `estimate_context_budget` now treats `context_window_size` as the input budget and derives soft/hard threshold tokens via ratios.
- Existing frozen command/open-host option field names remain intact; internal wiring maps old option inputs into ratio-first policy or preserves the already supplied `HostLocalExecutionOptions.context_budget_policy`.
- `MemoryProjectionPolicy` now carries `context_window_size` and ratio/floor/cap triples for raw turn, history pool, and stable layer budgets; Host derives effective size units internally.
- `ToolTruncateSpec` enabled declaration can omit the strategy limit and TTL; invalid target combinations and invalid provided limits still fail fast.
- Added `dayu.runtime.tool_truncation.effective_tool_truncate_spec()` as the default-fill helper. Placement note: this was required by adjudication because the helper only consumes `ToolTruncateSpec` and caller-supplied defaults. It is outside the handoff's initial source-module list, but keeping it in Host would violate the accepted placement constraint.
- `ToolRuntime` now stores effective truncate specs in the effective bundle while preserving declaration projection for schema digest/source declaration.

## README Sync Decision

- Updated `dayu/host/README.md` because Host public policy/truncation contract facts changed.
- Updated `dayu/README.md` because `dayu.runtime` gained a new layer-neutral helper category.
- Did not update `tests/README.md`: no testing convention changed.
- Did not update root `README.md`: existing dirty root README is out-of-scope and no allowed Slice 1 trigger applied.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`  
  Result: passed, `75 passed`.
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_phase6_toolruntime_integration.py -q`  
  Result: passed, `8 passed`.
- `source .venv/bin/activate && python -m pyright dayu/host dayu/contracts tests/host`  
  Result: passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`  
  Result: passed.

## Residual Risks

- `dayu/host/api.py`, `dayu/host/command.py`, and `dayu/host/open_host.py` were touched even though not listed in the initial allowed source modules. Reason: pyright over `dayu/host` and the frozen public option fields required an internal mapping layer after the policy dataclass migration. Public command/opener field names and handle methods were not changed.
- `MemoryProjectionPolicy` keeps internal derived properties named `max_raw_turn_size_units`, `history_pool_size_units`, and `stable_layer_size_units` so existing Host internals can consume effective units without duplicating derivation logic. They are not dataclass constructor fields.
- Tool truncation policy defaults used by `ToolRuntime` are local named defaults until later slices introduce ConfigLoader/runtime assembly policy input.

## Stop Status

Slice 1 implementation complete. No commits, pushes, PRs, or additional gates were started.

## Fix Addendum - 2026-05-21

### Source Review Inputs

- Controller adjudication: `docs/reviews/phase12-1-slice1-code-review-controller-adjudication-20260521.md`
- MiMo review: `docs/reviews/phase12-1-slice1-code-review-mimo-20260521.md`
- DS review: `docs/reviews/phase12-1-slice1-code-review-ds-20260521.md`

### Accepted Findings Fixed

- MiMo F-1 / DS F1: `_command_context_budget_fields_from_open_host_options` ignored explicit `OpenHostOptions.context_budget_policy` and returned fallback command context window in both branches.
  - Status: fixed.
  - Fix: non-`None` policy branch now preserves `context_policy.context_window_size` in the internal `HostCommandHandleOptions` mapping. The reserved-output value remains an internal validation placeholder because ratio-first `ContextBudgetPolicy` no longer exposes public reserved output tokens; it is derived as a positive value smaller than the supplied context window.
- MiMo F-2: `_CommandContextBudgetFields` kept stale `hard_threshold_tokens` and `minimum_protection_tokens`.
  - Status: fixed.
  - Fix: removed those stale internal fields and now passes `None` directly for the unchanged public command option fields. Public option field names were not changed.

### Changed Files In Fix Pass

- `dayu/host/open_host.py`
- `tests/host/test_open_host_runtime.py`
- `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md`

### Fix Validation

- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py::test_command_options_reflect_explicit_context_budget_policy -q`  
  Result: passed, `1 passed`.
- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`  
  Result: passed, `75 passed`.
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_phase6_toolruntime_integration.py -q`  
  Result: passed, `8 passed`.
- `source .venv/bin/activate && python -m pyright dayu/host dayu/contracts tests/host`  
  Result: passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`  
  Result: passed.

### Residual Risk Classification

- ToolRuntime truncation default constants remain deferred to Slice 2 / Slice 4 per controller adjudication.
- `MemoryProjectionPolicy.policy_ref` remains rejected for this slice per controller adjudication.
- No new residual risk introduced by this fix pass.
