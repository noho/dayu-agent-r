# WU-DUR-01 + WU-DUR-02 discussion / code inspection

## Gate / work unit / branch / inspected docs

- Gate: WU-DUR-01 + WU-DUR-02 combined discussion / code inspection gate
- Work units:
  - WU-DUR-01 Schema Bootstrap / DDL Atomicity / WAL Checkpoint Policy
  - WU-DUR-02 Durable Concurrency Conflict Matrix
- Branch: `feat/wu-dur-bootstrap-concurrency`
- Baseline check:
  - `git branch --show-current` -> `feat/wu-dur-bootstrap-concurrency`
  - `git status --short` -> clean
- Inspected docs:
  - `docs/host/design.md`
  - `docs/host/host-core-followup-implementation-control.md`
- Stop boundary: inspection only. No source, test, README, design_doc or control_doc changes.

## 直接证据

### Durable bootstrap / schema validation / WAL / transaction

- `docs/host/host-core-followup-implementation-control.md:248-273`: WU-DUR-01 明确要求 fresh bootstrap DDL 与 `user_version` 同成同败、current-version DB 缺表/缺索引不得被 opener 静默补建、WAL checkpoint 可观测且不进入 hot write path、read stale 语义有直接测试。
- `docs/host/design.md:738-753`: 设计真源要求 bootstrap 设置并校验 `PRAGMA user_version`；fresh DDL 与 `user_version` 必须有明确事务边界并同成同败；current-version opener 不得只信 `user_version` 或用 `CREATE ... IF NOT EXISTS` 静默修复；WAL auto-checkpoint 只是 baseline，production hardening 必须定义 Host-owned checkpoint maintenance policy；read transaction 允许稳定旧快照，fresh truth 必须开启新的短事务。
- `dayu/host/durable/connection.py:146-168`: `open_host_durable_store()` 设置 PRAGMA 后调用 `bootstrap_host_durable_store()` 再 `validate_host_schema_version()`；普通 opener 当前始终走 bootstrap。
- `dayu/host/durable/connection.py:171-192`: `HostDurableStore.connect()` 打开的独立 connection 只做 PRAGMA 与 `validate_host_schema_version()`，不做结构完整性校验。
- `dayu/host/durable/schema.py:1206-1223`: `HOST_DURABLE_DDL` 是全部 table/index DDL 的串联集合。
- `dayu/host/durable/schema.py:1226-1250`: `bootstrap_host_durable_store()` 读取 `user_version`，只拒绝非 0 且非 current 的版本；随后逐条执行 `HOST_DURABLE_DDL`，再执行 `PRAGMA user_version=HOST_SCHEMA_VERSION` 与 `connection.commit()`；没有显式 `BEGIN` 包裹 fresh DDL。
- `dayu/host/durable/schema.py:1253-1269`: `validate_host_schema_version()` 只校验 `PRAGMA user_version`，不校验 required table / index / invariant。
- `dayu/host/durable/transaction.py:252-312`: write transaction 使用 `BEGIN IMMEDIATE`，busy/locked 有限重试，constraint/domain error 不作为 busy retry。
- `dayu/host/durable/transaction.py:314-363`: read transaction 使用 `BEGIN`，因此单次 read transaction 具备 SQLite snapshot 语义。
- `dayu/host/durable/transaction.py:366-379`: connection PRAGMA 设置 `busy_timeout`、`foreign_keys=ON`、`journal_mode=WAL`、`wal_autocheckpoint=256`。
- `tests/host/test_durable_schema.py:227-264`: 已测 fresh DB 创建全部表、WAL、foreign_keys、busy_timeout、`user_version`，以及 matching schema bootstrap 可重复执行。
- `tests/host/test_durable_schema.py:267-278`: 已测非 current `user_version` 抛 `HostSchemaMismatchError`。
- `tests/host/test_durable_connection.py:35-44`: 已测 auto-checkpoint PRAGMA 为 256。
- `tests/host/test_durable_transaction.py:302-350`: 已测 write busy/locked 有限重试耗尽，transaction body / after_commit 不应执行。
- `tests/host/test_durable_transaction.py:353-377`: 已测 read busy/locked 有限重试。
- `tests/host/test_durable_transaction.py:398-485`: 已测 unique / foreign key / CHECK constraint 错误不按 busy retry。
- `tests/host/test_durable_transaction.py:488-522`: 已测 schema/domain error 不按 busy retry。

### EventLog / idempotency / ensure_session / projection / memory / liveness

