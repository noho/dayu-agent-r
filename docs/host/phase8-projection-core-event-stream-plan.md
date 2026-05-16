# Host Phase 8 Projection Core / Host Event Stream / Minimal Read Model Plan

- **当前 gate**: Phase 8 plan fix，等待 plan re-review
- **工作单元**: Projection Core / Host Event Stream / Minimal Read Model
- **计划状态**: plan-fix complete，等待 MiMo / DS re-review
- **blocking question 数量**: 0
- **artifact path**: `docs/host/phase8-projection-core-event-stream-plan.md`

本文档是 Gateflow-governed handoff plan。implementation agent 只能按本文档指定的 contract、文件边界、slice、测试和 stop condition 实施；不得重新设计 Host / Engine 分层、command path 状态机、Run / Attempt governance truth、Memory、Recovery、Audit、Tool Trace、Outbox、Service / UI channel delivery 或 Remote 协议。

## 1. 目标 / 动机 / 非目标

### 1.1 目标

Phase 8 落地 committed EventLog 消费基座、projection checkpoint、Host event stream 的 EventLog cursor truth，以及最小 RunResult / Session timeline read model 和可重建 repair path。

本 phase 只让 projection 读取已提交 EventLog 并维护 projection-owned 派生表。Projection lag、projection failure、stream fanout 慢客户端或 read model 损坏，不得影响 EventLog append、Run terminal、resume、memory truth、RunInputBuilder 或 Host command path 成功条件。

### 1.2 动机有效性

动机成立，严重性没有被高估。

直接原因是当前 Host 已有 EventLog、public read API、ToolRuntime、waiting / resume 等治理路径，但后续 Memory、Recovery 观察、Audit / Tool Trace / Outbox sinks 如果各自临时实现 EventLog replay、checkpoint、失败重试和 rebuild，会产生不一致 cursor 语义和反向 truth 风险。Phase 8 需要先固定公共的 committed EventLog consumer framework 与最小可重建 read model，使后续 phase 复用同一个 checkpoint / idempotency / failure invariant。

### 1.3 设计锚点

- `docs/host/design.md` §14：Observer / Sink 只消费 committed EventLog，按 `event_sequence` checkpoint 追平，按 canonical `event_id` 幂等消费；Sink failure 只能更新 sink-local retry / error state，不能回滚 EventLog 或改变 Run / Attempt。
- `docs/host/design.md` §16：EventLog 是真源；RunResult、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot、outbox 都是 read model 或 projection；投影损坏或缺失时必须能从 EventLog 重建。
- `docs/host/implementation-control.md` Phase 8：允许修改 projection runner、checkpoint store、typed consumer contract、stream fanout 基础、Host event stream、timeline / RunResult 最小 read model；明确排除 `LogAuditSink(JSONL)`、tool trace hot / cold、OutboxSink、外部 audit 系统和 channel delivery exactly-once。
- `docs/reviews/host-phase8-design-discussion-controller-adjudication-20260516.md`：Phase 8 design discussion PASS；plan 必须固定 typed consumer contract、checkpoint schema、Host event stream cursor truth、stream fanout non-truth boundary、minimal read model schema、repair helper、per-slice files/tests/pyright/README/stop conditions。

### 1.4 成功信号

- Projection runner 能按全局 `event_sequence` 从 checkpoint 后重放 committed EventLog rows，并按 consumer 声明的 event filter 调用 typed consumer。
- Checkpoint 只在 consumer-owned projection 写入与幂等记录成功后推进；失败不推进 checkpoint。
- 重复扫描同一 `event_id` 不重复插入 RunResult、Session timeline item 或其它 Phase 8 projection row。
- Consumer failure 只写 projection-local failure state，不回滚 EventLog，不更新 Run / Attempt / wait / dispatch / admission truth。
- `stream_run_events` 继续只从 EventLog `event_sequence` cursor 补读；过滤后空结果仍按扫描窗口推进 `next_cursor`；无新 row 时保持输入 cursor。
- Stream fanout 如被实现，只能是 wakeup / attached-client optimization；断线补读和 cursor correctness 不依赖 fanout。
- Minimal RunResult 能从 terminal canonical facts 重建；Session timeline 能表达多条独立 `USER_INPUT_ACCEPTED`，包括已取消输入和后续新输入。
- 删除或清空 Phase 8 minimal read model 后，内部 repair helper 能从 EventLog replay 恢复一致 projection。
- Projection checkpoint advance 与对应 projection writes 必须在同一个 `HostTransactionRunner` 管理的 Host durable transaction 内提交；consumer 幂等 upsert 只能防御 replay，不能替代事务原子性。
- Phase 9 Memory 可以复用 consumer / checkpoint framework，但不需要读取 Session timeline 或 RunResult 作为 memory truth。

### 1.5 非目标

Phase 8 不做以下事项：

