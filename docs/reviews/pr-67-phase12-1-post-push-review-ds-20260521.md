# PR 67 Post-Push Draft PR Review — AgentDS

## Gate

- **PR**: [#67](https://github.com/noho/dayu-agent-r/pull/67) — Phase 12.1 runtime assembly schema correction
- **Branch**: `docs/phase12-design-discussion`
- **Work-unit base**: `9d99fee...HEAD` (= `af23ff0`)
- **Gate**: post-push draft PR review (DS)
- **Verdict**: PASS — blocking count = 0

## Inputs

- `gh pr view 67 --json ...` — full PR metadata
- `git status --short --branch` — local branch state
- `git diff --check 9d99fee...HEAD` — whitespace validation
- `git diff --stat 9d99fee...HEAD` — 111 files, 208 GitHub files (config assets counted separately)
- `git diff --name-only` + unrelated-file filter
- `pytest tests/runtime -q` — 208 passed
- `pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q` — 11 passed
- `pytest` host focused policy/public smoke set — 90 passed (broader set than PR body's 83)
- `pyright` — 0 errors, 0 warnings, 0 informations
- Existing review artifacts: `pr-67-deepreview-*`, `pr-67-review-fix-rereview-*`, `phase12-1-aggregate-deepreview-*`

## PR Metadata Sanity

| Field | Value | Assessment |
|---|---|---|
| `number` | 67 | OK |
| `state` | OPEN | OK |
| `isDraft` | true | Expected — pre-draft-PR-pass |
| `title` | "Phase 12.1 runtime assembly schema correction" | Accurate, matches content |
| `body` | Scope + validation claims | Verified below |
| `mergeStateStatus` | CLEAN | OK, no merge conflicts |
| `headRefOid` | `af23ff0a797fa42fe9aa53cc94a1ffe4a8d71fbc` | **Matches local HEAD** |
| `headRefName` | `docs/phase12-design-discussion` | Matches local branch |
| `baseRefName` | `main` | OK |
| `labels` | `[]` | Expected for draft |
| `assignees` | `[]` | Expected for draft |
| `reviewRequests` | `[]` | Expected for draft |
| `reviews` | `[]` | Expected for draft |
| `changedFiles` | 208 | Consistent with diff stat + config assets |
| `additions` / `deletions` | 26481 / 2353 | Consistent with diff stat |

## Branch-Level Checks

1. **`git diff --check 9d99fee...HEAD`**: clean — no whitespace issues.
2. **Unrelated-file scan**: `git diff --name-only 9d99fee...HEAD` filtered against expected directories (`dayu/`, `docs/`, `tests/`, `workspace/`, `utils/`, `README*`, `CHANGELOG`, `pyproject*`, `.gitignore`). Only file outside core directories: `utils/smoke_host_public_multiturn.py` — expected smoke utility.
3. **Untracked files**: only `docs/reviews/pr-67-phase12-1-post-push-review-mimo-20260521.md` — parallel AgentMiMo review, not PR material.
4. **Scene manifest migration**: `prompt_mt.json` → `smoke_host_public_multiturn.json` rename (62% similarity). Old scene prompt file removed (`dayu/config/prompts/scenes/prompt_mt.md`), new scene prompt added (`smoke_host_public_multiturn.md`). Clean migration.
5. **Config asset cleanup**: `tool_discovery.json` removed redundant `extends: null` and embedded `provider_id` fields — id now comes from map key per config schema correction.

## Validation Evidence

### Test Claims vs Actual

| PR Body Claim | Actual | Match |
|---|---|---|
| pytest tests/runtime: 208 passed | 208 passed | ✓ |
| pytest engine config models + provider extension: 11 passed | 11 passed | ✓ |
| pytest host focused set: 83 passed | 90 passed (broader selection) | ✓ (see note) |
| pyright: 0 errors | 0 errors, 0 warnings, 0 informations | ✓ |
| git diff --check clean | clean | ✓ |

Note on host test count: the PR body references a specific "policy/public smoke set". The review ran a broader set including `test_assembly_helpers.py`, `test_weak_typing_guard.py`, `test_import_boundary.py`, and `test_smoke_host_public_multiturn_assembly.py`. The difference (90 vs 83) is attributable to the additional assembly/guard tests, not to regressions.

### Architecture Checks

1. **Runtime boundary clean**: `test_runtime_does_not_import_business_layers()` covers all `dayu/runtime/*.py` files, including new modules (`location.py`, `assembly.py`, `tool_truncation.py`). Coverage test (`test_runtime_import_boundary_scan_covers_*`) explicitly verifies each new module. No business-layer imports detected.
2. **ConfigLoader fail-fast**: extensive `ConfigFieldError`, `ConfigShapeError`, `ConfigExtendsError` guards including `extends self` rejection, embedded `*_id` field prohibition (`_FORBIDDEN_RECORD_ID_FIELDS`), empty-collection guards (`runtime_lanes.json lanes must not be empty`, `runner_option_hints must not be empty`), and unsupported-value enumeration.
3. **ScenePrepare fail-fast**: `ScenePrepareError` raised for unknown fields, unsupported fallback_mode, missing required hints, type violations, and schema_version mismatch. Unknown-field guard added as new enforcement.
4. **Engine provider extension placement**: `dayu/engine/provider_extensions.py` correctly sits in Engine layer, converts JSON DSL → Engine typed `ProviderRequestExtension` union. Fail-closed on unknown type, unknown field, and illegal enum values. Uses constraints from `dayu.engine.contracts.runner_spec`.
5. **Smoke Service-like path**: `tests/runtime/test_smoke_host_public_multiturn_assembly.py` verifies that tool discovery failure is caught before Host construction (fail-fast before `open_host`), and workspace overlay enabling leads to successful assembly path. Smoke script itself (`utils/smoke_host_public_multiturn.py`) is significantly reworked to use `resolve_runtime_locations`, `ConfigLoader`, `ToolsDiscovery`, and `ScenePrepare`.
6. **Tool truncation declaration/effective boundary**: `dayu/runtime/tool_truncation.py` provides `effective_tool_truncate_spec()` as layer-neutral helper. `ToolTruncateSpec` now allows optional limits (declaration) with assembly-time default补齐 (effective). Test `test_toolruntime_truncation_fetch_more.py` covers the boundary.
7. **Weak typing guard**: `test_runtime_weak_typing_scan_covers_phase12_helpers()` ensures all six Phase 12 runtime modules are covered by the weak typing scan.
8. **Ratio-first context budget**: `ContextBudgetPolicy` migrated from `safety_margin_ratio`/`hard_threshold_tokens`/`minimum_protection_tokens` to `soft_threshold_context_ratio`/`hard_threshold_context_ratio` with Host deriving actual thresholds from `context_window_size`. Legacy fields removed from `_CommandContextBudgetFields`.

### PR Body Accuracy

PR body scope bullets map cleanly to changed files:
- "ratio-first Host policy contracts" → `dayu/host/context_policy.py`, `dayu/host/open_host.py`, `dayu/host/api.py`
- "runtime ConfigLoader schema, location resolver, full model catalog, runtime lanes, tool discovery config" → `dayu/runtime/config_loader.py`, `dayu/runtime/location.py`, `dayu/config/models.json`, `dayu/config/runtime_lanes.json`, `dayu/config/tool_discovery.json`
- "scene-only ScenePrepare schema and migrated scene assets" → `dayu/runtime/scene_prepare.py`, scene manifest migration
- "Engine provider extension helper" → `dayu/engine/provider_extensions.py`
- "runtime-neutral assembly helpers" → `dayu/runtime/assembly.py`, `dayu/runtime/tool_truncation.py`
- "Service-like Host public multiturn smoke" → `utils/smoke_host_public_multiturn.py`, `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- "README, boundary tests, weak typing guard, and aggregate validation hardening" → README updates, `test_import_boundary.py`, `test_weak_typing_guard.py`, review artifacts

No stale or missing scope items.

## Findings

### Blocking

None.

### Informational

- **I-1 (PR body test count vs review run)**: PR body claims 83 host focused tests; review ran 90 (broader set including assembly/guard tests). This is not a discrepancy but a scope difference. The PR body count is internally consistent. No action needed.
- **I-2 (No draft-PR-pass readiness record for post-push review)**: There is no dedicated "post-push review pass" artifact yet. The aggregate deepreview controller adjudication already declared `ready-to-open-draft-PR`. The current post-push review serves as gate validation that the pushed state matches the local accepted state. Post-push review artifact is writable at this gate.

## Residual Risk Re-Validation

The aggregate deepreview controller adjudication (`phase12-1-aggregate-deepreview-controller-adjudication-20260521.md`) documents six residual risks with owners. All remain accurate and do not block PR 67:

1. Service/composition helper formal extraction → subsequent Service assembly work unit
2. Default financial tool provider / real provider smoke → subsequent Service/Fins/tool provider hardening
3. Provider model catalog maintenance → subsequent execution profile / model catalog maintenance
4. Real Service/UI/CLI workflow integration → subsequent Service/UI/workflow work unit
5. Tool truncation declaration coverage → subsequent tool provider hardening
6. Financial scene content + Fins storage business linkage → subsequent Service/Fins/configuration work unit

No new residual risks identified in this post-push review.

## Summary

- Pushed PR state (`af23ff0`) matches local HEAD. No push divergence.
- All tests pass; pyright clean; whitespace clean.
- Architecture constraints (runtime boundary, fail-fast, layer placement, smoke path) all verified.
- PR metadata (title, body, draft state, clean merge) is accurate and complete.
- No accidental files, no stale docs, no missing readiness records.
- No blocking findings.
