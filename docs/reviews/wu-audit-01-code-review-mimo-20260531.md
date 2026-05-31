# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-purge-audit-reconciliation`
- Base: `main`
- Output file: `docs/reviews/wu-audit-01-code-review-mimo-20260531.md`
- Included scope:
  - `dayu/host/audit.py` — purge audit line builders, append helpers, source key idempotency, marks helper
  - `dayu/host/command.py` — `purge_session` orchestration, started/failed/completed ordering, retry path
  - `dayu/host/durable/purge.py` — tombstone helpers, `PurgeSessionDeleteRequest` refactor, audit recorder removal
  - `dayu/host/api.py` — `PurgeSessionResult` docstring update
  - `tests/host/test_purge_session.py` — purge session integration tests
  - `tests/host/test_audit_sink.py` — audit line builder/append unit tests
  - `tests/host/test_package_exports.py` — export boundary tests
  - Accepted plan: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
  - Implementation report: `docs/reviews/wu-audit-01-slice1-implementation-codex-20260531.md`
  - Design source: `docs/host/design.md`
- Excluded scope: README updates (per controller禁令), general audit analyze/query API (non-goal)
- Parallel review coverage: 4 parallel subagents reviewed audit.py, command.py, durable/purge.py, and tests respectively

## Findings

未发现实质性问题。

以下是对 plan correctness requirements 的逐项 evidence-based 验证：

### Correctness Verification: purge_started 不表示完成

- **入口**: `audit_json_line_marks_purged_source_eventlog_facts`
- **文件**: `dayu/host/audit.py` (marks helper)
- **直接证据**: 该函数检查 `line_kind == "purge_completed"` AND `source_eventlog_facts_purged is True`。`purge_started` builder 设置 `source_eventlog_facts_purged=False`，`purge_failed` 同理。`line_kind` guard 确保只有 `purge_completed` 能通过。
- **测试**: `test_purge_audit_lines_are_append_only_and_only_completed_marks_purged` (test_audit_sink.py) 直接断言 `marks(started_line) is False` 和 `marks(failed_line) is False`。

### Correctness Verification: purge_completed 仅在 tombstone commit 后写入并引用 tombstone digest

- **入口**: `purge_session` → `append_purge_completed_audit_record`
- **文件**: `dayu/host/command.py` L843-850
- **直接证据**: completed append 在 `host._transaction_runner().run_write(operation)` 之后（L811-817），SQLite commit 已完成。`PurgeCompletedAuditRecordRequest` 接收 `result.tombstone`（committed tombstone row）。`build_purge_completed_audit_json_line` 从 tombstone 读取 `audit_record_ref`/`audit_record_digest`（指向 started line），并通过 `build_purge_tombstone_digest(tombstone)` 计算 tombstone digest。
- **测试**: `test_public_purge_session_appends_tombstone_audit_jsonl` (test_purge_session.py) 断言 `completed_line["purge_tombstone_digest"] == build_purge_tombstone_digest(tombstone)` 和 `tombstone.audit_record_ref == started_line["audit_record_ref"]`。

### Correctness Verification: SQLite 失败无 completed

- **入口**: `purge_session` exception handlers
- **文件**: `dayu/host/command.py` L818-842
- **直接证据**: 四个 except 分支（`PurgeSessionInvalidStateError`、`PurgeSessionAlreadyPurgedError`、`PurgeSessionNotFoundError`、`HostDurableError`）均在 completed append 之前触发，调用 `_append_purge_failed_best_effort` 后 raise。completed append 只在 try 块成功后执行。
- **测试**: `test_public_purge_session_sqlite_failure_writes_started_and_no_completed` (test_purge_session.py) 使用 BEFORE INSERT trigger 注入失败，断言 `line_kinds == ("purge_started", "purge_failed")`，无 `purge_completed`，`tombstone is None`，`event_count == 12`（rollback proof）。

### Correctness Verification: idempotent replay 无条件尝试 completed 且不扫描 JSONL

- **入口**: `purge_session` L843-850
- **文件**: `dayu/host/command.py`
- **直接证据**: `append_purge_completed_audit_record` 在 transaction 之后无条件执行，不检查 `result.idempotent_replay`。JSONL 去重依赖 `_append_purge_audit_json_line` 的 source key `(line_kind, purge_attempt_ref)` 组合匹配（`_jsonl_contains_line` 使用 `all()` 语义）。不读取、不扫描 JSONL。
- **测试**: `test_public_purge_session_completed_append_failure_retries_completed` (test_purge_session.py) 验证：第一次 completed append 失败 → retryable error；第二次同 key retry → tombstone replay → 无条件 completed append（source key 幂等去重）→ 最终 JSONL 恰好 1 条 started + 1 条 completed。

### Correctness Verification: 不引入通用 audit analyze/query API

- **直接证据**: diff 中无新增通用 audit 查询、分析或 reconciliation report 函数。新增的 `_base_purge_audit_fields`、`_purge_audit_record_ref`、`_validate_purge_*_request`、`_bounded_failure_message` 均为 purge 专用私有 helper。`__all__` 中无通用 audit analyze/query 导出。

### Correctness Verification: durable schema 不变

- **直接证据**: diff 中无 `dayu/host/durable/schema.py` 修改。`host_purge_tombstones` DDL 未变。`PurgeTombstoneRow` 字段集不变。`audit_record_ref`/`audit_record_digest` 语义从 "purge tombstone audit" 更新为 "purge_started audit line"，通过 docstring 说明。

### Architecture Verification: durable 层不 import dayu.host.audit

- **直接证据**: `dayu/host/durable/purge.py` 的 import 列表中无 `dayu.host.audit`。`audit.py` import `purge.py`（`PurgeTombstoneRow`、`build_purge_attempt_ref`、`build_purge_tombstone_digest`），方向正确（audit → durable，非反向）。

### Source Key Idempotency: `all()` 语义变更

- **入口**: `_jsonl_contains_line`
- **文件**: `dayu/host/audit.py`
- **变更**: source key 匹配从"任一 key 命中即冲突"改为"全部 key 命中才冲突"。
- **正确性**: 对 EventLog audit 投影（单 source key `event_id`），`all()` over 1-tuple 语义等价。对 purge audit（组合 source key `(line_kind, purge_attempt_ref)`），`all()` 是必须的：旧 `any()` 语义下，`purge_started` 和 `purge_completed` 共享 `purge_attempt_ref`，会互相冲突，无法写入同一 attempt 的不同 line kind。

### pyright / 测试真实性

- `source .venv/bin/activate && pyright`: **0 errors, 0 warnings, 0 informations**（已验证）。
- `source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_audit_sink.py tests/host/test_package_exports.py -q`: **46 passed**（已验证）。
- 测试使用真实 SQLite durable store（`open_host_durable_store`）和真实 JSONL 文件，非 mock durable store。monkeypatch 仅用于窄范围 failure injection（completed append 失败），且在 retry 前 `undo()`。

## Open Questions

无。

## Residual Risk

- `purge_failed` 是 best-effort 诊断；如果 failed append 自身失败，command path 只记录 warning，不替换原始 durable/API 错误。这是 plan 明确接受的设计决策（Section 2.5）。
- 本轮未更新 README（per controller 禁令）。当前 README 若仍描述旧 `purge_tombstone` audit line，需后续 slice 同步。
- `operation_context_digest` 在 `_PurgeAuditInputs` 中类型为 `str`（非 `str | None`），但 `PurgeSessionDeleteRequest` 中为 `str | None`。当前 `_PurgeAuditInputs` 总是传入非 None 值（由 `sha256_digest_json` 产生），类型不一致但无运行时风险。
