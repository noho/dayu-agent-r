# Host Design v2 Review — AgentMiMo

## 元信息

- **Review target**: `docs/host/design.md` (draft design v2), `dayu/README.md`
- **Reference**: `docs/host/implementation-control.md` (gate 状态与流程约束)
- **Review persona**: AgentMiMo — 产品目标、买方财报分析 Agent 第一性原理、交互路径、用户可见语义、过度设计、phase readiness
- **Date**: 2026-05-13
- **Gate**: draft design v2 review

## 结论

**design v2 可进入 phase 编排。无 blocker。**

设计文档从第一性原理出发，清晰定义了 Host 作为"宿主强约束下的 LLM in the loop"治理真源的完整边界。状态机、EventLog 语义、幂等契约、多进程并发、远程执行不变量、工具治理、context governance 和恢复路径均有具体文件和章节支撑。术语与 `dayu/README.md` 一致，无冲突。

以下 findings 按优先级分组，均不阻断 phase 编排进入。

## Findings

### Blocker

无。

### High

#### H1. Run RUNNING 时机语义需显式锚定

**证据**: `docs/host/design.md` Section 6, Section 7, Section 8.1

设计存在一个微妙的语义缝隙：`Run RUNNING` 定义为"Run 当前有 active Attempt 正在执行"（Section 6），但 Attempt 有 `STARTING` 和 `RUNNING` 两个非终态（Section 7）。Section 8.1 的 `start_run` 行写 `Run RUNNING` + `ATTEMPT_STARTED`（Attempt status=`STARTING`），这意味着 `Run RUNNING` 在 Attempt 还处于 `STARTING` 时就已成立。

这本身是合理设计——`Run RUNNING` 表达的是"已占用 active slot"而非"worker 已确认执行"。但 Section 26.1 的恢复路径中，`RECOVERING -> RUNNING` 的退出条件写的是"Host 成功基于 canonical facts 创建并派发新 Attempt"，这里的"派发"是 dispatch 语义（Attempt `STARTING`）还是 worker accepted 语义（Attempt `RUNNING`）？

**风险**: phase agent 实现 recovery 时，可能在 dispatch 后立即将 Run 标为 `RUNNING`，但如果 dispatch 被拒绝或超时，Run 状态需要回退。若设计不显式锚定，不同 phase 可能对"Run 何时算 RUNNING"有不同理解。

**建议**: 在 Section 6 或 Section 8.1 中显式声明：`Run RUNNING` 表示 Host 已为该 Run 创建 Attempt 并完成 dispatch intent（Attempt `STARTING`），不要求 worker 已确认。Recovery 路径的 `RECOVERING -> RUNNING` 也应锚定到同一语义。

#### H2. wait_record "abandoned" vs "cancelled" 术语不一致

**证据**: `docs/host/design.md` Section 8.1 (cancel_run on waiting), Section 11 (WAITING Run steer path)

- Section 8.1 `cancel_run` on `WAITING`: "标记 active wait record cancelled"
- Section 11 `steer` on `WAITING`: "Host marks active wait record abandoned for resume purposes"

两个路径都使 wait record 不再接受后续 resolution，但用了不同术语。Section 19 的 wait record status 集合是 `waiting | resolved | failed | cancelled | lost`，没有 `abandoned`。

**风险**: phase agent 可能对 steer 路径的 wait record 使用非标准状态值，或者对 "abandoned" 和 "cancelled" 的迟到结果处理产生歧义。

**建议**: 统一为 `cancelled`，并在 Section 11 steer 路径中明确说明：steer 路径的 wait record 标记为 `cancelled`，语义与 cancel 路径一致——迟到结果只能进入 diagnostic / tool trace。

#### H3. Session 读取与关闭的 request shape 未定义

**证据**: `docs/host/design.md` Section 10

Section 10 列出的最小接口包含 `get_session(host, session_id)` 和 `close_session(host, session_id, request)`，但只定义了 `EnsureSessionRequest`、`CreateSessionRequest` 等 request shape，未给出 `CloseSessionRequest` 的字段。

`close_session` 是 mutating 操作（会 append `SESSION_CLOSED`），按 Section 10 的设计原则应携带 `HostCallContext` 和 `client_request_id`。缺少 request shape 会导致 phase agent 猜测是否需要 `reason`、`client_request_id` 等字段。

