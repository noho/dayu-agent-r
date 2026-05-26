# PR 68 post-draft fullrepo validation fix re-review (DS) — 2026-05-26

## Gate

- Current gate: re-review scene asset migration validation fix
- Role: narrow validation-fix re-reviewer
- Scope: only `tests/runtime/test_scene_assets_migration.py` fix and codex review artifact
- Non-goals: no file modification, no commit, no push, no PR comment

## Verdict: PASS

The fix is correct, minimal, and does not mask any manifest issue.

## Finding Status

### F1 — `_OLD_SCENE_MAX_ITERATIONS` entry addition: PASS

**Evidence chain:**

1. `smoke_host_public_conversation_memory.json` declares `agent_policy: {max_iterations: 20, allow_tool_calls: true}`.
2. `smoke_host_public_multiturn.json` declares the identical `agent_policy` shape and is already listed with value `20`.
3. The test (`test_scene_manifest_agent_policy_carries_old_max_iterations_only`) classifies scenes via `_OLD_SCENE_MAX_ITERATIONS`:
   - Listed → expects `agent_policy.max_iterations == expected`, asserts no legacy timeout fields.
   - Not listed + not compactor → expects `agent_policy is None` (fails here before fix).
4. Adding `"smoke_host_public_conversation_memory": 20` aligns the test inventory with the manifest, matching the precedent set by `smoke_host_public_multiturn`.

**Why not remove `allow_tool_calls` from the manifest instead:** The test does not forbid `allow_tool_calls` for ordinary scenes — it only checks `max_iterations` matches and that legacy fields (`tool_timeout_seconds`, `tool_execution_timeout_seconds`) are absent. `allow_tool_calls` is a current-schema field, not a legacy field. Removing it would be a manifest change with no test-driven justification.

### F2 — Manifest correctness: PASS

Manifest `smoke_host_public_conversation_memory.json` passes all schema guards:
- All top-level keys are in `_ALLOWED_MANIFEST_FIELDS` (verified by `test_migrated_scene_manifest_schema_excludes_legacy_fields`).
- All `model` keys are in `_ALLOWED_MODEL_FIELDS`.
- No `conversation` or `runtime` legacy keys.
- Fragment paths resolve under prompt root (verified by `test_all_migrated_scene_assets_prepare_successfully`).
- Empty `context_slots` is valid — `_required_context_slot_values` handles this.

### F3 — No unrelated changes in scope: PASS

The diff in `tests/runtime/test_scene_assets_migration.py` is exactly one line: the dictionary entry addition. No other modifications to migration test logic, constants, or assertions.

## Validation Reviewed

Codex review reports:
- Focused failure reproduction → confirmed root cause matches the evidence.
- Full migration test suite: 6 passed → consistent with the fix scope.
- Related runtime/service tests: 58 passed → no regression in adjacent test suites.
- Pyright: 0 errors, 0 warnings → type-clean.

All reported validations are appropriate and sufficient for a test inventory correction.

## Residual Risks

None. The fix corrects a pure test inventory drift. The manifest is structurally validated by independent schema tests. The `allow_tool_calls` field is intentionally present in both ordinary smoke scenes and is not a legacy artifact.
