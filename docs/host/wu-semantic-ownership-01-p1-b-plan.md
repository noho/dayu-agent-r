# WU-SEMANTIC-OWNERSHIP-01 P1-B Plan

## 1. Goal / motivation / success signal

目标：为 `P1-B. Host event type and cancellation durable contract` 收敛两类 Host 语义真源：

- Run terminal / lifecycle event type、terminal status 与 public outbox terminal item set 不再由各消费者私有重复定义。
- `cancel_request_event_id` 不再从 `RUN_CANCELLING` payload JSON loose parsing 作为 active cancel critical linkage；改为 typed durable state 或等价 typed indexed relation。

第一性原理判断：问题仍真实存在，且严重性没有被高估。terminal event type 与 terminal status 属于 Host durable lifecycle contract；Outbox、Read Model、Tool Trace、Engine ingest 和 dispatch watchdog 都只能消费该 contract，不能各自定义 terminal 集合。active cancel linkage 决定 `RUN_CANCELLING` 后 cooperative worker terminal、watchdog closeout、recovery defer 和 dispatch diagnostic 是否能关联同一个用户取消事实；若该 link 只存在于 JSON payload 且靠 loose parsing 读取，就会形成“EventLog 看似有事实，但 durable state / recovery / projection 无 typed truth”的语义漂移。

成功信号：

- Host terminal helper 明确区分 Host terminal/lifecycle event set、public outbox terminal item event set、non-public terminal fact skip/diagnostic behavior。
- `RUN_LOST` 仍是 Host terminal/lifecycle fact 和 public HostEvent/read-model terminal，但不是 public outbox terminal item；Outbox public watermark / latest cursor 不因 `RUN_LOST` 要求存在 outbox item。
- active cancel closeout、watchdog、engine ingest、dispatch active cancel candidate、recovery accepted-cancel 判断均从 typed durable Run state 或 typed relation 读取 `cancel_request_event_id`。
- `RUN_CANCELLING` payload 可保留审计可读字段，但不再是 critical cancel linkage 真源。
- schema tests、cancel lifecycle tests、outbox/read model/tool trace/engine ingest/dispatch tests 和 pyright 通过；`git diff --check` 通过。

## 2. Current direct evidence

必须扫描已执行：

```bash
rg -n "RUN_SUCCEEDED|RUN_FAILED|RUN_CANCELLED|RUN_LOST|TERMINAL_EVENT|TERMINAL_STATUS|terminal event|terminal status|outbox terminal|RUN_CANCELLING|cancel_request_event_id|_cancel_request_event_id_from_cancelling" docs/host/design.md dayu/host tests/host
rg -n "request_active_attempt_cancel_in_transaction|mark_run_cancelling|RUN_CANCELLING|cancel_request_event_id|watchdog|active cancel" dayu/host tests/host
```

补充扫描已执行：

```bash
rg -n "P1-B|terminal|cancel" docs/host/wu-semantic-ownership-01-umbrella-plan.md docs/host/issues-implementation-control.md docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md
rg -n "RUN_LOST|outbox|terminal|cancel_request_event_id|RUN_CANCELLING" docs/host/design.md
rg -n "_TERMINAL_STATUS_BY_EVENT_TYPE|_TERMINAL_EVENT_TYPES|RUN_LOST|RUN_SUCCEEDED|RUN_FAILED|RUN_CANCELLED" dayu/host --glob '*.py'
```

直接证据：

