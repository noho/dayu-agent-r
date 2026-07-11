# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch E1 Implementation

## Scope

- Work unit: WU-SEMANTIC-OWNERSHIP-01 / Round2 Batch E1.
- Gate role: AgentCodex implementation/fix.
- Baseline noted by controller: D2b2 accepted commit `2a94f0bb`.
- Implemented only accepted direct-evidence scope for Fins read runtime processor capability typing, source meta typing/cache bound, targeted object signature leaks, and guard tests.
- Did not implement ingestion runtime God module, ToolRuntime monolith, broad processor coverage, or broad read runtime search/table Any cleanup.

## Changed Files

- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/result_types.py`
- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/processors/sec_section_build.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/processors/sec_form_section_common.py`
- `dayu/documents/processors/docling_processor.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `dayu/fins/README.md`

`dayu/fins/tools/result_types.py` was added to the touched set because it owns the public read runtime result contract. Without updating that owner, `read_runtime.py` would need casts or loose result dicts to satisfy old `dict[str, Any]` result fields, which would preserve finding `150304-07`.

## Semantic Owner Decisions

- Processor optional capability owner: read runtime capability boundary. Added runtime-checkable typed protocols for page content, financial statement, XBRL facts, and XBRL taxonomy capabilities. Removed `getattr(processor, ...)` capability probes from accepted read runtime paths.
- Source meta owner inside read runtime: local typed projection. Raw storage meta remains storage-owned JSON, but read runtime now parses it into `_SourceDocumentMeta` before citation, list_documents, fiscal inference, and document alias resolution.
- Source meta cache owner: `FinsReadRuntime` instance. `_meta_cache` now uses bounded `ProcessorLRUCache[_CachedSourceDocumentMeta]`, with configurable `source_meta_cache_max_entries`.
- Public result contract owner: `dayu/fins/tools/result_types.py`. Narrowed list/page/financial/XBRL result fields touched by this batch so runtime can construct typed results without schema-hiding casts.
- External object shape owners:
  - filesystem storage JSON scalar size uses `JsonValue`;
  - SEC edgartools table/document shapes use module-local Protocols;
  - Docling label enum uses a Protocol with `value: str`;
  - structured section split ref is normalized at the call site to `str | None`.

## Findings Status

- `144330-02`: fixed. Processor read runtime capability checks now use typed Protocol branches; taxonomy helper uses `XbrlTaxonomyProcessor`. Controller follow-up fixed taxonomy failure semantics: only a processor that does not implement `XbrlTaxonomyProcessor` returns `None`; `get_xbrl_taxonomy()` exceptions now propagate instead of falling back to global default concepts.
- `150304-07`: fixed for accepted direct evidence. `_meta_cache`, source document collection/citation paths, and financial/XBRL result construction no longer use the cited `dict[str, Any]`/casts.
- `150304-08`: fixed. Added bounded source meta LRU and test proving eviction.
- `150304-27`: fixed for the listed object signatures.
- `150304-28` / `150304-30`: fixed. Added focused guard tests for Fins weak typing and import boundary.
- `150304-10`: deferred-with-owner / not applicable for this batch. Current evidence shows `dayu.fins.ingestion.wait_adapter` still integrates directly with Host wait-resume types (`dayu.host.api`, `dayu.host.durable.state`, `dayu.host.wait_adapter`). The lower neutral Fins observation owner exists in `dayu.fins.ingestion.observation_handle`, but Host wait adapter public contracts remain Host-owned and no lower public wait adapter contract was introduced by the inspected current code. Forcing a migration would require inventing a new public contract package, explicitly disallowed by the handoff. Owner remains Host wait-resume contract / future wait adapter boundary WU.

## Validation

Follow-up validation after controller taxonomy semantics finding:

- `source .venv/bin/activate && pytest -q tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_read_runtime.py`
  - Result: 11 passed, 3 edgartools deprecation warnings.
- `source .venv/bin/activate && pytest -q tests/fins/test_fins_storage_provider.py -k query_xbrl_facts`
  - Result: 1 passed, 46 deselected, 3 edgartools deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings.

- `source .venv/bin/activate && pytest -q tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_projects_provider_owned_source_types tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_reuses_single_cached_source_meta_read tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_rejects_incomplete_source_meta tests/documents/test_processors.py tests/fins/test_processor_registry.py`
  - Result: 18 passed, 3 edgartools deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings.
- `git diff --check`
  - Result: passed.
- Accepted evidence scan:
  - Command scanned targeted files for `getattr(processor`, unbounded `_meta_cache` dict pattern, targeted `list[dict[str, Any]]` source document returns, and listed `object` signatures.
  - Result: no matches.
- Broad weak typing scan:
  - Command scanned targeted files for `dict[str, Any]`, `Any`, and `: object`.
  - Result: residual matches remain in pre-existing broad search/table/processor/raw JSON surfaces and Docling/storage helpers outside accepted direct evidence scope. This is intentionally not closed in Batch E1.
- Fins import scan:
  - Result: only `dayu/fins/ingestion/wait_adapter.py` imports Host, matching the existing documented exception.

## README Decision

- Updated `dayu/fins/README.md` because `dayu/fins/` read runtime behavior and stable capability/cache boundaries changed.
- Did not update `tests/README.md`: this batch adds focused tests under an existing directory and does not change test hierarchy, execution rules, or maintenance policy.
- Did not update root `README.md` or `dayu/README.md`: no user-facing workflow, install, CLI, Web/WeChat entry, or cross-layer architecture boundary changed.

## Residual Risks

- Broad `Any` surfaces remain in read runtime search/table normalization, SEC section construction, storage raw JSON helpers, and Docling payload conversion. These are outside accepted Batch E direct-evidence scope and should not be treated as closed by this artifact.
- `dayu.fins.ingestion.wait_adapter` remains the sole Host import exception. A future boundary WU can migrate it only if Host exposes a lower public wait adapter contract outside `dayu.host`.
- `result_types.py` still contains older `dict[str, Any]` fields for search/table/citation surfaces not touched by this batch.

## Round2 Review-Fix

Controller accepted items fixed in this pass:

- `ACCEPT-1` / MiMo `E1-01`: fixed. `ProcessorCacheKey` now has optional `source_kind`; processor cache and creation locks keep default `None`, while `_get_source_meta_cached_by_kind` keys source meta with `source_kind.value`. Added behavior test proving same ticker/document_id with filing vs material meta does not mix.
- `ACCEPT-2` / DS finding 1: fixed. `_parse_source_document_meta` now preserves valid bools and storage-contract defaults for missing fields, but raises `ValueError` when `amended`, `is_deleted`, or `ingest_complete` exists with a non-bool value. Added focused tests for each field.
- `ACCEPT-3` / DS finding 2: fixed. `_normalize_json_scalar_text` has a single owner in `read_runtime_helpers.py`; `read_runtime.py` imports it and no longer defines a duplicate.
- `ACCEPT-4` / DS finding 6: fixed. `get_financial_statement` now rejects missing or non-list `rows` with `ValueError`; added tests for missing rows, dict rows, and the normal list path.
- `ACCEPT-5` / MiMo `E1-02` and DS findings 3/4: fixed in tests. The source meta cache bounded test now uses counting repository calls and eviction behavior instead of `runtime._meta_cache`; weak typing guards now use AST checks for `getattr(processor, ...)`, targeted return annotations, and listed weak argument annotations.

Controller rejected/deferred items kept out of scope:

- MiMo `E1-03` `_ProcessorFinancialStatementPayload.data_quality/reason`: not changed per controller reject/defer decision.
- DS finding 5 `_iter_sections Any`: not changed per controller defer decision; broad processor typing residual remains outside this batch.
- Broad `Any`, wait adapter, and non-batch paths: not expanded.

Review-fix validation:

- `source .venv/bin/activate && pytest -q tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_projects_provider_owned_source_types tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_reuses_single_cached_source_meta_read tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_rejects_incomplete_source_meta tests/documents/test_processors.py tests/fins/test_processor_registry.py`
  - Result: 27 passed, 3 edgartools deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings.

## Stop Status

COMPLETE. No commit, push, PR, or unrelated file edits performed.
