# WU-CM-01-F01-S7-R1-S1 Re-Review Controller Adjudication

## Gate

- gate: re-review adjudication
- work unit: `WU-CM-01-F01-S7-R1`
- slice: `S7-R1-S1`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- implementation artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s1-implementation-codex.md`
- review artifacts:
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-mimo.md`
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-ds.md`
- fix artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s1-review-fix-codex.md`
- re-review artifacts:
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-mimo.md`
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-ds.md`
- adjudication artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-controller-adjudication.md`

## Findings Adjudication

- MiMo initial review: PASS, with residual risk that focused tests duplicated a smaller forbidden-fragment list than production.
- DS initial review: PASS with required fix findings:
  - Finding 01 / 03: accepted. Focused tests duplicated a true subset of the production forbidden-fragment contract.
  - Finding 02: accepted. Same-section item separators were missing from deterministic boundedness overhead.
  - Finding 04: not accepted as a current blocker. Prefix-based routing remains a future-proofing risk, but the accepted design and current module-owned material prefixes do not require a typed section carrier in this slice.
- Codex review fix:
  - focused test helper now reuses `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`;
  - `_system_envelope_overhead()` now includes same-section item separator overhead;
  - `test_system_envelope_boundedness_allows_multiple_items_in_same_section()` covers the latent boundedness failure.
- MiMo re-review: PASS.
- DS re-review: PASS.

## Controller Verdict

PASS. S7-R1-S1 is accepted for the one-system-message production assembly gate.

The accepted fix preserves the core contract:

- ordinary public `AgentRunRequest.messages` has at most one `system` message, and that message is first when present;
- non-system user / assistant continuity roles remain unchanged;
- `RUNNER_CALL_INPUT_ASSEMBLED` manifest records normalized final messages;
- LLM-facing system envelope avoids internal governance identifiers;
- boundedness sanity accounts for deterministic headers, section separators, and same-section item separators.

## Validation

- Controller validation:
  - `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
  - result after fix: `57 passed, 1 skipped`
- Controller validation:
  - `source .venv/bin/activate && pyright`
  - result: `0 errors, 0 warnings, 0 informations`
- Controller validation:
  - `git diff --check`
  - result: passed
- Re-review validation:
  - MiMo reran the focused pytest, pyright, and diff check.
  - DS reran the focused pytest, pyright, diff check, and manually checked the Finding 02 boundedness calculation.

## Residual Risk

- Real provider matrix remains environment-gated and was not required for this deterministic production shape gate.
- Prefix-based section routing remains a future-proofing risk if future material sources introduce conflicting prefixes. It is not a blocker for the current accepted design.

## Status

Accepted. Proceed to final Slice 7 public-path validation and closeout.