- 不实现 `LogAuditSink(JSONL)`、audit policy、外部 audit 系统或 audit 查询。
- 不实现 tool trace hot JSON / cold JSONL、trace analyze 支持或 provider request id trace 投影。
- 不实现 OutboxSink、outbox delivery queue、terminal delivery retry、channel delivery exactly-once、seen cursor 存储或 UI / Service 投递状态。
- 不实现 Memory snapshot、Conversation Memory policy、RunInputBuilder memory provider、memory lag threshold 或 memory repair。
- 不实现 Recovery scan、orphan proof、Attempt takeover、从 projection 恢复 Run / Attempt truth。
- 不修改 Engine、Engine contracts、WorkerProxy / RemoteProxy / RemoteStub wire protocol。
- 不修改 command path 状态机、Run / Attempt governance state、wait record state、dispatch state、admission / cancel / resume terminal transaction 语义。
- 不把 terminal transaction 同步写 outbox 表，也不让 command path 同步执行慢 projection。
- 不创建兼容旧 schema 的读取、迁移、wrapper、facade 或 re-export；schema 变更按 fresh DB 起库处理。

## 2. 公共 / 私有契约决策

### 2.1 Public API 表面

Phase 8 不新增面向 Service / UI 的 public command API。`stream_run_events`、`get_run`、`get_session` 仍是 public read surface，且 `stream_run_events` 的 truth 保持为 EventLog read path。

允许在 `dayu.host.api` 中新增或扩展只读 snapshot / read model 类型，但必须满足以下限制：

- 只能新增稳定、强类型、frozen / slots dataclass 或 `StrEnum`。
- 不得使用 `Any`、`object`、裸 `dict` / `list` / `tuple` / `set` / `frozenset` 注解。
- 不得把 projection runner、checkpoint row、durable table row 或 repair internals 导出到 `dayu.host.__all__`。
- `RunSnapshot` / `SessionSnapshot` 的治理字段仍来自 Host durable truth；read model 只能补充终态摘要或 timeline cursor / item 查询，不得覆盖 active Run、queued Runs、Run status 或 Attempt state。

第一版建议不新增 public timeline API。Minimal Session timeline 先作为 Host internal read model 和后续 Service/UI owner 的稳定基座；若 implementation agent 认为必须新增 `read_session_timeline(...)` public facade，必须停止并交回 controller，因为当前 design / control truth 未授权该 public API 扩面。

### 2.2 Host 内部契约

新增 projection core 是 `dayu.host` 内部基础能力，不属于 `dayu.runtime`。它可以被 Phase 9 Memory 和 Phase 13 sinks 复用，但不得下放到 `dayu.runtime`，因为 checkpoint、EventLog cursor 和 Host event classes 都是 Host 语义。

核心 internal contract 固定如下：

- `ProjectionConsumerId(value: str)`：稳定 consumer id，非空，建议 ASCII `[A-Za-z0-9_.:-]`，长度上限使用模块级常量。
- `ProjectionEventClassFilter(event_class: EventClass, event_types: tuple[str, ...] | None)`：声明单个 event class 的 type filter。`event_types=None` 表示该 class 下全部类型；非 `None` 时 tuple 必须非空，表示只消费该 class 下列出的 event type。
- `ProjectionEventFilter(class_filters: tuple[ProjectionEventClassFilter, ...])`：声明 consumer 消费哪些 event class / type。`class_filters` 必须非空，同一个 `EventClass` 不得重复声明；匹配语义是各 class filter 之间 OR、单个 class filter 内 `event_class` 与 `event_type` AND。每个 event class 独立决定消费全部类型或指定类型，不存在跨 class 共享的全局 `event_types`。默认 consumer 只能选择 `canonical_fact`，除非明确声明 preview / diagnostic / projection_signal。
- `ProjectionEventView`：从 `EventLogRow` 映射出的 typed input view，字段至少包含 `event_sequence`、`event_id`、`event_class`、`event_type`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`occurred_at`、`payload_ref`、`payload_digest`、`payload: Mapping[str, JsonValue]`。payload 必须由 `dayu.host._event_payload.payload_object` 解析；禁止把 raw JSON string 或 untyped bag 传给 consumer。
- `ProjectionApplyResult`：consumer 处理单 event 的结果，至少区分 `APPLIED`、`SKIPPED`、`DUPLICATE`。结果中可携带 `idempotency_key: str` 和 `detail_code: str | None`，不得携带无结构 payload。
- `ProjectionConsumer` Protocol：暴露 `consumer_id`、`event_filter`、`apply_event(transaction, event) -> ProjectionApplyResult`。consumer 可以在同一个 Host transaction 内写 projection-owned tables；不得调用 command transition / admission / recovery / Run / Attempt mutator。
- `ProjectionRunner`：构造时必须接收现有 `HostTransactionRunner` 和 concrete consumers，由 `HostCommandHandle` 或后续 composition root 通过 private dependency 注入；不得自建 SQLite connection，不得持有或调用 public command facade。runner 读取 checkpoint 后的 EventLog rows，按 `event_sequence` 升序过滤并调用 consumer；consumer apply 成功后，在同一个 `HostTransactionRunner.run_write()` Host durable transaction 内写 projection rows 并推进 checkpoint；异常时记录 projection-local failure 并停止当前 batch。

Phase 8 不强制接入 after-commit wakeup，也不要求 command / dispatch path 自动追平 read model。自动追平 owner 明确 deferred 给 Phase 9 Conversation Memory composition：Phase 9 可以把 terminal transaction after-commit hook 接到 runner wakeup port，但该 hook 只能触发 wakeup，不能在 terminal transaction 内运行 projection。Phase 8 的交付物是可复用 runner、checkpoint / failure store、minimal read model consumer 与 repair primitive。

