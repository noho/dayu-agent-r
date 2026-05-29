# Phase 15 Slice P15-S4 Fix Artifact

## Scope

Fix pass for Phase 15 Slice P15-S4 Audit JSONL Retention And Tombstone Audit Record.

Input adjudication: `docs/reviews/phase15-s4-code-review-controller-adjudication-20260529.md`.

本次只修复 controller accepted findings S4-ADJ-001、S4-ADJ-002、S4-ADJ-003；未处理已拒绝的 S4-ADJ-004，未扩大处理 deferred residual S4-ADJ-005，未 commit / push / PR。

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/purge.py`
- `dayu/host/audit.py`
- `dayu/host/open_host.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_audit_sink.py`

## Accepted Findings Fixed

### S4-ADJ-001

Finding: fresh schema/type/codec 层仍把 `PurgeTombstoneRow.audit_record_ref` / `audit_record_digest` 表达为可空，S4 invariant 只靠 runtime check。

Fix:

- `host_purge_tombstones.audit_record_ref` 与 `audit_record_digest` 从 `TEXT NULL` 改为 `TEXT NOT NULL`，删除双空 CHECK。schema v14 是 fresh-start，因此不做旧库兼容或迁移读取。
- `PurgeTombstoneRow.audit_record_ref` 与 `audit_record_digest` 类型改为 `str`。
- tombstone row decode 改为读取必填非空 ref 与必填 sha256 digest；新增私有 codec helper 返回 typed value，避免把只做校验的 helper 当作取值函数。
- tombstone validation 保持非空 ref 与 sha256 digest 校验。
- 测试新增 schema NOT NULL 断言，并把 malformed tombstone 测试改为验证空 ref / 非 sha256 digest 被拒绝。

### S4-ADJ-002

Finding: audit 默认路径常量与 helper 在 `dayu.host.audit` 和 `dayu.host.open_host` 中重复。

Fix:

- `open_host.py` 直接复用 `dayu.host.audit.default_log_audit_sink_options(...)`。
- 删除 `open_host.py` 内重复的 audit 默认路径常量、`_log_audit_sink_options_from_open_host_options`、`_default_audit_jsonl_path`、`_default_audit_lock_path`。
- `tests/host/test_audit_sink.py` 改为验证 `default_log_audit_sink_options(...)` 派生的 JSONL 路径与 lock 路径。

### S4-ADJ-003

Finding: `LogAuditSink._append_line` 与 `_append_audit_json_line` 重复创建目录。

Fix:

- 删除 `LogAuditSink._append_line` 中的冗余 `mkdir`。
- 保留 `_append_audit_json_line` 作为 audit JSONL append 的目录创建 owner。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py tests/host/test_durable_schema.py tests/host/test_open_host_runtime.py -q
```

结果：

```text
63 passed in 0.75s
```

已运行：

```bash
source .venv/bin/activate && python -m pyright dayu/host/audit.py dayu/host/durable/audit.py dayu/host/durable/purge.py dayu/host/durable/schema.py dayu/host/command.py dayu/host/open_host.py tests/host
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## README Decision

触发检查：本次修改触及 `dayu/host/`、`dayu/host/durable/schema.py`、`dayu/host/open_host.py` 与 `tests/host/`。

结论：不更新 README。修复内容是 S4 内部 storage contract、codec 类型表达、默认 audit sink options 复用和测试同步；未改变 public API shape、OpenHostOptions、命令使用方式、配置入口、分层关系或测试手册职责。现有 README 对 `purge_session` destructive cleanup、tombstone replay、purge 后 read fail-closed 以及测试分层说明仍然成立。

## Residual Risks

- S4-ADJ-005 仍按 controller adjudication 作为 deferred residual：audit JSONL append 成功但后续 SQLite commit 失败时，可能留下 orphan audit JSONL line。当前 fix 未扩大到跨介质 atomicity 方案。
- 本 fix 未修改 `utils/` analyze helper；S4 已提供 `audit_json_line_marks_purged_source_eventlog_facts(...)` 作为当前边界内的 tombstone audit line 识别 helper。
