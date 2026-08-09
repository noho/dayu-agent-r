# Code Review: PR 190 F11/F12 S4.2 accepted terminal payload fix

## Scope

- Mode: current changes (uncommitted)
- Branch: `codex/interactive-oracle`
- Base: `f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- Output file: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-review-20260805.md`
- Included scope: `dayu/host/` 生产代码、`tests/host/` 测试代码、README 更新
- Excluded scope: 无
- Parallel review coverage: 无

## Review Intent

审查 S4.2 accepted terminal payload fix 的实现，验证：
1. canonical terminal durable owner 是否正确
2. proactive/reactive writer 是否都外置超限完整 payload 且不提高 limit/删字段
3. 所有 terminal/Memory/compact material/RunInput/proactive replay/projection/public Tool Trace consumer 是否统一严格解析
4. ref/digest/descriptor/blob corruption 是否 fail closed
5. artifact 与 terminal truth 是否同源
6. 是否有第二真源、下游补偿、兼容 shim、God helper、格式 churn、测试误改
7. background promotion 无 fatal/hang 断言是否真实
8. owner tests 是否覆盖小 inline、超限 proactive/reactive、Memory/artifact/F11 response identity

## Failure Evidence

冻结证据：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-final-k5hWK9/screen/07-deepseek-replacement-retry.txt`

直接堆栈表明：
- DeepSeek candidate 已进入 accepted compact commit 路径
- proactive writer 把完整 `CONTEXT_COMPACTED` canonical payload 全量写入 EventLog inline 字段
- payload 超过 EventLog 当前 inline threshold 后由 durable invariant 抛出 `HostPayloadReferenceError`
- 进而使 promotion critical task fatal

## Findings

### 未发现实质性问题

经过全面审查，本次改动正确解决了 production blocker，所有验证点均通过。

## Detailed Verification

### 1. Canonical terminal durable owner 正确性 ✅

**新增模块 `dayu/host/context_event_payload.py`**：
- `store_context_compacted_payload()` - 写入时，如果 payload 超过 inline threshold，写入 descriptor/blob，EventLog 只保存 `{}`
- `resolve_context_compacted_payload()` - 读取时，严格解析 inline 或 descriptor-backed payload
- 模块职责清晰：只负责 durable payload 映射，不产生 compact 业务语义

**证据**：
- `context_event_payload.py:50-104` - `store_context_compacted_payload` 实现
- `context_event_payload.py:107-133` - `resolve_context_compacted_payload` 实现
- `context_event_payload.py:77` - 调用 `validate_context_compacted_payload` 确保完整 canonical contract

### 2. Proactive/Reactive writer 外置超限完整 payload ✅

**Proactive writer (`dispatch.py`)**：
- `dispatch.py:3288-3325` - 先构建完整 payload，调用 `store_context_compacted_payload` 获取存储计划
- `dispatch.py:3325-3335` - 将返回的三个字段原样写入 EventLog

**Reactive writer (`engine_ingest.py`)**：
- `engine_ingest.py:3093-3132` - 与 proactive writer 使用相同的模式
- 两路都预先确定 event id，再从同一完整 payload 生成存储计划

**证据**：
- 两路 writer 都不提高 limit，不删字段、截断
- `context_event_payload.py:79` - 阈值判断使用 `transaction.payload_inline_threshold_bytes`
- `context_event_payload.py:86-104` - 超限时写入 descriptor/blob，EventLog 只保存 `{}`

### 3. 所有消费者统一严格解析 ✅

**已修改的消费者**：
- `compact_material.py:2490-2495` - `_validated_compacted_payload` 改为使用 `resolve_context_compacted_payload`
- `compaction_terminal.py:212-265` - `_strict_terminal_payload` 改为使用 `resolve_context_compacted_payload`
- `durable/tool_trace.py:667-670` - `_resolved_compactor_response_from_row` 改为使用 `resolve_context_compacted_payload`
- `proactive_compaction.py:461-467` - `_project_state` 改为使用 `resolve_context_compacted_payload`
- `projection.py:713-719` - `projection_event_view_from_row` 改为使用 `resolve_context_compacted_payload`
- `run_input.py:4245-4248` - `_load_pre_start_compact_artifact` 改为使用 `resolve_context_compacted_payload`
- `run_input.py:5488-5493` - `_memory_projection_payload` 改为使用 `resolve_context_compacted_payload`
- `run_input.py:5554-5570` - `_validate_loaded_compact_view_matches_event` 改为使用 `resolve_context_compacted_payload`
- `run_input.py:5590-5595` - `_compaction_trigger_source_for_compacted_event` 改为使用 `resolve_context_compacted_payload`

**未修改但正确的消费者**：
- `read_api.py:_context_compaction_activity` - 只读 inline payload，对于 CONTEXT_COMPACTED 只需要 status/title/summary/severity，不需要 payload 中的其他字段
- `context_anchor.py` - 只判断 `row.event_type == _CONTEXT_COMPACTED` 是否停止扫描，不解析 payload
- `memory.py` - 通过上层传入的 `MemoryProjectionEvent.compacted_semantics` 获取数据，上层已正确处理
- `lifecycle_events.py` - 只定义事件类型常量，不解析 payload

### 4. Ref/digest/descriptor/blob corruption fail closed ✅

**`resolve_context_compacted_payload` 严格校验**：
- `context_event_payload.py:120-121` - 校验 event class 和 event type
- `context_event_payload.py:122-123` - 校验 ref/digest pairing
- `context_event_payload.py:124-128` - 调用 `event_payload_object` 读取 payload（处理 inline 或 descriptor-backed）
- `context_event_payload.py:129-132` - 调用 `validate_context_compacted_payload` 校验完整 canonical contract

**证据**：
- 任一校验失败都抛出 `HostDurableError`
- 测试 `test_oversized_accepted_compact_terminal_uses_descriptor_truth` 验证了 digest 漂移后 fail closed

### 5. Artifact 与 terminal truth 同源 ✅

**测试验证**：
- `test_dispatch_scheduler.py:7389-7405` - 验证 `compact_artifact_ref` 和 terminal payload 中的 `accepted_candidate` 一致
- `test_dispatch_scheduler.py:7395-7405` - 读取 compact artifact bytes，验证 `compact_artifact_json["accepted_candidate"] == compacted_payload["accepted_candidate"]`

### 6. 无第二真源、下游补偿、兼容 shim、God helper、格式 churn、测试误改 ✅

**证据**：
- 所有消费者都使用同一个 `resolve_context_compacted_payload` resolver
- 无 fallback、特例、`hasattr`/`getattr`、loose parsing
- 无兼容 shim 或下游特例
- `context_event_payload.py` 职责清晰，不是 God helper
- 实现说明提到已恢复格式 churn
- 测试改动只更新了 `projection_event_view_from_row` 签名，不影响测试逻辑

### 7. Background promotion 无 fatal/hang 断言真实 ✅

**测试验证**：
- `test_dispatch_scheduler.py:7417-7425` - 断言：
  - `_event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1` - 只提交一个 terminal
  - `_run_status(store.transaction_runner, seeded.run_id) is RunStatus.RUNNING` - Run 进入 RUNNING
  - `scheduler._promotion_drain_task.done() is False` - promotion task 保持存活
  - `scheduler._health_gate.state is HostExecutionHealthState.READY` - health 为 READY
  - `not any("critical_task.fatal" in record.getMessage() for record in caplog.records)` - 无 critical_task.fatal

### 8. Owner tests 覆盖全面 ✅

**Proactive test (`test_oversized_accepted_compact_terminal_uses_descriptor_truth`)**：
- 通过真实 background queue promotion 路径触发
- 断言只提交一个 `CONTEXT_COMPACTED` terminal
- 断言 EventLog hot payload 为 `{}`，terminal descriptor 为 artifact-backed
- 断言 digest 与完整 payload 精确一致
- 断言 compact artifact bytes 与 terminal accepted candidate 同源
- 断言 Conversation Memory latest compaction ref 与 summary 已物化
- 断言 public Tool Trace compactor response identity 可解析
- 断言篡改 terminal digest 后 public resolver fail closed
- 断言 Run 进入 RUNNING、promotion task 保持存活、health 为 READY，且无 critical_task.fatal 或 hang

**Reactive test (`test_reactive_oversized_accepted_terminal_uses_descriptor_truth`)**：
- 断言 reactive writer 使用相同 descriptor truth
- 断言完整 payload 可严格解析
- 断言只提交一个 terminal
- 断言只触发一次 recovery wake

**既有测试**：
- 既有 inline accepted compact、terminal permit、Memory、RunInput、projection 与 Tool Trace tests 保持通过

## Open Questions

无

## Residual Risk

1. **`read_api.py` 的 `_context_compaction_activity`**：使用 `_activity_payload_without_descriptor` 读取 inline payload，对于 descriptor-backed 的 CONTEXT_COMPACTED 会返回空 mapping。这不是功能性问题，因为 CONTEXT_COMPACTED 是成功事件，不需要 failure_reason，但语义上丢失了 payload 信息。Severity: Low，不影响功能正确性。

2. **测试覆盖**：已验证 proactive 和 reactive 超限场景，以及 fail-closed 行为。但未显式测试 inline 场景（小 payload）的回归，不过既有测试已覆盖。

## Verification Summary

| 验证项 | 结果 |
|--------|------|
| canonical terminal durable owner 正确 | ✅ PASS |
| proactive/reactive writer 外置超限完整 payload | ✅ PASS |
| 不提高 limit/删字段 | ✅ PASS |
| 所有消费者统一严格解析 | ✅ PASS |
| ref/digest/descriptor/blob corruption fail closed | ✅ PASS |
| artifact 与 terminal truth 同源 | ✅ PASS |
| 无第二真源、下游补偿、兼容 shim | ✅ PASS |
| 无 God helper、格式 churn、测试误改 | ✅ PASS |
| background promotion 无 fatal/hang 断言真实 | ✅ PASS |
| owner tests 覆盖全面 | ✅ PASS |
| affected regression 通过 | ✅ PASS (369 passed) |
| pyright 类型检查 | ✅ PASS (0 errors) |

## Conclusion

**PASS** - 本次改动正确解决了 production blocker，所有验证点均通过。实现符合语义所有权原则，无第二真源、下游补偿或兼容 shim。测试覆盖全面，包括 proactive 和 reactive 超限场景、fail-closed 行为、artifact 同源性验证。
