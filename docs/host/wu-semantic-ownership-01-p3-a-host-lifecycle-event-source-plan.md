# WU-SEMANTIC-OWNERSHIP-01 P3-A Host Lifecycle / Run Status / Terminal Event Source Plan

## 1. 目标、动机与成功信号

Work unit：`WU-SEMANTIC-OWNERSHIP-01 P3-A - Host lifecycle, run status, and terminal event source of truth`。

当前 gate：plan only。本 artifact 只给出 code-generation-ready plan，不实施代码、不修改测试、不 commit、不 push、不进入 plan review 或 implementation gate。

目标：只围绕 Host lifecycle、Run / Attempt status、terminal event source-of-truth 修复当前代码中仍成立的语义所有权漂移。核心原则是让 Host durable state 拥有 status 终态/非终态判定，让 `dayu.host.lifecycle_events` 拥有 Host lifecycle event type 与 terminal event type 映射，让 worker lifecycle closeout 使用 Host-owned identity 和 closeout path，而不是借用 synthetic Engine event 语义。

第一性原理判断：P3-A 动机成立，但不能机械照搬所有 source finding 的建议。当前设计真源明确：

- Host 是 Session / Run / Attempt / EventLog / lifecycle / cancel / recovery 的治理真源。
- EngineEvent stream 只是 Host ingest 输入来源，不是 Host durable truth。
- Run terminal canonical facts 是 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST`。
- `RUN_SUSPENDED` 是 Engine terminal event，但在 Host 中对应 `WAITING`，不是 Run terminal event。
- `CANCELLED` wait record 仍可被 poller 观察一次以执行 best-effort abandon；这不是 Run terminal source-of-truth 问题。

成功信号：

- 生产代码中 Run terminal status、non-terminal/start-blocking status、Attempt terminal status 判定只通过 durable state owner helpers 暴露；消费者不再内联 tuple / frozenset / SQL placeholder 列表。
- `run_transition.py` 与 `engine_ingest.py` 的 Run / Attempt terminal event type 生成复用 `lifecycle_events.py` helper / enum，不再复制 terminal event type 字符串与 status-to-event if/elif 链。
- `_late_rejection_reason` 用 status-owned predicates 判断 terminal closed，不用 nullable `terminal_event_id` / `terminal_event_sequence` 作为 lifecycle truth。
- `_close_worker_lifecycle` 不再合成 `EngineEvent(type=RUN_FAILED)`；worker EOF / crash 使用 Host-owned lifecycle closeout candidate、Host-owned event identity 和现有 terminal closeout transaction。
- pre-worker direct cancel predicate 的 owner 从 `command.py` 下移到 durable state helper；command path 不再重建 dispatch record worker-accepted nullable 字段组合。
- 受影响 Host tests、pyright、`git diff --check` 通过；README 是否更新按触发规则裁决。

## 2. 直接证据与 source findings 裁决

### AgentCodex 12：accepted

当前仍成立。`dayu/host/lifecycle_events.py:1-6` 声明自己是 Host Run lifecycle event type 与 terminal event set 真源，但 `dayu/host/durable/run_transition.py:88-103` 仍定义 `_EVENT_TYPE_RUN_SUCCEEDED` / `_EVENT_TYPE_RUN_FAILED` / `_EVENT_TYPE_RUN_CANCELLED` / `_EVENT_TYPE_RUN_LOST` 等裸字符串，`run_transition.py:5555-5571` 仍用 if/elif 把 `RunStatus` 映射回这些字符串。修复应落在 event type owner 和 durable transition producer，不在 projection 下游补特例。

### AgentDS 1：accepted with scope correction

当前仍成立，但 purge 部分已较原 finding 缩小。直接证据：

- `_row_rules.py:13-18` 定义 schema row terminal status text。
- `state.py:71-75` 从 row rules 派生 `TERMINAL_RUN_STATUSES` / `NON_TERMINAL_RUN_STATUSES`。
- `admission.py:4557-4569` 仍内联 `RunStatus.SUCCEEDED/FAILED/CANCELLED/LOST`。
- `read_model.py:38-40` 仍定义独立 `_TERMINAL_RUN_STATUSES`。
- `state.py:1596-1607` 与 `state.py:1750-1761` 仍在 SQL 中硬编码状态 placeholder 与状态参数。
- `purge.py:122-123` 当前已从 `state.NON_TERMINAL_RUN_STATUSES` / `TERMINAL_RUN_STATUSES` 派生 value set，不是完全独立真源；但仍可在本 WU 中改为复用同一个 serialization helper，减少重复 value projection。

Root cause 是 status closed set 与 SQL status filters 没有统一 helper。修复 owner 是 durable state / row rules 的直接上游，不是 tests 或 API projection。

### AgentDS 9：accepted

当前仍成立。`engine_ingest.py:2453-2471` 在 worker lifecycle closeout 中合成 `EngineEvent(type=EngineEventType.RUN_FAILED, data=RunFailedData(...))`，但实际 closeout plan 可能写 `ATTEMPT_LOST` / `RUN_LOST`。这让 Host-owned worker lifecycle fact 借用了 Engine event type 语义，也让 `_late_rejection_reason` 的 EngineEventType 分支可能误分类。修复必须在 Host ingest / closeout owner 内完成，不能在 tests 或 projection 中屏蔽。

### AgentDS 10：accepted

当前仍成立。`engine_ingest.py:228-236` 仍复制 Attempt / Run terminal event string；`run_transition.py:88-103` 与 `run_transition.py:5536-5571` 仍复制 terminal event mapping；`lifecycle_events.py:57-68` 已有 Run terminal event -> status mapping。修复应让 durable transition 和 engine ingest 消费 lifecycle event owner，不新增第四套映射。

### AgentDS 11：accepted

当前仍成立。`engine_ingest.py:3327-3328` 使用 `context.run.terminal_event_id is not None or context.attempt.terminal_event_id is not None` 判断 terminal closed。按设计，Run / Attempt status 是 lifecycle truth，terminal event refs 是同事务索引引用；nullable ref 不应成为独立分类真源。修复应改用 durable state predicates。

### AgentDS 17：accepted

当前仍成立。`command.py:1721-1740` 通过 `DispatchRecordRow.status` 加 `worker_accepted_at` / `worker_accept_event_id` / `worker_accept_event_sequence` 三个 nullable 字段判断 pre-worker direct cancel。正确 owner 应是 durable state / dispatch record helper；command path 只表达 cancel command，不应理解 dispatch row 内部组合。

### AgentMiMo SM-1：accepted

当前仍成立。`lifecycle_events.py`、`run_transition.py`、`engine_ingest.py` 仍分别定义 Host lifecycle / terminal event string 常量。修复同 AgentCodex 12 / AgentDS 10。

### AgentMiMo SM-2：accepted with solution correction

当前“映射分散”问题成立，但原建议中“一张 Engine -> Host terminal map”不能原样实施。原因是 Engine terminal event 与 Host lifecycle transition 不是一对一 terminal mapping：`RUN_SUSPENDED` 在 Engine 是 terminal，但 Host 只做 waiting confirmation；recoverable `RUN_FAILED` 可能进入 reactive recovery path；`CONTEXT_COMPACTION_REQUESTED` 不是 terminal closeout。P3-A 只建立 Host lifecycle event source-of-truth 与 terminal closeout predicates；不把 Engine ingest 状态机压成一个 flat dict。

### AgentMiMo SM-3：accepted with schema non-goal

当前 predicate 漂移成立：worker accepted 语义在 `command.py` 与 durable SQL guard 中都通过 nullable worker-accept refs 组合表达。但 broad schema redesign 不是本 WU 目标。P3-A 只把“pre-worker direct cancelable”封装到 durable state helper，让 command path 不再重建 nullable 字段组合；不新增 dispatch status、schema migration 或 worker accepted terminal state。

### AgentMiMo SM-4：accepted

当前仍成立。`read_active_run_for_session` 与 `read_non_terminal_runs_for_session` 仍硬编码 SQL `status IN (?, ...)` 与状态参数，未从 `NON_TERMINAL_RUN_STATUSES` 或 start-blocking status helper 派生。修复应在 durable state 生成 SQL predicate / params，避免新增状态时查询漏判。

### AgentMiMo SM-5：rejected-with-reason

当前 review 严重性被高估，不应在 P3-A 实施。`state.py:2070-2074` 明确说明 cancelled wait row 会返回给 poller 以 abandon 外部 job，`state.py:2188-2190` 也只允许 `(status=CANCELLED AND poll_abandoned_at IS NULL)` 被 claim。这与 Host design 中“adapter 观察到 wait record cancelled 后可以 best-effort cancel / revoke / abandon 外部 job”的边界一致。`CANCELLED` wait 不会进入 `resolve_wait`，也不是 Run terminal truth。若未来要重命名为 `awaiting_abandon_pending`，应归 wait poller / external job lifecycle WU，不是 P3-A。

### AgentMiMo SM-7：needs-more-evidence

直接证据只显示 `FollowupSnapshot.__post_init__` 在 `api.py:2399-2402` 拒绝 `accepted_run_status=RECOVERING`。review 没有证明当前生产 submit path 能产生 recovering accepted followup，也没有证明 durable owner 缺少对应前置校验会导致错误事实持久化。当前 P3-A 不应为此新增 durable 规则。后续若能提供生产路径证据，可归 public snapshot / admission contract hardening owner。

进入 S1 前必须做一次 SM-7 pre-implementation verification：搜索生产代码中所有 `FollowupSnapshot(...)` 构造点和 `accepted_run_status` 传参，确认是否存在 `accepted_run_status=RunStatus.RECOVERING` 或等价变量路径。建议命令：

```bash
rg "FollowupSnapshot|accepted_run_status|RunStatus\.RECOVERING" dayu/host dayu/service dayu/cli
```

若发现生产 submit / follow-up path 可能构造 recovering accepted followup，implementation 必须停止并把 SM-7 升级为 P3-A scope，或记录明确 deferred owner；若未发现，implementation artifact 记录搜索命令、结果摘要和 needs-more-evidence closure basis。

### AgentMiMo SM-8：rejected-with-reason

`_session_timeline_cursor(session)` 当前返回 `closed_event_sequence` 或 `created_event_sequence`，这是 cursor / EventLog sequencing 事实，不是 Session status 判定。Session row shape validation 已要求 open session 的 closed refs 为空。把 timeline cursor 改成由 `status` 派生反而会丢失具体 EventLog cursor。该 finding 不属于 P3-A lifecycle/status terminal source-of-truth 修复。

裁决汇总：accepted 10；rejected 2；needs-more-evidence 1；deferred 0。

## 3. 语义 owner boundary

| 语义事实 | 首次产生 | 校验 | 持久化 / 真源 | 投影 / 消费 | P3-A 修复边界 |
|---|---|---|---|---|---|
| Run status closed set、terminal / non-terminal / start-blocking 判定 | `RunStatus` public enum + durable row rules | durable state row codec / schema row rules | `host_runs.status` 与同事务 EventLog canonical facts | admission、cancel、read model、purge、recovery、API snapshot | 在 `dayu.host.durable.state` 暴露 predicates / SQL value helpers；消费者删除内联集合 |
| Attempt terminal status 判定 | `AttemptStatus` public enum + durable row rules | durable state row codec / schema row rules | `host_attempts.status` 与同事务 Attempt terminal facts | engine ingest late rejection、transition closeout、recovery | 暴露 `TERMINAL_ATTEMPT_STATUSES` / `is_terminal_attempt_status` |
| Host lifecycle event type | `dayu.host.lifecycle_events` | enum parser / helper fail-fast | EventLog `event_type` canonical strings | durable transition、engine ingest、outbox/read API | 扩展 lifecycle event owner helper；producer 使用 helper 生成 terminal event type |
| terminal closeout event identity | EngineEvent candidate for Engine-origin events；Host lifecycle candidate for worker EOF/crash | ingest / duplicate check | EventLog `event_id` + `event_sequence` | duplicate detection、audit、projection | worker lifecycle path 使用 Host-owned identity，不合成 Engine event |
| terminal already closed predicate | durable Run / Attempt status | durable state predicates | `host_runs.status` / `host_attempts.status` | `_late_rejection_reason` | 用 status predicate，不用 terminal refs nullable shape |
| pre-worker direct cancelability | durable dispatch record state owner | durable state helper over dispatch row | dispatch record row + Attempt status/EventLog | command cancel path | helper 下移到 `durable.state`，command 调用 helper |

Propagation audit baseline:

```text
Engine final answer / failure / cancel
  -> EngineEventCandidate
  -> engine_ingest validates run_id / attempt_id / execution_id
  -> lifecycle_events helper chooses Host terminal event type
  -> terminal_closeout_in_transaction appends Attempt + Run canonical facts
  -> durable state row status updated in same transaction
  -> read model / outbox / memory / audit consume EventLog + status truth
