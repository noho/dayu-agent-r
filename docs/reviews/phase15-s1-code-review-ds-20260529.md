# Phase 15 P15-S1 Code Review Artifact (AgentDS)

## Gate

- Work unit: Phase 15 retention purge production hardening
- Current gate: Phase 15 S1 code review
- Review slice: P15-S1 Purge Tombstone Schema And Durable Primitives
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Implementation artifact: `docs/reviews/phase15-s1-implementation-codex-20260529.md`
- Review output: `docs/reviews/phase15-s1-code-review-ds-20260529.md`

## Scope Adherence

P15-S1 scope per plan:
- Bump `HOST_SCHEMA_VERSION` 13 → 14
- Add `host_purge_tombstones` table, index, DDL, table set membership
- Implement typed dataclasses: `PurgeTombstoneRow`, `PurgeDeleteCounts`, `PurgePreconditionSnapshot`, `PurgeReplayDecision`/`PurgeReplayDecisionKind`
- Implement helpers: tombstone read/insert, semantic digest, deleted counts digest, idempotency replay
- Reuse `IdempotencyStore` with NULL `created_event_id`/`created_event_sequence`

Verified: implementation **does not** delete Session/EventLog facts, does not implement public `purge_session`, does not write audit JSONL. Scope boundary is respected.

## Review Summary

| Dimension | Result |
| --- | --- |
| Tests | 26 passed, 0 failed |
| Pyright | 0 errors, 0 warnings, 0 informations |
| Schema correctness | PASS |
| FK invariants | PASS (no FK to event_log or host_sessions) |
| Idempotency replay semantics | PASS with 1 medium finding |
| Strict typing | PASS (no `Any`/`object`/untyped signatures) |
| Chinese docstrings | PASS |
| Plan compliance | PASS with 1 deviation noted |

## Findings

### F1 [Medium] `_decision_for_existing_tombstone` 错误地将 durable inconsistency 映射为 `IDEMPOTENCY_CONFLICT`

**文件**: `dayu/host/durable/purge.py:539-552`

**证据**:

```python
# purge.py:519-552
if scope.idempotency_key != tombstone.client_request_id:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.ALREADY_PURGED_CONFLICT, ...
    )
if semantic_request_digest != tombstone.semantic_request_digest:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT, ...
    )
# ... digest 已确认匹配 tombstone ...
try:
    record = IdempotencyStore().record_idempotent_result(
        transaction, scope, semantic_request_digest, result,
    )
except HostIdempotencyConflictError:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT,  # <-- 问题
        ...
    )
```

**分析**: `record_idempotent_result` 仅在已存在同 scope/key 但 **不同** `semantic_input_digest` 的记录时抛出 `HostIdempotencyConflictError`。但此时我们已经验证了 `semantic_request_digest == tombstone.semantic_request_digest`（第 526 行），所以当前请求的 digest 与 tombstone 一致。idempotency 表中已存在的记录持有第三个不同的 digest，这意味着 durable 状态不一致（tombstone 说 digest_A，idempotency 表说 digest_B）。这是 `DURABLE_INCONSISTENCY`，不应报告为 `IDEMPOTENCY_CONFLICT`。报告为 `IDEMPOTENCY_CONFLICT` 会误导调用方以为自己的请求 digest 不匹配，而实际问题是 DB 内部不一致。

**计划依据**: 计划 Section "Idempotency Design" 第 3 条："Tombstone 存在但 purge idempotency row 缺失时……若 request `client_request_id` 与 tombstone row 相同且 semantic digest 相同，返回 tombstone replay result；不得为了 replay 重建 Session facts。" 当前实现在 race/bug 导致 idempotency 表出现第三方 digest 时返回了 `IDEMPOTENCY_CONFLICT` 而非 `DURABLE_INCONSISTENCY`，偏离了"同 key 同 digest 应 replay"的语义。

**影响**: 在 S1 范围内此路径不可达（没有 delete path，不会产生 tombstone + 冲突 idempotency 的组合），但在 S2 引入 delete 后可能由并发或 bug 触发。错误类型会误导上层 error mapper。

**建议修复**:
```python
except HostIdempotencyConflictError:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY,
        tombstone=tombstone,
        idempotency_record=None,
        message=_DECISION_MESSAGE_DURABLE_INCONSISTENCY,
    )
```

### F2 [Low] 缺少 `_validate_tombstone` 和 `_validate_delete_counts` 拒绝路径的测试覆盖