不引入 global untyped dispatcher，也不允许所有 sinks 共享一个“Event payload dict”。每个 concrete consumer 必须在自身模块把 `ProjectionEventView` 解码成自己的 typed projection row。

### 2.3 Host Event Stream Cursor 真源

`HostStreamCursor.event_sequence` 是 `stream_run_events` 的唯一 cursor truth。`projection_checkpoint`、session-local cursor、client sequence、fanout queue offset 或内存订阅位置都不能替代它。

Implementation 可以重构 `dayu/host/read_api.py` 中的 event stream reader，但必须保留 Phase 4 contract：

- `limit` 表示本次扫描的全局 EventLog row 窗口，不是只返回目标 Run event 的数量。
- 与目标 Run 无关的 row 被扫描时，`next_cursor` 必须推进到本次扫描窗口最后一个 `event_sequence`。
- 没有扫描到任何 row 时，`next_cursor` 等于输入 cursor。
- `stream_run_events` 不触发 Engine dispatch、不启动 projection rebuild、不调用 fanout、不写 projection table。

### 2.4 Stream Fanout 非真源边界

Phase 8 的 fanout / wakeup 只允许作为可选 non-truth optimization；本计划不要求创建 fanout shell，也不把 wakeup 作为 Phase 8 correctness 或成功信号：

- fanout 只能通知“可能有新 EventLog row”，不得分配 cursor。
- fanout 丢消息、慢客户端、listener 关闭或进程重启，只能导致 attached client 体验变慢；客户端必须能用 `event_sequence` cursor 从 EventLog 补读。
- fanout 不得写 EventLog、Run / Attempt、projection checkpoint 或 read model truth。
- 如果后续 approved owner 新增 wakeup port，必须证明它只在 commit 后触发通知，不运行 projection transaction，不改变 `stream_run_events`、repair 或 checkpoint 语义。
- 如果 implementation 发现需要维护 per-client delivery ack、seen terminal cursor、channel retry 或离线补投状态，必须停止并交回 controller；这些属于 Service / UI 或 Phase 13 Outbox owner。

### 2.5 Minimal Read Model Scope

Minimal RunResult / Session timeline 只服务 Host internal read path 和后续上层读取，不是治理真源。

RunResult 第一版只投影 terminal canonical event：

- terminal event identity：`terminal_event_id`、`terminal_event_sequence`。
- `run_id`、`session_id`、terminal `RunStatus`。
- terminal summary refs：优先使用 terminal closeout 已写入的 EventLog payload descriptor / typed payload 字段；不得假设 `host_runs` 当前已有 `terminal_summary_ref` / `terminal_summary_digest` 列，也不得 ad hoc 解析 raw 字符串。
- `result_ref` / `result_digest` 可以等同 terminal event 的 `payload_ref` / `payload_digest`，但不得使用 final answer 文本作为 identity 或 dedupe key。

Session timeline 第一版只投影最小 item：

- `timeline_item_id` 使用 source `event_id`。
- `session_id`、`run_id | None`、`event_id`、`event_sequence`、`event_type`。
- `item_kind` 至少覆盖 user input、run lifecycle、attempt lifecycle、tool fact、wait lifecycle、terminal、diagnostic summary；具体 enum 可更细，但不得把 UI 展示形态写死。
- 可选 `display_text` 只允许从 typed `USER_INPUT_ACCEPTED` payload 的 `display_text` 字段读取；其它事件不得从 raw payload 任意拼展示文本。
- `payload_ref` / `payload_digest` 保留为 refs，不复制大 payload。

Session timeline 必须保留每条 `USER_INPUT_ACCEPTED` 独立 item。取消输入与后续新输入是两条不同 EventLog facts，不得按文本或 session position 合并为 edit。

P8-S3 payload stop check：implementation agent 必须确认 `USER_INPUT_ACCEPTED` 的 typed payload 是否包含 `display_text` 字段。若不存在，timeline consumer 不得从 raw payload、JSON 字符串或其它展示字段拼接文本；应保留 `payload_ref` / `payload_digest`，并将 nullable `display_text` 写为 NULL，同时用测试覆盖该行为。

## 3. Schema / 表变更

当前 `HOST_SCHEMA_VERSION` 为 `4`。Phase 8 implementation 必须将 fresh schema version bump 到 `5`。若 plan review 或 implementation 前 schema version 已变化，implementation agent 必须停止并交回 controller，不得静默猜测版本。

所有新增表属于 projection / read model owner，不是 Host governance truth。它们不得被 admission、cancel、resume、RunInputBuilder、Recovery 或 memory truth 读取为状态迁移依据。

P8-S1 schema stop check：implementation agent 必须先确认 `event_log(event_sequence)` 是否满足 SQLite foreign key parent key 要求，也就是该列是 PRIMARY KEY 或受 UNIQUE 约束保护。若不满足，必须在 Phase 8 schema bump 内补齐唯一约束 / 唯一索引，或改用符合 SQLite FK 规则且仍保留 `event_sequence` 查询索引的 schema 方案，并新增 durable schema 测试覆盖 FK 可创建、可校验和无效引用会失败；不得留下无效 FK DDL。

### 3.1 Projection Checkpoint 表

新增 `host_projection_checkpoints`：

