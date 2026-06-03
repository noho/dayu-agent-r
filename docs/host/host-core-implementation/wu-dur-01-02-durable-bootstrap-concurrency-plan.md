# WU-DUR-01 + WU-DUR-02 Durable Bootstrap / Concurrency Plan

## Gate / Role

- **Gate**: WU-DUR-01 + WU-DUR-02 joint plan gate
- **Role**: planning specialist；只写 code-generation-ready plan，不实现代码，不做 review，不提交，不 push，不创建 PR。
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Inspection artifact**: `docs/reviews/wu-dur-01-02-discussion-code-inspection-20260601.md`
- **Plan output**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`

## Goal / Motivation / Why Risk Is Real

本 work unit 目标是用测试先行、窄范围实现关闭两个真实 durable 风险面：

- WU-DUR-01：fresh bootstrap DDL 与 `PRAGMA user_version` 必须同事务同成同败；current-version DB 缺 required table / index 时，普通 opener 必须结构化失败，不能通过 `CREATE ... IF NOT EXISTS` 静默补齐；WAL checkpoint 只补 Host durable 内部 maintenance diagnostic；read stale snapshot 语义补直接测试。
- WU-DUR-02：只补 inspection 证明仍缺的 durable concurrency matrix 项。EventLog append 与 `ensure_session` 多进程项已经 closed by evidence，不制造表面改动；idempotency、projection checkpoint CAS、memory snapshot + checkpoint CAS 补缺口测试；liveness update 继续 closed by evidence，除非新增测试直接暴露问题。

动机成立，且严重性没有被高估：

- `docs/host/design.md:738-753` 要求 fresh DDL 与 `user_version` 有明确事务边界，current-version opener 不得只信 `user_version` 或静默修表，WAL auto-checkpoint 只是 baseline，fresh truth 读取必须开启新的短事务。
- `docs/host/host-core-followup-implementation-control.md:248-298` 明确 WU-DUR-01 / WU-DUR-02 的验收信号，并要求先核对已有覆盖、只补真实缺口。
- `dayu/host/durable/connection.py:146-168` 的普通 opener 当前总是调用 `bootstrap_host_durable_store()`，再做 version validation。
- `dayu/host/durable/schema.py:1226-1250` 当前在 `isolation_level=None` connection 上逐条执行 `HOST_DURABLE_DDL`，之后设置 `PRAGMA user_version` 并 commit；没有显式 fresh bootstrap transaction。
- `dayu/host/durable/schema.py:1253-1269` 当前 validation 只读取 `PRAGMA user_version`，不校验 required table / index。
- `dayu/host/durable/transaction.py:366-379` 当前只有 `wal_autocheckpoint=256` baseline；inspection 未发现 Host-owned checkpoint maintenance primitive、WAL size / result 观测或 busy / failure diagnostic。
- `dayu/host/durable/transaction.py:314-363` 的 read transaction 使用 `BEGIN`，具备 SQLite snapshot stale 语义，但 inspection 未找到长 read transaction 旧快照 / 新 read transaction fresh truth 的直接测试。
- `docs/reviews/wu-dur-01-02-discussion-code-inspection-20260601.md:76-100` 已逐项裁决真实缺口和 closed-by-evidence 项；本计划只按该证据实施。

## Non-goals / Scope Boundaries

- 不新增 Host public maintenance API，不修改 `open_host(options)`、`OpenHostOptions`、Service-facing `Host` handle 或 `dayu.host` public exports。
- 不新增后台 lifecycle scheduler，不把 WAL checkpoint 接入 hot write path，不把 checkpoint 成功作为 EventLog append、state transition、recovery、projection 或 memory correctness 前置条件。
- 不引入旧 schema 兼容读取、兼容迁移、offline repair / rebuild 工具或兼容 wrapper。按全新 schema 起库处理；current-version 缺结构直接 fail closed。
- 不把所有 durable 操作抽象成 God helper；schema validation、WAL maintenance、idempotency、projection、memory、liveness 仍由各自 owner 负责。
- 不重做已覆盖的 busy retry、after-commit aggregation、基础 transaction wrapper、EventLog append 多进程 sequence / identity conflict、`ensure_session` 同 slot 多进程一致性。
- 不发明 memory snapshot row 自身 CAS。本轮 “memory CAS” 只指 `write_memory_snapshot_with_checkpoint()` 写 snapshot 后推进 projection checkpoint CAS，并由同一 transaction rollback 保证 snapshot 不半提交。
- 默认不纳入 rollback failure。inspection 只说明 `_rollback()` best-effort suppresses sqlite error，但 controller 裁决边界未要求 WU-DUR-02 覆盖 rollback failure；将其纳入会扩大 scope。
- 不修改 `docs/host/design.md`、`docs/host/host-core-followup-implementation-control.md` 或 inspection artifact。若实现时发现必须改 public contract、schema version、state-machine 或 maintenance API，立即停止并回报 blocking design question。

## Affected Files / Modules

Planning specialist 本轮只允许编辑本 plan 文件。Implementation gate 的 allowed files 按 slice 限定如下。

### Slice 1 Allowed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/connection.py`
- `tests/host/test_durable_schema.py`
- `dayu/host/README.md`，仅当当前 Host durable opener / schema validation 说明与代码事实不一致时更新。

