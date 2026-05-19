# 复审：Host-owned LLM context compactor plan (v2)

**Reviewer**: AgentMiMo
**Date**: 2026-05-19
**Plan artifact**: `docs/host/host-owned-compactor-plan.md` (已吸收初审 B-1/B-2/B-3 与总控讨论)
**Review scope**: 确认初审 blocking findings 是否收口；检查新增约束是否完整覆盖

## 0. 初审 Blocking Findings 收口状态

### B-1 [HIGH] LLMContextCompactor 构造映射步骤缺失 → RESOLVED

**初审问题**：Plan 缺少 `LLMContextCompactor.__init__` 完整签名、prompt/AgentPolicy/CancellationToken 来源定义。

**收口证据**：

- §3.2 给出完整构造签名：`def __init__(self, *, runner_spec, runner_options, compactor_policy_ref) -> None`
- §3.2 bullet 4: prompt 是 Host private helper，不进入 public options
- §3.2 bullet 5: `AgentPolicy` 由 Host 固定：`allow_tool_calls=False`、`max_iterations` 使用小上限、timeout/retry 只来自 runner spec/options
- §3.2 bullet 6: `CancellationToken` 第一版不从 Service 传入；LLM 调用返回后重新检查 durable Run/Attempt 状态，状态已变化则丢弃结果
- Slice 2 step 5: `tool_schemas=()`、rejecting tool executor、`allow_tool_calls=False`
- Slice 2 step 6: 当前 `ContextCompactor.compact(request)` 无 token 参数，第一版依赖 runner timeout/retry

**评价**：完全收口。构造边界、prompt ownership、AgentPolicy 策略、CancellationToken 处理均有明确固定策略，不留实现者自行决定的空间。

### B-2 [HIGH] Reactive compact 注入链未覆盖 → RESOLVED

**初审问题**：Plan 未写出 `CompactorRunnerBaseline` → `LLMContextCompactor` → `HostLocalExecutionOptions.context_compactor` → `EngineEventIngestor` 的完整注入链。

**收口证据**：

- Slice 3 step 4: "显式保持完整注入链：`CompactorRunnerBaseline` -> Host-owned `LLMContextCompactor` -> `HostLocalExecutionOptions.context_compactor` -> `HostDispatchScheduler` -> `EngineEventIngestor`。proactive 与 reactive compact 必须使用同一个 Host-owned instance/config 来源。"
- Slice 3 step 6: "Slice 1、2、3 必须作为同一个 implementation PR 内的连续变更完成，不接受'public API 已切但 Host-owned compactor 未接线'的可合并中间态。"

**评价**：完全收口。注入链显式写出，且禁止中间态合并，消除了 reactive compact 路径断掉的风险。

### B-3 [MEDIUM] Smoke 断言策略不足 → RESOLVED

**初审问题**：删除 `_RealLLMContextCompactor` 后只检查 artifact 文件存在，无法区分"compactor 真的跑了"和"旧 artifact"。

**收口证据**：

- Slice 5 step 4: "compact artifact root 下存在本次运行窗口内新创建或新修改的 artifact"
- Slice 5 step 4: "artifact path / metadata 能和本次 smoke session/run window 对上，避免误读旧 artifact"
- §6.3 manual smoke: "compact artifact root 下有本次 run window 内产生的 artifact"

**评价**：完全收口。断言策略从"artifact 存在"升级为"当前 run window 的 artifact"，有时效性校验。

## 1. 新增约束检查

### C-1: Service 不实现 ContextCompactor.compact

**Plan 覆盖**：

- §0: "Service 不实现 `ContextCompactor.compact(...)`"
- §3.1: "普通 Service / `OpenHostOptions` 只提供 compactor 运行与存储配置，不提供 `ContextCompactor` 实例"
- §3.5: "不得出现在普通 Service-facing package root / `OpenHostOptions` public contract、manual smoke 的 Service 装配路径或 README 普通用法中"
- Slice 1 step 3: "删除普通 Service-facing 的 `CompactorExecutionBaseline` 路径"

**评价**：完整覆盖。`ContextCompactor` 从 public contract 移除，`CompactorExecutionBaseline` 从包根删除，Service 只传 `CompactorRunnerBaseline`（runner config only）。

### C-2: Provider/transport failure 只走 runner bounded retry

