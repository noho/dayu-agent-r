# Host P8 Plan Re-review：Attempt Lease / Recovery / 多进程并发基础

> 注意：本复审完成后，用户进一步确认 P8 必须实施全局单调 fencing token，并区分
> owner secret 与 fencing token。因此本复审结论对全局 fencing token 契约未覆盖，需要追加复审。

## 结论：通过

本次复审只做文档复审，不写生产代码。复审目标是确认用户最新决策写回后，`docs/host/phase8-plan.md` 是否仍然 handoff-ready / code-generation-ready。结论为通过：P8 plan 已把 recovery 主路径、async observer 协议、多平台 multiprocessing 测试 helper、慢盘 Docker stress 后移、ToolRuntime attempt-scoped fencing、terminal 原子事务和 slice 边界写成确定方案，没有留下阻断性开放问题。

P8 动机仍成立。`docs/host/migration-plan.md` 已把 P6 后移项中的真实多进程 stress、owner lease / fencing / orphan recovery、attempt `terminal_event_position` 写入登记到 P8；`docs/host/phase8-plan.md` 进一步把这些缺口收敛为具体 schema、状态机、CAS 条件、supervisor API、测试矩阵和 smoke 验收。

## 用户最新决策核验

- `ObserverSink.process`：已固定升级为 async 协议。证据：`docs/host/phase8-plan.md` 第 11 节明确最终协议为 `async def process(...)`，要求迁移 memory / timeline / audit / tool trace observer，删除 `_run_async` bridge；P8-S2 是独立 slice。
- Observer ownership：未误引入 observer claim / lease。证据：第 11 节边界、P8-S2 非目标、P8 阶段总览均写明不实现 observer claim / lease、不实现后台 observer worker、不改变 projection checkpoint schema。
- 多平台测试 helper：已固定为 tests / smoke helper，不提升为 Host 生产 launcher。证据：第 1 节、第 5 节、第 13 节、P8-S7 均要求封装 start method、join timeout、进程终止、exitcode 断言、文件 SQLite path、跨进程结果收集；`dayu/runtime/**` 明确不应修改，除非未来另行评估层中立运行时能力。
- 慢硬盘 + Docker Linux stress：已正确后移到 issue #38，不进入默认 pytest。证据：第 1 节、P8-S8、第 16 节均写明默认 pytest 只保留 deterministic multiprocessing append / terminal race / stale recovery / observer drain。
- Recovery 主路径：已固定为不 takeover 同一 attempt，而是关闭旧 attempt 后创建新 recovery attempt。证据：第 1 节、第 6.3 节、第 10 节、P8-S6 均写明 `RECOVERING + new attempt` 与 `recovered_from_attempt_id`。
- ToolRuntime facts fencing：已进入 attempt-scoped 写入范围。证据：第 7.1 节列出全部 ToolRuntime Host-owned canonical facts，第 7.3 节定义 `ToolRuntimeEventAppender` / `ToolRuntimeOwnerScope`，P8-S5 设置了专门测试。

## Findings

无阻断 finding。

## Handoff-ready / Code-generation-ready 复审

P8 plan 已达到可交接标准：

- 契约明确：第 6 节给出 `AttemptState`、owner token、owner context、lease result、fencing reason、recovery decision、terminal link 等内部类型，且明确不进入 `dayu.host.__all__`。
- schema 明确：第 6.2 节固定扩展 `host_attempts`，不保留 `host_attempt_leases` 备选表，列出字段、索引、nullable 语义和 token hash 约束。
- 状态机明确：第 6.3 节列出合法迁移，并明确 `STALE` / `RECOVERING` / `LOST` 不允许回到 `RUNNING`，也不允许 takeover 同一 attempt。
- CAS 语义明确：第 6.4 节写出 acquire / renew / verify / terminal close / mark recovering 的 where 条件和 `rowcount == 0` typed result / error 语义。
- terminal 原子事务明确：第 8 节要求 terminal event append、owner fencing、attempt close、`terminal_event_position` 写入处于同一个 `BEGIN IMMEDIATE` 事务，并禁止后补或猜 position。
- ToolRuntime owner 注入明确：第 7.3 节明确不修改 `ToolExecutionContext`，通过 Host internal append port 和 `ToolRuntimeOwnerScope` 注入当前 attempt owner。
- observer async 迁移明确：第 11 节与 P8-S2 独立覆盖协议、实现、测试和停止条件。
- 多平台 helper 明确：P8-S7 将平台差异限制在 `tests/host/_multiprocess_platform.py` 或同等私有 helper，测试主体不得散落 `multiprocessing.set_start_method`、裸 `join(timeout)` 或重复清理逻辑。
- slices 符合 Gateflow：P8-S1 至 P8-S9 按依赖串行拆分，每个 slice 都有目标、文件 ownership、允许修改、非目标、前置依赖、验证命令、完成信号、停止条件和上下文压力。

## 非阻断注意项

- P8-S7 的“确认 P8 不需要 observer claim / lease”应按 scope 理解为“验证 P8 当前范围内 deterministic multiprocessing observer drain 不依赖 claim / lease”。它不能证明未来生产后台 observer worker 永远不需要 claim / lease；这一点计划已由 #28 / P15 承接。
- P8-S3 中“异常退出未 terminal 时按当前原因写 `FAILED` 或 `STALE` 诊断收口”需要实施时严格服从第 8 节边界：正常 terminal attempt 必须走 P8-S4 的 `append_terminal_and_close(...)` 同事务路径；无 terminal RunEvent 的诊断终态才允许没有 `terminal_event_position`。
- async observer 在同一 storage transaction 内 `await observer.process(...)` 是 P8 的显式取舍；它删除 P6/P7 的 sync-async bridge，但不解决后台 drain / sink 不阻塞 terminal 的问题，该能力仍由 #28 或 P15 承接。

## 仍需用户决策的问题

无阻断性开放问题。

## 验证说明

本次只做文档复审与一致性检查，不运行 pytest / pyright，不修改生产代码。
