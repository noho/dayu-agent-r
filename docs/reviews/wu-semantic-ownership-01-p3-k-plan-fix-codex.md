# WU-SEMANTIC-OWNERSHIP-01 P3-K Plan Fix — AgentCodex

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-K - Test harness semantic coupling cleanup`
- Gate: `plan fix`
- Agent: `AgentCodex`
- Date: `2026-07-11`
- Fixed plan artifact: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-fix-codex.md`

## First-Principles Judgment

The accepted findings are valid plan-readiness defects, not implementation defects. The original plan had the right ownership stance, but left too many implementation-time decisions open: resume guidance assertion ownership, raw SQL helper disposition, cancellation helper state transition semantics, and README no-update reporting.

The fix keeps P3-K test-harness-only. It does not expand scope into production APIs, code changes, tests, README edits, commits, pushes, PR work, or re-review.

## Plan Sections Updated

- `S1 - Owner-Level Contract Assertions`
  - Clarified dynamic owner-derived assertions versus named production-owned resume guidance semantics.
  - Required non-vague assertion strategy for resume guidance.
  - Preferred file-local helper unless cross-file reuse justifies `tests/host/llm_text_assertions.py`.
  - Added completion signal for the resume guidance helper ownership boundary.
- `S2 - Durable Diagnostic Helper Boundary`
  - Added final disposition list for each TF-2 / same-boundary raw SQL helper.
  - Corrected the nonexistent liveness API reference to `read_host_instance(...)`.
  - Verified projection checkpoint helper names/signatures and classified `force_memory_projection_lag(...)` as fault-injection-only retention.
  - Changed completion signal from broad raw SQL reduction to exact-replaceable SQL removal only.
- `S3 - Protocol-Faithful Test Double Consolidation`
  - Defined `ControllableCancellationToken()` as open by default.
  - Required explicit `request_cancel(reason)` transition and removed constructor-as-cancelled semantics.
  - Required external `.trigger(...)` call sites to migrate away.
  - Decided `tests/service/test_fins_direct.py` should default to the canonical open token, with a narrow allowance for a clearly named non-mutable open observation stub.
  - Required a focused helper contract test for open state, UTC-aware `requested_at`, reason, and idempotent cancellation.
- `6. README / Docs Decision`
  - Added the explicit no-update branch: `tests/README.md: no update needed`.
- `7. Validation Matrix`
  - Made `ControllableCancellationToken` helper contract coverage mandatory rather than indirect/conditional.

## Accepted Finding Status

| Finding | Status | Fix summary |
|---|---|---|
| `P3-K-PF-01` | `已修复` | S1 now separates dynamic owner-derived content from production-owned guidance semantics, bans vague substring checks, and prefers file-local helpers unless reuse justifies a shared helper. |
| `P3-K-PF-02` | `已修复` | S2 now enumerates raw SQL helper dispositions, corrects `read_host_instance(...)`, verifies checkpoint helper signatures, and limits success to removing exact-replaceable SQL. |
| `P3-K-PF-03` | `已修复` | S3 now defines open default construction, explicit `request_cancel(...)`, no constructor-as-cancelled behavior, no external `.trigger(...)`, explicit Service handling, and mandatory focused helper contract tests. |
| `P3-K-PF-04` | `已修复` | README decision now includes the explicit `tests/README.md: no update needed` branch. |

## Rejected Item Handling

- The rejected `test_dispatch_scheduler.py` validation expansion remains respected. The fixed plan does not add `test_dispatch_scheduler.py` as required S3 validation.

## Validation

- Per user instruction, no tests or pyright were run because this was a plan-only fix.
- Markdown / diff sanity completed by reading the modified plan sections after patching.

## Residual Risks

- No unclassified residual risk remains in this plan-fix gate.
- Implementation may still discover code facts that require returning to plan review, but the fixed plan now names those stop conditions rather than leaving them as implementation discretion.

## Completion Status

`ready-for-plan-rereview`
