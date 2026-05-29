# Phase 15 S4 Code Review

## Gate

Phase 15 Slice P15-S4 Audit JSONL Retention And Tombstone Audit Record。

## Reviewer

AgentMiMo code review specialist。

## Scope

- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Implementation artifact: `docs/reviews/phase15-s4-implementation-codex-20260529.md`
- Workspace diff: `dayu/host/audit.py`, `dayu/host/durable/purge.py`, `dayu/host/command.py`, `tests/host/test_audit_sink.py`, `tests/host/test_purge_session.py`

## Checklist Results

### 1. public purge_session 成功返回前是否已经 append purge tombstone audit JSONL line，且 tombstone row 带 audit_record_ref / audit_record_digest

**PASS.**

`_insert_tombstone_and_idempotency()` 在 `purge.py:1613` 调用 `request.audit_recorder.record_purge_tombstone_audit()`，先于 `insert_purge_tombstone()` 调用。audit recorder 返回后经 `_validate_audit_record_result()` 校验 ref 非空、digest 为 sha256，然后才写入 tombstone row。tombstone validation (`_validate_tombstone()` at `purge.py:2719`) 强制 `audit_record_ref` 与 `audit_record_digest` 非空。

### 2. audit append failure 是否 rollback，不留下 successful tombstone，不返回 PurgeSessionResult

**PASS.**

audit recorder 调用在 SQLite write transaction 内 (`_insert_tombstone_and_idempotency`)。如果 `record_purge_tombstone_audit` 抛出 `OSError` 或 `RuntimeFileLockError`，异常传播到 `purge_session_durable()`，transaction runner rollback 整个删除矩阵。public command 层 (`command.py:812`) 捕获 `(OSError, RuntimeFileLockError)` 映射为 `HostApiErrorCode.INTERNAL_ERROR, retryable=True`，不返回 `PurgeSessionResult`。

测试 `test_purge_session_durable_audit_failure_rolls_back_tombstone` 验证 rollback 后 tombstone 不存在、EventLog 行数不变。测试 `test_public_purge_session_audit_append_failure_fails_before_success` 验证 public 路径返回 `INTERNAL_ERROR` 且无 successful tombstone。

### 3. replay 是否 deterministic，不重复追加第二个 tombstone 或第二条 audit line

**PASS.**

replay 路径在 `purge_session_durable()` 第 778 行 `_result_for_replay_decision()` 返回后直接 return，不调用 `_insert_tombstone_and_idempotency()`，因此不触发 audit recorder。tombstone 由 `session_id UNIQUE` 约束保证最多一条。audit line 由 `_append_text_if_absent()` 的 source key (`purge_tombstone_ref`) + `line_digest` 幂等机制保证不重复追加。

测试 `test_purge_session_durable_deletes_matrix_and_preserves_replay` 验证 replay 后 `len(audit_recorder.requests) == 1`。

### 4. 既有 EventLog-derived audit JSONL 是否保留，不 rewrite/truncate/delete

**PASS.**

`_append_audit_json_line()` 和 `_append_text()` 只做 append-only 写入，不打开 truncate/write mode。`_append_text_if_absent()` 先读再判断是否追加，不修改已有行。purge 删除矩阵删除 `host_audit_sink_markers`（sink-local idempotency rows），但不触及 JSONL 文件本身。

测试 `test_purge_tombstone_audit_line_is_append_only_and_recognizable` 验证既有行（`event_id: event-1`）在 purge audit line 追加后仍然存在且不变。

### 5. audit marker rows 指向 deleted EventLog 是否不阻塞 purge

**PASS.**

删除矩阵第一序位即删除 audit sink markers（`purge.py` 中 `_delete_session_matrix`），先于 EventLog 行删除。这符合 plan 中 FK 依赖顺序。

### 6. durable 层是否保持下层边界，不 import JSONL sink，不引入 Any/object/extra payload/hasattr/getattr 逃避类型

**PASS.**

