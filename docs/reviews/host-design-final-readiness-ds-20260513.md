# Host Design Final Readiness Review — Adversarial

**Reviewed documents**:
- `docs/host/design.md` (v2 post-P0-cleanup, 终态)
- `docs/host/implementation-control.md` (实施总控)

**Terminology source of truth**: `dayu/README.md`

**Date**: 2026-05-13
**Review type**: Adversarial final readiness review — gate for phase orchestration entry
**Prior gate**: v2 controller adjudication (P0s resolved, re-review passed)

---

## Verdict

**PASS with non-blocking findings**

The design is sufficiently hardened to enter phase orchestration. Architecture boundaries are hard, semantic contracts are clear, the state machine is complete, and there are no remaining blockers that would prevent a phase plan agent from producing implementation-ready plans. The 10 findings below are phase-level refinements that can be resolved during their respective phase discussions.

---

## Findings

### Blocker

None.

---

### High

#### H1. `submit_followup(behavior=queue)` 降级路径的 request shape 不一致

- **Evidence**: design.md §10 `SubmitFollowupRequest` 不含 `execution_target`，但 §11 规定 "当前 Session 没有 active Run 时，follow-up 可按普通 `start_run` 语义创建新 Run"。`StartRunRequest` 包含 `execution_target` 和 `queue_policy`。
- **Risk**: Phase plan agent 在拆解 Public API phase 时，需要自行决定 followup-queue 降级为 start_run 时 `execution_target` 的来源——从 Session 默认派生？从 Service 层传入？从上次 Run 继承？设计未指定，存在猜测空间。
- **Recommendation**: 在 Public API phase discussion 中明确：`submit_followup(behavior=queue)` 降级为 start_run 时，`execution_target` 的默认来源规则。建议在 `SubmitFollowupRequest` 中加入 optional `execution_target`，或明确降级时由 Host policy 决定默认 target。不阻塞 phase 编排，但必须在对应 phase plan 前裁决。

#### H2. Memory snapshot 的 atomic commit marker 语义为 v1 引入过度复杂性

- **Evidence**: design.md §23 定义了不在同一 SQLite transaction 内时 memory snapshot 的 "atomic commit marker" 机制，包含 "snapshot content / artifact 必须先 durable 并可按 digest 校验，随后才能提交覆盖该 snapshot 的 checkpoint" 等细粒度语义。
- **Risk**: 对于 v1，memory projection 完全可以与 EventLog 位于同一 SQLite 进程内，直接在同一事务中提交 snapshot + checkpoint。引入跨存储的 atomic commit marker 增加了设计复杂度、测试矩阵和实现风险，同时带来的价值（memory 独立存储）在 v1 并不需要。
- **Recommendation**: v1 将 memory projection 约束为与 EventLog 同 SQLite transaction 提交，简化 atomicity 语义。跨存储的 atomic commit marker 作为 deferred capability 写入 implementation-control 追踪区。不阻塞 phase 编排，但 Memory phase plan 必须据此简化。

#### H3. ToolRuntime accept barrier 在远程执行下的延迟模型未讨论

- **Evidence**: design.md §17 规定 ToolRuntime 必须走 Host accept barrier：工具结果先提交 Host durable accept，收到 ack 后才能返回 Engine。§16 规定 LocalProxy 与 RemoteProxy 语义一致，RemoteProxy "通过等价远程请求 / ack 语义表达"。
- **Risk**: 在远程执行场景下，每次工具调用增加一次 Host 往返延迟。对于需要多次工具调用的 Run，总延迟可能显著。设计未讨论 batching accept、pipeline accept 或 async pre-accept 等优化策略。虽然没有正确的替代方案（绕过 accept barrier 是架构违规），但 phase plan agent 面对远程场景时可能倾向于"优化掉" barrier。
- **Recommendation**: 在 WorkerProxy / RemoteProxy phase discussion 中，显式声明 accept barrier 是不可妥协的架构约束，同时允许 phase design 讨论 batching accept 等不绕过 barrier 的延迟优化策略。在 implementation-control 中增加一项：远程 ToolRuntime 不得以延迟为由绕过 Host accept barrier。

---

### Medium

#### M1. `retry_run` 与 `replay_run` 对非标准 Run 状态的前置条件未穷举

- **Evidence**: design.md §8.1 状态迁移表定义 `retry(run)` 前置条件为 "Run FAILED 或 recoverable failure"，`replay(run)` 前置条件为 "Run SUCCEEDED 且 final answer 格式 / schema / 结构需修复"。以下状态组合未明确：
  - `retry_run` 对 `LOST` Run 的行为
  - `retry_run` 对 `RECOVERING` Run 的行为
  - `replay_run` 对 `FAILED` 但 final answer 格式也不对的 Run 的行为
