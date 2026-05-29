# Phase 13 Aggregate Deepreview — AgentMiMo

**Reviewer**: AgentMiMo
**Date**: 2026-05-29
**Branch**: `feat/phase-13-audit-trace-outbox`
**Base**: `main`
**Scope**: Phase 13 全部 diff（49 files, +11439/-21）与全部 artifacts

## Review Inputs

- Design truth: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`
- Slice 1-4 code review artifacts & controller adjudications

## Aggregate Validation

| Check | Result |
|---|---|
| pytest (plan-listed 96+) | **830 passed, 1 FAILED** |
| pyright dayu/host tests/host | 0 errors, 0 warnings |
| git diff --check | passed |
| tests/README.md unchanged | confirmed — no trigger |

**pytest failure**: `tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth`

---

## Slice Completeness

### Slice 1: LogAuditSink JSONL

- `dayu/host/audit.py` (577 lines): `LogAuditSink` projection consumer, `LogAuditSinkOptions`, `AuditJsonLine`, `build_audit_json_line`, `catch_up_log_audit_sink_projection` — **complete**.
- `dayu/host/durable/audit.py` (187 lines): audit sink-local marker durable helper — **complete**.
- Schema: `host_audit_sink_markers` table DDL with FK to event_log — **complete**.
- Tests: `test_audit_sink.py` (387 lines) — field integrity, marker dedup, file write failure, no governance mutation, default path derivation — **complete**.

### Slice 2: Tool Trace Hot/Cold

- `dayu/host/tool_trace.py` (990 lines): `ToolTraceProjectionConsumer`, `ToolTraceSinkOptions`, `ToolTraceColdLine`, `catch_up_tool_trace_projection`, whitelist event extraction for canonical/diagnostic/projection_signal — **complete**.
- `dayu/host/durable/tool_trace.py` (593 lines): hot projection durable helper, query helpers by run/tool_call/provider_request/diagnostic_ref — **complete**.
- Schema: `host_tool_trace_hot` table DDL with 5 conditional indexes — **complete**.
- Tests: `test_tool_trace_projection.py` (389 lines), `test_tool_trace_queries.py` (242 lines) — **complete**.

### Slice 3: Outbox Durable Projection

- `dayu/host/outbox.py` (527 lines): `OutboxTerminalProjectionConsumer`, identity builder, row builder, `catch_up_outbox_terminal_projection` — **complete**.
- `dayu/host/durable/outbox.py` (877 lines): terminal item read/insert/drain/idempotency — **complete**.
- Schema: `host_outbox_terminal_items` + `host_outbox_drain_idempotency` table DDL with 3 indexes — **complete**.
- Tests: `test_outbox_durable.py` (318 lines), `test_outbox_projection.py` (264 lines) — **complete**.

### Slice 4: Public Outbox Read/Drain + Offline Smoke

- `dayu/host/api.py`: `OutboxTerminalItemState`, `OutboxProjectionStatus`, `OutboxTerminalCursor`, `OutboxTerminalItem`, `ReadOutboxTerminalItemsRequest`, `DrainOutboxTerminalItemsRequest`, `OutboxTerminalItemsBatch` dataclasses; `Host` Protocol extended with `read_outbox_terminal_items` / `drain_outbox_terminal_items` — **complete**.
- `dayu/host/read_api.py`: `read_outbox_terminal_items`, `drain_outbox_terminal_items`, projection state reading, outbox item mapping — **complete**.
- `dayu/host/open_host.py`: `_PublicHostHandle` extended with read/drain methods; composite catch-up port includes outbox; audit/tool-trace/outbox path derivation from `artifact_root` — **complete**.
- Tests: `test_public_outbox_api.py` (213 lines), `test_public_offline_outbox_smoke.py` (255 lines) — **complete**.

**Verdict**: All four slices are fully implemented per plan.

---

## Architecture Boundary Compliance

### Projection/Sink — Not Truth Source

- **Audit**: `LogAuditSink` only consumes committed canonical facts, writes append-only JSONL, uses sink-local marker for idempotency. Does not write EventLog, does not modify Run/Attempt state. **PASS**.
- **Tool Trace**: `ToolTraceProjectionConsumer` only consumes whitelisted committed events, writes hot SQLite + cold JSONL. Does not participate in Host durable truth, recovery, resume, memory, or Run state migration. **PASS**.
- **Outbox**: `OutboxTerminalProjectionConsumer` only consumes committed terminal canonical facts. Does not write EventLog, does not update Run/Attempt. Drain state is projection queue state, not channel delivery success. **PASS**.

### Projection Checkpoint/Failure/Idempotency

All three projections use the existing `ProjectionRunner` / `ProjectionCheckpoint` framework:
- Checkpoint advances after successful batch.
- Failure recorded via `host_projection_failures` without rolling back command path.
- Idempotency via per-projection marker tables (`host_audit_sink_markers`, `host_tool_trace_hot.event_id UNIQUE`, `host_outbox_terminal_items.idempotency_key UNIQUE`).

**PASS** — follows established projection framework conventions.

### Schema Version 10→13 Committed History

Schema version progressed from 10 to 13 across the four slices (documented in `docs/reviews/phase13-schema-version-controller-clarification-20260529.md`). `HOST_SCHEMA_VERSION = 13` in `durable/schema.py`. Fresh bootstrap DDL includes all Phase 13 tables. `bootstrap_host_durable_store` rejects non-matching versions without compatibility reads. `test_durable_schema.py` covers bootstrap, version assertion, and constraint tests.

**PASS** — fresh schema, no legacy compatibility path.

---

## Findings

### F001-未修复-严重-read\_api.py 违反 import 边界，导入 durable.projection

**Severity**: BLOCKING

**Evidence**:

`dayu/host/read_api.py:53-57` imports:
```python
from dayu.host.durable.projection import (
    ProjectionCheckpointRow,
    read_projection_checkpoint,
    read_projection_failure,
)
```

`tests/host/test_import_boundary.py:73-79` defines the forbidden prefix list:
```python
READ_API_EVENT_STREAM_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.host.projection",
    "dayu.host.durable.projection",
    ...
)
```

Test `test_read_api_stream_does_not_reference_projection_or_fanout_truth` (line 273) fails:
```
AssertionError: read_api forbidden stream imports: ['dayu.host.durable.projection']
```

**Impact**: `read_api.py` 是 Host public read facade，其架构定位是只从 durable Session/Run/EventLog truth 构造 snapshot，不引用 projection checkpoint、outbox state 或 session-local cursor。当前实现直接导入 `durable.projection` 来读取 Outbox projection checkpoint/failure 状态，破坏了 `read_api` 作为 projection-agnostic facade 的边界。这不仅导致 pytest 失败，还意味着 `read_api` 的依赖图不再纯净——未来新增的 projection 类型可能继续在此处扩散 projection 依赖。

**Required change**: 将 `read_projection_checkpoint` / `read_projection_failure` 的调用从 `read_api.py` 下沉到 `dayu/host/durable/outbox.py` 或新建一个 outbox projection state helper。`read_api.py` 只通过 outbox durable helper 获取已封装的 projection state，不直接导入 `durable.projection`。具体方案：
1. 在 `dayu/host/durable/outbox.py` 中新增 `read_outbox_projection_state(transaction, consumer_id) -> OutboxProjectionState` helper，封装 checkpoint + failure 读取。
2. `read_api.py` 的 `_read_outbox_projection_state` 改为调用该 helper，移除对 `durable.projection` 的直接导入。
3. 重新运行 `test_read_api_stream_does_not_reference_projection_or_fanout_truth` 确认通过。

---

### F002-未修复-低-ToolTrace cold JSONL 先写文件后 marker，crash 导致重复行

**Severity**: LOW (residual risk, 不 blocking)

**Evidence**:

`dayu/host/tool_trace.py:318-326` (`ToolTraceProjectionConsumer.apply_event`):
```python
write_result = insert_tool_trace_hot_row_if_absent(transaction, hot_row)
if write_result.status is ToolTraceHotRowWriteStatus.DUPLICATE:
    return ProjectionApplyResult(...)
