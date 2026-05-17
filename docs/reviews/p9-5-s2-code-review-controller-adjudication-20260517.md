# P9.5 S2 Code Review Controller Adjudication

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Slice: S2 Engine / OpenAI Runner / Parser Hardening.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md`.
- Implementation artifact: `docs/reviews/p9-5-s2-engine-openai-runner-parser-implementation-20260517.md`.
- Code review artifact:
  - `docs/reviews/p9-5-s2-code-review-ds-20260517.md`
- Reviewer availability note:
  - AgentMiMo was assigned the same review but stalled during file reading twice and produced no artifact after interruption and a narrower follow-up. Controller records AgentMiMo unavailable for this S2 code review and proceeds with the available AgentDS review plus controller evidence review.
- Date: 2026-05-17.

## Verdict

S2 requires a fix before accepted slice commit.

AgentDS reported 0 blocking findings, but the controller accepts three findings as required current-slice fixes under the project rules and the approved S2 direct-evidence standard.

## Finding Adjudication

| Source | Finding | Controller decision | Required action |
| --- | --- | --- | --- |
| AgentDS F1 | `_OpenAIUsage` TypedDict is dead code after `usage.py` extraction | Accepted as required fix | Remove `_OpenAIUsage` and its private `__all__` entry from `dayu/engine/runners/openai/_types.py`. |
| AgentDS F2 | `bool`-as-`int` persists in `_coerce_tool_call_delta` index handling | Accepted as required fix | Reject bool index values in `dayu/engine/runners/openai/sse_parser.py`; add focused test coverage. WARN diagnostic is optional only if it follows existing parser diagnostic style without logging payload. |
| AgentDS F3 | `bool`-as-`int` persists in `ToolCallAggregator._resolve_index` | Accepted as required fix | Reject bool index values in `dayu/engine/runners/openai/tool_call_aggregator.py`; add focused test coverage or extend the S2 id-fallback test. |
| AgentDS F4 | non-stream `non_stream_missing_choices` lacks partial tool calls | Rejected as non-issue | No fix. There is no aggregator in that path and no partial tool calls to report. |
| AgentDS F5-F8 | Info observations | Accepted as observations | No current fix required. |

## Controller Rationale

- F1 is not runtime-breaking, but leaving a private dead `TypedDict` after extracting the true usage normalization owner creates a misleading internal seam. The project forbids compatibility/dead-code leftovers when doing a fresh refactor.
- F2 and F3 are direct code evidence, not theory-only hardening: Python treats `bool` as `int`, and the same defect class fixed for usage token counts remains in tool-call index routing. A malformed boolean index can route deltas to index 0/1 and corrupt aggregation. This is parser correctness, not a new provider contract.
- The fix must remain local to OpenAI-compatible parser internals. It must not add provider public state, retry redesign, Host governance, memory/tool governance, proactive context governance, or P10+ semantics.

## Required Fix Scope

Allowed files for the fix:

- `dayu/engine/runners/openai/_types.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- focused tests under `tests/engine/runners/openai/`
- fix artifact `docs/reviews/p9-5-s2-fix-20260517.md`

Required validation after fix:

- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine/test_metadata_boundary.py tests/engine/test_engine_event_contract.py`
- `source .venv/bin/activate && python -m pyright dayu/engine tests/engine`
- `git diff --check`

## Next Gate

Next gate: S2 fix, then S2 code re-review. Re-review must verify F1/F2/F3 fixed and no new blockers introduced.
