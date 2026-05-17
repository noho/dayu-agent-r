# Phase 9 Plan Re-Review — DS Findings Resolution Verification

**Reviewer**: AgentDS (planreview skill, re-review)
**Date**: 2026-05-16
**Plan under review**: `docs/host/phase9-conversation-memory-plan.md` (updated)
**Prior review**: `docs/reviews/p9-plan-review-ds-20260516.md` (DS initial review, verdict PASS, 0 blocking)
**Scope**: Verify DS F1–F6 are resolved; check for new blocking issues introduced by fixes.

---

## Verdict: PASS

**Remaining blocking findings: 0**

All six DS findings (2 medium, 3 low, 1 info) are resolved. The updated plan introduces no new blocking issues. The plan is implementation-ready.

---

## Finding Resolution Evidence

### F1 [MEDIUM] — Claim status lifecycle undefined for P9 → RESOLVED

**Original**: Plan defined 6 `MemoryClaimStatus` values but didn't specify which P9 actively produces vs. reserves for issue 39.

**Fix applied**:

| Location | Change |
|---|---|
| §4.2 new paragraph | "P9 projection 主动产生的 claim status 只有两类：`TOOL_VERIFIED`（由 `TOOL_RESULT_ACCEPTED` 产生）和 `ASSUMPTION`（由用户输入、assistant conclusion / final answer、LLM patch candidate 产生）。`CANDIDATE`、`CONFLICTED`、`STALE`、`SUPERSEDED` 是为 issue 39 / 后续长期 memory 与 query-time retrieval 预留的 enum 值；P9 不主动合成。" |
| §4.2 guard clause | "只有当前 canonical fact 已显式携带 Host 中立 claim status 时，P9 才能按该中立状态投影，不得自行推断业务冲突、陈旧或替代关系。" |
| §9 new test | "P9 不合成 `CONFLICTED`、`STALE`、`SUPERSEDED` claim status。" |
| S2 test requirement | "P9 不主动产生 `CONFLICTED`、`STALE`、`SUPERSEDED`；除非 canonical fact 显式携带中立 status，否则 reserved statuses 不出现在 snapshot 中。" |

**Assessment**: The fix clearly partitions active vs. reserved statuses, adds a defensive guard clause (only project if canonical fact explicitly carries status), and adds test coverage. The implementation agent cannot misinterpret which statuses to implement.

---

### F2 [MEDIUM] — RUN_SUCCEEDED event consumption purpose underspecified → RESOLVED

**Original**: Plan listed `RUN_SUCCEEDED` in event_filter but didn't specify `apply_event` behavior — what struct it produces, which fields.

**Fix applied**:

| Location | Change |
|---|---|
| New §4.5 | Full `ConversationContinuityItem` typed contract: `item_id`, `item_kind: ConversationContinuityKind`, `producer_kind: ASSISTANT \| USER \| HOST_PROJECTION`, `claim_status: ASSUMPTION`, `event_id`, `event_sequence`, `run_id`, `summary_text`, `payload_ref`, `payload_digest`, `included_reason`, `excluded_reason`, `size_units` |
| §6 new sentence | "`RUN_SUCCEEDED` 的处理只创建 `ConversationContinuityItem` / assistant conclusion；若存在 `payload_ref` / digest，优先保留 ref；若只能读取小型 `final_answer` / summary text，也必须标记为 continuity / `ASSUMPTION`，不得进入 `verified_facts`。" |
| §9 updated test | "`RUN_SUCCEEDED` final answer 进入 `ConversationContinuityItem`，`producer_kind=ASSISTANT`，语义为 continuity / `ASSUMPTION`，不是 verified fact；大内容优先以 payload ref / digest 表达。" |
| S2 test requirement | "`RUN_SUCCEEDED` 产生 `ConversationContinuityItem`，`producer_kind=ASSISTANT`，claim status 为 `ASSUMPTION` / continuity semantics；优先保留 payload ref / digest，不复制大文本。" |

**Assessment**: The fix defines a complete typed contract for continuity items, specifies exact `apply_event` behavior for `RUN_SUCCEEDED`, and adds test coverage. The implementation agent has unambiguous guidance.

Note: `ConversationContinuityKind` enum values are not explicitly enumerated — the agent can infer reasonable values (`RAW_TURN`, `EPISODE_SUMMARY`, `ASSISTANT_CONCLUSION`) from the surrounding context. Not blocking.

