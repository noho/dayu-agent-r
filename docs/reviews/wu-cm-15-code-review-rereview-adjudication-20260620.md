# WU-CM-15 Code Review Re-review Adjudication

## Gate

- Work unit: WU-CM-15.
- Gate: focused code-review re-review after AgentCodex fix and Controller correction.
- Base accepted plan commit: `97518e93`.
- Re-review artifacts:
  - AgentMiMo: `docs/reviews/code-review-20260620-115326.md`.
  - AgentDS: `docs/reviews/code-review-rereview-ds-20260620.md`.

## Decision

Result: PASS.

Both reviewers passed the focused re-review. The accepted code-review findings are closed:

- Reactive old marker is written into the `reactive-r1-old-seed` public prompt and the recovery dispatch oracle asserts it is absent, so the check is not empty.
- The reactive suite applies a smoke-local copied memory projection policy only for `memory-reactive-compact`, keeping the old seed outside selected recent while preserving protected recent and current input signals.
- `_deterministic_dropped_old_marker(...)` and `_assert_reactive_compact_acceptance(...)` fail closed for missing dropped marker and old-marker leakage.
- `_patched_compactor_runner(...)` now verifies patch identity and restores the original runner in `finally`.
- `_compact_pressure_reserve_tokens(...)` and the obsolete large-window helper constant are removed from this smoke script.
- The fallback suite still verifies proactive compact failure, deterministic dispatch fallback, selected / dropped / current refs, and absence of fake semantic memory sections.
- `tests/README.md` was minimally updated for the new runtime assembly coverage.

## Controller Notes

AgentDS noted that assembly tests do not drive the full Host path for old-marker exclusion. This is accepted as non-blocking because Controller reran the end-to-end deterministic reactive smoke after restoring the old marker into the r1 prompt; it passed with `requested_reactive=1`, `compacted_reactive=1`, `failed_reactive=0`, and a recovery dispatch.

AgentDS also noted that fallback helper tests do not isolate a missing `dropped_block_ids` failure branch. This is non-blocking for WU-CM-15 because the smoke-level fallback acceptance verifies non-empty `dropped_block_ids` and the helper test already covers the main proactive request, pressure, selected recent, current input, and dropped old-marker oracle. Broader negative-branch expansion can be considered with future smoke hardening.

## Controller Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Passed: `20 passed`.
  - Warnings: existing third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL`
  - Passed: observed reactive request, accepted compact, no reactive failure, and recovery dispatch.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL`
  - Passed: observed proactive compact failure, `fallback_action=dispatch`, selected / dropped refs, and final dispatch.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors`.
- `git diff --check`
  - Passed.

## Residual Risks

- Existing real-provider `memory-compact` smoke remains strict and depends on a valid compactor provider key. The prior `test-provider-key` failure is an environment/provider validation residual, not a deterministic reactive/fallback coverage blocker.
- `_patched_compactor_runner(...)` remains a smoke-local module monkey patch. The fix adds fail-fast identity checking and `finally` restore; future parallel smoke execution would need stronger isolation.
- The reactive suite now fails closed if the configured selected recent turn floor exceeds the six-round deterministic layout.
