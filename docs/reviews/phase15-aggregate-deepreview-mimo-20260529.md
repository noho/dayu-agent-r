# Phase 15 Aggregate Deep Review

## Gate

Phase 15 aggregate deepreview — `feat/host-phase15-retention-purge-hardening` vs `main`。

## Scope

审查 Phase 15 整体 diff（main...HEAD），覆盖 purge tombstone schema/codec/idempotency、delete matrix、public command/read-after-purge、audit JSONL fail-before-success、projection reset/rebuild/recovery/dispatch/multiprocess hardening、README/guard tests、分层边界、docstring/typing/pyright、non-goals 越界。

不重复 slice-level 已解决问题，除非仍有全局风险或集成回归。

## Verdict

**PASS** — 无 blocker，无 severity ≥ HIGH 的 finding。

## Changed Files Summary

| 文件 | 变更类型 | 行数 |
|------|----------|------|
| `dayu/host/durable/purge.py` | 新增 | +2695 |
| `dayu/host/durable/projection.py` | 新增 | +192 |
| `dayu/host/durable/schema.py` | 修改 | +51/-3 |
| `dayu/host/command.py` | 修改 | +164/-1 |
| `dayu/host/audit.py` | 修改 | +218/-4 |
| `dayu/host/open_host.py` | 修改 | +75/-53 |
| `dayu/host/dispatch.py` | 修改 | +11 |
| `dayu/host/recovery.py` | 修改 | +3 |
| `dayu/host/README.md` | 修改 | +11/-4 |
| `tests/host/test_purge_session.py` | 新增 | +3104 |
| 其它测试文件 | 修改 | 合计 +624 |

总变更：+13682 / -126 行，14 个 commits。

## Verification

- **pyright**: 0 errors, 0 warnings (source + tests)
- **pytest**: 26 passed (test_purge_session.py), 134 passed (related test suite), 总计 160 tests 全部通过
- **README**: 已移除 `purge_session structured unsupported` 语句，替换为已实现 purge 语义说明

## Findings

### INFO-01: `_PurgePreconditionSnapshot` dataclass 未被使用

**Severity**: INFO
**File**: `dayu/host/durable/purge.py:263-306`
**Description**: `PurgePreconditionSnapshot` dataclass 已定义但未被任何代码实例化或引用。`_build_purge_precondition_digest` 直接使用 `HostRow` + 显式参数构建 precondition JSON，不构造此 dataclass。
**Risk**: 无功能风险。属于 dead code，可在未来清理。
**Recommendation**: 非阻塞。若 plan 原意是用此 dataclass 作为 precondition 输入的 typed boundary，可后续补充使用；否则可删除。

### INFO-02: `_placeholders` helper 未被使用

**Severity**: INFO
**File**: `dayu/host/durable/purge.py:2301-2311`
**Description**: `_placeholders` 函数已定义但未被调用。`_in_clause` 自行内联构造 placeholder。
**Risk**: 无功能风险。Dead code。
**Recommendation**: 非阻塞。可删除。

### INFO-03: `purge_session` audit recorder 在 SQLite write transaction 内执行文件 IO

**Severity**: INFO
**File**: `dayu/host/durable/purge.py:1593`, `dayu/host/command.py:812-817`
**Description**: `_insert_tombstone_and_idempotency` 在 SQLite write transaction body 内调用 `request.audit_recorder.record_purge_tombstone_audit()`，该调用会执行 JSONL 文件 append 与 filelock 操作。plan 明确允许这种短 I/O（"implementation 可以在 DB transaction 前后组织短 I/O"），且 command 层对 `OSError` / `RuntimeFileLockError` 做了 catch 并返回 `INTERNAL_ERROR(retryable=True)`。
**Risk**: 极低。JSONL append + filelock 是短操作，且失败时 SQLite transaction runner 会 rollback，不会留下无 audit 的 tombstone。fail-before-success 语义正确。
**Recommendation**: 无需修改。记录供未来优化参考。

### INFO-04: `_delete_old_idempotency_records` 使用 OR-based SQL

