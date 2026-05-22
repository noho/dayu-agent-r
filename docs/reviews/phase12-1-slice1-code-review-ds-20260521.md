# Phase 12.1 Slice 1 Code Review — AgentDS — 2026-05-21

## Verdict: PASS with Findings

Slice 1 implementation is correct in its primary objectives: ratio-first `ContextBudgetPolicy`, ratio/floor/cap `MemoryProjectionPolicy`, and declaration/effective `ToolTruncateSpec` semantics. No old-schema compatibility path was introduced. Public Host surface (`OpenHostOptions` fields, handle methods, request/response dataclass field names) is unchanged. `dayu.runtime.tool_truncation` import boundary is clean. Tests pass (75 + 8), pyright clean.

One High severity finding below requires a fix; the rest are Medium/Low or Informational.

---

## Findings

### F1 [HIGH] `_command_context_budget_fields_from_open_host_options` 两个分支返回相同 fallback 值

**File:** `dayu/host/open_host.py:578-610`

**Evidence:** 函数内 `if context_policy is None` 分支和 `else` 分支的 `return` 语句完全一致——都返回带有 `_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE` (8192) 和 `_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS` (1024) 的 `_CommandContextBudgetFields`。当调用方显式传入了 `ContextBudgetPolicy`（例如 `context_window_size=128000`）时，该 policy 的窗口大小完全未被使用。

**Impact assessment:** 在当前 `open_host` 流程中，`_CommandContextBudgetFields` 仅用于构造 `HostCommandHandleOptions`，而后者只服务于 `create_host_command_handle`（该函数拒绝 `local_execution`，仅打开 durable store）。真正的 context budget policy 通过 `_local_execution_options_from_open_host_options` 的 `context_budget_policy=options.context_budget_policy` (line 644) 直达 `HostLocalExecutionOptions` 并被 `HostDispatchScheduler` 使用。因此当前没有运行时正确性 bug。

**Root cause:** 代码意图是当 `context_budget_policy` 非 None 时从中提取 `context_window_size` 作为 command options 的窗口大小，但实现时两个分支被写成了相同的 fallback。这是 dead/incorrect code path，且 docstring 声称"生产调用方需要显式预算治理时必须传入 ContextBudgetPolicy"与实现行为不一致。

**Recommendation:** 修正 else 分支，从 `context_policy.context_window_size` 提取 `context_window_size`，`reserved_output_tokens` 从 policy 的 `soft_threshold_context_ratio` 派生的 soft_threshold 反推，或直接使用更合理的派生逻辑。如果当前阶段 `HostCommandHandleOptions` 的 context budget 字段确实只用于 validation fallback 且不需要反映真实 policy，应在 docstring 中明确说明原因，并合并两个分支避免 dead code 误导读者。

---

### F2 [MEDIUM] `MemoryProjectionPolicy` 缺少 `policy_ref` 字段

**File:** `dayu/host/memory.py:599-635`

**Evidence:** `ContextBudgetPolicy` 有 `policy_ref: str` 字段用于 policy snapshot/composition ref。`MemoryProjectionPolicy` 没有对应的 policy ref 字段。在 memory projection snapshot 中，`policy_digest` 通过 `digest_memory_projection_policy()` 计算，但缺少一个稳定的 human-readable policy ref。

**Impact:** 不影响运行时正确性。但对于 policy governance、审计和诊断场景，缺少 policy ref 会降低可追溯性，与 `ContextBudgetPolicy` 的设计不对称。

**Recommendation:** 考虑为 `MemoryProjectionPolicy` 增加 `policy_ref: str` 字段。这可以与 Slice 4 config assembly 一起处理，在 Slice 1 中作为已知缺口记录即可。

---

### F3 [MEDIUM] `ToolRuntime` 中的默认截断常量是临时占位

**File:** `dayu/host/tool_runtime.py`（`_DEFAULT_TRUNCATION_LIMITS_BY_STRATEGY`、`_DEFAULT_TRUNCATION_TTL_SECONDS`）

