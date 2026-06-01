# WU-DUR-01 + WU-DUR-02 PR Review — AgentMiMo

- **Gate**: draft PR review
- **Role**: AgentMiMo
- **PR**: https://github.com/noho/dayu-agent-r/pull/103
- **Branch**: `feat/wu-dur-bootstrap-concurrency` vs `main`
- **Date**: 2026-06-01
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`

## Verdict

**PASS — 可进入 draft-PR-pass。**

PR diff 严格对齐 plan 的 4 个 slice，correctness、stability、maintainability、Host 分层边界均通过独立验证。PR body 准确，gate artifacts 完整，deferred residual risks 分类清晰且有明确 owner。无 blocking findings。

## PR Body 准确性检查

| PR Body 声明 | 实际验证 | 结论 |
|---|---|---|
| tighten Host durable fresh bootstrap so DDL and user_version commit or roll back together | `_bootstrap_fresh_schema()` 使用 `BEGIN IMMEDIATE` / DDL / `PRAGMA user_version` / `COMMIT`，失败时 ROLLBACK | **准确** |
| validate current-version durable schema without silent table or index repair | `bootstrap_host_durable_store()` current 分支只调 `validate_host_durable_schema()`，不执行 DDL | **准确** |
| add internal WAL checkpoint diagnostics and read-stale snapshot proof | `maintenance.py` 新增 `run_host_wal_checkpoint()`；`test_durable_transaction.py` 新增 read stale 测试 | **准确** |
| add durable concurrency matrix coverage for idempotency, projection CAS, and memory snapshot rollback | `test_durable_concurrency_matrix.py` 新增 4 个测试 | **准确** |

## 独立验证结果

### Pyright

```
python -m pyright dayu/host/durable/schema.py dayu/host/durable/connection.py dayu/host/durable/maintenance.py → 0 errors
python -m pyright tests/host/test_durable_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_durable_concurrency_matrix.py → 0 errors
```

### Tests

```
pytest tests/host/test_durable_schema.py -q → 28 passed
pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q → 22 passed
pytest tests/host/test_durable_concurrency_matrix.py -q → 4 passed
pytest tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q → 77 passed
pytest tests/host/test_event_log_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_host_instance_liveness.py -q → 27 passed
```

总计 158 tests passed，0 failed。

## Changed Files Summary

### Production changes (4 files, ~+278/-18)

| 文件 | 变更 | 评估 |
|---|---|---|
| `dayu/host/durable/schema.py` | `HOST_DURABLE_INDEXES` 常量、`_bootstrap_fresh_schema()` 事务化、`validate_host_durable_schema()` 全结构校验、`_validate_required_tables()` / `_validate_required_indexes()` | 正确：fresh 分支事务化保证原子性；current 分支只校验不修复；mismatch 分支 fail closed |
| `dayu/host/durable/connection.py` | 删除 `open_host_durable_store` 中冗余 post-bootstrap validation；secondary path 使用 `validate_host_durable_schema` | 正确：避免 primary opener 双重 full validation；secondary path 只校验不 bootstrap |
| `dayu/host/durable/maintenance.py` | 新增 `run_host_wal_checkpoint()` 及诊断类型 | 正确：纯 diagnostic，不导出到 `dayu.host`，不被任何生产热路径调用 |
| `dayu/host/README.md` | durable foundation bullet 拆分为 6 个子项 | 正确：内容与代码一致，提及 secondary connection validation |

### Test changes (5 files, ~+1240/+0)

| 文件 | 变更 | 评估 |
|---|---|---|
| `tests/host/test_durable_schema.py` | +232: bootstrap rollback、missing table/index、secondary validation、DDL↔constant 一致性 | 覆盖完整，28 tests |
| `tests/host/test_durable_connection.py` | +238: WAL checkpoint observable fields、closed connection、stat failure、truth unchanged | 覆盖完整 |
| `tests/host/test_durable_transaction.py` | +133: read stale snapshot proof | 覆盖 snapshot 隔离语义和 fresh truth |
| `tests/host/test_durable_concurrency_matrix.py` | +835: idempotency 多进程、projection lost CAS、memory CAS rollback | 4 tests，覆盖 plan 矩阵全部新增项 |
| `tests/README.md` | +6/-1: 更新测试命令与 concurrency matrix 描述 | 与代码一致 |

### Gate artifacts

40+ review/planning/implementation artifacts under `docs/reviews/` and `docs/host/`。全部为 gate 产物，非生产代码。

## Findings (按严重性排序)

### F1 — INFO: `_validate_required_tables` / `_validate_required_indexes` 只报第一个缺失对象

- **严重性**: INFO (不阻塞)
- **文件**: `dayu/host/durable/schema.py:1341-1371`
- **证据**: 两个函数在 `for` 循环中第一个缺失对象处即 `raise`，不收集全部缺失对象后一次性报告
- **评估**: 当前 fail-closed 行为满足 WU-DUR 验收信号。批量诊断属于运维可读性增强，已在 plan 中明确 deferred 到 WU-LAYER-01。aggregate deepreview DS 的 MEDIUM-1 和 controller adjudication 均已裁决为 deferred-with-owner
- **结论**: 不修，deferred 到 WU-LAYER-01

### F2 — INFO: `_bootstrap_fresh_schema` 读取 `user_version` 在 `BEGIN IMMEDIATE` 之外

- **严重性**: INFO (设计意图正确)
- **文件**: `dayu/host/durable/schema.py:1268-1270`
- **证据**: `bootstrap_host_durable_store()` 在显式事务外读取 `_read_user_version(connection)` 判断分支，然后 `_bootstrap_fresh_schema()` 在内部执行 `BEGIN IMMEDIATE`
- **评估**: 这是 plan 中的明确设计。WAL 模式下 `BEGIN IMMEDIATE` 确保同一时刻只有一个 writer；DDL 中的 `IF NOT EXISTS` 防御 TOCTOU 窗口。aggregate deepreview DS 的 HIGH-1 和 controller adjudication 均已裁决为 closed by existing design
- **结论**: 不修，已由 WAL + IF NOT EXISTS 充分缓解

### F3 — INFO: WAL checkpoint `db_path` / `connection` 无一致性校验

- **严重性**: INFO (当前调用方安全)
- **文件**: `dayu/host/durable/maintenance.py:51-93`
- **证据**: `run_host_wal_checkpoint()` 独立接收 `connection` 和 `db_path`，不验证两者是否指向同一 DB
- **评估**: 当前唯一调用方是测试代码，传入同一 store 的 connection/path pair，必然一致。aggregate deepreview DS 的 HIGH-3 和 controller adjudication 均已裁决为 deferred-with-owner（后续 Host maintenance hardening）
- **结论**: 不修，deferred 到后续 maintenance hardening

### F4 — INFO: `HOST_DURABLE_DDL` 保留 `CREATE ... IF NOT EXISTS`

- **严重性**: INFO (设计意图正确)
- **文件**: `dayu/host/durable/schema.py` DDL statements
- **证据**: DDL 语句保留 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
- **评估**: plan 已明确裁决：fresh branch 是唯一执行 DDL 的路径，current branch 不执行 DDL。`IF NOT EXISTS` 是 fresh bootstrap 的安全阀，不影响 current-version 行为。aggregate deepreview MiMo 的 F2 已裁决为无需修改
- **结论**: 不修

## Correctness 验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| fresh bootstrap DDL + `user_version` 在同一事务 | **PASS** | `_bootstrap_fresh_schema()` 使用 `BEGIN IMMEDIATE` / DDL / `PRAGMA user_version` / `COMMIT` |
| DDL 中途失败 rollback 不留 partial schema | **PASS** | `test_fresh_bootstrap_rolls_back_when_ddl_fails` 验证 `user_version == 0` 且无用户表 |
| current-version 缺 table opener fail closed | **PASS** | `test_current_schema_missing_table_opener_raises_without_repair` |
| current-version 缺 index opener fail closed | **PASS** | `test_current_schema_missing_index_opener_raises_without_repair` |
| secondary connection 缺 table/index fail closed | **PASS** | `test_secondary_connection_missing_table_raises_without_repair` / `test_secondary_connection_missing_index_raises_without_repair` |
| `HOST_DURABLE_INDEXES` 与 DDL 同源 | **PASS** | `test_host_durable_indexes_match_create_index_ddl` |
| `HOST_DURABLE_TABLES` 与 DDL 同源 | **PASS** | `test_host_durable_tables_match_create_table_ddl` |
| WAL checkpoint 诊断字段可观测 | **PASS** | `test_wal_checkpoint_passive_result_fields_are_observable` |
| WAL checkpoint 不改变 EventLog truth | **PASS** | `test_wal_checkpoint_diagnostic_does_not_change_event_log_truth` |
| read stale snapshot 同事务保持旧快照 | **PASS** | `test_read_transaction_keeps_stale_snapshot_until_commit` |
| 新短读事务看到 fresh truth | **PASS** | 同上测试断言 `fresh_count == 2` |
| idempotency 同 key/same digest 多进程共享 winner | **PASS** | `test_idempotency_same_scope_key_same_digest_multiprocess_shares_winner` |
| idempotency 同 key/different digest 多进程只有一个 winner | **PASS** | `test_idempotency_same_scope_key_different_digest_multiprocess_conflicts` |
| projection checkpoint lost CAS 不推进 persisted checkpoint | **PASS** | `test_projection_checkpoint_lost_cas_keeps_persisted_checkpoint` |
| memory snapshot + checkpoint CAS failure rollback snapshot | **PASS** | `test_memory_snapshot_checkpoint_lost_cas_rolls_back_snapshot` |

## Host 分层边界验证

| 检查项 | 结果 | 证据 |
|---|---|---|
| `maintenance.py` 不导出到 `dayu.host` 包根 | **PASS** | `grep maintenance dayu/host/__init__.py` → not found |
| `maintenance.py` 模块 docstring 声明非 public API | **PASS** | "不是 Service-facing public maintenance API" |
| `_bootstrap_fresh_schema()` 是唯一执行 DDL 的路径 | **PASS** | current 分支不遍历 `HOST_DURABLE_DDL` |
| secondary connection path 不 bootstrap、不执行 DDL | **PASS** | `_open_configured_connection()` 只调 `validate_host_durable_schema()` |
| 无反向依赖 | **PASS** | 所有 import 仅依赖 `dayu.host.durable.*`、`dayu.contracts.*`、标准库 |
| 无兼容性 wrapper / facade | **PASS** | `validate_host_schema_version` → `validate_host_durable_schema` 是直接改名+扩展 |

## README 同步验证

| README | 触发条件 | 变更 | 评估 |
|---|---|---|---|
| `dayu/host/README.md` | `dayu/host/` 修改 | durable foundation bullet 拆分为 6 子项，新增 read snapshot / WAL checkpoint / secondary validation 说明 | **正确**：内容与代码一致 |
| `tests/README.md` | `tests/` 修改 | 新增 `test_durable_concurrency_matrix.py` 相关测试命令 | **正确**：覆盖新增测试文件 |
| 根目录 `README.md` | CLI/render/config 变化 | 无变更 | **正确**：不触发 |
| `dayu/README.md` | 分层关系变化 | 无变更 | **正确**：不触发 |

## Deferred Residual Risks

| ID | 风险 | Owner / Destination |
|---|---|---|
| RR-DUR-01 | projection checkpoint 真实多进程 CAS race 证明 | WU-LIFE-01 recovery lifecycle proof |
| RR-DUR-02 | WAL checkpoint connection/db_path 一致性校验 | future Host maintenance hardening |
| RR-DUR-03 | schema validation 批量缺失对象诊断 | WU-LAYER-01 schema invariant hardening |
| RR-DUR-04 | production long read transaction governance scan | WU-LIFE-01 recovery lifecycle proof |
| RR-DUR-05 | index definition / DDL text invariant validation | WU-LAYER-01 schema invariant hardening |

所有 deferred risks 均有明确 owner 和 destination，且已在 control doc 中记录。

## Gate Artifacts 完整性

| Gate | Artifacts | 评估 |
|---|---|---|
| Plan | `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md` | 462 行，覆盖全量实施决策 |
| Plan review | MiMo + DS + controller adjudication + fix + re-review | 6 artifacts |
| Implementation | Slice 1-4 implementation artifacts | 4 artifacts |
| Code review | Slice 1-4 MiMo + DS review + controller adjudication + fix + re-review | 20+ artifacts |
| Aggregate deepreview | MiMo + DS + controller adjudication + fix + re-review | 5 artifacts |
| Discussion | code inspection | 1 artifact |

Gate 流程完整：plan → plan review → plan fix → plan re-review → implementation (4 slices) → code review (4 slices) → fix → re-review → aggregate deepreview → aggregate fix → aggregate re-review → PR review。

## Open Questions

none。

所有 plan 中的 blocking open questions 已在实现中关闭。deferred items 均有明确 owner。

## 结论

**PASS — 可进入 draft-PR-pass。**

PR 实现严格对齐 plan，correctness 通过 158 个测试验证，pyright 零报错，Host 分层边界无违规，README 同步正确，PR body 准确，gate artifacts 完整。4 个 INFO findings 均为设计意图或 deferred items，不阻塞合并。
