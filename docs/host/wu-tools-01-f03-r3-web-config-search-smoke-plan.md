# WU-TOOLS-01-F03-R3 Web Config And Search Smoke Plan

## 1. 范围与第一性原理判断

本计划只覆盖 `WU-TOOLS-01-F03-R3`：修复 Web tools 默认配置装配缺口，并增强 Web smoke 对生产式 Web config assembly 与 `search_web` provider 路径的观测。当前任务处于 plan gate；本计划不进入 implementation gate，不修改 Host / Engine public contract。

### 1.1 问题是否成立

问题成立，且不是单纯 provider/API availability residual。

直接证据：

- `dayu/config/tool_discovery.json` 的 `web-tools.config` 目前只有 `request_timeout_seconds`、`max_search_results`、`allow_private_network_url`，缺少 `dayu/config/README.md` 已声明的 `provider`、`fetch_truncate_chars`、`playwright_channel`、`playwright_storage_state_dir`。
- `dayu/runtime/config_loader.py` 对 `tool_discovery` 的 provider `config` 只做 JSON object typed view，不解释 Web 语义；因此默认配置缺字段不会被 Runtime 自动补齐成可审计默认。
- `dayu/service/host_assembly.py` 的 `discover_service_tools()` 通过 `_tool_discovery_specs()` 把 `ToolDiscoveryProviderConfig.config` 交给 `ToolsDiscoveryProviderSpec.config`；当前测试已有通用 doc provider config 原样映射，但没有 web-specific 默认配置与 production discovery 闭环证据。
- `dayu/tools/web/provider.py` 的 `WebToolsConfig` 与 `_parse_config()` 已支持 `provider`、`fetch_truncate_chars`、`playwright_channel`、`playwright_storage_state_dir`，说明 provider 侧具备能力，缺口主要在默认 config 与测试 / smoke 证据。
- `dayu/tools/web/web_tools.py` 的 `register_web_tools()`、`_create_search_web_tool()`、`_create_fetch_web_page_tool()` 会把 provider config 闭进 `search_web` / `fetch_web_page` callable；但当前测试没有同时证明 search provider 参数、truncate spec 与 Playwright fallback 参数都来自 config。
- `dayu/tools/web/web_search_providers.py` 的 `_candidate_providers()` 覆盖 `auto` / Tavily / Serper / DuckDuckGo，`TAVILY_API_KEY` / `SERPER_API_KEY` 影响候选与失败语义；当前 smoke 没有输出这些 provider 路径的成功 / 失败 artifact。
- `utils/smoke_web_ci.py` 当前 local cases 通过 `utils.diagnose_web_access` 间接覆盖 fetch path，不证明 `ConfigLoader -> Service discover_service_tools -> ToolsDiscovery -> web provider -> ToolDefinition.callable` 生产式 assembly 链路。

### 1.2 真 blocker 与 diagnostic-only

真 blocker：

- 默认 `web-tools.config` 缺少 README 已声明且 provider 已支持的配置字段，导致默认配置不完整且不可由 config artifact 自解释。
- ConfigLoader / Service assembly / ToolsDiscovery / web provider / tool callable 链路没有 web-specific hard evidence，无法证明生产式装配不会丢 Web provider config。
- `fetch_truncate_chars`、`playwright_channel`、`playwright_storage_state_dir` 是否进入工具闭包缺少测试；这会直接影响本地 fetch 行为与 browser fallback 参数。
- `utils/smoke_web_ci.py` local smoke 没有 production-style assembly case；如果配置装配断裂，当前 smoke 仍可能通过，因为它只走 diagnostics 临时构造的 fetch config。

Diagnostic-only：

- Tavily / Serper API key 缺失。
- Tavily / Serper 鉴权失败、quota / rate-limit、provider 服务不可用、网络波动。
- DuckDuckGo HTML 搜索页面临时变化或外部网络不可达。

原因：这些外部搜索 provider 状态不由本地仓库、默认 config 或 Service assembly 决定。在建立明确 provider 环境契约前，它们必须被观测并写入 artifact，但不能让本地 fetch hard gate 失败。只有配置缺失、assembly 断裂、tool closure 未收到配置，才是 local blocker。

## 2. 非目标与边界

