# WU-CLI-DEBUG-STREAM-01 Plan Fix

## Metadata

- Work unit: WU-CLI-DEBUG-STREAM-01
- Gate: fix for plan review
- Date: 2026-06-20
- Plan artifact: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- Plan review artifacts:
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-mimo-20260620.md`
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-ds-20260620.md`
- Adjudication artifact: `docs/reviews/plan-review-wu-cli-debug-stream-01-adjudication-20260620.md`
- Fix artifact: `docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md`

## Scope

This fix gate only updates the plan artifact and records the fix outcome. It does not enter implementation, re-review, commit, push, or PR work.

Allowed files used:

- Modified: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- Added: `docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md`

Files intentionally not changed:

- Production code
- Tests
- README files
- Control documents
- Existing plan review / adjudication artifacts

## Fix Decisions

### DS F-1 / MiMo F-1: `--debug-stream` precedence is underspecified

Status: 已修复

Plan changes:

- `Implementation Decisions` now states that `set_level_from_flags()` must resolve `debug_stream=True` to `LogLevel.STREAM_DEBUG` before any parsed `log_level` value.
- The plan explicitly defines `--debug-stream` as the most-verbose diagnostic request once it reaches runtime logging, including when other log-level flags have already populated `log_level`.
- CLI help and README planning language now says `--debug-stream` enables ordinary DEBUG plus stream diagnostics, and users should not combine mutually contradictory log-level flags.

### DS F-2: old Host logging test name becomes misleading

Status: 已修复

Plan changes:

- Slice 2 now explicitly requires renaming `tests/host/test_logging.py::test_engine_ingest_delta_events_use_debug_log_level` to a stream-debug-specific name when the expected level changes.

### DS F-3: missing combined `--debug --debug-stream` test

Status: 已修复

Plan changes:

- Slice 1 expected assertions now require parsing `--debug` together with `--debug-stream`.
- Slice 1 expected assertions now require runtime resolution coverage proving `set_level_from_flags(log_level="debug", debug_stream=True, ...)` resolves to `LogLevel.STREAM_DEBUG`.

### MiMo F-2: cleanup path lacks explicit `debug_stream` assertion

Status: 已修复

Plan changes:

- Slice 1 expected assertions now require `main(("prompt", "x", "--debug-stream"))` spy coverage for both the initial runtime logging configuration call and the cleanup reconfiguration call.
- Both calls must carry `debug_stream=True` and the parsed `log_level` value.

### DS F-4: `ParsedCliArgs` construction sites may need updates

Status: deferred-with-owner

Owner: implementation gate

Reason:

- The plan already leaves construction-site verification to implementation, where actual type-check and affected CLI tests must run.
- This fix gate must not inspect or edit production/test construction sites.

### DS F-5 / MiMo residual: README `critical` mismatch

Status: deferred-with-owner

Owner: separate cleanup work unit or explicit user decision

Reason:

- This is a pre-existing docs/parser mismatch outside Issue 148.
- The plan still instructs implementation to avoid worsening the mismatch while adding `--debug-stream` documentation.

## No-Regression Scope

`memory_repair.catch_up.budget_exhausted` remains excluded as an already-fixed bug / no-regression verification point.

The plan still treats current memory repair behavior as code fact:

- No current `BUDGET_EXHAUSTED` stop reason is expected.
- Successful memory catch-up / rebuild summary remains non-warning diagnostic behavior.
- This WU does not add a pending fix for memory repair.

## Validation

Required fix-gate validation:

```bash
git diff --check
git diff --no-index --check /dev/null docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md
```

Expected `git diff --no-index --check` behavior:

- It may return non-zero because one side is `/dev/null`.
- It must produce no whitespace-error output.

## Residual Risks

- Future stream diagnostics may still be added at ordinary DEBUG by mistake.
  Classification: covered by later approved slice. Slice 2 requires Host ingest and OpenAI stream diagnostic level tests.
- `--debug-stream` with contradictory quiet/error-only flags remains a confusing user input.
  Classification: fixed in current plan. The plan now defines precedence and requires CLI help / README wording that discourages contradictory combinations.
- Existing README `critical` mismatch remains unresolved.
  Classification: assigned to later work unit or explicit user decision.
- `ParsedCliArgs` construction-site updates are not verified in this gate.
  Classification: covered by later approved implementation gate.

## Completion Status

Plan fix gate is complete and ready for re-review. No implementation, commit, push, or PR action was performed.
