# WU-SEMANTIC-OWNERSHIP-01 P3-D S1 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Slice: `S1 - Adapter choice and finish-reason policy`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s1-implementation-codex.md`
- Accepted plan commit: `c52519f0`
- Controller validation date: 2026-07-10

## Validation Commands

| Validation | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py --cov=dayu.engine.runners.openai.sse_parser --cov=dayu.engine.runners.openai.non_stream_parser --cov-report=term-missing -q` | `60 passed`; `sse_parser.py` 86%, `non_stream_parser.py` 89% |
| `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | pass |
| `rg -n 'unknown_finish_reason\|FinishReason\\.STOP\|finish_reason or FinishReason\\.STOP' dayu/engine/runners/openai tests/engine/runners/openai` | no `unknown_finish_reason`; no `finish_reason or FinishReason.STOP`; remaining `FinishReason.STOP` hits are explicit `"stop"` mapping or positive assertions |
| `rg -n '\\b(PROVIDER_DIAGNOSTIC\|provider_diagnostic\|memory\|compact\|evidence\|prompt\|final_answer\|LLM-facing)\\b' ...S1 touched files...` | no matches |
| `source .venv/bin/activate && pytest tests/engine/runners/openai -q` | `267 passed` |

## Propagation Audit

Semantic: OpenAI-compatible provider `choices` and `finish_reason`.

Path:

```text
provider wire response
  -> OpenAI adapter private choice policy
  -> SSE / non-stream parser normalized RunnerEvent
  -> Agent consumes RunnerEvent
  -> EngineEvent projection
  -> Host ingest / EventLog / read models
```

Controller finding:

- The first validation and normalization owner is the OpenAI-compatible Runner adapter.
- SSE now validates choice policy before state merge.
- Non-stream now validates response-level `choices` before selecting a choice.
- Unknown or invalid `finish_reason` no longer becomes `FinishReason.STOP`.
- Host / Agent downstream code does not need new provider-string special cases for this S1 semantic.
- This slice did not introduce provider diagnostics into memory, final answer, accepted evidence material, compact material, or prompt text.

## Decision

S1 implementation is ready for independent code review by AgentMiMo and AgentDS.
