# WU-TOOLS-01-F01-03 Slice 4 Fix - AgentCodex

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: Slice 4 fix
- Controller adjudication: `docs/reviews/wu-tools-01-f01-03-slice4-code-review-controller-adjudication.md`
- Fix boundary: only controller accepted findings `CTRL-S4-01` through `CTRL-S4-04`.
- Non-goals preserved: no OLD upload business rule rewrite, no deferred test matrix expansion, no upload tool/provider/wait adapter, no process/CLI/Host/Engine contract work, no commit.

## Fix Status

| Finding | Status | Files | Evidence |
| --- | --- | --- | --- |
| `CTRL-S4-01` | Fixed | `dayu/fins/pipelines/sec_pipeline.py`, `dayu/fins/pipelines/cn_pipeline.py`, `dayu/fins/ingestion_runtime.py` | Module/runtime docstrings now state Slice 4 upload facade/direct runtime runner is implemented, while process/CLI/Host/tool/provider remain out of scope. Behavior unchanged. |
| `CTRL-S4-02` | Fixed | `dayu/fins/pipelines/docling_upload_service.py` | Removed all `_`-prefixed private helpers and `_PendingFileAsset` from `__all__`; helper names and tests remain unchanged. |
| `CTRL-S4-03` | Fixed | `dayu/fins/pipelines/sec_upload_workflow.py` | Deleted unused `cast_upload_host`, removed it from `__all__`, and removed the dedicated `typing.cast` import. `SecUploadWorkflowHost` and stream behavior unchanged. |
| `CTRL-S4-04` | Fixed | `dayu/fins/service_runtime.py` | Added a concise comment explaining why download adapters and upload runner use separate pipeline instances while sharing repository/job-store objects. No pipeline construction refactor. |

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `58 passed, 1 skipped, 3 warnings`
  - Skipped test: real Docling integration requires `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`.
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- Targeted type scan over touched Slice 4 production/test files:
  - `rg -n "\bAny\b|\bobject\b" ...`
  - Result: no matches.
- Boundary scan over touched Slice 4 production files:
  - scanned for Host/Engine/UI/CLI/tool/provider imports and provider/tool symbols.
  - Result: no matches.
- `docling_upload_service.__all__` private export scan:
  - `awk '/__all__ = \[/{flag=1; next} flag && /\]/{flag=0} flag' dayu/fins/pipelines/docling_upload_service.py | rg '"_'`
  - Result: no matches.
- Dead helper scan:
  - `rg -n "cast_upload_host" dayu/fins tests`
  - Result: no matches.

## README Decision

No README update in this fix gate. The changed facts were docstring/export/comment cleanup only; Slice 4 implementation README updates already covered the production upload runtime behavior.

## Residual Risks

- Deferred upload failure-path matrix remains deferred by controller adjudication.
- Runtime combination hardening and direct update-path coverage remain deferred by controller adjudication.
- Upload progress helper literal consolidation remains deferred by controller adjudication.
- No blocker found in this fix gate.

## Completion

- Accepted findings fixed: yes.
- Validation complete: yes.
- Commit created: no.
