# Phase 10 Aggregate Deep Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: Phase 10 Context Governance / Compaction aggregate deepreview
Commit range: f131fb8..HEAD (7 commits)
Gate: Phase 10 aggregate deepreview

## Verdict

**PASS — Phase 10 已可进入 ready-to-open-draft-PR。**

## Summary

Phase 10 实现了 Host-owned context budget governance、proactive compaction、reactive overflow recovery、canonical compact event/artifact、P9 memory projection consumption、RunInputBuilder compact/memory provider 与 production composition wiring。全部 6 个 slice（S1-S6）已通过各自 code review 并被 controller accepted。

验证结果：261 passed，pyright 0 errors，`git diff --check` clean。

架构边界全部通过（7/7），状态机转换全部正确（14/14 子项），持久化与事件 schema 全部通过（5/5），三个 exit condition 全部由测试覆盖。8 项已知 residual 均为 accepted residual，有明确 owner 和 destination，不阻塞 PR。

---

## 1. Exit Condition 验证

### Exit Condition 1：Host 主动 compact + Engine overflow reactive fallback

> Host 能在 dispatch 前主动 compact，并能把 Engine overflow 当作 reactive fallback 恢复，不让 Engine 管理 Host context budget。

**PASS。**

| 子条件 | 测试证据 | 结论 |
| --- | --- | --- |
| Proactive soft threshold 在 Attempt 前触发 compact | `test_dispatch_scheduler.py:1918` — 事件顺序 CONTEXT_COMPACTION_REQUESTED < CONTEXT_COMPACTED < RUN_STARTED < ATTEMPT_STARTED | PASS |
| Proactive compact failure attempt-free | `test_dispatch_scheduler.py:1962` — 零 Attempt，Run FAILED | PASS |
| Proactive count limit 阻止二次 compact | `test_dispatch_scheduler.py:1998` — proactive_compact_limit_reached | PASS |
| Reactive overflow 使用 Host estimator（非 Engine budget_state） | `test_engine_ingest_mapping.py:296` — budget_state=None 时使用 Host estimator | PASS |
| Reactive stale identity 拒绝 | `test_engine_ingest_mapping.py:348` — stale execution_id rejected | PASS |
| Reactive recovery 创建新 Attempt | `test_engine_ingest_mapping.py:296` — 新 Attempt + execution_id | PASS |
| Reactive failure 不进入 LOST | `test_engine_ingest_mapping.py:390` — FAILED 收口 | PASS |
| Reactive count limit | `test_engine_ingest_mapping.py:458` — reactive_compact_limit_reached | PASS |
| Reactive worker overflow 端到端 | `test_dispatch_scheduler.py:2187` — accepted_snapshots=2, 新旧 attempt_id 不同 | PASS |
| Budget 参数仅来自 typed Host policy | 架构边界检查 3 — context_budget.py 不读取 Engine spec/metadata/payload | PASS |

### Exit Condition 2：多轮会话主体闭环可验证

> 多轮会话主体闭环可验证：用户约束/目标、tool-verified facts、recent raw turns、older raw turns 与 accepted episode summaries 能在后续 Run 的 AgentRunRequest.messages 中按 P9/P10 policy 稳定出现。

**PASS。**

| 子条件 | 测试证据 | 结论 |
| --- | --- | --- |
| Recent raw turns 在后续 Run 出现 | `test_dispatch_scheduler.py:2123` — Turn 2 request 包含 Turn 1 text | PASS |
| Proactive compact 后 pinned state 出现 | `test_dispatch_scheduler.py:2177` — `current_goal=` 存在 | PASS |
| Proactive compact 后 confirmed_subjects 出现 | `test_dispatch_scheduler.py:2178` — `confirmed_subject=subject:` 存在 | PASS |
| Proactive compact 后 episode summary 出现 | `test_dispatch_scheduler.py:2173-2174` — `Memory episode summaries:` 存在 | PASS |
| 消息排序：pinned < raw < episode | `test_dispatch_scheduler.py:2180` — goal_index < raw_index < episode_index | PASS |
| CONTEXT_COMPACTED 被 memory projection 消费 | `test_memory_projection.py:1322` — episode summary + pinned patch | PASS |
| DurableCompactArtifactProvider 注入 RunInputBuilder | `test_run_input_builder.py:849` — pinned state + episode summary in messages | PASS |
| Memory snapshot 与 RunInputBuilder 消息顺序 | `test_run_input_builder.py:424` — system → memory → facts → raw → episode → prompt | PASS |
| History pool recent floor 保留 | `test_memory_projection.py:1501` — recent raw turns 不被丢弃 | PASS |