- `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md` P1 accepted findings 指出 terminal event type strings 在 11+ production modules 重复、Outbox terminal status set 与 terminal event type set 对 `RUN_LOST` 不一致、`cancel_request_event_id` 只存在于 `RUN_CANCELLING` payload JSON。
- `docs/host/wu-semantic-ownership-01-umbrella-plan.md` P1-B 已裁决 `RUN_LOST` 是 Host terminal/lifecycle fact，不是 public outbox terminal item；若 `docs/host/design.md` 未写清，P1-B 必须先更新 design truth。
- `dayu/host/outbox.py` 私有 `_TERMINAL_EVENT_TYPES` 包含 `RUN_LOST`，但 `_TERMINAL_STATUS_BY_EVENT_TYPE` 只包含 succeeded/failed/cancelled；`apply_event()` 对 `RUN_LOST` 单独 skip。
- `dayu/host/durable/outbox.py` 的 `_latest_outbox_terminal_event_sequence()` 用 `_TERMINAL_EVENT_TYPES` 计算 latest terminal sequence，当前集合包含 `RUN_LOST`，这会把 public outbox watermark 与 non-public terminal fact 混在一起。
- `dayu/host/read_model.py` 私有 `_TERMINAL_STATUS_BY_EVENT_TYPE` 再次定义 succeeded/failed/cancelled/lost，且 `_TIMELINE_EVENT_TYPES` 复制 Run lifecycle / terminal strings。
- `dayu/host/tool_trace.py` 私有 `_CANONICAL_EVENT_TYPES` 再次复制 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST`。
- `dayu/host/engine_ingest.py`、`dayu/host/read_api.py`、`dayu/host/durable/run_transition.py` 等模块继续各自持有 Run terminal event type strings。
- `dayu/host/durable/schema.py` 的 `host_runs` 当前只有 `terminal_event_id` / `terminal_event_sequence`、`current_attempt_id` 等列，没有 typed `cancel_request_event_id`。
- `dayu/host/durable/state.py` 的 `RunRow` 没有 cancel linkage 字段；`mark_run_cancelling_row()` 只把 status 改为 `cancelling`，不写 cancel request link。
- `dayu/host/durable/run_transition.py` 的 `request_active_attempt_cancel_in_transaction()` append `CANCEL_REQUESTED` 与 `RUN_CANCELLING` 后调用 `mark_run_cancelling_row()`，但 `cancel_request_event_id` 只进入 `RUN_CANCELLING` payload。
- `dayu/host/durable/run_transition.py` 的 `active_cancel_watchdog_closeout_in_transaction()` 读取 latest `RUN_CANCELLING`，再用 `_cancel_request_event_id_from_cancelling()` 从 payload JSON 解析 link；helper 捕获 `JSONDecodeError`、payload 非 object、字段缺失并返回 `None`。
- `dayu/host/engine_ingest.py` cooperative `RUN_CANCELLED` closeout 同样读取 latest `RUN_CANCELLING` 并调用 `_cancel_request_event_id_from_cancelling()`；payload malformed 时写 rejected diagnostic。
- `dayu/host/dispatch.py` `_read_linked_cancel_requested_event()` 读取 latest `RUN_CANCELLING` payload，再根据 `cancel_request_event_id` 回查 `CANCEL_REQUESTED`。
- `tests/host/test_run_attempt_transitions.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_recovery_scan.py` 已有 malformed `RUN_CANCELLING` payload 测试，说明当前行为把 critical linkage 的异常建模在 payload parsing 失败上，而不是 typed durable state 缺失上。

## 3. Design truth confirmation and required design update decision

`docs/host/design.md` 已清楚表达：

- Host canonical EventLog / Run / Attempt 是 lifecycle truth。
- `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` 是 Run terminal canonical facts。
- `RUN_LOST` 来源于 recovery / lifecycle positive orphan proof，不得伪装成用户 cancel 或 failure。
- Outbox 是 projection / work queue，不能回滚或驱动 Run terminal truth。

但 `docs/host/design.md` 目前没有自足地区分三类集合：

1. Host terminal/lifecycle event set：包含 `RUN_LOST`。
2. Public outbox terminal item event set：只包含 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED`，排除 `RUN_LOST`。
3. Non-public terminal fact skip/diagnostic behavior：Outbox consumer 可以显式 skip `RUN_LOST` 并记录 diagnostic，但 public outbox watermark / latest item cursor 不能把 `RUN_LOST` 当成必须投递的 item。

因此 P1-B implementation 前必须先更新 `docs/host/design.md`，把上述设计写成 Host design truth。不得直接以 `outbox.py` 当前 skip 分支作为事实真源，也不得让 `durable/outbox.py` 的 latest terminal watermark 继续把 `RUN_LOST` 当成 public outbox item 候选。

## 4. Owner boundary

Producer：

