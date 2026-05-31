# Phase 15 S4 Re-Review Artifact (AgentDS)

- **Gate**: Phase 15 S4 re-review
- **Date**: 2026-05-29
- **Reviewer**: AgentDS code re-review specialist
- **Input adjudication**: `docs/reviews/phase15-s4-code-review-controller-adjudication-20260529.md`
- **Fix artifact**: `docs/reviews/phase15-s4-fix-codex-20260529.md`
- **Original reviews**: `docs/reviews/phase15-s4-code-review-mimo-20260529.md`, `docs/reviews/phase15-s4-code-review-ds-20260529.md`
- **Output artifact**: `docs/reviews/phase15-s4-rereview-ds-20260529.md`

## Scope

只复核 controller accepted findings：S4-ADJ-001、S4-ADJ-002、S4-ADJ-003。确认 S4-ADJ-005 仍是 deferred residual。检查是否引入新 blocker。

## Accepted Finding Verdicts

### S4-ADJ-001: schema/type/codec non-null audit ref/digest — FIXED

**Finding**: fresh schema/type/codec 层仍把 `PurgeTombstoneRow.audit_record_ref` / `audit_record_digest` 表达为可空，S4 invariant 只靠 runtime check。

**Evidence**:

| Layer | Location | Before | After |
|-------|----------|--------|-------|
| DDL | `schema.py:988-989` | `TEXT NULL` + 双空 CHECK | `TEXT NOT NULL` |
| Type | `purge.py:347-348` | `str \| None` | `str` |
| Codec (decode) | `purge.py:2496-2502` | 普通 row get | `_required_non_empty_text_value()` / `_required_sha256_digest_value()` 返回 `str` |
| Codec (validate) | `purge.py:2748-2753` | 已有非空校验 | 保持不变，与类型一致 |

- `_required_non_empty_text_value` (purge.py:2644-2655) 在 decode 时即返回 `str`，不把空值传回调用方。
- `_required_sha256_digest_value` (purge.py:2658-2669) 同理返回 `str`。
- DDL 删除双空 CHECK，改为 `TEXT NOT NULL`；schema v14 是 fresh-start，不做旧库兼容。

**Tests**:
- `test_purge_tombstone_table_has_no_session_or_event_log_fk` (test_durable_schema.py:325-326): 验证 `audit_record_ref` 和 `audit_record_digest` 在 NOT NULL 列集合中。
- `test_insert_tombstone_rejects_invalid_audit_record_ref` (test_purge_session.py:2416-2426): 空 ref 被 `_require_non_empty_text` 拒绝。
- `test_insert_tombstone_rejects_invalid_audit_record_digest` (test_purge_session.py:2429-2439): 非 sha256 digest 被 `_require_sha256_digest` 拒绝。
- `test_purge_session_durable_deletes_matrix_and_preserves_replay` (test_purge_session.py:2541-2542): 验证成功路径 tombstone 携带 `audit_record_ref` / `audit_record_digest`。

**Verdict**: FIXED。类型系统、DDL、codec 三层一致表达 S4 invariant。

---

### S4-ADJ-002: open_host 复用 default_log_audit_sink_options — FIXED

**Finding**: audit 默认路径常量与 helper 在 `dayu.host.audit` 和 `dayu.host.open_host` 中重复。

**Evidence**:

Grep for duplicate symbols in `open_host.py`:

```
_AUDIT_ARTIFACT_DIRECTORY_NAME → 0 matches
_AUDIT_JSONL_FILE_NAME → 0 matches
_AUDIT_LOCK_FILE_SUFFIX → 0 matches
_default_audit_jsonl_path → 0 matches
_default_audit_lock_path → 0 matches
_log_audit_sink_options_from_open_host_options → 0 matches
```

- `open_host.py:20-25`: 从 `dayu.host.audit` import `default_log_audit_sink_options`。
- `open_host.py:639-642`: `_LogAuditProjectionCatchupPort` 构造直接调用 `default_log_audit_sink_options(self._options.artifact_root, create_parent_dirs=self._options.create_parent_dirs)`。
- `command.py:224-227`: `_audit_sink_options()` 同样调用同一个 `default_log_audit_sink_options()`。二者共享同一路径派生真源。
- 对比 Tool Trace：`open_host.py` 仍保留 `_tool_trace_sink_options_from_open_host_options` 私有 helper（line 916-932），这是合理的——Tool Trace 未暴露 public factory，其路径常量 `_TOOL_TRACE_ARTIFACT_DIRECTORY_NAME` 等（lines 114-121）属于 `open_host.py` 内部实现。Audit 路径已统一由 `audit.py` 的 `default_log_audit_sink_options` 提供。

