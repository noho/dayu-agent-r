# Phase 9 Plan Review — Adversarial Review Artifact

**Reviewer**: AgentDS (planreview skill)
**Date**: 2026-05-16
**Plan under review**: `docs/host/phase9-conversation-memory-plan.md`
**Design truth sources**:
- `docs/host/design.md` §23 RunInputBuilder, §24 Conversation Memory, §26 Evidence / Retrieval / Long-term Memory
- `docs/host/implementation-control.md` Phase 9 entry + P9 design refinement 追踪
**Codebase evidence**:
- `dayu/host/run_input.py` (RunInputBuilder, MemorySnapshotProvider protocol, MemorySnapshotView, SessionContinuityProvider, factory functions)
- `dayu/host/projection.py` (ProjectionConsumer, ProjectionRunner, ProjectionEventView, ProjectionEventFilter)
- `dayu/host/durable/schema.py` (HOST_SCHEMA_VERSION=5, PROJECTION_TABLES, HOST_DURABLE_TABLES)
- `dayu/host/api.py` (AttemptDispatchSnapshot)
- `dayu/host/durable/event_log.py` (EventClass.CANONICAL_FACT)

---

## Verdict: PASS

**Blocking findings: 0**

The plan correctly implements the P9 design refinement rulings recorded in `implementation-control.md`. No design deviation, no Host boundary violation, no scope creep into long-term retrieval or business semantics. The four memory views, provenance model, provider boundary, budget strategy, and lag/repair semantics are all consistent with the design truth sources.

Below are evidence-based findings, ordered by severity. All are non-blocking; the plan is implementation-ready.

---

## Findings

### F1 [MEDIUM] Claim status lifecycle undefined for P9 — which statuses does P9 actually produce?

**Evidence**:
- Plan §4.2 defines `MemoryClaimStatus` enum: `TOOL_VERIFIED`, `ASSUMPTION`, `CANDIDATE`, `CONFLICTED`, `STALE`, `SUPERSEDED`.
- Plan §1 explicitly says "长期记忆、跨多年 signal ledger...不是 P9 必要条件" and "P9 不实现业务归因 verification".
- Plan §12 residual risks routes conflict/staleness detection to issue 39 / future phases.
- Plan §9 anti-hallucination test matrix only tests `TOOL_VERIFIED` provenance and `final_answer` → not verified fact. No test covers CONFLICTED, STALE, or SUPERSEDED lifecycle.

**Finding**: The plan defines six claim statuses but never specifies which ones the P9 projection consumer actively populates. `CONFLICTED` requires cross-claim comparison logic that P9 doesn't implement. `STALE` requires supersede/policy-expiry detection that P9 doesn't implement. `SUPERSEDED` requires claim lineage tracking that P9 doesn't implement. `CANDIDATE` is defined as "早期弱信号或待验证线索" but the plan gives no projection rule for when an event produces CANDIDATE vs. ASSUMPTION.

**Risk**: Implementation agent may attempt to build staleness/conflict detection that belongs in issue 39, wasting effort and introducing unvalidated logic.

**Recommendation**: Add explicit statement: "P9 projection only produces `TOOL_VERIFIED` (from `TOOL_RESULT_ACCEPTED`) and `ASSUMPTION` (from user input, assistant conclusion, LLM patch candidate). `CANDIDATE`, `CONFLICTED`, `STALE`, and `SUPERSEDED` are reserved enum values; their population logic is owned by issue 39 / future long-term memory phase." Also add a test: "P9 memory projection never produces CONFLICTED, STALE, or SUPERSEDED claim status."

---

### F2 [MEDIUM] `RUN_SUCCEEDED` event consumption purpose underspecified

**Evidence**:
- Plan §6 lists `RUN_SUCCEEDED` in the event_filter for `ConversationMemoryProjectionConsumer`.
- Plan §9 anti-hallucination test matrix: "`final_answer` 不进入 `verified_facts`；只能作为 assistant conclusion / raw continuity."
- Design §24: "`final_answer` 是 assistant role 产出的最终回答，只能作为 raw turn / assistant conclusion 参与连续性."
- Plan §6 does not explicitly describe what `apply_event` does with `RUN_SUCCEEDED` — is it extracting `final_answer` from the event payload? Creating a `WorkingAssumptionView` or `ConversationContinuity` entry?

