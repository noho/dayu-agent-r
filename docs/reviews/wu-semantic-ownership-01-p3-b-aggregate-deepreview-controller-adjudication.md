# WU-SEMANTIC-OWNERSHIP-01 P3-B aggregate deepreview controller adjudication

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`.
- Gate: aggregate deepreview controller adjudication.
- Reviews:
  - `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-ds.md`
- Decision: enter aggregate fix gate with one Low-severity finding.

## Review merge

- AgentMiMo: PASS, 0 material findings.
- AgentDS: PASS, one new Low finding.
- All previously accepted code-review findings remain closed.

## Accepted finding

### P3-B-AGG-F01 - blank Outbox `finish_reason` diagnostic boundary

`_final_answer_from_outbox_json` rejects non-text `finish_reason` itself but delegates blank text to `HostFinalAnswerView`, causing a corrupted raw Outbox row to surface `ValueError` instead of the documented durable/public error chain. This has the same owner and boundary as the already-fixed blank `content` case.

Required fix:

- Reject empty/blank `finish_reason` in the Outbox JSON read parser with `HostDurableError` and an Outbox field-specific diagnostic.
- Add a raw SQLite row -> public Outbox read test that asserts `HostApiError(INTERNAL_ERROR)` and the durable cause.
- Retain the independent `HostFinalAnswerView` public validation and add no conversion or compatibility path.

## Residual reconciliation

- DDL conditional CHECK remains assigned to P3-J.
- Descriptor automatic repair remains assigned to P3-J/storage hardening if direct product need appears.
- Optional-material strictness remains governed by current design; any change belongs to P3-C/design adjudication.
- Writer/reader field constants are simple private projection details protected by behavior tests; no new shared registry is justified.

No residual is left without an owner.

## Completion

- Accepted aggregate fixes: 1.
- Blocking open question: none.
- Next gate: aggregate fix by AgentCodex, then parallel aggregate re-review.
