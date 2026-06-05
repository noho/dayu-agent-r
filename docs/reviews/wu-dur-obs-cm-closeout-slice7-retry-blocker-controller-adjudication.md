# Controller Adjudication — WU-CM-01-F01 Slice 7 Retry Blocker

## Scope

- Work unit: `WU-CM-01-F01`
- Slice: Slice 7 public smoke correctness closeout
- Gate: implementation retry blocker review
- Implementation retry artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice7-implementation-retry-codex.md`
- DS review artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice7-retry-blocker-review-ds.md`
- MiMo review status: pane review produced a PASS/blocker-valid oral verdict but did not persist the requested artifact before timeout; captured verdict is recorded in this adjudication.

## Verdict

Blocker accepted.

Slice 7 retry correctly added focused public smoke assertions and then stopped when those assertions exposed production public-path multi-system-message behavior outside Slice 7 allowed files. The failure is not a test-private artifact: the assertions read `AgentRunRequest.messages` and scripted runner `messages_seen` captured from the public `open_host()` / `submit_followup()` path.

## Accepted Findings

### 1. Production RunInput still emits multiple system messages on ordinary public runner calls

- Severity: blocking
- Evidence:
  - `tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity` fails with `roles=('system', 'user', 'system', 'assistant', 'user')`.
  - `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` fails with `roles=('system', 'system', 'system', 'user', 'system', 'assistant', 'system', 'user')`.
  - DS review traced the source to production `dayu/host/run_input.py` message assembly: system prompt, Host execution context, memory sections, and compact artifact can each enter the final request as independent `SystemMessage` values.
- Decision:
  - This is outside Slice 7 allowed files.
  - It requires a production RunInput / memory projection shape rescope before WU-CM-01-F01 can pass final public smoke closeout.

### 2. Compact material / manifest assertions are acceptable, with one low-risk future false-positive note

- Severity: low residual observation
- Evidence:
  - `_assert_runner_call_manifest_messages()` verifies `message_count`, `message_entries`, role order, and `role_sequence_digest` from the final manifest.
  - `_assert_compactor_material_instruction_contract()` verifies the accepted S6-R1 instruction literal and rejects internal compact type names / Host bookkeeping terms in material JSON.
  - DS and MiMo both noted that broad forbidden prompt terms such as `policy` / `digest` may be overbroad for future prompt wording.
- Decision:
  - No blocker for the current retry.
  - If a future prompt needs ordinary-language `policy` or `digest`, narrow the forbidden terms to internal forms instead of weakening the LLM-facing rule.

## Controller Rationale

The blocker motivation is valid and not overestimated. Multiple system messages are not inherently illegal for every provider, but this work unit's accepted success signal is stricter: public smoke should prove the LLM-facing runner-call shape has at most one system message to reduce provider-compatible ambiguity. If that requirement is later rejected as too strict, the design source and control plan must be updated first; it cannot be silently bypassed in Slice 7 tests.

Therefore, the correct next step is not to weaken the new assertions. The next step is a production rescope that decides and implements the single-system-message assembly contract in `RunInputBuilder` / memory projection, while preserving the business-readable content and bounded memory semantics.

## Validation Considered

Controller re-ran:

```bash
source .venv/bin/activate && pytest tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
source .venv/bin/activate && pyright
git diff --check
```

Results:

- Targeted pytest: `4 failed, 9 passed, 1 skipped`; the four failures are the accepted blocker evidence.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Diff check: clean.

## Next Gate

Create a production one-system-message rescope for `WU-CM-01-F01-S7-R1`.

The rescope must update design truth before implementation if it changes the stable RunInput message assembly contract. It must not rely on smoke-only helpers or provider logs as the fix.
