# Phase 13 Slice 2 Code Review — DeepSeek

## Gate

Phase 13 Slice 2 code review。

## Review Target

- 当前分支 `feat/phase-13-audit-trace-outbox` 相对 HEAD 的未提交 Slice 2 diff
- Implementation artifact: `docs/reviews/phase13-slice2-implementation-codex-20260529.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`
- Schema clarification: `docs/reviews/phase13-schema-version-controller-clarification-20260529.md`

## Files Reviewed

```
dayu/host/tool_trace.py                   (new, 991 lines)
dayu/host/durable/tool_trace.py           (new, 594 lines)
dayu/host/durable/schema.py               (modified, +110 lines)
dayu/host/open_host.py                     (modified, +94 lines)
tests/host/test_tool_trace_projection.py  (new, 390 lines)
tests/host/test_tool_trace_queries.py     (new, 243 lines)
tests/host/test_durable_schema.py         (modified, +98 lines)
docs/reviews/phase13-slice2-implementation-codex-20260529.md
docs/host/implementation-control.md       (modified, gate status only)
```

## Review Checklist

### 1. Tool Trace 只消费 committed EventLog / typed projection input

**PASS.** `ToolTraceProjectionConsumer.apply_event()` 接收 `ProjectionEventView`（typed dataclass），通过 `read_event_by_id(transaction, event.event_id)` 只读已提交 EventLog row。不 import Engine、ToolRuntime、raw EngineEvent。`_extract_tool_trace()` 按 `event.event_class` (Enum) 分发到 `_extract_canonical_trace` / `_extract_diagnostic_trace` / `_extract_usage_trace`，每个分支只通过 `Mapping[str, JsonValue]` 访问 payload 字段名（均为模块级常量）。无 `getattr`/`hasattr`。

### 2. Diagnostic whitelist 足够窄，缺失时跳过不猜测

**PASS.** `_DIAGNOSTIC_EVENT_TYPES = ("ENGINE_EVENT_DIAGNOSTIC", "PROVIDER_PROTOCOL_ERROR")` 仅两个 event type。`_extract_diagnostic_trace()` 对 `ENGINE_EVENT_DIAGNOSTIC` 当 `provider_request_id is None` 时返回 `None`（skip，line 507-511）。`_extract_usage_trace()` 当 `provider_request_id is None` 且 `diagnostic_refs` 为空时返回 `None`（skip，line 561-562）。不用 `getattr`/`hasattr`，不从 payload 语义推断。

### 3. Hot SQLite row / cold JSONL 只作为 diagnostic projection

**PASS.** 两个模块 docstring 均声明 "不参与 Host durable truth、恢复、resume、memory 或 Run 状态迁移"。`host_tool_trace_hot` 通过 `TOOL_TRACE_PROJECTION_TABLES` 加入 `HOST_DURABLE_TABLES`，与 foundation/state/projection 物理隔离。无 Tool Trace import 于 recovery、memory、run_transition 模块。测试验证 `host_runs` / `host_attempts` 在 projection rebuild 后仍为 0。

### 4. Cold writer / hot row failure 只走 projection failure，不推进 checkpoint，不影响 command path

**PASS.** `apply_event()` 内 cold JSONL append 在 hot row insert 之后、checkpoint advance 之前。`ProjectionRunner._process_next_event()` 内 consumer apply 失败被捕获为 `_ProjectionApplyFailed`，由 `run_once()` 调用 `_record_failure()` 并 `break`。测试 `test_cold_writer_failure_records_projection_failure_without_checkpoint` 证实：failures=1，checkpoint_event_sequence=0（未推进），failure row 已写，hot_row is None。Tool Trace 未接入 command path——仅在 `close_projection_catchup_port` composite 中作为 catch-up port。

### 5. Query helpers 是 internal、typed、分页语义明确

