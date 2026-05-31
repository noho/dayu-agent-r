# WU-AUDIT-01 Purge Audit Cross-medium Orphan Reconciliation Plan

## 1. 目标与动机判断

### 1.1 目标

用最小必要改动修正 `purge_session` 审计语义：

- 在 destructive purge attempt 前写入 `purge_started`，只表示尝试开始，不表示 purge 完成。
- SQLite `host_purge_tombstones` commit 成功后写入 `purge_completed`，并引用已提交 tombstone 的 id 与 digest。
- SQLite purge / tombstone transaction 失败后可 best-effort 写入 `purge_failed`，仅用于轻量诊断，不引入查询框架。
- `audit_json_line_marks_purged_source_eventlog_facts(...)` 只允许 `purge_completed` 被判定为 purge completed。

### 1.2 非目标

- 不做通用审计分析或查询 API。
- 不新增复杂诊断框架。
- 不重做通用 audit pipeline。
- 不让 audit JSONL 成为 Host durable truth。
- 不修改 public `PurgeSessionResult` 字段。
- 不修改 `host_purge_tombstones` schema，除非实现阶段发现不可绕开的直接证据。
- 不保留旧 `purge_tombstone` audit line 的兼容 wrapper / facade。

### 1.3 动机仍然成立

当前问题是真实存在的，但严重性不需要上升到通用审计系统设计：

- 当前 `dayu/host/durable/purge.py` 在插入 tombstone 前调用 audit recorder。
- 当前 `dayu/host/audit.py` 只写单条 `line_kind=purge_tombstone`，并设置 `source_eventlog_facts_purged=True`。
- JSONL append 与 SQLite commit 不在同一 durable transaction 中；如果 JSONL append 成功后 SQLite tombstone insert / commit 失败，旧 audit line 会错误表现为 purge 完成。

root cause 是完成语义过早写入 JSONL。最小修复是把 audit line 分成 started 与 completed，并让 helper 只把 completed 当作完成。

## 2. Contract Decisions

### 2.1 Audit line kinds

新增或替换为三个 purge audit line kind：

- `purge_started`
- `purge_completed`
- `purge_failed`

`purge_failed` 是 best-effort 诊断 line；实现复杂度必须低，不为它引入状态机或查询 API。

### 2.2 共同字段

三类 purge audit line 使用必要公共字段：

- `schema_version`
- `line_kind`
- `audit_record_ref`
- `purge_attempt_ref`
- `session_id`
- `client_request_id`
- `actor`
- `source`
- `operation_context_refs`
- `operation_context_digest`
- `reason`
- `request_context`
- `semantic_request_digest`
- `line_digest`

`purge_attempt_ref` 使用稳定值：`purge-attempt:{tombstone_id}`。

JSONL 幂等 source key 使用 `(line_kind, purge_attempt_ref)`。同一次 attempt 可以各写一条 started / completed / failed；同一 kind 同一 attempt 的不同 digest 必须冲突。

`schema_version`、`line_kind`、`audit_record_ref`、`line_digest` 必须由 builder 生成，调用方不得传入。`purge_attempt_ref` 必须由 builder 使用 `tombstone_id` 派生，调用方不得直接传入，避免上层传入不一致 ref。

purge command path 直接写 JSONL 是 purge 专用例外：目标 Session 的 EventLog 会被 purge 删除，无法依赖常规 EventLog audit projection 在事后生成 destructive purge 流水。该例外不得扩散成通用 command path 直接写 audit 模式；普通 Host command 仍应通过 committed EventLog facts 驱动 audit projection。

### 2.3 `purge_started`

必要字段：

- 共同字段。
- `planned_purge_tombstone_ref`: deterministic tombstone id。
- `purge_tombstone_ref`: `null`。
- `purge_tombstone_digest`: `null`。
- `source_eventlog_facts_purged`: `false`。

语义：

- 只表示 destructive attempt 已发起。
- 不携带 `deleted_counts`、`deleted_counts_digest`、`deleted_refs_digest`、`precondition_digest`，避免把 transaction 内才确定的信息提前写入。
- 字段必须完全 deterministic，不包含 timestamp、random id、进程 id 或其它会随 retry 变化的值，保证同一 `session_id`、`client_request_id`、semantic digest retry 时 started line digest 稳定，并依赖 `(line_kind, purge_attempt_ref)` 幂等去重。

