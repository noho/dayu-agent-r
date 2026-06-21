# Host Phase 15 Retention / Purge / Production Hardening Handoff Plan

## Gate

当前 gate：Phase 15 handoff implementation-ready plan。

本文档只供 implementation agent 使用：本 planning work unit 不修改 `dayu/` 源码、不修改 tests、不修改 runtime 代码、不提交、不 push、不创建 PR、不进入 implementation gate。

## Goal / Motivation / Direct Evidence

目标是在已冻结的 Host public API envelope 内落地 Phase 15 的 release-blocking 范围：

- `purge_session(...)` destructive cleanup。
- purge tombstone durable record。
- append-only audit JSONL retention 与 purge tombstone audit/query 识别。
- projection cleanup / rebuild confidence。
- local multiprocess / recovery 相关的 purge safety hardening。

动机成立，但严重性不得扩大。P15 不是泛化 production scale work，也不是 RemoteProxy / RemoteStub work。它的 root cause 是：Host 已冻结 `PurgeSessionRequest` / `PurgeSessionResult` public envelope，但 destructive cleanup 仍被 deferred；同时 Phase 13 已落地 audit / tool trace / outbox projections，purge 必须补齐这些派生数据与 append-only audit retention 的边界。

直接证据：

- `docs/host/design.md` 明确 `purge_session` 是第一版 destructive purge API，用于清理已结束且不再需要恢复的 Session 的 Host 本地数据；它不是 close、cancel、archive、memory forget 或 UI hide。
- `docs/host/design.md` 明确 purge 前置条件：Session 已关闭，且不存在 active / queued / waiting / recovering / cancelling Run，所有 Run 已 terminal。
- `docs/host/design.md` 明确 purge 删除范围包括 Session / slot binding、Run、Attempt、EventLog rows、payload descriptors / local payloads、memory snapshot、projection rows、outbox items、tool trace hot data；共享 cold artifact 只有在没有其它 durable ref 引用时才可清理。
- `docs/host/design.md` 明确 purge 必须保留 tombstone / audit record，且 tombstone 不得位于被 purge 的 Session EventLog 中。
- `docs/host/design.md` 明确 `purge_session` 不删除已经写入的 append-only audit JSONL，既有 audit 行可以保留对已删除 EventLog rows 的 refs。
- `docs/host/implementation-control.md` 当前 work unit 是 Phase 15 Retention / Purge / Production Hardening，当前 gate 是 handoff implementation-ready plan；P15 plan 必须排除 remote-dependent smoke / hardening。
- `docs/reviews/phase15-design-discussion-controller-20260529.md` 裁决 P15 可进入 plan generation，release-blocking 只包括 purge/tombstone/audit/projection/local hardening，不包括 broad production scale tuning。
- 当前代码中 `dayu.host.api.PurgeSessionRequest` 与 `PurgeSessionResult` 已存在；`dayu.host.command.purge_session(...)` 仍稳定抛 `UNSUPPORTED_OPERATION`，尚未执行 transaction、写幂等记录或删除 durable facts。
- 当前 `dayu/host/durable/schema.py` 的 `HOST_SCHEMA_VERSION` 为 `13`，且已包含 EventLog、idempotency、payload、Session / Run / Attempt / wait、projection、memory、audit marker、tool trace hot、outbox 表；尚无 purge tombstone table。

成功信号：

- `purge_session(session_id, request)` 在 Host handle 未关闭、请求合法、前置条件满足时返回 `PurgeSessionResult(purged=True, purge_tombstone_ref=..., deleted_counts_digest=...)`。
- 同一 `(session_id, client_request_id)` 与同一 semantic digest 在 Session facts 删除后仍可幂等重放并返回同一 tombstone result。
- 同一 `(session_id, client_request_id)` 但不同 semantic digest 返回 `IDEMPOTENCY_CONFLICT`。
- purge 后 `get_session`、`get_run`、`retry_run`、`replay_run` 与 internal EventLog 补读不能恢复该 Session 的可恢复事实。
- purge 不删除 append-only audit JSONL；必须写入 purge tombstone audit line 或等价 append-only purge audit record，使 audit/query/analyze 能识别源 EventLog facts 已 purge。
- projection/read model/memory/outbox/tool trace hot rows 不残留可被普通 read path 当作 active facts 的目标 Session 数据。
- shared cold artifacts 只有在 durable descriptor/ref 证明不再被其它 row 引用时才删除；不能用路径前缀或文件名猜测 ownership。
- `watch_session_events(session_id)` 仍 live-only，不新增 cursor、不补历史、不合并 outbox。

## Non-goals / Scope Boundary

不做：

- 不修改 Host public API shape：`PurgeSessionRequest`、`PurgeSessionResult`、`Host` handle methods、`OpenHostOptions`、`watch_session_events(...)` live-only 语义均不得重塑。
- 不实现 `archive_session`。
- 不实现长期 memory edit / reset / forget。
- 不实现 public payload reader。
- 不实现 `wait_final_answer(...)`、`get_run_result(...)` 或 Service-facing 捷径。
- 不做 RemoteProxy / RemoteStub smoke，不做 remote wire protocol work；remote-dependent items 继续归 issue 73。
- 不修改 Engine。若 implementation 发现必须改 Engine，立即停止并写入 Blocking Questions For Controller。
- 不让 projection、audit、outbox、memory、tool trace 或 minimal read model 成为 Host governance truth。
- 不删除 append-only audit JSONL。
- 不把 P15 扩成长期归档、外部 audit、channel delivery exactly-once、heavy sink runner、retention scheduler、GC daemon、remote production scale tuning 或 all-repository performance hardening。
- 不为旧 schema 做兼容读取、兼容迁移测试、compat re-export、compat wrapper 或旧接口保留逻辑；schema 变更按 fresh DB 起库处理。

必须保持：

- Host governance truth 仍是 Session / Run / Attempt / EventLog 与同事务状态索引。Purge tombstone 只证明已删除，不参与 resume、retry、replay、memory、RunInputBuilder 或 Run 状态迁移。
- Audit JSONL 是 projection / sink，不是 truth；purge audit line 只服务审计识别。
- Projection cleanup 只能删除或 reset 派生表，不得用 projection checkpoint 证明 purge 前置条件。
- Command path 内只做短 SQLite transaction、EventLog/状态事实删除、tombstone/idempotency 写入和必要本地 payload row 删除；文件系统删除必须基于 transaction 内收集的可删除 artifact refs，在 commit 后执行，失败只影响 cleanup report / diagnostic，不回滚 tombstone。

## Affected Files / Modules

### Release-blocking

允许修改：