- `docs/host/host-core-followup-implementation-control.md:275-298`: WU-DUR-02 要求整理 EventLog append、idempotency write、session ensure、projection CAS、memory CAS、liveness update 的并发冲突矩阵，已有覆盖要 closed by evidence，只补缺口。
- `dayu/host/durable/event_log.py:316-406`: `append_event()` 先按 `event_id` 读既有 row；同 digest 返回既有 row，异 digest 抛 `HostEventIdentityConflictError`；INSERT 阶段 `IntegrityError` 会二次读取并重分类同体/异体冲突。
- `tests/host/test_event_log_multiprocess.py:213-260`: 多进程 append 后断言 row count 正确、`event_sequence` 全局唯一递增、`event_id` 唯一。
- `tests/host/test_event_log_multiprocess.py:263-321`: 多进程同 `event_id` 异体写入压测，每轮只允许一个 inserted，其余分类为 conflict。
- `tests/host/test_event_log_multiprocess.py:324-369`: 模拟 INSERT unique race，断言重分类为 `HostEventIdentityConflictError`。
- `dayu/host/durable/idempotency.py:128-197`: `record_idempotent_result()` 同 scope/key/digest 返回既有记录；同 scope/key 不同 digest 抛 `HostIdempotencyConflictError`；INSERT `IntegrityError` 后回读并重分类。
- `tests/host/test_idempotency_store.py:231-265`: 同 scope/key/digest 返回既有 record，不覆盖 result ref。
- `tests/host/test_idempotency_store.py:268-301`: 模拟 INSERT 并发唯一冲突，同 digest 返回并发 record，不同 digest 抛 `HostIdempotencyConflictError`。
- `tests/host/test_idempotency_store.py:332-357`: 同 scope/key 不同 digest 抛 `HostIdempotencyConflictError`。
- `tests/host/test_idempotency_store.py:462-499`: 幂等冲突不是 busy retry。
- `dayu/host/durable/session_lifecycle.py:95-110`: `ensure_session()` 通过 `transaction_runner.run_write()` 执行。
- `dayu/host/durable/session_lifecycle.py:190-259`: `ensure_session` 在同一 write transaction 内读取 slot；无 slot 时 append `SESSION_CREATED`、insert session、insert slot。
- `tests/host/test_admission_multiprocess.py:106-169`: 多进程同 slot `ensure_session` 只产生一个 Session row 和一个 slot row，所有 worker 返回同一 session_id。
- `dayu/host/durable/projection.py:117-149`: `ensure_projection_checkpoint()` 缺失时初始化 cursor 0。
- `dayu/host/durable/projection.py:152-209`: `advance_projection_checkpoint()` 要求 event sequence 正向推进，UPDATE 条件包含 `checkpoint_event_sequence`，rowcount 非 1 或读回不一致时报 `"projection checkpoint advance lost CAS race"`。
- `tests/host/test_projection_checkpoint.py:109-188`: 已测 checkpoint 正向推进、倒退拒绝、同 sequence 重复推进拒绝。
- `dayu/host/durable/memory.py:481-514`: `write_memory_snapshot_with_checkpoint()` 在同一 transaction 写 memory snapshot 并推进 projection checkpoint；正 cursor 使用 `advance_projection_checkpoint()`。
- `tests/host/test_memory_projection.py:922-935`: snapshot 与 checkpoint 在同一 transaction 内提交或一起 rollback。
- `tests/host/test_memory_projection.py:2766-2830`: `ProjectionRunner` 可由 memory consumer 从 committed EventLog 构建 snapshot 并推进 checkpoint。
- `tests/host/test_memory_projection.py:3208-3263`: rebuild memory projection 稳定且不 append EventLog，checkpoint 跟随 snapshot cursor。
- `dayu/host/durable/liveness.py:178-250`: `register_current_instance()` 插入或刷新当前 instance；同 id 不同 identity 抛身份冲突；terminal status 不允许注册回 running。
- `dayu/host/durable/liveness.py:253-299`: `heartbeat_current_instance()` 要求 row 存在、identity 匹配、status 允许；UPDATE rowcount 异常交给 `_require_single_liveness_update()`。
- `dayu/host/durable/liveness.py:376-424`: stopping/stopped 标记通过 status 条件 UPDATE 实现。
- `dayu/host/durable/liveness.py:452-508`: liveness UPDATE rowcount 0 被重新读取并分类为 not registered、identity conflict 或 lifecycle conflict。
- `tests/host/test_host_instance_liveness.py:195-266`: repeated register 同 identity 刷新 heartbeat；STOPPING 不能被 register 静默回 RUNNING。
- `tests/host/test_host_instance_liveness.py:273-320`: STOPPED / CRASHED_SUSPECTED 不能被 register、heartbeat、stopping、stopped 复活。
- `tests/host/test_host_instance_liveness.py:379-463`: heartbeat 只更新相同 identity；错误 token 抛身份冲突且不改写 row。
- `tests/host/test_host_instance_liveness.py:463-523`: 模拟 identity precheck 后 UPDATE 零命中，分类为 `HostInstanceIdentityConflictError`。
- `tests/host/test_host_instance_liveness.py:650-675`: read 返回 typed liveness row，且 liveness row 明确不是 orphan proof。

