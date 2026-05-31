# Code Review — WU-AUDIT-01 Integrated Implementation

## Scope

- Mode: current changes
- Branch: `feat/host-purge-audit-reconciliation`
- Base: `main`
- Output file: `docs/reviews/wu-audit-01-code-review-ds-20260531.md`
- Included scope:
  - `dayu/host/api.py` — `PurgeSessionResult` docstring 更新
  - `dayu/host/audit.py` — 新 purge started/completed/failed builder / append / marks helper
  - `dayu/host/command.py` — `purge_session` 编排重构
  - `dayu/host/durable/purge.py` — 新 tombstone helper，删除 audit recorder
  - `tests/host/test_purge_session.py` — 新 audit 测试
  - `tests/host/test_audit_sink.py` — 旧测试更新
  - `tests/host/test_package_exports.py` — 导出白名单同步
  - `docs/host/host-core-followup-implementation-control.md` — residual risk 记录
- Excluded scope: 无（全部未提交 diff 已 review）
- Parallel review coverage: 无（单 reviewer 全量走读）

## Design / Contract Baseline

- Accepted plan: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
- Implementation report: `docs/reviews/wu-audit-01-slice1-implementation-codex-20260531.md`
- Design source: `docs/host/design.md`（仅作为 Host 层架构边界参照，不逐条对照）

## Review Method

沿真实代码路径逐行走读三条主链路：

1. **成功路径**：`purge_session` → `append_purge_started_audit_record` → `purge_session_durable` (SQLite commit) → `append_purge_completed_audit_record`
2. **SQLite 失败路径**：`purge_session` → `append_purge_started_audit_record` → SQLite transaction 失败 → `_append_purge_failed_best_effort` → raise
3. **completed append 失败 + retry 路径**：第一次 completed append 失败 → retryable error → 同 key retry → tombstone replay → 补写 completed

每条链路检查：入参、分支条件、下游调用、返回值/raise、副作用、状态一致性。

额外检查：adversarial failure pass、架构边界、Protocol/interface 耦合、参数生效链、state machine ownership、JSONL source key 幂等去重逻辑。

---

## Findings

### F-01-未修复-中-`_append_purge_failed_best_effort` 对所有 failure type 使用相同 `failure_stage`

- **入口/函数**: `_append_purge_failed_best_effort` → `append_purge_failed_audit_record`
- **文件(行号)**: `dayu/host/command.py:944-982`
- **输入场景**: `PurgeSessionInvalidStateError`（Session 未关闭）、`PurgeSessionAlreadyPurgedError`（已由不同请求 purge）、`PurgeSessionNotFoundError`（Session 不存在）等 precondition failure
- **实际分支**: 所有 catch 分支均调用 `_append_purge_failed_best_effort`，内部硬编码 `failure_stage="sqlite_purge_transaction"`
- **预期行为**: `failure_stage` 应反映实际失败阶段。precondition check 失败不是 SQLite transaction 失败
- **实际行为**: 无论何种 failure type，audit JSONL 中 `failure_stage` 均为 `"sqlite_purge_transaction"`
- **直接证据**: `command.py:972` — `failure_stage="sqlite_purge_transaction"` 硬编码在 `_append_purge_failed_best_effort` 函数体内，对所有调用路径无区分
- **影响**: 诊断信息失真。当 `purge_failed` line 的 `failure_stage` 显示 `sqlite_purge_transaction` 但实际原因是 Session 未关闭时，运维排查会被误导
- **建议改法和验证点**: 将 `failure_stage` 作为 `_append_purge_failed_best_effort` 参数传入，调用侧根据实际异常类型传入 `"precondition_check"` / `"sqlite_purge_transaction"` / `"idempotency_conflict"` 等稳定字符串；验证 `test_public_purge_session_sqlite_failure_writes_started_and_no_completed` 中 `failure_stage` 字段值与实际失败原因一致
- **修复风险（低）**: 改动局限在 `_append_purge_failed_best_effort` 签名与 4 处调用点，不涉及核心编排逻辑
- **严重程度（中）**: 不造成 correctness 问题（`purge_failed` 本身是 best-effort 诊断），但 plan 要求 `failure_stage` 为稳定诊断字符串，当前实现降低了诊断价值