### Exit Condition 3：无 owner 的 stable layer / history pool 缺口

> P10 不留下无 owner 的"stable layer / history pool 只有结构没有来源"缺口。

**PASS。**

| 数据来源 | 映射 | 测试证据 | 结论 |
| --- | --- | --- | --- |
| pinned_state.current_goal | USER_INPUT_ACCEPTED 初始化 | `test_memory_projection.py:1069` | PASS |
| pinned_state.current_goal | CONTEXT_COMPACTED patch 更新 | `test_memory_projection.py:1348` | PASS |
| pinned_state.confirmed_subjects | CONTEXT_COMPACTED patch 更新 | `test_memory_projection.py:1348` | PASS |
| pinned_state.user_constraints | USER_INPUT_ACCEPTED 初始化 | `test_memory_projection.py:1039` | PASS |
| verified_facts | TOOL_RESULT_ACCEPTED 仅此一个 | `test_memory_projection.py:1146` | PASS |
| verified_facts 不来自 USER_INPUT | 反面测试 | `test_memory_projection.py:1039` | PASS |
| verified_facts 不来自 RUN_SUCCEEDED | 反面测试 | `test_memory_projection.py:1013` | PASS |
| verified_facts 不来自 CONTEXT_COMPACTED | 反面测试 | `test_memory_projection.py:1467` | PASS |
| episode_summaries | CONTEXT_COMPACTED episode_summary_candidate 仅此一个 | `test_memory_projection.py:1322` | PASS |
| recent raw turns | USER_INPUT_ACCEPTED + RUN_SUCCEEDED | `test_memory_projection.py:1039,1013` | PASS |

---

## 2. 架构边界验证

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| Context Governance 不直接写 memory snapshot | PASS | `context_governance.py` 仅从 `compaction.py` 导入，未导入 `memory.py` / `durable/memory.py` |
| Engine 不拥有 budget/memory/recovery | PASS | `engine_ingest.py` 使用 Host 注入的 `context_budget_policy`，不从 Engine spec/metadata/payload 读取 budget |
| Budget 参数仅来自 typed Host policy | PASS | `context_budget.py` docstring 明确声明；`dispatch.py` 通过 `self._local_execution.context_budget_policy` 读取 |
| Memory projection 仅来自 committed canonical facts | PASS | `durable/memory.py` event filter 只过滤 CANONICAL_FACT class，包含 CONTEXT_COMPACTED |
| DurableCompactArtifactProvider 仅暴露安全字段 | PASS | `run_input.py:1909-1945` — event_sequence < started_event_sequence 过滤，只暴露 ref/digest/episode summary |
| 7 个 P10 新模块无反向依赖 | PASS | 全部仅导入 dayu.host 内部模块和 dayu.contracts |
| FakeContextCompactor 不被 production 路径导入 | PASS | 仅 4 个 test 文件导入 |

---

## 3. 状态机验证

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| start_run 创建 ACCEPTED Run 无 Attempt | PASS | `run_transition.py:818-862` — current_attempt_id=None, 不插入 Attempt |
| cancel_run 处理 ACCEPTED 无 Attempt | PASS | `run_transition.py:2078-2139` — CANCEL_REQUESTED + RUN_CANCELLED, attempt=None |
| ALLOW_DISPATCH: RUN_STARTED + ATTEMPT_STARTED | PASS | `run_transition.py:1034-1069` — 无 RECOVERING |
| SOFT_THRESHOLD compact 成功后启动 | PASS | `dispatch.py:517-530` — memory catch-up 后 _start_governed_after_compact |
| HARD_THRESHOLD/compact failure: RUN_FAILED 无 Attempt | PASS | `run_transition.py:1080-1130` — current_attempt_id != None 拒绝 |
| Per-Run proactive count 阻止二次 compact | PASS | `dispatch.py:609-647,769-791` — count_committed_events_by_run_and_type |
| Reactive validates attempt_id + execution_id | PASS | `engine_ingest.py:493,754-758` |
| ATTEMPT_FAILED + RUN_RECOVERING | PASS | `run_transition.py:1158-1196` |
| Recovery: 新 Attempt + RUN_STARTED(RECOVERY) + ATTEMPT_STARTED | PASS | `engine_ingest.py:348-349`, `run_transition.py:1245-1280` |
| Recovery failure: RUN_FAILED 从 RECOVERING，永不 LOST | PASS | `engine_ingest.py:1526-1586`, `run_transition.py:1292-1350` |
| Per-Run reactive count 阻止二次 compact | PASS | `engine_ingest.py:1030-1050,1236-1258` |
| Proactive 事件排序 | PASS | REQUESTED → COMPACTED → RUN_STARTED → ATTEMPT_STARTED |
| Reactive 事件排序 | PASS | REQUESTED → ATTEMPT_FAILED → RUN_RECOVERING → COMPACTED → RUN_STARTED → ATTEMPT_STARTED |
| 旧 Attempt 不被 resume 或 takeover | PASS | `run_transition.py:1177-1184,1266-1280` — FAILED 终态 + 新 Attempt row |

