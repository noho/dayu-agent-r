# WU-TOOLS-01-F03-R4 Plan Re-Review — AgentDS

## Re-Review Metadata

- **Reviewed target**: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`
- **Work unit**: WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup
- **Review agent**: AgentDS
- **Timestamp**: 20260621-073335
- **Prior review artifact**: `docs/reviews/wu-tools-01-f03-r4-plan-review-ds.md`
- **Plan-fix artifact**: `docs/reviews/wu-tools-01-f03-r4-plan-fix-codex.md`
- **Control truth consulted**: `docs/host/issues-implementation-control.md` (WU-TOOLS-01-F03-R4 controller plan-review judgment and plan-fix summary, lines 236-317)

## Re-Review Scope

This is a **re-review only**. Per user instruction: verify accepted findings are fixed, judge whether the fixed plan is code-generation-ready, do not expand scope. Only report new blocking findings if they arise directly from plan-fix changes or would prevent implementation.

## Accepted Findings Verification

Seven findings were accepted by controller judgment (control doc lines 253-259). Each is verified against the plan-fix artifact claims and the updated plan text.

### Finding 1: MiMo F01 — wait adapter effective config

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Plan now requires wait adapter construction to consume the same effective provider config tuple as discovery. Raw packaged `"workspace/"` must not reach `_fins_wait_adapter_registry_from_provider_configs(...)`.
- **Plan evidence**:
  - Decision 7 (line 160): `"discover_service_tools(...)` and Host tooling wait adapter assembly must consume the same effective provider config tuple. Assemble effective configs once in `assemble_effective_tool_provider_configs(...)`, pass that tuple through `ServiceDiscoveredTools.effective_provider_configs`, and use it when building `HostToolingOptions`. `_fins_wait_adapter_registry_from_provider_configs(...)` must receive configs after `_effective_tool_provider_config(...)` has resolved relative Fins workspace roots to absolute paths; it must not read raw packaged `"workspace/"`."
  - Slice 2 (line 260): `"Route wait adapter construction through the same effective provider config tuple used for discovery."`
  - Slice 2 tests (line 281): `"Include an assertion that wait adapter registry construction uses the same effective absolute workspace root and no longer sees raw relative `"workspace/"`."`
- **Status**: **已修复** — The plan now explicitly requires the wait adapter path to consume effective provider configs after workspace resolution, not raw packaged config. This is testable and unambiguous.

### Finding 2: MiMo F02 / DS F6 — workspace/ resolution base

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Plan now fixes relative Fins `workspace_root` semantics: Service request/runtime `workspace_root=/path/to/project` plus packaged `"workspace/"` resolves to `/path/to/project/workspace`.
- **Plan evidence**:
  - Decision 5 (lines 52-56): `"if relative, resolve against Service request/runtime workspace_root with the same containment semantics as _resolve_project_path(...). The packaged "workspace/" value means: when Service receives workspace_root=/path/to/project, the effective Fins workspace_root is /path/to/project/workspace."`
  - Slice 2 (line 270): `"Packaged "workspace/" always resolves relative to Service request/runtime workspace_root; for workspace_root=/path/to/project, effective Fins workspace_root must be /path/to/project/workspace."`
  - Slice 2 tests (line 280): `"Include an assertion that packaged relative "workspace/" resolves to /path/to/project/workspace when Service request/runtime workspace_root is /path/to/project, and raw config is not mutated."`
- **Status**: **已修复** — The resolution base is explicit and testable. No longer left for implementation agent to guess.

### Finding 3: MiMo F03 / DS F5 — default scene upload exposure verification

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Plan now records manifest evidence and makes default scene exposure a current-WU implementation item. Current default scenes are treated as non-upload scenes and must stop selecting upload via broad `"fins"` tag matching.
- **Plan evidence**:
  - Code evidence (lines 70-71): `"dayu/config/prompts/manifests/*.json` currently has no `mode="all"`; but multiple default scenes use `tool_tags_any` matching `"fins"`. `ScenePrepare` unions explicit names and tag matches and has no exclusion field. `start_fins_upload` has tags `("fins", "fins-upload")`, therefore upload default registration would be selected by broad `"fins"` tag."
  - Decision 13 (lines 175-176): `"Update default scene manifest selection inputs so they no longer select upload via broad "fins" tag matching. Use explicit tool_names for list_documents, get_document_sections, read_section, search_document, list_tables, get_table, get_page_content, get_financial_statement, query_xbrl_facts, start_fins_download and start_fins_preprocess; keep existing "web" tag selection where applicable; do not change scene tool_selection.allow_empty semantics."`
  - Slice 4 (lines 343-345): Scene manifest changes as part of upload slice.
  - Slice 4 tests (lines 358, 378-379): Explicit manifest assertions.
