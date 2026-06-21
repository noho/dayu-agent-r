# WU-TOOLS-01-F03-R4 Aggregate Deepreview

## Verdict

**pass**

## Scope

- **Mode**: current changes (aggregate deepreview of completed WU)
- **Branch**: `phase/wu-tools-01-f03-r4`
- **Base**: `main`
- **Commits reviewed**: `fe212365`, `c785f218`, `3f7fd44a`, `4514f550`, `ee5f2e19`, `d8db0b49`, `21751ec9`
- **Output file**: `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-ds.md`
- **Artifacts reviewed**: plan (`docs/host/host-issues/`), all slice reviews (`docs/reviews/wu-tools-01-f03-r4-slice*-code-review-*.md`), slice implementations, slice fixes, re-reviews, and final validation
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Excluded scope**: GitHub remote operations, PR creation, merge, push; web smoke log capture fix; Host unified permission system design

## Commands Run

```bash
# Full diff analysis
git diff --stat main...HEAD
git diff main...HEAD -- '*.py' '*.json'

# pyright
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings, 0 informations

# Focused test suites
pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q
# → 60 passed

pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
# → 58 passed, 3 upstream edgar deprecation warnings

pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
# → 112 passed, 3 upstream edgar deprecation warnings

pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_assets_migration.py -q
# → 38 passed

# Web smoke residual confirmation
pytest tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases -q
# → 1 failed (pre-existing, log capture vs stdout mismatch)

# Broad test suite minus web smoke
pytest tests/runtime tests/service tests/fins tests/tools -q --ignore=tests/tools/web/test_smoke_web_ci.py
# → 866 passed, 1 skipped

# Stale field grep
rg -n "include_read_tools|allowed_upload_roots" dayu/ tests/ README.md
# → only tests/runtime/test_config_loader.py:413 negative assertion for allowed_upload_roots

rg -n "workspace_root\": null" dayu/config/tool_discovery.json tests/
# → no matches

rg -n "\"allow_empty\"|allow_empty" dayu/config/ dayu/runtime/ dayu/service/ dayu/fins/ dayu/tools/ tests/ README.md docs/host/design.md
# → all remaining hits are scene tool_selection.allow_empty (independent semantics),
#   internal ToolBundle._allow_empty, old-field rejection tests, or doc text correctly
#   describing the current semantics

# Scene manifest tag verification
rg -n '"fins"|fins-upload|"ingestion"|start_fins_upload' dayu/config/prompts/manifests/
# → no matches
```

## Review Coverage

### Covered by this aggregate review

Each review target was verified by direct code reading of the complete execution chain:

1. **provider-level `allow_empty` 删除 / scene `tool_selection.allow_empty` 保留**
   - `ToolsDiscoveryProviderSpec` dataclass: no `allow_empty` field (`dayu/runtime/tools_discovery.py:88-112`)
   - `_validate_provider_output`: raises `ToolsDiscoveryError` on empty definitions (`tools_discovery.py:542-543`)
   - `discover_from_bindings`: `_allow_empty=True` only on the empty `ToolBundle` when zero providers are enabled (`tools_discovery.py:262-266`), not on any provider output
   - Scene `tool_selection.allow_empty`: independent semantics confirmed in `scene_prepare.py:287,1101-1104` and all manifests
   - ConfigLoader rejects old `allow_empty` field: `test_tool_discovery_provider_allow_empty_is_rejected` (`tests/runtime/test_config_loader.py:1083-1098`)
   - Runtime rejects empty provider output: `test_empty_provider_without_allow_empty_fails` (`tests/runtime/test_tools_discovery.py:420`)