### 2.4 `purge_completed`

必要字段：

- 共同字段。
- `purge_tombstone_ref`: committed tombstone id。
- `purge_tombstone_digest`: committed tombstone row 的 stable digest。
- `started_audit_record_ref`: started line 的 ref。
- `started_audit_record_digest`: started line 的 digest。
- `deleted_counts_digest`: tombstone row 的 `deleted_counts_digest`。
- `precondition_digest`: tombstone row 的 `precondition_digest`。
- `deleted_refs_digest`: tombstone row 的 `deleted_refs_digest`。
- `source_eventlog_facts_purged`: `true`。

语义：

- 只有 `purge_completed` 可以表达 audit 流水上的 purge complete。
- 真正完成真源仍是 SQLite tombstone；JSONL 不参与 recovery / resume / memory / durable truth。

### 2.5 `purge_failed`

必要字段：

- 共同字段。
- `planned_purge_tombstone_ref`: deterministic tombstone id。
- `failure_stage`: 简单稳定字符串，例如 `sqlite_purge_transaction`。
- `failure_message`: bounded diagnostic text。
- `source_eventlog_facts_purged`: `false`。

语义：

- 只做 best-effort 诊断。
- 写入失败不得掩盖原始 SQLite / durable 错误。
- 不围绕 failed line 设计额外查询或分类系统。

## 3. Durable Schema Decision

不修改 `host_purge_tombstones` schema。

理由：

- tombstone row 已经是 purge 完成真源。
- `purge_completed` 可以在 SQLite commit 后根据 committed tombstone row 写入，不需要把 completed audit ref/digest 写回 tombstone。
- 当前 `audit_record_ref` / `audit_record_digest` 可以保存 started line 的 ref/digest。实现阶段必须更新 docstring，说明该字段是 destructive attempt audit ref，不再表示 completed line。

需要新增最小 helper：

- `build_purge_tombstone_id(session_id: str, client_request_id: str, semantic_request_digest: str) -> str`
- `build_purge_attempt_ref(tombstone_id: str) -> str`
- `build_purge_tombstone_digest(tombstone: PurgeTombstoneRow) -> str`

`build_purge_tombstone_digest` 对 `PurgeTombstoneRow` 的全部已持久字段做 canonical digest，字段集必须与 `host_purge_tombstones` row 语义一致：

- `tombstone_id`
- `session_id`
- `client_request_id`
- `semantic_request_digest`
- `actor`
- `source`
- `operation_context_digest`
- `operation_context_refs`
- `reason`
- `purged_at`
- `precondition_digest`
- `deleted_counts`
- `deleted_counts_digest`
- `deleted_refs_digest`
- `audit_record_ref`
- `audit_record_digest`
- `request_context`

其中 `audit_record_ref` / `audit_record_digest` 指向 started line，因此属于 committed tombstone row 的持久语义，必须纳入 digest。digest 不包含 `purge_completed` line 的 ref/digest 或任何 completed append 结果，避免循环依赖。

## 4. Transaction And Failure Ordering

固定顺序：

1. public command path 构造 `semantic_request_digest`、稳定 `tombstone_id`、`purge_attempt_ref`。
2. 写入 `purge_started`。
   - started append 失败：不进入 destructive SQLite transaction，返回现有 audit append failure 风格的 retryable `HostApiError`。
3. 执行 SQLite write transaction：删除矩阵、插入 tombstone、写 purge idempotency row、commit。
   - SQLite transaction / tombstone insert / commit 失败：transaction rollback，best-effort 写 `purge_failed`，返回原始 durable error 映射。
   - `purge_failed` append 失败：只 log warning，不替换原错误。
4. SQLite commit 成功后写入 `purge_completed`。
   - completed append 成功：返回 `PurgeSessionResult(purged=True, ...)`。
   - completed append 失败：tombstone 已提交，purge 已完成；返回 retryable `HostApiError(INTERNAL_ERROR, "Host purge completed audit append failed")`，同 `client_request_id` retry 应 replay tombstone 并重试 completed append。