```sql
CREATE TABLE IF NOT EXISTS host_projection_checkpoints (
  consumer_id TEXT PRIMARY KEY,
  checkpoint_event_sequence INTEGER NOT NULL CHECK (checkpoint_event_sequence >= 0),
  checkpoint_event_id TEXT NULL,
  last_success_at TEXT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(checkpoint_event_id) REFERENCES event_log(event_id),
  CHECK (
    (checkpoint_event_sequence = 0 AND checkpoint_event_id IS NULL)
    OR
    (checkpoint_event_sequence > 0 AND checkpoint_event_id IS NOT NULL)
  )
)
```

不变量：

- `checkpoint_event_sequence=0` 表示从头开始 replay。
- checkpoint 必须在 consumer projection writes 成功后推进。
- checkpoint 不得超过已经成功处理并提交的 EventLog row。
- checkpoint 不表达 EventLog truth，也不参与 resume / memory / recovery 事实判断。

### 3.2 Projection Failure 表

新增 `host_projection_failures`：

```sql
CREATE TABLE IF NOT EXISTS host_projection_failures (
  consumer_id TEXT PRIMARY KEY,
  failed_event_sequence INTEGER NOT NULL CHECK (failed_event_sequence > 0),
  failed_event_id TEXT NOT NULL,
  failure_count INTEGER NOT NULL CHECK (failure_count > 0),
  last_error_code TEXT NOT NULL,
  last_error_message TEXT NOT NULL,
  first_failed_at TEXT NOT NULL,
  last_failed_at TEXT NOT NULL,
  retry_after TEXT NULL,
  FOREIGN KEY(failed_event_id) REFERENCES event_log(event_id)
)
```

不变量：

- failure row 是 projection-local diagnostic / retry state。
- 写 failure row 不推进 checkpoint。
- 同一 consumer 后续成功处理失败 event 并推进 checkpoint 后，必须清除或标记该 failure row 为 resolved；第一版建议直接 delete failure row。
- failure row 不得被 command path 读取，不得改变 Run / Attempt。

### 3.3 Minimal RunResult 表

新增 `host_run_results`：

```sql
CREATE TABLE IF NOT EXISTS host_run_results (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  terminal_status TEXT NOT NULL CHECK (
    terminal_status IN ('succeeded', 'failed', 'cancelled', 'lost')
  ),
  terminal_event_id TEXT NOT NULL UNIQUE,
  terminal_event_sequence INTEGER NOT NULL,
  result_ref TEXT NULL,
  result_digest TEXT NULL,
  summary_ref TEXT NULL,
  summary_digest TEXT NULL,
  projected_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES host_runs(run_id),
  FOREIGN KEY(session_id) REFERENCES host_sessions(session_id),
  FOREIGN KEY(terminal_event_id) REFERENCES event_log(event_id),
  FOREIGN KEY(terminal_event_sequence) REFERENCES event_log(event_sequence),
  CHECK (
    (result_ref IS NULL AND result_digest IS NULL)
    OR
    (result_ref IS NOT NULL AND result_digest IS NOT NULL)
  ),
  CHECK (
    (summary_ref IS NULL AND summary_digest IS NULL)
    OR
    (summary_ref IS NOT NULL AND summary_digest IS NOT NULL)
  )
)
```

索引：

- `host_run_results_session_terminal_sequence` on `(session_id, terminal_event_sequence)`。

幂等：

- RunResult consumer 必须先按 `run_id` 读取既有 row。
- 若 row 不存在，插入新的 terminal row。
- 若 row 存在且 `terminal_event_id` 与 `terminal_event_sequence` 均匹配当前 terminal event，返回 duplicate / no-op。
- 若 row 存在但 `terminal_event_id` 或 `terminal_event_sequence` 与当前 terminal event 不同，必须 raise projection error，记录 projection failure，且 checkpoint 不推进。
- 禁止使用 `INSERT OR REPLACE`，也禁止使用会静默覆盖 `terminal_event_id` / `terminal_event_sequence` 的 `ON CONFLICT(run_id) DO UPDATE`。
- Duplicate `terminal_event_id` replay returns duplicate / no-op。
- Different terminal event for same `run_id` indicates EventLog / projection invariant violation; consumer must raise projection error and not advance checkpoint.

### 3.4 Minimal Session Timeline 表

新增 `host_session_timeline_items`：

```sql
CREATE TABLE IF NOT EXISTS host_session_timeline_items (
  timeline_item_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT NULL,
  event_id TEXT NOT NULL UNIQUE,
  event_sequence INTEGER NOT NULL,
  item_kind TEXT NOT NULL,
  event_type TEXT NOT NULL,
  display_text TEXT NULL,
  payload_ref TEXT NULL,
  payload_digest TEXT NULL,
  projected_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES host_sessions(session_id),
  FOREIGN KEY(run_id) REFERENCES host_runs(run_id),
  FOREIGN KEY(event_id) REFERENCES event_log(event_id),
  FOREIGN KEY(event_sequence) REFERENCES event_log(event_sequence),
  CHECK (
    (payload_ref IS NULL AND payload_digest IS NULL)
    OR
    (payload_ref IS NOT NULL AND payload_digest IS NOT NULL)
  )
)
```

索引：

