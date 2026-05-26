# PR 68 post-draft fullrepo validation fix - Codex - 2026-05-26

## Gate

- Current gate: post-draft fullrepo validation fix
- Role: fix agent
- Scope: only the validation failure in `tests/runtime/test_scene_assets_migration.py::test_scene_manifest_agent_policy_carries_old_max_iterations_only`
- Non-goals: no commit, no push, no PR, no rewrite of existing dispatch B1/B2 fix

## Root Cause

`smoke_host_public_conversation_memory` is a new ordinary Host public smoke scene. Its manifest declares the same ordinary smoke-style `agent_policy` shape as `smoke_host_public_multiturn`:

- `max_iterations`: `20`
- `allow_tool_calls`: `true`

The migration test classifies ordinary scenes with migrated `agent_policy.max_iterations` through `_OLD_SCENE_MAX_ITERATIONS`. The existing ordinary smoke scene `smoke_host_public_multiturn` was already listed with value `20`, but the new `smoke_host_public_conversation_memory` scene was not. As a result, the test treated it as an unknown non-compactor scene and incorrectly expected `agent_policy is None`.

This is a test scene inventory drift, not evidence that the new manifest's `allow_tool_calls` field is wrong.

## Changed Files

- `tests/runtime/test_scene_assets_migration.py`
  - Added `smoke_host_public_conversation_memory: 20` to `_OLD_SCENE_MAX_ITERATIONS`.
- `docs/reviews/pr-68-postdraft-fullrepo-validation-fix-codex-20260526.md`
  - Added this completion artifact.

## Validation

- Reproduced the focused failure before the fix:
  - `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py::test_scene_manifest_agent_policy_carries_old_max_iterations_only -q`
  - Result: failed because `agent_policy` was `{"max_iterations": 20, "allow_tool_calls": true}` while the stale inventory expected no policy.
- Ran the requested migration validation:
  - `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py -q`
  - Result: `6 passed in 0.16s`
- Ran the requested related runtime/service validation:
  - `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q`
  - Result: `58 passed in 0.87s`
- Ran the requested type check:
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## Documentation Decision

No README update was needed. The change only corrects a test inventory for an existing manifest contract and does not alter user-facing commands, architecture, runtime behavior, configuration semantics, or test maintenance rules.

## Residual Risks

No residual risk remains for this validation failure. The fix intentionally does not remove `allow_tool_calls` from the manifest because direct evidence shows the existing ordinary public multiturn smoke scene uses the same field style.
