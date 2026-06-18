# WU-CLI-ACTIVITY-01 Slice A Code Review Adjudication

## Scope

- Work unit: `WU-CLI-ACTIVITY-01`
- Gate: Slice A code review adjudication
- Implementation artifact: `docs/reviews/wu-cli-activity-01-slice-a-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/code-review-20260617-132628.md` (AgentMiMo)
  - `docs/reviews/code-review-20260617-132508.md` (AgentDS)

## Decision

Slice A implementation direction is accepted, but the code review loop must enter fix because AgentDS identified one material test coverage gap and two low-risk maintainability issues. AgentMiMo found no substantive issue.

## Finding Adjudication

| Finding | Decision | Rationale |
|---|---|---|
| DS F-1: activity projection allowlist test coverage gap | accepted | Slice A implemented multiple allowlist branches. Direct regression tests should cover context compaction, awaiting/waiting, non-terminal lifecycle, additional tool result outcomes, display fallback, descriptor degradation, and bounded summary boundaries before slice closeout. |
| DS F-2: `_tool_display_name` locally instantiates `EventLogStore()` | accepted | Current behavior is correct, but read API already uses explicit store objects elsewhere. Passing/reusing a store or module-level private store makes ownership clearer and avoids future constructor drift. |
| DS F-3: redundant `_public_event_class_from_durable` call in `_activity_from_row` | accepted | The extra validation call is redundant because `_host_event_from_row` already maps the row identity. Remove it or refactor so the validation happens once. |

## Required Fix

AgentCodex must:

1. Add focused tests to `tests/host/test_host_activity_event_projection.py` for:
   - `TOOL_RESULT_ACCEPTED` completed and cancelled outcomes.
   - `TOOL_AWAITING` and `RUN_WAITING` activity projection.
   - context compaction requested / compacted / failed / attempt rejected activity projection.
   - non-terminal lifecycle events such as `RUN_ACCEPTED` / `RUN_STARTED`.
   - display fallback chain for missing run/input/payload/display mapping.
   - activity descriptor read degradation and bounded summary boundaries.
2. Replace `_tool_display_name` local `EventLogStore()` construction with a clearer dependency shape, without widening public API or adding stateful globals.
3. Remove the redundant event class validation call in `_activity_from_row` or otherwise make the single validation point explicit.
4. Re-run affected host tests, pyright, and `git diff --check`.
5. Write a fix artifact under `docs/reviews/`.

## Next Gate

Proceed to fix by AgentCodex, then code re-review.
