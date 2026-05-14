# Host Phase 2 Durable Store / EventLog / Payload Foundation Plan

## Plan Status

ready for plan re-review after Phase 2 plan fix

## Work Unit

Host Phase 2 Durable Store / EventLog / Payload Foundation。

当前 gate 是 Phase 2 handoff-ready plan。本计划只定义可交给 implementation agent 执行的 durable foundation 实施边界、schema / contract、切片、测试和文档同步要求；不修改生产代码、不进入 implementation、不做 review / fix / commit / push / PR。

## Source Of Truth

本计划以以下材料为真源：

- `docs/host/design.md` §10 Durable Store。
- `docs/host/design.md` §13 EventLog。
- `docs/host/design.md` §13.1 Payload 存储。
- `docs/host/design.md` §27 Host Lifecycle / Recovery 中 host instance liveness foundation。
- `docs/host/implementation-control.md` Phase 2 条目、已确认 durable foundation 决策、当前状态与追踪区。
- `docs/reviews/gateflow-phase-design-re-review-host-p2-controller-adjudication-20260514.md`。
- `dayu/README.md` 术语真源。
- 当前 Phase 1 代码边界：`dayu/host/api.py`、`dayu/host/tooling.py`、`dayu/runtime/lane.py`、`dayu/runtime/filelock.py`、`tests/host`、`tests/runtime`。

真源优先级：Host 架构语义以 `docs/host/design.md` 为准；Phase 边界和已确认决策以 `docs/host/implementation-control.md` 与 controller adjudication 为准；术语以 `dayu/README.md` 为准；当前代码只作为已落地边界与测试风格事实，不得反向改变架构语义。

## Goal, Motivation, Success Signal

### Goal

建立后续 Host phases 可依赖的本地 durable foundation：

- 单个 Host SQLite durable DB、fresh bootstrap、schema version 校验与事务 runner。
- append-only EventLog append / read primitive、全局 `event_sequence` cursor 与 ledger `event_id`。
- 通用 idempotency primitive。
- 最小 payload descriptor，支持 `sqlite_payload` 与本地 `artifact_ref`。
- host instance liveness primitive，支持当前 instance register / heartbeat / stopping / stopped / read。

### Motivation And Direct Evidence

问题真实存在，且不是文档表述问题：

- `docs/host/design.md` §10 明确 Host durable store 是单个 SQLite 本地治理真源，EventLog append、payload row、idempotency、host instance liveness 是 durable foundation；后续 Session / Run / Attempt、wait、projection、memory、audit、outbox 只能在该 foundation 上扩展。
- `docs/host/design.md` §13 明确 EventLog 是 append-only event ledger，`event_sequence` 是 Host event stream cursor、projection checkpoint、outbox dispatch、audit replay 与 recovery scan 的主 cursor；没有 EventLog primitive，后续 command path、projection、recovery 都缺少事实真源。
- `docs/host/design.md` §13.1 明确 EventLog row 不应内嵌大 payload，必须有可校验 descriptor / digest；大 payload 必须先 durable artifact 写入、digest verify、atomic rename，再写 SQLite descriptor 与 EventLog。
- `docs/host/design.md` §27 明确 recovery 的输入只能是 Host durable truth，其中包含 host instance liveness record；但 Phase 2 只实现 liveness primitive，不实现 positive orphan proof classifier。
- `docs/host/implementation-control.md` Phase 2 目标明确要求建立 SQLite durable truth、EventLog append primitive、payload descriptor、idempotency record、host instance liveness 与事务边界，并把 Session / Run / Attempt tables、wait record、projection / memory / audit / trace / outbox / purge tombstone tables分配给后续 phase。
- `docs/reviews/gateflow-phase-design-re-review-host-p2-controller-adjudication-20260514.md` 裁决 BQ1-BQ5 均已修复，并要求本 plan 把 timestamp format、busy timeout、retry policy、payload threshold、artifact write crash window、idempotency conflict 和 after-commit rollback behavior 转成 typed API、DDL、error types 和 tests。
- 当前 Phase 1 代码只提供 `dayu.host` 公共 request / snapshot / tooling 类型与 `dayu.runtime` lane / filelock。`dayu/README.md` 已明确 Host durable store、EventLog、dispatch、command path、ToolRuntime 与 policy provider 不属于 Phase 1 公共命名空间，因此 Phase 2 需要在 `dayu.host` 内部新增 durable foundation，而不是扩展 `dayu.runtime` 或包根公共 API。

### Success Signal

Phase 2 完成后：

- 新建 fresh Host SQLite DB 会创建 foundation tables，设置并校验 `PRAGMA user_version = 1`，启用 WAL、`foreign_keys=ON` 与明确 busy timeout；schema version mismatch 结构化失败。
- 后续 phase 可通过 transaction runner 在一个短 `BEGIN IMMEDIATE` write transaction 内 append canonical facts、写 foundation row，并只在 commit 成功后触发 after-commit callbacks。
- EventLog append 返回全局单调 `event_sequence`；duplicate `event_id` 不追加第二行；reader 可按全局 cursor 补读。
- idempotency primitive 对同一 `(scope_kind, scope_id, idempotency_key)` + 相同 `semantic_input_digest` 返回既有 result ref；同 key 不同 digest 返回 `idempotency_conflict`。
- 小 payload 可在 SQLite transaction 内写入 `sqlite_payload` descriptor；大 payload 可先写本地 artifact、digest verify、atomic rename，再在 SQLite 中写 descriptor 与 EventLog；SQLite transaction 失败时已发布 artifact 不成为 accepted fact。
- 当前 host instance 可 register / heartbeat / mark stopping / mark stopped / read；heartbeat 只能刷新当前 instance，不实现 lease、fencing、takeover 或 orphan classifier。
- 受影响单测、integration smoke、multi-process concurrent append smoke 和 pyright 通过；文档按触发规则检查并只在职责范围内更新。

## Non-Goals And Scope Boundary

本 phase 明确不做：

- Session / Run / Attempt 状态机、admission、queue promotion、CAS 状态迁移、active index、queue index。
- Host command path，例如 `start_run`、`submit_followup`、`cancel_run`、`resolve_wait`、`retry_run`、`replay_run`。
- Engine dispatch、WorkerProxy、RemoteProxy / RemoteStub、EngineEvent ingest、远端 transport。
- Projection、Observer / Sink、audit、tool trace、usage、stream fanout、outbox、memory、context governance。
- ToolRuntime、TruncationManager、`fetch_more`、工具执行、工具 policy resolution、工具事实 accept barrier。
- Recovery classifier、positive orphan proof、dispatch record join、Attempt `LOST` CAS、Run `RECOVERING`、新 Attempt 创建。
- lease / fencing / takeover / remote owner / Attempt owner 语义。
- 旧库兼容 migration、旧 schema fallback、兼容读取、兼容 wrapper / facade / re-export。
- 将 Host durable truth、EventLog ordering、idempotency、payload descriptor 或 host liveness 放入 `dayu.runtime`。
- 修改 `docs/host/design.md` 或 `docs/host/implementation-control.md`。

