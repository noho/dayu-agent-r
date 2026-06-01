# WU-DUR-01-02 Plan Re-review - DS

## Reviewed Fix

- **Plan (fixed)**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Controller adjudication**: `docs/reviews/wu-dur-01-02-plan-controller-adjudication-20260601.md`
- **Fix artifact**: `docs/reviews/wu-dur-01-02-plan-fix-codex-20260601.md`
- **Original DS review**: `docs/reviews/wu-dur-01-02-plan-review-ds-20260601.md`
- **MiMo review**: `docs/reviews/wu-dur-01-02-plan-review-mimo-20260601.md`

## Conclusion

**pass**

全部 7 条 controller-accepted findings/suggestions 均已修复，无新增 blocking issue。Plan 已达到 code-generation-ready 标准，可进入 implementation gate。

## Finding Status

### MIMO-P1 — fixed

- **要求**: 明确 `_bootstrap_fresh_schema()` 是唯一允许执行 `HOST_DURABLE_DDL` 的路径，`user_version == HOST_SCHEMA_VERSION` 分支只做 validation。
- **证据**: Plan line 102-103 明确写"`_bootstrap_fresh_schema(connection)` 是本 work unit 唯一允许执行 `HOST_DURABLE_DDL` 的路径。`bootstrap_host_durable_store()` 自身不得在该 helper 外遍历或执行 `HOST_DURABLE_DDL`；`user_version == HOST_SCHEMA_VERSION` 分支必须直接跳过 DDL loop"。Slice 1 Exact changes (line 250-253) 重复了同一约束。

### MIMO-P2 — fixed

- **要求**: 明确 `_open_configured_connection()` / `HostDurableStore.connect()` 为 validation-only、no-bootstrap 路径。
- **证据**: Plan line 145 明确"`_open_configured_connection()` / `HostDurableStore.connect()`：是 secondary connection validation-only 路径。该路径只做 parent 准备、raw connection、PRAGMA setup、`validate_host_durable_schema(connection)`；不得调用 `bootstrap_host_durable_store()`、不得调用 `_bootstrap_fresh_schema()`、不得执行任何 DDL"。Slice 1 Exact changes (line 253-254) 和测试 (line 274) 均覆盖该路径。

### MIMO-P3 / DS-P1 (combined) — fixed

- **要求**: `HOST_DURABLE_INDEXES` 必须覆盖全部已有 `INDEX_*` durable index name constants，并增加 consistency test。
- **证据**: Plan line 113 明确"必须包含 `schema.py` 中全部已有 `INDEX_*` durable index name constants"，line 113-136 列出全部 22 个 index name constants，line 249 明确"不允许只挑核心索引子集"。Slice 1 测试 (line 275) 增加 consistency test：解析 `HOST_DURABLE_DDL` 中 `CREATE INDEX` / `CREATE UNIQUE INDEX` 语句，断言提取的 index name 集合 == `set(HOST_DURABLE_INDEXES)`。

### MIMO-P4 — fixed

- **要求**: 将 busy 测试标注为 diagnostic-field observability，明确不要求稳定制造 `busy_pages > 0`，可选 unit-level synthetic coverage 仅在不过度 mock SQLite 的前提下允许。
- **证据**: Plan line 290-292 明确"at minimum assert result fields are non-negative and no correctness path depends on checkpoint success"，line 292-293 明确"只有在不 over-mock SQLite transaction、WAL、locking、checkpoint correctness 或 production retry behavior 的前提下，才可增加 unit-level synthetic `busy_pages > 0` coverage"。

### DS-NBS-1 — fixed

- **要求**: 澄清 validation call ownership，消除 `open_host_durable_store()` 双重 full validation 歧义。
- **证据**: Plan line 141-144 明确了三方 ownership：`open_host_durable_store()` 只做 parent 准备 + PRAGMA + 调用 bootstrap，不在 bootstrap 返回后再次 validate；`bootstrap_host_durable_store()` 是 schema dispatch + final validation owner；fresh 分支 DDL 后 validate，current 分支只 validate。

### DS-NBS-2 — fixed

- **要求**: 显式声明 `_open_configured_connection()` 不调用 bootstrap。
- **证据**: Plan line 145 明确"不得调用 `bootstrap_host_durable_store()`、不得调用 `_bootstrap_fresh_schema()`、不得执行任何 DDL"。Slice 1 Exact changes (line 253-254) 重复了同一约束。

### DS-NBS-3 — fixed

- **要求**: Read-stale 测试明确使用 `HostDurableStore` primary connection + `store.connect()` 获取两个独立 SQLite connection。
- **证据**: Plan line 198-201 明确"使用 `open_host_durable_store()` 返回的 primary store connection 作为 connection A，再通过同一个 `HostDurableStore` 的 `store.connect()` 获取 connection B"。Slice 2 data flow (line 300-301) 同步要求。

## New Blocking Issues

none.

Plan fix 仅做文档层面的澄清和具体化，未改变 scope、未新增 public API、未引入 schema migration、未扩展 WU-DUR-02 范围。修复后的 plan 在以下方面比原版更精确：

- bootstrap 分支的 DDL 执行边界从"隐含推断"变为"显式禁令"
- secondary connection 路径的 validation-only 语义从"可从 slice 逻辑推断"变为"显式 contract"
- `HOST_DURABLE_INDEXES` 从"由 index name constants 组成"变为"必须覆盖全部 22 个已有常量 + consistency test 验证"
- 双重 validation 从"歧义"变为"单 owner 明确"
- Read-stale 测试的 connection 来源从"两个独立 configured connection"变为"primary store connection + store.connect()"

无新增 correctness / scope / boundary 风险。

## Stop Status

rereview-complete
