# WU-CM-08-S2 Implementation Report

## Scope

- Work unit: WU-CM-08 Compaction Material Readability And Smoke Maintenance
- Slice: S2 Public Compact Smoke Failure Localization
- Implementer: AgentCodex
- Branch: `work/cm-05-06-08-09`

## Changes

- Extended the existing `_assert_compactor_material_instruction_contract(...)` path instead of adding a parallel overlapping helper.
- Added compact-smoke-specific assertion helpers for:
  - top-level material section shape and stale legacy section rejection;
  - forbidden internal term leakage in LLM-facing material;
  - evidence material marker retention;
  - fake compactor proposal label-only / canonical-ref leakage.
- Added positive and negative tests for the new non-trivial helpers, with negative cases matching boundary-specific failure messages.
- Replaced inline evidence/proposal assertions in the public compact smoke with the focused helpers.
- Did not modify `tests/host/public_smoke_support.py`; helpers remained compact-smoke-specific inside `tests/host/test_public_compact_smoke.py`.

## Validation

- Baseline before edits: `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q`: 41 passed, 1 skipped.
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`: 11 passed, 1 skipped.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations.
- `git diff --name-only`: `docs/host/issues-implementation-control.md`, `tests/host/test_public_compact_smoke.py`.
- `git diff --check`: passed.

## README Decision

- `tests/README.md`: not updated. S2 kept helpers private to the existing public compact smoke file and did not add a new test layer, command, shared helper module, or maintenance rule.
- `dayu/host/README.md`: not triggered because no production Host code changed.

## Residual Risk

- None identified for S2. The pre-existing `tests/host/fake_compaction.py` `cast(...)` residual was not touched and did not affect this slice.
