# Host Discussion Note 设计就绪性 Adversarial Review

## 元信息

- **reviewer**: MiMo (adversarial review)
- **date**: 2026-05-12
- **gate**: pre-design readiness review
- **target**: `docs/host/discussion-note.md` + `docs/host/implementation-control.md`
- **scope**: 挑战 discussion-note 是否足够 ready 用来生成新的 `docs/host/design.md`，并按 implementation-control 推进后续 phase
- **排除**: `docs/host/design.md` 是即将被删除并重写的旧文件，不作为本次 review 的设计真源。本 review 只以 discussion-note 和 implementation-control 为判断基础。

## 结论摘要

**总体判定：通过，存在 1 个 high finding 和 6 个 medium finding。无 blocking finding。**

discussion-note 在架构边界、EventLog 真源、Session/Run/Attempt 生命周期、取消治理和 memory 原则方面有扎实且自洽的思考，覆盖了 Host 设计的核心概念空间。主要风险不在架构正确性，而在以下两点：

1. **第一版与后续能力的边界模糊**：steer、guidance、context governance 完整版、long-term memory 等能力混在"已吸收需求"中，未显式区分哪些进入第一版 design.md、哪些只做设计预留。
2. **若干关键设计决策尚未收敛**：EngineEvent 到 canonical Event 的翻译规则、session slot 持久化规格、context governance 预算分配等。

这些 gap 不阻塞 design.md 生成，但 design.md 生成过程中需要逐一做出决策。建议在进入 design.md 生成前，先用一轮简短讨论确认第一版 scope boundary。

---

## Controller 状态标注（2026-05-12）

本 pre-design readiness review 已完成归属裁决；其 finding 已吸收到 `docs/host/design.md`、`docs/host/implementation-control.md` 或后续 phase 讨论边界中。
下方原始严重度、blocking/high 标记和修正建议保留为 review-time 记录；后续 plan / implementation 以本节状态为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| Finding-1 第一版与后续能力边界 | 已吸收 | `design.md` 已区分核心架构、第一版实现范围、后续 phase 细化项；总控文档规定每个 phase 先讨论细化 design。 |
| Finding-2 EngineEvent 到 canonical EventLog 翻译 | 已吸收 | `design.md` 已定义 RunnerEvent -> EventLog 的治理边界、canonical/projection/diagnostic 分类和压缩事件响应。 |
| Finding-3 Session Slot 持久化与并发 | 已吸收 | `design.md` 已拆分 `create_session` / `ensure_session`，并明确 slot 归属、幂等和多进程并发约束。 |
| Finding-4 Context Governance 范围 | 已吸收到架构级 | `design.md` 定义 Host 负责 compact 响应与上下文治理；预算参数与具体策略留到 memory / context phase。 |
| Finding-5 Guidance 语义 | 已吸收到架构级 | `design.md` 已把 guidance 纳入 Host 管控输入、EventLog 和 RunInputBuilder 边界；具体策略留到对应 phase。 |
| Finding-6 Cancel 治理开放项 | 已吸收 | `design.md` 已明确 terminal 优先、queued cancel、LOST / RECOVERABLE_LOST、重启恢复和 watchdog 延后边界。 |
| Finding-7 Memory 结构表述 | 已吸收 | `design.md` 已按财报 Agent 第一性原理定义 memory、长期记忆、事实来源和 query-time retrieval 边界。 |
| Finding-8 RemoteProxy wire protocol | 已吸收 / 后移 | `design.md` 已明确 Remote semantic contract；具体 RPC、ack、replay、heartbeat 属于 Remote phase，不作为当前 blocker。 |

---

## Finding 列表

### Finding-1: "已吸收需求"中第一版与后续能力的边界未显式区分

**严重程度**: HIGH

**位置**: `discussion-note.md` "已吸收需求主题" 节（L22-L32）

**当前写法**:

"已吸收需求主题"列出 10 个主题，全部以相同权重呈现：