```

```text
Worker EOF / crash
  -> Host worker lifecycle signal
  -> HostLifecycleCloseoutCandidate with Host-owned event identity
  -> durable context validation
  -> status-owned late / duplicate checks
  -> terminal_closeout_in_transaction appends FAILED or LOST canonical facts
  -> durable state row status updated in same transaction
  -> projections consume the same EventLog / status truth
```

Import graph baseline:

```text
dayu.host.api
  -> does not import dayu.host.durable

dayu.host.lifecycle_events
  -> may import RunStatus / AttemptStatus / Host terminal status contracts from dayu.host.api
  -> must not import dayu.host.durable.state, run_transition, or engine_ingest

dayu.host.durable.state
  -> imports dayu.host.api and durable row rules
  -> must not import lifecycle_events

dayu.host.durable.run_transition
  -> may import lifecycle_events helpers and durable.state helpers

dayu.host.engine_ingest
  -> may import lifecycle_events helpers and durable.state helpers
```

已核对当前 `dayu/host/api.py` 不导入 `dayu/host/durable/` 下模块，因此 `run_transition.py -> lifecycle_events.py -> api.py` 与 `engine_ingest.py -> lifecycle_events.py -> api.py` 不构成循环。S1/S2 后必须运行导入验证：

```bash
source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
```

若 helper placement 引入 import cycle，implementation 必须停止并回到 design/plan fix；不得用 lazy import 或兼容 wrapper 掩盖依赖方向错误。

## 4. Non-goals、stop conditions 与不过度设计说明

Non-goals：

- 不处理 P3-B 及之后的 final answer / compact / evidence / Engine provider / Fins / CLI package / broad schema hardening / test coupling。
- 不做全 EventLog closed-set schema hardening。
- 不引入 RunStatus 新成员，不新增 `RUN_REJECTED`，不改 durable schema version。
- 不重构 Engine runner assembly，不改 Engine contracts。
- 不把 EngineEvent ingest 改写成全局 flat mapping table。
- 不改变 wait record lifecycle，不改 wait poller abandon 行为。
- 不实现 broad dispatch record schema redesign、worker accepted 新状态或 migration。
- 不修改下游 projection 以掩盖上游事实漂移。
- 不预设计 P3-B final answer / terminal descriptor 新字段。S3 如抽取 closeout core，只能保持现有 `_close_terminal` 已有 final-answer / terminal descriptor 参数和行为；P3-B 后续可消费同一 closeout path，但 P3-A 不新增 final-answer-specific 字段，除非它们已由当前 `_close_terminal` 调用签名要求。
- 不处理非 terminal Host EventLog 常量的全局 owner 化。P3-A 只收敛 terminal event source-of-truth；非 terminal 常量作为 P3-J / future EventLog schema hardening 输入留痕。

Stop conditions：

- 如果 implementation 发现 terminal status / terminal event 的正确修复必须新增 durable schema CHECK 或迁移，停止并先回 design truth，不在 P3-A 私自迁移。
- 如果 worker lifecycle closeout 无法在不合成 EngineEvent 的情况下复用 terminal closeout transaction，应停止并要求设计裁决新的 Host lifecycle closeout contract。
- 如果 lifecycle event owner 扩展到 Attempt event type 会引入 import cycle或 public API 破坏，应停止并裁决是否新增层中立 Host event type module。
- 如果 SQL status helper 无法在不牺牲 query plan / index usage 的情况下动态生成，应停止并记录证据；不能退回硬编码魔法状态列表。
- 如果 tests 需要通过 raw SQL 特例构造违反 row shape 的状态才能通过，应迁移测试边界，而不是在生产代码保留兼容分支。

不过度设计说明：本 plan 只把已经存在的 status 集合、event type 集合、status-to-event 映射和 closeout identity 移到现有 owner；不新增平台、registry、schema migration、EventLog universal enum、dispatch state machine 或 wait lifecycle。所有 slices 都是 current code 直接证据支撑的 owner-boundary cleanup。

## 5. Implementation slices

### S1. Lifecycle/status owner helpers

Objective：建立生产代码可直接消费的 Host lifecycle event type 与 Run / Attempt status predicate 真源，作为后续迁移的稳定 contract。

Allowed files/modules：

- `dayu/host/lifecycle_events.py`
- `dayu/host/durable/state.py`
- `tests/host/test_lifecycle_events.py` 或等价新测试文件
- `tests/host/test_state_schema.py`，仅补 owner-level status predicate 测试

Exact allowed changes：

- 在 `lifecycle_events.py` 中保留 `HostRunEventType`，并新增 Attempt lifecycle terminal event enum/helper，建议命名：
  - `HostAttemptEventType`
  - `HOST_ATTEMPT_TERMINAL_EVENT_TYPES`
  - `attempt_terminal_event_type_for_status(status: AttemptStatus) -> HostAttemptEventType`
  - `run_terminal_event_type_for_status(status: RunStatus) -> HostRunEventType`
- `run_terminal_event_type_for_status` 对非 terminal status fail-fast，不能返回 fallback 字符串。
- event type value projection 采用简单分离 helper，不做 TypeVar / overload 泛化：保留 Run event value helper 只接收 `tuple[HostRunEventType, ...]`，新增 `attempt_event_type_values(events: tuple[HostAttemptEventType, ...]) -> tuple[str, ...]`。禁止用 `Any` 或宽泛 enum bag 规避类型。
- 在 `durable/state.py` 中把 `_TERMINAL_ATTEMPT_STATUSES` 升级为公开模块常量 `TERMINAL_ATTEMPT_STATUSES`，新增：
  - `START_BLOCKING_RUN_STATUSES = NON_TERMINAL_RUN_STATUSES - {RunStatus.QUEUED}`，docstring 必须说明当前假设是“所有 non-terminal statuses except `QUEUED` 都会阻塞启动新 Run”；它用于 accepted/start-blocking admission 查询，不等于 active slot。若未来新增不应 blocking 的 non-terminal status，必须改为显式枚举并重新裁决 admission 语义。
  - `is_terminal_run_status(status: RunStatus) -> bool`
  - `is_terminal_attempt_status(status: AttemptStatus) -> bool`
  - `serialized_run_status_values(statuses: frozenset[RunStatus] | tuple[RunStatus, ...]) -> tuple[str, ...]`
  - `run_status_in_clause(statuses: tuple[RunStatus, ...] | frozenset[RunStatus]) -> tuple[str, tuple[str, ...]]` 或等价私有 SQL helper；返回 placeholder fragment 与 params，集中处理空集合。
- Helper 必须有完整中文 docstring，包含参数、返回值、异常。

Tests / expected assertions：

- `test_lifecycle_events.py` 断言 `run_terminal_event_type_for_status(SUCCEEDED/FAILED/CANCELLED/LOST)` 与 `HOST_RUN_TERMINAL_EVENT_TYPES` 全量一致，非 terminal status 抛 `ValueError`。
- 断言 Attempt terminal status `SUCCEEDED/FAILED/CANCELLED/LOST` 映射到对应 Attempt terminal event；`SUSPENDED/STEERED` 是否进入 helper由 implementation 按当前 closeout support 裁决，但若不支持必须明确 fail-fast，并用测试覆盖。
- `test_state_schema.py` 或新 owner test 断言 `TERMINAL_RUN_STATUSES` 与 `_row_rules.TERMINAL_RUN_STATUS_VALUES` 同源，`NON_TERMINAL_RUN_STATUSES` 自动等于 `RunStatus - terminal`，`START_BLOCKING_RUN_STATUSES` 明确排除 `QUEUED`。
- 增加 `START_BLOCKING_RUN_STATUSES` 精确成员集合测试：当前应等于 `NON_TERMINAL_RUN_STATUSES - {RunStatus.QUEUED}` 的具体成员。该测试必须在新增 `RunStatus` 非终态时失败，迫使开发者显式审查 start-blocking 假设。
- 增加 SQL helper owner test，断言 `run_status_in_clause(...)` 对空集合 fail-fast 或返回明确 false predicate，对 terminal/non-terminal/start-blocking 集合生成的 placeholder 数量与 params 数量一致，params 完全来自 `serialized_run_status_values(...)`。

Validation：

```bash
source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py -q
source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
source .venv/bin/activate && pyright
git diff --check
```

README / docs decision：S1 触及 `dayu/host/` 与 tests；implementation 必须先阅读并检查 `dayu/host/README.md` 和 `tests/README.md` 的 Agent 更新约束与相关 lifecycle/status/test 描述，再记录“更新”或“不更新”的实际依据。不能用“预计不更新”替代检查；如 README 未描述 lifecycle event owner boundary，记录为无需更新。

Rollback risk：低。新增 helper 与 tests 先落地，不改变行为路径；若 helper 命名不合适，回滚仅影响新增调用前的文件。

### S2. Migrate terminal status/event consumers

Objective：删除 P3-A 范围内的 duplicate status/event consumers，让 durable transition、admission、read model 与 SQL queries 消费 S1 owner helper。

Allowed files/modules：

- `dayu/host/durable/run_transition.py`
- `dayu/host/engine_ingest.py`，仅替换 terminal event type constants / status mapping，不改 worker lifecycle synthetic event path
- `dayu/host/admission.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/purge.py`，仅在需要复用 status value helper 时修改
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_purge_session.py`，仅在 purge helper value 行为变化时修改

