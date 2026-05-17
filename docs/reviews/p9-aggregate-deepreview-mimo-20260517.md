# P9 Aggregate Deep Review — AgentMiMo

**Date**: 2026-05-17
**Reviewer**: AgentMiMo (mimo-v2.5-pro)
**Branch**: `feat/host-p9-conversation-memory`
**Base**: `f27ce8a`
**Head**: `1b19b35`
**Scope**: Phase 9 Conversation Memory / Session Memory Projection — plan + implementation + docs

## Verdict

**PASS — no blocking findings.**

P9 正确实施了 session-level memory projection 作为财报分析工作台状态投影，不是聊天记录压缩器。Memory 四类视图守住边界，verified facts 只来自工具事实并保留完整 provenance，RunInputBuilder 注入顺序与 budget 策略符合裁决，projection lag / repair / catch-up 不触发 Run recovery，Issue 39 预留保持 Host 中立。存在 8 个 non-blocking findings 和 3 个 test gap，均为可改进项，不阻塞合并。

---

## Blocking Findings

**无。**

---

## Non-Blocking Findings

### NB-1: `MemoryIncludedReason` / `MemoryExcludedReason` 枚举值与 plan 规格存在简化差异

**Severity**: Low
**Evidence**: `dayu/host/memory.py:121-138`

Plan §4.8 指定了 6 个 included reasons 和 11 个 excluded reasons，实现使用了简化合并值：

| Plan 规格 | 实现值 |
|---|---|
| `PINNED_STATE_REQUIRED` | `PINNED_STATE` |
| `VERIFIED_FACT_REQUIRED` | `TOOL_VERIFIED_FACT` |
| `WORKING_ASSUMPTION_REQUIRED` | `WORKING_ASSUMPTION` |
| `RECENT_RAW_TURN_FLOOR` | `RECENT_RAW_TURN` |
| `HISTORY_POOL_BUDGET_AVAILABLE` | *(无)* |
| `INLINE_DELTA_REPAIR_INCLUDED` | *(无，使用 diagnostic reason)* |
| `OVER_STABLE_LAYER_LIMIT` | `BUDGET_LIMIT` (合并) |
| `OVER_HISTORY_POOL_LIMIT` | `BUDGET_LIMIT` (合并) |
| `OLDER_RAW_TURN_DEGRADED` | *(无)* |
| `EPISODE_SUMMARY_DEGRADED` | *(无)* |
| `MISSING_EVIDENCE_ANCHOR` | `MISSING_PROVENANCE` (合并) |
| `MISSING_FACT_SUMMARY_FALLBACK` | *(使用 diagnostic reason)* |

**影响**: 语义等价，但 item-level 粒度低于 plan 预期。后续 Trace / Tool Trace projection 若需 item-level included / excluded 精细分类，需扩展枚举。

**建议**: P9 不阻塞；Phase 10 接入 trace sink 时按需扩展。

---

### NB-2: `catch_up_projection_best_effort` 在 `HostDispatchScheduler.promote_next_queued_run` 中于 promotion commit 前触发

**Severity**: Low
**Evidence**: `dayu/host/dispatch.py:412-416`

```python
catch_up_projection_best_effort(self._projection_catchup_port)  # line 412
create_host_admission_service(...).promote_next_queued_run(session_id)  # line 414-416
```

dispatch 层的 catch-up 在 admission service promotion commit 之前执行，意味着这次 catch-up 可能基于过时的 projection 状态。admission service 内部的 `promote_next_queued_run` 会在自身 commit 后再次调用 catch-up，形成同一 promotion 路径的双重调用。

**影响**: 不影响正确性——第一次 catch-up 是 no-op 或提前追平，第二次 catch-up 在 promotion commit 后确保覆盖。但增加了不必要的 projection runner 开销。

**建议**: P9 不阻塞；后续 production wiring 时可移除 dispatch 层的提前 catch-up，只保留 admission service 内部的 after-commit catch-up。

---

### NB-3: `catch_up_projection_best_effort` 在 `DefaultHostResolveWaitService.resolve_wait` 中于 promotion commit 前触发

**Severity**: Low
**Evidence**: `dayu/host/waiting.py:588-592`

```python
catch_up_projection_best_effort(self._projection_catchup_port)  # line 588
if isinstance(result, _LateRejectResult): ...  # line 589
# 后续 promotion 在 dispatch_wakeup 中触发
```

与 NB-2 同一模式：resolve_wait 的 write transaction commit 后立即 catch-up，但后续的 promotion 可能产生新的 EventLog events。

**影响**: 同 NB-2，不影响正确性但有额外开销。

**建议**: 同 NB-2。

---

### NB-4: `DurableSessionContinuityProvider.load_session_continuity` 接收但丢弃 `snapshot` 参数

**Severity**: Low
**Evidence**: `dayu/host/run_input.py:569`

```python
del snapshot
```

方法签名保持 `SessionContinuityProvider` protocol 兼容，但 `snapshot` 参数未使用。