```text
- 取消治理：Host 是取消真源...
- 等待协作：Engine 可以产出 ToolAwaitingOutcome...
- 工具结果截断与续读：Host / ToolRuntime 需要内置 TruncationManager...
- Run-time guidance：Host 需要支持在当前 run 内插入 guidance...
- Follow-up / Steer：Host 需要支持 run 运行中接收用户后续输入...
- 多轮会话记忆：记忆系统从财报 Agent 的会话不变量出发...
- Context governance：Host 负责 provider-aware context budget...
- EventLog projection：EventLog 需要 Observer / Sink 机制...
- 长期 memory governance：...不阻塞第一版，但设计不能封死。
- 弱信号证据链：...Host 保持业务中立...
```

其中只有"长期 memory governance"显式标注"不阻塞第一版"。其余 9 个主题没有标注优先级。

**为什么有问题**:

1. **steer 的优先级不明**："Follow-up / Steer"在"已吸收需求"中，但文中另一处（L343-L345）又说"steer 不破坏同一 session active run admission...queue 与 steer 的选择来自上层 UI / Service"。design.md 生成时无法判断 steer 是第一版必须实现的能力，还是只做状态机和 EventLog 预留。

2. **guidance 的优先级不明**："Run-time guidance"在"已吸收需求"中，但它的 EventLog 语义（是否成为 canonical fact）尚未决定（L582），与 context compaction 的交互也未定义。如果 guidance 是第一版能力，它需要完整的 EventLog 和 RunInputBuilder 设计。如果只是预留，design.md 只需留插入位。

3. **context governance 的范围矛盾**：L816 说"第一版设计应一步到位覆盖完整治理范围"，但 L800-L813 列出的参数（`memory_token_budget_ratio`、`compaction_trigger_context_ratio` 等）说"具体默认值属于 memory 实施阶段决策"。"一步到位"与"留到实施阶段"矛盾。

4. **cancel 治理的范围不明**：L690-L717 列出 6 个"需要继续讨论"的问题（watchdog timeout、LOST 升级、RemoteProxy cancel 消息等），但没有给出 working assumption。design.md 生成时，如果 cancel 是第一版能力，这些问题是 blocking decision；如果 cancel 增强后移，只需写最小规格。

**影响**: design.md 生成时，如果无法区分第一版 scope，会导致两种风险：(a) 设计过度——为后移能力写了完整规格，浪费设计精力；(b) 设计不足——假设某能力后移但实际需要第一版支撑。

**建议改法**:

在 discussion-note 中为每个"已吸收需求"主题标注优先级：

```text
第一版必须: EventLog、取消治理（最小版本）、等待协作（最小版本）、Conversation Memory、
           工具截断与续读、context governance（最小版本）
第一版预留: steer、guidance、session slot
后续演进:   长期 memory governance、弱信号证据链、context governance 完整版
```

每个主题的标注应附带一句话说明"第一版做什么"和"第一版不做什么"。

**是否阻塞 design.md 生成**: 否，但强烈建议在进入 design.md 生成前确认。如果跳过，design.md 生成过程中需要自行做 scope 判断，可能与用户预期不一致。

---

### Finding-2: EngineEvent 到 Canonical EventLog Event 的翻译规则缺失

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "Canonical EventLog 最小分类" 节（L417-L473），"EventLog Observer / Sink 讨论入口" 节（L347-L398）

**当前写法**:

discussion-note 列出了 canonical facts 分类：

```text
SESSION_CREATED, SESSION_CLOSED
RUN_ACCEPTED, RUN_QUEUED, RUN_STARTED, RUN_WAITING, RUN_CANCELLING, RUN_TERMINAL
ATTEMPT_STARTED, ATTEMPT_EVENT_ACCEPTED, ATTEMPT_TERMINAL
USER_INPUT_ACCEPTED, FOLLOWUP_QUEUED, STEER_REQUESTED, CANCEL_REQUESTED, RESUME_REQUESTED
TOOL_RESULT_ACCEPTED, TOOL_AWAITING, TOOL_TERMINAL_RESULT, GUIDANCE_INSERTED
```

同时在 L419-L420 定义了判定标准："canonical facts 的判定标准：它是否参与状态恢复、resume 输入重建、memory projection、audit 责任链或治理决策。"

