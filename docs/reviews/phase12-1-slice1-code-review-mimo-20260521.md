# Phase 12.1 Slice 1 Code Review — MiMo — 2026-05-21

## Gate

- Review scope: Slice 1 implementation only.
- Design truth: `docs/host/design.md`.
- Control truth: `docs/host/implementation-control.md`.
- Plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`.
- Plan adjudication: `docs/reviews/phase12-1-plan-review-controller-adjudication-20260521.md`.
- Implementation artifact: `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md`.

## Files Reviewed

- `dayu/host/context_policy.py`
- `dayu/host/context_budget.py`
- `dayu/host/memory.py` (MemoryProjectionPolicy, derived properties, `_effective_size_units`, validation)
- `dayu/contracts/tool_schema.py` (ToolTruncateSpec, `truncate_limit_key_for_strategy`)
- `dayu/host/tool_runtime.py` (EffectiveToolBundle, EffectiveToolBundleBuilder.build, effective spec usage, `dayu.runtime.tool_truncation` import)
- `dayu/runtime/tool_truncation.py`
- `dayu/runtime/__init__.py`
- `dayu/host/api.py` (OpenHostOptions, HostCommandHandleOptions, `_context_budget_policy_from_command_options`)
- `dayu/host/command.py` (compose_host_local_execution_options)
- `dayu/host/open_host.py` (`_CommandContextBudgetFields`, `_command_context_budget_fields_from_open_host_options`, `_local_execution_options_from_open_host_options`)
- `tests/host/test_context_policy.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `dayu/host/README.md`
- `dayu/README.md`

## Findings

### F-1 [Medium] open_host.py `_command_context_budget_fields_from_open_host_options` 两个分支返回相同值

**File:** `dayu/host/open_host.py:578-610`

`_command_context_budget_fields_from_open_host_options` 的 `context_policy is None` 和 `context_policy is not None` 两个分支返回完全相同的 `_CommandContextBudgetFields` fallback 值（`context_window_size=8192`, `reserved_output_tokens=1024`, `hard_threshold_tokens=None`, `minimum_protection_tokens=None`）。

当调用方通过 `OpenHostOptions.context_budget_policy` 显式传入 `ContextBudgetPolicy`（例如 `context_window_size=16384`），`_command_options_from_open_host_options` 仍向 `HostCommandHandleOptions` 写入 fallback `context_window_size=8192`。主 dispatch 路径通过 `_local_execution_options_from_open_host_options` 正确传递 policy（line 644: `context_budget_policy=options.context_budget_policy`），不受此 bug 影响；但 command handle fallback 路径（`compose_host_local_execution_options` 在 `local_execution.context_budget_policy is None` 时从 command options 派生 policy）会使用错误的 window size。

所有现有测试通过，因为测试要么走 dispatch 路径（绕过此 mapping），要么直接构造 command handle options。但该代码缺陷会在后续 slice 或真实 Service-like 装配中暴露。

**建议修复：** `context_policy is not None` 分支应从 `context_policy.context_window_size` 和 `context_policy.hard_threshold_context_ratio` 派生字段值，或至少使用 policy 的 `context_window_size` 替代 fallback 常量。

### F-2 [Low] `_CommandContextBudgetFields` 保留旧 policy 字段名

**File:** `dayu/host/open_host.py:88-100`

`_CommandContextBudgetFields` dataclass 保留了 `hard_threshold_tokens` 和 `minimum_protection_tokens` 字段，这些是 Slice 1 迁移前的旧 policy 字段名。当前 mapping 函数对这两个字段始终写入 `None`。虽然不影响正确性，但作为 Slice 1 新引入的内部类型，保留已移除的字段名会误导后续维护者。

**建议：** 该 dataclass 应只保留 `context_window_size` 和 `reserved_output_tokens`（或按 F-1 修复后进一步简化），移除不再由 ratio-first policy 派生的字段。

## PASS Items

### ContextBudgetPolicy ratio-first typed shape

`ContextBudgetPolicy`（`context_policy.py:41-115`）字段为 `context_window_size`、`soft_threshold_context_ratio`、`hard_threshold_context_ratio`、compaction 次数上限和 `policy_ref`。`__post_init__` 校验 ratio ∈ (0, 1]、soft < hard、hard threshold ≥ `MIN_CONTEXT_HARD_THRESHOLD_TOKENS`。旧字段（`reserved_output_tokens`、`safety_margin_ratio`、`hard_threshold_tokens`、`minimum_protection_tokens`）已从 dataclass 移除。`context_budget_policy_from_threshold_tokens` helper 从已计算 token 反推 ratio，用于旧 command option 边界映射。PASS。

### context_budget.py ratio-derived threshold behavior

`estimate_context_budget`（`context_budget.py:287-342`）使用 `policy.context_window_size` 作为 `input_budget_tokens`，通过 `floor(context_window_size * ratio)` 派生 soft/hard threshold。`safety_margin_tokens = input_budget_tokens - soft_threshold_tokens`。`decide_context_budget` 三态决策逻辑正确。`BudgetEstimate.__post_init__` 校验 hard threshold ≥ `MIN_CONTEXT_HARD_THRESHOLD_TOKENS`。测试覆盖 ratio 派生、soft/hard 边界、small ratio 正边界。PASS。

