# WU-CM-09 Durable Memory Snapshot Corruption Policy Plan

## Preflight

GitHub Issue #41 当前为 OPEN，原状态是 deferred behind #81。#81 已关闭，用户指定恢复推进，因此前置条件解除。

动机成立，但严重性边界需要收窄：当前代码已经对普通运行路径 fail closed。`read_memory_snapshot(...)`、`read_latest_memory_snapshot(...)` 和 `read_latest_memory_snapshot_at_or_before(...)` 会解析 snapshot JSON、恢复 typed snapshot、校验 digest、校验 durable item kind；`RunInputBuilder` 读到缺失或损坏 snapshot 时转成 `MemoryProjectionRepairRequired`，不改写 Run / Attempt / EventLog；projection catch-up 遇到损坏 snapshot 会留下 projection failure row 并记录 warning。因此本 WU 不是修复静默吞错，也不是让 snapshot 成为 truth。

真实缺口是 operator-facing corruption policy 不完整：损坏 row 的来源分类、诊断入口和可审计报告还没有稳定 typed surface。Issue #41 的 acceptance signals 要求覆盖 invalid JSON、schema-mismatched JSON、digest mismatch、unsupported item kind、manual corruption 和 storage-read failure classification；这些不能靠泛化 `HostDurableError("memory snapshot JSON is invalid")` 满足。

## Design Boundary

- Host design source: `docs/host/design.md` § Conversation Memory / Context Governance。
- Engine design source: `docs/engine/design.md` 无需修改；Engine 不拥有 memory snapshot。
- memory snapshot 仍是 EventLog 派生 read model，可重建、可修复，不是 Host durable truth。
- `run_storage_maintenance(...)` 是已有 operator-facing 显式 maintenance 入口。第一版最小实现把 memory snapshot integrity classification 挂到该入口的 dry-run/report 结果里，不删除 SQLite row，不 quarantine，不 rebuild，不 overwrite。
- classification 只暴露 operator 可读的损坏类别、snapshot row identity 和短错误摘要，不暴露 snapshot JSON、prompt、tool payload 或大内容。

## Non-Goals

- 不自动覆盖 damaged snapshot row。
- 不新增兼容旧 corrupt payload 的 reader。
- 不新增 quarantine 表，除非 plan review 证明没有它无法满足当前 acceptance。
- 不让 command path 静默触发 rebuild / overwrite。
- 不改 Engine。
- 不把 memory snapshot 变成 recovery truth。

## Implementation Slices

### S1: Durable Integrity Classifier

Files:

- `dayu/host/durable/memory.py`
- `tests/host/test_memory_projection.py`

Changes:

- 在 `dayu.host.durable.memory` 内新增 Host durable-owned typed enum/dataclass，避免 durable 层反向 import Host 上层模块：
  - `MemorySnapshotIntegrityFailureKind`
  - `MemorySnapshotIntegrityIssue`
- 在 `dayu.host.durable.memory` 新增 read-only classifier，例如 `inspect_memory_snapshot_integrity(transaction) -> tuple[MemorySnapshotIntegrityIssue, ...]`。
- classifier 扫描 `host_memory_snapshots`，逐 row 分类：
  - `invalid_json`: `snapshot_json` 不是合法 JSON。
  - `schema_mismatch`: JSON 合法但不符合 `ConversationMemorySnapshotVNext` typed shape。
  - `digest_mismatch`: typed snapshot 可恢复但 canonical digest 不匹配。
  - `unsupported_item_kind`: snapshot 关联 `host_memory_items.item_kind` 是旧 `verified_fact` 或未知 kind。
  - `storage_read_failed`: snapshot scan query、row identity 读取或字段恢复过程中出现不能归入前述类别的 durable 读取错误。
