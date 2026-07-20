# WU-SEMANTIC-OWNERSHIP-01 P0-A Code Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-A`
- Gate: code review
- Accepted plan commit: `b1a0631f`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p0-a-implementation-codex.md`
- Controller validation note: `docs/reviews/wu-semantic-ownership-01-p0-a-controller-validation.md`
- Review artifacts:
  - `docs/reviews/code-review-20260709-151414.md` (AgentMiMo)
  - `docs/reviews/code-review-20260709-151525.md` (AgentDS)
- Decision date: 2026-07-09

## Decision

`accepted-no-fix-required`

Both reviewers concluded pass / no substantive P0-A issue. Controller accepts P0-A implementation for accepted commit. No fix gate is required for P0-A.

## Finding Adjudication

| Item | AgentMiMo | AgentDS | Controller decision |
|---|---|---|---|
| Finish reason authority cleanup | pass | pass | accepted |
| Usage `provider_request_id` propagation | pass | pass | accepted |
| Parser event ordering / tool-call finish reason | pass | pass | accepted |
| Host `content_completed` preview no longer projects finish reason | pass | pass | accepted |
| Tests and README owner-boundary sync | pass | pass | accepted |
| Semantic ownership drift | none found | none found | accepted |
| LLM-facing text leakage | none found | none found | accepted |

## Broad Matrix Failure Adjudication

Both reviewers and controller validation agree that the broad matrix failures are not P0-A blockers:

- `tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes`
  - Decision: `deferred-with-owner`
  - Owner: OpenAI Runner stream idle heartbeat / stream-debug gating maintainer.
  - Evidence: P0-A did not modify `test_stream_idle.py` or `dayu/engine/runners/openai/runner.py`; the failure is not on the finish reason or usage identity data path.
- Five waiting-confirmation count assertions in `tests/host/test_engine_ingest_mapping.py`
  - Decision: `deferred-with-owner`
  - Owner: Host waiting/confirmation flow maintainer.
  - Evidence: P0-A did not modify waiting-confirmation or canonical tool event count logic; changed lines in that file only remove content-completed `finish_reason` fixture args and update usage provider id assertions.

These failures remain residual validation debt for their owners. They do not justify widening P0-A because doing so would cross owner boundaries and violate the accepted sub WU scope.

## Accepted Propagation Audit

Finish reason:

- Provider `choices[].finish_reason` is mapped by the OpenAI-compatible parser.
- Parser emits the authoritative `RunnerDoneData.finish_reason`.
- Agent writes `_IterationState.finish_reason` only from `RunnerDoneData`.
- Agent emits `IterationCompletedData.finish_reason`.
- Host terminal/final-answer and iteration-completed preview paths preserve finish reason.
- `RunnerContentCompletedData`, `ContentCompleteData`, and Host content-completed preview/audit no longer carry finish reason.

Usage identity:

- Provider response header is captured as Runner provider request id.
- SSE and non-stream parser usage events emit `RunnerUsageRecordedData.provider_request_id`.
- Agent emits `UsageReportedData.provider_request_id`.
- Host ingest writes the same value into `USAGE_REPORTED` payload, `UsageObservation`, and invalid usage observation digest.

## Validation Accepted For P0-A

- Controller focused P0-A subset: 50 passed.
- AgentDS focused validation: selected P0-A tests passed.
- `pyright`: 0 errors.
- `git diff --check`: pass.
- Content-completed finish reason constructor invariant scan: no matches.

## Next Gate

Proceed to accepted P0-A commit, then continue with ordered sub WU P0-B. The umbrella WU remains open.
