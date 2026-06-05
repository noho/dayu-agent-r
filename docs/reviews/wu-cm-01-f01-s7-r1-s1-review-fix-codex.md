# WU-CM-01-F01-S7-R1-S1 Review Fix Codex

## Gate

- gate: review-fix
- work unit: `WU-CM-01-F01-S7-R1`
- slice: `S7-R1-S1`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- triggering reviews:
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-mimo.md`
  - `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-ds.md`
- artifact path: `docs/reviews/wu-cm-01-f01-s7-r1-s1-review-fix-codex.md`

## Accepted Findings

- DS Finding 01 / 03 accepted: focused test helper duplicated a subset of the production forbidden-fragment contract.
- DS Finding 02 accepted: `_system_envelope_overhead()` did not account for deterministic `\n` separators inserted between multiple items in the same system envelope section.

MiMo reported PASS with the same forbidden-fragment-list drift as residual risk. Controller accepts the drift and overhead issue as fix-before-acceptance items for this gate.

## Fixes

- `dayu/host/run_input.py`
  - `_non_empty_system_section_blocks()` now carries item count per rendered section block.
  - `_system_envelope_overhead()` now includes same-section item separator overhead in addition to section headers and section separators.
- `tests/host/test_run_input_builder.py`
  - `_assert_system_content_has_no_internal_refs()` now reuses `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` from production, removing the duplicated subset list.
  - Added `test_system_envelope_boundedness_allows_multiple_items_in_same_section()` to cover two unprefixed system materials in `Task Instructions`; the old overhead calculation would have rejected this legal envelope.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
  - result: `57 passed, 1 skipped in 11.89s`
- `source .venv/bin/activate && pyright`
  - result: `0 errors, 0 warnings, 0 informations`
  - note: pyright only reported an available version update warning.
- `git diff --check`
  - result: passed, no whitespace errors.

## Residual Risk

- DS Finding 04 was not accepted as a current blocker. Prefix-based routing remains a known future-proofing risk, but current material sources use module-owned prefixes and the accepted design does not require typed section carriers in this slice.
- Real provider matrix remains environment-gated and outside this deterministic production shape fix.

## Status

Review findings fixed and ready for S7-R1-S1 re-review.