- `host_session_timeline_items_session_sequence` on `(session_id, event_sequence)`。
- `host_session_timeline_items_run_sequence` on `(run_id, event_sequence)` where `run_id IS NOT NULL`。

幂等：

- `timeline_item_id` 必须等于 source `event_id` 或由 `event_id` 稳定派生。
- Duplicate event replay 必须 no-op。
- 不得用 display text、run-local index 或 client request order 作为主键。

## 4. 建议模块 / 文件

### 4.1 后续实现允许修改的生产文件

- `dayu/host/api.py`
  - 仅在需要新增 public read model enum / dataclass 时修改。
  - 不导出 projection runner / checkpoint / durable rows。
- `dayu/host/__init__.py`
  - 仅当 `api.py` 新增 public read type 时同步 package root export。
  - 不导出 internal projection core。
- `dayu/host/durable/schema.py`
  - 增加 Phase 8 projection / read model tables、indexes、`HOST_SCHEMA_VERSION` bump。
- `dayu/host/durable/projection.py` new
  - checkpoint row codec / store、failure row codec / store、transaction-scoped helpers。
- `dayu/host/durable/read_model.py` new
  - `RunResultRow`、`SessionTimelineItemRow`、upsert / read / delete / rebuild primitives。
- `dayu/host/projection.py` new
  - `ProjectionConsumerId`、`ProjectionEventClassFilter`、`ProjectionEventFilter`、`ProjectionEventView`、`ProjectionApplyResult`、`ProjectionConsumer` Protocol、`ProjectionRunner`。
- `dayu/host/read_model.py` new
  - minimal read model concrete consumer、EventLog event -> RunResult / SessionTimeline typed mapping、internal `repair_minimal_read_models(...)` helper。
- `dayu/host/read_api.py`
  - 保持 `stream_run_events` EventLog-backed；可让 `get_run` / internal read helpers 优先读取 RunResult projection 补充 terminal summary，但 active / queued / status truth 仍来自 durable Run / Session rows。
- `dayu/host/_event_payload.py`
  - 只允许补充 typed payload helper，例如读取 `USER_INPUT_ACCEPTED.display_text`、terminal summary refs；不得加入 UI 展示逻辑。
- `dayu/host/README.md`
  - implementation 完成后按触发规则同步 Host read model / event stream / projection boundary。

### 4.2 后续实现允许修改的测试文件