**为什么有问题**:

1. **Engine 产出 18 种 EngineEventType**（从 `dayu/engine/contracts/engine_events.py` 可确认：`ITERATION_STARTED`、`CONTENT_DELTA`、`REASONING_DELTA`、`CONTENT_COMPLETED`、`TOOL_CALL_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE`、`TOOL_AWAITING`、`CONTEXT_COMPACTION_REQUESTED`、`USAGE_REPORTED`、`PROVIDER_PROTOCOL_ERROR`、`ITERATION_COMPLETED`、`FINAL_ANSWER`、`RUN_SUSPENDED`、`RUN_CANCELLED`、`RUN_FAILED`）。discussion-note 的 canonical 列表中没有 `ITERATION_STARTED`、`CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE`、`USAGE_REPORTED`、`PROVIDER_PROTOCOL_ERROR`、`ITERATION_COMPLETED` 等类型。**哪些 EngineEvent 翻译为 canonical event？哪些只作为 preview event？翻译规则未定义。**

2. **`ATTEMPT_EVENT_ACCEPTED` 语义不明**：这个 canonical event 类型在 discussion-note 中没有定义说明。它与 `TOOL_RESULT_ACCEPTED` 的关系不清楚——是否 `TOOL_RESULT_ACCEPTED` 是 `ATTEMPT_EVENT_ACCEPTED` 的子类型？

3. **`RUN_TERMINAL` 过于粗糙**：Run 的终态有 SUCCEEDED、FAILED、CANCELLED、LOST 四种。discussion-note 使用单一 `RUN_TERMINAL`，是否需要拆分为独立终态事件？如果不拆分，payload 中如何区分终态类型？

4. **Engine 的 `FINAL_ANSWER` 如何映射**：Engine 产出 `FINAL_ANSWER` 事件（含 content、filtered、degraded、finish_reason），它是否直接映射为某个 canonical event？还是 Host 先创建 Run 终态事件，再由 projection 从终态事件提取 final answer？

**影响**: EventLog 事件分类是 Host 持久化、恢复、memory projection 和 audit 的基础。翻译规则不明确会导致：EventLog schema 无法确定；canonical/preview 边界无法实施；Observer 消费规则无法定义。

**建议改法**:

在 discussion-note 中补充一个 EngineEvent -> Canonical/Preview 映射表，至少覆盖：

```text
EngineEvent                    -> Canonical or Preview
ITERATION_STARTED              -> preview
CONTENT_DELTA                  -> preview
REASONING_DELTA                -> preview
CONTENT_COMPLETED              -> preview
TOOL_CALL_DELTA                -> preview
TOOL_CALLS_BATCH_READY         -> preview (或 canonical 取决于是否需要恢复)
TOOL_CALL_REQUESTED            -> canonical (参与恢复和 audit)
TOOL_RESULT_ACCEPTED           -> canonical
TOOL_CALLS_BATCH_DONE          -> preview (汇总信号，可从 TOOL_RESULT_ACCEPTED 重建)
TOOL_AWAITING                  -> canonical
CONTEXT_COMPACTION_REQUESTED   -> canonical
USAGE_REPORTED                 -> canonical (audit) 或 preview (可重建)
PROVIDER_PROTOCOL_ERROR        -> canonical
ITERATION_COMPLETED            -> preview (可从 terminal 事件重建)
FINAL_ANSWER                   -> canonical (参与 memory projection 和 resume)
RUN_SUSPENDED                  -> canonical
RUN_CANCELLED                  -> canonical
RUN_FAILED                     -> canonical
```

**是否阻塞 design.md 生成**: 否。design.md 生成时可以基于 discussion-note 的判定标准（"是否参与恢复/resume/memory/audit/governance"）推导映射表。但如果有现成映射，design.md 生成会更高效。

---

### Finding-3: Session Slot 的持久化与并发规格缺失

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "Session Slot" 节（L97-L122）

**当前写法**:

