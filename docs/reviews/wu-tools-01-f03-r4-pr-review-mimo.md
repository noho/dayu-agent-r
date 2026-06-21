# PR Review: WU-TOOLS-01-F03-R4

## Scope

- Mode: PR Review
- PR: #160 — `WU-TOOLS-01-F03-R4: clean up Tools Discovery spec semantics`
- URL: https://github.com/noho/dayu-agent-r/pull/160
- Author: noho
- Base: `main`
- Head: `phase/wu-tools-01-f03-r4`
- Draft: true
- Verdict: **pass**

## PR Metadata Reviewed and Commands Run

```
gh pr view 160 --json title,url,author,headRefName,baseRefName,state,isDraft,body
gh pr diff 160
gh pr checks 160 → no checks available
git log --oneline -10
git rev-parse HEAD → de02e701
```

- PR title accurately describes the change: removing `allow_empty`, `include_read_tools`, `allowed_upload_roots`, and migrating limits.
- PR body includes `Closes #133` and lists four deferred residual risks with explicit owners.
- Local HEAD `de02e701` is the most recent commit on the branch, matching the gateflow commit sequence from `fe212365` through `3463ae9d` plus the two draft PR commits `5f396408` and `de02e701`.
- Remote `origin/phase/wu-tools-01-f03-r4` fetch failed (remote branch not found locally under that name), but the PR head branch name matches and the local branch has the expected gateflow commit chain.

## Validation Run During Review

| Command | Result |
|---|---|
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q` | 60 passed |
| `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 58 passed, 3 warnings |
| `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q` | 70 passed, 3 warnings |
| `pytest tests/runtime tests/service tests/fins tests/tools -q --ignore=tests/tools/web/test_smoke_web_ci.py` | 866 passed, 1 skipped, 3 warnings |
| `pyright dayu tests utils` | 0 errors, 0 warnings, 0 informations |
| `rg -n "include_read_tools" dayu tests utils --type py` | no hits |
| `rg -n "allowed_upload_roots" dayu tests utils --type py` | only negative assertion in `tests/runtime/test_config_loader.py:413` |
| `rg -n "allow_empty" dayu/config/tool_discovery.json` | no hits |
| `rg -n '"fins"' dayu/config/prompts/manifests/` | no hits |
| `rg -n '"ingestion"' dayu/config/prompts/manifests/` | no hits |
| `rg -n "start_fins_upload" dayu/config/prompts/manifests/` | no hits |

All validation results match PR body claims exactly.

## Issue-133 Completeness Judgment

Issue #133 requests six items. Each is verified against PR diff:

1. **Remove `allow_empty`** — ✅ Complete. Removed from `tool_discovery.json`, `ToolDiscoveryProviderConfig`, `ToolsDiscoveryProviderSpec`, `host_assembly.py` mapping, and all tests. ToolsDiscovery now always rejects empty provider output.

2. **Remove `include_read_tools`** — ✅ Complete. Removed from `tool_discovery.json` and `dayu/fins/tools/provider.py`. `_parse_bool_default()` helper deleted. Read provider enabled = always returns nine tools.

3. **`workspace_root` changed to `"workspace/"`** — ✅ Complete. All four Fins providers in `tool_discovery.json` now have `workspace_root: "workspace/"`. Service `host_assembly.py` added `_effective_fins_workspace_root_config_value()` that resolves relative paths against runtime `workspace_root`. Tests assert `/path/to/project` + `"workspace/"` → `/path/to/project/workspace`.

4. **`financial-read-tools` migrated OLD limits** — ✅ Complete. `tool_discovery.json` now carries all 10 explicit limits. Tests assert packaged values propagate to `ToolDefinition` truncate specs.

5. **`financial-upload-tools` removed `allowed_upload_roots`** — ✅ Complete. Removed from `tool_discovery.json`, `upload_provider.py`, and `upload_tools.py`. Upload callable no longer stores or checks allowlist. Local file validation reduced to existence + regular file + non-empty. LLM-facing schema updated.

6. **`doc-tools` migrated OLD limits** — ✅ Complete. `tool_discovery.json` now carries 5 explicit Doc limits. `doc-tools.enabled` set to `false`. Enabled Doc provider with empty `allowed_paths` now raises `ValueError` instead of returning empty definitions.

