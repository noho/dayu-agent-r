# WU-CM-01-F03 Plan Review Controller Adjudication

## Gate

- Work unit: WU-CM-01-F03 Assistant final answer continuity fidelity closeout
- Gate: plan review adjudication
- Design source: `docs/host/design.md`; `docs/engine/design.md`
- Plan artifact: `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md`
- Review artifacts:
  - `docs/reviews/wu-cm-01-f03-plan-review-mimo.md`
  - `docs/reviews/wu-cm-01-f03-plan-review-ds.md`
- Controller verdict: plan requires fix before re-review

## Overall Judgment

The plan direction is accepted. The root problem is real: assistant final answer continuity currently uses a mixed summary helper that can read `summary_text` or nested `summary`, which violates the design boundary for LLM-facing Trace / Answer material.

The plan correctly narrows assistant continuity to `final_answer` or digest-checked terminal summary artifact `content`, and keeps Session Summary Memory sourced only from accepted compact `session_summary`. However, the reviewers found two plan-level gaps that should be fixed before implementation.

## Finding Decisions

| Finding | Source | Decision | Controller rationale |
|---|---|---|---|
| `_successful_run_continuity_messages` / `_successful_run_message_pair` / `_continuity_message_from_event` are dead code and should be deleted, not left as conditional migration. | DS BF-1; MiMo Finding 4 | accepted | Direct grep evidence shows the chain has no production callers. Keeping migration as an option leaves avoidable old summary semantics in the implementation plan. |
| `STRICT_ALLOW_EMPTY` removal and durable vs inline text policy unification are not explicit. | DS BF-2; MiMo Finding 2 | accepted | Empty final answer should not be valid assistant continuity. The plan must explicitly migrate durable memory hydration to `STRICT_NON_EMPTY`, and empty `final_answer` must fall through to terminal artifact `content` when available. |
| `_payload_with_terminal_summary` early-return guard must only check `final_answer`, not `content` or `summary_text`. | MiMo Finding 1 | accepted | This is the same source boundary issue. RUN payload `content` must not short-circuit terminal artifact hydration. |
| `_selected_assistant_item` returning `None` requires a caller guard. | MiMo Finding 3 | accepted | This is an implementation detail, but the plan should mention it so pyright-clean implementation is straightforward. |
| `test_terminal_summary_payload.py` does not exist and should be created. | DS NF-2; MiMo Finding 5 | accepted | Low risk, but the plan should say "new test file" to avoid ambiguity. |
| Import-cycle fallback needs a concrete module decision. | DS NF-1; MiMo Finding 6 | accepted with adjusted fix | The plan should either record static no-cycle evidence or name a concrete fallback module such as `dayu/host/_terminal_answer.py` for the transaction-aware resolver. Implementation must not use callback indirection or duplicate field policy. |

## Required Plan Fix

AgentCodex must update only `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md` and record:

- The dead `run_input.py` helper chain is to be deleted outright after a final grep confirmation.
- `STRICT_ALLOW_EMPTY` is removed intentionally; both durable and inline paths use non-empty semantics for assistant continuity.
- Empty `final_answer` is not valid continuity and should not block terminal artifact `content` lookup.
- RUN payload early-return checks only `final_answer`.
- `_selected_assistant_item` caller must skip replacement when the new helper returns `None`.
- `tests/host/test_terminal_summary_payload.py` is a new test file.
- If transaction-aware terminal content resolver cannot live in `terminal_summary_payload.py` without import-cycle risk, the fallback module name and dependency direction are explicit.

## Residual Risks

No design-level residual risk. The remaining risks are implementation hygiene and test coverage risks covered by the accepted plan fix items.
