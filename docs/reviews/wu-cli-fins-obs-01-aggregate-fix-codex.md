# WU-CLI-FINS-OBS-01 Aggregate Deepreview Fix

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: aggregate deepreview fix
- Input adjudication: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-adjudication-20260615-210618.md`
- Output file: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`
- Accepted fixes only: `AGG-FIX-01`, `AGG-FIX-02`, `AGG-FIX-03`
- Deferred / accepted-risk items: not changed

## Changed Files

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/cli/test_fins_commands.py`
- `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`

## Fix Decisions

### AGG-FIX-01 Corrupted Fins job event sidecar line

Status: 已修复。

- `FsFinsIngestionJobStore._iter_event_records_locked(...)` now skips malformed JSONL rows, non-object JSON rows, and rows that fail typed event record validation.
- Each skipped row records a bounded warning with sidecar kind, sidecar suffix, line number, error type, and fixed error summary.
- The warning does not include sidecar payload values, job id, or file path values.
- Valid event records still require strictly increasing `sequence`; non-monotonic valid records still raise `ValueError`.
- Later `append_job_event(...)` uses the last valid record sequence and can continue after corrupted rows.

Tests added:

- `test_job_event_sidecar_skips_corrupted_rows_and_append_continues`
- `test_job_event_sidecar_still_rejects_non_monotonic_valid_records`

### AGG-FIX-02 CLI synthetic terminal fallback rendering coverage

Status: 已修复。

- CLI Fins direct fake service can now emit a Service-produced synthetic terminal fallback event with `event_label="job_terminal_fallback"`.
- Added CLI-level test proving the event is rendered as a terminal success and `cli_main.main(...)` returns the terminal exit code.

Test added:

- `test_live_fins_command_renders_synthetic_terminal_fallback_and_exit_code`

### AGG-FIX-03 `_LOGGER` constant annotation consistency

Status: 已修复。

- `dayu/fins/ingestion_runtime.py` now annotates `_LOGGER` as `Final[logging.Logger]`.
- Pyright was run on the affected production and test files.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q
source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py
git diff --check
```

Results:

- Pytest: `83 passed`, with three third-party `edgar` deprecation warnings.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Docs Decision

- `dayu/fins/README.md` checked under its Agent update constraints.
- `tests/README.md` checked under its update boundary.
- No README update needed: no public architecture, public interface, test layer, or documented command surface changed. The new tests only cover existing event sidecar and Fins direct CLI behavior.

## Residual Risks

- DS finding 3 `_is_summary_key_allowed` conservative substring matching: accepted-risk per adjudication, not changed.
- DS finding 5 synchronous `request_cancel` in SIGINT coroutine: deferred per adjudication, not changed.
- DS finding 6 repeated RUNNING claim `updated_at`: deferred per adjudication, not changed.
- DS finding 7 `_last_event_sequence_locked` O(N) append scan: deferred per adjudication, not changed.
- DS finding 8 mutable `FINS_DIRECT_SERVICE_FACTORY` test seam: accepted-risk per adjudication, not changed.

All residual risks are classified by the controller adjudication; none is newly introduced by this fix pass.

## Completion Status

Aggregate deepreview accepted fixes are implemented and locally validated.
