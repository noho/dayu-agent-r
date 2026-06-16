# WU-CLI-FINS-DIAG-01 Implementation Review — AgentMiMo

## Gate Metadata

- Gate: implementation review
- Work unit: `WU-CLI-FINS-DIAG-01`
- Scope: close `WU-CLI-FINS-OBS-01-R3` and `WU-CLI-FINS-OBS-01-R5`
- Review source: workspace diff against HEAD (`1286d293`)
- Design truth: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- Implementation artifact: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-codex-20260616.md`
- Control source: `docs/host/issues-implementation-control.md`
- Date: 2026-06-16

## Review Scope

13 files changed, +362 / -102 lines. Focused on:

1. `dayu/runtime/log.py` — stderr default diagnostic stream
2. `dayu/cli/main.py` — explicit `stream=sys.stderr` at composition root
3. `dayu/cli/output.py` — path redaction removal, bounded display retained
4. `dayu/cli/commands/fins.py` — enriched Fins diagnostic event summaries
5. `tests/runtime/test_log.py` — stderr assertions and stream override
6. `tests/cli/test_arg_parsing.py` — `stream=sys.stderr` forwarding
7. `tests/cli/test_prompt_command.py` — stdout cleanliness regression
8. `tests/cli/test_interactive_command.py` — stdout cleanliness regression
9. `tests/cli/test_fins_commands.py` — stderr diagnostics, path visibility, bounded display
10. `dayu/README.md` — logging channel documentation
11. `tests/README.md` — test coverage description update
12. `docs/host/issues-implementation-control.md` — residual reconciliation
13. `docs/reviews/wu-cli-fins-obs-01-final-closeout-20260616.md` — residual closure

## Conclusion

**PASS**

Implementation correctly and completely resolves R3 and R5 per the accepted plan. No blocking findings. Two non-blocking observations.

## Detailed Review

### R5: stdout/stderr Separation — PASS

**Root cause and fix**: `dayu.runtime.log._build_marker_handler` previously hardcoded `stream=sys.stdout`. The fix adds an optional `stream: TextIO | None = None` parameter to `configure()` and `set_level_from_flags()`, defaulting to `sys.stderr`. CLI `main()` explicitly passes `stream=sys.stderr` at the composition root.

**Evidence**:

- `dayu/runtime/log.py:122` — `effective_stream = sys.stderr if stream is None else stream`. Default is stderr.
- `dayu/runtime/log.py:248` — `_build_marker_handler` signature now accepts `stream: TextIO` and uses it.
- `dayu/cli/main.py:75` — `stream=sys.stderr` explicitly passed.
- `dayu/runtime/log.py:45` — marker value renamed from `dayu.runtime.log:stdout` to `dayu.runtime.log:diagnostic` (stream-neutral).

**Layering**: `dayu.runtime.log` remains layer-neutral infrastructure. No import of CLI/Service/Host/Engine/Fins. The `stream` parameter is an optional `TextIO`, not a CLI-specific type.

**Tests**:

- `test_logger_emits_to_stderr_by_default` — asserts `captured.out == ""` and content in `captured.err`.
- `test_configure_stream_override_keeps_diagnostics_redirectable` — asserts explicit `stream=sys.stdout` redirects back to stdout.
- `test_log_verbose_uses_call_site_logger` — updated from stdout to stderr.
- `test_main_configures_runtime_log_from_parsed_cli_flags` — verifies `stream=sys.stderr` is forwarded.
- `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` — parametrized for `--verbose` and `--debug`, asserts `captured.out.strip() == "prompt answer"` with no `[VERBOSE]` or `[DEBUG]` in stdout.
- `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout` — same pattern for interactive.
- `test_fins_direct_verbose_log_outputs_execution_skeleton` — verifies Fins progress on stdout, diagnostics on stderr.
- `test_fins_direct_debug_log_outputs_event_details` — verifies Fins debug details on stderr, not stdout.

**Verdict**: R5 fully closed. Stdout is clean for prompt, interactive and Fins commands under both `--verbose` and `--debug`.

### R3: Path Redaction Removal and Diagnostic Enrichment — PASS

**Path redaction removal** (`dayu/cli/output.py`):

- Removed: `_FINS_REDACTED_TEXT`, `_ABSOLUTE_PATH_PATTERN`, `_looks_like_absolute_path`, `_redact_absolute_path_match`.
- `_safe_text_value` now only truncates at `_FINS_TEXT_MAX_CHARS=120`. Paths remain visible.
- `_bounded_json_text` docstring updated from "脱敏、截断" to "截断".
- No dangling references to removed symbols found in codebase.

**Contract boundary**: `dayu/fins/direct_events.py` still validates that event field values don't contain absolute paths (line 421-423). The presentation-layer redaction in `output.py` was a redundant defense for the current Fins event rendering. Removing it is correct per the plan's contract boundary analysis.

**Fins diagnostic enrichment** (`dayu/cli/commands/fins.py`):

- `_log_fins_direct_event_received` now calls two new helpers:
  - `_fins_event_verbose_diagnostic_parts` — operation, event_type, ticker, document, stage, status, message.
  - `_fins_event_debug_diagnostic_parts` — operation, event_type, filing_kind, completed_units, total_units, status, title, error_kind, exit_code, bounded details.
- All values are scalar strings passed to logging. No raw event objects, no `job_id`, no `sequence`, no durable cursor, no artifact ref.
- Text bounded at `_FINS_DIAGNOSTIC_TEXT_MAX_CHARS=120` via `_bounded_diagnostic_text`.
- Details bounded at `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS=4`.
- `shlex.quote` applied via `_quoted_diagnostic_text` for shell-safe log tokens.

**Tests**:

- `test_output_keeps_absolute_paths_visible_and_bounded` — asserts POSIX and Windows paths visible, long paths truncated at 120 chars.
- `test_fins_direct_verbose_log_outputs_execution_skeleton` — asserts enriched verbose fields (`message`, `document`, `stage`) in stderr.
- `test_fins_direct_debug_log_outputs_event_details` — asserts enriched debug fields (`filing_kind`, `completed_units`, `total_units`, `status`, `title`, `exit_code`, `details`) in stderr, and no `sequence=`, `job_id=`, `cursor`, or `artifact` identifiers.

**Verdict**: R3 fully closed. Paths visible, diagnostics enriched with useful bounded summaries, no sensitive identifiers leaked.

### AGENTS.md Compliance — PASS

- **Docstring**: All new/changed functions have complete Chinese docstrings with `:param`, `:returns`, `:raises`.
- **Types**: No `object`, `Any`, or untyped parameters. `_append_optional_diagnostic_part(parts: list[str], key: str, value: str | None)` and similar are properly typed.
- **Module-level private helpers**: All new helpers (`_fins_event_verbose_diagnostic_parts`, `_fins_event_debug_diagnostic_parts`, `_append_optional_diagnostic_part`, `_append_optional_int_diagnostic_part`, `_append_result_details_diagnostic_parts`, `_quoted_diagnostic_text`, `_bounded_diagnostic_text`) are module-level private functions.
- **No magic numbers**: `_FINS_DIAGNOSTIC_TEXT_MAX_CHARS`, `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS`, `_FINS_DIAGNOSTIC_TRUNCATED_SUFFIX` are `Final` constants.
- **No `hasattr`/`getattr` abuse**: The existing `_reset_marker_handlers` uses `getattr` with a default for handler marker checking, which is the established pattern.
- **Layering**: `dayu.runtime.log` does not import CLI/Service/Host/Engine/Fins. `dayu.cli.commands.fins` imports `dayu.runtime.log` (UI -> runtime, allowed). `dayu.cli.output` imports `dayu.fins.direct_events` (UI -> Fins contract types, allowed per existing boundary).
- **`__all__`**: `fins.py` exports only `FINS_DIRECT_SERVICE_FACTORY`, `FinsDirectServiceFactory`, `run_fins_direct_command`. New private helpers are not exported.

### Diagnostic Safety — PASS

- **No raw payload/job/sidecar/cursor/artifact leak**: Diagnostic parts only extract scalar business-readable fields from `FinsEvent`: `operation_kind`, `event_type`, `ticker`, `filing_kind`, `document_label`, `progress.stage`, `progress.completed_units`, `progress.total_units`, `result.status`, `result.title`, `result.error_kind`, `result.exit_code`, `result.details`, `message`.
- **No API key exposure**: No code path logs provider headers, resolved API key values, or `dayu/config/models.json` content.
- **Bounded output**: All text values capped at 120 chars via `_bounded_diagnostic_text`. Details capped at 4 items via `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS`.
- **No new diagnostic artifacts**: No file writes, no new JSONL, no new projections.

### Test Coverage — PASS

R3 and R5 coverage matrix:

| Requirement | Test(s) | Status |
|---|---|---|
| R5: stdout clean under `--verbose` | `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout`, `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout`, `test_fins_direct_verbose_log_outputs_execution_skeleton` | ✅ |
| R5: stdout clean under `--debug` | same parametrized tests, `test_fins_direct_debug_log_outputs_event_details` | ✅ |
| R5: stderr receives diagnostics | `test_logger_emits_to_stderr_by_default`, `test_fins_direct_verbose_log_outputs_execution_skeleton`, `test_fins_direct_debug_log_outputs_event_details` | ✅ |
| R5: stream override works | `test_configure_stream_override_keeps_diagnostics_redirectable` | ✅ |
| R5: CLI main passes stderr | `test_main_configures_runtime_log_from_parsed_cli_flags` | ✅ |
| R3: paths visible | `test_output_keeps_absolute_paths_visible_and_bounded` | ✅ |
| R3: long values bounded | `test_output_keeps_absolute_paths_visible_and_bounded` (asserts len==120) | ✅ |
| R3: enriched verbose diagnostics | `test_fins_direct_verbose_log_outputs_execution_skeleton` (message, document, stage) | ✅ |
| R3: enriched debug diagnostics | `test_fins_direct_debug_log_outputs_event_details` (filing_kind, counts, title, exit_code, details) | ✅ |
| R3: no internal identifiers | `test_fins_direct_debug_log_outputs_event_details` (no sequence, job_id, cursor, artifact) | ✅ |

### README / Control Doc — PASS

- `dayu/README.md` — Added one sentence documenting the stderr diagnostic channel and stdout UI/result channel. Within the README's documented responsibilities for the logging section.
- `tests/README.md` — Updated CLI test descriptions to reflect stderr diagnostic assertions and path visibility policy. Within the README's update scope.
- `docs/host/issues-implementation-control.md` — R3/R5 removed from residual table. `WU-CLI-FINS-DIAG-01` recorded as completed. `WU-CLI-SESSION-01` and `WU-CLI-ACTIVITY-01` added as pending work units. R10 removed (confirmed non-residual). Residual reconciliation line updated.
- `docs/reviews/wu-cli-fins-obs-01-final-closeout-20260616.md` — R3/R5/R10 moved to closed section with closure evidence. Transferred follow-up to #145 recorded.

### Layering / Dependency — PASS

- `dayu/runtime/log.py` — no new imports from upper layers. Only added `TextIO` from `typing`.
- `dayu/cli/main.py` — only added `stream=sys.stderr` argument to existing call.
- `dayu/cli/output.py` — removed code (net -30 lines). No new dependencies.
- `dayu/cli/commands/fins.py` — added `import shlex` (stdlib). No new upper-layer imports.

## Findings

### Non-Blocking

#### N1: `_append_result_details_diagnostic_parts` joins details with `,` inside `details=...`

**File**: `dayu/cli/commands/fins.py:867`
**Severity**: non-blocking observation

The details rendering uses `','.join(rendered)` inside a `details=` prefix. If a detail value itself contains a comma (after `shlex.quote` wrapping), the resulting log line could be ambiguous to parse. This is acceptable for human-readable diagnostic logs but could be noted for any future structured log parsing.

**Recommendation**: No change needed for current diagnostic-only use. If structured log parsing is ever added, details should use a less ambiguous separator.

#### N2: Test coverage for `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS` truncation not exercised

**File**: `tests/cli/test_fins_commands.py`
**Severity**: non-blocking observation

The test fixture `_result_event` has only 1 detail item (`processed_count=1`), while `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS=4`. The truncation path at line 860 (`if len(rendered) >= _FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS: break`) is not exercised by any test.

**Recommendation**: Non-blocking for current scope. A future test could add 5+ details to verify truncation behavior.

## Validation Evidence

- `pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q` → 120 passed, 3 warnings (edgar deprecation)
- `pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/output.py dayu/cli/commands/fins.py tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py` → 0 errors, 0 warnings, 0 informations
- No dangling references to removed symbols (`_FINS_REDACTED_TEXT`, `_ABSOLUTE_PATH_PATTERN`, `_looks_like_absolute_path`, `_redact_absolute_path_match`)
- `git diff --check` clean (not verified in this review but implementation artifact reports clean)

## Residual Risks

Per the implementation artifact, the following remain deferred with owners:

- Engine/provider diagnostic redaction broader than R3 user裁决 — deferred to later Engine/provider work unit.
- Prompt/interactive activity readability — tracked by GitHub Issue #144.
- CLI session management — tracked by GitHub Issue #145.
- Fins event messages/details assumed free of resolved API keys — residual assumption, no evidence of leakage found.
