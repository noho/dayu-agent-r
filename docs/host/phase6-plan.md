# Host P6 Handoff Plan：Durable EventLog / Run State / Projection

## 1. 目标

P6 目标是在 P1.5 Minimal EventLog / RunEventStore 语义之上，建立 Host 后半段多进程治理的 durable facts
基础。动机成立：P1.5 到 P5 已经证明单进程、顺序 happy path 可以通过同一份 EventLog / ToolRuntime /
Conversation Memory / compact 链路跑通，但当前真源仍主要是内存态；若 P7 tool trace、P8 attempt lease 或
P9 lifecycle 直接各自补持久化，会形成多套事实来源，后续很难 review 和恢复。

本阶段必须产出：

- 多进程共享 durable EventLog：保留 P1.5 append-before-stream、per-run cursor、exclusive replay、
  canonical / preview、terminal guard 语义，并新增跨进程安全的 append 与 replay 能力。
- Run / Attempt 最小持久状态：只记录 P6 恢复、terminal reconcile、projection rebuild 所需的最小状态；
  不实现生产级 admission、owner lease 或 fencing。
- atomic append / cursor allocation：同一事务中完成 per-run cursor、内部全局 event position、事件落库和必要
  Run / Attempt 最小状态更新。
- projection checkpoint：observer / projection 以 durable checkpoint 记录最后成功消费位置、schema version、
  retry / error / lag 状态，并可幂等重建 read model。
- 最小 observer / sink protocol：为 audit、timeline、memory、后续 tool trace 提供 durable protocol 与 checkpoint
  基础；P6 只提供可验证最小示例，不落地正式 tool trace schema。
- audit / timeline / memory projection 重建基础：至少能从 durable EventLog 重新生成 memory read model 与一个
  最小 timeline / audit 示例 read model，证明 projection 不依赖进程内事件流。
- observer retry / lag：observer 失败可重试，失败状态、重试次数、最后成功 cursor / position 与 lag 可查询或
  通过 smoke 输出观察。
- LocalRunHarness 防 God Object 改造边界：P6 只允许通过明确模块边界接入 durable store 与 projection coordinator，
  不继续把 durable schema、checkpoint、observer dispatch、rebuild 逻辑堆进 `_run_harness.py`。

P6 验收信号：

- EventLog storage 本身具备多进程安全的 append / replay / checkpoint 语义。
- P5 单进程路径可以切到 durable store 后继续通过 append-before-stream、memory projection 与 compact 相关测试。
- kill / recreate store client 后，可从 durable EventLog replay 并重建 memory / timeline / audit 示例 read model。
- observer checkpoint 可以从失败处重试，重复消费同一事件不产生重复投影。

## 2. 非目标

P6 不实现以下能力：

- P8 attempt lease / recovery / fencing、owner token、lease renew、late write fencing、orphan recovery。
- P7 正式 Tool Trace Projection / Sink，不落地具体 `tool_trace_v2` schema，不做 OLD trace schema 对齐。
- 不把 trace 写回 Engine，不恢复 Engine 私有 `ToolTraceRecorder` / JSONL store。
- 不要求所有 observer hard-gate Run terminal；P6 只定义 required / best-effort 的边界与最小 required projection
  入口，不能把 audit / trace / metrics 全部隐式同步写入主执行路径。
- 不把 observer / sink 做成完整消息队列消费者框架：不做独立 worker fleet、复杂 claim / lease / rebalance、
  consumer group、ack protocol、dead-letter queue 或跨服务投递协议。
- 不实现完整 Session / Run lifecycle governance：`client_request_id` 幂等、同 Session active Run admission、
  `cancel_run`、完整 public interface 固定均留到 P9。
- 不实现 P10 完整 ToolRegistry、权限治理、middleware、业务工具迁移。
- 不实现 P12 Reply Outbox、P13 RemoteProxy / RemoteStub、P14 Wait / Suspend / Resume。
- 不迁移 business fins / doc / web 工具；财报文档存取仍只能由业务工具通过 `dayu.fins.storage` 保证。
- 不做 context governance、provider 官方 tokenizer、长期记忆、public memory edit / reset / forget；这些由
  issue #23、#20、#24 跟踪。
- 不新增 Engine 公共契约，不修改 Engine 运行边界；如果发现 EngineEvent 事实不足，只能形成 P7+ 或 Engine
  契约专项 issue / plan，不能在 P6 让 Engine 反向依赖 Host projection。
- 不做旧库兼容读取或兼容测试。P6 若新增持久 schema，一律按全新 schema 起库处理，除非用户另行明确要求兼容升级。

## 3. 当前事实与依赖

当前已经落地的 Host 事实：

- `dayu/host/_event_store.py`
  - 定义 `RunEventStore` protocol 与 `InMemoryRunEventStore`。
  - 只保证单进程内 append-only、per-run cursor、exclusive replay、replay-then-follow、terminal guard。
  - 不提供 durable schema、多进程一致性、startup recovery、observer checkpoint。
- `dayu/host/_run_harness.py`
  - `LocalRunHarness.start_run` 先 append Host-owned `USER_INPUT_ACCEPTED`，再构造 RunInput 并启动 Engine。
  - `_run_to_store` 消费 `WorkerProxy.stream_engine_events`，将 EngineEvent 翻译成 RunEventDraft 后 append 到 store。
  - terminal 后调用 `_project_run_events`，从 `event_store.list_events` 读取本 run 全量事件并投影到 memory。
  - 当前 `_run_to_store` 已承担 orchestration、event append、context compact retry、memory projection trigger、
    result projection、diagnostic cache 等职责；P6 必须拆出新增 durable / projection 职责。
- `dayu/host/_conversation_memory.py`
  - 定义 `ConversationMemoryStore` protocol 与 `InMemoryConversationMemoryStore`。
  - 当前 memory projection 从 canonical RunEvent 派生，服务 P3-P5 单进程多轮；不持久、不支持多进程 rebuild 真源。
