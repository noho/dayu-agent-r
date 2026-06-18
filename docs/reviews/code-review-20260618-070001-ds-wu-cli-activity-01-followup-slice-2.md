# Code Review

## Scope

- Mode: current changes
- Branch: wu-cli-activity-01
- Base: main (workspace uncommitted changes only)
- Output file: docs/reviews/code-review-20260618-070001-ds-wu-cli-activity-01-followup-slice-2.md
- Included scope:
  - `dayu/host/engine_ingest.py` — 新增 `_is_transient_delta_event`、`_accepted_no_event_result`，在 `_ingest_validated` 头部增加 transient delta 分流，`_DELTA_ENGINE_EVENT_TYPES` 增加 `TOOL_CALL_DELTA`
  - `tests/host/test_engine_ingest_mapping.py` — 新增 delta 三类全覆盖测试、更新旧 stale 测试改用 CONTENT_COMPLETED、拆分 batch 测试、重命名匹配类型测试
  - `dayu/host/README.md` — PREVIEW event class 描述更新
- Excluded scope:
  - 已提交的 Slice 1 commits（plan 阶段、slice-1 实现）
  - 未变更的其余 `dayu/host/` 文件
  - `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md`（Codex 产物，仅作为参考）
- Parallel review coverage: 无

## Design Truth Reference

`docs/host/design.md` 规定：content_delta / reasoning_delta / tool_call_delta 默认不写主 EventLog，Host 可接受并用于即时展示，但 durable replay / event stream backfill / memory / audit / RunResult 不承诺 token-level delta replay。本次改动实现了该设计。

## Findings

### 1-未修复-低-`_preview_payload` 内 delta 分支成为不可达死代码

- **入口/函数**: `_preview_payload`（模块级函数）
- **文件(行号)**: `dayu/host/engine_ingest.py:4751-4767`
- **输入场景**: 任何 CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA event
- **实际分支**: 这三类 delta 在 `_ingest_validated:928` 被 `_is_transient_delta_event` 先命中，执行 `return _accepted_no_event_result()`，永远不会到达 `_is_preview_event` 分支（`:1010`），进而永远不会进入 `_append_preview_event` → `_preview_payload`。
- **预期行为**: 死代码应清理或显式标记为不可达，避免后续维护者误以为这些分支仍被使用。
- **实际行为**: `_preview_payload:4751-4767` 内 `isinstance(data, ContentDeltaData)`、`isinstance(data, ReasoningDeltaData)`、`isinstance(data, ToolCallDeltaData)` 三个分支在通过 `_append_preview_event` 调用的路径上不可达。`_is_preview_event:4679-4691` 内的对应三个分类分支同样在 `_ingest_validated` 路径上不可达。
- **直接证据**:
  - `_ingest_validated:928-929`：`if _is_transient_delta_event(event): return _accepted_no_event_result()` — 提前返回
  - `_ingest_validated:1010-1012`：`if _is_preview_event(event): row = self._append_preview_event(...)` — 被短路
  - `_append_preview_event:2423` 调用 `_preview_payload` — 唯一调用点
  - Grep 确认 `_is_preview_event` 无其他调用点（仅 `:1010` 和定义 `:4669`），`_preview_payload` 无其他调用点（仅 `:2423` 和定义 `:4729`）
- **影响**: 无运行时影响。对后续维护者造成认知负担——可能误以为修改 `_preview_payload` 的 delta 分支会影响行为，或往 delta 分支里加新逻辑而不知其不可达。违反 CLAUDE.md"禁止兼容性代码"精神（保留不再执行的语义分支）。
- **建议改法和验证点**:
  方案 A（推荐）：在 `_preview_payload` 三个 delta 分支前加注释 `# unreachable: transient deltas short-circuit in _ingest_validated`。
  方案 B：删除 `_preview_payload` 和 `_is_preview_event` 中的 delta 分支并增加 `assert not isinstance(data, (ContentDeltaData, ReasoningDeltaData, ToolCallDeltaData))` 防御。
  选择方案 B 需同步评估 `_is_preview_event` 是否将来会被其他调用方期望返回 delta 类型的 True——当前无此需求，但函数签名语义上 delta 确实是"preview-like"。建议选择方案 A。
- **修复风险（低）**: 方案 A 为注释，零风险；方案 B 需验证无其他模块通过 import 依赖这些分支的行为。
- **严重程度（低）**: 无行为错误，仅维护性瑕疵。

### 2-未修复-低-测试命名滞后：`test_preview_event_rejects_missing_or_wrong_data` 使用 CONTENT_DELTA 但已不再是 preview

