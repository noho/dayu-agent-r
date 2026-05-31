# Phase 15 PR #74 Deep Review — AgentDS

**Date:** 2026-05-29
**Reviewer:** AgentDS (PR review specialist)
**PR:** [#74](https://github.com/noho/dayu-agent-r/pull/74)
**Base:** main
**Head:** feat/host-phase15-retention-purge-hardening
**Plan:** docs/host/phase15-retention-purge-production-hardening-plan.md

## Overall Verdict: **PASS — No Blocker**

全量 1010 passed, 2 skipped, pyright 0 errors, git diff --check clean。Phase 15 实现严格按照 6-slice plan 执行，所有 release-blocking 契约已满足，aggregate review 已通过的 findings 均已被 fix 或确认无需修复。本 PR 处于 draft-PR-ready 状态，不存在 blocker。

## Scope Verification

PR diff 覆盖 78 files (+14311/-126)，包含：

| Category | Files | Assessment |
|---|---|---|
| 核心实现 | `dayu/host/durable/purge.py` (+2635), `command.py`, `audit.py`, `schema.py`, `projection.py` | 完整 |
| Hardening | `dispatch.py`, `recovery.py`, `open_host.py` | 完整 |
| Tests | `test_purge_session.py` (+3104), 11 modified test files | 完整 |
| Docs | `dayu/host/README.md`, plan doc, implementation-control doc, 34 review artifacts | 完整 |
| 禁止修改 | `dayu/engine/`, `dayu/service/`, `dayu/ui/`, `dayu/fins/`, `dayu/runtime/` | 零变更 ✅ |

## Previously Resolved Findings (No Regression)

以下 aggregate deepreview findings 已通过 fix + re-review + controller adjudication 确认，当前 PR diff 中不存在对应问题：

| Finding | Status |
|---|---|
| AGG-ADJ-001: `_placeholders` dead code in purge.py | **已删除** — purge.py 中无残留 |
| AGG-ADJ-001: `PurgePreconditionSnapshot` unused dataclass | **已删除** — 全代码库无 .py 引用 |
| AGG-ADJ-002: short file IO inside SQLite transaction | **Non-issue** — 设计的 fail-before-success 模式，rollback 测试覆盖 |
| AGG-ADJ-003: OSError → retryable INTERNAL_ERROR | **Accepted** — public error taxonomy 无更细码 |
| AGG-ADJ-004: audit_record_ref 无文件路径偏移量 | **Intentional** — P15 不做 public tombstone reader |
| AGG-ADJ-005: OR-based idempotency delete SQL | **Verified safe** — event_sequence 为 AUTOINCREMENT 全局唯一，不可能跨 Session 误删 |

## Independent Adversarial Pass

### 1. Tombstone Schema ✅

```
host_purge_tombstones (
  tombstone_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,          -- 无 FK 约束
  ...
  audit_record_ref TEXT NOT NULL,    -- 保证 no audit-pending success path
  ...
)
CREATE UNIQUE INDEX ... ON host_purge_tombstones(session_id)
```

- 无 FK 到 event_log / host_sessions（已通过 schema test 验证）
- session_id UNIQUE index 保证一个 Session 最多一个 tombstone
- audit_record_ref NOT NULL 强制 audit-before-tombstone 执行顺序

### 2. Delete Matrix FK-Safe Order ✅

```
audit_sink_markers (FK event_id)
  → outbox_drain_idempotency / outbox_terminal_items (FK event_id, session_id)
  → tool_trace_hot (FK event_id, session_id)
    → memory_diagnostics / memory_items / memory_snapshots (FK event_id, session_id)
    → run_results / session_timeline_items (FK event_id, session_id)
      → projection checkpoints/failures (exact reset by event_id + consumer whitelist)
      → old command idempotency (FK created_event_id/sequence)
        → wait_records (FK event_id, session_id)
          → dispatch_records (FK run_id)
            → attempts (FK run_id)
              → runs (child-before-parent via source_run_id leaf-deletion loop)
                → session_slots (FK session_id)
                  → session (PK)
                    → event_log (PK)
                      → unreferenced payload descriptors → sqlite payloads
```

- 全部在 `PRAGMA foreign_keys=ON` 下通过
- child-before-parent 循环最坏 O(n²)，对低频 purge 操作无实际性能风险
- Payload cleanup 扫描 8 个 durable 表的 payload ref 列做 ref-count 验证

### 3. Idempotency Replay (6-path) ✅

```
PROCEED_TO_PURGE    ← tombstone 不存在 + idempotency 不存在
REPLAY_TOMBSTONE    ← tombstone 存在 + 同 key/digest；或 idempotency 存在 + tombstone 有效
IDEMPOTENCY_CONFLICT ← 同 key + 不同 digest
ALREADY_PURGED_CONFLICT ← 不同 key + tombstone 已存在
DURABLE_INCONSISTENCY ← idempotency 存在但 result_kind 不匹配或 tombstone 缺失
```

- Semantic digest 仅含 session_id/reason/operation_context/request_context，不含 timestamp
- Tombstone-only replay: `_decision_for_existing_tombstone` 在 tombstone 存在但 idempotency row 缺失时补写 idempotency 并 replay
- Tombstone id 确定性构造：`purge-tombstone-{sha256(session_id, client_request_id, semantic_digest)}`

### 4. Audit JSONL Fail-Before-Success ✅

```
同一 SQLite write transaction 内：
1. 删除矩阵
2. payload cleanup
3. _insert_tombstone_and_idempotency():
   a. build tombstone_id (deterministic)
   b. compute deleted_counts_digest
   c. audit_recorder.record_purge_tombstone_audit()  ← 追加 JSONL line
   d. validate audit result
   e. insert_purge_tombstone()
   f. record_idempotent_result()
4. 返回 PurgeSessionDeleteResult
```

- Audit append 在 tombstone insert 之前 → 失败则 transaction rollback → 全部 deletes 回滚
- Retry 时 `_jsonl_contains_line` dedup: 同 tombstone_id + 同 digest → skip append → tombstone 写入成功
- Source key guard: 同 source key + 不同 digest → 抛出 HostDurableError 防冲突
- audit_record_ref 为 NOT NULL，SQLite 约束保证 tombstone 没有 audit ref 无法存在

### 5. Recovery / Dispatch Hardening ✅

三个 guard 点防止对已 purge Session 重激活：

| Location | Guard | Effect |
|---|---|---|
| `recovery.py:242` | `read_session_by_id(transaction, run.session_id) is None` | 返回 NOT_FOUND，不进 recovery 分类 |
| `dispatch.py:2166-2170` | `session_exists` 条件加入 `_is_dispatchable_recheck` | lane acquired 后 recheck 拒绝已 purge Session |
| `dispatch.py:3167` | `read_session_by_id(transaction, session_id) is None` guard | queue promotion 拒绝已 purge Session |

### 6. Read-after-Purge ✅

- `get_session`、`get_run`、`retry_run`、`replay_run` 全部 test-verified 返回 `NOT_FOUND`
- read_api.py 无需变更 — Session/Run rows 物理删除后现有 `NOT_FOUND` 路径自然覆盖
- 不同 request id 对已 purge Session 返回 `CONFLICT`

### 7. Public API Integrity ✅

- `PurgeSessionRequest` / `PurgeSessionResult` envelope 不变
- 不新增 public error code（使用现有 NOT_FOUND / CONFLICT / INVALID_STATE / IDEMPOTENCY_CONFLICT / INTERNAL_ERROR）
- Closed-handle guard 保持（`_raise_if_closed()` 在 purge 入口第一行）
- Error mapping:
  - `PurgeSessionInvalidStateError` → `INVALID_STATE`
  - `PurgeSessionNotFoundError` → `NOT_FOUND`
  - `PurgeSessionAlreadyPurgedError` → `CONFLICT`
  - `HostIdempotencyConflictError` → `IDEMPOTENCY_CONFLICT`
  - `OSError / RuntimeFileLockError` → `INTERNAL_ERROR` + retryable
  - 其他 `HostDurableError` → `INTERNAL_ERROR`

### 8. Layering / Import Boundary ✅

- `dayu/host/durable/purge.py` 只依赖 `dayu.host.durable.*` 和 `dayu.contracts.json_value`
- PurgeTombstoneAuditRecorder Protocol: purge durable 定义写入端口，command layer 提供实现（`_PurgeAuditJsonlRecorder`）
- purge durable 不 import command/audit/dispatch/open_host/recovery（test_import_boundary 验证）
- `dayu/engine/`、`dayu/service/`、`dayu/ui/`、`dayu/fins/` 零变更

### 9. Code Quality ✅

- 所有新增 module/class/function 提供完整中文 docstring
- 无 `object`、`Any`、裸 `dict/list/set` 签名
- 无 `hasattr`/`getattr` 逃避类型边界
- 魔法数字全部模块级常量
- 禁止兼容性代码
- Pyright 全量: 0 errors

### 10. Test Coverage ✅

Purge session 专项测试 26 cases 覆盖：
- Tombstone round-trip codec
- 6-path idempotency replay（PROCEED / REPLAY / CONFLICT × 2 / INCONSISTENCY × 2）
- Delete matrix with replay
- Audit failure rollback（fail-before-success）
- Public API: JSONL append + audit failure
- Multiprocess cross-process read paths
- Precondition rejection: open Session, all 6 non-terminal Run statuses, active wait
- Unsupported projection consumer rejection（checkpoint + failure, with rollback）
- Missing Session → NOT_FOUND

加上 11 个 modified test files 的 guard/regression 测试。

### 11. Project Instructions Compliance ✅

逐项对照 CLAUDE.md 硬约束：

| 约束 | 状态 |
|---|---|
| 分层架构 UI→Service→Host→Engine | ✅ 无反向依赖 |
| dayu.runtime 不得 import 上层 | ✅ 无变更 |
| 财报存取通过 dayu.fins.storage | ✅ 无关 |
| 函数完整中文 docstring | ✅ |
| 禁止 object/Any/无类型签名 | ✅ |
| 禁止胶水 seam/lazy import | ✅ |
| 禁止魔法数字/字符串 | ✅ |
| 禁止兼容性代码 | ✅ |
| 禁止 god object/function/dataclass | ✅ purge.py 职责单一 |
| schema 按全新起库 | ✅ schema v14 fresh bootstrap |
| 测试 ≥ 80% 覆盖率 | ✅ |
| pyright 0 errors | ✅ |
| README 同步 | ✅ |

## Residual Observations (Non-blocking)

以下为独立复核中注意到的细微点，均不构成 blocker，仅供后续参考：

1. **`_delete_old_idempotency_records` OR-based SQL 安全性**：MiMo INFO-04 曾关注 OR 条件可能过度删除。独立复核确认 `event_sequence` 为 `INTEGER PRIMARY KEY AUTOINCREMENT`（全局唯一），`created_event_sequence IN (purged_sequences)` 不可能匹配其他 Session 的 idempotency 记录。该设计是安全的。

2. **`_jsonl_contains_line` 全文件扫描**：每次 purge 需要线性扫描 audit JSONL 做 dedup。对大型 JSONL 文件有性能影响，但 purge 是低频操作，且 audit JSONL rotation/compaction 已明确列为 follow-up non-goal。当前行为正确。

3. **Projection rebuildable consumer 白名单同步**：`_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS` 在 purge.py:131 硬编码 5 个 consumer。新增 rebuildable consumer 时需同步更新，否则 purge 会抛出 `HostDurableError` 阻止删除。建议在 purge.py 模块 docstring 中注明此约束。

## Conclusion

**PASS — No blocker.**

Phase 15 PR #74 实现完整、测试充分、分层边界清晰、无已知回归。所有 release-blocking 契约已满足：

- Purge tombstone schema/codec/idempotency replay
- FK-safe delete matrix with payload ref-count cleanup
- Public purge_session command with error mapping
- Read-after-purge: physical deletion → NOT_FOUND
- Audit JSONL fail-before-success with dedup
- Recovery/dispatch hardening (3 session_exists guards)
- 1010 tests passed, pyright 0 errors
- All non-goals preserved

Draft PR 可进入 ready-to-open-draft-PR gate。
