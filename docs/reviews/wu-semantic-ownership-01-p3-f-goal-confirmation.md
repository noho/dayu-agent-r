# WU-SEMANTIC-OWNERSHIP-01 P3-F Goal Confirmation

## Work Unit

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership`
- Type: umbrella semantic ownership sub WU
- Current gate: goal confirmation
- Next gate: plan
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`

## First-Principles Judgment

P3-F is valid. The affected facts are user- or LLM-visible source/provenance facts and Host wait lifecycle facts, so they must be produced by their semantic owners rather than reconstructed by downstream consumers.

The work unit should not be implemented as a single broad Fins cleanup. It should be planned as owner-aligned slices:

- Source document provenance, blob acknowledgement, and citation projection are one owner boundary: Fins source repository owns document existence, source kind, provider/provenance, file membership, and ingestion completeness; tools consume typed repository truth.
- Wait timeout is a Host wait record fact: Fins wait adapter consumes `WaitRecordRow.deadline_at` / `expires_at`; it must not invent an independent transient pending age when those fields apply.
- Company metadata freshness is a company metadata repository/resolver contract: it should be fixed only if direct code inspection confirms stale data is reused in current production paths without refresh semantics.

## Direct Evidence

### Source provenance and citation

- `dayu/fins/tools/read_runtime.py:_build_citation` currently builds LLM-facing `Citation.source_type` from `document_id.startswith("fil_")` plus `ingest_method`.
- CN/HK downloaded filings also use `fil_*` document ids while their provider truth is `source_provider` such as `cninfo` / `hkexnews`.
- `dayu/fins/storage/_fs_source_document_core.py:_upsert_source_document` writes `source_kind` only as the caller-supplied storage location, but the source meta does not consistently include a typed citation provenance contract.
- This makes LLM-facing citations vulnerable to saying CN/HK filings are `SEC_EDGAR` or supplementary materials are ordinary uploads.

### Blob/source acknowledgement

- `dayu/fins/storage/_fs_blob_core.py:store_file` writes a file object using a `SourceHandle` / `ProcessedHandle`; it does not first prove that source repository has acknowledged the source document.
- `dayu/fins/pipelines/docling_upload_service.py:execute_upload` writes pending assets through `blob_repository.store_file(...)` and only later calls `_upsert_source_document(...)`.
- SEC and CN download flows likewise pass store callbacks or call `blob_repository.store_file(...)` before final source meta commit in some paths.
- If source upsert fails after blob writes, the blob layer can contain files for a source document the source repository does not acknowledge. The fix belongs at source/blob boundary or an explicit staging contract, not in read/citation consumers.

### Wait timeout ownership

- `dayu/fins/ingestion/wait_adapter.py:_transient_pending_expired` computes age from `wait_record.created_at` and hardcoded `_TRANSIENT_PENDING_MAX_SECONDS = 300.0`.
- Host wait records already carry `deadline_at` and `expires_at` fields in `WaitRecordRow`.
- `dayu/host/wait_callback.py:_stale_status_or_none` already uses `deadline_at` / `expires_at` as the stale boundary for callbacks, proving those fields are the durable wait boundary owner.

### Company metadata freshness

- `dayu/fins/domain/document_models.py:CompanyMeta` has `resolver_version` and `updated_at`, but no typed `expires_at`, `refresh_after`, or freshness policy.
- `dayu/fins/storage/_fs_company_meta_core.py:get_company_meta` returns cached/stored metadata until explicit upsert invalidates the cache.
- This source finding remains plausible, but implementation planning must first identify the production path that should refresh stale metadata and avoid inventing a broad resolver policy without a current consumer.

## Owner Boundary

- Producer of source document provenance: Fins source repository and source upsert pipelines.
- Validator of source document completeness and file membership: Fins source repository / explicit staging contract.
- Persistent source of source document facts: Fins source meta / manifest through `dayu.fins.storage`.
- Projection to LLM-facing citation: Fins read runtime, using repository-provided typed provenance only.
- Producer and persistent source of wait timeout: Host wait record.
- Consumer of wait timeout: Fins wait adapter.
- Producer/persistent source of company metadata freshness: company metadata repository/resolver contract.

## Success Signals

- Citation source type/provider no longer depends on `document_id` prefixes.
- Source meta or a repository projection exposes typed provenance sufficient for all read/search citation builders.
- Blob writes cannot create acknowledged source documents implicitly; either source document acknowledgement precedes blob writes, or an explicit staging source contract owns pre-commit files and cleanup.
- Fins wait adapter uses Host wait `deadline_at` / `expires_at` where applicable instead of a hardcoded independent pending age.
- Company metadata freshness is either implemented at the metadata owner with tests or explicitly deferred/rejected with current-code evidence.
- Tests cover SEC downloaded filing, CN/HK downloaded filing, uploaded filing, supplementary material, source/blob failure behavior, wait deadline/expiry, and any accepted company metadata freshness behavior.
- Pyright and affected tests pass; README updates are made only where triggered.

## Non-Goals

- Do not redesign all Fins storage schemas or all file layout conventions.
- Do not make read runtime infer missing provenance by document id, path, or fixture naming.
- Do not add compatibility shims for old source meta unless the plan explicitly justifies a current migration requirement.
- Do not implement a general job scheduler or global wait timeout policy outside Host wait record ownership.
- Do not solve P3-G form/domain rule typing, P3-H UI copy cleanup, P3-I CLI/package entrypoints, P3-J durable schema backlog, or P3-K test harness cleanup here.

## Controller Decision

P3-F is ready for plan gate. AgentCodex should produce a code-generation-ready plan that adjudicates the four accepted scope items, splits implementation by semantic owner, and identifies any company metadata freshness portion that should be fixed now versus deferred with explicit owner and evidence.