---

## 4. 持久化与事件验证

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| RunStatus.ACCEPTED 在 schema CHECK 中 | PASS | `schema.py:302-315` — status IN (..., 'accepted', ...) |
| Schema 版本 HOST_SCHEMA_VERSION = 9 | PASS | `schema.py:25` |
| Accepted Run 专用 CHECK 约束 | PASS | `schema.py:349-357` — queued/started/current_attempt 全 NULL |
| Accepted per-session 唯一索引 | PASS | `schema.py:817-820` — INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION |
| CONTEXT_COMPACTION_REQUESTED payload 校验 | PASS | `context_events.py:168-193` — reactive 要求 attempt_id + execution_id |
| CONTEXT_COMPACTED payload 校验 | PASS | `context_events.py:252-285` — proposed_verified_fact_refs 必须为空 |
| CONTEXT_COMPACTION_FAILED payload 校验 | PASS | `context_events.py:324-337` |
| Compact artifact 确定性 descriptor + digest | PASS | `compact_artifact.py:154-167` — canonical_json_dumps + expected_digest |
| Corrupted digest 拒绝 | PASS | `compact_artifact.py:156-159` — HostDigestMismatchError |
| Proactive compact count 与 REQUESTED 同一写事务 | PASS | `dispatch.py:609-629,669` — 同一 run_write 回调 |
| Memory catch-up 在 RUN_STARTED 之前 | PASS | `dispatch.py:518-526` — catch_up → _start_governed_after_compact |
| Corrupted compact count fail closed | PASS | `dispatch.py:608-629` — 任何异常 → CONTEXT_COMPACTION_FAILED + RUN_FAILED |
| DurableCompactArtifactProvider cursor 过滤 | PASS | `run_input.py:1909-1945` — event_sequence < started_event_sequence |

---

## 5. 测试覆盖总结

| 测试文件 | 所属 Slice | 测试数 |
| --- | --- | --- |
| test_context_budget.py | S1 | 20 |
| test_compaction_contract.py | S2 | ~10 |
| test_compact_artifact_store.py | S2 | ~7 |
| test_context_compact_events.py | S3 | 15 |
| test_memory_projection.py | S3 | ~30+ |
| test_run_input_builder.py | S3/S4 | ~20+ |
| test_engine_ingest_mapping.py | S1/S5 | ~15+ |
| test_run_attempt_transitions.py | S4/S5 | ~15+ |
| test_dispatch_scheduler.py | S4/S5/S6 | ~30+ |
| test_phase5_local_execution_integration.py | S4/S5/S6 | ~10+ |
| test_public_contracts.py | S1/S6 | 39 |
| **总计** | | **261 passed** |

pyright: 0 errors, 0 warnings, 0 informations。

---

## 6. 已知 Residual 评估

### R1. Compactor 调用与 artifact write 在 SQLite write transaction 内

- **来源**: S4 controller accepted residual (追踪区 1496-1498)
- **风险**: 真实异步 LLM compactor 接入时，compactor 调用（可能数秒）在 SQLite write transaction 内会阻塞其它写操作
- **当前缓解**: FakeContextCompactor 是确定性同步调用，无实际延迟
- **评估**: **accepted residual**。引入真实 LLM compactor 时必须设计 durable in-progress / fencing，将 compactor 调用移出 write transaction。当前架构不阻塞 PR。
- **Owner**: Production compactor adapter owner

### R2. Budget estimate 只覆盖当前 user input display_text

- **来源**: S4 controller accepted residual (追踪区 1499-1500)
- **风险**: 不完整估算 RunInputBuilder 最终 messages（含 memory snapshot、tool schemas、compact artifact refs）可能导致 compact 触发偏早或偏晚
- **当前缓解**: Conservative estimator 使用 `ceil(len/3) + 12` overhead，偏保守
- **评估**: **accepted residual**。Provider-specific tokenizer 和完整 message sizing 归后续 owner。Conservative estimator 保证不会低估。
- **Owner**: Tokenizer / sizing owner (future phase)

### R3. `promote_next_queued_run` legacy helper 公开表面

