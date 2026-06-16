# WU-CLI-FINS-OBS-01 Slice E Implementation

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: E, README / design-adjacent docs / tests synchronization
- Implementer: AgentCodex
- Date: 2026-06-16
- Plan source: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`

## First-principles judgment

The implementation motivation is valid. Slices A-D changed the stable public semantics from CLI-facing durable jobs and sidecar events to direct `AsyncIterator[FinsEvent]`, while preserving tool awaiting through lightweight observation handles. Several README sections still described Fins direct or awaiting as durable job / job event / `request_cancel(job_id)` flows, so docs would mislead future implementers back into the rejected design.

## Changed files

- `dayu/README.md`
- `dayu/service/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

## Implementation summary

- Updated top-level architecture text to distinguish:
  - direct Fins commands: `AsyncIterator[FinsEvent]`, `PROGRESS`, unique terminal `RESULT`, operation-scoped cancellation;
  - Fins awaiting tools: `ToolAwaitingOutcome(EXTERNAL_JOB)` plus lightweight observation handle;
  - legacy job-store helpers: still present in runtime foundation, but not Service direct or awaiting tool public semantics.
- Updated Service README so `dayu.service.fins_direct` no longer claims job handle, sidecar, terminal fallback polling, or `request_cancel(job_id)` semantics.
- Updated Fins README to document direct stream API, observation handle API, wait adapter mapping, process-local recovery/lost behavior, and the remaining legacy job-store helpers with explicit scope.
- Post-review cleanup addressed DS-E01 by changing the Fins README caller example from legacy `start_*` calls to recommended direct `async for` stream consumption, with observation-handle and legacy job-store examples explicitly separated.
- Updated Tests README so Fins direct, ingestion runtime, and awaiting tool tests describe current ownership: direct stream tests, observation handle tests, bounded transient/lost tests, and legacy job-store coverage where it still exists.

## README Boundary Check

- `dayu/README.md`: has explicit Agent update constraints; only cross-package stable boundary text was changed.
- `dayu/fins/README.md`: has explicit Agent update constraints; updated current `dayu.fins` capability, public contracts, stable boundaries, state paths and extension guidance.
- `tests/README.md`: has explicit update boundary; updated current test ownership descriptions.
- `dayu/service/README.md`: has no explicit Agent update constraints; limited edits to current stable Service boundary descriptions.

## Validation

```text
source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q
281 passed, 3 warnings

source .venv/bin/activate && pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
clean
```
