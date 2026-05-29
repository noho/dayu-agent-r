# Phase 13 Aggregate Deepreview — AgentDS

**Date**: 2026-05-29
**Reviewer**: AgentDS
**Target**: `feat/phase-13-audit-trace-outbox` 相对 `main` 的全部 Phase 13 diff
**Design Truth**: `docs/host/design.md`
**Control Doc**: `docs/host/implementation-control.md`
**Accepted Plan**: `docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Verdict: PASS

无 blocking findings。Phase 13 完整实现了 accepted plan 的四个 slices，Audit / Tool Trace / Outbox 全部保持 projection/sink 边界，schema version 10→11→12→13 自洽，所有验证通过。以下为逐项详细审查结果。

---

## 1. Plan Slice Completeness

### Slice 1 — LogAuditSink JSONL ✅

| Check | Evidence | Result |
|-------|----------|--------|
| `LogAuditSinkOptions` dataclass | `dayu/host/audit.py:90-100` | PASS |
| `LogAuditSink` projection consumer | `dayu/host/audit.py`, consumer id `host.audit-log-jsonl` | PASS |
| append-only JSONL with `line_digest` | `dayu/host/audit.py`, field `_AUDIT_FIELD_LINE_DIGEST` | PASS |
| sink-local idempotency marker table | `dayu/host/durable/audit.py`, `TABLE_HOST_AUDIT_SINK_MARKERS` | PASS |
| default path from `artifact_root` | `dayu/host/open_host.py:_default_audit_jsonl_path` | PASS |
| composite catch-up port wiring | `dayu/host/open_host.py:_LogAuditProjectionCatchupPort` | PASS |
| audit field completeness | 18 fields matching plan specification | PASS |

### Slice 2 — Tool Trace Hot JSON / Cold JSONL ✅

| Check | Evidence | Result |
|-------|----------|--------|
| `ToolTraceSinkOptions` dataclass | `dayu/host/tool_trace.py` | PASS |
| `ToolTraceProjectionConsumer` | `dayu/host/tool_trace.py`, consumer id `host.tool-trace` | PASS |
| hot projection table + indexes | `dayu/host/durable/schema.py`, `TABLE_HOST_TOOL_TRACE_HOT` + 5 indexes | PASS |
| cold JSONL writer | `dayu/host/tool_trace.py`, `_write_cold_trace_line` pattern | PASS |
| typed whitelist discovery | `dayu/host/tool_trace.py` lines 47-66, canonical/diagnostic event_type whitelist | PASS |
| internal query helpers | `dayu/host/durable/tool_trace.py`, `read_tool_trace_by_run` / `find_tool_trace_by_tool_call_id` / `find_tool_trace_by_provider_request_id` / `find_tool_trace_by_diagnostic_ref` | PASS |
| `ToolTraceQueryPage` pagination | `event_sequence ASC`, `after_event_sequence` cursor, `has_more` | PASS |

### Slice 3 — OutboxSink Durable Projection ✅

| Check | Evidence | Result |
|-------|----------|--------|
| `OutboxTerminalProjectionConsumer` | `dayu/host/outbox.py`, consumer id `host.outbox-terminal` | PASS |
| `host_outbox_terminal_items` table + indexes | `dayu/host/durable/schema.py`, CHECK constraints for state/payload consistency | PASS |
| `host_outbox_drain_idempotency` table | `dayu/host/durable/schema.py`, PK `(session_id, drain_request_id)` | PASS |
| `RUN_LOST` skipped | `dayu/host/outbox.py` line 51: `_DETAIL_CODE_RUN_LOST_SKIPPED` | PASS |
| item idempotency via `item_id` / `idempotency_key` | stable derivation from `terminal_event_id`, `run_id`, result digest | PASS |
| read cursor / seen ids / scanned watermark | `dayu/host/durable/outbox.py:read_outbox_terminal_items_after` | PASS |
| drain idempotency | `dayu/host/durable/outbox.py:drain_outbox_terminal_items` | PASS |
| `dedupe_key = terminal_event_id` | enforced in public dataclass `__post_init__` | PASS |

### Slice 4 — Public Outbox Read / Drain API Offline Smoke ✅

| Check | Evidence | Result |
|-------|----------|--------|
| `Host` Protocol additive methods | `dayu/host/api.py:3152-3190` | PASS |
| `_PublicHostHandle` methods | `dayu/host/open_host.py:349-390` | PASS |
| public dataclasses | `OutboxTerminalCursor`, `ReadOutboxTerminalItemsRequest`, `DrainOutboxTerminalItemsRequest`, `OutboxTerminalItem`, `OutboxTerminalItemsBatch` | PASS |
| enums | `OutboxTerminalItemState`, `OutboxProjectionStatus` | PASS |
| validation rules | `__post_init__` coverage for all public dataclasses | PASS |
| closed handle → `HostClosedError` | standard `_raise_if_closed()` pattern | PASS |
| `__all__` export updates | `dayu/host/api.py` and `dayu/host/__init__.py` | PASS |
| composite close flush includes outbox | `_CompositeProjectionCatchupPort` ordering: memory → audit → trace → outbox | PASS |
| smoke: offline read + drain idempotent | `test_public_offline_outbox_smoke.py:28` | PASS |
| smoke: live-first seen_ids filter | `test_public_offline_outbox_smoke.py:101` | PASS |
| smoke: drain-first + second-read cover window | `test_public_offline_outbox_smoke.py:157` | PASS |
| smoke: LAGGED → CAUGHT_UP recovery | `test_public_outbox_api.py:144` | PASS |

---

## 2. Projection / Sink Boundary Enforcement

All three systems maintain strict projection/sink discipline. No reverse dependency on EventLog truth, no command path mutation, no Run/Attempt state change.

| Audit boundary | `dayu/host/audit.py:1-6` — "不是 Host truth; 失败只应通过 projection runner 的 failure path 暴露" |
| Tool Trace boundary | `dayu/host/tool_trace.py:1-6` — "只用于诊断查询，不参与 Host durable truth、恢复、resume、memory 或 Run 状态迁移" |
| Outbox boundary | `dayu/host/outbox.py:1-7` — "不写 EventLog，不更新 Run / Attempt，也不把 drain state 解释为 channel delivery success" |

Concrete verification:
- All three consumers implement `ProjectionApplyResult` pattern with `SKIPPED` / `DUPLICATE` status codes
- checkpoint advance only on successful projection write
- failure writes `host_projection_failures`, not EventLog
- `tool_trace.py` and `audit.py` JSONL writes use `file_lock` for cross-process safety, not for truth expression

---

## 3. Schema Version Self-Consistency

Committed schema history is self-consistent:

```
commit 7432f02 (Slice 1): HOST_SCHEMA_VERSION 10 → 11
commit 0a675a5 (Slice 2): HOST_SCHEMA_VERSION 11 → 12
commit 1a37946 (Slice 3): HOST_SCHEMA_VERSION 12 → 13
commit 1d9e732 (Slice 4): no schema change (public API only)
```

Final `HOST_SCHEMA_VERSION = 13`. Fresh schema DDL completeness:

| Table | CHECK constraints | Foreign Keys | Indexes | Test |
|-------|-------------------|-------------|---------|------|
| `host_audit_sink_markers` | `event_sequence > 0` | FK to `event_log(event_id)`, `event_log(event_sequence)` | N/A (PK only) | ✅ |
| `host_tool_trace_hot` | `event_class IN (...)`, paired ref/digest CHECKs | FK to `event_log(event_id)`, `event_log(event_sequence)` | 5 partial indexes | ✅ |
| `host_outbox_terminal_items` | `terminal_status IN (...)`, `item_state IN (...)`, paired ref/digest CHECKs, state/drain column consistency CHECK | FK to `event_log(terminal_event_id)`, `event_log(event_sequence)` | 3 indexes | ✅ |
| `host_outbox_drain_idempotency` | PK `(session_id, drain_request_id)` | N/A | N/A | ✅ |

Tests:
- `test_host_schema_version_is_phase13_outbox_version` — asserts `HOST_SCHEMA_VERSION == 13`
- `test_fresh_db_creates_foundation_phase8_and_memory_tables` — extended to verify Phase 13 tables
- `test_audit_sink_marker_table_is_created` — verifies table + PK
- `test_tool_trace_hot_table_and_indexes_are_created` — verifies table + indexes
- `test_outbox_terminal_items_table_and_indexes_are_created` — verifies constraints/indexes
- `test_outbox_drain_idempotency_table_is_created` — verifies PK

No old-schema compat paths, no migration reads, no `PRAGMA user_version` fallback to pre-13 values.

---

## 4. Projection Checkpoint / Failure / Idempotency

All three consumers follow the same pattern, consistent with Phase 8 projection framework:

1. **Checkpoint read**: `read_projection_checkpoint(consumer_id)` → get current `event_sequence`
2. **EventLog scan**: read events after checkpoint, filtered by consumer's `ProjectionEventFilter`
3. **Event apply**: per-event `apply(event)` → `ProjectionApplyResult`
4. **Checkpoint advance**: only after successful apply, in same or subsequent transaction
5. **Failure recording**: write `host_projection_failures` without advancing checkpoint
6. **Normal replay idempotency**: 
   - Audit: `insert_audit_sink_marker_if_absent` → `DUPLICATE` on same `event_id`
   - Tool Trace: `insert_tool_trace_hot_row_if_absent` → `DUPLICATE` on same `trace_id` (= `event_id`)
   - Outbox: `insert_outbox_terminal_item_if_absent` → `DUPLICATE` on same `idempotency_key`

Failure does not roll back command path. Verified: none of the three consumers write to `event_log`, `host_runs`, `host_attempts`, or `host_sessions`.

---

## 5. Cross-Media Residual Risk (JSONL / SQLite)

The plan §"Storage / Schema / Checkpoint Decisions" explicitly documents:

> 本地 append-only JSONL 与 SQLite checkpoint 无法形成真正跨介质原子事务。Implementation 必须用 `event_id` / line digest marker 避免 normal retry 重复 append；若进程在 file append 成功、marker/checkpoint 提交前崩溃，物理 JSONL 可能出现重复 `event_id` 行。

Implementation:
- `LogAuditSink`: writes JSONL line, then `insert_audit_sink_marker_if_absent` in durable transaction. If crash between line write and marker commit, normal retry will re-read the event, check the marker, and skip (duplicate). The risk is that the marker table write fails after JSONL append succeeds but before marker commit — in which case retry produces a duplicate `event_id` line. The plan correctly classifies this as P1 material but accepted.
- `ToolTraceProjectionConsumer`: same pattern — cold JSONL write followed by hot row insert. The hot row serves as the logical "was written" marker.

The residual risk is accurately documented and owned. Consumer code uses `event_id`-based duplicate detection; analyze helpers must deduplicate by `event_id`.

---

## 6. Public API Contract Analysis

### Outbox is the ONLY additive public extension ✅

`git diff main -- dayu/host/api.py` confirms:
- **No new `OpenHostOptions` fields** — audit/trace paths derived from existing `artifact_root`
- **No `wait_final_answer`** — not present
- **No `get_run_result`** — not present
- **No payload reader public API** — internal resolution only
- **No timeline replay** — not present
- **New types added**: `DrainOutboxTerminalItemsRequest`, `ReadOutboxTerminalItemsRequest`, `OutboxTerminalCursor`, `OutboxTerminalItem`, `OutboxTerminalItemsBatch`, `OutboxTerminalItemState`, `OutboxProjectionStatus`, constants `HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT`, `HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT`
- **New Protocol methods**: `Host.read_outbox_terminal_items`, `Host.drain_outbox_terminal_items`

### watch_session_events unchanged ✅

```python
# api.py — unchanged signature
def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:

# open_host.py — unchanged signature  
def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
```

Zero diff lines touching `watch_session_events`. No cursor parameter, no replay mode.

---

## 7. Anti-Leak Protocol Coverage

The plan requires two attach patterns to be tested. Both are present:

### live-first ✅
`test_live_first_seen_ids_filter_outbox_duplicate` (smoke line 101):
1. Open `watch_session_events`
2. Submit followup, receive terminal via live watch
3. Read Outbox with `seen_terminal_event_ids=(terminal.event_id,)` → empty result
4. Read Outbox without filter → item present
5. Verifies `dedupe_key == terminal.dedupe_key`

### drain-first + second-read ✅
`test_drain_first_second_read_covers_live_attach_window` (smoke line 157):
1. Run first terminal, drain Outbox
2. Open live watch
3. Submit second followup, receive terminal via live watch
4. Second Outbox read with `after=first_batch.next_cursor` + `seen_terminal_event_ids=(live_terminal.event_id,)` → empty
5. Verifies `scanned_watermark >= live_terminal.event_sequence`

### anti-leak LAGGED case ✅
`test_public_outbox_reports_lagged_then_catches_up` (api test line 144):
1. Run to terminal
2. Monkeypatch catch-up to no-op → read returns `LAGGED`, empty items
3. Restore catch-up → read returns `CAUGHT_UP` with terminal item

---

## 8. README Synchronization

### dayu/host/README.md ✅

Changes are within the README's declared responsibility boundary:
- Public constants list: added Outbox constants mention
- Public type categories: added "outbox read / drain" line with 7 type names
- Handle methods: added `read_outbox_terminal_items` and `drain_outbox_terminal_items` descriptions
- Opener assembly: added "audit、tool trace 与 outbox projection catch-up port" mention
- EventLog section: added Outbox terminal read/drain semantic paragraph with deduplication and projection status guidance

All changes are factual descriptions of current code. No process state, no future plans.

### tests/README.md ✅ (not modified)

Per plan: "若只是新增同类测试且 README 已覆盖，可在最终说明中明确'检查后无需更新'."

Rationale: Phase 13 added 8 test files, all `tests/host/test_*`. The test README §"tests/host/" already generically covers Host tests: "覆盖 `dayu.host` 的稳定边界". The new tests are the same kind (host unit/integration tests following existing patterns). No new test layer, no new running conventions, no new maintenance rules.

### 根 README.md ✅ (not modified)

No CLI/render/project-level entry changes in Phase 13.

---

## 9. Type Quality

| Metric | Result |
|--------|--------|
| `pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** |
| `Any` type in new files | **0 occurrences** |
| `: object` type annotation in new files | **0 occurrences** |
| `getattr` / `hasattr` in new files | **0 occurrences** (only legacy `durable/transaction.py` with documented justification) |
| Untyped function parameters | **0** |
| Untyped return values | **0** |

