# WU-TOOLS-CANCEL-01 Plan Review — AgentMiMo

## Reviewed Target

- Plan artifact: `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- Work unit: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- Gate: plan review
- Reviewer: AgentMiMo
- Timestamp: 2026-07-04T18:23:30

## Scope

Adversarial plan review covering: motivation, root cause, design alignment, architecture boundary, non-goal discipline, slice structure, test coverage, residual risk, and code-generation readiness.

## Assumptions Tested

1. **Plan consumes completed WUs, not redoing them** — confirmed. Plan explicitly does not rewrite Host terminal truth (WU-LIFE-03), active cancel timeout (WU-LIFE-04), or WAITING lifecycle (WU-WAIT-03). Non-goals section is precise.
2. **Root cause is correctly identified** — confirmed. `await_or_cancel` on `asyncio.to_thread(...)` task only cancels the coroutine wrapper, not the underlying OS thread. Code evidence at `tool_runtime.py:2610-2613` and all four tool files using `asyncio.to_thread` verified.
3. **Accept barrier and late rejection exist and are adequate foundations** — confirmed. `_invalid_accept_context_reason` at `tool_runtime.py:3510-3544` checks Run/Attempt/Dispatch same-origin and running state. `_late_rejection_reason` at `engine_ingest.py:3283-3308` rejects events after terminal or after active cancel.
4. **Lane token release depends on `_consume_worker_events` finally** — confirmed. `dispatch.py:3904-3911` finally block unregisters active handle, closes handle, and releases lane token.
5. **Default local worker `on_cancel` is currently no-op** — confirmed. `local_proxy.py:136-147` only does `del reason`.
6. **Plan does not introduce second cancel timeout** — confirmed. Section 7 states "所有 deadline 继续来自 `tool_execution_timeout_seconds`".
7. **Plan does not hardcode provider-specific kill in Host core** — confirmed. Section 2 non-goal: "不把 provider-specific kill API 硬编码进 Host core".
8. **No durable schema / EventLog / public API changes needed** — confirmed. Section 6 "Not required" list is consistent with design truth: cancel request, terminal truth, late rejection, accept barrier all already exist.
9. **3 slices follow control doc slice principles** — confirmed with one finding. Each slice is a semantic closure (runtime boundary, tool migration, public UX). Not mechanically split by module.
10. **Code references are accurate** — confirmed. Both Explore agents verified all 14 key code references (line numbers, method signatures, semantics) against actual source files. Zero mismatches.

## Findings

### 001-unfixed-MEDIUM-capsule execution mode not distinguished in contract

- **位置**: Section 7.1 "Interruptible execution capsule", Section 7.4 "Subprocess / process group / sandbox termination"
- **问题类型**: 契约缺失
- **当前写法**: Plan describes capsule with `run()`, `request_interrupt(reason)`, `terminate(reason)`, `kill(reason)`, `close()` semantics. Section 7.1 says capsule "包住单个 tool call 的真实执行形态". Section 7.4 says "对非协作 blocking I/O，生产级路径优先使用 process-backed capsule". Section R1 acknowledges pickling risk.
- **反例/失败场景**: Implementation agent receives capsule contract but has no typed distinction between "this capsule runs the callable in a thread" vs "this capsule runs the callable in a subprocess". For thread-backed execution, `terminate()` and `kill()` have no OS-level effect — the thread continues until it finishes naturally. The capsule contract promises interrupt semantics that cannot be delivered for thread-backed mode. Implementation agent may either (a) implement only thread-backed mode and claim production-grade interrupt, or (b) have to redesign mid-S2 when discovering a tool cannot be pickled for process execution.
- **为什么有问题**: The plan's root cause analysis correctly identifies that `asyncio.to_thread(...)` cancellation doesn't stop the underlying thread. But the capsule contract itself doesn't encode this distinction. Without a typed execution mode declaration, S1 can produce a capsule that passes tests with cooperative fixtures but fails on real blocking I/O. S2 then discovers the gap and has to redesign.
- **直接证据**: Plan Section 7.1 describes capsule semantics without execution mode. Plan Section 7.4 acknowledges process-backed is needed for non-cooperative blocking I/O but positions it as an implementation detail. Plan R1 says "若无法通过 typed declaration / adapter 解决，转为 dedicated follow-up issue" — this acknowledges the risk but doesn't resolve it in the contract.
- **影响**: Implementation agent may implement thread-backed-only capsule in S1, write tests that pass with cooperative fixtures, then discover in S2 that production tools need process-backed execution. This creates rework and potential scope creep. Alternatively, S2 implementation may silently keep some tools on thread path without proper interrupt semantics.
- **建议改法和验证点**: S1 capsule contract should include a typed execution mode enum (e.g., `async_direct`, `thread_backed`, `process_backed`). The `terminate()` / `kill()` semantics should be specified per mode: for `async_direct`, cancel the task; for `thread_backed`, only set cancellation flag (no OS interrupt); for `process_backed`, SIGTERM/SIGKILL. Tool declarations should include which execution mode they require. S1 tests should cover at least `async_direct` and `process_backed` modes. Verification: capsule contract file defines execution mode enum; S1 test proves process-backed capsule interrupts non-cooperative blocking fixture.
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-unfixed-LOW-S2 migration scope may be underestimated

- **位置**: Section 8 Slice S2 "Production tool/provider migration"
- **问题类型**: 切片过粗
- **当前写法**: S2 covers `doc_tools.py`, `fins_tools.py`, `web_tools.py`, `web_http_session.py`, `web_playwright_backend.py`, plus narrowly required `dayu/fins/*` helper modules. Expected assertions include doc/fins/web blocking fixtures, web request budget, Playwright terminate+kill, and cancelled outcome compatibility.
- **反例/失败场景**: Each tool family has different blocking characteristics: doc tools use `asyncio.to_thread` with sync HTTP inside; fins tools use `asyncio.to_thread` with sync file I/O; web tools use `asyncio.to_thread` with sync search/fetch; Playwright uses subprocess. Migrating all four in one slice means the implementation agent must handle four different migration patterns simultaneously. If any one hits a pickling or process-backed complexity wall, the entire S2 stalls.
- **为什么有问题**: The control doc's slice principles say "slice 必须控制模型一次实施和 reviewer 一次审查能够稳定承载的上下文规模" and "每个 slice 都是可验证行为闭环". Four tool families with different blocking patterns in one slice is on the edge of what a single implementation agent can handle without context loss.
- **直接证据**: Plan R1 acknowledges pickling risk. Plan S2 stop condition says "If a production tool cannot be made interruptible without changing business storage / download architecture, stop and classify that residual to a dedicated issue". This stop condition exists but is reactive — the plan doesn't pre-assess which tools are easy vs hard to migrate.
- **影响**: S2 may take longer than expected or require mid-slice scope reduction. Low severity because the stop condition exists and the plan explicitly allows classifying hard cases as residual.
- **建议改法和验证点**: Consider adding a pre-migration assessment in S2: for each tool family, classify as (a) direct `asyncio.to_thread` -> process-backed capsule, (b) already has HTTP abort path -> adapter hook, (c) complex pickling -> needs dedicated design. This doesn't require splitting S2 but gives the implementation agent a decision framework. Verification: S2 implementation report includes per-tool-family migration assessment.
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-unfixed-LOW-async HTTP abort path not explicitly covered

- **位置**: Section 7.3 "Request / stream abort", Section 5 "Affected Files / Modules"
- **问题类型**: 契约缺失
- **当前写法**: Section 7.3 covers "async provider / httpx path：取消 pending task，并关闭 response/client stream" and "provider SSE stream：继续由 Runner / provider adapter 关闭连接". Section 5 mentions `web_http_session.py` and notes deadline helper only works when caller passes budget.
- **反例/失败场景**: `sec_downloader.py` uses `httpx.AsyncClient` directly. If the capsule only wraps `asyncio.to_thread(...)` calls, async HTTP paths like SEC downloader won't go through the capsule. The plan says capsule is for "单个 tool call 的真实执行形态" — but async HTTP tools execute directly in the event loop, not through `to_thread`. Their cancellation is through task cancel + response close, which is a different pattern than the capsule's `terminate()`/`kill()`.
- **为什么有问题**: The plan's scope is "blocking I/O cancellation hardening", and async HTTP paths are not blocking I/O. But they still need proper abort semantics for Esc responsiveness. If the capsule contract only covers thread/process-backed execution, async HTTP tools need a separate adapter hook pattern. The plan mentions this in 7.3 but doesn't specify whether it goes through the capsule or a parallel path.
- **直接证据**: Plan Section 7.3 describes two distinct abort patterns (async cancel + close, vs sync thread/process). Plan Section 5 lists `web_http_session.py` but the capsule design in 7.1 focuses on `run()`/`terminate()`/`kill()` which maps to process lifecycle, not HTTP stream lifecycle.
- **影响**: Implementation agent may not know whether async HTTP abort should use the capsule or a separate adapter hook. Low severity because the existing `await_or_cancel` + task cancel already works for async paths; the gap is mainly in ensuring response/session cleanup happens.
- **建议改法和验证点**: Clarify in S1 or S2 whether async HTTP tools use the capsule (with async_direct mode) or a parallel "stream abort hook" pattern. The capsule's `request_interrupt()` for async_direct mode should cancel the task and close any open response/session. Verification: S2 test covers httpx async path cancellation with response cleanup.
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无 blocking open question。

## Residual Risks / Uncovered Areas

| ID | Risk | Owner | Destination |
|----|------|-------|-------------|
| R1 | Pickling risk for process-backed capsule | S1 implementation | If unsolvable via typed declaration/adapter, transfer to dedicated issue |
| R2 | `asyncio.to_thread` thread continues after cancel | S2 implementation | Production blocking I/O must migrate to process-backed; pure thread only for cooperative/read-only |
| R3 | Race between worker stream close and cooperative cancel | S1 tests | Correctness via Host terminal first-committer-wins and late rejection |
| R4 | Hard kill diagnostic in LLM-facing result | S1/S2 implementation | Must be bounded runtime diagnostic, not business fact |
| R5 | Public smoke in non-TTY CI | S3 tests | Use key monitor fake at CLI command boundary |

Residual risks R1-R5 are already tracked in the plan's Section 11 with explicit owners. No additional residual risks identified.

## Slice Review

### S1: ToolRuntime interrupt capsule and worker cleanup

- **语义闭环**: Yes. Creates capsule abstraction, integrates into ToolRuntime dispatch, adds local worker on_cancel cleanup, proves with focused tests.
- **依赖顺序**: Correct. S1 is foundation for S2 and S3.
- **验证矩阵**: Adequate. Covers non-cooperative blocking fixture, cancel->cleanup->lane release, stale quarantine, terminate vs kill paths.
- **Stop condition**: Correct. If durable schema change needed, stop. If process-backed capsule can't carry tool callable, stop and update plan.
- **Issue**: Capsule contract doesn't distinguish execution modes (Finding 001).

### S2: Production tool/provider migration

- **语义闭环**: Yes. Migrates all production blocking paths to S1 capsule boundary.
- **依赖顺序**: Correct. Depends on S1 capsule.
- **验证矩阵**: Adequate. Per-tool-family tests, Playwright terminate+kill, web request budget.
- **Stop condition**: Correct. Hard tools get classified to dedicated issue.
- **Issue**: Scope may be large for one slice (Finding 002). Async HTTP abort path clarity (Finding 003).

### S3: Public Esc/cancel smoke, stale quarantine, docs sync

- **语义闭环**: Yes. End-to-end UX validation, stale result proof, docs sync.
- **依赖顺序**: Correct. Depends on S1+S2.
- **验证矩阵**: Strong. Public smoke, new input progress, late result quarantine, lane cleanup assertion.
- **Stop condition**: Correct. If Host still waits for old worker lane, return to S1.

## Verdict

**pass-with-findings**

- Blocking findings: 0
- Non-blocking findings: 3 (1 medium, 2 low)
- All code references verified accurate
- Design alignment confirmed
- No architecture boundary violations
- No overengineering detected
- No overcoupling detected
- Slice structure adequate (3 slices within control doc budget)

## Artifact Path

`docs/reviews/plan-review-20260704-182330.md`