## WU-DUR-01 risk-by-risk verdict

| Risk | Verdict | Evidence / basis |
| --- | --- | --- |
| Fresh bootstrap DDL + `user_version` 原子性 | 真实存在 | `schema.py:1226-1250` 在 `isolation_level=None` 的 connection 上逐条执行 DDL，再设置 `user_version`；无显式 fresh bootstrap transaction。DDL 中途失败时不会留下 current `user_version` 的直接代码迹象，因为 `user_version` 在 DDL 循环之后写入；但 fresh DDL 与 `user_version` 并非同一个 all-or-nothing 边界，可能留下 partial schema + `user_version=0`，下一次 opener 又会用 `IF NOT EXISTS` 补齐。现有测试只覆盖成功 bootstrap 和 version mismatch，缺少中途 DDL failure 注入测试。 |
| Current-version 缺表/缺索引是否会被 opener 静默补齐 | 真实存在 | `bootstrap_host_durable_store()` 允许 current version，并对所有 DDL 使用 `CREATE ... IF NOT EXISTS` 串行执行；`validate_host_schema_version()` 只检查 `PRAGMA user_version`。因此 current `user_version` 但缺 required table/index 的 DB 会被普通 opener 静默补建并继续运行。现有测试没有构造 current-version 缺表/缺索引 DB。 |
| WAL checkpoint 是否已有 Host-owned maintenance policy | 真实存在缺口 | `transaction.py:366-379` 只有 `wal_autocheckpoint=256` baseline；`tests/host/test_durable_connection.py:35-44` 只验证该 PRAGMA。未发现 `wal_checkpoint`/checkpoint maintenance API、WAL size/result 观测、busy/failure diagnostic 或非 hot path 触发点。 |
| Read stale 语义是否已有直接测试 | 需要更多证据 / 测试缺口 | `transaction.py:314-363` 提供 `BEGIN` read transaction，具备 snapshot 基础；`read_api.py` public read 通过 `host._run_read(...)` 短事务执行，`dispatch.py`/`recovery.py` 也多处调用 `transaction_runner.run_read()` 或 write transaction 读取治理事实。未找到直接测试“长 read transaction 观察旧快照，新 read transaction 观察已提交事实”，也未找到专门断言 public read / recovery governance 不复用长 read transaction 或 projection lag 的测试。 |
| Busy retry / after-commit aggregation /基础 transaction wrapper | 已覆盖 / 非目标 | WU-DUR-01 明确非目标。`test_durable_transaction.py` 已覆盖 busy retry、read retry、constraint/domain error 不重试、after_commit 错误聚合。closed by evidence。 |

## WU-DUR-02 concurrency matrix draft

