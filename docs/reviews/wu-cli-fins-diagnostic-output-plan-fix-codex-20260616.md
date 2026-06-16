# WU-CLI-FINS-DIAG-01 Plan Fix — Codex

## Fix Metadata

- Target plan: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- Review inputs:
  - `docs/reviews/wu-cli-fins-diagnostic-output-plan-review-ds-20260616.md`
  - `docs/reviews/plan-review-20260616-150120.md`
- Gate: plan fix
- Date: 2026-06-16

## Accepted Items

- Accepted DS F1: promoted prompt/interactive stdout cleanliness from recommended regression to required validation. Updated Slice 1 validation and Aggregate Validation to require `tests/cli/test_prompt_command.py` and `tests/cli/test_interactive_command.py`, with explicit `--verbose`/`--debug` assertions that stdout does not contain `[VERBOSE]` or `[DEBUG]`.
- Accepted DS F2 / MiMo F04: added Slice 2 contract-boundary text explaining that `FinsEvent` validation already rejects absolute paths, `output.py` path redaction is presentation-layer redundancy, `direct_events.py` must not be modified, and future non-`FinsEvent` reuse of `_safe_text_value` requires re-evaluation.
- Accepted DS F3 / MiMo F02: added the runtime log production-caller audit to Implementation Decisions and Residual Risks. The plan now states the only current production path is CLI `main()` -> `set_level_from_flags()` -> `configure()`, with no Host/Service/Engine production caller, while keeping explicit `stream` override.
- Accepted MiMo F01: revised the R3/R5 grouping rationale to say the slices are grouped under one output policy to reduce coordination and test-update cost, not because of strict technical coupling.
- Accepted marker rename suggestion: made Slice 1 require renaming `_HANDLER_MARKER_VALUE` to a stream-neutral private value such as `dayu.runtime.log:diagnostic`.

## Rejected Items

- Rejected MiMo F03 per Controller裁决: the plan does not add `args.debug`, `args.verbose` or `args.quiet` forwarding. `arg_parsing.py` already normalizes these flags into `args.log_level`, and `main.py` already passes `log_level=args.log_level`; the boolean parameters on `set_level_from_flags` are legacy runtime-helper paths outside this work unit.

## Modified Locations

- `docs/host/wu-cli-fins-diagnostic-output-plan.md`
  - First-Principles Judgment: R3/R5 grouping rationale.
  - Implementation Decisions: runtime log caller audit, stream override policy, marker rename, and rejected boolean forwarding note.
  - Slice 1: required prompt/interactive stdout cleanliness tests and refined stop condition.
  - Slice 2: `FinsEvent` contract versus `output.py` presentation redundancy boundary.
  - Aggregate Validation: prompt/interactive tests moved into minimum required validation with explicit stdout-clean assertions.
  - Residual Risks: updated runtime-log caller audit language.

## Verification

- Documentation-only change. No production code, tests, commit or push performed.