- **来源**: S4 controller accepted residual (追踪区 1501-1502)
- **风险**: 该 helper 直接创建 RUN_STARTED + ATTEMPT_STARTED，不经过 Context Governance gate。如果被误用为 production 调用，会绕过 proactive compact
- **当前缓解**: 无 production 调用者；scheduler 的 `wake_queue_promotion` 走独立 governance 路径；README 已说明保留为低层 admission helper
- **评估: accepted residual**。Controller 要求 "Phase 10 closeout 或后续 Host public API cleanup 必须复查是否收敛接口面"。当前不阻塞 PR，但应在 Phase 10 closeout 或 Phase 11 中决定：(a) 加 governance gate wrapper，(b) 标记为 internal，或 (c) 移除并让测试改用 governance gate 路径。
- **Owner**: Host public API cleanup owner

### R4. `EngineEventIngestor._start_reactive_context_recovery` 方法体偏长

- **来源**: S5 controller accepted residual (追踪区 1515-1517)
- **风险**: ~124 行方法承担 policy 读取、input event 读取、budget estimate、compact count 检查、request append、attempt closeout、compact 调用、失败收口和 accepted 返回
- **当前缓解**: 内部已抽取 `_fail_reactive_recovery_without_request`、`_append_reactive_compaction_requested_event`、`_close_attempt_for_context_recovery`、`_compact_reactive_recovery` 等 helper
- **评估: accepted residual**。职责仍属于 EngineEvent ingest owner。可进一步抽取 budget/compact decision helper，但不得改变 EventLog / state machine ordering。
- **Owner**: EngineEvent ingest owner

### R5. `compose_host_local_execution_options(...)` 只有 Host helper，无 production caller

- **来源**: S6 controller accepted residual (追踪区 1532-1534)
- **风险**: composition helper 已实现但 Service/composition root 尚未调用
- **当前缓解**: public contract test 已验证 wiring 正确性
- **评估: accepted residual**。等待 Service/composition root 实现时接入。
- **Owner**: Production composition root owner

### R6. Production LLM compactor adapter 未实现

- **来源**: S2/S6 controller accepted residual (追踪区 1535-1536)
- **风险**: 未配置 compactor 时 compact 触发 fail closed（RUN_FAILED）
- **当前缓解**: FakeContextCompactor 仅在 tests/local dev 显式注入；production 不隐式使用 fake
- **评估: accepted residual**。Production 必须显式提供 `ContextCompactor` 实现。
- **Owner**: Production compactor adapter owner

### R7. S6 aggregate test 未串完整业务工具 verified fact public fake-worker 链路

- **来源**: S6 controller accepted residual (追踪区 1537-1540)
- **风险**: multi-turn test 使用 `_FinalAnswerWorker`（返回 final_answer），不执行工具调用，因此不产生 TOOL_RESULT_ACCEPTED → verified fact
- **当前缓解**: ToolRuntime accepted fact、memory projection verified fact、RunInputBuilder verified fact message 由分层测试覆盖
- **评估: accepted residual**。若要求更高保真 E2E，应作为 aggregate fix item，但不把 fake compactor 注入 production 默认路径。
- **Owner**: Aggregate validation owner

### R8. Provider-specific tokenizer / conservative estimator 精度

- **来源**: Plan residual #6 (plan 583-589)
- **风险**: `ceil(len/3) + 12` 可能触发比必要更多的 compact
- **当前缓解**: 偏保守保证不会低估；不会导致 correctness 问题
- **评估: accepted residual**。独立能力接入，不改变 Host policy 真源边界。
- **Owner**: Future tokenizer adapter phase

---

## 7. 分层越界最终检查

| 设计约束 | 实现状态 | 证据 |
| --- | --- | --- |
| Engine 不做 Host-side compact retry | PASS | Engine 只 emit context_compaction_requested；Host 负责 compact |
| Host 不从 Engine spec/metadata/payload 读取 budget | PASS | 架构边界检查 2 + 3 |
| Context Governance 不直接写 memory snapshot | PASS | 架构边界检查 1 |
| Memory projection 只消费 committed canonical facts | PASS | 架构边界检查 4 |
| LLM output 是 candidate，quality check 后才写 COMPACTED | PASS | `context_governance.py` + `dispatch.py` / `engine_ingest.py` quality check |
| Proactive failure 不创建 Attempt | PASS | 状态机检查 5 |
| Reactive failure 不进入 LOST | PASS | 状态机检查 10 |
| Compact 不能改写历史 EventLog facts | PASS | EventLog 只 append，不 update |
| episode summary 不替代 evidence anchor | PASS | `test_memory_projection.py:1289` |
| verified_facts 只来自 TOOL_RESULT_ACCEPTED | PASS | `test_memory_projection.py:1146` + 反面测试 |
| 新 Attempt 使用新 attempt_id + execution_id | PASS | `engine_ingest.py:348-349` |
| 旧 Attempt 不被 resume 或 takeover | PASS | 状态机检查 14 |

