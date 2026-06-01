# WU-DUR-01-02 Plan Review - MiMo

## Reviewed Target

- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Inspection artifact**: `docs/reviews/wu-dur-01-02-discussion-code-inspection-20260601.md`
- **Design source**: `docs/host/design.md` (sections 738-753)
- **Control source**: `docs/host/host-core-followup-implementation-control.md` (sections 248-298)

## Assumptions Tested

1. Fresh bootstrap 当前无显式事务 — **confirmed**: `schema.py:1226-1250` 逐条 execute DDL + `PRAGMA user_version` + `commit()`，无 `BEGIN` 包裹。
2. Current-version validation 只看 `user_version` — **confirmed**: `schema.py:1253-1269` 只校验 `PRAGMA user_version`，不查 `sqlite_master`。
3. `_open_configured_connection()` 也只做 version validation — **confirmed**: `connection.py:171-192` 调用 `validate_host_schema_version()`。
4. WAL checkpoint 只有 auto-checkpoint baseline — **confirmed**: `transaction.py:366-379` 设 `wal_autocheckpoint=256`，无 Host-owned checkpoint primitive。
5. Read stale 无直接测试 — **confirmed**: inspection 未找到长 read transaction 旧快照 / 新 read transaction fresh truth 的直接测试。
6. Memory CAS 语义 — **confirmed**: 只有 `write_memory_snapshot_with_checkpoint()` 内 projection checkpoint CAS，无 snapshot row CAS。
7. `HOST_DURABLE_TABLES` 已定义但无 `HOST_DURABLE_INDEXES` — **confirmed**: `schema.py:126` 定义了 `HOST_DURABLE_TABLES`，无对应 index 列表。

## Conclusion

**pass-with-findings**

Plan 结构合理、slice 边界清晰、scope 约束严格、non-goals 明确。Plan 真实解决了 WU-DUR-01 和 WU-DUR-02 的验收信号，没有引入过度设计。以下 findings 均为 medium 或 low，不阻塞进入 implementation，但需要 implementation agent 在实施时确认或修正。

## Findings

### MIMO-P1-未修复-中-bootstrap 分支条件与 current-version DDL 路径的边界

- **位置**: Detailed Implementation Decisions → Fresh Bootstrap Transaction
- **问题类型**: 状态机漏洞
- **当前写法**: Plan 说 `user_version == 0` 走 fresh branch，`user_version == HOST_SCHEMA_VERSION` 走 validate-only branch，其它走 mismatch。DDL 仍保留 `CREATE ... IF NOT EXISTS`。
- **反例/失败场景**: 当前 `bootstrap_host_durable_store()` 允许 `current_version in (0, HOST_SCHEMA_VERSION)` 后对**所有** DDL 逐条 execute（包括 current version）。Plan 要求拆成 fresh-only DDL + current validate-only。但如果 implementation agent 仅修改 `if` 分支而未确保 current branch **完全跳过** DDL 循环，则 current DB 仍然执行 `CREATE ... IF NOT EXISTS`，与"current-version 不静默修复"目标矛盾。
- **为什么有问题**: 验收信号明确要求"current-version 缺 required table / index 时普通 opener 必须结构化失败"。如果 current branch 仍执行 DDL，缺表会被静默补齐。
- **直接证据**: `schema.py:1246-1248` 当前对所有 DDL 逐条 execute 无分支保护；plan Slice 1 说"fresh 才执行 DDL，current 只 validate，不 repair"，但代码层面的具体实现要点（跳过 DDL 循环）需要在 slice 描述中更明确。
- **影响**: Implementation agent 可能误解为只需在 `bootstrap_host_durable_store()` 加 `if` 而不跳过 DDL 循环。
- **建议改法和验证点**: Slice 1 的 Exact changes 应明确写"_bootstrap_fresh_schema(connection) 是唯一执行 HOST_DURABLE_DDL 的路径；`user_version == HOST_SCHEMA_VERSION` 分支直接调用 `validate_host_durable_schema(connection)`，不执行任何 DDL"。测试应构造 current version + 缺表 DB，断言 opener 不创建缺失表。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### MIMO-P2-未修复-低-`_open_configured_connection()` 的 validate 调用升级

- **位置**: Slice 1 → Exact changes / connection.py
- **问题类型**: 契约缺失
- **当前写法**: Plan 说 "`connection.py` 改为 import / call `validate_host_durable_schema()`"，但未明确区分 `open_host_durable_store()` 和 `_open_configured_connection()` 两条路径。
- **反例/失败场景**: Implementation agent 可能只改 `open_host_durable_store()` 路径，遗漏 `_open_configured_connection()`（`HostDurableStore.connect()` 使用），导致独立 connection 仍然只做 version validation。
- **为什么有问题**: `connection.py:171-192` 的 `_open_configured_connection()` 被 `HostDuralStore.connect()` 调用，用于创建独立 read/write connection。如果这条路径不做 full schema validation，缺表/缺索引 DB 仍能创建独立 connection 并继续运行。
- **直接证据**: `connection.py:184-186` 当前只调用 `validate_host_schema_version()`；inspection artifact `R2` 也指出这个缺口。
- **影响**: 部分路径绕过 schema validation。
- **建议改法和验证点**: Slice 1 的 Exact changes 中明确列出 `_open_configured_connection()` 也必须改为调用 `validate_host_durable_schema()`。测试应覆盖 `HostDuralStore.connect()` 路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### MIMO-P3-未修复-低-`HOST_DURABLE_INDEXES` 来源的完整性保证

