# Phase 12 Aggregate Deep Review

- **Reviewer**: AgentMiMo
- **Date**: 2026-05-21
- **Branch**: `docs/phase12-design-discussion`
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/implementation-control.md`
- **Plan source**: `docs/host/phase12-runtime-assembly-plan.md`

## Verdict: PASS

Phase 12 runtime assembly implementation satisfies all design boundaries and constraints. Three runtime components (`ToolsDiscovery`, `ConfigLoader`, `ScenePrepare`) are correctly placed in `dayu.runtime`, fully layer-neutral, well-separated in responsibility, and backed by comprehensive tests. No Host public interface was modified. Ready to proceed to draft PR gate.

---

## Validation Runs (on branch)

| Check | Result |
|-------|--------|
| `pytest tests/runtime -q` | 174 passed |
| `pytest tests/contracts tests/engine/test_config_models.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 69 passed |
| `pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host tests/engine/test_config_models.py` | 0 errors, 0 warnings |
| `git diff --check` | clean |
| `git status --short` | clean |

## Primary Questions Answered

### Q1: Does the implementation satisfy design.md Phase 12 boundaries without modifying Host public interface?

**YES.** Phase 12 delivered three independent runtime assembly components (`ToolsDiscovery`, `ConfigLoader`, `ScenePrepare`) in `dayu.runtime`. No changes were made to `open_host` options, `SubmitFollowupRequest` fields, Host state machine, or Engine execution path. The only commit touching `dayu/host/` (`1aae08d`) relocated `ToolBundleSourceKind`/`ToolBundleSourceRef` definitions from local code to `dayu.contracts` imports while preserving the re-export surface -- a pure internal refactor.

### Q2: Does dayu.runtime remain layer-neutral and free of Host/Engine/Service/UI/Fins/business tool imports?

**YES.** AST-based import boundary scan (`tests/runtime/test_import_boundary.py`) covers all 9 runtime source files. Every file imports only from: Python stdlib, `dayu.contracts`, `dayu.runtime` intra-package, and third-party `filelock` (confined to `filelock.py`). Zero violations.

### Q3: Are ToolsDiscovery, ScenePrepare, and ConfigLoader responsibilities separated correctly?

**YES.** The three modules share zero imports between them. Each has a distinct contract:
- `ToolsDiscovery`: resolves provider callables, aggregates `ToolBundle`, computes content digests, validates reserved tool names.
- `ConfigLoader`: loads 4 typed config schema files, applies workspace overlay (whole-record replacement, single-inheritance extends), produces frozen typed config views.
- `ScenePrepare`: parses scene manifests with single-inheritance extends, renders prompt fragments with `{{slot_name}}` substitution, outputs `PreparedSceneInputs` with full source refs and digest.

All runtime values are injected via request objects; no module reaches into Host/Service/Engine context.

### Q4: Are config/prompt assets and README docs consistent with current code?

**MOSTLY YES.** Prompt asset migration is complete: `dayu/config/prompts/` contains 4 base fragments, 14 scene manifests, and 14 scene `.md` files. Legacy `llm_models.json` and `run.json` are fully removed from disk. `dayu/README.md` and `dayu/config/README.md` are current.

**One gap**: `dayu/runtime/README.md` does not exist. The CLAUDE.md trigger rule for `tests/` changes did not mandate a runtime README because `dayu/runtime/` is not in the trigger list. This is an oversight -- the runtime package now has 3 substantial Phase 12 components that warrant a dedicated development README per the CLAUDE.md README convention.

### Q5: Are tests and pyright coverage sufficient?

**YES.** 243 tests pass across runtime, contracts, host, and engine scopes. Pyright reports zero errors. Test coverage includes:
- Positive-path and error-path for all three components
- Digest stability and sensitivity assertions
- AST-based import boundary enforcement across 7 test locations
- Export whitelist guards for contracts and host packages
- Weak typing guard scans

---

## Findings

### HIGH

None.

### MEDIUM

| # | Finding | File | Line |
|---|---------|------|------|
| M1 | `dayu/runtime/README.md` missing. Three Phase 12 components (`config_loader`, `scene_prepare`, `tools_discovery`) lack a dedicated development README. Per CLAUDE.md README convention, each substantial package should have a README documenting interfaces, architecture, boundaries, and extension points. | `dayu/runtime/` | -- |

### LOW

| # | Finding | File | Line |
|---|---------|------|------|
| L1 | `ToolBundleSourceRef` dataclass lacks dedicated behavioral tests (e.g., `source_id` emptiness rejection, optional blank-string rejection). The export whitelist is guarded, but the validation logic in `__post_init__` has no unit test under `tests/contracts/`. | `dayu/contracts/tool_source.py` | -- |
| L2 | `test_scene_assets_migration.py` depends on real repo manifest files (`dayu/config/prompts/manifests/*.json`). If scene manifests change without corresponding test updates, this test becomes fragile. | `tests/runtime/test_scene_assets_migration.py` | -- |

### INFORMATIONAL

| # | Finding | File | Line |
|---|---------|------|------|
| I1 | `_LEGACY_CONFIG_FILES` in `config_loader.py` (line 24-26) is a tombstone frozenset used only by `legacy_config_file_names()` for diagnostics. Benign, but could be removed once migration confidence is high. | `dayu/runtime/config_loader.py` | 24-26 |
| I2 | Docstring comment in `dayu/engine/contracts/runner_spec.py:32` references "OLD `llm_models.json`" for historical context. Minor staleness in a docstring, not a code issue. | `dayu/engine/contracts/runner_spec.py` | 32 |

---

## Residual Risks

1. **Runtime README gap**: The missing `dayu/runtime/README.md` means new contributors to the runtime package lack a local development guide. This should be addressed before or immediately after merging Phase 12.

2. **Scene asset fragility**: The real-manifest-dependent migration test could break silently if someone adds/removes scene manifests. Consider adding a manifest enumeration assertion to catch drift.

3. **No Phase 13 hooks yet**: Phase 12 deliberately excludes Audit/Tool Trace/Outbox projections (Phase 13). The digest and source ref infrastructure is in place, but the projection consumers are not. This is by design, not a gap.

---

## Scope Confirmation

- Phase 12 slices 1-6: all accepted and verified.
- Aggregate fix (contracts export whitelist for `ToolBundleSourceKind`/`ToolBundleSourceRef`): in place and guarded.
- No out-of-scope changes detected in Host, Engine, Service, UI, or Fins layers.
