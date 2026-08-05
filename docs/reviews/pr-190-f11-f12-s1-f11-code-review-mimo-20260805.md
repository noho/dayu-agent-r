# Code Review — PR 190 F11/F12 S1 F11 Implementation

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `19a6d6257504876e01da3067bbc4cf33ae99525d`（implementation artifact 指定 base）
- Output file: `docs/reviews/pr-190-f11-f12-s1-f11-code-review-mimo-20260805.md`
- Included scope: `dayu/host/context_events.py`、`dayu/host/durable/tool_trace.py`、`dayu/host/tool_trace_analysis_input.py`、`dayu/host/tool_trace_analysis_contracts.py`、`dayu/host/tool_trace_analysis_rules.py`、`dayu/host/tool_trace_analysis.py`、`dayu/host/README.md` 及其对应 5 个测试文件
- Excluded scope: F12 compaction contract redesign（S2-S5 owned）、provider/model selection、CLI/Service 层
- Parallel review coverage: 无

## Review Checklist Verification

以下按用户要求的验证点逐项展开。

### 1. canonical SuccessfulRunnerResponseIdentity 是否为唯一 response truth

**PASS。** `parse_successful_runner_response_identity()` 是 `SuccessfulRunnerResponseIdentity` 的唯一公开 strict parser（`context_events.py:1740-1795`），由 `__all__` 导出。canonical compact validator（`validate_context_compacted_payload` L1295）、attempt-rejected validator（`validate_context_compaction_attempt_rejected_payload` L1620-1631）与 Tool Trace resolver（`_resolved_compactor_response_from_row` L691）均复用该 parser，未各自读取 nested identity 字段。

### 2. successful compact / post-success rejected / no-success rejected 三态是否严格

**PASS。** `context_events.py:995-1001` 定义：

```python
_POST_SUCCESS_REJECTION_CATEGORIES = frozenset(("quality_check_rejected", "hard_threshold_after_compact"))
_NO_SUCCESS_REJECTION_CATEGORIES = frozenset(("cancellation_requested",))
```

`validate_context_compaction_attempt_rejected_payload()` L1628-1631 强制：
- post-success category + `successful_response_identity is None` → ValueError
- no-success category + `successful_response_identity is not None` → ValueError

`CompactorResponseDisposition` 枚举（`tool_trace.py:129-133`）只含 `ACCEPTED` 与 `ATTEMPT_REJECTED`。`ResolvedCompactorResponseIdentity.__post_init__()` L429-434 强制 `ACCEPTED` 必须有 non-null `successful_response_identity`。`ToolTraceCompactorResponseSummary.__post_init__()` L512-558 强制 accepted summary 的 identity 字段整体 non-null、no-success summary 的 identity 字段整体 null。

其他 failure category（如 `invalid_json_output`）允许 identity 为 null 或 non-null，符合设计意图：canonical terminal 只记录 Engine 事实，不限制预存取阶段。

### 3. manifest ref/digest、operation、attempt、parent Host Run 与 compactor Engine request identity 是否 exact 同源且 mismatch fail closed

**PASS。** 验证链路：

1. **EventLog 写入时绑定**：`build_context_compacted_payload()` L1230-1235 调用 `_validate_successful_response_manifest_binding()`（L1671-1708），强制 `manifest.compaction_operation_id == operation_id`、`manifest.compaction_attempt_number == attempt_number`、`successful_response_identity.runner_request_identity.run_id == manifest.compactor_engine_run_id`。attempt-rejected builder 同样调用该函数（L1528-1533）。

2. **Resolver 读取时校验**：`_resolved_compactor_response_from_row()` L676-689 强制 operation/attempt 同时匹配 manifest_ref/digest。若 `operation_matches != manifest_matches`，抛 `CompactorResponseResolutionError`。L693-699 校验 Engine run identity。

3. **Hot row 二次校验**：`_typed_manifest_from_signal()` L544-560 重新从 canonical hot event 读取并比对 signal 的 14 个 identity 字段，任何不一致抛 `HostDurableError`。

### 4. EventLog terminal 分页是否完整 exhaustion、cursor/duplicate/malformed 反例是否正确

**PASS。** `_resolve_compactor_response_identity()` L586-634：

