# Phase 15 S1 Fix Artifact

## Gate

- Work unit: Phase 15 retention purge production hardening
- Current gate: Phase 15 S1 fix
- Source reviews:
  - `docs/reviews/phase15-s1-code-review-ds-20260529.md`
  - `docs/reviews/phase15-s1-code-review-mimo-20260529.md`
  - `docs/reviews/phase15-s1-code-review-controller-adjudication-20260529.md`

## Changed Files

- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s1-fix-codex-20260529.md`

## Finding Status

### S1-ADJ-001 已修复

- Accepted finding: `_decision_for_existing_tombstone(...)` 将内部 durable inconsistency 误分类为 `IDEMPOTENCY_CONFLICT`。
- Fix: `HostIdempotencyConflictError` 现在返回 `PurgeReplayDecisionKind.DURABLE_INCONSISTENCY`，message 使用 durable inconsistency 诊断。
- Test: 新增 tombstone 同 key/digest、但 idempotency 表同 scope/key 为不同 digest 的 focused test，断言返回 durable inconsistency。

### S1-ADJ-002 已修复

- Accepted finding: 缺少 tombstone validation 拒绝路径测试。
- Fix: 生产代码未发现额外 bug，未扩大修改。
- Tests:
  - negative `PurgeDeleteCounts` 拒绝；
  - `deleted_counts_digest` 与实际 counts 不匹配拒绝；
  - `audit_record_ref` / `audit_record_digest` 任一单边存在都拒绝。

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
```

Result: `30 passed in 0.40s`.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py
```

Result: `0 errors, 0 warnings, 0 informations`.

Additional hygiene:

```bash
git diff --check -- dayu/host/durable/purge.py tests/host/test_purge_session.py
```

Result: passed.

## Residual Risks

- Public `purge_session` command remains unsupported by design and is owned by later P15 slices.
- Delete matrix, precondition enforcement, audit JSONL purge line, and projection/payload cleanup remain later-slice responsibilities.
- No new residual risk introduced by this fix.

## Blocking Questions

None.

## Stop Status

Phase 15 S1 fix complete. Both accepted findings are fixed.
