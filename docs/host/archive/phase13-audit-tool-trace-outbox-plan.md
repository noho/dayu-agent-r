# Host Phase 13 Audit / Tool Trace / Outbox Projections Handoff Plan

## Gate

当前 gate：Phase 13 handoff implementation-ready plan。

本文档只供 implementation agent 使用：本次 planning work unit 不修改 `dayu/` 源码、不修改 tests、不修改 README、不提交、不 push、不创建 PR。

## Goal / Motivation / Success Signals

目标是在 Phase 8 已落地的 committed EventLog projection framework 上实现三类派生能力：

- `LogAuditSink`：append-only JSONL audit sink，记录治理责任链与可追溯 refs。
- Tool Trace：hot JSON projection + cold JSONL writer，支持 provider / tool diagnostic refs 查询。
- Outbox：terminal/final-answer delivery queue projection，以及唯一允许的 Phase 13 additive public read / drain API。

动机成立，严重性没有被高估。第一性原理判断如下：

- Host durable truth 已由 Session / Run / Attempt / EventLog 与同事务 state indexes 承担；Audit / Tool Trace / Outbox 只解决可观测性、诊断与离线 terminal notification，不需要也不应进入 command path。
- P10.5 已冻结 `watch_session_events(session_id)` 为 live-only 主事件入口，但明确留下离线 terminal/final answer 补读缺口；Outbox 是补这个缺口的最小 projection，不是完整 timeline。
- ToolRuntime、Engine ingest、Context Governance 已在 EventLog payload / refs 中保留诊断来源；Phase 13 的 root cause 不是缺少新的治理事实，而是缺少稳定的 sink / projection 消费、存储和查询边界。

成功信号：

- Audit / Tool Trace / Outbox 均只消费 committed EventLog，通过 `event_sequence` checkpoint 追平，并按 `event_id` / terminal identity 幂等。
- 任一 sink 写文件、写 projection、查询或 catch-up 失败，只产生 sink-local failure / lag，不回滚 EventLog，不影响 Run terminal、recovery、resume、memory 或 command path 成功条件。
- `LogAuditSink` 写 append-only JSONL，行内含治理责任链 refs；不复制大 payload，不替代 tool trace。
- Tool Trace hot projection 可按 `run_id`、`tool_name`、`tool_call_id`、`provider_request_id`、diagnostic refs 查询；cold JSONL 保存长参数 / 长结果 / 截断 / duplicate / wait / provider 细节 refs。
- OutboxSink 从 terminal canonical facts 派生 terminal delivery items；重复扫描不创建重复 item。
- Service 可通过 Outbox read / drain API 按 terminal watermark + seen terminal ids 补读离线 terminal/final answer，并与随后或并发的 `watch_session_events(session_id)` 用 `terminal_event_id` / `event_sequence` / `run_id` 去重。
- `watch_session_events(session_id)` 不新增 cursor / replay 参数，不合并 Outbox，不改变 live-only 语义。

## Non-goals / Scope Boundaries

不做：

- 不修改 Engine；若 implementation 发现必须改 Engine，立即停止并作为 blocking question 交给 controller。
- 不改变 EventLog append 语义、Run / Attempt governance state、terminal transaction、recovery、resume、memory truth、Context Governance 或 ToolRuntime accept barrier。
- 不把 Audit / Tool Trace / Outbox 当作恢复、resume、memory、Run 状态迁移或 final answer truth。
- 不把 Outbox 合并进 `watch_session_events(...)`，不为 live watch 加 cursor / replay 参数。
- 不补完整 timeline、reasoning、progress、preview、streaming content 或 Run detail read model。
- 不实现 Service / UI / channel delivery state、channel exactly-once、WeChat / Web / GUI 绑定、客户端 seen state 持久化或投递成功状态。
- 不实现外部 audit 系统、AuditPolicy 规则引擎、长期归档策略、retention cleanup、purge tombstone audit record、outbox cleanup、tool trace cleanup 或 purge destructive cleanup；这些统一归 Phase 15 Retention / Purge / Production Hardening。
- 不把 tool trace cold JSONL 当作恢复、resume、memory 或治理状态真源。
- 不做旧 schema 兼容读取、旧库迁移测试、compat re-export、compat wrapper 或 facade。

必须保持：

- `watch_session_events(session_id)` 是普通 Service-facing live Host event stream，仍不接收 cursor。
- terminal transaction 不同步写 outbox / audit / trace 表或 JSONL；command path 只 append canonical facts 与必要 Host state indexes。
- Sink catch-up 可以由 opener close、read/drain 前 best-effort catch-up 或后台 runner 触发，但正确性来自 EventLog replay + checkpoint，不来自内存通知。

## Direct Evidence

设计真源证据：