- 使用 `read_run_events_by_types_page()` 以 `after_event_sequence` keyset cursor 分页，固定 page size 128。
- 每行校验 `row.event_sequence > previous_sequence`（L612），否则抛 `CompactorResponseResolutionError`。
- full page 后若 `previous_sequence <= cursor`（L632），抛 error。
- short/empty page 完成 exhaustion（L629）。
- 无总页数 cap。

测试覆盖：
- `test_compactor_response_resolver_exhausts_multiple_full_pages_without_cap`：monkeypatch page size=1，3 个无关 terminal + 1 个目标 terminal。
- `test_compactor_response_resolver_returns_missing_only_after_exhaustion`：empty exhaustion 返回 None。
- `test_compactor_response_resolver_rejects_non_advancing_cursor`：`_NonAdvancingTerminalPageReader` 重复返回同 row。
- `test_compactor_response_resolver_fails_closed_for_binding_corruption`：7 个参数化 tamper（manifest_ref、manifest_digest、operation_id、attempt_number、engine_run_id、duplicate_terminal、malformed_identity）。

### 5. public typed resolver/analysis JSON/Markdown 是否安全白名单并可供正式 CI 使用

**PASS。**

- `ToolTraceCompactorResponseSummary`（contracts L442-558）只投影 `parent_host_run_id`、`disposition`、terminal binding、`effective_provider`、`effective_model`、`runner_request_identity`（Run/Attempt/iteration/runner_call_index/client_correlation_id）、`provider_request_id_availability`、`provider_request_id`。
- `_compactor_response_json()`（analysis L185-226）逐字段投影，`runner_request_identity` 只输出 7 个 safe fields。
- Markdown renderer（analysis L640-699）消费同一 report，不回读 raw payload。
- `parse_successful_runner_response_identity()` 的 `_require_exact_fields()` 拒绝未知字段（如 `authorization` header）。
- tests 验证 malformed identity（含 `authorization: Bearer must-not-leak`）被拒绝。

### 6. missing terminal limitation 是否只在完整 exhaustion 后形成

**PASS。** `tool_trace_analysis_input.py` L655-675：只有当 `signal.runner_call_kind == "compactor_proposal"` 且 `projection.compactor_response_identity is None` 时才附加 `_COMPACTOR_RESPONSE_TERMINAL_NOT_OBSERVED_REASON` limitation。而 `compactor_response_identity` 只在 resolver 完整 exhaustion 后返回 `None`。resolver 的 `CompactorResponseResolutionError`（corruption）会直接 raise，不会降级为 limitation。

### 7. 是否存在 config/邻近事件/时间顺序推断、下游补偿、compatibility shim、schema/public surface 过扩、secret/raw payload 泄漏

**PASS。**

- 无 config/时间推断：identity 从 canonical EventLog payload 严格解析。
- 无下游补偿：analysis input/rules 只消费 `RunnerCallResolvedProjection` typed projection。
- 无 compatibility shim：schema version 2 是 fresh breaking contract，`ToolTraceAnalysisReport.__post_init__()` L842 拒绝非 2。
- 无 schema 过扩：`__all__` 导出列表与 contracts `__all__` 对齐，不新增内部类型。
- 无 secret 泄漏：`_successful_response_identity_json()` 只投影 `effective_provider`、`effective_model`、`runner_request_identity`、`provider_request_id_availability`、`provider_request_id`。

### 8. tests 是否 owner-level 且 coverage 诚实

**PASS。**

- 172 focused tests passed。
- Branch coverage：context_events 83%、durable/tool_trace 82%、tool_trace_analysis 100%、tool_trace_analysis_contracts 84%、tool_trace_analysis_input 83%、tool_trace_analysis_rules 92%，总计 86%，所有模块 ≥80%。
- 测试覆盖 happy path（accepted/rejected/ordinary）、failure path（wrong ref/digest/operation/attempt/Engine run/duplicate/malformed）、boundary（empty/short/full page exhaustion、non-advancing cursor）和 regression（schema v2 rejection、secret whitelist）。

## Findings

### 001-未修复-低-CompactorResponseResolutionError 在 _resolved_compactor_response_from_row 中对无 manifest binding 的 rejected terminal 缺乏明确语义

