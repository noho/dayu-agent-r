# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 code review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-controller-validation.md`
- Review inputs:
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-ds.md`

## Controller Result

Controller accepts two S2 code-review fixes and rejects one non-defect observation.

## Findings Adjudication

| Finding | Source | Decision | Reason |
|---|---|---|---|
| `P3-H-S2-CR-F01` `_failure_message` can fall back to `snapshot.message`. | AgentDS finding 1; AgentMiMo residual risk. | Accepted, fixed pending re-review. | `snapshot.message` is process-local observation diagnostic text. LLM-visible failed wait message must come from `FinsResultSummary.error_message`, which is produced from `direct_event_text.py`. |
| `P3-H-S2-CR-F02` missing programmatic invariant tests for observation terminal `error_message`. | AgentDS finding 2. | Accepted, fixed pending re-review. | Controller validation scans were not enough. Tests must cover cancellation-before-activation, activation failure, producer missing result, and malformed failed snapshot. |
| `P3-H-S2-CR-N01` whitespace-only `fallback_message` is ignored. | AgentMiMo finding 001. | Rejected as non-defect. | `direct_failure_message(...)` explicitly treats empty fallback as absent. Whitespace-only input is semantically empty and current call sites pass `None` or already cleaned text. |

## Required Fix

- Remove `_failure_message(...)` fallback to `snapshot.message`.
- Fail fast when a failed observation result lacks non-empty `error_message`.
- Add tests proving internal `Observation ...` diagnostic text does not enter `FinsResultSummary.error_message`.
- Add a malformed failed snapshot test proving wait adapter does not silently fall back to `snapshot.message`.

## Status

Fix is implemented locally and ready for independent re-review.
