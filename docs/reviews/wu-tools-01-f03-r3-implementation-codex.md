# WU-TOOLS-01-F03-R3 Implementation Artifact

## Gate / Scope

- Gate: implementation
- Work unit: `WU-TOOLS-01-F03-R3`
- Scope: Web tools config assembly 与 search provider smoke gap
- Design source: `docs/host/design.md`、`docs/engine/design.md`
- Plan source: `docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f03-r3-plan-review-controller-adjudication.md`

## 修改摘要

- 补齐 `dayu/config/tool_discovery.json` 中默认 `web-tools.config` 的 `provider=auto`、`fetch_truncate_chars=80000`、`playwright_channel=chrome`、`playwright_storage_state_dir=""`，保持 `enabled=false` 与 `allow_private_network_url=false`。
- 补充 ConfigLoader / Service assembly 测试，覆盖默认 Web config typed view、Web config 原样进入 `ToolsDiscoveryProviderSpec.config`，以及完整 `ConfigLoader.load()` + `discover_service_tools()` 能发现 `search_web` / `fetch_web_page`。
- 补充 Web provider deterministic tests，覆盖 `provider` / timeout / max results / private URL flag 进入 `search_web`，`fetch_truncate_chars` 进入 `ToolTruncateSpec`，`playwright_channel` 与空/非空 `playwright_storage_state_dir` 进入 browser fallback 参数。
- 增强 `utils/smoke_web_ci.py`：
  - 新增默认 local assembly config hard gate，走 `ConfigLoader.load()`、`discover_service_tools()` 与 `ToolDefinition.callable`，不调用 diagnostics 子进程。
  - 新增 `web-smoke-assembly-v1` artifact，记录 overlay provider config、`truncate_max_chars`、tool names 与 fetch 内容匹配结果。
  - 新增 typed `search_cases`，默认运行 `auto` / `tavily` / `serper` / `duckduckgo` 四个 `search_web` provider diagnostic-only cases。
  - search provider artifact 使用 `web-smoke-search-v1`，只记录 API key env 名与 present/missing，不写 secret；外部 provider 失败不影响 local hard gate。
  - `external_cases` 继续只保留外部 URL fetch diagnostics，不混入 search provider cases。
- 更新 `tests/README.md` 的 Web provider 与 Web smoke 测试事实；`dayu/config/README.md` 已声明字段与职责，无需修改。

## 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - Result: 133 passed, 3 warnings
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings, 0 informations
- `source .venv/bin/activate && python utils/smoke_web_ci.py`
  - Result: exit code 0
  - Output: `workspace/output/web_smoke/web-smoke-20260610T063509Z`
  - Summary: status passed, local_cases 4, external_cases 2, search_cases 4, diagnostic_only 6
  - Local assembly config case: passed，artifact 记录 `provider_config.fetch_truncate_chars=3210` 与 `truncate_max_chars=3210`
- `git diff --check`
  - Result: passed

## 文档决策

- `tests/README.md` 已更新，因为本次修改改变了 tests 与 smoke 的实际覆盖事实。
- `dayu/config/README.md` 未修改，因为该 README 已声明 `web-tools.config` 字段、默认 disabled 与 provider config 职责，本次只是让默认 JSON 与既有文档一致。
- 未修改 Host / Engine 设计真源；本次不涉及 public contract、durable schema 或状态机变更。

## 风险 / 未覆盖项

- Tavily / Serper API key、auth、quota、rate limit 与外部 provider 可用性仍是 diagnostic-only，不作为 local hard gate；artifact 记录 bucket 与建议下一步。
- DuckDuckGo 与 external URL live 结果受外部网络和站点页面变化影响；默认只提供诊断证据，不判断为本地 regression。
- Web tools 仍通过迁移 adapter 暴露；native 化与 legacy adapter 删除继续由既有 residual `WU-TOOLS-01-F01-02-R3` / GitHub Issue #130 承接。

## Completion Status

Implementation gate completed locally. 下一步应进入 code review gate；本轮未 commit、未 push、未创建 PR。