- 不恢复旧 `run.json` 兼容读取。
- 不重写 Web provider 架构，不迁移 legacy adapter，不引入新 provider abstraction。
- 不修改 Host / Engine public contract；如果实现发现必须改 public contract，立即停止并回到设计真源，不在本 work unit 内扩 scope。
- 不把外部 provider 波动升级为 hard gate。
- 不把完整 Web CI URL corpus 变成 smoke gate。
- 不让 `dayu.runtime` import Service / Host / Engine / Fins / UI。
- 不把显式 Web config 参数放入 extra payload 或弱类型跨层袋。
- `utils/smoke_web_ci.py` 是仓库级 smoke harness，允许直接 import `ConfigLoader`、runtime location helper 与 `discover_service_tools()` 来验证生产式本地装配；不得为了 smoke 新增 production helper、wrapper 或 facade。

## 3. Slice 计划

### Slice 1：补齐默认 Web provider config

目标：让包内默认 `tool_discovery.json` 与 `dayu/config/README.md` 声明一致，并让默认 scene manifests 能从默认工具目录中选到 Web tools。

文件：

- `dayu/config/tool_discovery.json`
- `tests/runtime/test_config_loader.py`
- `dayu/config/README.md`，按 README 约束判断是否需要改

实施步骤：

1. 在 `web-tools.config` 增加：
   - `provider`: `"auto"`
   - `fetch_truncate_chars`: `80000`
   - `playwright_channel`: `"chrome"`
   - `playwright_storage_state_dir`: `"workspace/.dayu/web_tools_storage_states"`
2. 保持 `enabled=true`、`allow_empty=true`、`allow_private_network_url=false`。
3. 在 `test_default_runtime_config_files_load_as_typed_views()` 中断言上述字段从默认配置原样进入 `config.tool_discovery.providers["web-tools"].config`。
4. 当前决策：`dayu/config/README.md` 已声明 `web-tools.config` 字段；除非实现改变配置职责或目标读者需要，否则不修改该 README，不为默认值补表做机械文档同步。

测试：

- `pytest tests/runtime/test_config_loader.py -q`

验收信号：

- 默认 config 中 web provider 字段完整。
- ConfigLoader 不解释 Web 语义，只原样保留 JSON config。
- Web tools provider 默认参与 discovery；private / local network URL 仍默认拒绝。

Stop condition：

- 若 ConfigLoader 需要新增 Web-specific typed schema 才能通过测试，停止；这会违反 Runtime 层中立边界。

### Slice 2：补 Service assembly 到 ToolsDiscoveryProviderSpec 的 Web config 证据

目标：证明 Web provider config 从 ConfigLoader 进入 Service `_tool_discovery_specs()` 和 `discover_service_tools()`，且没有被 Service 解释或丢字段。

文件：

- `tests/service/test_host_assembly.py`
- `dayu/service/host_assembly.py` 仅当测试发现映射缺口时最小修复

实施步骤：

1. 增加 web-specific `_tool_discovery_specs()` 测试：构造 `ToolDiscoveryProviderConfig(provider_id="web-tools", import_path="dayu.tools.web:discover_tools", enabled=True, config={...})`，断言 `ToolsDiscoveryProviderSpec.config` 完整等于输入字段。
2. 增加 ConfigLoader + Service discovery 闭环测试：在临时 workspace overlay 中只启用 `web-tools`，设置 `allow_private_network_url=true` 与非默认 `provider`、`fetch_truncate_chars`、`playwright_channel`、`playwright_storage_state_dir`。
3. 调用 `ConfigLoader(...).load()` 与 `discover_service_tools(config)`，断言发现 `search_web` / `fetch_web_page`，provider report 指向 `web-tools`。
4. 不在 Service 中解析 Web 字段；Service 只负责 config 到 ToolsDiscovery spec 的映射。

测试：

- `pytest tests/service/test_host_assembly.py -q`

验收信号：

- `ToolsDiscoveryProviderSpec.config` 保留 Web config 原文。
- `discover_service_tools()` 能通过真实 `dayu.tools.web:discover_tools` 发现 Web tool bundle。
- 没有引入 Service 对 Web 业务字段的硬编码解释。

Stop condition：

- 若需要让 Service 认识 `provider` / `fetch_truncate_chars` 等 Web 字段才能完成映射，停止；应修复映射原样透传，而不是扩大 Service 语义。

### Slice 3：补 Web provider 闭包测试

目标：证明 Web provider config 进入 `search_web`、truncate spec 和 Playwright fallback 参数。

文件：