- `dayu/host/api.py`：仅允许补充 existing dataclass/docstring 中 purge 已实现语义的说明；不得新增/删除/重命名 public 字段或方法。
- `dayu/host/command.py`：把 `purge_session(...)` 从 structured unsupported 接到 purge service；保持 closed-handle guard 与 durable error -> `HostApiError` 映射。
- `dayu/host/durable/schema.py`：fresh schema bump `13 -> 14`，新增 purge tombstone table / indexes / constants；更新 table set 与 schema tests。
- 新增 `dayu/host/durable/purge.py`：purge tombstone row codec、precondition read、delete matrix transaction helpers、idempotency replay helpers、deleted counts digest helper。
- `dayu/host/durable/payload.py`：仅新增 transaction-scoped read/delete/ref-count helpers，用于安全删除 payload descriptors 与 SQLite payload rows；不得解释业务 payload。
- `dayu/host/durable/read_model.py`：新增按 session 删除 minimal read model rows 或 consumer-scoped rebuild helper；不得让 read model 成为 truth。
- `dayu/host/durable/memory.py`：新增按 session 删除 memory snapshots/items/diagnostics helper。
- `dayu/host/durable/tool_trace.py`：新增按 session 删除 tool trace hot rows helper；cold JSONL 不在 release-blocking 删除范围。
- `dayu/host/durable/outbox.py`：新增按 session 删除 outbox terminal items / drain idempotency helper。
- `dayu/host/durable/audit.py`：新增 purge tombstone audit marker/query support 所需的 sink-local helper；不得把 marker 当 audit truth。
- `dayu/host/audit.py`：新增 append-only purge tombstone audit line builder / writer 或 query annotation helper；不得改 existing EventLog audit line schema 破坏旧行读取。
- `dayu/host/open_host.py`：只接入 public handle `purge_session` 调用路径与 closed-handle guard；不得新增 `OpenHostOptions` 字段。
- `dayu/host/read_api.py`：只允许在 read-after-purge 中优先识别 tombstone 并返回现有 `NOT_FOUND`/等价 typed error；不得新增 public reader。
- `dayu/host/recovery.py`、`dayu/host/dispatch.py`：仅允许补 closed/purged Session local hardening 所需的 narrow guard，防止 startup recovery / scheduler 对已 purge Session 重新派发；不得改变 recovery state machine。
- `tests/host/test_purge_session.py` 或等价新增 focused tests。
- `tests/host/test_durable_schema.py`、`tests/host/test_package_exports.py`、`tests/host/test_command_handle.py`、`tests/host/test_public_run_api.py`、`tests/host/test_public_session_api.py`、`tests/host/test_audit_sink.py`、`tests/host/test_projection_read_model.py`、`tests/host/test_memory_projection.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_outbox_durable.py`、`tests/host/test_open_host_runtime.py`：只按触发点更新 focused assertions。
- `dayu/host/README.md`、`tests/README.md`：实现和测试通过后按职责同步当前事实。

禁止修改：

- `dayu/engine/**`。
- `dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`。
- `dayu/runtime/**`，除非 filelock 等既有 runtime bug 被直接证明阻塞 audit JSONL append-only retention；若触及 runtime，停止交 Controller。
- RemoteProxy / RemoteStub / wire protocol 相关模块。
- `OpenHostOptions` 字段集合、`Host` public method shape、`watch_session_events` signature / semantics。

### Follow-up Only

- retention policy scheduler / periodic GC。
- cold artifact long-term archival、cross-workspace artifact GC、external blob storage cleanup。
- external audit system 投递与查询。
- audit JSONL compaction / rotation / archive。
- tool trace cold JSONL retention policy。
- outbox channel delivery success state、external channel exactly-once。
- heavy sink runner / batch transaction tuning。
- remote multiprocess / remote worker smoke 和 wire protocol hardening，继续归 issue 73。
- broad performance tuning、large DB vacuum strategy、operator dashboard。

## Contract / Schema / State-machine / Public-interface Decisions

Public interface:

- 不新增 public method，不改变 `purge_session(session_id, request) -> PurgeSessionResult`。
- 不改变 `PurgeSessionRequest(context, client_request_id, reason)`。
- 不改变 `PurgeSessionResult(session_id, purged, purge_tombstone_ref, deleted_counts_digest)`。
- read-after-purge 不新增 `GONE` public error code。当前 public error taxonomy 无 `GONE`，因此 release-blocking 行为使用现有 `HostApiErrorCode.NOT_FOUND` 表达不可恢复事实缺失；内部可通过 tombstone helper 区分 purged vs never existed 以写 audit/query diagnostic。
- `watch_session_events(session_id)` purge 后仍按现有 missing Session 行为返回 `NOT_FOUND` 或 closed-handle exception；不得补读 tombstone 或历史事件。

Schema:

- 需要 schema 变更：新增 purge tombstone durable table，fresh schema bump `HOST_SCHEMA_VERSION = 14`。
- 不写旧库兼容读取，不写旧库迁移测试。所有 schema tests 按 fresh v14 起库断言。
- 新表建议：`host_purge_tombstones`。
- 建议字段：
  - `tombstone_id TEXT PRIMARY KEY`
  - `session_id TEXT NOT NULL UNIQUE`
  - `client_request_id TEXT NOT NULL`
  - `semantic_request_digest TEXT NOT NULL`
  - `actor TEXT NULL`
  - `source TEXT NULL`
  - `operation_context_digest TEXT NULL`
  - `operation_context_refs_json TEXT NOT NULL`
  - `reason TEXT NOT NULL`
  - `purged_at TEXT NOT NULL`
  - `precondition_digest TEXT NOT NULL`
  - `deleted_counts_json TEXT NOT NULL`
  - `deleted_counts_digest TEXT NOT NULL`
  - `deleted_refs_digest TEXT NOT NULL`
  - `audit_record_ref TEXT NULL`
  - `audit_record_digest TEXT NULL`
  - `request_context_json TEXT NOT NULL`
- `session_id` unique，保证一个 Session 最多一个 tombstone。重复 purge 只能通过 tombstone/idempotency replay，不创建第二个 tombstone。
- `host_purge_tombstones` 不得 FK 到 `host_sessions` 或 `event_log`，因为目标 rows 会被删除。
- `idempotency_records` 可复用：scope_kind 固定为 `purge_session`，scope_id 为 `session_id`，idempotency_key 为 request `client_request_id`，result_kind 为 `purge_tombstone`，result_ref 为 `tombstone_id`，`created_event_id/created_event_sequence` 为 `NULL`。这允许 Session facts 删除后仍 replay。

State machine:

- purge 不是 Session 状态。它是 destructive cleanup command，在前置条件满足时删除可恢复事实并写 tombstone。
- purge 前不写 EventLog canonical fact，因为目标 Session EventLog 将被删除，且 tombstone 不能位于被 purge 的 Session EventLog 中。
- purge 后该 Session 不再处于 `CLOSED`、`OPEN` 或任何可恢复 state；普通 read path 视为 missing/gone。
- startup recovery、scheduler、RunInputBuilder、memory repair、projection rebuild 不得从 tombstone 恢复 Session facts。

## Purge Delete Matrix

| Target | Release-blocking action | Owner / rule |
| --- | --- | --- |
| EventLog | 删除 `event_log.session_id = target` rows。删除前收集 event ids / sequences / payload refs / run ids / attempt ids，用于 deleted counts、digest、payload cleanup 与 tombstone。 | EventLog 是被 purge 的 recoverable facts；purge 是唯一 destructive exception。 |
| Idempotency records | 删除会阻塞目标 EventLog 删除的旧 command idempotency rows：`created_event_id` / `created_event_sequence` 指向 target Session EventLog rows 的记录，以及 `scope_id = session_id` 且 `scope_kind` 属于 Session / Run command 的记录。保留新 `purge_session` replay row，且该 row 必须使用 `created_event_id = NULL`、`created_event_sequence = NULL`。 | 旧 command idempotency rows 是 target recoverable facts 的索引；purge 自身幂等性由 tombstone + NULL EventLog FK idempotency row 承担。 |
| Payload descriptors | 删除只被目标 Session rows 引用的 `payload_descriptors`。必须先计算 refs：EventLog payload_ref、minimal read model payload_ref、memory item payload_ref、tool trace hot payload_ref、outbox result/summary refs、compact/artifact descriptors 若有 durable row ref。 | 不得按字符串前缀删除；只删 durable ref count 为 0 的 descriptor。 |
| SQLite payloads | 删除被已删除 descriptor 唯一引用的 `host_sqlite_payloads` rows。 | 仅限 `payload_kind='sqlite_payload'` 且 descriptor 不再存在引用。 |
| Session / slot | 删除 `host_session_slots` 中绑定 target session 的 rows；删除 `host_sessions.session_id = target`。 | Session / slot binding 是目标 Session-owned governance state。 |
| Run | 删除 `host_runs.session_id = target` rows；删除前确认全部 terminal，且无 accepted/queued/running/waiting/cancelling/recovering。删除时必须按 `source_run_id` 自引用依赖子先父后：先删引用其它 Run 的 retry/replay child runs，再删 source roots；可用递归 CTE 计算依赖深度并按 depth DESC 删除。 | 前置条件失败返回 `INVALID_STATE`，不写 tombstone；retry/replay 链必须可 purge。 |
| Attempt | 删除目标 Session run ids 对应的 `host_attempts`。 | 必须先删依赖 attempt 的 dispatch / wait rows。 |
| Attempt dispatch records | 删除目标 run ids 对应 `host_attempt_dispatch_records`。 | 只允许在全部 Run terminal 时删除；pending/dispatching 等非终态由前置条件拦截。 |
| Wait records | 删除 `host_wait_records.session_id = target`。 | 若存在 `status='waiting'`，前置条件失败；terminal wait records 可删除。 |
| Minimal read model | 删除 `host_run_results.session_id = target` 与 `host_session_timeline_items.session_id = target`。 | Read model 是 projection，不是 truth；不得用其决定前置条件。 |
| Memory snapshot/items/diagnostics | 删除 `host_memory_snapshots/items/diagnostics.session_id = target`；items 也会因 snapshot cascade 删除，但 helper 应显式统计。 | Memory 是可重建 projection；purge 后不得保留目标 Session memory。 |
| Audit markers | 不删除 append-only audit JSONL。`host_audit_sink_markers` 中指向被删除 EventLog 的 marker 若有 FK，会阻塞 EventLog 删除；release-blocking 方案应删除这些 marker rows，并另写 purge tombstone audit marker/record 不 FK 到 deleted EventLog。 | Marker 是 sink-local idempotency，不是 audit truth；JSONL 行保留。 |
| Tool trace hot | 删除 `host_tool_trace_hot.session_id = target`。 | Hot projection 可删除；cold JSONL follow-up retention，不作为 release-blocking 删除。 |
| Outbox terminal items | 删除 `host_outbox_terminal_items.session_id = target`；删除 `host_outbox_drain_idempotency.session_id = target`。 | Outbox 是 projection/work queue；purge 后不得再补投 terminal item。 |
| Projection checkpoint/failure | 不按 session 盲删 global consumer checkpoints。若 checkpoint/failure FK 指向 target EventLog，必须执行精确 reset：`DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN target_event_ids`；`DELETE FROM host_projection_failures WHERE failed_event_id IN target_event_ids`。允许 reset 的 consumer 必须满足 rebuildability criterion：consumer 只消费 committed EventLog、projection rows 可从 remaining EventLog 从 cursor 0 重建、不会写 Host governance state。当前 release-blocking allowed consumer set 为 minimal read model、memory projection、audit JSONL marker/checkpoint、tool trace hot projection、outbox terminal projection；不得 reset recovery/admission/state owner。 | Checkpoint/failure 是 consumer-owned global projection state，不是 Session truth；reset 只能用于可由 remaining EventLog rebuild 的 projection/sink consumers。 |
| Cold artifacts | 只删除有 durable descriptor 且 ref count 为 0 的 local artifact；跨 Session/shared artifact 保留。 | 文件删除 commit 后执行；失败记录 residual cleanup risk，不回滚 tombstone。 |
| Audit JSONL | 绝不删除、截断、重写既有 JSONL。追加 purge tombstone audit record，包含 tombstone ref/digest、session id、reason、actor/source/operation refs、deleted counts digest 与 `source_eventlog_facts_purged=true`。 | Append-only audit retention 是 release-blocking invariant。 |

## Idempotency Design

Semantic digest:

- `sha256_digest_json` 输入必须包括 operation `"purge_session"`、`session_id`、`request.reason`、`request.context` 的 stable audit/context refs digest。
- 不包括当前 deleted counts、timestamp 或 mutable DB state；否则同一请求 replay 无法匹配。
- 显式参数不得塞入 metadata / extra payload。

Replay after Session facts deleted:

1. `purge_session` 先在 write transaction 中读取 `host_purge_tombstones` by `session_id`。
2. 若 tombstone 存在：
   - 若 `client_request_id` 与 `semantic_request_digest` 均匹配，返回 `PurgeSessionResult`，不尝试读取已删除 Session facts。
   - 若 `client_request_id` 相同但 digest 不同，返回 `IDEMPOTENCY_CONFLICT`。
   - 若 `client_request_id` 不同，返回 `CONFLICT` 或 `INVALID_STATE`，message 明确 Session has already been purged；不得创建第二个 tombstone。
