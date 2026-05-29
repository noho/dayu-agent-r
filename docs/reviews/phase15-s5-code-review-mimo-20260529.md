# Phase 15 Slice P15-S5 Code Review

## Gate / Scope

- Gate: Phase 15 Slice P15-S5 code review.
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md` Slice P15-S5.
- Implementation artifact: `docs/reviews/phase15-s5-implementation-codex-20260529.md`.
- Reviewer: AgentMiMo code review specialist.
- Review date: 2026-05-29.
- Review mode: workspace diff only; no code changes, no commit/push/PR.

## Verdict

**PASS — no blocker, no major finding.**

S5 实现完全符合 approved plan Slice P15-S5 的目标与约束。所有 74 项相关测试通过，pyright 0 errors，diff 范围精确，未越界修改禁止模块。

## Changed Files Summary

| File | Change type | Description |
|---|---|---|
| `dayu/host/durable/projection.py` | feature | 新增 `ProjectionResetResult`、`reset_projection_refs_for_deleted_events` 及内部验证/删除 helpers |
| `dayu/host/durable/purge.py` | refactor | 迁移 projection reset SQL 到 `projection.py` owner helper，删除 purge-local 重复实现 |
| `dayu/host/recovery.py` | hardening | `_classify_run` 前新增 Session row 存在性检查 |
| `dayu/host/dispatch.py` | hardening | queue promotion 与 lane-acquired recheck 新增 Session 存在性检查 |
| `tests/host/test_projection_checkpoint.py` | test | 新增 reset helper 白名单 consumer 测试与非白名单拒绝测试 |
| `tests/host/test_projection_read_model.py` | test | 新增 purge 后 read model 从剩余 EventLog 重建测试 |
| `tests/host/test_purge_session.py` | test | 新增独立进程 multiprocess read-after-purge fail-closed 测试 |
| `tests/host/test_recovery_scan.py` | test | 新增 Session row 缺失时 recovery skip 测试 |

## Findings

### F-01 [INFO] projection reset helper 精确性 — PASS

**审查点**: `reset_projection_refs_for_deleted_events` 是否只处理 caller-provided deleted EventLog ids，且只允许 rebuildable consumers。

**结论**: 完全符合。

- 函数签名 `(transaction, *, event_ids, rebuildable_consumer_ids)` 明确要求调用方传入已确认的 EventLog ids 和白名单 consumer ids。
- `_validate_reset_event_ids` 校验非空、无重复。
- `_validate_rebuildable_consumer_ids` 校验非空、无重复。
- `_raise_for_unsupported_projection_reset_refs` 在 checkpoint 和 failure 两张表上分别检查：若存在非白名单 consumer 引用目标 EventLog，抛 `HostDurableError` 拒绝整个操作。
- `_delete_allowed_projection_reset_refs` 只删除白名单 consumer 且引用目标 EventLog 的 rows。
- 空 `event_ids` 时提前返回 `ProjectionResetResult(0, 0)`，不发起无谓查询。
- helper 不决定 purge 前置条件，不读 Session/Run truth，只处理 caller 确认过的 EventLog ids。

### F-02 [INFO] purge.py 迁移正确性 — PASS

**审查点**: purge.py 是否只迁移到 projection owner helper，不改变 purge precondition truth。

**结论**: 完全符合。

- `purge.py` 删除了 66 行 purge-local `_raise_for_unsupported_projection_reset_refs` 和 `_delete_allowed_projection_reset_refs` 实现。
- 替换为 `reset_projection_refs_for_deleted_events(transaction, event_ids=event_ids, rebuildable_consumer_ids=_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS)`。
- `_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS` 元组保留在 `purge.py` 中作为 purge 侧策略常量，传给 projection helper。
- 删除计数从 `projection_reset.deleted_checkpoints` / `projection_reset.deleted_failures` 取得，语义不变。
- purge 前置条件检查（`_enforce_session_closed`、`_enforce_no_non_terminal_runs`、`_enforce_no_active_waits`）完全未变，仍使用 Session/Run/Attempt/wait governance truth。
- `TABLE_HOST_PROJECTION_CHECKPOINTS` 和 `TABLE_HOST_PROJECTION_FAILURES` 从 `purge.py` import 中移除，符合职责迁移。

### F-03 [INFO] minimal read model rebuild from remaining EventLog — PASS

**审查点**: rebuild 是否排除 purged Session 且保留其他 Session。

**结论**: 完全符合。

- `test_rebuild_after_purge_replays_remaining_eventlog_only` 测试流程：
  1. 创建两个 Session（purged / preserved），各有一个 Run。
  2. 为两个 Run 附加 terminal EventLog 并标记 Run 为 terminal。
  3. 关闭两个 Session。
  4. 执行一次 read model repair。
  5. purge 目标 Session。
  6. 删除 read model rows 和 checkpoint。
  7. 再次 repair（从 cursor 0 重建）。
- 断言：
  - `purged_result is None` — purged Session 的 RunResult 未重建。
  - `purged_timeline == ()` — purged Session 的 timeline 未重建。
  - `preserved_result` 存在且 `run_id` 正确 — preserved Session 数据完整。
  - `preserved_texts == ("preserved input",)` — preserved Session 的 user input 保留。
  - `repair.failures == 0` — 重建无失败。

### F-04 [INFO] recovery/dispatch missing Session guard — PASS

**审查点**: guard 是否只防复活，不改变 state machine 或引入 Engine/Remote 修改。

**结论**: 完全符合。

**recovery.py**:
- `StartupRecoveryScanner._classify_run` 在现有 status 分支前新增：
  ```python
  if read_session_by_id(transaction, run.session_id) is None:
      return _action(run, StartupRecoveryDecision.NOT_FOUND, "session_missing")
  ```
- 使用既有 `read_session_by_id`（从 `dayu.host.durable.state` import），不引入新依赖。
- 返回 `NOT_FOUND` + `session_missing` reason，不创建 recovery/lost 等治理事实。
- 不修改 state machine、不修改 recovery policy、不触及 Engine。

**dispatch.py**:
- `_read_startable_run` 在 accepted/queued 查询前新增 Session 存在性检查。
- `_is_dispatchable_recheck` 新增 `session_exists` 参数，在 lane-acquired recheck 中加入 `and session_exists` 条件。
- 两处 guard 都只做 read check + skip，不修改 dispatch state machine。
- 使用既有 `read_session_by_id`，不引入新依赖。

**测试覆盖**:
- `test_scan_skips_non_terminal_run_when_session_row_is_missing` 通过 `_delete_session_rows_without_foreign_keys`（`PRAGMA foreign_keys=OFF` 后删除 Session rows）模拟残留 Run 场景，验证 recovery 返回 `NOT_FOUND` + `session_missing` 且不追加 recovery/lost EventLog。

### F-05 [INFO] local multiprocess smoke 独立进程验证 — PASS

**审查点**: 是否真正使用 independent processes / separate SQLite connections。

**结论**: 完全符合。

- `test_public_purge_is_observed_by_independent_process_read_paths` 使用 `multiprocessing.Process(target=..., args=...)` 创建两个 OS 级进程。
- 进程 A (`_purge_in_independent_process`): 通过 `asyncio.run` + `open_host(options)` 打开独立 Host handle，执行 `purge_session`，将结果写入 marker 文件。
- 进程 B (`_read_after_purge_in_independent_process`): 同样通过 `asyncio.run` + `open_host(options)` 打开独立 Host handle，验证 `get_session`、`get_run`、`retry_run`、`replay_run`、`watch_session_events` 均返回 `NOT_FOUND`。
- 两个进程通过 marker 文件传递结果，不共享 Python 对象或 SQLite 连接。
- `open_host_options` 和 `deterministic_runner_spec` 来自 `tests.host.public_smoke_support`，与既有多进程测试一致。
- 进程 join timeout 为 5 秒，exitcode 断言为 0。
- 不涉及 RemoteProxy / RemoteStub / wire protocol。

### F-06 [INFO] tests 覆盖 plan expected assertions — PASS

**审查点**: tests 是否覆盖 plan expected assertions。

S5 plan expected assertions 与实际测试覆盖对照：

| Plan assertion | Test | Status |
|---|---|---|
| Projection checkpoint/failure reset 不使用 projection 当 truth | `test_reset_refs_for_deleted_events_deletes_only_rebuildable_consumers` | covered |
| Projection reset 遇非白名单 consumer 拒绝 | `test_reset_refs_for_deleted_events_rejects_non_rebuildable_consumer` | covered |
| Rebuild from remaining EventLog 排除 purged Session | `test_rebuild_after_purge_replays_remaining_eventlog_only` | covered |
| Rebuild 保留 other Session | 同上（preserved assertions） | covered |
| Recovery 不 recover purged Session | `test_scan_skips_non_terminal_run_when_session_row_is_missing` | covered |
| Multiprocess read/replay/watch after purge fail closed | `test_public_purge_is_observed_by_independent_process_read_paths` | covered |

### F-07 [INFO] pyright / docstring / typing — PASS

- pyright: `0 errors, 0 warnings, 0 informations`（implementation artifact 声明 + reviewer 独立验证）。
- 新增函数全部提供中文 docstring，含参数、返回值、异常。
- 新增 `ProjectionResetResult` 为 `frozen=True, slots=True` dataclass。
- 新增 helper 函数参数均有类型注解，无 `Any`、`object`、无类型参数。
- `_validate_reset_event_ids`、`_validate_rebuildable_consumer_ids`、`_raise_for_unsupported_projection_reset_refs`、`_delete_allowed_projection_reset_refs`、`_in_clause`、`_placeholders` 均为模块级私有函数。

### F-08 [INFO] README decision — PASS

**审查点**: README 不更新是否合理。

- S5 implementation artifact 声明：P15-S5 变更了 local hardening 和 tests，未变更 user-facing commands、public API shape、配置或 stable Host architecture text。
- plan Docs Decision 明确 `dayu/host/README.md` 更新时机为 S3/S4 完成后。
- S6 的职责为 docs/import-boundaries/full-validation。
- S5 不更新 README 符合 plan 约定和职责分工。
- S6 docs 不应提前实现，implementation artifact 正确遵守。

## Adversarial Failure Pass

### 退化场景检查

1. **空 EventLog session purge**: `reset_projection_refs_for_deleted_events` 在空 `event_ids` 时提前返回零计数，不查询 DB。purge helper 层面 `_read_target_event_refs` 返回空时抛 `HostDurableError("purge target Session has no EventLog facts")`，正确拦截。PASS。

2. **Session row 缺失但 Run row 残留（FK 关闭后）**: recovery test 通过 `_delete_session_rows_without_foreign_keys` 模拟，验证 NOT_FOUND + session_missing。不追加治理事实。PASS。

3. **非白名单 consumer 引用目标 EventLog**: `_raise_for_unsupported_projection_reset_refs` 检查 checkpoint 和 failure 两表，发现非白名单 consumer 时抛 `HostDurableError`，整个 purge transaction 回滚。PASS。

4. **独立进程 purge 后 read**: multiprocess test 验证 5 个 public API 均返回 NOT_FOUND。PASS。

### 过度耦合检查

- `projection.py` 不 import `purge.py`，purge.py 单向 import projection.py。PASS。
- `recovery.py` 和 `dispatch.py` 使用既有 `read_session_by_id`，不新增跨层依赖。PASS。
- 测试 helper `_delete_session_rows_without_foreign_keys` 使用 `sqlite3` 直连，仅限测试内使用，不泄漏到生产代码。PASS。

### 边界条件检查

- `_validate_reset_event_ids` 拒绝重复 event_id。PASS。
- `_validate_rebuildable_consumer_ids` 拒绝空列表和重复 consumer_id。PASS。
- `_is_dispatchable_recheck` 新增 `session_exists` 条件位于 `run is not None and attempt is not None and dispatch_record is not None` 之后、`run.status == RunStatus.RUNNING` 之前，逻辑顺序正确。PASS。

## Residual Risks

| Risk | Classification | Owner |
|---|---|---|
| RemoteProxy / RemoteStub multiprocess purge 行为 | deferred to issue 73 | remote follow-up |
| Multiprocess race 覆盖证明 post-commit fail-closed，不覆盖 in-transaction race | by design: SQLite CAS ordering | N/A |
| recovery missing-Session test 使用 FK-disabled 残留行 | hardening test，非标准 purge path | N/A |

## Completion

P15-S5 code review complete.无 blocker，无 major finding。所有 8 项 INFO findings 均 PASS。实现符合 approved plan Slice P15-S5 目标与约束。
