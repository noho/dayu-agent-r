# Phase 15 P15-S2 Code Review — AgentDS

## Gate / Scope

- Gate: Phase 15 Slice P15-S2 code review.
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`.
- Implementation artifact: `docs/reviews/phase15-s2-implementation-codex-20260529.md`.
- Review scope: S2 only — internal transaction-scoped delete matrix helper and tests.

## Review Targets

- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s2-implementation-codex-20260529.md`

## Review Findings

### F1 [PASS] FK-safe delete ordering

**证据**: `purge.py:1318-1445` `_delete_session_matrix`。

按以下顺序执行删除，所有 FK 约束由 `PRAGMA foreign_keys=ON` (`transaction.py:364`) 保障：

1. audit sink markers (FK → event_log)
2. outbox drain idempotency / terminal items (FK → event_log)
3. tool trace hot (FK → event_log)
4. memory diagnostics / items / snapshots (FK → event_log, items cascade from snapshots)
5. minimal read model rows (FK → event_log, runs, sessions)
6. projection checkpoints / failures (FK → event_log)
7. old command idempotency records (FK → event_log via created_event_id/sequence)
8. wait records (FK → event_log, runs, sessions, attempts)
9. dispatch records (FK → event_log, runs, attempts)
10. attempts (FK → event_log, runs)
11. runs — child-before-parent via iterative leaf deletion (`purge.py:1792-1823`)
12. session slots (FK → sessions, event_log)
13. session row (FK → event_log)
14. EventLog rows
15. unreferenced payload descriptors
16. unreferenced SQLite payload rows

所有 FK 引用表均在 EventLog 之前删除。子先父后 Run 删除使用循环叶删除 (`NOT IN source_run_id`)，循环依赖检测通过 `rows <= 0` 守卫触发 `HostDurableError`。

**判定**: PASS。

---

### F2 [PASS] Precondition enforcement from governance truth only

**证据**: `purge.py:709-714`。

三个前置条件均从 durable governance tables 读取：
- `_read_session_row` 读取 `host_sessions` status
- `_enforce_session_closed` 校验 status == "closed"
- `_enforce_no_non_terminal_runs` 读取 `host_runs` status，拒绝 6 种非终态
- `_enforce_no_active_waits` 读取 `host_wait_records` WHERE status = "waiting"

未使用 projection、audit marker、outbox 或 memory 表证明前置条件。

**判定**: PASS。

---

### F3 [PASS] Tombstone/idempotency survival after target facts deleted

**证据**: `purge.py:697-781`, `purge.py:1513-1571`, `tests/host/test_purge_session.py:2134-2223`。

- tombstone 在同一个 write transaction 内先于 commit 写入，无 FK 到被删除表
- purge 幂等记录使用 `created_event_id=None, created_event_sequence=None`
- 首次 purge: `idempotent_replay=False`，tombstone 写入成功
- 第二次 purge（replay）: `idempotent_replay=True`，返回相同 tombstone
- 测试确认 purge 幂等 row 的 `created_event_id IS NULL AND created_event_sequence IS NULL`
- 测试确认 tombstone 按 session_id 读取成功
- 测试确认 target Session EventLog/state/projection/memory rows 已清零
- 测试确认 other Session 保留

**判定**: PASS。

---

### F4 [PASS] Payload ref-count cleanup (not path-guessed)

**证据**: `purge.py:1448-1510`, `purge.py:1935-1997`。

- 删除前通过 `_read_target_payload_refs` 收集所有 durable payload ref（8 个引用源 → set 去重）
- 删除矩阵后，对每个收集的 ref 调用 `_payload_ref_is_still_referenced`，扫描所有 8 个引用列确认无剩余引用
- 只有 ref-count = 0 的 descriptor 被删除
- SQLite payload 同样检查 `_sqlite_payload_is_still_referenced`，确认无 descriptor 再引用后删除
- 测试中 `_SHARED_PAYLOAD_REF` 因 other Session 引用而被保留，`_UNIQUE_PAYLOAD_REF` 因引用归零被删除
- artifact 路径通过 `PurgeCommitCleanupRefs` 带回，不在 transaction 内做 IO

**判定**: PASS。

---

### F5 [PASS] Other Session preservation

**证据**: `tests/host/test_purge_session.py:2159-2168`。

