# Phase 12.1 Aggregate Deep Review — AgentDS — 2026-05-22

## Review Scope

Complete Phase 12.1 work unit diff: `git diff 9d99fee...HEAD` (14 commits, 107 files, +12761/−1961). Current branch: `docs/phase12-design-discussion`.

Design source: `docs/host/design.md`. Control doc: `docs/host/implementation-control.md`. Plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`.

## Independent Verification Results

| Command | Result |
|---|---|
| `pytest tests/runtime -q` | 208 passed |
| `pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q` | 11 passed |
| `pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q` | 83 passed |
| `python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/runtime tests/engine tests/host utils/smoke_host_public_multiturn.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check 9d99fee...HEAD` | trailing whitespace in 1 review artifact only (known, non-blocking) |

## Findings

### F1 (PASS) — Host public surface not widened beyond plan

`OpenHostOptions` (`dayu/host/api.py:968`) preserves all existing public field names. The typed shape changes (policy types moving from raw dicts to typed dataclasses, tool truncation policy, provider extension mapping) are approved by the plan. No DSL parsing for config/scene/provider was moved into Host — `ConfigLoader`, `ScenePrepare`, and `provider_extensions.py` handle parsing in their respective layers. Host receives only final typed inputs.

### F2 (PASS) — dayu.runtime import boundary clean

- `dayu/runtime/__init__.py` explicitly states the hard constraint: no imports from `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins`.
- AST-based boundary test `test_runtime_does_not_import_business_layers` passes, scanning all `.py` files under `dayu/runtime/`.
- Explicit coverage tests exist for all Phase 12 modules: `config_loader.py`, `location.py`, `scene_prepare.py`, `tools_discovery.py`, `assembly.py`, `tool_truncation.py`.
- Phase 0 forbidden modules test (`aiohttp`, `requests`, `httpx`) also passes.
- `third-party filelock` import confinement test passes — only `dayu.runtime.filelock` imports the `filelock` package.
- Manual grep for `import.*dayu\.(engine|host|service|ui|fins)` in `dayu/runtime/` returns zero actual imports (only the docstring constraint itself).

### F3 (PASS) — ConfigLoader new schema is fail-fast, map-key id is canonical

- All five config files have `_require_exact_fields` enforcement — unknown fields are rejected immediately.
- `_require_no_forbidden_id_fields` prevents embedded `model_id`, `profile_id`, `provider_id`, etc. in record bodies; ids come from map keys only.
- Old `llm_models.json` and `run.json` files no longer exist on disk. `_LEGACY_CONFIG_FILES` constant is a diagnostic helper, not a read path. `config_file_names()` returns only the five current file names.
- `_resolve_record_map` enforces single-parent `extends` (list → error, self-reference → error, cycle → error, missing parent → error).
- Cross-file reference validation: `_validate_execution_model_references` checks model_id + runner_option_hint_id across `models.json` and `execution_profiles.json`; `_validate_host_runtime_lane_references` checks lane names across `host_runtime.json` and `runtime_lanes.json`.
- Typed config views (`ModelsConfig`, `ExecutionProfilesConfig`, `HostRuntimeConfig`, `RuntimeLanesConfig`, `ToolDiscoveryConfig`) align with the five-file design.

### F4 (PASS) — ScenePrepare schema is scene-only

- `_ALLOWED_MANIFEST_FIELDS` confirms no `conversation`, `runtime`, `prompt_mt`, `workflow`, `artifact`, `parser`, `retry`, or `checkpoint` fields.
- `model` hint block: only `default_model_id` and `runner_option_hint_id` — typed, fail-fast on unknown fields.
- `agent_policy` override block: 8 allowlisted fields, `fallback_mode` validated against `{"force_answer", "raise_error"}`, all fields typed and optional.
- `tool_selection` block: `mode` enum (`all`/`none`/`select`), `tool_names` + `tool_tags_any` allowlist, `allow_empty` default `false`.
- `defaults.missing_required_fragment`: only `"fail_closed"` accepted.
- Context slots: only `value_type=string` supported; unknown type → error.
- Scene id pattern enforced: `^[A-Za-z][A-Za-z0-9_.-]*$`.
- Inheritance: single-parent only (multi → error), cycle detection via stack, child-overrides-parent merge with fragment uniqueness validation.

### F5 (PASS) — ToolsDiscovery / tool bundle selection correct

- `SceneToolCatalog` (`scene_prepare.py:139`) stores only `SceneToolInfo(name, tags)` — no callables, no `ToolBundle` references.
- `SceneToolCatalog.from_tool_bundle()` projects `ToolBundle.definitions` → name+tags only.
- `_select_tools()` operates on `SceneToolSelection` config against `SceneToolCatalog`: `all` → `None` (all tools), `none` → empty frozenset, `select` → union of explicit names + tag-matched names.
- Unknown tool names → `ScenePrepareError`. Tag mismatch with `allow_empty=false` → error. Empty selection with `allow_empty=false` → error.
- No raw `ToolBundle` is stuffed into `PreparedSceneInputs` or per-run request.

### F6 (PASS) — Engine provider extension helper fail-closed and correctly placed

- `provider_request_extension_from_json()` is in `dayu/engine/provider_extensions.py` — Engine layer, not runtime.
- `dayu.runtime` does not import it (confirmed by boundary test and manual grep).
- Unknown `type` → `ProviderExtensionConfigError("unsupported type")`. Unknown fields → `_require_exact_fields` error. Illegal enum values → `_parse_enum` error. Invalid field combinations → `_wrap_contract_error` catches `ValueError` from contract dataclass `__post_init__`.
- Six provider types supported: `openai_reasoning`, `anthropic_thinking`, `deepseek_thinking`, `mimo_thinking`, `gemini_thinking`, `qwen_thinking`.
- Smoke script imports it as `from dayu.engine.provider_extensions import provider_request_extension_from_json` — consuming at Engine layer, not runtime.

### F7 (PASS) — Tool truncation declaration/effective split and policy defaults correct

- `dayu/runtime/tool_truncation.py`: `effective_tool_truncate_spec()` takes a `ToolTruncateSpec` declaration + `default_limits_by_strategy` + `default_ttl_seconds`, returns completed spec. Disabled specs returned as-is. Enabled specs require `strategy`; missing limit for strategy → `ValueError`.
- `dayu/runtime/assembly.py`: `tool_truncation_policy_defaults()` projects `ToolTruncationPolicyConfig` → `ToolTruncationPolicyDefaults` (enabled, limits by strategy, TTL). `effective_tool_truncate_spec_from_policy()` chains policy defaults into `effective_tool_truncate_spec()`.
- The declaration (tool author) / effective (runtime assembly) split is clean: tool authors declare `ToolTruncateSpec` with optional fields; the assembly layer fills in policy defaults.

### F8 (PASS) — smoke_host_public_multiturn.py is real Service-like assembly

The smoke script (`utils/smoke_host_public_multiturn.py`) assembles the full path:

1. `resolve_runtime_locations(project_root=..., package_config_root=...)` → `RuntimeLocations`
2. `ConfigLoader().load(workspace_config_dir=locations.config_overlay_dir)` → `RuntimeConfig`
3. `ToolsDiscovery(...).discover(...)` → `ToolBundle` → `SceneToolCatalog.from_tool_bundle()`
4. `prepare_scene(ScenePrepareRequest(...))` → `PreparedSceneInputs`
5. `select_runner_option_hint(...)` → `RunnerOptionHintSelection`
6. `merge_agent_policy_config(...)` → `MergedAgentPolicyConfig`
7. `provider_request_extension_from_json(...)` for provider extension mapping
8. `_compose_open_host_options(...)` builds `OpenHostOptions` from typed assembly output
9. `open_host(options)` → public Host handle

No manual hardcoded defaults mask schema gaps. The `_prepare_runtime_assembly` function fails before Host call when tools aren't discovered (verified by `test_runtime_assembly_fails_before_host_when_tools_not_discovered`).

### F9 (PASS) — README / test docs match current code facts

Confirmed by Slice 6 dedicated review (F1-F6 in `phase12-1-slice6-code-review-ds-20260521.md`):
- Root `README.md`: old `run.json` and `prompt_mt` references removed; config table, model examples, and `provider_request_extension` description aligned.
- `dayu/README.md`: `assembly` module listed; provider extension DSL extension entry documented.
- `tests/README.md`: import boundary coverage list includes all Phase 12 modules; weak typing guard coverage documented.
- `dayu/config/README.md`, `dayu/host/README.md`, `dayu/engine/README.md`: confirmed current by Slice 6 implementation artifact — no changes needed.

### F10 (PASS) — Residual risks have owners; no unowned blockers

Plan Section 7 lists 5 residual risks. Slice 6 implementation artifact lists 6 (same set, expanded detail). All have explicit owners:

1. Service/composition helper formal extraction → Service assembly work unit
2. Default financial tool provider / real provider smoke → Service / Fins / tool provider hardening
3. Provider model catalog maintenance → execution profile / model catalog maintenance
4. Real Service / UI / CLI workflow integration → Service / UI / workflow work unit
5. Tool truncation declaration coverage → tool provider hardening
6. Financial scene content and Fins storage business path → Service / Fins / configuration work unit

No risk is unowned. None blocks `ready-to-open-draft-PR`.

## Adversarial Failure Pass

| Attack | Result |
|---|---|
| Unknown field in any config file | `ConfigShapeError` / `ConfigFieldError` — fail-fast |
| Embedded `model_id` in record body | `ConfigFieldError` — forbidden id field |
| Multi-parent `extends` in config | `ConfigExtendsError` — not allowed |
| Multi-parent `extends` in scene | `ScenePrepareError` — allows only one parent |
| Circular `extends` | `ConfigExtendsError` / `ScenePrepareError` — cycle detected |
| Missing parent in `extends` | `ConfigExtendsError` — parent not found |
| Unknown provider extension `type` | `ProviderExtensionConfigError` — unsupported type |
| Unknown field in provider extension DSL | `ProviderExtensionConfigError` — unknown fields |
| Scene with `conversation` / `runtime` / `prompt_mt` field | `ScenePrepareError` — unsupported fields |
| Unknown tool name in `tool_selection` | `ScenePrepareError` — unknown tool_names |
| Tag mismatch with `allow_empty=false` | `ScenePrepareError` — matched no tools |
| Required fragment missing with `fail_closed` | `ScenePrepareError` — required fragment missing |
| Unresolved placeholder after rendering | `ScenePrepareError` — unresolved placeholder remains |
| Path escape in fragment path | `ScenePrepareError` — path escapes root |
| `fallback_mode` illegal value | Rejected at parse time (both ScenePrepare and assembly) |
| `dayu.runtime` importing business layer | AST boundary test fails |
| Old `llm_models.json` / `run.json` read | Files don't exist; only referenced in diagnostic constant |

All fail-closed. No silent degradation paths found.

## Architecture Constraint Verification

| Constraint | Status |
|---|---|
| `dayu.runtime` no import of engine/host/service/ui/fins | PASS (AST test + manual grep) |
| `dayu.runtime` no concrete tool/provider client imports | PASS |
| Host no config/scene DSL parsing | PASS (ConfigLoader/ScenePrepare handle parsing) |
| Engine provider extension in Engine layer | PASS (`dayu/engine/provider_extensions.py`) |
| ScenePrepare scene-only (no conversation/runtime/prompt_mt) | PASS |
| ConfigLoader five-file schema, map-key id canonical | PASS |
| ToolsDiscovery no raw ToolBundle in per-run request | PASS |
| No compatibility re-exports or wrappers | PASS |

## Verdict

**PASS** — No blocking findings.

All 302 tests pass. Pyright reports 0 errors across the full review scope. All 10 review focus areas are confirmed clean. The adversarial failure pass shows fail-closed behavior on every tested edge case. Architecture constraints are satisfied. Residual risks are all owned by subsequent work units and none blocks `ready-to-open-draft-PR`.

The Phase 12.1 work unit delivers a coherent, layer-clean runtime assembly foundation: ConfigLoader with fail-fast typed views, ScenePrepare with scene-only manifest schema, ToolsDiscovery with catalog projection, runtime assembly helpers with four-layer priority merge, Engine provider extension parsing with fail-closed dispatch, tool truncation declaration/effective split, and a real Service-like assembly smoke that exercises the full path without manual defaults.