- **Risk**: 低——`LOST` 的语义是 "治理无法恢复或无法确认"，不应支持 retry；`RECOVERING` 不是终态，不应 retry；`FAILED` 无 final answer 则 replay 无意义。但这些推断应显式化，避免 phase agent 自行发明行为。
- **Recommendation**: 在 Retry / Replay phase discussion 中补齐前置条件矩阵。推荐：`retry_run` 仅在 Run 为 `FAILED` 或符合 retry policy 的 recoverable failure 时接受；`replay_run` 仅在 Run 为 `SUCCEEDED` 时接受；其余状态返回 `invalid_state`。

#### M2. Canonical event 类型数量偏高（28 types），部分可合并

- **Evidence**: design.md §12.2 定义 28 种 canonical event。其中 `TOOL_RESULT_ACCEPTED` 与 `TOOL_TERMINAL_RESULT` 语义相近（后者仅表达等待解决后的 terminal result），`RUN_ACCEPTED` / `RUN_QUEUED` / `RUN_STARTED` 三者在 admission 路径中紧密耦合。
- **Risk**: 低——设计明确拒绝模糊 `RUN_TERMINAL` 作为唯一类型，这是正确的审计导向设计。但 28 种 event type 增加了 EventLog schema、ingest 分类逻辑和测试矩阵的规模。phase plan agent 可能倾向于进一步拆分，导致 event type 膨胀。
- **Recommendation**: 当前 28 种可接受，但应在 EventLog phase discussion 中做一次显式的 "event type 必要性审核"：每种 type 是否回答了一个不同的问题（审计问题、恢复问题、UI 展示问题）？若两种 type 回答同一问题且仅 payload 不同，应合并 type 并在 payload 中区分。

#### M3. EngineEvent stream 非正常终止的即时处理路径缺失

- **Evidence**: design.md §16 定义了 EngineEvent stream 的 ingest 路径（验证 → 分类 → append），§26 定义了 crash recovery scan。但 EngineWorker 在运行中崩溃、RemoteProxy 断连、或 EngineEvent stream 中途结束（未发出 terminal event）时的即时反应路径未描述。当前唯一覆盖是 Host 重启后的 recovery scan。
- **Risk**: 中——如果 EngineEvent stream 中途断开（例如远端 worker 进程被 kill），Host 当前 Attem 处于 `RUNNING` 但不再收到事件。如果没有 stream-level 的超时或 close 检测，该 Attempt 会一直处于 `RUNNING` 直到下次 Host 重启 recovery scan。这会导致 Session active slot 被无效占用。
- **Recommendation**: 在 WorkerProxy phase discussion 中补充 stream-liveness 检测语义：EngineEvent stream 关闭（EOF / error / timeout）但无 terminal event 时，Host 应记录 diagnostic、将 Attempt 收口为疑似丢失，并触发 Run 状态评估（`RECOVERING` 或 `LOST`）。不需要完整的 stream health check 协议，但至少定义 stream close-without-terminal 的收口路径。

#### M4. `HostPolicyProviderSet` 与 service locator 的边界在实现中容易模糊

- **Evidence**: design.md §9.1 定义 `HostPolicyProviderSet` 是一组 typed policy providers，并反复强调它不是 service locator、不是 god bag。但 policy resolution path（ProviderSet → command path resolve → typed policy view → subsystem）在实际代码中容易退化为 subsystem 通过字符串 key 或类型查询反查 ProviderSet。
- **Risk**: 中——设计文档的"不是 service locator"是声明而非机制。如果 phase agent 在实现时将 ProviderSet 作为全局可访问对象传入子系统，subsystem 就能绕过 typed view 约束直接查询任意 policy。这不会破坏正确性，但会破坏模块边界和可测试性。
- **Recommendation**: 在 Host Composition Root phase discussion 中，明确 ProviderSet 的注入边界：子系统构造函数只接收已解析的 typed policy view / immutable snapshot ref，不接收 ProviderSet 本身。将此约束写入 phase plan 的模块接口规范中。

#### M5. `close_session` 对 `QUEUED` Run 的语义矛盾

