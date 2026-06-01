# WU-DUR-01 + WU-DUR-02 Aggregate Deepreview — AgentDS

- **Gate**: aggregate deepreview
- **Role**: AgentDS
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Base**: `main`
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Planned target**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Date**: 2026-06-01

## Verdict

**PASS with findings — no correctness blockers.** 4 个 HIGH 严重性 findings 均不阻塞 draft-PR-pass；其中 2 个是设计边界 trade-off（已有对应 acceptance 或 deferred），1 个是并发 TOCTOU 已被 WAL + IF NOT EXISTS 缓解，1 个是可测试性缺口。MEDIUM findings 集中在 WAL checkpoint API 的 db_path/connection 一致性、error message precision 和 docstring 一处不一致。LOW findings 为测试 helper 重复、WAL 文件探测 edge case 和 validator error 单对象提示。

所有 Slice 1-4 的核心交付物均对齐 plan 和设计真源：bootstrap 原子性正确、current-schema validation 正确 fail closed、WAL checkpoint primitive 为纯 diagnostic、read stale 语义有直接测试、concurrency matrix 补齐缺口测试。无 layering 违规、无反向依赖、无 public API 变更。

## Summary of Changes

43 文件变更，+4213/-40 行，其中生产代码约 +278/-18，测试代码约 +1240/+0，review/discussion artifact 为 review gate 产物。

### Production changes

| File | Delta | Summary |
|---|---|---|
| `dayu/host/durable/schema.py` | +143/-18 | fresh bootstrap 事务化、current-version 只校验不修复、required index 校验 |
| `dayu/host/durable/connection.py` | +9/-10 | 删除重复 validation、secondary path 使用 full validation |
| `dayu/host/durable/maintenance.py` | +126 (new) | 内部 WAL checkpoint diagnostic primitive |
| `dayu/host/README.md` | +2/-1 | 同步 read snapshot 语义与 WAL checkpoint 位置 |

### Test changes

| File | Delta | Summary |
|---|---|---|
| `tests/host/test_durable_schema.py` | +232/-0 | bootstrap rollback、missing table/index、secondary validation、DDL↔constant 一致性 |
| `tests/host/test_durable_connection.py` | +240/-2 | WAL checkpoint observable fields、closed connection、stat failure、truth unchanged |
| `tests/host/test_durable_transaction.py` | +133/-0 | read stale snapshot proof |
| `tests/host/test_durable_concurrency_matrix.py` | +835 (new) | idempotency 多进程、projection lost CAS、memory CAS rollback |
| `tests/README.md` | +6/-1 | 更新测试命令与 concurrency matrix 描述 |

## Findings

### HIGH-1: fresh bootstrap 并发 TOCTOU — WAL + IF NOT EXISTS 缓解但无直接测试

**Severity**: HIGH
**Category**: Correctness / Atomicity
**Evidence**:
- `dayu/host/durable/schema.py:1268` — `bootstrap_host_durable_store()` 在显式事务外读取 `_read_user_version(connection)` 判断 `current_version == 0`
- `dayu/host/durable/schema.py:1316` — `_bootstrap_fresh_schema()` 在内部执行 `BEGIN IMMEDIATE`

**Root cause**: `user_version` 的读取和 `BEGIN IMMEDIATE` 不在同一原子边界内。两个并发的 `open_host_durable_store()` 调用可能同时读到 `user_version=0`，然后分别在各自的 `BEGIN IMMEDIATE` 事务中执行 DDL。第二个事务的 DDL 因为 `IF NOT EXISTS` 是安全 no-op，但依赖 DDL 文本中的 `IF NOT EXISTS` 作为隐式防御，而非显式并发 bootstrap 设计。

**Actual risk**: 低。原因：
- WAL 模式下 `BEGIN IMMEDIATE` 确保同一时刻只有一个 writer
- 第一个事务 COMMIT 后第二个事务看到 `user_version != 0` 的表已存在，`IF NOT EXISTS` 使 DDL 成为 no-op
- 不存在数据损坏或半初始化 schema 风险

**Mitigation**: 当前 DDL 保留 `IF NOT EXISTS`（plan 中明确裁决），这恰好防御了 TOCTOU 窗口。但 plan 中该防御未被显式列为并发安全保证。

