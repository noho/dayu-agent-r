# WU-CM-15 Code Review Adjudication

## Scope

- Work unit: WU-CM-15 Conversation memory public smoke reactive compact and fallback coverage.
- Gate: code review adjudication.
- Base: accepted plan commit `97518e93`.
- Implementation artifact: `docs/reviews/wu-cm-15-implementation-codex-20260620.md`.
- Code review artifacts:
  - `docs/reviews/code-review-20260620-112127.md` (AgentDS).
  - `docs/reviews/code-review-20260620-112301.md` (AgentMiMo).

## Controller Decision

Code review found one material smoke-oracle gap and two low-risk maintainability issues. The implementation direction remains valid and within WU-CM-15 scope. Next gate is fix by AgentCodex, limited to the accepted findings below.

## Finding Adjudication

| Review finding | Decision | Required fix |
|---|---|---|
| DS 1: reactive acceptance does not assert old seed marker is excluded from recovery dispatch | accepted | Make `memory-reactive-compact` treat `_SMOKE_REACTIVE_OLD_MARKER` as the dropped old marker and assert it is absent from the recovery dispatch input. Add or update helper tests so this omission cannot regress silently. |
| MiMo 1: `_compact_pressure_reserve_tokens` dead code | accepted | Delete the unused helper and verify pyright / tests still pass. |
| MiMo 2: private compactor runner monkey-patch lacks sanity check | accepted | Add a minimal sanity check in `_patched_compactor_runner` confirming the module attribute points to the injected runner while patched, and still restore in `finally`. |
| DS 2: fallback pressure observation may differ by about one token from padding calculation | rejected-with-reason | Current implementation has explicit soft/hard threshold assertions, large margin, and passing helper/smoke validation. Returning extra internal token accounting would add complexity without improving WU-CM-15 acceptance. Reconsider only if a future test proves boundary flakiness. |

## Residual Risks

- Existing `memory-compact` real-provider smoke remains dependent on a valid compactor provider key. Current failure with `test-provider-key` is classified as environment/authentication residual, not a WU-CM-15 implementation bug.
- Runtime patching of `dayu.host.llm_compaction._run_agent_request` remains a known smoke-local maintenance tradeoff; accepted fix only adds a sanity check.

## Next Gate

- Gate: fix.
- Agent: AgentCodex.
- Allowed files:
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - `docs/reviews/wu-cm-15-code-review-fix-codex-20260620.md`
- No commit, push, PR, merge, control-doc edit, README edit, or re-review.