- `tests/tools/web/test_web_tools_provider.py`
- `dayu/tools/web/provider.py` / `dayu/tools/web/web_tools.py` 仅当测试发现闭包缺口时最小修复

实施步骤：

1. 增加 search closure 测试：
   - monkeypatch `web_tools.search_public_web`；
   - 用 `_discover_definitions({"provider": "serper", "request_timeout_seconds": 3.5, "max_search_results": 4, "allow_private_network_url": True})` 获取 `search_web`；
   - 调用 callable；
   - 断言 fake 收到 `provider="serper"`、`request_timeout_seconds=3.5`、`max_search_results=4`、`allow_private_network_url=True`。
2. 扩展已有 truncate 测试，保留 `fetch_truncate_chars` 进入 `fetch_web_page.truncate.limits["max_chars"]` 的断言。
3. 增加 Playwright fallback 参数测试：
   - 优先 monkeypatch `_try_playwright_fallback` 记录 `playwright_channel` 与 `playwright_storage_state_path`，或使用现有稳定 backend seam；避免为了触达 fallback 精确耦合 requests 主路径的多处升级条件。
   - 覆盖非空 storage state dir：用临时 storage state dir 和 host 对应 JSON 文件，断言 callable 传入配置的 channel，并按 URL host 解析到 `<host>.json`。
   - 覆盖空 storage state dir：配置 `playwright_storage_state_dir=""`，断言 fallback 收到的 storage state path 为空值 / 不启用 storage state。
4. 所有 Web provider 测试保持 deterministic，不做 live network。

测试：

- `pytest tests/tools/web/test_web_tools_provider.py -q`

验收信号：

- `provider` 确实进入 `search_public_web()`。
- `fetch_truncate_chars` 确实进入 current `ToolTruncateSpec`。
- `playwright_channel` / `playwright_storage_state_dir` 确实进入 browser fallback 参数。
- 不引入旧 registry / truncation / fetch_more / UI import。

Stop condition：

- 如果 Playwright fallback 参数只能通过不可测试的内部路径观测，先补最小可观测 helper 或现有 backend monkeypatch 点；不得通过 brittle string inspection 或访问闭包 cell 伪造证明。

### Slice 4：增强 smoke 的 local assembly config hard gate

目标：在 `utils/smoke_web_ci.py` 增加本地 assembly config case，走生产式 `ConfigLoader -> Service discover_service_tools -> ToolsDiscovery -> ToolDefinition.callable`，验证本地 fetch path 与配置闭包。

文件：

- `utils/smoke_web_ci.py`
- `tests/tools/web/test_smoke_web_ci.py`

实施步骤：

