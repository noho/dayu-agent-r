# WU-DUR-01-02 Plan Review - DS

## Reviewed Target

- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Inspection**: `docs/reviews/wu-dur-01-02-discussion-code-inspection-20260601.md`
- **Design source**: `docs/host/design.md` (esp. line 738-753)
- **Control source**: `docs/host/host-core-followup-implementation-control.md` (esp. line 248-298)
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Reviewed by**: AgentDS, adversarial plan review

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | `BEGIN IMMEDIATE` + DDL + `PRAGMA user_version` + `COMMIT` in autocommit-mode connection 实现 fresh bootstrap 原子性 | 成立。`isolation_level=None` 连接上 `BEGIN IMMEDIATE` 启动显式事务，SQLite DDL 是事务性的，`COMMIT`/`ROLLBACK` 控制同成同败。经核验 `connection.py:207` 确认 `isolation_level=None`，与 `transaction.py:277` 中 `run_write()` 使用同一模式一致。 |
| A2 | `validate_host_durable_schema()` 校验 required tables + indexes 覆盖所有 foundation 对象 | 成立。`HOST_DURABLE_TABLES` 已存在（`schema.py:126`），覆盖全部 table。index name constants 已逐一定义（`schema.py:53-75`），与 DDL tuples 严格 1:1 映射。`HOST_DURABLE_INDEXES` 可直接由现有 index name constants 组成。 |
| A3 | `_open_configured_connection()` (即 `connect()`) 加 full validation 不改变 public contract | 成立。`connect()` 是 `HostDurableStore` 内部方法（`connection.py:70-89`），非 public API；加 table/index validation 是 hardening，不新增公开入口。 |
| A4 | WAL checkpoint 被限定为内部 primitive，不进入 correctness 路径 | 成立。Plan 明确 non-goal（line 34-36）、maintenance.py docstring 约束（line 120）、函数约束（line 157-163）、slice stop condition（line 278），四层防护。 |
| A5 | Monkeypatch `ensure_projection_checkpoint` 可确定性触发 CAS race | 成立。`advance_projection_checkpoint()` 内部调用 `ensure_projection_checkpoint()` 读取当前 checkpoint（projection.py:176），其返回值用于 UPDATE WHERE 的 CAS 条件（projection.py:188,196）。monkeypatch 返回 stale sequence 使 rowcount=0，触发 `"projection checkpoint advance lost CAS race"`。经核验 `write_memory_snapshot_with_checkpoint()` 也经 `advance_projection_checkpoint()` 走同一 CAS 路径（memory.py:507-512），且同一 transaction 内 snapshot write 先于 checkpoint advance（memory.py:496），CAS failure 会触发 transaction rollback。 |
| A6 | Memory CAS 未误解为 snapshot row CAS | 成立。Plan non-goal（line 38）明确："本轮 'memory CAS' 只指 `write_memory_snapshot_with_checkpoint()` 写 snapshot 后推进 projection checkpoint CAS，并由同一 transaction rollback 保证 snapshot 不半提交。" Concurrency matrix（line 197）和 memory CAS test（line 203-209）均围绕 checkpoint CAS。 |
| A7 | Rollback failure 正确排除 | 成立。Plan non-goal（line 39）明确排除，并引用 controller 裁决边界。Inspection 确认 `_rollback()` 是 best-effort suppress（transaction.py:490-500），没有 surfaced error 需求。 |
| A8 | Slice 切分满足可独立验证的行为闭环 | 成立。Slice 1（bootstrap+validation）→ Slice 2（WAL+read stale）→ Slice 3（concurrency matrix）→ Slice 4（docs sync），各 slice 有独立 allowed files、独立 pytest 命令、独立 stop condition。Slice 3 对 Slice 2 无硬依赖（line 284: "Slice 2 not required unless helpers are reused"）。 |

## Conclusion

**pass**

Plan 窄范围、测试先行、精确对应 inspection evidence 和 design doc 要求。所有 review lens（fresh bootstrap transaction、current-version schema validation、WAL checkpoint 边界、read stale 证明、WU-DUR-02 缺口范围、memory CAS 语义、rollback failure 排除、slice ownership）均通过，无 blocking findings。

## Findings

### DS-P1-未修复-低-`HOST_DURABLE_INDEXES` 构造方式未指定，存在维护漂移风险

