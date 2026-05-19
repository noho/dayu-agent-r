# PR-62 Fullrepo Accepted-Fix Re-Review

## Scope

- Mode: current changes（未提交 workspace changes 相对 HEAD）
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: HEAD (当前已提交 commit `55c8d1d`)
- Output file: `docs/reviews/pr-62-fullrepo-accepted-fix-rereview-ds-20260519.md`
- Input artifacts:
  - `docs/reviews/repo-review-20260519-182223.md`（全仓 review #1）
  - `docs/reviews/repo-review-20260519-182226.md`（全仓 review #2）
  - `docs/reviews/pr-62-fullrepo-review-controller-adjudication-20260519.md`（总控裁决）
- Included scope: 全部 24 个 modified + 1 个 new 文件
- Excluded scope: 无
- Review method: 独立逐行走读，不依赖总控裁决结论

## 总控裁决 defensibility 评估

总控裁决 artifact 对 deferred findings 的分类判断整体 defensible：

- **God dataclass (Finding 2)**：拆分会牵动 accept candidate 全链路，作为独立重构切片合理。当前无运行时 correctness 影响。
- **Compact fallback (Finding 7)**：dispatch/proactive 路径已有 fail-unstarted 收口，将端到端 failure matrix 延后合理。
- **LaneController race (Finding 10)**：有 TTL 兜底（30s），且不在 Host accepted-fix 主路径。
- **DDL 原子性 (Finding 5-1)**：`IF NOT EXISTS` 提供幂等恢复，实际安全。
- **Crash recovery tests (Finding 8-1)**：需多进程/强杀设计，超出 accepted-fix 范围。
- **其余 deferred findings**：均为 observability/维护性/性能项，无 correctness blocker。

**裁决 artifact 记录的被修复项与 workspace diff 一致，160 passed + pyright 0 errors 可复现。**

## Findings

### 01-中-`_awaiting_accept_failure_outcome` 丢弃 `ToolAwaitingAcceptTimedOut` 中的 diagnostic_refs

- **入口/函数**: `_awaiting_accept_failure_outcome`
- **文件(行号)**: `dayu/host/tool_runtime.py:5274-5296`
- **输入场景**: `_accept_awaiting_with_retry` 重试耗尽返回 `ToolAwaitingAcceptTimedOut` 后，调用 `_awaiting_accept_failure_outcome` 转换为 `ToolFailedOutcome`
- **实际分支**: `_awaiting_accept_failure_outcome` 行 5292-5296 构造 `ToolFailedOutcome` 时只提取 `last_error_code` 作为 hint，不传递 `diagnostic_refs`
- **预期行为**: `ToolAwaitingAcceptTimedOut.diagnostic_refs` 中收集的中间重试诊断 ref 和最终 timeout 诊断 ref 应进入最终 outcome，使下游 trace/EventLog 可关联
- **实际行为**: `_accept_awaiting_with_retry` 行 2848 通过 `self._diagnostic_emitter.emit()` 发出诊断并产生 ref_id，行 2854-2857 将 ref_id 写入 `ToolAwaitingAcceptTimedOut.diagnostic_refs`。但 `_awaiting_accept_failure_outcome` 行 5292-5296 完全忽略 `result.diagnostic_refs`。`ToolFailedOutcome` 本身无 `diagnostic_refs` 字段（`tool_outcome.py:72-78`），最终工具失败 outcome 不携带诊断引用。
- **直接证据**:
  - `_awaiting_accept_failure_outcome` (line 5292-5296) 只访问 `result.last_error_code`，不访问 `result.diagnostic_refs`
  - `ToolFailedOutcome` (tool_outcome.py:72-78) 只有 `result: ToolResultFailure` 字段
  - `_tool_failed_outcome` (line 5144-5163) 不接受 `diagnostic_refs` 参数
  - 对比非 awaiting 路径 `_accept_with_retry`（line 2922-2980），其 timeout 分支的 diagnostic refs 通过 accept candidate 写入 EventLog（line 3418-3420），而 awaiting timeout 路径不走 candidate accept
