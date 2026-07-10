# WU-SEMANTIC-OWNERSHIP-01 P3-H aggregate validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Accepted plan commit: `ba607309`
- Accepted implementation commits:
  - S1 Web search provider facts and Web tool projection text: `35be9dc3`
  - S2 Fins direct stream and wait visible-language owner: `86034f4f`
  - S3 SEC downloader diagnostics, README decision, and aggregate scans: `c2d66c48`

## Controller Result

P3-H implementation slices are complete and ready for aggregate deepreview.

All accepted S1, S2, and S3 code-review findings have been fixed and re-reviewed where required.

## Validation Summary

- S1 validation:
  - Affected Web tests: `44 passed, 1 skipped, 3 warnings`
  - Pyright: `0 errors`
  - Source scans and propagation audit passed.

- S2 validation:
  - S2 matrix: `215 passed, 3 warnings`
  - `dayu/fins/direct_event_text.py` coverage: `86%`
  - Pyright: `0 errors`
  - Source scans and propagation audit passed.

- S3 / aggregate validation:
  - SEC focused tests: `47 passed`
  - P3-H aggregate matrix: `306 passed, 1 skipped, 3 warnings`
  - Pyright: `0 errors`
  - `git diff --check`: passed
  - Required source scans passed with only documented allowed hits.

## Source Scan Summary

- DS12 ToolRuntime hidden hint protocol: no matches.
- Web provider LLM next-action prose / derived output fields: no provider-internal matches.
- Web cancellation helper migration: no obsolete `web_cancellation_text.py` import/module remains; helper and consumer/test hits are allowed.
- Web tools local cancellation literals: no matches.
- Fins direct/wait hardcoded prose: only docstring matches in `ingestion_runtime.py`; no direct-stream or wait-outcome hardcoded prose remains.
- Fins job sidecar text: retained by runtime job lifecycle/audit owner and not counted as direct/wait cleanup.
- SEC downloader CLI command names: no `dayu-cli` matches in `dayu/fins/downloaders` or `tests/fins`.

## README Decision

- `dayu/fins/README.md` was checked during S2/S3 and did not require updates.
- `tests/README.md` was checked during S1/S2/S3 and did not require updates.
- Root `README.md` and `dayu/README.md` did not require updates because P3-H did not change user commands, public workflows, package layering, or cross-package architecture.

## Propagation Audit

- Web search: provider produces facts only; `web_search_projection.py` builds LLM-facing search output; tool outcome carries the projected JSON.
- Web cancellation/declaration: `web_tool_projection_text.py` owns cancellation/recovery text; `@tool(...)` declarations remain the display metadata owner.
- Fins direct: runtime emits typed operation/status/count/payload facts; `direct_event_text.py` supplies direct progress/result text; Service/CLI direct stream consumes `FinsEvent` text derived from the helper.
- Fins wait: observation snapshots carry status/result/error facts; wait adapter maps typed facts to Host outcomes and consumes helper text for failed/cancelled LLM-facing outcomes.
- Fins job sidecar: runtime job lifecycle/audit sidecar messages remain with runtime owner and are not projected through direct stream or wait outcome in this WU.
- SEC diagnostics: downloader reports missing `SEC_USER_AGENT` / caller configuration fact; CLI command names remain outside downloader diagnostics.

## Residual Risk

- Third-party `edgar` deprecation warnings remain unrelated to P3-H.
- Aggregate scans are bounded evidence checks, not a substitute for the later full-repository deepreview rounds required by the umbrella WU.