Exact allowed changes：

- `run_transition.py` 删除 `_EVENT_TYPE_RUN_SUCCEEDED/_FAILED/_CANCELLED/_LOST` 与 `_EVENT_TYPE_ATTEMPT_SUCCEEDED/_FAILED/_CANCELLED/_LOST` 的 terminal producer用途，改用 `lifecycle_events.run_terminal_event_type_for_status(...).value` 和 `attempt_terminal_event_type_for_status(...).value`。
- `_run_terminal_event_type` / `_attempt_terminal_event_type` 只保留为薄私有 wrapper 时必须增加有效语义，例如统一转换异常消息；否则删除并直接调用 owner helper。不得保留一份 if/elif 映射。
- `_TERMINAL_STATUS_PAIRS` 不作为单独 durable row-rule truth，也不手写固定 tuple。它是 derived transition invariant：从 `state.TERMINAL_RUN_STATUSES`、`state.TERMINAL_ATTEMPT_STATUSES` 和 lifecycle terminal event helper 支持的 closeout 子集派生，只允许 `(SUCCEEDED, SUCCEEDED)`、`(FAILED, FAILED)`、`(CANCELLED, CANCELLED)`、`(LOST, LOST)` 这类 Run / Attempt 同名 terminal pair 进入 closeout。该 invariant 可留在 `run_transition.py` 的 transition closeout 边界，但必须命名/注释为 derived invariant，不是 event type mapping truth 或 durable row-rule truth。
- `engine_ingest.py` terminal closeout plan 中的 run / attempt terminal event type 改用 lifecycle helper；保留非 terminal event 常量如 `ENGINE_EVENT_REJECTED`、`PROVIDER_PROTOCOL_ERROR`、`RUN_WAITING` 可在本 WU 不处理。
- `admission.py:_is_terminal_run_status` 删除内联 tuple，改用 `state.is_terminal_run_status`。
- `read_model.py` 删除本地 `_TERMINAL_RUN_STATUSES`，使用 `state.TERMINAL_RUN_STATUSES` 或 `state.is_terminal_run_status`。
- `state.py:read_active_run_for_session` 使用 `START_BLOCKING_RUN_STATUSES` + SQL helper 生成 `IN` clause；`read_non_terminal_runs_for_session` 与 `read_non_terminal_runs` 使用 `NON_TERMINAL_RUN_STATUSES` + SQL helper。
- `purge.py` 如仍需要 status value set，只能通过 `state.serialized_run_status_values(...)` 派生；不要维护本地 status owner。