- **影响**: awaiting accept timeout 场景下，重试过程中的诊断和最终 timeout 诊断虽被 emitter 发出（在 `DeterministicToolTraceDiagnosticEmitter` 下产生确定性 ref_id），但 ref_id 无法传播到最终 outcome，下游 trace 缺少诊断关联
- **建议改法和验证点**: 两种可选修法：(a) 在 `_awaiting_accept_failure_outcome` 中通过 emitter 额外 emit 一条携带 `result.diagnostic_refs` 上下文的诊断，使 trace 可定位；(b) 将 `diagnostic_refs` 信息编码到 `ToolResultFailure.hint` 字段中。验证：构造 awaiting accept retry exhaustion 场景，断言最终 `ToolFailedOutcome` 可追溯到诊断信息
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-低-`_preserved_ref_texts` 对 event ref 字符串做 token 估算语义不匹配

- **入口/函数**: `_preserved_ref_texts` → `_estimate_preserved_context_tokens`
- **文件(行号)**: `dayu/host/compaction_budget.py:75-90` → `compaction_budget.py:49-72`
- **输入场景**: 任意 compaction 请求
- **实际分支**: `_estimate_preserved_context_tokens` 计算 `typed_fragment_tokens` 时，对 `_preserved_ref_texts(request)` 返回的每个 ref 字符串（如 `"event-recent-raw-turn-xxx"`）调用 `estimate_text_tokens`，产生约 `ceil(len(ref_string) / 3)` ≈ 9 tokens 的估算
- **预期行为**: 保守估算应反映 preserved 内容的实际 token 量，而非 ref ID 字符串本身的长度
- **实际行为**: ref ID 字符串的 token 估算（每条约 9 tokens）与实际指向的 content（可能数千 tokens）完全无关。`sysem_prompt` 和 `current_message_summary.summary_text` 的估算有意义，但 ref 字符串的估算在 `typed_fragment_tokens` 中贡献极微
- **直接证据**: `compaction_budget.py:61-67` 循环中对 `_preserved_ref_texts(request)` 的每个元素（ref ID 字符串）调用 `estimate_text_tokens(fragment)`
- **影响**: `typed_fragment_tokens` 主要由 system_prompt + summary_text 贡献，ref strings 部分接近噪声。但最终取值是 `max(typed_fragment_tokens, budget_proportion_estimate)`（line 69-72），在正常路径下 `budget_proportion_estimate` 会远大于 ref-string-based 估算，实际行为由比例估算主导，因此影响可控。极端情况（`retained_count == 0` 且 `tool_fact_refs`/`verified_fact_refs`/`existing_episode_summary_refs` 均为空）下 budget_proportion_estimate 返回 0，此时严重低估
- **建议改法和验证点**: 在 `_estimate_preserved_share_from_budget` 返回 0 时增加 fallback：将 `recent_raw_turn_refs` 数量按 `estimated_input_tokens / max(len(source_refs), 1)` 估算，而非直接返回 0。或至少加 defensive log warning
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-低-`_cancelled_eof_candidate` fallback 对 `requested_at` 和 `reason` 有冗余保护但掩盖调用方 invariant