- `dayu/host/durable/purge.py` 不 import `dayu.host.audit`、`dayu.host.command`、`dayu.host.open_host`、`dayu.host.read_api`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins`。grep 确认零反向依赖。
- 使用 `Protocol` (`PurgeTombstoneAuditRecorder`) 定义端口，durable 层不依赖具体 JSONL 实现。
- 无 `hasattr`/`getattr` 使用。
- 所有 dataclass 使用 `frozen=True, slots=True`。
- `PurgeTombstoneRow.audit_record_ref` 类型为 `str | None`（S1 schema），但 `_validate_tombstone()` 运行时强制非空。这是类型签名与运行时校验的合理分离：row codec 保持 nullable 以兼容从 DB 读取可能存在的旧数据，validation 层强制新写入必须非空。

### 7. error mapping 是否使用现有 HostApiErrorCode，不新增 public API shape

**PASS.**

`command.py:812` 捕获 `(OSError, RuntimeFileLockError)` 映射为 `HostApiErrorCode.INTERNAL_ERROR`。未新增任何 public error code。`PurgeSessionResult`、`PurgeSessionRequest`、`Host` public method shape 均未修改。

### 8. tests 是否覆盖 fail-before-success、audit line fields、replay、failure rollback

**PASS.**

| 场景 | 测试 |
|---|---|
| audit line append-only 且可识别 | `test_purge_tombstone_audit_line_is_append_only_and_recognizable` |
| 既有 JSONL 保留 | 同上（验证 `lines[0]["event_id"] == "event-1"`） |
| tombstone 拒绝缺失 audit record | `test_insert_tombstone_rejects_missing_audit_record` |
| tombstone 拒绝单边 audit record | `test_insert_tombstone_rejects_unpaired_audit_record_ref` |
| durable audit failure rollback | `test_purge_session_durable_audit_failure_rolls_back_tombstone` |
| durable 成功路径写入 audit ref/digest | `test_purge_session_durable_deletes_matrix_and_preserves_replay`（新增 assertions） |
| public 成功路径追加 audit line | `test_public_purge_session_appends_tombstone_audit_jsonl` |
| public audit failure fail-before-success | `test_public_purge_session_audit_append_failure_fails_before_success` |
| replay 不重复追加 audit | `test_purge_session_durable_deletes_matrix_and_preserves_replay`（验证 `len(requests) == 1`） |

### 9. README decision 是否合理

**PASS.**

本次修改不改变 public API shape、命令用法、配置入口或 README 面向读者的稳定操作说明，只补齐内部 fail-before-success invariant 与测试。`dayu/host/README.md` 与 `tests/README.md` 无需更新。

## Findings

无 blocking findings。

### Severity: INFO

#### I-1. `PurgeTombstoneRow.audit_record_ref` 类型为 `str | None` 但运行时强制非空

`PurgeTombstoneRow` dataclass 定义 `audit_record_ref: str | None` 与 `audit_record_digest: str | None`。`_validate_tombstone()` 在 `purge.py:2719` 做 `if tombstone.audit_record_ref is None or tombstone.audit_record_digest is None` 运行时检查后调用 `_require_non_empty_text` / `_require_sha256_digest`。

这是 S1 schema 设计遗留的 nullable 类型签名，与 S4 新增的非空约束之间存在表面张力。但这是合理的分层：row codec 保持 nullable 以处理从 DB 读取的边界情况（如旧 schema 迁移后的行），validation 层在写入路径强制非空。不影响正确性。

#### I-2. `_append_text_if_absent` source key 幂等依赖文件系统读取

`_append_text_if_absent()` 通过 `_jsonl_contains_line()` 扫描 JSONL 文件检查是否存在相同 source key 或 digest 的行。这在大文件下可能有性能影响，但当前是 release-blocking 正确性优先的合理选择，且 plan 中已明确 JSONL rotation/compaction 归 follow-up。

#### I-3. `_PurgeAuditJsonlRecorder` 是 frozen dataclass 但 `_RecordingAuditRecorder` 是 mutable class

`command.py` 中 `_PurgeAuditJsonlRecorder` 使用 `@dataclass(frozen=True, slots=True)`，而测试中 `_RecordingAuditRecorder` 使用普通 `__init__` + mutable `self.requests`。这是测试 fixture 的常见模式，不影响生产代码正确性。

## Verification

- `pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py -q`: 33 passed in 0.46s
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations

## Conclusion

**PASS.** S4 实现正确落地 plan 中 audit JSONL retention 与 tombstone audit record 的全部 release-blocking 要求。fail-before-success invariant 在 durable 层和 public command 层双重保障。durable 层通过 `PurgeTombstoneAuditRecorder` Protocol 保持下层边界，不引入反向依赖。replay 路径不触发 audit append。测试覆盖全面。无 blocking findings。
