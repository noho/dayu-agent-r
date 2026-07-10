# WU-SEMANTIC-OWNERSHIP-01 P3-H S3 controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S3 - SEC downloader diagnostics, README decision, and aggregate scans`
- Prior accepted commits:
  - Plan: `ba607309`
  - S1: `35be9dc3`
  - S2: `86034f4f`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-s3-implementation-codex.md`

## Controller Result

Controller validation passes for S3 pending independent code review.

## Changed Boundary

- `dayu/fins/downloaders/sec_downloader.py` still owns the missing SEC User-Agent configuration diagnostic.
- The diagnostic now references the typed configuration fact `SEC_USER_AGENT` and caller/deployment configuration only.
- CLI command names remain outside downloader diagnostics and belong to CLI/help/docs owners.
- Fallback `_UNCONFIGURED_USER_AGENT`, request headers, rate limit behavior, and SEC download behavior are unchanged.

## Validation Commands

- `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py -q`
  - Result: `47 passed`

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_downloader.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`
  - Result: `306 passed, 1 skipped, 3 warnings`

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

- `git diff --check`
  - Result: passed

## Required Source Scans

- DS12 ToolRuntime hidden hint scan:
  - `rg -n "_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_hint_with_diagnostic_refs|hint=policy_decision\\.reason_code" dayu tests`
  - Result: no matches.

- Web provider LLM prose scan:
  - Provider internals: no matches.
  - Allowed test-only matches remain in `tests/tools/web/test_smoke_web_ci.py` and `tests/tools/web/test_web_tools_provider.py`.

- Web provider derived output field scan:
  - `rg -n "preferred_result_summary|next_action|next_action_args|\\\"hint\\\"" dayu/tools/web/web_search_providers.py`
  - Result: no matches.

- Web cancellation scan:
  - No obsolete `web_cancellation_text.py` module/import match.
  - Allowed `WEB_CANCELLED_HINT` hits remain in `web_tool_projection_text.py`, `web_tools.py`, and tests.

- Web tools local cancellation literal scan:
  - Result: no matches.

- Fins direct/wait prose scan:
  - Only two docstring matches in `dayu/fins/ingestion_runtime.py` exception documentation.
  - No direct-stream or wait-outcome hardcoded prose matches in `ingestion_runtime.py` or `wait_adapter.py`.

- Fins job sidecar scan:
  - Expected retained sidecar hits remain in `_append_job_event_warn(...)` and job lifecycle helpers.
  - These are durable job/audit sidecar text and were not counted as moved direct/wait copy.

- SEC downloader CLI-name scan:
  - `rg -n "dayu-cli init|dayu-cli" dayu/fins/downloaders tests/fins`
  - Result: no matches.

## README Decision

- AgentCodex read `dayu/fins/README.md` update constraints and made no update. S3 changes an existing downloader diagnostic, not a stable Fins developer-facing boundary.
- AgentCodex read `tests/README.md` update constraints and made no update. The new assertion belongs to an existing Fins downloader test file and does not add a new testing layer.
- Root `README.md` and `dayu/README.md` were not changed because S3 does not change user commands, public workflow, package layering, or cross-package architecture.

## Propagation Audit

- SEC diagnostic producer: `_resolve_user_agent(...)` detects missing configured User-Agent and emits a warning about `SEC_USER_AGENT` / caller-deployment configuration.
- CLI/user docs owner: command names such as `dayu-cli init` are not emitted by SEC downloader diagnostics.
- User-visible diagnostic: warning text no longer carries CLI command names.
- Downloader behavior: fallback User-Agent and subsequent request header construction remain unchanged.

## Residual Risk

- No current S3 residual risk remains.
- Aggregate scans are bounded evidence checks; they do not replace later full-repository deepreview rounds required by the umbrella WU.