- Issue #41 的 `manual corruption` 不作为独立 failure kind；手动 SQL 修改 durable row 导致的损坏会被 `invalid_json`、`schema_mismatch`、`digest_mismatch`、`unsupported_item_kind` 或 `storage_read_failed` 捕获。
- classifier 不抛出单个 row 的损坏错误；它返回 issue tuple。若 snapshot scan query 自身失败，也返回一个 `storage_read_failed` issue，且 `snapshot_id` / `session_id` 等 row identity 字段为 `None`。
- 现有 `read_*memory_snapshot*` fail-closed 行为保持不变。
- 第一版执行全 DB scan，不按 session 过滤；这是 operator maintenance report 的有意选择，不进入 command hot path。
- `unsupported_item_kind` 主要防御旧数据、手工 DB 修改和新代码 bug；当前 DDL 正常写入路径不会产生旧 `verified_fact` item kind。
- 测试组织：classifier tests 追加到 `tests/host/test_memory_projection.py`，函数名使用 `test_memory_snapshot_integrity_...` 前缀，避免与 projection materialization 语义混杂。
- 最小测试矩阵：empty DB、valid snapshot returns no issues、invalid JSON、schema mismatch、digest mismatch、unsupported old `verified_fact` item kind、manual SQL corruption mapped to digest mismatch、mixed damaged rows、storage read failure。

Validation:

- Baseline before edits: `pytest tests/host/test_memory_projection.py -q`
- `pytest tests/host/test_memory_projection.py -q`
- `python -m pyright dayu/ tests/ utils/`

### S2: Operator-Facing Maintenance Report

Files:

- `dayu/host/storage_maintenance.py`
- `dayu/host/open_host.py` and `dayu/host/api.py` only if type exports require docstring/type updates
- `dayu/host/__init__.py`
- `tests/host/test_storage_maintenance.py`
- `tests/host/test_package_exports.py`

Changes:

- Extend `HostStorageMaintenanceResult` with `memory_snapshot_integrity_issues: tuple[MemorySnapshotIntegrityIssue, ...]`.
- `run_storage_maintenance(...)` reads classifier output in the same read state as usage report and artifact refs.
- Extend `HostStorageMaintenanceResult.__post_init__` with tuple-of-`MemorySnapshotIntegrityIssue` validation.
- `json_value()` includes `"memory_snapshot_integrity_issues"` as self-explaining JSON objects.
- Root exports include the public diagnostic type if it appears in the public result surface.
- Tests cover:
  - valid DB returns empty integrity issue tuple.
  - invalid JSON classification.
  - schema mismatch classification.
  - digest mismatch classification via manual SQL corruption.
  - unsupported old `verified_fact` item kind classification.
  - storage-read failure classification by monkeypatching the classifier's module-private snapshot row reader helper to raise `sqlite3.OperationalError`; production corruption semantics remain unchanged.
  - json output key set and non-negative/stable fields.

Validation:

- Baseline before edits: `pytest tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q`
- `pytest tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q`
- `python -m pyright dayu/ tests/ utils/`

### S3: Design / README / Control Closure

Files:

- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`

Changes:

- `docs/host/design.md`: document policy that corrupt snapshot classification is read-only operator maintenance output; automatic overwrite/quarantine is not introduced in this WU.
- `dayu/host/README.md`: because `dayu/host/` public maintenance result changes, update current implemented Host developer contract.
- `tests/README.md`: because tests add memory snapshot integrity maintenance coverage, update Host tests coverage paragraph only if the existing coverage summary becomes stale.
- Update control doc with slice commits, review artifacts, validation and residual risks.

Validation:

- Baseline before edits: `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q`
- `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q`
- `python -m pyright dayu/ tests/ utils/`
- `git diff --check`

## Review Checklist

- Does this preserve EventLog as truth and snapshot as read model?
- Does any command path silently rebuild or overwrite a corrupt snapshot? It must not.
- Are corruption classes derived from direct parse/digest/item-kind evidence rather than indirect symptoms?
- Does operator-facing JSON avoid large payload leakage?
- Does the public result extension require root/API export updates?
- Are README updates limited to current implemented behavior?