- `dayu/host/_event_translation.py`
  - 负责 `EngineEvent -> RunEventDraft` 与 Host-owned failure / context compact facts 构造。
  - 已做 framework `fetch_more` 参数、tool result truncation、final answer internal echo 的写 EventLog 前收敛。
- `dayu/host/contracts.py`
  - 当前 `RunState` 是最小状态：`CREATED / RUNNING / SUCCEEDED / FAILED / CANCELLED / SUSPENDED`。
  - `RunEvent` 已有 `RunEventCursor`、`RunEventKind`、`RunEventSource`、`RunEventType`、封闭 data union。
  - 未定义 durable storage record、global event position、projection checkpoint、observer status。

当前设计与总控依赖：

- `docs/host/migration-plan.md` 最新 P6 定义要求：durable facts、Run / Attempt 最小状态、atomic append /
  cursor allocation、projection checkpoint、最小 observer / sink protocol、audit / timeline / memory projection
  重建基础、observer retry / lag；明确不做 attempt lease / fencing、不落地 P7 tool trace schema。
- P5.5 总控判断固定：P6 先建立 durable facts 与最小 observer / sink 基础；P7 再做正式 tool trace；P8
  才做 attempt ownership；P9 再固定 lifecycle 与 public interface。
- `docs/host/design.md` 第 9 节要求 EventLog 是 Run append-only 事实账本，不是 EventBus；observer 默认消费
  EventLog 而不是进程内 EngineEvent iterator。
- `docs/host/design.md` 第 12 节要求 Conversation Memory / RunInputBuilder 属于 Host，Engine 只消费最终 messages；
  reasoning / preview 不能回流运行态。
- `docs/engine/design.md` 明确 Engine 不负责 Host 持久化治理、trace store、memory、audit、ToolRuntime 或
  lifecycle；P6 不能把 Host durable / projection / trace / memory / governance 回流 Engine。
- P16 freeze 约束要求最终 full-governance smoke 后才冻结 Engine / Host public contracts。P6 可以新增 Host
  internal contracts 与必要 public smoke 入口，但不能把临时实现口径写成最终冻结接口。

依赖顺序：

```text
P1.5 Minimal EventLog
  -> P2 ToolRuntime facts
  -> P3 Conversation Memory / RunInputBuilder
  -> P4 Context Compact
  -> P5 No-Full-Governance Smoke
  -> P5.5 Deferred Scope Reconciliation
  -> P6 Durable EventLog / Run State / Projection
  -> P7 Tool Trace Projection / Sink
  -> P8 Attempt Lease / Recovery
  -> P9 Session / Run Lifecycle Governance
```

## 4. 设计边界和关键决策

### 4.1 Durable EventLog 是 P1.5 契约的生产实现，不是第二事实源

P6 应新增或替换为 durable `RunEventStore` 实现，但必须保留现有 protocol 语义：

- `append(draft) -> RunEvent` 后才允许 stream / observer 看到事件。
- `RunEventCursor` 继续表示单个 run 内严格单调 cursor，`stream_run_events(after=cursor)` 继续是 exclusive。
- Engine sequence 不能成为 Host cursor 真源。
- terminal event 之后禁止继续 append 普通 RunEvent；如果实施 Agent 认为某些 projection 状态需要 terminal 后写入，
  应写入 projection / checkpoint 表，不得追加新的 RunEvent 篡改 run 事实。

### 4.2 新增内部全局 event position 支撑 observer

P1.5 的 per-run cursor 适合 `stream_run_events(run_id, after=...)`，但 observer / projection 需要跨 run 消费。
P6 应新增 internal `event_position` 或等价全局单调位置：

- `RunEvent.cursor` 对外仍是 per-run cursor。
- durable table 内部记录 `event_position`，作为 projection checkpoint 的主消费位置。
- 不把 `event_position` 暗示成 public RunEventCursor；若未来 public 需要跨 session timeline cursor，应在对应
  phase 单独设计。

### 4.3 P6 最小持久状态只服务 reconcile，不承担 P9 admission

P6 可以新增 durable `RunRecord` 与 `AttemptRecord`，但只用于：

- run 创建事实、当前最小状态、terminal cursor / event position、result snapshot reconcile。
- attempt index / attempt id / 最小状态，用于 context compact retry、projection 关联和 P8 前置数据模型。
- startup 后重建 projection 与发现 incomplete run 的诊断状态。

P6 不用这些状态实现同 Session active Run 仲裁、`client_request_id` 幂等、取消治理或 attempt owner 判断。这些必须留给
P8 / P9。

### 4.4 Observer / sink 是 durable projection protocol，不是 MQ 框架

P6 observer 最小形态应是 Host 内部可显式调用的 projection runner：

- 读取 durable EventLog 中 checkpoint 之后的事件。
- 按 observer id 与 schema version 幂等写入 sink / read model。
- 成功后更新 checkpoint。
- 失败时记录 error / retry_count / next retry hint / lag。

不做完整消费者框架。P6 不需要后台常驻 worker、复杂 claim / lease、分区 rebalance、DLQ 或跨服务 ack。多进程同一
observer 的并发执行只需通过 checkpoint 事务边界与唯一键保证幂等；完整 observer claim / lease 可后移到证明必要的
phase。

### 4.5 Required 与 best-effort projection 必须显式

P6 不要求所有 observer hard-gate，但不能让实现隐式混乱。建议分类：

- required projection：RunResult / Run state reconcile、P6 需要的 memory read model 更新或 rebuild 检查。它们失败时
  必须可观察，并由调用方或 harness 明确等待 / drain / reconcile。
- best-effort projection：audit 示例、timeline 示例、P7 前 tool trace 示例基础、metrics 诊断。它们默认不阻塞 Run
  terminal。

