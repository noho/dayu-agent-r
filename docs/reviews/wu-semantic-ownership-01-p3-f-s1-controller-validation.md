# WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership`
- Slice: S1 - Source repository provenance and citation projection
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-implementation-codex.md`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md`

## Result

`ready-for-code-review`

Controller validation confirms the S1 implementation stays within the approved S1 scope:

- Adds storage-facing `FinsSourceProvider` and `SourceDocumentProvenance`.
- Adds `get_source_document_provenance(...)` and `stage_source_document(...)` protocol/core skeleton required by the accepted plan.
- Writes / validates source providers for SEC, CNINFO, HKEXNEWS, and user upload source meta.
- Projects citation `source_type` and `source_provider` from repository provenance instead of `document_id` prefix or `ingest_method` alone.
- Updates focused Fins tests and README documents triggered by Fins/test changes.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py tests/fins/test_docling_upload_service.py -q
```

Result: `76 passed, 3 warnings in 7.44s`. Warnings are existing `edgar` deprecation warnings.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed:

```bash
git diff --check
```

Result: no output.

Source scan:

```bash
rg -n "startswith\\(\\\"fil_\\\"\\)|startswith\\('fil_'\\)" dayu/fins/tools dayu/fins/pipelines
```

Result:

- `dayu/fins/pipelines/sec_rebuild_workflow.py:253`: classified as SEC accession reconstruction during rebuild, not citation/provenance source classification.

Source scan:

```bash
rg -n "def _build_citation|_build_citation\\(" dayu/fins/tools/read_runtime.py
```

Result: one helper definition and all citation construction call sites route through `_build_citation(...)`.

Source/provider scan:

```bash
rg -n "source_provider|source_type" dayu/fins tests/fins
```

Result: matches are expected S1 implementation, tests, README, and fixture updates.

## README Decision

- `dayu/fins/README.md` update is within its Agent update constraints because source provenance and citation projection are current implemented Fins package contract facts.
- `tests/README.md` update is within its test-maintenance scope because Fins tests now cover source provenance and citation provider projection.

## Propagation Audit

- Producer: SEC/CN/HK/upload pipelines persist `source_provider` in source meta.
- Validator: `SourceDocumentProvenance.from_meta(...)` and source repository provenance projection fail closed on missing/invalid completed-source provider.
- Persistence: filesystem source meta carries provider values.
- Projection: `FinsReadRuntime._build_citation(...)` uses source meta `source_kind` only as routing context and uses repository provenance for LLM-facing `source_type` / `source_provider`.
- LLM-facing output: `Citation.to_dict()` emits exact self-explanatory provider values when present and omits `source_provider` only when it is `None`.

## Coverage

Single-file coverage was not measured. AgentCodex reported pytest-cov collection failed locally with a numpy/pandas import error (`cannot load module more than once per process` / pandas unable to import numpy). Controller did not rerun coverage because the same focused tests and pyright pass without coverage instrumentation. This remains a validation gap for the code review gate to consider, not an implementation blocker by itself.

## Residual Risk

- S2 still owns blob acknowledgement enforcement and SEC/upload staging-before-blob sequencing.
- S1 adds the staging protocol/core skeleton but does not yet wire blob repository enforcement.
- Coverage measurement remains unavailable in this local environment due pytest-cov collection/import failure.