- `docs/host/design.md` §2：Observer / Sink / Projection 只消费 committed EventLog，维护派生视图和外部投递队列；Projection、timeline、audit、tool trace、outbox、memory snapshot 不能反向成为 EventLog 真源。
- `docs/host/design.md` §14：Sink 必须按 `event_sequence` checkpoint 追平，按 canonical `event_id` 幂等消费；Sink failure 只能更新 sink-local retry / error state，不能回滚 EventLog 或改变 Run / Attempt。
- `docs/host/design.md` §14.1：Tool trace 是 EventLog 派生 projection，不是 Host durable truth；hot JSON 保存近期可查询 summary，cold JSONL 保存归档细节；损坏或缺失只能影响诊断。
- `docs/host/design.md` §15：Audit 不是事实真源；`LogAuditSink` 第一版写本地 append-only JSONL，路径由 typed options 注入且可有默认值；失败只产生 sink-local error / lag。
- `docs/host/design.md` §16：Outbox 只补未 attach / 离线期间 terminal/final answer notification，不补完整中间过程；OutboxSink 按 checkpoint 扫描 terminal EventLog facts 并 upsert item。
- `docs/host/design.md` P10.5 约束：`watch_session_events(session_id)` 是 live watch，不接收 cursor，不承担离线补读；Service 保存 terminal watermark / seen terminal ids 并与 Outbox 去重。

控制真源证据：

- `docs/host/implementation-control.md` 当前状态：Phase 13 design discussion 已由用户确认，当前 gate 是 handoff implementation-ready plan。
- `docs/host/implementation-control.md` Phase 13：允许修改 LogAuditSink、tool trace hot JSON projection、tool trace cold JSONL writer、OutboxSink、sink-local retry / error state、相关 read / analyze support；禁止修改 EventLog append 语义、Run / Attempt governance state、terminal transaction、UI / Service channel delivery 状态。
- `docs/host/implementation-control.md` Phase 13 tracking：需落地 durable tool trace hot / cold storage、provider request 排错链、terminal delivery outbox、projection concrete sinks 与 outbox read / drain API。

裁决证据：

- `docs/reviews/phase13-design-discussion-controller-adjudication-20260529.md` D1-D5 已确认：Audit / Tool Trace / Outbox 全部保持 projection / sink；Outbox 只补离线 terminal/final answer notification；Outbox read / drain API 是唯一 Phase 13 additive public extension；LogAuditSink 第一版 append-only JSONL；Tool Trace 第一版 hot JSON projection + cold JSONL writer。

## Affected Files / Modules

允许修改：

- `dayu/host/api.py`：新增 Outbox read / drain public dataclass、枚举和 `Host` Protocol additive methods；不得修改既有 request / response 字段语义。
- `dayu/host/__init__.py`：只导出 Outbox additive public API 类型与方法名称；不得做兼容 re-export。
- `dayu/host/open_host.py`：在 public handle 上接入 Outbox read / drain methods；组合 memory + audit + tool trace + outbox projection catch-up port；从既有 `artifact_root` 派生默认 JSONL 路径。
- `dayu/host/projection.py`：仅在现有 runner 无法复用时做窄幅扩展；不得改变 checkpoint 语义。
- `dayu/host/audit.py`、`dayu/host/tool_trace.py`、`dayu/host/outbox.py`：新增 concrete consumers / sink options / repair helpers / query helpers。
- `dayu/host/durable/audit.py`：只在需要记录 JSONL logical idempotency marker 时新增 audit sink-local durable helper；不得成为 audit truth。
- `dayu/host/durable/tool_trace.py`、`dayu/host/durable/outbox.py`：新增 projection-owned row codecs、query、upsert、reset helpers。
- `dayu/host/durable/schema.py`：fresh schema bump，新增 projection-owned tables / indexes / constants。
- `dayu/host/read_api.py`：只允许接入 Outbox read / drain public helper；不得改变 `get_run`、`get_session`、`stream_run_events` 或 session live watch cursor semantics。
- `utils/`：可新增 narrow analyze helper 读取 audit / tool trace JSONL，但不是 Phase 13 必需项。
- `tests/host/*`、`tests/README.md`、`dayu/host/README.md`：implementation 阶段按触发规则补测试和文档。

禁止修改：

- `dayu/engine/**`。
- `dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`。
- `dayu/host/admission.py`、`dayu/host/command.py`、`dayu/host/durable/run_transition.py`、`dayu/host/durable/state.py` 的 command / state-machine 语义；若发现必须修改，停止交 controller。
- `watch_session_events(...)` signature、`HostEvent` terminal final answer shape、EventLog append primitive、terminal closeout transaction。
- README 在本 planning work unit 中不得修改；implementation 完成并验证后再按触发规则更新。

## Public Contract Changes

Phase 13 唯一 additive public extension 是 Outbox read / drain API。不得新增 `OpenHostOptions` public 字段。LogAuditSink / Tool Trace 路径注入在 sink constructor 层完成；production `open_host` 第一版从既有 `OpenHostOptions.artifact_root` 派生默认路径，避免扩大 public construction surface。