- **Evidence**: Plan line 111 要求 "新增 `HOST_DURABLE_INDEXES: tuple[str, ...]`，由现有 index name constants 组成"。代码中 index name constants 已存在（`schema.py:53-75`），与 DDL strings 严格 1:1 映射。但 plan 未明确指定 `HOST_DURABLE_INDEXES` 必须覆盖全部 index name constants，还是允许实现 agent 自行选择子集。
- **Why it matters**: 如果实现 agent 只选取"核心"索引而遗漏 projection / outbox / purge 等索引，validation 会出现盲区——缺某些索引的 current-version DB 不会被 opener 拒绝。虽然 DDL text drift 属于 WU-LAYER-01 scope（plan 非阻塞问题 line 391-392），但遗漏 required index name 比 DDL text drift 更直接——它让 validation 的 "缺索引 fail closed" 承诺不完整。
- **Required fix**: 在 Slice 1 Exact changes 中明确 `HOST_DURABLE_INDEXES` 必须包含全部已有 `INDEX_*` 常量（`schema.py:53-75` 全量），且与 `HOST_DURABLE_TABLES` 保持同等覆盖完整性。
- **Controller decision status**: pending

## Non-blocking Suggestions

### NBS-1: `open_host_durable_store()` 双重 validation 调用

Plan line 100 让 `bootstrap_host_durable_store()` 对 current version 直接调用 `validate_host_durable_schema()`，line 115 又让 `open_host_durable_store()` 再次调用。结果：current-version 路径跑两次 full validation（version + tables + indexes），fresh 路径也在 bootstrap 后跑两次。不破坏正确性，但建议澄清：要么 `bootstrap_host_durable_store()` 只决定是否执行 DDL，validation 统一由 opener 调用；要么 opener 不再重复调用。当前写法增加了 implementation agent 的解读歧义。

### NBS-2: `_open_configured_connection()` 未显式说明不再调用 bootstrap

Plan line 223 说 `connection.py` 改为 import/call `validate_host_durable_schema()`。当前 `_open_configured_connection()` 只调 `validate_host_schema_version()`，不调 `bootstrap_host_durable_store()`。Plan 未显式声明该路径不调 bootstrap（因为 secondary connection 不应做 DDL）。虽然从 slice 逻辑可推断，但建议在 Slice 1 Exact changes 中加一句话澄清，避免 implementation agent 误在此路径加入 DDL 执行。

### NBS-3: Read stale 测试的 connection 创建方式

Plan line 267 说 "Read stale test uses two independent configured connections and two `HostTransactionRunner` instances"。当前 `HostTransactionRunner` 需要 `sqlite3.Connection` + policy 参数构造。Plan 未明确两个 runner 是共享同一 DB path 还是独立 store。建议实现时通过 `HostDurableStore` 的 primary connection 和 `store.connect()` 分别获取，确保两个 runner 指向同一 DB 文件但使用不同 SQLite connection，语义与设计预期一致。

## Open Questions / Residual Risk

### Blocking

none.

### Non-blocking

| ID | Question / Risk | Owner |
|----|----------------|-------|
| OQ-1 | SQLite `PRAGMA wal_checkpoint(PASSIVE)` 在测试中 `busy_pages > 0` 可能不稳定。Plan 已处理（line 260-261: "at minimum assert result fields are non-negative and no correctness path depends on checkpoint success"），不需 plan 级修改。 | Implementation agent |
| OQ-2 | `CREATE ... IF NOT EXISTS` 保留在 DDL 文本中，与 current-version 不静默修复的设计意图表面冲突。Plan 已通过 bootstrap 分支（fresh only executes DDL, current only validates）解决实质边界（line 103）。若 reviewer 要求移除 `IF NOT EXISTS`，需评估 fresh validation 和 test setup 影响（line 393-394），不属于 plan 缺陷。 | Controller / code reviewer |
| OQ-3 | 新增 idempotency multiprocess tests 在极慢 CI 机器上可能 timing flake。Plan 建议使用 start gate + result files 模式（line 392-393），与既有 `test_event_log_multiprocess.py` 一致。风险可控，不需 plan 级修改。 | Implementation agent |
| OQ-4 | `validate_host_durable_schema()` 第一版只校验 table/index existence，不做 DDL text diff。Plan 非阻塞问题（line 391-392）已将此 deferred 到 WU-LAYER-01。属于明确的 scope deferral，不是 plan gap。 | WU-LAYER-01 owner |

## Stop Status

review-complete