- **入口/函数**: `_resolved_compactor_response_from_row()` (`dayu/host/durable/tool_trace.py:700-703`)
- **文件(行号)**: `dayu/host/durable/tool_trace.py:700-703`
- **输入场景**: `CONTEXT_COMPACTION_ATTEMPT_REJECTED` terminal 的 `proposal_manifest_ref` 为 None（proposal 未发出），但 resolver 的 `proposal_manifest_ref` 参数非 None
- **实际分支**: `operation_matches` 为 True（同 operation/attempt），`manifest_matches` 为 False（terminal 的 ref 为 None），`operation_matches != manifest_matches` 为 True → 抛 error
- **预期行为**: 与当前行为一致——若 operation/attempt 匹配但 terminal 不携带 manifest binding，视为 corruption
- **实际行为**: 抛 `CompactorResponseResolutionError("compactor terminal manifest/operation/attempt binding mismatch")`
- **直接证据**: L685-688: `if operation_matches != manifest_matches: raise CompactorResponseResolutionError(...)`
- **影响**: 当前无实际影响，因为 production 流程中 proposal manifest 总是在 attempt-rejected terminal 之前写入。仅在数据手动篡改时触发。
- **建议改法和验证点**: 无需修改。当前 fail-closed 行为正确。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-analysis rules _compactor_response_summaries 对缺少 parent Host Run id 的 compactor projection 抛 ValueError 而非跳过

- **入口/函数**: `_compactor_response_summaries()` (`dayu/host/tool_trace_analysis_rules.py:306-307`)
- **文件(行号)**: `dayu/host/tool_trace_analysis_rules.py:306-307`
- **输入场景**: `runner_call_projection.signal.run_id` 为 None（runner-call signal 缺少 run_id）
- **实际分支**: `parent_host_run_id is None` → `raise ValueError("compactor runner-call projection requires parent run id")`
- **预期行为**: 生产流程中 compactor_proposal signal 总有 parent run_id；此 guard 防止数据损坏时静默产出无效 summary
- **实际行为**: 抛 ValueError，阻止整个 analysis report 构建
- **直接证据**: L306-307: `if parent_host_run_id is None: raise ValueError(...)`
- **影响**: 当前无实际影响，runner-call signal 的 run_id 由 hot projection owner 保证。仅在数据损坏时触发。
- **建议改法和验证点**: 无需修改。fail-closed 比静默跳过更安全。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-compactor terminal scan page size 为模块私有常量，无法由调用方定制

- **入口/函数**: `_resolve_compactor_response_identity()` (`dayu/host/durable/tool_trace.py:597`)
- **文件(行号)**: `dayu/host/durable/tool_trace.py:60`
- **输入场景**: 无。当前 page size 固定为 128。
- **实际分支**: 使用 `_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE` 常量
- **预期行为**: 模块私有常量，不需要调用方定制
- **实际行为**: 固定 128，测试通过 monkeypatch 验证
- **直接证据**: L60: `_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE = 128`
- **影响**: 无实际影响。128 是合理的默认值，避免单次查询过大。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

1. **F12 compaction contract redesign 未覆盖**：S1 不涉及 F12 的 compact v3、policy_limit 分支移除、prompt 简化等。这些由 accepted plan 的 S2-S5 拥有。
2. **真实 provider conformance 证据未覆盖**：S1 的 deterministic owner tests 和 public-resolver integration tests 不等同于 formal CLI conformance 或 real-provider scenario evidence。五个 `interactive.g06.*` 场景仍由 Oracle controller 的 readiness gate 拥有。
3. **schema v2 迁移**：F11 是 fresh breaking contract，仓外自建 Tool Trace report consumer 需按 v2 显式升级。S1 不提供 v1 reader/adapter。

## Verdict

**PASS**

S1 F11 implementation 完整实现了 accepted plan 要求的 canonical compactor response identity 公开投影。canonical `SuccessfulRunnerResponseIdentity` 为唯一 response truth；三态 binding 严格；manifest/operation/attempt/Engine run exact 同源且 mismatch fail closed；EventLog terminal 分页完整 exhaustion；public typed resolver/analysis JSON/Markdown 安全白名单；missing terminal limitation 只在 exhaustion 后形成；无 config 推断、下游补偿、compatibility shim、schema 过扩或 secret 泄漏。tests 是 owner-level 且 coverage 诚实（86% aggregate, all ≥80%）。

三个低严重程度 finding 均为防御性 guard 的预期行为，不需要修复。
