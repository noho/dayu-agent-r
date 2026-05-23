# PR 68 Post-Draft Re-Review: Compactor AgentPolicy / User Prompt Template Ownership

**Reviewer**: AgentDS (DeepReview)
**Date**: 2026-05-23
**Gate**: P12.5 compactor AgentPolicy / user prompt template ownership fix
**Scope**: working-tree uncommitted diff (19 files, +382/-64)
**Pre-check**: affected pytest 364 passed; pyright dayu tests 0; git diff --check clean

---

## Verdict: PASS — no blocking findings

---

## Findings

### Finding 1 (INFO) — Compactor AgentPolicy ownership is correctly transferred from hardcoded constants to scene-defined typed policy

**Severity**: INFO
**Files / Lines**:
- `dayu/config/prompts/manifests/conversation_compaction.json:14-23` — scene manifest now declares full `agent_policy` block
- `dayu/host/llm_compaction.py:185-186` (removed) — `_COMPACTOR_MAX_ITERATIONS`, `_COMPACTOR_TOOL_TIMEOUT_SECONDS` constants deleted
- `dayu/host/llm_compaction.py:264-271` (removed) — inline `AgentPolicy(...)` construction in `_agent_request` removed
- `dayu/host/llm_compaction.py:139` — `agent_policy: AgentPolicy` is now a required `__init__` parameter
- `dayu/host/llm_compaction.py:159-160` — type check `isinstance(agent_policy, AgentPolicy)`
- `dayu/service/host_assembly.py:640-689` — `_compactor_agent_policy_from_scene_inputs` validates all 8 fields and constructs typed `AgentPolicy`
- `dayu/service/host_assembly.py:503` — `compactor_agent_policy=compactor_prompts.agent_policy` wired into `CompactorRunnerBaseline`
- `dayu/host/api.py:939` — `compactor_agent_policy: AgentPolicy` field on `CompactorRunnerBaseline`
- `dayu/host/api.py:962-966` — `__post_init__` type validation
- `dayu/host/open_host.py:651` — passes `compactor_agent_policy` into `LLMContextCompactor`

**Evidence**: Hardcoded `_COMPACTOR_MAX_ITERATIONS = 1` and `_COMPACTOR_TOOL_TIMEOUT_SECONDS = 1.0` are fully removed. The `AgentPolicy` flow is: scene manifest → `ScenePrepare` (as `agent_policy_override`) → Service `_compactor_agent_policy_from_scene_inputs` → typed `AgentPolicy` → `CompactorRunnerBaseline.compactor_agent_policy` → `LLMContextCompactor.__init__` → `_agent_request`. No shortcuts remain.

---

### Finding 2 (INFO) — User prompt template is correctly extracted from scene manifest fragments and placed under execution profile control

**Severity**: INFO
**Files / Lines**:
- `dayu/config/prompts/manifests/conversation_compaction.json:33-40` — fragments now contain only 1 entry (`conversation_compaction_system`); old `conversation_compaction_user` fragment removed
- `dayu/config/execution_profiles.json:15,18,63,80,151,219` — all 4 profiles gain `user_prompt_template_path: "scenes/conversation_compaction_user.md"` in `compactor_baseline`
- `dayu/runtime/config_loader.py:196-204` — `CompactorBaselineConfig` gains `user_prompt_template_path: str` field
- `dayu/runtime/config_loader.py:1387-1416` — `_parse_compactor_baseline` now requires `user_prompt_template_path` in allowed fields and returns it
- `dayu/service/host_assembly.py:576-595` — `_read_compactor_user_prompt_template` reads file from `compactor_baseline.user_prompt_template_path`
- `dayu/service/host_assembly.py:598-623` — `_resolve_prompt_asset_path` validates path is relative and does not escape prompt asset root
- `dayu/service/host_assembly.py:626-637` — `_require_non_empty_text` helper validates non-empty configured path
- `dayu/service/host_assembly.py:341` — `_COMPACTOR_PROMPT_FRAGMENT_COUNT` constant updated from `2` to `_COMPACTOR_SYSTEM_PROMPT_FRAGMENT_COUNT = 1`