### API Shape

新增 public 类型建议放在 `dayu.host.api` 并从包根导出：

```text
OutboxTerminalItemState(StrEnum)
  PENDING = "pending"
  DRAINED = "drained"

OutboxProjectionStatus(StrEnum)
  CAUGHT_UP = "caught_up"
  LAGGED = "lagged"
  FAILED = "failed"

@dataclass(frozen=True, slots=True)
OutboxTerminalCursor
  event_sequence: int

@dataclass(frozen=True, slots=True)
OutboxTerminalItem
  item_id: str
  idempotency_key: str
  terminal_event_id: str
  event_sequence: int
  session_id: str
  run_id: str
  terminal_status: HostTerminalStatus
  dedupe_key: str
  final_answer: HostFinalAnswerView | None
  error_message: str | None
  cancel_reason: str | None
  result_ref: str | None
  result_digest: str | None
  terminal_summary_ref: str | None
  terminal_summary_digest: str | None
  projected_at: datetime
  item_state: OutboxTerminalItemState

@dataclass(frozen=True, slots=True)
ReadOutboxTerminalItemsRequest
  after: OutboxTerminalCursor
  seen_terminal_event_ids: tuple[str, ...]
  limit: int

@dataclass(frozen=True, slots=True)
DrainOutboxTerminalItemsRequest
  context: HostCallContext
  after: OutboxTerminalCursor
  seen_terminal_event_ids: tuple[str, ...]
  limit: int
  drain_request_id: str

@dataclass(frozen=True, slots=True)
OutboxTerminalItemsBatch
  items: tuple[OutboxTerminalItem, ...]
  next_cursor: OutboxTerminalCursor
  scanned_watermark: OutboxTerminalCursor
  projection_checkpoint: OutboxTerminalCursor
  projection_status: OutboxProjectionStatus
  projection_error_code: str | None
  projection_error_message: str | None
  has_more: bool

Host.read_outbox_terminal_items(
  session_id: str,
  request: ReadOutboxTerminalItemsRequest,
) -> Awaitable[OutboxTerminalItemsBatch]

Host.drain_outbox_terminal_items(
  session_id: str,
  request: DrainOutboxTerminalItemsRequest,
) -> Awaitable[OutboxTerminalItemsBatch]
```

Validation rules:

- `event_sequence` 必须为非负整数，`limit` 必须为正整数且不超过模块级上限，例如 `HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT`。
- `seen_terminal_event_ids` 为 tuple，元素非空、去重，长度上限使用模块级常量。
- `drain_request_id` 非空；同一 request id 重复调用必须返回同一 logical drain result 或结构化 idempotency conflict，不得重复 drain 新 item。
- 不使用 `object`、`Any`、无类型参数、裸 dict/list/set public signature。

### Cursor / Watermark

- `after.event_sequence` 是客户端保存的 terminal watermark，查询语义为严格返回 `event_sequence > after.event_sequence` 的 terminal items。
- `seen_terminal_event_ids` 是 overlap 去重集合，用于 live watch 与 Outbox 并发 attach 时过滤已展示 terminal event；不得用 final answer 文本去重。
- `scanned_watermark` 表示本次查询事务实际扫描到的最高 Outbox terminal item sequence；即使 item 因 `seen_terminal_event_ids` 被过滤，也允许推进到该 scanned watermark。
- `next_cursor` 是调用方可保存的推荐 terminal watermark；若 `projection_status != CAUGHT_UP`，调用方不得把 `next_cursor` 当作最终已无遗漏证明，只能结合 `projection_checkpoint` 决定是否 retry。
- `projection_checkpoint` 是 OutboxSink 当前已成功追平的 EventLog sequence；它是 projection status，不是 EventLog truth，也不是 live watch cursor。

### Idempotency / Dedupe

- Outbox item identity：`item_id = "outbox-terminal-" + sha256(terminal_event_id, run_id, result_digest_or_payload_digest)` 或等价稳定算法；必须以 terminal event identity、`run_id`、result digest/ref 为输入，不得以 final answer 文本为主键。
- `idempotency_key` 是 OutboxSink durable upsert 与 drain idempotency 使用的稳定幂等键，由 `terminal_event_id`、`run_id` 与 result digest/ref 派生；它属于 Host projection 内部持久化语义，UI / Service 不应依赖它做消息去重。
- `dedupe_key` 是 UI / Service 与 live `HostEvent.dedupe_key` 对齐的去重键，固定等于 `terminal_event_id`。Phase 13 不允许使用 `run_id + terminal_event_id` 或其它复合替代写法；未来若要改变 dedupe 规则，必须同步修改 `HostEvent.dedupe_key` 的 public contract。
- OutboxSink 重放同一 terminal event 时返回 duplicate，不得新增第二条 item。
- `drain_outbox_terminal_items` 的 side effect 只更新 Outbox projection queue state 和 drain idempotency row；它不表示 channel 投递成功，不写 EventLog，不更新 Run / Attempt。
- `read_outbox_terminal_items` 不写 EventLog，不更新 Run / Attempt，不改变任何 Outbox item 的 `item_state`，也不写 channel delivery state。它允许在返回前 best-effort catch up OutboxSink；该 catch-up 只能写 projection-local rows、sink-local failure row 与 `host_projection_checkpoints`，不能越过 projection 边界。