2. **`financial-read-tools` 删除 `include_read_tools`**
   - Provider code path: `dayu/fins/tools/provider.py:31-58` — no `include_read_tools` branch; `enabled` is sole gate
   - Packaged config: `tool_discovery.json:3-23` — `financial-read-tools` has no `include_read_tools`
   - `ConfigLoader`: `_parse_tool_discovery_provider` allows only `config` as optional field (`config_loader.py:2023-2067`); unknown fields like `include_read_tools` would be rejected by `_require_required_and_optional_fields`
   - grep: zero production/test hits for `include_read_tools`

3. **Packaged Fins `workspace_root` 默认 `workspace/` → Service effective absolute path → provider 只接收 absolute path**
   - Packaged: `tool_discovery.json` — all four Fins providers have `"workspace_root": "workspace/"`
   - Service resolution chain:
     - `assemble_effective_tool_provider_configs` (`host_assembly.py:363-386`) iterates provider configs
     - `_effective_tool_provider_config` (`host_assembly.py:943-967`) checks `_is_fins_workspace_bound_provider_config`, calls `_effective_fins_workspace_root_config_value`
     - `_effective_fins_workspace_root_config_value` (`host_assembly.py:970-1012`): handles `None` (inject project root), non-string (raise), empty string (raise), absolute (pass through), relative (resolve via `_resolve_project_path`)
   - Provider boundary:
     - `parse_fins_workspace_root_config` (`fins/tools/provider.py:61-80`): requires non-empty absolute string, rejects relative, no cwd/env fallback
     - `_fins_workspace_root_from_provider_config` (`host_assembly.py:1521-1541`): same absolute-only requirement for wait adapter
   - Tests: `tests/service/test_host_assembly.py` covers effective resolution scenarios, error boundaries, and wait adapter workspace consumption
   - Wait adapter construction: `_fins_wait_adapter_registry_from_provider_configs` (`host_assembly.py:1453-1487`) consumes `effective_provider_configs` from `discovered_tools` — same effective config tuple used for both discovery and wait adapter construction

4. **Doc / Fins limits 从 OLD 配置迁移到 packaged `tool_discovery.json`**
   - `financial-read-tools.config.limits`: 9 explicit positive integer fields (`tool_discovery.json:11-22`)
   - `doc-tools.config.limits`: 5 explicit positive integer fields (`tool_discovery.json:63-69`)
   - Fins provider parsing: `_parse_limits` (`fins/tools/provider.py:83-153`) → `FinsToolLimits` → enters all 9 `ToolDefinition.truncate.limits`
   - Doc provider parsing: `_parse_limits` (`tools/doc_provider.py:60-105`) → `DocToolLimits` → enters doc `ToolDefinition.truncate.limits`
   - `processor_cache_max_entries` correctly treated as runtime-only (not in ToolDefinition.truncate.limits); tests confirm absence (`tests/fins/test_fins_storage_provider.py` Slice 5 fix)
   - Partial limits fallback to dataclass defaults tested (`tests/tools/test_doc_tools_provider.py`)
   - ConfigLoader does NOT parse provider-specific limits — provider-owned parsing

5. **Upload provider/tool 删除 `allowed_upload_roots`**
   - `upload_provider.py` (`fins/tools/upload_provider.py:21-46`): no `allowed_upload_roots` reference; always registers `start_fins_upload` when enabled with valid absolute `workspace_root`
   - `upload_tools.py` (`fins/tools/upload_tools.py:381-427`): `_upload_files_from_arguments` validates action/file count, `_resolve_upload_file_path` validates existing regular file + non-empty; no allowlist containment
   - Delete action still forbids files (`upload_tools.py:400-402`)
   - Packaged config: `financial-upload-tools.enabled=true`, no `allowed_upload_roots` (`tool_discovery.json:45-54`)
   - Repository write boundary: upload tool only provides local source path; destination write path derived by `FinsIngestionRuntime` / `dayu.fins.storage` repository
   - grep negative assertion only: `tests/runtime/test_config_loader.py:413`