All public dataclasses are `frozen=True, slots=True` with typed `__post_init__` validation. All Chinese docstrings include `:param`, `:returns`, `:raises` as required.

---

## 10. Aggregate Validation

Re-ran plan-listed validation commands:

```bash
$ pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py tests/host/test_projection_runner.py \
  tests/host/test_projection_checkpoint.py tests/host/test_public_event_stream.py \
  tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py \
  tests/host/test_package_exports.py tests/host/test_durable_schema.py -q

Result: 96 passed in 1.29s
```

```bash
$ python -m pyright dayu/host tests/host

Result: 0 errors, 0 warnings, 0 informations
```

```bash
$ git diff --check

Result: (clean, no output)
```

All three pass. No pre-existing pyright errors in Phase 13 files.

---

## 11. `object` Reference Audit

The word "object" appears in new Phase 13 files only in:
- Docstrings ("JSON object", "canonical JSON object")
- Error messages ("must be JSON object")

**Zero** instances of `object` as a Python type annotation in Phase 13 files (`audit.py`, `tool_trace.py`, `outbox.py`, `durable/audit.py`, `durable/tool_trace.py`, `durable/outbox.py`, `read_api.py`).

---

## 12. Residual Risks (All Previously Documented, All With Owner)

| # | Risk | Severity | Owner | Status |
|---|------|----------|-------|--------|
| R1 | JSONL/SQLite cross-media exactly-once: crash between JSONL append and marker/checkpoint commit may produce duplicate `event_id` lines in physical JSONL; does not affect Host truth | P1 — material but accepted | Phase 13 implementation (documented in plan §"JSONL crash residual") | Analyze helpers must deduplicate by `event_id` |
| R2 | Outbox drain ≠ channel delivery success: Service/UI must persist seen terminal watermark/ids; Phase 13 does not implement channel exactly-once | P1 — material but accepted | Service/UI layer | Documented in plan §"Idempotency / Dedupe" |
| R3 | purge tombstone audit record, outbox cleanup, tool trace cleanup, projection cleanup, retention matrix | P2 — deferred | Phase 15 Retention / Purge / Production Hardening | Documented in plan §"Non-goals" and control doc §"Phase 15 tracking" |
| R4 | External audit system, long-term archival strategy, heavy sink runner / batch transaction hardening | P2 — deferred | Phase 15 / subsequent production hardening | Documented in plan §"Non-goals" |