All six items are implemented, tested, and documented. No item is deferred or partial.

## PR Body Accuracy Judgment

PR body "Summary" section describes six concrete changes. All six are directly evidenced in the diff:

- The `allow_empty` removal is complete across config, runtime, service, and all providers.
- The `include_read_tools` removal is complete in Fins read provider.
- The `workspace_root` default change with Service effective resolution is implemented.
- The limits migration is implemented with explicit packaged values.
- The `allowed_upload_roots` removal is complete in upload provider and callable.
- The scene manifest changes prevent upload exposure via broad `"fins"` tag.

PR body "Validation" section lists 8 test commands. All pass as verified during this review.

PR body does not claim any future work as completed. All four residual risks are explicitly listed as deferred with owners.

## Residual Risks / Owners Judgment

PR body lists four residual risks:

| ID | Classification | Owner |
|---|---|---|
| `WU-TOOLS-01-F03-R4-POLICY-R1` | `deferred-with-owner` | Future Host / policy design |
| `WU-TOOLS-01-F03-R4-PATH-R1` | `deferred-with-owner` | Future provider path-boundary hardening |
| `WU-TOOLS-01-F03-R4-SCENE-R1` | `deferred-with-owner` | Future scene manifest maintenance |
| `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1` | `deferred-with-owner` | Web smoke / CI owner |

All four residual risks are:
- Consistent with the control doc `docs/host/issues-implementation-control.md` Residual Risk table.
- Properly classified as `deferred-with-owner`, not `open`.
- None block this PR: POLICY-R1 is an explicit non-goal; PATH-R1 preserves current `Path.resolve()` semantics; SCENE-R1 is covered by current manifest tests; WEB-SMOKE-R1 is a pre-existing stdout-vs-logging capture mismatch not introduced by this WU.

No residual risk is missing from either PR body or control doc.

## PR Diff Scope Judgment

Changed files in PR diff (59 files total):

- **Production/config (10 files)**: `tool_discovery.json`, `config_loader.py`, `tools_discovery.py`, `host_assembly.py`, `provider.py`, `upload_provider.py`, `upload_tools.py`, `doc_provider.py`, 10 scene manifests, `utils/diagnose_web_access.py`
- **Design/README (4 files)**: `docs/host/design.md`, `dayu/config/README.md`, `dayu/fins/README.md`, `tests/README.md`
- **Tests (14 files)**: config loader, tools discovery, host assembly, scene prepare, scene assets migration, Fins storage provider, Fins ingestion tools, doc tools provider, combined tools acceptance, web tools provider, entrypoint runtime, smoke assembly, conversation memory scenarios assembly
- **Review/plan artifacts (27 files)**: all in `docs/reviews/` and `docs/host/host-issues/`
- **Control doc (1 file)**: `docs/host/issues-implementation-control.md`

No non-WU changes detected. The `utils/diagnose_web_access.py` change is a signature fallout from `ToolsDiscoveryProviderSpec.allow_empty` removal (confirmed in Slice 1 review as acceptable). The `tests/tools/web/test_web_tools_provider.py` change is test fixture cleanup consistent with the WU scope.

All changes are within the accepted plan's allowed files.

## Blocking Issues

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk / Uncovered Areas

- **Web smoke residual**: `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases` continues to fail with stdout-vs-logging capture mismatch. Classification `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1` is acceptable: this is a pre-existing issue not introduced by this WU, and the PR correctly defers it to the web smoke owner.
- **Remote branch verification**: `origin/phase/wu-tools-01-f03-r4` fetch failed (remote ref not available locally). Local branch gateflow commit chain is consistent with PR metadata; no evidence of divergence.

## Completion Status

- PR body accuracy: ✅ verified
- Issue-133 six items: ✅ all complete
- Residual risks / owners: ✅ complete and non-blocking
- PR diff scope: ✅ no non-WU changes
- Test validation: ✅ all pass as claimed
- Pyright: ✅ 0 errors
- Stale field grep: ✅ clean
- Blocking findings: 0
- Verdict: **pass**