如果实施 Agent 需要让某个 observer 阻塞 Run terminal，必须在该 observer contract 中显式标记 `required=True`，
并补状态机、失败收口和测试；禁止通过在 `_run_to_store` 里同步调用一堆 sink 来形成隐式 hard-gate。

### 4.6 Storage backend 选择

当前项目没有现成数据库依赖。P6 实施 Agent 应先检查是否已有 workspace storage / init 约定；若没有明确更高层真源，
推荐使用标准库 `sqlite3` 作为本地 durable backend，并使用 WAL / transaction / unique constraint 验证多进程语义。

选择 SQLite 的理由是：P6 需要本地 durable、多进程 append 与事务约束，不需要引入服务型数据库或消息队列。若实施
Agent 判断 SQLite 无法满足目标，必须在 plan 修订或实施说明中给出直接证据和替代方案，不得临时引入大依赖。

### 4.7 Host internal transaction owner / Unit of Work 是 P6 必做设计

P6 不能让 `LocalRunHarness` 或测试 harness 直接按顺序调用 durable EventLog、RunStateStore、AttemptStateStore、
ProjectionStore 的多个 `commit` 来“拼出”一致性。Host durable storage 必须有一个明确的 internal transaction owner：

- 若采用 SQLite，必须由同一 SQLite connection / transaction 承载 event append、cursor allocation、Run / Attempt
  minimal state、terminal result snapshot / reconcile 标记，以及 required projection 需要同事务推进的 checkpoint。
- 推荐新增 Host internal Unit of Work / transaction helper，或让 durable EventLog append 作为唯一事务 owner，并通过内部
  store writer 在该事务中完成 Run / Attempt state 写入。
- `RunStateStore` / `AttemptStateStore` / `ProjectionStore` 可以暴露独立查询协议，但它们的写入入口必须能接收 UoW /
  transaction context，或只能由事务 owner 调用内部 writer。
- 禁止 `_run_harness.py` 直接组合多个 store 写入并分别提交；harness 只能调用一个 append / reconcile / projection
  coordinator 入口。
- 故障注入测试必须证明 event row 插入后 state 更新前、state 更新后 terminal snapshot 前、sink 写入后 checkpoint
  前进前的异常都会回滚到可 replay / reconcile 的状态，不留下“事件已提交但状态不可调和”或“checkpoint 越过未写入
  sink”的状态。

这个 UoW 是 Host internal 基础设施，不属于 `dayu.runtime`，也不是 P8 attempt owner lease / fencing。它只解决 P6
durable facts 的共享事务边界。

### 4.8 Durable RunEventData 序列化策略必须在 P6 固定

P6 durable EventLog 不能把 `RunEvent.data` 降级为 `asdict`、开放 dict、任意 JSON payload 或字符串化内容。实施前必须
固定封闭 serializer registry：

- 以 `RunEventType -> RunEventData` 的封闭映射作为唯一真源，每个 event type 只能对应明确的强类型 data。
- 每条 durable event payload 必须记录 `schema_version` 与稳定 type discriminator；schema version 变化仍按全新起库
  处理，不做旧库兼容读取。
- deserializer 遇到未知 `RunEventType`、未知 data type、缺失 schema version 或字段不匹配必须 fail-fast，不能静默
  返回空 payload、开放 dict 或 best-effort 字符串。
- serializer / deserializer 必须有 round-trip 测试覆盖当前所有 canonical / preview / Host-owned / Engine-sourced
  `RunEventData` 变体。
- 工具 schema 内的字面量字符串仍按项目编码约束例外处理；durable EventLog payload 不适用该例外。

## 5. 文件级改动清单

### 5.1 计划新增

- `dayu/host/_durable_event_store.py`
  - 实现 durable `RunEventStore`，复用 P1.5 protocol。
  - 负责事务内 per-run cursor allocation、internal global event position、event payload 序列化、terminal guard、
    replay、stream replay-then-follow 的 durable backend。
  - 若采用 SQLite，连接、事务、WAL、schema bootstrap 应封装在本模块或独立 storage module，不泄漏到 harness。

- `dayu/host/_run_state_store.py`
  - 定义并实现 Host internal `RunStateStore` / `AttemptStateStore` 最小协议。
  - 管理 Run / Attempt 最小持久状态与 terminal reconcile。
  - 不实现 admission、client_request_id 幂等、owner lease、fencing。

- `dayu/host/_projection_store.py`
  - 定义 projection checkpoint、observer status、projection lag 的 durable 存取协议与实现。
  - 提供 checkpoint compare-and-set / transaction helper，保证同一 observer 重复执行不会倒退。

- `dayu/host/_host_storage_transaction.py` 或等价 internal module
  - 定义 Host durable Unit of Work / transaction context。
  - 在同一 connection / transaction 中协调 EventLog append、cursor allocation、Run / Attempt minimal state、
    terminal result snapshot / reconcile 标记，以及需要同事务提交的 sink / checkpoint 写入。
  - 只作为 Host internal 基础设施，不进入 public export，不放入 `dayu.runtime`。

- `dayu/host/_event_observer.py`
  - 定义最小 observer / sink protocol、projection batch runner、retry policy、lag 计算。
  - observer 入参应是已 append 的 durable event envelope，不是 EngineEvent iterator。
  - 不包含 P7 tool trace schema。

- `dayu/host/_timeline_projection.py`
  - 最小 timeline read model 示例 / 基础实现。
  - 只消费 client-visible 或 display-allowed RunEvent；reasoning 只能作为展示字段，不进入 RunInputBuilder。
  - 若实现范围需要压缩，可只提供 rebuild/query 的内部结构与测试，不扩展 public API。

