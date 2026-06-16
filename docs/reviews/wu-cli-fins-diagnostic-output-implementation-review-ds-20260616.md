# WU-CLI-FINS-DIAG-01 Implementation Review — AgentDS

## Gate Metadata

- Gate: review
- Work unit: `WU-CLI-FINS-DIAG-01`
- Scope: close `WU-CLI-FINS-OBS-01-R3` (Fins path redaction) and `WU-CLI-FINS-OBS-01-R5` (stdout/stderr separation)
- Design truth: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- Implementation artifact: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-codex-20260616.md`
- Date: 2026-06-16
- Review type: adversarial deep review — stdout/stderr separation, path redaction removal, diagnostic leakage, AGENTS compliance, test coverage for R3/R5

## First-Principles Judgment

The implementation correctly addresses both residuals at root cause:

- **R5 root cause**: `dayu.runtime.log._build_marker_handler` hardcoded `sys.stdout` as the stream. Fix: `configure()` and `set_level_from_flags()` now accept optional `stream: TextIO | None`, defaulting to `sys.stderr`; CLI `main()` explicitly passes `stream=sys.stderr`.
- **R3 root cause**: `dayu/cli/output.py._safe_text_value` treated absolute paths as secrets via regex-based redaction. Fix: removed `_ABSOLUTE_PATH_PATTERN`, `_FINS_REDACTED_TEXT`, `_looks_like_absolute_path`, and `_redact_absolute_path_match`; kept bounded truncation only.

The implementation does not modify `dayu/fins/direct_events.py` (verified by `git diff HEAD -- dayu/fins/direct_events.py` returning empty), does not introduce durable jobs/sidecars/cursors, and does not expand scope into Engine/provider diagnostic redaction or activity UI.

## Adversarial Challenge Results

### Challenge 1: stdout/stderr Separation

**Result: PASS**

- `dayu/runtime/log.py` line 122: `effective_stream = sys.stderr if stream is None else stream` — default is stderr.
- `dayu/cli/main.py` line 75: `stream=sys.stderr` passed explicitly.
- `_HANDLER_MARKER_VALUE` renamed from `"dayu.runtime.log:stdout"` to `"dayu.runtime.log:diagnostic"` (line 45) — stream-neutral naming.
- `_build_marker_handler` signature changed from `(level)` to `(level, stream)` — no hidden stdout default.
- Zero `sys.stdout` references remain in `dayu/runtime/log.py` or `dayu/cli/main.py` (grep confirmed).
- `_build_marker_handler` is only called from `configure()` (verified by grep); no external callers broken.
- `utils/smoke_web_ci.py` calls `configure(level=options.log_level, configure_root=True)` without `stream` — correctly falls through to `sys.stderr` default.

### Challenge 2: prompt/interactive stdout Cleanliness

**Result: PASS**

- `tests/cli/test_prompt_command.py`: `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` (lines 501-530) parametrized with `--verbose` and `--debug`, verifies `captured.out.strip() == "prompt answer"` and `[VERBOSE]`/`[DEBUG]` not in stdout.
- `tests/cli/test_interactive_command.py`: `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout` (lines 521-568) parametrized with `--verbose` and `--debug`, verifies `captured.out.strip() == "answer for run-1"` and `[VERBOSE]`/`[DEBUG]` not in stdout.
- Tests use exact-match assertions on stdout content (`==`), so any extra diagnostic output to stdout would fail.
- Additional coverage: `test_fins_direct_verbose_log_outputs_execution_skeleton` and `test_fins_direct_debug_log_outputs_event_details` independently verify diagnostics appear in `captured.err` and not in `captured.out`.

### Challenge 3: Fins Path Not Redacted

**Result: PASS**

- `test_output_keeps_absolute_paths_visible_and_bounded` (replaces `test_output_redacts_embedded_absolute_paths`):
  - Line 636: `_safe_text_value("/tmp/a") == "/tmp/a"` — POSIX short path preserved.
  - Line 637: `_safe_text_value("path=/Users/a/b") == "path=/Users/a/b"` — embedded path preserved.
  - Line 638: `_safe_text_value(r"error=C:\tmp\a") == r"error=C:\tmp\a"` — Windows path preserved.
  - Lines 639-641: Long path truncated to 120 chars with `...` suffix.
- `direct_events.py` unchanged (diff is empty) — no upstream contract change.
- All redaction functions (`_ABSOLUTE_PATH_PATTERN`, `_FINS_REDACTED_TEXT`, `_looks_like_absolute_path`, `_redact_absolute_path_match`) are fully removed with zero stale references (grep confirmed).
- `_safe_text_value` remains private to `dayu/cli/output.py` — no wider contract surface changed.

### Challenge 4: Diagnostic Leakage Analysis

**Result: PASS — no leakage of raw payload, job_id, sidecar, durable cursor, artifact, or API key**

- grep for `payload|job_id|sequence|cursor|artifact|sidecar|raw` in fins.py diff: zero hits.
- grep for `api_key|API_KEY|secret|password|token|authorization|Bearer` in `dayu/cli/commands/fins.py`, `dayu/runtime/log.py`, `dayu/cli/output.py`: only `cancellation_token` (CLI cancel mechanism) and display "token" (UI text token, not auth token).
- All diagnostic values are bounded: `_FINS_DIAGNOSTIC_TEXT_MAX_CHARS = 120`, `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS = 4`.
- `_bounded_diagnostic_text` correctly truncates long values with `...` suffix, maintaining exact 120-char limit.
- `_quoted_diagnostic_text` applies `shlex.quote` after truncation — quoted output stays at ≤120 chars for ASCII.
- Value flow: scalar strings passed to logging framework — no raw `FinsEvent` object, dataclass, or dict logged.
- Verbose diagnostic includes: operation, event_type, ticker, document, progress stage, result status, message.
- Debug diagnostic includes: operation, event_type, filing_kind, progress counts, result status/title/error_kind/exit_code, bounded details (≤4 items).
- Enum `.value` accesses (`operation_kind.value`, `event_type.value`, `result.status.value`, `result.error_kind.value`) produce business strings ("download", "progress", "success") — not secrets.
- Test assertions at lines 616-624 explicitly verify `sequence=`, `job_id=`, `cursor`, `artifact` are NOT present in debug output.

### Challenge 5: AGENTS Type/Docstring/README/Layer Constraints

**Result: PASS**

- All new functions have complete Chinese docstrings with `:param`, `:returns`, `:raises`.
- No `Any`, `object`, or untyped signatures in new code.
- `dayu/runtime/log.py` has zero imports from `dayu.cli`, `dayu.service`, `dayu.host`, `dayu.engine`, `dayu.fins`, or `dayu.ui` — layer-neutral compliance maintained.
- `dayu/README.md` update (lines 217-218): single sentence documenting stderr diagnostic channel and stdout UI channel — minimal, accurate, matches actual behavior.
- `tests/README.md` updates: accurately describe stderr diagnostic stream, path visibility (not redaction), and stdout cleanliness regression tests.
- `docs/host/issues-implementation-control.md` updates: correctly track R3/R5 as closed, R10 as closed (not transferred), and WU-CLI-FINS-DIAG-01 as completed.

### Challenge 6: Test Coverage for R3 and R5

**Result: PASS**

R3 coverage:
- `test_output_keeps_absolute_paths_visible_and_bounded` — POSIX, Windows, truncation. ✅
- Implicitly covered by `test_fins_direct_verbose_log_outputs_execution_skeleton` and `test_fins_direct_debug_log_outputs_event_details` which exercise the Fins output rendering path end-to-end.

R5 coverage:
- `test_logger_emits_to_stderr_by_default` — default stderr. ✅
- `test_configure_stream_override_keeps_diagnostics_redirectable` — explicit stream override. ✅
- `test_log_verbose_uses_call_site_logger` — `log_verbose` writes to stderr. ✅
- `test_fins_direct_verbose_log_outputs_execution_skeleton` — verbose diagnostics in stderr, not stdout. ✅
- `test_fins_direct_debug_log_outputs_event_details` — debug diagnostics in stderr, not stdout. ✅
- `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` — prompt stdout cleanliness. ✅
- `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout` — interactive stdout cleanliness. ✅
- `test_main_configures_runtime_log_from_parsed_cli_flags` — CLI main passes `stream=sys.stderr`. ✅

## Slice-by-Slice Verification

### Slice 1: Runtime and CLI Log Stream Separation

| Requirement | Evidence |
|---|---|
| `configure` accepts optional `stream` | `dayu/runtime/log.py:101` — `stream: TextIO \| None = None` |
| Default is stderr when `None` | `dayu/runtime/log.py:122` — `effective_stream = sys.stderr if stream is None else stream` |
| `set_level_from_flags` forwards stream | `dayu/runtime/log.py:149` — `stream: TextIO \| None = None` |
| CLI main passes stderr | `dayu/cli/main.py:75` — `stream=sys.stderr` |
| Marker value is stream-neutral | `dayu/runtime/log.py:45` — `"dayu.runtime.log:diagnostic"` |
| Tests assert stderr | `tests/runtime/test_log.py:348-358` — `captured.out == ""` + stderr regex match |
| Stream override test | `tests/runtime/test_log.py:341-353` — `stream=sys.stdout` redirected correctly |

### Slice 2: Fins UI Output Bounded Display Without Path Redaction

| Requirement | Evidence |
|---|---|
| Path redaction removed | `dayu/cli/output.py` — `_ABSOLUTE_PATH_PATTERN`, `_FINS_REDACTED_TEXT`, `_looks_like_absolute_path`, `_redact_absolute_path_match` all removed |
| `_safe_text_value` only truncates | `dayu/cli/output.py:319-323` — simple length check + truncation |
| `_bounded_json_text` docstring updated | `dayu/cli/output.py:297` — no longer mentions "脱敏" |
| Test verifies path visibility | `tests/cli/test_fins_commands.py:630-641` — POSIX, Windows, truncation |
| `direct_events.py` unchanged | Empty `git diff HEAD -- dayu/fins/direct_events.py` |

### Slice 3: Fins Direct Diagnostic Event Summaries

| Requirement | Evidence |
|---|---|
| VERBOSE includes bounded summary | `dayu/cli/commands/fins.py:760-771` — operation, event_type, ticker, document, stage, status, message |
| DEBUG includes bounded details | `dayu/cli/commands/fins.py:782-805` — + filing_kind, progress counts, title, error_kind, exit_code, details (≤4) |
| Constants for bounds | `dayu/cli/commands/fins.py:89-91` — max 120 chars, max 4 details, `...` suffix |
| No job/sidecar/cursor/artifact | Test lines 616-624 assert absence |
| Scalars only to logging | All functions return strings; logging calls pass pre-joined strings |

### Slice 4: Documentation and Control Closeout

| Requirement | Evidence |
|---|---|
| `dayu/README.md` updated | Lines 217-218 — stderr diagnostic + stdout UI channel |
| `tests/README.md` updated | Logging description includes stderr default and stream override; CLI tests describe path visibility and stdout cleanliness |
| Control doc R3/R5 closed | `docs/host/issues-implementation-control.md` — R3/R5 removed from active residuals, WU-CLI-FINS-DIAG-01 marked completed |
| Closeout doc updated | `docs/reviews/wu-cli-fins-obs-01-final-closeout-20260616.md` — residuals reconciled, R10 also properly closed |

## Validation

Tests:
```
source .venv/bin/activate && pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q
```
Result: **120 passed, 3 warnings** (warnings are edgar deprecation, pre-existing).

Pyright:
```
source .venv/bin/activate && pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/output.py dayu/cli/commands/fins.py tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
```
Result: **0 errors, 0 warnings, 0 informations**.

## Findings

### Pass — No Blocking Findings

No correctness, stability, maintainability, security, or compliance findings that would block acceptance.

### Non-Blocking Observations

| ID | Severity | File:Line | Observation |
|---|---|---|---|
| DS-OBS-01 | note | `dayu/cli/commands/fins.py:89-90` | `_FINS_DIAGNOSTIC_TEXT_MAX_CHARS=120` and `_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS=4` are arbitrary bounds. They are reasonable for current use but have no documented rationale for these specific values. If future FinsEvent fields grow significantly beyond 120-char labels, the truncation could make diagnostics less useful. Not a current issue — the plan explicitly calls for bounded display justified by volume/noise/readability, not secrecy. |
| DS-OBS-02 | note | `tests/cli/test_fins_commands.py:644-683` | Test fixtures `_progress_event` and `_result_event` now always set `filing_kind="10-K"` and `document_label="AAPL 10-K FY2024"` (previously `None`). The `None` code paths in `_append_optional_diagnostic_part` are no longer exercised for these fields. The functions handle `None` trivially (`if value is None: return`), so coverage regression is negligible. |
| DS-OBS-03 | note | `dayu/runtime/log.py:248` | `_build_marker_handler` signature changed from `(level)` to `(level, stream)` — this is a private function only called from `configure()`, so no external caller impact. Verified by grep: only two call sites, both inside `configure()`. |
| DS-OBS-04 | note | `dayu/cli/output.py:296` | `_bounded_json_text` docstring was updated to remove "脱敏" (redaction), but the function name still contains "json" which suggests JSON encoding, not just text bounding. The name accurately describes the function's behavior (it still calls `json.dumps`). No action needed. |

## Residual Risk Assessment

The plan's residual risks are correctly addressed:

1. **Engine/provider diagnostic redaction remains broader than R3 裁决**: Still out of scope. Correctly not touched.
2. **Fins event messages/details assumed free of API keys**: No counter-evidence found. The `_append_result_details_diagnostic_parts` function bounds output to 4 items at 120 chars each, providing defense-in-depth.
3. **No non-CLI production caller of `configure()`**: Verified — only CLI `main()` and `utils/smoke_web_ci.py` call `configure()`. Both now correctly use stderr (smoke_web_ci.py via default).
4. **Prompt/interactive activity readability**: Still assigned to issue #144. This WU only prevents diagnostic log pollution.
5. **Session lifecycle UX**: Still assigned to issue #145.

## Conclusion

**Verdict: pass**

All 13 changed files are correct and consistent. Tests pass (120/120), pyright is clean (0/0/0). No sensitive data leakage, no cross-layer violations, no direct_events.py modification, no durable job/sidecar/cursor/artifact introduction. The implementation faithfully follows the plan's four slices with the exact allowed changes and no scope expansion.

R3 and R5 are properly closed. The control doc and closeout doc accurately reflect the new state. README updates are minimal and accurate.
