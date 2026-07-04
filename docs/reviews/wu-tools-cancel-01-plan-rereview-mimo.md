# WU-TOOLS-CANCEL-01 Plan Re-Review — AgentMiMo

## Metadata

- **Reviewer**: AgentMiMo
- **Reviewed artifact**: `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md` (post-fix)
- **Work unit**: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- **Gate**: re-review
- **Timestamp**: 2026-07-04T18:34:05
- **Review inputs**:
  - `docs/reviews/wu-tools-cancel-01-plan-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-cancel-01-plan-fix-codex.md`

## Re-Review Scope

1. Verify accepted blocking findings (DS F1, DS F2 + MiMo 001) are closed.
2. Verify accepted non-blocking findings (F3, F4, F5, F6, MiMo 002, MiMo 003) are closed.
3. Verify plan remains scoped (no WU rework, no second cancel timeout, no layering breach).
4. Verify 3 implementation slices remain code-generation-ready and reviewable.
5. Identify any new issues.

---

## 1. Accepted-Blocking-Finding Closure Matrix

### DS F1 — `on_cancel` → worker stream interruption mechanism unspecified

**Status: CLOSED**

Plan Section 7.7 now specifies (lines 284-289):

- `on_cancel(...)` must call event stream `close()`, not just set a flag or cancel a bare task.
- `close()` cancels active `anext` task, awaits and suppresses `CancelledError`, calls `aclose()` on the underlying async generator.
- `close()` is idempotent (verified by code: `_DefaultLocalWorkerEventStream.close()` uses `self._lock` + `self._closed` guard).
- `_consume_worker_events(...)` reaches `finally` via either `CancelledError` re-raise or clean EOF path; both are tolerated.
- `finally` block (verified at `dispatch.py:3904-3923`) unregisters active handle, closes handle, releases lane token.
- `CancelledError` can propagate to dispatch owner task but must not skip `finally`.

**Code verification**: `_DefaultLocalWorkerEventStream.close()` at `local_proxy.py:221-239` implements exactly the described pattern: lock-guarded idempotency, task cancel + `_suppress_task_cancel` + `aclose()`. The `_consume_worker_events` `finally` at `dispatch.py:3904-3923` performs `_safe_release_lane_token(token)`.

**Verdict**: Fix is complete and code-grounded.

---

### DS F2 + MiMo 001 — Typed execution modes and per-mode terminate/kill semantics

**Status: CLOSED**

Plan Section 7.1 now includes a typed execution mode table (lines 209-215):

| Mode | `request_interrupt` | `terminate` | `kill` | Production-grade non-cooperative cancel |
|---|---|---|---|---|
| `async_direct` | Cancel task + adapter close response/stream | Adapter close (no process kill) | No-op diagnostic | Only if adapter can close underlying request/stream on task cancel |
| `thread_backed` | Set cooperative token + cancel wrapper awaitable | Does NOT stop OS thread; adapter socket/session close at most | Logs unsupported diagnostic | NOT satisfied for non-cooperative blocking |
| `process_backed` | Set token + stop receiving late result | Terminate process/group, close queue/pipe write end | Bounded grace → kill process/group, join/close | Satisfied (if entry/args/results serializable) |

Plan explicitly states (line 215): "生产级非协作 blocking cancel 只能由 `process_backed` 或 request-abort-capable 的 `async_direct` 满足。`thread_backed` 不是 hard interrupt 机制。"

Section 7.4.1 adds a per-tool-family feasibility matrix covering Doc, Fins read, Web sync HTTP, async HTTP/httpx, and Playwright, with picklability risks, fallback strategies, and a global design-gate stop condition.

**Verdict**: Fix is complete. Execution modes are typed, per-mode semantics are explicit, thread_backed does not overpromise, and the feasibility matrix addresses the DS F2 concern about S1 discovering process-backed infeasibility too late.

---

## 2. Accepted-Non-Blocking-Finding Closure Matrix

### F3 — Bounded cleanup grace value unspecified

**Status: CLOSED**