**Finding**: The event filter is specified, but the consumer's `apply_event` behavior for `RUN_SUCCEEDED` is only implicitly described via the anti-hallucination test matrix. The plan's §4 memory view contracts define `VerifiedFactView`, `WorkingAssumptionView`, and `PinnedStateView` but don't define a `ConversationContinuityItem` struct. The implementation agent must infer: (a) what struct `RUN_SUCCEEDED` produces, (b) which fields it populates, (c) whether the `final_answer` text is stored in item_json or referenced by payload_ref.

**Recommendation**: In §4, add a `ConversationContinuityItem` typed contract (or explicitly state it uses `WorkingAssumptionView` with `claim_status=ASSUMPTION`). In §6, clarify: "`RUN_SUCCEEDED` → extract `final_answer` from payload, create `ConversationContinuityItem` with `claim_status=ASSUMPTION`, producer_kind=`ASSISTANT`, linked to the `RUN_SUCCEEDED` event refs."

---

### F3 [LOW] `required_event_sequence` computation left to agent inference

**Evidence**:
- Plan §4.5: "`required_event_sequence` 应取当前 `RUN_STARTED` / Attempt 边界之前 RunInputBuilder 需要覆盖的最大 canonical fact sequence."
- Design §23: "同一 EventLog 在同一 policy 下必须构造出等价 messages."
- Current code: `DurableSessionContinuityProvider` uses `current_facts.attempt.started_event_sequence` as the `before_event_sequence` boundary for reading continuity events (`run_input.py:479`).

**Finding**: The plan describes `required_event_sequence` conceptually but doesn't specify the concrete computation. The implementation agent needs to determine: is it `attempt.started_event_sequence - 1`? Is it the max sequence of all canonical facts in the session before this Run? The existing `started_event_sequence` in AttemptRow is the natural boundary, but the plan doesn't reference it.

**Recommendation**: Tie `required_event_sequence` to the existing durable field: "`required_event_sequence` = `current_facts.attempt.started_event_sequence - 1`，即本 Attempt 启动前最后一个已提交 canonical fact 的 sequence." Or if the intent is different, specify the exact derivation.

---

### F4 [LOW] SessionContinuityProvider budget enforcement — two valid options, no recommendation

**Evidence**:
- Plan §7 note: "若保留 `SessionContinuityProvider`，其输出必须受同一 history pool 预算约束，不能绕过 memory budget."
- Plan gives two options: converge continuity into memory history pool, or make durable memory provider reuse EventLog continuity reader with budget control.
- Current code: `DurableSessionContinuityProvider` reads raw turns from EventLog with no budget constraint (`run_input.py:462-490`).

**Finding**: Both options are architecturally valid, but the plan doesn't recommend one. The "converge into memory" option is architecturally cleaner (single budget authority) but requires more refactoring of the existing continuity path. The "budget-control existing provider" option is less invasive but creates two budget-aware components that must agree on the same history pool quota.

**Recommendation**: Recommend "converge into memory" as the primary path — it aligns with the design's single Conversation Memory authority. The existing `SessionContinuityProvider` can be simplified to only handle resume/resume-wait messages (which are not raw turns and don't compete for history pool budget), with raw turns+episode summaries moved under `MemorySnapshotProvider`.

---

### F5 [LOW] `open_questions` dual placement — in `PinnedStateView` vs separate top-level view

**Evidence**:
- Design §24 structure: `stable_layer → pinned_state`, `verified_facts`, `working_assumptions`, `open_questions`.
- Design §24 pinned_state contents: `current_goal`, `confirmed_subjects`, `user_constraints`, `open_questions`.
- Plan §4.1: `ConversationMemorySnapshot` has `pinned_state: PinnedStateView` (contains open_questions implicitly) and separate `working_assumptions: tuple[WorkingAssumptionView, ...]`.
- Plan §7 message ordering: "4. open questions / working assumptions" — groups them together.