retry / replay 规则：

- `purge_session_durable(...)` 返回 `PurgeSessionDeleteResult.idempotent_replay is True` 时，command path 必须无条件尝试 append `purge_completed`。
- 不读取、不扫描 JSONL 来判断 completed 是否已存在；只依赖 `_append_audit_json_line` 的 source key `(line_kind, purge_attempt_ref)` 幂等去重。
- 同 key retry 可以再次构造 deterministic started line；若 started 已存在，append helper 通过同 source key / same digest 幂等跳过，不产生重复 line。
- 同 key retry 在 tombstone replay 后仍尝试 completed append；如果 completed 已存在，append helper 幂等跳过；如果上次 completed append 失败，则本次补写。

## 5. Affected Files

### 5.1 `dayu/host/durable/purge.py`

允许改动：

- 新增 tombstone id / attempt ref / tombstone digest helper。
- `PurgeSessionDeleteRequest` 删除 audit recorder port，改为接收 started audit ref/digest。
- `_insert_tombstone_and_idempotency` 不再调用 audit recorder；直接把 started audit ref/digest 写入 `PurgeTombstoneRow.audit_record_ref/audit_record_digest`。
- 更新相关中文 docstring。

禁止改动：

- 不 import `dayu.host.audit`。
- 不修改 `host_purge_tombstones` DDL。

### 5.2 `dayu/host/audit.py`

允许改动：

- 新增最小 request/result dataclass：
  - `PurgeStartedAuditRecordRequest`
  - `PurgeCompletedAuditRecordRequest`
  - `PurgeFailedAuditRecordRequest`
  - `PurgeAuditRecordResult`
- `PurgeStartedAuditRecordRequest` 字段必须为：
  - `tombstone_id: str`
  - `session_id: str`
  - `client_request_id: str`
  - `semantic_request_digest: str`
  - `actor: str | None`
  - `source: str | None`
  - `operation_context_digest: str | None`
  - `operation_context_refs: Mapping[str, JsonValue]`
  - `reason: str`
  - `request_context: Mapping[str, JsonValue]`
- `PurgeCompletedAuditRecordRequest` 字段必须为：
  - `tombstone: PurgeTombstoneRow`
  - `semantic_request_digest: str`
- `PurgeFailedAuditRecordRequest` 字段必须为：
  - `tombstone_id: str`
  - `session_id: str`
  - `client_request_id: str`
  - `semantic_request_digest: str`
  - `actor: str | None`
  - `source: str | None`
  - `operation_context_digest: str | None`
  - `operation_context_refs: Mapping[str, JsonValue]`
  - `reason: str`
  - `request_context: Mapping[str, JsonValue]`
  - `failure_stage: str`
  - `failure_message: str`
- 上述 request dataclass 不得包含 `schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest` 字段；这些值由 builder 根据 line kind 与 `tombstone_id` 统一派生。
- `PurgeAuditRecordResult` 字段必须为：
  - `audit_record_ref: str`
  - `audit_record_digest: str`
- 新增最小 builder / append 函数：
  - `build_purge_started_audit_json_line(...)`
  - `append_purge_started_audit_record(...)`
  - `build_purge_completed_audit_json_line(...)`
  - `append_purge_completed_audit_record(...)`
  - `build_purge_failed_audit_json_line(...)`
  - `append_purge_failed_audit_record(...)`
- 修改 `audit_json_line_marks_purged_source_eventlog_facts(...)`：只有 `line_kind == "purge_completed"` 且 `source_eventlog_facts_purged is True` 返回 `True`。
- 删除旧 `purge_tombstone` line 的生产使用，不加兼容 wrapper。

禁止改动：

- 不新增通用审计查询或分析 API。
- 不新增 purge audit reconciliation report。

### 5.3 `dayu/host/command.py`

允许改动：