**Recommendation**: 本轮不修代码；在 aggregate review artifact 中记录此 TOCTOU 窗口已被 WAL + IF NOT EXISTS 充分缓解，不作为 blocking finding。若后续需要更强证明，可增加并发 fresh bootstrap 直接测试（两个进程同时 open fresh DB 并断言双方成功、schema 完整）。已在 plan non-blocking open question 间接覆盖。

### HIGH-2: projection checkpoint lost CAS 测试使用 synthetic stale row 而非真实 race

**Severity**: HIGH
**Category**: Testability / Correctness proof
**Evidence**:
- `tests/host/test_durable_concurrency_matrix.py:558-563` — `_stale_projection_checkpoint()` 返回 `checkpoint_event_sequence=0`、`checkpoint_event_id=None` 的 synthetic row
- `tests/host/test_durable_concurrency_matrix.py:676-680` — 测试通过 monkeypatch `projection_module.ensure_projection_checkpoint` 注入 stale row
- `tests/host/test_durable_concurrency_matrix.py:724-736` — memory CAS 测试同样使用 synthetic stale row

**Root cause**: 测试 mock 返回的 synthetic stale row (`checkpoint_event_sequence=0`) 在 DB 中实际不存在——真实的 persisted checkpoint 在 `sequence=1`。`advance_projection_checkpoint` 的 CAS UPDATE 因为 WHERE 子句 `checkpoint_event_sequence=0` 匹配不到实际行而 rowcount=0，触发 `"projection checkpoint advance lost CAS race"` 错误。

这个测试验证了 **CAS failure 的错误处理和 rollback 行为**，但未验证 **真实并发下两个 writer 同时推进 checkpoint 的竞态**。这是 valid 的 unit-level 验证，但不是 end-to-end concurrency proof。

**Actual risk**: 中等。CAS failure 路径的代码行为已被验证（错误消息、checkpoint 不变、memory snapshot rollback）。但以下未验证：
- 真实多进程同时推进同一 consumer checkpoint 的 winner/loser 行为
- SQLite `BEGIN IMMEDIATE` 在真实竞态下的 serialization 是否正确隔离 CAS 检查与写入

**Recommendation**: 本轮不要求新增真实多进程 CAS race 测试。原因：plan 明确允许 monkeypatch 方式（plan:227-240），且已有 `test_event_log_multiprocess.py` 等多进程测试验证了 SQLite 并发 isolation。若后续 WU-LIFE-01 recovery lifecycle 需要更强 checkpoint race 证明，再补多进程 CAS 竞态测试。

### HIGH-3: WAL checkpoint `db_path` 与 `connection` 无一致性校验

**Severity**: HIGH
**Category**: Correctness / API safety
**Evidence**:
- `dayu/host/durable/maintenance.py:62-64` — `run_host_wal_checkpoint()` 独立接收 `connection` 和 `db_path` 两个参数
- `dayu/host/durable/maintenance.py:68` — `connection.execute(f"PRAGMA wal_checkpoint({mode.value})")` 在 connection 上执行
- `dayu/host/durable/maintenance.py:120-126` — `_read_wal_size_bytes(db_path)` 使用 `db_path.with_name(db_path.name + "-wal")` 独立读取 WAL 文件

**Root cause**: 函数签名不强制 `connection` 对应的数据库文件就是 `db_path`。如果调用方传入了不匹配的 `connection` 和 `db_path`，checkpoint 在 connection A 的数据库上执行，但 WAL 文件大小从 `db_path` 读取——两个数据库不一致时报告错误的 WAL size。更严重的是，如果 `db_path` 指向的不相关数据库恰好有同名 WAL 文件，诊断数据会产生静默错误的关联。

**Actual risk**: 低（当前调用方）。当前唯一调用方是测试代码（`test_durable_connection.py`），测试中 `db_path=options.db_path` 与 connection 来自同一 store，必然一致。但 `run_host_wal_checkpoint` 是 `dayu.host.durable` 内部 public 函数，后续 maintenance 调用方可能传入不一致参数。

**Recommendation**: 至少增加一个 assert 或 light validation：通过 `connection.execute("PRAGMA database_list")` 获取 attached database file path，与 `db_path.resolve()` 做一致性比对。若不匹配，抛 `HostDurableError`。当前是 "internal maintenance primitive"，API surface 窄，且 plan 禁止将 checkpoint 接入 hot write path——阻塞度低但不为零。建议作为 deferred-with-owner 记录。

### HIGH-4: `dayu/host/README.md` 更新为单行长句追加，降低可读性与可维护性