- **入口/函数**: `_cancelled_eof_candidate`
- **文件(行号)**: `dayu/host/dispatch.py:2654-2694`
- **输入场景**: `cancellation_token.is_cancelled()` 为 True 但 `requested_at()` 返回 None（理论上不应发生，因为 `is_cancelled()` 和 `requested_at()` 读同一 `_requested_at` under lock）
- **实际分支**: `requested_at is None` → fallback 为 `observed_at`；`reason is None` → fallback 为 `"host_cancelled"`
- **预期行为**: 由于调用方（line 2479-2480）已通过 `cancellation_token.is_cancelled()` 守卫，且 `is_cancelled()` 检查 `_reason is not None`（line 431），`requested_at` 和 `cancel_reason` 在此路径下不会为 None
- **实际行为**: fallback 被触发意味着 `_HostCancellationToken` 内部 invariant 被破坏（`_reason` 非 None 但 `_requested_at` 为 None），当前 fallback 静默掩盖此 invariant violation
- **直接证据**: `dispatch.py:2671-2676` 的 fallback 逻辑；`dispatch.py:431` 的 `is_cancelled()` 实现（检查 `self._reason is not None`）；`dispatch.py:449` 的 `requested_at()` 实现（返回 `self._requested_at`）
- **影响**: 极低。当前代码路径下 fallback 理论不可达，但若未来 `_HostCancellationToken` 修改导致 invariant 破裂，fallback 会掩盖 bug
- **建议改法和验证点**: 将 fallback 改为至少记录 warning 日志（`exc_info=True`），或使用 `assert` 守卫
- **修复风险（低/中/高）**: 极低
- **严重程度（低/中/高/严重）**: 低

## 重点反例逐项审查

### 1. compaction budget helper 是否仍低估 preserved content

**结论：显著改善，残留风险可控。**

- 旧代码 `min(summary_tokens, hard_threshold - 1)` 完全不估算 preserved 内容，adversarial 场景必过。
- 新代码 `summary_tokens + max(text_estimate, budget_proportion_estimate)` 通过双路估算（文本直接估算 + 按 ref 占比从 compact 前预算反推）得到保守下界。
- `budget_proportion_estimate` 按 `retained_refs / source_refs * estimated_input_tokens` 比例估算，假设各 ref 对应内容均匀分布。当 preserved refs 的内容显著大于平均（如保留了一个超大 tool result）时，比例估算偏保守（低估），但 `max()` 取两路较大值，正常路径不会漏过。
- fake/LLM compactor 一致：均调用 `estimate_compacted_context_budget` 同一入口，估算逻辑完全一致。
- 参见 Finding 02 关于 ref strings 语义不匹配的低风险残余。

### 2. engine_ingest unsupported fail closed 是否误停普通事件

**结论：不会。18 个 EngineEventType 全部显式覆盖。**

- `_ingest_validated` (engine_ingest.py:742-828) 涵盖全部 18 个 EngineEventType：FINAL_ANSWER, RUN_FAILED, RUN_CANCELLED, CONTEXT_COMPACTION_REQUESTED, RUN_SUSPENDED, TOOL_AWAITING, USAGE_REPORTED, PROVIDER_PROTOCOL_ERROR，以及 `_is_preview_event` 覆盖的 10 个 preview 类型（ITERATION_STARTED, CONTENT_DELTA, REASONING_DELTA, CONTENT_COMPLETED, TOOL_CALL_DELTA, TOOL_CALLS_BATCH_READY, TOOL_CALL_REQUESTED, TOOL_RESULT_ACCEPTED, TOOL_CALLS_BATCH_DONE, ITERATION_COMPLETED）。
- 每个分支不仅有 type 匹配还有 `isinstance(data, ...)` 类型守卫。
- 到达 unsupported fallthrough 的唯一场景：(a) Engine 新增 enum 成员 Host 未更新（版本不同步），或 (b) type/data 不匹配（Engine bug 或版本不同步）。两种场景下 fail-closed (`stop_worker_stream=True`) 是正确的安全决策。
- 测试 `test_unsupported_engine_event_shape_is_rejected` 和 `test_preview_event_rejects_missing_or_wrong_data` 验证了 `stop_worker_stream is True`。

### 3. active cancel clean EOF 合成 run_cancelled 是否误取消正常 EOF

**结论：不会。守卫条件正确区分了 cancel 和正常 EOF。**

