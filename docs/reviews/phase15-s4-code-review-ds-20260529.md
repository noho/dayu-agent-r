# Phase 15 Slice P15-S4 Code Review Artifact

## Gate

Phase 15 S4 code review (AgentDS), per Gateflow-governed review. 只审查 S4 diff，不改代码，不 commit/push/PR。

## Review Metadata

- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- **Implementation artifact**: `docs/reviews/phase15-s4-implementation-codex-20260529.md`
- **Review output**: `docs/reviews/phase15-s4-code-review-ds-20260529.md`
- **Scope**: audit JSONL retention and tombstone audit record (Slice P15-S4 only)
- **Date**: 2026-05-29

## Changed Files (Diff)

| File | Lines changed | Role |
| --- | --- | --- |
| `dayu/host/audit.py` | +216 | New purge tombstone audit line builder/appender/recognizer; extracted `_append_audit_json_line` helper from `LogAuditSink`; `default_log_audit_sink_options` public factory |
| `dayu/host/command.py` | +60 | `_PurgeAuditJsonlRecorder` injection; `OSError`/`RuntimeFileLockError` → `INTERNAL_ERROR` mapping; `_audit_sink_options()` derivation from durable store |
| `dayu/host/durable/purge.py` | +150 | Typed `PurgeTombstoneAuditRecorder` Protocol; `PurgeTombstoneAuditRecordRequest`/`Result`; audit call before tombstone insert; tombstone validation enforces non-null audit fields |
| `tests/host/test_audit_sink.py` | +103 | Purge audit line append-only idempotence, field content, recognition |
| `tests/host/test_purge_session.py` | +321 | Tombstone audit ref/digest assertions; durable audit failure rollback; public purge success audit line assertions; public audit failure fail-before-success |

## Validation

```text
pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py -q
→ 33 passed in 0.48s

python -m pyright dayu/host/audit.py dayu/host/durable/purge.py dayu/host/command.py tests/host
→ 0 errors, 0 warnings, 0 informations
```

## Findings

### BLOCKING

None.

### HIGH

**H1. `PurgeTombstoneRow` type annotations mismatch runtime contract**

`PurgeTombstoneRow.audit_record_ref: str | None` 和 `audit_record_digest: str | None` 在当前 S4 后运行时必然非空（`_validate_tombstone` 在 line 2719 强制拒绝 None），但类型标注仍为 `str | None`。这意味着：
- 所有读取 tombstone 的调用方都必须做不必要的 None 检查或使用 `cast` 绕过类型系统。
- 类型系统未能表达 S4 建立的新 invariant：valid tombstone row 必然包含 audit record ref/digest。
- `insert_purge_tombstone` 调用处传入 `audit_record.audit_record_ref`（类型为 `str`），pyright 通过仅因 dataclass 类型允许 `str` 赋值给 `str | None`，但反向读取路径会因 None 检查产生多余分支。

**建议**：将 `PurgeTombstoneRow` 的 `audit_record_ref` 和 `audit_record_digest` 类型收窄为 `str`。若需兼容旧 schema（NULLABLE column），应在 codec 层（`insert_purge_tombstone` / `_read_purge_tombstone_row`）做 None → 抛异常的边界校验，而非在 dataclass 层面保持宽松类型。

**严重性**：不阻塞 S4 合入，但属于类型安全债务，应在 S6 或即刻修复。

### MEDIUM

**M1. `default_log_audit_sink_options` 与 `open_host.py` 路径常量重复**

`dayu/host/audit.py` 新增常量 `_AUDIT_ARTIFACT_DIRECTORY_NAME = "audit"`、`_AUDIT_JSONL_FILE_NAME = "host-audit.jsonl"`、`_AUDIT_LOCK_FILE_SUFFIX = ".lock"`（lines 86-88）以及 `default_log_audit_sink_options()`（line 182），与 `dayu/host/open_host.py` lines 113-119 的私有常量和 `_log_audit_sink_options_from_open_host_options()` / `_default_audit_jsonl_path()` / `_default_audit_lock_path()` 语义完全重复。

- Audit path derivation logic 现在存在于两个模块中，各有独立常量定义。若未来变更 audit 目录名或文件名，需改两处。
- CLAUDE.md 要求"重复逻辑必须抽取"。虽然 plan 限制 S4 不能改 `open_host.py`，但 S4 选择了在 `audit.py` 新增完整重复而非仅在 `open_host.py` 暴露已有逻辑的方式。
- `command.py` 的 `_audit_sink_options()` 使用 `audit.py` 的新函数；`open_host.py` 的 opener 仍使用自己的私有函数。二者路径一致但无编译期保证。