**Severity**: HIGH
**Category**: Maintainability / Documentation
**Evidence**:
- `dayu/host/README.md:291` — durable 条目从 ~190 字符扩展为 ~450 字符的单行 bullet point

**Root cause**: README 更新的内容是正确的——增加了 read snapshot 语义和 WAL checkpoint primitive 位置说明。但更新方式是将新内容追加到已有长 bullet 行中，而非拆分为独立 bullet 或段落。导致该行在渲染和编辑时都难以阅读。

**Recommendation**: 将 durable foundation bullet 拆成多个子项：
```markdown
- durable store、transaction runner、schema、state row codec、payload table helper：
  - schema 按当前 fresh version 起库，版本不匹配时要求重建 durable DB；
  - SQLite 连接启用 WAL 与 auto-checkpoint；
  - transaction runner 的 read transaction 使用 SQLite snapshot 语义，新的短读事务读取最新 committed truth；
  - 内部 WAL checkpoint primitive 只服务显式 diagnostic / test entry，不属于 public maintenance API；
  - store close 会拒绝活跃 transaction，避免 SQLite 隐式 rollback 未提交写入。
```

该修改属于 README 职责范围（`dayu/host/` 变更触发），不阻塞 draft-PR-pass，可随下一轮 review fix 或下一个 work unit 附带修改。

### MEDIUM-1: `validate_host_durable_schema` 错误消息不支持批量诊断

**Severity**: MEDIUM
**Category**: Maintainability / Operational
**Evidence**:
- `dayu/host/durable/schema.py:1344-1348` — `_validate_required_tables()` 在第一个缺失 table 处立即 `raise HostSchemaMismatchError`
- `dayu/host/durable/schema.py:1364-1368` — `_validate_required_indexes()` 同理

**Root cause**: 校验循环在第一个缺失对象处即抛出异常。如果 DB 同时缺失 3 个 table 和 2 个 index，用户需要修复一个、重试、再修复下一个……循环 5 次才能看到完整缺失清单。在生产事故排查场景下这会显著延长诊断周期。

**Recommendation**: 收集所有缺失对象名后再一次性抛出，例如：
```python
missing_tables = [t for t in HOST_DURABLE_TABLES if t not in existing_tables]
if missing_tables:
    raise HostSchemaMismatchError(
        f"Host durable schema missing required tables: {', '.join(missing_tables)}"
    )
```
这不需要改变异常类型或调用方签名，只是消息聚合。但 plan 未要求此项，当前行为也满足验收信号（"缺 table 时抛 HostSchemaMismatchError"）。建议 deferred 到 WU-LAYER-01。

### MEDIUM-2: `_bootstrap_fresh_schema` docstring 未声明 `isolation_level=None` 前置条件

**Severity**: MEDIUM
**Category**: Documentation / Correctness
**Evidence**:
- `dayu/host/durable/schema.py:1307-1314` — docstring 声明 "已完成 PRAGMA setup 的 SQLite connection"，但未提及 connection 必须是 `isolation_level=None`（autocommit 模式）
- `dayu/host/durable/connection.py:194-208` — `_open_raw_connection()` 固定使用 `isolation_level=None`

**Root cause**: `_bootstrap_fresh_schema` 内部的显式 `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` 依赖于 `isolation_level=None` 模式（autocommit）。如果 connection 使用默认 `isolation_level=''`（隐式事务模式），`BEGIN IMMEDIATE` 会触发 `sqlite3.OperationalError: cannot start a transaction within a transaction`。当前所有调用路径都经过 `_open_raw_connection()` 保证 `isolation_level=None`，但 docstring 未将此列为前置条件。

**Recommendation**: docstring 补充 "connection 必须处于 autocommit 模式（isolation_level=None）"。不要求运行时检查，因为所有内部调用路径已保证该前提。

### MEDIUM-3: Host durable README 与 connection.py docstring 有一处不一致

**Severity**: MEDIUM
**Category**: Documentation
**Evidence**:
- `dayu/host/durable/connection.py:83` — `HostDurableStore.connect()` docstring 返回描述为 "已设置 PRAGMA 并校验当前 schema 结构的 SQLite connection"
- `dayu/host/durable/connection.py:173` — `_open_configured_connection()` docstring 返回描述为 "已配置并校验当前 schema 结构的 SQLite connection"

