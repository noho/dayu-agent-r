# WU-CLI-FINS-OBS-01 Slice E Review Fix

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: E, README / design-adjacent docs / tests synchronization
- Gate: review fix
- Implementer: AgentCodex
- Date: 2026-06-16

## Review Inputs

- `docs/reviews/wu-cli-fins-obs-01-slice-e-review-mimo-20260616.md`
- `docs/reviews/wu-cli-fins-obs-01-slice-e-review-ds-20260616.md`

## Adjudication

Both reviews passed with no blocking findings.

Accepted non-blocking cleanup:

- DS-E01: `dayu/fins/README.md` caller example still showed legacy `start_download` / `start_preprocess` / `start_upload` calls in the direct caller section.

## Fix

- Updated the Fins README caller example to show recommended direct stream consumption with `async for event in ingestion.download(...)`, `ingestion.preprocess(...)`, and `ingestion.upload(...)`.
- Added a separate observation-handle flow sketch for `start_fins_download` / `start_fins_preprocess` / `start_fins_upload`.
- Kept the legacy `start_download(...)` example only under an explicitly labeled legacy job-store helper section.

## Validation

```text
source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q
281 passed, 3 warnings

source .venv/bin/activate && pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
clean
```