测试验证 other Session (`_OTHER_SESSION_ID`) 在 target Session purge 后保留（count = 1），其关联 payload descriptor (`_SHARED_PAYLOAD_REF`) 也保留。

**判定**: PASS。

---

### F6 [PASS] Projection checkpoint/failure reset by exact EventLog id

**证据**: `purge.py:1385-1396`。

```python
projection_checkpoints = _delete_by_event_ids(
    transaction, TABLE_HOST_PROJECTION_CHECKPOINTS, "checkpoint_event_id", event_ids,
)
projection_failures = _delete_by_event_ids(
    transaction, TABLE_HOST_PROJECTION_FAILURES, "failed_event_id", event_ids,
)
```

使用精确 SQL `DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN (...)`，只删除行引用目标 EventLog 的 checkpoint/failure。不用 session_id 盲删，不用 projection 证明前置条件。

**判定**: PASS。

---

### F7 [PASS] Strict typing, Chinese docstrings, no magic values

**证据**: 全文件扫描。

- 所有函数有中文 docstring（params / returns / raises）
- 所有 dataclass 有中文 overview docstring 与字段说明
- 无 `object`、`Any`、裸 `dict/list/set`
- 无 `hasattr`/`getattr`
- 所有运行时字符串（`_SESSION_STATUS_CLOSED`、`_RUN_STATUS_SUCCEEDED` 等）均为模块级常量
- `__all__` 明确定义 exports
- `pyright` 0 errors, 0 warnings, 0 informations

**判定**: PASS。

---

### F8 [PASS] Semantic digest excludes mutable state

**证据**: `purge.py:559-593` `build_purge_semantic_digest`。

semantic digest 字段：operation (`"purge_session"`)、session_id、reason、operation_context_digest、operation_context_refs、request_context。不含 timestamp、deleted counts、DB state。同一请求 replay 时可稳定匹配。

**判定**: PASS。

---

### F9 [PASS] Replay / idempotency conflict classification

**证据**: `purge.py:607-674` `record_or_read_purge_idempotency` + `purge.py:1632-1687` `_decision_for_existing_tombstone`。

| 场景 | 判定 | 测试 |
|---|---|---|
| tombstone 不存在，无 idempotency row | PROCEED | 集成测试 |
| tombstone 存在，同 key + 同 digest | REPLAY | `test_tombstone_replay_records_purge_idempotency_with_null_event_refs` |
| tombstone 存在，同 key + 不同 digest | IDEMPOTENCY_CONFLICT | `test_tombstone_same_key_different_digest_conflicts` |
| tombstone 存在，不同 key | ALREADY_PURGED_CONFLICT | `test_tombstone_different_key_returns_already_purged_conflict` |
| tombstone 不存在，idempotency row 同 key + 不同 digest | IDEMPOTENCY_CONFLICT | `test_existing_idempotency_same_key_different_digest_conflicts` |
| tombstone 不存在，idempotency row 同 key + 同 digest + tombstone 缺失 | DURABLE_INCONSISTENCY | 间接覆盖 |
| tombstone 存在 + idempotency row 同 key 不同 digest | DURABLE_INCONSISTENCY | `test_tombstone_same_key_same_digest_with_conflicting_idempotency_is_inconsistent` |

全部 6 个 replay/conflict 判定测试覆盖。

**判定**: PASS。

---

### F10 [PASS] Child-before-parent Run deletion

**证据**: `purge.py:1792-1823` `_delete_runs_child_before_parent`。

使用迭代叶删除算法：每轮删除 `source_run_id` 不被任何剩余 Session Run 引用的 Run。测试使用 retry 关系（child `source_run_id` → parent），验证 parent + child 均成功删除。循环依赖通过 `rows <= 0` 检测中断并抛 `HostDurableError`。

**判定**: PASS。

---

### F11 [NOTE] Projection checkpoint reset not filtered by consumer rebuildability

**证据**: `purge.py:1385-1396`。

当前实现使用 `DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN (...)` — 只要 checkpoint 的 `checkpoint_event_id` 在 target EventLog 集合中，不论 consumer 身份均被 reset。

计划要求 (Error handling section):
> Projection checkpoint/failure reset is allowed only when the row references a target EventLog id and the consumer satisfies the rebuildability criterion: it is a projection/sink consumer whose rows are derived only from committed EventLog and can replay from cursor 0 over remaining EventLog. Current allowed consumers are minimal read model, memory projection, audit JSONL sink marker/checkpoint, tool trace hot projection, and outbox terminal projection.

