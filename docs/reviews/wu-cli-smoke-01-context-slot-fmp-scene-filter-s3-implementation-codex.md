# WU-CLI-SMOKE-01 Context Slot / FMP / Scene Filter S3 Implementation

## Metadata

- Gate: implementation slice S3
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Agent: AgentCodex
- Plan: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- Artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s3-implementation-codex.md`
- Commit/push/PR: not performed per controller instruction

## First-Principles Check

The S3 motivation is valid. The old entrypoint identity context slot was still declared in 12 scene manifests and still injected by CLI / smoke utility code. That made an identity label part of the LLM context slot contract even though current scene text does not consume it and Host call context already carries the user-facing actor identity separately.

Direct code facts before implementation:

- `rg -n base_user dayu/config/prompts dayu/cli tests utils` found manifest, CLI, utility and test fixture residues.
- Follow-up review found a subject-slot contract gap: multiple manifests declared `fins_default_subject`, but only `scenes/prompt.md` rendered `{{fins_default_subject}}`, and that placeholder had a leading space.
- `scenes/interactive.md` and `scenes/wechat.md` do not use a default subject slot.
- `dayu/config/prompts/base/soul.md` had no matching old identity placeholder, so it was not modified.
- Prompt / interactive / wechat manifests already select the real `get_current_time` tool through the `utils` tag; no scene text required a mechanical `current_time` placeholder addition.

## Changed Files

- `dayu/config/prompts/manifests/audit.json`
- `dayu/config/prompts/manifests/confirm.json`
- `dayu/config/prompts/manifests/decision.json`
- `dayu/config/prompts/manifests/fix.json`
- `dayu/config/prompts/manifests/interactive.json`
- `dayu/config/prompts/manifests/overview.json`
- `dayu/config/prompts/manifests/prompt.json`
- `dayu/config/prompts/manifests/regenerate.json`
- `dayu/config/prompts/manifests/repair.json`
- `dayu/config/prompts/manifests/smoke_host_public_multiturn.json`
- `dayu/config/prompts/manifests/wechat.json`
- `dayu/config/prompts/manifests/write.json`
- `dayu/config/prompts/scenes/audit.md`
- `dayu/config/prompts/scenes/confirm.md`
- `dayu/config/prompts/scenes/decision.md`
- `dayu/config/prompts/scenes/fix.md`
- `dayu/config/prompts/scenes/infer.md`
- `dayu/config/prompts/scenes/overview.md`
- `dayu/config/prompts/scenes/prompt.md`
- `dayu/config/prompts/scenes/regenerate.md`
- `dayu/config/prompts/scenes/repair.md`
- `dayu/config/prompts/scenes/smoke_host_public_multiturn.md`
- `dayu/config/prompts/scenes/write.md`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `utils/smoke_host_public_multiturn.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/runtime/test_scene_prepare.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_host_assembly.py`
- `dayu/config/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

## Implementation Details

### Review-Accepted Fix

S3 code review accepted DS F1: the CLI constant name `DEFAULT_BASE_USER` still carried the removed context-slot terminology even though runtime usage was only `display_user` / Host call context identity.

Fixed by pure semantic rename without behavior changes:

- `dayu/cli/commands/prompt.py`: `DEFAULT_BASE_USER` -> `DEFAULT_DISPLAY_USER`
- `dayu/cli/commands/interactive.py`: `DEFAULT_BASE_USER` -> `DEFAULT_DISPLAY_USER`
- `dayu/cli/commands/session.py`: `DEFAULT_BASE_USER` -> `DEFAULT_DISPLAY_USER`
- `utils/smoke_host_public_multiturn.py`: `_DEFAULT_USER` -> `_DEFAULT_ACTOR`

Values and call sites are unchanged semantically; no context slot values were reintroduced.

### Manifest Alignment

Removed the stale identity context slot from these 12 manifests:

- audit
- confirm
- decision
- fix
- interactive
- overview
- prompt
- regenerate
- repair
- smoke_host_public_multiturn
- wechat
- write

All manifests that declare `fins_default_subject` now have the corresponding scene fragment render `{{fins_default_subject}}` as a standalone line immediately after the H1 title:

