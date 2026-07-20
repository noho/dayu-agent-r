# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Controller Validation

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S3 - Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure`
- Gate: controller validation after implementation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-implementation-codex.md`
- Decision: validation pass; proceed to two-agent code review

## Scope Check

`git status --short` contains only S3 allowed production/test files, the new normalization owner, the new fiscal/normalization test, and the implementation artifact:

- production/docs: `dayu/fins/README.md`, `dayu/fins/domain/filing_semantics.py`, SEC download/upload pipeline files, SEC processor files, and read runtime files.
- new owner: `dayu/fins/processors/value_normalization.py`.
- tests: `tests/fins/test_fiscal_normalization_contracts.py`, SEC download/upload tests, and CN pipeline alias tests.
- artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-implementation-codex.md`.

No Host, Engine, config prompt, R3-E, upload/download security schema, or tool-security files are modified.

## Validation Commands

All commands were run after `source .venv/bin/activate`.

| Command | Result |
| --- | --- |
| `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q` | `37 passed, 3 warnings` |
| `pytest tests/fins/test_sec_pipeline_download.py -q -k 'skip or not_modified or download_version'` | `6 passed, 30 deselected, 3 warnings` |
| `pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q -k 'company_meta or ticker_alias'` | `8 passed, 12 deselected, 3 warnings` |
| `coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py -q` | `23 passed, 3 warnings` |
| `coverage report --include='dayu/fins/processors/value_normalization.py' --fail-under=80` | `100%`, passed |
| `pytest tests/fins -q` | `628 passed, 1 skipped, 3 warnings` |
| `pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_processor_read_consistency.py tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q` | `119 passed, 3 warnings` |
| `pytest tests/fins/test_fins_storage_provider.py -q -k 'financial_statement or xbrl_query or search_document or processor_cache or source_revision'` | `21 passed, 44 deselected, 3 warnings` |
| `pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q` | `1 passed, 3 warnings` |
| `pytest tests/fins/test_sec_pipeline_download.py -q -k 'xbrl or 6k or skip or not_modified or download_version'` | `12 passed, 24 deselected, 3 warnings` |
| `pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q -k 'company_meta or ticker_alias'` | `8 passed, 12 deselected, 3 warnings` |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | passed |

Warnings are existing `edgar` deprecation warnings.

## Propagation Scans

- Fiscal duplicate scan in `dayu/fins/tools`: zero matches for old fiscal rank, inference, fallback, and recommended-document helpers.
- Private optional string wrapper scan: zero matches in `sec_section_build.py`, `sec_table_extraction.py`, and `sec_xbrl_query.py`.
- `normalize_optional_dataframe_string` scan: matches only the new owner, direct SEC processor consumers, and owner contract tests.
- SEC version scan: fast skip, remote skip, and not-modified skip paths all route through `has_current_download_version(...)`; tests cover current, legacy, and missing-version cases.
- Upload alias scan: production `upload_company_meta.py` has no `strip().upper()` alias persistence; it uses `_normalize_ticker_aliases` and `try_normalize_ticker`. Extra `strip().upper()` matches are existing SEC download test stubs, not upload alias persistence.
- Fins README forbidden-term scan for `R3-D|plan gate|future|tool-security|SSRF|allowlist`: zero matches.
- `errors="ignore"` scan: only existing downloader heuristic parser matches in `dayu/fins/downloaders/sec_downloader.py`; not new S3 changes.
- `except Exception: continue` scan: only existing XBRL auxiliary probe matches in `sec_xbrl_query.py`; these remain typed-partial evidence probes, not empty-success query fallback.
- Financial shadow payload/NotRequired/scale-map scan: zero matches.
- Virtual-section assignment scan remains confined to the S2 mixin owner.
- Fins-to-Host/Engine import scan: zero matches.

## README Decision

`dayu/fins/README.md` was updated because S3 plus accepted S1/S2 changed current Fins developer contracts: result invariants, source revision cache, typed degradation, fiscal/normalization owners, and upload alias canonicalization. Root `README.md`, `dayu/README.md`, and `tests/README.md` were not updated because no installation, CLI, layer, or test-running contract changed.

## Residual Classification

- SEC downloader heuristic `errors="ignore"` paths: assigned to a later Fins downloader decode-policy owner; outside S3 allowed files.
- Broad `DocumentMeta` migration and 6-K BS-only routing: remain assigned to later owners per accepted plan.
- Existing `edgar` deprecation warnings: tracked dependency warning, not current-slice failure.

No unclassified residual risk and no blocking open question.