**建议**: 补充 `CloseSessionRequest` shape，至少包含 `client_request_id` 和 `reason`。

### Medium

#### M1. submit_followup(queue) 幂等语义需显式声明

**证据**: `docs/host/design.md` Section 10, Section 11

`submit_followup` 的 `behavior=queue` 路径创建后续 queued Run。Section 10 说"queued follow-up / queued run 也必须按 `(session_id, client_request_id)` 幂等"，但 `SubmitFollowupRequest` 没有显式声明幂等键。

对比 `start_run` 明确写了 `(session_id, client_request_id)` 幂等，`submit_followup` 应同等声明。

**建议**: 在 Section 10 `SubmitFollowupRequest` 或 Section 11 中显式声明 `submit_followup` 的幂等范围为 `(session_id, client_request_id)`。

#### M2. cancel_run mode 字段范围未限定

**证据**: `docs/host/design.md` Section 10

`CancelRunRequest` 定义了 `mode: graceful`，但未说明是否有其它 mode（如 `force`、`immediate`）。如果 `graceful` 是唯一 mode，字段冗余；如果有 future modes，应在 design 或 non-goals 中提及。

**建议**: 明确 `mode` 字段第一版只支持 `graceful`，其它 mode 属于后续扩展，或直接移除该字段。

#### M3. RetryRunRequest.policy_overrides 与 ReplayRunRequest.reuse_policy 未枚举

**证据**: `docs/host/design.md` Section 10

这两个字段有类型但无枚举值。Section 20 描述了 retry 和 replay 的语义边界，但未将 policy choices 映射到 request 字段。

**风险**: phase agent 实现时可能自行发明 policy 枚举值，导致不同 phase 间 policy 语义不一致。

**建议**: 在 Section 10 或 Section 20 中补充最小 policy 枚举，至少列出第一版支持的值。可标注"具体 policy 值属于 phase design scope"，但枚举框架应在 design 中锚定。

#### M4. delivery_target 三级 fallback 的 Session binding 语义未定义

**证据**: `docs/host/design.md` Section 15

delivery target 解析优先级为 "request 显式字段 > `HostCallContext` typed field > Session binding default"。但 Session binding default 的来源、持久化位置和更新机制未在 Session 生命周期（Section 4）或 Session slot（Section 5）中定义。

**建议**: 在 Section 4 或 Section 5 中明确 Session 是否有 default delivery binding，以及该 binding 的设置和更新路径。如不属于第一版，应在 Section 27 non-goals 中声明。

### Low

#### L1. EngineEvent 映射表中 context_compaction_requested 的 Attempt 状态处理

**证据**: `docs/host/design.md` Section 12.4

映射表写 `run_failed -> ATTEMPT_FAILED + (RUN_FAILED or RUN_RECOVERING by Host policy); context_compaction_required 在可恢复时进入 RUN_RECOVERING + new Attempt`。

这里的 `context_compaction_required` 与 Section 24.1 的 `context_compaction_requested` 是同一个 EngineEvent 还是不同事件？设计中 EngineEvent 名称是 `context_compaction_requested`，但映射表用了 `context_compaction_required`。

**建议**: 统一为 `context_compaction_requested`，与 Section 24.1 和 canonical event `CONTEXT_COMPACTION_REQUESTED` 一致。

#### L2. get_run / get_session 返回值中 "cursor" 语义需锚定

**证据**: `docs/host/design.md` Section 10

`RunSnapshot` 包含 `event_sequence cursor`，`SessionSnapshot` 包含 `timeline cursor`。`event_sequence` cursor 语义在 Section 12 中有完整定义，但 `timeline cursor` 的语义——它是 `event_sequence` 还是 session-local sequence——未显式说明。

**建议**: 明确 `SessionSnapshot.timeline cursor` 是 `event_sequence` cursor 还是 session-scoped cursor，以及 `stream_run_events` 是否可复用该 cursor。

#### L3. HostPolicyProviderSet 的 policy view 类型列举可推迟但应标注

**证据**: `docs/host/design.md` Section 9.1

设计列举了 5 个 typed policy view（`AdmissionPolicyView` 等），但 7 个 policy provider 中只有 5 个有对应 view。缺少 `CancelPolicyView` 和 `SinkOutboxPolicyView`。