### F-02-未修复-低-idempotency conflict / durable inconsistency 路径也写入 `purge_failed`，未在 plan 中明确覆盖

- **入口/函数**: `purge_session` except `HostDurableError` 分支
- **文件(行号)**: `dayu/host/command.py:839-841`
- **输入场景**: `HostIdempotencyConflictError`（同 key 不同 semantic digest）或 durable inconsistency 错误
- **实际分支**: 被泛化 `except HostDurableError as exc` 捕获，调用 `_append_purge_failed_best_effort`
- **预期行为**: plan 2.5 描述 `purge_failed` 在 "SQLite purge / tombstone transaction 失败后" 写入。idempotency conflict 未进入 destructive transaction，严格来说不在 plan 描述的 failed 场景内
- **实际行为**: idempotency conflict 也会产生 `purge_failed` line，`failure_stage="sqlite_purge_transaction"` 进一步放大 F-01 的误导
- **直接证据**: `command.py:839-841` — 泛化 `HostDurableError` catch；`command.py:972` — 固定 `failure_stage`
- **影响**: 轻微语义偏差。idempotency conflict 的 `purge_failed` line 提供了额外诊断信息但 `failure_stage` 标签不准确
- **建议改法和验证点**: 可选项：对 `HostIdempotencyConflictError` 单独 catch 并传入 `failure_stage="idempotency_conflict"`，或不写 `purge_failed`（按 plan 字面含义）。如果觉得 `purge_failed` 附加信息有价值，保留但修正 `failure_stage`
- **修复风险（低）**: 调整 catch 顺序或 failure_stage 参数
- **严重程度（低）**: plan 2.5 明确 `purge_failed` 是 best-effort 且“不围绕 failed line 设计额外查询或分类系统”，当前行为在 plan 容忍范围内

---

## Correctness Verification（按用户指定的重点逐条验证）

### purge_started 不表示完成

- **入口**: `audit_json_line_marks_purged_source_eventlog_facts`
- **文件(行号)**: `dayu/host/audit.py:650-663`
- **验证**: 函数要求 `line_kind == "purge_completed"` AND `source_eventlog_facts_purged is True`。`purge_started` 的 `line_kind` 是 `"purge_started"` 且 `source_eventlog_facts_purged` 为 `False`（行 498-505），因此必然返回 `False`。`purge_failed` 同理。
- **测试覆盖**: `test_public_purge_session_appends_tombstone_audit_jsonl` 断言 started line marks 为 False；`test_purge_audit_lines_are_append_only_and_only_completed_marks_purged` 断言 started/failed 返回 False，completed 返回 True
- **结论**: 通过

### purge_completed 仅在 tombstone commit 后写入并引用 tombstone digest

- **入口**: `purge_session` → `append_purge_completed_audit_record`
- **文件(行号)**: `dayu/host/command.py:843-858`
- **验证**: `append_purge_completed_audit_record` 调用在 `host._transaction_runner().run_write(operation)` 成功返回之后（行 817-841 try/except 块外部），仅在 SQLite commit 成功且无 durable error 时执行。`build_purge_completed_audit_json_line`（audit.py:528-569）从 `tombstone` row 读取 `tombstone_id`、`deleted_counts_digest`、`precondition_digest`、`deleted_refs_digest`、`audit_record_ref`、`audit_record_digest`，并通过 `build_purge_tombstone_digest(tombstone)` 计算 tombstone 完整 digest
- **测试覆盖**: `test_public_purge_session_appends_tombstone_audit_jsonl` 断言 `completed_line["purge_tombstone_digest"] == build_purge_tombstone_digest(tombstone)` 且 `completed_line["purge_tombstone_ref"] == tombstone.tombstone_id`
- **结论**: 通过

### SQLite 失败无 completed

