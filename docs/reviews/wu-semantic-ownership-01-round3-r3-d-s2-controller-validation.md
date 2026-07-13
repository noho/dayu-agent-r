# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Controller Validation

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 - Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: controller validation after implementation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-implementation-codex.md`
- Controller timestamp: `2026-07-13 10:02:44 CST`
- Decision: validation pass; proceed to two-agent code review

## Scope Check

`git status --short` contains only accepted S2 production/test files and the S2 implementation artifact:

- production: `dayu/fins/domain/document_models.py`, `dayu/fins/storage/*`, `dayu/fins/processors/source_text.py`, SEC form processors, `dayu/fins/pipelines/sec_6k_rules.py`, and Fins read runtime/error mapping files.
- tests: `tests/fins/test_processor_read_consistency.py`, `tests/fins/test_fins_storage_provider.py`, `tests/fins/test_sec_pipeline_download.py`.
- artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-implementation-codex.md`.

No Host, Engine, R3-E, upload/download security, tool-security, prompt, or schema-security files are modified.

## Validation Commands

All commands were run after `source .venv/bin/activate`.

| Command | Result |
| --- | --- |
| `pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q` | `37 passed, 3 warnings` |
| `pytest tests/fins/test_fins_storage_provider.py -q -k 'search_document or processor_cache or source_meta_cache or source_revision'` | `19 passed, 46 deselected, 3 warnings` |
| `pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q` | `1 passed, 3 warnings` |
| `coverage run -m pytest tests/fins/test_processor_read_consistency.py -q` | `23 passed, 3 warnings` |
| `coverage report --include='dayu/fins/processors/source_text.py' --fail-under=80` | `94%`, passed |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | passed |

The warnings are existing `edgar` deprecation warnings, not S2 failures.

## Propagation Scans

- `rg -n 'errors="ignore"' dayu/fins`: only existing downloader-side matches in `dayu/fins/downloaders/sec_downloader.py` at lines 568, 2342, and 2392. They are outside S2 allowed files and outside the read-success source decoder owner path.
- `rg -n -U 'except Exception:\n\s+pass' dayu/fins/tools/read_runtime.py`: zero matches.
- `rg -n '_virtual_section_by_ref\s*=|_assign_tables_to_virtual_sections\(' dayu/fins/processors`: assignments/calls are confined to `dayu/fins/processors/sec_form_section_common.py`.
- `rg -n 'mtime|stat\(' dayu/fins/tools/read_runtime.py`: zero matches.
- Cache/revision scan shows `_processor_cache` and `_meta_cache` semantic read/write paths in `read_runtime.py` paired with `get_source_revision`; storage protocol/facade/core own the revision projection.
- Typed-failure scan shows `SourceDocumentRevision` in domain/storage/read runtime/tests, and `source_changed_during_read`, `search_index_failed`, `source_decode_failed` through `ErrorCode` plus owner paths.

## README Decision

No README update in S2. The accepted plan assigns Fins README synchronization to S3 aggregate closure so the documentation records the final combined read/normalization contract, not an intermediate S2-only state.

## Residual Classification

- Historical non-UTF-8 sources: assigned to a later encoding-policy work unit if product requirements require non-UTF-8 support; S2 correctly fails closed and must not restore ignore/replace.
- Cache reuse now performs storage revision reads: assigned to later profiling/performance optimization only if needed; correctness owner comparison must remain.
- Full `pytest tests/fins -q`: covered by later approved S3 aggregate validation.
- Downloader-side `errors="ignore"` matches: outside S2 read owner path; not changed here.

## Stop Status

No blocking open question. S2 is ready for MiMo/DS code review.
