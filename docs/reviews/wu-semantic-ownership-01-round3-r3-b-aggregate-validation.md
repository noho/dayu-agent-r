# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Aggregate Validation

## 范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Accepted commits：
  - Plan：`d1cdfca4`
  - S1：`791ed144`
  - S2：`50ed754e`
  - S3：`1a70fd20`
- Gate：aggregate validation before aggregate deepreview
- Date：2026-07-12

## Aggregate validation fix

Default `pytest -q` first exposed two stable Host test failures outside R3-B production scope:

1. `tests/host/test_public_steer.py::test_steer_replays_same_client_request_id_idempotently`
   - Root cause：test waited for `RunStatus.RUNNING` but not for the current attempt to reach `ATTEMPT_RUNNING`; admission correctly rejects steer when a RUNNING Run's current Attempt is not yet running.
   - Fix：wait for `ATTEMPT_RUNNING` diagnostic before submitting steer, matching the owner boundary already used by the adjacent steer test.
   - Production change：none.

2. `tests/host/test_read_api_terminal_policy.py::test_succeeded_terminal_projection_fails_closed_for_descriptor_errors[...]`
   - Root cause：the test claimed to verify payload digest mismatch but used invalid digest format `sha256:mismatch`; durable payload owner correctly failed earlier with `expected_digest must be sha256 digest`.
   - Fix：use a valid but wrong sha256 digest and assert the actual owner-level descriptor digest mismatch fragment.
   - Production change：none.

Both fixes are test input / synchronization corrections required for aggregate default pytest. They do not modify Host production behavior and do not add compatibility or downstream repair.

## Required validation

### Default pytest

```text
pytest -q
4137 passed, 3 skipped, 5 deselected, 3 warnings in 103.29s
```

Warnings are existing Edgar deprecation warnings from dependency imports.

### Pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Source scans

```text
rg -n 'state\.(done_seen|finish_reason|provider_request_id)|or FinishReason\.STOP' dayu/engine/agent.py
# no output

rg -n 'state\.failure_candidate\s*=' dayu/engine/agent.py
564:    state.failure_candidate = candidate

rg -n 'isinstance\(arguments, Mapping\)|json\.dumps\(dict\(arguments\)\)|dict arguments preserved' dayu/engine/runners/openai/non_stream_parser.py tests/engine/runners/openai
# no output

rg -n 'done_finish_reason = FinishReason\.TOOL_CALLS|finish = FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
# no output

rg -n 'FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/_choice_policy.py dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
dayu/engine/runners/openai/_choice_policy.py:31:    "tool_calls": FinishReason.TOOL_CALLS
dayu/engine/runners/openai/_choice_policy.py:366:    finish_declares_tool_calls = finish_reason is FinishReason.TOOL_CALLS

rg -n 'source\.name \+ target\.name|source\.arguments_buffer \+ target\.arguments_buffer|target\.tool_call_id = target\.tool_call_id or source\.tool_call_id' dayu/engine/runners/openai/tool_call_aggregator.py
# no output

rg -n 'value not in enum_value|value in enum_value' dayu/runtime/tool_call_projection.py
# no output

rg -n '"(minLength|maxLength|minItems|maxItems)"\s*:\s*-' dayu
# no output

rg -n 'hasattr\(|getattr\(' dayu/engine/contracts/engine_events.py dayu/engine/contracts/messages.py dayu/engine/agent.py dayu/engine/runners/openai dayu/contracts/tool_schema.py dayu/runtime/tool_call_projection.py
# no output
```

The remaining expected hits are the first-candidate helper's sole assignment and `_choice_policy.py`'s explicit `TOOL_CALLS` wire mapping / fail-closed comparison.

### Whitespace

```text
git diff --check
# no output
```

## Controller conclusion

Aggregate validation is green and ready for aggregate deepreview. The two validation fixes are test-only and should be reviewed as part of aggregate deepreview before the aggregate accepted commit.
