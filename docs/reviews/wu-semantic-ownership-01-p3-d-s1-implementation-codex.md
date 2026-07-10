# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 implementation - AgentCodex

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Slice: `S1 - Adapter choice and finish-reason policy`
- Agent: AgentCodex
- Accepted plan commit: `c52519f0`
- Status: implementation complete

## Source Findings

### Closed in S1

- AgentCodex 5: SSE 多 choice 合并与 non-stream `choices[0]` 任意选择已关闭。
  - SSE 在 `_handle_chunk_object()` 内通过 adapter 私有 choice policy 先校验 `choices`，fatal 后直接产出 `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)`，不会先合并 content / tool state。
  - Non-stream 在读取 `message` 前先做 response-level `choices` 校验，missing / non-list / empty / multi-choice / explicit non-zero index 都 fail closed。
- AgentDS 21 的 S1 部分：unknown / invalid `finish_reason` 默认 `STOP` 已关闭。
  - `unknown_finish_reason` warning fallback 已移除。
  - unknown non-empty string、empty string、bool / number / array / object 均 fatal。
  - `null` / missing 只表示 absent；content-only success 缺 terminal finish reason fatal；tool_calls 完整路径仍由 adapter 归一为 `TOOL_CALLS`。
  - SSE cross-chunk conflicting terminal `finish_reason` fatal。

### Still Open by Approved Later Slice

- AgentCodex 4: fatal provider protocol error 与 non-fatal provider diagnostic 仍待 S2 拆分。本 slice 未新增 `PROVIDER_DIAGNOSTIC` 或 Host 行为。
- AgentDS 2: Engine error code typing 仍待 S3。
- AgentDS 4 / AgentMiMo BI-7: context-overflow provenance diagnostic 仍待 S2。

## Exact Files Changed

- `dayu/engine/runners/openai/_choice_policy.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `dayu/engine/README.md`
- `tests/README.md`

Unrelated untracked files were not modified.

## Implementation Summary

- Added one OpenAI adapter-private choice policy helper for shared `choices` and `finish_reason` validation.
- SSE now validates each chunk before merging content / reasoning / tool deltas. `choices=[]` is legal only when the same chunk has valid usage. Empty delta without terminal finish reason is not a valid assistant choice, but invalid shape or non-zero index remains fatal.
- Non-stream now requires exactly one assistant choice before selecting it.
- Removed unknown `finish_reason -> STOP` fallback in both paths.
- Added fail-closed tests for stream / non-stream invalid finish reasons, multi-choice, explicit non-zero index, absent terminal finish reason, SSE cross-chunk finish conflict, and empty-delta plus one valid choice behavior.

## Validation

- Focused tests:
  - `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py -q`
  - Result: `60 passed`
- Pyright:
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- Diff whitespace:
  - `git diff --check`
  - Result: pass
- Coverage:
  - `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py --cov=dayu.engine.runners.openai.sse_parser --cov=dayu.engine.runners.openai.non_stream_parser --cov-report=term-missing -q`
  - Result: `60 passed`
  - `dayu/engine/runners/openai/sse_parser.py`: 86%
  - `dayu/engine/runners/openai/non_stream_parser.py`: 89%
- Source scan:
  - `rg -n "unknown_finish_reason|FinishReason\\.STOP|finish_reason or FinishReason\\.STOP" dayu/engine/runners/openai tests/engine/runners/openai`
  - Result: no `unknown_finish_reason`; no `finish_reason or FinishReason.STOP`.
  - Remaining `FinishReason.STOP` hits are the known-string mapping in `_choice_policy.py` and positive tests asserting explicit provider `"stop"` maps to `STOP`.
- no-LLM-facing diagnostic leakage validation:
  - `rg -n "\\b(PROVIDER_DIAGNOSTIC|provider_diagnostic|memory|compact|evidence|prompt|final_answer|LLM-facing)\\b" dayu/engine/runners/openai/_choice_policy.py dayu/engine/runners/openai/sse_parser.py dayu/engine/runners/openai/non_stream_parser.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py`
  - Result: no matches.

## README Decision

- `dayu/engine/README.md`: updated. The Runner protocol section already documents OpenAI-compatible Runner behavior; adapter-owned choice / finish_reason fail-closed policy is now current implementation behavior relevant to developers.
- `tests/README.md`: updated. The OpenAI runner test layer now explicitly records choice policy fail-closed coverage for SSE and non-stream.

## Propagation Audit

Semantic: provider `choices` and `finish_reason`.

Path:

```text
provider wire response
  -> OpenAI adapter private choice policy
  -> SSE / non-stream parser normalized RunnerEvent
  -> Agent consumes RunnerEvent
  -> EngineEvent projection
  -> Host ingest / EventLog / read models
```

Audit result:

- Producer: provider HTTP/SSE response first produces raw `choices` and `finish_reason`.
- Validator / normalizer: OpenAI-compatible Runner adapter now validates these facts before state merge or choice selection.
- Persisted / projected fact: downstream only receives `RunnerContentCompletedData`, `RunnerToolCallsCompletedData`, `RunnerDoneData(FinishReason.*)`, or fatal `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)`.
- No Host / Agent downstream code needs to infer multiple choice policy, index policy, unknown finish reason, or absent terminal finish reason from raw provider strings.
- Durable state / trace / memory / audit / UI / LLM-facing outputs remain downstream of the normalized RunnerEvent. This slice did not add diagnostic projection, memory material, compact material, evidence material, prompt text, or final-answer text.

## Residual Risks

- Fixed: S1 adapter choice policy and `finish_reason` fail-closed behavior.
- Covered by later approved slice: non-fatal provider diagnostics and context-overflow provenance remain S2.
- Covered by later approved slice: typed Engine error-code contract remains S3.
- Existing issue: some providers may return multiple choices despite Dayu not requesting them; S1 intentionally fails closed rather than fabricating one assistant response.
- User decision: no backward compatibility wrapper or old alias added, per S1 non-goals and repository constraints.
