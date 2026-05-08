# Host P6 Plan Review：Durable EventLog / Run State / Projection

## 结论

有条件通过。

`docs/host/phase6-plan.md` 的动机成立，主边界与 `migration-plan.md` 的 P5.5 总控判断一致：P6 聚焦 durable EventLog、Run / Attempt 最小状态、projection checkpoint 与最小 observer / sink protocol，没有把 P7 tool trace schema、P8 attempt lease / fencing、P9 lifecycle admission、P10 ToolRegistry、P10.5 web tools 或 P11-P14 能力提前塞入实现范围。Plan 也明确保护 Engine 边界，要求 observer 消费 EventLog 而非 EngineEvent iterator，并限制 `LocalRunHarness` 只做装配与薄委托。

进入代码实施前，建议先处理下面 findings 中的条件项，尤其是同事务边界和 durable payload 序列化真源；否则实施 Agent 仍可能在文件拆分时做出两套事实源或弱一致性落库。

## Findings

### 1. [已修复] Atomic append 的共享事务边界仍需落成可执行接口

严重级别：高

证据：

- P6 plan 要求 append 在单个持久事务中完成 cursor 分配、event row 插入、Run / Attempt 最小状态更新、terminal result snapshot / reconcile 标记，并在 commit 后再通知订阅者：`docs/host/phase6-plan.md:455`。
- 文件级计划把 durable EventLog、Run / Attempt state、projection checkpoint 分到 `_durable_event_store.py`、`_run_state_store.py`、`_projection_store.py`：`docs/host/phase6-plan.md:184`。
- 当前 `RunEventStore` protocol 只有 `append(draft) -> RunEvent`、`list_events`、`subscribe`，没有事务上下文或 state store 协作入口：`dayu/host/_event_store.py:39`。

影响：

如果实施时各 store 各自管理连接 / commit，可能出现 terminal RunEvent 已落库但 Run state / result snapshot 未更新，或 state 已更新但 event append 回滚。这个问题会直接破坏 P6 的 terminal reconcile、startup recovery、projection rebuild 与多进程一致性验收。

建议：

在 P6 实施前补充一个明确的 Host internal transaction owner / Unit of Work 决策：要么由 durable EventLog append 在同一 SQLite connection / transaction 中调用 RunStateStore 的内部写入，要么引入层中立的 Host storage transaction helper 并禁止 harness 直接组合多次 commit。测试中应加入故障注入，覆盖 event 插入后、state 更新前以及 checkpoint 前进前后的回滚 / reconcile。

### 2. [已修复] Durable RunEventData 序列化仍停留在待确认项，handoff 粒度偏松

严重级别：中

证据：

- P6 EventLog 数据模型要求 `typed data payload` 具备稳定 JSON 表达：`docs/host/phase6-plan.md:314`。
- Plan 已识别开放 dict 的风险，并把 serializer / deserializer registry 放入待确认项：`docs/host/phase6-plan.md:690`、`docs/host/phase6-plan.md:699`。
- 当前 `RunEventData` 是封闭联合，但包含 `EngineEventData` 与 ToolRuntime 事件数据，后续 durable 落库需要稳定 type discriminator 与 round-trip 规则：`dayu/host/contracts.py:463`。

影响：

如果实施 Agent 临场使用 `asdict`、开放 dict 或字符串化 payload，pyright 可能仍通过，但 durable EventLog 会失去可演进的 schema 真源。后续 P7 trace、P8 recovery、P9 lifecycle replay 会基于不可验证 payload 重建事实，风险会被放大。

建议：

把 P6 handoff 条件收紧为：先确定封闭 serializer registry、事件 type 到 data 类型的映射、版本字段、未知 type fail-fast 策略和 round-trip 测试；禁止把 typed payload 降级成开放 dict。schema version 改变仍按全新起库，不做旧库兼容读取。

### 3. [已修复] Memory rebuild 对非成功终态的语义需要补测试约束

严重级别：中

证据：

- Host 设计要求失败轮次的用户输入事实和中性 terminal summary 进入下一轮 memory：`docs/host/design.md:990`。
- P6 plan 的 memory rebuild 测试覆盖了 durable rebuild、工具事实脱敏、final answer 不升级 verified claim、session 隔离、compact retry 去重，但没有明确覆盖 Engine `RUN_FAILED`、`RUN_CANCELLED`、`RUN_SUSPENDED` 等非成功终态：`docs/host/phase6-plan.md:587`。
- 当前 `_project_raw_turn` 只识别 `FINAL_ANSWER` 和 Host-owned `HostRunFailedData`，没有为 Engine failure / cancelled / suspended 生成 terminal summary：`dayu/host/_conversation_memory.py:611`、`dayu/host/_conversation_memory.py:637`。

