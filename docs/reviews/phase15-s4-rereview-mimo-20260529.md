# Phase 15 S4 Re-Review Artifact

## Gate

Phase 15 S4 re-review (AgentMiMo)。只复核 controller adjudication 中 accepted findings 的 fix 落地，不改代码，不 commit/push/PR。

## Re-Review Metadata

- **Controller adjudication**: `docs/reviews/phase15-s4-code-review-controller-adjudication-20260529.md`
- **Fix artifact**: `docs/reviews/phase15-s4-fix-codex-20260529.md`
- **Original reviews**: `docs/reviews/phase15-s4-code-review-mimo-20260529.md`, `docs/reviews/phase15-s4-code-review-ds-20260529.md`
- **Scope**: S4-ADJ-001, S4-ADJ-002, S4-ADJ-003 fix verification; S4-ADJ-005 residual confirmation
- **Date**: 2026-05-29

## Accepted Findings Verification

### S4-ADJ-001 — schema/type/codec non-null audit ref/digest

**FIXED.**

| 层 | 验证 | 证据 |
|---|---|---|
| Schema DDL | `audit_record_ref TEXT NOT NULL`, `audit_record_digest TEXT NOT NULL` | `schema.py:988-989` |
| Row dataclass | `audit_record_ref: str`, `audit_record_digest: str`（无 `| None`） | `purge.py:347-348` |
| Row decode | `_required_non_empty_text_value` / `_required_sha256_digest_value` 读取必填非空 ref 与 sha256 digest | `purge.py:2496-2503` |
| Validation | `_validate_tombstone` 保持 `_require_non_empty_text` + `_require_sha256_digest` | `purge.py:2747-2754` |
| Schema test | `test_purge_tombstone_table_has_no_session_or_event_log_fk` 断言 `audit_record_ref` / `audit_record_digest` 在 `not_null_columns` 中 | `test_durable_schema.py:325-326` |
| Validation test | `test_insert_tombstone_rejects_invalid_audit_record_ref` 验证空 ref 被拒 | `test_purge_session.py:2416-2426` |
| Validation test | `test_insert_tombstone_rejects_invalid_audit_record_digest` 验证非 sha256 digest 被拒 | `test_purge_session.py:2429-2439` |

schema/type/codec 三层一致，runtime validation 保持双重保障。无残留 nullable 读取路径。

### S4-ADJ-002 — open_host 复用 audit.default_log_audit_sink_options 且无重复路径常量/helper

**FIXED.**

| 验证 | 证据 |
|---|---|
| `open_host.py` 导入 `default_log_audit_sink_options` | `open_host.py:24` |
| `open_host.py` 调用 `default_log_audit_sink_options(artifact_root, create_parent_dirs=...)` | `open_host.py:639-642` |
| `open_host.py` 中无 `_AUDIT_ARTIFACT_DIRECTORY_NAME`、`_AUDIT_JSONL_FILE_NAME`、`_AUDIT_LOCK_FILE_SUFFIX` 常量 | grep 确认仅剩 `_TOOL_TRACE_*` 常量 |
| `open_host.py` 中无 `_log_audit_sink_options_from_open_host_options`、`_default_audit_jsonl_path`、`_default_audit_lock_path` 函数 | grep 确认不存在 |
| `command.py` 同样导入并使用 `default_log_audit_sink_options` | `command.py:21`、`command.py:224-227` |
| `test_audit_sink.py` 验证 `default_log_audit_sink_options` 派生路径正确 | `test_audit_sink.py:576-589` |

audit path derivation 现在唯一真源在 `dayu/host/audit.py`，`open_host.py` 和 `command.py` 均通过 public factory 复用。

### S4-ADJ-003 — 删除冗余 mkdir

**FIXED.**

| 验证 | 证据 |
|---|---|
| `LogAuditSink._append_line` 不含 `mkdir` 调用 | `audit.py:294-312`，直接调用 `_append_audit_json_line` |
| `_append_audit_json_line` 拥有目录创建 | `audit.py:556-557`：`options.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)` |

目录创建职责单一，由 `_append_audit_json_line` 统一 owner。

### S4-ADJ-005 — audit JSONL orphan line residual

**仍为 residual，不要求当前 fix。**

fix artifact 已明确声明：本次 fix 未扩大到跨介质 atomicity 方案。S4-ADJ-005 描述的场景（audit append 成功后 SQLite commit 失败留下 orphan JSONL line）是文件系统与 SQLite 非共享事务的内在限制，不违反 S4 fail-before-success invariant。

## New Blocker Check

| 检查项 | 结果 | 证据 |
|---|---|---|
| schema tests 通过 | PASS | `test_durable_schema.py` 全部通过 |
| purge session tests 通过 | PASS | `test_purge_session.py` 全部通过 |
| audit sink tests 通过 | PASS | `test_audit_sink.py` 全部通过 |
| pyright 0 errors | PASS | `pyright dayu/host/audit.py dayu/host/durable/purge.py dayu/host/durable/schema.py dayu/host/command.py dayu/host/open_host.py tests/host` → 0 errors |
| open_host audit path 正确 | PASS | `default_log_audit_sink_options` 返回 `artifact_root / "audit" / "host-audit.jsonl"`，与原常量语义一致 |
| purge replay 不触发 audit append | PASS | `purge_session_durable` replay 路径直接 return，不进入 `_insert_tombstone_and_idempotency` |
| purge fail-before-success 完整 | PASS | `test_public_purge_session_audit_append_failure_fails_before_success` 验证 `INTERNAL_ERROR` + `retryable=True` + tombstone 为 None + event count 不变 |
| 无新增 `Any`/`object`/`hasattr`/`getattr` | PASS | 全部新增/修改 dataclass 使用严格类型，无 type 逃避 |
| 无反向依赖 | PASS | `purge.py` 不 import `audit.py`/`command.py`/`open_host.py` |

**无新 blocker。**

## Validation

```text
pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py tests/host/test_durable_schema.py -q
→ 54 passed in 0.57s

python -m pyright dayu/host/audit.py dayu/host/durable/purge.py dayu/host/durable/schema.py dayu/host/command.py dayu/host/open_host.py tests/host
→ 0 errors, 0 warnings, 0 informations
```

## Conclusion

**PASS.**

三项 accepted findings 全部正确落地：

1. **S4-ADJ-001**: schema DDL `TEXT NOT NULL` + dataclass `str` + codec `_required_non_empty_text_value` / `_required_sha256_digest_value` 三层一致，测试覆盖 NOT NULL 断言与空值/digest 拒绝。
2. **S4-ADJ-002**: `open_host.py` 和 `command.py` 均通过 `default_log_audit_sink_options` 复用 audit path derivation，旧重复常量和 helper 已完全删除。
3. **S4-ADJ-003**: `LogAuditSink._append_line` 不再调用 `mkdir`，目录创建由 `_append_audit_json_line` 统一负责。

S4-ADJ-005 仍为 deferred residual，不要求当前 fix。无新 blocker。S4 fix 可以合入。