**PASS.** `dayu/host/durable/tool_trace.py` 的 `__all__` 导出 `read_tool_trace_by_run`、`find_tool_trace_by_tool_call_id`、`find_tool_trace_by_provider_request_id`、`find_tool_trace_by_diagnostic_ref`、`ToolTraceQueryPage` 等。这些符号：
- 未出现于 `dayu/host/__init__.py`、`dayu/host/api.py`
- 未从 `open_host.py` public 方法调用
- 仅在测试中使用
- `ToolTraceQueryPage` 有 `rows: tuple[ToolTraceHotRow, ...]`、`next_event_sequence: int`、`has_more: bool` — 分页语义清晰
- 所有查询均 `event_sequence > after_event_sequence ORDER BY event_sequence ASC LIMIT limit+1`（"多取一行"判断 has_more），limit 有模块级 `TOOL_TRACE_QUERY_MAX_LIMIT = 500` 上限
- `find_tool_trace_by_diagnostic_ref` 用 `json_each` 匹配 `trace_summary_json` 中的 `diagnostic_refs` 数组，同时匹配 `diagnostic_ref` 列——覆盖精准匹配和 JSON 数组搜索

### 6. open_host 未新增 OpenHostOptions public fields，未改变 command path

**PASS.** `_tool_trace_sink_options_from_open_host_options(options: OpenHostOptions)` 仅读取既有 `options.artifact_root` 和 `options.create_parent_dirs` 派生 `ToolTraceSinkOptions`。未新增 `OpenHostOptions` 字段。Tool Trace catch-up 仅在 `_CompositeProjectionCatchupPort` 中添加一个 port——该 port 只在 opener close 时执行。未修改 `watch_session_events`、EventLog append、Run/Attempt state、terminal transaction、`HostDispatchScheduler`。

### 7. Schema bump 11 → 12 fresh-schema consistent

**PASS.** `HOST_SCHEMA_VERSION = 12`。新增：
- `TABLE_HOST_TOOL_TRACE_HOT = "host_tool_trace_hot"`
- 5 个 partial indexes (WHERE not null)
- DDL 含 `FOREIGN KEY(event_id) REFERENCES event_log(event_id)`、`CHECK (event_sequence > 0)`、`CHECK (event_class IN (...))`、payload/cold ref-diges 成对 CHECK
- `TOOL_TRACE_PROJECTION_TABLES` → `HOST_DURABLE_TABLES`，`TOOL_TRACE_PROJECTION_DDL` + `TOOL_TRACE_PROJECTION_INDEX_DDL` → `HOST_DURABLE_DDL`

测试覆盖：`test_host_schema_version_is_phase13_tool_trace_version`、`test_tool_trace_hot_table_and_indexes_are_created`（验证所有 5 个 index）、`test_projection_schema_constraints_reject_invalid_rows`（验证 cold_ref CHECK 和 FOREIGN KEY CHECK，共新增 2 个约束违反用例）。无旧库兼容读取路径。

### 8. 中文 docstring、严格类型、无 object/Any/无类型签名、无 getattr/hasattr

**PASS.**
- 所有函数均有完整中文 docstring 含参数、返回值、异常
- `getattr`/`hasattr`：两个文件均为 0 匹配
- `object`/`Any` 类型：签名中 0 匹配（仅在 docstring 中出现 "JSON object" 描述文本）
- 所有字段名用模块级常量（如 `_FIELD_TOOL_CALL_ID = "tool_call_id"`），无魔法字符串扩散
- `cast()` 仅在 `isinstance` 检查后的类型缩窄使用（`_diagnostic_refs`、`_payload_ref_from_payload`、`_optional_mapping`）
- `event_class` 比较使用 `EventClass.CANONICAL_FACT` / `EventClass.DIAGNOSTIC` / `EventClass.PROJECTION_SIGNAL` 枚举值，不用字符串

## Findings

### DS-F1-未修复-LOW-`_append_text` flush 但未 fsync

**Evidence:** `dayu/host/tool_trace.py:952-953`

```python
with path.open("a", encoding="utf-8") as handle:
    handle.write(text)
    handle.flush()
```

`flush()` 只确保数据到 OS buffer，不保证落盘。系统崩溃时 in-flight cold JSONL line 可能丢失（非 corruption，因 append-only + line 完整性在文件系统层面通常受保护）。