- **入口**: `purge_session` exception handling
- **文件(行号)**: `dayu/host/command.py:818-841`
- **验证**: 所有 SQLite/durable 失败路径均进入特定 except 分支 → `_append_purge_failed_best_effort` → re-raise，不执行到行 843 的 `append_purge_completed_audit_record`
- **测试覆盖**: `test_public_purge_session_sqlite_failure_writes_started_and_no_completed` 使用 `BEFORE INSERT` trigger `RAISE(ABORT)` 注入 tombstone 插入失败，断言 JSONL 无 `purge_completed`，EventLog rows 仍存在（rollback 验证）
- **结论**: 通过

### idempotent replay 无条件尝试 completed 且不扫描 JSONL

- **入口**: `purge_session` → `_PurgeSessionOperation` → `purge_session_durable`
- **文件(行号)**: `dayu/host/command.py:843-858`；`dayu/host/durable/purge.py:690-788`
- **验证**: `purge_session_durable` 在 replay 路径返回 `PurgeSessionDeleteResult(idempotent_replay=True, ...)`。command path 不检查 `idempotent_replay` 标志来决定是否调用 `append_purge_completed_audit_record`——它始终在 transaction 成功后无条件调用。重复控制完全由 `_append_purge_audit_json_line` 的 source key `(line_kind, purge_attempt_ref)` 幂等去重实现。生产代码不读取 JSONL 判断 completed 是否已存在
- **测试覆盖**: `test_public_purge_session_completed_append_failure_retries_completed` 通过 monkeypatch 注入 completed append 失败，验证 retry 补写 completed，且最终 JSONL 只有一条 started、一条 completed
- **结论**: 通过

### 不引入通用 audit analyze/query API

- **验证**: `audit.py` 和 `__all__` 中无新增通用查询、分析或 reconciliation API。`audit_json_line_marks_purged_source_eventlog_facts` 是既有函数的语义修正，不是新查询 API
- **结论**: 通过

### durable schema 不变

- **验证**: `TABLE_HOST_PURGE_TOMBSTONES` DDL 未修改。`PurgeTombstoneRow` 字段不变，仅 docstring 更新
- **结论**: 通过

### pyright 0 errors / 测试真实性

- **验证**: implementation report 声明 pyright 0 errors, 0 warnings, 0 informations；46 tests passed
- **审查**: 4 个关键测试直接验证 correctness contract 的每条要求；测试使用真实 SQLite trigger 注入失败（非 mock）；monkeypatch 注入 completed append 失败后 undo 验证补写。测试覆盖了成功路径、SQLite 失败路径、completed append failure + retry 路径
- **结论**: 通过（未独立重跑，信任 implementation report；测试代码本身经走读确认断言覆盖关键 correctness 条件）

---

## Adversarial Failure Pass

| 场景 | 行为 | 评判 |
|---|---|---|
| started append 失败（OSError/lock/conflict） | raise retryable/non-retryable HostApiError，不进入 SQLite transaction | 正确 |
| Crash between started append and SQLite transaction | started line 存在，`source_eventlog_facts_purged=False`，不被误判；retry 从 started 重新开始（幂等跳过），执行 PROCEED_TO_PURGE | 正确 |
| SQLite transaction 中途 crash | SQLite atomic rollback，started 存在，无 tombstone，无 completed；retry 重新执行完整 delete matrix | 正确 |
| Crash after SQLite commit before completed append | tombstone committed，started 存在，无 completed；retry REPLAY_TOMBSTONE → 无条件 append completed | 正确 |
| completed append 失败（OSError） | raise retryable HostApiError("Host purge completed audit append failed")，tombstone 已持久 | 正确 |
| completed append 失败（HostDurableError, source key conflict） | `_host_api_error_from_durable_error` → `INTERNAL_ERROR, retryable=False` | 可接受：deterministic 输入下不应出现 completed digest 冲突 |
| 并发 purge 同 Session（不同 client_request_id） | ALREADY_PURGED_CONFLICT → `purge_failed` best-effort → raise CONFLICT retryable=False | 正确 |
| 并发 purge 同 Session（同 client_request_id retry） | REPLAY_TOMBSTONE → 补写 completed（或幂等跳过） | 正确 |
| `_append_purge_failed_best_effort` 自身失败 | `except Exception` 捕获，`_LOGGER.warning`，不替换原始错误 | 正确 |
| JSONL 中存在旧格式 `purge_tombstone` line（legacy data） | `audit_json_line_marks_purged_source_eventlog_facts` 对 `line_kind != "purge_completed"` 返回 False → 旧 line 不再被识别为 completed | 正确：向后兼容的语义修正 |
| JSONL 中存在 corrupt/malformed line | `_json_object_from_jsonl_line` 返回 None → 跳过，不影响 source key 检查 | 正确 |

