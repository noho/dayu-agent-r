# Phase 15 P15-S1 Re-review Artifact (AgentDS)

## Gate

- Work unit: Phase 15 retention purge production hardening
- Current gate: Phase 15 S1 re-review
- Source reviews: `phase15-s1-code-review-ds-20260529.md`, `phase15-s1-code-review-mimo-20260529.md`
- Controller adjudication: `phase15-s1-code-review-controller-adjudication-20260529.md`
- Fix artifact: `phase15-s1-fix-codex-20260529.md`
- Output: `phase15-s1-rereview-ds-20260529.md`

## Scope

仅验证 accepted findings S1-ADJ-001 和 S1-ADJ-002 是否已修复。不引入无关发现，不检查 scope 合规性（已在原始 review 中通过）。

---

## Finding Status

### S1-ADJ-001: 已修复

**来源**: DS review F1 — `_decision_for_existing_tombstone` 中 `HostIdempotencyConflictError` 误分类为 `IDEMPOTENCY_CONFLICT`

**修复验证**:

| 要求 | 状态 | 证据 |
| --- | --- | --- |
| `HostIdempotencyConflictError` → `DURABLE_INCONSISTENCY` | ✅ | `purge.py:546-552`: `kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY` |
| 保留正常 replay 路径 | ✅ | `purge.py:553-558`: try 成功后返回 `REPLAY_TOMBSTONE` |
| 新增 focused test | ✅ | `test_purge_session.py:455-475`: `_SeedTombstoneWithConflictingIdempotencyOperation` 构造 tombstone + 冲突 idempotency row，断言 `DURABLE_INCONSISTENCY` |

**代码差异** (purge.py:546-552):

```python
# 修复前:
except HostIdempotencyConflictError:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.IDEMPOTENCY_CONFLICT,  # 误分类
        ...
    )

# 修复后:
except HostIdempotencyConflictError:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY,  # 正确
        ...
    )
```

**测试覆盖**: `test_tombstone_same_key_same_digest_with_conflicting_idempotency_is_inconsistent` — 先写入 tombstone（digest_A），再写入同 scope/key 但 digest_B 的幂等 row，然后以 digest_A 请求 replay，断言 `DURABLE_INCONSISTENCY`、tombstone 存在、idempotency_record 为 None。

---

### S1-ADJ-002: 已修复

**来源**: DS review F2 — 缺少 `_validate_tombstone` 和 `_validate_delete_counts` 拒绝路径测试

**修复验证**:

| 要求 | 状态 | 证据 |
| --- | --- | --- |
| negative delete counts | ✅ | `test_purge_session.py:478-482`: `replace(_counts(), event_log_rows=-1)` → `HostDurableError` |
| mismatched `deleted_counts_digest` | ✅ | `test_purge_session.py:485-495`: `replace(_tombstone(), deleted_counts_digest=_DIGEST_A)` → `HostDurableError` |
| unpaired `audit_record_ref` (ref-only) | ✅ | `test_purge_session.py:498-513`: `replace(_tombstone(), audit_record_ref="audit-record-1")` → `HostDurableError` |
| unpaired `audit_record_digest` (digest-only) | ✅ | `test_purge_session.py:498-513`: `replace(_tombstone(), audit_record_digest=_DIGEST_A)` → `HostDurableError` |

**生产代码**: 未新增修改。`dataclasses.replace` 的 import 是测试文件唯一的新增依赖，未扩散到生产代码。

---

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
# 30 passed in 0.39s (原始: 26 passed; +4 新增测试)

source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py
# 0 errors, 0 warnings, 0 informations
```

新增 4 个测试:
1. `test_tombstone_same_key_same_digest_with_conflicting_idempotency_is_inconsistent` (S1-ADJ-001)
2. `test_deleted_counts_digest_rejects_negative_counts` (S1-ADJ-002)
3. `test_insert_tombstone_rejects_mismatched_deleted_counts_digest` (S1-ADJ-002)
4. `test_insert_tombstone_rejects_unpaired_audit_record_ref` (S1-ADJ-002)

---

## New Blocker Check

无新增 blocker:
- 生产代码改动仅 1 行（error kind 映射），不改变控制流或公共接口。
- 测试代码改动仅新增 4 个测试 + `dataclasses.replace` import，不修改已有测试断言。
- Pyright 0 错误，30 测试全部通过。
- 无 scope 扩散（未触及 public command、EventLog 删除、audit JSONL）。

---

## Status Summary

| Finding | 状态 |
| --- | --- |
| S1-ADJ-001 | 已修复 |
| S1-ADJ-002 | 已修复 |

**Verdict: PASS**

两个 accepted findings 均已通过代码变更和 focused 测试完整修复。Validation 充分（30 passed, pyright 0 errors）。无新增 blocker。
