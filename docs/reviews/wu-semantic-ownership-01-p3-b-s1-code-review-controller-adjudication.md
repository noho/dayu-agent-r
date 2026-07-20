# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 code review controller adjudication

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`.
- Gate: S1 code review controller adjudication.
- Reviews:
  - `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-ds.md`
- Decision: enter code-review fix gate with two merged Low-severity fixes.

## Review merge

- AgentMiMo: accept, 0 findings.
- AgentDS: pass, 3 Low findings; findings 1 and 3 have the same root cause and fix.
- The controller does not use the passing verdict to discard directly evidenced defensive-contract gaps.

## Accepted fixes

### P3-B-S1-CR-F01 - Outbox public JSON read boundary

Accepted by merging DS findings 1 and 3. `_final_answer_from_outbox_json` currently verifies that `content` is text but delegates non-empty validation to `HostFinalAnswerView`, producing `ValueError` for a corrupted raw row even though the read path documents `HostDurableError`. Add Outbox-row-specific non-empty/blank validation at this parsing boundary and a raw-row/public-read behavior test asserting `HostDurableError` with an Outbox-specific diagnostic. Keep `HostFinalAnswerView` validation as the public contract; do not remove either layer.

### P3-B-S1-CR-F02 - malformed `finish_reason` regression

Accepted from DS finding 2. Production paths already fail closed for non-text `finish_reason`, but the canonical metadata matrix does not lock this behavior for both Outbox projection failure and succeeded HostEvent read. Add behavior coverage using a non-text value and assert the stable `finish_reason` diagnostic. Do not add a compatibility conversion.

## Rejected / deferred

- P3-J DDL conditional CHECK: remains deferred with owner; no current failure requires schema expansion.
- Descriptor automatic repair and optional-material policy tightening: remain explicit non-goals with their recorded owners.
- No additional fix is inferred from MiMo's accepted implementation observations.

## Completion

- Accepted merged fixes: 2.
- Rejected/deferred current fixes: 0 material code defects beyond the two above.
- Blocking open question: none.
- Next gate: S1 code-review fix by AgentCodex, then parallel code re-review.