**影响**: 无功能影响。接口 contract 允许实现忽略不需要的参数。

**建议**: 保持现状即可；若后续 SessionContinuityProvider 不再需要 snapshot 参数，可在 Phase 10 重构 protocol。

---

### NB-5: `_unsupported_event_type_diagnostic` 使用 `SNAPSHOT_DAMAGED` reason 表达 unsupported event type

**Severity**: Low
**Evidence**: `dayu/host/memory.py:1710-1740`

```python
reason=MemoryDiagnosticReason.SNAPSHOT_DAMAGED,
message=(
    f"{MemoryExcludedReason.UNSUPPORTED_EVENT_TYPE.value}: "
    f"event_type={event.event_type}"
),
```

`SNAPSHOT_DAMAGED` 语义上表达的是 snapshot 数据损坏，但此处用于表达"遇到未识别的 event type"。两者是不同的诊断场景。

**影响**: diagnostic message 文本可区分，但 reason 枚举不精确。当前 durable schema 的 `host_memory_diagnostics.reason` CHECK 约束不包含 `unsupported_event_type`，因此只能借用 `SNAPSHOT_DAMAGED`。

**建议**: P9 不阻塞。后续 schema 版本可新增 `UNSUPPORTED_EVENT_TYPE` diagnostic reason。

---

### NB-6: `MemoryExcludedReason.UNSUPPORTED_EVENT_TYPE` 存在但未被任何 item 的 `excluded_reason` 使用

**Severity**: Low
**Evidence**: `dayu/host/memory.py:136-138`, `dayu/host/memory.py:1710-1740`

`UNSUPPORTED_EVENT_TYPE` 作为 `MemoryExcludedReason` 枚举值存在，但只在 `_unsupported_event_type_diagnostic` 中作为 message 前缀使用，未写入任何 item 的 `excluded_reason` 字段。不支持的 event type 不产生 memory item，因此没有 item 可被标记为 excluded。

**影响**: 枚举值存在但未使用，属于 dead enum member。

**建议**: 不阻塞。保留该值作为未来扩展点。

---

### NB-7: Stable layer budget 以 block 为单位裁剪，不支持 block 内截断

**Severity**: Low
**Evidence**: `dayu/host/run_input.py:1572-1595`

`_bounded_stable_memory_messages` 按 block 整体判断是否在 budget 内。若剩余 budget 不足以容纳整个 block，该 block 被整体跳过。

**影响**: 若一个大 block（如 verified facts）排在靠前位置但超出剩余 budget，后续较小 block 也会被跳过（因为 budget 已耗尽在大 block 上）。但 block 按 P9 优先级排序（goals > subjects > facts > assumptions），高优先级 block 先消耗 budget 是正确行为。

**建议**: 不阻塞。当前 block 粒度已足够；若后续需要更精细裁剪，可在 block 内做 per-item truncation。

---

### NB-8: `_limit_pinned_state` 对所有 pinned 字段使用同一 `max_pinned_items` 限制

**Severity**: Low
**Evidence**: `dayu/host/memory.py:1368-1385`

`max_pinned_items` 同时限制 `confirmed_subjects`、`user_constraints` 和 `open_questions` 的条目数。若某类 pinned 条目需要不同上限，当前 policy 不支持。

**影响**: 第一版保守策略，足够克制。后续 Phase 10 可按需拆分 pinned 字段上限。

**建议**: 不阻塞。

---

## Tests & Docs Gaps

### TG-1: 缺少 `SNAPSHOT_LAG_OVER_THRESHOLD` 和 `SNAPSHOT_AHEAD_OF_REQUIRED` 的 state non-mutation 断言

**Evidence**: `tests/host/test_run_input_builder.py:727-797`

`test_over_threshold_memory_lag_raises_repair_required` 和 `test_ahead_memory_snapshot_raises_repair_required` 验证了 exception reason，但未像 `test_missing_memory_snapshot_raises_repair_without_state_mutation` 那样断言 Run / Attempt / EventLog 状态不变。

**建议**: 补充 `_run_attempt_eventlog_state` 断言，与 `test_missing_memory_snapshot_raises_repair_without_state_mutation` 保持一致。

### TG-2: 缺少 `catch_up_conversation_memory_projection` 从 committed EventLog 追平的端到端测试

**Evidence**: `tests/host/test_memory_projection.py`

现有测试覆盖了 rebuild（从 cursor 0 重放）和 consumer apply_event，但未测试从中间 checkpoint 追平的场景。

**建议**: 补充测试：先 projection 到中间 checkpoint，追加新 events 到 EventLog，调用 catch-up，验证 snapshot 覆盖到最新 committed events。

### TG-3: 缺少 `catch_up_projection_best_effort` 异常容忍测试

**Evidence**: `dayu/host/projection.py:286-293`

函数实现为 try/except + logger.exception，但无测试验证 port 抛异常时函数确实不传播异常。