### Error Semantics

- Host handle closed：抛 `HostClosedError`，不写 EventLog。
- Session 不存在 / purge 后 gone：抛现有 typed `HostApiError` not-found / gone code；不新增 command fact。
- Request validation failure：dataclass `__post_init__` 抛 `TypeError` / `ValueError`。
- Durable query failure：抛现有 durable / Host API error；不改变 projection checkpoint。
- OutboxSink catch-up failure：返回已投影 rows 加 `projection_status=FAILED`、`projection_error_code`、`projection_error_message`；不得伪装为完整补读，不得静默返回 stale empty。若实现选择抛 retryable `HostApiError`，必须先在 plan review 中确认 error code，不得临场扩展。
- Projection lag：catch-up 未运行、批量上限未追到 EventLog high watermark 或 projection checkpoint 落后时，返回 `projection_status=LAGGED` 与 `projection_checkpoint`；Service 不应把空结果解释为“无 terminal”，除非 `projection_status=CAUGHT_UP` 且 `has_more=False`。

### Live Watch 去重 / 防漏协议

Implementation tests 必须覆盖两个 attach 形态：

- live-first：先打开 `watch_session_events(session_id)`，再调用 `read_outbox_terminal_items` 或 `drain_outbox_terminal_items`；Service 用 `terminal_event_id` / `event_sequence` / `run_id` upsert，重复 item 不重复展示。
- drain-first：先 Outbox read/drain，再打开 `watch_session_events(session_id)`，随后用同一 saved watermark + 已 seen terminal ids 做第二次 Outbox read；第二次 read 负责覆盖第一次 read 与 live attach 之间的 terminal window。不得要求 `watch_session_events` 支持 cursor。

禁止声称单次 drain-first read + later live watch 天然无漏；没有 live watch cursor 时必须通过第二次 Outbox read 或 live-first overlap 证明防漏。

## Storage / Schema / Checkpoint Decisions

当前 `HOST_SCHEMA_VERSION` 为 `10`。Phase 13 implementation 必须 fresh schema bump 到 `11`。若实施前版本已变化，implementation agent 必须停下交 controller，不得静默猜测。

新增表全部是 projection-owned / sink-local，不是 Host governance truth。建议：

- `host_tool_trace_hot`
  - `trace_id TEXT PRIMARY KEY`，建议等于 source `event_id` 或稳定派生 id。
  - `event_id TEXT NOT NULL UNIQUE`，`event_sequence INTEGER NOT NULL`。
  - `session_id TEXT NOT NULL`、`run_id TEXT NULL`、`attempt_id TEXT NULL`、`execution_id TEXT NULL`。
  - `event_type TEXT NOT NULL`、`tool_call_id TEXT NULL`、`tool_name TEXT NULL`。
  - `provider_request_id TEXT NULL`、`diagnostic_ref TEXT NULL`。
  - `normalized_arguments_digest TEXT NULL`、`semantic_input_digest TEXT NULL`、`result_digest TEXT NULL`、`payload_ref TEXT NULL`、`payload_digest TEXT NULL`。
  - `policy_decision_json TEXT NULL`、`trace_summary_json TEXT NOT NULL`、`cold_trace_ref TEXT NULL`、`cold_trace_digest TEXT NULL`。
  - `projected_at TEXT NOT NULL`、`updated_at TEXT NOT NULL`。
  - indexes：`run_id,event_sequence`、`tool_name,event_sequence`、`tool_call_id`、`provider_request_id`、`diagnostic_ref`。
- `host_outbox_terminal_items`
  - `item_id TEXT PRIMARY KEY`、`idempotency_key TEXT NOT NULL UNIQUE`。
  - `terminal_event_id TEXT NOT NULL UNIQUE`、`event_sequence INTEGER NOT NULL`。
  - `session_id TEXT NOT NULL`、`run_id TEXT NOT NULL`。
  - `terminal_status TEXT NOT NULL`、`dedupe_key TEXT NOT NULL`。
  - `final_answer_json TEXT NULL`、`error_message TEXT NULL`、`cancel_reason TEXT NULL`。
  - `result_ref TEXT NULL`、`result_digest TEXT NULL`、`terminal_summary_ref TEXT NULL`、`terminal_summary_digest TEXT NULL`。
  - `item_state TEXT NOT NULL CHECK item_state IN ('pending','drained')`。
  - `projected_at TEXT NOT NULL`、`updated_at TEXT NOT NULL`、`drained_at TEXT NULL`、`last_drain_request_id TEXT NULL`。
  - indexes：`session_id,event_sequence`、`item_state,event_sequence`、`run_id`。