**Evidence:** 这两个模块级常量（约在 line 2190 附近引用）是硬编码的默认值，用于 `effective_tool_truncate_spec()` 调用中补齐 declaration spec 的缺失 limit/TTL。它们不属于任何 typed policy，且在实现 artifact 中标注为"local named defaults until later slices introduce ConfigLoader/runtime assembly policy input"。

**Impact:** 当前行为正确——declaration spec 被正确补齐。但这些默认值不与任何 config/policy 真源关联，后续 Slice 2-4 如果遗漏替换，可能变成隐藏的生产默认值。

**Recommendation:** 在 Slice 2 或 Slice 4 的 implementation artifact 中显式记录需要替换这两个常量。可选方案：在 `dayu/host/tool_runtime.py` 中增加 `# TODO(Phase12.1-Slice4)` 注释标记这两个常量的临时性。

---

### F4 [LOW] `context_budget_policy_from_threshold_tokens` 位于 public export 但在 plan 中未明确其归属

**File:** `dayu/host/context_policy.py:201-263`

**Evidence:** 该函数被导出到 `__all__`，并被 `tests/host/test_dispatch_scheduler.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_public_compact_smoke.py` 等测试使用。其 docstring 明确说明"该 helper 只服务于已有 Host opener / command option 字段到 ratio-first policy 的边界映射"。

**Assessment:** 这是一个内部映射 helper，不是 compatibility wrapper。它将已冻结的 `HostCommandHandleOptions` 字段（`context_window_size`、`reserved_output_tokens`、`hard_threshold_tokens`、`minimum_protection_tokens`）映射为新的 ratio-first `ContextBudgetPolicy`。这是合理的边界映射，不是一个需要消除的兼容层——因为 `HostCommandHandleOptions` 字段名本身是 frozen public surface 的一部分。

**Recommendation:** 无需修改。但在 Slice 4/5 assembly helpers 就位后，可以重新评估 `context_budget_policy_from_threshold_tokens` 是否仍被需要，或是否被 Service/composition helper 取代。当前保留即可。

---

### F5 [LOW] `MemoryProjectionPolicy` internal derived properties 命名可能产生歧义

**File:** `dayu/host/memory.py`（`max_raw_turn_size_units`、`history_pool_size_units`、`stable_layer_size_units` 等 derived properties）

**Evidence:** 实现 artifact 说明这些是"internal derived properties"而非 dataclass constructor fields。它们是 `MemoryProjectionPolicy` 上的 `@property`，从 `context_window_size * ratio` 派生，受 floor/cap 约束。

**Assessment:** 设计合理。这些属性不会出现在 `dataclass` 构造函数签名中，调用方不能直接设置。它们只是 Host 内部 memory projection 的 effective size units 缓存。

**Recommendation:** 确认这些 property 的 docstring 清晰标注为 "internal derived" 以避免调用方误以为是可配置字段。当前实现已满足。

---

### F6 [INFO] `dayu.runtime.tool_truncation` 中的 `_require_positive_int` / `_require_non_negative_int` 与 Host 中的同名 helper 重复

**File:** `dayu/runtime/tool_truncation.py:89-118` vs `dayu/host/_public_validation.py`、`dayu/host/api.py`

**Evidence:** `dayu.runtime.tool_truncation` 模块在模块私有作用域中定义了自己的 `_require_positive_int` 和 `_require_non_negative_int`，语义与 `dayu.host._public_validation` 中的对应函数相同，但实现略有不同（runtime 版本不检查 bool dispatch 细节）。

**Assessment:** 这不是 import boundary 违规——`dayu.runtime` 不能 import `dayu.host`。这是两个独立层各自实现相同语义的私有校验函数。不构成代码重复问题，因为它们的所属层不同且语义契约独立。