- `purge_session(...)` 按 started -> SQLite transaction -> completed 顺序编排。
- transaction 失败时 best-effort append failed。
- completed append 失败时返回 retryable error；同 key retry replay tombstone 后重试 completed append。
- `PurgeSessionDeleteResult.idempotent_replay is True` 时仍无条件调用 `append_purge_completed_audit_record(...)`，不扫描 JSONL。
- started append 也必须走 deterministic source key 幂等；同 key retry 不应产生第二条 started line。
- 删除或收窄 `_PurgeAuditJsonlRecorder`，避免它继续表达 pre-commit tombstone completion audit。

### 5.4 `dayu/host/api.py`

预计无需 public field 变更。

允许改动：

- 仅更新 `PurgeSessionResult` docstring，说明 `purged=True` 以 committed tombstone 为准。

### 5.5 Tests

主要更新：

- `tests/host/test_purge_session.py`

如测试文件过大，可以新增一个小文件只覆盖 audit line builder/helper，但不要新增生产查询或分析 API。

## 6. Implementation Slices

### Slice 1：durable purge 去掉 pre-commit completion audit

改动：

- 新增 tombstone id / attempt ref / tombstone digest helper。
- `PurgeSessionDeleteRequest` 改为接收 started audit ref/digest。
- `_insert_tombstone_and_idempotency` 删除 audit recorder 调用。
- 更新 low-level durable purge tests 中的 request 构造与 tombstone 断言。

验收：

- durable 层不再依赖 audit writer port。
- tombstone 中保存 started audit ref/digest。
- `host_purge_tombstones` schema 不变。

### Slice 2：最小 audit line contract

改动：

- 新增 started/completed/failed builder 与 append 函数。
- request dataclass 只接收业务输入；`schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest` 由 builder 生成。
- 修改 `audit_json_line_marks_purged_source_eventlog_facts(...)` 只识别 completed。
- 移除旧 `purge_tombstone` line 的生产入口。

验收：

- started line `source_eventlog_facts_purged is False`。
- failed line `source_eventlog_facts_purged is False`。
- completed line `source_eventlog_facts_purged is True`。
- marks helper 对 started / failed 返回 `False`，对 completed 返回 `True`。

### Slice 3：public command 顺序编排

改动：

- `purge_session` 在 transaction 前 append started。
- SQLite commit 后 append completed。
- SQLite 失败后 best-effort append failed。
- completed append 失败后，同 key retry 在 durable replay 时无条件尝试 append completed，并依赖 JSONL source key 幂等去重。

验收：

- 成功路径 JSONL 至少包含 started 与 completed。
- completed 引用 committed tombstone id/digest。
- SQLite 失败路径没有 completed。
- completed append 失败后同 key retry 最终只有一条 completed。

## 7. Required Tests

### 7.1 started-only 不被误判为 completed

断言：

- 构造或写入 `purge_started` line。
- `audit_json_line_marks_purged_source_eventlog_facts(started_line) is False`。
- 若写入 `purge_failed` line，同 helper 也返回 `False`。
- 同 key retry 再次尝试 append deterministic started line 后，JSONL 中仍只有一条 started line；测试不得通过扫描生产逻辑实现去重，只验证 append helper source key 幂等结果。

### 7.2 completed 引用 committed tombstone

断言：

- public purge 成功后 JSONL 包含 `purge_started` 与 `purge_completed`。
- tombstone 存在。
- completed line 的 `purge_tombstone_ref == tombstone.tombstone_id`。
- completed line 的 `purge_tombstone_digest == build_purge_tombstone_digest(tombstone)`。
- tombstone 的 `audit_record_ref/audit_record_digest` 指向 started line。
- `audit_json_line_marks_purged_source_eventlog_facts(completed_line) is True`。
- `build_purge_tombstone_digest(tombstone)` 覆盖 tombstone 全部已持久字段，包括指向 started line 的 `audit_record_ref/audit_record_digest`，且不包含 completed line 信息。

### 7.3 SQLite 失败无 completed

建议 failure injection：

- seed closed session matrix。
- 在测试 DB 上创建 `BEFORE INSERT ON host_purge_tombstones` trigger，使用 `RAISE(ABORT, 'test tombstone insert failed')`。
- 调用 public `purge_session`。

断言：

