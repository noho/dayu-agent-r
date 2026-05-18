# Phase 10 Plan Review — AgentDS

**Artifact**: `docs/reviews/phase10-plan-review-ds-20260518.md`
**Reviewer**: AgentDS
**Plan Under Review**: `docs/host/phase10-context-governance-plan.md`
**Date**: 2026-05-18
**Method**: Adversarial independent review against design, implementation-control, and code evidence.

---

## Verdict: PASS

The plan is implementation-ready. Six well-scoped slices with explicit allowed files, data flows, state transitions, tests, and stop conditions. An implementation agent can follow slice-by-slice without re-deriving architecture. The `RunStatus.ACCEPTED` pre-start gate is necessary, consistent with the design state matrix, and the only correct way to satisfy "proactive compact failure must not create Attempt."

Below are findings organized by severity, each with evidence citations to design/plan/code.

---

## Findings

### Blocking: 0

No blocking findings.

---

### High: 3

#### H1. Pre-start governance orchestration wakeup mechanism not specified

- **Plan reference**: Slice 4, "Add pre-start governance worker/path in Host dispatch/admission orchestration" (plan:328-331).
- **Evidence**: Current admission flow (`dayu/host/admission.py:1791-1817`) calls `create_running_run_with_starting_attempt_in_transaction` in a single transaction that creates `RUNNING` status, `ATTEMPT_STARTED`, and `pending` dispatch record. The scheduler loop in `dispatch.py` polls `dispatch_record.status = 'pending'`. After P10, an `ACCEPTED` Run has no Attempt and no dispatch record — nothing in the current scheduler picks it up.
- **Why it matters**: The implementation agent needs to decide: (a) inline governance check in the same admission transaction, (b) a new background governance task/poll, (c) extending the scheduler to handle ACCEPTED runs. Each has different transaction boundaries and concurrency implications. Without this decision, Slice 4 has an ambiguous handoff between admission and governance.
- **Mitigation**: The plan provides enough semantics (state transitions, data flow, stop conditions) that an experienced agent can choose correctly. The test requirements (Slice 4 tests line 353-359) implicitly constrain the implementation — e.g., "proactive soft threshold triggers one compact before any Attempt row exists" forces the governance check to happen after admission commits `ACCEPTED` but before `RUN_STARTED`.
- **Recommendation**: Implementation agent should document the chosen wakeup mechanism in the first Slice 4 commit, referencing this finding.

#### H2. ACCEPTED state interaction with ATTACH_ACTIVE admission policy not addressed

- **Plan reference**: Slice 4 state transitions (plan:347-351) cover proactive accepted/failed, but only when "no active Run exists."
- **Evidence**: `dayu/host/admission.py:791-818` handles `_handle_active_run` with `REJECT` and `ATTACH_ACTIVE` policies. The plan says `accepted` is pre-active and excluded from the active-run unique index (plan:166). But what happens when a `start_run` arrives and an `ACCEPTED` Run exists? Is `ACCEPTED` considered "active" for admission purposes?
- **Design reference**: `docs/host/design.md:546` — "At most one Run per Session can be in active lifecycle: `RUNNING` or `WAITING`." The design doesn't define `ACCEPTED` as active.
- **Why it matters**: If ACCEPTED is pre-active, another `start_run` with ATTACH_ACTIVE policy should not attach to an ACCEPTED Run (no Attempt to attach to). It should either queue or reject. But if a governance worker is processing the ACCEPTED Run concurrently, there's a race between the new `start_run` admission and the governance worker's transition. The plan's "single-start arbitration" constraint (plan:167) covers this but the admission code path needs explicit handling.
- **Recommendation**: Implementation agent should add a test case: `start_run` with ATTACH_ACTIVE when an ACCEPTED Run exists. The expected behavior should be explicitly documented before Slice 4 implementation.

#### H3. `submit_followup(queue)` promotion path transitions unspecified in proactive governance