若 implementation agent 发现完成当前 slice 需要实现以上任一 non-goal，必须停止并交回 controller。

## Affected Files And Modules

### 允许新增或修改的生产模块

建议新增 `dayu/host/durable/` 内部子包。该子包属于 Host 层内部 durable foundation，不从 `dayu.host` 包根导出。

- 新建 `dayu/host/durable/__init__.py`
  - 只提供模块中文概览 docstring。
  - 不从此处做兼容 re-export；如需便捷导入，后续 implementation 必须先证明不会扩大公共命名空间。
- 新建 `dayu/host/durable/errors.py`
  - durable foundation 结构化错误类型。
- 新建 `dayu/host/durable/codec.py`
  - canonical JSON、UTC ISO timestamp、digest helpers。
- 新建 `dayu/host/durable/options.py`
  - `HostDurableStoreOptions`、`HostSQLiteStoragePolicy`、`PayloadStoragePolicy`。
- 新建 `dayu/host/durable/schema.py`
  - schema version、table names、DDL bootstrap 与 schema validation。
- 新建 `dayu/host/durable/connection.py`
  - SQLite connection factory、PRAGMA setup、fresh bootstrap orchestration。
- 新建 `dayu/host/durable/transaction.py`
  - typed transaction runner、after-commit callback handling、busy / locked retry。
- 新建 `dayu/host/durable/event_log.py`
  - EventLog row contract、append / read primitive、event duplicate handling。
- 新建 `dayu/host/durable/idempotency.py`
  - idempotency scope、record、result ref、claim / read primitive。
- 新建 `dayu/host/durable/payload.py`
  - payload descriptor、SQLite payload row、descriptor write / read helper。
- 新建 `dayu/host/durable/artifact.py`
  - local artifact write helper、relative path validation、digest verify。
- 新建 `dayu/host/durable/liveness.py`
  - host instance liveness row、register / heartbeat / mark / read primitive。

允许最小修改：

- `dayu/host/README.md`：只在 Phase 2 实现后、职责范围内同步当前 durable foundation 已实现边界。
- `tests/README.md`：只在 Phase 2 新增测试层级 / 命令 / 维护规则后同步。

### 允许新增或修改的测试

- 新建 `tests/host/test_durable_schema.py`
- 新建 `tests/host/test_durable_transaction.py`
- 新建 `tests/host/test_event_log_store.py`
- 新建 `tests/host/test_event_log_multiprocess.py`
- 新建 `tests/host/test_idempotency_store.py`
- 新建 `tests/host/test_payload_store.py`
- 新建 `tests/host/test_artifact_store.py`
- 新建 `tests/host/test_host_instance_liveness.py`
- 修改 `tests/host/test_package_exports.py`：确认 durable foundation 不进入 `dayu.host` 包根和 `dayu.host.api.__all__`。
- 现有 `tests/host/test_import_boundary.py` 与 `tests/host/test_weak_typing_guard.py` 会自动覆盖新增 Host 模块；若覆盖不足，允许在同文件中补充针对 `dayu.host.durable` 的断言。

### 明确禁止修改

- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `dayu/runtime/**`，除非 plan review 后 controller 另行确认；本 plan 默认禁止。
- `dayu/engine/**`
- `dayu/fins/**`
- `dayu/service/**`
- `dayu/ui/**`
- `tests/runtime/**`，除非现有 import boundary 测试需要证明 runtime 未被污染；默认不改。

## Contract / Schema / Public Interface Decisions

### Namespace And Public Boundary

- `dayu.host.durable` 是 Host 内部稳定 foundation，不是 `dayu.host` 包根公共 API。
- 不修改 `dayu.host.api` 的 Phase 1 request / snapshot / context 类型。
- 不把 durable row、transaction object、payload descriptor、idempotency record 或 host instance row 导出到 `dayu.host.__all__`。
- 后续 Host 内部 phase 可以直接 import `dayu.host.durable.*`；UI / Service 不应依赖这些内部模块。
- `dayu.runtime` 不承载 Host durable truth。`dayu.runtime.lane` 继续只表达 runtime capacity claim；`dayu.runtime.filelock` 继续只用于普通文件互斥，不用于 SQLite / EventLog truth。

### SQLite Schema Convention

固定决策：

- 单个 Host SQLite durable DB。
- fresh bootstrap；不做旧库兼容读取、兼容 migration 或旧 schema fallback。
- `PRAGMA user_version = 1`，不匹配时抛出 `HostSchemaMismatchError`。
- durable ids 一律 TEXT，例如 `event_id`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`host_instance_id`。
- durable timestamp 一律 UTC ISO-8601 TEXT，固定微秒精度和 `Z` 后缀，例如 `2026-05-14T01:02:03.123456Z`。
- structured JSON 一律 canonical JSON TEXT。
- `PRAGMA foreign_keys=ON`。
- 能由 schema 表达的唯一性必须用 explicit primary key 或 unique index。
- 每个 foundation table 必须有明确语义 owner；不得预创建 Session / Run / Attempt / wait / projection / outbox / memory / purge tables。

Foundation tables:

```text
event_log
  event_sequence INTEGER PRIMARY KEY AUTOINCREMENT
  event_id TEXT NOT NULL UNIQUE
  event_body_digest TEXT NOT NULL
  event_class TEXT NOT NULL CHECK event_class in (...)
  session_id TEXT NOT NULL
  run_id TEXT NULL
  attempt_id TEXT NULL
  execution_id TEXT NULL
  event_type TEXT NOT NULL
  occurred_at TEXT NOT NULL
  actor TEXT NULL
  source TEXT NULL
  client_request_id TEXT NULL
  idempotency_key TEXT NULL
  policy_decision_json TEXT NULL
  reason_json TEXT NULL
  payload_json TEXT NOT NULL
  payload_ref TEXT NULL
  payload_digest TEXT NULL
  appended_at TEXT NOT NULL
  FOREIGN KEY(payload_ref) REFERENCES payload_descriptors(payload_ref)
```

约束：

- `event_sequence` 使用 `AUTOINCREMENT`，避免未来 destructive purge 后 rowid 复用。
- `event_id` 全局唯一。
- `event_class` 只能是 `canonical_fact`、`preview`、`diagnostic`、`projection_signal`。
- `payload_json` 不允许 NULL；无 inline payload 时写 canonical JSON `null`。
- `payload_ref IS NOT NULL` 时 `payload_digest IS NOT NULL`。

