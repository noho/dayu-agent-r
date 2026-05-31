# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-purge-audit-reconciliation
- Base: main
- Output file: docs/reviews/wu-audit-01-aggregate-deepreview-mimo-20260531.md
- Included scope: dayu/host/audit.py, dayu/host/command.py, dayu/host/durable/purge.py, dayu/host/api.py, dayu/host/README.md, tests/README.md, tests/host/test_audit_sink.py, tests/host/test_purge_session.py, tests/host/test_package_exports.py, docs/host/*control*, docs/host/wu-audit-01-purge-audit-reconciliation-plan.md, docs/reviews/wu-audit-01-*
- Excluded scope: dayu/engine, dayu/fins, dayu/config, dayu/ui, dayu/runtime, utils/
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Verification Summary

### Plan Artifacts

- plan (`docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`) 清晰定义了 3 个 purge audit line kind、contract decisions、transaction ordering、affected files、implementation slices、required tests 和 stop conditions。
- 非目标明确：不做通用审计分析或查询 API、不新增复杂诊断框架、不重做通用 audit pipeline、不修改 public `PurgeSessionResult` 字段、不保留旧 `purge_tombstone` 兼容 wrapper。
- 2 轮 plan review + plan re-review + controller adjudication 均已通过并记录在 `docs/reviews/wu-audit-01-plan-*`。

### Control Doc Rename / Status / Residual Risk

- `followup-implementation-control.md` 已重命名为 `host-core-followup-implementation-control.md`，内容正确更新。
- 状态已更新：gate=review, implementation status=accepted-slice-committed, active work unit=WU-AUDIT-01。
- RR-AUDIT-01（slice boundary）和 RR-AUDIT-02（docs sync）均已 closed。
- 4 份 control doc 均新增"plan 必须避免过度设计"约束。

### Implementation Correctness

1. **Transaction ordering**：`purge_session` 严格按 started -> SQLite transaction -> completed 顺序编排，与 plan Section 4 一致。
2. **Deterministic started line**：`build_purge_started_audit_json_line` 不包含 timestamp、random id 等非确定性值；同 key retry 产生相同 digest，source key 幂等去重正确。
3. **Tombstone commit 后 completed**：`append_purge_completed_audit_record` 在 SQLite commit 成功后调用，引用 committed tombstone 的 id/digest。
4. **SQLite failure no completed**：transaction 失败后 best-effort `_append_purge_failed_best_effort`，不写 completed。失败路径有 5 个稳定 failure_stage 常量覆盖所有错误类型。
5. **Idempotent replay 仍尝试 completed**：`PurgeSessionDeleteResult.idempotent_replay is True` 时 command path 无条件调用 `append_purge_completed_audit_record`，依赖 JSONL source key 幂等去重。
6. **Completed append failure retry**：tombstone 已提交、返回 retryable error；同 key retry 通过 tombstone replay 后重试 completed append。测试 `test_public_purge_session_completed_append_failure_retries_completed` 验证此路径。
7. **Audit line semantics**：`audit_json_line_marks_purged_source_eventlog_facts` 只对 `purge_completed` 且 `source_eventlog_facts_purged is True` 返回 `True`，started/failed 均返回 `False`。
8. **Best-effort failed append**：`_append_purge_failed_best_effort` 捕获所有异常并 log warning，不掩盖原始错误。
9. **Bounded failure message**：`_bounded_failure_message` 截断到 512 字符，在 validation 之后应用。
10. **Durable layer independence**：`purge.py` 不 import `dayu.host.audit`，不写 JSONL；`PurgeSessionDeleteRequest` 只接收 started audit ref/digest，不接收 audit recorder。

### Architecture Boundary

- `dayu.host.durable.purge` 不 import `dayu.host.audit`；purge audit 编排在 command path，是 purge 专用例外。
- `audit.py` import `purge.py` 的 `PurgeTombstoneRow`、`build_purge_attempt_ref`、`build_purge_tombstone_digest`，方向正确（上层依赖下层类型）。
- command path 直接写 JSONL 是 purge 专用例外，docstring 明确禁止扩散为通用 command audit 模式。
- `_PurgeAuditJsonlRecorder` 已删除，消除旧 pre-commit completion audit 语义。
- `PurgeTombstoneAuditRecorder` Protocol、`PurgeTombstoneAuditRecordRequest`、`PurgeTombstoneAuditRecordResult` 已从 `purge.py` 全量删除。
- 包导出测试 `test_package_exports.py` 已同步：`INTERNAL_PURGE_DURABLE_EXPORTS` 包含新 helper，确认不进入 `dayu.host` Service-facing 根命名空间。

### No Overdesign

- 无通用审计查询或分析 API。
- 无 purge audit reconciliation report。
- 无新增状态机、分类系统或复杂诊断框架。
- `purge_failed` 定位为 best-effort 诊断，不参与 durable truth、recovery 或 reconciliation。
- 3 个 request dataclass 只接收业务输入；`schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest` 由 builder 派生。
- failure_stage 使用 5 个稳定字符串常量，不引入枚举类或分类框架。

### Tests

- 46 tests pass, pyright 0 errors。
- 覆盖 plan Section 7 全部 4 类 required test：
  - 7.1 started-only 不被误判为 completed：`test_purge_audit_lines_are_append_only_and_only_completed_marks_purged`
  - 7.2 completed 引用 committed tombstone：`test_public_purge_session_appends_tombstone_audit_jsonl`
  - 7.3 SQLite 失败无 completed：`test_public_purge_session_sqlite_failure_writes_started_and_no_completed`（使用 BEFORE INSERT trigger injection）
  - 7.4 completed append 失败后 retry 幂等补写：`test_public_purge_session_completed_append_failure_retries_completed`
- 独立进程 purge 后 fail-closed 测试：`test_public_purge_is_observed_by_independent_process_read_paths` 验证 get_session/get_run/retry_run/replay_run/watch_session_events 均返回 NOT_FOUND。
- tombstone id/attempt ref/tombstone digest helper 测试：`test_purge_session_durable_deletes_matrix_and_preserves_replay` 断言 `build_purge_tombstone_id`、`build_purge_attempt_ref`、`build_purge_tombstone_digest` 输出。
- durable 层拒绝无效 started audit ref：`test_purge_session_durable_rejects_invalid_started_audit_ref_before_delete`。

### README Sync

- `dayu/host/README.md`：purge audit 语义已同步为 purge_started / purge_completed / purge_failed 三线模型，tombstone audit ref 指向 started 行。
- `tests/README.md`：purge_session 测试覆盖描述已同步为"append-only audit JSONL 的 purge_started / purge_completed / best-effort purge_failed 语义"。
- 无根目录 README 变更（public CLI / 用户工作流未变），正确。

### Residual Risk

- `purge_failed` 是 best-effort；如果 failed append 也失败，JSONL 只会留下 started line，但 helper 不会把它误判为 completed。此风险在 plan Section 12 已记录。
- tombstone 的 `audit_record_ref/digest` 指向 started line，docstring 已更新说明，避免误读为 completed audit ref。
- `_bounded_failure_message` 截断到 512 字符；超长 exception message 会被截断，但原始 error 不受影响。此为合理存储约束。
- `_append_purge_failed_best_effort` 的 warning log 是唯一失败诊断通道；若 logging 也被抑制，失败审计行将完全不可观测。此为 best-effort 语义的固有限制。

## Open Questions

无。

## Residual Risk

- `purge_failed` best-effort 失败时 JSONL 只有 started line，无 completed/failed，但不会被误判为 completed。已在 plan 和 implementation docstring 中记录。
