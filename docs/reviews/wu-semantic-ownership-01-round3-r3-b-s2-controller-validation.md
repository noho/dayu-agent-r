# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S2 Controller Validation

## 范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Slice：`S2 — OpenAI Tool Identity And Terminal Protocol Normalization`
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-implementation-codex.md`
- Controller validation time：2026-07-12

## Scope check

S2 修改集中在 accepted plan 允许的 OpenAI adapter owner：

- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/runners/openai/_choice_policy.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`

测试修改集中在 S2 allowed OpenAI tests，并新增 plan 指定的 identity-conflict test file。没有 Host、Agent、runtime schema、Fins、Service、CLI、README 或 design doc 修改。

## Controller rerun

### Position-routed conflict node

```text
pytest tests/engine/runners/openai/test_tool_call_identity_conflicts.py::test_position_routed_conflict_fails_closed_without_merge -q
1 passed in 0.13s
```

### S2 focused matrix

```text
pytest tests/engine/runners/openai/test_tool_call_identity_conflicts.py tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_old_protocol_parity_regressions.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
109 passed in 0.21s
```

### Full OpenAI adapter suite

```text
pytest tests/engine/runners/openai -q
302 passed in 1.54s
```

### Pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Source scans

```text
rg -n 'isinstance\(arguments, Mapping\)|json\.dumps\(dict\(arguments\)\)|dict arguments preserved' dayu/engine/runners/openai/non_stream_parser.py tests/engine/runners/openai
# no output

rg -n 'done_finish_reason = FinishReason\.TOOL_CALLS|finish = FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
# no output

rg -n 'FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/_choice_policy.py dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
dayu/engine/runners/openai/_choice_policy.py:31:    "tool_calls": FinishReason.TOOL_CALLS
dayu/engine/runners/openai/_choice_policy.py:366:    finish_declares_tool_calls = finish_reason is FinishReason.TOOL_CALLS

rg -n 'source\.name \+ target\.name|source\.arguments_buffer \+ target\.arguments_buffer|target\.tool_call_id = target\.tool_call_id or source\.tool_call_id' dayu/engine/runners/openai/tool_call_aggregator.py
# no output
```

The remaining `FinishReason.TOOL_CALLS` hits are both in `_choice_policy.py`: explicit provider wire mapping and fail-closed presence/mismatch comparison. There is no parser direct forcing in `sse_parser.py` or `non_stream_parser.py`.

### Whitespace

```text
git diff --check
# no output
```

## Controller conclusion

S2 implementation is ready for code review. Review focus should include:

- native index validation and no fallback on explicit invalid index;
- id/index/position identity conflict handling, including position-routed occupied target;
- absence of old partial merge and absence of executable completed tool calls after fatal conflict;
- shared `_choice_policy` terminal shape ownership for SSE/non-stream;
- deletion of non-stream dict/list/number/bool/null arguments compatibility;
- semantic classification of `FinishReason.TOOL_CALLS` scan hits.