### Slice 2 Allowed Files

- `dayu/host/durable/maintenance.py`，新增 Host durable 内部 WAL maintenance primitive。
- `dayu/host/durable/transaction.py`，仅允许复用现有 `_SQLITE_WAL_AUTOCHECKPOINT_PAGES` 或移动常量 owner，禁止改 transaction retry 语义。
- `tests/host/test_durable_connection.py`
- `tests/host/test_durable_transaction.py`
- `dayu/host/README.md`，仅同步内部 durable maintenance / read transaction 当前能力。

### Slice 3 Allowed Files

- `tests/host/test_durable_concurrency_matrix.py`，新增矩阵缺口测试。
- `tests/host/test_idempotency_store.py`，仅当复用现有 helper 比新增文件更窄时可添加轻量多进程测试。
- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_memory_projection.py`
- `dayu/host/durable/idempotency.py`、`dayu/host/durable/projection.py`、`dayu/host/durable/memory.py`，仅当新增 tests-first 测试暴露错误分类或 rollback 语义不稳定时允许最小修复。
- 禁止修改 `dayu/host/durable/event_log.py`、`dayu/host/durable/session_lifecycle.py`、`dayu/host/durable/liveness.py`，除非测试给出新的直接 failure evidence 并由 controller 接受。

### Slice 4 Allowed Files

- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-dur-01-02-implementation-slice*-*.md`，implementation artifact 输出路径由 controller 分配。
- 禁止修改根目录 `README.md`、`dayu/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`，除非实际代码变化命中对应职责触发规则。

## Contract / Schema / State-machine / Public-interface Changes

- **Host public API**: 无变化。
- **Service-facing behavior**: 无变化。
- **Durable DDL shape**: 不新增表，不新增索引，不改变 column / CHECK / FK，不 bump `HOST_SCHEMA_VERSION`。本轮改变的是 opener validation behavior。
- **Schema validation behavior**: 有变化。`user_version == HOST_SCHEMA_VERSION` 但缺 required table / index 的 DB，普通 opener 从“静默补齐并继续运行”改为结构化 `HostSchemaMismatchError` / `HostDurableError` 失败。该行为符合设计真源，不是兼容破坏规避对象。
- **Fresh bootstrap state**: 有变化。fresh DB 的全量 DDL 与 `PRAGMA user_version` 在同一显式 transaction 内执行，DDL 中途失败必须 rollback，不留下 partial schema 或 current `user_version`。
- **WAL maintenance interface**: 只新增 `dayu.host.durable` 内部模块函数 / dataclass，不导出到 `dayu.host` 包根，不进入 public opener contract，不注册后台任务。
- **State machine / EventLog semantics**: 无变化。
- **Concurrency semantics**: 仅补测试和必要诊断稳定性；不改变 EventLog append、idempotency、projection checkpoint、memory projection、liveness 的设计语义。

## Detailed Implementation Decisions

### Fresh Bootstrap Transaction

`bootstrap_host_durable_store(connection)` 必须分成两个分支：

- `user_version == 0`: 调用私有 helper，例如 `_bootstrap_fresh_schema(connection)`。该 helper 执行：
  - `BEGIN IMMEDIATE`
  - 顺序执行 `HOST_DURABLE_DDL`
  - `PRAGMA user_version={HOST_SCHEMA_VERSION}`
  - `COMMIT`
  - 失败时 best-effort `ROLLBACK` 后透传原始 `sqlite3.Error`，由 opener 包装成现有 durable error。
- `user_version == HOST_SCHEMA_VERSION`: 不执行任何 DDL；只调用 `validate_host_durable_schema(connection)` 做 full schema validation。
- 其它 version：抛 `HostSchemaMismatchError`，保持现有 mismatch 语义。

