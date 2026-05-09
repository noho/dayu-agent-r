# Host P8 Plan Review：Attempt Lease / Recovery / 多进程并发基础

## 结论：不通过

P8 动机成立。`docs/host/migration-plan.md` 已把真实多进程 stress、owner lease / fencing / orphan recovery、`terminal_event_position` 写入明确登记为 `deferred-with-owner: P8`，当前代码也能直接证明缺口存在：`host_attempts` 仍无 owner / lease 字段，`AttemptStateStore.update_state` 只按 `attempt_id` 更新，`_finish_attempt_if_durable` 仍把 `terminal_position` 固定为 `None`。

Scope 大体正确：计划没有明显偷做 P9 Session lifecycle、P10 ToolRegistry、Remote、Outbox、Wait/Suspend/Resume。但它还不能直接交给实施 Agent。核心问题是关键契约、schema、recovery policy、observer 决策和 attempt-scoped append 覆盖面仍未定稿；其中部分还被列为“待用户确认项”。按 gateflow 的 handoff-ready 要求，这些属于阻断性 open questions，必须先修 plan。

## Findings

### F1 [High] 阻断性 Open Questions 仍留给实施阶段决策 [已修复]

**证据：**

- `docs/host/phase8-plan.md:527-532` 将 recovery 主路径、observer claim / lease 是否进入 P8、multiprocessing stress 是否默认运行、`AttemptFencingError` 是否写 diagnostic RunEvent 列为“待用户确认项”。
- `docs/host/phase8-plan.md:337-340` 的 S5 同时允许 takeover、mark lost、创建 recovery attempt，但未指定 P8 主路径。
- `docs/host/phase8-plan.md:198-204` 要求 observer claim / lease 若引入必须独立切片，但又只给“默认建议”。

**为什么影响直接实施：**

这些问题直接影响 schema、状态机、文件 ownership、测试断言和用户可见治理语义。尤其 recovery 是接管同一 attempt 还是创建新 recovery attempt，会决定 `attempt_index`、`recovered_from_attempt_id`、terminal close、tool trace source position 如何建模；observer claim / lease 是否进入 P8 会决定是否新增 projection 状态机与测试矩阵。实施 Agent 不能在代码阶段自行选择。

**要求的修复：**

把这些 open questions 改成 plan 决策：明确 P8 首版 recovery 主路径、observer claim / lease 是否不做且后移 owner、stress 是否作为默认 pytest 还是 marker、fencing diagnostic 是否不写 EventLog。若任一项确需用户决定，必须标为 blocking，并在 plan re-review 前由用户确认后写回为确定决策。

### F2 [High] 契约 / Schema / 状态机仍是“候选”，缺少可生成代码的精确定义 [已修复]

**证据：**

- `docs/host/phase8-plan.md:82-116` 标题和正文多次使用“候选”“建议扩展”“也可新增表”。
- `docs/host/phase8-plan.md:86-91` 只列出 `AttemptOwnerToken`、`AttemptLeaseDecision`、`AttemptRecoveryDecision` 等名称，没有字段类型、方法签名、枚举真值、错误 reason enum。
- `docs/host/phase8-plan.md:97-107` 对 `host_attempts` 扩字段和新增 `host_attempt_leases` 表仍保留选择。
- `docs/host/phase8-plan.md:118-133` 的状态机同时出现 `LEASED`、`STARTING`、`STALE`、`LOST`、`CANCELLING`、`CANCELLED`，但 P8 最小实现只说“可接受”，未给最终 `AttemptState` 枚举变更。

**为什么影响直接实施：**

当前代码的 `AttemptState` 只有 `CREATED/RUNNING/SUCCEEDED/FAILED/CANCELLED/SUSPENDED/STALE_DIAGNOSTIC`，`host_attempts` schema 也只有 P6 最小字段。实施 Agent 需要知道到底新增哪些 enum、哪些 dataclass、哪些 store 方法、哪些 SQL 条件和哪些返回类型。计划如果停留在候选列表，会诱导多个实现分叉，review 也无法判断是否按计划完成。

**要求的修复：**

