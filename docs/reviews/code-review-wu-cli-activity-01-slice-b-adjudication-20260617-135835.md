# WU-CLI-ACTIVITY-01 Slice B Code Review Adjudication

## Scope

- Work unit: `WU-CLI-ACTIVITY-01`
- Gate: Slice B code review adjudication
- Implementation artifact: `docs/reviews/wu-cli-activity-01-slice-b-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/code-review-20260617-135557.md` (AgentMiMo)
  - `docs/reviews/code-review-20260617-135353.md` (AgentDS)

## Decision

Slice B implementation direction is accepted. Enter fix for two small issues before slice commit.

## Finding Adjudication

| Finding | Decision | Rationale |
|---|---|---|
| DS F-1: `_terminal_result_from_live_event` shares terminal dedupe set with non-terminal events | accepted | Even if Host should keep dedupe keys unique, terminal observation should not let a non-terminal event suppress a terminal result. Fix by ensuring terminal dedupe key state is only written for terminal events, or by using separate domains. |
| DS F-2: `cancel_entrypoint_run_and_wait` lacks `on_activity` | deferred-with-owner | Current Slice B scope only covers submit wait activity. Cancel-running activity belongs to approved Slice E interactive running activity / cancel integration. |
| DS F-3: activity callback exception propagation untested | accepted | Behavior is intentional and consistent with `on_run_accepted`; add a focused test so future renderer integration does not accidentally swallow or mask callback exceptions. |

## Required Fix

AgentCodex must:

1. Prevent non-terminal activity/progress events from populating terminal dedupe key state in `_terminal_result_from_live_event`, or otherwise separate terminal and non-terminal dedupe domains.
2. Add regression test proving a non-terminal event and later terminal event with the same dedupe key still returns the terminal result.
3. Add test proving `on_activity` callback exceptions propagate as designed.
4. Re-run Service tests, pyright, and `git diff --check`.
5. Write/update a Slice B fix artifact.

## Next Gate

Proceed to fix by AgentCodex, then code re-review.