- Admission / cancel command 产生用户取消意图，append `CANCEL_REQUESTED`。
- Durable run transition 产生 Run lifecycle fact，append `RUN_CANCELLING` / terminal facts，并更新 Run row。
- Engine ingest 只把 Engine terminal candidate 转成 Host terminal transition request，不拥有 Host cancel linkage。
- Recovery / dispatch closeout 产生 `RUN_LOST`、watchdog `RUN_CANCELLED` 或 dispatch failure terminal facts，但必须消费 Host durable truth。

Validator：

- Host durable transition layer 校验状态机、terminal first-committer-wins、cancel request link 非空、Run / Attempt / dispatch record 前置条件。
- Schema / row codec 校验 `RunRow.cancel_request_event_id` 类型、nullable 形状与 row projection。

Durable：

- EventLog 继续保存 `CANCEL_REQUESTED`、`RUN_CANCELLING`、terminal facts 的 audit-readable payload。
- `host_runs.cancel_request_event_id` 成为当前 Run 已接受 cancel request 的 typed durable link；至少 `CANCELLING` 与 `CANCELLED` Run 必须能从该字段找到同 Run 的 `CANCEL_REQUESTED`。
- 若 implementation 发现一个 Run 需要多条 accepted cancel request history，必须停下；不得临时添加 loose JSON 或 extra payload。届时改为 typed indexed relation，并更新本 plan / design truth。

Projection：

- Outbox、Read Model、Tool Trace、Read API、Engine ingest diagnostic 和 dispatch watchdog 只消费同一个 terminal helper / cancel linkage contract。
- Projection 不写 Run / Attempt，不解析 payload 作为 lifecycle truth，不把 `RUN_LOST` 投影成 public outbox terminal item。

Tests：

- Durable schema tests 覆盖新列 / row codec / schema version。
- Cancel lifecycle tests 覆盖 active cancel、watchdog、cooperative worker cancel、session cancel replay、malformed legacy payload 不再影响 typed link。
- Outbox/read model/tool trace/engine ingest/dispatch tests 覆盖 terminal helper 与 `RUN_LOST` public outbox skip。

## 5. Selected contract/schema approach

### 5.1 Terminal helper

新增 Host-owned lifecycle/terminal contract helper，建议文件：

- `dayu/host/lifecycle_events.py`

该模块不是兼容 re-export，不从 projection 层反向抽取；它是 Host lifecycle event type 与 terminal mapping 的 source-of-truth。建议提供：

- `HostRunEventType(StrEnum)`：至少包含 `RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED`、`RUN_WAITING`、`RUN_CANCELLING`、`RUN_RECOVERING`、`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST`。
- `HOST_RUN_TERMINAL_EVENT_TYPES: tuple[HostRunEventType, ...]`：包含 succeeded/failed/cancelled/lost。
- `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES: tuple[HostRunEventType, ...]`：只包含 succeeded/failed/cancelled。
- `HOST_RUN_LIFECYCLE_EVENT_TYPES: tuple[HostRunEventType, ...]`：供 read model / tool trace 组合 lifecycle filter。
- `run_status_for_terminal_event(event_type: str) -> RunStatus | None`。
- `host_terminal_status_for_terminal_event(event_type: str) -> HostTerminalStatus | None`。
- `is_host_run_terminal_event(event_type: str) -> bool`。
- `is_public_outbox_terminal_item_event(event_type: str) -> bool`。
- `event_type_values(event_types: tuple[HostRunEventType, ...]) -> tuple[str, ...]`，供 `ProjectionEventClassFilter` / SQL `IN` 参数使用。

实现约束：