- **Evidence**: design.md §4 规定 CLOSED Session 下 "close 前已 durable accepted 的 QUEUED Run 继续保留，并可在 active slot 释放后 promotion"。但同时 `start_run` 和 `submit_followup` 在 CLOSED Session 被拒绝。
- **Risk**: 低——这其实是正确的语义（close 不删除已有 queue），但需要澄清一个边缘情况：如果所有 active Run 都终态且 Session 已 CLOSED，promotion 是否仍会触发？如果 promotion 触发并创建新 Attempt，这相当于在已关闭的 Session 中启动了新的执行，与 "close 不取消已有工作" 的语义一致，但可能与用户直觉 "关闭后不应再有新活动" 冲突。
- **Recommendation**: 在 Session / Public API phase discussion 中明确：CLOSED Session 下，queue promotion 在 active slot 释放后仍然触发；这是 "close 不等于 cancel" 的自然结果。如果用户希望停止所有未来工作，应先 cancel queued Run 再 close Session。UI / Service 应在 close 时提示或提供 "cancel all queued then close" 的复合操作。

---

### Low

#### L1. `purge_session` tombstone 的具体字段未指定

- **Evidence**: design.md §4 规定 purge 保留 "最小 purge tombstone / audit record" 但仅列出概念字段。
- **Risk**: 低——Storage phase 会细化。当前不影响 phase 编排。
- **Recommendation**: Storage phase discussion 时补齐。

#### L2. Outbox item 的 idempotency key 派生规则留白

- **Evidence**: design.md §15 规定 "outbox item idempotency key 必须由 terminal event identity 派生" 但未给派生算法。
- **Risk**: 低——Projection / Sink phase 会细化。
- **Recommendation**: Outbox phase discussion 时给出确定性派生规则。

#### L3. Context governance proactive trigger 的 budget estimation gap

- **Evidence**: design.md §24 规定 Host 使用 "provider-aware context budget policy"，但承认没有 provider tokenizer adapter 时只能使用 "保守 token estimator"。
- **Risk**: 低——保守估计 + safety margin + reactive fallback 是合理的渐进策略。但如果保守估计与实际 token 计数偏差过大，可能导致频繁 reactive compaction，在 v1 生产场景中表现为不必要的重试和延迟。
- **Recommendation**: Context Governance phase 应评估是否需要至少一个 provider tokenizer adapter（如 tiktoken for OpenAI）作为 v1 能力，或接受保守估计带来的重试开销。

---

## Over-coupling / Over-engineering Findings

### OE1. RunInputBuilder 的 7 个 typed input provider protocols

- **Evidence**: design.md §22 定义 `CurrentRunFactProvider`、`SessionContinuityProvider`、`MemorySnapshotProvider`、`CompactArtifactProvider`、`ToolSchemaSnapshotProvider`、`SceneParameterProvider`、`PolicySnapshotProvider` 共 7 个 provider protocol。
- **Assessment**: 对于 v1，大部分 provider 读取的是同一 SQLite EventLog。`CurrentRunFactProvider` 和 `SessionContinuityProvider` 均可通过 "EventLog cursor range + filter" 实现，拆成两个独立 protocol 增加了接口数量但未增加语义独立性。建议 v1 合并为 `EventLogFactProvider(run_id, cursor_range)` + `MemorySnapshotProvider` + `SceneParameterProvider` 三个 protocol，其余在需要时拆分。
- **Severity**: Low — 不影响正确性，但增加了 phase agent 需要实现的接口数量。

### OE2. Memory atomic commit marker 跨存储机制

- **Evidence**: design.md §23 定义 memory snapshot 不在同一 SQLite transaction 时的 atomic commit marker。
- **Assessment**: 已在高优 H2 中分析。v1 不需要此机制——将其纳入 deferred capability 而非当前设计。
- **Severity**: High — 见 H2。

### OE3. `HostPolicyProviderSet` → typed view → subsystem 的三层 policy 解析

- **Evidence**: design.md §9.1 定义 policy resolution path 为 ProviderSet → command path resolution → typed policy view → subsystem。
- **Assessment**: 三层解析提供了良好的边界和可测试性，但对于 v1 的策略数量（~7 个 policy），可以在不牺牲边界的前提下简化为两层：ProviderSet 在构造时预解析为 immutable policy snapshot，command path 和 subsystem 直接消费 snapshot。中间 "command path resolves" 步骤增加了调用链长度但未增加新的类型安全性。
- **Severity**: Low — 当前设计已提供足够的边界防护，三层 vs 两层是实现偏好，不构成设计问题。

---

## Phase Readiness Gaps

### PRG1. Engine Context Compaction Event 语义前置依赖

- **Evidence**: implementation-control.md 追踪区 "Engine Context Compaction Event 语义前置" 明确：Context Governance phase 依赖 Engine cleanup work unit 完成，或 plan 中写明临时兼容假设。
- **Gap**: implementation-control.md 未明确 Context Governance phase 的 phase ordering——它必须在 Engine cleanup 之后，还是可以并行启动（带兼容假设）？
- **Recommendation**: 在 phase 编排前增加显式的 phase dependency declaration。推荐 Context Governance phase 在 Engine cleanup 完成后启动，避免 plan 中包含临时兼容假设。