- **Plan reference**: Slice 4, "Promotion from QUEUED should also go through the same proactive governance gate before RUN_STARTED / ATTEMPT_STARTED" (plan:168).
- **Evidence**: Current `PromoteNextQueuedRunOperation` (`dayu/host/admission.py:898-949`) directly calls `promote_queued_run_in_transaction` which appends `RUN_STARTED(start_reason=queue_promotion)` + `ATTEMPT_STARTED` + dispatch record in one transaction (`dayu/host/durable/run_transition.py:758`). The plan says this must go through governance, but doesn't say whether promotion: (a) transitions QUEUED -> ACCEPTED first, then governance -> RUNNING, or (b) governance evaluates QUEUED Run in-place and either promotes to RUNNING (with compact if needed) or fails.
- **Why it matters**: This is a material state machine decision. Option (a) adds an extra state transition and changes `RunStartReason` semantics. Option (b) keeps promotion as a single operation but adds governance inside it. The plan's test requirement "Existing queued promotion still preserves FIFO and active-run uniqueness" (plan:358) suggests option (b) is intended, but the implementation agent needs clarity.
- **Recommendation**: Controller should confirm the promotion path before Slice 4. The simplest approach consistent with the plan: promotion evaluates budget on the QUEUED Run's facts, compacts if needed, then appends events in sequence — without a separate ACCEPTED state for promotion.

---

### Medium: 5

#### M1. `RunStartReason.RECOVERY` not present in current codebase

- **Plan reference**: Slice 5, "Add RunStartReason.RECOVERY if not present" (plan:179).
- **Evidence**: `dayu/host/durable/state.py:114-119` defines only `INITIAL`, `QUEUE_PROMOTION`, `RESUME`. The design (`docs/host/design.md:579`) includes `recovery` in the first-edition enum. The plan correctly identifies this gap but says "if not present" — it is definitely not present, so this is not a conditional.
- **Impact**: Low risk — adding an enum member is straightforward. But tests that enumerate all `RunStartReason` values will need updating.
- **Recommendation**: Change "if not present" to definitive language in implementation.

#### M2. `RunStartReason.STEER` not addressed

- **Plan reference**: Non-goals, not mentioned.
- **Evidence**: Design `docs/host/design.md:579` includes `steer` in the first-edition enum. Current code only has 3 values. The plan doesn't add `STEER` (correct — out of P10 scope), but the implementation agent touching `RunStartReason` in Slice 5 might be confused about whether to add it proactively.
- **Impact**: Low. The plan's stop condition for Slice 5 (plan:413) focuses on attempt identity, not enum completeness. But if the implementation agent adds RECOVERY but not STEER, the enum will remain incomplete against the design spec.
- **Recommendation**: Explicitly note in Slice 5: "Only add RECOVERY. STEER belongs to the steer phase owner."

#### M3. Schema CHECK constraint change requires migration awareness

- **Plan reference**: Slice 4, "Add RunStatus.ACCEPTED to host_runs.status schema check in dayu/host/durable/schema.py" (plan:162).
- **Evidence**: `dayu/host/durable/schema.py:301-312` has a CHECK constraint listing all valid statuses. Adding `'accepted'` requires a DDL change. The project's CLAUDE.md says "schema 变更时一律按全新 schema 起库处理；禁止旧库兼容读取、兼容测试."
- **Impact**: Medium — any test database created before this change will fail with the new CHECK constraint. Tests using `open_host_durable_store` with `tmp_path` (fresh DB per test) are fine. But any persistent test DB or manual testing DB needs recreation.
- **Recommendation**: Document in Slice 4 that fresh DB creation is required. This aligns with the project's "全新 schema 起库" policy.

#### M4. `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED` removal scope unclear