- helper 可依赖 `dayu.host.api.RunStatus` 与 `HostTerminalStatus`，因为 durable state 已依赖 `dayu.host.api` 的状态类型；不得依赖 projection、outbox、engine ingest、dispatch 或 concrete durable store。
- mapping / predicate helper 接受 raw EventLog `str` event type，而不是要求调用方先传 `HostRunEventType`。理由是当前 EventLog row、projection filter、SQL `IN` 参数、HostEvent 投影和 diagnostic 输入边界的事实形态都是 durable string；若强制每个消费者先 parse，会把同一 parse/classification 责任分散回消费者。`lifecycle_events.py` 必须在 helper 内部完成 parse / classification：合法 Run lifecycle string 映射为 `HostRunEventType` 后判断，未知或非 Run event string 返回 `None` / `False`，不得抛出给 projection consumer 作为正常分类路径。
- `HostRunEventType` 仍是 helper 内部集合和新生产代码使用的 typed source-of-truth；`event_type_values(...)` 是唯一允许把 typed tuple 转成 string tuple 的 helper。
- 各消费者必须删除自己的 terminal set / status mapping 私有拷贝；只保留消费者私有的 payload field names、detail code、item kind 等投影语义。
- `RUN_LOST` 在 Read API / HostEvent / Read Model 可映射为 `lost` terminal；在 Outbox helper 映射为 non-public terminal skip。

### 5.2 Cancel durable linkage

选择直接在 `host_runs` 新增 typed nullable 列：

- `cancel_request_event_id TEXT NULL`
- 外键引用 `event_log(event_id)`。

选择列而非 relation 的原因：

- 当前状态机中一个 Run 只应有一个 accepted cancel request 进入 lifecycle truth；active cancel replay 不追加第二个 `RUN_CANCELLING`，terminal first-committer-wins 阻止 terminal 后 cancel 改写。
- 该 link 与 Run lifecycle 强绑定，Run row 是最小 source-of-truth；新增 relation 表会引入一对多历史语义和额外 owner，当前没有真实需求支撑。
- 若 implementation 发现同一 Run 必须持久化多条 cancel request history 或 cancel retry diagnostics，触发 stop condition，回到 design 决策。

字段语义：

- `cancel_request_event_id` 表达该 Run 已接受并进入 durable lifecycle 的 cancel request fact。
- `CANCELLING` Run 必须非空。
- `CANCELLED` Run 必须非空。
- `LOST` Run 可为空；若它曾经过 accepted active cancel 并最终 lost，可保留该 link 作为诊断关联，但不能把 lost 解释为 public outbox cancel item。
- 非 cancel lifecycle Run 默认为 `None`；terminal 已先提交后到达的 cancel 不得写该字段。

transition 变更：

- 所有 append `CANCEL_REQUESTED` 并把 Run 推入 `CANCELLING` 或 `CANCELLED` 的 transition，在同一事务更新 `host_runs.cancel_request_event_id`。
- `mark_run_cancelling_row()` 增加 `cancel_request_event_id` 参数并 CAS 写入该列。
- direct cancel terminal row mutator 增加或复用 cancel request id 参数，保证 queued / accepted / waiting / pre-worker direct cancel 也有 typed link。
- active watchdog、cooperative engine cancel、dispatch `_read_linked_cancel_requested_event()`、recovery accepted-cancel 判断优先读取 `RunRow.cancel_request_event_id`，再回查同 Run `CANCEL_REQUESTED` event type；不得从 `RUN_CANCELLING` payload JSON 解析 critical link。
- `_cancel_request_event_id_from_cancelling()` 删除，或降级为仅供一次性 diagnostic / historical payload audit 的非 critical helper；若保留，生产 closeout path 不得调用它。

Schema policy：

- 按全新 schema 起库；不实现旧库兼容读取，不写 workspace migration，除非 controller 明确追加兼容升级要求。
- schema version / schema SQL / schema tests 与 row codec 同步更新。

## 6. Non-goals

- 不重新设计 cancellation UX。
- 不改变 Engine cancellation token contract。
- 不设计 provider-specific physical cancel API。
- 不改变 `RUN_LOST` 的 Host terminal/lifecycle 语义。
- 不让 Outbox 把 `RUN_LOST` 投影成 public success/failure/cancel terminal item。
- 不为旧 schema / 旧数据库做兼容读取或迁移。
- 不用下游展示、测试夹具或单入口特例掩盖 terminal set / cancel linkage 问题。

## 7. Implementation slices

### S0. Design truth update

Objective：先把 `docs/host/design.md` 写清 terminal set 与 public outbox item set 的关系。

Allowed files：

- `docs/host/design.md`
- `docs/reviews/wu-semantic-ownership-01-p1-b-s0-design-truth-codex.md` 或等价 implementation artifact

Required changes：

