# Phase 13 Slice 1 Code Review

## Gate

Phase 13 Slice 1 code review。

## Review Target

当前分支 `feat/phase-13-audit-trace-outbox` 未提交 Slice 1 diff：
- `dayu/host/audit.py`
- `dayu/host/durable/audit.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_durable_schema.py`
- `docs/host/implementation-control.md`（仅 gate status）

Implementation artifact：`docs/reviews/phase13-slice1-implementation-codex-20260529.md`

Accepted plan：`docs/host/phase13-audit-tool-trace-outbox-plan.md`

Controller adjudication：`docs/reviews/phase13-plan-rereview-controller-adjudication-20260529.md`

## Review Scope Verification

所有变更文件均在 Slice 1 allowed files 列表内。`docs/host/implementation-control.md` 仅更新 gate status 文本，未修改 implementation behavior。

## Validation Re-run

```
pytest tests/host/test_audit_sink.py tests/host/test_durable_schema.py -q
  22 passed

pyright dayu/host/audit.py dayu/host/durable/audit.py dayu/host/durable/schema.py
  dayu/host/open_host.py tests/host/test_audit_sink.py tests/host/test_durable_schema.py
  0 errors, 0 warnings, 0 informations

git diff --check: passed
```

## Key Design Decisions Verified

### 1. LogAuditSink 只消费 committed canonical EventLog

`LogAuditSink.event_filter` 返回仅包含 `EventClass.CANONICAL_FACT` 的 `ProjectionEventFilter`，`event_types=None` 表示消费该 class 下全部类型。不消费 `PREVIEW` class。`ProjectionRunner` 在 committed 事务中调用 `apply_event`，event 来源为已提交 EventLog。验证通过。

### 2. host_audit_sink_markers 只是 sink-local idempotency marker

Durable helper `dayu/host/durable/audit.py` 提供 `read_audit_sink_marker` 与 `insert_audit_sink_marker_if_absent`。Marker 表 schema 定义在 `schema.py`，归入 `AUDIT_PROJECTION_TABLES`，不与 governance truth 表混入同一 tuple。Marker 只在 JSONL append 成功后写入，用于避免普通 retry 重复 append。实现 artifact 明确声明 marker 不是 audit truth。验证通过。

### 3. JSONL append + marker/checkpoint 顺序

`apply_event` 内部顺序：
1. `read_audit_sink_marker` → 存在则返回 DUPLICATE（不写文件）
2. `read_event_by_id` → 取 EventLog typed row
3. `build_audit_json_line` → 构造带 `line_digest` 的 audit line
4. `_append_line` → 写 JSONL（文件 I/O side effect，在 SQLite 事务外）
5. `insert_audit_sink_marker_if_absent` → 写 marker（在 SQLite 事务内）

`ProjectionRunner` 在 `apply_event` 返回 APPLIED/DUPLICATE 后，在同一事务中推进 checkpoint。若步骤 5 抛异常，runner 记录 projection failure，checkpoint 不推进。

**Accepted residual 确认**：文件 append 在 marker 写入前执行。若进程在步骤 4 成功、步骤 5 提交前崩溃，物理 JSONL 可能出现重复 `event_id` 行。这不影响 Host truth。实现与 accepted plan residual 一致。验证通过。

### 4. File write / lock failure 只走 projection failure

`_append_line` 抛出 `OSError` 或 `RuntimeFileLockError` 时，异常向上传播至 `ProjectionRunner._process_next_event`，runner 捕获后调用 `_record_failure` 写入 `host_projection_failures` 并 break 当前 batch。checkpoint 不推进，不回滚 EventLog，不影响 command path。测试 `test_file_write_failure_records_projection_failure_without_checkpoint` 覆盖此场景。验证通过。

### 5. open_host 接线