**建议**：S6 统一：删 `open_host.py` 的私有常量和 `_default_audit_jsonl_path`/`_default_audit_lock_path`/`_log_audit_sink_options_from_open_host_options`，全部改用 `audit.py` 的 `default_log_audit_sink_options`。

**严重性**：不阻塞 S4，但为 S6 必须项。

**M2. `LogAuditSink._append_line` 冗余 `mkdir` 调用**

`LogAuditSink._append_line`（audit.py line 303）在调用 `_append_audit_json_line` 之前先执行 `self._options.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)`，而 `_append_audit_json_line`（line 558）对同一路径再次执行 `mkdir(parents=True, exist_ok=True)`。功能上无害（exist_ok=True），但逻辑冗余：`_append_audit_json_line` 既然设计为独立 helper（被 `LogAuditSink._append_line` 和 `append_purge_tombstone_audit_record` 两处调用），`_append_line` 就不应再做前置目录创建。

**建议**：删除 `LogAuditSink._append_line` 中的 `mkdir` 调用（lines 303-304），完全依赖 `_append_audit_json_line` 内部的目录创建。

### LOW

**L1. `_RecordingAuditRecorder.requests` 使用 `cast` 无必要**

`tests/host/test_purge_session.py` 中 `_RecordingAuditRecorder` 的 `requests` 字段初始化为 `()`（空 tuple），后续通过 `self.requests + (request,)` 累加。类型推断可自然推导为 `tuple[PurgeTombstoneAuditRecordRequest, ...]`，无需 `cast`。

**L2. Audit JSONL orphan line 风险已正确识别但未量化**

Implementation artifact 已将"audit append 成功后 SQLite commit 失败导致 orphan audit line"列为 residual risk。这是文件系统与 SQLite 非原子性的内在限制，非 S4 缺陷。但当前测试未覆盖此场景：若 SQLite commit 在 audit append 之后、tombstone insert 期间失败（如磁盘满），测试路径仅验证了 audit append 本身的失败导致 rollback，未验证 commit 级失败。

**建议**：在 S5/S6 考虑增加对 tombstone-less audit line 的 query helper 容忍度，或至少文档化此场景的操作影响。

### PASS（逐项检查）

| # | 检查项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | public purge_session 成功返回前一定已经 append purge tombstone audit JSONL line | **PASS** | `_insert_tombstone_and_idempotency` (purge.py:1613) 先调用 `audit_recorder.record_purge_tombstone_audit()`，然后才 `insert_purge_tombstone()` |
| 2 | tombstone row 带 `audit_record_ref` / `audit_record_digest` | **PASS** | `PurgeTombstoneRow` 构造时传入 `audit_record.audit_record_ref` / `audit_record.audit_record_digest` (purge.py:1648-1649)；`_validate_tombstone` 强制非空 (purge.py:2719-2728) |
| 3 | audit append failure 时 rollback，不留下 successful tombstone，不返回 PurgeSessionResult | **PASS** | Audit 在 `_insert_tombstone_and_idempotency` 内、tombstone insert 前调用；失败时异常穿透 transaction runner 触发 rollback；`test_purge_session_durable_audit_failure_rolls_back_tombstone` 和 `test_public_purge_session_audit_append_failure_fails_before_success` 均通过 |
| 4 | replay 不重复追加第二个 tombstone 或第二条 audit line | **PASS** | Replay path (`_result_for_replay_decision`) 直接返回既有 tombstone，不进入 `_insert_tombstone_and_idempotency`，故不调用 audit recorder；audit line 的 `_append_text_if_absent` 基于 source_key + line_digest 幂等跳过 |
| 5 | 既有 EventLog-derived audit JSONL 保留，不 rewrite/truncate/delete | **PASS** | `_append_text` 使用 `open(path, "a")` 追加模式；`test_purge_tombstone_audit_line_is_append_only_and_recognizable` 验证既有行保留（`assert lines[0]["event_id"] == "event-1"`）；`test_public_purge_session_appends_tombstone_audit_jsonl` 同样验证 |
| 6 | audit marker rows 指向 deleted EventLog 不阻塞 purge | **PASS** | S2 的 delete matrix 在步骤 1 中先删除 `host_audit_sink_markers`，再删除 EventLog；S4 未改变此顺序 |
| 7 | durable 层不 import JSONL sink | **PASS** | `dayu/host/durable/purge.py` 使用 `PurgeTombstoneAuditRecorder` Protocol (line 488)，不 import `dayu.host.audit`；具体 JSONL 实现由 `command.py` 的 `_PurgeAuditJsonlRecorder` 注入 |
| 8 | 不引入 `Any`/`object`/extra payload/`hasattr`/`getattr` | **PASS** | 所有新增 dataclass 字段严格类型化；`Protocol` 的 exception 用 `Exception` 基类但 docstring 已说明语义；无 `Any`、无 `object`、无 `hasattr`/`getattr` |
| 9 | error mapping 使用现有 `HostApiErrorCode`，不新增 public API shape | **PASS** | Audit 失败映射为 `HostApiErrorCode.INTERNAL_ERROR` + `retryable=True` (command.py:814-817)；无新增 error code |
| 10 | test 覆盖 fail-before-success | **PASS** | `test_purge_session_durable_audit_failure_rolls_back_tombstone` (durable 层) + `test_public_purge_session_audit_append_failure_fails_before_success` (public 层) |
| 11 | test 覆盖 audit line fields | **PASS** | `test_purge_tombstone_audit_line_is_append_only_and_recognizable` 和 `test_public_purge_session_appends_tombstone_audit_jsonl` 验证 session_id、tombstone_ref、deleted_counts_digest、reason、actor、source、source_eventlog_facts_purged、audit_record_ref 等全部关键字段 |
| 12 | test 覆盖 replay | **PASS** | `test_purge_session_durable_deletes_matrix_and_preserves_replay` 增强后验证 replay result 的 tombstone 携带 audit ref/digest |
| 13 | test 覆盖 failure rollback | **PASS** | Durable 层：OSError → tombstone is None, event count unchanged；Public 层：OSError → `HostApiError(INTERNAL_ERROR, retryable=True)`, tombstone is None, event count unchanged |
| 14 | README decision 合理 | **PASS** | S4 未改变 public API shape、命令用法、配置入口或 README 面向读者的稳定操作说明；README 更新留在 S6 |

