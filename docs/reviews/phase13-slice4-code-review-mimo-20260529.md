# Phase 13 Slice 4 Code Review

Reviewer: AgentMiMo
Date: 2026-05-29
Target: `feat/phase-13-audit-trace-outbox` uncommitted Slice 4 diff + implementation artifact

## Review Scope

- `dayu/host/api.py` — public dataclasses / enums / constants / `Host` Protocol methods
- `dayu/host/__init__.py` — package root exports
- `dayu/host/open_host.py` — `_PublicHostHandle` + composite projection catch-up port
- `dayu/host/read_api.py` — public read / drain implementation
- `tests/host/test_public_outbox_api.py` — API validation / error path tests
- `tests/host/test_public_offline_outbox_smoke.py` — offline terminal read + live dedup smoke
- `tests/host/test_package_exports.py` — export completeness
- `tests/host/test_open_host_runtime.py` — close flush test
- `dayu/host/README.md` — public contract documentation
- `docs/reviews/phase13-slice4-implementation-codex-20260529.md` — implementation artifact
- `docs/host/implementation-control.md` — controller gate status update

Design truth: `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox
Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md` Slice 4

## Checklist

### 1. Public API Scope — Additive Only

| Requirement | Status |
|---|---|
| Only additive `read_outbox_terminal_items` / `drain_outbox_terminal_items` | PASS |
| No `OpenHostOptions` fields | PASS |
| No `wait_final_answer` | PASS |
| No `get_run_result` | PASS |
| No payload reader | PASS |
| No timeline replay | PASS |

Evidence: `Host` Protocol in `api.py:3149-3184` adds exactly two methods. `__init__.py` exports exactly the new types + constants + method names. No other Protocol methods, no `OpenHostOptions` field changes.

### 2. Reuse of Slice 3 Durable Helpers

| Requirement | Status |
|---|---|
| Public read delegates to `read_outbox_terminal_items_after` durable helper | PASS |
| Public drain delegates to `drain_outbox_terminal_items` durable helper | PASS |
| Catch-up delegates to `catch_up_outbox_terminal_projection` | PASS |
| No re-implementation of identity / query / drain / watermark logic | PASS |

Evidence: `read_api.py:181-231` — `read_outbox_terminal_items` and `drain_outbox_terminal_items` both call `_catch_up_outbox_terminal_projection_best_effort` then delegate to `_ReadOutboxTerminalItemsOperation` / `_DrainOutboxTerminalItemsOperation`, which pass through to `_read_outbox_terminal_items_after` / `_drain_outbox_terminal_items` from `dayu.host.durable.outbox`. Public layer only adds session validation, projection state reading, and row→public mapping.

### 3. Session Validation + Error Style

| Requirement | Status |
|---|---|
| Read/drain verify session before catch-up | PASS |
| Session missing → `HostApiErrorCode.NOT_FOUND` | PASS |
| Closed handle → `HostClosedError` | PASS |
| Idempotency conflict → `HostApiErrorCode.IDEMPOTENCY_CONFLICT` | PASS |
| Follows existing Host public error style | PASS |

Evidence:
- `read_api.py:181-183` / `read_api.py:206-208` — both call `_RequireSessionExistsOperation` before catch-up.
- `open_host.py:346-407` — `_PublicHostHandle.read_outbox_terminal_items` / `drain_outbox_terminal_items` both call `self._raise_if_closed()`.
- `test_public_outbox_api.py:90-99` — session not found tested with `HostApiErrorCode.NOT_FOUND`.
- `test_public_outbox_api.py:128-140` — drain idempotency conflict tested with `HostApiErrorCode.IDEMPOTENCY_CONFLICT`.
- `test_public_outbox_api.py:64-72` — closed handle tested with `HostClosedError`.

### 4. Best-Effort Catch-Up + Projection Status

| Requirement | Status |
|---|---|
| Best-effort catch-up before read/drain | PASS |
| `CAUGHT_UP` / `LAGGED` / `FAILED` correctly distinguished | PASS |
| Empty result + `LAGGED` does not mislead caller | PASS |
| Catch-up failure does not swallow durable corruption | PASS |

Evidence:
- `read_api.py:593-608` — `_catch_up_outbox_terminal_projection_best_effort` catches all exceptions into `_OutboxCatchupError`.
- `read_api.py:611-657` — `_read_outbox_projection_state` checks: (1) catchup_error → `FAILED`, (2) failure row → `FAILED`, (3) checkpoint < latest → `LAGGED`, (4) else → `CAUGHT_UP`.
- `test_public_outbox_api.py:143-200` — monkeypatched noop catchup → `LAGGED` + empty items; undo → `CAUGHT_UP` + items returned.
- `ProjectionRunner._record_failure` writes failure rows to durable store; `_read_outbox_projection_state` reads them back. Failure is never silently swallowed.

### 5. Drain Side Effects

| Requirement | Status |
|---|---|
| Drain only writes Outbox projection queue state | PASS |
| Drain only writes drain idempotency row | PASS |
| Drain does NOT write EventLog | PASS |
| Drain does NOT update Run / Attempt | PASS |
| Drain does NOT express channel delivery success | PASS |

