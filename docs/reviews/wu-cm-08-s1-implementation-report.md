# WU-CM-08-S1 Implementation Report

## Scope

- Work unit: WU-CM-08 Compaction Material Readability And Smoke Maintenance
- Slice: S1 Focused Compact Material Test Readability
- Implementer: AgentCodex
- Branch: `work/cm-05-06-08-09`

## Changes

- Added typed test-only shape summaries in `tests/host/test_compact_material.py`:
  - `_MaterialPackShape` for compact material pack prompt-local labels and citable labels.
  - `_VNextInputShape` for vNext top-level JSON keys and section counts.
- Strengthened the existing vNext material mapping test to positively assert current top-level keys while keeping stale legacy key exclusions.
- Added shape assertions for evidence chunk labels and explicit previous compacted view pack paths, so failures identify section / prompt-local label boundaries instead of only reporting raw tuple mismatches.
- Did not modify production compact material code.

## Validation

- Baseline before edits: `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q`: 41 passed, 1 skipped.
- `source .venv/bin/activate && pytest tests/host/test_compact_material.py -q`: 35 passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations.
- `git diff --name-only`: `docs/host/issues-implementation-control.md`, `tests/host/test_compact_material.py`.
- `git diff --check`: passed.

## README Decision

- `tests/README.md`: not updated. S1 adds private helpers inside an existing Host test file and does not add a new test layer, command, shared helper module, or maintenance rule.
- `dayu/host/README.md`: not triggered because no production Host code changed.

## Residual Risk

- None identified for S1. The implementation remained test-only; production defect stop-the-line path was not triggered.