- `host_outbox_drain_idempotency`
  - `session_id TEXT NOT NULL`、`drain_request_id TEXT NOT NULL`。
  - `request_digest TEXT NOT NULL`、`batch_item_ids_json TEXT NOT NULL`、`created_at TEXT NOT NULL`。
  - primary key `(session_id, drain_request_id)`。
- Optional `host_audit_sink_markers`
  - 仅作为 LogAuditSink normal retry logical idempotency marker：`event_id TEXT PRIMARY KEY`、`event_sequence INTEGER NOT NULL`、`line_digest TEXT NOT NULL`、`written_at TEXT NOT NULL`。
  - 这不是 audit event store，不作为 audit truth，也不作为 audit 查询真源；JSONL 行仍是 audit artifact，EventLog 仍是 Host truth。

Cold JSONL 与 audit JSONL 不进入 SQLite schema；路径由 sink options 注入。第一版默认路径：

- audit：`artifact_root / "audit" / "host-audit.jsonl"`。
- tool trace cold：`artifact_root / "tool-trace" / "tool-trace-cold.jsonl"`。
- lock path 使用相邻 `.lock`，可复用 `dayu.runtime.filelock`；不得用 file lock 表达 Host truth。

Checkpoint：

- 复用 `host_projection_checkpoints` / `host_projection_failures`。
- consumer ids：
  - `host.audit-log-jsonl`
  - `host.tool-trace`
  - `host.outbox-terminal`
- checkpoint 只在 consumer projection write / JSONL logical append 成功后推进。
- failure row 不推进 checkpoint；后续 retry 成功后清除 failure。

JSONL crash residual：

- 本地 append-only JSONL 与 SQLite checkpoint 无法形成真正跨介质原子事务。Implementation 必须用 `event_id` / line digest marker 避免 normal retry 重复 append；若进程在 file append 成功、marker/checkpoint 提交前崩溃，物理 JSONL 可能出现重复 `event_id` 行。
- 该风险不影响 Host truth。Audit / trace analyze helper 必须按 `event_id` 逻辑去重，并在 residual risk 中保留“跨介质 exactly-once 非目标”。

## LogAuditSink JSONL

Sink options：

```text
@dataclass(frozen=True, slots=True)
LogAuditSinkOptions
  audit_jsonl_path: Path
  create_parent_dirs: bool
  lock_path: Path | None
```

字段最小集合：

- `schema_version`
- `event_sequence`
- `event_id`
- `event_type`
- `event_class`
- `occurred_at`
- `session_id`
- `run_id`
- `attempt_id`
- `execution_id`
- `actor`
- `principal`
- `source`
- `client_request_id`
- `operation_context_refs`
- `operation_context_digest`
- `policy_decision_ref`
- `policy_decision_summary`
- `reason`
- `payload_ref`
- `payload_digest`
- `line_digest`

实现要求：

- 从 `ProjectionEventView` 与 EventLog row typed fields 构造 audit line；不读取 raw EngineEvent，不读取 Service/UI 状态。
- actor / principal / source 缺失时写 `null` 或结构化 `"unknown"` 需统一，不能从 prompt 文本推断。
- 不写大 payload，不复制 tool trace cold detail。
- 文件写失败抛给 `ProjectionRunner`，由 runner 写 projection-local failure；不得影响 command path。
- `NoopAuditSink` 只允许显式测试 / 开发配置，不作为 production opener 默认。

## Tool Trace Hot / Cold

事件输入：

- canonical facts whitelist：
  - tool / wait chain：`TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED`、`TOOL_AWAITING`、`RUN_WAITING`、wait resolution 产生的 `TOOL_RESULT_ACCEPTED`、`WAIT_LATE_RESULT_REJECTED`。
  - context/provider refs：`CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`、`CONTEXT_COMPACTION_ATTEMPT_REJECTED`，但仅抽取已有 typed payload 中的 provider / artifact / diagnostic refs。
  - terminal provider chain：`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`；`RUN_LOST` 只允许作为 skipped detail，不生成 public Outbox item。
- diagnostic / preview whitelist：
  - `event_class=diagnostic` 且 `event_type=ENGINE_EVENT_DIAGNOSTIC`，仅当 typed payload 中存在 `provider_request_id`、`engine_event_type=CONTEXT_COMPACTION_REQUESTED` 或 `engine_event_type=RUN_SUSPENDED` 之一。
  - `event_class=diagnostic` 且 `event_type=PROVIDER_PROTOCOL_ERROR`。
  - `event_class=canonical_fact` 且 `event_type=USAGE_REPORTED`，仅抽取 provider request / usage digest refs，不把 usage 当 Tool Trace truth。
  - 第一版不消费任意 preview stream delta；如 Slice 2 发现必须消费 preview 才能满足 provider / tool diagnostic refs 查询，必须停止交 controller。
