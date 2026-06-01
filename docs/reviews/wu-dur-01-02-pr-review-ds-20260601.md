# WU-DUR-01 + WU-DUR-02 Draft PR Review — AgentDS

- **Gate**: draft PR gate
- **Role**: AgentDS
- **PR**: https://github.com/noho/dayu-agent-r/pull/103
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Base**: `main`
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Date**: 2026-06-01

## Verdict

**PASS — draft-PR-pass. 无 blocking findings.**

PR diff 相对 main 的 4 个生产文件变更和 4 个测试文件变更均对齐 plan，aggregate deepreview controller adjudication 的 3 个 doc-only fix（AGG-DOC-1/2/3）均已完成。所有 deferred residual risks 在 control doc 中有明确 owner 和 destination。158 个受影响测试全部通过，pyright 零报错。无 layering 违规、无 public API 变更、无未记录的行为改动。

## Review Scope

本 review 覆盖 `feat/wu-dur-bootstrap-concurrency` 相对 `main` 的完整 diff（共 49 文件，+4940/-41 行），重点审查：

- `dayu/host/durable/schema.py` — bootstrap 事务化、current-schema validation、required index 校验
- `dayu/host/durable/connection.py` — 删除重复 validation、secondary path 使用 full validation
- `dayu/host/durable/maintenance.py` — 新增 WAL checkpoint diagnostic primitive
- `dayu/host/README.md` — durable foundation 说明更新
- `tests/host/test_durable_schema.py` — bootstrap rollback、missing table/index、secondary validation、DDL↔constant 一致性
- `tests/host/test_durable_connection.py` — WAL checkpoint 可观测性、closed connection、stat failure、truth unchanged
- `tests/host/test_durable_transaction.py` — read stale snapshot proof
- `tests/host/test_durable_concurrency_matrix.py` — idempotency 多进程、projection lost CAS、memory CAS rollback
- `tests/README.md` — 测试命令拆分与 concurrency matrix 描述
- `docs/host/host-core-followup-implementation-control.md` — 状态更新与 residual risks 登记

不逐行审查 `docs/reviews/` 下历史 gate artifact（已在对应 gate 审查通过）。

## Plan Alignment

| Plan 要求 | 代码对齐 | 证据 |
|---|---|---|
| fresh bootstrap DDL + `user_version` 同事务同成同败 | **对齐** | `schema.py:1307-1327` `_bootstrap_fresh_schema()` 显式 `BEGIN IMMEDIATE` → DDL → `PRAGMA user_version` → `COMMIT`；失败时 best-effort `ROLLBACK` |
| current-version 缺 required table/index 时 fail closed | **对齐** | `schema.py:1273-1275` current 分支只调 `validate_host_durable_schema()`，不执行 DDL |
| `bootstrap_host_durable_store()` 是 schema dispatch + final validation owner | **对齐** | `schema.py:1268-1283` fresh branch 执行 bootstrap 后 validate；current branch 只 validate；mismatch branch 抛错 |
| primary opener 不重复 full validation | **对齐** | `connection.py:162` 删除了 bootstrap 后的 `validate_host_schema_version()` 调用 |
| secondary connection 只 validation，不 bootstrap，不执行 DDL | **对齐** | `connection.py:185` `_open_configured_connection()` 改为调用 `validate_host_durable_schema()` |
| WAL checkpoint 为纯 diagnostic，不接入 hot path | **对齐** | `maintenance.py` 的 `run_host_wal_checkpoint()` 未被任何 production hot path 调用 |
| WAL checkpoint 不作为 EventLog/state correctness 前置条件 | **对齐** | 测试 `test_wal_checkpoint_diagnostic_does_not_change_event_log_truth` 明确验证 |
| read stale snapshot 有直接测试 | **对齐** | `test_durable_transaction.py:450-516` 两个独立 connection 验证 snapshot 稳定性 |
| concurrency matrix 缺口补齐 | **对齐** | `test_durable_concurrency_matrix.py` module docstring 列出 closed-by-evidence 项和新增项 |
| idempotency 同 key 多进程 same/different digest | **对齐** | `test_durable_concurrency_matrix.py:439-503` |
| projection checkpoint lost CAS | **对齐** | `test_durable_concurrency_matrix.py:506-538` |
| memory snapshot + checkpoint CAS rollback | **对齐** | `test_durable_concurrency_matrix.py:541-593` |
| 不修改 public API、不新增 scheduler、不 bump schema version | **对齐** | 全部变更在 `dayu.host.durable` 内部 |

## Aggregate Deepreview Remedial Action Verification

Controller adjudication（`docs/reviews/wu-dur-01-02-aggregate-controller-adjudication-20260601.md`）要求的 3 个 doc-only fix 验证如下：

### AGG-DOC-1: Host README durable bullet 可读性

- **要求**: 拆分长 bullet，明确 secondary durable connections 也执行 full schema validation
- **实际**: `dayu/host/README.md:291-298` 已拆分为 6 条子 bullet，子项 2 明确写入"主连接与 secondary durable connections 都会执行完整当前 schema validation"
- **结论**: **PASS**