Plan Section 7.7 (line 288) now specifies: "worker handle close 使用内部小型 cleanup grace，例如命名常量或 typed internal option `local_worker_close_grace_seconds = 3.0`。这是 cleanup grace，不是 cancel timeout，不是 public API，不得从 `tool_execution_timeout_seconds` 派生更长等待。"

Line 289: "close grace 到期后记录 bounded diagnostic 并继续释放 lane token。"

**Verdict**: Closed. Value is specified (3.0s), semantics are explicit (not a second cancel timeout, does not extend tool deadline), and diagnostic on timeout is required.

---

### F4 — Slice 3 public smoke lacks non-cooperative blocking fixture

**Status: CLOSED**

Plan Section 8 Slice S3 "Exact allowed changes" (lines 506-507) now requires: "Add public or Host-public smoke where Run A uses a non-cooperative blocking fixture, interactive Esc / cancel returns user to input-ready state, and Run B in the same Session advances to terminal."

S3 "Expected assertions" (line 541): "public Esc/cancel smoke or Host-public lifecycle smoke uses a non-cooperative blocking fixture for Run A, then proves Run B advances in the same Session."

**Verdict**: Closed. S3 now explicitly requires non-cooperative blocking fixture in the public smoke, not just cooperative cancellation.

---

### F5 — `dayu.contracts` modification scope ambiguity

**Status: CLOSED**

Plan Section 5 "Runtime / contracts" (lines 133-134) now reads: "默认不修改 `dayu.contracts`。Execution mode 优先作为 Host / runtime internal typed contract；如果直接证据证明 provider 必须在 shared tool declaration 中声明 mode / interrupt capability，implementation 必须停止并返回 design / contract gate。"

Section 6 "Not required" (line 189): "默认不新增 `dayu.contracts` 字段。"

**Verdict**: Closed. Default is no change; stop condition if evidence requires it.

---

### F6 — Cooperative async path regression coverage missing

**Status: CLOSED**

Plan Section 9 "Implementation Validation Matrix" (line 581) now includes: "cooperative async regression：现有纯 async tool 在 capsule integration 后 success / exception / timeout / cancel outcome 不变。"

S1 "Expected assertions" (line 383): "cooperative async fixture preserves existing success, exception, timeout and cancellation outcome behavior."

**Verdict**: Closed. Validation matrix explicitly requires regression coverage for cooperative async path.

---

### MiMo 002 — S2 migration scope may be underestimated

**Status: CLOSED**

Plan S2 "Exact allowed changes" (line 425) now requires: "For each tool family, record chosen mode and feasibility result in the S2 implementation artifact: direct process-backed, request-abort-capable async direct, cooperative-only / non-production, or design-stop."

S2 "Expected assertions" (line 469): "S2 implementation artifact includes doc / fins / web sync HTTP / async HTTP / Playwright migration assessment and chosen fallback/stop classification."

**Verdict**: Closed. S2 now requires per-tool-family assessment before migration.

---

### MiMo 003 — Async HTTP abort path not explicitly covered

**Status: CLOSED**

Plan Section 7.3 (lines 234-236) now specifies: "async provider / httpx path：按 `async_direct` capsule 语义执行，取消 pending task，并通过 adapter hook 关闭 response / stream / client。"

Section 7.4.1 feasibility matrix row for "Async HTTP / httpx" (line 259): "`async_direct`，task cancel + response/client close hook；保留剩余 tool deadline 到 request timeout。"

S2 "Exact allowed changes" (line 429): "Async HTTP / httpx paths must use `async_direct` semantics or an explicit adapter abort hook; tests must validate response / client cleanup after cancel."

**Verdict**: Closed. Async HTTP uses `async_direct` mode with adapter abort hook; cleanup validation required.

---

## 3. Scope Discipline Verification