No new residual risks discovered during this review beyond those already documented.

---

## 13. Finding Summary

**No blocking findings.**

**No non-blocking findings.**

All plan requirements are met. All verification gates pass. All residual risks have documented owners and follow-up phases.

The implementation correctly adheres to the Host design principle that Audit / Tool Trace / Outbox are projections/sinks consuming committed EventLog — not EventLog truth sources, not recovery/resume/memory truth sources, not command path participants.

## Review Evidence Index

| Evidence | Source |
|----------|--------|
| Plan completeness (4 slices) | `docs/host/phase13-audit-tool-trace-outbox-plan.md` §§Implementation Slices |
| Design truth references | `docs/host/design.md` §§14, 15, 16 |
| Control doc Phase 13 tracking | `docs/host/implementation-control.md` §§Phase 13 Audit/Tool Trace/Outbox tracking, 历史记录 2026-05-29 |
| Schema commit history | `git log main..HEAD -- dayu/host/durable/schema.py` showing 10→11→12→13 |
| Public API contract | `dayu/host/api.py` (414+ lines added), `dayu/host/__init__.py` (new exports) |
| Audit implementation | `dayu/host/audit.py` (577 lines), `dayu/host/durable/audit.py` (187 lines) |
| Tool Trace implementation | `dayu/host/tool_trace.py` (990 lines), `dayu/host/durable/tool_trace.py` (593 lines) |
| Outbox implementation | `dayu/host/outbox.py` (527 lines), `dayu/host/durable/outbox.py` (877 lines) |
| Public read/drain API | `dayu/host/read_api.py` (377 lines added), `dayu/host/open_host.py` (299 lines added) |
| Schema DDL | `dayu/host/durable/schema.py` (236 lines added) |
| Test suite | 8 new test files totaling 2,335 lines; 96 tests passed |
| Validation | pyright 0 errors, git diff --check clean, pytest 96 passed |
| Prior reviews | Slice 1-4 code reviews (MiMo + DS) all PASS; controller adjudications all accepted |