- terminal events：`RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` 只抽取 provider_request_id、engine_event_ref、terminal_summary refs 用于 provider request chain，不复制 final answer 大文本。

Slice 2 的第一步必须做 typed whitelist discovery：逐项核对上述 event_type 是否已存在、payload view 是否有强类型字段、字段是否足以构造 hot/cold trace。不得用无结构全量 diagnostic payload 兜底；一旦需要 Engine 或 ToolRuntime contract change 才能取得必要 refs，立即停止交 controller。

Hot JSON fields：

- source identity：`event_id`、`event_sequence`、`event_type`、`event_class`。
- scope：`session_id`、`run_id`、`attempt_id`、`execution_id`。
- tool identity：`tool_call_id`、`tool_name`、`tool_schema_digest`、`tool_identity_digest`。
- semantic refs：`normalized_arguments_digest`、`semantic_input_digest`、`duplicate_key`、`duplicate_decision`、`reuse_prior_event_refs`。
- result refs：`payload_ref`、`payload_digest`、`result_digest`、`outcome_digest`、`evidence_anchor_refs`。
- governance：`policy_decision_json`、`truncation_json`、`await_json`、`error_code`、`duration_ms`。
- provider diagnostics：`provider_request_id`、`engine_event_ref`、`provider_error_ref`、`diagnostic_refs`。
- cold link：`cold_trace_ref`、`cold_trace_digest`。

Cold JSONL fields：

- hot fields 的 superset。
- long args/result summaries, truncation metadata, duplicate governance context, wait/cancel/timeout detail, provider / tool raw diagnostic refs。
- 不写可恢复 truth，不反向驱动 memory。

查询：

- internal query helpers：
  - `read_tool_trace_by_run(run_id: str, after_event_sequence: int, limit: int) -> ToolTraceQueryPage`
  - `find_tool_trace_by_tool_call_id(tool_call_id: str, after_event_sequence: int, limit: int) -> ToolTraceQueryPage`
  - `find_tool_trace_by_provider_request_id(provider_request_id: str, after_event_sequence: int, limit: int) -> ToolTraceQueryPage`
  - `find_tool_trace_by_diagnostic_ref(diagnostic_ref: str, after_event_sequence: int, limit: int) -> ToolTraceQueryPage`
- `ToolTraceQueryPage` 是 internal frozen / slots dataclass，至少包含 `rows: tuple[ToolTraceHotRow, ...]`、`next_event_sequence: int`、`has_more: bool`。所有 helper 均按 `event_sequence ASC` 返回 `event_sequence > after_event_sequence` 的匹配 row，`limit` 为正整数且有模块级上限。相同 `tool_call_id` / `provider_request_id` / `diagnostic_ref` 可返回多行，不得由 helper 隐式只取最新一条。
- 这些 helper 第一版不作为 Service-facing public API 导出；如 implementation 认为必须 public，停止交 controller。

## OutboxSink

事件输入：

- terminal canonical facts：`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST`。
- `RUN_SUCCEEDED` 必须尽力携带 final answer view 所需 refs / summary；若 EventLog terminal payload 只能提供 summary ref，Outbox item 写 refs，不读取 internal payload reader 作为 public result API。

Item derivation：

- `terminal_event_id = event.event_id`。
- `event_sequence = event.event_sequence`。
- `run_id` / `session_id` 来自 source EventLog。
- `terminal_status` 从 event_type 映射到 `HostTerminalStatus`；Phase 13 第一版 OutboxSink 对 `RUN_LOST` 返回 `ProjectionApplyResult(SKIPPED, detail_code="run_lost_not_public_terminal_item")`，不创建 public terminal item。LOST notification / outbox item 化必须进入 recovery / public terminal contract gate 后再议。
- `dedupe_key = terminal_event_id`，固定与 live `HostEvent.dedupe_key` 对齐。
- final answer 只用于 succeeded item；failed/cancelled item 使用 error/cancel fields。

Read / drain：

- read/drain 前可运行 OutboxSink catch-up 到当前 EventLog high watermark；catch-up 只能产生 projection-local writes，失败通过 `projection_status=LAGGED` 或 `projection_status=FAILED` 暴露。
- read 返回所有 matching item，不因 `item_state=DRAINED` 隐藏 session reconnect 所需 terminal item。
- drain 只把 returned item 标记为 `DRAINED`，用于 queue worker 竞争；不表示 channel delivery success。
- drain idempotency 按 `(session_id, drain_request_id)` 固定；同一 request digest 重放返回同一 item id 集合，不重复改变其它 item。

## Implementation Slices

建议 4 个 slices。不得超过下述范围扩展；任一 slice 发现需要修改 Engine、command path 状态机、terminal transaction 或 `watch_session_events` signature，立即停止。

### Slice 1. LogAuditSink JSONL

Objective：落地 append-only audit JSONL sink、sink-local idempotency marker、默认路径派生和测试。