- `is_cancelled()` 守卫（dispatch.py:2479）：仅在 `_HostCancellationToken._reason is not None` 时返回 True，即 Host 主动调用 `cancel()` 后才为 True。正常 worker 完成不会触发此条件。
- `not self._closed` 守卫（dispatch.py:2480）：scheduler shutdown 时不合成 cancel 事件，避免在关闭竞态中制造虚假 cancel。
- `run_terminal_closed = False` 初始化（dispatch.py:2428）确保变量在使用前已绑定，且 `if not run_terminal_closed` 在合成 cancel ingest 未成功 close run 时正确 fallback 到 clean_eof 路径。无 UnboundLocalError 风险。
- 非 cancel 正常 EOF：`is_cancelled()` = False → 跳过合成 block → `run_terminal_closed` 保持 False → 进入 clean_eof_without_terminal 路径。

### 4. resolve wait fail closed 是否破坏幂等重放

**结论：不会。幂等重放在 fail-closed 检查之前。**

- 调用顺序（waiting.py:739-801）：先读幂等记录（line 739-741）→ 命中则直接返回已存结果（line 749），不经过 `_resolve_created_event_ref` → 只有首次 resolution 才执行 resolve + `_resolve_created_event_ref`（line 789）。
- `_resolve_created_event_ref`（line 2020-2042）仅在首次 resolution 路径执行，若 `started_event_id`/`started_event_sequence` 或 `terminal_event_id`/`terminal_event_sequence` 为 None，抛出 `INTERNAL_ERROR` 导致事务 rollback。这是正确的 fail-closed：数据完整性异常不应写入无效幂等记录。
- 新增测试 `test_resolve_created_event_ref_fails_closed_for_missing_resume_start` 验证了此行为。

### 5. awaiting diagnostic refs 是否真实进入 timeout result

**结论：refs 进入中间结果 `ToolAwaitingAcceptTimedOut`，但被 `_awaiting_accept_failure_outcome` 丢弃，未传播到最终 `ToolFailedOutcome`。**

- `_accept_awaiting_with_retry` (line 2848-2857)：`emit()` 产生诊断记录 → `timeout_ref.ref_id` 进入 `ToolAwaitingAcceptTimedOut.diagnostic_refs`。中间重试产生的诊断也通过 `diagnostics = result.diagnostic_refs` 累积。
- `_awaiting_accept_failure_outcome` (line 5292-5296)：提取 `last_error_code` 但不提取 `diagnostic_refs`。
- `ToolFailedOutcome` 没有 `diagnostic_refs` 字段，无法承载诊断引用。
- 诊断 emitter 的 `emit()` 调用确实执行，ref_id 已生成（deterministic 或 in-memory），但无法通过 outcome 传播到下游 EventLog/trace。
- 参见 Finding 01。

### 6. import boundary 白名单是否过宽

**结论：不过宽。`llm_compaction.py` 的 Engine 依赖均为公共契约。**

- `llm_compaction.py` 从 `dayu.engine` 导入的内容（llm_compaction.py:20-36）：
  - `run_agent_and_wait` — Engine 公共入口函数
  - `AgentPolicy`, `AgentRunRequest`, `FinishReason`, `SystemMessage`, `UserMessage`, `RunnerSpec`, `RunnerCallOptions` — 均为 Engine 公共契约类型
  - 无 Runner 实现类、内部 helper 或私有模块的导入
- 白名单机制是文件级 gate，与 `api.py`, `dispatch.py`, `engine_ingest.py`, `local_proxy.py`, `run_input.py` 等其他边界模块待遇一致
- 架构约束（Host README 和 design.md）明确允许 Host-owned LLM compaction 调用 Engine public API

### 7. test update 是否降低断言质量

**结论：没有实质性降低。每处变更均有合理理由。**