- **位置**: Slice 1 → Required Table / Index Validation Owner
- **问题类型**: 测试缺口
- **当前写法**: Plan 说"新增 `HOST_DURABLE_INDEXES: tuple[str, ...]`，由现有 index name constants 组成"，但未要求测试验证该列表与实际 DDL 中的 index 一致。
- **反例/失败场景**: 如果 `HOST_DURABLE_INDEXES` 遗漏了某个 index name，validation 不会检测到该 index 缺失；或者如果后续 phase 新增 index 但忘记更新 `HOST_DURABLE_INDEXES`，validation 会过时。
- **为什么有问题**: `HOST_DURABLE_TABLES` 已有定义但 `HOST_DURABLE_INDEXES` 是新增的，需要有机制保证它与 `HOST_DURABLE_DDL` 中的 index DDL 保持同步。
- **直接证据**: `schema.py:126` 定义 `HOST_DURABLE_TABLES`，有约 20+ index DDL（`schema.py:226, 985-1106`）分散在多个 DDL tuple 中。
- **影响**: 维护漂移风险，但不阻塞本轮实现。
- **建议改法和验证点**: 建议在 Slice 1 测试中加一个 consistency test：解析 `HOST_DURABLE_DDL` 中所有 `CREATE INDEX` / `CREATE UNIQUE INDEX` 语句，断言提取的 index name 集合 == `HOST_DURABLE_INDEXES` 集合。这能自动检测漂移。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### MIMO-P4-未修复-低-WAL checkpoint busy diagnostic 测试的确定性

- **位置**: Slice 2 → Tests/validation
- **问题类型**: 测试缺口
- **当前写法**: Plan 说 "Add tests for busy diagnostic by holding an active read transaction on another configured connection, performing writes, then running PASSIVE checkpoint and asserting result is observable. Do not require `busy_pages > 0` unless the setup deterministically produces it"。
- **反例/失败场景**: SQLite PASSIVE checkpoint 的 busy 行为取决于 WAL 文件状态和并发 reader 位置。在 CI 环境中，即使有 active reader，PASSIVE checkpoint 也可能返回 `busy_pages == 0`（因为 WAL 文件很小或 reader 已经不在 WAL 内）。这使得 busy diagnostic 测试实际上是 no-op 断言。
- **为什么有问题**: 测试只断言字段非负但不能证明 busy diagnostic path 被真正执行过。这是一个已知 limitation，plan 已经提到 "Do not require busy_pages > 0"，但应明确这是 non-blocking limitation 而不是验证目标。
- **直接证据**: Plan non-blocking section 已提到 "SQLite PRAGMA wal_checkpoint(PASSIVE) 在本地测试中未必稳定返回 busy_pages > 0"。
- **影响**: 不阻塞实现，但 busy diagnostic path 的真实覆盖可能只有在 production 或特定 stress 条件下才能验证。
- **建议改法和验证点**: 在测试中明确标注该测试是 "diagnostic field observable" 而非 "busy path exercised"。可选：用 monkeypatch 或 mock 验证 `busy_pages > 0` 时 diagnostic 正确返回，作为 unit-level coverage。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Non-blocking Suggestions

1. **DDL text diff 作为后续 WU-LAYER-01 工作**: Plan 已正确说明 `validate_host_durable_schema()` 第一版只校验 required table/index existence，不做 full SQL DDL text diff。这是合理的 scope 控制。DDL text drift 应追踪为 WU-LAYER-01 的工作。

2. **idempotency multiprocess 测试的 start gate 模式**: Plan 建议复用 `test_event_log_multiprocess.py` / `test_admission_multiprocess.py` 的 start gate + result files 模式。这是正确的，但 implementation agent 应注意 idempotency 的 start gate 需要在所有 worker 都准备好之后才触发，以确保真正的并发竞争。

3. **`CREATE ... IF NOT EXISTS` 保留**: Plan 保留 DDL 中的 `IF NOT EXISTS`，因为 fresh branch 只服务 `user_version == 0`。这是正确的工程判断。如果 reviewer 有顾虑，可以通过 consistency test（验证 current branch 不执行 DDL）来消除疑虑，而不必修改 DDL 文本。

4. **Slice 3 的 monkeypatch 对 `ensure_projection_checkpoint` 的注入点**: Plan 说 monkeypatch `dayu.host.durable.projection.ensure_projection_checkpoint`。Implementation agent 应确认 `advance_projection_checkpoint()` 内部确实调用 `ensure_projection_checkpoint()`（`projection.py:176`），否则 monkeypatch 目标可能需要调整。当前代码确认了这个调用链。

## Open Questions / Residual Risk

### Blocking

none。

### Non-blocking

| Item | Risk / Question | Destination |
| --- | --- | --- |
| OQ-1 | `HOST_DURABLE_INDEXES` 与实际 DDL 的一致性需要自动检测机制。Implementation agent 应在 Slice 1 加 consistency test。 | WU-DUR-01 Slice 1 implementation |
| OQ-2 | WAL checkpoint busy diagnostic 的生产可观测性只能通过 production hardening 或 stress suite 验证，当前测试覆盖的是 field observability 而非 busy path execution。 | WU-STRESS-01 或 future hardening |
| OQ-3 | `validate_host_durable_schema()` 的第一版不做 DDL text diff，DDL drift 风险需要后续 WU-LAYER-01 关闭。 | WU-LAYER-01 |

## Stop Status

review-complete