`_bootstrap_fresh_schema(connection)` 是本 work unit 唯一允许执行 `HOST_DURABLE_DDL` 的路径。`bootstrap_host_durable_store()` 自身不得在该 helper 外遍历或执行 `HOST_DURABLE_DDL`；`user_version == HOST_SCHEMA_VERSION` 分支必须直接跳过 DDL loop，避免 current-version DB 被 `CREATE ... IF NOT EXISTS` 静默补齐。

DDL 仍可保留 `CREATE ... IF NOT EXISTS`，因为 fresh branch 只服务 `user_version == 0` 的新库；但 current branch 禁止执行 DDL，避免静默补齐。

### Required Table / Index Validation Owner And Call Ownership

schema validation owner 放在 `dayu/host/durable/schema.py`。新增或改名为 `validate_host_durable_schema(connection)`，它必须：

- 先校验 `PRAGMA user_version == HOST_SCHEMA_VERSION`。
- 查询 `sqlite_master`，校验 `HOST_DURABLE_TABLES` 全量存在。
- 新增 `HOST_DURABLE_INDEXES: tuple[str, ...]`，必须包含 `schema.py` 中全部已有 `INDEX_*` durable index name constants，校验 required index 全量存在。初始集合必须覆盖：
  - `INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION`
  - `INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION`
  - `INDEX_HOST_RUNS_QUEUE_FIFO`
  - `INDEX_HOST_RUNS_SESSION_STATUS`
  - `INDEX_HOST_WAIT_RECORDS_ONE_ACTIVE_PER_RUN`
  - `INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL`
  - `INDEX_HOST_WAIT_RECORDS_EXTERNAL_JOB`
  - `INDEX_HOST_RUN_RESULTS_SESSION_TERMINAL_SEQUENCE`
  - `INDEX_HOST_SESSION_TIMELINE_ITEMS_SESSION_SEQUENCE`
  - `INDEX_HOST_SESSION_TIMELINE_ITEMS_RUN_SEQUENCE`
  - `INDEX_HOST_MEMORY_SNAPSHOTS_SESSION_CURSOR`
  - `INDEX_HOST_MEMORY_ITEMS_SESSION_SEQUENCE`
  - `INDEX_HOST_MEMORY_DIAGNOSTICS_SESSION_REASON`
  - `INDEX_EVENT_LOG_RUN_TYPE_SEQUENCE`
  - `INDEX_HOST_TOOL_TRACE_HOT_RUN_SEQUENCE`
  - `INDEX_HOST_TOOL_TRACE_HOT_TOOL_SEQUENCE`
  - `INDEX_HOST_TOOL_TRACE_HOT_TOOL_CALL`
  - `INDEX_HOST_TOOL_TRACE_HOT_PROVIDER_REQUEST`
  - `INDEX_HOST_TOOL_TRACE_HOT_DIAGNOSTIC_REF`
  - `INDEX_HOST_OUTBOX_TERMINAL_ITEMS_SESSION_SEQUENCE`
  - `INDEX_HOST_OUTBOX_TERMINAL_ITEMS_STATE_SEQUENCE`
  - `INDEX_HOST_OUTBOX_TERMINAL_ITEMS_RUN`
  - `INDEX_HOST_PURGE_TOMBSTONES_SESSION`
- 缺 table 时抛 `HostSchemaMismatchError("Host durable schema missing required table: ...")`。
- 缺 index 时抛 `HostSchemaMismatchError("Host durable schema missing required index: ...")`。
- 不做旧库迁移，不尝试 repair，不根据缺失对象执行 DDL。

validation call ownership 固定如下，避免 primary opener 双重 full validation：

- `open_host_durable_store()`：只负责 parent 准备、raw connection、PRAGMA setup、调用 `bootstrap_host_durable_store(connection)`，不在 bootstrap 返回后再次调用 `validate_host_durable_schema()`。
- `bootstrap_host_durable_store()`：是 primary opener 的 schema dispatch + final validation owner。fresh 分支调用 `_bootstrap_fresh_schema(connection)` 后立即调用 `validate_host_durable_schema(connection)`；current 分支只调用 `validate_host_durable_schema(connection)`；mismatch 分支抛 `HostSchemaMismatchError`。
- `_open_configured_connection()` / `HostDurableStore.connect()`：是 secondary connection validation-only 路径。该路径只做 parent 准备、raw connection、PRAGMA setup、`validate_host_durable_schema(connection)`；不得调用 `bootstrap_host_durable_store()`、不得调用 `_bootstrap_fresh_schema()`、不得执行任何 DDL。

### WAL Checkpoint Internal Primitive / Diagnostic

