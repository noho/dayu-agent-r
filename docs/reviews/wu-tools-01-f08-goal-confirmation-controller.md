# WU-TOOLS-01-F08 Goal Confirmation

## Metadata

- Work unit: `WU-TOOLS-01-F08`
- Type: post-migration cleanup / naming boundary fix
- Gate: goal confirmation
- Date: 2026-06-11
- Controller: AgentController
- Design sources:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md`

## User Decision

User explicitly directed that the work units to advance are `WU-TOOLS-01-F01-02-R3` and `WU-TOOLS-01-F08`. `WU-TOOLS-01-F01-02-R3` has reached `draft-PR-pass-final-closeout-passed` with draft PR 135 open. This instruction is treated as the user decision to proceed to `WU-TOOLS-01-F08` without waiting for PR 135 merge.

## First-Principles Judgment

The motivation is valid and appropriately scoped.

Direct code evidence:

- `dayu.documents.processors.registry.build_engine_processor_registry(...)` constructs a generic documents processor registry containing Docling, Markdown, and BS processors.
- `dayu.documents.processors.__init__` exports `build_engine_processor_registry`, making the stale `engine` wording visible to package consumers.
- `dayu.documents.processors._doc_processor_factory` uses the same builder for Doc tools.
- `dayu.fins.processors.registry` imports the same builder and then registers Fins-specific processors on top.
- The function is not an Engine component and should not imply ownership by `dayu.engine`.

The issue is a real ownership / naming drift introduced by migration staging, not a runtime behavior bug. The correct fix is a direct rename to a documents/default registry name with all current production, test, and stable README references updated. A compatibility alias would preserve the misleading boundary and is explicitly out of scope.

## Goal

Rename the documents default processor registry builder away from OLD `engine` wording and update direct callers / exports / tests / docs while preserving registry behavior.

## Success Signal

- `build_engine_processor_registry` has no residual references in production code, tests, stable README, or `docs/host/issues-implementation-control.md`; historical review artifacts may retain old text.
- The new builder name clearly expresses documents ownership, preferably `build_documents_processor_registry(...)`.
- Documents default registry still registers Docling, Markdown, and BS processors in the same order and priority.
- Fins registry still starts from the documents default registry, then overwrites/registers Fins-specific processors.
- Focused tests and pyright pass.

## Non-Goals

- Do not change `ProcessorRegistry` behavior.
- Do not change Docling / Markdown / BS / Fins processor priority, fallback, matching, or processor implementation.
- Do not add compatibility alias, compatibility re-export, wrapper, or facade for the old name.
- Do not touch unrelated Web / Fins ingestion / Host / Engine state machine behavior.

## Scope Boundary

Expected implementation scope:

- `dayu/documents/processors/registry.py`
- `dayu/documents/processors/__init__.py`
- `dayu/documents/processors/_doc_processor_factory.py`
- `dayu/fins/processors/registry.py`
- focused documents / fins processor registry tests
- README files only if their update constraints and reader scope require it
- `docs/host/issues-implementation-control.md` for control-state and residual-risk bookkeeping

## Blocking Open Questions

None.

## Next Gate

Proceed to plan gate. AgentCodex should generate a code-generation-ready plan before implementation.