Tests / expected assertions：

- 新增或更新 transition owner tests，断言 durable transition 生成的 Run terminal event types 与 `HOST_RUN_TERMINAL_EVENT_TYPES` 一致，Attempt terminal closeout event types 与 Attempt owner helper 一致。
- `test_engine_ingest_mapping.py` 保留 final answer / failed / cancel / lost closeout 行为断言，并加一条 owner-level test 防止 engine ingest 复制 terminal event string。
- `test_public_run_api.py` / `test_state_schema.py` 覆盖 terminal status predicate，避免新增 status 时 admission/read model 漏判。
- Source scan 是 S2 强制 validation，不是可选测试。精确扫描 terminal event 常量：

```bash
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host
```

预期结果：`dayu/host/durable/run_transition.py` 与 `dayu/host/engine_ingest.py` 不得残留上述 terminal `_EVENT_TYPE_*` constant 定义、if/elif mapping 或裸字符串 producer；`dayu/host/lifecycle_events.py` 可定义 `HostRunEventType` / `HostAttemptEventType` terminal enum member，但不应使用 `_EVENT_TYPE_*` 前缀。测试文件只能显式引用 enum member 或 helper 断言。不得使用“diagnostic whitelist”泛化放行 terminal constant。
- 非 terminal constants 不在 P3-A scope，但必须作为 residual input 记录给 P3-J / future EventLog schema hardening。当前已知生产残留包括：`dayu/host/durable/run_transition.py` 中的 `_EVENT_TYPE_RUN_ACCEPTED`、`_EVENT_TYPE_RUN_QUEUED`、`_EVENT_TYPE_RUN_STARTED`、`_EVENT_TYPE_ATTEMPT_STARTED`、`_EVENT_TYPE_RUN_RECOVERING`、`_EVENT_TYPE_ATTEMPT_RUNNING`、`_EVENT_TYPE_CANCEL_REQUESTED`、`_EVENT_TYPE_RUN_CANCELLING`、`_EVENT_TYPE_RESUME_REQUESTED`、`_EVENT_TYPE_TOOL_RESULT_ACCEPTED`；`dayu/host/engine_ingest.py` 中的 `_EVENT_TYPE_ENGINE_EVENT_REJECTED`、`_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC`、`_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`、`_EVENT_TYPE_RUN_RECOVERING`、`_EVENT_TYPE_TOOL_AWAITING`、`_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED`、`_EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED`、`_EVENT_TYPE_RUN_WAITING`、`_EVENT_TYPE_ATTEMPT_SUSPENDED`。
- 增加 `_TERMINAL_STATUS_PAIRS` derived invariant 测试，断言它由 Run / Attempt terminal owner 集合派生，非法 Run / Attempt terminal pair fail-fast；新增 terminal status 时必须触发测试失败或显式扩展 closeout-supported 子集。