新增 `dayu/host/durable/maintenance.py`，模块概览 docstring 必须说明：该模块只服务 Host durable 内部 maintenance / test entry，不是 public maintenance API，不改变 EventLog correctness 前置条件。

建议固定类型：

```python
class HostWalCheckpointMode(StrEnum):
    """Host durable WAL checkpoint 模式。"""

    PASSIVE = "PASSIVE"
    TRUNCATE = "TRUNCATE"


@dataclass(frozen=True, slots=True)
class HostWalCheckpointResult:
    """WAL checkpoint 诊断结果。

    :param mode: 执行的 checkpoint 模式。
    :param busy_pages: SQLite 返回的 busy pages / frames 数。
    :param log_pages: WAL log pages / frames 数。
    :param checkpointed_pages: 已 checkpoint pages / frames 数。
    :param wal_size_bytes: 调用后 WAL 文件大小；文件不存在时为 ``0``。
    """
```

函数签名：

```python
def run_host_wal_checkpoint(
    connection: sqlite3.Connection,
    *,
    db_path: Path,
    mode: HostWalCheckpointMode = HostWalCheckpointMode.PASSIVE,
) -> HostWalCheckpointResult:
    ...
```

约束：

- 只执行 `PRAGMA wal_checkpoint(PASSIVE)` 或 `PRAGMA wal_checkpoint(TRUNCATE)`。
- 必须读取 SQLite 返回 row，缺 row 时抛 `HostDurableError("Host durable WAL checkpoint returned no result")`。
- `busy_pages > 0` 不抛错，返回 diagnostic；调用方可用它判断 busy。
- `sqlite3.Error` 统一转为 `HostDurableError("Host durable WAL checkpoint failed")`。
- `wal_size_bytes` 通过 `db_path.with_name(db_path.name + "-wal")` 读取；不存在则为 `0`。
- 不在 `open_host_durable_store()`、transaction runner、EventLog append 或 projection writer 中自动调用。

如果 implementation agent 判断必须新增 public API、后台 scheduler、opener option 或 lifecycle hook 才能满足 WAL checkpoint 验收，立即停止并报告 blocking design question；不得自行扩展。

### Read Stale Tests

新增直接测试证明：

- 在同一 DB 文件上创建两个独立 SQLite connections，例如 `open_host_durable_store()` 返回的 primary store connection 作为 connection A，再通过同一个 `HostDurableStore` 的 `store.connect()` 获取 connection B。
- connection A 通过 `HostTransactionRunner.run_read()` 开启 read transaction 并读取 EventLog count。
- read transaction 未结束时，connection B 通过独立 runner `run_write()` append canonical EventLog row 并 commit。
- connection A 在同一个 read transaction 内再次读取 count，仍看到旧 count。
- connection A read transaction commit 后，新的短 read transaction 必须看到 connection B 已提交的新 count。

该测试只证明 SQLite snapshot 语义和短事务 fresh truth；不要求改 production code。public read / recovery / scheduler governance 是否复用长 read transaction 以 code evidence 为准，若发现生产路径持有长 read transaction 做 governance decision，停止并报告。

### Concurrency Matrix Tests

本轮矩阵裁决：

| 场景 | 处理 |
| --- | --- |
| EventLog append 不同 `event_id` 多进程 | closed by evidence：`tests/host/test_event_log_multiprocess.py:213`。不改。 |
| EventLog append 同 `event_id` 异体并发 | closed by evidence：`tests/host/test_event_log_multiprocess.py:263`。不改。 |
| ensure_session 同 slot 多进程 | closed by evidence：`tests/host/test_admission_multiprocess.py:106`。不改。 |
| idempotency 同 key / same digest / different digest 真实 SQLite 多进程 | 补普通 pytest 多进程测试，不标 `stress`。 |
| projection checkpoint lost CAS | 补 synthetic direct test，断言 `"projection checkpoint advance lost CAS race"`。 |
| memory snapshot + checkpoint CAS | 补 direct test，证明 checkpoint CAS failure 会 rollback snapshot 写入；不新增 snapshot row CAS。 |
| liveness wrong identity / rowcount 0 classification | closed by evidence：`tests/host/test_host_instance_liveness.py:463` 等。默认不改。 |
| rollback failure | non-goal，不纳入。 |

idempotency 多进程测试应复用 `tests/host/test_event_log_multiprocess.py` / `tests/host/test_admission_multiprocess.py` 的 start gate + result files 模式，避免不可控 sleep。普通测试即可，因为进程数和轮次固定小预算，与现有 durable multiprocess smoke 同类；不使用 `stress` marker。

projection CAS synthetic test 推荐用 monkeypatch 让 `advance_projection_checkpoint()` 读到 stale checkpoint input：