- audit
- confirm
- decision
- fix
- infer
- overview
- prompt
- regenerate
- repair
- smoke_host_public_multiturn
- write

`prompt.md` no longer has a leading space before the placeholder. `interactive.json` and `wechat.json` require no context slots, and their scene fragments do not render the subject placeholder. Existing tool selection stayed unchanged: prompt / interactive / wechat still select the real current-time tool through the `utils` tag.

### CLI And Utility Entrypoints

- `dayu-cli prompt` no longer appends the old identity context slot to `context_slot_values`.
- `dayu-cli interactive` now passes an empty context slot map.
- `dayu-cli session` no longer appends the old identity context slot while preparing prompt runtime.
- `utils/smoke_host_public_multiturn.py` removed its old identity context-slot CLI argument and dataclass field.
- The smoke utility still uses a fixed Host actor for `HostCallContext`; that value is not an LLM context slot.
- The smoke utility now preserves `discovered.fins_awaiting_runtime` when it appends the built-in smoke tool to a `ServiceDiscoveredTools` result. This was required because aggregate validation exercises the same Service assembly path that builds Fins wait activation registries from effective provider configs.

### Tests

Updated S1/S2 fixture expectations to follow the new boundary:

- Prompt tests still assert `fins_default_subject` and `current_time` values where real CLI generation provides them, but no longer expect an identity slot.
- Interactive tests now assert empty context slot maps.
- Service prompt path tests still verify `fins_default_subject` is required and consumed.
- Service interactive path tests verify empty context slot maps prepare successfully.
- Host assembly and smoke tests no longer pass the removed slot.
- Runtime scene asset tests continue to verify condition-block filtering and prompt tool selection.
- Runtime scene asset tests now also protect the subject-slot invariant: any manifest declaring `fins_default_subject` must have its scene fragment render `{{fins_default_subject}}` as a standalone line; interactive/wechat must not declare or render it.

### README Updates

- `dayu/config/README.md`: documented `<when_tag>` / `<when_tool>` as ScenePrepare prompt asset control syntax that must not reach final LLM-facing output, and documented that manifests use the `utils` tag to select `get_current_time`.
- `dayu/fins/README.md`: clarified the current FMP resolver failure boundary, including second-hop failure wrapping.
- `tests/README.md`: recorded scene condition filtering, FMP resolver coverage, slot builder coverage, and the aggregate old identity slot residue scan.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py
# 58 passed

source .venv/bin/activate && pytest tests/fins/test_fmp_company_info_resolver.py
# 8 passed

source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_assembly.py
# 102 passed, 3 warnings

source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
# 91 passed, 3 warnings

source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py
# 7 passed, 3 warnings

rg -n base_user dayu/config/prompts dayu/cli tests utils
# no matches

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

Warnings are existing `edgar` deprecation warnings. `pyright` also printed a newer-version notice; it was not a type-check failure.

Follow-up subject-slot contract rework validation:

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py
# 50 passed

source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_assembly.py
# 102 passed, 3 warnings

source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
# 91 passed, 3 warnings

rg -n base_user dayu/config/prompts dayu/cli tests utils
# no matches

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

Review-accepted DS F1 naming fix validation:

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
# 91 passed, 3 warnings

source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py
# 7 passed, 3 warnings

/usr/bin/grep -rn "BASE_USER\|base_user" dayu/config/prompts dayu/cli tests utils || true
# no source matches

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

## Scope Boundaries

Not changed:

- Host / Engine state machines.
- Durable schema.
- Fins storage protocols.
- `dayu/config/prompts/base/soul.md`.
- Prompt / interactive / wechat `get_current_time` tool availability.
- Real FMP network smoke.

## Residual Risks

- Real provider smoke was not executed. Classification: optional later validation.
- `current_time` is still generated by the Service slot builder for entrypoints that call it, but prompt assets do not consume a `current_time` placeholder because prompt / interactive / wechat use the real current-time tool. Classification: accepted S3 design choice, covered by manifest tool selection tests.

## Completion Status

S3 implementation is complete locally. No commit, push, issue or PR was created.
