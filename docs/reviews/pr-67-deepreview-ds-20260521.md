# PR 67 Deep Review — Phase 12 Runtime Assembly

**Reviewer**: AgentDS
**Artifact**: `docs/reviews/pr-67-deepreview-ds-20260521.md`
**Verdict**: PASS
**Blocking**: 0
**Date**: 2026-05-21

## Review Scope

PR 67 (`docs/phase12-design-discussion` → `main`) delivers Phase 12 runtime assembly:
`ToolsDiscovery`, `ConfigLoader`, `ScenePrepare` layer-neutral components, canonical
source ref migration, config schema migration, legacy scene asset migration, and
aggregate review fixes.

Review against design source `docs/host/design.md` and control source
`docs/host/implementation-control.md`.

## Validation Run

| Command | Result |
|---|---|
| `pytest tests/runtime -q` | 174 passed |
| `pytest tests/contracts tests/engine/test_config_models.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 69 passed |
| `pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host tests/engine/test_config_models.py` | 0 errors, 0 warnings |
| `git diff --check main...HEAD` | 1 trailing whitespace (see L1) |
| AST import boundary scan `dayu.runtime` | 0 business layer imports |
| AST import boundary scan `dayu.contracts` | 0 upper layer imports |
| `gh pr view 67` | draft=true, state=OPEN, mergeStateStatus=CLEAN, statusCheckRollup=[] |
| Branch alignment | local HEAD = `fe4f408`, pushed HEAD confirmed same via `git log` |

## Findings

### L1 — `dayu/config/prompts/scenes/decision.md:27`: trailing blank line at EOF

`git diff --check main...HEAD` reports `dayu/config/prompts/scenes/decision.md:27: new blank line at EOF.`

**Severity**: Low. Prompt asset trailing whitespace; no functional impact on `ScenePrepare`
assembly or content digest. Could cause minor CI noise if a future whitespace check is
added.

### N1 — `SERVICE_COMPOSITION` enum member unused in runtime tool discovery path

`dayu/contracts/tool_source.py` defines `ToolBundleSourceKind.SERVICE_COMPOSITION`, which
is excluded from `config_loader.py`'s `_TOOL_DISCOVERY_SOURCE_KINDS` validation set.
This is correct by design — `SERVICE_COMPOSITION` represents Service-level composition
that bypasses `tool_discovery.json` config — but the unused member in the contracts enum
has no consumer within this PR's scope.

**Severity**: Observation. Not a defect. The member is reserved for future Service
assembly paths. No action required.

## Architecture Boundaries — PASS

- `dayu.runtime.*` imports zero business layer modules (AST scan confirms no
  `dayu.engine/host/service/ui/fins`).
- `dayu.contracts.*` imports zero upper layer modules (AST scan confirms no
  `dayu.engine/host/runtime/service/ui/fins`).
- `ToolBundleSourceKind` / `ToolBundleSourceRef` canonical owner is `dayu.contracts.tool_source`,
  re-exported via `dayu.contracts.__init__` and imported by `dayu.host.tooling` as a
  coherent public API surface (accepted in plan review as non-compatibility re-export).
- `_digest.py` is a private shared helper; only depends on `dayu.contracts.JsonValue`.
- Old `llm_models.json` and `run.json` deleted; no compatibility read path retained.

## Host Public Interface — PASS

- No Host public API changes. `host/tooling.py` changes are internal restructuring:
  `ToolBundleSourceKind` and `ToolBundleSourceRef` definitions moved to contracts,
  host imports from `dayu.contracts`. `HostToolingOptions` field types unchanged.
- No new per-run override fields added. No Host state machine modifications.
- Runtime assembly components deliver typed outputs consumed by Service/composition root
  for `open_host` construction-time and per-run request mapping; the mapping logic itself
  is a Service concern outside this PR.

## Config Schema Migration — PASS

- Four new config files (`models.json`, `execution_profiles.json`, `host_runtime.json`,
  `tool_discovery.json`) with typed `ConfigLoader` views.
- Overlay rules: top-level map by stable id, workspace whole-record replacement, no
  implicit deep merge, explicit single `extends`.
- `extends` inheritance validated: missing parent, multi-parent, cycle, non-map child
  all produce structured errors.
- Legacy `dayu/config/llm_models.json` and `dayu/config/run.json` deleted.
- `tests/engine/test_config_models.py` updated to match new typed view semantics
  (no `extra_payloads`).

## Scene Prepare Assembly — PASS

- Manifest schema v1: `scene_id`, `version`, `extends` (single only), `model` (concrete
  must declare), `runtime`, `conversation`, `tool_selection`, `fragments`, `context_slots`.
- `{{slot_name}}` deterministic rendering; unresolved placeholders fail closed.
- Fragment file containment: symlink escape rejected, resolved path must stay under
  `prompt_asset_root`.
- Tool selection all/none/select modes with names and tags correctly implemented;
  unknown names → error, tag-no-match → error (unless `allow_empty`).
- `SceneModelHints.temperature_profile_id` preserved (Slice 4 follow-up fix).
- Context slot dedup preserves parent-first ordering.

## Tools Discovery — PASS

- Provider resolution: `module:attribute` import path and package entry point both
  supported, with proper error wrapping (`ModuleNotFoundError` → `ToolsDiscoveryError`).
- Provider output validation: empty source_refs → error, empty definitions without
  `allow_empty` → error, duplicate provider id → error, duplicate tool names → error.
- Reserved framework tool name `fetch_more` rejected at discovery level.
- Content digest computed from tool declarations (name, schema, truncate, tags, display);
  callable references excluded.
- Non-string Mapping keys in digest canonicalization fail fast (Slice 2 fix).

## Legacy Scene Asset Migration — PASS

- 14 scene manifests migrated from old `dayu-agent` project to `dayu/config/prompts/manifests/`.
- Corresponding prompt fragments under `dayu/config/prompts/base/` and `dayu/config/prompts/scenes/`.
- `base/tools.md` cleaned of old conditional template markers (`<when_tag>`, `<when_tool>`).
- `base/agents.md` and `base/fact_rules.md` wired to context slots.
- Migration tests verify: required slots consumed by fragments, prepared messages contain
  slot values, no residual old template markers in prompt assets.

## Tests — PASS

- `tests/runtime/`: 17 test modules covering tools_discovery (basic + digest),
  config_loader, scene_prepare, scene_tool_selection, scene_assets_migration,
  import_boundary, weak_typing_guard.
- Import boundary tests explicitly cover all new runtime modules and `tool_source.py`.
- Real prompt asset tests exercise `ScenePrepare` against migrated manifests.

## Docs — PASS

- `dayu/config/README.md`: rewritten for new four-file schema, overlay rules, prompts
  directory structure; old config references removed.
- `dayu/README.md`: runtime assembly components listed.
- `tests/README.md`: runtime/contracts import boundary and scene asset migration coverage
  documented.
- Root `README.md`: config references updated.
- `dayu/contracts/__init__.py`: docstring updated for new source ref types.
- `dayu/runtime/__init__.py`: docstring updated for new components.

## Residual Risks

1. Real Service assembly/wire-up, model allow-list enforcement, temperature profile
   mapping to runner options, and old runtime budget mapping are deferred to subsequent
   Service/execution profile owner phases.
2. `ToolBundleSourceRef` dedicated behavioral tests and runtime README hardening deferred
   to test/docs hardening owner.
3. Audit/Tool Trace/Outbox digest and source ref consumers deferred to Phase 13.
4. Scene asset drift guard (manifest ↔ fragment consistency) not implemented; current
   tests only validate at migration snapshot time.
5. `SERVICE_COMPOSITION` enum member has no consumer in this PR; awaiting Service
   assembly paths.