- **Plan reference**: Slice 3, "Remove or update tests that seed EPISODE_SUMMARY_ACCEPTED as canonical compact truth" (plan:284).
- **Evidence**: `dayu/host/durable/memory.py:73` defines `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED` and includes it in `_EVENT_TYPE_FILTER`. `dayu/host/memory.py:1049` handles it in `project_conversation_memory_event`. The plan says to replace consumption with `CONTEXT_COMPACTED`, but doesn't say whether to remove `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED` from the filter tuple entirely or leave it for other consumers.
- **Impact**: Medium — if the constant and filter entry are removed, any other code or test referencing `EPISODE_SUMMARY_ACCEPTED` will break. Grepping shows no other consumers beyond memory projection, so removal should be safe.
- **Recommendation**: Implementation agent should verify no other consumers before removing the constant.

#### M5. `DurableCompactArtifactProvider` message rendering semantics under-specified

- **Plan reference**: Slice 4, "Renders bounded system messages describing compact artifact ref/digest and accepted summary navigation only when needed" (plan:337-338).
- **Evidence**: `CompactArtifactView` (`dayu/host/run_input.py` around line 338 protocol) returns a tuple of messages. The plan says the durable provider should render "bounded system messages." The existing message order in RunInputBuilder is: scene -> memory -> compact -> continuity -> current prompt (plan:1209). Compact messages sit between memory and continuity — what exactly should these messages contain? Are they navigation hints? Full summaries? Ref pointers?
- **Why it matters**: The compact provider's output determines what the LLM sees about prior episode summaries. If too verbose, it competes with the current prompt. If too sparse, the model loses navigation context.
- **Recommendation**: Slice 4 should include a concrete message format specification or reference `CompactArtifactView` field semantics.

---

### Low: 4

#### L1. Conservative estimator coefficient constants not specified

- **Plan reference**: Slice 1, "所有系数必须是命名 policy 常量" (plan:92).
- **Evidence**: The plan defers specific char-to-token ratios to implementation, only requiring they be named constants. This is acceptable for a conservative first edition.
- **Recommendation**: Implementation should define constants like `CONSERVATIVE_CHARS_PER_TOKEN = 4` and `FIXED_PER_MESSAGE_OVERHEAD_TOKENS = 3` with explicit justification comments.

#### L2. Orphan artifact file cleanup not addressed

- **Plan reference**: Residual Risks, "crash between artifact file write and DB event append can leave orphan artifact files" (plan:512).
- **Evidence**: Plan correctly defers cleanup to Phase 11. The artifact write-then-DB-commit order (plan:130) means a crash after file write but before DB commit leaves an orphan file.
- **Impact**: Low for P10 — orphan files are cold residues, not truth. Artifact read path should validate digest and ignore unmatched files.
- **Recommendation**: Add a diagnostic log message when encountering orphan artifact files, as preparation for Phase 11.

#### L3. `CONTEXT_COMPACTION_FAILED` not consumed by memory projection

- **Plan reference**: Slice 3 only specifies `CONTEXT_COMPACTED` in memory projection consumption (plan:279-283).
- **Evidence**: This is correct — failed compactions produce no summary/patch to materialize. But the plan doesn't explicitly state this as a non-goal for Slice 3.
- **Recommendation**: Explicitly note in Slice 3: "CONTEXT_COMPACTION_FAILED is NOT consumed by memory projection."

#### L4. `FakeContextCompactor` placement ambiguity

- **Plan reference**: Slice 2, "推荐 production 放 dayu/host/fake_compaction.py" (plan:111).
- **Evidence**: The plan recommends this location but says "tests use fake compactor." The CLAUDE.md says "测试辅助代码仅放在 utils/" but also says `utils/` is for "分析辅助代码." A fake compactor used only in tests could go in `tests/host/` as a test helper, or in production as recommended. The plan's recommendation is reasonable.
- **Recommendation**: If placed in production, ensure `fake_compaction.py` has a module docstring stating "仅用于测试与本地开发，不得用于生产路径."

---

### Info: 3

#### I1. Plan correctly identifies all P10 non-goals

The non-goals section (plan:24-33) is comprehensive and correctly excludes: provider tokenizer adapter, long-term retrieval, public memory edit API, Phase 11 recovery, Phase 13 sinks, Engine proactive compaction, direct memory writes, metadata-based budget reading, old event type compatibility, and provider overflow as budget truth.

