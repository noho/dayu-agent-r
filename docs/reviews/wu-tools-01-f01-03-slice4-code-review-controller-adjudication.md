# WU-TOOLS-01-F01-03 Slice 4 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 4: Migrate Upload Service And Production Upload Runtime`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice4-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice4-code-review-ds.md`
- Implementation artifact: `docs/reviews/wu-tools-01-f01-03-slice4-implementation-codex.md`

## Verdict

`fix-required`

Both review agents confirmed the main migration is correct: OLD upload semantics are preserved, `FinsIngestionRuntime` remains lifecycle-only, upload stays a long transaction behind a runner, storage/ticker boundaries are respected, and no Host/Engine/tool/provider/CLI boundary was crossed. Controller accepts a narrow maintainability/compliance fix set before Slice 4 can be accepted.

## Accepted Fixes

### CTRL-S4-01: Update stale upload/runtime docstrings

- Source findings: AgentMiMo Finding 3; AgentDS F1/F2.
- Severity: high / accepted.
- Evidence:
  - `dayu/fins/pipelines/sec_pipeline.py` and `dayu/fins/pipelines/cn_pipeline.py` module docstrings still say upload is out of scope, while Slice 4 added upload facade methods.
  - `dayu/fins/ingestion_runtime.py` `start_upload` docstring still describes the Slice 1 default unsupported-runner state, while `DefaultFinsRuntime` now wires a production upload runner.
- Required fix:
  - Update these docstrings to reflect current facts: upload facade/runtime direct runner is implemented; process/CLI/Host/tool/provider remain out of scope for this slice.
  - Do not change behavior.

### CTRL-S4-02: Remove private helper symbols from `docling_upload_service.__all__`

- Source findings: AgentMiMo Finding 1; AgentDS F3.
- Severity: medium / accepted.
- Evidence: `dayu/fins/pipelines/docling_upload_service.py` exports `_`-prefixed helpers and `_PendingFileAsset` in `__all__`, mixing private implementation details into the public export set.
- Required fix:
  - Remove all `_`-prefixed symbols from `__all__`.
  - Keep tests allowed to import private helpers directly where they intentionally test internals; direct import does not require `__all__`.
  - Do not rename helpers or expand public API in this fix.

### CTRL-S4-03: Remove dead `cast_upload_host`

- Source findings: AgentMiMo Finding 2; AgentDS F6.
- Severity: medium / accepted.
- Evidence: `sec_upload_workflow.cast_upload_host` is an identity `typing.cast` wrapper, exported but unused in the repository.
- Required fix:
  - Delete `cast_upload_host` and remove it from `__all__`.
  - Do not alter `SecUploadWorkflowHost` protocol or stream behavior.

### CTRL-S4-04: Clarify `DefaultFinsRuntime` pipeline instance split

- Source finding: AgentDS F4.
- Severity: low / accepted.
- Evidence: `DefaultFinsRuntime.get_ingestion_runtime()` constructs separate SEC/CN pipeline instances for download adapters and upload runner. This is behaviorally correct because repositories are shared, but the intent is not documented.
- Required fix:
  - Add a concise code comment explaining the split: download adapters keep source-specific downloader defaults/adapter identity, upload runner uses production upload facades, and all instances share the same repository objects/job store.
  - Do not refactor or merge pipeline instances in this fix.

## Deferred Findings

### CTRL-S4-D1: Broader upload failure-path test matrix

- Source findings: AgentDS F5/F7/F8 and residual notes.
- Decision: deferred.
- Reason: Slice 4 already has deterministic service/pipeline/runtime success and overwrite/skip coverage plus runtime terminal-job coverage. Additional conversion-error, mid-upload cancellation, empty-file, SEC material runtime, CN filing runtime, and direct update-path matrix is valuable hardening but not required to accept the migration slice. Keep this as residual test hardening unless later Slice 5 review finds a concrete regression.

### CTRL-S4-D2: Upload progress helper literal-key consolidation

- Source finding: AgentDS F9.
- Decision: deferred.
- Reason: The literal values are constrained by `UploadFileEventType` typing and covered by mapping tests. Consolidation can be handled as cleanup if drift appears.

## Rejected Findings

None.

## Required Validation After Fix

- `source .venv/bin/activate && pytest tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`
- Targeted scan: touched Slice 4 production/test files must not introduce `Any` / type `object`, Host/Engine/UI/CLI/tool/provider imports, or public `__all__` private helper exports in `docling_upload_service.py`.