Allowed files：

- `dayu/host/audit.py`
- `dayu/host/durable/audit.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_durable_schema.py`

Exact changes：

- 新增 `LogAuditSinkOptions`、`LogAuditSink` projection consumer、audit line typed builder。
- consumer id 使用 `host.audit-log-jsonl`。
- 使用 `ProjectionEventFilter` 消费 audit-relevant canonical facts，默认不消费 preview。
- 通过 sink-local marker 避免 normal retry 重复 append；JSONL 行包含 `line_digest`。
- `open_host` 从 `artifact_root` 派生默认 audit path，并纳入 composite projection catch-up close flush。

Non-goals：

- 不实现外部 audit 系统、audit query UI、purge tombstone audit record、purge cleanup 或 retention matrix；purge 相关 audit / outbox / tool trace 行为归 Phase 15。
- 不新增 public options。

Tests：

- JSONL line 字段完整性。
- checkpoint / duplicate replay 不重复 logical audit event。
- 文件写失败只写 projection failure，不推进 checkpoint。
- audit sink 不修改 Run / Attempt / EventLog。

Stop condition：

- 需要 command path 同步写 audit 或新增 `OpenHostOptions` 字段时停止。

### Slice 2. Tool Trace Hot JSON / Cold JSONL

Objective：落地 tool trace hot projection、cold JSONL writer、provider/tool diagnostic refs 查询。

Allowed files：

- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_durable_schema.py`

Exact changes：

- 新增 `ToolTraceSinkOptions`、`ToolTraceProjectionConsumer`、hot row codec、cold JSONL writer。
- schema 新增 `host_tool_trace_hot` 与 indexes。
- Slice 起步先做 typed EventLog whitelist discovery，逐项确认计划中列出的 canonical / diagnostic event_type 与 payload view；不得自行扩大到未命名 diagnostic event。
- 从 typed EventLog payload 抽取 tool/provider refs；不能用 `getattr`/`hasattr` 逃避 payload schema。
- hot row 与 cold line 均携带 event/session/run/attempt/execution identity 与 operation context refs/digest。
- 新增 internal query helpers by run/tool_call/provider_request/diagnostic_ref，返回 `ToolTraceQueryPage`，按 `event_sequence ASC` 分页。

Non-goals：

- 不新增 public Service-facing trace API。
- 不把 cold JSONL 当恢复或 memory truth。

Tests：

- `TOOL_CALL_REQUESTED` / `TOOL_CALL_GOVERNED` / `TOOL_RESULT_ACCEPTED` 投影字段。
- provider_request_id terminal diagnostic 查询。
- cold writer failure 只造成 projection failure。
- projection rebuild from EventLog 恢复 hot rows。

Stop condition：

- EventLog 现有 payload 缺少必要 provider/tool refs、白名单 event_type 不存在、payload view 无强类型字段，且需要改 Engine 或 ToolRuntime accept contract 时停止交 controller。

### Slice 3. OutboxSink Durable Projection

Objective：落地 terminal delivery queue projection、item identity、idempotent upsert、read/drain durable helpers。

Allowed files：

- `dayu/host/outbox.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_outbox_durable.py`
- `tests/host/test_durable_schema.py`

Exact changes：

- schema 新增 `host_outbox_terminal_items`、`host_outbox_drain_idempotency` 与 indexes。
- 新增 `OutboxTerminalProjectionConsumer`，consumer id `host.outbox-terminal`。
- 从 terminal canonical facts upsert item；重复 replay 返回 duplicate。
- `RUN_LOST` 返回 skipped + `detail_code="run_lost_not_public_terminal_item"`，不创建 public terminal item。
- 实现 read rows after cursor + seen ids filtering + scanned watermark。
- 实现 drain idempotency、item_state update；drain 不写 EventLog，不记录 channel success。

Non-goals：

- 不接 public Host handle。
- 不改 RunSnapshot `outbox_summary`，除非已有 read snapshot owner 明确需要且不改变 public semantics；默认保持独立 read/drain API。

Tests：

- item idempotency key 稳定。
- same terminal event replay 不重复。
- read cursor / seen ids / `has_more` / scanned watermark。
- drain request idempotency conflict。

Stop condition：

- 需要把 outbox item 写入 terminal transaction，或需要 session live watch cursor 才能证明防漏时停止。

### Slice 4. Public Outbox Read / Drain API And Offline Smoke

Objective：将 Outbox read/drain 作为唯一 additive public extension 接到 `Host` Protocol / `_PublicHostHandle`，并用 smoke 证明离线补读与 live watch 去重。

Allowed files：

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/open_host.py`
- `dayu/host/read_api.py`
- `dayu/host/outbox.py`
- `tests/host/test_public_outbox_api.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_open_host_runtime.py`
- `dayu/host/README.md`
- `tests/README.md`

Exact changes：