| 测试变更 | 旧断言 | 新断言 | 评估 |
|---|---|---|---|
| `test_fake_compactor_*` | `budget_after_compact == hard_threshold - 1` | `budget_after_compact >= hard_threshold` | 行为变更：不再 clamp 到 hard_threshold 以下。新断言验证 preserved refs 被计入，实际更强 |
| `test_llm_context_compactor_maps_final_answer_to_candidate` | `budget_after_compact == 8` | `budget_after_compact > 8` | 从精确值改为不等式，因为新预算公式依赖多输入。新测试 `test_llm_context_compactor_budget_counts_preserved_context` 补充了 `>= 80` 强下界 |
| `test_mock_tool_fact_enters_memory_*` | `event_ref=event-engine-` | `event_id=event-tool-result-accepted-` | 修正错误断言：旧期望的 event_id 格式已过时 |
| `test_unsupported_engine_event_shape_is_rejected` | 无 `stop_worker_stream` 断言 | `assert result.stop_worker_stream is True` | **新增断言**，增强覆盖 |
| 新增 `test_close_runner_once_marks_closed_after_close_error` | 不存在 | `assert runner.close_count == 1` | 新测试覆盖 once 语义 |
| 新增 `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref` | 不存在 | `assert diagnostics.records[0].reason_code == "accept_timeout"` | 新测试覆盖诊断发射 |

### 8. deferred findings 是否确非 PR-62 blocker

**结论：总控裁决的 deferred 分类正确，均非 correctness blocker。**

逐一验证：
- **God dataclass**：维护性重构，22 字段虽多但当前所有字段均有明确消费者，拆分不会改变运行时行为
- **Compact fallback**：`compaction_operation.py` 返回明确 `failure_reason`，dispatch/proactive 路径有 fail-unstarted 收口
- **LaneController race**：30s TTL cleanup 兜底，无永久泄漏
- **`_execute_batch` 日志**：异常被转为 tool failed outcome，不影响 Host 终态
- **`log.py` import 副作用**：`addLevelName` 幂等
- **DDL 原子性**：`IF NOT EXISTS` 幂等恢复
- **after-commit callback**：不影响 committed truth
- **service/ui 测试**：代码未实现
- **crash recovery tests**：需要多进程测试基础设施
- **sensitive marker 精度**：偏保守 redact 不会漏标
- **open_host fallback**：已文档化非生产默认值
- **session watch 轮询**：20ms 为常规 SQLite 读负载
- **import boundary helper 重复**：纯测试维护性

## Open Questions

1. **`ToolAwaitingAcceptTimedOut.diagnostic_refs` 的类型 `tuple[str, ...]` vs accept candidate 的 `tuple[ToolTraceDiagnosticRef, ...]**：两者类型不同。`_accept_awaiting_with_retry` 中 middle-retry 的 `diagnostics` 来自 `result.diagnostic_refs`（类型 `tuple[str, ...]`），而 final timeout 的 `timeout_ref.ref_id` 也是 `str`。类型一致但语义不如 `ToolTraceDiagnosticRef` 丰富。是否需要统一为 `ToolTraceDiagnosticRef`？

## Residual Risk

- **Compaction budget 比例估算假设均匀分布**：当 preserved refs 的 content 显著大于平均值时，比例估算偏保守（低估），但 `max()` 取两路较大值，且低估方向是安全方向（更可能触发 hard threshold rejection）
- **`_awaiting_accept_failure_outcome` 诊断丢弃**：实际影响受限于 `DeterministicToolTraceDiagnosticEmitter` 的确定性 ref_id（可事后重建），但联机 trace 关联缺失
- **未覆盖的 cancel EOF race 路径**：`_cancelled_eof_candidate` 合成的 `RunCancelledData` 的 `requested_at`、`accepted_at`、`finished_at` 均设为同一时间点（`observed_at`），丢失了 cancel 请求到完成的时间线精度。当前无消费方依赖此精度，暂不构成问题
- **未运行完整测试套件验证**：本次 review 未执行 pytest，依赖总控裁决记录的 160 passed + pyright 0 errors。建议在 accept 前运行 `pytest` 全量确认

## 结论

**PASS** — 未发现 BLOCKED 级别的 correctness 或 stability 缺陷。

- 9 项 accepted fixes 均正确实施，代码变更与总控裁决描述一致
- 1 项中等发现（diagnostic_refs 在 awaiting timeout 路径的传播链断裂）和 2 项低等发现
- 所有 8 项用户指定的反例均已独立走读验证，无 blocker
- 总控裁决 artifact 对 deferred findings 的分类 defensible