| 场景 | 现有测试 | 缺口 | 期望 diagnostic / reason | 是否需要生产代码修改初判 | 是否需要多进程验证 |
| --- | --- | --- | --- | --- | --- |
| EventLog append: 多 writer 不同 `event_id` | `test_multiprocess_append_allocates_unique_global_sequences` closed by evidence | 无明显缺口 | 成功；`event_sequence` 全局唯一递增 | 不需要 | 已有 |
| EventLog append: 同 `event_id` 同体重试 | 单元路径由 `append_event()` digest 比较覆盖；需要确认现有 test_event_log_store 是否有同体 replay 命名测试 | 若没有，应补直接单元测试列入矩阵 | `inserted=False`，返回既有 row | 不需要 | 不需要 |
| EventLog append: 同 `event_id` 异体并发 | `test_multiprocess_same_event_id_stress_classifies_conflicts` 与 `test_append_event_reclassifies_insert_unique_race_as_identity_conflict` closed by evidence | 无明显缺口 | `HostEventIdentityConflictError` | 不需要 | 已有 |
| Idempotency write: 同 scope/key/digest 重试 | `test_repeat_same_scope_key_and_digest_returns_existing_record` closed by evidence | 无明显单元缺口 | 返回既有 `IdempotencyRecord`，不覆盖 result ref | 不需要 | 可选；若矩阵要求真实多进程，同 key/same digest 可补轻量多进程 |
| Idempotency write: INSERT unique race 同 digest / 不同 digest | `test_integrity_error_with_same_digest_returns_concurrent_record`、`test_integrity_error_with_different_digest_raises_conflict` closed by evidence | 真实多进程同 key race 未覆盖 | 同 digest 返回并发 record；不同 digest -> `HostIdempotencyConflictError` | 不需要 | 建议补一个多进程 stress，验证 SQLite/BEGIN IMMEDIATE 真实路径 |
| Idempotency write: 业务冲突不重试 | `test_idempotency_conflict_is_not_retried_by_transaction_runner` closed by evidence | 无 | `HostIdempotencyConflictError`，调用一次 | 不需要 | 不需要 |
| ensure_session: 同 slot 并发 | `test_multiprocess_same_slot_ensure_returns_one_bound_session` closed by evidence | 无明显缺口 | 所有进程返回同一 session；DB 只有 1 session + 1 slot | 不需要 | 已有 |
| Projection checkpoint CAS: 正向推进 | `test_advance_checkpoint_persists_event_identity_and_timestamp` closed by evidence | 无 | 成功，checkpoint sequence/id/timestamp 持久化 | 不需要 | 不需要 |
| Projection checkpoint CAS: stale / lost CAS | `projection.py:179-208` 有 CAS rowcount 诊断；现有测试只覆盖倒退/重复，不直接制造 UPDATE rowcount 0 或读回不一致 | 应补 synthetic transaction 或 monkeypatch 类测试，断言 `"projection checkpoint advance lost CAS race"` | `HostDurableError("projection checkpoint advance lost CAS race")` | 初判不需要，除非测试暴露诊断不稳定 | 多进程未必必要；`BEGIN IMMEDIATE` 会序列化真实 writer，synthetic 更直接 |
| Projection checkpoint: 倒退/重复 | `test_advancing_checkpoint_backwards_is_rejected`、`test_advancing_checkpoint_to_same_event_sequence_is_rejected` closed by evidence | 无 | `HostDurableError("projection checkpoint cannot move backwards")` | 不需要 | 不需要 |
| Memory snapshot + checkpoint atomicity | `test_snapshot_and_checkpoint_rollback_together`、`test_projection_consumer_writes_snapshot_with_runner_checkpoint` closed by evidence | 无 atomicity 缺口 | 同 transaction 提交或回滚 | 不需要 | 不需要 |
| Memory CAS / stale checkpoint | memory 通过 `write_memory_snapshot_with_checkpoint()` 复用 projection checkpoint CAS；没有 memory-specific stale/CAS 直接测试 | 若 WU-DUR-02 的“memory CAS”指 snapshot + checkpoint cursor stale，应补围绕 `write_memory_snapshot_with_checkpoint()` 的 stale checkpoint 诊断测试；若指 snapshot row 自身 CAS，当前设计证据不足，应先问 controller/design owner | 复用 projection CAS 时应为 `HostDurableError("projection checkpoint advance lost CAS race")` 或正向/倒退错误 | 复用 checkpoint CAS 不需要；新增 snapshot CAS 需要设计裁决 | 不建议先做多进程；先单元定义语义 |
| Liveness register/heartbeat same identity | `test_repeated_register_same_identity_refreshes_heartbeat_and_status` closed by evidence | 无 | repeated register/heartbeat 成功刷新 heartbeat | 不需要 | 不需要 |
| Liveness wrong identity / lifecycle conflict | `test_heartbeat_wrong_token_raises_identity_conflict`、`test_terminal_instance_does_not_revert_to_running_or_stopping` closed by evidence | 无明显单元缺口 | `HostInstanceIdentityConflictError` 或 `HostInstanceLifecycleConflictError` | 不需要 | 可选；如要覆盖真实多进程同 `host_instance_id` 不同 token race，可补 |
| Liveness UPDATE rowcount 0 classification | `test_heartbeat_rowcount_zero_after_identity_precheck_raises_conflict` closed by evidence | 无 | row 消失 -> not registered；identity drift -> identity conflict；status drift -> lifecycle conflict | 不需要 | 不需要 |
| Transaction busy / locked | `test_busy_locked_retries_are_finite_and_do_not_run_after_commit`、`test_read_busy_locked_retries_are_finite` closed by evidence | 无 | `HostTransactionRetryExhaustedError(attempts=n)` | 不需要 | 现有 lock connection 足够 |
| Rollback failure | WU 背景说已有 after-commit 多错误聚合；当前 inspection 未定位到 rollback failure 专项测试 | 需要更多证据：若矩阵要求 rollback failure 分类，应补搜索/测试或明确非目标 | 目前 `_rollback()` best-effort suppresses sqlite error (`transaction.py:490-500`) | 不建议先改；先确认验收是否真的要求 rollback failure surfaced | 不需要 |