- `dayu/host/_audit_projection.py`
  - 最小 audit 示例 sink，证明 observer / checkpoint / retry / lag protocol 可支撑治理事件。
  - 不实现 audit hard-gate，不定义完整合规保留策略。

- `dayu/host/_memory_projection.py`
  - 将当前 terminal 后 `_project_run_events` 触发的 in-memory 投影迁到明确 projection 边界。
  - 支持从 durable EventLog 全量 rebuild `ConversationMemoryStore` 或 durable memory read model。
  - 可复用 `_conversation_memory.py` 的投影规则，但不能把 observer dispatch 塞回 `_conversation_memory.py`。

- `tests/host/test_phase6_durable_event_store.py`
  - 覆盖 durable append、per-run cursor、global event position、exclusive replay、terminal guard、append-before-stream、
    `RunEventData` serializer round-trip 与 unknown type fail-fast。

- `tests/host/test_phase6_durable_event_concurrency.py`
  - 覆盖多连接 / 多进程或多 worker 并发 append，同一 run cursor 不重复、不乱序，跨 run global position 不重复。

- `tests/host/test_phase6_run_state_store.py`
  - 覆盖 Run / Attempt 最小状态创建、状态更新、terminal reconcile、部分写入恢复判断。

- `tests/host/test_phase6_host_storage_transaction.py`
  - 覆盖 Host internal UoW / transaction owner 的同事务写入边界。
  - 注入 event 插入后 state 更新前、state 更新后 terminal snapshot 前、sink 写入后 checkpoint 前进前的异常，
    验证回滚 / reconcile 结果。

- `tests/host/test_phase6_projection_checkpoint.py`
  - 覆盖 checkpoint 前进、不能倒退、重复消费幂等、失败记录、retry_count、lag。

- `tests/host/test_phase6_projection_rebuild.py`
  - 覆盖 timeline / audit 示例 projection rebuild。

- `tests/host/test_phase6_memory_rebuild.py`
  - 覆盖从 durable EventLog rebuild memory read model，证明不依赖 `LocalRunHarness` 进程内缓存。
  - 覆盖 Engine `RUN_FAILED`、Host-owned failure、cancelled、suspended 等非成功终态，至少保证
    `USER_INPUT_ACCEPTED` 不丢失，并验证 terminal summary 进入 / 不进入 memory 的 P6 规则。

- `tests/host/test_phase6_observer_retry_lag.py`
  - 覆盖 observer 失败、重试、lag 计算、恢复后继续 checkpoint。

- `utils/smoke_host_p6_durable_eventlog.py`
  - P6 必须新增的手工 smoke。P5 已用 `utils/smoke_host_multiturn_no_governance.py` 建立
    no-full-governance 纵向基线；P6 新增 durable EventLog / Run state / projection 治理能力后，
    必须提供对应 smoke，让用户通过日志和关键摘要观察 durable append / replay / projection /
    observer checkpoint / rebuild 路径。
  - smoke 不替代单元 / 并发 / 恢复测试，不依赖联网模型，不打印 delta、大 event payload、scope token
    或内部大块 prompt。

### 5.2 计划修改

- `dayu/host/contracts.py`
  - 新增 Host internal 所需强类型：durable event identity、global event position、projection checkpoint、
    observer status、observer lag、最小 Run / Attempt record data。
  - 若这些类型不应进入 public `dayu.host.__all__`，可保留为 internal contracts 或放在新 internal module。
  - 所有新增签名必须强类型，禁止 `Any`、`object`、开放 dict、无类型参数。
  - P6 若触及本文件，必须同步修正 `StartRunRequest` 附近“创建幂等与同 Session active Run 仲裁在 P7 落地”的旧注释，
    将阶段口径改为 P9；这只修正文档口径，不改变生产接口语义。
  - 即使 P6 实施未触及该 dataclass，也必须增加 grep / review 检查，避免 `contracts.py` 继续把 lifecycle 幂等误标为
    P7。

- `dayu/host/_event_store.py`
  - 保留 `RunEventStore` protocol 作为共同契约。
  - 允许 `InMemoryRunEventStore` 继续服务小单元测试，但 README / design 必须写明它不是 P6 durable 默认。
  - 若 protocol 需要增加 durable observer 查询方法，应避免污染 public stream 契约；可以新增 separate protocol。

- `dayu/host/_run_harness.py`
  - 只做装配调整：注入 durable event store、run state store、projection coordinator。
  - `_run_to_store` 只能继续负责 run orchestration 主流程；新增 projection drain / checkpoint / rebuild 应委托
    `_event_observer.py` / `_memory_projection.py` 等模块。
  - 删除或收窄 `_project_run_events` 的职责，使它变成调用 projection coordinator 的薄入口，或迁走。
  - 不在本文件新增 schema SQL、checkpoint 逻辑、observer retry 循环、timeline / audit sink 实现。

- `dayu/host/_conversation_memory.py`
  - 保留 memory 数据结构与投影规则。
  - 如需 durable read model，可新增实现或适配器；不得让 memory store 直接读取 EngineEvent 或绕过 EventLog。
  - 不加入 public memory edit / reset / forget。

- `dayu/host/_event_translation.py`
  - 仅当 durable append 需要 stable append id / attempt id / provenance 扩展时修改。
  - 不新增 trace schema，不把 observer 逻辑放入翻译层。

- `dayu/host/__init__.py`
  - 只导出当前 Run 级必要 public surface。
  - P6 不固定最终 Host public interface；除非 smoke 必需，不新增最终态 public API。

- `dayu/host/README.md`
  - P6 代码落地后更新当前事实：durable EventLog、Run / Attempt 最小状态、projection checkpoint、
    observer / sink 最小基础、仍未落地 P7/P8/P9。

- `docs/host/design.md`
  - P6 代码落地后写回当前事实：durable EventLog schema 语义、global event position 内部边界、
    observer checkpoint、memory / timeline / audit projection rebuild 能力。
  - 不把 P7 tool trace、P8 lease、P9 lifecycle 写成已落地。

