# WU-CLI-FINS-OBS-01 Closeout

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Topic: Fins Direct CLI Live Event Stream / Log / UI Print
- Owner / destination: user-directed immediate residual; no GitHub Issue
- Closeout time: 2026-06-15 21:20:45 Asia/Shanghai

## Accepted Commits

- Slice S1 Fins job event contract and store: `3787f43d`
- Slice S2 runtime-owned progress events: `123a7db8`
- Slice S3 Service Fins direct event subscription: `4164b4da`
- Slice S4 CLI event consumer, UI print, and cancel semantics: `e597d8e8`
- Slice S5 CLI logging assembly and command UI/log audit: `8d93dc68`
- Slice S6 README sync: `2d4679af`
- Aggregate deepreview fix: `804b3b7d`

## Delivered Behavior

- Fins direct commands consume Service-projected job events and render live progress / terminal summaries through CLI UI output.
- Fins job events are Fins-owned sidecar JSONL observation records, not Host EventLog, Host truth, Engine stream, or provider raw event stream.
- Service owns event observation and terminal fallback; CLI remains a UI consumer and does not read Fins storage directly.
- Ctrl+C still requests durable Fins job cancel; second Ctrl+C exits locally with job id context.
- CLI main restores runtime log assembly for `--debug`, `--verbose`, `--quiet`, and `--log-level`.
- Logs remain diagnostics; progress / terminal results remain UI output.
- README files now describe the stable landed boundaries.

## Final Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/runtime/test_log.py -q`
  - Result: `210 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py dayu/service/fins_direct.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/cli/output.py dayu/runtime/log.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/runtime/test_log.py`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

## Residual Risk Reconciliation

- Fine-grained pipeline stream consumption remains outside this work unit by approved plan scope. Current runtime emits coarse progress events; future high-frequency event streaming should revisit sidecar write/read scalability.
- `_last_event_sequence_locked` remains O(N) over valid sidecar rows. This is deferred because current event volume is bounded and correctness is covered.
- `_is_summary_key_allowed` remains conservative and may over-redact some business keys. This is accepted-risk because relaxing it can leak path/raw/content fields and needs a separate redaction policy review.
- CLI synchronous cancel request inside SIGINT handling remains deferred. Fixing it would alter cancel concurrency semantics and should be handled by a dedicated cancel responsiveness work unit if needed.
- Prompt / interactive token/content streaming remains outside this work unit by accepted scope; prompt / interactive terminal output was preserved and tested.

These items are mirrored in `docs/host/issues-implementation-control.md` as `WU-CLI-FINS-OBS-01-R1` through `WU-CLI-FINS-OBS-01-R5`.

## Closeout Decision

All accepted slice findings and aggregate findings are closed. No unowned blocker remains for this work unit. Proceed to draft PR gate.