- 优先在 `docs/host/design.md` 的状态迁移 terminal facts 表之后，或 Durable Store / EventLog / Outbox ownership 段落之后写入设计真源。若 implementation 选择其它等价位置，S0 implementation artifact 必须记录最终插入位置、章节标题和选择理由，保证读者能从 EventLog 与 Outbox 设计处找到该语义。
- 新增内容至少包含三段自足结构：
  - Host terminal / lifecycle event set：`RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` 都是 Host Run terminal canonical facts，其中 `RUN_LOST` 是 lost terminal。
  - Public outbox terminal item set：只包含 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED`，排除 `RUN_LOST`；public outbox item 不把 lost 伪装为 success / failure / cancel。
  - Non-public terminal fact skip / diagnostic behavior：`RUN_LOST` 在 Read Model / Read API / HostEvent 中投影为 `lost` terminal；在 Outbox 中只能产生 explicit skip / diagnostic，不要求 public outbox item。Public outbox watermark / latest item logic 只以 public outbox item event set 为准。
- 不修改生产代码和测试。

Validation：

```bash
git diff --check
```

Stop condition：design owner 不接受 `RUN_LOST` 非 public outbox item 的区分，或要求改变 public notification contract。

### S1. Terminal event/status contract helper

Objective：建立 Host terminal/lifecycle event helper，并迁移重复 terminal set consumers。

Allowed files：

- `dayu/host/lifecycle_events.py`
- `dayu/host/outbox.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/read_model.py`
- `dayu/host/tool_trace.py`
- `dayu/host/read_api.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- affected Host projection / read API / ingest tests

Required changes：

- 新增 helper 与中文 docstring，所有函数签名避免 `Any` / `object`。
- Outbox consumer filter 使用 `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`，或继续观察 Host terminal set 但通过 helper 明确 skip `RUN_LOST`；同时 `durable/outbox.py` latest public terminal sequence 必须使用 `lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` 的字符串值形式或 `event_type_values(PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES)`，不得包含 `RUN_LOST`，也不得在 `durable/outbox.py` 保留第二份本地 public outbox terminal tuple。
- Read Model 使用 Host terminal helper 映射 terminal status，保留 `RUN_LOST` 为 read model terminal result。
- Tool Trace 使用 Host lifecycle helper 组合 canonical event filter，不私有复制 terminal tuple。
- Read API / HostEvent terminal mapping 复用 helper，不私有复制 `RUN_*` terminal mapping。
- Engine ingest 只在需要识别 terminal event type 时复用 helper；不得把 EngineEvent terminal type 当 Host terminal set 真源。

Expected tests：

- Outbox `RUN_LOST` skip / diagnostic 仍存在，但 latest public terminal sequence 不被 lost 推进到需要 item 的位置。
- Durable outbox projection state 覆盖 `RUN_LOST` 在最新 EventLog sequence 后出现时，latest public terminal sequence 仍停留在最近一个 public outbox terminal item event，不能产生 “checkpoint 落后但无 item 可投递” 的假 lag。
- Read model / HostEvent 仍能把 `RUN_LOST` 投影为 lost terminal。
- Tool Trace 继续消费 terminal canonical facts。

Validation：

```bash
source .venv/bin/activate && pytest tests/host/test_projection_read_model.py tests/host/test_public_host_event.py tests/host/test_context_compact_events.py tests/host/test_tool_trace*.py
source .venv/bin/activate && pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py
source .venv/bin/activate && pyright
git diff --check
```

Stop condition：发现 public API 或 external caller 依赖 projection-private terminal constants，不能在当前 slice 内迁移。

### S2. Cancellation durable linkage

Objective：新增 typed cancel request link，并迁移 active cancel readers。