```text
CreateSessionRequest:
  scope
  slot_key
  create_policy: reuse | new
  metadata

语义：
- (scope, slot_key) 唯一映射到一个当前 session。
- create_policy=reuse 时，重复 create_session(scope, slot_key) 返回同一个当前 session。
- create_policy=new 时，Host 创建新 session，并把该 (scope, slot_key) 重新指向新 session。
```

**为什么有问题**:

1. **持久化规格缺失**：`(scope, slot_key)` 到 `session_id` 的映射存储在哪里？是独立表还是 Session 表的索引？`create_policy=new` 时旧映射是物理删除还是逻辑标记？如果逻辑标记，查询"当前 session"的条件是什么？

2. **并发竞态未定义**：两个进程同时 `create_session(scope, slot_key, reuse)` 时，是否需要行级锁或 CAS？两个进程同时 `create_session(scope, slot_key, new)` 时，旧映射的 rebind 如何保证原子性？

3. **scope 的语义边界模糊**：L121 说"scope 是入口或身份命名空间"，L122 说"Host 不把 session slot 当成权限模型"。那么 scope 除了作为命名空间前缀，还有什么实际作用？如果只是命名空间前缀，为什么不用 `session_id` 的命名约定（例如 `wechat:user123`）来表达？

**影响**: session slot 是 `create_session` 接口的核心参数。持久化规格和并发规则不明确，design.md 中 Session 创建路径的 schema 和幂等语义无法确定。

**建议改法**:

1. 明确 session slot 的持久化方式：独立 `session_slot` 表 vs Session 表索引。
2. 定义并发 `create_session` 的竞态处理：行锁 + INSERT OR IGNORE / UPSERT / CAS。
3. 说明 scope 相对于 `session_id` 命名约定的增量价值。

**是否阻塞 design.md 生成**: 否。design.md 可以基于 discussion-note 的语义描述推导 schema 和并发规则。但如果 discussion-note 已有具体方案，design.md 生成会更准确。

---

### Finding-4: Context Governance 的"一步到位"与参数"留到实施阶段"矛盾

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "Context governance" 节（L815-L823），"参数与策略" 节（L799-L813）

**当前写法**:

L816:

```text
Context governance 是生产级财报 Agent 的必要能力，第一版设计应一步到位覆盖完整治理范围
```

L800-L813:

```text
Memory 参数需要从财报场景重新论证，但具体默认值属于 memory 实施阶段决策：
- memory_token_budget_ratio：历史池占模型窗口比例。
- memory_token_budget_floor：短窗口模型下的最低连续性预算。
...
这些参数需要通过财报场景目标来定。长窗口模型下 cap 应选择 32K、48K、60K 还是其它值，
compaction trigger 应偏早保护财报材料空间还是偏晚减少额外成本，都留到 memory 实施计划中结合测试与样例决定。
```

**为什么有问题**:

1. "一步到位覆盖完整治理范围"暗示第一版 design.md 需要包含 context governance 的所有子系统：provider-aware budget、RunInputBuilder 预算分配、compact 触发、LLM episode summary compaction、pinned_state patch、保真检查、retry policy、context overflow retry、compact event、trace、audit projection。

2. 但参数表明确说"具体默认值属于 memory 实施阶段决策"，并且承认参数值需要"结合测试与样例决定"。

3. 这造成 design.md 的两难：如果"一步到位"，design.md 需要为所有子系统写出完整规格（包括参数值）；如果参数"留到实施阶段"，design.md 只能写结构和规则框架，参数值写"待定"。

**影响**: context governance 是 Conversation Memory 的核心依赖。如果 design.md 中预算分配规则不明确，RunInputBuilder 的 token 竞争和 compaction 触发条件无法确定。

**建议改法**:

将 L816 修改为更精确的表述，区分"设计覆盖范围"和"实施落地范围"：

```text
Context governance 的设计必须覆盖完整治理范围（budget policy、RunInputBuilder 预算分配、
compact 触发、episode summary compaction、pinned_state patch、保真检查、retry policy、
trace、audit projection），但各子系统的实施优先级和参数默认值由对应 phase 决定。
第一版实施优先级：budget policy > compact 触发 > 保真检查 > retry policy > 其它。
```

