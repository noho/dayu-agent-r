# WU-TOOLS-01-F03-R4 PR Review — AgentDS

## Verdict

**pass-with-findings** — 无阻塞 correctness、architecture、test 或 LLM-facing 文本问题。一份低严重度 finding 关于 `start_fins_upload` 的 LLM-facing schema description 不再传达任何路径授权语义；该缺口已由 residual `WU-TOOLS-01-F03-R4-POLICY-R1` 覆盖。

## PR Metadata

- **Repository**: noho/dayu-agent-r
- **PR**: [#160](https://github.com/noho/dayu-agent-r/pull/160)
- **Title**: WU-TOOLS-01-F03-R4: clean up Tools Discovery spec semantics
- **Author**: noho
- **Head**: `phase/wu-tools-01-f03-r4`
- **Base**: `main`
- **State**: OPEN / draft
- **Created**: 2026-06-21T01:08:52Z
- **Issue**: [#133](https://github.com/noho/dayu-agent-r/issues/133) — 评估并调整 Tools Discovery spec 语义

### Commands Run

```bash
gh pr view 160 --json title,url,author,headRefName,baseRefName,body,state,number,createdAt
gh pr diff 160 (全量, 65 files, 6929 lines)
gh pr checks 160 (no checks reported on branch)
git diff main...HEAD --stat (65 changed files)
git diff main...HEAD -- <production files>
pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q → 60 passed
pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q → 58 passed
pytest tests/runtime/test_config_loader.py::test_tool_discovery_provider_allow_empty_is_rejected -xvs → 1 passed
```

### Local HEAD vs Remote

当前分支 `phase/wu-tools-01-f03-r4`，最近 commit `de02e701` (`gateflow: record WU-TOOLS-01-F03-R4 draft PR`)。PR head 与该 commit 一致（通过 `gh pr view` 的 `headRefName` 和本地 `git log` 交叉验证）。remote `github` 可通过 `git push -u github` 推送到 GitHub。

## Issue-133 六项完成状态

| # | 请求项 | 实现状态 | 证据 |
|---|---|---|---|
| 1 | 去掉 `allow_empty` | ✅ 完成 | `ToolDiscoveryProviderConfig`、`ToolsDiscoveryProviderSpec`、`tool_discovery.json` 均移除；`config_loader.py` `_parse_tool_discovery_provider` 不再要求 `allow_empty`，且将旧字段作为未知字段拒绝；测试 `test_tool_discovery_provider_allow_empty_is_rejected` 验证 |
| 2 | 去掉 `include_read_tools` | ✅ 完成 | `dayu/fins/tools/provider.py` 移除 `_CONFIG_INCLUDE_READ_TOOLS_FIELD` 和 `_parse_bool_default`；`tool_discovery.json` 不再包含该字段；启用 read provider 始终返回九个 Fins read tools |
| 3 | `workspace_root` 改为 `"workspace/"` | ✅ 完成 | 四个 Fins providers 的 config 中 `workspace_root` 全部从 `null` 改为 `"workspace/"`；Service `_effective_fins_workspace_root_config_value` 负责将相对路径按 runtime `workspace_root` 解析为绝对路径后传给 Fins providers |
| 4 | `financial-read-tools` 迁移 OLD limits | ✅ 完成 | `tool_discovery.json` 中显式列出九项 limits 具体值（`processor_cache_max_entries: 128` 等）；`_parse_limits` 接受显式 config 值并回退到 `FinsToolLimits()` dataclass 默认值 |
| 5 | `financial-upload-tools` 去掉 `allowed_upload_roots` | ✅ 完成 | `upload_provider.py` `parse_allowed_upload_roots_config` 删除；`upload_tools.py` 移除 `allowed_upload_roots` 参数和 `_normalize_allowed_upload_roots`、`_resolve_upload_path` 的 allowlist 校验；`build_fins_upload_tool(runtime)` 签名简化 |
| 6 | `doc-tools` 迁移 OLD limits | ✅ 完成 | `tool_discovery.json` 中显式列出五项 Doc limits；`doc_provider.py` 启用但无 `allowed_paths` 时 fail fast with business-specific error；增加显式 limits 投影测试 |

## Findings

### F01-未修复-低-`start_fins_upload` files 参数 description 不再传达路径授权语义

- **入口/函数**: `_upload_parameters_schema()` → `"files"` property `"description"`
- **文件(行号)**: `dayu/fins/tools/upload_tools.py:229`
- **输入场景**: LLM 阅读 `start_fins_upload` 的 tool schema 参数说明
- **实际分支**: 不适用（schema 文本变更）
- **预期行为**: LLM 应从 schema description 理解上传文件路径的约束
- **实际行为**: 新 description `"Local file paths to upload. Each path must point to an existing non-empty regular file."` 传达了文件形态校验约束，但不传达任何路径范围或授权边界。旧 description 通过 `"Paths must be under the configured upload roots"` 至少向 LLM 传递了“路径受限于配置的根目录”的信号，现在该信号完全消失
- **直接证据**: diff 中 `upload_tools.py` 的 `files` parameter description 替换 (`dayu/fins/tools/upload_tools.py:229`)；`allowed_upload_roots` 相关校验逻辑已全部删除
- **影响**: LLM 在没有任何路径约束信号的情况下可能提交任意路径尝试，工具会在运行时因文件不存在/非普通文件/空文件而返回 `ValueError`，造成一次无效工具调用。这不是 correctness bug（工具行为正确拒绝非法文件），但增加了 LLM 的试错成本
- **建议改法和验证点**: 当前 WU 不处理此缺口——已被 `WU-TOOLS-01-F03-R4-POLICY-R1` 显式 deferred 到 future Host / policy design。建议在 description 中加入类似 `"Files must exist as non-empty regular files; allowed source directories are controlled by the system administrator."` 的提示语句，让 LLM 知道它不能任意选择路径。或等待 Host / policy 统一授权方案完成后统一更新 schema
- **修复风险（低）**: 仅为 LLM-facing 文本调整
- **严重程度（低）**: 不影响工具执行 correctness，不产生错误状态，仅增加 LLM 试错可能性

## Closing Keyword 判断

PR body 使用 `Closes #133`。判断：**合理**。

- Issue-133 的六项 Tools Discovery spec 请求已全部实现、测试和文档同步。
- 四项 deferred residual risks 均使用独立追踪 ID（`WU-TOOLS-01-F03-R4-POLICY-R1` 等），不属于 issue-133 本身范围，在 control doc 中各自有明确的 deferred-with-owner 状态。
- PR body 在 "Residual risks / owners" 节中完整列出了四项 residual 及其 owner，与 control doc 一致。
- Merge 后 `Closes #133` 会正确关闭 issue-133；residual risks 不会因 issue 关闭而丢失追踪——它们由 control doc 独立管理。

## Web Smoke Residual 分类判断

分类 `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1` (deferred-with-owner, web smoke / CI owner)：**可接受**。

- 失败测试 `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases` 未出现在 PR diff 中。
- `utils/smoke_web_ci.py` 也未出现在 PR diff 中。
- 该测试仅通过移除 `allow_empty=False` 参数与 WU 产生间接关联（`utils/diagnose_web_access.py`），但该文件中只改了 spec 构造参数，不改变测试断言逻辑。
- stdout-vs-logging capture 问题是 CI 测试基础设施问题，非本 WU 引入。

## Residual Risks / Uncovered Areas

| ID | 状态 | Owner | 说明 |
|---|---|---|---|
| WU-TOOLS-01-F03-R4-POLICY-R1 | deferred-with-owner | Future Host / policy design | 上传工具不再做本地文件 allowlist 授权，文件读取权限治理留待统一方案 |
| WU-TOOLS-01-F03-R4-PATH-R1 | deferred-with-owner | Future provider path-boundary hardening | Doc / upload 路径工具当前按 `Path.resolve()` 语义处理 symlink |
| WU-TOOLS-01-F03-R4-SCENE-R1 | deferred-with-owner | Future scene manifest maintenance | 默认 scene 的 Fins tool_names 已显式列出；新增 packaged scene 需同步验证 |
| WU-TOOLS-01-F03-R4-WEB-SMOKE-R1 | deferred-with-owner | Web smoke / CI owner | 日志 capture mismatch，非本 WU 引入 |

无本 WU scope 内未覆盖的新 uncovered area。所有 deferred items 在 control doc 中均有明确 owner 和追踪 ID。

## PR Body 准确性

PR body summary 与真实代码改动一致：

- ✅ "Remove provider-level `allow_empty`" — 准确
- ✅ "Remove Fins read provider `include_read_tools`" — 准确
- ✅ "Set packaged Fins `workspace_root` default to `workspace/`" — 准确
- ✅ "Migrate Doc/Fins limits into packaged `tool_discovery.json`" — 准确
- ✅ "Remove upload `allowed_upload_roots`" — 准确
- ✅ "Prevent default non-upload scenes from selecting `start_fins_upload`" — 准确

无 "future work 写成已完成" 的情况。所有 deferred items 均明确标注为 residual。

## 非 WU 改动检查

65 个 changed files 中：
- 30+ files 为 `docs/reviews/` 下的 review artifact（前置 gate 产出）
- 3 files 为 docs（`design.md`, `issues-implementation-control.md`, plan doc）
- 3 README 更新
- 其余均为 WU scope 内的 production / test 文件

无发现非本 WU 改动。无遗漏最新 control doc 状态。

## 完成状态

- [x] PR metadata reviewed and commands run
- [x] Issue-133 六项完成状态确认
- [x] PR body 准确性确认
- [x] Closing keyword 合理性确认
- [x] Web smoke residual 分类确认
- [x] 非 WU 改动检查
- [x] correctness / architecture / test / LLM-facing 文本审查
- [x] 前置 artifact 核对（plan doc + aggregate deepreview artifacts）
- [x] Residual risks / uncovered areas 记录

## Review 覆盖范围

本次 review 沿以下真实代码路径走读：

1. **Config 加载链路**: `tool_discovery.json` → `ConfigLoader.load_tool_discovery()` → `_parse_tool_discovery_provider()` → `ToolDiscoveryProviderConfig`（验证 `allow_empty` 字段已完全移除，旧字段被拒绝）
2. **Service assembly 链路**: `assemble_effective_tool_provider_configs()` → `_effective_tool_provider_config()` → `_effective_fins_workspace_root_config_value()` → `_is_fins_workspace_bound_provider_config()`（验证相对 → 绝对 workspace_root 解析、非字符串/空字符串拒绝、缺少 runtime workspace_root 时的错误处理）
3. **ToolsDiscovery 链路**: `_tool_discovery_specs()` → `ToolsDiscovery.discover_from_bindings()` → `_validate_provider_output()`（验证 `allow_empty` 移除后空 provider 输出统一 fail fast）
4. **Provider 边界**: `provider.py` (read)、`upload_provider.py`、`upload_tools.py`、`doc_provider.py`（验证 `include_read_tools` 移除、`allowed_upload_roots` 逻辑移除、Doc fail-fast）
5. **Scene manifest 暴露面**: 11 个 manifests 逐一核对（验证所有非 upload 默认 scene 不再通过 broad `fins` tag 选中 `start_fins_upload`）
6. **Wait adapter 构造链路**: `_fins_wait_adapter_registry_from_provider_configs()` → `_fins_workspace_root_from_provider_config()` → `_single_fins_workspace_root()`（验证 effective config 的绝对路径消费正确）
7. **测试面**: config_loader、tools_discovery、host_assembly、fins_ingestion、fins_storage、doc_tools_provider 等关键测试更新核验
