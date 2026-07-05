# WU-TOOLS-CANCEL-01 Plan Re-Review — AgentDS

## Metadata

- **Reviewer**: AgentDS (re-review)
- **Reviewed artifact**: `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- **Work unit**: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- **Gate**: re-review (post plan-fix)
- **Timestamp**: 20260704-183338
- **Re-review scope**: per controller adjudication — verify accepted findings closed, scope intact, slices code-generation-ready, no new blocking issues
- **Fix artifact**: `docs/reviews/wu-tools-cancel-01-plan-fix-codex.md`
- **Review inputs**:
  - `docs/reviews/wu-tools-cancel-01-plan-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-cancel-01-plan-fix-codex.md`
- **Code evidence re-verified**:
  - `dayu/host/local_proxy.py:136-146` — `on_cancel` still no-op (confirmed)
  - `dayu/host/local_proxy.py:168-239` — `_DefaultLocalWorkerEventStream` with `__anext__` task tracking, `close()` with task cancel + `_suppress_task_cancel` + `aclose()`, idempotent close lock
  - `dayu/host/dispatch.py:3794-3923` — `_consume_worker_events` loop with `CancelledError` re-raise at line 3829, `StopAsyncIteration` at line 3797, finally block at lines 3904-3923 (discard handle, unregister, close handle, release lane token)

---

## Accepted-Finding Closure Matrix

### Blocking Findings

| Finding | Source | Status | Evidence of Closure in Plan |
|---|---|---|---|
| **DS F1**: `on_cancel` → worker stream interruption mechanism unspecified | AgentDS | **CLOSED** | Section 7.7 now specifies: (1) `on_cancel` calls event stream `close()` path; (2) close cancels active `anext` task; (3) swallows task CancelledError; (4) calls `aclose()` on generator; (5) close is idempotent; (6) `_consume_worker_events` reaches `finally` in both `CancelledError` re-raise and clean EOF paths; (7) `CancelledError` may propagate to dispatch owner but must not skip finally; (8) internal cleanup grace `local_worker_close_grace_seconds = 3.0`. Code evidence confirms existing `_DefaultLocalWorkerEventStream.close()` (lines 221-239) already implements task cancel + suppress + aclose + idempotent lock — plan correctly wires `on_cancel` to this existing mechanism. |
| **DS F2 + MiMo 001**: Process-backed capsule feasibility / execution mode not distinguished | AgentDS / AgentMiMo | **CLOSED** | Section 7.1 now defines typed execution mode table with `async_direct`, `thread_backed`, `process_backed` and per-mode interrupt semantics. `thread_backed` explicitly marked as NOT satisfying production-grade non-cooperative blocking cancel. Section 7.4.1 adds full feasibility/migration matrix covering Doc tools, Fins read tools, Web sync HTTP, Async HTTP/httpx, Playwright — each with current blocking form, preferred strategy, picklability/migration risk, fallback strategy, and stop condition. Global stop condition: if key production paths can't be `process_backed` or request-abort-capable `async_direct`, return to design gate, do not claim #87 closeout. |

### Non-Blocking Findings

| Finding | Source | Status | Evidence of Closure in Plan |
|---|---|---|---|
| **DS F3**: Bounded close timeout value unspecified | AgentDS | **CLOSED** | Section 7.7: `local_worker_close_grace_seconds = 3.0`, explicitly stated as cleanup grace (not cancel timeout, not public API, not derived from `tool_execution_timeout_seconds`). |
| **DS F4**: Slice 3 lacks non-cooperative blocking fixture + new input progress | AgentDS | **CLOSED** | Section 8 Slice S3 "Exact allowed changes": "Add public or Host-public smoke where Run A uses a non-cooperative blocking fixture, interactive Esc / cancel returns user to input-ready state, and Run B in the same Session advances to terminal." Expected assertions now include non-cooperative blocking fixture for Run A + Run B progression. |
| **DS F5**: `dayu.contracts` modification ambiguity | AgentDS | **CLOSED** | Section 6 "Not required": "默认不新增 `dayu.contracts` 字段。" Section 6 "Required": if S1 proves provider declarations necessary, implementation stops for design/contract update. No magic string, no `extra payload`. |
| **DS F6**: Cooperative async path regression coverage missing | AgentDS | **CLOSED** | Section 9 validation matrix: "cooperative async regression：现有纯 async tool 在 capsule integration 后 success / exception / timeout / cancel outcome 不变。" S1 expected assertions: "cooperative async fixture preserves existing success, exception, timeout and cancellation outcome behavior." |
| **MiMo 002**: S2 migration scope may be underestimated | AgentMiMo | **CLOSED** | Section 7.4.1 adds per-tool-family migration matrix. S2 "Exact allowed changes": "For each tool family, record chosen mode and feasibility result in the S2 implementation artifact." S2 requires implementation report with per-tool-family results, chosen mode, test cases, and uncovered items. |
| **MiMo 003**: Async HTTP abort path not explicitly covered | AgentMiMo | **CLOSED** | Section 7.3: async HTTP/httpx uses `async_direct` capsule semantics — task cancel + response/client close hook. Migration matrix row for "Async HTTP / httpx": `async_direct` with response/client close hook, deadline propagation. S2 expected assertions: "async HTTP / httpx cancellation closes or releases response/client resources." |

**Closure summary**: 2/2 blocking findings closed, 6/6 non-blocking findings closed. All 8 adjudicated items have specific, verifiable plan text.

---

## Scope Boundary Verification

| Constraint | Status | Evidence |
|---|---|---|
| No WU-LIFE-03 rework | **PASS** | Section 2: "不重做 WU-LIFE-03：不重写 Host active cancel watchdog、Run / Attempt terminal truth、late terminal race 或 queued promotion 状态机。" |
| No WU-LIFE-04 rework | **PASS** | Section 2: "不重做 WU-LIFE-04：不恢复 `active_cancel_timeout_seconds`，不引入第二套 cancel timeout，不把 cancel 解释为新的等待预算。" |
| No WU-WAIT-03 rework | **PASS** | Section 2: "不重做 WU-WAIT-03：不改变 WAITING external job cancel / revoke / abandon lifecycle，不绕过 `resolve_wait(...)` 和 late-result rejection。" |
| No second cancel timeout | **PASS** | Section 2, Section 6, Section 7.7 — consistently stated. `local_worker_close_grace_seconds` explicitly distinguished as cleanup grace, not cancel timeout. |
| No extension of `tool_execution_timeout_seconds` | **PASS** | Section 7.7: cleanup grace "不得从 `tool_execution_timeout_seconds` 派生更长等待"。All deadlines continue from existing `BatchToolExecutionContext.timeout_seconds`. |
| No provider-specific kill in Host core | **PASS** | Section 2: "不把 provider-specific kill API 硬编码进 Host core。" Capsule provides typed generic boundary; adapters implement provider-specific abort. |
| No UI/Service/Host/Engine layering breach | **PASS** | Section 3: Host design alignment preserves dependency direction; Engine contract unchanged; `dayu.runtime` helper constrained to layer-neutral. |

**Scope verdict**: All 7 scope constraints pass. No drift detected.

---

## Slice Code-Generation-Readiness Assessment

### Slice S1: ToolRuntime interrupt capsule and worker cleanup

| Criterion | Status | Notes |
|---|---|---|
| Objective clear | **PASS** | Three concrete goals: typed capsule, worker cleanup, non-cooperative fixture proof |
| Allowed files explicit | **PASS** | 9 files listed with fallback conditions |
| Exact changes enumerated | **PASS** | 8 specific changes with typed mode requirements, cleanup grace, barrier preservation |
| State transitions defined | **PASS** | 4 transitions: RUNNING→CANCELLING (unchanged), watchdog closeout (unchanged), worker cleanup after cancel (new), late result rejection (existing) |
| Error handling specified | **PASS** | 6 error cases: cooperative cancel outcome, timeout outcome, thread_backed unsupported, process_backed terminate→kill escalation, kill failure diagnostic, runtime helper failure non-blocking |
| Invariants listed | **PASS** | 7 invariants covering API, schema, timeout, provider isolation, lane release, thread_backed limitation |
| Test commands provided | **PASS** | Specific pytest + pyright + git diff commands |
| Expected assertions enumerated | **PASS** | 9 assertion categories with concrete verification targets |
| Stop conditions defined | **PASS** | 3 stop conditions: durable schema change, process-backed capsule can't carry callable, provider declarations needed in contracts |

**Verdict**: **Code-generation-ready.** The `on_cancel` → `close()` wiring is a direct integration of existing `_DefaultLocalWorkerEventStream.close()` infrastructure. An implementation agent can proceed without re-design.

### Slice S2: Production tool/provider migration

| Criterion | Status | Notes |
|---|---|---|
| Objective clear | **PASS** | Migrate doc/fins/web blocking paths to S1 interrupt boundary with per-family assessment |
| Allowed files explicit | **PASS** | 10 files listed with conditional `dayu/fins/*` helpers |
| Exact changes enumerated | **PASS** | 6 specific changes with per-family recording requirement, migration matrix reference, deadline propagation, WAITING path exclusion |
| State transitions defined | **PASS** | 3 transitions: normal accepted, cancelled before accepted, awaiting unchanged |
| Error handling specified | **PASS** | 4 error cases: business exceptions, cancellation projection, HTTP timeout vs Host cancel distinguishability, hard-kill diagnostic isolation |
| Invariants listed | **PASS** | 5 invariants: fins storage, no provider kill in Host, no magic branch, no extra payload, LLM-facing text constraints |
| Test commands provided | **PASS** | Specific pytest commands per tool family + pyright + git diff |
| Expected assertions enumerated | **PASS** | 6 assertion categories with per-family coverage |
| Stop conditions defined | **PASS** | 2 stop conditions: architecture change needed, key paths can't be process-backed/abort-capable |

**Verdict**: **Code-generation-ready.** The migration matrix in Section 7.4.1 gives the implementation agent a concrete decision framework per tool family. The S2 implementation report requirement provides reviewable output.

### Slice S3: Public Esc/cancel smoke, stale quarantine, docs sync

| Criterion | Status | Notes |
|---|---|---|
| Objective clear | **PASS** | Public UX validation, new input progress proof, docs sync |
| Allowed files explicit | **PASS** | 6 files listed with conditional smoke support and README/design doc conditions |
| Exact changes enumerated | **PASS** | 4 specific changes including non-cooperative blocking fixture smoke, stale late-result test, lane cleanup assertion, conditional docs update |
| State transitions defined | **PASS** | 3 transitions: Run A RUNNING→CANCELLING→CANCELLED, Run B QUEUED/STARTING→RUNNING→SUCCEEDED, late Run A result rejected |
| Error handling specified | **PASS** | 2 error cases: no private manual resolve shortcuts, non-TTY CI fallback via key monitor fake |
| Invariants listed | **PASS** | 3 invariants: Esc→GRACEFUL mapping, no command/API surface change, no future sandbox claims |
| Test commands provided | **PASS** | Full test suite commands covering CLI + Host + tools + pyright + git diff |
| Expected assertions enumerated | **PASS** | 5 assertion categories with public smoke, late result, lane cleanup, docs sync |
| Stop conditions defined | **PASS** | 1 stop condition: if Host still waits for old worker lane after watchdog terminal, return to S1 |

**Verdict**: **Code-generation-ready.** The non-cooperative blocking fixture requirement (added per F4 fix) ensures the smoke validates the actual #87 closeout scenario.

---

## New Findings

**No new blocking or non-blocking findings.**

Rationale: The plan fix comprehensively addressed all 8 adjudicated findings. The re-review verified each closure against specific plan text and confirmed the plan's specifications are consistent with existing code infrastructure (`_DefaultLocalWorkerEventStream.close()`, `_consume_worker_events` finally block, accept/ingest barriers). No material gaps, ambiguities, or contradictions found in the current plan text that would prevent an implementation agent from proceeding.

Minor observation (not a finding, no fix required): The plan uses "例如" (for example) qualifier for `local_worker_close_grace_seconds = 3.0` in Section 7.7. The 3.0s value is well-justified as a small bounded grace, and the principle (not a second cancel timeout, not derived from tool_execution_timeout_seconds) is unambiguously stated. The "例如" phrasing is acceptable at plan level — the implementation agent can choose a nearby value (e.g., 2.0–5.0) as long as the principle is preserved.

---

## Residual Risks / Uncovered Areas

All 5 plan-tracked residual risks (R1–R5) remain valid and appropriately owned:

| ID | Risk | Owner | Re-review Assessment |
|---|---|---|---|
| R1 | Tool callable not picklable for process-backed capsule | S1/S2 implementation | Migration matrix now provides per-family fallback strategies. Stop condition gates #87 closeout if key paths can't be migrated. Risk appropriately managed. |
| R2 | `asyncio.to_thread` thread continues after cancel | S2 implementation | Plan explicitly requires production blocking I/O to migrate to process-backed or request-abort-capable adapter. Thread path restricted to cooperative/read-only. Risk appropriately managed. |
| R3 | Race between worker stream close and cooperative cancel | S1 tests | Correctness via first-committer-wins + late rejection, not event ordering. Plan correctly identifies this as test concern, not design flaw. |
| R4 | Hard kill diagnostic entering LLM-facing result | S1/S2 implementation | Plan explicitly requires diagnostic isolation from business facts. |
| R5 | Public smoke in non-TTY CI | S3 tests | Key monitor fake + Host public lifecycle smoke fallback specified. |

No new residual risks identified beyond R1–R5 and the plan's own migration matrix stop conditions.

---

## Special Lens Re-Review

### Architecture Boundary

**PASS (unchanged from initial review).** The plan fix did not introduce new architectural coupling. Capsule remains ToolRuntime-owned; Engine contract unchanged; `dayu.runtime` constrained to layer-neutral; `dayu.contracts` defaulted to no-change with explicit stop condition.

### Overengineering

**PASS (unchanged).** The typed execution mode enum (`async_direct`/`thread_backed`/`process_backed`) is the minimum necessary distinction to prevent `thread_backed` from overpromising hard interrupt. It is not a general-purpose execution platform — it has exactly 3 modes, each with clearly bounded semantics.

### Overcoupling

**PASS (unchanged).** The migration matrix (Section 7.4.1) is a decision framework, not a coupling mechanism. Each tool family's migration path is independently specified with its own fallback and stop condition. No cross-tool-family coupling introduced.

---

## Verdict

**Verdict: PASS**

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Accepted findings closed**: 8/8 (2 blocking + 6 non-blocking)
- **Scope constraints**: 7/7 pass
- **Slice readiness**: 3/3 code-generation-ready
- **New findings**: 0

The plan is ready for implementation gate. All adjudicated findings are closed with specific, verifiable plan text. The 3 slices are well-scoped, have concrete allowed changes and stop conditions, and can be independently implemented and reviewed. No residual design ambiguities remain that would force an implementation agent to re-design.

---

## Artifact Path

`docs/reviews/wu-tools-cancel-01-plan-rereview-ds.md`
