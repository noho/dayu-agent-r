# WU-CLI-FINS-OBS-01 Slice D Implementation

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: D, Fins tool awaiting and wait adapter lightweight handle
- Implementer: Codex
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan source: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- Control source: `docs/host/issues-implementation-control.md`

## First-principles judgment

The implementation motivation is valid. Before this slice, Fins awaiting tools and `FinsIngestionWaitPollAdapter` still treated `ToolAwaitSpec.resume_token` as a durable Fins job id and resolved waits through `read_job(...)` / `request_cancel(...)`. That conflicts with the accepted Slice D0 contract: tool awaiting only needs a lightweight, process-local observation handle; it does not justify durable Fins job records, job event sidecars, or cross-restart recovery.

## Changed files

- `dayu/fins/ingestion/observation_handle.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/tools/_ingestion_tool_helpers.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/ingestion/__init__.py`
- `dayu/service/host_assembly.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`

## Implementation summary

- Added a classified `FinsObservationPollError` and kept observation handle parsing opaque and handle-id based.
- Added process-local observation registry support to `FinsIngestionRuntime`:
  - `start_observed_download(...)`
  - `start_observed_preprocess(...)`
  - `start_observed_upload(...)`
  - `poll_observation(...)`
  - `cancel_observation(...)`
  - `abandon_observation(...)`
- Reused the existing runtime business producers for observed operations, but registered only process-local observation records and snapshots. The observed path does not write durable job records or job event sidecars for wait observation.
- Migrated download / preprocess / upload awaiting tools to call `start_observed_*` and to return `ToolAwaitingOutcome(EXTERNAL_JOB)` with `observation_handle_id_to_resume_token(handle)`.
- Rewrote the Fins wait adapter to parse `resume_token` as an observation handle token, call async observation runtime poll/cancel/abandon from its sync Host adapter boundary, and map:
  - `SUCCEEDED` -> `ResolveWaitCompletedOutcome`
  - `FAILED` -> `ResolveWaitFailedOutcome`
  - `CANCELLED` -> `ResolveWaitCancelledOutcome`
  - `LOST`, corrupt token, or missing handle -> `ResolveWaitLostOutcome`
- Added bounded transient unavailable handling: transient observation poll failures remain not-ready only inside a fixed window; after that, the adapter resolves LOST instead of pending forever.
- Updated tests away from `resume_token == job_id`, `read_job(job_id)`, and `request_cancel(job_id)` assertions.
- Controller integration fixed the remaining import-cycle root cause after implementation: `dayu.fins.ingestion.__init__` no longer eagerly re-exports wait-adapter symbols, because importing `observation_handle` through the package was loading `wait_adapter -> service_runtime -> ingestion_runtime`. Adapter symbols now import from `dayu.fins.ingestion.wait_adapter` directly in Service assembly and tests. This removes the need for runtime function-local imports and keeps observation contract importable as a lower-level contract module.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `107 passed`, 3 third-party deprecation warnings from `edgar`.
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
  - Result: `45 passed`, 3 third-party deprecation warnings from `edgar`.
- `source .venv/bin/activate && pyright dayu/fins/tools/download_tools.py dayu/fins/tools/preprocess_tools.py dayu/fins/tools/upload_tools.py dayu/fins/tools/_ingestion_tool_helpers.py dayu/fins/ingestion/wait_adapter.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py`
  - Result: `0 errors, 0 warnings`.
- `python -c "import dayu.fins.ingestion_runtime; import dayu.fins.ingestion; print('ok')"`
  - Result: `ok`.
- Controller post-integration validation:
  - `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_host_assembly.py -q`
  - Result: `152 passed`, 3 third-party deprecation warnings from `edgar`.
  - `source .venv/bin/activate && pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings`.
- `git diff --check`
  - Result: clean.

## README impact

- `dayu/fins/` changed, so `dayu/fins/README.md` was checked. Its update boundary says it should describe current stable package capability and architecture, not work-unit process details.
- `dayu/service/` changed by import-boundary cleanup, so `dayu/service/README.md` was checked. It has no explicit Agent update boundary. Its existing Fins direct wording is already superseded by earlier accepted slices, but replacement plan assigns cross-README consistency to Slice E.
- `tests/` changed, so `tests/README.md` was checked. Its boundary covers current test layering and maintenance conventions.
- No README was edited in this Slice D implementation because the accepted plan and user instruction allow the larger docs synchronization to remain in Slice E. The existing Fins README still contains durable ingestion job wording that Slice E should reconcile with the new direct stream / business summary / lightweight observation split.

## Residual risk

- The process-local observation registry is intentionally not cross-restart durable. Missing handles resolve LOST as required.
- Observed operations reuse the existing bounded direct-event queue. A very slow or absent poller can delay a highly chatty observed producer once the bounded queue is full. This is acceptable for the current lightweight local observation contract, but a future production poller/backoff work unit may want a coalescing progress snapshot instead of event buffering.
- README consistency is deferred to Slice E as planned.

## Completion status

Slice D implementation is complete locally and not committed.
