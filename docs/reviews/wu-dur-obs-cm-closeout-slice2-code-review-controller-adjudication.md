# WU-DUR-P01 Slice 2 Code Review Controller Adjudication

## Verdict

fix required. Slice 2 is not accepted yet.

## Reviewed Inputs

- `docs/host/design.md`
- `docs/host/wu-dur-obs-cm-closeout-plan.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-implementation-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-code-review-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice2-code-review-ds.md`
- Current Slice 2 workspace diff.

## Controller Judgment

AgentDS's blocking scope finding is accepted.

The design and plan both describe Slice 2 as a runner-call manifest signal for each logical runner call. The implementation records `RUNNER_CALL_INPUT_ASSEMBLED` for the ordinary `RunInputBuilder` path, but tool-loop continuation runner calls currently only emit Engine-owned `message_count` / `role_sequence_digest` observations and Host ingest only validates against an already-existing manifest. If no manifest exists, the signal remains preview-only `limited_signal` and no canonical `RUNNER_CALL_INPUT_ASSEMBLED` event is written.

That is not enough to accept Slice 2 as implemented. The missing continuation path directly affects the slice's stated data flow:

`RunInputBuilder/Engine messages -> Engine-owned observations -> Host manifest/digests -> RUNNER_CALL_INPUT_ASSEMBLED -> EventLog/payload/artifact refs -> Tool Trace projection`.

## Accepted Findings For Fix Gate

| ID | Severity | Decision | Required action |
|---|---|---|---|
| S2-F1 | blocking | accepted | Resolve the tool-loop continuation manifest gap. Either implement a production-grade Host-owned canonical `RUNNER_CALL_INPUT_ASSEMBLED` signal for continuation calls within the Slice 2 allowed boundary, or produce a blocker artifact with direct code/design evidence proving the current plan cannot be implemented without changing the Slice 2 contract or allowed file set. Do not silently defer it as residual risk. |
| S2-F2 | medium | accepted if S2-F1 is implemented | If a non-`complete` continuation manifest or diagnostic event is written, Tool Trace diagnostic output must not hardcode diagnostic details to `None`; it must either read typed diagnostic fields from the manifest/canonical payload or fail closed as a limited signal with a contract-compliant reason. |
| S2-F3 | medium | accepted if S2-F1 is implemented | Continuation runner-call validation must be visible through the canonical manifest / Tool Trace signal path, not only in `EventClass.PREVIEW`. |

## Not Accepted For Immediate Fix

- MiMo F1 duplicate `_find_runner_call_manifest_event`: valid maintenance issue, but not the current root cause. Do not block Slice 2 acceptance on this unless the S2-F1 fix needs the helper anyway.
- MiMo F2 / DS finding-4 recovery trigger classification: valid future hardening concern. The current slice primarily covers ordinary path and the accepted blocking issue is continuation manifest coverage. Do not broaden this fix unless a small local correction is necessary for S2-F1.
- MiMo low findings around content-prefix projector classification, bounded-size threshold, and projector purpose coverage: not immediate blockers.
- DS low finding about AssistantMessage content digest asymmetry: not a correctness issue for this slice.

## Validation Already Run

Before review, controller reproduced:

- `pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py`: 153 passed.
- `pyright`: 0 errors.
- `git diff --check`: clean.

These validations prove the current ordinary-path implementation is internally consistent, but they do not close S2-F1.

## Next Gate

Slice 2 fix gate. AgentCodex must either:

1. implement the accepted fix and update focused tests / README / implementation fix artifact, or
2. stop with a blocker artifact proving the plan requires reslicing or design amendment.
