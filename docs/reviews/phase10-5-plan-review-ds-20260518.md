# Phase 10.5 Plan Review

**Reviewer**: AgentDS (P10.5 plan review specialist)
**Date**: 2026-05-18
**Gate**: Phase 10.5 plan review
**Review type**: adversarial plan review — handoff-readiness / code-generation-readiness
**Reviewed artifact**: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`

**Design truth**: `docs/host/design.md`
**Control truth**: `docs/host/implementation-control.md`
**P10.5 scope/coverage input**: `docs/host/post-p10.md`
**Readiness review inputs**:
- `docs/reviews/post-p10-5-plan-readiness-review-mimo-20260518.md`
- `docs/reviews/post-p10-5-plan-readiness-review-ds-20260518.md`
- `docs/reviews/post-p10-5-plan-readiness-review-codex-20260518.md`

---

## Review Question

Is the plan handoff-ready / code-generation-ready — can an implementation agent pick up this plan and implement P10.5 without redesigning public API, state machine, schema, file ownership, test boundaries, or smoke success signals?

---

## Conclusion

**PASS.** The plan is handoff-ready. It correctly derives all decisions from the design truth, closes all readiness review items, provides a complete unified coverage table with per-row owner/test/public-path assertions/skip conditions, and defines six well-scoped implementation slices with clear allowed files, exact allowed changes, non-goals, state transitions, tests, validation commands, and stop conditions.

0 blocking findings. 5 non-blocking findings, 3 clarification findings, 4 residual risks.

---

## Blocking Findings

**None.**

---

## Non-blocking Findings

### N1. Slice 2 stop condition implicitly depends on Slice 3 request shape work

**Severity**: non-blocking
**Evidence**:
- Plan Slice 2 stop condition (line 357): "A deterministic no-tool local worker can complete one public `submit_followup(queue)` through `open_host` without manual scheduler wakeup."
- Plan Slice 3 (line 361-400): defines `SubmitFollowupRequest` new fields (`system_prompt`, `user_prompt`, `tool_names`, optional `runner_spec`/`runner_options`/`agent_policy`), replaces old `HostInput` usage.

**Problem**: Slice 2's stop condition requires `submit_followup(queue)` to work end-to-end. But the new typed request shape with `system_prompt`/`user_prompt` fields is defined in Slice 3. The plan doesn't clarify whether Slice 2 validates against the current codebase's existing request shape (old `HostInput`) or must already consume the new shape. If Slice 2 uses the old shape, Slice 3 will need to refactor Slice 2's request handling. If Slice 2 must use the new shape, then Slice 3's request contract work must be completed before Slice 2's stop condition can be met.

**Why not blocking**: The implementation agent can use the existing `HostInput` shape in Slice 2 and migrate in Slice 3, or reorder to do request shape first. Either path is clear enough.

**Suggested fix**: Plan should note: "Slice 2 may validate with current `HostInput` shape; Slice 3 migrates to new `SubmitFollowupRequest` fields. Slice 2 stop condition uses the shape available at that point."

---

### N2. `ensure_session`/`create_session`/`get_session` async public handle wrappers not explicitly allocated to any slice

**Severity**: non-blocking
**Evidence**:
- Plan Public Contract Change List (line 78): "新增 Host public handle：只暴露普通 Service 需要的方法"
- Plan Slice 2 allowed changes (line 331-336): lists wiring for command handle, scheduler, wakeup, memory catch-up, compactor, close lifecycle. Does not list "add async wrappers for ensure_session/create_session/get_session to public handle."
- Design.md §11 (line 920-925): `ensure_session`, `create_session`, `get_session` are in the minimum interface set.

**Problem**: The public contract change list says the Host public handle exposes session methods. But no slice explicitly assigns the task of wrapping existing `ensure_session`/`create_session`/`get_session` as async public handle methods. Slice 2 wires the internal command handle — these methods may come "for free" through delegation — but the plan doesn't say so. The implementation agent might not know whether to add explicit async wrappers or rely on internal delegation.

**Why not blocking**: Slice 2 wires `dayu/host/command.py` and `dayu/host/api.py` into the composition root. The existing command facade already has these methods. The implementation agent can infer that they become available through the public handle. Slice 2's allowed files include `dayu/host/api.py` where these live.

**Suggested fix**: Slice 2 exact allowed changes should add: "Delegate existing `ensure_session`/`create_session`/`get_session`/`get_run` from internal command handle to public async handle facade."

---

### N3. Existing `HostEventStream` class disposition not explicit

**Severity**: non-blocking
**Evidence**:
- Plan Public Contract Change List (line 90): "`HostEventStream` 若保留，只能是内部实现或返回类型别名 / Protocol；不能成为 Service 必须理解的 context manager、subscription handle 或第二套 public stream contract."
- Plan Slice 4 (line 420): "Remove ordinary public docs / exports for `HostEventView` and `stream_run_events`"
- Codex F2 (readiness review): requires `HostEventStream` terminology convergence.
- Current code: `HostEventStream` exists in `dayu/host/__init__.py.__all__`.

**Problem**: The plan says what `HostEventStream` must NOT be, but doesn't say what the implementation agent should DO with the existing class. Slice 4 addresses `HostEventView` and `stream_run_events` removal from exports, but doesn't mention `HostEventStream` by name in its allowed changes. The implementation agent might leave it in public exports, rename it, or remove it — all could be valid but the uncertainty is unnecessary.

**Why not blocking**: The plan's public contract change list (line 90) is clear enough: if kept, internal-only or type alias. Slice 4's non-goals and the plan's explicit statement converge on the right behavior. The implementation agent just needs to apply this rule to the existing class.

**Suggested fix**: Slice 4 exact allowed changes should add: "Remove `HostEventStream` from `dayu.host` public exports if it exists there; keep as internal module-level type alias for `AsyncIterator[HostEvent]` if needed by implementation."

---

### N4. `CompactorExecutionBaseline | None` semantics not stated

**Severity**: non-blocking
**Evidence**:
- Plan typed options shape (line 140): `compactor_baseline: CompactorExecutionBaseline | None`
- Plan S4 compact smoke boundary (line 238): "Host production opener 不得隐式默认 fake compactor."
- Design.md §11 (line 865): compactor execution baseline is independent construction-time baseline.

**Problem**: `compactor_baseline` is typed as `CompactorExecutionBaseline | None`. When `None`, what is the behavior under budget pressure? Does compaction fail-closed (Run fails with budget error)? Is proactive compact skipped (Run proceeds until reactive overflow triggers, then fails)? The plan doesn't state the None-semantics. The implementation agent needs to decide: should `None` mean "no compaction capability, fail on budget pressure" or "skip compaction, hope budget is enough"?

**Why not blocking**: The smoke test requires an explicit real compactor adapter (S4). The None case is a valid production configuration (short sessions that never hit budget). The implementation agent can choose fail-closed as the safe default. The semantic boundary (independent baseline, not affected by ordinary Run override) is already frozen.

**Suggested fix**: Plan should state: "When `compactor_baseline=None`, budget pressure triggers fail-closed (Run fails with budget error). Compaction is opt-in via explicit `CompactorExecutionBaseline`."

---

### N5. Slice 2 compactor wiring description is underspecified

**Severity**: non-blocking
**Evidence**:
- Plan Slice 2 exact allowed changes (line 333): "Wire memory projection catch-up and compactor baseline into dispatch path through existing `HostLocalExecutionOptions` or refined internal equivalent."
- Design.md §11 (line 869): Host opener must wire compactor baseline, budget policy, artifact root, and memory catch-up; Service must not touch these internals.

**Problem**: "Through existing `HostLocalExecutionOptions` or refined internal equivalent" is vague. `HostLocalExecutionOptions` is being demoted to internal contract in the same plan (Slice 1). The implementation agent needs to know: does Slice 2 construct `HostLocalExecutionOptions` from `OpenHostOptions` fields? Does it pass `CompactorExecutionBaseline` through as-is? Does it need to create new internal wiring points?

**Why not blocking**: The plan already says Slice 2 builds internal `HostCommandHandleOptions` and `HostLocalExecutionOptions` from `OpenHostOptions` (line 331). The compactor wiring is part of that translation. The implementation agent can follow the existing code's pattern for how `HostLocalExecutionOptions` receives compactor-related fields.

**Suggested fix**: Add to Slice 2: "Map `OpenHostOptions.compactor_baseline` fields to internal `HostLocalExecutionOptions` compactor fields (context_compactor, compactor_runner_spec, compactor_runner_options, compactor_policy_ref, compact_artifact_root)."

---

## Clarification Findings

### C1. Coverage table S4 compact owner "Slice 1 + Slice 6" — Slice 2 wiring not referenced

**Severity**: clarification
**Evidence**:
- Plan unified coverage table (line 269): "S4 compact real compactor | Slice 1 + Slice 6"
- Plan Slice 1 (line 276-315): defines types only, no runtime wiring.
- Plan Slice 2 (line 316-357): wires compactor baseline into dispatch path.
- Plan Slice 6 (line 493-533): smoke tests.

**Problem**: The coverage table says S4 compact smoke owner is "Slice 1 + Slice 6." But the compactor wiring that makes the smoke possible is in Slice 2 (line 333: "Wire memory projection catch-up and compactor baseline into dispatch path"). Slice 1 only defines `CompactorExecutionBaseline` as a type. The coverage table should reference Slice 2 as the wiring owner.

**Why not blocking**: The coverage table's "Owner slice" column is primarily about which slice proves the coverage, not which slice builds the dependency. Slice 6 runs the smoke, Slice 1 defines the types it validates. Slice 2 is an implicit dependency of all slices. The table is still accurate about where the test lives and what it proves.

**Suggested fix**: Consider adding a "depends on slice" column or noting in the S4 row that Slice 2 provides the wiring dependency.

---

### C2. `HostToolingOptions` shape assumed from existing codebase, not restated in plan

**Severity**: clarification
**Evidence**:
- Plan typed options shape (line 138): `tooling_options: HostToolingOptions | None`
- Design.md §11 (line 861): options must include "全量 business `ToolBundle`、ToolRuntime policy"

**Problem**: `HostToolingOptions` already exists in the codebase. The plan uses it as a field type without restating its shape. The implementation agent needs to know: does the existing `HostToolingOptions` already carry both the business `ToolBundle` and the ToolRuntime policy? If ToolRuntime policy is a separate concern, is there a missing field in `OpenHostOptions`?

**Why not blocking**: The existing `HostToolingOptions` type in the codebase is the authoritative definition. The plan defers to it. If the existing type doesn't cover ToolRuntime policy separately, that's a pre-existing code issue, not a plan defect.

**Suggested fix**: Plan could add a one-line note: "`HostToolingOptions` shape as currently defined in `dayu/host/api.py`; if it lacks ToolRuntime policy fields, Slice 1 adds them as typed fields."

---

### C3. Slice dependency ordering — implicit cross-slice dependencies could confuse sequential implementation

**Severity**: clarification
**Evidence**:
- Plan slices are numbered 1-6 and presented sequentially.
- Slice 4 (event stream) needs Slice 2 (runtime) to have a working `open_host` to attach to.
- Slice 5 (control commands) needs Slice 3 (request contract) for typed request shapes, and Slice 2 for runtime.
- Slice 3 (request contract) refines what Slice 2's stop condition validated against.

**Problem**: The slices are presented as a sequential list, but they have non-linear dependencies. Slice 4 can't be fully tested until Slices 2 and 3 exist. Slice 5 needs Slices 2, 3, and 4. An implementation agent working strictly sequentially might hit "cannot test" walls. The plan doesn't have a dependency diagram or explicit notes about which slices can be developed in parallel.

**Why not blocking**: The slice stop conditions are worded as integration milestones, not as "all tests must pass in isolation." Slice 4's stop condition (line 441): "S1 can consume final answer exclusively through `watch_session_events`" — this is a cross-slice validation that naturally comes after Slice 3. The implementation agent can read the stop conditions and infer ordering. Professional judgment suffices.

**Suggested fix**: Add a one-paragraph "Slice Dependency Graph" before the slice list, noting: Slice 1 → Slice 2 → {Slice 3, Slice 4} → Slice 5 → Slice 6.

---

## Readiness Review Closure Verification

Each non-blocking/clarification item from the three readiness reviews is checked against the plan:

| Review item | Source | Plan resolution | Status |
| --- | --- | --- | --- |
| Smoke naming/owner gap | MiMo F1, Codex F1 | Unified coverage table maps all S1-S5, WAITING, steer/retry/replay, multi-client watch, close boundary to slice/tests. | **Closed** |
| `OpenHostOptions` typed shape | MiMo F2, DS F1 | Slice 1 defines `OpenHostOptions`, `OrdinaryRunExecutionBaseline`, `CompactorExecutionBaseline` as frozen slots dataclasses. | **Closed** |
| `HostClosedError` identity | MiMo F3 | Plan specifies standalone lifecycle exception; if new error code needed, stops for Controller. | **Closed** |
| S5/WAITING checklist | MiMo F4, Codex F1 | Coverage table has dedicated rows for cancel accepted/queued/pre-dispatch/active/session-scope/close boundary and WAITING resume public path. | **Closed** |
| HostEvent typed shape | DS F2, Codex F2 | Slice 4 freezes terminal `SUCCEEDED`/`FAILED`/`CANCELLED` typed view. `HostEventStream`收敛为非 Service-facing handle. | **Closed** |
| Per-run partial merge | DS F3 | Plan explicitly chooses field-level partial merge (not all-or-nothing). Slice 3/Slice 6. | **Closed** |
| Followup watermark | DS F4 | Plan states watermark is not watch cursor. Slice 2/Slice 3. | **Closed** |
| Compactor typed options | DS F5 | Plan defines `CompactorExecutionBaseline` sub-object; states it's不受 ordinary override 影响. | **Closed** |
| Gate state sync | DS F6 | Plan notes this is Controller responsibility. | **Closed** |

**Verdict**: All 9 readiness review items are closed with explicit plan resolution, owner slice, or Controller handoff.

---

## Design Conformance Verification

### Public API conformance

| Design requirement (design.md §11) | Plan coverage | Status |
| --- | --- | --- |
| `open_host(options)` async context manager | Plan §Typed Options Shape, Slice 1 | **Conformant** |
| Host public handle with async methods only | Plan §Public Contract Change List, Slice 2 | **Conformant** |
| `submit_followup(queue)` as sole prompt entry | Plan §Public Contract Change List, Slice 3 | **Conformant** |
| `watch_session_events(session_id) -> AsyncIterator[HostEvent]` | Plan §Session-level Live Event Stream, Slice 4 | **Conformant** |
| terminal `HostEvent` final answer view fields: content, filtered, degraded, finish_reason, terminal_status | Plan §Session-level Live Event Stream (line 197) | **Conformant** |
| `start_run` → internal `_start_run` | Plan §Public Contract Change List (line 86), Slice 1 (line 293-295) | **Conformant** |
| `HostEventView` internal DTO only | Plan §Public Contract Change List (line 89), Slice 4 (line 420) | **Conformant** |
| `stream_run_events` internal only | Plan §Public Contract Change List (line 89), Slice 4 (line 420) | **Conformant** |
| Field-level partial merge for per-run execution override | Plan §Per-run Effective Config Freeze (line 168-176) | **Conformant** |
| Per-run `tool_names` selector: None=all, empty=disable, subset=filter | Plan §Per-run Tool Selection (line 180-187) | **Conformant** |
| Compactor baseline independent of ordinary Run override | Plan §Memory Catch-up And Compact Opener Contract (line 240) | **Conformant** |
| `close_session` ≠ cancel ≠ opener close | Plan §Close / Cancel Boundary (line 209-214) | **Conformant** |
| `resolve_wait` public resume path, no callback/poller loop | Plan §WAITING Resume Path (line 218-229) | **Conformant** |
| No `wait_final_answer`, no public payload reader | Plan §Non-goals (line 35-36), §Public Contract Change List | **Conformant** |

### Architecture boundary conformance

| Boundary (design.md §2) | Plan safeguard | Status |
| --- | --- | --- |
| Engine 不得理解 Host 状态 | Plan §Scope Boundary (line 50) | **Conformant** |
| Service 不得手工装配 Host internals | Plan §Scope Boundary (line 51), Slice 2 objective | **Conformant** |
| EngineEvent `tool_awaiting` 不得创建 wait record | Plan §Scope Boundary (line 53) | **Conformant** |
| Replay 不得暴露 tool schemas 或执行工具 | Plan §Scope Boundary (line 54), Slice 5 (line 463) | **Conformant** |

---

## Implementation-Control Phase 10.5 Conformance

### Key design questions

| Control doc key design question (implementation-control.md Phase 10.5) | Plan resolution | Status |
| --- | --- | --- |
| options shape, lifecycle, error semantics | Slice 1 + Slice 2 | **Addressed** |
| Host opener close shutdown order | Slice 2 (line 335) | **Addressed** |
| command → scheduler wakeup internal wiring | Slice 2 (line 332-333) | **Addressed** |
| session-level live Host event stream | Slice 4 | **Addressed** |
| multi-client write strategy | Coverage table + Slice 3/4/6 | **Addressed** |
| Outbox裁剪 (freeze recipe only) | Non-goals (line 30), Docs Decision | **Addressed** |
| submit_followup request/response contract | Slice 3 | **Addressed** |
| per-run tool selection contract | Slice 3 | **Addressed** |
| memory catch-up / compactor opener contract | Slice 1 + Slice 2 | **Addressed** |
| WAITING / resolve_wait public resume | Slice 5 | **Addressed** |
| Session cleanup (close_session/public contract) | Slice 2 + Slice 5 | **Addressed** |
| HostEventStream typed HostEvent terminal contract | Slice 4 | **Addressed** |
| per-run execution override field-level partial merge | Slice 3 / Slice 6 | **Addressed** |
| steer/retry/replay local semantics | Slice 5 | **Addressed** |
| smoke coverage matrix | Unified coverage table | **Addressed** |

### Exit conditions

| Control doc exit condition | Plan validation | Status |
| --- | --- | --- |
| 普通 Service 只调 Host public contract 完成多轮闭环 | S1 real-runner smoke (coverage table row 1) | **Provable** |
| steer/retry/replay 不再是 stable unsupported | Slice 5 stop condition (line 491) | **Provable** |
| smoke 均走同一 public path | Coverage table public-path assertions column | **Provable** |
| 冻结结论写入 closeout | Docs Decision (line 535-542) | **Planned** |
| P11 可在不破坏 P10.5 contract 下继续 | Residual Risks (line 585) | **Acknowledged** |

---

## Coverage Table Audit

Each row in the unified coverage table is checked for: owner slice, test name, public-path assertions, skip condition, follow-up owner.

| Coverage row | Owner slice | Test name present? | Public-path assertions? | Skip condition? | Follow-up owner? | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| S1 real-runner no-tool multi-turn | Slice 6 | Yes | Yes — `open_host`, `submit_followup(queue)`, pre-start governance, LocalProxy/real runner, memory catch-up, terminal `HostEvent.final_answer.content` | Yes — provider secret/network unavailable | Controller if all skipped | **Complete** |
| S1 multi-client watch / queue idempotency | Slice 3+4+6 | Yes — two test names | Yes — two watchers observe same terminal; different client_request_id queue; same idempotency | Yes — provider skip for real runner variant | None | **Complete** |
| S1 per-run execution override | Slice 3+6 | Yes | Yes — field-level override freezes effective config | None for unit; provider skip for real | None | **Complete** |
| S1 WAITING public resume | Slice 5 | Yes | Yes — public `resolve_wait`, after-commit wakeup, terminal HostEvent | None for mock waiting tool | Callback/poller to later owner | **Complete** |
| S1 steer/retry/replay controls | Slice 5 | Yes — three test names | Yes — public handle; events/get_run visible; retry/replay source relation; replay no-tool | None for deterministic harness | LOST/RECOVERING to Phase 11 | **Complete** |
| S2 mock-tool wiring | Slice 3+6 | Yes — two test names | Yes — ToolBundle from opener; tool_names subset/empty; ToolExecutor path; Host accept barrier; tool fact in memory | None | Real business tools to Phase 12 | **Complete** |
| S3 real-runner matrix | Slice 6 | Yes — parametrized | Yes — four providers, same public path, two-turn answer non-empty | Yes — per provider API key/network | Controller if all skipped | **Complete** |
| S4 compact real compactor | Slice 1+6 | Yes | Yes — real compactor adapter; canonical events and artifact; memory projection; continuity marker | Yes — provider secret/network; mock compactor cannot replace | Provider-specific hardening | **Complete** (see C1) |
| S5 cancel accepted/queued/pre-dispatch | Slice 5 | Yes — two test names | Yes — public cancel only; no internal dispatch row edits; get_run and watch see cancel | None | Active cancel watchdog to Phase 11 | **Complete** |
| S5 active/session-scope cancel | Slice 5+6 | Yes — two test names | Yes — shared active registry; cancel event visible; session-scope isolation | Deterministic worker path required; long-running may skip | Phase 11 stuck active timeout | **Complete** |
| S5 close boundary | Slice 2+5 | Yes | Yes — close_session rejects input, keeps read/watch; opener close raises HostClosedError, no cancel facts; cancel writes cancel facts | None | Purge to Phase 15 | **Complete** |

**Coverage table verdict**: All 11 rows have owner slice, test name, public-path assertions, skip conditions, and follow-up owners. No row relies on mock runner, internal durable table reads, or bypass of public path.

---

## Slice Quality Assessment

| Slice | Objective clear? | Allowed files explicit? | Exact changes explicit? | Non-goals clear? | State transitions? | Tests named? | Validation commands? | Stop condition measurable? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Slice 1 | Yes | Yes | Yes | Yes | N/A (types only) | Yes (2 files) | Yes | Yes |
| Slice 2 | Yes | Yes | Yes | Yes | Yes | Yes (2 files) | Yes | Yes |
| Slice 3 | Yes | Yes | Yes | Yes | Yes | Yes (3 files) | Yes | Yes |
| Slice 4 | Yes | Yes | Yes | Yes | Yes | Yes (2 files) | Yes | Yes |
| Slice 5 | Yes | Yes | Yes | Yes | Yes | Yes (4 files) | Yes | Yes |
| Slice 6 | Yes | Yes | Yes | Yes | Yes | Yes (5 files) | Yes | Yes |

**Slice quality verdict**: All six slices meet the minimum bar for code-generation-readiness. No slice asks the implementation agent to design public API, state machine, or file ownership from scratch.

---

## Residual Risks

| # | Risk | Severity | Owner | Mitigation |
| --- | --- | --- | --- | --- |
| R1 | Real runner matrix all-skip (no provider available) | Medium | Slice 6 + Controller | Skip reasons must name provider and missing env; Controller decides acceptance. Plan explicitly flags this (line 583). |
| R2 | Real compactor adapter unavailable | Medium | Slice 6 + Controller | Mock compactor cannot replace success signal. Plan explicitly flags this (line 584). |
| R3 | Phase 11 Recovery may need to modify P10.5-frozen interfaces if P10.5 implementation makes crash-free assumptions | Low | Phase 11 | Mitigated by design.md §27 and implementation-control.md Phase 11 precondition: "不得破坏 P10.5 已冻结 contract." |
| R4 | `OpenHostOptions` field count (18+ fields) — Service construction may be verbose | Low | Slice 1 | Plan allows implementation to微调 field names. Sensible defaults for lane parameters could reduce verbosity without violating the "no ConfigLoader" rule. Future phases can add builder/helper without changing the frozen contract. |

---

## Verdict

**PASS.** The plan is handoff-ready and code-generation-ready.

- **Blocking count**: 0
- **Non-blocking count**: 5 (N1-N5)
- **Clarification count**: 3 (C1-C3)
- **Residual risks**: 4 (R1-R4)

The implementation agent can proceed to Slice 1 without redesigning public API, state machine, schema, file ownership, test boundaries, or smoke success signals. All design decisions are derived from `docs/host/design.md` and `docs/host/implementation-control.md`. All three readiness review non-blocking/clarification items are closed with explicit plan resolution. The unified coverage table provides complete per-row ownership, test names, public-path assertions, skip conditions, and follow-up owners.

---

**Artifact path**: `docs/reviews/phase10-5-plan-review-ds-20260518.md`