**建议**: 补齐或标注"具体 policy view 类型属于 phase design scope"。

## Over-coupling / Overengineering Check

### Over-coupling

**未发现 over-coupling 问题。** 设计的模块边界（Section 2）清晰，依赖方向固定，各模块 ownership 明确。尤其是：

- Engine 不理解 Host 治理（Section 2 边界约束）
- ToolRuntime 通过 `ToolExecutor` 协议与 Engine 解耦（Section 17）
- Sink 不拥有治理状态（Section 13）
- RemoteStub 不拥有 Host 状态（Section 16）

### Overengineering

**轻微 overengineering 倾向，但不阻断：**

1. **HostPolicyProviderSet 7 个 policy provider**：对第一版而言，admission policy、cancel policy、retry/replay policy、context budget policy 可以从 typed config 直接读取，不必全部抽象为 provider。第一版可以先用 immutable config snapshot，后续再提升为 dynamic provider。这属于 phase plan 的实现选择，不影响设计正确性。

2. **RunInputBuilder 7 个 typed input provider**：`CurrentRunFactProvider`、`SessionContinuityProvider` 等是合理的抽象边界，但第一版实现时可以先用函数调用而非独立 provider class。设计定义的是接口语义，不是实现形态，这一点 design 已明确（"typed input provider protocols"），无过度设计风险。

3. **Canonical event 30+ 种**：对生产级 Host 而言，这个数量是合理的。每个 event 都有明确的状态副作用和恢复语义，无冗余。

## Phase-Readiness Verdict

**可进入 phase 编排。**

design v2 对以下关键维度提供了足够支撑：

| 维度 | 覆盖度 | 说明 |
| --- | --- | --- |
| 状态机（Session / Run / Attempt） | 完整 | 状态集合、终态、迁移规则、竞态处理均已定义 |
| EventLog 语义 | 完整 | event_class 分层、canonical event 最小集合、contract matrix、ingest 语义 |
| 公共接口 | 充足 | 最小接口集合、request shape、幂等契约、错误分类 |
| 多进程并发 | 完整 | SQLite 事务、CAS、promotion 竞态、cancel 竞态 |
| 远程执行 | 充足 | 语义契约已定义，wire protocol 显式排除 |
| 工具治理 | 完整 | ToolRuntime 边界、accept barrier、截断、重复治理、awaiting |
| 恢复 | 完整 | Recovery scan、attempt dispatch record、graceful shutdown |
| Context governance | 充足 | proactive / reactive 双路径、compact event 契约 |

**Phase agent 不会因文档不硬而自行猜测的关键维度**：

- 状态迁移有明确的 contract matrix（Section 8.1）
- Canonical event 有明确的 contract matrix（Section 12.3）
- EngineEvent 映射有规范性边界（Section 12.4）
- 幂等范围有显式声明（Section 10）
- 术语与 `dayu/README.md` 一致，无歧义

**Phase agent 可能需要在 phase discussion 中细化的维度**（不阻断进入编排）：

- policy 枚举值的具体定义
- RunInputBuilder provider 的数据形状
- Session default delivery binding
- 各 phase 的测试矩阵

## Residual Risks

1. **Engine context compaction event 语义前置**：`implementation-control.md` 已追踪。Host Context Governance phase 依赖 Engine contract cleanup 完成。当前 design 已正确描述 proactive / reactive 双路径，但 Engine 侧 `budget_state` 的 `0/0/0` 占位问题仍需在 Host phase 前解决。

2. **External job cancel adapter 能力**：`implementation-control.md` 已追踪。Tool Awaiting / Wait Adapter phase 需定义 wait record cancelled 后 adapter 如何观察该状态。design 已明确这是 best-effort，不阻断。

3. **Tool trace / provider request 排错**：`implementation-control.md` 已追踪。后续实现 tool trace 时需纳入 `provider_request_id`。不阻断 Host design。

4. **H1 (Run RUNNING 时机) 若不在 phase discussion 前锚定**：可能导致不同 phase 对 Run 状态语义理解不一致，增加集成风险。建议在第一个 phase 的 discussion 中优先确认。

5. **长期 memory 与 retrieval**：design Section 25 明确排除在第一版外，但边界定义清晰，不会封死后续扩展。residual risk 低。