**影响**: 若存在非 rebuildable consumer（如 recovery/admission state owner）的 checkpoint 恰好引用 target EventLog 行，其 checkpoint 会被错误 reset。在 S2 当前 scope 内此风险低（这些 consumer 的 checkpoint 通常不会恰好落在被 purge Session 的 EventLog 上），但计划明确要求 S5 补充此 guard。

**建议**: S5 中添加 `consumer_id IN ('host.minimal-read-model', ...)` 过滤，或为 rebuildable consumers 建立白名单常量。

**判定**: NOTE（S2 实现符合 S2 scope 的精确重置 SQL 要求，但 rebuildability filter 需在 S5 补齐）。

---

### F12 [NOTE] Test coverage gaps

**证据**: `tests/host/test_purge_session.py`。

| 缺失覆盖 | 风险 |
|---|---|
| terminal Run statuses `failed`, `cancelled`, `lost` 未单独测试 | 低 — 代码逻辑仅检查 `status not in _NON_TERMINAL_RUN_STATUSES`，不依赖具体 terminal 值 |
| Session with 0 Run rows 未测试 | 低 — 需要在 `_build_purge_precondition_digest` 中处理空 `run_ids`（当前通过 `if ... else []` 守卫） |
| `PRAGMA foreign_keys=ON` 未显式断言 | 低 — `transaction.py:364` 已全局开启，测试通过已隐式验证 |

**建议**: 可接受不在此 slice 修复；如果后续 S5 或 S6 时间允许，可补齐。

**判定**: NOTE。

---

### F13 [NOTE] `PurgePreconditionSnapshot` exported but unused

**证据**: `purge.py:257-299`, `__all__` 中包含。

S1 中已标记 "only a typed carrier in this slice"，S2 中 `purge_session_durable` 使用 `_read_session_row` + `_build_purge_precondition_digest` 直接从 HostRow 构造 digest，不通过 `PurgePreconditionSnapshot`。该 dataclass 作为 stable public type 存在合理，但当前无消费者。

**判定**: NOTE（S1 已知 issue，非 S2 新增问题）。

---

## Test Validation

- **Command**: `pytest tests/host/test_purge_session.py tests/host/test_payload_store.py tests/host/test_projection_read_model.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py -q`
- **Result**: 110 passed in 0.69s
- **Pyright**: `python -m pyright dayu/host/durable/purge.py dayu/host/durable/payload.py dayu/host/durable/read_model.py dayu/host/durable/memory.py dayu/host/durable/tool_trace.py dayu/host/durable/outbox.py dayu/host/durable/audit.py tests/host`
- **Result**: 0 errors, 0 warnings, 0 informations

## Scope Boundary Verification

| 计划约束 | 验证结果 |
|---|---|
| 不实现 public `purge_session` command | ✓ `purge_session_durable` 是内部 helper |
| 不写 audit JSONL | ✓ `audit_record_ref/digest` 传入为 None，不写 JSONL |
| 不删除 cold JSONL | ✓ 只返回 `PurgeCommitCleanupRefs`，不做文件 IO |
| 不改变 public API | ✓ 未修改 `api.py`、`command.py`、`open_host.py`、`read_api.py` |
| 不修改 Engine | ✓ |
| 不使用 projection/audit/outbox/memory 证明前置条件 | ✓ 前置条件仅从 Session/Run/wait governance tables |
| 不在 transaction 内做慢 IO | ✓ 文件删除仅返回路径引用 |
| 唯一 tombstone per Session | ✓ `session_id UNIQUE` 约束保证 |

## Review Decision

**PASS** — 3 findings, 0 blocking.

P15-S2 implementation correctly delivers the internal transaction-scoped purge delete matrix:
- FK-safe deletion order validated against all 22 tables in the delete matrix
- Preconditions enforced from governance truth only
- Tombstone/idempotency survive deleted Session facts
- Payload cleanup by ref-count, not path-guess
- Other Sessions and shared payloads preserved
- All 6 replay/conflict classifications tested
- Zero pyright errors, 110 tests pass

One deferred action for S5: add consumer rebuildability filter to projection checkpoint reset (`F11`).