**Tests**:
- `test_default_audit_path_is_derived_from_artifact_root` (test_audit_sink.py:576-589): 验证 `default_log_audit_sink_options()` 正确派生 JSONL 路径与 lock 路径。

**Verdict**: FIXED。Audit 路径派生单源化，无重复常量/helper。

---

### S4-ADJ-003: 删除冗余 mkdir — FIXED

**Finding**: `LogAuditSink._append_line` 与 `_append_audit_json_line` 重复创建目录。

**Evidence**:

Grep for `mkdir` in `audit.py`:

```
557: options.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
```

唯一一处 `mkdir` 位于 `_append_audit_json_line`（line 557），作为 audit JSONL append 的目录创建 owner。

`LogAuditSink._append_line`（lines 294-312）:
```python
def _append_line(self, line: AuditJsonLine) -> None:
    _append_audit_json_line(
        self._options,
        line,
        source_keys=(...),
    )
```
不再有自己的 `mkdir` 调用，完全委托给 `_append_audit_json_line`。

**Verdict**: FIXED。目录创建职责单一化为 `_append_audit_json_line`。

---

### S4-ADJ-005: deferred residual — CONFIRMED

Controller adjudication 将 S4-ADJ-005（audit JSONL append 成功但 SQLite commit 失败导致 orphan JSONL line）列为 deferred residual。Fix artifact 明确未扩大处理。当前代码无跨介质原子性方案。

**Verdict**: 仍为 residual，不要求当前修复。符合 adjudication。

---

## New Blocker Check

### Schema tests

`test_durable_schema.py` 中的 `test_purge_tombstone_table_has_no_session_or_event_log_fk`（line 307-347）新增 NOT NULL 断言（lines 325-326），与 DDL 变更一致。所有 schema 测试通过。

### Pyright

Fix artifact 报告 `0 errors, 0 warnings, 0 informations`。类型收窄（`str | None` → `str`）消除了原有 H1 finding 中的类型债务；`open_host.py` 删除的常量和 helper 不影响其他模块；`audit.py` 删除的 `mkdir` 不改变函数签名。

### open_host audit path

`open_host.py:639` 直接调用 `default_log_audit_sink_options(self._options.artifact_root, create_parent_dirs=self._options.create_parent_dirs)`，与 `command.py:224` 的 `_audit_sink_options()` 使用同一 public factory。路径派生一致，无发散风险。

### purge replay

`test_purge_session_durable_deletes_matrix_and_preserves_replay`（test_purge_session.py:2442-2550）验证:
- 首次 purge: `audit_recorder.requests` 包含 1 条记录（line 2543）
- Replay: `result.idempotent_replay is True`，tombstone 相同（line 2514-2515）
- Replay 路径不进入 `_insert_tombstone_and_idempotency`，不触发 audit recorder

### fail-before-success

| 测试 | 层 | 验证 |
|------|-----|------|
| `test_purge_session_durable_audit_failure_rolls_back_tombstone` (line 2553-2576) | durable | OSError → tombstone is None, event count unchanged |
| `test_public_purge_session_audit_append_failure_fails_before_success` (line 2626-2663) | public | `HostApiError(INTERNAL_ERROR, retryable=True)`, tombstone is None, event count unchanged |

Public 路径 `command.py:812-817` 捕获 `(OSError, RuntimeFileLockError)` → `HostApiErrorCode.INTERNAL_ERROR, retryable=True`，不返回 `PurgeSessionResult`。

### No regression in existing functionality

所有改动的测试覆盖保持通过：
- `test_audit_sink.py`: audit JSONL 追加/幂等/冲突/failure 不变
- `test_purge_session.py`: tombstone 插入/读取/replay/validation/delete matrix/rollback 不变
- `test_durable_schema.py`: schema bootstrap/NOT NULL 断言不变

### No new imports / no new public API

修复未新增任何 public export、error code、API shape 或跨层 import。

---

## Final Verdict

**PASS**

三项 accepted findings 全部修复到位:

| ID | Finding | Verdict |
|----|---------|---------|
| S4-ADJ-001 | schema/type/codec non-null audit ref/digest | **FIXED** |
| S4-ADJ-002 | open_host 复用 default_log_audit_sink_options | **FIXED** |
| S4-ADJ-003 | 删除冗余 mkdir | **FIXED** |
| S4-ADJ-005 | orphan JSONL line | **DEFERRED** (residual, per adjudication) |

无新 blocking findings。Schema tests、pyright、open_host audit path、purge replay、fail-before-success 全部验证通过。无 public API shape 变更。