- `tests/README.md`
  - P6 代码落地后补 Host durable / projection 测试分层与验证命令。

- 根目录 `README.md`
  - 因 P6 新增 `utils/` smoke，若该 smoke 是用户可运行入口，应补手工 smoke 命令与注意事项。

### 5.3 禁止修改或只读参考

- 禁止修改 `dayu/engine/*` 生产代码；P6 不能把 Host durable / projection / trace / memory / governance 回流 Engine。
- 禁止修改 `dayu/runtime/*` 来承载 EventLog、Run state、projection 或 Host governance 语义。
- 禁止修改 `dayu/fins/*` 实现财报业务存取；P6 不迁移业务工具。
- 禁止新增 P7 tool trace schema / sink 生产实现。
- 禁止修改 Service / UI 层装配来绕过 Host internal 边界。
- `docs/engine/design.md`、P1.5/P2/P3/P4/P5 plan、P5.5 plan、当前 Host 代码只读参考；除非 P6 实施后需要
  当前事实同步，不应修改历史 phase plan。

## 6. 状态机 / 数据模型

### 6.1 Durable EventLog

P6 durable EventLog 至少需要表达：

- `run_id`
- `session_id`
- per-run `cursor.sequence`
- internal `event_position`
- `kind`
- `source`
- `type`
- `occurred_at`
- typed data payload 的稳定 JSON 表达
- `source_engine_event_id`
- optional `attempt_id` / `attempt_index`
- created / stored timestamp
- stable append identity 或 idempotency key

约束：

- `(run_id, cursor.sequence)` 唯一。
- `event_position` 全局唯一且单调前进。
- Engine-sourced event 对同一 run 的 `source_engine_event_id` 应唯一；Host-owned event 需要等价 stable append identity，
  避免 retry 时重复写 terminal failure / compact facts。
- terminal event 只能出现一次，或必须有明确终态优先级与 reconcile 规则；P6 建议继续保持单 terminal guard。
- preview event 可以持久化，但 projection rebuild 的运行态 read model 不得依赖 preview 作为唯一事实。
- typed data payload 只能通过封闭 serializer registry 落库与读取；registry 必须覆盖当前 `RunEventType` 到
  `RunEventData` 的映射、`schema_version`、unknown type fail-fast 与全变体 round-trip 测试。
- 禁止使用 `asdict`、开放 dict、字符串化 payload、best-effort JSON dump 作为 durable payload 真源。

### 6.2 Run / Attempt 最小持久状态

Run 最小状态建议：

```text
CREATED
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
LOST_DIAGNOSTIC
```

说明：

- `LOST_DIAGNOSTIC` 若实现，仅表示 P6 startup / reconcile 发现 EventLog 与 Run state 不一致，需要人工或后续 P8/P9
  策略处理；它不是完整 P9 public `LOST` 治理。
- P6 不实现 `QUEUED / RECOVERING / CANCELLING / WAITING` 的完整 lifecycle admission。

Run record 最小字段：

- `run_id`
- `session_id`
- `state`
- `created_at`
- `updated_at`
- `terminal_event_cursor`
- `terminal_event_position`
- optional `result_snapshot_ref` 或内联最小 `RunResult` snapshot

Attempt 最小状态建议：

```text
CREATED
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STALE_DIAGNOSTIC
```

Attempt record 最小字段：

- `attempt_id`
- `run_id`
- `attempt_index`
- `state`
- `started_at`
- `finished_at`
- `terminal_event_position`
- `failure_summary`

P6 不包含：

- `owner_id`
- `lease_token`
- `fencing_token`
- lease expiry / heartbeat
- owner stale cleanup

若为了 P8 数据模型预留字段，可以在 schema review 中明确为 nullable / unused，并不得在 P6 逻辑中伪造 owner 语义。

### 6.3 Projection Checkpoint

Projection checkpoint 最小字段：

- `observer_id`
- `projection_name`
- `schema_version`
- `last_success_position`
- `last_attempted_position`
- `status`
- `retry_count`
- `last_error_code`
- `last_error_message`
- `last_success_at`
- `updated_at`
- `lag_events`

状态建议：

```text
IDLE
RUNNING
RETRYABLE_FAILED
BLOCKED_FAILED
CAUGHT_UP
DISABLED
```

约束：

- checkpoint 只能前进，不能倒退。
- observer sink 写入与 checkpoint 前进必须在同一事务，或使用可证明的幂等 reconcile 机制。
- schema version 改变时必须能选择 rebuild；P6 不做旧 schema 兼容升级。

### 6.4 Observer / Sink 最小协议

Observer protocol 应表达：

- stable `observer_id`
- `projection_name`
- `schema_version`
- subscribed event kind / visibility / type filter
- `required` 标记
- `process(batch) -> projection result`
- retry policy

Sink protocol 应表达：

- 幂等写入 key，例如 `(observer_id, event_position)` 或 read model 自身唯一键。
- 写入成功后可安全重复执行。
- 不反向调用 Engine，不直接消费 EngineEvent iterator。

P6 最小 observer：

- `memory_projection_observer`：从 durable EventLog rebuild 或增量更新 memory read model。
- `timeline_projection_observer`：从 client-visible / display-allowed facts 生成最小 timeline read model。
- `audit_projection_observer`：从治理 facts 生成最小 audit 示例记录，验证 checkpoint / retry / lag。

P7 才新增正式 `tool_trace_observer` 与 tool trace sink schema。

### 6.5 Memory projection 的非成功终态语义

P6 memory rebuild 必须以 durable EventLog canonical facts 为真源，并固定非成功终态的最小语义：