1. 新增 case kind，例如 `local_assembly_config`。
2. 在 smoke 本地 fixture server 启动后，为该 case 创建临时 workspace config overlay：
   - 启用 `web-tools`。
   - 设置 `allow_private_network_url=true`，否则 loopback URL 应按安全策略被拒绝。
   - 设置可识别的 `provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`playwright_channel`、`playwright_storage_state_dir`。
   - overlay 只写 `tool_discovery.json`；其余配置文件来自显式 `package_config_dir=dayu/config`。
3. 显式构造 `ConfigLoader(package_config_dir=<repo>/dayu/config, workspace_config_dir=<temp config dir>)` 并调用 `load()`，再调用 `discover_service_tools(config)`，从 `ServiceDiscoveredTools.tool_bundle` 中取 `fetch_web_page` 的 `ToolDefinition.callable`。
   - `ConfigLoader.load()` 必须走完整五类配置加载与校验链路；不得降级为 `load_tool_discovery()` 或手写 partial assembly。
   - 若 `ConfigLoader.load()` 因包内配置、overlay、跨文件引用或本地装配基础设施失败而报错，分类为 local assembly hard failure / infra failure，并让 smoke 非 0；不得 skip 或降级。
4. 通过 callable 抓取 local HTML fixture，使用当前 `BatchToolExecutionContext` 测试 helper 风格构造 execution context。
5. 写独立 artifact，例如 `diagnostics/local/local-assembly-config.json`，字段保持最小：
   - `schema_version`: `"web-smoke-assembly-v1"`
   - `case_kind`: `"local_assembly_config"`
   - `tool_names`
   - `provider_config`
   - `called_tool`: `"fetch_web_page"`
   - `fetch_ok`
   - `content_length`
   - `observed_title` 或 `content_contains_fixture_text`
   - `truncate_max_chars`
   - `assembly_path`: 固定字符串，说明本 case 走 `ConfigLoader -> discover_service_tools -> ToolDefinition.callable`
   - `bucket`
   - `suggested_next_step`
6. artifact 与断言必须证明 overlay 配置进入 provider/tool closure：
   - `provider_config.fetch_truncate_chars` 等于 overlay 中设置的 `fetch_truncate_chars`。
   - `truncate_max_chars` 等于 overlay 中设置的 `fetch_truncate_chars`。
   - `provider_config.provider`、`request_timeout_seconds`、`max_search_results`、`playwright_channel`、`playwright_storage_state_dir` 至少在 artifact 中保留 overlay 值，便于审计。
7. 将该 case 计入 `local_cases`，失败时 exit code 为 local blocker：
   - 配置加载失败：`web_config_loader_failure`
   - Service discovery 失败：`web_assembly_discovery_failure`
   - 工具缺失：`web_tool_missing`
   - callable 失败：`web_assembly_fetch_failure`
   - fixture 内容不匹配：`web_assembly_fetch_content_failure`
   - overlay 配置未进入 provider config / truncate spec：`web_assembly_config_mismatch`
8. 更新 stdout summary 计数，使默认 local case 数从 3 增为 4。

测试：

- `pytest tests/tools/web/test_smoke_web_ci.py -q`

pytest 策略：

- smoke control-flow 测试可 monkeypatch `ConfigLoader.load()` 与 `discover_service_tools()`，返回受控 config / tool bundle / callable，只验证 smoke case 编排、artifact、bucket、summary 和 exit-code 语义。
- 真实 assembly 链路由 `tests/service/test_host_assembly.py` 与 `tests/tools/web/test_web_tools_provider.py` 覆盖；`test_smoke_web_ci.py` 不承担 live assembly 的全部证明。
- pytest 不访问 live network，不依赖真实 provider credential。

验收信号：

- 默认 `python utils/smoke_web_ci.py` 会执行 local assembly config case。
- local assembly config case 不调用 `utils.diagnose_web_access` 子进程。
- assembly 断裂或 tool closure 未收到 config 会让 smoke exit code 非 0。
- external diagnostic-only 仍不覆盖 local pass / fail 语义。

Stop condition：

- 若为了 smoke 需要新增生产特殊入口或绕过 `discover_service_tools()`，停止；该 case 的价值就是证明生产式 assembly。

### Slice 5：增强 search provider diagnostic cases

目标：让 smoke 覆盖 `search_web` 的 `auto`、`tavily`、`serper`、`duckduckgo` provider 路径，成功或失败都写 artifact，并按 key/auth/quota/provider availability 分类。

文件：

- `utils/smoke_web_ci.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `dayu/tools/web/web_search_providers.py` 仅当现有错误语义无法分类时最小补充可读诊断；不得重写 provider 架构

实施步骤：

1. 新增 search diagnostic case kind，例如 `search_provider`.
2. 默认运行四个 provider 策略：`auto`、`tavily`、`serper`、`duckduckgo`。每个 case 都使用 `ConfigLoader -> discover_service_tools -> search_web ToolDefinition.callable`，而不是直接调用 `_search_with_*`。
   - 每个 provider case 使用显式 `ConfigLoader(package_config_dir=<repo>/dayu/config, workspace_config_dir=<temp config dir>)`。
   - 临时 workspace overlay 只写 `tool_discovery.json`，用 provider-specific config 启用 `web-tools`；其余配置文件从包内 `dayu/config` 读取。
   - `ConfigLoader.load()` 必须走完整链路；不得为 search smoke 降级调用 `load_tool_discovery()`。
   - `ConfigLoader.load()` 或 `discover_service_tools()` 失败属于 local assembly / infra failure，不归类为 provider diagnostic-only bucket，不得被外部 provider 容错逻辑吞掉。
3. 查询使用低风险稳定 query，例如 `"OpenAI investor relations"` 或项目内常量；不对具体搜索结果内容作 hard assertion，只记录结果数量、preferred URL host 和 provider outcome。
4. Tavily / Serper key 观测：
   - 读取 env 是否存在非空 `TAVILY_API_KEY` / `SERPER_API_KEY`，artifact 只写 `present` / `missing`，不写 secret 值。
   - key missing 时仍执行 provider case 或在调用前分类为 `provider_key_missing`。若选择仍执行，应记录 callable failure 中的缺 key 错误。
