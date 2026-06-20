# WU-CLI-DEBUG-STREAM-01 Final Closeout

## Verdict

WU-CLI-DEBUG-STREAM-01 is ready for the draft PR gate.

All planned slices passed implementation review and aggregate deepreview. No must-fix findings remain.

## Delivered

- Added global CLI `--debug-stream`.
- Added runtime `STREAM_DEBUG` logging level below ordinary `DEBUG`.
- Configured `--debug-stream` to be the strongest verbosity request and to include ordinary DEBUG diagnostics.
- Moved high-frequency stream diagnostics to stream-debug level:
  - Host ingest `content_delta` / `reasoning_delta` / `tool_call_delta`.
  - OpenAI runner stream idle heartbeat.
  - OpenAI SSE done-token diagnostic with `provider_request_id`.
- Kept lifecycle / HTTP DEBUG diagnostics and warnings at their existing levels.
- Added prompt / interactive guards proving `--debug-stream` is a global logging flag, not an unsupported legacy Agent execution option, and does not pollute stdout.
- Updated root README and tests README for user-visible behavior and test coverage responsibilities.

## Reviews

- Slice 1 re-review: PASS from AgentMiMo and AgentDS.
- Slice 2 re-review: PASS from AgentMiMo and AgentDS.
- Slice 3 code review: PASS from AgentMiMo and AgentDS.
- Slice 4 code review: PASS from AgentMiMo and AgentDS.
- Aggregate deepreview: PASS from AgentMiMo and AgentDS.

## Final Validation

- `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - Result: 159 passed, 3 existing third-party edgar deprecation warnings.
- `python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: clean.

## Residual Risks

- `WU-CLI-DEBUG-STREAM-01-R1`: future stream diagnostic sites could accidentally use ordinary DEBUG. Status: deferred-with-owner. Owner: future WU review gates for new Host / Engine stream diagnostics. Current mitigation: tests lock current stream diagnostic sites and README defines the `--debug` / `--debug-stream` split.
- `WU-CLI-DEBUG-STREAM-01-R2`: pre-existing root README `--log-level critical` mismatch with current parser choices. Status: deferred-with-owner. Owner: future CLI docs / parameter alignment work. Current WU did not introduce or worsen this mismatch.

## Explicit Non-Scope

`memory_repair.catch_up.budget_exhausted` is an already-fixed bug, not a noise item for this WU. Current code has no `BUDGET_EXHAUSTED` stop reason, and aggregate deepreview found no regression evidence.
