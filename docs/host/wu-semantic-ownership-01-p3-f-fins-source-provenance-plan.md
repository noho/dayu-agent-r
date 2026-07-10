# WU-SEMANTIC-OWNERSHIP-01 P3-F Fins Source Provenance Plan

## Scope / Non-goals

本计划覆盖 `WU-SEMANTIC-OWNERSHIP-01 P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership` 的 plan gate。目标是把 Fins source document、blob 文件、citation provenance、Fins awaiting timeout、company metadata freshness 这些事实收回到各自 semantic owner，并让下游 projection 只消费 owner 提供的 typed truth。

当前动机成立。直接代码证据显示：

- `dayu/fins/tools/read_runtime.py:_build_citation` 仍用 `document_id.startswith("fil_")` 与 `ingest_method` 推断 LLM-facing `source_type`。
- `dayu/fins/storage/_fs_blob_core.py:store_file` 对 `SourceHandle` 未验证 source repository 已承认该 source document。
- `dayu/fins/pipelines/docling_upload_service.py:execute_upload` 与 SEC 下载路径在最终 source meta commit 前写 blob。
- `dayu/fins/ingestion/wait_adapter.py:_transient_pending_expired` 仍使用 `_TRANSIENT_PENDING_MAX_SECONDS = 300.0` 与 `wait_record.created_at`。
- `dayu/fins/pipelines/upload_company_meta.py:upsert_company_meta_for_upload` 在 existing meta 存在时忽略本次 company fields，`dayu/fins/storage/_fs_company_meta_core.py:get_company_meta` 缓存直到 explicit upsert。

Non-goals:

- 不做 P3-G form/domain rule typing。
- 不做 P3-H UI copy 或 LLM-facing copy cleanup，除 citation 字段语义自解释外不改 prompt 文案。
- 不做 P3-I CLI/package entrypoints。
- 不做 P3-J durable schema backlog 或全量旧库兼容迁移。
- 不做 P3-K test harness cleanup。
- 不重构全部 Fins storage layout，不引入通用 job scheduler，不让 read runtime 通过文件名、路径或测试 fixture 反推 provenance。

## Source Finding Adjudication Table

| Finding | Disposition | Owner | Reason and current evidence |
| --- | --- | --- | --- |
| Prevent blob writes from creating source documents the source repository does not acknowledge, or introduce explicit staging source contract. | accepted | Fins source document repository plus blob repository boundary | Blob `store_file(SourceHandle, ...)` writes by handle key only. Upload and SEC download currently construct `SourceHandle` and write files before final source meta commit. CN path already has an `ingest_complete=False` staging pattern, proving a narrow staging contract fits current design. |
| Make citation `source_type` / provider derive from repository provenance, never from `document_id` prefix. | accepted | Fins source document repository owns provenance; read runtime owns citation projection | `_build_citation` branches on `document_id.startswith("fil_")`. CN/HK downloaded filings also use `fil_*` ids and carry `source_provider`, so prefix inference can misclassify provider and LLM-facing source type. |
| Use wait record deadline/expiry truth instead of Fins adapter hardcoded transient pending age where applicable. | accepted | Host wait record owns wait time boundary; Fins adapter consumes it | `WaitRecordRow` has `deadline_at` / `expires_at`; `dayu/host/wait_callback.py:_stale_status_or_none` already uses these fields. Fins adapter currently creates a separate 300 second transient unavailable window from `created_at`. |
| Define stale/refresh semantics for company metadata if direct code inspection confirms stale data can be reused indefinitely. | accepted, narrow scope | Company metadata repository and resolver/upsert helpers | Upload path ignores fresh company args whenever existing meta is present, and repository cache persists until explicit upsert. SEC/CN download paths refresh on each download, so the current-scope fix should define resolver-version freshness for upload/existing-meta reuse, not a global TTL or read-time resolver. |

Counts: accepted 4, rejected 0, deferred 0, needs-more-evidence 0.

## Owner Boundary and Propagation Paths

Source document and citation path:

1. Producer: SEC/CN/HK/upload pipeline writes source meta through `SourceDocumentRepositoryProtocol`.
2. Validator: source repository validates source kind, ingest method, source provider/provenance, `ingest_complete`, primary document, file membership.
3. Persistence: filesystem source meta and manifests under `dayu.fins.storage`.
4. Blob boundary: blob repository may write files for a `SourceHandle` only after source repository has acknowledged either a staging source document or a completed source document.
5. Projection: `FinsReadRuntime` reads typed source provenance from repository and maps it to `Citation.source_type` plus `source_provider`.
6. LLM-facing output: all read/search/section/table/page/financial statement outputs use the same citation helper and never inspect `document_id` prefixes.

`_build_citation` may read source meta only for routing and citation business fields. The routing read obtains `source_kind` so the repository can address the correct source document namespace; `source_kind` by itself is not provider/provenance truth and must not drive `source_type`. Business meta reads may still supply `form_type`, `filing_date`, `accession_no`, fiscal period, and heading because those are citation content fields, not source classification fields.

Wait path:

1. Producer and durable truth: Host creates `WaitRecordRow` with `deadline_at` / `expires_at`.
2. Consumer: `FinsIngestionWaitPollAdapter` receives `WaitRecordRow` in `poll_wait`.
3. Projection: transient observation unavailability becomes `WaitPollNotReady` before the Host boundary, and `WaitPollLost` only when the Host-owned boundary says the wait is stale/expired.
4. User/LLM-visible result: Host wait resolution remains the only source of terminal wait outcome.

Company metadata path:

1. Producer: SEC download resolver, CN/HK downloader profile, or upload-provided company fields.
2. Validator and persistence: company metadata upsert helpers plus `CompanyMetaRepositoryProtocol`.
3. Freshness truth: current scope defines upload freshness by resolver owner version, not by read-runtime caching, `updated_at` age, or ticker aliases.
4. Projection: `FinsReadRuntime._read_company_info` consumes repository meta only; it does not refresh or infer.

Source provenance and blob acknowledgement should be separate implementation slices. They both touch source meta, but they guard different invariants. Provenance/citation fixes LLM-facing classification of already acknowledged documents. Blob acknowledgement fixes pre-commit file ownership and failure behavior. The invariant between them is: any blob file referenced by completed source meta must have been written under a source document previously acknowledged by source repository, and citation must only project completed source documents using the same repository provenance.

Slice dependency rule: Slice 1 introduces the shared domain/protocol surface used by later slices: `FinsSourceProvider`, `SourceDocumentProvenance`, `get_source_document_provenance(...)`, and the `stage_source_document(...)` protocol signature plus filesystem repository core implementation. Slice 2 consumes that staging protocol in blob validation and SEC/upload workflow sequencing. Slice 2 may adjust implementation details of staging, but must not invent a second staging semantic outside the source repository invariant.

## Proposed Contracts / APIs

Add typed source provenance contracts in `dayu/fins/domain/document_models.py`:

- `FinsSourceProvider(str, Enum)` with exactly these current-scope values:
  - `SEC_EDGAR = "sec_edgar"`
  - `CNINFO = "cninfo"`
  - `HKEXNEWS = "hkexnews"`
  - `USER_UPLOAD = "user_upload"`
  These are storage values, not LLM-facing display strings.
- `SourceDocumentProvenance` dataclass with `source_kind: SourceKind`, `ingest_method: FinsIngestMethod`, `source_provider: FinsSourceProvider`, `ingest_complete: bool`.
- Parsing helper `SourceDocumentProvenance.from_meta(meta: Mapping[str, JsonValue], source_kind: SourceKind) -> SourceDocumentProvenance` or an equivalent module-level helper in the domain layer. It must fail closed on missing/invalid provider for completed source documents.

Extend `SourceDocumentRepositoryProtocol` in `dayu/fins/storage/repository_protocols.py`:

- `get_source_document_provenance(ticker: str, document_id: str, source_kind: SourceKind) -> SourceDocumentProvenance`.
- Keep `source_kind` in the provenance method signature. This matches existing repository addressing, avoids a cross-kind search on every citation, and keeps source classification inside the returned provenance projection. Callers that only have `ticker` / `document_id` must first obtain `source_kind` as a routing key from source meta or an already available `SourceHandle`; they must not derive provider/source type from that routing key.
- `stage_source_document(req: SourceDocumentUpsertRequest, source_kind: SourceKind) -> SourceHandle`. This method writes or reuses `ingest_complete=False` meta and returns the only handle valid for pre-commit blob writes.

`stage_source_document(...)` semantics:

- First call: create a source meta record with `ingest_complete=False`, valid `source_kind`, valid `source_provider`, valid `ingest_method`, and no completed file membership claim. `primary_document` may be `None`, and `files` / `file_entries` must be empty or omitted until membership is known.
- Repeated call when existing meta has `ingest_complete=False`: return the same `SourceHandle` idempotently only if stable request fields match the existing staging meta. Stable fields include `ticker`, `document_id`, `internal_document_id`, `source_kind`, `source_provider`, `ingest_method`, source fingerprint or remote fingerprint when present, and expected market/company identity fields when present.
- Repeated call with mismatched stable fields: fail closed with a deterministic conflict exception before any blob write. Do not mutate the existing staging meta to hide a different request under the same source id.
- Existing completed source meta with `ingest_complete=True`: fail closed with a deterministic conflict exception unless the caller goes through the existing completed-source update/overwrite path. Staging must not downgrade completed source meta.
- Staging-to-complete: final source document commit updates the same source id to `ingest_complete=True` and writes primary document plus full file membership. Commit is the first point where source meta may claim completed file membership.
- Failed/retried SEC download: failed download may leave `ingest_complete=False` meta. A retry with matching stable fields reuses it; a retry with changed stable fields fails before blob writes so the caller must make an explicit overwrite/new-source decision.

Update storage implementation:

- `dayu/fins/storage/_fs_source_document_core.py` implements provenance projection from stored meta and staging write.
- `dayu/fins/storage/_fs_blob_core.py:store_file` enforces source acknowledgement only for `SourceHandle` before writing. `ProcessedHandle` remains under processed artifact ownership and is not widened in P3-F unless implementation evidence shows the same orphan-source bug exists there.
- Enforcement layer: blob repository performs the final guard because it is the boundary that can otherwise create ownerless blob state. The filesystem implementation should receive a source-meta existence/provenance reader by constructor injection or share a lower-level storage core supplied by the storage assembly. It must not import a concrete higher-layer repository, pipeline, service, Host, or UI object.
- TOCTOU classification: the source-meta check followed by blob write is a residual race in multi-process writers. P3-F accepts this residual because the current Host is expected to operate through a single storage assembly and the new guard still prevents all ordinary orphan writes. If implementation finds multi-worker writes in the same workspace, it must either put the check/write under the existing workspace file lock or record a follow-up owner before proceeding.

Update citation model in `dayu/fins/domain/tool_models.py`:

- Add `source_provider: str | None` to `Citation`.
- `Citation.source_provider` is visible in `Citation.to_dict()` when non-`None`. Completed source-backed citations must normally emit a non-`None` provider. `None` is allowed only for non-source-backed transitional citations or explicitly providerless citation paths; `to_dict()` should omit the field when it is `None`, and implementation must not use `None` to mask missing provider in completed source meta.
- LLM-facing `SourceType` enum values and exact output strings:
  - `SEC_EDGAR = "SEC_EDGAR"`
  - `CNINFO = "CNINFO"`
  - `HKEXNEWS = "HKEXNEWS"`
  - `UPLOADED = "UPLOADED"`
  - `SUPPLEMENTARY = "SUPPLEMENTARY"`
