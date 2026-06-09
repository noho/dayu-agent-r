# WU-TOOLS-01-F01-02 Slice 4 Code Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | Slice 4 code review adjudication |
| slice | Slice 4 - Fins Read Tools Context Injection And Checkpoints |
| plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| implementation | `docs/reviews/wu-tools-01-f01-02-slice4-implementation-codex.md` |
| MiMo review | `docs/reviews/wu-tools-01-f01-02-slice4-code-review-mimo.md` |
| DS review | `docs/reviews/wu-tools-01-f01-02-slice4-code-review-ds.md` |

## Review Summary

AgentMiMo verdict: PASS, no blocking finding. MiMo noted duplicate cancel helpers and a pre-existing broad exception pattern in `search_document` as non-blocking.

AgentDS verdict: PASS with required fix. DS identified one Medium-High cancellation swallow path in `read_section` and one lower-severity sibling path in `search_document`.

Controller validation before review passed:

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`
  - `45 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## Adjudication

### Accepted Finding S4-F1

Source: AgentDS Finding 1.

Finding: `read_section` added `_raise_if_fins_cancelled(cancellation_token)` inside an existing broad `except Exception` parent-title lookup block. Because `ToolBusinessError` inherits from `Exception`, cancellation can be caught and converted to `parent_title = None`. There is no later checkpoint before return, so the tool can return a successful `SectionContentResult` after cancellation was observed.

Decision: accepted for current Slice 4 fix.

Required fix: ensure the parent-title lookup block does not swallow `ToolBusinessError(code="tool_cancelled")`. Re-raise cancellation explicitly before preserving the existing best-effort fallback behavior for other exceptions.

### Accepted Finding S4-F2

Source: AgentDS Finding 2 and AgentMiMo non-blocking observation N2.

Finding: `search_document` added cancellation checkpoints inside an existing broad `except Exception` semantic enrichment block. A swallowed cancellation is likely re-observed by the next search boundary, so the current impact is lower than S4-F1. However, the root cause is the same: newly introduced cancellation exceptions should not be hidden by broad fallback exception handlers.

Decision: accepted for current Slice 4 fix as a narrow same-root-cause cleanup.

Required fix: ensure the semantic enrichment fallback block re-raises `ToolBusinessError(code="tool_cancelled")` before preserving existing fallback behavior for other exceptions.

### No-Action Observations

- Duplicate cancellation helper logic between `read_runtime.py` and `search_engine.py` is accepted for this slice because both are module-level private helpers and avoid expanding public contract surface.
- XBRL raw/normalized facts double checkpoint is accepted as conservative and cheap enough for current risk.

## Required Next Gate

Dispatch AgentCodex for a narrow Slice 4 fix:

- Modify only the accepted broad-except swallow paths and add or update targeted tests if needed.
- Re-run focused Fins tests, combined acceptance, pyright, and diff check.
- Do not change Host / Engine contract, storage boundaries, tool schemas, or checkpoint placement beyond the accepted swallow fixes.