Validation：

```bash
source .venv/bin/activate && pytest \
  tests/host/test_lifecycle_events.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_run_api.py \
  tests/host/test_state_schema.py -q
source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
! rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
source .venv/bin/activate && pyright
git diff --check
```

SQL/query-plan validation：S2 必须验证 SQL helper 生成的 `IN (?, ...)` 不破坏 durable read helper 行为。可接受方式是新增 targeted durable state test，通过 `EXPLAIN QUERY PLAN` 或等价行为断言确认 `read_active_run_for_session`、`read_non_terminal_runs_for_session`、`read_non_terminal_runs` 使用 helper 生成的 params 后仍命中既有 session/status 过滤语义；若 SQLite planner 不展示稳定 index 名称，测试至少必须断言 helper SQL 与查询结果等价并记录 planner 输出。不能为了 planner 顾虑保留手写 status list。

README / docs decision：触及 Host internals 和 tests。implementation 必须实际检查 `dayu/host/README.md` 和 `tests/README.md`；只有确认 README 未描述或无需同步 lifecycle/status owner、测试运行类别时，才能记录不更新。

Rollback risk：中低。行为应保持等价，但跨模块 imports 可能触发 cycle；若出现 cycle，必须停止并裁决 event type owner module，而不是用 lazy import。