- LLM-facing `Citation.source_provider` output strings are uppercase self-explanatory business provider names derived from `FinsSourceProvider`:
  - `FinsSourceProvider.SEC_EDGAR` -> `"SEC_EDGAR"`
  - `FinsSourceProvider.CNINFO` -> `"CNINFO"`
  - `FinsSourceProvider.HKEXNEWS` -> `"HKEXNEWS"`
  - `FinsSourceProvider.USER_UPLOAD` -> `"USER_UPLOAD"`
- Required citation mapping:
  - SEC downloaded filing -> `source_type="SEC_EDGAR"`, `source_provider="SEC_EDGAR"`.
  - CNINFO downloaded filing -> `source_type="CNINFO"`, `source_provider="CNINFO"`.
  - HKEXNEWS downloaded filing -> `source_type="HKEXNEWS"`, `source_provider="HKEXNEWS"`.
  - user-uploaded filing -> `source_type="UPLOADED"`, `source_provider="USER_UPLOAD"`.
  - supplementary material -> `source_type="SUPPLEMENTARY"`, `source_provider` from provenance, normally `"USER_UPLOAD"` for uploaded material.

Update company metadata freshness without schema expansion:

- Define resolver-version freshness helper in `dayu/fins/pipelines/upload_company_meta.py`, for example `_existing_company_meta_is_fresh(existing_meta: CompanyMeta, resolver_version: str) -> bool`.
- `RESOLVER_VERSION` remains owned by the upload company-meta resolver helper. It must change only when upload-provided company identity normalization or required-field semantics change in a way that makes previously persisted upload meta stale for future uploads. It is not a release version, schema version, market-data recency marker, or cache TTL.
- Current-scope rule: upload may preserve existing company meta only when its `resolver_version` matches upload resolver version. If the version differs, upload must require current company fields and upsert a fresh `CompanyMeta`. No time-based TTL is introduced in P3-F.
- Tests must construct older-version metadata explicitly so the freshness path is exercised without relying on a future real version bump.

Update wait adapter helper:

- Replace `_transient_pending_expired` with a helper that reads `wait_record.deadline_at` first, then `wait_record.expires_at`, matching Host callback precedence.
- Invalid boundary text should fail closed as `WaitPollLost(_lost_outcome())` only if the boundary is present but invalid; with no boundary, return `WaitPollNotReady` for transient unavailable.
- Host wait creation evidence to verify during implementation: `dayu/host/waiting.py:_wait_record_row` currently derives `deadline_at` from `candidate.await_spec.deadline` and writes `expires_at=None`. Fins awaiting tools may therefore produce no-boundary wait records if the await spec has no deadline.
- No-boundary rationale: Fins adapter is not the lifecycle owner and must not invent a terminal lost boundary from `created_at`. Practical retry cadence is bounded by Host poller policy (`WaitPollerRuntimePolicy.not_ready_observe_interval_seconds`, claim TTL, backoff, close/cancel lifecycle), while true terminal loss remains Host/user cancellation, explicit callback/poll loss, or a Host-owned deadline/expires boundary.

## Implementation Slices with Files, Behavior Changes, Tests, Validation

### Slice 1 - Source Repository Provenance and Citation Projection

Dependency ownership:

- Slice 1 owns the shared domain/protocol addition for provenance and staging signatures: `FinsSourceProvider`, `SourceDocumentProvenance`, `get_source_document_provenance(...)`, and `stage_source_document(...)`.
- Slice 2 consumes `stage_source_document(...)`; it must not add a parallel staging protocol.

Files:

- `dayu/fins/domain/document_models.py`
- `dayu/fins/domain/tool_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/upload_company_meta.py` only if upload provider constant is shared here; otherwise keep to slice 4.
- `dayu/fins/tools/read_runtime.py`

Behavior changes:

- SEC download source meta writes `source_provider=sec_edgar`.
- CN/HK download keeps existing `source_provider` but parses it through `FinsSourceProvider`.
- Upload source meta writes `source_provider=user_upload`.
- `SourceDocumentRepositoryProtocol.get_source_document_provenance(...)` is the only source of citation provider/source classification.
- `_build_citation` obtains `source_kind` by reading source meta as a routing key, then calls `get_source_document_provenance(ticker, document_id, source_kind)`. It may keep using meta values for citation business fields, but must not use `source_kind`, `ingest_method`, file path, id prefix, or provider fallback branches for classification.
- `_build_citation` removes all `document_id.startswith("fil_")` classification logic.
- Citation includes exact LLM-facing `source_provider` and provider-correct `source_type` values defined above.
- All read/search/section/table/page/financial-statement citation call sites must continue to route through `_build_citation`; callers must not each reconstruct provider mapping.

Tests:

- Add/update `tests/fins/test_fins_storage_provider.py`:
  - source provenance projection returns SEC/CNINFO/HKEXNEWS/USER_UPLOAD values from repository meta.
  - invalid/missing provider on completed source document fails closed.
  - read runtime citation for SEC downloaded filing reports `source_type="SEC_EDGAR"` and `source_provider="SEC_EDGAR"`.
  - read runtime citation for CNINFO `fil_*` filing reports `source_type="CNINFO"` and `source_provider="CNINFO"`.
  - read runtime citation for HKEXNEWS `fil_*` filing reports `source_type="HKEXNEWS"` and `source_provider="HKEXNEWS"`.
  - uploaded filing reports `source_type="UPLOADED"` and `source_provider="USER_UPLOAD"`.
  - uploaded material reports `source_type="SUPPLEMENTARY"` and `source_provider="USER_UPLOAD"`.
  - `Citation.to_dict()` includes `source_provider` only when non-`None`.
- Add/update `tests/fins/test_sec_pipeline_download.py` and `tests/fins/test_cn_download_runtime.py` for persisted `source_provider`.
- Before implementation, run a fixture/source-meta scan and migrate fixtures instead of adding production prefix fallback:
  - `rg -l '"ingest_complete": true|"ingest_complete":true' tests/fins`
  - `rg --files tests/fins --glob '**/meta.json'`
  - Likely affected fixture classes/directories: `tests/fins/fixtures/**/meta.json`, SEC downloaded filing fixtures, CN/HK downloaded filing fixtures, upload filing/material workspace fixtures, and read-runtime fixtures that call `_build_citation`.
  - Any completed source meta loaded through the new provenance contract must include valid `source_provider`; missing provider fails closed by design, and tests must be migrated to the new schema.

Validation:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py
source .venv/bin/activate && rg -n 'startswith\("fil_"\)|startswith\('\''fil_'\''\)' dayu/fins/tools dayu/fins/pipelines
source .venv/bin/activate && rg -n 'def _build_citation|_build_citation\(' dayu/fins/tools/read_runtime.py
```

The `startswith("fil_")` scan must be zero in citation/provenance paths. Non-citation identity normalization in `sec_rebuild_workflow.py` may remain only if classified in the implementation report as SEC accession reconstruction, not source classification.
The `_build_citation` scan must show one helper definition and all citation construction call sites going through that helper.

### Slice 2 - Blob Acknowledgement and Explicit Staging Source Contract

Dependency ownership:

- Slice 2 consumes the Slice 1 repository protocol and filesystem source repository staging implementation.
- CN staging must align with the same source repository invariant. It may keep `update_cn_staging_source_document(...)` as a workflow-shaped helper, but that helper must delegate to or be semantically backed by the same `stage_source_document(...)` idempotency and conflict rules. Do not leave CN and SEC with two independent definitions of staging.

Files:

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py` only to align naming or tests; CN already has staging behavior and should not be rewritten broadly.

Behavior changes:

- `store_file(SourceHandle, ...)` raises `FileNotFoundError` before writing if source meta is absent.
- Upload and SEC download create an `ingest_complete=False` staging source document before any blob write.
- Concrete SEC insertion point: in `dayu/fins/pipelines/sec_download_filing_workflow.py`, after the target `SourceHandle` is known and before calling either downloader path that receives `store_file=host._build_store_file(source_handle=source_handle)`. The stream and non-stream branches must both be downstream of staging. Any equivalent class path in `dayu/fins/pipelines/sec_pipeline.py` must call the same workflow helper or the same staging helper before `_build_store_file(...)` can be invoked.
- SEC staging placeholder requirements before remote file membership is known: `ingest_complete=False`, valid `source_kind=filing`, valid `source_provider=sec_edgar`, valid `ingest_method=download`, stable SEC identity/fingerprint fields when available, `primary_document=None`, and empty/omitted `files` and `file_entries`. This placeholder must not be listable/readable as a completed document.
- Final source document commit updates the staged source to `ingest_complete=True` with primary document and full file entries.
- If conversion/download fails after staging, incomplete staging meta may remain as an acknowledged incomplete source document; read runtime already excludes `ingest_complete=False`.
- Blob repository never creates source document acknowledgement implicitly.

Tests:

- Add/update `tests/fins/test_fins_storage_provider.py`:
  - first `stage_source_document(...)` creates incomplete source meta and returns a `SourceHandle`.
  - repeated `stage_source_document(...)` with matching stable fields is idempotent.
  - repeated staging with mismatched stable fields fails before blob write.
  - staging when completed source meta already exists fails with a completed-source conflict.
  - staging-to-complete commit updates the same source id to `ingest_complete=True` and full membership.
  - `FsDocumentBlobRepository.store_file(SourceHandle(...))` rejects missing source meta and does not create a file.
  - after `stage_source_document`, `store_file` succeeds.
  - `list_documents` / read runtime excludes staging `ingest_complete=False`.
- Add/update `tests/fins/test_docling_upload_service.py`:
  - upload stages before first blob write using a fake source/blob repository call log.
  - if final upsert fails, blob writes happened only under an acknowledged staging source.
- Add/update `tests/fins/test_sec_pipeline_download_stream.py`:
  - SEC stream stages before downloader `store_file` callback is invoked.
  - SEC non-stream path stages before downloader `store_file` callback is invoked if covered by a distinct code path.
  - failed download does not produce completed source meta.
  - failed/retried SEC download reuses matching incomplete staging meta and completes on retry.
  - retry with mismatched stable request fields fails closed before blob write.
- Add/update CN tests only if common contract changes break existing CN staging expectations.

Validation:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py
```

### Slice 3 - Fins Wait Adapter Deadline/Expiry Consumption

Files:

- `dayu/fins/ingestion/wait_adapter.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py` if helper builders need default boundary updates.

Behavior changes:

- Remove `_TRANSIENT_PENDING_MAX_SECONDS` and created-at age ownership from transient unavailable classification.
- Implementation must inspect and cite Host wait creation for Fins awaiting tools before changing behavior. Current evidence to confirm is `dayu/host/waiting.py:_wait_record_row`: `deadline_at` is derived from `candidate.await_spec.deadline`, while `expires_at` is written as `None`.
- For `TRANSIENT_UNAVAILABLE`:
  - if `deadline_at` exists and current time is after it, return `WaitPollLost`.
  - else if `expires_at` exists and current time is after it, return `WaitPollLost`.
  - else if a present boundary is invalid timestamp text, return `WaitPollLost`.
  - else return `WaitPollNotReady`.
- Use the same boundary precedence as `dayu/host/wait_callback.py:_stale_status_or_none`: `deadline_at` first, then `expires_at`.
- No-boundary wait records are valid if the await spec did not provide a deadline. In that case, adapter-level `WaitPollNotReady` is correct because Fins does not own a terminal timeout; Host poller cadence is controlled by `WaitPollerRuntimePolicy.not_ready_observe_interval_seconds`, claim TTL, backoff, close, and external cancellation.
- Do not expose wait record ids, deadlines, expiry timestamps, or Host governance terminology to LLM-facing tool results.

Tests:

- Add/update `tests/fins/test_fins_ingestion_tools.py`:
  - transient unavailable with future `deadline_at` returns `WaitPollNotReady`.
  - transient unavailable with past `deadline_at` returns `WaitPollLost`.
  - transient unavailable with no `deadline_at` but past `expires_at` returns `WaitPollLost`.
  - transient unavailable with invalid `deadline_at` or invalid `expires_at` returns `WaitPollLost`.
  - transient unavailable with no boundary returns `WaitPollNotReady`.
  - created_at older than 300 seconds no longer makes the result lost when no boundary exists.
- Add/update Host/Fins wait builder tests only if existing builders hide boundary behavior:
  - Fins awaiting wait creation with a deadline populates `deadline_at`.
  - Fins awaiting wait creation without a deadline leaves both `deadline_at` and `expires_at` absent and relies on Host poller policy/cancel lifecycle.
- Update WaitRecordRow builders in tests to set boundary explicitly only when the test asserts boundary behavior.

Validation:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py
source .venv/bin/activate && rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests
```