3. Tombstone 存在但 purge idempotency row 缺失时，tombstone 是更强 durable proof：
   - 若 request `client_request_id` 与 tombstone row 相同且 semantic digest 相同，返回 tombstone replay result；不得为了 replay 重建 Session facts。
   - 若 request `client_request_id` 与 tombstone row 相同但 semantic digest 不同，返回 `IDEMPOTENCY_CONFLICT`。
   - 若 request `client_request_id` 与 tombstone row 不同，返回 `CONFLICT`，不得创建第二条 purge idempotency row 或第二个 tombstone。
4. 若 tombstone 不存在，再读取 idempotency record by `(scope_kind='purge_session', scope_id=session_id, idempotency_key=client_request_id)`：
   - 同 digest 且 result_ref tombstone 存在，返回 replay result。
   - 同 digest 但 tombstone 缺失是 durable inconsistency，返回 `INTERNAL_ERROR`。
   - 不同 digest 返回 `IDEMPOTENCY_CONFLICT`。
5. 若 tombstone/idempotency 均不存在，执行 normal precondition/read/delete path。

Conflict classification:

- Same key + different semantic digest：`HostApiErrorCode.IDEMPOTENCY_CONFLICT`。
- Different key for already purged Session：`HostApiErrorCode.CONFLICT`，不写新 tombstone。
- Tombstone-present / idempotency-missing / same key and same digest：return replay result from tombstone。
- Tombstone-present / idempotency-missing / same key and different digest：`HostApiErrorCode.IDEMPOTENCY_CONFLICT`。
- Session missing and no tombstone：`HostApiErrorCode.NOT_FOUND`。
- Session open or any non-terminal/start-blocking Run exists：`HostApiErrorCode.INVALID_STATE`。
- Durable FK/ref inconsistency during purge transaction：`HostApiErrorCode.INTERNAL_ERROR`，transaction rollback，不写 tombstone。

## Tombstone Design

Storage owner:

- Durable owner 是 new `dayu.host.durable.purge`，table owner 是 `host_purge_tombstones`。
- Tombstone 不属于 EventLog、projection、audit marker、memory、outbox 或 Service。

Minimum fields:

- `tombstone_id`：稳定 id，建议 `purge-tombstone-{sha256(session_id, client_request_id, semantic_request_digest)}`。
- `session_id`。
- `client_request_id`。
- `semantic_request_digest`。
- `actor` / `source` / `operation_context_refs_json` / `operation_context_digest`。
- `reason`。
- `purged_at`。
- `precondition_digest`：必须由 `build_purge_precondition_digest(...)` 对以下字段计算，禁止使用开放式 `extra` 字段：`session_id`、Session `status`、Session `created_event_id` / `created_event_sequence`、Session `closed_event_id` / `closed_event_sequence`、bound slot refs `(scope, slot_key)`、按 `run_id ASC` 排序的 Run entries、每个 Run 的 `run_id` / `status` / `accepted_event_id` / `accepted_event_sequence` / `queued_event_id` / `queued_event_sequence` / `started_event_id` / `started_event_sequence` / `terminal_event_id` / `terminal_event_sequence` / `current_attempt_id` / `source_run_id` / `source_run_relation`、按 `attempt_id ASC` 排序的 Attempt entries、每个 Attempt 的 `attempt_id` / `run_id` / `execution_id` / `status` / `started_event_id` / `started_event_sequence` / `terminal_event_id` / `terminal_event_sequence`、按 `wait_id ASC` 排序的 wait entries、每个 wait 的 `wait_id` / `run_id` / `attempt_id` / `execution_id` / `status` / `created_event_id` / `created_event_sequence` / `updated_event_id` / `updated_event_sequence`、target Session `event_log` 的 `MIN(event_sequence)` / `MAX(event_sequence)` / `COUNT(*)`、target EventLog payload ref count、target command idempotency row count、pre-purge projection row counts by table、pre-purge memory row counts by table、pre-purge outbox/tool trace hot row counts by table。
- `deleted_counts_json`：按 delete matrix 分项计数。
- `deleted_counts_digest`。
- `deleted_refs_digest`：对 event ids、run ids、attempt ids、payload refs、projection row ids 等删除对象 refs 的 canonical digest；不存大列表。
- `audit_record_ref` / `audit_record_digest`：append-only purge audit line 的 ref/digest。Release-blocking 策略固定为 fail-before-success：如果 purge audit line 不能写入并取得 digest，public `purge_session` 不得返回 successful `PurgeSessionResult`。实现可以在 DB transaction 前后组织短 I/O，但对调用方的成功返回必须以 tombstone row 和 purge audit line 都成功为前提；不允许 audit-pending 成功路径。
- `request_context_json`：只存 typed context refs，不复制 prompt / raw payload。

Digest:

- `deleted_counts_digest = sha256_digest_json(deleted_counts_json)`。
- `tombstone_digest = sha256_digest_json` over stable tombstone fields including `audit_record_ref` / `audit_record_digest` once the required purge audit line has been appended；public success 前这些 audit fields 必须已知且 replay deterministic。
- Public result 的 `deleted_counts_digest` 直接来自 tombstone row。

Query path:

- Internal helper `read_purge_tombstone_by_session_id(transaction, session_id)`。
- Internal helper `read_purge_tombstone_by_id(transaction, tombstone_id)`。
- No public payload/tombstone reader in P15。
- `read_api` 可用 tombstone lookup only to choose existing `NOT_FOUND` message/detail-safe diagnostic，不改变 public shape。

Audit JSONL behavior:

- 既有 EventLog-derived audit JSONL lines 保留。
- P15 必须新增 purge tombstone audit line，line source 是 tombstone row 而不是 deleted EventLog row。
- Audit query/analyze helper 如读取到 tombstone，必须能标注 `source_eventlog_facts_purged=true` 或等价字段。
- `host_audit_sink_markers` 中 FK 到 deleted EventLog 的 markers 可删除；这不删除 audit JSONL，只删除 sink-local duplicate marker。

## Read-after-purge Behavior