**Impact:** 极低。Cold JSONL 是 diagnostic projection，不可用于恢复。且 `file_lock` 路径（`lock_path is not None`）同样调用 `_append_text`，lock 不改变 fsync 缺失。丢失的 line 在下次 catch-up 中会被重新投影（`event_id` 去重）。

**Required change:** 无需修改。与 plan 声明的 residual risk 一致："交叉介质 exactly-once 非目标"。若后续 production hardening 需要更强保证，可在 Phase 15 加上 optional `os.fsync`。

### DS-F2-未修复-LOW-cold JSONL 包含完整 `event.payload`

**Evidence:** `dayu/host/tool_trace.py:694`

```python
_FIELD_PAYLOAD: event.payload,
```

cold JSONL line 的 `"payload"` 字段包含 `ProjectionEventView` 的完整 inline payload。对于含大结果（如 tool 返回的财报全文）的事件，单条 JSONL 行可能很大。

**Impact:** 低。Plan 明确 cold JSONL "保存长参数 / 长结果"。这是 by-design 的 cold/archive 行为。hot row 只存 refs/digests，不存大 payload。

**Required change:** 无需修改。若 cold JSONL 行体积成为实际运维问题，可在后续 phase 引入行级 payload 截断或 external ref 机制。

### DS-O1-观察-`apply_event` 内冗余 EventLog row 重读

**Evidence:** `dayu/host/tool_trace.py:297`

```python
row = read_event_by_id(transaction, event.event_id)
```

`ProjectionRunner._process_next_event()` 已从 EventLog 读取 row 并转换为 `ProjectionEventView`。`apply_event()` 再次通过 `read_event_by_id()` 读取相同 row，仅为了获取 `payload_ref`、`payload_digest`、`policy_decision_json`——这些字段不在 `ProjectionEventView` 中。

**Impact:** 无功能影响。二级查询在同一 `HostTransaction` 内，一致性和正确性不变。轻微性能开销（每条 trace event 多一次 SELECT by PK）。

**Required change:** 无需修改。这是 `ProjectionEventView` 当前 contract 的 trade-off——view 只暴露 payload field 子集，不暴露 EventLog row 的 storage/ledger 字段。若后续发现成为性能瓶颈，可在 `ProjectionEventView` 中增加 `payload_ref`、`payload_digest`、`policy_decision_json` 字段。

### DS-O2-观察-`diagnostic_refs` 数组中字符串元素不经去重

**Evidence:** `dayu/host/tool_trace.py:782-795`

```python
refs: list[str] = []
for item in value:
    if isinstance(item, str):
        if item.strip() != "":
            refs.append(item)
        continue
    ...
```

**Impact:** 极低。`diagnostic_refs` 数组元素保留原始顺序，未去重。这对查询无影响（`find_tool_trace_by_diagnostic_ref` 用 `json_each` + `=` 匹配，重复 ref 不影响命中）。`trace_summary` 中的 `diagnostic_refs` 列表可能包含重复字符串。

**Required change:** 无需修改。保持原始数据形态是正确行为，不应在 projection 中隐式去重。

## Adversarial Failure Pass

| Scenario | Behavior | Verdict |
|---|---|---|
| Cold JSONL 目录不存在 (`create_parent_dirs=False`) | `_append_line` 抛 OSError → `_ProjectionApplyFailed` → record failure, no checkpoint advance | PASS |
| 同一 event_id 重复 replay | `insert_tool_trace_hot_row_if_absent` 检测 duplicate → `ProjectionApplyStatus.DUPLICATE` → cold append 被跳过 | PASS |
| EventLog row 与 ProjectionEventView 身份不一致 | `_validate_event_row_identity` 抛 `HostDurableError` → rollback | PASS |
| ENGINE_EVENT_DIAGNOSTIC 无 provider_request_id | `_extract_diagnostic_trace` 返回 `None` → SKIPPED | PASS |
| USAGE_REPORTED 无 provider_request_id 且无 diagnostic refs | `_extract_usage_trace` 返回 `None` → SKIPPED | PASS |
| trace_summary_json 包含 JSON 非法值 | `canonical_json_dumps` 在 `_validate_hot_row` 中抛出 → `HostDurableError` | PASS |
| 文件锁获取超时 | `RuntimeFileLockError` 从 `file_lock` 传播 → `_ProjectionApplyFailed` → record failure | PASS |
| 进程在 cold append 成功后、transaction commit 前崩溃 | Cold line 可能 physical duplicate；hot row 未提交；retry 重新投影同一 event → hot row idempotent insert、cold line 重新 append（可能 duplicate line） | ACCEPTED residual risk |
| 进程在 transaction commit 后、cold append 前崩溃 | Hot row committed、checkpoint advanced；cold line 缺失；retry 时 event behind checkpoint 不重新处理 → cold line 永久缺失 | ACCEPTED residual risk |