**是否阻塞 design.md 生成**: 否。design.md 生成时可以自行区分"设计规格"和"实施参数"。但明确表述可以避免 design.md 生成时的 scope 判断歧义。

---

### Finding-5: Guidance 的 EventLog 语义和第一版归属未决定

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "Run-time Guidance 讨论入口" 节（L563-L585）

**当前写法**:

L582:

```text
guidance 应作为 Host-governed input artifact 进入当前 run，可被 EventLog / tool trace / audit 观察；
是否成为 canonical fact 需要在 EventLog taxonomy 中明确。
```

**为什么有问题**:

1. **canonical fact 状态未决定**：guidance 是否进入 canonical EventLog 是一个关键设计决策。如果进入，RunInputBuilder 需要在 crash recovery 后重建 guidance（因为它改变了 `AgentRunRequest.messages`）。如果不进入，guidance 只是运行时内存态注入，crash 后丢失。

2. **在 `AgentRunRequest.messages` 中的 role 未定义**：discussion-note 说"Engine 只消费构造好的 messages"，但 guidance 作为 message 的 role 是什么？system？还是特殊的 Host 注入标记？

3. **与 context compaction 的交互未定义**：如果 guidance 插入后触发 context compaction，compaction 算法是否保留 guidance？guidance 的优先级高于还是低于 tool fact？

4. **第一版归属不明**：guidance 在"已吸收需求"中，但 EventLog 语义尚未决定。如果 guidance 是第一版能力，它需要完整的 EventLog 和 RunInputBuilder 设计。如果只是预留，design.md 只需在 RunInputBuilder 中留插入位。

**影响**: guidance 影响 RunInputBuilder 的消息构造、EventLog 的事件分类和 crash recovery 的重建逻辑。

**建议改法**:

1. 决定 guidance 是否进入第一版。如果后加，在"已吸收需求"中标注"第一版预留"。
2. 如果进入第一版，决定 canonical fact 状态、message role 和 compaction 优先级。
3. 如果后加，明确 design.md 只需在 RunInputBuilder 中预留 guidance message 插入位。

**是否阻塞 design.md 生成**: 否。design.md 可以将 guidance 标记为"预留"，只在 RunInputBuilder 中留插入位。

---

### Finding-6: Cancel 治理的 6 个开放问题缺乏 working assumption

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "Cancel 讨论入口" 节（L690-L717）

**当前写法**:

L709-L717:

```text
取消治理需要继续讨论：
- QUEUED 且尚未创建 attempt 的 run 是否直接 CANCELLED。
- RUNNING 进入 CANCELLING 后 watchdog 的 timeout 边界。
- timeout 后升级为 LOST、强制终止执行环境、后台 job reconcile 或其它结构化终态的条件。
- RemoteProxy / RemoteStub 取消控制消息需要携带哪些 id。
- 工具等待、SSE、后台 job 在取消路径中如何暴露可观测事实。
- 取消超时、强制终止、资源收口失败应写入哪些 canonical EventLog facts。
```

**为什么有问题**:

1. 这 6 个问题全部标记为"需要继续讨论"，但没有给出 working assumption。design.md 生成时如果遇到这些问题，无法判断是写具体规格还是写"待定"。

2. **QUEUED run 取消**：这个问题的答案直接影响 Run 状态机的迁移规则。如果 `QUEUED` 直接 `CANCELLED`，Run 状态机需要这条迁移路径。如果需要先创建 attempt 再取消，迁移路径不同。

3. **watchdog timeout**：如果 timeout 是可配置的，design.md 需要定义配置接口。如果是固定值，design.md 需要给出默认值。如果是"后移"，design.md 只需在状态机中标注 `CANCELLING -> LOST` 的迁移条件为"超时后由 policy 决定"。

4. **与第一版 scope 的关系**：如果 cancel 增强（watchdog、强制终止、后台 job reconcile）后移，第一版 cancel 的最小可用规格是什么？discussion-note 的初始取消路径（L696-L707）已经给出了基本流程，但超时和异常路径未覆盖。

**影响**: cancel 治理是 Host 核心能力，影响 Run 状态机迁移规则和 EventLog 事件分类。

