# WU-TOOLS-01-F08 Implementation Artifact

## Metadata

- Work unit: `WU-TOOLS-01-F08`
- Gate: implementation
- Date: 2026-06-11
- Implementer: AgentCodex
- Accepted plan: `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
- Output artifact: `docs/reviews/wu-tools-01-f08-implementation-codex.md`

## Scope

Implemented the accepted single slice `S1 registry naming cleanup`.

Changed files:

- `dayu/documents/processors/registry.py`
- `dayu/documents/processors/__init__.py`
- `dayu/documents/processors/_doc_processor_factory.py`
- `dayu/fins/processors/registry.py`
- `tests/documents/test_processors.py`
- `tests/fins/test_processor_registry.py`
- `dayu/fins/README.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-tools-01-f08-implementation-codex.md`

No files were staged, committed, or pushed.

## Implementation Summary

- Renamed the documents registry builder from the old Engine-worded name to `build_documents_processor_registry(...)`.
- Updated the direct package export in `dayu.documents.processors`.
- Renamed the doc tools factory cache/helper from old Engine-worded names to documents-worded names.
- Updated `dayu.fins.processors.registry` to build from the documents default registry and removed Engine-ownership wording.
- Added a documents focused registry test that locks default processor names, classes, priorities, and order.
- Added a Fins focused registry contract test in `tests/fins/test_processor_registry.py`, using public `list_processors()` to assert name -> class/priority mapping and SEC priority buckets without hardcoding the full list order.
- Updated `dayu/fins/README.md` to say Fins overlays the documents default processor registry.
- Updated `docs/host/issues-implementation-control.md` to mark implementation complete, close `WU-TOOLS-01-S1-R2`, and set the next entry point to code review gate.

Processor registration behavior was intentionally unchanged:

- Documents default registry still registers `DoclingProcessor`, `MarkdownProcessor`, and `BSProcessor` at priority `10`.
- Fins registry still starts from the documents default registry, then overlays shared names with `FinsDoclingProcessor` / `FinsMarkdownProcessor` at priority `100` and `FinsBSProcessor` at priority `80`.
- Fins registry still includes SEC form-specific BS primary processors at priority `200`, edgartools fallback processors at priority `190`, and `SecProcessor` at priority `120`.

## Validation

Commands were run from the repository root after `source .venv/bin/activate` where required.

- Stable-target old-name cleanup check over `dayu`, `tests`, `dayu/fins/README.md`, and `docs/host/issues-implementation-control.md`
  - Result: passed; no matches. `rg` exited `1`, which is expected for no matches.
- Historical `docs/reviews` old builder name check
  - Result: passed; matches remain only in historical review / plan review artifacts. These are not cleanup targets under the accepted plan.
- `pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q`
  - Result: passed; `5 passed, 3 warnings`.
- `pytest tests/documents tests/fins -q`
  - Result: passed; `263 passed, 1 skipped, 3 warnings`.
  - Classification: no full `tests/fins` heavy fixture / environment failure occurred, so no rename-regression classification was needed.
- `python -m pyright dayu/ tests/ utils/`
  - Result: passed; `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

Warnings observed in pytest were existing edgartools deprecation warnings from dependency imports, not rename regressions.

## README Decision

- `dayu/fins/README.md`: updated. The change touched `dayu/fins/`, and the README's Agent update constraints allow current implemented architecture / processor boundary documentation. The old ownership wording was in scope and was corrected to documents default registry wording.
- `tests/README.md`: checked but not updated. The new focused Fins registry test lives under the existing `tests/fins/` layer, and the documents registry test lives under existing `tests/documents/`; no new test layer, command class, fixture category, or maintenance rule was introduced.
- `dayu/README.md`: not updated. This implementation did not change the UI / Service / Host / Engine layering relationship or assembly model; it only removed a misleading builder name from documents/Fins registry ownership.

## Residual Risks And Uncovered Areas

- Historical `docs/reviews/` artifacts still contain the old builder name. Classification: accepted historical artifact留痕; not a cleanup target for this work unit.
- Removing the old public export can break repository-external consumers still importing the old name. Classification: assigned to PR/release communication; compatibility alias/re-export/wrapper is explicitly forbidden by AGENTS.md and the accepted plan.
- Single-file coverage was not separately measured. Classification: uncovered metric; behavior risk is covered by focused registry contract tests and full `tests/documents tests/fins` validation.

## Completion Status

Implementation gate completed locally. The next gate is code review. No stage, commit, or push was performed.