5. 分类 bucket 建议：
   - `search_provider_passed`
   - `provider_key_missing`
   - `provider_auth_failure`
   - `provider_quota_or_rate_limited`
   - `provider_network_failure`
   - `provider_response_parse_failure`
   - `provider_no_results`
   - `provider_unavailable`
   - `search_tool_execution_error`
6. 分类依据：
   - 优先使用确定性信号：`RuntimeError` 中明确 key missing 的错误、或 `requests.HTTPError.response.status_code`。
   - Tavily / Serper key missing：`provider_key_missing`；artifact 只记录 env 名和 present/missing，绝不写 secret 值。
   - HTTP 401 / 403 -> `provider_auth_failure`。
   - HTTP 429 -> `provider_quota_or_rate_limited`。
   - timeout / connection / DNS / TLS 类异常 -> `provider_network_failure`。
   - JSON parse / unexpected response shape -> `provider_response_parse_failure`。
   - callable 成功但 total 为 0 -> `provider_no_results`。
   - 关键词匹配只作为 secondary heuristic，case-insensitive，例如 unauthorized / forbidden / invalid key、quota / rate limit / too many requests。
   - 分类失败时兜底为 `provider_unavailable` 或 `search_tool_execution_error`；未分类异常不得逃逸为 hard gate。
7. 所有 search provider cases 默认进入 `diagnostic_only`，`exit_code=0`，不影响 local fetch hard gate。即使 `duckduckgo` 失败，也只说明外部搜索路径诊断失败，不代表本地 Web config assembly 失败。
8. `SmokeSummary` 新增 typed `search_cases`，元素为 `SmokeCaseResult`；`external_cases` 只保留外部 URL fetch cases。不得新增 `metadata` 弱类型字段，search provider 细节写入独立 artifact。

Smoke artifact 最小 schema：

```json
{
  "schema_version": "web-smoke-search-v1",
  "case_kind": "search_provider",
  "provider": "tavily",
  "query": "OpenAI investor relations",
  "status": "diagnostic_only",
  "bucket": "provider_key_missing",
  "api_key_env": "TAVILY_API_KEY",
  "api_key_present": false,
  "tool_name": "search_web",
  "result_total": 0,
  "preferred_result_url": "",
  "error_type": "RuntimeError",
  "error_summary": "TAVILY_API_KEY 未配置",
  "suggested_next_step": "配置 TAVILY_API_KEY 后重跑；默认不影响 local smoke gate。"
}
```

测试：

- `pytest tests/tools/web/test_smoke_web_ci.py -q`

pytest 策略：

- smoke control-flow 测试可 monkeypatch `ConfigLoader.load()` 与 `discover_service_tools()`，返回可控的 `search_web` callable，验证 provider case 编排、分类、artifact、typed `search_cases` summary 与 diagnostic-only exit code。
- 对 search callable 的网络行为使用 fake，不访问 live network，不依赖 `TAVILY_API_KEY` / `SERPER_API_KEY` 真实值。
- 真实 config 到 search provider callable 的参数传递由 Service assembly 测试与 Web provider 测试覆盖。

验收信号：

- 默认 smoke summary 能看到 auto / Tavily / Serper / DuckDuckGo 四个 search diagnostic cases。
- summary JSON 包含 typed `search_cases` 数组；`external_cases` 只包含外部 URL fetch cases。
- Tavily / Serper key missing、auth、quota / rate-limit、provider / network failure 都能落入稳定 bucket。
- 搜索成功和失败都有 artifact path。
- 外部 provider case 不改变 local fetch hard gate exit code。

Stop condition：

- 若需要真实 provider credential 才能让测试通过，停止；pytest 必须通过 monkeypatch / fixture 保持 deterministic。
- 若要把外部 provider failure 设为 hard gate，停止；这超出 R3 默认边界。

### Slice 6：README、总控与验证收口

目标：按触发规则更新文档，并执行必要验证。

文件：

- `dayu/config/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`

实施步骤：

1. 先阅读目标 README 的更新约束。
2. `dayu/config/tool_discovery.json` 变更命中 `dayu/config/README.md` 检查；当前 README 已声明 `web-tools.config` 字段，除非配置职责或目标读者说明发生变化，不修改。
3. `tests/` 变更命中 `tests/README.md` 检查；按 implementation 实际落地事实更新 Web provider / smoke 测试事实：
   - Web provider deterministic tests 覆盖 provider closure、truncate 和 browser fallback config。
   - `utils/smoke_web_ci.py` 默认 local matrix 包含 local assembly config case。
   - search provider cases 是 diagnostic-only。
