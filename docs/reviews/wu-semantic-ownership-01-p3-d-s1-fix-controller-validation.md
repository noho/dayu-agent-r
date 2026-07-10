# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 Fix Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Slice: `S1 - Adapter choice and finish-reason policy`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-fix-codex.md`
- Accepted findings: `P3-D-S1-CR-F01`, `P3-D-S1-CR-F02`, `P3-D-S1-CR-F03`
- Controller validation date: 2026-07-10

## Finding Closure Check

| Finding | Controller check |
| --- | --- |
| `P3-D-S1-CR-F01` | `test_sse_finish_reason_without_delta_emits_invalid_choice_shape` covers `{"choices":[{"finish_reason":"stop"}]}` and asserts `sse_invalid_choice_shape`, `delta_missing`, `RunnerDoneData(ERROR)`, and no content completed event. |
| `P3-D-S1-CR-F02` | `test_sse_empty_choices_without_usage_emits_protocol_error` covers `{"choices":[]}` without usage and asserts `sse_missing_choices`, `choices_empty_without_usage`, and `RunnerDoneData(ERROR)`. |
| `P3-D-S1-CR-F03` | `test_non_stream_choice_without_message_or_finish_reason_fails_closed` covers one non-stream choice with neither `message` nor `finish_reason` and asserts `non_stream_invalid_choice_shape`, `message_missing`, and `RunnerDoneData(ERROR)`. |

## Validation Commands

| Validation | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py --cov=dayu.engine.runners.openai.sse_parser --cov=dayu.engine.runners.openai.non_stream_parser --cov=dayu.engine.runners.openai._choice_policy --cov-report=term-missing -q` | `63 passed`; `_choice_policy.py` 95%, `sse_parser.py` 86%, `non_stream_parser.py` 89% |
| `source .venv/bin/activate && pytest tests/engine/runners/openai -q` | `270 passed` |
| `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | pass |
| `rg -n 'unknown_finish_reason\|FinishReason\\.STOP\|finish_reason or FinishReason\\.STOP' dayu/engine/runners/openai tests/engine/runners/openai` | no `unknown_finish_reason`; no `finish_reason or FinishReason.STOP`; remaining `FinishReason.STOP` hits are explicit `"stop"` mapping or positive assertions |

## Decision

The accepted S1 code-review findings are fixed pending independent re-review.