- 任意 run 只要存在 canonical `USER_INPUT_ACCEPTED`，rebuild 后对应用户输入不得丢失；这不依赖 run 是否成功。
- 成功终态按 P3-P5 已有规则投影 assistant final answer，但 final answer 不自动升级为 verified claim。
- Engine `RUN_FAILED` 与 Host-owned failure 必须写入中性 terminal summary，summary 只能包含可展示的失败类别 /
  摘要，不能包含 stack、内部 prompt、scope token、cursor 原文或大工具结果。
- cancelled 在 P6 不写 assistant terminal summary；memory 只保留用户输入。取消治理与 public cancel 语义留到 P9。
- suspended 在 P6 不写 assistant terminal summary；memory 只保留用户输入。wait / suspend / resume 协作语义留到 P14。
- timeline / audit projection 可以记录 cancelled / suspended 的终态事实；这些展示 / 治理事实不得回流
  RunInputBuilder。

如果实施 Agent 发现当前 EventLog 无法区分 Engine failure、Host-owned failure、cancelled、suspended，必须先补强
Host internal 强类型事件或形成专项 plan 修订；不能在 rebuild 中用字符串猜测终态。

## 7. 并发与一致性

### 7.1 Atomic Append

P6 append 必须通过 Host internal transaction owner / Unit of Work 在单个持久事务中完成：

1. 校验 draft provenance。
2. 校验 run 未 terminal。
3. 分配 per-run cursor。
4. 分配 internal global event position。
5. 插入 event row。
6. 必要时更新 Run / Attempt 最小状态。
7. terminal 时写入 terminal cursor / position / result snapshot 或可 reconcile 标记。
8. commit 后再通知本进程订阅者。

事务失败时不能通知订阅者，不能留下只有通知没有事实的窗口。

UoW 的可执行接口必须保证：

- EventLog append、cursor allocation、Run / Attempt minimal state、terminal result snapshot / reconcile 标记共享同一
  connection / transaction。
- required projection 若需要阻塞 terminal，其 sink 写入和 checkpoint 前进也必须进入同一 UoW，或给出等价事务 helper
  与幂等 reconcile 证据。
- `LocalRunHarness` 不能先 append event 再单独调用 state store commit；也不能由测试 harness 绕过 UoW 组合多个
  store commit 来制造“通过”的假象。
- commit 后才能发布本进程订阅通知；rollback 后 subscriber、observer、projection 都不能看到未提交事实。

### 7.2 Cursor / Sequence 唯一

P6 必须用数据库约束或等价跨进程协调保证：

- 同一 run 下 cursor sequence 唯一且严格递增。
- 全局 event position 唯一且严格递增。
- 同一 Engine source event 不重复 append。
- terminal event 不重复 append。

不能依赖单进程 `asyncio.Lock`、`Condition` 或进程内 dict 维护 cursor 正确性。

### 7.3 事务边界

如果使用 SQLite，实施 Agent 应优先使用明确事务边界，例如 `BEGIN IMMEDIATE` 或等价写锁策略，并用唯一约束验证并发。
如果使用其它 backend，也必须在测试中证明同一 run 多进程 append 不会分配重复 cursor。

Run terminal 收敛至少要保证：

- terminal canonical RunEvent 与 Run state 可调和。
- 若 RunResult snapshot 与 terminal event 分表，事务中断后有 reconciler 能从 EventLog 补齐或标记诊断失败。
- Host 自身 append / projection 错误不能伪装成 worker / proxy failure。

故障注入必须覆盖：

- event row 插入成功后、Run / Attempt state 更新前抛错。
- Run / Attempt state 更新成功后、terminal snapshot / reconcile 标记写入前抛错。
- required sink 写入成功后、checkpoint 前进前抛错。
- subscriber 通知前抛错。

每个场景都必须验证数据库中没有半提交状态，或存在明确可由 EventLog 真源补齐的 diagnostic / reconcile 状态。

### 7.4 Checkpoint 幂等

Projection runner 需要满足 at-least-once：

- observer 可能重复看到同一 event。
- sink 写入必须幂等。
- checkpoint 在 sink 成功后前进。
- 如果 sink 成功但 checkpoint 失败，下一次重复消费不能产生重复 read model。
- 如果 checkpoint 成功但 sink 未成功，这是严重一致性错误；实现应通过事务避免该状态，或在 code review 中给出
  reconcile 证据。

### 7.5 P6 不做 attempt owner lease / fencing

P6 必须明确停止在以下边界：

- 不判断哪个进程拥有 attempt。
- 不拒绝旧 owner 迟到写入；因为 owner token / fencing 尚未落地。
- 不做 orphan / stale attempt 自动恢复。
- 不把 observer checkpoint 的并发控制伪装成 attempt lease。

若测试需要多进程 append，可直接测试 storage append 并发，不测试“同一个 attempt 只有一个 owner 写入”的语义。

## 8. LocalRunHarness 防 God Object 分解策略

P6 实施必须先拆职责边界，再接 durable 能力。`LocalRunHarness` 当前已经承担较多职责；P6 不能继续膨胀。

允许 `LocalRunHarness` 保留：

- `start_run` ingress 编排。
- 调用 RunInputBuilder 构造 Engine request。
- 调用 WorkerProxy 消费 EngineEvent。
- 调用 EventStore append。
- 根据 terminal 结果触发 projection coordinator 的明确入口。

必须迁出或不得新增到 `LocalRunHarness`：

- durable schema bootstrap / SQL / connection lifecycle。
- cursor allocation 细节。
- Run / Attempt state persistence 细节。
- observer scan / dispatch / retry loop。
- checkpoint CAS / lag 计算。
- timeline / audit / memory read model 写入规则。
- projection rebuild 全流程。
- smoke 输出格式。

建议新增装配关系：

```text
LocalRunHarness
  -> RunOrchestrator-like methods already present in harness
  -> RunEventStore
  -> RunStateStore
  -> ProjectionCoordinator
      -> ObserverRunner
      -> MemoryProjection
      -> TimelineProjection
      -> AuditProjection
```