| Scope constraint | Status | Evidence |
|---|---|---|
| No WU-LIFE-03/04 rework | ✅ Pass | Section 2 Non-goals: "不重做 WU-LIFE-03"、"不重做 WU-LIFE-04" |
| No WU-WAIT-03 rework | ✅ Pass | Section 2 Non-goals: "不重做 WU-WAIT-03" |
| No second cancel timeout | ✅ Pass | Section 2 + Section 6: "不引入第二套 cancel timeout" |
| No extension of `tool_execution_timeout_seconds` | ✅ Pass | Section 7.7: cleanup grace "不得从 `tool_execution_timeout_seconds` 派生更长等待" |
| No provider-specific kill in Host core | ✅ Pass | Section 2 + Section 7.1: capsule is typed generic boundary |
| No UI/Service/Host/Engine layering breach | ✅ Pass | Section 3: Host→Engine direction preserved; capsule is ToolRuntime internal; runtime helper in `dayu.runtime` has no Host/Engine imports |

**Verdict**: Plan remains correctly scoped. No scope creep detected.

---

## 4. Implementation Slice Readiness

### S1: Interrupt capsule + local worker cleanup

- **Code-generation-ready**: Yes. Allowed files, exact allowed changes, invariants, stop conditions, error handling, and expected assertions are all specified.
- **Reviewable**: Yes. Semantic closure (capsule boundary + worker cleanup + focused tests). No hidden cross-slice dependency.
- **Key mechanism grounded**: `on_cancel` → `close()` → `CancelledError` path → `finally` lane release. All verified against code.

### S2: Production tool/provider migration

- **Code-generation-ready**: Yes. Per-tool-family feasibility matrix with picklability risks, fallback strategies, and design-gate stop condition. Migration assessment required per tool family.
- **Reviewable**: Yes. Each tool family has a clear migration path (process-backed / async_direct / design-stop). Stop conditions prevent silent degradation.
- **Key risk mitigated**: Picklability risk (R1) now has a decision framework before implementation, not just a reactive stop condition.

### S3: Public Esc/cancel smoke + stale quarantine + docs sync

- **Code-generation-ready**: Yes. Non-cooperative blocking fixture required in public smoke. Stale quarantine assertion specified. Docs sync decision framework included.
- **Reviewable**: Yes. End-to-end UX validation with clear expected assertions.
- **Key gap closed**: Non-cooperative blocking + new input progress now explicitly required (was F4).

**Verdict**: All 3 slices are code-generation-ready and reviewable.

---

## 5. New Findings

No new blocking or non-blocking findings identified during re-review.

The plan fix addressed all accepted findings from the controller adjudication. Code verification confirms the mechanisms described in the plan match actual source code behavior. The feasibility matrix (Section 7.4.1) provides a concrete decision framework for S2 implementation, which was the most significant gap in the original plan.

---

## 6. Residual Risks / Uncovered Areas

| ID | Risk | Status | Notes |
|---|---|---|---|
| R1 | Pickling risk for process-backed capsule | Unchanged | Now has feasibility matrix and fallback framework in Section 7.4.1; owner remains S1/S2 implementation |
| R2 | `asyncio.to_thread` thread continues after cancel | Unchanged | Production blocking I/O must migrate to process-backed or request-abort-capable async_direct; owner S2 |
| R3 | Race between worker stream close and cooperative cancel | Unchanged | Correctness via Host terminal first-committer-wins and late rejection; owner S1 tests |
| R4 | Hard kill diagnostic in LLM-facing result | Unchanged | Must be bounded runtime diagnostic, not business fact; owner S1/S2 |
| R5 | Public smoke in non-TTY CI | Unchanged | Use key monitor fake at CLI command boundary; owner S3 |

No new residual risks identified. Existing risks have clear owners and destinations.

---

## 7. Verdict

**Verdict: pass**

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Accepted-finding closure**: 8/8 closed (2 blocking + 6 non-blocking)
- **Scope discipline**: Verified — no rework, no scope creep, no layering breach
- **Slice readiness**: 3 slices code-generation-ready and reviewable
- **Code verification**: All key code references confirmed against source

The plan is ready to proceed to implementation gate.

---

## Artifact Path

`docs/reviews/wu-tools-cancel-01-plan-rereview-mimo.md`