---

### F3 [LOW] — required_event_sequence computation left to agent inference → RESOLVED

**Original**: Plan described `required_event_sequence` conceptually without concrete formula tied to existing durable fields.

**Fix applied**:

| Location | Change |
|---|---|
| §4.6 new formula | `required_event_sequence = current_facts.attempt.started_event_sequence - 1` |
| §4.6 new explanation | "它表示当前 Attempt 启动前 session memory 需要覆盖的最大 committed canonical fact sequence。" |
| S3 test requirement | "`required_event_sequence` 使用 `current_facts.attempt.started_event_sequence - 1`" |

**Assessment**: The fix ties computation to the existing `AttemptRow.started_event_sequence` field (already used by `DurableSessionContinuityProvider` at `run_input.py:479`). Implementation agent can directly use this formula.

---

### F4 [LOW] — SessionContinuityProvider budget enforcement, no recommendation → RESOLVED

**Original**: Plan gave two valid options (converge into memory vs. budget-control existing provider) without recommending one.

**Fix applied**:

| Location | Change |
|---|---|
| §7 new "明确接线决策" subsection | "P9 primary path 是把 historical raw turns 与 episode summaries 移入 `MemorySnapshotProvider` / history pool，由 memory policy 成为单一预算权威。" |
| §7 SessionContinuityProvider scope | "`SessionContinuityProvider` 可以保留，但只允许承载非 raw history 的 continuity / resume-specific facts，例如当前 resume wait result message；或者对 raw history 返回 no-op。" |
| §7 explicit prohibition | "`SessionContinuityProvider` 不得再注入未经过 memory history pool 预算的历史 raw user / assistant turns。" |
| S3 stop condition | "Historical raw user / assistant turns 只来自 memory history pool 或 no-op，不再从 `SessionContinuityProvider` 绕过预算进入 messages。" |
| §9 new test | "`SessionContinuityProvider` 不注入未预算 historical raw turns；raw history 由 memory history pool 统一预算。" |

**Assessment**: The fix chooses "converge into memory" as the primary path, explicitly scopes down `SessionContinuityProvider` to resume-specific facts only, and adds a hard prohibition + test. The implementation agent has a single clear path.

---

### F5 [LOW] — open_questions dual placement → RESOLVED

**Original**: Design §24 listed `open_questions` both in `pinned_state` contents and as a stable layer peer; plan message ordering grouped "open questions / working assumptions" without clarifying which view owns `open_questions`.

**Fix applied**:

| Location | Change |
|---|---|
| §4.1 new `PinnedStateView` spec | `PinnedStateView` must explicitly contain `current_goal`, `confirmed_subjects`, `user_constraints`, `open_questions` |
| §4.1 new placement rule | "`open_questions` 只存放在 `PinnedStateView`，不得在 `WorkingAssumptionView` 或其它顶层字段中重复存储。" |
| §4.1 new rendering clarification | "Memory provider messages 中的 'open questions / working assumptions' 表示先渲染 pinned state 中的 open questions，再渲染 working assumptions。" |
| S1 test requirement | "`PinnedStateView` 包含 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions`，且 open questions 不在 working assumptions 中重复存储。" |

**Assessment**: The fix establishes `PinnedStateView` as the single source of truth for `open_questions`, clarifies the rendering order, and adds a test for non-duplication.

---

### F6 [INFO] — snapshot_digest canonicalization algorithm not specified → RESOLVED

**Original**: Plan required deterministic digest but didn't specify canonicalization rules.

**Fix applied**:

| Location | Change |
|---|---|
| §4.7 new "Canonical digest 规则" subsection | "policy digest 与 snapshot digest 均使用 canonical JSON：UTF-8、sorted keys、稳定 tuple/list 顺序、确定性 `null` 处理、无非确定性 whitespace。" |
| §4.7 ordering rule | "tuple/list 顺序必须来自 EventLog sequence 或 policy 明确排序，不得按 dict iteration 或物理读取偶然顺序。" |
| §4.7 exclusion rule | "`built_at`、`updated_at`、projection 写入时间等非确定性字段不得进入 digest input。" |

