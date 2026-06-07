# WU-CM-01-F03 Plan Fix — AgentCodex

## Gate

- Work unit: WU-CM-01-F03 Assistant final answer continuity fidelity closeout
- Gate: plan fix
- Design source: `docs/host/design.md`; `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Plan artifact fixed: `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md`
- Controller adjudication: `docs/reviews/wu-cm-01-f03-plan-review-controller-adjudication.md`

## Accepted Findings Addressed

| Accepted finding | Plan fix applied | Status |
|---|---|---|
| Delete the dead `run_input.py` helper chain outright after final grep confirmation: `_successful_run_continuity_messages`, `_successful_run_message_pair`, `_continuity_message_from_event`. | Updated Exact Implementation Decision 4, Slice 3, search validation, and risks to require final grep confirmation followed by direct deletion. Removed the previous conditional migration wording. | addressed |
| Make `STRICT_ALLOW_EMPTY` removal explicit; durable and inline paths must use non-empty assistant continuity semantics. Empty `final_answer` must not be valid continuity and must not block terminal artifact lookup. | Updated Exact Implementation Decisions 1 and 2 plus Slice 1 / Slice 2 tests. Durable and inline hydration now explicitly use non-empty semantics, and blank `final_answer` falls through to digest-checked terminal artifact `content`. | addressed |
| RUN payload early-return guard checks only `final_answer`; RUN payload `content` and `summary_text` must not short-circuit terminal artifact hydration. | Updated Exact Implementation Decision 2 to specify `_payload_with_assistant_final_answer()` early-return checks only non-empty RUN payload `final_answer`, not `content`, `summary_text`, or nested `summary`. | addressed |
| `_selected_assistant_item` caller must guard `None` and skip replacement when no assistant final answer continuity text exists. | Updated Exact Implementation Decision 3 to require an explicit caller-side `None` guard before `_replace_item_by_id(...)`. | addressed |
| `tests/host/test_terminal_summary_payload.py` is a new test file. | Updated Slice 1 allowed files to mark `tests/host/test_terminal_summary_payload.py` as a new test file. | addressed |
| Import-cycle fallback needs a concrete plan: static no-cycle evidence or fallback module such as `dayu/host/_terminal_answer.py`; no callback indirection or duplicate field policy. | Updated Risks / Open Questions with a concrete dependency decision: try the transaction-aware resolver in `terminal_summary_payload.py` with import-smoke validation; if a cycle appears, move only `assistant_final_answer_continuity_text(...)` to `dayu/host/_terminal_answer.py` while keeping pure field readers in `terminal_summary_payload.py`. Callback indirection and duplicate field policy remain forbidden. | addressed |

## Exact Plan Sections Changed

- `Exact Implementation Decisions`
  - Added explicit `STRICT_ALLOW_EMPTY` deletion and non-empty semantics for durable and inline hydration.
  - Added early-return guard rule: only non-empty RUN payload `final_answer` can short-circuit terminal artifact hydration.
  - Added `_selected_assistant_item()` caller-side `None` guard requirement.
  - Replaced conditional `_continuity_message_from_event()` migration language with direct deletion of the confirmed dead helper chain.
- `Small Implementation Slices`
  - Marked `tests/host/test_terminal_summary_payload.py` as a new focused test file.
  - Added blank `final_answer` / blank terminal `content` negative helper tests.
  - Added durable projection test for blank `final_answer` plus valid terminal artifact `content`.
  - Updated Slice 3 to require deletion of `_successful_run_continuity_messages`, `_successful_run_message_pair`, and `_continuity_message_from_event`.
- `Required Tests / Validation Commands`
  - Added search validation for `STRICT_ALLOW_EMPTY` and the dead `run_input.py` helper chain.
- `Risks / Open Questions`
  - Removed the lingering conditional dead-helper wording.
  - Added the concrete import-cycle fallback module `dayu/host/_terminal_answer.py` and dependency direction.

## Remaining Risks / Open Questions

- No blocking open question remains for plan re-review.
- Implementation still must perform the final grep confirmation before deleting the dead helper chain.
- Implementation still must import-smoke the transaction-aware resolver location and use `dayu/host/_terminal_answer.py` only if `terminal_summary_payload.py` creates a cycle.
- Existing durable data containing only `summary_text` remains intentionally fail-closed under the plan; no compatibility read path is introduced.

## Validation

- Plan-only fix; no production code, tests, README, control doc, or review artifact was modified.
- No code tests were run because this gate only updates the plan artifact and writes this fix artifact.
- Preflight recorded current branch and dirty state before edits.

## Verdict

ready-for-rereview