**文件**: `tests/host/test_purge_session.py`

**证据**: 测试文件中没有针对以下场景的测试用例：
- `PurgeDeleteCounts` 包含负数 → `_validate_delete_counts` 应抛出 `HostDurableError`
- `PurgeTombstoneRow.deleted_counts_digest` 与实际 counts 不匹配 → `_validate_tombstone` 应抛出 `HostDurableError`
- `audit_record_ref` 和 `audit_record_digest` 不配对 → `_validate_tombstone` 应抛出 `HostDurableError`

**分析**: `_validate_tombstone` (purge.py:827-879) 和 `_validate_delete_counts` (purge.py:791-824) 包含重要的数据完整性校验，但测试仅覆盖了 happy path。如果未来有人重构这些校验函数，缺少拒绝路径测试可能导致退化。

**影响**: 低。校验逻辑简单且由类型系统部分保护，但缺少回归保护。

**建议**: 在 S2 或后续 slice 中补齐 `test_validate_tombstone_rejects_*` 和 `test_validate_delete_counts_rejects_negative` 测试用例。

### F3 [Info] `PurgePreconditionSnapshot` 在 S1 中无消费者

**文件**: `dayu/host/durable/purge.py:172-215`

**证据**: `PurgePreconditionSnapshot` 已定义完整字段，但 S1 中没有任何函数构造或读取它。实现 artifact 已声明："`PurgePreconditionSnapshot` is only a typed carrier in this slice."

**分析**: 这是符合计划的有意延期，不是 bug。S2 delete matrix slice 将添加 precondition reader 和 digest builder。

**影响**: 无。代码整洁，不会导致运行时问题。

## Positive Observations

1. **Schema 设计**: `host_purge_tombstones` 无 FK 到 `event_log` 或 `host_sessions`，使用 UNIQUE index 保证 `session_id` 唯一——精确匹配计划要求。`audit_record_ref`/`audit_record_digest` 的 CHECK 约束确保配对。

2. **Idempotency replay 算法**: `record_or_read_purge_idempotency` 的 5 层判定（tombstone 存在/不存在 × idempotency 记录存在/不存在 × digest 匹配/不匹配）完整覆盖计划中 Idempotency Design 的所有路径。`created_event_id = NULL` / `created_event_sequence = NULL` 的实现正确。

3. **Digest 稳定性**: `build_purge_semantic_digest` 输入仅包含 `operation`、`session_id`、`reason`、`operation_context_digest`、`operation_context_refs`、`request_context`——不包含 mutable DB state 或 timestamp，确保 replay 确定性。

4. **严格类型**: 所有公开函数签名使用具体类型，`Mapping[str, JsonValue]` 替代裸 `dict`，`StrEnum` 用于封闭判定类型。无 `Any`/`object`/无类型签名。

5. **中文 docstring**: 所有公开函数、类、模块均提供完整中文 docstring，包含参数、返回值、异常说明。

6. **模块级常量**: 所有 operation name、result kind、JSON key、count field name 均定义为模块级私有常量，无魔法字符串。

7. **测试质量**: 测试覆盖了 tombstone round-trip、tombstone-present + idempotency-missing replay、same-key-different-digest conflict、different-key already-purged conflict、existing idempotency conflict 等关键路径。所有测试通过且 pyright 零错误。

## Test Verification

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
# Result: 26 passed in 0.37s

source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py dayu/host/durable/schema.py tests/host/test_purge_session.py tests/host/test_durable_schema.py
# Result: 0 errors, 0 warnings, 0 informations
```

## Residual Risks

| Risk | Classification | Owner |
| --- | --- | --- |
| F1 durable inconsistency misclassified as idempotency conflict | Fix in S2/S3 before public command wiring | S2 implementation |
| F2 missing validation rejection tests | Low; add in S2 | S2 implementation |
| Public `purge_session` still throws `UNSUPPORTED_OPERATION` | By design; owned by S3 | S3 implementation |

## Verdict

**PASS** — 2 findings, 0 blocking.

F1 建议在 S2 或 S3 修复（将 `IDEMPOTENCY_CONFLICT` 改为 `DURABLE_INCONSISTENCY`），但不足以阻止 P15-S1 closeout。F2 为非阻塞测试覆盖 gap。所有硬约束（schema 正确性、FK 不变式、严格类型、pyright 零错误、计划 scope 边界）均通过。