- 未新增 `OpenHostOptions` public 字段。
- `_log_audit_sink_options_from_open_host_options` 从 `artifact_root` 派生默认路径，使用 `_default_audit_jsonl_path` 与 `_default_audit_lock_path`。
- `_PublicHostHandle` 构造签名未变。
- `HostDispatchScheduler.open()` 仍接收 `_MemoryProjectionCatchupPort`（仅 memory），close path 接收 `_CompositeProjectionCatchupPort`（memory + audit）。
- Command path、EventLog append、Run/Attempt state、terminal transaction、`watch_session_events` 均未修改。
- `OpenHostOptions` diff 只新增 import 和 private helpers。验证通过。

### 6. Schema bump 到 11

`HOST_SCHEMA_VERSION` 从 10 改为 11。新增 `TABLE_HOST_AUDIT_SINK_MARKERS` 常量、DDL 和 tuple 注册。DDL 包含 `event_id TEXT PRIMARY KEY`、`event_sequence INTEGER NOT NULL CHECK (event_sequence > 0)`、`line_digest TEXT NOT NULL`、`written_at TEXT NOT NULL`，以及两个 FOREIGN KEY 引用 `event_log(event_id)` 和 `event_log(event_sequence)`。`AUDIT_PROJECTION_TABLES` 与 `AUDIT_PROJECTION_DDL` 按正确顺序加入 `HOST_DURABLE_TABLES` 与 `HOST_DURABLE_DDL`。测试 `test_audit_sink_marker_table_is_created` 验证 fresh bootstrap。测试 `test_projection_schema_constraints_reject_invalid_rows` 覆盖 event_sequence <= 0 与 FK 违反场景。验证通过。

### 7. 编码硬约束

- 中文 docstring：所有 public 函数、类、模块均有中文概览和参数/返回值/异常 docstring。验证通过。
- 严格类型：无 `object`、`Any`、无类型参数、无类型返回值。`JsonValue` 是项目标准 JSON 联合类型。验证通过。
- 无 `getattr`/`hasattr` 逃避类型：payload 字段访问使用 `Mapping.get()`。验证通过。
- 无魔法字符串扩散：audit line 字段名全部定义为模块级私有常量（`_AUDIT_FIELD_*`）。`_AUDIT_LINE_SCHEMA_VERSION = 1` 是 schema version 常量。`_PRINCIPAL_CLAIM_NAMES` 使用 `frozenset`。验证通过。
- 模块级私有辅助函数：`_append_text`、`_operation_context_refs`、`_principal_from_payload`、`_policy_decision_summary`、`_reason_value`、`_json_value_from_text`、`_optional_mapping`、`_optional_text_from_payload`、`_require_path`、`_utc_now_text` 均为模块级私有函数。无嵌套函数/类。验证通过。

### 8. 测试覆盖

| 计划要求 | 测试覆盖 |
|---------|---------|
| JSONL line 字段完整性 | `test_jsonl_line_contains_required_audit_fields` ✓ |
| checkpoint / duplicate replay 不重复 logical audit event | `test_marker_prevents_duplicate_append_when_checkpoint_replays` ✓ |
| 文件写失败只写 projection failure，不推进 checkpoint | `test_file_write_failure_records_projection_failure_without_checkpoint` ✓ |
| audit sink 不修改 Run / Attempt / EventLog | `test_audit_sink_does_not_modify_governance_or_event_log` ✓ |
| 默认路径从 artifact_root 派生 | `test_default_audit_path_is_derived_from_artifact_root` ✓ |
| Schema fresh bootstrap 创建 marker table | `test_audit_sink_marker_table_is_created` (durable_schema) ✓ |
| Schema 约束拒绝无效行 | `test_projection_schema_constraints_reject_invalid_rows` (durable_schema) ✓ |

## Findings

### F1-未修复-P3-_CompositeProjectionCatchupPort 不隔离子 port 异常

**Evidence**：`open_host.py` `_CompositeProjectionCatchupPort.catch_up_projection()` 顺序遍历 ports 并调用 `catch_up_projection()`，不捕获子 port 异常：

```python
def catch_up_projection(self) -> None:
    for port in self.ports:
        port.catch_up_projection()
```