#### I2. P9/P10 boundary is correctly maintained

The plan consistently routes compact output through `EventLog -> ConversationMemoryProjectionConsumer -> project_conversation_memory_event -> memory snapshot -> DurableMemorySnapshotProvider -> RunInputBuilder`. This preserves the EventLog-as-truth, memory-as-read-model architecture required by `docs/host/design.md:51-52`.

#### I3. Slice dependency ordering is sound

Slice 1 (budget policy/estimator) -> Slice 2 (compactor contracts/artifact store) -> Slice 3 (canonical events + P9 consumption) -> Slice 4 (proactive orchestration) -> Slice 5 (reactive recovery) -> Slice 6 (production wiring). Each slice produces stable contracts consumed by later slices. Slices 1-2 could potentially be parallelized since they have no mutual dependencies (Slice 2's contracts don't depend on budget policy types).

---

## Residual Risks and Assumptions

1. **Multi-turn session body closure assumes all 6 slices complete**. After Slice 3, memory projection consumes CONTEXT_COMPACTED but nothing produces it. After Slice 4, proactive path works but reactive doesn't. Only after Slice 6 is the full multi-turn session body workable. This is inherent to the phase structure, not a plan defect.

2. **Real LLM compactor adapter not in scope**. The plan uses fake compactor for governance validation. Production wiring needs a real LLM compactor that calls a model with a compaction scene. The plan's `ContextCompactor` Protocol is the correct boundary — the real adapter can be injected later without changing governance logic. Risk: if the fake compactor's episode summary format doesn't match what a real LLM produces, quality check may have false positives/negatives. Mitigation: quality check is Host-side and deterministic, not LLM-dependent.

3. **Active-run unique index semantics**. The plan correctly excludes `accepted` from the active-run index (plan:166). The current `_HOST_RUNS_QUEUE_FIFO_INDEX_DDL` (`schema.py:806-809`) is `WHERE status = 'queued'` — no change needed for ACCEPTED. But verify that the one-active-per-session index is implemented as a partial index, not a full-table constraint.

4. **Conservative estimator may over-trigger compaction**. The plan acknowledges this (plan:513) and correctly prioritizes safety over precision. Provider-specific tokenizer adapter is deferred.

5. **Test database recreation required**. Adding `'accepted'` to the schema CHECK constraint means any existing test databases need recreation. This is expected per the project's schema policy.

---

## Verification Summary

| Criterion | Status |
|---|---|
| Plan references design evidence | PASS — cites design §13.3, §23, §24, §25, §25.1 with line-specific references |
| Plan references code evidence | PASS — cites specific file:line for all claims |
| Slices have allowed files/modules | PASS — each slice lists exact files |
| Slices have stop conditions | PASS — each slice has explicit stop condition |
| Tests specified per slice | PASS — exact test files and assertion categories listed |
| P9/P10 boundary preserved | PASS — Context Governance never writes memory directly |
| Budget truth source correct | PASS — Host policy, not Engine/metadata/provider overflow |
| old event type cleanup explicit | PASS — EPISODE_SUMMARY_ACCEPTED replaced by CONTEXT_COMPACTED |
| Usage as observation only | PASS — no dynamic threshold update from usage |
| Proactive failure no Attempt | PASS — enforced via ACCEPTED state |
| Reactive failure no LOST | PASS — enforced via stop condition |
| Verified facts only TOOL_RESULT_ACCEPTED | PASS — enforced in Slice 3 tests |
| Multi-turn session body data sources clear | PASS — stable layer / history pool owners documented |

---

## Conclusion

The Phase 10 implementation-ready handoff plan is **PASS** with 0 blocking, 3 high, 5 medium, 4 low, and 3 info findings. All high findings concern orchestration mechanism specification that an experienced implementation agent can resolve by following the plan's state transition and test constraints. No finding requires plan restructuring.

Implementation agent should address H1-H3 with the controller before or during Slice 4, and reference M1-M5 in implementation decisions.