影响：

P6 若只验证成功终态和 Host failure，replay / rebuild 后的 memory read model 可能与实时投影或设计语义不一致。多进程恢复时，失败、取消、挂起 run 的用户输入虽已进入 EventLog，但下一轮 RunInputBuilder 看到的 terminal context 可能缺失。

建议：

在 P6 测试清单中明确加入非成功终态 rebuild 场景：Engine `RUN_FAILED`、Host-owned failure、cancelled、suspended 至少要证明用户输入不丢失，terminal summary 的进入 / 不进入 memory 有明确规则。若 P6 决定暂不把某类终态写入 memory，也应在 plan 中写成显式非目标或 residual risk。

### 4. [已修复] 现有 contracts 注释仍把 lifecycle 幂等写成 P7，容易误导实施边界

严重级别：低

证据：

- 总控计划明确 P7 是 Tool Trace，P9 才固定 Session / Run lifecycle、`client_request_id` 幂等、active Run admission 与 public interface：`docs/host/migration-plan.md:142`、`docs/host/migration-plan.md:144`。
- P6 plan 也把 `client_request_id` 幂等、同 Session active Run admission、`cancel_run` 和完整 public interface 固定列为 P9 非目标：`docs/host/phase6-plan.md:47`。
- 当前 `StartRunRequest` docstring 仍写“完整创建幂等与同 Session active Run 仲裁在 P7 落地”：`dayu/host/contracts.py:510`。

影响：

P6 会修改 `contracts.py` 增加强类型 durable / projection contract。如果实施 Agent 没注意该旧注释，可能把 lifecycle 幂等误排到 P7，或在 P6 contracts 同步时保留错误阶段口径，导致 review 和 README 同步出现新旧术语并存。

建议：

P6 实施若触及 `contracts.py`，应把该注释同步为 P9，不改变生产接口语义；如果 P6 不触及该区域，也应把它列入 P9 前文档债务，避免用旧注释指导 phase 边界。

## 通过项

- Scope 边界基本正确：P6 明确不做 P7 正式 tool trace schema、不做 P8 lease / fencing、不做 P9 lifecycle / admission、不做 P10 ToolRegistry、不做 P10.5 web tools、不做 P11-P14 能力。
- Observer / sink 方向正确：计划限定为最小 durable protocol、checkpoint、retry / lag，不做 MQ consumer framework、worker fleet、consumer group、DLQ 或跨服务 ack。
- Engine 边界保护充分：计划禁止修改 Engine 生产代码，要求 Host durable / projection / memory / governance 不回流 Engine，并把 EngineEvent 事实不足时的处理放到 P7+ 或专项契约讨论。
- 多进程事实层关键点齐全：计划覆盖 atomic append、per-run cursor、internal global event position、terminal guard、checkpoint 幂等、replay / rebuild 和 fresh schema 起库。
- `LocalRunHarness` 防 God Object 边界明确：计划要求 projection coordinator、observer runner、memory / timeline / audit projection 分模块承载，禁止在 harness 中新增 SQL、checkpoint、retry loop 和 read model 写入规则。
- 测试与 smoke 覆盖面总体足够：包含 durable store、并发、run state、checkpoint、projection rebuild、memory rebuild、observer retry / lag、边界测试、P1.5-P5 回归、pyright 与 P6 smoke。

## Residual Risk / Open Questions

- SQLite 是否作为 P6 durable backend 仍是待确认项；如果改用其它 backend，必须重新证明多进程 cursor allocation 与 transaction 语义。
- Memory read model 是否必须 durable 落库仍未最终固定。若 P6 只 rebuild 到 in-memory store，后续多进程共享 memory 的验收信号要避免被误读为已完成。
- Observer lag 查询是 public diagnostic API 还是 internal helper / smoke 输出仍未固定；P6 不应借此冻结 Host public interface。
- P6 不做 observer claim / lease 是合理边界，但同一 observer 多进程重复 drain 的幂等测试必须足够强，否则 P8 前会留下重复 sink 写入风险。

## Review 结论说明

本 plan 可以作为 P6 handoff plan 的基础，但应带条件进入实施：先固定共享事务边界与 payload serializer 策略，并补足 memory rebuild 的非成功终态测试口径。上述条件不要求提前实现 P7/P8/P9 能力，也不要求修改 Engine；它们都是 P6 durable facts 自身的必要清晰度。