close 路径结构为：

```python
try:
    await self._scheduler.close()
finally:
    try:
        self._projection_catchup_port.catch_up_projection()
    finally:
        self._command_handle.close()
```

**Impact**：若 memory projection catch-up 成功但 audit projection catch-up 失败，异常会从 composite port 传播到 close 路径。`command_handle.close()` 仍在 finally 中执行（durable store 正常关闭），但 audit 的失败会掩盖 `__aexit__` 中 user code 的原始异常（若存在）。此外，若 memory catch-up 失败，audit catch-up 不会执行。

这符合 plan 中"每个 sink failure 只记录日志 / failure row，close 不伪造 command facts"的意图——projection failure 已由 `ProjectionRunner` 记录到 `host_projection_failures`。但 composite port 未 catch 子 port 异常意味着 close 路径的行为取决于子 port 失败顺序，而非独立隔离。

**Required change**：建议 `_CompositeProjectionCatchupPort.catch_up_projection()` 捕获每个子 port 异常并 log，确保所有 port 都有机会执行：

```python
def catch_up_projection(self) -> None:
    for port in self.ports:
        try:
            port.catch_up_projection()
        except Exception:
            _LOGGER.error("composite projection catch-up port failed", exc_info=True)
```

这是 P3 建议，不阻塞当前 slice。

### F2-未修复-P3-缺少 marker 冲突路径测试

**Evidence**：`dayu/host/durable/audit.py:109-114` 存在 marker 冲突检测逻辑：

```python
if (
    existing.event_sequence != event_sequence
    or existing.line_digest != line_digest
):
    raise HostDurableError("audit sink marker conflicts with audit line")
```

**Impact**：当同一 `event_id` 已有 marker 但 `event_sequence` 或 `line_digest` 不一致时，`insert_audit_sink_marker_if_absent` 抛出 `HostDurableError`，`ProjectionRunner` 记录 failure。此路径是防御性分支（正常情况下同一 event_id 的 sequence 和 digest 不应变化），但当前测试未覆盖。

**Required change**：建议在 `test_audit_sink.py` 中新增测试：手动插入一个 marker（使用不同的 event_sequence 或 line_digest），然后验证 `apply_event` 导致 projection failure 被记录。

这是 P3 建议，marker 冲突是极端防御性场景。

### F3-未修复-P3-catch_up_log_audit_sink_projection batch loop 遇 failure 立即终止

**Evidence**：`audit.py:373-374`：

```python
if batch_result.failures > 0 or batch_result.events_scanned < batch_size:
    break
```

**Impact**：若一个 batch 中某个 event 导致 failure（如 marker 冲突或文件写入失败），该 batch 剩余 event 不会被处理。这些 event 需要下次 catch-up 调用才能重试。在 close 路径中，如果这是最后一次 catch-up，剩余 event 可能延迟到下次 open 时才被处理。

这不影响 Host truth（EventLog 和 checkpoint 不受影响），但 audit JSONL 可能存在短暂滞后。

**Required change**：建议在 break 前 log warning 说明有剩余 event 未处理。这是 P3 建议，不阻塞当前 slice。

## Verdict

**PASS**。无 blocking findings。3 个 P3 建议项，均为防御性改进，不影响 Slice 1 正确性。

实现与 accepted plan 一致：
- LogAuditSink 只消费 committed canonical EventLog，不消费 preview。
- host_audit_sink_markers 只是 sink-local idempotency marker，不是 audit truth。
- JSONL append + marker/checkpoint 顺序符合 accepted residual。
- File write / lock failure 只走 projection failure，不影响 command path。
- open_host 接线未新增 OpenHostOptions public fields，未改变 command path、EventLog append、Run/Attempt state、terminal transaction、watch_session_events。
- Schema bump 到 11 是 fresh-schema consistent，测试覆盖完整。
- 编码硬约束全部满足：中文 docstring、严格类型、无 object/Any、无 getattr/hasattr 逃避类型、无魔法字符串扩散。
