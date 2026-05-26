# PR 68 post-draft fullrepo validation fix re-review — MiMo — 2026-05-26

## Gate

- Current gate: re-review scene asset migration validation fix
- Role: narrow validation-fix re-reviewer
- Scope: `tests/runtime/test_scene_assets_migration.py` and the codex fix artifact
- Constraint: read-only review, no file modification, no commit/push/approve/comment

## Verdict

**PASS**

## Review Checklist

### 1. Is `smoke_host_public_conversation_memory: 20` the correct minimal fix?

**Yes.** The test `test_scene_manifest_agent_policy_carries_old_max_iterations_only` uses `_OLD_SCENE_MAX_ITERATIONS` as the authoritative inventory of ordinary scenes whose `agent_policy.max_iterations` was migrated from the old runner. The manifest declares `max_iterations: 20`, which matches the identical ordinary smoke scene `smoke_host_public_multiturn`. Adding the entry to the inventory is the correct minimal fix — it aligns the test's expectations with the manifest's declared value.

### 2. Does the fix mask an invalid manifest?

**No.** The test still enforces at lines 275–290:
- `agent_policy` must be a `Mapping`
- `agent_policy.max_iterations` must equal the expected value (`20`)
- `agent_policy` must not contain `tool_timeout_seconds` or `tool_execution_timeout_seconds`
- `prepare_scene` must produce an `agent_policy_override` with matching `max_iterations`

The `allow_tool_calls: true` field in the manifest is not tested by this particular test, but it is a standard agent_policy field validated elsewhere (schema validation in `test_migrated_scene_manifest_schema_excludes_legacy_fields` and assembly in `test_all_migrated_scene_assets_prepare_successfully`). No validation is bypassed.

### 3. Is not changing the manifest appropriate?

**Yes.** Direct evidence:
- `smoke_host_public_multiturn` (the existing ordinary public smoke scene) has the identical `agent_policy` shape: `{"max_iterations": 20, "allow_tool_calls": true}`.
- Both scenes share the same `tool_selection` pattern (`mode: "select"`, `tool_tags_any: ["manual-smoke"]`).
- Both are ordinary smoke scenes, not compactor scenes.

The manifest is correct as-is. Changing it would break the established pattern.

### 4. Are reported validations sufficient?

**Yes.** The fix artifact reports:
- Focused failure reproduction before fix: ✓
- Full migration test suite (6 passed): ✓
- Related runtime/service tests (58 passed): ✓
- Pyright type check (0 errors): ✓

I independently verified `pytest tests/runtime/test_scene_assets_migration.py -q` → `6 passed`.

### 5. Are unrelated changes included?

**No.** Only `_OLD_SCENE_MAX_ITERATIONS` in the test file was modified (one line added). No other code, configuration, or documentation was changed.

## Residual Risks

None. The fix is a minimal test inventory correction for a valid new manifest. Future smoke scenes with `agent_policy` will need the same inventory addition — this is expected behavior of the migration test contract, not a design flaw.