- `get_session(session_id)`：若 tombstone 存在或 Session row 不存在，返回现有 `HostApiErrorCode.NOT_FOUND`；message 可说明 Session not found or purged，不新增 public code。
- `get_run(run_id)`：Run row 已删除，返回 `NOT_FOUND`。不得通过 tombstone、outbox、timeline 或 audit JSONL 重建 RunSnapshot。
- `retry_run(run_id, request)` / `replay_run(run_id, request)`：源 Run row 缺失，返回 `NOT_FOUND`；不得从 audit/outbox/memory 恢复 source Run。
- `submit_followup(session_id, request)`：目标 Session row 缺失，返回 `NOT_FOUND`；不得根据 tombstone 创建同 id Session。
- `watch_session_events(session_id)`：Host handle closed 时仍抛 `HostClosedError`；未关闭但 Session purged 时按 missing Session 返回 `NOT_FOUND` 或 iterator creation error 的既有 typed behavior。不得补发 tombstone event。
- Internal EventLog补读 / projection rebuild：扫描 remaining EventLog；deleted Session rows 不再出现。若 projection checkpoint reset 后 replay，不得因 tombstone 生成 Session timeline、RunResult、memory item 或 outbox item。
- Audit query/analyze：可以显示 tombstone/audit line，并提示源 EventLog facts 已 purge；它不能作为 Host read path。

## Implementation Constraints

- 所有新增模块、类、函数必须提供中文 docstring，函数 docstring 至少包含参数、返回值、异常。
- 禁止 `object`、`Any`、无类型参数、无类型返回值、裸 `dict/list/set` 签名；JSON 使用项目既有 `JsonValue` / typed Mapping 边界。
- 禁止 `hasattr` / `getattr` 逃避类型边界。
- 禁止魔法数字、魔法字符串；新增 operation names、result kinds、table names、field names 使用模块级常量。
- 优先模块级私有 helper；禁止无必要嵌套函数/类。
- 不做 compatibility re-export / wrapper / facade。
- 不用 projection/audit/outbox/memory 证明 purge 前置条件。
- 不在 SQLite write transaction 内执行慢文件删除、JSONL 大扫描、projection catch-up 或 cold artifact IO。
- 文件删除必须 commit 后执行；DB tombstone 成功但文件删除失败时，implementation report 必须列 residual cleanup refs 与风险分类。
- 新增/修改代码必须通过 pyright，不能新增、扩散、掩盖类型错误。
- 修改后必须补测试；单文件测试覆盖率目标 >= 80%，`dayu/render/` 与 `utils/` 脚本例外。
- README 只在实现和测试通过后按触发规则更新，不写未来设计。

## Implementation Slices

### Slice P15-S1. Purge Tombstone Schema And Durable Primitives

Objective:

- 新增 purge tombstone durable schema、row codec、idempotency replay helper、deleted count digest helper，为后续 command path 提供唯一 owner。

Allowed files/modules:

- `dayu/host/durable/schema.py`
- new `dayu/host/durable/purge.py`
- `dayu/host/durable/__init__.py` only if existing package conventions require export
- `tests/host/test_durable_schema.py`
- new `tests/host/test_purge_session.py`
- `tests/host/test_weak_typing_guard.py` only if new module scan list must be updated

Exact allowed changes:

- Bump `HOST_SCHEMA_VERSION` from `13` to `14`.
- Add `TABLE_HOST_PURGE_TOMBSTONES`, index constants, DDL, table set membership, and schema test assertions.
- Implement typed dataclasses:
  - `PurgeTombstoneRow`
  - `PurgeDeleteCounts`
  - `PurgePreconditionSnapshot`
  - `PurgeReplayDecision` closed union or StrEnum + dataclass result
- Implement helpers:
  - `read_purge_tombstone_by_session_id(...)`
  - `read_purge_tombstone_by_id(...)`
  - `insert_purge_tombstone(...)`
  - `build_purge_semantic_digest(...)`
  - `build_deleted_counts_digest(...)`
  - `record_or_read_purge_idempotency(...)`
- Use existing `IdempotencyStore`; `created_event_id` fields stay `NULL`.

Data flow:

- Request/context -> semantic digest -> idempotency scope -> tombstone row/result.

State transitions:

- None. This slice must not delete Session facts and must not implement public command behavior.

Error handling:

- Duplicate session tombstone with same digest returns replay decision.
- Duplicate same key different digest raises/returns idempotency conflict path.
- Invalid durable row JSON/digest raises `HostDurableError`.

