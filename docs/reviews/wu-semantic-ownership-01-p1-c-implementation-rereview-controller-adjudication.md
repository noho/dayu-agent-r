# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation Re-review Controller Adjudication

## Inputs

- MiMo re-review: `docs/reviews/wu-semantic-ownership-01-p1-c-implementation-rereview-mimo.md`
- DS re-review: `docs/reviews/wu-semantic-ownership-01-p1-c-implementation-rereview-ds.md`
- Review adjudication / fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-c-implementation-review-controller-adjudication.md`

## Verdict

P1-C implementation is accepted.

Both re-review agents concluded `pass`. The accepted blocker F-1 and accepted cleanup F-2 are closed:

- F-1 Web cancellation hint leakage: closed. All Web search/fetch cancellation projection paths now use `WEB_CANCELLED_HINT`, and exception handlers no longer trust `exc.hint` at the LLM-facing `host_cancelled_outcome()` boundary.
- F-2 `_PAYLOAD_FIELD_EVIDENCE_KIND` dead constants: closed. Stale constants were removed from `compact_material.py` and `run_input.py`; Host-owned typed `evidence_kind` remains intact.

## Controller Acceptance Notes

- The Web cancellation fix is at the owner boundary: `dayu/tools/web` owns Web tool business-readable cancellation text, and `web_tools.py` owns the final LLM-facing `ToolCancelledOutcome` projection.
- The shared Web hint source is local to the Web tool package and has no Host/Service/Engine dependency.
- The strengthened tests deliberately inject legacy governance text and verify production projection replaces it with the shared business-readable hint.
- Residual `continue_without_web` in `web_recovery.py` is a Web recovery action code, not the old cancellation hint prefix.
- Residual Host / poll / adapter / governance terms are internal implementation, docstring, diagnostic, or test-only surfaces unless separately proven LLM-facing in a later WU.

## Validation

Controller validation after fixes:

- `pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py tests/runtime/test_tool_call_projection.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/fins/test_fins_storage_provider.py` -> `325 passed, 1 skipped, 3 warnings`
- `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools` -> `1119 passed, 2 skipped, 3 warnings`
- `pyright` -> `0 errors, 0 warnings, 0 informations`
- `git diff --check` -> passed
- Extended residual scans over `dayu/config dayu/fins dayu/host dayu/runtime dayu/tools tests` ran with English and Chinese governance patterns; remaining hits were classified as internal, business-readable allowed, docstring, or adversarial test fixture.
- P1-A accepted-result projection references remain in `run_input.py`, `compact_material.py`, and `memory.py`.

## Residual Risks

- `FactEvidenceKindVNext.TOOL_RESULT` and `TOOL_SOURCE_TEXT` remain internal enum members but are not assigned by the current compact parser. This is deferred cleanup, not P1-C blocking.
- Web process-path cancellation envelope has internal process/runtime wording, but no current evidence shows it is projected to LLM-facing outcomes. Track under future Web process hardening if that path becomes active.
- Real LLM compaction smoke remains useful to observe behavior after removing LLM-facing `evidence_kind`, but parser/contract/material/RunInput tests cover the deterministic owner boundary.

## Next Gate

Update control doc to P1-C accepted implementation and proceed to `WU-SEMANTIC-OWNERSHIP-01 P2-A` planning. The umbrella WU remains open.