### MemoryProjectionPolicy ratio/floor/cap typed shape

`MemoryProjectionPolicy`（`memory.py:599-683`）字段为 `context_window_size`、ratio/floor/cap 三组（raw turn、history pool、stable layer）、`max_pinned_items`、`max_verified_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、`max_lag_events_for_inline_delta`、`max_delta_repair_events`。`__post_init__` 校验 ratio ∈ (0, 1]、floor ≤ cap。内部派生 property `max_raw_turn_size_units`、`history_pool_size_units`、`stable_layer_size_units` 通过 `_effective_size_units(context_window_size, ratio, floor, cap)` 计算，逻辑为 `min(cap, max(floor, int(window * ratio)))`。PASS。

### Host public field names unchanged

- `OpenHostOptions.context_budget_policy`、`OpenHostOptions.memory_projection_policy`：字段名未变（`api.py:1023-1025`）。
- `open_host(options)` public opener 字段名未变（`open_host.py:522-530`）。
- `Host` protocol 方法名、request / response dataclass 字段名均未变（`api.py` 全文）。
- `HostCommandHandleOptions.context_window_size`、`reserved_output_tokens` 字段名未变（`api.py:1471-1472`）。
- `HostLocalExecutionOptions.context_budget_policy`、`memory_projection_policy` 字段名未变（`api.py:747-754`）。
PASS。

### api.py / command.py / open_host.py narrow internal mapping

- `api.py` 新增 `_context_budget_policy_from_command_options`，从旧 command options 字段映射到 ratio-first policy，仅用于 command handle fallback 路径。
- `command.py` `compose_host_local_execution_options` 优先使用 `local_execution.context_budget_policy`，fallback 到 command options 派生。
- `open_host.py` `_local_execution_options_from_open_host_options` 直接传递 `options.context_budget_policy`。
- 无 compatibility wrapper，无新 public surface。
PASS（不含 F-1 bug）。

### ToolTruncateSpec declaration/effective semantics

- `ToolTruncateSpec`（`tool_schema.py:98-181`）：enabled + strategy 时允许 `limits` 缺对应 key、`ttl_seconds=None`；仍禁止未知 strategy、非法 limit、target_field + field_path 同时设置。
- `truncate_limit_key_for_strategy`（`tool_schema.py:183-193`）：返回策略对应 limit key。
- `effective_tool_truncate_spec`（`tool_truncation.py:19-64`）：补齐缺省 limit 和 TTL，disabled spec 原样返回。
- `EffectiveToolBundleBuilder.build`（`tool_runtime.py:2190-2199`）对每个有 `truncate` 的 definition 调用 `effective_tool_truncate_spec`，结果存入 `truncate_specs_by_name`。
- `fetch_more` 名称来自 `FrameworkToolName.FETCH_MORE`，不进入 config。
PASS。

### dayu.runtime.tool_truncation import boundary

`dayu.runtime.tool_truncation`（`tool_truncation.py:1-6`）只 import `dayu.contracts.tool_schema` 和 `collections.abc.Mapping`。无 Host / Engine / Service / UI / Fins import。PASS。

### Tests adequacy

- `test_context_policy.py`：覆盖 ratio 验证、compaction attempt budget、soft/hard threshold 派生。
- `test_context_budget.py`：覆盖 budget 估算、ratio 派生阈值、soft/hard decision、tool schema overhead、usage observation、EventLog compaction event helper。
- `test_memory_projection.py`：覆盖 snapshot 创建/读取/rollback、typed contract 验证、pinned state、verified fact、working assumption、continuity、episode summary、history pool budget、rebuild、catch-up、reset。
- `test_toolruntime_truncation_fetch_more.py`：覆盖 declaration 允许缺省 limit/TTL、target ambiguity 拒绝、四种策略截断与 fetch_more 补读、cursor 单次使用、TTL 过期、scope token 校验、digest 校验。
PASS。

### README sync

- `dayu/host/README.md`：ContextBudgetPolicy ratio-first 描述、MemoryProjectionPolicy ratio/floor/cap 描述、ToolTruncateSpec declaration/effective 描述均已更新。
- `dayu/README.md`：`dayu.runtime` 已实现能力列表新增 `tool_truncation` 描述。
PASS。

### No old schema compatibility path

未引入旧 schema compatibility reader、compatibility wrapper、compatibility re-export 或兼容测试。PASS。

## Open Questions

无。

## Residual Risks

- F-1 的 open_host.py mapping bug 当前不影响主 dispatch 路径，但会在后续 ConfigLoader / adapter 生成 typed Host input 时暴露。建议在 Slice 2 前修复。
- `_CommandContextBudgetFields`（F-2）作为 Slice 1 新引入的内部类型，保留旧字段名会在后续 slice 维护中产生困惑。

## Verdict

**Conditional PASS.** F-1 是 Medium 级别代码缺陷，不影响主 dispatch 路径正确性，但应在后续 slice 开始前修复。F-2 是 Low 级别清理项。其余所有 review lens 均 PASS。