**建议**: 补充测试：注入抛异常的 `ProjectionCatchupPort`，验证 `catch_up_projection_best_effort` 不抛异常。

---

## Residual Risks & Owners

| Risk | Owner |
|---|---|
| Tool result payload 未必总带业务 fact summary；P9 使用中立 fallback + diagnostic | ToolRuntime / tool contract 后续 work unit |
| Trace / tool trace projection 尚未完整落地；P9 保留 included / excluded reason typed boundary | 后续 Audit / Tool Trace phase |
| Context governance orchestration 尚未完整落地；P9 只提供 repair-required contract | Phase 10 |
| Long-term retrieval、signal ledger、signal-to-outcome verification | Issue 39 / 后续长期 memory phase |
| Public memory edit / reset / forget API | Issue 39 / 需先回写 design.md |
| Provider-aware tokenizer；第一版使用保守 character count estimator | Phase 10 或后续 provider budget work unit |
| `MemoryIncludedReason` / `MemoryExcludedReason` 枚举粒度低于 plan 规格 | Phase 10 接入 trace sink 时扩展 |
| dispatch / waiting 层 catch-up 在 promotion commit 前触发（双重调用） | Production wiring 时优化 |

---

## Evidence Summary

### 核心设计不变量验证

| 不变量 | 状态 | 证据 |
|---|---|---|
| P9 保持"财报分析工作台状态投影"而非聊天记录压缩器 | PASS | `dayu/host/memory.py:1-6` docstring; `dayu/host/memory.py:964-1085` projection 函数 |
| `verified_facts` 只来自工具事实 | PASS | `dayu/host/memory.py:364-367` `__post_init__` 强制 `TOOL_VERIFIED` + `TOOL` producer |
| `final_answer` 不进入 `verified_facts` | PASS | `dayu/host/memory.py:1255-1291` → `ConversationContinuityItem` + `ASSUMPTION` |
| 用户输入不进入 `verified_facts` | PASS | `dayu/host/memory.py:1332-1365` → pinned constraints + continuity |
| P9 不合成 `CONFLICTED` / `STALE` / `SUPERSEDED` | PASS | `tests/host/test_memory_projection.py:1093-1121` |
| provenance 保留 event_id / event_sequence / tool refs | PASS | `dayu/host/memory.py:1201-1213` |
| RunInputBuilder 注入顺序：goals → subjects → facts → assumptions → raw turns → episodes | PASS | `dayu/host/run_input.py:1451-1495` `_memory_stable_blocks` + `_memory_raw_turn_messages` + `_memory_episode_summary_message` |
| recent raw turns floor 是 count-based floor | PASS | `dayu/host/memory.py:1460-1464` |
| older raw turns 与 episode summaries 共享 history pool | PASS | `dayu/host/memory.py:1466-1480` |
| 降级顺序：episode summaries 先降级，older raw turns 后降级 | PASS | `dayu/host/memory.py:1473-1480` — older_raw + primary_pool 先填充，episodes 后填充 |
| projection lag 不触发 Run recovery | PASS | `MemoryProjectionRepairRequired` 继承 `HostDurableError`，不修改 Run 状态 |
| snapshot 缺失 / 损坏 → repair-required | PASS | `tests/host/test_run_input_builder.py:630-674` |
| snapshot 与 checkpoint 同事务提交 | PASS | `dayu/host/durable/memory.py` `write_memory_snapshot_with_checkpoint` |
| `SessionContinuityProvider` 不注入未预算 historical raw turns | PASS | `dayu/host/run_input.py:569-577` `del snapshot; return resume-only` |
| Host memory schema / contracts 不包含业务专有字段 | PASS | `tests/host/test_memory_projection.py:84-88` `_FORBIDDEN_BUSINESS_TERMS` 断言 |
| `OpaqueMemoryRef.ref_kind` 使用 Host-neutral enum | PASS | `dayu/host/memory.py:108-118` `HostNeutralRefKind` |
| `dayu.host.memory` 不 import engine / fins / service / ui | PASS | grep 无匹配 |
| snapshot digest 不包含 `built_at` / `diagnostic_id` / `recorded_at` | PASS | `dayu/host/memory.py:2168-2197` `_snapshot_digest_json_value` |
| 同一 EventLog + 同一 policy → 稳定 snapshot digest | PASS | `tests/host/test_memory_projection.py:1335-1400` |
| after-commit catch-up best-effort failure 不影响 EventLog append / Run terminal | PASS | `dayu/host/projection.py:286-293` try/except + logger.exception |
| schema fresh-only，不写旧库兼容 | PASS | `dayu/host/durable/schema.py:931-933` 版本不匹配直接 raise |
| `HOST_SCHEMA_VERSION` 从 5 递增到 6 | PASS | `dayu/host/durable/schema.py:25` |
| Issue 39 预留保持 Host 中立 | PASS | `MemoryClaimStatus` 只预留 enum 值，不主动合成 conflict / stale / supersede |