```text
idempotency_records
  scope_kind TEXT NOT NULL
  scope_id TEXT NOT NULL
  idempotency_key TEXT NOT NULL
  semantic_input_digest TEXT NOT NULL
  result_kind TEXT NOT NULL
  result_ref TEXT NOT NULL
  created_event_id TEXT NULL
  created_event_sequence INTEGER NULL
  created_at TEXT NOT NULL
  PRIMARY KEY(scope_kind, scope_id, idempotency_key)
  FOREIGN KEY(created_event_id) REFERENCES event_log(event_id)
  FOREIGN KEY(created_event_sequence) REFERENCES event_log(event_sequence)
```

```text
host_sqlite_payloads
  payload_id TEXT PRIMARY KEY
  payload_format TEXT NOT NULL CHECK payload_format in ('canonical_json', 'bytes')
  payload_json TEXT NULL
  payload_bytes BLOB NULL
  payload_size_bytes INTEGER NOT NULL CHECK payload_size_bytes >= 0
  payload_digest TEXT NOT NULL
  created_at TEXT NOT NULL
```

约束：

- `payload_format='canonical_json'` 时 `payload_json IS NOT NULL AND payload_bytes IS NULL`。
- `payload_format='bytes'` 时 `payload_bytes IS NOT NULL AND payload_json IS NULL`。

```text
payload_descriptors
  payload_ref TEXT PRIMARY KEY
  payload_kind TEXT NOT NULL CHECK payload_kind in ('sqlite_payload', 'artifact_ref')
  payload_digest TEXT NOT NULL
  payload_size_bytes INTEGER NOT NULL CHECK payload_size_bytes >= 0
  media_type TEXT NULL
  sqlite_payload_id TEXT NULL
  artifact_relative_path TEXT NULL
  metadata_json TEXT NOT NULL
  created_at TEXT NOT NULL
  FOREIGN KEY(sqlite_payload_id) REFERENCES host_sqlite_payloads(payload_id)
```

约束：

- `payload_kind='sqlite_payload'` 时 `sqlite_payload_id IS NOT NULL AND artifact_relative_path IS NULL`。
- `payload_kind='artifact_ref'` 时 `artifact_relative_path IS NOT NULL AND sqlite_payload_id IS NULL`。
- `metadata_json` 无元数据时写 canonical JSON `{}`。

```text
host_instances
  host_instance_id TEXT PRIMARY KEY
  pid INTEGER NOT NULL CHECK pid > 0
  process_start_token TEXT NOT NULL
  boot_id TEXT NULL
  created_at TEXT NOT NULL
  heartbeat_at TEXT NOT NULL
  status TEXT NOT NULL CHECK status in ('running', 'stopping', 'stopped', 'crashed_suspected')
```

Phase 2 不创建 `dispatch_records`，也不读取或 join dispatch record。

### Transaction Runner Typed API

Target types:

- `HostSQLiteStoragePolicy`
  - `busy_timeout_seconds: float = 5.0`
  - `write_busy_retry_count: int = 3`
  - `write_retry_initial_delay_seconds: float = 0.01`
  - `write_retry_backoff_multiplier: float = 2.0`
  - `write_retry_max_delay_seconds: float = 0.1`
- `AfterCommitCallback(Protocol)`
  - `def __call__(self) -> None`
- `HostTransactionOperation[T](Protocol)`
  - `def __call__(self, transaction: HostTransaction) -> T`
- `HostTransaction`
  - internal transaction handle used only by `dayu.host.durable.*` modules.
  - does not expose raw `sqlite3.Connection` to `dayu.host` package root or to callers outside durable foundation.
  - minimal wrapper API:
    - `execute(sql: str, parameters: SQLParameters = ()) -> HostExecuteResult`
    - `fetchone(sql: str, parameters: SQLParameters = ()) -> HostRow | None`
    - `fetchall(sql: str, parameters: SQLParameters = ()) -> tuple[HostRow, ...]`
  - `SQLParameters` is a typed tuple / mapping of SQLite scalar values, and `HostRow` is a typed row view over SQLite scalar values; implementation must not use `Any`、`object` or untyped row payloads.
  - domain modules such as EventLog / Payload / Liveness build their table-specific operations on this wrapper; `HostTransaction` must not become a domain store or expose per-feature business methods.
- `HostTransactionRunner`
  - `run_write(operation: HostTransactionOperation[T], *, after_commit: tuple[AfterCommitCallback, ...] = ()) -> T`

Transaction semantics:

- write transaction uses `BEGIN IMMEDIATE`.
- transaction body must be short; no Engine dispatch, no projection, no audit, no memory, no network, no large artifact write inside transaction.
- retry only wraps SQLite busy / locked failures at whole transaction level.
- retry does not wrap unique constraint conflict、foreign key error、schema mismatch、digest mismatch、idempotency conflict、event identity conflict、host instance identity conflict、host instance missing registration、payload reference error、artifact write error。
- after-commit callbacks run only after SQLite commit succeeds.
- rollback、transaction body exception、commit failure、retry intermediate failure must not trigger after-commit callbacks。
- if an after-commit callback fails, transaction remains committed; runner raises or aggregates `HostAfterCommitError` only after durable commit is complete. Tests must assert committed row remains visible.

### Storage Policy Options

Target types:

- `HostDurableStoreOptions`
  - `db_path: Path`
  - `create_parent_dirs: bool = True`
  - `sqlite_policy: HostSQLiteStoragePolicy = default`
  - `payload_policy: PayloadStoragePolicy`
- `PayloadStoragePolicy`
  - `artifact_root: Path`
  - `payload_inline_threshold_bytes: int = 65536`
  - `create_artifact_root: bool = True`

Validation:

- `db_path` must include a filename.
- `busy_timeout_seconds`、retry delays、backoff、payload threshold must be positive except `write_busy_retry_count` can be zero.
- `artifact_root` must be an explicit directory path, not derived from cwd or environment.
- defaults are applied only by construction root / options, not module-level hidden singletons.

`HostDurableStore` minimum responsibility:

- It is an internal Host durable handle returned by `open_host_durable_store(options)` and used by later Host internals; it is not exported from `dayu.host` package root and is not a public API.
- It holds the validated `HostDurableStoreOptions`, the connection factory / ownership needed to open configured SQLite connections, and the `HostTransactionRunner`.
- It may provide explicit `close()` / context-manager lifecycle if the implementation owns long-lived resources.
- It must not become a God object: it must not implement EventLog, idempotency, payload, artifact, liveness, command path, projection, recovery or Engine dispatch behavior directly.