**建议改法**:

为每个开放问题给出 working assumption，至少标注"第一版假设"：

```text
- QUEUED run 取消：第一版假设直接 CANCELLED，不创建 attempt。
- watchdog timeout：第一版假设固定超时（如 30s），超时后 Run 进入 LOST。
- timeout 升级：第一版假设只标记 LOST，不做强制终止。强制终止后移。
- RemoteProxy cancel id：第一版假设携带 (run_id, attempt_id, execution_id)。
- 工具等待取消：第一版假设 cancel 直接传播到 ToolExecutor，不做细粒度 job 取消。
- 超时 EventLog facts：第一版假设追加 CANCEL_REQUESTED + RUN_TERMINAL(LOST)。
```

**是否阻塞 design.md 生成**: 否。design.md 可以基于初始取消路径（L696-L707）写最小规格，将超时和异常路径标注为"后续增强"。但有 working assumption 会让 design.md 更准确。

---

### Finding-7: Memory 结构的两层描述与分层竞争规则的表述需要统一

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "基本结构" 节（L733-L757），"Conversation Memory 讨论入口" 整节（L719-L846）

**当前写法**:

L733-L746:

```text
Conversation Memory 分为稳定层与历史池：
  -> stable layer
      -> pinned_state
      -> tool-verified facts
      -> assumptions / open questions
      -> evidence anchors / tool facts
  -> history pool
      -> recent raw turns floor
      -> older raw turns
      -> episode summaries
```

L754:

```text
pinned_state 与 tool-verified stable facts 应全量注入，不参与历史池预算竞争。
```

**为什么有问题**:

1. **"稳定层 + 历史池"的两层描述是正确的高层抽象**，但 L754 提到"不参与历史池预算竞争"时，隐含了存在预算竞争机制。竞争规则是什么？是简单的 token 预算截断，还是带 ranking 的候选选择？

2. **recent raw turns floor 的"保底"语义需要更精确**：L755 说"最近 N 轮是反退化下限保底"，但 N 是固定值还是可配置？如果最近一轮的 raw turn 本身超过预算上限，是截断该轮还是保留完整？

3. **"历史池"内部的竞争优先级未定义**：older raw turns、episode summaries、tool-verified facts（如果超出 stable layer 预算时）在同一历史池中竞争，优先级规则是什么？

4. **与 context governance 的关系**：memory 的 token 预算是 context governance 的一部分。如果 context governance 的预算分配规则未确定（Finding-4），memory 的 token 竞争也无法确定。

**影响**: memory 结构是 RunInputBuilder 的核心设计。分层和竞争规则不明确，RunInputBuilder 的预算分配算法无法确定。

**建议改法**:

在 discussion-note 中补充 memory 预算消费的最小规则：

```text
预算消费顺序：
1. stable layer 全量渲染，不扣 history pool budget，但计入总上下文估算。
2. recent raw turns 至少保留 N 轮语义代表（N 为可配置参数，建议默认 3）。
3. evidence anchors / tool summaries 与 older raw turns 在历史池中按相关性排序竞争。
4. episode summaries 使用剩余预算。
5. 超大 raw turn 降级为 intent / final summary / anchors，不全文保留。
```

**是否阻塞 design.md 生成**: 否。design.md 可以基于 discussion-note 的原则推导预算规则。但如果有明确规则，design.md 会更精确。

---

### Finding-8: RemoteProxy wire protocol 缺乏最小规格

**严重程度**: MEDIUM

**位置**: `discussion-note.md` "远程执行拓扑" 节（L35-L44），"远程执行控制边界" 节（L626-L638）

**当前写法**:

```text
Host -> RemoteProxy -> RemoteStub -> EngineWorker -> Engine

RemoteStub / EngineWorker 只执行并回传带 run_id、attempt_id、execution_id、sequence / event id 的事件。
Host 校验 attempt_id + execution_id 后决定是否 append canonical EventLog。
```

**为什么有问题**:

1. **wire protocol 完全未定义**：RemoteStub 与 Host 之间使用什么传输协议？HTTP/gRPC/WebSocket？事件流如何表达？cursor/ack 如何工作？