Allowed files：

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/admission.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/recovery.py`
- cancel lifecycle / durable schema tests

Required changes：

- `host_runs` DDL 增加 `cancel_request_event_id`，`RunRow`、row decoder、all select/insert paths 同步。
- 更新 schema version / expected schema tests；按全新 schema 起库，不做旧库 compatibility。
- `mark_run_cancelling_row()` 与所有 direct cancel row mutator 同事务写入 `cancel_request_event_id`。
- `request_active_attempt_cancel_in_transaction()` append `CANCEL_REQUESTED` 后，把 event id 传给 Run row mutation。
- active watchdog closeout 从 `RunRow.cancel_request_event_id` 读取 link，回查 `CANCEL_REQUESTED` 事件并校验同 Run。
- engine ingest cooperative cancel 从 Run row 读取 link；缺失时写 typed diagnostic，诊断 reason 从 malformed payload 改为 typed durable link missing / invalid。
- dispatch `_read_linked_cancel_requested_event()` 从 Run row 读取 link。
- recovery accepted-cancel 判断从 Run row 读取 link，不再解析 `RUN_CANCELLING` payload。
- 删除或降级 `_cancel_request_event_id_from_cancelling()`，并用 `rg` 证明 critical path 不再调用。
- 同步审计 `event_payload_object(...RUN_CANCELLING...)` 调用残留。允许命中仅限一次性 audit / diagnostic / historical payload readability 路径；禁止命中 active watchdog、engine ingest cooperative cancel、dispatch linked cancel、recovery accepted-cancel 等 critical closeout 路径。

Expected tests：

- Active cancel request 后 `RunRow.cancel_request_event_id` 等于 `CANCEL_REQUESTED.event_id`。
- Watchdog closeout 不依赖 `RUN_CANCELLING` payload；即使 payload 缺少该字段，只要 typed Run row link 存在，closeout 正常。
- typed link 缺失时 watchdog / engine ingest fail closed，不追加 terminal facts。
- direct queued / accepted / waiting / pre-worker cancel terminal rows 均写入 typed link。
- session cancel replay 不重复追加 `CANCEL_REQUESTED` / `RUN_CANCELLING`，也不改写已有 typed link。

Validation：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_open_host_runtime.py
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py
source .venv/bin/activate && rg -n "_cancel_request_event_id_from_cancelling|payload\\.get\\(\"cancel_request_event_id\"\\)|event_payload_object\\(.*RUN_CANCELLING" dayu/host tests/host
source .venv/bin/activate && pyright
git diff --check
```

Stop condition：发现现有 workspace 必须迁移历史 `RUN_CANCELLING` payload 才能继续运行；发现同一 Run 需要多条 accepted cancel request history；或发现 queued / accepted / waiting / pre-worker direct cancel 路径在某些 Run 状态下无法安全写入 `cancel_request_event_id`，且不能通过调整 transition 顺序或同事务 row mutation 解决。

### S3. README / design / propagation audit sync

Objective：同步文档与完成 propagation audit。

Allowed files：

- `dayu/host/README.md`，如 Host lifecycle / schema / cancellation contract 变化属于其读者职责。
- `tests/README.md`，如新增 schema / cancel lifecycle 测试分类属于其读者职责。
- `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md` 或等价 implementation artifact。

Required changes：

- 修改 README 前先阅读目标 README 的 `Agent更新约束【必须遵守】`。
- 在 implementation artifact 中列出 propagation audit 结果与 residual risks。

Validation：

```bash
source .venv/bin/activate && pyright
git diff --check
```

## 8. Allowed files/modules

Plan gate 本轮只允许写：

- `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- `docs/reviews/wu-semantic-ownership-01-p1-b-plan-codex.md`

后续 implementation allowed files/modules：

- `docs/host/design.md`
- `dayu/host/lifecycle_events.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/admission.py`
- `dayu/host/dispatch.py`
- `dayu/host/recovery.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/read_model.py`
- `dayu/host/outbox.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/tool_trace.py`
- `dayu/host/read_api.py`
- focused Host tests under `tests/host/`
- README files only after trigger/readership check

If implementation scan finds another production consumer of terminal set or active cancel link, update the plan or stop for controller adjudication before editing that file.

## 9. Validation commands

Full P1-B implementation validation target:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_open_host_runtime.py
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py
source .venv/bin/activate && pytest tests/host/test_projection_read_model.py tests/host/test_public_host_event.py tests/host/test_context_compact_events.py tests/host/test_tool_trace*.py
source .venv/bin/activate && pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py
source .venv/bin/activate && rg -n "_TERMINAL_STATUS_BY_EVENT_TYPE|_TERMINAL_EVENT_TYPES|_cancel_request_event_id_from_cancelling|payload\\.get\\(\"cancel_request_event_id\"\\)|event_payload_object\\(.*RUN_CANCELLING" dayu/host tests/host
source .venv/bin/activate && pyright
git diff --check
```

