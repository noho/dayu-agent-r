# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Goal Confirmation

## Work Unit

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Type: production-high semantic ownership / atomicity fix
- Theme: Fins storage identity, mutation atomicity, temp cleanup, and layer boundary
- Design truth:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `dayu/README.md`
  - `dayu/fins/README.md`
- Control truth:
  - `docs/host/issues-implementation-control.md`
  - `docs/phaseflow-umbrella-optimization-control.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`

## First-Principles Judgment

R3-C is valid and should proceed after excluding tool-security work from this WU.

Fins owns financial document storage identity, upload/download ingestion, repository mutation, and direct Fins runtime semantics. Host and Engine must not repair these facts downstream. The current code still has direct evidence that file identities, storage side effects, temporary files, and Host wait adapter glue cross owner boundaries without a single complete Fins-owned contract.

The risk is not style cleanup. The current R3-C implementation scope can produce path escape, partial document mutation after failures, leaked temp files, and reverse Fins -> Host dependency.

Tool-security findings are real but intentionally excluded by the user's current scope instruction. They require a dedicated tool-security plan before implementation.

## Direct Evidence

- `dayu/fins/ingestion/wait_adapter.py:49` imports `dayu.host.api`; `:56` imports `dayu.host.durable.state`; `:57` imports `dayu.host.wait_adapter`. This violates the R3-C adjudication owner boundary that Service/Host assembly should own Host-facing wait adapter glue.
- `dayu/fins/storage/_fs_blob_core.py:141` only strips `filename`, and `:147` passes it into `_build_store_key`; it does not reuse the single-component entry-name/document-id validator at the storage owner boundary.
- `dayu/fins/storage/_fs_blob_core.py:144` checks source handles through `_get_handle_meta`, but no equivalent existence check is visible for `ProcessedHandle` before blob writes.
- `dayu/fins/storage/local_file_store.py:70-78` writes to a `.part` file and replaces the target, but does not fsync the temp file or parent directory before/after replace.
- `dayu/fins/downloaders/cninfo_downloader.py:337-346` and `dayu/fins/downloaders/hkexnews_downloader.py:334-343` create temp PDFs with `delete=False`; cleanup depends on downstream workflow reading and unlinking the path.
- `dayu/fins/pipelines/docling_upload_service.py:399-402` sets `token = None` before `commit_batch`; if commit fails, the exception handler at `:417-420` cannot rollback that token.

## Tool-Security Findings Excluded From This WU

The following accepted Round3 findings are security/tool-safety work. They are not planned or implemented in this WU unless the user explicitly opens a dedicated tool-security plan:

- LLM-facing upload may persist arbitrary process-readable local files:
  - `dayu/fins/pipelines/docling_upload_service.py:581-590` reads user-provided upload files fully with `Path.read_bytes()`.
  - `dayu/fins/pipelines/docling_upload_service.py:794-804` checks existence, file type suffix, and ordinary file status, but not explicit user file authority or a symlink-safe allowlist.
- CN/HK remote download provenance and resource-budget enforcement:
  - `dayu/fins/downloaders/cninfo_downloader.py:66-69` uses `http://` CN provider URLs.
  - `dayu/fins/downloaders/cninfo_downloader.py:676-678` and `dayu/fins/downloaders/hkexnews_downloader.py:527-529` follow redirects and read `response.content` without trusted URL / redirect / byte-budget enforcement.

Current R3-C may touch adjacent download/upload code only for non-security atomicity, rollback, temp cleanup, or storage owner fixes. It must not implement allowlists, URL/TLS provenance policy, redirect policy, SSRF/egress policy, or download byte-budget policy.

## Goal

Make R3-C owner-closed:

- Fins storage must own single-component identity validation for ticker/document id/entry name/filename/object key and handle existence before filesystem key construction.
- Fins completed document mutation must avoid or repair partial source/blob/processed side effects on cancel, exception, and commit failure paths.
- Fins temp assets must be cleaned on cancel, exception, and generator-close paths.
- Fins must not import Host; Host wait adapter glue must move to Service/Host assembly or another correct upper boundary.

## Non-Goals

- Do not change financial read semantics, XBRL projection, fiscal period inference, processor freshness, or result projection; those belong to R3-D.
- Do not broaden into Web/Documents egress or diagnostic policy; those belong to R3-E.
- Do not implement tool-security policy in this WU: no upload file allowlist/user-file authority, no URL/TLS/redirect/SSRF provenance policy, and no remote download byte-budget policy.
- Do not refactor all Fins processors, split large files for style, or fix generic broad-exception / typing cleanup without direct R3-C ownership evidence.
- Do not introduce a durable Fins job system beyond the existing observation/job foundation.
- Do not preserve old unsafe storage/mutation behavior through compatibility shims.

## Scope Boundary

Allowed production areas for the plan:

- `dayu/fins/storage/`
- `dayu/fins/domain/document_models.py` if storage handle contracts need owner-level validation
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/pipelines/*download*`, `docling_upload_service.py`, upload/download event mapping as needed
- `dayu/fins/ingestion/`, `dayu/fins/ingestion_runtime.py`
- Service/Host assembly files only for removing Fins -> Host wait adapter imports
- focused tests under `tests/fins/`, plus Host/Service integration tests only where wait adapter relocation requires them
- README/design docs triggered by actual code changes

Out of scope unless directly required by owner relocation:

- Engine provider protocol
- Host lifecycle state machine
- Fins financial/read semantics
- Web/Documents tools
- CLI public command rendering
- Tool-security policy and LLM-facing upload/download security schema changes

## Success Signals

- Storage path traversal and filename/entry-name tests fail closed at Fins storage owner boundaries.
- Download/upload batch rollback tests prove source/blob/processed observable state does not expose completed partial mutations after commit/cancel/exception failures.
- Temp cleanup tests prove CN/HK temp PDFs are removed on success, cancel, exception, and generator close paths.
- Import-boundary scan proves `dayu.fins` no longer imports `dayu.host`.
- Focused Fins tests, affected Host/Service tests, pyright, `git diff --check`, and owner scans pass.

## Slice Guidance

Use `docs/phaseflow-umbrella-optimization-control.md`: do not create one slice per finding. R3-C is production-high, so it needs full plan/review/implementation/review/aggregate deepreview gates, but related findings should be merged by owner boundary:

- storage identity / fs atomicity
- upload batch rollback
- CN/HK temp cleanup
- wait adapter dependency relocation

The plan may use fewer or more slices only if it explains the semantic owner boundary, validation matrix, and rollback risk. More than three implementation slices requires explicit justification.

## Blocking Questions

None. The user's continuation instruction is treated as confirmation to proceed through plan and subsequent gates for all accepted findings in the umbrella WU.

## Next Gate

Dispatch AgentCodex to produce a code-generation-ready R3-C plan.