The constant/helper scan must be zero after implementation.

### Slice 4 - Company Metadata Freshness Semantics

Files:

- `dayu/fins/pipelines/upload_company_meta.py`
- `tests/fins/test_upload_batch.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_cn_pipeline.py` only for upload paths that reuse `upsert_company_meta_for_upload`.

Behavior changes:

- Upload preserves existing company meta only when `existing_meta.resolver_version == RESOLVER_VERSION`.
- Upload treats existing meta with a different resolver version as stale and requires current `company_name` to refresh it.
- `RESOLVER_VERSION` is owned by `dayu/fins/pipelines/upload_company_meta.py` and changes only with upload company identity normalization or required-field semantics. Implementation must not read it from wall-clock time, external market-data recency, or release metadata.
- SEC/CN download paths remain producer-owned refreshes and should not be routed through upload freshness logic.
- `updated_at` remains audit time, not a TTL boundary, in this work unit.

Tests:

- Add tests for `upsert_company_meta_for_upload`:
  - existing same-version meta is preserved and current company args are ignored with existing warning behavior.
  - existing older-version meta constructed in the test is refreshed from current upload fields.
  - stale existing meta plus missing `company_name` raises the same create/update validation error instead of silently reusing stale data.
  - read runtime still reads repository meta and does not perform refresh.

Validation:

```bash
source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py
```

### Final Validation for the Work Unit

