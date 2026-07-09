# WU-SEMANTIC-OWNERSHIP-01 P0-A Controller Validation Note

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-A`
- Gate: implementation validation before code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p0-a-implementation-codex.md`
- Date: 2026-07-09

## Controller Re-Runs

- `source .venv/bin/activate && pyright`
  - Result: pass, 0 errors.
- `git diff --check`
  - Result: pass.
- `source .venv/bin/activate && rg -n "ContentCompleteData\\(.+finish_reason|RunnerContentCompletedData\\(.+finish_reason" dayu/engine dayu/host tests`
  - Result: no matches. The removed content-completed finish reason constructors did not remain.
- Focused P0-A behavior subset:
  - Command: `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_metadata_boundary.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_sse_content_delta.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/host/test_engine_ingest_mapping.py -k 'usage_reported or runner_done_finish_reason_is_authority or content_completed_fields_exclude_finish_reason or runner_content_completed_data_excludes_finish_reason or non_stream_response or protocol_error or sse_content_delta or stream_and_non_stream_content'`
  - Result: 50 passed, 154 deselected.

## Broad Matrix Failures

The required broad commands still fail and must be reviewed before P0-A can be accepted:

- `tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes`
  - Controller rerun result: still fails.
  - Direct diff evidence: `tests/engine/runners/openai/test_stream_idle.py` and `dayu/engine/runners/openai/runner.py` have no diff in this implementation.
  - Current hypothesis: not on P0-A finish reason or usage provider id data path, but reviewers must verify.
- Five waiting-confirmation count assertions in `tests/host/test_engine_ingest_mapping.py`.
  - Controller rerun result: still fail.
  - Direct diff evidence: the failing assertion blocks around waiting confirmation were not modified by P0-A; the test diff only removed content-completed `finish_reason` fixture args and changed usage provider id assertions.
  - Current hypothesis: not on P0-A usage/content-completed data path, but reviewers must verify.

## Review Instruction

Code review must explicitly adjudicate whether these broad matrix failures are:

- accepted P0-A blockers that must be fixed in this sub WU before review pass;
- rejected as unrelated existing failures with direct evidence; or
- deferred with owner because they belong to another active sub WU / follow-up lane.