- 先在真实 DB 初始化 consumer checkpoint 到 sequence 1。
- append 第二条 EventLog。
- monkeypatch `dayu.host.durable.projection.ensure_projection_checkpoint` 返回 stale `ProjectionCheckpointRow(..., checkpoint_event_sequence=0, ...)`。
- 调用 `advance_projection_checkpoint(... event_sequence=2 ...)`。
- 断言 `HostDurableError` message 包含 `"projection checkpoint advance lost CAS race"`，且 persisted checkpoint 仍是 sequence 1。

memory CAS direct test 使用同一 stale checkpoint 方法，通过 `write_memory_snapshot_with_checkpoint()` 触发 CAS failure：

- 先写入 checkpoint sequence 1。
- 构造 cursor sequence 2 的 `ConversationMemorySnapshot`。
- monkeypatch projection checkpoint read helper 使 checkpoint CAS rowcount 0。
- 在 `run_write()` 中调用 `write_memory_snapshot_with_checkpoint()`，断言抛 `HostDurableError`。
- 新短 read transaction 中断言目标 `snapshot_id` 不存在，checkpoint 仍是旧 sequence。

## Small Implementation Slices

### Slice 1: Bootstrap Atomicity And Current-schema Validation

- **Objective**: fresh bootstrap 全量 DDL + `user_version` 同事务同成同败；current-version 缺 table / index 普通 opener fail closed。
- **Allowed files/modules**: `dayu/host/durable/schema.py`、`dayu/host/durable/connection.py`、`tests/host/test_durable_schema.py`、必要时 `dayu/host/README.md`。
- **Prerequisites**: 无。
- **Exact changes**:
  - 在 `schema.py` 新增 `HOST_DURABLE_INDEXES`，包含全部已有 `INDEX_*` durable index name constants，不允许只挑核心索引子集。
  - 新增 `_bootstrap_fresh_schema(connection)` 私有 helper，显式 `BEGIN IMMEDIATE` / DDL / `PRAGMA user_version` / `COMMIT` / rollback。
  - 调整 `bootstrap_host_durable_store()`：`_bootstrap_fresh_schema(connection)` 是唯一允许执行 `HOST_DURABLE_DDL` 的路径；fresh 才执行 DDL 后 validate；current 只调用 `validate_host_durable_schema(connection)`，不 repair；mismatch 抛 `HostSchemaMismatchError`。
  - 新增 `validate_host_durable_schema(connection)`，校验 version、required tables、required indexes。
  - `open_host_durable_store()` 保留调用 `bootstrap_host_durable_store(connection)`，删除 bootstrap 返回后的重复 `validate_host_schema_version()` / `validate_host_durable_schema()` 调用，避免 primary opener 双重 full validation。
  - `_open_configured_connection()` / `HostDurableStore.connect()` 改为 validation-only secondary connection 路径：import / call `validate_host_durable_schema()`，不调用 bootstrap，不执行任何 DDL。
  - 删除或改写仅 version-only 的旧 helper；不要留下只为旧名字透传的新 wrapper。若保留 `validate_host_schema_version()`，它必须有独立真实语义，不能只是兼容 facade。
- **Functions/classes**:
  - `bootstrap_host_durable_store(connection: sqlite3.Connection) -> None`
  - `_bootstrap_fresh_schema(connection: sqlite3.Connection) -> None`
  - `validate_host_durable_schema(connection: sqlite3.Connection) -> None`
  - `_validate_required_tables(connection: sqlite3.Connection) -> None`
  - `_validate_required_indexes(connection: sqlite3.Connection) -> None`
- **Data flow**:
  - primary opener configures PRAGMA -> `bootstrap_host_durable_store()` decides fresh/current/mismatch -> fresh branch commits complete schema and validates / current branch only validates / mismatch raises -> store returned。
  - independent `store.connect()` configures PRAGMA -> full validation only -> connection returned；该路径不 bootstrap、不执行 DDL。
- **Error handling**:
  - non-current version: `HostSchemaMismatchError`。
  - missing table/index: `HostSchemaMismatchError` with specific object name。
  - fresh DDL failure: rollback, then existing opener wraps sqlite failure as `HostDurableError("Host durable SQLite bootstrap failed")` when invoked through opener。
  - rollback failure remains best-effort suppressed; not expanded.