Tests/validation:

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py
```

Expected assertions:

- Fresh DB schema version is 14.
- `host_purge_tombstones` exists and has no FK to `event_log` / `host_sessions`.
- Insert/read tombstone round trip.
- Same `(session_id, client_request_id, digest)` replays after no Session row exists.
- Tombstone-present but purge idempotency row missing still replays for same key/digest and conflicts for same key/different digest.
- Same key different digest conflicts.

Non-goals:

- No public `purge_session` implementation.
- No EventLog deletion.
- No audit JSONL writing.

Stop conditions:

- If `PurgeSessionResult` cannot carry tombstone ref and deleted counts digest without shape change, stop and report Blocking Questions For Controller.

### Slice P15-S2. Delete Matrix Transaction Helper

Objective:

- Implement the core transaction-scoped purge delete matrix using Session / Run / Attempt / EventLog truth, preserving tombstone/idempotency after target facts are deleted.

Allowed files/modules:

- `dayu/host/durable/purge.py`
- `dayu/host/durable/payload.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/durable/memory.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/durable/audit.py`
- `tests/host/test_purge_session.py`
- focused existing durable tests for touched helpers

FK dependency summary:

- `idempotency_records.created_event_id` / `created_event_sequence` -> `event_log` and must be deleted for target EventLog refs before EventLog rows.
- `host_session_slots.session_id` -> `host_sessions` and `bound_event_id` / `bound_event_sequence` -> `event_log`.
- `host_runs.session_id` -> `host_sessions`; `input_event_id`、`accepted_event_id`、`queued_event_id`、`started_event_id`、`terminal_event_id` / sequence -> `event_log`; `source_run_id` -> `host_runs(run_id)` self-FK.
- `host_attempts.run_id` -> `host_runs`; started/terminal event refs -> `event_log`.
- `host_attempt_dispatch_records.run_id` -> `host_runs`; `attempt_id` / `execution_id` -> `host_attempts`; created/worker/cancel event refs -> `event_log`.
- `host_wait_records.session_id` -> `host_sessions`; `run_id` -> `host_runs`; `attempt_id` / `execution_id` -> `host_attempts`; created/updated event refs -> `event_log`.
- `host_run_results.run_id` -> `host_runs`; `session_id` -> `host_sessions`; terminal event refs -> `event_log`.
- `host_session_timeline_items.session_id` -> `host_sessions`; `run_id` -> `host_runs`; event refs -> `event_log`.
- `host_memory_snapshots.checkpoint_event_id` -> `event_log`; `host_memory_items.snapshot_id` -> `host_memory_snapshots ON DELETE CASCADE` and event refs -> `event_log`; diagnostics snapshot FK cascades.
- `host_audit_sink_markers`、`host_tool_trace_hot`、`host_outbox_terminal_items` all FK to `event_log`.
- `event_log.payload_ref` -> `payload_descriptors`; `payload_descriptors.sqlite_payload_id` -> `host_sqlite_payloads`。因此 payload cleanup 必须在 EventLog/projection rows 删除后，先删 unreferenced descriptors，再删不再被 descriptor 引用的 SQLite payload rows。

Exact allowed changes:

- Add `purge_session_durable(transaction, session_id, request_context, semantic_digest, now)` or equivalent internal helper.
- Read Session and Runs from governance tables; enforce:
  - Session exists.
  - Session status is `closed`.
  - No Run in `accepted`, `queued`, `running`, `waiting`, `cancelling`, `recovering`.
  - All Runs are terminal.
  - No active wait record remains.
- Collect deletion refs/counts before delete.
- Delete in FK-safe order:
  1. audit sink markers for target EventLog ids
  2. outbox drain idempotency / terminal items
  3. tool trace hot rows
  4. memory diagnostics/items/snapshots
  5. minimal read model rows
  6. projection checkpoints/failures using exact reset SQL: `DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN target_event_ids` and `DELETE FROM host_projection_failures WHERE failed_event_id IN target_event_ids`
  7. old command idempotency records whose `created_event_id` / `created_event_sequence` points to target EventLog rows, plus target Session command idempotency rows scoped to deleted Session facts; do not delete the new `purge_session` idempotency row with NULL created EventLog refs
  8. wait records
  9. dispatch records
  10. attempts
  11. runs in source dependency order: compute retry/replay child depth from `source_run_id` and delete deepest children first, then roots; implementation may use a recursive CTE or repeated leaf deletion, but must prove child-before-parent under `PRAGMA foreign_keys=ON`
  12. session slots
  13. session row
  14. EventLog rows
  15. unreferenced payload descriptors, then unreferenced SQLite payload rows
- Insert tombstone and idempotency record in the same transaction before commit; ensure no FK from tombstone to deleted rows.
- Return `PurgeDeleteCounts`, `PurgeTombstoneRow`, and commit-after file cleanup refs.

Data flow:

- Public command/service later calls helper -> helper verifies truth -> builds precondition digest -> deletes rows -> writes tombstone -> returns deleted counts.

State transitions:

- Terminal Session facts are removed; no Run/Attempt state transition facts are appended.

Error handling:

- Open Session / non-terminal Run / active wait -> `INVALID_STATE`.
- Missing Session without tombstone -> `NOT_FOUND`.
- FK/row count mismatch -> `INTERNAL_ERROR` rollback.
- Projection checkpoint/failure reset is allowed only when the row references a target EventLog id and the consumer satisfies the rebuildability criterion: it is a projection/sink consumer whose rows are derived only from committed EventLog and can replay from cursor 0 over remaining EventLog. Current allowed consumers are minimal read model, memory projection, audit JSONL sink marker/checkpoint, tool trace hot projection, and outbox terminal projection.

Tests/validation:

```bash
source .venv/bin/activate
pytest tests/host/test_purge_session.py tests/host/test_payload_store.py tests/host/test_projection_read_model.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py -q
python -m pyright dayu/host/durable/purge.py dayu/host/durable/payload.py dayu/host/durable/read_model.py dayu/host/durable/memory.py dayu/host/durable/tool_trace.py dayu/host/durable/outbox.py dayu/host/durable/audit.py tests/host
```

Expected assertions:

- Purge rejects open Session.
- Purge rejects accepted/queued/running/waiting/cancelling/recovering Runs.
- Purge deletes target Session EventLog/state/projection/memory/outbox/tool trace hot rows.
- Purge preserves other Session rows and shared payload/artifact descriptors.
- Tombstone remains queryable after Session/EventLog rows are gone.
- Deleted counts digest is deterministic.
- Purge succeeds with `PRAGMA foreign_keys=ON`; tests must assert no FK violation when target Session has existing command idempotency rows.
- Purge preserves and replays through the new `purge_session` idempotency row with NULL `created_event_id` / `created_event_sequence`.
- Closed Session containing retry/replay-linked Runs purges successfully, proving child-before-parent `source_run_id` ordering.

Non-goals:

- No public command wiring.
- No audit JSONL append.
- No cold JSONL / external artifact broad GC.

Stop conditions:

- If existing FK graph makes EventLog deletion impossible without deleting append-only audit JSONL or changing public API, stop and report Blocking Questions For Controller.

### Slice P15-S3. Public Command Wiring And Read-after-purge Semantics

Objective:

- Replace `UNSUPPORTED_OPERATION` with frozen-envelope public purge behavior and ensure read paths fail closed after purge.

Allowed files/modules:

- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `dayu/host/read_api.py`
- `dayu/host/api.py` docstring-only semantic updates if needed
- `dayu/host/__init__.py` only if package export tests reveal no-op mismatch
- `tests/host/test_command_handle.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_lifecycle_smoke.py` only focused purge/closed-handle assertions

Exact allowed changes:

- `command.purge_session(...)`:
  - keep `host._raise_if_closed()` first.
  - validate request via dataclass only; no extra payload.
  - call durable purge service in write transaction.
  - map durable errors to existing `HostApiErrorCode`.
  - return `PurgeSessionResult`.
- `open_host.Host.purge_session(...)`:
  - keep closed-handle guard.
  - call command facade; no new options.
- `read_api.get_session/get_run`:
  - ensure target purged/missing returns existing `NOT_FOUND`; do not reconstruct from tombstone/projection/audit.
- Retry/replay source missing behavior remains `NOT_FOUND`; add tests after purge.

Data flow:

- Public request -> command semantic digest -> durable purge helper -> public result.

State transitions:

- No public state transition. Purge is destructive cleanup plus tombstone.

Error handling:

- Closed handle -> `HostClosedError`, no DB access.
- Precondition failure -> `HostApiError(INVALID_STATE)`.
- Idempotency conflict -> `HostApiError(IDEMPOTENCY_CONFLICT)`.
- Already purged with different request id -> `HostApiError(CONFLICT)`.
- Missing and no tombstone -> `HostApiError(NOT_FOUND)`.

Tests/validation:

```bash
source .venv/bin/activate
pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_open_host_runtime.py tests/host/test_purge_session.py -q
python -m pyright dayu/host/command.py dayu/host/open_host.py dayu/host/read_api.py tests/host
```

Expected assertions:

- `purge_session` no longer returns `UNSUPPORTED_OPERATION` for valid closed terminal Session.
- Closed handle raises `HostClosedError`.
- Replay after facts deleted returns same tombstone ref/digest.
- `get_session`, `get_run`, `retry_run`, `replay_run`, `submit_followup`, `watch_session_events` do not resurrect purged Session.
- Public API shape/export tests remain stable.

Non-goals:

- No new public reader.
- No `wait_final_answer` / `get_run_result`.
- No watch cursor.

Stop conditions:

- If read-after-purge requires new public error code to satisfy tests, stop and ask Controller; default is existing `NOT_FOUND`.

### Slice P15-S4. Audit JSONL Retention And Tombstone Audit Record

Objective:

- Preserve existing append-only audit JSONL while adding purge tombstone audit evidence and query/analyze recognition.

Allowed files/modules:

- `dayu/host/audit.py`
- `dayu/host/durable/audit.py`
- `dayu/host/durable/purge.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_purge_session.py`
- `utils/` only if an existing analyze helper must recognize tombstones; otherwise defer

Exact allowed changes:

- Add purge tombstone audit line builder with stable schema version or explicit line kind.
- Append purge audit line without reading deleted EventLog rows.
- Ensure existing JSONL file is opened append-only; never rewrite/truncate.
- Enforce fail-before-success audit strategy: public `purge_session` may return success only after the purge tombstone audit line has been appended and its digest/ref is known. If audit append fails, return a retryable `HostApiErrorCode.INTERNAL_ERROR` or equivalent existing durable-to-public error and do not return `PurgeSessionResult(purged=True, ...)`.
- If implementation writes DB tombstone before audit append, it must rollback or compensate inside the same command so the public failure path does not leave a successful tombstone without a purge audit line. No audit-pending successful state is allowed in release-blocking scope.
- Add audit query/analyze helper that can identify tombstone and annotate deleted source facts.

Data flow:

- Tombstone candidate -> purge audit line -> append JSONL -> tombstone row with audit ref/digest -> public success. Any audit append failure exits before public success.

State transitions:

- None. Audit remains projection/sink.

Error handling:

- Audit append failure must fail the public command before success. The plan explicitly rejects an audit-pending success path: no successful `PurgeSessionResult` may be returned unless the purge tombstone audit record has been written.
- Existing EventLog-derived audit lines remain valid even if their EventLog source rows are deleted.

Tests/validation:

```bash
source .venv/bin/activate
pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py -q
python -m pyright dayu/host/audit.py dayu/host/durable/audit.py dayu/host/durable/purge.py tests/host
```

Expected assertions:

- Audit JSONL existing lines remain after purge.
- Purge appends a tombstone audit line containing session id, tombstone ref/digest, deleted counts digest, reason, actor/source/context refs, and purged marker.
- Audit marker rows pointing to deleted EventLog do not block purge.
- Tombstone audit line can be recognized without EventLog source row.
- Injected audit append failure causes public `purge_session` to fail and not return a successful `PurgeSessionResult`; tests must assert no audit-pending successful tombstone path is observable.

Non-goals:

- No external audit system.
- No JSONL rotation/compaction.
- No deletion of audit JSONL.

Stop conditions:

- If append-only audit retention cannot be achieved without changing `OpenHostOptions`, stop and report Blocking Questions For Controller.

### Slice P15-S5. Projection Cleanup, Rebuild Confidence, And Local Hardening

Objective:

- Prove purge leaves projection state rebuildable and local multiprocess/recovery paths do not reanimate purged Session facts.

Allowed files/modules:

- `dayu/host/durable/projection.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/projection.py`
- `dayu/host/recovery.py`
- `dayu/host/dispatch.py`
- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_purge_session.py`