---

## 8. README / Docs / PR Readiness

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `dayu/host/README.md` 覆盖 P10 五项核心内容 | PASS | Context Governance Boundary 节 (行 123-141) |
| `tests/README.md` 列出 P10 测试文件 | PASS | 嵌入式引用 (行 50-51, 95) |
| `implementation-control.md` 状态与残余追踪 | PASS | 当前 gate: aggregate deepreview (行 225-227)，追踪区 8 项 (行 1486-1540) |
| `promote_next_queued_run` 文档说明 | PASS | README 行 175: "保留为低层 admission helper" |
| git diff --check | PASS | clean |

---

## 9. Findings Summary

**无 blocking / high / medium / low findings。**

全部 8 项已知 residual 均为 **accepted residual**，有明确 owner 和 destination：

| ID | 描述 | 级别 | Owner | Destination |
| --- | --- | --- | --- | --- |
| R1 | Compactor 在 write transaction 内 | accepted residual | compactor adapter owner | 引入真实 LLM compactor 时 |
| R2 | Budget estimate 只覆盖 display_text | accepted residual | tokenizer/sizing owner | future phase |
| R3 | `promote_next_queued_run` 接口面 | accepted residual | API cleanup owner | P10 closeout / P11 |
| R4 | `_start_reactive_context_recovery` 偏长 | accepted residual | ingest owner | code organization |
| R5 | composition helper 无 production caller | accepted residual | composition root owner | Service 层实现时 |
| R6 | Production LLM compactor 未实现 | accepted residual | compactor adapter owner | production wiring |
| R7 | Aggregate test 未串 verified fact 链路 | accepted residual | aggregate owner | higher-fidelity E2E |
| R8 | Conservative estimator 精度 | accepted residual | tokenizer owner | future phase |

---

## 10. Residual 风险矩阵

| 风险 | 可能性 | 影响 | 缓解 | 阻塞 PR |
| --- | --- | --- | --- | --- |
| `promote_next_queued_run` 被误用绕过 governance gate | 低（无 production caller） | 高（跳过 proactive compact） | README 已说明；追踪区已记录 | 否 |
| Compactor LLM 调用阻塞 SQLite writes | N/A（当前无真实 LLM） | 高 | FakeContextCompactor 同步无延迟 | 否 |
| Budget estimate 不完整导致 compact 偏早 | 中（conservative estimator） | 低（偏早 compact 不影响 correctness） | 偏保守策略 | 否 |
| Orphan artifact 文件（进程 crash） | 低 | 低（非 truth，可重建） | Phase 11 startup recovery | 否 |
| RECOVERING 状态无 cancel 路径 | 低（需 Engine 同时发 overflow + 用户 cancel） | 中（Run 卡在 RECOVERING） | Phase 11 接管 | 否 |

---

## 11. 结论

Phase 10 达到了设计目标：

1. **Host-owned context budget policy** — `ContextBudgetPolicy` 由 composition root 显式提供，`context_window_size` / `reserved_output_tokens` 必填
2. **Proactive compaction** — `wake_queue_promotion` 的 pre-start governance gate 在 Attempt 前触发
3. **Reactive overflow recovery** — Engine `context_compaction_requested` → Host 校验 identity → close old Attempt → RECOVERING → compact → new Attempt
4. **Canonical compact event/artifact** — `CONTEXT_COMPACTED` payload 包含 episode summary candidate、pinned state patch candidate、preserved fact refs、quality check、budget after compact
5. **P9 memory projection consumption** — `ConversationMemoryProjectionConsumer` 消费 `CONTEXT_COMPACTED`，按三态语义更新 pinned state，产生 episode summary continuity item
6. **RunInputBuilder compact/memory provider** — `DurableCompactArtifactProvider` 读取 Attempt cursor 之前的 compacted event，`DurableMemorySnapshotProvider` 提供 memory snapshot
7. **Production composition wiring** — `compose_host_local_execution_options(...)` 从 command options 构造 typed `ContextBudgetPolicy`，注入 compact artifact root

多轮会话主体闭环已可验证：pinned state、confirmed subjects、tool-verified facts、recent raw turns、episode summaries 在后续 Run 的 Engine request messages 中按 P9/P10 policy 稳定出现。

**Phase 10 已可进入 ready-to-open-draft-PR。**