如果实施中发现 `_run_harness.py` 修改超过装配与薄委托，应停下来做架构专项 review，不要把“先跑通”作为继续堆职责的理由。

## 9. 测试清单

### 9.1 单元测试

- durable store schema bootstrap / fresh DB 初始化。
- `RunEventDraft` provenance 校验沿用 P1.5 行为。
- append 后返回 `RunEvent` 带 per-run cursor。
- `list_events(after=cursor)` exclusive 语义。
- terminal guard。
- Engine-sourced event id / Host append id 去重。
- Run / Attempt minimal state 更新与 terminal reconcile。
- Host internal UoW 中 EventLog append、cursor allocation、Run / Attempt state、terminal snapshot / reconcile 同事务提交。
- `RunEventData` serializer registry 覆盖全部当前 data 变体，unknown event type / schema version fail-fast。
- projection checkpoint 前进、不能倒退、schema version 分离。

### 9.2 并发测试

- 同一 run 多连接并发 append，cursor 不重复、不跳回。
- 多 run 并发 append，global event position 不重复。
- terminal append 与普通 append 竞争时，terminal 后普通 append 被拒绝或按明确顺序收口。
- observer 重复运行同一 batch，不重复写 sink。

### 9.3 恢复 / replay

- 关闭并重建 store client 后，可 replay 已 append 事件。
- Run terminal state 可从 terminal RunEvent reconcile。
- result snapshot 缺失时可从 terminal event 补齐或标记诊断状态。
- incomplete run 在 P6 只报告诊断，不自动 lease / recover。
- `contracts.py` 中 `StartRunRequest` docstring 不再把创建幂等与同 Session active Run 仲裁标为 P7；grep 检查应确认
  lifecycle 幂等口径指向 P9。

### 9.4 Projection rebuild

- 从空 projection 表开始 rebuild timeline 示例。
- 从空 audit 示例 sink 开始 rebuild。
- schema version 改变后可选择 rebuild，不读旧 schema 做兼容。
- preview / reasoning 只进入允许的 display read model，不进入 memory / RunInputBuilder。

### 9.5 Memory read model rebuild

- 从 durable EventLog rebuild `ConversationMemorySnapshot`。
- tool truncate / fetch_more facts 只以中性摘要进入 memory，不含 `scope_token`、cursor 原文、大结果。
- assistant final answer 不自动升级为 verified claim。
- 不同 session memory 不串读。
- compact retry 同一 run 不重复投影 `USER_INPUT_ACCEPTED`。
- Engine `RUN_FAILED` rebuild 后保留用户输入，并写入中性 terminal summary。
- Host-owned failure rebuild 后保留用户输入，并写入中性 terminal summary。
- cancelled rebuild 后保留用户输入，且 P6 不写 assistant terminal summary。
- suspended rebuild 后保留用户输入，且 P6 不写 assistant terminal summary。

### 9.6 Observer checkpoint / retry

- observer sink 故障时 checkpoint 不前进。
- 故障记录 `RETRYABLE_FAILED`、retry_count、last_error。
- 修复 sink 后从原 checkpoint 重试并 catch up。
- lag 能根据 latest event position 与 checkpoint 计算。

### 9.7 边界测试

- Engine 不 import Host durable / projection 模块。
- Host public API 不导出 durable implementation、observer runner、sink 实现。
- `dayu.runtime` 不 import Host / Engine，也不承载 EventLog / projection 语义。
- P6 不新增 tool trace schema public exports。

### 9.8 验证命令

实施完成后至少运行：

```bash
source .venv/bin/activate
pytest tests/host/test_phase6_durable_event_store.py \
  tests/host/test_phase6_durable_event_concurrency.py \
  tests/host/test_phase6_host_storage_transaction.py \
  tests/host/test_phase6_run_state_store.py \
  tests/host/test_phase6_projection_checkpoint.py \
  tests/host/test_phase6_projection_rebuild.py \
  tests/host/test_phase6_memory_rebuild.py \
  tests/host/test_phase6_observer_retry_lag.py
! rg -n "完整创建幂等与同 Session active Run 仲裁在 P7|client_request_id.*P7" dayu/host/contracts.py
pyright
```

如果 P6 修改了 P1.5-P5 主路径，还必须补跑受影响旧测试，例如：

```bash
source .venv/bin/activate
pytest tests/host/test_phase1_5_event_store.py \
  tests/host/test_phase1_5_run_harness_eventlog.py \
  tests/host/test_phase2_tool_runtime_eventlog.py \
  tests/host/test_phase3_conversation_memory_projection.py \
  tests/host/test_phase3_multiturn_smoke.py \
  tests/host/test_phase4_overflow_retry.py \
  tests/host/test_phase5_multiturn_no_governance_smoke.py
pyright
```

## 10. 手工 smoke

P6 必须新增 `utils/smoke_host_p6_durable_eventlog.py`。从 P6 开始，每新增一项 Host 治理能力，都必须
有对应 `utils/` 手工 smoke；P6 smoke 是 durable facts / projection 治理能力的观察入口。

smoke 目标：

- 使用临时 workspace / DB 路径初始化 durable Host store。
- 追加一组 canonical / preview / terminal RunEvent，输出 run_id、per-run cursor、global position、event type。
- 关闭并重新打开 store，replay 同一 run，输出 replay count 与 terminal state。
- 运行 memory / timeline / audit 示例 projection，输出 observer_id、schema_version、checkpoint、lag、projected rows。
- 注入一个可控失败 observer，展示 retry_count / last_error / checkpoint 未前进。
- 修复 observer 后重新 drain，展示 checkpoint 前进与 lag 归零。
- 输出必须能看清 P6 新增治理能力的执行路径：append transaction、event position、projection
  checkpoint、observer retry、rebuild。输出只打印摘要，不打印大块 payload。

