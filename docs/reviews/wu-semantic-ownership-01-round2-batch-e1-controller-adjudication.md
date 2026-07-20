# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch E1 Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01` / Round2 Batch E1.
- Controller role: 合并 AgentCodex implementation、MiMo/DS code review、review-fix 与 targeted rereview。
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-implementation-codex.md`
- Code reviews:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-code-review-ds.md`
- Targeted rereviews:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-rereview-ds.md`

## Accepted Findings Closed

- `144330-02`: processor optional capabilities now use typed Protocol boundaries instead of `getattr(processor, ...)` capability repair.
- `150304-07`: accepted direct evidence fixed for source meta projection, source document collection/citation paths, and financial/XBRL result construction.
- `150304-08`: source meta cache is bounded LRU and by-kind reads are partitioned by `source_kind`.
- `150304-27`: listed object signatures were narrowed at the owner boundary.
- `150304-28` / `150304-30`: added focused guard tests for Fins weak typing and import boundary.
- Controller review-fix accepted items:
  - source meta cache key now includes `source_kind` for by-kind reads;
  - source meta bool fields fail loud on explicit non-bool values and preserve storage defaults only when absent;
  - `_normalize_json_scalar_text` has a single owner in `read_runtime_helpers.py`;
  - `get_financial_statement` rejects missing/non-list `rows`;
  - guard tests use behavior/AST checks rather than private cache field assertions and brittle string scanning.

## Rejected Or Deferred Review Items

- MiMo `E1-03` `_ProcessorFinancialStatementPayload.data_quality/reason`: not fixed in this batch. It is a low-risk payload typing concern without direct runtime correctness impact in the accepted E1 evidence.
- DS finding `_iter_sections Any`: deferred as broad processor typing residual outside accepted direct evidence.
- `150304-10`: remains deferred/not applicable for this batch. Current code still has the documented `dayu.fins.ingestion.wait_adapter` Host wait-contract exception; introducing a lower public wait adapter contract would be a separate boundary WU.
- Broad read runtime search/table `Any`, storage raw JSON helpers, and Docling payload conversion remain residuals outside this batch.

## Rereview Result

- MiMo targeted rereview: non-blocking; all 5 controller-accepted review-fix findings verified closed.
- DS targeted rereview: non-blocking; all 5 controller-accepted review-fix findings verified closed.

## Controller Validation

- `source .venv/bin/activate && pytest -q tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_projects_provider_owned_source_types tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_reuses_single_cached_source_meta_read tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_rejects_incomplete_source_meta tests/documents/test_processors.py tests/fins/test_processor_registry.py`
  - Result: 27 passed, 3 edgartools deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings.
- `git diff --check`
  - Result: passed.
- Targeted evidence scan:
  - Production `read_runtime.py` / `read_runtime_helpers.py` no longer contain `getattr(processor, ...)`.
  - `_normalize_json_scalar_text` is defined only in `read_runtime_helpers.py`.
  - Accepted weak signatures and `_collect_source_documents* -> list[dict[str, Any]]` evidence are absent.
  - The old `runtime._meta_cache` private-field test assertion and `_function_source` string-slice helper are absent.

## Residual Risk

- `_get_document_meta_cached` and `_get_source_meta_cached_by_kind` can store separate entries for the same `(ticker, document_id)` because the former resolves source kind internally while the latter receives it explicitly. This is a cache-efficiency trade-off, not a correctness blocker.
- Existing broad weak typing remains in search/table/citation surfaces outside Batch E1.
- The wait adapter Host dependency remains intentionally deferred.

## Decision

Batch E1 is accepted and ready to commit.