### S3. Host lifecycle closeout and lifecycle predicates

Objective：修复 synthetic EngineEvent、nullable terminal refs 与 dispatch predicate owner 漂移，完成 lifecycle/status propagation audit。

Allowed files/modules：

- `dayu/host/engine_ingest.py`
- `dayu/host/durable/state.py`
- `dayu/host/command.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_public_cancel_session_runs.py` 或现有覆盖 direct cancel 的测试

Exact allowed changes：

- 在 `engine_ingest.py` 内保留两条 typed closeout path，不引入 god-bag：
  - Engine-origin terminal closeout 继续使用现有 `EngineEventCandidate`。
  - Worker EOF/crash closeout 新增 `_HostLifecycleCloseoutCandidate`，字段必须是 Host lifecycle path 的必填事实，例如 `envelope`、`observed_at`、`worker_event_index`、`plan`、`lifecycle_source`、`execution_id`。不得用 optional-field probing 区分 Engine-origin 与 Host-lifecycle-origin。
  - 如果实现确实需要共享 internal closeout core，只能使用明确 tagged union：`TerminalCloseoutOrigin` discriminator + typed payload；禁止一个 dataclass 同时塞入互斥 optional Engine / Host 字段。
- Host lifecycle event id 使用独立命名空间，建议公式：

