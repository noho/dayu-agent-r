# WU-CLI-DEBUG-STREAM-01 Plan Review Adjudication

## Metadata

- Work unit: WU-CLI-DEBUG-STREAM-01
- Gate: plan review adjudication
- Date: 2026-06-20
- Plan artifact: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-mimo-20260620.md`
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-ds-20260620.md`

## Overall Decision

Plan review is `PASS_WITH_FINDINGS`. The plan is directionally valid, but it must be fixed before re-review. The fix must clarify the `--debug-stream` precedence rule and tighten the test expectations named by both reviewers.

## Finding Decisions

| Finding | Decision | Required action |
|---|---|---|
| DS F-1 / MiMo F-1: `--debug-stream` precedence is underspecified | accepted | Revise the plan so the precedence rule is explicit and implementation-ready. The adjudicated behavior is: if `debug_stream=True` reaches runtime logging, it resolves to `STREAM_DEBUG` before any parsed `log_level` value. This makes `--debug-stream` an explicit most-verbose diagnostic request and satisfies Issue 148's requirement that it can be combined with `--debug`. CLI help / README must say `--debug-stream` enables ordinary DEBUG plus stream diagnostics; users should not combine contradictory log-level flags. |
| DS F-2: old Host logging test name becomes misleading | accepted | Revise Slice 2 to require renaming `test_engine_ingest_delta_events_use_debug_log_level` to a stream-debug-specific name when implementation changes the expected level. |
| DS F-3: missing combined `--debug --debug-stream` test | accepted | Revise Slice 1 expected assertions to require a combined parsing / runtime resolution test for `--debug` with `--debug-stream`. |
| MiMo F-2: cleanup path lacks explicit `debug_stream` assertion | accepted | Revise Slice 1 expected assertions to require both initial and cleanup `set_level_from_flags(...)` calls to carry the `debug_stream` value. |
| DS F-4: `ParsedCliArgs` construction sites may need updates | deferred-with-owner | Owner is implementation gate. The existing plan already requires checking manual `ParsedCliArgs` construction; implementation must run pyright and affected CLI tests. |
| DS F-5 / MiMo residual: README `critical` mismatch | deferred-with-owner | This is a pre-existing docs/parser mismatch outside Issue 148. Implementation must avoid worsening it; a separate cleanup work unit or user decision owns any direct fix. |

## Rationale

The custom `STREAM_DEBUG` level remains acceptable: it is smaller and more maintainable than message-based filters or module-specific logger overrides, and it follows the existing `VERBOSE=15` pattern in `dayu.runtime.log`.

The precedence rule is the only plan-level ambiguity. The chosen rule deliberately makes `--debug-stream` the strongest diagnostic request because the flag exists to unlock records below ordinary DEBUG. Preserving `--quiet` as stronger would require either source-aware argparse tracking or a different flag model; neither is needed for Issue 148. The user-facing docs should instead describe the intended non-contradictory usage.

`memory_repair.catch_up.budget_exhausted` remains excluded from implementation scope. Current code no longer has that stop reason, and memory repair warnings remain reserved for real failures.

## Residual Risks

- Future stream diagnostics may still be added at ordinary DEBUG. Implementation tests must pin the current Host ingest and OpenAI stream diagnostics levels.
- The `--debug-stream` versus contradictory quiet/log-level combinations are not a new product workflow. Documentation should describe normal usage without expanding this WU into a full logging policy redesign.