self._append_line(cold_line)  # cold JSONL write AFTER hot marker
```

Hot marker 在事务内先写入，cold JSONL 在事务外后写入。如果 hot marker commit 成功但 cold JSONL 写入前进程 crash，replay 时 hot marker 判定 DUPLICATE 跳过，cold JSONL 永久缺失该行。

与 Audit sink (`audit.py:231-239`) 的模式一致：先写 JSONL 后写 marker。Tool Trace 选择了相反顺序（先 marker 后 cold line），这意味着 cold JSONL 在 crash 场景下可能丢失行，而 Audit sink 的 cold-first 模式则是 crash 后可能重复行。

**Impact**: Tool Trace cold JSONL 是诊断用途，丢失单行不影响 Host truth。但与 Audit sink 的写入顺序不一致，增加认知负担。

**Required change**: 记录为 residual risk，owner 为 Phase 15 retention/purge/cleanup。如果 cold JSONL 完整性变得重要，应统一为 cold-first + marker-idempotent 模式（与 Audit sink 一致）。

---

## Residual Risks (已记录，有 owner)

| Risk | Owner | Notes |
|---|---|---|
| JSONL exactly-once 语义（Audit cold-first 可能重复行，Tool Trace marker-first 可能丢行） | Phase 15 | 跨介质 residual risk，不影响 Host truth |
| Outbox drain 不等于 channel delivery success | Phase 14/15 Service 集成 | drain side effect 只属于 projection queue state |
| Phase 15 retention/purge/cleanup | Phase 15 | JSONL 文件、hot SQLite rows、outbox drained items 的清理策略 |
| External audit / long-term archival / heavy sink runner | Phase 15+ | 当前 LogAuditSink 是轻量 in-process JSONL append |
| Outbox projection lag 导致空结果被误判为无遗漏 | Service 集成时 | `projection_status != CAUGHT_UP` 时调用方必须处理 lag |

## README 同步

- `dayu/host/README.md`: 已更新，新增 Outbox read/drain 说明、projection catch-up port 说明。内容与当前代码一致，职责边界正确。**PASS**.
- `tests/README.md`: 未修改。Phase 13 新增 9 个测试文件，但 `tests/README.md` 的职责是测试分层、运行方式、约定与维护规则，不逐文件列举。无触发条件要求更新。**PASS — 不改合理**.
- 根目录 `README.md`: Phase 13 变更不涉及 CLI 命令、用户工作流或安装配置，无触发条件。**PASS**.

## 编码硬约束检查

| 约束 | 状态 |
|---|---|
| 严格类型、无 Any/object/无类型签名 | **PASS** — 全部新增文件使用严格类型标注 |
| 中文 docstring | **PASS** — 所有公开函数、类、模块均有中文 docstring |
| 无 getattr/hasattr 逃避类型 | **PASS** — 未发现 |
| 无魔法字符串扩散 | **PASS** — schema DDL 中的字面量字符串属于工具 schema 例外；其余均使用模块级常量 |
| 无 God object/function | **PASS** — 每个模块职责单一，函数粒度合理 |
| 无兼容性 re-export/wrapper | **PASS** — 全新实现，无旧接口兼容逻辑 |
| 无反向依赖 | **PASS** — projection 层只读 EventLog，不写 canonical facts |

## Verdict

**PASS with 1 BLOCKING finding (F001)**

Phase 13 四个 slice 完整实现 plan，架构边界正确（Audit/Tool Trace/Outbox 均为 projection/sink，不反向成为 truth），schema version 自洽，projection checkpoint/failure/idempotency 遵循框架约定，Outbox public read/drain 是唯一 additive public extension，`watch_session_events` 仍为 live-only，类型安全通过 pyright。

F001 (`read_api.py` 违反 import 边界) 是唯一 blocking finding，需要在 merge 前修复。修复方案明确且局部：将 projection state 读取下沉到 outbox durable helper。