两者已在 Slice 1 实现中同步更新为提到 "当前 schema 结构"（而非原来的 "schema version"），一致且正确。但 `dayu/host/README.md:291` 的 durable 条目未提及 secondary connection 也执行 full schema validation 的事实——当前描述只覆盖 primary opener。这不影响正确性，但 README 的 durable 描述与 connection.py 实际行为存在轻微 gap。

**Recommendation**: 可选在 HIGH-4 修复时一并补充 `store.connect()` 也会执行 full schema validation 的说明。非阻塞。

### LOW-1: 测试 helper `_event_request()` / `_append_event()` / `_count_event_log_rows()` 在多个测试文件中重复定义

**Severity**: LOW
**Category**: Maintainability
**Evidence**:
- `tests/host/test_durable_connection.py:67-106` — `_event_request()`, `_append_event()`, `_count_event_log_rows()`
- `tests/host/test_durable_transaction.py:108-158` — 同一组 helpers 重复
- `tests/host/test_durable_concurrency_matrix.py` — 使用 inline 的 `_AppendEventOperation` class，与上述略有不同

**Root cause**: 三个测试文件各自定义了语义几乎相同的 helper 函数。`test_durable_connection.py` 和 `test_durable_transaction.py` 的 helpers 完全重复。

**Recommendation**: 抽取到 `tests/host/conftest.py` 或 `tests/host/durable_test_helpers.py`。但这是测试辅助代码重复，不影响生产正确性，不阻塞本轮。可 deferred 到后续测试整理 work unit。

### LOW-2: `_read_wal_size_bytes` 在 WAL 文件被外部进程删除时返回 0

**Severity**: LOW
**Category**: Correctness / Edge case
**Evidence**:
- `dayu/host/durable/maintenance.py:118-126` — `FileNotFoundError` 捕获后返回 `0`

**Root cause**: `PRAGMA wal_checkpoint(PASSIVE)` 成功后 WAL 文件可能被 SQLite 自动 truncate 到 0 或删除。`_read_wal_size_bytes()` 在 `FileNotFoundError` 时返回 `0`，语义上表示 "WAL 文件不存在或已被清理"。但如果在 checkpoint 成功后、`Path.stat()` 调用前，另一个进程恰好删除了 WAL 文件（极端边缘场景），返回 `0` 仍然正确——WAL 文件确实不存在。这是一个 design choice，不是 bug。

**Recommendation**: 当前语义合理，不要求修改。但可考虑在 docstring 中说明返回 `0` 的两种场景（文件不存在 / 已被 SQLite 清理），提高可读性。

## Design Source Alignment

### 与 `docs/host/design.md` 对齐检查

| 设计真源要求 | 代码对齐 | 证据 |
|---|---|---|
| `design.md:738` — fresh bootstrap DDL 与 `user_version` 同成同败 | **对齐** | `schema.py:1307-1327` `_bootstrap_fresh_schema()` 在单事务中执行全部 DDL + PRAGMA + COMMIT；失败时 ROLLBACK |
| `design.md:739` — DDL 中途失败不得留下 current `user_version` + 半初始化 schema | **对齐** | `schema.py:1322-1327` 异常路径 try-ROLLBACK 后 re-raise；测试 `test_fresh_bootstrap_rolls_back_when_ddl_fails` 验证 `user_version==0` 且无表 |
| `design.md:740` — current-version 缺表/缺索引必须 fail closed，不得静默修复 | **对齐** | `schema.py:1273-1275` current 分支只调 `validate_host_durable_schema()`，不执行 DDL；测试覆盖缺表和缺索引 |
| `design.md:741` — 不提供旧库兼容读取或迁移 | **对齐** | `schema.py:1276-1280` 其它版本直接抛 `HostSchemaMismatchError` |
| `design.md:750-751` — WAL checkpoint 不在 hot write path 阻塞执行，失败只进 diagnostic | **对齐** | `maintenance.py` 的 `run_host_wal_checkpoint()` 未被任何 production hot path 调用；失败只返回 error，不改变 EventLog/state truth |
| `design.md:751` — checkpoint 不得成为 EventLog/state/recovery/projection correctness 前置条件 | **对齐** | checkpoint primitive 无调用方；测试 `test_wal_checkpoint_diagnostic_does_not_change_event_log_truth` 明确验证 |
| `design.md:2631` — memory snapshot 与 checkpoint 同一 transaction 提交，checkpoint 不得先于 snapshot 落库 | **对齐** | `write_memory_snapshot_with_checkpoint()` 现有实现已满足；新增测试验证 CAS 失败时 snapshot rollback |