- `tests/host/test_projection_checkpoint.py` new
- `tests/host/test_projection_runner.py` new
- `tests/host/test_projection_read_model.py` new
- `tests/host/test_public_event_stream.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `tests/README.md`
  - 仅在新增测试分层 / 命令说明发生事实变化时更新。

### 4.3 明确禁止修改的文件 / 模块

- `dayu/engine/**`
- `dayu/runtime/**`
- `dayu/service/**`
- `dayu/ui/**`
- `dayu/fins/**`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/admission.py`
- `dayu/host/waiting.py`
- Audit / Tool Trace / Outbox concrete sink modules、JSONL writer、delivery queue。

## 5. Checkpoint / 幂等 / 失败不变量

1. EventLog append 与 Run terminal transaction 是 upstream truth；projection runner 只能在 commit 后读取。
2. Projection checkpoint 的 cursor 是 `event_sequence`，幂等 identity 是 canonical `event_id`。
3. Checkpoint advance 与对应 projection writes 必须处于同一个 `HostTransactionRunner.run_write()` 管理的 Host durable transaction。第一版禁止用“等价原子性”替代同事务提交，禁止引入第二套 transaction abstraction。
4. Consumer apply 成功但 checkpoint 写失败时，后续 replay 会重复调用 consumer；consumer 必须依赖 `event_id` / terminal identity upsert 保证幂等，但幂等 upsert 只能作为 replay 防御，不能替代第 3 条的同事务原子性。
5. Consumer apply 失败时，runner 必须写 `host_projection_failures`，不得推进 checkpoint。
6. Projection failure 不得回滚 EventLog，不得更新 Run / Attempt / wait / dispatch state，不得阻止 terminal closeout 或 queue promotion。
7. Projection lag 不得改变 `stream_run_events` 结果，因为 stream 直接读 EventLog。
8. Minimal read model stale / missing 时，public `get_run` / `get_session` 可以降级使用 durable state snapshot；不得为了补齐 projection 在 read API 内同步重建。
9. Repair helper 可以清空 Phase 8 projection rows 并从 EventLog replay；repair 失败只留下 projection 缺失 / lag，不能污染 Host truth。
10. Projection modules 不得 import command transition service、admission service、recovery internals、waiting CAS mutators、dispatch mutators或 Engine contracts。

## 6. Minimal Rebuild / Repair 路径

新增 internal helper，建议签名：

```python
def repair_minimal_read_models(
    transaction_runner: HostTransactionRunner,
    *,
    reset_checkpoint: bool,
    batch_size: int,
) -> ProjectionRepairResult:
    ...
```

要求：

- 该 helper 位于 `dayu.host.read_model`，不是 public package root export。
- 该 helper 只接收 `HostTransactionRunner` 或由它构造的 `ProjectionRunner`，不得持有 `HostCommandHandle` public command facade。若后续 composition 需要从 handle 暴露 repair 入口，只能由 handle 的 private dependency 把现有 transaction runner 传入 helper。
- `batch_size` 必须大于 0，默认值如需要应使用模块级常量，不得在循环内硬编码魔法数字。
- `reset_checkpoint=True` 时，repair 必须两阶段执行：第一阶段只用一个短 `HostTransactionRunner.run_write()` transaction 删除 `host_run_results`、`host_session_timeline_items`、minimal read model consumer checkpoint 与 failure row；该 transaction 提交后，第二阶段从 cursor 0 replay。
- `reset_checkpoint=False` 时，从当前 checkpoint catch up。
- replay 必须按 `batch_size` 分批执行，每批使用独立 `HostTransactionRunner.run_write()` transaction，并在同一批 transaction 内写 projection rows 与推进 checkpoint。
- replay 中途失败时，已提交批次的 checkpoint 必须保留在最后成功 cursor；下一次 repair 从 checkpoint 继续，不得要求重新执行全量 reset，也不得把全量 replay 放进单个长 write transaction。
- `ProjectionRepairResult` 必须强类型，至少包含 `consumer_id`、`started_cursor`、`finished_cursor`、`events_scanned`、`events_applied`、`duplicates`、`failures`。
- 不提供 CLI / admin surface；Phase 15 production hardening owner 决定是否暴露维护命令。
- Repair 不得读取 Session timeline 或 RunResult 作为输入，只能读取 EventLog 和必要 durable Run / Session rows 做 referential validation。

## 7. 实施切片

### P8-S1 Projection Runner / Checkpoint / Typed Consumer Contracts

目标：建立 committed EventLog replay consumer 基础，包含 checkpoint / failure store、typed consumer protocol 和 runner。

允许文件：

- `dayu/host/durable/schema.py`
- `dayu/host/durable/projection.py`
- `dayu/host/projection.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `tests/README.md` only if test docs need factual sync

允许变更：

- Add `host_projection_checkpoints` and `host_projection_failures` DDL / table constants / indexes if needed.
- Bump fresh schema version from 4 to 5.
- Add checkpoint row dataclasses and row codec functions with Chinese docstrings.
- Add read / initialize / advance checkpoint helpers.
- Add write / clear failure helpers.
- Add `ProjectionEventClassFilter`、`ProjectionEventFilter`、`ProjectionConsumer` typed Protocol and `ProjectionRunner`.
- Add per-class event filter logic using `EventClass` / event type strings. Tests must cover multiple event classes where one class consumes all types and another consumes only specified types.
- Add `ProjectionEventView` builder from `EventLogRow` and typed payload parser.
- Construct `ProjectionRunner` with an injected `HostTransactionRunner`; runner must not open its own SQLite connection and must not depend on `HostCommandHandle` public command methods.

非目标：

- Do not implement RunResult / Session timeline projection in this slice.
- Do not modify `stream_run_events`.
- Do not add Audit / Tool Trace / Outbox consumers.
- Do not wire runner into background supervisor, command path or dispatch path in Phase 8.

测试：

- Schema test: fresh bootstrap creates checkpoint / failure tables, `PRAGMA user_version=5`, constraints reject negative checkpoint and invalid failure count.
- Schema test: `event_log(event_sequence)` is a valid SQLite FK target for Phase 8 tables, or schema uses an explicitly tested compliant FK / index alternative.
- Checkpoint test: missing checkpoint initializes to cursor 0; advance after event sequence N persists event id and timestamp; advancing backwards is rejected.
- Runner test: event filter calls consumer only for matching committed events and in ascending `event_sequence` order.
- Runner filter test: per-class filters handle multi-class + type combinations without applying one class's `event_types` to another class.
- Runner transaction test: consumer projection writes and checkpoint advance commit in the same `HostTransactionRunner` transaction; a consumer write failure leaves checkpoint unchanged.
- Runner idempotency test: consumer duplicate result still allows checkpoint advance when projection store reports duplicate.
- Failure test: consumer exception writes failure row and does not advance checkpoint; second successful run from same cursor clears failure row.
- Boundary test: projection modules do not import Engine / Service / UI / Fins / runtime business layers, and do not import admission / waiting / recovery mutator modules.
- Weak typing guard remains green.

验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```

完成信号：

- Runner can replay committed EventLog rows with a fake typed consumer.
- Checkpoint / failure invariants are covered by tests.
- No production code outside allowed files changed.

停止条件：

- If implementing runner requires changing command path transactions, Run / Attempt state mutators, Engine contracts or `dayu.runtime`, stop and return to controller.
- If a generic untyped payload dispatcher appears necessary, stop and return to controller.
- If `event_log(event_sequence)` cannot be used as a SQLite FK target and no compliant schema/index alternative can be kept inside Phase 8 schema scope, stop and return to controller.

### P8-S2 Host Event Stream Cursor Truth / Fanout Boundary

目标：把 `stream_run_events` 固定为 EventLog-backed read path，并防止 fanout / projection checkpoint 成为 stream truth。

允许文件：

- `dayu/host/read_api.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `dayu/host/README.md` only after implementation validation, if Host README current event stream boundary becomes stale

允许变更：

- Preserve or strengthen `stream_run_events(host, run_id, cursor, limit)` semantics from Phase 4.
- Add tests proving projection checkpoint lag / failure does not affect `stream_run_events`.
- Do not add fanout / wakeup implementation in P8-S2. This slice only proves `stream_run_events` correctness is independent from projection, notification and read model side effects.
- Do not change `HostEventStream` public shape unless controller approves a public contract change.

非目标：

- Do not implement WebSocket / SSE / GUI / CLI delivery.
- Do not store client seen cursors.
- Do not read `host_projection_checkpoints` in `stream_run_events`.
- Do not read `host_session_timeline_items` in `stream_run_events`.
- Do not create placeholder fanout modules or disabled notification shells just to satisfy tests.

测试：

- Existing Phase 4 stream tests remain green.
- New test: manually set projection checkpoint behind EventLog; `stream_run_events` still returns all matching EventLog rows after input cursor.
- New test: projection failure row exists; `stream_run_events` still returns EventLog rows and correct `next_cursor`.
- New test: `stream_run_events` correctness does not depend on projection or notification side effects.
- New test: `stream_run_events` does not invoke projection repair or write projection tables.

验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_public_event_stream.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```

完成信号：

- Host event stream correctness is proven to depend only on EventLog cursor.
- No fanout / wakeup code is required for this slice; if such code is later added by an approved owner, it remains wakeup-only and not exported as truth.

停止条件：

- If implementation wants to replace EventLog cursor with projection cursor or fanout offset, stop.
- If implementation needs Service / UI channel delivery state, stop.
- If passing P8-S2 tests appears to require creating a fanout shell, stop and rename/reshape the test around EventLog-backed stream correctness instead.

### P8-S3 Minimal RunResult / Session Timeline Read Model / Repair

目标：实现 minimal read model consumer 和真实的内部 rebuild / repair helper。

允许文件：

- `dayu/host/api.py` only for read model enum / result dataclass if strictly needed
- `dayu/host/__init__.py` only if `api.py` adds public type exports
- `dayu/host/durable/schema.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/read_model.py`
- `dayu/host/read_api.py`
- `dayu/host/_event_payload.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `dayu/host/README.md`
- `tests/README.md` only if new test files / command examples must be documented

允许变更：

- Add `host_run_results` and `host_session_timeline_items` DDL / row codecs / stores.
- Add `MinimalReadModelProjectionConsumer` using `ProjectionConsumer`.
- Map terminal event types `RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST` to RunResult.
- Map timeline item events from committed EventLog. First version should include `USER_INPUT_ACCEPTED` and Run lifecycle / terminal canonical facts; additional known canonical facts may be included if typed mapping is explicit.
- Add internal `repair_minimal_read_models(...)` helper and `ProjectionRepairResult`.
- Inject the same `HostTransactionRunner` used by `ProjectionRunner` into repair; repair must not call public command methods or create its own SQLite connection.
- Optionally update `get_run` to use `host_run_results` for terminal summary refs while preserving durable Run status truth.
- Optionally update internal session timeline read helper; do not add public timeline facade without controller approval.

非目标：

- Do not build a full UI chat transcript.
- Do not fold cancelled input into later input.
- Do not implement outbox item derivation.
- Do not implement memory snapshot or recovery scan.

测试：

- Terminal EventLog -> `host_run_results` row with stable terminal event identity, status and result / summary refs.
- Duplicate terminal event replay -> no duplicate RunResult.
- Conflicting terminal event for same Run -> projection failure, checkpoint not advanced.
- RunResult conflict test must prove no `INSERT OR REPLACE` or silent `ON CONFLICT(run_id) DO UPDATE` overwrite occurs when terminal identity differs.
- `USER_INPUT_ACCEPTED` events produce distinct timeline items even when display text repeats.
- `USER_INPUT_ACCEPTED` without typed `display_text` keeps `display_text` NULL and preserves refs; timeline consumer must not synthesize display text from raw payload.
- Cancelled Run input and later new input remain two separate timeline rows.
- Deleting `host_run_results` / `host_session_timeline_items` and resetting checkpoint, then running repair, rebuilds the same rows from EventLog.
- Repair batch test: `reset_checkpoint=True` performs a short reset transaction, then replays in multiple `batch_size` transactions; if a later batch fails, the next repair resumes from the last committed checkpoint.
- Projection stale / missing read model does not affect `stream_run_events` and does not change `RunSnapshot.status`.
- `get_run` fallback behavior remains stable when RunResult projection is missing.
- Package export tests updated only if new public read type is added.

验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```

完成信号：

- Minimal read model can be built, replayed idempotently and rebuilt after deletion.
- Public read API truth boundaries remain unchanged.
- README decision executed.

停止条件：

- If timeline requirements expand into UI display product semantics, stop and return to controller.
- If repair needs to read projection as input truth, stop.
- If RunResult is needed by resume / memory / recovery truth path in Phase 8, stop.
- If `USER_INPUT_ACCEPTED` payload lacks typed `display_text`, do not parse raw payload text or invent display text; keep refs and nullable `display_text` instead.

## 8. README 同步决策

本计划文件本身只是 planning artifact，不触发 README 同步。

后续 implementation 会修改 `dayu/host/` 和 tests，因此 implementation gate 的 README 决策如下：

- Update `dayu/host/README.md` after tests pass, but only for current Host development manual facts: projection core boundary, EventLog-backed stream cursor, minimal read model rebuild, and explicit non-goals for Audit / Tool Trace / Outbox / Memory / Recovery.
- Update `tests/README.md` only if new test files or command examples change the documented Host test layering.
- Do not update root `README.md` unless user-visible CLI / trace / render / configuration entry points change. Phase 8 should not change them.
- Do not update `dayu/README.md` unless implementation changes layer relationships or assembly boundaries. Phase 8 should not.

## 9. Import / Boundary Guard 要求

Implementation must add or update guard tests so the following remain enforced:

- `dayu.host.projection`, `dayu.host.read_model`, `dayu.host.durable.projection`, `dayu.host.durable.read_model` do not import `dayu.engine`, `dayu.service`, `dayu.ui`, `dayu.fins` or `dayu.config`.
- Projection modules do not import `dayu.host.admission`, `dayu.host.waiting`, `dayu.host.engine_ingest`, `dayu.host.dispatch` mutator internals, or recovery internals. Reading `dayu.host.durable.event_log`, `dayu.host.durable.transaction`, `dayu.host.durable.projection`, `dayu.host.durable.read_model` is allowed.
- `dayu.runtime` remains untouched and must not import Host.
- No new annotation uses `Any` / `object` / missing types / bare builtin generics.
- No explicit request or contract field is hidden in `metadata` / `extra payload`.
- No lazy import unless implementation documents a concrete cycle or optional dependency reason and plan review accepts it.
- No compatibility re-export / facade / wrapper for old paths.

## 10. 风险 / 后置 owner

- Phase 9 owner：Conversation Memory projection、memory snapshot cursor、RunInputBuilder memory provider、memory lag repair。Phase 8 only provides reusable consumer / checkpoint foundation.
- Phase 11 owner：Recovery scan、orphan proof、Run / Attempt recovery。Recovery must read Host durable truth and EventLog canonical facts, not RunResult / timeline projection.
- Phase 13 owner：Audit、Tool Trace、Outbox concrete sinks、JSONL writer、delivery queue、sink-specific retry policy。Phase 8 only reserves reusable typed consumer contract.
- Phase 15 owner：production hardening、admin rebuild CLI / tooling、purge cleanup matrix for projection / outbox / tool trace / audit hot data。
- Service / UI owner：channel delivery、client seen cursor、offline notification display dedupe、Web / CLI / GUI / WeChat ack state。

残余风险：

- Generic runner may drift toward untyped event bus. Mitigation: plan review must block `Any` / `object` / raw payload dispatcher.
- A repair helper that only exists in tests would leave no real recovery primitive. Mitigation: P8-S3 requires production internal helper.
- Stream fanout can accidentally become a hidden truth. Mitigation: P8-S2 tests must prove `stream_run_events` ignores projection checkpoint / fanout state.
- Checkpoint + projection writes share one SQLite transaction, so long consumers can hold write locks. Mitigation: Phase 8 consumer must keep work small and local; Audit / Tool Trace / Outbox heavy sinks remain Phase 13.
- Automatic after-commit projection catch-up is deferred. Owner: Phase 9 Conversation Memory composition; Phase 8 must leave a reusable `ProjectionRunner` / repair primitive and must not make read API correctness depend on automatic wakeup.

## 11. Phase 8 完整实现的精确验证命令

Implementation agents 必须按 slice 运行受影响测试。进入 aggregate review 前运行：

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/host tests/host
git diff --check
```

如果 implementation 修改了 Host internal 之外的共享 public contract 或 package export，还必须运行：

```bash
source .venv/bin/activate
pytest tests/contracts tests/host -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

进入 code review 前的预期结果：

- All selected pytest commands pass.
- `python -m pyright dayu/host tests/host` reports 0 errors.
- No new or expanded pyright errors in touched scope.
- `git diff --check` is clean.
- README sync decision is executed and documented in implementation artifact.

## 12. Plan Review 标准

Plan review 必须把以下情况视为 blocking finding：

- Consumer boundary uses `Any`、`object`、raw `dict` payload bag or untyped callback.
- Projection checkpoint, RunResult, Session timeline, fanout or failure row is described as Host governance truth.
- Any slice modifies Engine, Service, UI, Fins, `dayu.runtime`, command path state machine, Run / Attempt mutators or Recovery internals without explicit controller approval.
- `stream_run_events` reads projection checkpoint / fanout / timeline instead of EventLog.
- Read model rebuild exists only in test fixture.
- Slice ownership is too broad or allows implementation agent to also build Audit / Tool Trace / Outbox concrete sinks.
- Tests only appear at final aggregate stage rather than per slice.

## 13. Implementation Report 格式

每个 slice implementation artifact 必须报告：

- Gate and slice id.
- Approved plan path.
- Changed files.
- Implemented plan items.
- Explicit non-goals kept out.
- 验证命令与结果。
- README sync decision.
- Residual risks classified as fixed in current slice, covered by later slice, assigned to later phase/work unit, tracked by issue, or requiring controller/user decision.
- Stop status: completed / blocked, with blocker evidence if blocked.

## 14. 当前 Planning Gate 状态

本计划已完成 Phase 8 plan fix，P8-PLAN-F1 至 P8-PLAN-F7 均已写回 plan。下一步应进入 MiMo / DS plan re-review gate；re-review 通过前不应进入 implementation。