After all slices:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py
source .venv/bin/activate && pyright
source .venv/bin/activate && git diff --check
```

Coverage expectation: each touched production file should keep or reach the repository target of at least 80% single-file coverage where coverage is measured. If an existing touched file is already below target and the slice does not materially expand its behavior, the implementation report must state the current measured coverage and why the focused new tests cover the changed owner boundary.

## README / Doc Update Decision

README trigger checks required during implementation:

- `dayu/fins/` will be modified. Read `dayu/fins/README.md` and update only if its Agent update constraints say source provenance, staging source contract, wait adapter boundary, or company metadata freshness are in scope for its target reader.
- `tests/` will be modified. Read `tests/README.md` and update only if new test organization, required validation commands, or fixture semantics change its documented responsibilities.
- Host production code is not expected to change. If implementation unexpectedly touches `dayu/host/`, read `dayu/host/README.md` and update only if its constraints require it.
- Service production code is not expected to change. If implementation unexpectedly touches `dayu/service/`, inspect the relevant README trigger before editing docs.
- Root `README.md` is not expected to change because no user-visible CLI/Web/WeChat command, installation workflow, or workspace location changes are planned.

This plan artifact itself does not update README files.

## Propagation Audit Criteria

Source provenance and citation:

- Every completed source document meta has a valid `source_provider`, `ingest_method`, `source_kind`, `ingest_complete=True`, primary document, and file membership.
- Repository provenance projection is the only source read runtime uses for citation source classification.
- `_build_citation` may use source meta `source_kind` only as repository routing context; it must use `SourceDocumentProvenance` for `source_type` / `source_provider`.
- Read runtime citation outputs for list/search/read/table/page/financial-statement paths all pass through the same helper.
- No citation path contains `document_id.startswith("fil_")` or equivalent path/name inference.
- CNINFO/HKEXNEWS downloaded filings with `fil_*` ids never project as SEC EDGAR.
- Upload and material citation source provider comes from source meta provenance, not from default branch guessing.
- Exact citation output strings are asserted for SEC EDGAR, CNINFO, HKEXNEWS, uploaded filings, and supplementary material.

Blob acknowledgement:

- A blob file written with `SourceHandle` must be under source meta that exists before the write.
- Staging source documents are explicitly marked `ingest_complete=False` and excluded from read/list tools.
- Repeated staging is idempotent only for matching stable request fields; mismatched staging and completed-source conflicts fail before blob writes.
- SEC staging occurs before any downloader `store_file` callback can run, including stream and non-stream paths.
- Final source meta `files[]` entries refer only to blob files written under the acknowledged source handle.
- Failure between staging and final commit leaves an incomplete source document, not an ownerless blob masquerading as completed source.
- `ProcessedHandle` blob writes remain out of this validation scope unless separate evidence widens ownership.

Wait:

- Fins adapter `TRANSIENT_UNAVAILABLE` outcome uses `deadline_at` / `expires_at` from `WaitRecordRow`.
- Host wait creation for Fins awaiting tools is inspected and documented; no-boundary wait records remain `WaitPollNotReady` because Fins does not own a terminal timeout.
- Created-at age and hardcoded adapter age do not affect terminal lost classification.
- Terminal wait resolution remains Host-owned; Fins adapter only returns typed poll result.

Company metadata:

- Upload stale/fresh decision is derived from resolver version, not from repository cache hit or ticker alias.
- `RESOLVER_VERSION` ownership and change rule are documented and tested with explicit older-version metadata.
- Download paths keep their current resolver-owned upsert behavior.
- Read runtime does not become a resolver or freshness owner.

## Source Scans That Must Be Zero or Classified

Must be zero after implementation:

```bash
rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests
```

Must be zero in citation/provenance paths, with any remaining matches classified as non-citation identity reconstruction:

```bash
rg -n 'startswith\("fil_"\)|startswith\('\''fil_'\''\)' dayu/fins/tools dayu/fins/pipelines tests/fins
```

Must be reviewed and classified so `source_provider` is written by source owners and read by projection only:

```bash
rg -n 'source_provider|source_type' dayu/fins tests/fins
```

Must show all citation construction still routes through one helper:

```bash
rg -n 'def _build_citation|_build_citation\(' dayu/fins/tools/read_runtime.py
```

Must show no direct source classification from `ingest_method` alone in read runtime:

```bash
rg -n 'ingest_method|FinsIngestMethod' dayu/fins/tools/read_runtime.py
```

## Risks / Residuals / Deferred Items

- Adding strict provenance requires a fixture/source-meta scan before Slice 1. Completed source meta missing `source_provider` fails closed in new-schema behavior; implementation must migrate tests/fixtures rather than adding compatibility shims that silently infer provider from missing fields.
- Staging source documents may remain after failed conversion/download. This is acceptable only if they are explicitly incomplete and excluded from read/citation. Physical cleanup of stale staging directories is not required in P3-F unless a test proves current repository operations cannot tolerate them.
- Blob repository source-meta validation has an accepted TOCTOU residual in theoretical multi-process writers. If implementation finds same-workspace multi-worker writes, move source check and blob write into an existing file-lock/atomic critical section or stop with a follow-up owner.
- Company metadata time-based TTL is intentionally not introduced. If product later requires market-data recency windows, that belongs to a separate resolver policy WU with external data source ownership.
- SourceType expansion is LLM-facing. Keep it self-explanatory and limited to current providers; do not expose internal module names, pipeline names, digest, cursor, wait id, or storage path as business facts.
- Rejected filing artifact storage is outside the source document acknowledgement invariant unless it uses `SourceHandle`; if scans show it only uses `FilingMaintenanceRepositoryProtocol`, classify it as separate maintenance owner.

## Completion State

ready-for-plan-rereview