### AGG-DOC-2: Fresh bootstrap docstring 前置条件

- **要求**: `_bootstrap_fresh_schema()` docstring 声明 connection 需处于 autocommit 模式（`isolation_level=None`）
- **实际**: `schema.py:1320-1321` docstring `:param connection:` 已更新为"已完成 PRAGMA setup 且处于 autocommit 模式（``isolation_level=None``）的 SQLite connection；本函数会自行开启 ``BEGIN IMMEDIATE`` 显式事务"
- **结论**: **PASS**，docstring 与实现（`schema.py:1332` `connection.execute("BEGIN IMMEDIATE")`）一致

### AGG-DOC-3: WAL size missing-file diagnostic 措辞

- **要求**: `_read_wal_size_bytes()` docstring 说明 WAL 文件不存在时返回 `0`，覆盖不存在与被 SQLite 清理两种情况
- **实际**: `maintenance.py:188` `:returns:` 已更新为"WAL 文件不存在或已被 SQLite 清理时返回 ``0``"
- **结论**: **PASS**，docstring 与实现（`maintenance.py:195-196` `except FileNotFoundError: return 0`）语义一致

## Deferred Residual Risks

Control doc（`docs/host/host-core-followup-implementation-control.md:176-180`）已登记 5 个 deferred residual risks：

| ID | 内容 | Owner / Destination | 评估 |
|---|---|---|---|
| RR-DUR-01 | projection checkpoint 真实多进程 CAS race 证明 | WU-LIFE-01 recovery lifecycle proof | 合理 defer；synthetic test 已验证 CAS failure 路径 |
| RR-DUR-02 | WAL checkpoint connection/db_path 一致性校验 | future Host maintenance hardening | 合理 defer；当前无 production caller |
| RR-DUR-03 | schema validation 批量缺失对象诊断 | WU-LAYER-01 schema invariant hardening | 合理 defer；fail-closed 行为满足验收信号 |
| RR-DUR-04 | production long read transaction governance scan | WU-LIFE-01 recovery lifecycle proof | 合理 defer；当前未发现治理误用 |
| RR-DUR-05 | index definition / DDL text invariant validation | WU-LAYER-01 schema invariant hardening | 合理 defer；plan 明确 scope 外 |

所有 residual risks 均有明确 owner 和 destination work unit，不影响 draft-PR-pass。

## Findings

### MEDIUM-1: PR body validation commands 存在冗余条目

- **Severity**: MEDIUM
- **Category**: Documentation / PR body accuracy
- **Evidence**: PR body Validation 节列出 6 条 pytest 命令，其中 `pytest tests/host/test_durable_schema.py -q` 与 `pytest tests/host/test_durable_schema.py tests/host/test_durable_connection.py -q` 存在重复覆盖
- **Root cause**: Validation 命令列表中第 1 条和第 5 条有交集（`test_durable_schema.py` 被运行两次），是编辑残留
- **Recommendation**: 清理重复命令条目，将 validation 命令整理为与 plan 一致的 4 条核心命令。不阻塞 draft-PR-pass，可在下一轮 fix 或 squash merge 前修正

### LOW-1: 测试 helper `_event_request()` / `_append_event()` / `_count_event_log_rows()` 在两个文件中重复定义

- **Severity**: LOW
- **Category**: Maintainability
- **Evidence**: `test_durable_connection.py:67-106` 和 `test_durable_transaction.py:108-158` 定义了语义完全相同的三个 helper 函数
- **Root cause**: Slice 2 实现时两个测试文件独立实现各自的 EventLog helper，未抽取公共 helper
- **Recommendation**: 后续 test-maintenance cleanup 可抽取到 `tests/host/conftest.py`。已在 aggregate deepreview 中记录为 deferred，不阻塞本轮。不影响生产正确性

### LOW-2: `bootstrap_host_durable_store` 中 `user_version` 读取在事务外

- **Severity**: LOW（已在 aggregate deepreview HIGH-1 中裁决为 mitigated）
- **Category**: Correctness / TOCTOU
- **Evidence**: `schema.py:1268` 在显式事务外读取 `_read_user_version(connection)`，然后 `schema.py:1270` 调用 `_bootstrap_fresh_schema()` 内部执行 `BEGIN IMMEDIATE`
- **Root cause**: 读取和 `BEGIN IMMEDIATE` 不在同一原子边界内。两个并发 opener 可能同时读到 `user_version=0`
- **Mitigation**: WAL 模式下 `BEGIN IMMEDIATE` 确保同一时刻只有一个 writer；DDL 保留 `IF NOT EXISTS` 使第二个事务的 DDL 成为安全 no-op。不存在数据损坏或半初始化风险
- **Recommendation**: 不修改。已在 aggregate controller adjudication 中 closed by existing design。若后续需要更严格证明，可增加并发 fresh bootstrap 直接测试

## Design Source Alignment