```text
event-host-lifecycle-{digest}

digest = sha256(
  "host-lifecycle-terminal"
  + session_id
  + run_id
  + attempt_id
  + execution_id
  + worker_event_index
  + event_class
  + event_type
  + sub_index
  + lifecycle_source
  + plan.reason
)
```

  其中 `event_class` 使用 canonical terminal class，`event_type` 是 `ATTEMPT_FAILED` / `RUN_FAILED` / `ATTEMPT_LOST` / `RUN_LOST` 等 Host terminal fact，`sub_index` 区分 Attempt / Run 两条 canonical facts。该 namespace 与现有 Engine-origin `_EVENT_ID_PREFIX = "event-engine-"` disjoint；duplicate terminal detection 必须按最终 event ids 查重，因此 Engine-origin candidate 和 Host-lifecycle candidate 不会因 id collision 互相吞掉。
- Host lifecycle candidate 不提供伪造 Engine event ref。若 audit payload 需要来源引用，使用明确 Host lifecycle ref，例如 `host-lifecycle:{execution_id}:{worker_event_index}:{lifecycle_source}:{plan.reason}`；该 ref 只是治理来源标签，不是 Engine event id 或业务事实。
- late rejection / closeout routing 不再读取 `candidate.engine_event.type` 作为唯一分支。Engine-origin path 可继续基于真实 `EngineEventType` 路由；Host-lifecycle path 必须基于 `_HostLifecycleCloseoutCandidate.lifecycle_source` / `plan.reason` / closeout plan kind 路由，例如 `worker_clean_eof` 与 `worker_lost`，并把该路由信息传给 `_late_rejection_reason` 或等价 helper。
- `_close_worker_lifecycle` 不再构造 `EngineEvent(type=RUN_FAILED)` / `EngineEventCandidate`。它应直接读取 durable context、做 duplicate terminal id 计算、late rejection、再调用 `_close_terminal` 或抽出的 closeout core。
- `_duplicate_terminal_result` 拆成 Engine candidate 与 Host lifecycle candidate 两条 typed identity path，或抽出接受 event-id tuple 的 helper；Host lifecycle path 必须使用上述 `event-host-lifecycle-` namespace。
- `_late_rejection_reason` 改用 `state.is_terminal_run_status(context.run.status)` 或 `state.is_terminal_attempt_status(context.attempt.status)`；保留 WAITING / SUSPENDED confirmation exception。
- active cancel late terminal 特判必须按下表实现或保持等价测试：

| Run 状态 | Incoming fact | Decision | Owner / recorded fact |
|---|---|---|---|
| `CANCELLING` | Engine-origin `FINAL_ANSWER` | reject as late terminal after active cancel | Host ingest writes existing rejected / diagnostic path; Engine event remains input, not Host terminal truth |
| `CANCELLING` | Engine-origin `RUN_FAILED` | reject as late terminal after active cancel | Host ingest writes existing rejected / diagnostic path; no Run terminal success/failure is accepted from Engine |
| `CANCELLING` | Host lifecycle worker clean EOF | do not synthesize Engine `RUN_FAILED`; record Host lifecycle diagnostic or no-op according to existing cancel closeout state, but do not convert to Run failed | Host lifecycle closeout owner records source as Host lifecycle diagnostic if a durable fact is needed; cancel watchdog / cancel transition remains terminal owner |
| `CANCELLING` | Host lifecycle worker lost/crash | do not accept as Engine `RUN_FAILED`; record Host lifecycle worker-lost diagnostic unless existing cancel/watchdog policy already closes Run | Host lifecycle closeout owner records worker-lost diagnostic; cancel watchdog / cancel transition remains terminal owner |
| `CANCELLING` | Other Engine events | reject or ignore by existing non-terminal stale-event rules; must not create terminal Run facts | Host ingest diagnostic / stale event owner |

  表内“diagnostic”不得伪装成 `RUN_FAILED` / Engine terminal event。若 implementation 发现现有 cancel/watchdog design 要求 worker crash 在 `CANCELLING` 时 first-committer-wins 写 `RUN_LOST`，必须停止并要求 design truth 裁决；不能在 P3-A 内自行改 active cancel semantics。
- 在 `durable/state.py` 新增 `is_dispatch_record_direct_cancelable(record: DispatchRecordRow) -> bool`，封装 `PENDING` / `WAITING_FOR_LANE` / pre-worker `DISPATCHING` 判定；`command.py:_is_direct_cancelable_dispatch_record` 删除或改为调用该 helper，不再直接检查 worker accepted nullable 字段。

Tests / expected assertions：

