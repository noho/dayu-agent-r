# WU-DUR-01-02 Plan Fix - Codex

## Gate

- **Gate**: plan fix
- **Role**: planning fix specialist
- **Work unit**: WU-DUR-01 + WU-DUR-02
- **Plan fixed**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Controller adjudication**: `docs/reviews/wu-dur-01-02-plan-controller-adjudication-20260601.md`
- **Review artifacts**:
  - `docs/reviews/wu-dur-01-02-plan-review-mimo-20260601.md`
  - `docs/reviews/wu-dur-01-02-plan-review-ds-20260601.md`

## Scope Boundary

本次只修 controller accepted plan findings / suggestions，不做 implementation，不改 source、tests、README、design、control，不提交、不 push、不创建 PR。

## Per-finding Fix Status

### MIMO-P1-已修复-bootstrap 分支条件与 current-version DDL 路径的边界

- **Controller decision**: accepted
- **Fix status**: 已修复
- **Plan changes**:
  - 明确 `_bootstrap_fresh_schema(connection)` 是唯一允许执行 `HOST_DURABLE_DDL` 的路径。
  - 明确 `bootstrap_host_durable_store()` 不得在该 helper 外遍历或执行 `HOST_DURABLE_DDL`。
  - 明确 `user_version == HOST_SCHEMA_VERSION` 分支只调用 `validate_host_durable_schema(connection)`，直接跳过 DDL loop，不做 repair。

### MIMO-P2-已修复-`_open_configured_connection()` 的 validate 调用升级

- **Controller decision**: accepted
- **Fix status**: 已修复
- **Plan changes**:
  - 明确 `_open_configured_connection()` / `HostDurableStore.connect()` 是 secondary connection validation-only 路径。
  - 明确该路径只做 parent 准备、raw connection、PRAGMA setup 和 full schema validation。
  - 明确该路径不得调用 bootstrap、不得调用 `_bootstrap_fresh_schema()`、不得执行任何 DDL。
  - Slice 1 增加 `store.connect()` 缺表或缺索引 fail closed 且不重建对象的测试要求。

### MIMO-P3-已修复-`HOST_DURABLE_INDEXES` 来源的完整性保证

- **Controller decision**: accepted with DS-P1
- **Fix status**: 已修复
- **Plan changes**:
  - 明确 `HOST_DURABLE_INDEXES` 必须包含 `schema.py` 中全部已有 `INDEX_*` durable index name constants。
  - 在 plan 中列出当前全部 durable index name constants。
  - Slice 1 增加 consistency test：解析 `HOST_DURABLE_DDL` 中 `CREATE INDEX` / `CREATE UNIQUE INDEX` 的 index name 集合，并断言等于 `set(HOST_DURABLE_INDEXES)`。

### DS-P1-已修复-`HOST_DURABLE_INDEXES` 构造方式未指定

- **Controller decision**: accepted with MIMO-P3
- **Fix status**: 已修复
- **Plan changes**:
  - 同 MIMO-P3，明确不得只选择核心索引子集，必须覆盖全部已有 `INDEX_*` durable index name constants。
  - 将完整性保证落到 Slice 1 exact changes 和测试验证点。

### MIMO-P4-已修复-WAL checkpoint busy diagnostic 测试的确定性

- **Controller decision**: accepted
- **Fix status**: 已修复
- **Plan changes**:
  - 明确 WAL checkpoint busy 测试目标是 diagnostic-field observability，不要求稳定制造 `busy_pages > 0`。
  - 明确 live SQLite PASSIVE checkpoint 断言只要求字段合法、diagnostic 可观测、truth 不依赖 checkpoint success。
  - 明确只有在不 over-mock SQLite transaction、WAL、locking、checkpoint correctness 或 retry behavior 的前提下，才可增加 unit-level synthetic `busy_pages > 0` coverage。

### DS-NBS-1-已修复-open_host_durable_store 双重 validation 调用

- **Controller decision**: accepted
- **Fix status**: 已修复
- **Plan changes**:
  - 选择并写入清晰 owner 方案：`bootstrap_host_durable_store()` 是 primary opener 的 schema dispatch + final validation owner。
  - `open_host_durable_store()` 只做 parent 准备、raw connection、PRAGMA setup、调用 bootstrap，不在 bootstrap 返回后再次 full validation。
  - fresh 分支在 `_bootstrap_fresh_schema()` 后 validate，current 分支只 validate，mismatch 分支抛错。

### DS-NBS-2-已修复-`_open_configured_connection()` 未显式说明不再调用 bootstrap

- **Controller decision**: accepted
- **Fix status**: 已修复
- **Plan changes**:
  - 明确 `_open_configured_connection()` / `HostDurableStore.connect()` 是 secondary connection validation-only 路径。
  - 明确该路径不调用 `bootstrap_host_durable_store()`，不调用 `_bootstrap_fresh_schema()`，不执行任何 DDL。

### DS-NBS-3-已修复-Read stale 测试的 connection 创建方式

- **Controller decision**: accepted
- **Fix status**: 已修复
- **Plan changes**:
  - 明确 read-stale 测试必须使用同一 DB 文件上的两个独立 SQLite connections。
  - 建议使用 `open_host_durable_store()` 返回的 primary store connection 作为 connection A，再通过同一个 `HostDurableStore` 的 `store.connect()` 获取 connection B。
  - Slice 2 data flow 同步要求 primary connection + `store.connect()` 和两个 `HostTransactionRunner` 实例。

## Changed Files

- `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- `docs/reviews/wu-dur-01-02-plan-fix-codex-20260601.md`

## Not Changed

- 未修改 source。
- 未修改 tests。
- 未修改 README。
- 未修改 `docs/host/design.md`。
- 未修改 `docs/host/host-core-followup-implementation-control.md`。

## Validation

- 未运行 pytest / pyright；本次是 plan-only 文档修复，且用户限定不得进入 implementation 或修改 source/tests/README。
- 已用文本检索复核 plan 中 `_bootstrap_fresh_schema`、validation ownership、secondary connection、`HOST_DURABLE_INDEXES`、`busy_pages`、read-stale connection 要求均已落入目标 plan。

## New Risks / Open Questions

- 无新增 blocking question。
- 剩余 deferred scope 保持 controller adjudication 原裁决：DDL text diff validation deferred to WU-LAYER-01；生产级 WAL busy 覆盖 deferred to future hardening；rollback failure 和 memory snapshot row CAS 仍不纳入本 work unit。

## Stop Status

plan-fix-complete

## Artifact Path

`docs/reviews/wu-dur-01-02-plan-fix-codex-20260601.md`
