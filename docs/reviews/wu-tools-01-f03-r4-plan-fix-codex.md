# WU-TOOLS-01-F03-R4 Plan Fix — AgentCodex

## Scope

- Work unit: `WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup`
- Gate: fix after plan review
- Fixed target: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`
- Review inputs:
  - `docs/reviews/wu-tools-01-f03-r4-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f03-r4-plan-review-ds.md`
  - `docs/host/issues-implementation-control.md` 中本 WU 的 Controller plan-review judgment
- This fix only updated plan artifacts. It did not implement production code, modify tests, modify controller state, commit, push, open PR, or enter re-review.

## Accepted Findings Fix Status

| Finding | Status | Fix summary |
|---|---|---|
| MiMo F01 | 已修复 | Plan now requires wait adapter construction to consume the same effective provider config tuple as discovery. Raw packaged `"workspace/"` must not reach `_fins_wait_adapter_registry_from_provider_configs(...)`. |
| MiMo F02 / DS F6 | 已修复 | Plan now fixes relative Fins `workspace_root` semantics: Service request/runtime `workspace_root=/path/to/project` plus packaged `"workspace/"` resolves to `/path/to/project/workspace`, with explicit tests. |
| MiMo F03 / DS F5 | 已修复 | Plan now records manifest evidence and makes default scene exposure a current-WU implementation item. Current default scenes are treated as non-upload scenes and must stop selecting upload via broad `"fins"` tag matching. |
| DS F1 | 已修复 | Doc provider decision is single-path: packaged `doc-tools.enabled=false`, and enabled Doc provider with missing or empty `allowed_paths` must fail fast with a Doc-specific error. |
| DS F2 | 已修复 | Plan merged provider-level `allow_empty` config removal, `ToolsDiscoveryProviderSpec.allow_empty` removal, and `host_assembly.py` mapping removal into one independently verifiable Slice 1. |
| DS F3 | 已修复 | Plan now records direct Web provider evidence: `dayu.tools.web:discover_tools` reaches `dayu/tools/web/provider.py`, which validates exact `search_web` / `fetch_web_page` definitions and has no normal empty-output path. |
| DS F4 | 已修复 | Plan now records direct Fins download / preprocess provider evidence: each provider returns exactly one awaiting tool definition under valid effective absolute `workspace_root`. |

## Plan Sections Changed

- `First-principles Judgment And Direct Code Evidence`: added wait adapter raw/effective config path, Doc provider empty-output path, Web provider direct evidence, download/preprocess direct evidence, and default scene manifest exposure evidence.
- `Affected Files / Modules`: added `dayu/config/prompts/manifests/*.json` as affected implementation input.
- `Contract / Schema / State-machine / Public-interface Changes`: clarified that scene `tool_selection.allow_empty` remains unchanged while default scene selection inputs may change.
- `Exact Implementation Decisions`: fixed workspace resolution semantics, required wait adapter effective configs, removed Doc provider fork, added Web/download/preprocess evidence decisions, and made scene upload exposure a current-WU implementation decision.
- `Implementation Slices`: consolidated generic `allow_empty` cleanup into Slice 1; moved Service workspace/wait adapter logic to Slice 2; added scene manifest handling to upload Slice 4; added Doc fail-fast to Slice 5.
- `Tests / Validation Commands And Expected Assertions`: added scene prepare validation, wait adapter effective-config assertion, Web/download/preprocess non-empty assertions, Doc fail-fast assertion, and upload non-exposure assertion.
- `Risks / Open Questions / Residual Risks`: replaced old open risks with resolved plan-review risks and retained only classified residual risks.

## Direct Code Evidence Summary

- `dayu/service/host_assembly.py`: `_effective_tool_provider_config(...)` currently only injects runtime workspace root when config `workspace_root` is `None`; `_fins_wait_adapter_registry_from_provider_configs(...)` separately reads provider config and requires absolute `workspace_root`. This supports the required effective-config wait adapter fix.
- `dayu/tools/web/__init__.py` and `dayu/tools/web/provider.py`: packaged `dayu.tools.web:discover_tools` resolves to the provider module. `discover_tools(...)` builds definitions and `_validate_web_definitions(...)` requires exactly `("search_web", "fetch_web_page")`.
- `dayu/fins/tools/download_provider.py`: under valid absolute `workspace_root`, `discover_tools(...)` returns `(build_fins_download_tool(...),)`.
- `dayu/fins/tools/preprocess_provider.py`: under valid absolute `workspace_root`, `discover_tools(...)` returns `(build_fins_preprocess_tool(...),)`.
- `dayu/tools/doc_provider.py`: current enabled + empty `allowed_paths` path returns empty definitions, so the plan now requires Doc-specific fail-fast.
- `dayu/config/prompts/manifests/*.json` and `dayu/runtime/scene_prepare.py`: current default manifests do not use `mode="all"`, but many select `"fins"` by tag; `ScenePrepare` unions explicit names and tag matches and has no exclusion field. Since `start_fins_upload` has tags `("fins", "fins-upload")`, default scenes would select upload unless manifest selection changes.

## Validation

- Text self-check: searched the plan for stale open-ended language including `implementation owner`, `Product owner`, `Preferred`, `unless implementation`, `or revise`, `must verify`, `should confirm`, and obsolete slice labels. Only slice headings and valid cross-references remain.
- Git status checked: existing workspace still shows unrelated controller/review/plan artifact state; this fix only wrote the allowed plan artifact and this allowed fix artifact.
- Pytest/pyright were not run because this gate intentionally changed only documentation artifacts and no production/test code.

## Residual Risks / Uncovered Items

- No accepted plan-review finding remains unresolved in the plan artifact.
- Implementation still must validate that scene manifest changes preserve intended read/download/preprocess/web tool availability while excluding `start_fins_upload`.
- Upload local file read authorization remains deferred to future Host / policy work, as required by the confirmed non-goals.
- Existing unrelated git status entries were not modified or resolved by this gate.