6. **默认非 upload scene 不通过 broad tag 误选 `start_fins_upload`**
   - All default scene manifests use explicit Fins tool names (`list_documents`, `get_document_sections`, `read_section`, `search_document`, `list_tables`, `get_table`, `get_page_content`, `get_financial_statement`, `query_xbrl_facts`, `start_fins_download`, `start_fins_preprocess`)
   - Only `"web"` tag in `tool_tags_any`
   - No scene manifest uses `"fins"`, `"ingestion"`, or `"fins-upload"` tags
   - `start_fins_upload` is not selected by any default scene
   - grep confirmation: zero hits for broad Fins/ingestion/upload tags in manifests

7. **README / design / tests / control doc 当前语义一致**
   - `docs/host/design.md:2058` — states enabled provider empty output is configuration error; `tool_selection.allow_empty` is independent
   - `dayu/config/README.md` — documents packaged `workspace/`, effective resolution, Doc/Fins limits, `doc-tools.enabled=false`, scene selection avoiding upload via broad tag
   - `dayu/fins/README.md` — describes all four Fins providers requiring absolute `workspace_root`, `enabled` as sole read switch, upload local source authorization not provider-owned
   - `tests/README.md` — coverage descriptions match current tests
   - `docs/host/issues-implementation-control.md` — WU entry current through Slice 7, residual risks table current
   - No process/gate/PR status leaked into stable docs

### Not covered / excluded by design
- Host unified permission system (explicit non-goal)
- Web smoke log capture fix (classified residual `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1`)
- SEC/Fins CI pipeline, CN/HK Docling CI pipeline (out of scope)
- Full end-to-end Host/Agent/Runner execution with actual LLM (beyond unit/integration test scope)

## Findings

### F-01【低】empty `ToolBundle` construction 使用 `_allow_empty=True` 的语义区分度不足

- **入口/函数**: `ToolsDiscovery.discover_from_bindings` → `ToolBundle(definitions=(), _allow_empty=True)`
- **文件(行号)**: `dayu/runtime/tools_discovery.py:262-266`
- **输入场景**: 当所有 provider 均 `enabled=false` 时，`discover_from_bindings` 接收空 bindings 元组，循环体不执行，`definitions` 保持为空列表
- **实际分支**: `not definitions` → `ToolBundle(definitions=(), _allow_empty=True)`
- **预期行为**: 当零个 provider 启用时，返回空 ToolBundle 是正确的；但 `_allow_empty=True` 是 ToolBundle 构造参数，其语义是"此空 bundle 由调用方显式授权"，与下游 ScenePrepare 的 `tool_selection.allow_empty` 是不同层次的独立语义
- **实际行为**: 行为正确——零 provider 启用时返回空 ToolBundle，由 Service 层决定是否允许继续
- **直接证据**: `tools_discovery.py:262-266` — `_allow_empty=True` 仅在零 provider 启用时用于空 ToolBundle 构造；该参数是 ToolBundle 私有构造契约，不进入 LLM-facing material、不进入 ToolDefinition、不进入 provider output 校验
- **影响**: 无运行时错误。语义区分度不足：如果未来有人在 enabled provider 也产生空输出的路径上误用 `_allow_empty=True`，会绕过 `_validate_provider_output` 的保护。当前代码路径上该风险不成立——每个 enabled provider 的输出必然经过 `_validate_provider_output`
- **建议改法和验证点**: 接受当前状态；若未来 ToolBundle 构造语义变化或新增空 ToolBundle 构造点，review 时需确认没有绕过 provider output validation。不要求立即修改
- **修复风险**: 低
- **严重程度**: 低
- **分类建议**: accepted — 语义隔离已由 `_validate_provider_output` 在 provider 输出边界强制执行，当前无实际缺陷

### F-02【低】`discover_from_bindings` 中存在双重 `enabled` 过滤

