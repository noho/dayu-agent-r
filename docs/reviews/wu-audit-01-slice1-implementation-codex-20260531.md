# WU-AUDIT-01 Integrated Implementation Report

## Scope

- 执行范围：Slice 1 durable purge purge_started ref/digest 持久化，加 controller 裁决后的最小 end-to-end audit 闭环（原 Slice 2 + Slice 3）。
- 未修改 README、总控文档、通用 audit analyze/query API、reconciliation report、durable schema 或 public result fields。
- 未 commit、未 push、未创建 PR。

## Changed Files

- `dayu/host/durable/purge.py`
- `dayu/host/audit.py`
- `dayu/host/command.py`
- `dayu/host/api.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_package_exports.py`
- `docs/reviews/wu-audit-01-slice1-implementation-codex-20260531.md`

## Implemented Items

- durable purge 不再接收或调用 audit recorder；`PurgeSessionDeleteRequest` 改为接收 `started_audit_record_ref` / `started_audit_record_digest`。
- 新增 durable helper：`build_purge_tombstone_id`、`build_purge_attempt_ref`、`build_purge_tombstone_digest`。
- `audit.py` 新增 `purge_started` / `purge_completed` / `purge_failed` request、builder 与 append helper；`schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest` 均由 builder 派生。
- purge audit JSONL source key 改为组合 `(line_kind, purge_attempt_ref)`，同一 attempt 的 started/completed/failed 可各写一条，重复 append 依赖 source key 幂等。
- `audit_json_line_marks_purged_source_eventlog_facts(...)` 只在 `line_kind == "purge_completed"` 且 `source_eventlog_facts_purged is True` 时返回 `True`。
- `purge_session(...)` 编排顺序改为：transaction 前 append started；SQLite transaction 失败后 best-effort append failed；SQLite commit 后 append completed；idempotent replay 仍无条件尝试 completed append，不扫描 JSONL。
- completed append 失败返回 retryable `HostApiError`；同 key retry 通过 tombstone replay 补写 completed。
- 测试覆盖 started/failed 不被误判为 completed、completed 引用 committed tombstone digest、SQLite failure 无 completed、completed append failure 后 retry 补写。
- DS review F-01/F-02 fix：`_append_purge_failed_best_effort(...)` 改为显式接收 `failure_stage`，各 catch 分支传稳定 stage，避免所有失败都被误标为 SQLite transaction；SQLite trigger 失败仍断言为 `sqlite_purge_transaction`。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_purge_session.py -q`
  - 通过：`28 passed`
- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py -q`
  - 通过：`8 passed`
- `source .venv/bin/activate && pytest tests/host/test_package_exports.py -q`
  - 通过：`10 passed`
- `source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_audit_sink.py tests/host/test_package_exports.py -q`
  - 通过：`46 passed`
- `source .venv/bin/activate && pyright`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过。

## Residual Risks

- `purge_failed` 是 best-effort 诊断；如果 failed append 自身失败，command path 只记录 warning，不替换原始 durable/API 错误。
- 本轮按 controller 禁令未更新 README；当前 README 若仍描述旧 purge tombstone audit line，需要由后续允许文档修改的 slice 同步。
- durable schema 未变更，`host_purge_tombstones.audit_record_ref/audit_record_digest` 现在语义为 started audit line ref/digest。