**Evidence**: The user prompt template file `scenes/conversation_compaction_user.md` exists and contains `<<compaction_request>>` placeholder. Service reads it via `execution_profile.compactor_baseline.user_prompt_template_path` (not via scene fragments). Host never reads prompt asset files. The separation is clean: scene manifest defines system prompt + AgentPolicy; execution profile defines which user prompt template file to use.

---

### Finding 3 (INFO) — Host correctly receives only typed fields and does not read config or prompt assets

**Severity**: INFO
**Files / Lines**:
- `dayu/host/api.py:937-943` — `CompactorRunnerBaseline` fields are all typed: `RunnerSpec`, `RunnerCallOptions`, `AgentPolicy`, `str`, `Path`, `bool`
- `dayu/host/open_host.py:646-658` — `LLMContextCompactor` is constructed from `CompactorRunnerBaseline` fields inside Host opener composition root
- `dayu/host/llm_compaction.py:134-178` — `LLMContextCompactor.__init__` only validates and stores typed parameters; no file I/O or config reading
- `dayu/host/llm_compaction.py:216-254` — `_agent_request` receives `agent_policy` as parameter and passes it directly to `AgentRunRequest`
- `dayu/host/llm_compaction.py:1-63` — module imports: no `dayu.config`, no `dayu.runtime.config_loader`, no `pathlib` used for reading prompt assets

**Evidence**: Host module `llm_compaction.py` does not import any config loading or prompt asset reading capability. The `_COMPACTOR_RUN_ID_PREFIX = "context-compactor"` is a Host-internal constant (not config-derived, not scene-derived), consistent with the architecture rule that compactor policy id is Host-internal.

---

### Finding 4 (INFO) — Tests are correctly updated for new contract

**Severity**: INFO
**Files / Lines**:
- `tests/host/test_llm_compaction.py:48-53` — `_TEST_AGENT_POLICY` fixture with typed `AgentPolicy`
- `tests/host/test_llm_compaction.py:78-83` — `_llm_compactor` factory passes `agent_policy`
- `tests/host/test_llm_compaction.py:87-105` — `test_llm_context_compactor_requires_scene_prompt_template` updated docstring and passes `agent_policy` in error-path constructions
- `tests/host/test_llm_compaction.py:130-139` — `test_llm_context_compactor_builds_tool_disabled_request` asserts `seen[0].agent_policy is _TEST_AGENT_POLICY` and removes old `allow_tool_calls is False` check (now covered by typed AgentPolicy)
- `tests/host/test_open_host_runtime.py:489-498` — `test_compactor_runner_baseline_maps_to_host_owned_compactor` passes `compactor_agent_policy`
- `tests/host/test_public_compact_smoke.py:96-100` — `_compactor_baseline_inputs()` returns 3-tuple including `AgentPolicy`
- `tests/host/test_public_compact_smoke.py:187-228` — updated helper reads user prompt template from `_PACKAGE_CONFIG_ROOT / "prompts" / compactor_baseline.user_prompt_template_path`, validates `agent_policy_override` all required fields, constructs typed `AgentPolicy`
- `tests/host/test_public_open_host_options.py:271-287` — `test_compactor_runner_baseline_validates_typed_fields` adds `compactor_agent_policy` type error path
- `tests/runtime/test_config_loader.py:768-843` — new `test_compactor_baseline_requires_user_prompt_template_path` test verifies fail-fast on missing field
- `tests/runtime/test_config_loader.py:297-300` — verifies `user_prompt_template_path` in default config
- `tests/runtime/test_scene_assets_migration.py:251-265` — updated to allow compactor scene to declare full policy (not just `max_iterations`)
- `tests/service/test_host_assembly.py:115-136` — verifies `compactor_baseline.compactor_agent_policy` equals expected typed `AgentPolicy`
- `tests/service/test_host_assembly.py:283-327` — new `test_compactor_prompt_scene_requires_one_system_fragment` and `test_compactor_prompt_scene_requires_agent_policy` tests
- `tests/service/test_host_assembly.py:726-755` — `_custom_compactor_scene_locations` updated: adds `agent_policy` block, removes `conversation_compaction_user` fragment