**Finding**: Design §24 lists `open_questions` both as a sub-element of `pinned_state` and as a peer of `working_assumptions` in the stable layer structure diagram. The plan resolves this by putting `open_questions` inside `PinnedStateView`, consistent with the pinned_state content spec. However, the message ordering groups "open questions / working assumptions" together, which may confuse the implementation agent about whether `open_questions` should also appear inside `WorkingAssumptionView`.

**Recommendation**: Clarify in §4.1: "`open_questions` 仅存在于 `PinnedStateView` 中，不在 `WorkingAssumptionView` 中重复。消息排序中 'open questions / working assumptions' 是指先注入 pinned 中的 open_questions，再注入 working_assumptions。"

---

### F6 [INFO] `snapshot_digest` canonicalization algorithm not specified

**Evidence**:
- Plan §4.1: "`snapshot_digest` 必须由 canonical JSON 计算，覆盖 cursor、policy digest、四类 view 和 diagnostics 中影响 messages 的字段。不得包含非确定性字段."
- Plan §4.6: "`MemoryPolicyDigest` 必须由 policy canonical JSON 生成."
- Plan §9 anti-hallucination tests require: "同一 EventLog + 同一 policy digest 生成稳定 snapshot digest."

**Finding**: The plan requires deterministic digest computation but doesn't specify canonicalization rules (field ordering, whitespace, whether tuples are sorted, how Optional fields are represented in JSON). The implementation agent will need to define these. This is a routine implementation detail, not a design gap, but it's worth noting because digest stability is a hard requirement tested in the anti-hallucination matrix.

**Recommendation**: Not required for plan — the implementation agent can define canonicalization during Slice 1. Consider adding a note: "canonical JSON 使用 sorted keys、no trailing comma、UTF-8；Optional 字段为 null 时不参与 digest input."

---

## Design Conformance Checklist

| Requirement | Design Source | Plan Coverage | Verdict |
|---|---|---|---|
| "财报分析工作台状态投影，不是聊天记录压缩器" | design.md §24 para 1 | Plan §1 明确陈述 | PASS |
| 四类 memory view: pinned_state, verified_facts, working_assumptions, conversation_continuity | design.md §24 structure | Plan §4.1, §4.4 typed contracts | PASS |
| verified_facts 只来自工具事实，保留 provenance | design.md §24 invariants | Plan §4.3/§4.4, §9 test matrix | PASS |
| final_answer 不自动升级为 verified fact | design.md §24 invariants | Plan §9 row 1 anti-hallucination test | PASS |
| pinned/verified facts 不参与 history pool 竞争，但有尺寸上限 | design.md §24 invariants | Plan §2 goals, §4.6 policy | PASS |
| recent raw turns floor 是下限，older raw turns/episode summaries 共享 history pool | design.md §24 invariants | Plan §2 goals, §7 ordering | PASS |
| projection lag 不得触发 Run recovery / RECOVERING | design.md §24 invariants | Plan §4.8, §6 repair strategy, §9 test | PASS |
| memory snapshot 是 read model，可重建，不是事实真源 | design.md §24 invariants | Plan §1 para 1, §6 rebuild strategy | PASS |
| RunInputBuilder 消费 memory snapshot 时记录 cursor | design.md §24 invariants | Plan §4.5 cursor validation, §7 provider | PASS |
| 同一 EventLog + policy 下 messages 稳定 | design.md §23 invariants | Plan §4.6 policy digest, §9 test matrix | PASS |
| USER_INPUT_ACCEPTED 仍是当前用户 prompt 唯一事实入口 | design.md §23 | Plan §7 明确保留 CurrentRunFactProvider | PASS |
| 不实现长期 retrieval / signal ledger / verification / edit-reset-forget | design.md §26, control P9 scope | Plan §2 non-goals explicit | PASS |
| Host 不 import dayu.fins，不保存业务原文，schema 无业务语义 | design.md §24, control P9 tracking | Plan §2 non-goals, §4.3 OpaqueMemoryRef, §9 test row | PASS |
| 不修改 Engine, EventLog canonical semantics, Recovery state machine | control P9 scope | Plan §3 禁止修改列表 | PASS |
| P9 为 issue 39 预留 evidence anchor/claim/provenance/trace 边界 | control P9 tracking | Plan §2 goals, §4.2/4.3 typed contracts | PASS |