输出要求：

- 不打印大块 delta、大工具结果、scope token、cursor 原文或内部 prompt。
- 每个阶段输出 1-3 行摘要，便于人工观察，不刷屏。
- 缺少可选真实 provider 配置不应影响 P6 smoke；P6 smoke 应以 durable storage / projection 为主，不依赖联网模型。

示例输出字段：

```text
storage_path=...
append run_id=... cursor=0 position=1 type=user_input_accepted
append run_id=... cursor=3 position=4 type=final_answer terminal=true
replay run_id=... count=4 terminal_state=succeeded
projection observer=memory schema=1 checkpoint=4 lag=0 rows=...
projection observer=audit schema=1 status=retryable_failed checkpoint=2 retry_count=1
projection observer=audit schema=1 status=caught_up checkpoint=4 lag=0
```

## 11. README / docs 同步触发判断

P6 plan 本身只新增 `docs/host/phase6-plan.md`，不要求同步 README。

P6 代码实施完成后，按触发规则判断：

- 修改 `dayu/host/`：必须检查并更新 `dayu/host/README.md`，只写已落地的 durable EventLog、Run / Attempt 最小状态、
  projection checkpoint、observer 基础与未落地 P7/P8/P9。
- 修改 Host 架构事实：必须更新 `docs/host/design.md` 对 EventLog / projection / memory rebuild 的当前事实描述。
- 新增 / 修改 `tests/host/`：必须检查并更新 `tests/README.md` 的 Host durable / projection 测试分层与命令。
- 新增 `utils/smoke_host_p6_durable_eventlog.py`：如果作为用户可运行 smoke，必须检查根目录 `README.md` 是否需要补命令。
- 不修改 `docs/engine/design.md`，除非发现文档存在与当前 Engine 边界相冲突的错误；不能借 P6 写 Engine 未来能力。
- 不维护“近期更新”“版本记录”，不把 P7+ 能力写成已落地事实。

## 12. 风险、待确认项、停止条件、实施完成汇报格式

### 12.1 风险

- SQLite / 本地 durable backend 的并发语义若实现不严谨，可能只在单进程测试通过，多进程下 cursor 重复。
- projection checkpoint 若不与 sink 写入同事务，可能出现重复投影或 checkpoint 越过未写入数据。
- `LocalRunHarness` 已经偏大，P6 若不拆 projection coordinator，会形成 God Object。
- durable EventLog payload 序列化若使用开放 dict，容易绕过强类型 contract。
- memory rebuild 若误读 preview / reasoning，会污染 RunInputBuilder。
- P6 若提前引入 observer worker / claim / lease，可能与 P8 attempt lease 概念混淆。

### 12.2 待确认项

- 当前项目是否已有总控认可的 workspace DB 初始化入口；若没有，P6 是否接受 Host internal schema bootstrap 作为临时新库起点。
- P6 durable backend 是否固定 SQLite，还是由总控指定其它 workspace storage。
- memory read model 在 P6 是否必须 durable 落库，还是允许由 durable EventLog rebuild 到 in-memory store 后服务 smoke。
  若目标是多进程共享 memory，建议至少提供 durable read model 或可跨进程读取的 projection store。
- P6 是否需要 public diagnostic API 查询 observer lag，或仅通过 internal helper / smoke / tests 验证。

### 12.3 停止条件

实施 Agent 遇到以下情况必须停下来修 plan 或请求总控判断：

- 需要修改 Engine 生产代码才能完成 P6。
- 需要把 trace schema、ToolTraceRecorder 或 JSONL trace store 作为 P6 正式能力落地。
- durable append 无法用事务 / unique constraint 证明多进程 cursor 唯一。
- observer checkpoint 无法做到 sink 写入与 checkpoint 前进一致。
- durable `RunEventData` 只能靠开放 dict、`asdict` 或字符串化 payload 才能落库。
- 需要实现 attempt owner lease / fencing 才能让 P6 测试通过。
- 需要把 observer / sink 扩展成完整 MQ consumer 框架。
- 需要旧库兼容读取、兼容迁移或兼容测试。
- `_run_harness.py` 成为 durable schema / observer / projection 的主要实现载体。
- pyright 需要通过 `Any`、`object`、无类型返回或 ignore 掩盖新增错误。

### 12.4 实施完成汇报格式

实施 Agent 完成后按以下格式汇报：

```text
改动概览：
- ...

关键设计取舍：
- durable EventLog backend：...
- Run / Attempt 最小状态：...
- observer / checkpoint：...
- P6 明确未做：...

验证：
- pytest ...
- pyright
- smoke ...

README / docs：
- 已更新 ...
- 判断无需更新 ...

风险与未覆盖：
- ...
```

## 13. Review gate

P6 进入代码实施前必须先做 plan review。建议 review gate：

- plan review：检查本 plan 是否与 `docs/host/migration-plan.md` 最新 P6、P5.5 总控判断、P16 freeze 约束一致。
- 架构边界专项 review：重点审 Host / Engine 边界、`dayu.runtime` 边界、LocalRunHarness 防 God Object、P7/P8/P9
  是否被提前实现。
- 并发 / 一致性专项 review：重点审 atomic append、cursor allocation、terminal guard、checkpoint 幂等、
  observer retry / lag。
- 必要 OLD / NEW review：只对照 OLD tool trace / conversation memory / durable trace 思路中可作为素材的部分，
  不要求 P6 迁回 OLD trace schema。

代码实施后必须由总控给 code review prompt，用户手工派 review Agent 执行；总控 Agent 不替代用户人工 review。
若 review finding 成立，修复 Agent 必须在对应 review 文档 finding 标题标注修复状态，并经复审通过后才能进入用户
人工确认与 PR 流程。
