# WU-CM-12 Slice S4 Code Review Adjudication

## Scope

- Work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- Slice: S4 Tier 1-3 Compact Recovery Fallback
- Implementation artifact: `docs/reviews/wu-cm-12-s4-implementation-codex-20260618.md`
- Review artifacts:
  - `docs/reviews/code-review-wu-cm-12-s4-mimo-20260618-164733.md`
  - `docs/reviews/code-review-wu-cm-12-s4-ds-20260618-164407.md`
- Focused re-review artifacts:
  - `docs/reviews/code-review-wu-cm-12-s4-rereview-mimo-20260618.md`
  - `docs/reviews/code-review-wu-cm-12-s4-rereview-ds-20260618.md`

## Decision

S4 is accepted.

AgentMiMo found one medium diagnostic correctness issue and one low test naming issue. Both were accepted and fixed:

- Recovery accepted `CONTEXT_COMPACTED` now records `accepted_attempt_number` as the global proposal sequence for the reused operation anchor, not the per-tier result sequence.
- Cancellation-before-attempt diagnostics are not counted as completed proposal calls.
- Tier 1 / tier 2 / tier 3 accepted tests assert accepted attempt numbers `2` / `3` / `4`.
- The stale test was renamed to describe the actual `stale during tier proposal` scenario.

AgentDS review passed before the fix. Both focused re-reviews passed after the fix, with no new blocker.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q`
  - Result: `166 passed`
- `source .venv/bin/activate && pyright dayu/host/dispatch.py dayu/host/compact_material.py dayu/host/compaction.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: PASS

## README Decision

No README update is required for S4. The change is Host-internal proactive compact recovery and focused Host tests. It does not change Host public API, Engine contract, test execution instructions, user-visible CLI / UI behavior, or stable README-facing workflow.

## Residual Risk

- Reactive compaction recovery remains out of this slice. S4 closes proactive recovery before tier 4/5 dispatch fallback only.
- Recovery tier failures do not add tier-specific durable payload fields. Existing `CONTEXT_COMPACTION_FAILED` shape is preserved by design.