---

## Architecture Boundary Check

- `dayu/host/audit.py` 导入 `PurgeTombstoneRow` 来自 `dayu.host.durable.purge`（行 30-33）：这是 Host 层内跨模块依赖，`PurgeTombstoneRow` 是 frozen dataclass（纯数据），plan 明确允许。未发现跨层穿透或反向依赖
- `dayu/host/command.py` 导入 `dayu.host.audit` 的 append 函数和 request dataclass：正确的 command → audit 方向依赖
- `dayu/host/durable/purge.py` 不再导入或依赖任何 audit 相关类型：符合 plan Slice 1 目标
- 未发现 새로운反向依赖或跨层穿透

---

## Parameter Effectiveness

- `semantic_request_digest`：`_build_purge_audit_inputs` → `build_purge_semantic_digest` → `_PurgeAuditInputs` → `PurgeStartedAuditRecordRequest` → `_base_purge_audit_fields` → JSONL field。链路完整
- `tombstone_id`：`_build_purge_audit_inputs` → `build_purge_tombstone_id`（基于 session_id + client_request_id + semantic_digest 的稳定 digest）。同一请求 retry 产生相同 tombstone_id，链路完整
- `started_audit_record_ref/digest`：`append_purge_started_audit_record` 返回 → `_PurgeSessionOperation` → `PurgeSessionDeleteRequest` → `_insert_tombstone_and_idempotency` → 写入 tombstone row。tombstone 持久化后 `audit_record_ref/digest` 指向 started line。链路完整
- `purge_attempt_ref`：`build_purge_attempt_ref(tombstone_id)` → `_base_purge_audit_fields` → JSONL source key。不可由调用方传入，防止不一致。正确

---

## Protocol / Interface Coupling

- 旧 `PurgeTombstoneAuditRecorder` Protocol 已删除。durable 层不再依赖 audit writer 端口——改为接收已完成的 started audit ref/digest 纯值。这是正确的解耦方向
- `PurgeSessionDeleteRequest` 从 `audit_recorder: Protocol` 改为 `started_audit_record_ref: str` + `started_audit_record_digest: str` 纯数据字段。更低耦合

---

## State Machine Ownership

- **Purge completion 真源**: SQLite `host_purge_tombstones` row（唯一真源）
- **状态推进权**: `purge_session_durable` 拥有推进权（在同一 write transaction 内写入 tombstone + 幂等记录）
- **终态**: tombstone 存在且 `idempotent_replay=True` 时，tombstone 已是 absorbing state；再次 purge 同一 Session 同 key → replay（不重复删除）；不同 key → ALREADY_PURGED_CONFLICT
- **JSONL 不参与状态判断**: `audit_json_line_marks_purged_source_eventlog_facts` 只做事后识别，不驱动 recovery / resume / memory / durable truth
- 未发现终态可回退、多写真源或推进权分散的问题

---

## Source Key Idempotency Detail

`_jsonl_contains_line` 的 source key 匹配逻辑从 OR 匹配（任一 key 匹配即冲突）改为 AND 匹配（全部 key 匹配才冲突）（`dayu/host/audit.py:1116-1122`）。