- 新增 public dataclasses / enums / constants / `Host` Protocol methods。
- `_PublicHostHandle.read_outbox_terminal_items(...)` 与 `drain_outbox_terminal_items(...)` 先检查 closed handle，再验证 session，再 best-effort catch up OutboxSink，最后返回 batch。
- 包根导出新增类型与方法名；不移除旧导出。
- Composite projection catch-up port close flush memory + audit + trace + outbox；每个 sink failure 只记录日志 / failure row，close 不伪造 command facts。
- Smoke 覆盖 live-first 与 drain-first + second-read 防漏协议。
- README 只按触发规则更新 Host public interface / tests 说明，不写过程状态。

Non-goals：

- 不新增 `wait_final_answer(...)`、`get_run_result(...)`、payload reader 或 timeline replay API。
- 不新增 `OpenHostOptions` 字段。

Tests：

- API validation / closed handle / session not found。
- projection lag / failure status 返回。
- offline terminal read after terminal happened while client detached。
- outbox item 与 `watch_session_events` terminal event dedupe identity 一致。
- drain-first 两次 read 覆盖 first drain 与 live attach 之间 terminal window。
- anti-leak lag case：第一次 drain/read 返回 `projection_status=LAGGED` 且无 terminal item；随后 OutboxSink catch-up 和 second read 返回该 terminal item，Service 以 `dedupe_key=terminal_event_id` upsert 后不重复展示。

Stop condition：

- 实现需要改变 `watch_session_events` signature 或把 Outbox 合并进 live watch 时停止。

## Tests / Validation Commands

每个 implementation slice 后必须运行对应测试与 pyright。最终 aggregate 验证：

```bash
source .venv/bin/activate
pytest \
  tests/host/test_audit_sink.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py \
  tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py \
  tests/host/test_projection_runner.py \
  tests/host/test_projection_checkpoint.py \
  tests/host/test_public_event_stream.py \
  tests/host/test_watch_session_events.py \
  tests/host/test_open_host_runtime.py \
  tests/host/test_package_exports.py \
  tests/host/test_durable_schema.py -q

python -m pyright dayu/host tests/host
git diff --check
```

README 触发判断：

- 修改 `dayu/host/**` 且新增 public Outbox read/drain API，implementation 必须更新 `dayu/host/README.md`。
- 新增 `tests/host/test_*outbox*` / audit / trace 测试，若测试分层或运行方式发生变化，更新 `tests/README.md`；若只是新增同类测试且 README 已覆盖，可在最终说明中明确“检查后无需更新”。
- 本 Phase 不修改根 README，除非 implementation 实际改变 CLI / render / 项目级使用入口；按当前计划不应触发。

## Review Gates / Residual Risk Classification

Plan review gate 必须检查：

- Outbox read / drain 是唯一 additive public extension；没有新增 `OpenHostOptions` 字段或其它 public shortcut。
- 所有新增 public dataclass / Protocol signature 均严格类型化，无 `object` / `Any` / 无类型参数。
- Sinks 只消费 `ProjectionEventView` / committed EventLog，不读取 command path transient state。
- Outbox 防漏协议有测试，且未改变 `watch_session_events` live-only。
- Tool trace 查询没有升格为 Service-facing public API。
- JSONL failure 只造成 projection-local failure / lag。

Implementation review gate 必须检查：

- Schema fresh bump 与 DDL / constants / bootstrap tests 一致。
- Projection checkpoint 在 projection write 成功后推进；failure 不推进。
- Normal replay idempotency 覆盖 audit / trace / outbox。
- Outbox read/drain 对 projection lag 有可见状态，不让 Service 把 stale empty 当完整结果。
- README 同步符合职责边界。

Residual risks：

- P0 blocking：无。
- P1 material but accepted：JSONL 与 SQLite checkpoint 无跨介质 exactly-once；物理 JSONL 在 crash window 可能出现重复 `event_id` 行，analyze/query 必须按 `event_id` 去重。这不影响 Host truth。
- P1 material but accepted：Outbox drain 不是 channel delivery success；Service/UI 必须保存 seen terminal watermark / ids。Phase 13 不实现 channel exactly-once。
- P2 deferred：purge tombstone audit record、outbox cleanup、tool trace cleanup、projection cleanup 与 retention matrix 归 Phase 15；Phase 13 不实现 purge 行为。
- P2 deferred：外部 audit 系统、长期归档策略、heavy sink runner / batch transaction hardening 归后续 production hardening。

## Blocking Open Questions

None。

若 implementation 发现以下任一情况，必须停止并交 controller，不得自行设计：

- 必须修改 Engine 才能提供 tool trace refs。
- 必须新增 `OpenHostOptions` public 字段才能满足 sink path injection。
- 必须改变 EventLog terminal transaction 才能保证 Outbox item 不漏。
- 必须给 `watch_session_events` 增加 cursor / replay 参数才能证明 attach 防漏。
- 必须把 Outbox item state 解释为 Service / UI channel delivery success。
