# Phase 15 PR 74 Review (MiMo)

- **Gate**: Phase 15 draft PR review
- **PR**: [#74](https://github.com/noho/dayu-agent-r/pull/74) — Host Phase 15 retention purge hardening
- **Base**: `main` (`ea0db2cd`)
- **Head**: `feat/host-phase15-retention-purge-hardening` (`3cf1c1e5`)
- **Date**: 2026-05-29
- **Role**: AgentMiMo PR review specialist
- **Scope**: Full PR diff; verify against Phase 15 design, slice reviews, aggregate review

## Verdict

**PASS** — 无 blocker，无 new major findings。PR 具备 merge readiness。

## PR Summary

| Metric | Value |
|--------|-------|
| Changed files | 78 |
| Lines added | +14,311 |
| Lines removed | -126 |
| Production code files | 9 (`dayu/host/`) |
| Test files | 14 (`tests/host/`) |
| Review/plan artifacts | 55 (`docs/`) |

## Core Production Changes

| File | Lines | Nature |
|------|-------|--------|
| `dayu/host/durable/purge.py` | +2635 | **New**: tombstone codec, delete matrix, idempotent replay |
| `dayu/host/durable/projection.py` | +192 | Projection reset for deleted events |
| `dayu/host/command.py` | +164 | Public `purge_session` command wiring |
| `dayu/host/audit.py` | +218 | Purge tombstone audit JSONL line |
| `dayu/host/open_host.py` | +75 | Public `Host.purge_session()` method |
| `dayu/host/durable/schema.py` | +51 | Tombstone DDL, schema version 13→14 |
| `dayu/host/dispatch.py` | +11 | Session-exists dispatch guard |
| `dayu/host/recovery.py` | +3 | Session-missing recovery guard |
| `dayu/host/README.md` | +10/-1 | Purge contract documentation |

## Design Assessment

### Architecture Alignment

- **分层正确**: `purge.py` (durable) → `command.py` (command) → `open_host.py` (opener) 符合 `Engine → Host → Service` 分层。
- **无反向依赖**: `purge.py` 不 import `command.py` / `open_host.py`；audit recorder 通过 Protocol 注入。
- **公共契约**: `purge_session(host, session_id, request)` 使用直接传参的朴素接口，符合设计约束。
- **Host 强约束**: purge 只允许 CLOSED session + terminal runs，前置条件不满足时 `INVALID_STATE`，不部分删除。

### Correctness

| Item | Status | Detail |
|------|--------|--------|
| FK-safe delete matrix | PASS | 按 FK 依赖顺序删除 20+ 表；子 Run 先于父 Run |
| Idempotent replay | PASS | 同 key 同 digest → tombstone replay；同 key 不同 digest → `IDEMPOTENCY_CONFLICT`；不同 key → `ALREADY_PURGED_CONFLICT` |
| Fail-closed after purge | PASS | `get_session`/`get_run`/`retry_run`/`replay_run`/watch 均返回 `NOT_FOUND` |
| Audit-before-delete | PASS | audit JSONL 写入失败 → 事务回滚，不留下 tombstone |
| Shared artifact safety | PASS | `_payload_ref_is_still_referenced` / `_sqlite_payload_is_still_referenced` 只删除无其它引用的 payload |
| Projection reset safety | PASS | 白名单 consumer 可 reset；非白名单 consumer 引用目标 EventLog 时抛出 `HostDurableError` |
| Dispatch/recovery hardening | PASS | dispatch recheck 和 recovery scan 均检查 session 存在性 |

### Stability

| Item | Status | Detail |
|------|--------|--------|
| Rollback on failure | PASS | audit/tombstone/idempotency 写入失败均回滚删除矩阵 |
| Schema migration | PASS | 版本 13→14，新增 `host_purge_tombstones` 表与索引 |
| No regression | PASS | 1011 tests passed, 1 skipped |
| Pyright clean | PASS | 0 errors, 0 warnings on all changed files |

### Maintainability

| Item | Status | Detail |
|------|--------|--------|
| Module boundary | PASS | `purge.py` 独立模块，不泄漏到非目标层 |
| Type safety | PASS | 全部 dataclass 使用 `frozen=True, slots=True`；无 `Any`、无 `object` |
| Docstring | PASS | 全部公共函数/类提供完整中文 docstring |
| Naming | PASS | 常量命名清晰；无魔法数字/字符串（schema literal 例外） |

## Findings

### INFO-01: `_in_clause` 在 `projection.py` 与 `purge.py` 中各有一份实现

**Severity**: INFO

两个模块各有私有 `_in_clause` helper，签名不同：
- `projection.py`: `tuple[str, ...]` (仅文本)
- `purge.py`: `tuple[str | int, ...]` (文本 + 整数)

两者都是模块私有、单点调用、行为一致。`projection.py` 的版本还配合 `_placeholders` 支持 `NOT IN` 子句。当前设计可接受，不需要合并。

### INFO-02: `_delete_old_idempotency_records` 使用 OR 组合删除

**Severity**: INFO

删除条件为 `event_id IN (...) OR event_sequence IN (...) OR (scope_id = ? AND scope_kind IN (...))`。参数拼接使用元组相加，语义正确。三条 OR 分支分别覆盖：
1. 指向目标 EventLog 的幂等记录（按 event_id）
2. 指向目标 EventLog 的幂等记录（按 event_sequence）
3. 目标 Session scope 下的 session fact 幂等记录

这是预期行为——purge 要删除所有与被清理事实关联的旧幂等记录。

### INFO-03: `_delete_runs_child_before_parent` 使用迭代删除

**Severity**: INFO

该函数通过 while 循环逐轮删除叶子 Run（无子 Run 引用的 Run），直到全部删除。如果 Run source 依赖图存在环（理论上不可能，因为 `source_run_id` 是有向边），会抛出 `HostDurableError`。当前 schema 不会产生环，设计合理。

## Test Coverage

| Category | Tests | Status |
|----------|-------|--------|
| Purge durable core | 26 | PASS |
| Projection checkpoint/reset | 10+ | PASS |
| Projection read model | 10+ | PASS |
| Recovery scan | 10+ | PASS |
| Audit sink | 10+ | PASS |
| Public session API | 5+ | PASS |
| Public run API | 10+ | PASS |
| Import boundary | 3 | PASS |
| Package exports | 3 | PASS |
| Weak typing guard | 1 | PASS |
| **Total host tests** | **1011** | **PASS** |

### Key Test Scenarios Verified

- [x] Purge deletes full matrix (20+ table categories)
- [x] Idempotent replay preserves tombstone
- [x] Same key + different digest → conflict
- [x] Different key + already purged → conflict
- [x] Open session → `INVALID_STATE`
- [x] Non-terminal run (6 statuses) → `INVALID_STATE`
- [x] Active wait → `INVALID_STATE`
- [x] Unsupported projection consumer → rollback
- [x] Audit append failure → rollback
- [x] Public audit JSONL append + tombstone ref
- [x] Public audit failure → `INTERNAL_ERROR`, retryable
- [x] Multiprocess purge + read-after-purge fail-closed
- [x] Shared payload preserved, unique payload deleted
- [x] Artifact cleanup refs collected for post-commit file IO
- [x] Session-missing guard in recovery scan
- [x] Session-exists guard in dispatch recheck

## Docs Assessment

| README | Updated? | Correct? |
|--------|----------|----------|
| `dayu/host/README.md` | YES | PASS — purge contract documented, deferred note removed |
| `tests/README.md` | YES | PASS — test fact sync |
| `dayu/README.md` | No change needed | N/A — no architecture boundary change |
| Root `README.md` | No change needed | N/A — no CLI/user-facing change |

## Resolved Slice/Aggregate Findings Reference

- AGG-ADJ-001 (dead code `PurgePreconditionSnapshot`): **FIXED** — confirmed removed
- AGG-ADJ-002 (fail-before-success design): **ACCEPTED** — covered by rollback tests
- AGG-ADJ-003 (retryable error code): **ACCEPTED** — no finer taxonomy needed
- AGG-ADJ-004 (no public tombstone reader): **ACCEPTED** — intentional P15 scope
- AGG-ADJ-005 (low-frequency purge perf): **ACCEPTED** — correctness unaffected

## Residual Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Purge 操作频率极低，生产验证不足 | Low | 设计为幂等 + 冲突检测；multiprocess smoke 测试覆盖 |
| Audit JSONL 无 rotation/compaction | Low | 已明确为 non-goal；不影响 purge 正确性 |
| `_delete_runs_child_before_parent` 理论上可能多轮 | Low | Run source 依赖图深度有限；异常时抛错回滚 |

## Conclusion

PR 74 实现完整、测试充分、架构合规。核心 purge durable primitive 设计严谨：FK-safe 删除矩阵、幂等 replay、fail-closed 语义、audit-before-delete 模式均已验证。全量 1011 host tests 通过，pyright 0 errors。无 blocker，**建议 merge**。