| 设计真源要求 | 对齐 | 证据 |
|---|---|---|
| `design.md:738` — fresh bootstrap DDL 与 `user_version` 同成同败 | **对齐** | `schema.py:1322-1327` 异常路径 try-ROLLBACK 后 re-raise |
| `design.md:739` — DDL 中途失败不得留下 partial schema | **对齐** | 测试验证 `user_version==0` 且无表残留 |
| `design.md:740` — current-version 缺结构 fail closed | **对齐** | `schema.py:1273-1275` 不执行 DDL |
| `design.md:741` — 不提供旧库兼容 | **对齐** | `schema.py:1276-1280` mismatch 直接抛错 |
| `design.md:750-751` — WAL checkpoint 不在 hot path 阻塞 | **对齐** | 无 production caller |
| `design.md:751` — checkpoint 不是 correctness 前置条件 | **对齐** | 测试明确验证 truth unchanged |

## Layering / Architecture Check

| 检查项 | 结果 |
|---|---|
| 无反向依赖（dayu.host 不向上依赖） | **PASS** |
| `dayu.runtime` 无变更 | **PASS** |
| Host durable 不向上泄漏实现细节 | **PASS** — `run_host_wal_checkpoint` 不导出到 `dayu.host` 包根 |
| 无 God object / function | **PASS** — `HostWalCheckpointResult` 为 frozen dataclass，validation 函数职责单一 |
| 无兼容性 re-export / wrapper | **PASS** — `validate_host_schema_version` → `validate_host_durable_schema` 是直接 rename+extension |
| `hasattr`/`getattr` 无滥用 | **PASS** — 变更代码中无 `hasattr`/`getattr` |
| 无魔法数字/字符串 | **PASS** — 所有常量均模块级命名 |
| 中文 docstring 完整 | **PASS** — 所有新增函数/类/模块有完整中文 docstring |
| 类型标注完整 | **PASS** — 无 `Any`/`object`/无类型签名 |

## Test Suite Verification

所有受影响测试独立运行通过：

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_durable_schema.py -q` | 28 passed |
| `pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q` | 22 passed |
| `pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q` | 81 passed |
| `pytest tests/host/test_event_log_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_host_instance_liveness.py -q` | 27 passed |

**总计: 158 passed, 0 failed.**

Pyright: `0 errors, 0 warnings, 0 informations`

## PR Body Accuracy

| 字段 | 评估 |
|---|---|
| Title: "Host durable bootstrap and concurrency hardening" | **准确** — 覆盖 WU-DUR-01（bootstrap）和 WU-DUR-02（concurrency） |
| Summary bullet 1: bootstrap DDL + user_version commit/rollback | **准确** |
| Summary bullet 2: current-version validation without silent repair | **准确** |
| Summary bullet 3: WAL checkpoint diagnostics + read-stale proof | **准确** |
| Summary bullet 4: concurrency matrix coverage | **准确** |
| Gate artifacts listing | **准确** — 列出 4 个关键 aggregate gate artifact |
| Validation commands | **基本准确** — 存在 MEDIUM-1 冗余条目，不影响正确性 |

## Concurrency Matrix 完整性

| 场景 | 状态 | 覆盖 |
|---|---|---|
| EventLog append 不同 `event_id` 多进程 | closed by evidence | `test_event_log_multiprocess.py:213` |
| EventLog append 同 `event_id` 异体并发 | closed by evidence | `test_event_log_multiprocess.py:263` |
| ensure_session 同 slot 多进程 | closed by evidence | `test_admission_multiprocess.py:106` |
| idempotency 同 key same digest 多进程 | **新增** | `test_durable_concurrency_matrix.py:439` |
| idempotency 同 key different digest 多进程 | **新增** | `test_durable_concurrency_matrix.py:473` |
| projection checkpoint lost CAS | **新增** | `test_durable_concurrency_matrix.py:506` |
| memory snapshot + checkpoint CAS rollback | **新增** | `test_durable_concurrency_matrix.py:541` |
| liveness wrong identity / rowcount 0 | closed by evidence | `test_host_instance_liveness.py:463` |
| rollback failure | non-goal | — |

矩阵闭环完整，无遗漏。

## Open Questions

1. **OO-PR-1 (non-blocking)**: control doc gate 状态已更新为 `ready-to-open-draft-PR`，PR 已打开。PR body gate artifacts 只列出 4 个 aggregate-level artifact，但完整 gate trail 包含 38 个 review/fix artifact。建议保持 PR body 简洁（当前做法合理），不需要列出所有 artifact。

2. **OO-PR-2 (non-blocking)**: `tests/host/test_durable_concurrency_matrix.py` 中 idempotency worker 在 `HostIdempotencyConflictError` 以外异常时会 crash 进程（exitcode != 0），这是正确的测试行为。但如果未来引入新的 conflict 子类型（如 `HostDurableError` 子类），需同时更新 worker 的 except 子句。当前 risk 低，因为冲突分类已稳定。

## Required Actions Before Merge

无。draft-PR-pass，可进入下一 gate（user merge decision）。

MEDIUM-1（PR body 冗余命令）可在 squash merge 前附带修正，不要求独立 fix/re-review 轮次。