把第 6 节改成最终契约：固定表设计，不保留 `host_attempt_leases` 备选；列出最终 schema 字段、nullable / NOT NULL、索引和唯一约束；给出 `AttemptState` 最终枚举和合法迁移；给出 `AttemptLeaseStore` / `AttemptSupervisor` 方法签名、参数类型、返回类型、错误 reason enum；说明每个 CAS 更新的 where 条件与 rowcount=0 的 typed result。

### F3 [High] ToolRuntime 的 attempt-scoped RunEvent 写入未纳入 fencing 覆盖面 [已修复]

**证据：**

- `docs/host/phase8-plan.md:149-155` 列出需要 owner fencing 的写入，只点名 Engine-sourced event、context compact fact、P7 run input context snapshot fact，没有覆盖 ToolRuntime facts。
- `docs/host/phase8-plan.md:315-329` 的 S4 预期结果也只覆盖 Engine-sourced event、context compact fact、run input context snapshot fact、terminal event。
- 当前 `dayu/host/_tool_runtime.py:1073-1101`、`1118-1133`、`1150-1166`、`1193-1221`、`1239-1255`、`1274-1285` 等路径直接调用 `event_store.append(...)` 写入 tool runtime canonical facts。
- `dayu/contracts/tool_call.py:74-98` 的 `ToolExecutionContext` 只有 run/session/iteration/tool_call 等字段，没有 attempt owner context。

**为什么影响直接实施：**