- **Status**: **已修复** — The problem is now an in-WU implementation item with specific allowed files, exact tool name list, and test assertions.

### Finding 4: DS F1 — Doc provider single path

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Doc provider decision is single-path: packaged `doc-tools.enabled=false`, and enabled Doc provider with missing or empty `allowed_paths` must fail fast with a Doc-specific error.
- **Plan evidence**:
  - Decision 10 (lines 170-172): `"The single accepted path is: packaged doc-tools.enabled=false by default; if a workspace overlay enables doc-tools with missing or empty allowed_paths, dayu.tools.doc_provider.discover_tools(...) must fail fast with a business-specific error such as doc provider config.allowed_paths must contain at least one path when doc-tools is enabled; do not let implementation choose between enabled=false and provider fail-fast; both are required."`
  - Slice 5 (line 399): `"replace the enabled + empty allowed_paths empty-output branch with ValueError carrying a Doc-specific message. This is required even though packaged doc-tools.enabled=false, so workspace overlays that enable doc tools without paths fail at the business boundary."`
  - Slice 5 tests (line 402): Doc-specific error assertion.
- **Status**: **已修复** — No fork remains. The plan is single-path and implementation agent has no design decision to make.

### Finding 5: DS F2 — allow_empty delete slice atomicity

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Plan merged provider-level `allow_empty` config removal, `ToolsDiscoveryProviderSpec.allow_empty` removal, and `host_assembly.py` mapping removal into one independently verifiable Slice 1.
- **Plan evidence**:
  - Slice 1 (lines 180-240): All three removal locations in one slice with explicit allowed files including `host_assembly.py`.
  - Slice 1 invariant (line 219): `"The codebase must remain importable and Service tool discovery callable after this slice; there must be no intermediate state where ToolsDiscoveryProviderSpec no longer accepts allow_empty but host_assembly.py still passes it."`
  - Slice 1 completion signal (line 239): `"no production or test code references ToolDiscoveryProviderConfig.allow_empty or ToolsDiscoveryProviderSpec.allow_empty."`
- **Status**: **已修复** — All three deletion sites are in one slice with an explicit invariant preventing intermediate broken state. The allowed files list includes `host_assembly.py`.

### Finding 6: DS F3 — Web provider non-empty evidence

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Plan now records direct Web provider evidence: `dayu.tools.web:discover_tools` reaches `dayu/tools/web/provider.py`, which validates exact `search_web` / `fetch_web_page` definitions and has no normal empty-output path.
- **Plan evidence**:
  - Code evidence (lines 68-69): `"Web provider entry is packaged import path dayu.tools.web:discover_tools, forwarded by dayu/tools/web/__init__.py to dayu/tools/web/provider.py. discover_tools(...) always calls build_web_tool_definitions(...), subsequently _validate_web_definitions(...) requires tool names exactly ("search_web", "fetch_web_page"), no normal empty definitions path."`
  - Decision 11 (line 173): `"For web-tools, keep enabled default. Direct code evidence from dayu/tools/web/provider.py shows the provider validates that definitions are exactly ("search_web", "fetch_web_page"); there is no normal empty-output path."`
- **Status**: **已修复** — The empty-output assumption is no longer an assumption; it is backed by direct code evidence with concrete module paths and function names.

### Finding 7: DS F4 — download/preprocess non-empty evidence

- **Controller judgment**: `accepted`
- **Plan-fix claim**: Plan now records direct Fins download / preprocess provider evidence: each provider returns exactly one awaiting tool definition under valid effective absolute `workspace_root`.
- **Plan evidence**:
  - Code evidence (lines 69-70): `"dayu/fins/tools/download_provider.py under valid absolute workspace_root always returns (build_fins_download_tool(...),); dayu/fins/tools/preprocess_provider.py under valid absolute workspace_root always returns (build_fins_preprocess_tool(...),), both have no empty definitions branch."`
  - Decision 12 (line 174): `"For financial-download-tools and financial-preprocess-tools, keep enabled defaults. Direct code evidence shows each provider parses effective absolute workspace_root and returns exactly one awaiting tool definition under valid config."`