- **Tests/validation**:
  - Add test injecting invalid DDL in the middle of `HOST_DURABLE_DDL`, assert no partial user tables and `PRAGMA user_version == 0` after failure.
  - Add test with raw DB `PRAGMA user_version=HOST_SCHEMA_VERSION` and no tables; `open_host_durable_store()` raises and does not create tables.
  - Add test dropping one required index from a fully bootstrapped DB; opener raises and does not recreate the index.
  - Add test for `HostDurableStore.connect()` / `_open_configured_connection()` path: after deleting one required table or index from a current-version DB, `store.connect()` raises `HostSchemaMismatchError` / `HostDurableError` and does not recreate the missing object.
  - Add consistency test that parses every `CREATE INDEX` / `CREATE UNIQUE INDEX` statement in `HOST_DURABLE_DDL`, extracts the index name set, and asserts it equals `set(HOST_DURABLE_INDEXES)`.
  - Existing `test_fresh_db_creates_*` and version mismatch tests must still pass.
- **Docs decision**:
  - Check `dayu/host/README.md` durable foundation wording. Update only if it incorrectly says opener only validates `user_version` or implies silent bootstrap repair of current DB.
- **Stop condition**:
  - Stop if transactional DDL cannot be made reliable with SQLite in this repo setup, or if fixing requires schema version bump / migration / offline repair design.

### Slice 2: Internal WAL Maintenance Primitive And Read-stale Proof

- **Objective**: add a Host durable internal WAL checkpoint diagnostic primitive and direct stale snapshot test without public API or scheduler.
- **Allowed files/modules**: `dayu/host/durable/maintenance.py`、`dayu/host/durable/transaction.py` only for constant owner cleanup、`tests/host/test_durable_connection.py`、`tests/host/test_durable_transaction.py`、必要时 `dayu/host/README.md`。
- **Prerequisites**: Slice 1 passed.
- **Exact changes**:
  - Add `maintenance.py` with `HostWalCheckpointMode`, `HostWalCheckpointResult`, `run_host_wal_checkpoint(...)` exactly as defined above.
  - Do not call `run_host_wal_checkpoint()` from opener, transaction runner, EventLog, projection, memory, scheduler or public handle.
  - Add tests for PASSIVE checkpoint result fields after WAL writes.
  - Add tests for busy diagnostic observability by holding an active read transaction on another configured connection, performing writes, then running PASSIVE checkpoint and asserting result fields are observable. This is a diagnostic-field observability test, not a requirement to stably manufacture `busy_pages > 0`; at minimum assert result fields are non-negative and no correctness path depends on checkpoint success.
  - Optional unit-level synthetic coverage may assert `busy_pages > 0` is returned as diagnostic only if it can be done without over-mocking SQLite correctness. Do not mock SQLite transaction, WAL, locking, checkpoint correctness, or production retry behavior just to force a busy result.
  - Add failure test with closed connection, asserting `HostDurableError("Host durable WAL checkpoint failed")`.
  - Add read stale snapshot direct test in `test_durable_transaction.py`.
- **Functions/classes**:
  - `HostWalCheckpointMode`
  - `HostWalCheckpointResult`
  - `run_host_wal_checkpoint(connection: sqlite3.Connection, *, db_path: Path, mode: HostWalCheckpointMode = HostWalCheckpointMode.PASSIVE) -> HostWalCheckpointResult`
- **Data flow**:
  - Test or future internal maintenance caller supplies a configured connection + DB path -> primitive executes SQLite checkpoint PRAGMA -> returns diagnostic only。
  - Read stale test uses two independent configured connections to the same DB file, preferably the primary store connection plus `store.connect()`, and two `HostTransactionRunner` instances。
- **Error handling**:
  - malformed / closed connection: `HostDurableError`。
  - checkpoint busy result: returned diagnostic, not exception。
  - missing PRAGMA row: `HostDurableError`。
- **Tests/validation**:
  - `pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q`
  - Assertions must prove checkpoint diagnostic fields are observable, checkpoint diagnostics do not mutate EventLog / state truth, and read stale behavior is isolated to a single read transaction.
  - Assertions must not require `busy_pages > 0` from a live SQLite PASSIVE checkpoint unless the local setup deterministically produces it without brittle timing.
- **Docs decision**:
  - Update `dayu/host/README.md` only if durable storage section needs to mention internal WAL maintenance diagnostic. Do not document it as Service-facing API.
- **Stop condition**:
  - Stop if implementation needs public maintenance method, opener option, background scheduler, or checkpoint correctness precondition.

### Slice 3: Durable Concurrency Matrix Gap Tests