**Assessment**: The fix specifies canonicalization rules sufficient for the implementation agent to produce deterministic digests. The exact JSON serialization library choice is left to the agent (standard: `json.dumps(sort_keys=True, ensure_ascii=True)`), which is appropriate.

---

## New Changes Not Required by DS Findings — Review

The updated plan includes additional improvements beyond F1-F6 fixes. All are positive; none introduce blocking issues.

| Change | Location | Assessment |
|---|---|---|
| `OpaqueMemoryRef.ref_kind` typed as `HostNeutralRefKind` enum (SOURCE, CHUNK, ENTITY, SUBJECT, TOPIC, EVIDENCE, PAYLOAD, EXTERNAL) instead of free-form `str` | §4.3 | Stronger typed contract. These are generic structural categories, not business semantics. Plan correctly adds: "不要实现脆弱的业务词 blocklist；Host 不解释 ref_kind 的财报业务语义。" PASS. |
| VerifiedFactView "实现 guidance" mapping to existing `tool_runtime` / `run_input` payload fields | §4.4 | Good implementation-level guidance. References existing code (`tool_name`, `tool_call_id`, `outcome_digest`, etc.) without introducing new dependencies. PASS. |
| `MemoryProjectionPolicy` adds `max_raw_turn_size_units`; history pool algorithm specifies single estimator helper, count-based floor, per-turn safety cap | §4.7 | Closes a budget ambiguity: without per-turn cap, a single oversized raw turn could consume the entire history pool. PASS. |
| `MemoryDiagnostic` vs `host_projection_failures`职责分离 | §5 | Explicitly distinguishes diagnostic (memory item/budget/lag decisions) from projection failure (consumer processing exceptions). Prevents category confusion. PASS. |
| After-commit hook guidance: "优先复用现有 projection notification / catch-up extension point；若现有扩展点不足，只能新增最小通用 projection catch-up extension，不得写 memory 专用旁路" | §6 | Prevents memory-specific bypass of the projection framework. Good architectural discipline. PASS. |
| New anti-hallucination tests: P9 doesn't synthesize reserved statuses; `SessionContinuityProvider` doesn't inject unbudgeted raw turns; schema/contracts contain no business fields; `OpaqueMemoryRef.ref_kind` uses Host-neutral enum | §9 | Test matrix expanded from 11 to 15 tests. All new tests trace to specific plan constraints. PASS. |

---

## Cross-Check: No New Blocking Issues

Reviewed the updated plan for regressions or new issues:

- **Host boundary**: `HostNeutralRefKind` enum values (ENTITY, SUBJECT, TOPIC) are generic structural categories, not财报-specific. Plan adds explicit test: "Host 不解释 ref_kind 的财报业务语义." PASS.
- **Import boundary**: No new imports of `dayu.fins` / `dayu.engine` in durable layer. `run_input.py` Engine message contract usage is explicit and pre-existing. PASS.
- **Scope creep**: No new goals, no long-term retrieval, no signal ledger, no edit/reset/forget API. §2 non-goals unchanged. PASS.
- **State machine isolation**: Projection lag still explicitly "不得修改 Run / Attempt 状态，不得把 Run 推入 RECOVERING." PASS.
- **Slice consistency**: S1-S5 test requirements and stop conditions updated to reflect new constraints (e.g., S1 tests `PinnedStateView` fields, S3 tests `required_event_sequence` formula, S3 stop condition includes `SessionContinuityProvider` scope reduction). All consistent. PASS.

---

## Summary

| Finding | Severity | Status |
|---|---|---|
| F1 — Claim status lifecycle | MEDIUM | RESOLVED |
| F2 — RUN_SUCCEEDED purpose | MEDIUM | RESOLVED |
| F3 — required_event_sequence | LOW | RESOLVED |
| F4 — Continuity budget recommendation | LOW | RESOLVED |
| F5 — open_questions placement | LOW | RESOLVED |
| F6 — Digest canonicalization | INFO | RESOLVED |

**Blocking findings: 0** (same as initial review; no new issues introduced)

The updated plan is implementation-ready. All six DS findings are resolved with concrete contract changes, explicit formulas, scope decisions, and corresponding test requirements. The additional improvements (HostNeutralRefKind enum, per-turn safety cap, diagnostic vs. failure separation, catch-up hook guidance) strengthen the plan without introducing new risks.