2. **cancel 控制通道未定义**：cancel 信号如何从 Host 传递到 RemoteStub？是独立连接还是复用事件流连接？

3. **断线重连语义未定义**：RemoteStub 与 Host 之间的连接断开后，如何恢复？已发送但未 ack 的事件如何处理？

4. **与设计目标的关系**："支持本地 Engine 和远程 Engine 并列执行"是四个设计目标之一。如果 wire protocol 完全未定义，远程执行只能作为架构预留，不能作为第一版实施目标。

**影响**: RemoteProxy 是远程执行的关键路径。缺乏 wire protocol 规格意味着远程执行在第一版可能无法落地。

**建议改法**:

1. 决定远程执行是否进入第一版实施。如果不进入，在 discussion-note 中明确标注"远程执行 wire protocol 后移，第一版只做 LocalProxy"。
2. 如果进入第一版，至少定义传输协议选择、事件流格式、cancel 控制通道和断线重连语义。

**是否阻塞 design.md 生成**: 否。design.md 可以将 RemoteProxy 标记为"架构预留，wire protocol 后移"，只详细设计 LocalProxy。

---

## 与四个设计目标的对齐评估

### 目标 1: 生产级买方财报分析 Agent

**对齐程度**: 高

discussion-note 对 Conversation Memory 的设计从财报分析的第一性原理出发（L720-L728），包括工具结果即事实、追问连续性、跨轮一致性、pinned state、evidence anchor 等，动机成立且设计合理。cross-year weak-signal evidence chain（L836-L846）虽然复杂，但明确标记为不阻塞第一版。

**风险**: context governance 的"一步到位"表述可能导致第一版 scope 过大。

### 目标 2: 宿主强约束下的 LLM in the loop

**对齐程度**: 高

核心边界清晰：
- Host 是治理真源，Engine 只消费 messages（L583）。
- EventLog 是 append-only 事实源，Observer/Sink 只消费已提交事件（L349-L382）。
- Engine 不恢复旧 Agent/Runner，Host 基于 canonical facts 重建 messages（L671-L676）。
- cancel 由 Host 发起，Engine 只观察 cancellation token（L691-L693）。

**风险**: guidance 机制可能模糊 Host/Engine 边界（guidance 是 Host 注入的治理输入，但最终变成 Engine 看到的 messages）。需要在 design.md 中明确 guidance 的 message role。

### 目标 3: 单机多客户端 / 多进程

**对齐程度**: 中

- session slot 支持多客户端入口（L97-L122）。
- EventLog 的 durable queue 语义支持崩溃恢复（L276-L283）。
- admission 不变量保证同一 Session 同时最多一个 active Run（L265-L267）。

**风险**: 多进程持久化方案未明确。discussion-note 提到 SQLite（L388），但 SQLite 的多进程并发能力有限。design.md 需要评估 SQLite WAL 模式是否满足需求，或明确替代方案。

### 目标 4: 本地 Engine 和远程 Engine 并列执行

**对齐程度**: 中

- LocalProxy/RemoteProxy 语义等价原则正确（L628-L629）。
- 远程执行不变量清晰：Host 创建 Run/Attempt/execution_id，RemoteStub 只执行并回传事件（L632-L638）。

**风险**: wire protocol 完全未定义（Finding-8），远程执行在第一版可能只能做架构预留。

---

## 过度设计 / 冗余设计评估

### 1. Guidance 机制

guidance 的动机成立：工具结果后引导模型修正上下文使用方式。但它的实现路径比讨论中呈现的更复杂：
- 需要 EventLog 事件分类决策（是否 canonical）。
- 需要 RunInputBuilder 消息插入位。
- 需要 context compaction 交互规则。
- 需要 crash recovery 重建逻辑。

**判断**: 如果 guidance 只是"在 tool result 后追加一条 system message"，它不需要独立治理机制。如果需要复杂触发条件和策略引擎，它不是第一版应该做的。**建议第一版只在 RunInputBuilder 中预留 guidance message 插入位，不实现完整 guidance 引擎。**