注意：上述两个 crash 场景共享同一 root cause——SQLite transaction 与文件 append 无跨介质原子性。Plan §Storage / Schema / Checkpoint Decisions 和 implementation report §Residual Risks 均已明确声明此风险。不影响 Host truth。

## Plan Alignment

| Plan Requirement | Status |
|---|---|
| Slice 2 first step: typed whitelist discovery | PASS — `_CANONICAL_EVENT_TYPES` (14), `_DIAGNOSTIC_EVENT_TYPES` (2), `_PROJECTION_SIGNAL_EVENT_TYPES` (1); 逐字段通过 `_optional_text` 访问 |
| 不消费任意 preview stream delta | PASS — `ProjectionEventFilter` 不含 `EventClass.PREVIEW` |
| `USAGE_REPORTED` 作为 projection_signal | PASS — 使用 `EventClass.PROJECTION_SIGNAL` filter |
| `provider_request_id` diagnostic whitelist gate | PASS — `ENGINE_EVENT_DIAGNOSTIC` 只在有 `provider_request_id` 时投影 |
| Cold writer failure → projection failure only | PASS — 验证通过 |
| Query helpers internal, not Service-facing | PASS — 未导出到 `dayu/host/__init__.py` |
| `RUN_LOST` 不生成 public item | PASS — `_CANONICAL_EVENT_TYPES` 包含 `RUN_LOST` 但当前仅做 canonical trace 抽取，未生成 Outbox item（Outbox 是 Slice 3 职责） |
| 不新增 `OpenHostOptions` 字段 | PASS — 路径从既有 `artifact_root` 派生 |

## Pyright / Test Baseline

- `python -m pyright dayu/host tests/host`: 0 errors, 0 warnings, 0 informations (已验证)
- `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_durable_schema.py`: 25 passed
- `git diff --check`: passed

## Verdict

**PASS** — 无 blocking findings。

Slice 2 实现正确遵守了 accepted plan 的所有硬约束：Tool Trace 只消费 committed EventLog、diagnostic whitelist 足够窄且缺失 refs 时 skip 不猜测、hot/cold 只作为 diagnostic projection、failure 不推进 checkpoint 不影响 command path、query helpers 保持 internal、open_host 不新增 public 字段、schema fresh bump 11→12 且 test 覆盖 table/index/version/constraints。

两个 LOW findings 均为计划预期的 residual risk 或 by-design trade-off，不要求修改。两个 OBSERVATION 为信息性记录，不构成 findings。

### Uncovered / Residual

1. P1 accepted: 跨介质 exactly-once 非目标（plan 和 implementation report 均已声明）。
2. P2 deferred: purge/cleanup/retention 归 Phase 15。
3. 未覆盖：large cold JSONL line（含完整 `event.payload`）的运维影响——当前无行大小上限或截断策略。
4. 未覆盖：`find_tool_trace_by_diagnostic_ref` 的 `json_each` 查询在大数据集上的性能——当前无覆盖 SQLite partial index 完全匹配此模式的 benchmark。

### Docs Decision

不触发 README 更新。本 slice 未新增 public Host API、CLI、config 或项目级使用入口变更。

### Stop Status

未触发 stop condition。所有实现均落在 Slice 2 allowed files 范围内，未出现需要修改 Engine、新增 `OpenHostOptions` public 字段、改变 terminal transaction、或给 `watch_session_events` 加 cursor 的情况。