- **入口/函数**: `ToolsDiscovery.discover_from_bindings` → `if not binding.spec.enabled: continue`
- **文件(行号)**: `dayu/runtime/tools_discovery.py:234`
- **输入场景**: 当 `discover_from_bindings` 被外部调用方以包含 disabled spec 的 bindings 调用时
- **实际分支**: Line 234 的 `if not binding.spec.enabled: continue`
- **预期行为**: 该 guard 是防御性的，因为公共入口 `discover` (`tools_discovery.py:208-209`) 已过滤掉 `enabled=false` 的 specs，不会产生 disabled binding。但如果外部调用方直接调用 `discover_from_bindings` 并传入 disabled binding，此 guard 是唯一保护
- **实际行为**: 行为正确——双重过滤防止绕过公共入口直接调用。两个 enabled 检查的存在使 `discover` 和 `discover_from_bindings` 各自独立安全
- **直接证据**: `tools_discovery.py:208-209` (discover 过滤) + `tools_discovery.py:234` (discover_from_bindings 冗余过滤)
- **影响**: 无运行时错误。防御性代码增加微小的认知负担（阅读时需要理解为什么有两处 checking），但不产生不正确行为
- **建议改法和验证点**: 接受当前状态。这是有意的 defensive check，确保 `discover_from_bindings` 作为独立公共方法也是安全的
- **修复风险**: 低
- **严重程度**: 低
- **分类建议**: accepted — 防御性设计，不产生实际缺陷

## Web Smoke Residual Judgment

### `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1`

**Judgment**: 确认为非本 WU 引入的提前存在 residual。

**直接证据**:
- 失败测试: `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases`
- 失败断言: `assert "web smoke execution started" in captured.out` (line 119)
- 失败原因: `"web smoke execution started"` 是 `logging.info()` 调用，通过 Python logging 模块输出到 stderr；pytest 将其捕获到 `Captured log call` (stderr)，而非 `captured.out` (stdout)。测试断言在 `captured.out` 中查找，故失败
- 本 WU 未修改: `tests/tools/web/test_smoke_web_ci.py` (0 lines changed) 和 `utils/smoke_web_ci.py` (0 lines changed)
- 当前分支 `test_smoke_web_ci.py` 与 `main` 分支内容一致（该文件不在 diff stat 中）

**分类**: `deferred-with-owner` → Web smoke / CI owner。已在 `docs/host/issues-implementation-control.md` Residual Risk 表中登记为 `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1`。

## Residual Risks and Uncovered Areas

| Risk | Severity | Status |
|------|----------|--------|
| Web smoke log capture assertion failure | 低 | `deferred-with-owner` — Web smoke / CI owner |
| Doc provider symlink path behavior | 低 | 当前 `Path.resolve()` follows symlinks；无专项测试。Slice 4 DS-F1 已 deferred |
| Scene test uses hardcoded default scene id list | 低 | 当前 packaged manifests 已覆盖；Slice 4 DS-F2 已 deferred |
| `_fins_workspace_root_from_provider_config` 在 `effective_provider_configs` 已被正确解析的前提下是 redundant guard | 低 | 作为 fail-fast 保护合理，不构成风险 |

## Completion Status

All seven review targets confirmed:
1. ✅ provider-level `allow_empty` 删除
2. ✅ `financial-read-tools` 删除 `include_read_tools`
3. ✅ packaged Fins `workspace_root` 默认 `workspace/`，Service 解析为 effective absolute path
4. ✅ Doc / Fins limits 从 OLD 迁移到 packaged `tool_discovery.json`
5. ✅ upload provider/tool 删除 `allowed_upload_roots`
6. ✅ 默认非 upload scene 不通过 broad tag 误选 `start_fins_upload`
7. ✅ README / design / tests / control doc 当前语义一致

pyright: 0 errors. All focused test suites pass. Broad test suite (866 passed, 1 skipped) passes excluding the pre-existing web smoke log capture issue. No blocking correctness, architecture, or test gap found.

Aggregate deepreview gate: **pass**.
