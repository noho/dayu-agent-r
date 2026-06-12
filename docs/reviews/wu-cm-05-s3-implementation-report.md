# WU-CM-05-S3 Implementation Report

## Scope

- Work unit: WU-CM-05 LLM Compaction Proposal Typed Parsing
- Slice: S3 Contract and boundary cleanup
- Implementer: AgentCodex
- Branch: `work/cm-05-06-08-09`

## Changes

- Removed `cast` usage from `tests/host/test_llm_compaction.py`.
- Added `_compact_input_json(...)` to explicitly narrow `ConversationCompactInputVNext.to_json()` into a JSON object before passing it to the deterministic proposal helper.
- Changed `_proposal_json(...)` to parse raw JSON into `JsonValue`, validate it with `_required_mapping(...)`, then return a mutable shallow `dict[str, JsonValue]`.
- Changed `_material_json_from_compactor_prompt(...)` to use the same explicit JSON object narrowing path.
- Added `_is_json_mapping(...)` as a typed guard for JSON object narrowing.

## Deferred Finding Closure

- Closed DS-F02 from `docs/reviews/code-review-20260612-143730.md`: `_proposal_json` no longer uses `cast`.
- No production parser behavior was changed in this slice.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q`: 37 passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations.
- `rg -n "cast\\(|from typing import .*cast" tests/host/test_llm_compaction.py`: no matches.

## Fix Gate Update 2026-06-12

- Fix gate: completed.
- Accepted review note addressed: `_proposal_json(...)` docstring now documents `json.JSONDecodeError` and `AssertionError` instead of the stale `TypeError`.
- Validation: `pytest tests/host/test_llm_compaction.py -q` still passes with 37 tests after the docstring fix.
- Validation: `python -m pyright dayu/ tests/ utils/` still reports 0 errors, 0 warnings, 0 informations after the docstring fix.

## README Decision

- `dayu/host/README.md`: not updated. This slice does not change Host public API, stable architecture boundary, event flow, state machine, or developer-facing Host contract.
- `tests/README.md`: not updated. This slice changes helper implementation inside an existing Host test file; it does not add a new test layer, command, or maintenance rule.

## Residual Risk

- `tests/host/fake_compaction.py` still contains an unrelated existing test helper `cast(...)`. It is outside the approved S3 file scope and was not introduced or expanded by this slice.