**Severity**: INFO
**File**: `dayu/host/durable/purge.py:1799-1810`
**Description**: 删除旧 command idempotency rows 的 SQL 使用三个 OR 条件：`created_event_id IN (...)`、`created_event_sequence IN (...)`、`(scope_id = ? AND scope_kind IN (...))`。SQLite 优化器可能无法高效利用索引。
**Risk**: 低。Purge 是低频操作，目标 Session 的 idempotency rows 通常很少。正确性无问题。
**Recommendation**: 非阻塞。若未来 purge 成为高频操作，可考虑拆分为三条 DELETE 语句。

## Correctness Assessment

### Purge Tombstone Schema

- `HOST_SCHEMA_VERSION` 13→14，fresh DB 起库，无兼容迁移。符合 plan。
- `host_purge_tombstones` DDL 无 FK 到 `event_log` 或 `host_sessions`。正确。
- UNIQUE index on `session_id` 保证一个 Session 最多一个 tombstone。正确。
- `__all__` exports 完整覆盖 public API。

### Tombstone Codec / Idempotency

- `PurgeTombstoneRow` 是 frozen+slots dataclass，所有字段有明确类型。
- `PurgeReplayDecisionKind` 是 closed StrEnum，覆盖 plan 中全部 5 种判定。
- `record_or_read_purge_idempotency` 正确处理 tombstone-present/idempotency-missing 场景：同 key+同 digest replay，同 key+不同 digest conflict，不同 key already-purged conflict。
- `IdempotencyStore().record_idempotent_result` 使用 `created_event_id=None`、`created_event_sequence=None`，保证 purge 幂等 row 不 FK 到已删除 EventLog。
- `build_purge_semantic_digest` 输入只包含稳定语义字段（operation、session_id、reason、operation_context_digest/refs、request_context），不含 mutable DB state。replay 匹配正确。

### Delete Matrix

FK-safe 删除顺序符合 plan：
1. audit sink markers (by event_id)
2. outbox drain idempotency / terminal items (by session_id)
3. tool trace hot (by session_id)
4. memory diagnostics/items/snapshots (by session_id)
5. read model run_results/timeline_items (by session_id)
6. projection checkpoints/failures (exact reset by event_id, whitelist guard)
7. old idempotency records (by event_id/event_sequence/scope)
8. wait records (by session_id)
9. dispatch records (by run_id)
10. attempts (by run_id)
11. runs (child-before-parent via iterative leaf deletion)
12. session slots (by session_id)
13. session (by session_id)
14. EventLog (by session_id)
15. unreferenced payload descriptors, then unreferenced SQLite payloads

`_delete_runs_child_before_parent` 使用 iterative leaf deletion：每轮删除没有子 Run 引用的叶子，直到全部删除。若某轮无进展则抛 `HostDurableError` 防止无限循环。正确。

Payload cleanup 使用 durable ref count 而非路径猜测：`_payload_ref_is_still_referenced` 检查 8 个引用列（包括其它 Session 的 EventLog、timeline、run_results、memory、tool_trace、outbox）。EventLog 和 projection rows 已在前面步骤中被删除，因此 ref count 查询看到的是 post-delete 状态。正确。

### Public Command Wiring

- `command.purge_session` 保持 `host._raise_if_closed()` 作为第一步。
- semantic digest 构造在 `_PurgeSessionOperation.__call__` 内，使用 `build_purge_semantic_digest` + `operation_context_digest`。
- 错误映射正确：`PurgeSessionInvalidStateError` → `INVALID_STATE`，`PurgeSessionAlreadyPurgedError` → `CONFLICT`，`PurgeSessionNotFoundError` → `NOT_FOUND`，`HostIdempotencyConflictError` → `IDEMPOTENCY_CONFLICT`，`OSError`/`RuntimeFileLockError` → `INTERNAL_ERROR(retryable=True)`。
- `open_host._PublicHostHandle.purge_session` 正确接入 `_purge_session` command facade。

### Read-after-purge