### Error Types

All errors live in `dayu.host.durable.errors` and derive from `HostDurableError`.

- `HostDurableConfigError`
- `HostSchemaMismatchError`
- `HostTransactionBusyError`
- `HostTransactionRetryExhaustedError`
- `HostUniqueConstraintError`
- `HostForeignKeyError`
- `HostDigestMismatchError`
- `HostIdempotencyConflictError`
- `HostEventIdentityConflictError`
- `HostInstanceIdentityConflictError`
- `HostInstanceNotRegisteredError`
- `HostPayloadReferenceError`
- `HostArtifactWriteError`
- `HostAfterCommitError`

Non-retryable errors: unique constraint conflict、foreign key error、schema mismatch、digest mismatch、idempotency conflict、event identity conflict、host instance identity conflict、host instance missing registration、payload reference error、artifact write error。

### EventLog Row Typed Contract

Target enums / dataclasses:

- `EventClass(StrEnum)`
  - `CANONICAL_FACT = "canonical_fact"`
  - `PREVIEW = "preview"`
  - `DIAGNOSTIC = "diagnostic"`
  - `PROJECTION_SIGNAL = "projection_signal"`
- `EventLogAppendRequest`
  - `event_id: str`
  - `event_class: EventClass`
  - `session_id: str`
  - `run_id: str | None`
  - `attempt_id: str | None`
  - `execution_id: str | None`
  - `event_type: str`
  - `occurred_at: datetime`
  - `actor: str | None`
  - `source: str | None`
  - `client_request_id: str | None`
  - `idempotency_key: str | None`
  - `policy_decision: JsonValue | None`
  - `reason: JsonValue | None`
  - `payload_json: JsonValue`
  - `payload_ref: str | None`
  - `payload_digest: str | None`
- `EventLogRow`
  - same identity fields plus:
  - `event_sequence: int`
  - `event_body_digest: str`
  - `occurred_at: str`
  - `policy_decision_json: str | None`
  - `reason_json: str | None`
  - `payload_json: str`
  - `appended_at: str`
- `EventLogAppendResult`
  - `row: EventLogRow`
  - `inserted: bool`

Behavior:

- Append computes canonical JSON for structured fields and `event_body_digest` before insert.
- `event_body_digest` input is the canonical JSON object containing exactly these request-assigned fields:
  - `event_class`
  - `session_id`
  - `run_id`
  - `attempt_id`
  - `execution_id`
  - `event_type`
  - `occurred_at`
  - `actor`
  - `source`
  - `client_request_id`
  - `idempotency_key`
  - `policy_decision_json`
  - `reason_json`
  - `payload_json`
  - `payload_ref`
  - `payload_digest`
- `event_body_digest` must exclude `event_id`, `event_sequence`, `appended_at` and every other DB-assigned or non-request field; duplicate identity detection compares the request body, not ledger placement metadata.
- Insert duplicate `event_id`:
  - if existing `event_body_digest` matches, return existing row with `inserted=False`;
  - if digest differs, raise `HostEventIdentityConflictError`;
  - never append a second row.
- Reader supports:
  - `read_event_by_id(event_id: str) -> EventLogRow | None`
  - `read_events_after(cursor: int, *, limit: int) -> tuple[EventLogRow, ...]`
  - optional filters by `session_id` / `run_id` may be included only if implemented without replacing global cursor semantics.
- `event_sequence` remains global; run / session filters never define separate cursor semantics.

### Idempotency Primitive

Target dataclasses:

- `IdempotencyScope`
  - `scope_kind: str`
  - `scope_id: str`
  - `idempotency_key: str`
- `IdempotencyResultRef`
  - `result_kind: str`
  - `result_ref: str`
  - `created_event_id: str | None`
  - `created_event_sequence: int | None`
- `IdempotencyRecord`
  - scope fields
  - `semantic_input_digest: str`
  - result ref fields
  - `created_at: str`

Target functions / methods:

- `record_idempotent_result(transaction: HostTransaction, scope: IdempotencyScope, semantic_input_digest: str, result: IdempotencyResultRef) -> IdempotencyRecord`
- `read_idempotency_record(transaction, scope) -> IdempotencyRecord | None`

Behavior:

- First insert stores digest and result ref.
- Repeated same scope + key + same digest returns existing record.
- Repeated same scope + key + different digest raises `HostIdempotencyConflictError`.
- Idempotency conflict is a business precondition failure, not SQLite busy / locked; transaction runner must not retry it.
- `result_kind` must come from explicit `IdempotencyResultRef.result_kind`; implementation must not infer it from `result_ref`, scope, event id or string prefix.

### Payload Descriptor And Artifact Ref

Target enums / dataclasses:

- `PayloadKind(StrEnum)`
  - `SQLITE_PAYLOAD = "sqlite_payload"`
  - `ARTIFACT_REF = "artifact_ref"`
- `SQLitePayloadFormat(StrEnum)`
  - `CANONICAL_JSON = "canonical_json"`
  - `BYTES = "bytes"`
- `SQLitePayloadWriteRequest`
  - `payload_id: str`
  - `payload_format: SQLitePayloadFormat`
  - `json_value: JsonValue | None`
  - `bytes_value: bytes | None`
  - `media_type: str | None`
  - `metadata: JsonValue`
- `PayloadDescriptor`
  - `payload_ref: str`
  - `payload_kind: PayloadKind`
  - `payload_digest: str`
  - `payload_size_bytes: int`
  - `media_type: str | None`
  - `sqlite_payload_id: str | None`
  - `artifact_relative_path: str | None`
  - `metadata_json: str`
  - `created_at: str`
- `LocalArtifactRef`
  - `artifact_relative_path: str`
  - `payload_digest: str`
  - `payload_size_bytes: int`

Digest semantics:

- digest string format is `sha256:<64 lowercase hex chars>`.
- JSON digest is computed from canonical JSON UTF-8 bytes.
- bytes digest is computed from raw bytes.
- `semantic_input_digest` and `event_body_digest` also use the same digest string format, but over their own canonical input structures.
- digest mismatch raises `HostDigestMismatchError` and is never retried as busy / locked.
- `payload_id` is provided by the caller and must follow the project TEXT durable id convention; payload store only validates, persists and links it through descriptor rows. It must not generate a hidden payload id or derive it from content digest.

Artifact write ordering:

1. Reject null bytes, absolute paths and `..` traversal before filesystem access.
2. Resolve symlinks for artifact root, candidate parent directories and final path, then perform a resolved-path containment check so symlink or traversal cannot escape artifact root.
3. Write temp file under `artifact_root/.tmp/`.
4. Temp filename must be unguessable and multi-process safe, using cryptographic random id or `tempfile` exclusive creation; never use timestamp / pid alone.
5. Flush and fsync temp file.
6. Compute and verify digest.
7. Atomic rename into final relative path.
8. Fsync containing directory where supported.
9. Only after steps 1-8 succeed, enter SQLite transaction to insert `payload_descriptors` and EventLog row.

If SQLite transaction fails after artifact publish, the artifact is an unreferenced local file for cleanup / diagnostics only. It is not an accepted fact because no descriptor row / EventLog row committed.

### Host Instance Liveness Primitive

Target enum / dataclasses:

- `HostInstanceStatus(StrEnum)`
  - `RUNNING = "running"`
  - `STOPPING = "stopping"`
  - `STOPPED = "stopped"`
  - `CRASHED_SUSPECTED = "crashed_suspected"`
- `HostInstanceIdentity`
  - `host_instance_id: str`
  - `pid: int`
  - `process_start_token: str`
  - `boot_id: str | None`
- `HostInstanceRow`
  - identity fields
  - `created_at: str`
  - `heartbeat_at: str`
  - `status: HostInstanceStatus`

Target functions / methods:

- `register_current_instance(transaction, identity, now) -> HostInstanceRow`
- `heartbeat_current_instance(transaction, identity, now) -> HostInstanceRow`
- `mark_current_instance_stopping(transaction, identity, now) -> HostInstanceRow | None`
- `mark_current_instance_stopped(transaction, identity, now) -> HostInstanceRow | None`
- `read_host_instance(transaction, host_instance_id) -> HostInstanceRow | None`

Behavior:

- Register inserts current instance as `running`; if the same `HostInstanceIdentity` already exists, it MUST idempotently refresh `heartbeat_at` and status `running`.
- If the same `host_instance_id` exists with a different `process_start_token`, register MUST raise `HostInstanceIdentityConflictError`, which is non-retryable by the transaction runner.
- Heartbeat updates only row matching current `host_instance_id` and `process_start_token`; it must never refresh another instance.
- Heartbeat missing the current row MUST raise `HostInstanceNotRegisteredError`; heartbeat with matching `host_instance_id` but mismatched `process_start_token` MUST raise `HostInstanceIdentityConflictError`. Both are dedicated non-retryable errors; heartbeat must not return `None` or silently skip.
- Mark stopping / stopped is best-effort for current instance only; if row is absent, return `None` rather than inventing a record.
- `crashed_suspected` is only a diagnostic row status value for future recovery code to write; Phase 2 does not classify or set other instances to `crashed_suspected`.
- No lease, no fencing, no Attempt owner, no takeover grant.

## Concrete Implementation Decisions

### Canonical JSON Helper

`canonical_json_dumps(value: JsonValue) -> str`:

- use deterministic key ordering and compact separators.
- reject NaN / Infinity by using JSON serialization settings that fail on non-finite floats.
- do not depend on Python dict insertion order.
- output is UTF-8 encodable and is the only source for JSON digest bytes.

`canonical_json_loads(text: str) -> JsonValue` may be implemented if reader needs parsed values, but EventLog row contract should keep canonical JSON TEXT fields to preserve storage facts.

### UTC Timestamp Helper

`format_utc_timestamp(value: datetime) -> str`:

- requires timezone-aware datetime.
- normalizes to UTC.
- emits fixed microsecond precision and `Z` suffix.

`parse_utc_timestamp(value: str) -> datetime`:

- accepts only the fixed Phase 2 format.
- rejects naive, local-time, missing microseconds, missing `Z`, Unix timestamp strings, or variant formats.

### Transaction Boundaries

- Schema bootstrap can run outside `HostTransactionRunner`, but must use explicit connection setup and validation.
- EventLog append + idempotency insert + SQLite payload descriptor insert happen inside one write transaction when used together.
- Local artifact file write happens before the SQLite transaction.
- after-commit callbacks are passed into `run_write`, not registered globally.
- after-commit callbacks are for wakeup only; they must not decide command success or mutate durable truth in Phase 2 tests.

### Diagnostics Foundation

Phase 2 diagnostics foundation is deliberately minimal:

- structured error types expose exact failure classes.
- artifact helper returns `LocalArtifactRef` only after durable publish and digest verification.
- tests cover the orphan window by forcing SQLite transaction failure after artifact publish and asserting no descriptor / EventLog row exists.
- no diagnostics table, cleanup scheduler, projection, audit sink, tool trace, memory or outbox table is created in Phase 2.

## Implementation Slices

### Slice 1: SQLite Schema Convention / Fresh DB Bootstrap / Transaction Runner

Objective:

- Establish Host durable DB options, schema bootstrap, schema validation, typed transaction runner and error taxonomy.

Allowed files / modules:

- `dayu/host/durable/__init__.py`
- `dayu/host/durable/errors.py`
- `dayu/host/durable/codec.py`
- `dayu/host/durable/options.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/transaction.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_durable_transaction.py`
- minimal updates to existing Host package export / import boundary tests only if needed to keep durable internals out of package root.

Dependencies:

- Phase 1 Host import boundary and weak typing guard.

Exact allowed changes:

- Add `HostSQLiteStoragePolicy` and `HostDurableStoreOptions` without payload descriptor behavior beyond carrying `PayloadStoragePolicy` placeholder if needed.
- Add schema constants and DDL for all Phase 2 foundation tables listed in this plan.
- Add bootstrap that creates parent directory when configured, opens SQLite connection, sets WAL / foreign keys / busy timeout, creates fresh schema, sets `PRAGMA user_version = 1`, and validates version on existing DB.
- Add transaction runner with `BEGIN IMMEDIATE`, retry on busy / locked only, rollback on failure, after-commit on successful commit only.
- Add codec helpers for canonical JSON, UTC timestamp and sha256 digest because schema and transaction tests need them.

Target functions / classes / types:

- `HostDurableError` family.
- `HostSQLiteStoragePolicy`
- `PayloadStoragePolicy`
- `HostDurableStoreOptions`
- `HostDurableStore`
- `open_host_durable_store(options: HostDurableStoreOptions) -> HostDurableStore`
- `bootstrap_host_durable_store(connection: sqlite3.Connection) -> None`
- `validate_host_schema_version(connection: sqlite3.Connection) -> None`
- `SQLiteScalar`
- `SQLParameters`
- `HostRow`
- `HostExecuteResult`
- `HostTransaction`
- `HostTransactionRunner`
- `HostTransactionOperation[T]`
- `AfterCommitCallback`
- `canonical_json_dumps`
- `format_utc_timestamp`
- `parse_utc_timestamp`
- `sha256_digest_bytes`
- `sha256_digest_json`