4. `docs/host/issues-implementation-control.md` 在 implementation closeout 时按事实更新 `WU-TOOLS-01-F03-R3` 状态、plan artifact、验证结果、residual closeout 或剩余 owner；plan 修订阶段不修改总控。

测试：

- 见第 6 节 Required validation。

验收信号：

- README 只记录已落地事实，不提前写未实现能力。
- 总控文档更新不引入新的架构决策，只记录 work unit 状态和交付物。

Stop condition：

- 若实施发现需要修改设计真源或 Host / Engine public contract，停止并回到设计讨论；不得在 README 或总控中偷渡新架构。

## 4. Smoke summary / artifact schema 决策

保持小 schema，不引入通用 CI 平台模型。

确定扩展：

- `SmokeSummary.to_json()` 增加 typed `search_cases`，元素为 `SmokeCaseResult`，每个元素 `case_kind="search_provider"`。
- `external_cases` 只保留外部 URL fetch cases，不混入 search provider cases。
- `diagnostic_only` 汇总继续收集 external URL 与 search provider diagnostic-only items。
- `SmokeCaseResult` 不新增 `metadata` 或其它弱类型 payload 字段；provider、api key present/missing、error type、preferred URL 等 search 细节只写 case artifact。

推荐 artifact：

- local diagnostics 继续使用现有 `web-diagnostics-v1`。
- local assembly config 使用 `web-smoke-assembly-v1`。
- search provider 使用 `web-smoke-search-v1`。

不建议：

- 不把所有 artifact 强行合并为一个大 schema。
- 不把 provider request / response 原文写入 summary。
- 不写 API key 值；只写 env 名和 present/missing。
- 不要求 search result 内容稳定。

## 5. 如何避免脆弱分支与旧 schema 兼容

- 默认配置按当前 `tool_discovery.json` 新 schema 起库处理，不读取旧 `run.json`。
- Runtime 继续只读 provider config，不新增 Web-specific runtime schema。
- Service 不解析 Web 字段，只原样映射到 ToolsDiscovery provider spec。
- Web provider 继续拥有 Web config 解析权；字段校验留在 `dayu/tools/web/provider.py`。
- Smoke 的 provider 分类只用于 diagnostic artifact，不改变生产 provider fallback 算法。
- 测试使用 monkeypatch / fixture 控制外部 provider 结果，不依赖 live network。
- 对外部错误分类优先使用确定性信号：key missing 的 `RuntimeError`、`HTTPError.response.status_code` 与异常类型；有限错误文本关键词只作为 secondary heuristic。分类失败落入通用 `provider_unavailable` / `search_tool_execution_error`，不为具体供应商临时文案堆脆弱分支。
- Smoke artifact 绝不写 API key、Authorization header、provider request body 或任何可能包含 secret 的原文。

## 6. Required validation

未来 implementation 完成后必须运行：

```bash
source .venv/bin/activate
pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
python -m pyright dayu/ tests/ utils/
python utils/smoke_web_ci.py
git diff --check
```

预期：

- pytest 全部通过。
- pyright 无新增、无扩散错误。
- `python utils/smoke_web_ci.py` 默认执行 local HTML / PDF / browser / assembly config hard gate，并执行 external URL 与 search provider diagnostic-only cases；外部 provider diagnostic failure 不改变 local pass exit code。
- `git diff --check` 无 whitespace error。

## 7. Key risks / stop conditions

- Public contract 风险：若实现需要修改 Host / Engine public dataclass、request / response 字段或 package exports，停止。
- 分层风险：若 `dayu.runtime` 需要 import Service / Tools concrete provider 才能完成验证，停止。
- Smoke 假阳性风险：local assembly config case 必须实际调用 `ToolDefinition.callable`，不能只检查 config JSON。
- 外部 provider 波动风险：Tavily / Serper / DuckDuckGo 失败只能 diagnostic-only；除非后续建立 provider environment contract，否则不能 hard gate。
- Secret 泄漏风险：artifact 只记录 API key env 名与 present/missing，不记录值、header、request body 中的 secret。
- 测试稳定性风险：pytest 不做 live network；search provider live 行为只出现在 smoke，且默认 diagnostic-only。
