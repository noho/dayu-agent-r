# Phase 12 Slice 4 Code Review Controller Adjudication

## Scope

- Work unit: Phase 12 ToolsDiscovery / ScenePrepare / ConfigLoader runtime assembly
- Gate: Phase 12 Slice 4 code review adjudication
- Implementation artifact: `docs/reviews/phase12-slice4-implementation-codex-20260521.md`
- Review artifacts:
  - `docs/reviews/phase12-slice4-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-slice4-code-review-ds-20260521.md`

## Verdict

Both reviewers returned PASS with blocking findings count = 0. The implementation satisfies the Slice 4 boundary: `ScenePrepare` is layer-neutral, takes explicit manifest / prompt roots, validates and renders single-run scene inputs, and does not modify Host public interface.

Controller decision: enter a narrow Slice 4 test-hardening fix. No production metadata shape or schema redesign is required.

## Findings Adjudication

### P12-S4-F1: optional missing fragment behavior lacks direct regression coverage

- Sources: MiMo finding 1, DS finding 1.
- Decision: accepted-current-fix for focused test coverage; rejected-current-fix for changing `PreparedSceneInputs` metadata shape.
- Rationale: Optional fragment skip is an intentional behavior. The manifest source ref and prepared digest already include the manifest declaration, while `fragment_refs` represents loaded fragments. A new public `missing` field is not required in this slice, but the skip branch should have a regression test.

### P12-S4-F2: symlink escape containment is not covered by automated test

- Source: DS residual risk 1 and MiMo manual verification.
- Decision: accepted-current-fix.
- Rationale: The design explicitly requires resolved-path containment after symlink resolution. Manual verification is not enough for this architecture-sensitive filesystem boundary.

### P12-S4-F3: inherited duplicate context slot parent-priority behavior lacks explicit test

- Source: MiMo residual risk 3.
- Decision: accepted-current-fix.
- Rationale: Parent-first context slot order is part of the scene inheritance contract. A focused test protects this behavior without changing production code.

### P12-S4-F4: duplicate fragment order error message lacks source detail

- Source: DS finding 2.
- Decision: deferred.
- Rationale: The current error fails fast and correctly identifies duplicate order. Improving the diagnostic message is useful but not required for correctness, public contract, or current phase exit.

## Required Fix Scope

Fix should be limited to:

- `tests/runtime/test_scene_prepare.py`
- `docs/reviews/phase12-slice4-implementation-codex-20260521.md` addendum if useful

No production code changes are expected unless a new test reveals a real implementation defect.

## Validation Required After Fix

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
- `git diff --check`