### 与 control doc 验收信号对齐

| WU-DUR-01 验收信号 | 对齐 | 证据 |
|---|---|---|
| 测试模拟 bootstrap DDL 中途失败不留下 current `user_version` | **对齐** | `test_durable_schema.py:346-370` |
| current `user_version` 缺 required table/index 时 opener 不静默补建 | **对齐** | `test_durable_schema.py:376-412` (缺表), `:415-437` (缺索引) |
| WAL checkpoint 行为可观测、可测试、不破坏并发读写 | **对齐** | `test_durable_connection.py:149-176` (可观测), `:215-249` (不改变 truth) |
| read stale 语义有直接测试 | **对齐** | `test_durable_transaction.py:452-500` |

| WU-DUR-02 验收信号 | 对齐 | 证据 |
|---|---|---|
| concurrency matrix 每类场景有明确裁决 | **对齐** | `test_durable_concurrency_matrix.py` module docstring |
| idempotency 同 key 多进程 same/different digest | **对齐** | `test_durable_concurrency_matrix.py:439-503` |
| projection checkpoint lost CAS 有测试 | **对齐** | `test_durable_concurrency_matrix.py:506-538` |
| memory snapshot + checkpoint CAS rollback 有测试 | **对齐** | `test_durable_concurrency_matrix.py:541-593` |
| 并发测试区分 busy、业务冲突、CAS stale 和不可恢复 I/O error | **对齐** | idempotency conflict → `HostIdempotencyConflictError`；projection CAS failure → `HostDurableError("projection checkpoint advance lost CAS race")` |

## Layering / Architecture Check

| 检查项 | 结果 | 证据 |
|---|---|---|
| 无反向依赖（dayu.host 不向上依赖 dayu.service/dayu.ui） | **PASS** | 所有 import 仅依赖 `dayu.host.durable.*`、`dayu.contracts.*`、标准库 |
| `dayu.runtime` 不 import `dayu.host` | **PASS** | 变更不在 runtime 内 |
| Host durable 不向上泄漏实现细节 | **PASS** | `run_host_wal_checkpoint` 不导出到 `dayu.host` 包根；`maintenance.py` module docstring 明确标注 "不是 Service-facing public maintenance API" |
| 无 God object / function / dataclass | **PASS** | `HostWalCheckpointResult` 是 frozen dataclass 只含诊断字段；各 validation 函数职责单一 |
| 无兼容性 re-export / wrapper | **PASS** | `validate_host_schema_version` → `validate_host_durable_schema` 是直接改名+扩展，不是兼容 wrapper；旧名无任何生产代码引用 |
| `hasattr`/`getattr` 无滥用 | **PASS** | 变更代码中无 `hasattr`/`getattr` |

## Concurrency Matrix 完整性

| 场景 | 本轮裁决 | 已有覆盖 | 新增覆盖 |
|---|---|---|---|
| EventLog append 不同 `event_id` 多进程 | closed by evidence | `test_event_log_multiprocess.py:213` | — |
| EventLog append 同 `event_id` 异体并发 | closed by evidence | `test_event_log_multiprocess.py:263` | — |
| ensure_session 同 slot 多进程 | closed by evidence | `test_admission_multiprocess.py:106` | — |
| idempotency 同 key same digest 多进程 | **新增** | — | `test_durable_concurrency_matrix.py:439` |
| idempotency 同 key different digest 多进程 | **新增** | — | `test_durable_concurrency_matrix.py:473` |
| projection checkpoint lost CAS | **新增** | — | `test_durable_concurrency_matrix.py:506` |
| memory snapshot + checkpoint CAS rollback | **新增** | — | `test_durable_concurrency_matrix.py:541` |
| liveness wrong identity / rowcount 0 | closed by evidence | `test_host_instance_liveness.py:463` | — |
| rollback failure | non-goal | — | — |

矩阵闭环完整，没有遗漏项。

## Open Questions

1. **OO-1 (non-blocking)**: 生产代码中是否有路径持有长 read transaction 做 governance decision？plan 要求 "若发现生产路径持有长 read transaction 做 governance decision，停止并报告"。Grep 在 `dayu/host/` 中未发现显式长读事务模式，但未逐路径审查 `run_read()` 调用的持有时间。建议记录为 residual risk 并在 WU-LIFE-01 recovery lifecycle proof 中附带检查。

