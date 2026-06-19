# WU-CM-13 Plan Review Adjudication

## Metadata

- Date: 2026-06-19
- Work unit: WU-CM-13 Unified Conversation Compact Pipeline Convergence
- Plan artifact: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- Initial plan reviews:
  - `docs/reviews/plan-review-20260619-194515.md`
  - `docs/reviews/plan-review-20260619-194657.md`
- Focused plan re-reviews:
  - `docs/reviews/plan-review-20260619-195507.md`
  - `docs/reviews/plan-review-20260619-195521.md`
  - `docs/reviews/plan-review-20260619-200133.md`
  - `docs/reviews/plan-review-20260619-200143.md`
- Verdict: PASS after plan fixes and focused re-review

## Controller Adjudication

The initial WU-CM-13 plan correctly identified the root cause but was not code-generation-ready. Controller accepted the plan review findings requiring concrete helper contracts, a thinner shared owner, caller-owned lifecycle guards, explicit tier 5 scope exclusion, a settled WU-CM-14 provider strategy, split render handoffs, fallback ownership boundaries, `compaction_evidence.py` migration mapping, and Session Semantic Memory equivalence criteria.

AgentCodex fixed the plan. AgentMiMo and AgentDS focused re-review confirmed the first fix pass, with four remaining clarification findings. Controller accepted those clarifications. AgentCodex fixed them, and the final focused re-review returned PASS from both reviewers.

## Finding Adjudication

| Finding | Source | Severity | Controller verdict | Re-review status |
|---|---|---:|---|---|
| Plan lacked concrete typed contracts and function signatures | Initial reviews | CRITICAL / HIGH | accepted | closed |
| Proposed `compact_pipeline.py` was too broad / over-engineered | Initial reviews | HIGH | accepted | closed |
| Commit guard semantics leaked lifecycle into shared helper | Initial reviews | HIGH / MEDIUM | accepted | closed |
| Tier 5 current-input-only fallback scope was unresolved | Initial reviews | HIGH | accepted; out of WU-CM-13 scope | closed |
| WU-CM-14 provider migration choice was unresolved | Initial reviews | HIGH / MEDIUM | accepted; pipeline-owned audited second-read provider selected | closed |
| Render handoff risked becoming a god bag | Initial reviews | MEDIUM | accepted; ordinary raw-tail and fallback handoffs split | closed |
| Fallback action ownership was overclaimed | Initial reviews | MEDIUM | accepted; shared helper owns selection / payload input / action hint only | closed |
| `compaction_evidence.py` migration lacked test mapping | Initial reviews | MEDIUM / LOW | accepted | closed |
| Session Semantic Memory equivalence was undefined | Initial reviews | LOW | accepted | closed |
| Missing source snapshot constructor signature | Focused re-review N1 | MEDIUM | accepted | closed |
| `policy_digest` semantics inconsistent | Focused re-review N2 | LOW | accepted | closed |
| fallback selected-material handoff consumption unclear | Focused re-review N3 | LOW | accepted | closed |
| tier recovery builder dependency on `build_compact_material_pack(...)` unclear | Focused re-review N4 | LOW | accepted | closed |

## Accepted Plan Constraints

- `dayu/host/compact_pipeline.py` must be a thin Host-internal helper owner, not a lifecycle coordinator.
- Proactive / reactive outer lifecycle, EventLog append, artifact write, Run / Attempt status transitions, and recovery Attempt creation stay in `dispatch.py` / `engine_ingest.py`.
- WU-CM-13 does not implement tier 5 current-input-only fallback and does not add `fallback_tier` payload fields.
- WU-CM-14 protected recent raw tail uses a pipeline-owned audited second-read provider / helper. It may still re-read EventLog, but selection eligibility must be owned by shared helper logic.
- `compaction_evidence.py` must not remain as a shadow material owner with only test callers.
- Final acceptance requires the real `utils/smoke_host_public_conversation_memory_scenarios.py` to pass without modifying or weakening the smoke.

## Final Verdict

PASS. WU-CM-13 may proceed to accepted plan commit and implementation gate.