## Scope recommendation

建议可以进入 WU-DUR-01 + WU-DUR-02 joint plan，但 plan 应保持“测试先行、只修真实暴露缺口”的窄范围。

Joint plan 推荐聚焦：

- WU-DUR-01 production fix + tests:
  - fresh bootstrap 使用显式事务边界，保证 DDL + `PRAGMA user_version` 同成同败；补 DDL 中途失败注入测试。
  - normal opener 对 current-version schema 做 required table/index validation；补 current `user_version` 缺表/缺索引不被静默补齐测试。
  - 定义最小 Host-owned WAL checkpoint maintenance primitive / diagnostic，不进入 hot write path；补 checkpoint busy/failure 可观测测试。
  - 补 read stale 直接测试：长 read transaction 稳定旧快照，新 read transaction 观察提交事实；并以 public read/recovery/scheduler 的短事务使用作为测试或 code evidence。
- WU-DUR-02 tests-first:
  - 保留 EventLog append 与 ensure_session 多进程项为 closed by evidence，不制造表面工作。
  - 补 idempotency same-key 多进程 stress（若 controller 要求真实多进程）。
  - 补 projection CAS lost/stale 的 synthetic 直接测试。
  - 补 memory checkpoint stale/CAS 直接测试，前提是“memory CAS”限定为 checkpoint CAS；不要发明 snapshot row CAS。
  - 只在新增测试暴露错误分类不稳定时改 production。

Blocking design question:

- 当前没有必须阻塞进入 joint plan 的设计问题，前提是 WAL checkpoint 被限定为 Host durable 内部 maintenance primitive / test entry，且不新增 public opener contract 或后台 lifecycle policy。
- 若 controller 期望 WU-DUR-01 同时决定生产运行中的 checkpoint 触发调度、public maintenance API、后台任务 lifecycle 或 observable diagnostic contract，则应先由 design owner 更新 `docs/host/design.md`，再进入 implementation-ready plan。
- “memory CAS”术语需要 controller 确认：本次 inspection 只找到 memory snapshot + projection checkpoint 的 CAS 语义；未找到设计要求 memory snapshot row 自身 CAS。若要新增 snapshot row CAS，应先设计裁决。

## Residual risks / open questions

| Item | Risk / question | Owner 建议 |
| --- | --- | --- |
| R1 | Fresh bootstrap 当前不是 all-or-nothing。即使不会直接留下 current `user_version` + half schema，partial schema + `user_version=0` 仍会被下一次 opener 继续补齐，缺少明确 corruption/repair 边界。 | implementation owner 在 joint plan 中修；review owner 验证失败注入测试 |
| R2 | Current-version schema validation 只看 `user_version`，会静默补缺表/缺索引。 | implementation owner 在 joint plan 中修；controller 确认 required table/index validation 范围 |
| R3 | WAL checkpoint maintenance policy 只有 auto-checkpoint baseline。 | controller/design owner 确认是否仅做内部 primitive；implementation owner 补最小诊断与测试 |
| R4 | Read stale 语义缺直接测试。 | implementation owner 补 test；review owner 检查 public/recovery/scheduler 没有依赖长 read/projection lag |
| R5 | Idempotency、projection CAS、memory checkpoint CAS、liveness 多进程覆盖不均衡。 | planning owner 在 matrix 中逐项标注“已有 / 补单元 / 补多进程 / 不需要多进程”的理由 |
| R6 | Rollback failure 是否属于 WU-DUR-02 当前验收未完全清晰。 | controller 确认是否纳入本轮；若纳入，planning owner 先补证据搜索或测试要求 |

## Stop status

inspection-complete