- **Status**: **已修复** — Both providers' empty-output behavior is now confirmed by direct code evidence, not left as "likely unchanged but must be checked."

## New Findings

No new blocking findings were identified. The plan-fix changes are semantically coherent and do not introduce fresh contradictions, gaps, or overreaches.

### Observation (non-blocking): ServiceDiscoveredTools.effective_provider_configs field

- **位置**: Decision 7 (line 160), Slice 2 (line 260)
- **问题类型**: 实施细节未完全明确（非阻塞）
- **当前写法**: Plan says `discover_service_tools(...)` stores effective configs in `ServiceDiscoveredTools.effective_provider_configs`, and wait adapter consumes them from there.
- **观察**: Plan does not state whether `ServiceDiscoveredTools` already has this field or needs it added. This is a minor implementation detail the implementation agent can resolve trivially by inspecting `ServiceDiscoveredTools` and adding the field if absent.
- **影响**: 无 — implementation agent 可以在 Slice 2 实施时自然发现并处理。
- **严重程度**: 无 — 不阻塞。

### Observation (non-blocking): scene manifest tool name list

- **位置**: Decision 13 (lines 175-176), Slice 4 (lines 343-345)
- **问题类型**: 实施细节验证
- **当前写法**: Plan lists 11 explicit Fins tool names for scene manifest updates.
- **观察**: The 11 names (9 read tools + `start_fins_download` + `start_fins_preprocess`) should match the actual tool names registered by Fins providers. The implementation agent will verify this naturally when making manifest changes.
- **影响**: 无 — implementation agent 会在操作 manifest 文件时直接看到实际 tool 名称，如不一致会自然发现。
- **严重程度**: 无 — 不阻塞。

## Residual Risks / Uncovered Areas

The following residual risks noted in the plan remain valid and do not block implementation:

| Risk | Severity | Status |
|------|----------|--------|
| Removing `allow_empty` can surface latent empty provider configs in user workspaces | 低 | Intended fail-fast; rollout notes may be needed outside code. Deferred to controller / release owner. |
| Upload tool schema wording must stay LLM-facing and not claim local file reads are globally safe | 低 | Plan addresses this in Decision 8 (line 167) and Slice 4. Implementation agent must follow through. |
| Provider dataclass defaults could drift from packaged defaults | 低 | Plan addresses this with explicit packaged limit assertions. |
| Upload local file read authorization remains unresolved | 中 | Explicitly deferred to future Host / policy design. Plan non-goals are clear. |
| Scene manifest changes must preserve intended read/download/preprocess/web tool availability | 低 | Plan includes explicit manifest assertions in Slice 4. |

## Verdict

**PASS**

All 7 accepted findings are **已修复**. The plan-fix artifact correctly addresses each finding in the updated plan text. The fixed plan is code-generation-ready.

### Finding Status Summary

| # | Finding | Status |
|---|---------|--------|
| 1 | MiMo F01 — wait adapter effective config | 已修复 |
| 2 | MiMo F02 / DS F6 — workspace/ resolution base | 已修复 |
| 3 | MiMo F03 / DS F5 — default scene upload exposure | 已修复 |
| 4 | DS F1 — Doc provider single path | 已修复 |
| 5 | DS F2 — allow_empty delete slice atomicity | 已修复 |
| 6 | DS F3 — Web provider non-empty evidence | 已修复 |
| 7 | DS F4 — download/preprocess non-empty evidence | 已修复 |

### Gate Entry Condition

**可以进入 accepted plan commit gate。** Blocking finding 数量: **0**。

Plan 在以下方面满足 code-generation-ready 要求:
- 每个 slice 有明确的 objective、allowed files、exact changes、invariants、non-goals 和 completion signal。
- 所有 provider 的空输出行为已由直接代码证据确认，不存在未验证假设。
- 关键架构边界（ConfigLoader raw read、Service effective mapping、ToolsDiscovery pure aggregation、Fins provider absolute-only contract）在 plan 中一致且可测试。
- 测试断言具体到可写为 pytest 断言的级别。
- README 更新决策已按 CLAUDE.md 触发规则逐项裁决。