## Architecture / Layering Check

```
command.py (_PurgeAuditJsonlRecorder)
    │  implements PurgeTombstoneAuditRecorder (Protocol defined in durable/purge.py)
    │  calls append_purge_tombstone_audit_record() from audit.py
    ▼
audit.py (append_purge_tombstone_audit_record, build_purge_tombstone_audit_json_line)
    │  uses _append_audit_json_line (extracted from LogAuditSink._append_line)
    │  writes to filesystem JSONL
    ▼
durable/purge.py (_insert_tombstone_and_idempotency)
    │  calls audit_recorder.record_purge_tombstone_audit() via Protocol
    │  validates result, writes tombstone + idempotency to SQLite
    ▼
SQLite DB + Audit JSONL file
```

分层正确：
- `durable/purge.py` 只表达"需要 audit ref/digest"的下层契约，不 import JSONL sink（满足 plan 约束）。
- `command.py` 是 wiring 层，负责从 durable store options 派生 sink options 并注入具体 recorder。
- `audit.py` 是 audit sink 实现层，拥有 append-only JSONL 写入逻辑和 purge line builder。
- 无反向依赖，无 `dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins` 泄露。

## Residual Risk Classification

| Risk | Classification | Owner |
| --- | --- | --- |
| Audit JSONL orphan line（audit append 成功 → SQLite commit 失败） | 已识别，非 S4 阻断；文件系统与 SQLite 无共享事务是已知限制 | S6 / follow-up audit tooling |
| `PurgeTombstoneRow` 类型标注过宽（`str \| None` vs 实际必非空） | 类型安全债务，S6 修复 | S6 |
| `open_host.py` 与 `audit.py` 路径常量重复 | S6 统一 | S6 |
| `LogAuditSink._append_line` 冗余 mkdir | 洁净度问题，S6 清理 | S6 |
| 不同 `client_request_id` 对已 purge Session 重试 → orphan audit line 可能 | 极端边缘场景，不影响正确性 | follow-up |

## Final Verdict

**PASS** — 无 blocking 发现。

S4 实现正确达成 plan 中规定的所有 release-blocking invariant：

1. public `purge_session` 成功返回前必然已追加 purge tombstone audit JSONL line（fail-before-success）。
2. Tombstone row 携带 `audit_record_ref` / `audit_record_digest`。
3. Audit append failure 触发 transaction rollback，不留 successful tombstone，不返回 `PurgeSessionResult(purged=True)`。
4. Replay 路径不重复追加 audit line 或 tombstone。
5. 既有 EventLog-derived audit JSONL 在 append-only 模式下完整保留。
6. Durable 层不 import JSONL sink，通过 Protocol 保持下层边界。
7. Error mapping 复用现有 `HostApiErrorCode`，不新增 public API shape。
8. 类型严格、无 `Any`/`object`/extra payload/`hasattr`/`getattr`。
9. 测试覆盖 fail-before-success、audit line fields、replay、failure rollback。

三项 MEDIUM 发现（类型标注、路径常量重复、冗余 mkdir）建议在 S6 修复；不阻塞 S4 合入。