### 2. Session Slot

session slot 的动机成立（WeChat 同一身份复用 session），但它增加了 `create_session` 接口的复杂度。

**判断**: 如果第一版只支持 CLI 和简单 Web 入口，session slot 可以后加。第一版 `create_session` 可以只接受 `session_id`（调用方生成），session slot 作为后续增强。**但 session slot 的设计预留应进入 design.md，避免后续实现推倒 Session schema。**

### 3. Cross-year Weak-signal Evidence Chain

明确标记为不阻塞第一版。设计预留合理。Host 只提供 evidence anchor / provenance / trace 骨架，业务层负责原始证据和 retrieval。**无过度设计风险。**

---

## 缺失需求评估

### 1. EventLog 的最小 schema 定义

discussion-note 给出了事件形态建议（L401-L415）：

```text
event_log
  event_id, session_id, run_id, attempt_id?, execution_id?,
  sequence, event_type, occurred_at, payload_json, payload_ref?, payload_digest?
```

这是好的起点，但缺少：
- canonical/preview 区分字段（或通过 event_type 隐含）。
- per-run cursor 与 global position 的关系。
- 幂等去重键（用于 Observer checkpoint 和重复事件识别）。

**建议**: 在 design.md 中补齐 EventLog schema，至少明确 canonical/preview 区分和幂等键。

### 2. Host 启动恢复（startup recovery）的触发条件和扫描范围

discussion-note 在 admission 不变量中提到（L281-L283）：

```text
Host 崩溃恢复后，QUEUED Run 保持 QUEUED，调度器恢复后继续按 durable 顺序启动，不得丢弃。
RUNNING / CANCELLING 的 active Attempt 在崩溃恢复时不能假装成功；必须进入 LOST。
```

但没有定义：
- 何时触发 recovery scan？（Host 启动时？定期？）
- 扫描范围是什么？（所有 non-terminal attempt？还是只有 lease 过期的？）
- recovery scan 的性能边界？

**建议**: 在 design.md 中补齐 startup recovery 的触发条件和扫描范围。

### 3. Host 公共接口的错误类型

discussion-note 列出了公共接口签名（L81-L91），但没有定义错误类型。例如：
- `create_session` 何时抛出什么错误？
- `start_run` 遇到 active run conflict 时返回什么类型的错误？
- `cancel_run` 遇到已终态 run 时返回什么？

**建议**: 在 design.md 中定义 Host 公共接口的错误分类（至少区分 conflict、not_found、invalid_state、internal）。

### 4. Durable Queue 的调度规则

discussion-note 在 admission 不变量中提到（L278-L280）：

```text
如果同一 Session 没有 active Run，Host 可以把最早可执行的 QUEUED Run 迁移为 RUNNING，并创建 Attempt。
```

但没有定义：
- 谁触发调度？（事件驱动？定时轮询？）
- 多个 QUEUED run 的优先级规则？（FIFO？priority？）
- 调度器是否需要 fencing / lease？

**建议**: 在 design.md 中补齐 durable queue 的调度触发和优先级规则。

---

## 总结

discussion-note 作为生成新 design.md 的输入是 **ready** 的。它覆盖了 Host 设计的核心概念空间，架构边界清晰，状态机自洽，EventLog 真源原则正确。

**无 blocking finding。** 进入 design.md 生成不需要先解决所有 gap。

**建议在进入 design.md 生成前做一轮简短讨论**（约 30 分钟），确认以下三点：
1. **第一版 scope boundary**（Finding-1）：哪些能力进入第一版 design.md，哪些只做预留。
2. **远程执行是否第一版**（Finding-8）：如果不进入，design.md 只详细设计 LocalProxy。
3. **cancel 治理的 working assumption**（Finding-6）：至少给出第一版最小 cancel 规格。

**其余 medium findings**（EngineEvent 映射、session slot 持久化、context governance 参数、guidance 归属、memory 竞争规则、缺失需求）可以在 design.md 生成过程中逐一决策。design.md 的职责就是把 discussion-note 中的讨论点收敛为可实施的规格。
