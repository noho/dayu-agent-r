# WU-CM-12 S2 Code Review Adjudication

## Scope

- Work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- Gate: code review
- Slice: S2 Turn-Group Selected Recent Window And Fallback Selection
- Reviewed artifacts:
  - `docs/reviews/code-review-20260618-151719.md`
  - `docs/reviews/code-review-20260618-151848.md`

## Verdict

- Both reviewers passed S2 core behavior.
- Controller accepts two cleanup / maintainability findings before S2 acceptance because they are low-risk and directly tied to the S2 plan.

## Accepted Findings

### S2-F1 accepted

- Finding: `compact_material.py` and `context_fallback.py` duplicate `RunInputMaterialBlock` turn-group helper logic.
- Reason: the S2 plan explicitly requires a shared internal helper for newest N non-null `turn_group_id` group computation. Keeping duplicate implementations would let compact segment and fallback selection drift later.
- Required fix: keep a single helper owner for `RunInputMaterialBlock` turn-group semantics and make `context_fallback.py` reuse it.

### S2-F2 accepted

- Finding: `compact_material.py::_is_raw_turn_block` is dead code after S2 replaces raw item floor logic.
- Reason: the helper is unreferenced and encodes the old user/assistant-only floor semantics.
- Required fix: delete the dead helper.

## Non-Blocking Residuals

- S3 selected-id provenance guards remain future scope.
- S4 tier 1-3 compact recovery remains future scope.
- Broader pre-existing dispatch scheduler failures reported by DS are not S2-induced; current S2 affected test matrix and public smokes pass.

## Fix Dispatch

- Owner: AgentCodex.
- Required update: amend `docs/reviews/wu-cm-12-s2-implementation-codex-20260618.md` with the fix and validation.
- Required re-review: focused MiMo / DS re-review after fix.