## Slice Assessment

| Slice | Scope | Stop Condition | Dependencies | Readiness |
|---|---|---|---|---|
| S1: Contracts + Schema | Typed contracts, durable tables, transaction primitives, schema bump | Empty snapshot on empty EventLog; checkpoint/snapshot in same TX | Phase 8 projection core | READY |
| S2: Projection Consumer | Consumer, stable layer builder, verified fact extraction, digest | Projection runner builds snapshot from committed EventLog; failure is projection-local | S1 contracts | READY — see F1, F2 |
| S3: RunInputBuilder Provider | DurableMemorySnapshotProvider, lag fallback, injection points | Noop tests pass; durable provider injectable; lag doesn't change Run state | S2 snapshot | READY — see F3, F4 |
| S4: Repair + Catch-up | Rebuild/repair service, after-commit hook | P9 exit condition: stable memory consumption | S3 provider | READY |
| S5: Docs + Closure | README sync, pyright, residual risks | Affected tests pass; pyright clean | S1-S4 complete | READY |

All slices have clear inputs, outputs, allowed files, test requirements, and stop conditions. No circular dependencies. Slice sequencing is correct: contracts → consumer → provider → repair → docs.

## Test Coverage Assessment

Plan §9 anti-hallucination test matrix covers 11 required tests. Mapped against design invariants and failure modes:

- **Provenance correctness**: 4 tests (final_answer not verified, user input not verified, tool facts verified with refs, episode summary not evidence anchor, rebuild preserves provenance)
- **State machine isolation**: 2 tests (lag doesn't change Run state, checkpoint ≠ truth)
- **Determinism**: 1 test (same EventLog + policy = stable digest)
- **Budget behavior**: 1 test (recent turns floor preserved under low budget)
- **Content filtering**: 2 tests (preview/reasoning not in memory, display-only facts not in memory)
- **Boundary enforcement**: 2 tests (no business fields in schema, no forbidden imports)

**Gap**: No test for "projection failure writes to `host_projection_failures` and does not affect EventLog append" — this is covered in S2 stop condition but not in the §9 matrix. It is tested in the per-slice test requirements (§8 Slice 2: "Projection failure 只写 projection-local failure row"). Acceptable.

**Gap**: No test for `SUPERSEDED` claim transition (see F1). Acceptable if F1 recommendation is adopted.

## pyright / Import Boundary Assessment

Plan §3 target files and §9 import boundary test correctly constrain:
- `dayu/host/memory.py`: must not import `dayu.fins`, `dayu.service`, `dayu.ui`, `dayu.engine`
- `dayu/host/durable/memory.py`: must not import Engine (design §24 says memory projection only consumes canonical facts via `ProjectionEventView`)
- `dayu/host/run_input.py`: allowed to use Engine message contracts (existing pattern)

This is consistent with the existing architecture: `run_input.py` already imports `AgentMessage`, `UserMessage`, etc. from Engine contracts, while `durable/` layer only touches `EventLogRow` and `ProjectionEventView`.

## Residual Risk Routing

Plan §12 routes risks correctly:
- Missing tool result summary → ToolRuntime / tool contract future work unit
- Trace projection not complete → future Audit / Tool Trace phase
- Context governance orchestration → Phase 10
- Long-term retrieval / signal → issue 39
- Public edit/reset/forget → requires design.md write-back first
- Provider-aware tokenizer → Phase 10 or later

All residual risks have named owners. No orphaned risks.

---

## Summary

- **Blocking findings**: 0
- **Medium findings**: 2 (F1 claim status lifecycle, F2 RUN_SUCCEEDED purpose)
- **Low findings**: 3 (F3 required_event_sequence, F4 continuity budget, F5 open_questions placement)
- **Info**: 1 (F6 digest canonicalization)

The plan is implementation-ready. F1 and F2 should be addressed before handing off to the implementation agent to avoid wasted effort or misinterpretation. F3-F5 are clarifications that the agent can resolve during implementation by reading the existing code. F6 is a routine implementation detail.

All design conformance checks pass. No Host business-neutrality violations. No scope creep. Slice structure is sound.
