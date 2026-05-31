# Code Re-Review

## Scope

- Mode: current changes (re-review after DS fix)
- Branch: `feat/host-purge-audit-reconciliation`
- Base: `main`
- Prior review: `docs/reviews/wu-audit-01-code-review-mimo-20260531.md` (PASS)
- DS review with findings: `docs/reviews/wu-audit-01-code-review-ds-20260531.md` (F-01 中, F-02 低)
- Output file: `docs/reviews/wu-audit-01-code-rereview-mimo-20260531.md`
- Focus: confirm DS fix does not break prior PASS; verify README sync accuracy

## DS Fix Summary

### F-01 fix: `failure_stage` parameterized

- **Before**: `_append_purge_failed_best_effort` 内部硬编码 `failure_stage="sqlite_purge_transaction"`，所有异常类型共用
- **After**: `_append_purge_failed_best_effort` 接收 `failure_stage: str` keyword 参数，各 except 分支传入对应常量：
  - `PurgeSessionInvalidStateError` → `"precondition_check"`
  - `PurgeSessionAlreadyPurgedError` → `"already_purged"`
  - `PurgeSessionNotFoundError` → `"not_found"`
  - `HostIdempotencyConflictError` → `"idempotency_conflict"`
  - `HostDurableError` → `"sqlite_purge_transaction"`
- **验证**: 5 个常量定义于 `command.py` L137-141，5 个调用点均传入正确常量

### F-02 fix: `HostIdempotencyConflictError` 单独 catch

- **Before**: `HostIdempotencyConflictError` 被泛化 `except HostDurableError` 捕获，`failure_stage` 为 `"sqlite_purge_transaction"`
- **After**: `except HostIdempotencyConflictError` 在 `except HostDurableError` 之前单独捕获，`failure_stage` 为 `"idempotency_conflict"`
- **验证**: `command.py` L859 独立 catch，L871 的 `except HostDurableError` 不再覆盖 idempotency conflict

### README sync

- **`dayu/host/README.md`**: 旧 "purge tombstone audit record" 更新为描述三种 audit line 语义：`purge_started` 表示 attempt 已发起不表示完成；`purge_completed` 在 tombstone commit 后写入并引用 tombstone；`purge_failed` 是 best-effort 诊断；tombstone audit ref/digest 指向 started 行
- **`tests/README.md`**: 旧 "append-only audit JSONL tombstone record" 更新为 "purge_started / purge_completed / best-effort purge_failed 语义"

## Correctness Impact Assessment

DS fix 的变更范围：

1. `failure_stage` 字符串值变化 — 纯诊断标签，不影响 audit line 的 `line_kind`、`source_eventlog_facts_purged`、`purge_tombstone_ref`、`purge_tombstone_digest` 或任何 correctness 关键字段
2. `HostIdempotencyConflictError` 独立 catch — 该异常是 `HostDurableError` 子类，之前被泛化 catch 处理，现在提前 catch 并传入更准确的 `failure_stage`。最终行为不变（均 re-raise 为 `HostApiError`）
3. README — 文档同步，不影响代码行为

**对 prior PASS 结论无影响。** 所有 6 项 correctness verification（purge_started 不表示完成、purge_completed 仅在 tombstone commit 后写入、SQLite 失败无 completed、idempotent replay 无条件尝试 completed、不引入通用 audit API、durable schema 不变）均不受影响。

## README Accuracy

### `dayu/host/README.md` 准确性

- "`purge_started` 表示 purge attempt 已发起，不表示完成" — 与 `audit_json_line_marks_purged_source_eventlog_facts` 行为一致
- "`purge_completed` 只在 SQLite tombstone commit 成功后写入，并引用 tombstone id / digest" — 与 `command.py` 编排顺序一致
- "`purge_failed` 是失败路径的 best-effort 诊断" — 与 `_append_purge_failed_best_effort` 实现一致
- "tombstone 中的 audit record ref / digest 指向 `purge_started` 行" — 与 `_insert_tombstone_and_idempotency` 使用 `request.started_audit_record_ref/digest` 一致
- "purge 完成真源仍是 SQLite tombstone" — 与 design.md 和 plan 一致

### `tests/README.md` 准确性

- 旧 "append-only audit JSONL tombstone record" → 新 "purge_started / purge_completed / best-effort purge_failed 语义" — 与实际测试覆盖一致

## Validation

- `source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_audit_sink.py tests/host/test_package_exports.py -q`: **46 passed**（已验证）
- `source .venv/bin/activate && pyright`: **0 errors, 0 warnings, 0 informations**（已验证）

## Findings

未发现实质性问题。DS fix 正确修复了 F-01 和 F-02，README 同步准确。

## Open Questions

无。

## Residual Risk

- 同 prior review：`purge_failed` best-effort 自身失败仅 warning；completed append 失败后调用方不 retry 则 JSONL audit trail 不完整；README 本轮已同步