Tests:

- `tests/host/test_durable_schema.py`
  - fresh DB creates all foundation tables and sets `PRAGMA user_version = 1`.
  - existing matching DB bootstrap is idempotent.
  - mismatched `user_version` raises `HostSchemaMismatchError`.
  - connection has `foreign_keys=ON` and WAL enabled.
  - a second independent connection to the same DB returns `wal` from `PRAGMA journal_mode`, proving WAL mode is persisted rather than only assumed on the original connection.
  - schema contains explicit PK / unique constraints for `event_id`, idempotency scope key, payload refs, `host_sqlite_payloads.payload_id` and host instance id.
  - no Session / Run / Attempt / wait / projection / outbox / memory / purge tables are created.
- `tests/host/test_durable_transaction.py`
  - successful transaction commits rows and then runs after-commit callback.
  - transaction body exception rolls back and does not run after-commit.
  - after-commit callback failure does not roll back already committed row.
  - busy / locked failure uses finite retry and then raises structured retry exhausted error.
  - unique constraint / foreign key / schema mismatch style errors are not retried.
  - canonical JSON is stable across key order; timestamp formatting is fixed microsecond UTC `Z`; digest uses `sha256:<hex>`.

Expected assertions:

- `event_sequence` column is `INTEGER PRIMARY KEY AUTOINCREMENT`.
- `payload_ref` FK exists from `event_log` to `payload_descriptors`.
- `PRAGMA journal_mode` is `wal` on a reopened independent connection.
- retry counter is finite and observable in a test using a controlled busy / locked scenario.
- after-commit callback list remains uncalled on rollback.

Completion signal:

- Slice 1 tests pass.
- `python -m pyright dayu/host tests/host` passes or has no new / expanded errors relative to baseline.
- Host durable modules do not import `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`。

Stop condition:

- Stop if schema decisions require adding Session / Run / Attempt tables.
- Stop if transaction runner requires moving code to `dayu.runtime`.
- Stop if busy retry classification cannot be implemented without swallowing non-retryable integrity / schema / digest errors.

Explicit non-goals:

- No EventLog appender behavior beyond schema.
- No idempotency behavior beyond schema.
- No payload write helper.
- No host instance liveness operations.
- No command path or Engine dispatch.

### Slice 2: EventLog Append / Read / event_sequence / Idempotency Primitive

Objective:

- Implement EventLog append / read primitive and idempotency record primitive on top of Slice 1 transaction runner.

Allowed files / modules:

- `dayu/host/durable/event_log.py`
- `dayu/host/durable/idempotency.py`
- targeted updates to `dayu/host/durable/errors.py` and `dayu/host/durable/codec.py` only when required by this slice.
- `tests/host/test_event_log_store.py`
- `tests/host/test_event_log_multiprocess.py`
- `tests/host/test_idempotency_store.py`

Dependencies:

- Slice 1 accepted and committed by controller.

Exact allowed changes:

- Add `EventClass`, `EventLogAppendRequest`, `EventLogRow`, `EventLogAppendResult`.
- Implement append that inserts into `event_log`, assigns global SQLite `event_sequence`, computes `event_body_digest`, and returns typed row.
- Implement duplicate `event_id` behavior: same body digest returns existing row, different body digest raises `HostEventIdentityConflictError`.
- Implement reader by `event_id` and global `event_sequence` cursor.
- Add `IdempotencyScope`, `IdempotencyResultRef`, `IdempotencyRecord`.
- Implement idempotency insert / read behavior with conflict detection.
- Keep all mutations inside caller-provided `HostTransaction`; do not create a separate command path.

Target functions / classes / types:

- `EventClass`
- `EventLogAppendRequest`
- `EventLogRow`
- `EventLogAppendResult`
- `EventLogStore`
- `append_event(transaction: HostTransaction, request: EventLogAppendRequest) -> EventLogAppendResult`
- `read_event_by_id(transaction: HostTransaction, event_id: str) -> EventLogRow | None`
- `read_events_after(transaction: HostTransaction, cursor: int, limit: int) -> tuple[EventLogRow, ...]`
- `IdempotencyScope`
- `IdempotencyResultRef`
- `IdempotencyRecord`
- `IdempotencyStore`
- `record_idempotent_result(transaction: HostTransaction, scope: IdempotencyScope, semantic_input_digest: str, result: IdempotencyResultRef) -> IdempotencyRecord`
- `read_idempotency_record(...) -> IdempotencyRecord | None`

Tests:

- `tests/host/test_event_log_store.py`
  - append canonical event returns `event_sequence=1` on fresh DB.
  - appending multiple event classes allocates one global monotonic cursor.
  - `event_id` duplicate with same body digest returns existing row and does not increase row count.
  - `event_id` duplicate with different payload / type / session raises `HostEventIdentityConflictError`.
  - reader by cursor returns rows after cursor ordered by `event_sequence`.
  - invalid event_class / empty ids / invalid timestamp / non-canonical payload ref combination fails before or during insert with structured error.
  - EventLog append with a non-existent non-null `payload_ref` raises `HostForeignKeyError` and transaction runner does not retry it.
  - after-commit callback for append is called only after committed append.
- `tests/host/test_event_log_multiprocess.py`
  - multiple processes append events into the same Host SQLite DB through `HostTransactionRunner`.
  - final row count equals total successful appends.
  - `event_sequence` values are unique, gap-tolerant but strictly increasing by row order, and no duplicate `event_id` appears.
  - busy / locked contention eventually succeeds within retry policy for normal short appends, or fails with structured retry exhausted error when deliberately held beyond policy.
- `tests/host/test_idempotency_store.py`
  - first idempotency record insert stores semantic digest and result ref.
  - same scope + key + same digest returns existing record.
  - same scope + key + different digest raises `HostIdempotencyConflictError`.
  - conflict is not retried by transaction runner.
  - idempotency record can reference created event id / sequence through FK.

Expected assertions:

- `event_sequence` is not a process-local counter.
- duplicate `event_id` never appends a second row.
- missing `payload_ref` FK violation is wrapped as `HostForeignKeyError` and is not retried.
- idempotency conflict returns structured Host durable error, not raw `sqlite3.IntegrityError`.
- reader uses global cursor semantics even when later filters are introduced.

Completion signal:

- Slice 2 tests pass, including multi-process smoke.
- `python -m pyright dayu/host tests/host` passes or has no new / expanded errors relative to baseline.
- Implementation artifact reports no need for Session / Run / Attempt state machine to use EventLog foundation.

Stop condition:

- Stop if appender needs to update Run / Attempt state indexes.
- Stop if idempotency scope cannot be expressed without inventing command path semantics.
- Stop if multi-process append requires using `dayu.runtime.lane` or file locks for EventLog ordering.

Explicit non-goals:

- No payload descriptor write beyond accepting nullable `payload_ref`.
- No projection, stream fanout, audit, trace, outbox or memory consumer.
- No EngineEvent ingest classifier.
- No Session / Run / Attempt status updates.

### Slice 3: Payload Descriptor / Local Artifact Ref Helper / Host Instance Liveness / Diagnostics Foundation

Objective:

- Implement minimal payload descriptor storage, local artifact write helper, host instance liveness primitive and failure diagnostics foundation required by future recovery / payload consumers.

Allowed files / modules:

- `dayu/host/durable/payload.py`
- `dayu/host/durable/artifact.py`
- `dayu/host/durable/liveness.py`
- targeted updates to `dayu/host/durable/errors.py`、`dayu/host/durable/options.py`、`dayu/host/durable/event_log.py` only if required to wire descriptor refs.
- `tests/host/test_payload_store.py`
- `tests/host/test_artifact_store.py`
- `tests/host/test_host_instance_liveness.py`
- `dayu/host/README.md` and `tests/README.md` only after checking README trigger rules and only within their stated responsibilities.

Dependencies:

- Slice 1 and Slice 2 accepted and committed by controller.

Exact allowed changes:

- Add payload descriptor dataclasses / enums and SQLite payload insert / descriptor insert / read helpers.
- Add local artifact helper that writes temp file, flushes / fsyncs, verifies digest, atomic renames to final relative path, and returns `LocalArtifactRef`.
- Add tests for transaction failure after artifact publish proving no accepted SQLite descriptor / EventLog row exists.
- Add host instance liveness dataclasses / enum and current-instance register / heartbeat / mark / read helpers.
- Add no diagnostics table; diagnostics foundation is structured errors plus test coverage for artifact orphan window.

Target functions / classes / types:

- `PayloadKind`
- `SQLitePayloadFormat`
- `SQLitePayloadWriteRequest`
- `PayloadDescriptor`
- `LocalArtifactRef`
- `PayloadStore`
- `write_sqlite_payload(transaction, request) -> PayloadDescriptor`
- `write_payload_descriptor_for_artifact(transaction, payload_ref, artifact_ref, media_type, metadata) -> PayloadDescriptor`
- `read_payload_descriptor(transaction, payload_ref) -> PayloadDescriptor | None`
- `LocalArtifactStore`
- `write_artifact_bytes(content: bytes, *, expected_digest: str | None = None) -> LocalArtifactRef`
- `HostInstanceStatus`
- `HostInstanceIdentity`
- `HostInstanceRow`
- `HostInstanceLivenessStore`
- `register_current_instance(...) -> HostInstanceRow`
- `heartbeat_current_instance(...) -> HostInstanceRow`
- `mark_current_instance_stopping(...) -> HostInstanceRow | None`
- `mark_current_instance_stopped(...) -> HostInstanceRow | None`
- `read_host_instance(...) -> HostInstanceRow | None`

Tests:

- `tests/host/test_payload_store.py`
  - canonical JSON payload under threshold writes `sqlite_payload` row and descriptor in one transaction.
  - bytes payload writes bytes row and descriptor with correct digest / size.
  - descriptor read returns typed `PayloadDescriptor`.
  - descriptor with missing sqlite payload FK fails as foreign key error.
  - digest mismatch raises `HostDigestMismatchError` and is not retried.
  - EventLog append can reference an existing descriptor and payload digest.
- `tests/host/test_artifact_store.py`
  - artifact helper writes under configured artifact root, not cwd or env.
  - relative path cannot be absolute, contain null byte, traverse with `..`, or escape artifact root through symlink resolution.
  - temp files are created under `artifact_root/.tmp/` with unguessable random id or `tempfile` exclusive creation, so concurrent writers do not collide.
  - temp file is not referenced by EventLog.
  - digest verify happens before final descriptor write.
  - final artifact path is atomically published and content digest matches returned ref.
  - forced SQLite failure after artifact publish leaves no descriptor and no EventLog row; published file is classified as cleanup / diagnostics orphan, not accepted fact.
- `tests/host/test_host_instance_liveness.py`
  - register inserts current instance with `running`, `created_at`, `heartbeat_at`.
  - repeated register with the same `HostInstanceIdentity` idempotently refreshes heartbeat/status.
  - register with the same `host_instance_id` and different `process_start_token` raises `HostInstanceIdentityConflictError`.
  - heartbeat updates only same `host_instance_id` + `process_start_token`.
  - heartbeat with missing current row raises `HostInstanceNotRegisteredError`.
  - heartbeat with wrong token does not refresh another instance and raises `HostInstanceIdentityConflictError`.
  - mark stopping / stopped updates only current row and is best-effort when row absent.
  - read returns typed row.
  - no test expects lease, fencing, orphan classifier, dispatch join, Attempt `LOST`, Run `RECOVERING` or takeover.

Expected assertions:

- `payload_inline_threshold_bytes` default is `65536` and can be overridden through `PayloadStoragePolicy`.
- artifact root is injected through options and can be test temp directory.
- artifact temp area is exactly under `artifact_root/.tmp/` and final resolved paths remain contained under artifact root.
- EventLog never references an artifact temp path.
- host instance heartbeat stale alone is not interpreted as orphan proof in any Phase 2 API.

Completion signal:

- Slice 3 tests pass.
- `python -m pyright dayu/host tests/host` passes or has no new / expanded errors relative to baseline.
- README check completed and only in-scope docs updated.
- Implementation artifact reports Phase 2 durable foundation complete and ready for Phase 3 state machine / admission to consume.

Stop condition:

- Stop if implementing payload descriptor requires ToolRuntime, Fins storage or trace cold data.
- Stop if liveness helper needs dispatch record, recovery classifier or Attempt / Run state updates.
- Stop if artifact cleanup scheduler or diagnostics projection becomes necessary.

Explicit non-goals:

- No positive orphan proof classifier.
- No lease / fencing / takeover.
- No projection cleanup worker.
- No ToolRuntime truncation cursor.
- No Fins document storage access.

## Tests And Validation Commands

All commands must run after activating the project virtualenv:

```bash
source .venv/bin/activate
```

Slice-scoped unit / integration tests:

```bash
pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q
pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q
pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q
```

Multi-process / concurrent append smoke:

```bash
pytest tests/host/test_event_log_multiprocess.py -q
```

Host regression and boundary tests:

```bash
pytest tests/host -q
```

Runtime regression check, to ensure Phase 2 did not pollute runtime boundaries:

```bash
pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q
```

Type check:

```bash
python -m pyright dayu/host tests/host
python -m pyright dayu/ tests/ utils/
```

Expected failure paths to test:

- schema version mismatch。
- invalid DB path / artifact root / policy values。
- SQLite busy / locked retry exhaustion。
- unique constraint conflict not retried。
- foreign key error not retried。
- EventLog append referencing missing `payload_ref` raises `HostForeignKeyError` and is not retried。
- after-commit callback not called on rollback。
- after-commit callback failure after committed row remains committed。
- duplicate event id with different body digest。
- idempotency same key different semantic digest。
- digest mismatch for payload / artifact。
- artifact path traversal / null byte / symlink escape attempt。
- SQLite transaction failure after artifact publish leaves no accepted descriptor / EventLog fact。
- heartbeat with wrong process token does not update another host instance。

Coverage expectation:

- New production files under `dayu/host/durable/` should have focused tests; single-file coverage target is >= 80% unless a file is pure constants / DDL and coverage is better represented through integration tests.

## Documentation Update Decision

README trigger check is required after implementation, but this plan itself does not modify README.

- `dayu/host/README.md`: Phase 2 modifies `dayu/host/`, so implementation must check this README. Update only if durable foundation is actually implemented; write current internal durable boundary, schema / transaction / EventLog / payload / liveness overview and non-goals. Do not write command path, state machine, recovery classifier or future phase details as completed.
- `tests/README.md`: Phase 2 adds `tests/host` durable tests and multi-process append smoke, so implementation must check this README. Update only current test layering, commands and maintenance rules.
- Root `README.md`: no user installation / CLI / workflow change expected; default no update.
- `dayu/README.md`: no terminology change expected; default no update. If implementation discovers a terminology conflict, stop and return to controller rather than editing terminology opportunistically.
- `docs/host/design.md` and `docs/host/implementation-control.md`: explicitly not allowed in this handoff.

## Review Gates

Plan review must verify:

- Motivation and direct evidence are anchored in the listed true sources.
- No Session / Run / Attempt state machine, command path, Engine dispatch, projection, memory, ToolRuntime, remote transport, recovery classifier, lease / fencing / takeover or migration compatibility slipped into scope.
- Module ownership stays in `dayu.host.durable`; `dayu.runtime` does not carry Host durable truth.
- Schema convention, transaction runner, storage policy defaults, timestamp format, canonical JSON, digest semantics, EventLog row contract, idempotency primitive, payload descriptor, artifact ordering and liveness primitive are concrete enough for code generation.
- Slices are small, ordered and file-bounded.
- Tests include expected assertions and failure paths, including concurrent append, idempotency conflict, digest mismatch, artifact orphan window and after-commit rollback behavior.
- README decision follows project trigger rules.

Code review for each slice must verify:

- Implementation stays within assigned slice and allowed files.
- All public / internal signatures are strongly typed; no `Any`、`object`、untyped parameters / returns or bare generic annotations.
- All modules, classes and functions have complete Chinese docstrings with params / returns / raises where applicable.
- No compatibility re-export / wrapper / facade.
- No hidden global storage policy or cwd / env-derived artifact root.
- No raw `sqlite3.IntegrityError` leaks where this plan requires structured Host durable error.
- No after-commit callback fires before successful commit.
- No artifact temp path can enter EventLog.
- No liveness primitive is interpreted as lease / fencing / owner.

## Stop Conditions

Controller / implementation agent must stop and report if:

- A material schema / transaction / contract decision not covered by this plan blocks implementation.
- Implementing a slice requires modifying forbidden modules or docs.
- Existing dirty changes in touched files make ownership unclear.
- pyright reveals pre-existing errors in touched files that cannot be fixed without expanding scope.
- Multi-process append cannot pass without adding runtime lane / filelock around EventLog ordering.
- Payload descriptor implementation needs Fins storage, ToolRuntime, trace projection or cleanup scheduler.
- Host instance liveness implementation needs recovery classifier, dispatch record or Attempt / Run state machine.

## Risks

- SQLite + external artifact writes are not atomic together. This is accepted by design; published-but-unreferenced artifact files are cleanup / diagnostics risk, not accepted fact. Slice 3 must test this crash window.
- `event_body_digest` is an implementation guard added to distinguish duplicate ledger identity from identity conflict. Review should verify the digest input is canonical and excludes only database-assigned fields.
- Multi-process tests can be timing-sensitive. Keep retry defaults short but finite, and write tests around invariants rather than exact sleep counts.
- `payload_inline_threshold_bytes=65536` is a plan-level default, not a business rule. Composition root options must override it.
- `HostAfterCommitError` after successful commit can make caller observe an exception after durable success. Tests and docs must make this explicit so later command path can decide result reporting semantics.

## Open Questions

### Blocking Questions For Controller

None. The material schema, transaction, storage policy, EventLog, idempotency, payload and liveness decisions needed for implementation are explicitly decided in this plan.

### Non-Blocking Questions

- Whether future command path exposes `dayu.host.durable` types directly or wraps them behind command services is deferred to later phases. This is non-blocking because Phase 2 only creates Host-internal foundation modules.
- Whether artifact orphan cleanup is manual, startup diagnostic, or background cleanup is deferred to a later cleanup / diagnostics work unit. This is non-blocking because accepted canonical facts already require descriptor + EventLog commit.
- Whether future `run_sequence` / `session_sequence` read-model optimization is needed is deferred to projection / read model phases. This is non-blocking because global `event_sequence` is the only Phase 2 cursor.

## Ready For Plan Review

This plan is ready for plan review. It has no blocking open question.

## Implementation Completion Report Format

Each implementation slice report must include:

```markdown
## Work Gate

implementation

## Work Unit And Slice

- Work unit: Host Phase 2 Durable Store / EventLog / Payload Foundation
- Assigned slice: <slice id and name>
- Approved plan: docs/host/phase2-durable-store-eventlog-plan.md

## Scope

- Allowed files / modules:
- Explicit non-goals:
- Plan items implemented:
- Plan items not implemented and reason:

## Changed Files

- <path>: <summary>

## Validation

- <command>: <result>
- <command>: <result>

## Documentation Decision

- README files checked:
- README files updated:
- Reason for no update, if applicable:

## Plan Gaps Or Controller Questions

- None / <details>

## Residual Risks And Uncovered Areas

- <risk>: fixed in current slice / covered by later slice <id> / assigned to later phase or work unit / tracked by issue / requires user decision

## Completion Signal

- <slice-specific completion signal status>

## Stop Condition Status

- No stop condition hit / <details>

## Artifact Path

- <implementation artifact path>
```