- **入口/函数**: `test_preview_event_rejects_missing_or_wrong_data`
- **文件(行号)**: `tests/host/test_engine_ingest_mapping.py:2357`
- **输入场景**: CONTENT_DELTA + None data / CONTENT_DELTA + IterationStartedData
- **实际分支**: 两种错误 data 均不匹配 `_is_transient_delta_event` 也不匹配 `_is_preview_event`，最终落 `_append_rejected_diagnostic`
- **预期行为**: 测试命名应反映当前架构：CONTENT_DELTA 现在是 transient delta 而非 preview event。测试逻辑本身正确，无需修改。
- **实际行为**: 测试名仍称 "preview_event"，但实际测试的是"transient delta event with wrong data is rejected"。
- **直接证据**: 测试行 `:2370` 使用 `event_type=EngineEventType.CONTENT_DELTA`，但 CONTENT_DELTA 已从 preview 路径重分类至 transient delta 路径。
- **影响**: 无运行时影响。后续维护者可能误解该测试覆盖的是 preview 拒绝逻辑，而非 transient delta 拒绝逻辑。
- **建议改法和验证点**: 重命名为 `test_transient_delta_event_rejects_missing_or_wrong_data`，或更精确的 `test_delta_event_with_type_data_mismatch_is_rejected`。docstring 同步更新。
- **修复风险（低）**: 仅改名，零风险。
- **严重程度（低）**: 命名问题。

## Open Questions

1. `_is_transient_delta_event` 和 `_is_preview_event` 对 type/data 同时校验（`event.type == X and isinstance(event.data, Y)`），但如果两者之一正确而另一个错误（如 CONTENT_DELTA + ReasoningDeltaData），会穿透两个 guard 落到 `_append_rejected_diagnostic` 且 `stop_worker_stream=True`。这是否是理想行为？——当前与变更前行为一致，非本次引入；但值得后续确认：单个 malformed delta 导致整条 worker stream 停止是否过激。

2. 仅有 CONTENT_DELTA 的 type/data mismatch 测试（`test_preview_event_rejects_missing_or_wrong_data`），REASONING_DELTA 和 TOOL_CALL_DELTA 的 mismatch 路径无测试覆盖。本次变更新增了 TOOL_CALL_DELTA 进入 transient delta 路径，但 mismatch 拒绝逻辑对所有三类 delta 路径一致，且由共同 fallthrough 实现，不太可能单类漂移。

## Residual Risk

- **无 PREVIEW path regression 测试针对 CONTENT_COMPLETED**：`test_old_steered_attempt_event_is_rejected_and_current_attempt_accepts` 改用 CONTENT_COMPLETED，对 CONTENT_COMPLETED 的 stale/late governance 有隐含覆盖，但尚未有针对 CONTENT_COMPLETED 单独验证 PREVIEW payload 字段（`has_content`、`has_reasoning_content`、`finish_reason`）的专项测试。当前测试仅断言 `has_content is True`。
- **delta 事件流中连续 delta 无 EventLog row 的场景**：如果 worker stream 产生大量连续 delta 后异常断开，`last_accepted_event_id` 始终停留在最后一个非 delta 事件，`_safe_close_worker_lost` 会携带该旧 event_id 进入 recovery。dispatch 恢复逻辑自身不需要 `last_accepted_event_id` 精确到 delta 粒度（因为 delta 不持久化），风险低。
- **`_accepted_no_event_result` 的 `stop_worker_stream` 依赖 dataclass 默认值 `False`**：显式构造中未传递此字段，依赖 `EngineIngestResult.stop_worker_stream: bool = False` 默认值。当前行为正确，但若将来 `EngineIngestResult` 默认值改为 `True`，会产生隐性语义变更。建议 `_accepted_no_event_result` 显式传递 `stop_worker_stream=False` 以减少对默认值的隐性依赖（与 `_single_event_result` 和 `_event_rows_result` 风格保持一致——后两者也未显式传递，属于现有模式）。

## Verification Summary

### 用户指定的五项重点检查

| 检查项 | 结果 |
|--------|------|
| `_ingest_validated` 分流顺序保持 stale/late/identity governance | **通过**。`_validate_durable_context`（`:751`）→ `_duplicate_terminal_result`（`:758`）→ `_late_rejection_reason`（`:761`）均在 `_ingest_validated`（`:768`）之前执行。`_is_transient_delta_event` 是 `_ingest_validated` 内第一个分支（`:928`），不绕过前置治理。 |
| 错误 data 仍 rejected | **通过**。type/data mismatch 的 delta 不匹配 `_is_transient_delta_event`（因为 `isinstance` 检查），也不匹配 `_is_preview_event`，落 `_append_rejected_diagnostic`。测试 `test_preview_event_rejects_missing_or_wrong_data` 覆盖此路径。 |
| no-row accepted result 对 dispatch/watchers 安全 | **通过**。`_accepted_no_event_result()` 返回 `ACCEPTED`、`events=()`、`terminal_closeout=False`、`stop_worker_stream=False`、`promotion_triggered=False`。dispatch loop `:3540` 的 `if result.events:` 正确处理空 events；`:3542` 的 terminal/stop 条件不触发。 |
| 测试覆盖三类 delta 和非 delta preview regression | **通过**。新增 `test_delta_events_are_accepted_without_event_log_rows` 覆盖 CONTENT_DELTA、REASONING_DELTA、TOOL_CALL_DELTA。保留 `test_tool_call_requested_and_result_accepted_are_preview`、`test_tool_batch_events_stay_preview_not_canonical`、`test_iteration_completed_preview_includes_client_correlation_id` 等非 delta preview 测试，未被改动破坏。 |
| README 符合 README 更新约束 | **通过**。改动范围属于 `dayu/host/README.md` 的 PREVIEW event class 描述更新，与代码变更一致，未超出职责边界。 |