- **Objective**: close WU-DUR-02 remaining evidence gaps with tests-first coverage for idempotency, projection checkpoint CAS and memory snapshot + checkpoint CAS.
- **Allowed files/modules**: `tests/host/test_durable_concurrency_matrix.py` preferred；or narrowly add to `tests/host/test_idempotency_store.py`、`tests/host/test_projection_checkpoint.py`、`tests/host/test_memory_projection.py`。Production files allowed only if new tests fail for real behavior: `dayu/host/durable/idempotency.py`、`dayu/host/durable/projection.py`、`dayu/host/durable/memory.py`。
- **Prerequisites**: Slice 1 passed. Slice 2 not required unless helpers are reused.
- **Exact changes**:
  - Add idempotency same scope/key/same digest multiprocess test: all workers use same digest with different result refs; assert one durable row, all returned records share winning digest/result ref, no conflict.
  - Add idempotency same scope/key/different digest multiprocess test: assert exactly one inserted/winner and remaining workers classify as `HostIdempotencyConflictError`; DB has one row.
  - Add projection checkpoint lost CAS synthetic test as specified in Detailed Implementation Decisions.
  - Add memory snapshot + checkpoint stale CAS test as specified; assert snapshot rollback and checkpoint unchanged.
  - Add a small matrix comment or module docstring listing closed-by-evidence rows and new rows, so future reviewers see why EventLog / ensure_session / liveness are not duplicated.
- **Functions/classes**:
  - Test-only worker target functions must be top-level for multiprocessing.
  - Test-only result constants must be module-level constants, not magic strings scattered through worker code.
  - Test-only helper functions must have full Chinese docstrings with 参数、返回值、异常。
  - No `Any` / `object` / untyped signature / bare `dict` / bare `list` annotations.
- **Data flow**:
  - Multiprocess workers open independent durable stores using the same DB path and artifact root, then call `record_idempotent_result()` inside `run_write()`。
  - Projection / memory CAS tests use real DB rows plus deterministic monkeypatch to force stale checkpoint precondition.
- **Error handling**:
  - Idempotency conflict must be `HostIdempotencyConflictError` and must not be retried as busy.
  - Projection / memory stale checkpoint must be `HostDurableError` with `"projection checkpoint advance lost CAS race"` or the existing positive / backward cursor error where applicable.
  - Memory snapshot write must rollback if checkpoint CAS fails.
- **Tests/validation**:
  - `pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q`
  - These tests are ordinary tests, not `stress` marker. Process counts must remain small and deterministic like existing durable multiprocess smoke.
- **Docs decision**:
  - Update `tests/README.md` only if a new test file or command materially changes the test manual. If tests are covered by existing `pytest tests/host -q` and existing durable foundation wording remains accurate, record “no README change needed” in implementation artifact.
- **Stop condition**:
  - Stop if implementation appears to require snapshot row CAS, liveness production changes, EventLog append changes, `ensure_session` changes, or rollback failure policy changes.

### Slice 4: Documentation Sync, Validation, And Handoff Artifacts

- **Objective**: ensure README sync decisions and validation evidence match actual changed files before review.
- **Allowed files/modules**: `dayu/host/README.md`、`tests/README.md`、implementation artifact under `docs/reviews/` assigned by controller。
- **Prerequisites**: Slices 1-3 complete.
- **Exact changes**:
  - Check `dayu/host/README.md` because `dayu/host/` production code changes are planned. Update only stable current facts about durable schema validation / internal WAL diagnostic if existing README is inaccurate.
  - Check `tests/README.md` because tests are changed. Update only if new file / command / ordinary multiprocess coverage needs stable mention.
  - Do not update root `README.md` unless implementation unexpectedly changes CLI, render, config entry, or project-level user workflow; current plan should not.
  - Produce implementation artifact listing per-slice changed files, tests run, pyright result, README decision and residual risks.
- **Tests/validation**:
  - Run affected pytest commands listed below.
  - Run pyright command listed below.
- **Docs decision**:
  - README updates must obey fixed responsibilities. No process status, future plan, changelog or old/new terminology coexistence.
- **Stop condition**:
  - Stop if README sync would require documenting public contract changes, because this plan forbids public contract changes.

## Tests And Validation Commands

All commands must run after:

```bash
source .venv/bin/activate
```

Affected pytest commands:

```bash
pytest tests/host/test_durable_schema.py -q
pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q
pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q
pytest tests/host/test_event_log_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_host_instance_liveness.py -q
```

If `tests/host/test_durable_concurrency_matrix.py` is not created and tests are added to existing files, replace the first path in the third command with the actual touched files.

Type check:

```bash
python -m pyright dayu/ tests/ utils/
```

README sync decision:

- `dayu/host/` 修改触发 `dayu/host/README.md` 检查；只更新当前 durable opener / maintenance / validation 稳定事实。
- `tests/` 修改触发 `tests/README.md` 检查；只更新测试分层、运行方式或维护规则中与当前代码不一致的部分。
- 本计划不触发根目录 `README.md`、`dayu/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`。

Stress / multiprocess marker decision:

- 新增 idempotency multiprocess tests 是普通 bounded multiprocess smoke，和既有 `test_event_log_multiprocess.py`、`test_admission_multiprocess.py` 同类，不加 `stress` marker。
- 不新增 pressure / soak / fuzz / long-running stress suite。

Coverage:

- 受影响新增或修改测试文件应维持单文件覆盖率目标 >= 80%。如果 coverage 工具不是当前默认命令，implementation artifact 必须说明未单独运行 coverage 的原因；但不得因此跳过 pytest / pyright。

## Review Gates

- **Plan review**: 由 controller 派发 `$planreview` / `/planreview` 或等价 plan review agent。重点检查 scope 是否过宽、WAL 是否误扩 public contract、memory CAS 是否误解、slice 是否 code-generation-ready。
- **Plan fix / re-review**: 只修 accepted plan findings；blocking open questions 必须在 re-review pass 前归零。
- **Implementation**: 按 slice 顺序执行，每个 slice tests-first，禁止提前做后续 slice。
- **Code review**: 每个 slice 完成后 review changed files / tests / docs decision，查 correctness、schema validation、transaction boundary、type-safety、README sync。
- **Fix / re-review**: 只修 controller-accepted findings。
- **Accepted slice commit**: 由 controller 执行，本 planning specialist 不提交。
- **Aggregate deepreview**: 所有 slices 后对当前 branch 相对 `main` 的完整 diff 运行 `$deepreview --base main` / `/deepreview --base main`。
- **PR review**: draft PR gate 获用户授权后再进入；本 plan 不 push、不创建 PR。

## Open Questions / Risks

### Blocking

none。

前提是 controller 既定裁决保持有效：WAL checkpoint 仅为 Host durable 内部 maintenance primitive / test entry；memory CAS 仅指 memory snapshot + projection checkpoint CAS；rollback failure 不纳入本轮。

### Non-blocking

- SQLite `PRAGMA wal_checkpoint(PASSIVE)` 在本地测试中未必稳定返回 `busy_pages > 0`。测试应断言 diagnostic 可观测、字段合法、failure 不影响 truth，而不是依赖具体 busy 数值。
- `validate_host_durable_schema()` 第一版只校验 required table / index existence，不做 full SQL DDL text diff。理由：总控和 inspection 的直接缺口是缺表 / 缺索引静默补齐；DDL text drift 可作为后续 WU-LAYER-01 schema invariant hardening，不在本轮扩大。
- 新增 idempotency multiprocess tests 可能在极慢机器上暴露 timing flake。实现应使用 start gate + finite retry policy + result files，不依赖 acquire ordering 或裸 sleep 判断成功。
- 保留 `CREATE ... IF NOT EXISTS` 在 DDL 文本中可能看起来与 current-version 不静默修复冲突；真实边界由 bootstrap 分支保证 current-version 不执行 DDL。若 reviewer 要求 DDL 文本移除 `IF NOT EXISTS`，需要评估 SQLite repeated fresh validation 和 test setup，不应机械替换。

## Completion Report Format

Implementation agent 每个 slice 完成后输出 artifact，格式固定如下：

```markdown
# WU-DUR-01-02 Implementation Slice <N> Report

- **Gate**: implementation
- **Work unit**: WU-DUR-01 + WU-DUR-02
- **Slice**: <slice id/name>
- **Approved plan**: docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md
- **Allowed files/modules**: <copy from assigned slice>
- **Changed files**:
  - <path>: <summary>
- **Implemented plan items**:
  - <item>
- **Tests run**:
  - `<command>` -> <pass/fail>
- **Pyright**:
  - `<command>` -> <pass/fail/not run with reason>
- **README decision**:
  - `dayu/host/README.md`: updated / checked-no-change / not applicable, with reason
  - `tests/README.md`: updated / checked-no-change / not applicable, with reason
- **Plan deviations**:
  - none / <explicit deviation and controller approval need>
- **Residual risks and classification**:
  - <risk>: fixed in current slice / covered by later slice / deferred-with-owner / needs user decision
- **Stop status**:
  - completed / stopped
- **Artifact path**: docs/reviews/<assigned-name>.md
```

Implementation agent must stop instead of continuing if it hits any stop condition, public contract pressure, schema migration pressure, memory snapshot row CAS pressure, rollback failure expansion, or need to modify forbidden files.