- `recovery.py`: `StartupRecoveryScanner._classify_single_run` 新增 `read_session_by_id` guard，Session 不存在时返回 `NOT_FOUND` decision。正确防止 recovery reanimate。
- `dispatch.py`: `_is_dispatchable_recheck` 新增 `session_exists` 参数，`_read_startable_run` 新增 Session 存在性检查。正确防止 dispatch 到已 purge Session。

### Audit JSONL

- `build_purge_tombstone_audit_json_line` 不读取已删除 EventLog，只使用 tombstone candidate 字段。
- `append_purge_tombstone_audit_record` 幂等追加：先检查 JSONL 中是否已有同 source key 行。
- fail-before-success 策略正确：audit recorder 在 tombstone INSERT 之前调用，若 audit 失败则异常传播，SQLite transaction rollback，public 返回 `INTERNAL_ERROR`。

### Projection Reset / Rebuild

- `reset_projection_refs_for_deleted_events` 只允许白名单 consumer（5 个：minimal-read-model、memory、audit-log-jsonl、tool-trace、outbox-terminal）。
- 非白名单 consumer 引用目标 EventLog 时抛 `HostDurableError`，阻止 purge。安全。
- reset 只删除引用目标 EventLog 的 checkpoint/failure rows，不盲删 global checkpoint。

### Docstring / Typing / Pyright

- 所有新增/修改函数提供完整中文 docstring，包含参数、返回值、异常。
- 无 `object`、`Any`、无类型参数、无类型返回值。
- pyright 0 errors, 0 warnings。

### Non-goals 越界检查

- 未修改 Engine。✓
- 未修改 Service/UI/Fins/Runtime。✓
- 未修改 `OpenHostOptions` 字段集合。✓
- 未修改 `watch_session_events` signature/semantics。✓
- 未新增 public error code（使用现有 `NOT_FOUND`、`CONFLICT`、`INVALID_STATE`、`IDEMPOTENCY_CONFLICT`、`INTERNAL_ERROR`）。✓
- 未实现 `archive_session`、`wait_final_answer`、`get_run_result`、public payload reader。✓
- 未做 remote/wire protocol work。✓
- 未删除/重写 audit JSONL。✓
- 未做旧 schema 兼容读取/迁移。✓

## Architecture Boundary Assessment

- `dayu/host/durable/purge.py` 只 import `dayu.host.durable.*` 和 `dayu.contracts.*`。不反向依赖 engine/service/ui/fins。✓
- `dayu/host/durable/projection.py` 只 import `dayu.host.durable.*`。✓
- `dayu/host/command.py` import `dayu.host.durable.purge` 和 `dayu.host.audit`，属于 Host 层内部正常组合。✓
- `dayu/host/audit.py` import `dayu.host.durable.purge` 的 Protocol/dataclass，用于 purge tombstone audit line 构造。属于 Host 层内部依赖。✓
- `purge.py` 中的 `PurgeTombstoneAuditRecorder` Protocol 解耦了 durable purge 与 JSONL 文件实现。正确使用 Protocol 做端口抽象。✓

## Residual Risks

| 风险 | 分类 | Owner |
|------|------|-------|
| `_PurgePreconditionSnapshot` 未使用 dead code | Follow-up cleanup | 无 |
| `_placeholders` 未使用 dead code | Follow-up cleanup | 无 |
| purge 在 write transaction 内做短文件 IO | 已接受，符合 plan | N/A |
| OR-based idempotency delete SQL 性能 | 低频操作，已接受 | N/A |
| cold JSONL / external artifact GC | Follow-up | 后续 retention work |
| remote multiprocess / wire protocol | Follow-up | issue 73 |
| retention scheduler / periodic GC | Follow-up | 后续 production scale work |

## Conclusion

Phase 15 实现完整覆盖 plan 中 release-blocking 范围：purge tombstone schema/codec/idempotency、FK-safe delete matrix、public command wiring、read-after-purge guard、audit JSONL fail-before-success retention、projection reset/rebuild/recovery/dispatch hardening。所有测试通过，pyright 无类型错误，README 已同步。无 blocker，无 severity ≥ HIGH finding。**PASS**。