Exact allowed changes:

- Add projection reset helper for consumers whose checkpoint/failure references deleted EventLog rows.
- Add tests proving minimal read model rebuild from remaining EventLog excludes purged Session.
- Add guard in recovery scan / scheduler candidate reads: if Session row is missing due to purge, skip and do not attempt recovery/dispatch.
- Add actual local multiprocess smoke using `multiprocessing` with independent Python processes and separate SQLite connections, following existing `test_recovery_multiprocess.py` / `test_admission_multiprocess.py` style. Process A opens Host and purges a closed terminal Session; Process B opens a separate Host handle against the same DB after purge commit and asserts `get_session` / `get_run` / `retry_run` or `replay_run` / `watch_session_events` fail closed with existing typed behavior. This is not same-process multi-handle and does not involve remote worker or wire protocol.
- Keep remote worker paths untouched.

Data flow:

- Purge deletes target facts -> projection checkpoints reset as needed -> subsequent projection catch-up scans remaining EventLog -> no target Session derived rows.

State transitions:

- None beyond purge deletion. Recovery/scheduler must skip missing/purged facts, not create new states.

Error handling:

- Projection rebuild failure records projection-local failure only; it must not recreate deleted facts or block tombstone read.
- Actual local multiprocess race: if another process command starts before purge transaction commits, SQLite serialization/CAS decides. If purge commits first, later process sees `NOT_FOUND`; if the other process commits first and creates a non-terminal Run, purge precondition fails. Tests must use independent processes, not only two handles in one process.

Tests/validation:

```bash
source .venv/bin/activate
pytest tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_recovery_scan.py tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_purge_session.py -q
python -m pyright dayu/host tests/host
```

Expected assertions:

- Projection checkpoint/failure reset does not use projection as truth.
- Rebuild from remaining EventLog excludes purged Session and preserves other Sessions.
- Recovery does not recover purged Session.
- Actual local multiprocess read/replay/watch after purge returns not_found/conflict as designed, using independent processes and no remote path.

Non-goals:

- No RemoteProxy / RemoteStub smoke.
- No heavy sink/batch runner.
- No production GC scheduler.

Stop conditions:

- If local hardening requires changing Engine or remote wire protocol, stop and report Blocking Questions For Controller.

### Slice P15-S6. Docs, Import Boundaries, Full Validation

Objective:

- Finalize docs and whole-scope validation after implementation slices pass.

Allowed files/modules:

- `dayu/host/README.md`
- `tests/README.md`
- `tests/host/test_import_boundary.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_weak_typing_guard.py`
- Review/implementation artifacts under `docs/reviews/`

Exact allowed changes:

- Update Host README only after purge is implemented:
  - remove statement that `purge_session` is structured unsupported.
  - document purge preconditions, tombstone, audit JSONL retention, read-after-purge behavior, and non-goals.
  - keep Service-facing vs diagnostic paths separate.
- Update tests README only if new purge tests or validation commands change current testing facts.
- Add import-boundary / weak-typing guard coverage for new `dayu.host.durable.purge` module.

Validation:

```bash
source .venv/bin/activate
pytest tests/host/test_purge_session.py tests/host/test_durable_schema.py tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_audit_sink.py tests/host/test_projection_read_model.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py tests/host/test_open_host_runtime.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- Focused P15 suite passes.
- Import boundary remains Host-only and no Engine/Service/UI/Fins reverse dependency appears.
- Pyright returns 0 errors.
- README reflects current implemented behavior only.

Non-goals:

- No implementation beyond docs/test guard cleanup.
- No commit/push/PR by implementation agent unless controller assigns that gate.

Stop conditions:

- If validation exposes unrelated dirty changes or unrelated failing tests, report exact commands and failure scope to Controller; do not broaden P15 scope.

## Tests / Validation Matrix

Required focused tests:

- Purge preconditions:
  - open Session rejected.
  - accepted / queued / running / waiting / cancelling / recovering Run rejected.
  - terminal-only closed Session accepted.
- Idempotent replay:
  - same `session_id + client_request_id + semantic digest` replays after Session facts deleted.
  - same id different digest -> `IDEMPOTENCY_CONFLICT`.
  - different id after purge -> `CONFLICT`.
  - tombstone exists but purge idempotency row is missing: same key/digest replays from tombstone, same key/different digest conflicts, different key returns already-purged conflict.
  - existing non-purge command idempotency rows with EventLog FK refs do not block purge; purge's own replay row keeps NULL `created_event_id` / `created_event_sequence`.
- Tombstone persistence:
  - tombstone survives EventLog/Session deletion.
  - tombstone contains required fields and stable digests.
  - public result uses tombstone ref and deleted counts digest.
  - `precondition_digest` is deterministic from the explicit field list in Tombstone Design.
- Audit JSONL retention:
  - existing JSONL lines remain unchanged.
  - purge tombstone audit line appended.
  - audit marker FK rows do not block EventLog deletion.
  - audit append failure does not return successful `PurgeSessionResult` and no audit-pending success path is observable.
- Projection cleanup/rebuild:
  - minimal read model, memory, outbox, tool trace hot rows deleted for target Session.
  - checkpoint/failure reset uses exact DELETE of rows whose checkpoint/failure event id is in target EventLog ids, and only for rebuildable projection/sink consumers.
  - other Session projections remain.
- FK/delete ordering:
  - full purge completes with `PRAGMA foreign_keys=ON`.
  - retry/replay-linked Run chains delete child-before-parent and purge successfully.
  - payload cleanup deletes descriptors before now-unreferenced SQLite payload rows.
- Read-after-purge:
  - `get_session`, `get_run`, `retry_run`, `replay_run`, `submit_followup`, `watch_session_events` fail closed with existing typed behavior.
- Closed-handle guard:
  - closed Host handle raises `HostClosedError` and does not write tombstone or delete facts.
- Local multiprocess/recovery:
  - actual independent-process local multiprocess command vs purge resolves by SQLite transaction ordering.
  - startup recovery does not reanimate purged facts.
- Pyright:
  - no new or expanded type errors.

Required commands:

```bash
source .venv/bin/activate
pytest tests/host/test_purge_session.py -q
pytest tests/host/test_durable_schema.py tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py -q
pytest tests/host/test_audit_sink.py tests/host/test_projection_read_model.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py -q
pytest tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q
pytest tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/ tests/ utils/
```

Optional smoke if time allows and focused tests are green:

```bash
source .venv/bin/activate
pytest tests/host -q
```

## Docs Decision

- `dayu/host/README.md` must be updated after S3/S4 complete and tests pass, because current README says `purge_session` is structured unsupported. Replace that with implemented purge semantics, preconditions, tombstone/audit retention, and read-after-purge behavior.
- `tests/README.md` must be updated after P15 tests are added if the Host testing facts or common command list change. Add purge tests to the Host durable/public API testing description; do not write process history or future plans.
- Root `README.md` is not triggered unless implementation changes CLI/user workflow, trace/render entry, configuration, or project-level usage. P15 as planned should not trigger root README.
- `dayu/README.md` is not triggered unless implementation changes layering or assembly boundaries. P15 as planned should not change layering.

## Review Gates

Plan review must reject:

- Any slice that requires public API shape changes.
- Any use of projection/audit/outbox/memory as purge precondition truth.
- Any audit JSONL deletion/rewrite.
- Any remote/wire protocol work.
- Any Engine change.
- Any schema compatibility/migration logic for old DBs.
- Any slice too broad to review independently.

Code review must check:

- FK-safe delete ordering and transaction atomicity.
- Tombstone/idempotency survives deleted Session facts.
- Precondition checks use Session/Run/Attempt/wait durable truth only.
- Read-after-purge cannot reconstruct from projection/audit/outbox/memory.
- Audit JSONL is append-only and purge audit record is emitted.
- Payload/artifact cleanup is ref-counted, not path guessed.
- New signatures/docstrings obey Chinese docstring and strict typing rules.
- Tests cover failure paths and closed-handle behavior.

Aggregate deepreview must run after all accepted slices and before ready-to-open-draft-PR. Remote-dependent findings should be deferred to issue 73 unless they reveal local purge correctness risk.

## Residual Risk Classification

Release-blocking before closeout:

- Missing tombstone/idempotency replay after facts deletion.
- Audit JSONL deletion, rewrite, or missing purge audit record.
- Purge succeeds while non-terminal or recoverable Run exists.
- Purge leaves target Session rows readable through public API.
- Projection checkpoint/failure FK points to deleted EventLog and breaks rebuild/read paths.
- Pyright errors or weak typing violations.

Covered by later slice:

- Public command wiring before S3.
- Audit JSONL purge line before S4.
- Multiprocess/recovery confidence before S5.
- README updates before S6.

Follow-up owner:

- RemoteProxy / RemoteStub smoke and wire protocol: issue 73.
- Cold JSONL retention/rotation/archive: later retention work unit.
- Heavy sink runner / batch scale: later production hardening.
- External audit/channel delivery: Service/channel adapter or later audit work.
- Periodic purge/retention scheduler and DB vacuum: later production scale work.

## Completion Report Format

Each implementation/fix report must include:

- Gate and slice id.
- Approved plan path: `docs/host/phase15-retention-purge-production-hardening-plan.md`.
- Changed files.
- Implemented plan items.
- Tests run and exact results.
- Pyright command and result.
- Docs decision/update.
- Residual risks with classification: fixed in current slice / covered by later slice / deferred to later phase or issue / requiring Controller decision.
- Stop status: complete or blocked.

Final closeout must state:

- What changed.
- What was verified.
- README updates.
- Finding status.
- Remaining risks and owners.
- Next entry point.

## Blocking Questions For Controller

None.