**Recommendation:** 无需修改。如果后续 `dayu.runtime` 中其他模块也需要这些校验，可以考虑提取为 `dayu.runtime._validation` 模块级私有 helper，但这超出了 Slice 1 范围。

---

### F7 [INFO] 测试覆盖良好，pyright 干净

**Evidence:**
- `pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`: 75 passed
- `pytest tests/host/test_public_open_host_options.py tests/host/test_phase6_toolruntime_integration.py -q`: 8 passed
- `python -m pyright dayu/host dayu/contracts tests/host`: 0 errors, 0 warnings, 0 informations

**Assessment:** 测试覆盖了 ratio-first policy 构造、阈值派生、budget 估算、truncation declaration/effective 语义。测试用例跟随 policy shape 迁移，旧测试被更新而非删除。

---

## Compliance Checklist

| Check | Status | Notes |
|---|---|---|
| Ratio-first `ContextBudgetPolicy` correctness | PASS | context_window_size * ratio → floor → threshold; soft < hard enforced |
| `MemoryProjectionPolicy` ratio/floor/cap correctness | PASS | ratio ∈ (0,1], floor ≤ cap, context_window_size applied |
| Public Host command/opener field names unchanged | PASS | `OpenHostOptions.context_budget_policy` / `.memory_projection_policy` field names preserved |
| Public request/response dataclass fields unchanged | PASS | No new fields; no field renames |
| `api.py` / `command.py` / `open_host.py` narrow internal mapping | PASS (with F1 caveat) | No new public surface; F1 dead code in open_host.py |
| No compatibility wrappers | PASS | `context_budget_policy_from_threshold_tokens` is a boundary mapper, not a compat wrapper |
| `ToolTruncateSpec` declaration can omit limit/TTL | PASS | `limits.get(key)` returns None → effective fill; invalid limits still fail fast |
| Effective spec helper fills defaults | PASS | `effective_tool_truncate_spec()` in `dayu.runtime.tool_truncation` |
| `fetch_more` remains framework name | PASS | `FrameworkToolName.FETCH_MORE`; not in config |
| `dayu.runtime.tool_truncation` clean import boundary | PASS | Only imports `dayu.contracts.tool_schema` |
| No old schema compatibility path | PASS | No old field names, deprecated aliases, or compat readers |
| Tests adequate | PASS | 75 + 8 passed; pyright clean |
| README sync adequate | PASS | `dayu/host/README.md` updated for ratio-first policy and ToolTruncateSpec boundary; `dayu/README.md` updated for new `tool_truncation` module |

---

## Open Questions

1. **Q1:** `_command_context_budget_fields_from_open_host_options` 的 else 分支是否需要修复（见 F1），还是当前阶段有意使用 fallback 且后续 Slice 会重写整个 opener wiring？

2. **Q2:** `MemoryProjectionPolicy.policy_ref` 是否应在 Slice 1 补齐，还是等到 Slice 4 config assembly 时与 truncation policy ref 一起添加？

## Residual Risks

- **R1 (F1):** `open_host.py` 中的 dead code path — 当前不影响运行时正确性但降低代码可读性，后续维护者可能误以为 `context_budget_policy` 被正常消费。Owner: Slice 1 fix agent or deferred to Slice 4 opener wiring refactor.
- **R2 (F3):** Truncation 默认常量 (`_DEFAULT_TRUNCATION_LIMITS_BY_STRATEGY`、`_DEFAULT_TRUNCATION_TTL_SECONDS`) 是临时硬编码，后续 Slice 如果遗漏替换将成为隐藏的 production default。Owner: Slice 2/4 implementation agent.
- **R3 (artifact):** `dayu/host/api.py`、`dayu/host/command.py`、`dayu/host/open_host.py` 在初始 plan 中未列为 owned source modules，实现 artifact 已记录原因（pyright 和 frozen public option field mapping 需要），风险已说明。

## Review Stop

Review complete. No commits, pushes, PRs, or gates were started.
