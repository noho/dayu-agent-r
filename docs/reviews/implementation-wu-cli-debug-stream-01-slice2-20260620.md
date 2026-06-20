# WU-CLI-DEBUG-STREAM-01 Slice 2 Implementation

## Scope

- Work unit: `WU-CLI-DEBUG-STREAM-01`
- Gate: `implementation`
- Slice: `2 - Host / Engine stream diagnostics level migration`
- Plan artifact: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- Accepted plan commit: `61bc9a9d`
- Accepted Slice 1 commit: `f53762a5`

## Changed Files

- `dayu/host/engine_ingest.py`
  - Host ingest delta event diagnostics now use `STREAM_DEBUG_LOG_LEVEL`.
  - Non-delta ingest diagnostics remain `VERBOSE_LOG_LEVEL`.
- `dayu/engine/runners/openai/runner.py`
  - `runner.stream_idle.heartbeat` moved from ordinary `DEBUG` to `STREAM_DEBUG_LOG_LEVEL`.
  - Runner lifecycle and HTTP diagnostics remain ordinary `DEBUG`.
- `dayu/engine/runners/openai/sse_parser.py`
  - `sse.done_token received` moved from ordinary `DEBUG` to `STREAM_DEBUG_LOG_LEVEL`.
- `tests/host/test_logging.py`
  - Renamed the delta ingest level test to stream-debug-specific wording.
  - Added coverage that ordinary `DEBUG` does not capture stream-debug delta records, while `STREAM_DEBUG` does.
- `tests/engine/runners/openai/test_runner_diagnostics.py`
  - Added coverage that ordinary `DEBUG` still captures runner attempt and HTTP diagnostics.
  - Added coverage that stream idle heartbeat and SSE done-token diagnostics require `STREAM_DEBUG_LOG_LEVEL`.

## Docs Decision

No README files were modified in Slice 2.

Reason: this slice only migrates Host / Engine internal diagnostic log levels. The user-visible CLI flag and README work belong to Slice 1 / Slice 4 per the accepted plan, and the user explicitly prohibited README changes for this slice.

`docs/host/issues-implementation-control.md` was not modified because it is controller-owned and explicitly out of scope.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q`
  - Passed: `13 passed in 0.72s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Passed

## Residual Risks / Uncovered Areas

- This slice did not run the entire test suite; validation was limited to the required affected tests plus full pyright.
- Existing stream idle tests outside the allowed file list still use old wording in comments or test names; they were not modified to respect the Slice 2 allowed-file boundary.
- This slice did not exercise CLI `--debug-stream` end-to-end because CLI/runtime files and prompt/interactive tests are outside Slice 2.