**Plan 覆盖**：

- §3.6: "Transport / provider failure：网络错误、timeout、5xx、rate limit 等只允许由 Runner/provider 层按 `RunnerSpec.max_retries` 与 retry policy 做 bounded retry。Host 不把 retry 策略交给 Service"
- Slice 2 step 9: `test_llm_context_compactor_uses_runner_retry_policy_not_dirty_output_replay`
- §5.1 风险: "脏输出误判为可重试错误：Provider failure 可以 runner retry；脏输出是 Host contract failure，第一版必须 fail closed"

**评价**：完整覆盖。Provider failure 与 dirty output 的边界清晰，retry 策略固化在 runner 层。

### C-3: Dirty output 不 replay 且 fail closed

**Plan 覆盖**：

- §3.6: "Dirty output / contract failure：非 final answer、空 summary、解析失败、candidate shape 非法、缺 preservation evidence、quality check reject、compact 后仍超过 hard threshold，第一版一律 fail closed：写 `CONTEXT_COMPACTION_FAILED`，不写 compact artifact，不写 `CONTEXT_COMPACTED`，不更新 memory projection"
- §3.6: "不做 dirty-output replay：脏数据不是 Run replay，也不是 Service retry"
- Slice 2 step 8: "LLM final answer 为空、非 final answer、解析失败或 summary 不满足最小约束时直接抛出 typed compaction failure；不在 `LLMContextCompactor` 内做 dirty-output replay"

**评价**：完整覆盖。dirty output 的定义枚举完整，fail closed 路径明确，不做自动 replay。

### C-4: 真实 LLM call 不在 Host write transaction 内

**Plan 覆盖**：

- §3.6: "LLM call 不得位于 Host write transaction 内：Host 可以在 write transaction 内冻结 input snapshot / append `CONTEXT_COMPACTION_REQUESTED`，但真实 LLM 调用必须发生在 transaction 外。LLM 返回后再开启新的 write transaction，recheck Run/Attempt/dispatch 状态与 expected cursor"
- Slice 4 step 2: proactive compact 拆成三段（write request → LLM call → recheck/write result）
- Slice 4 step 3: reactive fallback 同样拆成三段
- Slice 4 step 5: stale result 策略
- Slice 4 step 8: 新增 `test_proactive_compaction_calls_llm_outside_write_transaction`、`test_reactive_compaction_calls_llm_outside_write_transaction`、`test_compaction_stale_result_does_not_write_compacted_event`
- §7 handoff step 4: "审计并调整 dispatch / engine ingest compact 执行阶段"

**代码事实验证**：当前 `dispatch.py:1063` 和 `engine_ingest.py:1382` 的 `compactor.compact(request)` 都在 `transaction: HostTransaction` 参数的方法内调用。Plan Slice 4 正确识别了这个问题并要求拆分。

**评价**：完整覆盖。Plan 不仅提出了约束，还给出了具体的三段拆分方案、stale result 策略和对应的测试用例。这是本版 plan 最重要的架构改进之一。

### C-5: Current-run artifact 断言

**Plan 覆盖**：

- Slice 5 step 4: "compact artifact root 下存在本次运行窗口内新创建或新修改的 artifact；artifact path / metadata 能和本次 smoke session/run window 对上，避免误读旧 artifact"
- §6.3: "compact artifact root 下有本次 run window 内产生的 artifact"

**评价**：完整覆盖。断言策略有时效性和 session/run 关联校验。

## 2. 架构完整性检查

### 2.1 Transaction boundary 拆分的实现风险

Slice 4 要求把 proactive compact 从当前的"单 transaction 内完成全部操作"拆成"write request → LLM call → recheck/write result"三段。当前代码（`dispatch.py:979` `_compact_before_dispatch`）的 `transaction` 参数贯穿整个方法，包括 `compactor.compact(request)` 调用。

**风险**：拆分后，`CONTEXT_COMPACTION_REQUESTED` 与 `CONTEXT_COMPACTED` 不在同一个 transaction 内，中间可能出现：
- Run 被 cancel
- Session 被 close
- 另一个 compact 被触发（理论上不应发生，因为 budget governance 在 compact 后仍可能触发第二次）
- durable cursor 变化