**Evidence**: All test changes are consistent with the new contract. Test coverage includes: type validation, missing-field fail-fast, end-to-end composition validation, and scene migration backward-compatibility check.

---

### Finding 5 (INFO) — Documentation is correctly updated for new contract

**Severity**: INFO
**Files / Lines**:
- `dayu/README.md:61` — updates compactor assembly description to distinguish scene (system prompt + AgentPolicy) from baseline (user prompt template)
- `dayu/README.md:130` — updates extension guidance for new context compaction capability
- `dayu/config/README.md:85` — adds `user_prompt_template_path` to `compactor_baseline` field list
- `dayu/config/README.md:158-160` — updates scene manifest description: 1 fragment, user template from profile
- `dayu/config/README.md:163` — updates Service assembly description
- `dayu/host/README.md:96-97` — updates compactor baseline field description
- `dayu/host/README.md:258` — updates LLM compactor data source description (system prompt + AgentPolicy from scene; user prompt from baseline)
- `docs/host/design.md:89` — updates `execution_profiles.json` description
- `docs/host/design.md:907` — updates LLM compactor Service/Host contract description
- `docs/host/design.md:2689` — updates `LLMContextCompactor` data flow description
- `tests/README.md:114` — updates public-path smoke description

**Evidence**: All README/design changes accurately reflect the code. No stale references to "two prompt fragments", "scene assembles both prompts", or "scene_id only" remain.

---

### Finding 6 (INFO) — Architecture boundaries maintained

**Severity**: INFO
**Files / Lines**:
- `dayu/runtime/config_loader.py:18` — only imports `dayu.contracts` (layer-neutral)
- `dayu/runtime/config_loader.py:189-205` — `CompactorBaselineConfig` contains `user_prompt_template_path: str` (raw config string, not typed `AgentPolicy`)
- `dayu/service/host_assembly.py` — is the sole mapper from config/scene to Host typed input (`CompactorRunnerBaseline`)

**Evidence**: `grep '^from dayu\.(engine|host|service|ui|fins)\.' dayu/runtime/` returns no matches. The `CompactorBaselineConfig` in runtime is a layer-neutral typed config view containing raw strings; only Service transforms it into typed `AgentPolicy`. Service does not read Host internals; Host does not read config or prompt assets.

---

## Review Checklist

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Compactor AgentPolicy defined in scene, assembled by Service, typed into Host | PASS |
| 2 | User prompt template path in execution_profiles.json, read by Service | PASS |
| 3 | Host receives only typed CompactorRunnerBaseline; no config/prompt asset reading | PASS |
| 4 | Tests updated for new contract | PASS |
| 5 | Documentation (README/design/config) consistent with new contract | PASS |
| 6 | `dayu.runtime` no reverse dependency on upper layers | PASS |
| 7 | No hardcoded AgentPolicy in LLMContextCompactor or _agent_request | PASS |
| 8 | `_COMPACTOR_PROMPT_FRAGMENT_COUNT` updated from 2 to 1 | PASS |
| 9 | All 4 execution profiles gain `user_prompt_template_path` | PASS |
| 10 | Path escape validation (`_resolve_prompt_asset_path`) covers relative-to-relative, absolute, and escape attempts | PASS |

## Summary

All 5 review criteria pass without blocking findings. The diff cleanly separates concerns:

- **Scene manifest** (`conversation_compaction.json`): owns system prompt fragment + full AgentPolicy declaration
- **Execution profile** (`execution_profiles.json`): owns `user_prompt_template_path` pointing to the user prompt template asset
- **Service** (`host_assembly.py`): is the sole mapper — reads scene + profile + prompt asset, constructs typed `CompactorRunnerBaseline` including `compactor_agent_policy`
- **Host** (`api.py`, `open_host.py`, `llm_compaction.py`): receives only typed fields, constructs `LLMContextCompactor` internally, no config/file reading
- **Runtime** (`config_loader.py`): layer-neutral typed config view, no imported business-layer symbols