- `test_engine_ingest_mapping.py` 增加 worker clean EOF / worker lost closeout 测试，断言写入的 event ids 由 Host lifecycle identity 派生，EventLog payload 不包含伪造 Engine `run_failed` 语义；terminal facts 仍是 `ATTEMPT_FAILED/RUN_FAILED` 或 `ATTEMPT_LOST/RUN_LOST`。
- 增加 active cancel decision-table 测试：Engine-origin `FINAL_ANSWER` / `RUN_FAILED` 仍走 late terminal after active cancel；Host lifecycle worker clean EOF / lost 不会误归类为 synthetic Engine `RUN_FAILED`，只产生表内允许的 Host lifecycle diagnostic/no-op，且不写错误 Run failed terminal fact。
- 增加 `_late_rejection_reason` status predicate test：构造 status terminal 但 terminal refs 异常为空的 row 时仍拒绝 late event；构造 status non-terminal 但 refs 异常非空的 shape 应由 row validation / schema test fail closed，不让 late rejection 成为修复点。
- 增加 command direct cancel test 或 state helper unit test，断言 `is_dispatch_record_direct_cancelable` 覆盖 pending、waiting_for_lane、dispatching-before-worker-accepted、dispatching-after-worker-accepted、cancelled。

Validation：

```bash
source .venv/bin/activate && pytest \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_active_cancel_dispatch.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_public_cancel_session_runs.py \
  tests/host/test_run_attempt_transitions.py -q
source .venv/bin/activate && pyright
git diff --check
```

README / docs decision：S3 implementation 必须实际检查 `dayu/host/README.md` 是否描述 “EngineEvent -> Host facts”、worker lifecycle、cancel/watchdog 或 lifecycle owner boundary；如描述受影响，按 README Agent 更新约束更新。也必须检查 `tests/README.md` 是否需要记录新增测试类别或命令；不能用预计结论替代检查。

Rollback risk：中。`engine_ingest.py` closeout path 是关键路径；主要风险是 duplicate id 与 existing terminal detection 变化。S3 必须在 S1/S2 helper 稳定后实施，且不能与 final answer projection P3-B 混做。

## 6. Propagation audit plan

Implementation 完成后必须在 implementation artifact 中列出以下 audit：

- Run terminal event type：`RunStatus` / `HostRunEventType` owner helper -> durable transition producer -> EventLog `event_type` -> durable Run row status -> read model / outbox / HostEvent / memory consumers。Verification：mandatory terminal event source scan passes；transition tests assert EventLog `event_type` equals `run_terminal_event_type_for_status(status).value`; read/projection tests consume the resulting status/event without local terminal string mapping.
- Attempt terminal event type：`AttemptStatus` / `HostAttemptEventType` owner helper -> durable transition / engine ingest terminal closeout -> EventLog `event_type` -> durable Attempt row status -> recovery / cancel / diagnostic consumers。Verification：owner tests assert supported Attempt terminal statuses map through helper; engine ingest mapping tests assert terminal closeout uses helper-derived values; source scan shows no duplicate Attempt terminal constants outside owner.
- Run status predicate：`_row_rules.TERMINAL_RUN_STATUS_VALUES` -> `state.TERMINAL_RUN_STATUSES` / `NON_TERMINAL_RUN_STATUSES` / `START_BLOCKING_RUN_STATUSES` -> admission / SQL read helpers / read model / purge。Verification：state schema tests assert derivation and exact start-blocking set; source scan/review confirms consumers call `state.is_terminal_run_status` or SQL helper; SQL/query-plan or equivalent durable state tests validate generated `IN` helper behavior.
- Worker lifecycle closeout：worker EOF/crash signal -> Host lifecycle candidate -> Host-owned event ids -> terminal closeout transaction -> status row update -> projection catch-up。Verification：worker clean EOF/lost tests assert event ids start with `event-host-lifecycle-`, do not collide with `event-engine-`, and EventLog payload/source does not contain forged Engine `run_failed`; projection/read tests confirm final status derives from the same transaction.
- Late event rejection：durable Run / Attempt status -> `is_terminal_*` predicate -> rejected diagnostic or accepted waiting confirmation；nullable terminal refs remain row consistency fields only。Verification：tests cover terminal status with missing terminal refs still rejects late terminal input, while non-terminal status with malformed refs fails at row validation/schema boundary; active-cancel decision-table tests cover Engine-origin vs Host lifecycle routing.
- Direct cancelability：dispatch record row -> durable state predicate -> command cancel branch -> transition row update / terminal facts。Verification：state helper or command tests cover pending、waiting_for_lane、dispatching-before-worker-accepted、dispatching-after-worker-accepted、cancelled；source review confirms command no longer inspects worker accepted nullable fields directly.

每条 audit 都必须确认 durable state、EventLog、diagnostic、projection、用户/LLM 可见输出没有从不同真源重建同一 lifecycle/status 事实。

## 7. Completion report format

Implementation agent 完成每个 slice 时使用：

```text
status: completed | blocked
slice: S1 | S2 | S3
changed files:
tests:
pyright:
README decision:
propagation audit:
risks / residual owner:
```

本 plan gate 完成报告使用用户指定格式。