**Plan 收口**：Slice 4 step 5 明确要求"LLM 返回后若 run/attempt/session 已被取消、关闭、替换或 cursor 不匹配，不写 `CONTEXT_COMPACTED`"。这是正确的 stale result 防护。

**残留风险**：拆分后 `CONTEXT_COMPACTION_REQUESTED` 已写入 durable，但 compact 最终 failed——此时 Run 的 EventLog 会有一条 `REQUESTED` + 一条 `FAILED`，这是预期行为，不是 bug。但实现时需要确保 `REQUESTED` event 的 `event_id` 能被后续 `FAILED` event 正确引用，形成可追溯链。

### 2.2 Reactive compact 三段拆分的调用位置

当前 reactive compact 在 `EngineEventIngestor._compact_reactive_recovery`（`engine_ingest.py:1325`）中调用，该方法也是在 `transaction: HostTransaction` 内。拆分后需要确认：reactive compact 的"LLM call 在 transaction 外"如何与 `EngineEventIngestor` 的 ingest 流程集成？

当前 ingest 流程是：ingest Engine event → 判断是否需要 reactive compact → 在同一 transaction 内 compact → 写结果。拆分后应该是：ingest Engine event → 判断需要 compact → write `REQUESTED` → commit → LLM call → new transaction → recheck → write result。

**Plan 收口**：Slice 4 step 3 说"Reactive fallback 同样拆成 request durable write、transaction 外 LLM call、结果 recheck/write 三段"。但没有具体说明 `EngineEventIngestor` 的方法签名如何变化。

**残留风险**：低。`EngineEventIngestor` 的 reactive compact 是在 ingest 流程中触发的，拆分后 ingest 方法需要变成"要么完成 ingest + compact，要么只完成 ingest + write REQUESTED，返回后由外部调用 LLM 再 commit result"。这可能需要 `EngineEventIngestor` 的方法返回一个 compact pending 标识，由调用方（`dispatch.py`）在 transaction 外执行 LLM call 再回来写结果。Plan 没有写出这个交互细节，但 Slice 4 step 8 要求测试覆盖，实现时会自然暴露。

## 3. 测试矩阵完整性

| 测试名 | 覆盖维度 | 评价 |
|--------|---------|------|
| `test_llm_context_compactor_builds_tool_disabled_request` | request shape | 已列出 |
| `test_llm_context_compactor_maps_final_answer_to_candidate` | candidate mapping | 已列出 |
| `test_llm_context_compactor_rejects_empty_or_non_final_output` | dirty output fail closed | 已列出 |
| `test_llm_context_compactor_preserves_host_owned_refs_and_evidence` | ref/evidence ownership | 已列出 |
| `test_llm_context_compactor_uses_runner_retry_policy_not_dirty_output_replay` | retry vs replay 边界 | 已列出 |
| `test_proactive_compaction_calls_llm_outside_write_transaction` | transaction 边界 | 已列出 |
| `test_reactive_compaction_calls_llm_outside_write_transaction` | transaction 边界 | 已列出 |
| `test_compaction_stale_result_does_not_write_compacted_event` | stale result 防护 | 已列出 |

**评价**：测试矩阵完整，覆盖了 candidate mapping、dirty output、retry policy、transaction 边界和 stale result 五个关键维度。

## 4. 结论

**PASS。无 blocking finding。**

初审 B-1/B-2/B-3 全部收口。五个新增约束（Service 不实现 compact、runner bounded retry、dirty output fail closed、LLM call outside transaction、current-run artifact 断言）均有完整覆盖。

**Residual risks**（不 blocking）：

1. **Reactive compact 三段拆分的 `EngineEventIngestor` 方法签名变化**：Plan 没有写出 `EngineEventIngestor` 方法如何返回 compact pending 标识，但 Slice 4 step 8 的测试要求会在实现时自然暴露这个交互点。
2. **`CONTEXT_COMPACTION_REQUESTED` 与 `CONTEXT_COMPACTED` 跨 transaction 的可追溯链**：拆分后两条 event 不在同一个 transaction，实现时需确保 event_id 引用关系正确。
3. **Slice 1-3 合并为同一 PR 的 merge conflict 风险**：三个 slice 涉及 `api.py`、`__init__.py`、`open_host.py`、`dispatch.py`、`engine_ingest.py` 和多个测试文件，合并 PR 的 review 复杂度较高。