- 调用返回 durable / internal error 映射。
- JSONL 有 `purge_started`。
- JSONL 没有 `purge_completed`。
- 允许有 `purge_failed`，但不强制依赖复杂诊断。
- `host_purge_tombstones` 无目标 session tombstone。
- 目标 session EventLog rows 仍存在，证明 SQLite rollback。

### 7.4 completed append 失败后 retry 幂等补写

断言：

- 第一次 purge：started append 成功、SQLite tombstone commit 成功、completed append 注入失败，调用返回 retryable error。
- 第二次使用同一 `client_request_id` 和同一 request retry。
- durable path 返回 tombstone replay，command path 仍无条件尝试 append completed。
- JSONL 最终只有一条 `purge_started`，只有一条 `purge_completed`。
- 生产代码不扫描 JSONL 判断 completed 是否存在；重复控制只来自 append helper 的 `(line_kind, purge_attempt_ref)` source key。

## 8. Validation Commands

受影响测试：

```bash
source .venv/bin/activate && pytest tests/host/test_purge_session.py -q
```

如新增小测试文件：

```bash
source .venv/bin/activate && pytest tests/host/test_purge_audit.py -q
```

最终类型检查：

```bash
source .venv/bin/activate && pyright
```

若实现触及更多 Host command / audit 行为，追加：

```bash
source .venv/bin/activate && pytest tests/host -q
```

## 9. README / 文档同步决策

本 planning task 不修改 README。

实现阶段：

- 修改 `dayu/host/` 源码后，检查 `dayu/host/README.md` 是否需要同步最小 purge audit 语义。
- 修改 `tests/host/` 后，检查 `tests/README.md` 是否需要同步测试约定。
- 不更新根目录 `README.md`，除非 public CLI / 用户工作流发生变化。
- 不更新总控文档，除非 controller 明确授权。

实现阶段 docstring 必须同步更新：

- `dayu/host/durable/purge.py` 模块 docstring：说明 durable purge 不直接写 JSONL，started/completed 编排在 purge command path，且这是 purge 专用例外的下游依赖。
- `PurgeTombstoneRow` docstring：说明 `audit_record_ref` / `audit_record_digest` 指向 `purge_started` audit line。
- `PurgeSessionDeleteRequest` docstring：说明接收 started audit ref/digest，不接收 audit recorder。
- `PurgeSessionDeleteResult` docstring：说明 `idempotent_replay=True` 时 command path 仍需尝试 completed audit append。
- `build_purge_tombstone_digest` docstring：列明 digest 覆盖全部已持久 tombstone 字段，包含 started audit ref/digest，不包含 completed line。
- `dayu/host/audit.py` purge audit request/result dataclass 与 builder/append 函数 docstring：说明哪些字段由 request 提供，哪些字段由 builder 派生。
- `dayu/host/command.py` `purge_session` docstring 或邻近 helper docstring：说明 direct JSONL write 仅为 purge 专用例外，原因是目标 EventLog 将被删除，不得扩散为通用 command audit 模式。

## 10. Stop Conditions

实现阶段遇到以下情况必须停下回到 planning / controller：

- 必须修改 durable schema 才能实现 completed 引用 tombstone id/digest。
- 必须新增通用审计查询或分析 API 才能完成验收。
- 必须修改 public `PurgeSessionResult` 字段。
- 需要让 JSONL 驱动 recovery、resume、memory 或 durable truth。

## 11. Blocking Questions

无 blocking question。

## 12. Residual Risks

- completed append 在 SQLite commit 后失败时，tombstone 已是完成真源；调用方会收到 retryable error，并需要同 `client_request_id` retry 补写 completed line。
- `purge_failed` 是 best-effort；如果 failed append 也失败，JSONL 只会留下 started line，但 helper 不会把它误判为 completed。
- tombstone 的 `audit_record_ref/digest` 会指向 started line；实现阶段必须同步相关 docstring，避免误读为 completed audit ref。

## 13. Handoff Readiness

handoff-ready：是。

计划已收窄到必要 audit：started 不表示完成、completed 在 tombstone commit 后写入并引用 tombstone、SQLite 失败无 completed。