P8 的核心验收是“旧 owner、过期 owner、非 owner 的 attempt-scoped 写入被拒绝”。ToolRuntime facts 属于当前 attempt 执行产生的 Host-owned canonical facts；如果旧 owner 进程在 lease 过期后仍执行工具或 framework `fetch_more`，它可以绕过 P8 fencing 继续写 `TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、`TOOL_FETCH_MORE_*` 等事实，污染 EventLog 和后续 tool trace / memory projection。

**要求的修复：**

在 plan 中补一张 attempt-scoped append 覆盖表，逐项列出现有所有 `event_store.append` / `append_in_transaction` call site，并指定 owner context 如何传入。特别要明确 ToolRuntime 是否在 P8 接收 Host internal owner context、是否新增 fenced append port / protocol、framework `fetch_more` 在同一 run 内如何验证当前有效 attempt。补充对应测试：旧 owner lease 过期后 ToolRuntime append 被 typed fencing 拒绝，合法 owner 的 truncate / cursor / fetch_more facts 仍可写入。

### F4 [High] `terminal_event_position` 的同源写入与 slice 顺序不安全 [已修复]

**证据：**

- `docs/host/phase8-plan.md:111` 要求 terminal position 从 append 返回位置或查询 helper 写入。
- `docs/host/phase8-plan.md:166-167` 说 terminal event append 与 attempt terminal state / `terminal_event_position` 必须同源，但使用“推荐让 append 返回...”而不是固定方案。
- `docs/host/phase8-plan.md:280-312` 先在 S2 接入主路径 owner close，再在 S3 才实现 terminal position 同源写入。
- 当前代码 `dayu/host/_run_harness.py:1244-1264` 在 finish attempt 时将 `terminal_position` 固定为 `None`，且 terminal EventLog append 与 attempt update 是两个事务。
- 当前 `_AppendedRunEvent` 已存在但为私有类型，见 `dayu/host/_durable_event_store.py:70-75`；public internal `append_in_transaction` 仍只返回 `RunEvent`。

**为什么影响直接实施：**

P8 承接的 P6 residual 明确要求补齐 `terminal_event_position`。如果 S2 先把 owner close 接入主路径，但 S3 才决定 position API，S2 后系统仍处于“terminal attempt 无 position”的已知缺口；如果 S3 仍允许“同源事务”而非明确同一事务，实施 Agent 可能继续写成 terminal append 后另起事务 update attempt，留下 crash window。

**要求的修复：**

把 terminal append + owner fencing + attempt terminal close 的原子边界在计划里固定为同一个 `BEGIN IMMEDIATE` 事务，并给出具体 API，例如 `append_attempt_event_in_transaction(...) -> AppendedRunEvent` 或 `AttemptSupervisor.append_terminal_and_close(...) -> AttemptTerminalLink`。调整 slice 顺序：要么 S2/S3 合并为一个小的 terminal vertical slice，要么 S2 只接入 non-terminal acquire/renew，不允许声明 terminal close 完成，直到 S3 同事务 position 写入完成。

### F5 [Medium] Lease renew / heartbeat 运行机制不够 handoff-ready [已修复]

**证据：**

- `docs/host/phase8-plan.md:11` 把 heartbeat / renew 列为本阶段产出。
- `docs/host/phase8-plan.md:87`、`99-103` 只列 lease 字段。
- `docs/host/phase8-plan.md:262-296` 的 S1/S2 只写 acquire / renew / close 和主路径接入，没有说明 renew task 生命周期、renew 周期、TTL 常量、clock 注入位置、renew 失败后的执行收口。

**为什么影响直接实施：**

长 attempt 运行时，如果只在开始 acquire 而没有明确 heartbeat task，lease 会自然过期，新进程可 takeover，而旧进程仍可能继续 stream engine events 或执行 tools。反过来，如果实现 Agent临时加后台 task，也需要明确谁启动、谁取消、异常如何传播、Engine stream 是否停止、projection 是否仍 drain。缺少这些机制会让 P8 在真实多进程长运行下仍不具备有效 owner 真源。

**要求的修复：**

在 S2 前补充 lease runtime 决策：命名 TTL 与 renew interval 常量，使用可注入 UTC clock；定义 `AttemptSupervisor` 持有的 renew loop / context manager 生命周期；定义 renew rowcount=0、lease expired、storage error 时的 typed outcome 和 harness 行为；补测试覆盖运行中 renew、renew 失败停止后续 append、close 时停止 renew、异常路径不泄露 token。

### F6 [Medium] Observer async/sync 结论放在实施报告中，晚于 plan gate [已修复]

**证据：**

- `docs/host/phase8-plan.md:200-204` 说 `ObserverSink.process` 协议结论必须在 P8 Slice S1 固定。
- 但 `docs/host/phase8-plan.md:270` 又要求 S1“不改 observer 协议实现，只在实施报告给出 async/sync 结论”。
- `docs/host/migration-plan.md` 总控工作流要求 phase plan handoff-ready，不能让实施 Agent 自行补关键边界。

**为什么影响直接实施：**

observer 协议是否升级会改变 `_event_observer.py`、memory/timeline/audit/tool trace observer、projection tests 和 code review gate。把结论延后到实施报告，会让 S1 实施 Agent 在代码阶段才做架构判断，也让后续 S6 observer drain / recovery stress 的预期不稳定。

**要求的修复：**

在 plan review fix 阶段直接写成确定决策。若默认不升级，就明确 P8 保留同步 `ObserverSink.process`、不实现 observer claim / lease、后续 owner 为 P15 或独立 follow-up，并把 S1 的“实施报告给出结论”改为“实现中不得改 observer 协议，只需在文档同步中记录已复核结论”。若要升级，则必须新增独立 slice 和完整测试。

## Open Questions（修复后状态）

- 已解决：P8 首版 recovery 主路径固定为不 takeover 同一 attempt；旧 attempt 先标记为 `STALE` / `RECOVERING` / `LOST`，默认 `RECOVERING + new recovery attempt`，并记录 `recovered_from_attempt_id`。
- 已解决：P8 将 `ObserverSink.process` 升级为 async 协议，但不实现 observer claim / lease，不升级 observer ownership；后台 observer drain / observer claim 后续 owner 为 #28 或 P15。
- 已解决：ToolRuntime facts 全部视为 attempt-scoped Host-owned canonical facts；通过 `AttemptScopedRunEventAppender` / `ToolRuntimeEventAppender` 注入当前 attempt owner context。
- 已解决：terminal event append、owner fencing、attempt terminal close、`terminal_event_position` 写入固定在同一个 `BEGIN IMMEDIATE` 事务内，由 `AttemptSupervisor.append_terminal_and_close(...) -> AttemptTerminalLink` 承载。
- 已解决：基础 deterministic multiprocessing append / terminal race / stale recovery / observer drain 测试进入默认可运行 pytest；慢硬盘 + Docker Linux 重压版 stress 由 issue #38 跟踪，不进入默认 pytest。

## Residual Risks

本 review 原始结论为不通过；上述 finding 已由 plan fix 标注为已修复，仍需独立 plan re-review 给出最终通过 / 不通过结论。非阻断残余风险以修订后的 `docs/host/phase8-plan.md` 第 20 节为准。