Plan gate validation:

```bash
git diff --check
```

## 10. README/design update triggers

- `docs/host/design.md` must be updated before implementation because current design truth does not explicitly separate Host terminal event set, public outbox terminal item set, and `RUN_LOST` skip/diagnostic behavior.
- `dayu/host/README.md` must be checked if implementation changes Host lifecycle, durable schema, cancellation behavior, outbox terminal semantics, or dispatch/recovery closeout behavior.
- `tests/README.md` must be checked if implementation adds or reorganizes durable schema / cancel lifecycle / outbox projection test coverage.
- Root `README.md` is not expected unless user-visible CLI/Web/WeChat workflow, workspace file locations, logs, or final user workflow changes.
- `dayu/README.md` is not expected unless implementation changes `UI -> Service -> Host -> Engine` layering or assembly boundary.

## 11. Stop conditions / residual risks

Stop conditions:

- Design owner rejects the `RUN_LOST` non-public-outbox distinction or requests a different public notification contract.
- Historical workspace migration becomes required. Current task policy says schema changes are full new schema; no compatibility migration unless controller explicitly asks.
- Same Run needs more than one accepted cancel request as durable lifecycle history; direct Run column would be insufficient and a typed relation must be designed.
- Implementation scan finds terminal event type consumers outside the allowed files whose public contract cannot be migrated safely in P1-B.
- Pyright or focused Host tests reveal pre-existing errors in touched files that cannot be fixed within P1-B boundaries.

Residual risks:

- Some `RUN_SUCCEEDED`-only helpers, such as final-answer continuity and memory material, intentionally remain success-specific and should not be forced through a broad terminal helper unless they consume terminal set semantics.
- Non-terminal Run lifecycle constants such as `RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED`、`RUN_WAITING`、`RUN_CANCELLING`、`RUN_RECOVERING` are only migrated in P1-B where a touched consumer needs the shared lifecycle helper for terminal/read-model/tool-trace/outbox semantics. P1-B does not promise a repository-wide migration of every non-terminal lifecycle constant consumer; if `HostRunEventType` becomes the universal Run event string owner in a later work unit, those deferred consumers must be migrated there.
- `RUN_CANCELLING` payload may continue to contain `cancel_request_event_id` for audit readability; reviewers must verify no production critical path uses it as source-of-truth.
- Public outbox read API may have both item-query watermark and EventLog latest-terminal logic; both must be audited so `RUN_LOST` cannot create “cursor advanced but item absent” confusion for callers.

## 12. Propagation audit plan

Terminal event/status propagation:

1. Producer：durable transition / engine ingest / recovery produce `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` through Host lifecycle helper.
2. Durable：EventLog stores canonical facts; Run row stores terminal status and terminal event refs.
3. Projection：Read Model, Read API, Tool Trace and HostEvent derive terminal status from helper.
4. Outbox：Outbox derives public terminal item only for public outbox terminal item set; `RUN_LOST` records skip/diagnostic but no item.
5. User / LLM-visible output：public HostEvent may show lost terminal; public outbox does not deliver lost as success/failure/cancel; LLM-facing memory only consumes business-meaningful terminal material.

Cancel linkage propagation:

1. Producer：admission / cancel command appends `CANCEL_REQUESTED` and passes its event id into durable transition.
2. Validator：durable transition validates non-empty id, same Run state, and first-committer-wins preconditions.
3. Durable：Run row stores `cancel_request_event_id`; EventLog stores audit-readable `CANCEL_REQUESTED` / `RUN_CANCELLING` / terminal payload.
4. Projection / closeout：engine ingest, active cancel watchdog, dispatch watchdog and recovery read typed Run row link and validate referenced `CANCEL_REQUESTED` event.
5. Diagnostics：missing typed link is a durable invariant failure diagnostic; malformed `RUN_CANCELLING` payload is no longer a lifecycle blocker.
6. Tests：schema, transition, engine ingest, dispatch, recovery and public cancel tests assert the same link is used end to end.