2. **OO-2 (non-blocking)**: `HOST_DURABLE_INDEXES` 包含 23 个 index。如果后续 schema change 添加或删除 index，是否有流程保证常量同步更新？一致性测试 `test_host_durable_indexes_match_create_index_ddl` 提供了安全网，但 reviewer 和 implementer 需要知道这个一致性测试的存在。已在 `tests/README.md` 中记录 concurrency matrix 文件，但未单独列出 schema consistency 测试。

3. **OO-3 (non-blocking)**: `validate_host_durable_schema()` 校验 "required index 全量存在"，但不校验 index 的 column 组成或 UNIQUE 属性。一个恶意或损坏的 DB 可能拥有同名但不正确的 index。plan 明确这是 deferred to WU-LAYER-01 schema invariant hardening。当前 risk 可接受。

## Residual Risks

| ID | 来源 | 类型 | Severity | 状态 | Owner / Destination | 记录 |
|---|---|---|---|---|---|---|
| RR-DS-01 | HIGH-1 | concurrent fresh bootstrap TOCTOU | LOW (mitigated) | closed | WAL + IF NOT EXISTS 充分缓解 | 两个进程同时 fresh bootstrap 不会损坏数据；DDL IF NOT EXISTS 提供确定性安全。若需要更严格证明，后续可补并发 bootstrap 测试。 |
| RR-DS-02 | HIGH-2 | projection CAS synthetic test vs real race | MEDIUM | deferred-with-owner | WU-LIFE-01 recovery lifecycle proof | 当前 synthetic test 验证了 CAS failure 路径，未验证真实多进程竞态。WU-LIFE-01 的 recovery proof 可能需要更强 checkpoint race 覆盖。 |
| RR-DS-03 | HIGH-3 | WAL checkpoint db_path/connection 一致性 | LOW | deferred-with-owner | 后续 maintenance hardening | 当前调用方（仅测试）不会触发不一致。若后续引入 production maintenance 调用，需要增加一致性 assert。 |
| RR-DS-04 | HIGH-4 | README 单行长句可读性 | LOW | deferred-with-owner | 下一轮 review fix 或附带修改 | 不阻塞正确性，但降低可维护性。 |
| RR-DS-05 | OO-1 | 生产长 read transaction governance scan | LOW | deferred-with-owner | WU-LIFE-01 recovery lifecycle proof | 当前 Grep 未发现显式长读事务模式，但未逐路径审查。 |
| RR-DS-06 | MEDIUM-1 | 单对象错误消息 | LOW | deferred-with-owner | WU-LAYER-01 schema invariant hardening | 批量收集缺失对象后一次性报告。 |

## Verification Commands

以下命令应在合并前补跑确认（若 implement gate 已跑过则无需重复）：

```bash
source .venv/bin/activate

# Schema + connection + transaction tests (Slices 1-2)
pytest tests/host/test_durable_schema.py -q
pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q

# Concurrency matrix (Slice 3)
pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q

# Regression: existing multiprocess + liveness
pytest tests/host/test_event_log_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_host_instance_liveness.py -q

# Full Host test suite as final regression gate
pytest tests/host -q

# Type check
python -m pyright dayu/ tests/ utils/
```

## Review Scope Note

本 review 覆盖 `feat/wu-dur-bootstrap-concurrency` 相对 `main` 的完整 diff（不含 docs/reviews/ 下的历史 artifact）。重点审查了：
- `dayu/host/durable/schema.py` — 全部变更
- `dayu/host/durable/connection.py` — 全部变更
- `dayu/host/durable/maintenance.py` — 全部新增
- `tests/host/test_durable_schema.py` — 全部新增测试
- `tests/host/test_durable_connection.py` — 全部新增测试
- `tests/host/test_durable_transaction.py` — 全部新增测试
- `tests/host/test_durable_concurrency_matrix.py` — 全部新增
- `dayu/host/README.md` — 变更行
- `tests/README.md` — 变更行

未逐行审查：
- `docs/reviews/` 下历史 artifact（非生产代码，已通过对应 gate）
- `docs/host/` 下 plan 文件（plan 已在 plan gate 审查通过）
- `docs/host/host-core-followup-implementation-control.md` 的状态更新行