### PRG2. Phase 依赖图缺失

- **Evidence**: implementation-control.md 描述了工作流和各 phase 的追踪项，但未提供 phase 间的依赖图或推荐顺序。
- **Gap**: Phase plan agent 需要知道哪些 phase 必须先完成才能启动下一个。例如 Storage / Durable Store phase 几乎是所有 phase 的前置；Public API phase 依赖状态机 phase 的 Run/Attempt 迁移已确定。
- **Recommendation**: 在进入 phase 编排前，在 implementation-control.md 中增加 phase dependency graph。最小建议顺序：
  ```
  Storage / Durable Store → State Machine → Public API
  Storage / Durable Store → EventLog → Observer/Sink → Projection/Outbox
  Public API + WorkerProxy → ToolRuntime
  Public API + ToolRuntime → Recovery
  Public API → Context Governance
  All above → Integration / Cross-cutting
  ```

### PRG3. `submit_followup` request shape 的 `execution_target` 缺位

- **Evidence**: 见 H1。
- **Gap**: Public API phase plan 需要裁决此字段的默认来源规则。
- **Recommendation**: Public API phase discussion 的首要议题之一。

---

## Residual Risks for Implementation-Control

以下风险应在 implementation-control.md 追踪区中已有对应项或应新增：

### Already tracked (确认覆盖):

| Risk | implementation-control 追踪区 |
|---|---|
| Engine Context Compaction Event 语义前置 | 已追踪，含前置步骤和 Phase 依赖 |
| External Job Cancel Adapter 能力 | 已追踪，含 wait record cancelled 后适配器行为 |
| Tool Trace / Provider Request 排错 | 已追踪，含 provider_request_id 在热/冷层记录 |
| SQLite 多进程写入正确性验证 | 已追踪，含 WAL/busy timeout/CAS 验证要求 |
| Remote 物理执行 exactly-once 非目标 | 已追踪，含迟到事件拒绝和工具级幂等 |
| Session Purge / Archive | 已追踪，含 purge 前置条件和 archive deferred |
| Host 跨层测试策略 | 已追踪，含各 phase 测试覆盖要求 |
| UI / Service Outbox 去重边界 | 已追踪，含 terminal identity 和 seen cursor |

### Suggested additions:

#### RR-NEW-1. EngineEvent stream 非正常终止的即时收口

- **Risk**: EngineWorker 崩溃 / RemoteProxy 断连 / stream 中途关闭但无 terminal event 时，Attempt 保持 `RUNNING`，Session active slot 被无效占用，直到下次 Host 重启 recovery scan。
- **Recommendation**: 在 WorkerProxy phase 中定义 stream close-without-terminal 的即时收口路径。不要求复杂的 health check 协议，但需要 stream EOF/error → Attempt 评估的路径。
- **归属**: WorkerProxy / RemoteProxy phase。

#### RR-NEW-2. Provider tokenizer adapter gap 对 proactive compaction 的影响

- **Risk**: 没有 provider tokenizer adapter 时，保守 token estimator 可能与实际 token 计数偏差较大，导致频繁 reactive compaction 或过早 proactive compaction。
- **Recommendation**: Context Governance phase discussion 评估 v1 是否引入至少一个 tokenizer adapter（如 tiktoken），或明确接受保守估计的重试开销并定义降级策略。
- **归属**: Context Governance phase。

#### RR-NEW-3. Canonical event type 必要性审核

- **Evidence**: 见 M2。
- **Risk**: 28 种 canonical event type 中可能存在可合并项。在实现前未审核会导致 EventLog schema、ingest 分类逻辑和测试矩阵超出必要规模。
- **Recommendation**: EventLog phase discussion 中做一次显式审核。
- **归属**: EventLog phase。

---

## Summary

| Category | Count |
|---|---|
| Blocker | 0 |
| High | 3 |
| Medium | 5 |
| Low | 3 |
| Over-coupling/Over-engineering | 3 |
| Phase readiness gaps | 3 |
| New residual risks | 3 |

The design document is architecturally sound. All P0 issues from the v2 controller adjudication have been successfully resolved. The semantic contracts for state machines, admission, recovery, remote execution, EventLog, outbox, memory, and context governance are clear enough for phase plan agents to produce implementation-ready plans without guessing at architectural intent.

The non-blocking findings above are phase-level refinements that fall squarely within the intended design→phase discussion→phase plan workflow described in implementation-control.md.