Evidence:
- `read_api.py:272-287` — `_DrainOutboxTerminalItemsOperation` calls `_drain_outbox_terminal_items` (durable helper) then reads projection state. No EventLog / Run / Attempt writes.
- `test_public_offline_outbox_smoke.py:64-97` — `before_drain_eventlog_count == after_drain_eventlog_count` explicitly asserts no EventLog writes.
- Docstrings and README consistently state "不写 EventLog，不更新 Run / Attempt，也不把 drain state 解释为 channel delivery success".

### 6. Live Watch Dedup + Offline Smoke

| Requirement | Status |
|---|---|
| Live-first seen_ids filter works | PASS |
| Drain-first + second-read covers live attach window | PASS |
| `watch_session_events` live-only semantics unchanged | PASS |

Evidence:
- `test_public_offline_outbox_smoke.py:101-154` — live-first: watch receives terminal, then `read_outbox_terminal_items` with `seen_terminal_event_ids=(terminal.event_id,)` returns empty; without seen_ids returns 1 item. `dedupe_key == terminal.dedupe_key`.
- `test_public_offline_outbox_smoke.py:157-227` — drain-first: drain run-1, then watch run-2, then read with `after=first_batch.next_cursor` + `seen_terminal_event_ids=(live_terminal.event_id,)` → empty. `projection_status == CAUGHT_UP`.
- No changes to `watch_session_events` signature or implementation.

### 7. Final Answer Residual Risk

| Requirement | Status |
|---|---|
| No new payload reader | PASS |
| Final answer text not used for identity | PASS |
| Summary ref not disguised as payload | PASS |

Evidence:
- `outbox.py:184-228` — `build_outbox_terminal_item_identity` uses `terminal_event_id`, `run_id`, `result_ref/digest`, `terminal_summary_ref/digest`. Explicitly excludes final answer text from identity.
- `OutboxTerminalItem` exposes `result_ref` / `terminal_summary_ref` as references, not payload content. `final_answer` field is typed `HostFinalAnswerView | None` with no generic payload accessor.
- `read_api.py:1127-1165` — `_final_answer_from_outbox_json` only parses the structured JSON stored by `outbox.py:_final_answer_json`; no new external payload reading.

### 8. README

| Requirement | Status |
|---|---|
| Only describes current stable API | PASS |
| No future design | PASS |
| Updated per trigger rule (`dayu/host/**` + new public API) | PASS |

Evidence: README diff adds exactly the new types, constants, method descriptions, and boundary notes. No "future" or "planned" language.

### 9. Code Quality

| Requirement | Status |
|---|---|
| Chinese docstrings on all public functions/classes | PASS |
| Strict types, no `Any` / `object` / untyped | PASS |
| No `getattr` / `hasattr` escape | PASS |
| No magic strings (except schema constants) | PASS |
| Module-level private helpers preferred | PASS |

Evidence: All new dataclasses have typed fields and Chinese docstrings with `:param` / `:returns` / `:raises`. All `__post_init__` methods perform strict validation. Magic strings are limited to `_PAYLOAD_FIELD_*` / `_IDENTITY_FIELD_*` / `_EVENT_TYPE_*` constants. No `getattr` / `hasattr` / `Any` / `object` usage.

### 10. Implementation Artifact

Implementation artifact accurately describes scope, changed files, validation results, and residual risks. Non-goals correctly enumerated. Coverage notes match actual test content.

### 11. Controller Gate

`implementation-control.md` correctly updates gate from "Slice 4 implementation" to "Slice 4 code review" with validation summary.

## Findings

### F001-未修复-INFO-drain exact replay path untested

**Evidence**: `test_public_outbox_api.py:117-140` tests drain idempotency conflict (same `drain_request_id`, different cursor → `IDEMPOTENCY_CONFLICT`). The exact replay path (same `drain_request_id`, same cursor → returns cached page) is covered by the durable helper's logic but not explicitly asserted at the public API level.

**Impact**: No correctness risk. The durable helper `drain_outbox_terminal_items` correctly returns the cached page on exact replay. The test gap is coverage completeness only.

**Required change**: None for this review. Consider adding an explicit exact-replay assertion in a follow-up test maintenance pass.

### F002-未修复-INFO-tests/README.md not updated

**Evidence**: Plan lists `tests/README.md` as an allowed file. New test files `test_public_outbox_api.py` and `test_public_offline_outbox_smoke.py` follow existing patterns (same directory, same import style, same pytest-asyncio markers). The current `tests/README.md` already covers this test category.

**Impact**: No documentation drift. The new tests are the same kind as existing outbox/projection tests already documented.

**Required change**: None. The plan's README trigger rule states "若只是新增同类测试且 README 已覆盖，可在最终说明中明确'检查后无需更新'"。

## Verdict

**PASS** — 无 blocking findings。Slice 4 实现严格在 plan 允许范围内，正确复用 Slice 3 durable helper，public API 只做 additive extension，session 校验 / error 风格 / projection 状态 / drain side effect 边界均符合 design §16 契约。测试覆盖 offline read、live-first dedup、drain-first window、lag/catch-up、idempotency conflict、closed handle、session not found、close flush。