- **EventLog audit sink 路径**: source key 为单字段 `(event_id,)`，AND 匹配与 OR 匹配等价，行为不变
- **Purge audit 路径**: source key 为双字段 `(line_kind, purge_attempt_ref)`，AND 匹配正确表达了组合键语义——不同 line kind 按不同 attempt 隔离，不会误冲突
- **旧行为风险**: OR 匹配下，如果 JSONL 中存在任意 `purge_started` line（匹配 `line_kind`），后续任意不同 attempt 的 `purge_started` append 都会误判 source key 冲突。此 bug 在生产中尚未触发（因为此前只有单一 `purge_tombstone` line kind 且 source key 为单字段），但本次变更引入三种 line kind 后如不改 AND 匹配将立即触发

---

## Test Coverage Assessment

| 测试 | 覆盖场景 | 状态 |
|---|---|---|
| `test_public_purge_session_appends_tombstone_audit_jsonl` | 成功路径：started + completed，tombstone ref/digest 一致性 | 覆盖 |
| `test_public_purge_session_audit_append_failure_fails_before_success` | started append 失败：不进入 SQLite，tombstone=None，EventLog 保留 | 覆盖 |
| `test_public_purge_session_sqlite_failure_writes_started_and_no_completed` | SQLite 失败：trigger RAISE(ABORT)，rollback，JSONL 有 started+failed 无 completed | 覆盖 |
| `test_public_purge_session_completed_append_failure_retries_completed` | completed append 失败 + monkeypatch undo retry 补写 | 覆盖 |
| `test_purge_audit_lines_are_append_only_and_only_completed_marks_purged` | started/failed/completed 幂等去重 + marks helper 正确性 | 覆盖 |
| `test_purge_session_durable_deletes_matrix_and_preserves_replay` | durable 层 replay（`idempotent_replay=True`），tombstone digest/attempt_ref helper | 覆盖 |
| `test_purge_session_durable_rejects_invalid_started_audit_ref_before_delete` | 无效 started audit ref 在删除前被拒绝 | 覆盖 |

**未覆盖场景**：
- `purge_failed` append 自身失败（被 `_LOGGER.warning` 捕获）——难以在单元测试中可靠触发且价值有限，best-effort 语义下可接受
- 并发 purge（多进程同时 purge 同一 Session）——现有 `test_public_purge_is_observed_by_independent_process_read_paths` 覆盖了 purge 后独立进程 read path fail-closed，但不覆盖并发 purge race。由于 SQLite transaction 提供 serializable isolation，并发 purge 由 idempotency / tombstone check 在事务内裁决，race window 极小，低优先级

---

## Open Questions

1. 当前 README（`dayu/host/README.md`）可能仍描述旧 `purge_tombstone` audit line，是否需要在本 work unit 内同步更新？总控文档 RR-AUDIT-02 标记为 open，建议在 ready-to-open-draft-PR 前处理。此项不在本次 review scope（用户明确指示不要修改文件），仅标记注意。

---

## Residual Risk

- `purge_failed` 的 `failure_stage` 统一为 `"sqlite_purge_transaction"` 降低了诊断精度（F-01），但 plan 明确 `purge_failed` 为 best-effort 且不围绕其构建查询系统，风险可控
- completed append 在 SQLite commit 后失败时，调用方收到 retryable error；如果调用方不 retry，tombstone 已是完成真源，JSONL 缺少 completed line。`audit_json_line_marks_purged_source_eventlog_facts` 不会将只有 started 的 JSONL 误判为 completed，但 JSONL audit trail 不完整。plan §12 已记录此风险为 residual
- 未独立重跑测试和 pyright（implementation report 声明通过），信任 implementation report 的验证结果

---

## Conclusion

**PASS** — 未发现 correctness 阻塞问题。

实现严格遵循 accepted plan 的 correctness contract：`purge_started` 不表示完成；`purge_completed` 仅在 tombstone commit 后写入并引用 tombstone digest；SQLite 失败无 completed；idempotent replay 无条件尝试 completed 且不扫描 JSONL；durable schema 不变；无通用 audit analyze/query API。

F-01（`failure_stage` 统一标签）和 F-02（idempotency conflict 路径的 `purge_failed` 语义边界）为低/中严重度，建议在后续 slice 或 draft-PR review 前处理，但不阻塞当前 diff 的 correctness 验收。
