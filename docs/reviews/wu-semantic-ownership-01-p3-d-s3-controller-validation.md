# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Controller Validation

## Scope

- Slice: `S3 - Typed Engine error codes and propagation audit`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-implementation-codex.md`
- Controller decision: implementation gate returned; ready for independent code review.

## Validation

- `source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py -q`
  - Result: `149 passed in 0.19s`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_public_host_event.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_projection.py -q`
  - Result: `155 passed in 1.52s`
- `source .venv/bin/activate && pytest tests/engine -q`
  - Result: `514 passed in 2.04s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- Coverage command for S3 touched files:
  - Result: `669 passed in 4.84s`
  - Touched production file coverage:
    - `dayu/engine/agent.py`: 89%
    - `dayu/engine/contracts/agent_run.py`: 99%
    - `dayu/engine/contracts/engine_events.py`: 99%
    - `dayu/engine/contracts/error_codes.py`: 97%
    - `dayu/engine/runners/openai/non_stream_parser.py`: 93%
    - `dayu/engine/runners/openai/sse_parser.py`: 93%
    - `dayu/engine/runners/openai/tool_call_aggregator.py`: 89%
    - `dayu/host/engine_ingest.py`: 91%
  - Note: package `__init__.py` files are aggregate export surfaces covered by package export tests, not independent business logic files. Low coverage entries from untouched OpenAI helper modules were introduced by package-level coverage expansion and are not S3 touched files.

## Source Scans

- `rg -n "error_code: str|error_code=\"|error_code=data\\.error_code" dayu/engine dayu/host tests/engine tests/host`
  - No remaining `dayu/engine/contracts` public error-code field is `str`.
  - Remaining `dayu/engine/runners/openai/_choice_policy.py` and parser `error_code: str` hits are adapter-private values wrapped before `RunnerProtocolErrorData`.
  - Remaining `dayu/engine/agent.py` `error_code=data.error_code` hits are typed union / wrapper pass-through.
  - Host/test hits are durable text, Host-owned status/error fields, or test projection values.
- `rg -n "RunFailedData\\(|EngineRunOutcomeFailed\\(|ProviderProtocolErrorData\\(|RunnerProtocolErrorData\\(" dayu/engine tests/engine`
  - Constructors now use enum members or wrapper constructors; weak-typing guard covers future literal string regressions.
- `rg -n "error_code|provider_error_code|failure_metadata" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py dayu/host/outbox.py tests/host`
  - Host ingest serializes typed Engine codes through `serialize_engine_error_code(...)`.
  - Read API, Tool Trace, and Outbox consume durable serialized text only.
- `rg -n "_ERROR_|runner_error_done_without_detail|context_compaction_required|provider_error_code" dayu/engine dayu/host tests`
  - `_ERROR_*` constants are typed `EngineRunErrorCode` enum members.
  - `provider_error_code` remains durable/read/tool-trace text and tests; Host does not branch on wrapper internals.
- LLM-facing leakage narrow scan across config, memory, compact, run input, terminal answer, and accepted-result projection returned no hits.

## Propagation Audit

- Provider protocol code is produced by the adapter and wrapped as `RunnerSpecificErrorCode` before entering public Runner events.
- Agent failure candidates carry `EngineRunErrorCode | RunnerSpecificErrorCode`; bare strings are rejected by dataclass runtime checks.
- Engine `run_failed` and `EngineRunOutcomeFailed` keep the typed union until Host/public boundary serialization.
- Host `RUN_FAILED` ingest and provider protocol failure metadata call `serialize_engine_error_code(...)` before durable JSON writes.
- Tool Trace, Read API, public Host events, and Outbox read durable serialized text, not wrapper internals.
- Memory, compact material, accepted result projection, terminal answer, run input, and config/prompt paths do not receive typed error-code internals or provider diagnostic identifiers.

## Residual Risk

- S3 intentionally breaks old string-only Engine construction compatibility; this matches the approved non-goal/prohibition.
- Provider-specific code source remains internal to Engine typed wrapper and is serialized to text at Host boundary. Any future public exposure of wrapper source requires a new Host/Engine public contract decision.
