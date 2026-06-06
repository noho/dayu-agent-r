# WU-TOOLS-01 Slice S1 Implementation Report

Gate: implementation  
Work unit: WU-TOOLS-01  
Slice: S1 shared document foundations  
Agent: AgentCodex  
Branch: `phaseflow/wu-tools-01`  
Accepted plan commit: `f6658fb4`  
Artifact: `docs/reviews/wu-tools-01-slice1-implementation-codex.md`

## Scope

Implemented only Slice S1: established `dayu.documents` as the shared document processing and Docling runtime owner outside Engine.

No Doc provider, Fins provider, Web provider, ToolDefinition adapter, Host change, Engine implementation change, Fins storage migration, ToolRegistry migration, TruncationManager migration, `fetch_more` migration, OLD tool runtime owner migration, or OLD web UI migration was performed.

## Files Changed

- Added `dayu/documents/__init__.py`.
- Added migrated OLD `dayu/documents/docling_runtime.py`.
- Added migrated OLD `dayu/documents/processors/*.py`.
- Added `tests/documents/__init__.py`.
- Added `tests/documents/test_import_boundary.py`.
- Added `tests/documents/test_processors.py`.
- Updated `tests/engine/contracts/test_import_boundary.py`.
- Updated `tests/engine/test_import_boundary.py`.
- Updated `dayu/README.md`.

`dayu/engine/README.md` was inspected and left unchanged because it already states Engine does not own tool implementations or financial document storage and does not claim document processors live in Engine.

## Import-Closure Inventory

Inventory target before copying:

- `/Users/leo/workspace/dayu-agent/dayu/engine/processors/*`
- `/Users/leo/workspace/dayu-agent/dayu/docling_runtime.py`

Included OLD processor files:

- `dayu/engine/processors/__init__.py` -> `dayu/documents/processors/__init__.py`
- `dayu/engine/processors/_doc_processor_factory.py` -> `dayu/documents/processors/_doc_processor_factory.py`
- `dayu/engine/processors/base.py` -> `dayu/documents/processors/base.py`
- `dayu/engine/processors/bs_processor.py` -> `dayu/documents/processors/bs_processor.py`
- `dayu/engine/processors/docling_processor.py` -> `dayu/documents/processors/docling_processor.py`
- `dayu/engine/processors/html_extraction.py` -> `dayu/documents/processors/html_extraction.py`
- `dayu/engine/processors/html_markdown.py` -> `dayu/documents/processors/html_markdown.py`
- `dayu/engine/processors/html_normalization.py` -> `dayu/documents/processors/html_normalization.py`
- `dayu/engine/processors/html_pipeline.py` -> `dayu/documents/processors/html_pipeline.py`
- `dayu/engine/processors/local_file_source.py` -> `dayu/documents/processors/local_file_source.py`
- `dayu/engine/processors/markdown_processor.py` -> `dayu/documents/processors/markdown_processor.py`
- `dayu/engine/processors/perf_utils.py` -> `dayu/documents/processors/perf_utils.py`
- `dayu/engine/processors/processor_registry.py` -> `dayu/documents/processors/processor_registry.py`
- `dayu/engine/processors/registry.py` -> `dayu/documents/processors/registry.py`
- `dayu/engine/processors/search_utils.py` -> `dayu/documents/processors/search_utils.py`
- `dayu/engine/processors/source.py` -> `dayu/documents/processors/source.py`
- `dayu/engine/processors/table_utils.py` -> `dayu/documents/processors/table_utils.py`
- `dayu/engine/processors/text_utils.py` -> `dayu/documents/processors/text_utils.py`

Included OLD shared runtime file:

- `dayu/docling_runtime.py` -> `dayu/documents/docling_runtime.py`

Included internal closure:

- Relative processor imports among `.base`, `.source`, `.search_utils`, `.text_utils`, `.table_utils`, `.perf_utils`, `.local_file_source`, `.processor_registry`, `.registry`, `.html_extraction`, `.html_markdown`, `.html_normalization`, `.html_pipeline`, `.bs_processor`, `.markdown_processor`, and `.docling_processor`.

Excluded with reason:

- `dayu.log`: excluded. OLD logging helper is a top-level compatibility-style dependency and not needed by the moved document foundation. Replaced with stdlib `logging.getLogger(__name__)` in `dayu/documents/docling_runtime.py` and `dayu/documents/processors/perf_utils.py`.
- `dayu.contracts.env_keys`: excluded. Current repo has no such module, and importing it would add an unnecessary cross-contract dependency for one environment variable name. The migrated `perf_utils.py` keeps a module-level constant `FINS_PROCESSOR_PROFILE_ENV = "FINS_PROCESSOR_PROFILE"`.

External third-party imports observed but not copied because they are dependencies, not OLD helper files:

- `bs4`, `pandas`, `readability`, `trafilatura`, `html2text`, `markdownify`, `docling`, `docling_core`, `torch`, `tabulate`.

Blockers:

- None. The closure did not require OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate / fetch-more projection, Host runtime state, Engine runtime state, concrete tools, Fins storage, or OLD web UI files.

## Migration Principle Compliance Notes

- Processor class/function signatures and business parsing bodies were preserved. Edits were limited to package/documentation references and logging/runtime import adjustments required by the migration.
- No compatibility re-export was added under `dayu.engine`.
- No top-level `dayu.log` compatibility module was added.
- `dayu.documents` import boundary is enforced by AST tests and forbids `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins`, and `dayu.tools`.
- Engine import-boundary tests were tightened so Engine and Engine contracts cannot import `dayu.documents`.
- Fixtures cover Markdown, HTML, and Docling JSON behavior without invoking real PDF/OCR conversion.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/documents tests/runtime/test_import_boundary.py tests/engine/contracts/test_import_boundary.py
```

Result: passed, 18 tests.

Command:

```bash
source .venv/bin/activate && pytest tests/engine/test_import_boundary.py
```

Result: passed, 4 tests.

Command:

```bash
source .venv/bin/activate && pyright
```

Result: passed, 0 errors, 0 warnings, 0 informations.

## README / Doc Sync Decision

- Updated `dayu/README.md` because `dayu.documents` is now a stable shared package and affects stable boundaries and code reading order.
- Did not update `dayu/engine/README.md` because its current text remains true after S1.
- Did not update root `README.md`, `dayu/config/README.md`, `dayu/host/README.md`, or `dayu/fins/README.md` because S1 does not change user commands, config entry points, Host behavior, or Fins behavior.

## Residual Risks And Uncovered Areas

- Docling PDF conversion runtime is migrated and import/type checked, but S1 tests intentionally avoid real PDF/OCR conversion. Classification: covered by later approved slices or integration work that exercises Doc/Fins/Web conversion paths.
- `build_engine_processor_registry` remains the OLD function name inside the migrated processor code to preserve OLD function signatures. Classification: assigned to later work unit or explicit review decision if public naming cleanup is desired.
- Tests cover representative Markdown, HTML, and Docling JSON fixtures, not full OLD parity corpus. Classification: covered by later approved provider/tool migration slices and broader regression suites.

## Completion Status

Implementation gate for WU-TOOLS-01 Slice S1 is complete. Changes are intentionally left uncommitted.
