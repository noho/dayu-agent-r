# WU-SEMANTIC-OWNERSHIP-01 P0-A Entry Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-A`
- Gate: implementation entry
- Accepted plan commit: `b1a0631f`
- Plan artifact: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- Decision date: 2026-07-09

## Direct Evidence

P0-A accepted plan requires a consumer scan before implementation because `ContentCompleteData.finish_reason` and `RunnerContentCompletedData.finish_reason` must stop being independent authority.

Controller pre-scan found:

- `dayu/engine/contracts/runner_events.py`: `RunnerContentCompletedData.finish_reason` exists.
- `dayu/engine/contracts/engine_events.py`: `ContentCompleteData.finish_reason` exists.
- `dayu/engine/agent.py`: `RunnerContentCompletedData.finish_reason` is copied to iteration state and projected into `ContentCompleteData`; mismatch with `RunnerDoneData.finish_reason` currently prefers the earlier content-completed value.
- `dayu/host/engine_ingest.py`: `_make_preview_payload()` projects `ContentCompleteData.finish_reason` into Host preview/audit payload for `content_completed`.

## Owner Boundary

- Runner parser owns provider finish reason extraction.
- `RunnerDoneData.finish_reason` owns Runner-call completion authority.
- `IterationCompletedData.finish_reason` is the EngineEvent projection of that authority.
- `ContentCompleteData` only owns completed text/reasoning material and must not carry or project finish reason.
- Host ingest may persist/audit content completion metadata, but it must derive finish reason only from `IterationCompletedData` / final answer terminal facts, not from `ContentCompleteData`.

## Stop-Condition Decision

The `dayu/host/engine_ingest.py` hit is a production consumer outside Engine Agent/parser/tests, but it is already inside P0-A allowed files and only projects diagnostic preview material for `content_completed`. It does not justify keeping `ContentCompleteData.finish_reason`.

Controller authorizes P0-A implementation to migrate this projection by removing `finish_reason` from content-completed preview/audit payloads and preserving finish reason only on iteration-completed / final-answer / terminal paths.

This is not a downstream workaround because the fix removes the duplicate field at the Engine contract owner boundary and updates the downstream projection to consume the corrected contract.

## Implementation Requirements

- Remove `finish_reason` from `RunnerContentCompletedData` and `ContentCompleteData`.
- Ensure `RunnerDoneData.finish_reason` is the only Runner-call completion authority.
- Ensure Agent mismatch handling no longer prefers content-completed state over `RunnerDoneData.finish_reason`.
- Remove content-completed `finish_reason` projection from Host preview/audit payloads.
- Preserve finish reason on `IterationCompletedData`, final answer terminal payloads, Host final answer view, and other terminal facts.
- Add `provider_request_id` propagation to Runner usage and Engine `UsageReportedData`, then Host durable usage payload and diagnostics.
- Update affected Engine / Host tests and README files according to AGENTS.md triggers.
- Include a propagation audit in the implementation artifact.
