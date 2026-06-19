# WU-CM-14 Code Review Adjudication

## Metadata

- Date: 2026-06-19
- Work unit: WU-CM-14 Recent Final Answer Preservation for Ordinal Follow-ups
- Accepted plan commit: `d4b271cb`
- Implementation owner: AgentCodex
- Code review artifacts:
  - `docs/reviews/code-review-20260619-190815.md`
  - `docs/reviews/code-review-20260619-191152.md`
- Focused re-review artifacts:
  - `docs/reviews/code-review-20260619-192312.md`
  - `docs/reviews/code-review-20260619-192408.md`
- Verdict: PASS after accepted review fixes and focused re-review

## Controller Adjudication

AgentCodex implemented WU-CM-14 inside the accepted file boundary. The implementation passes the existing `selected_recent_window_turn_floor` into proactive normal compact selection and reactive root compact selection, adds an internal protected recent raw tail provider for ordinary post-compaction RunInput, and repairs reactive frozen material assembly enough for WU-CM-14 protected floor semantics.

AgentMiMo and AgentDS both reviewed the current changes. Controller accepted the missing focused tests for LLM-facing evidence source filtering and reactive frozen material stop-condition verification. AgentCodex fixed both findings. AgentMiMo and AgentDS focused re-review both returned PASS.

## Finding Adjudication

| Finding | Source | Severity | Controller verdict | Re-review status |
|---|---|---:|---|---|
| LLM-facing evidence source filtering lacked focused boundary tests | AgentDS F1 | MEDIUM | accepted | closed |
| Reactive frozen material assembly lacked direct stop-condition block-kind assertions | AgentMiMo 01 / AgentDS F4 | LOW | accepted | closed |
| EventLog double-read in protected recent raw tail provider | AgentMiMo 02 / DS residual | LOW | deferred-with-owner WU-CM-13 | not a WU-CM-14 blocker |
| Content digest normalization mismatch reduces dedupe fast-path hit rate | AgentDS F3 | LOW | rejected as nonblocking for WU-CM-14; source-ref / evidence-ref dedupe is the correctness path | no fix required |
| Empty protected raw tail selection lacks diagnostic log | AgentDS F2 | LOW | deferred as optional observability; no correctness impact | no fix required |

## Validation

- `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` passed: 220 tests.
- `python -m pyright dayu/ tests/ utils/` passed: 0 errors, 0 warnings, 0 informations.
- `git diff --check` passed.

## Final Verdict

PASS. WU-CM-14 implementation may proceed to accepted slice commit, then aggregate deepreview.
