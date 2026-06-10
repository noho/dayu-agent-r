# Plan Review: WU-TOOLS-01-F03-R3 Web Config And Search Smoke Plan

- **Review target**: `docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`
- **Scope**: R3 plan gate adversarial review — 六个 slice 的可实施性、架构边界、测试 determinism、secret 安全、覆盖完整性
- **Design truths**: `docs/host/design.md`, `docs/engine/design.md`, `AGENTS.md`, `dayu/config/README.md`
- **Reviewed**: 2026-06-10

## Assumptions Tested

1. 默认 `tool_discovery.json` 缺少 README 已声明的 Web config 字段 — **成立**。README L188 声明了 `provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel`、`playwright_storage_state_dir`；JSON 只有后三者中的两个（`request_timeout_seconds`、`max_search_results`）加上 `allow_private_network_url`。
2. ConfigLoader 不解释 Web 语义 — **成立**。`config_loader.py` 对 `tool_discovery.providers[x].config` 做 JSON object typed view，不解析 Web 业务字段。
3. Service `_tool_discovery_specs()` 原样透传 config — **成立**。L783: `config=provider_config.config`。
4. Web provider `_parse_config()` 能解析全部七个字段 — **成立**。`provider.py` L119-151。
5. Smoke 当前走 diagnostics 子进程，不走生产 assembly 链路 — **成立**。`smoke_web_ci.py` 通过 `_run_diagnostic_command` 调 `utils.diagnose_web_access`。
6. Search provider `auto` 候选依赖环境变量 — **成立**。`_candidate_providers()` 检查 `TAVILY_API_KEY` / `SERPER_API_KEY` 环境变量。

## Findings

### F01-未修复-高-smoke 脚本 import 架构边界未定义

- **位置**: Slice 4 §实施步骤 3-4, Slice 5 §实施步骤 2
- **问题类型**: 架构边界 / 不可直接实施
- **当前写法**: plan 要求 smoke 中调用 `resolve_runtime_locations()`、`ConfigLoader(...).load()`、`discover_service_tools(config)`，从 `ServiceDiscoveredTools.tool_bundle` 取 `fetch_web_page` / `search_web` 的 `ToolDefinition.callable`。
- **反例/失败场景**: `utils/smoke_web_ci.py` 当前只 import `dayu.contracts.json_value` 和 `dayu.runtime.log`。新增 `dayu.runtime.config_loader`、`dayu.runtime.location`、`dayu.service.host_assembly` import 后，`utils/` 脚本会依赖 Service 层。`AGENTS.md` 约定"分析辅助代码仅放在 `utils/`"，但未定义 `utils/` 能否反向 import Service。同时 `discover_service_tools()` 会触发 `ToolsDiscovery` 真实 import 并执行 `dayu.tools.web:discover_tools`，smoke 执行环境必须有完整依赖链。
- **为什么有问题**: 这是 smoke 脚本从"诊断辅助"升级为"生产装配验证"的架构跃迁。plan 没有说明：(a) `utils/` → Service 的 import 是否被项目约束允许；(b) smoke 如何在没有完整 Service 依赖的 CI 环境中运行；(c) 是否需要把 assembly smoke 逻辑抽取到 Service 可调用的 helper。
- **直接证据**: `smoke_web_ci.py` 当前 import 列表；`AGENTS.md` "分析辅助代码仅放在 `utils/`"；`discover_service_tools()` L271 会触发 `ToolsDiscovery().discover()`。
- **影响**: 实施 Agent 不知道该把 assembly 逻辑放在哪里，可能直接在 smoke 脚本里硬 import Service，破坏分层。
- **建议改法和验证点**: plan 应明确：(a) smoke 允许 import `dayu.service.host_assembly.discover_service_tools` 和 `dayu.runtime.config_loader.ConfigLoader`；或 (b) 在 `dayu.service` 或 `dayu.runtime` 中提供一个 smoke 可调用的 assembly entry point；或 (c) smoke 继续走子进程但 diagnostics 脚本内部调用 assembly。选择 (a) 最简单但需确认 `utils/` 约束允许。验证：smoke 脚本能 `python -c "from utils.smoke_web_ci import main"` 不报 import error。
- **修复风险（低/中/高）**: 中
- **严重程度（高）**

### F02-未修复-高-Slice 4/5 pytest determinism 策略缺失

- **位置**: Slice 4 §测试, Slice 5 §测试
- **问题类型**: 测试缺口
- **当前写法**: Slice 4/5 的测试只写 `pytest tests/tools/web/test_smoke_web_ci.py -q`。plan 的 Stop condition 说"pytest 必须通过 monkeypatch / fixture 保持 deterministic"，但没给具体策略。
- **反例/失败场景**: Slice 4 新增 `local_assembly_config` case 走 `ConfigLoader -> discover_service_tools -> ToolDefinition.callable`。现有 `test_default_run_executes_local_html_pdf_and_browser_cases` 通过 monkeypatch `_run_diagnostic_command` 和 `_running_local_fixture_server` 实现 determinism。但 `local_assembly_config` 不走子进程，直接调用生产 callable，无法用同样方式 monkeypatch。实施 Agent 可能：(a) 放弃 monkeypatch 直接跑真 HTTP，pytest 变 flaky；(b) monkeypatch `discover_service_tools` 本身，但这样测不到真实装配；(c) 不写这个 case 的 pytest，只靠 smoke 验证。
- **为什么有问题**: 项目约束要求"测试必须 deterministic，不依赖真实网络和真实 credential"。如果 Slice 4/5 的 pytest 不能 deterministic，要么违反约束，要么测试形同虚设。
- **直接证据**: `test_smoke_web_ci.py` 当前 monkeypatch 策略；`AGENTS.md` 测试约束。
- **影响**: 实施 Agent 可能写出 flaky 测试或跳过关键 case 的 pytest 覆盖。
- **建议改法和验证点**: plan 应明确 Slice 4/5 pytest 的 monkeypatch 策略。建议：(a) monkeypatch `ConfigLoader.load()` 返回预设 `RuntimeConfig`；(b) monkeypatch `discover_service_tools()` 返回预设 `ServiceDiscoveredTools`（含可控 callable）；(c) 对 callable 本身不做 monkeypatch，让它真实调用 local fixture server。这样既测到了 config → spec → callable 的透传，又不依赖网络。验证：`pytest tests/tools/web/test_smoke_web_ci.py -q` 在无网络环境通过。
- **修复风险（低/中/高）**: 中
- **严重程度（高）**

### F03-未修复-中-SmokeSummary schema 设计未收敛

- **位置**: §4 Smoke summary / artifact schema 建议
- **问题类型**: 契约缺失
- **当前写法**: plan 提出两种方案：(a) `SmokeSummary.to_json()` 增加 `search_cases`；(b) 暂放入 `external_cases` 但用 `case_kind="search_provider"` 区分。同时说 `SmokeCaseResult` 可新增可选 `metadata`，但"如果这会引入弱类型扩散，则不要改"。
- **反例/失败场景**: 实施 Agent 需要在 Slice 4/5 同时改变 `SmokeSummary` 结构和 `SmokeCaseResult` schema。两种方案有不同影响：(a) 新增 `search_cases` 需改 `SmokeSummary` dataclass、`to_json()`、`_summary_from_cases()`、`_summary_markdown()`、`_print_summary_ui()` 和所有断言 `SMOKE LOCAL_CASES` 的测试；(b) 放入 `external_cases` 会混淆 URL fetch 和 search 两类语义不同的 case。
- **为什么有问题**: plan 把 schema 决策留给实施 Agent，但这是一个影响 summary contract 稳定性的设计选择。
- **直接证据**: `SmokeSummary` dataclass L305-335；`_summary_from_cases()` L1681-1734；`_print_summary_ui()` L2395-2417。
- **影响**: 实施 Agent 可能做出与 plan 意图不符的 schema 选择，导致 summary 格式不稳定或语义混淆。
- **建议改法和验证点**: plan 应明确选择方案 (a) 新增 `search_cases: tuple[SmokeCaseResult, ...]`，并说明 `SmokeCaseResult` 不加 `metadata` 字段，search provider 诊断细节只写 case artifact。验证：summary JSON 包含 `search_cases` 数组，每个元素有 `case_kind="search_provider"`。
- **修复风险（低/中/高）**: 低
- **严重程度（中）**

### F04-未修复-中-Slice 4 不断言 config 字段进入 callable 闭包

- **位置**: Slice 4 §实施步骤 4-5
- **问题类型**: 测试缺口
- **当前写法**: Slice 4 验收信号只说"assembly 断裂或 tool closure 未收到 config 会让 smoke exit code 非 0"。实施步骤 4 说"通过 callable 抓取 local HTML fixture"。artifact schema 包含 `provider_config` 和 `truncate_max_chars`。
- **反例/失败场景**: callable 成功抓取 fixture 只证明 fetch pipeline 工作，不证明 config 字段正确进入闭包。如果 assembly 丢失了 `fetch_truncate_chars` 或 `playwright_channel`，callable 会使用 `WebToolsConfig` 默认值，fetch 仍成功，但 config 透传实际断裂。
- **为什么有问题**: Slice 3 已有闭包单元测试，但 Slice 4 的 production-style assembly 测试应独立证明端到端 config 透传，不依赖 Slice 3 的 monkeypatch 测试。
- **直接证据**: Slice 4 artifact schema 包含 `provider_config` 和 `truncate_max_chars` 但没有断言步骤。
- **影响**: smoke 可能通过但 config 透传实际断裂，需要到生产环境才发现。
- **建议改法和验证点**: Slice 4 应增加断言：artifact 的 `provider_config` 必须包含 `fetch_truncate_chars`、`playwright_channel` 等字段且值等于 overlay config 设定值；`truncate_max_chars` 必须等于 overlay 的 `fetch_truncate_chars`。验证：artifact JSON 的 `provider_config.fetch_truncate_chars == 12345`。
- **修复风险（低/中/高）**: 低
- **严重程度（中）**

### F05-未修复-中-Slice 5 search provider 通过生产 callable 调用但 smoke 脚本无法 deterministic

- **位置**: Slice 5 §实施步骤 2-3
- **问题类型**: 测试缺口 / 不可直接实施
- **当前写法**: plan 要求每个 search provider case 使用 `ConfigLoader -> discover_service_tools -> search_web ToolDefinition.callable`，查询使用"低风险稳定 query"。Stop condition 说"pytest 必须通过 monkeypatch / fixture 保持 deterministic"。
- **反例/失败场景**: `search_web` callable 内部调用 `search_public_web()`，后者对 DuckDuckGo 发真实 HTTP 请求到 `https://duckduckgo.com/html/`。即使在 smoke（非 pytest）中，DuckDuckGo 也可能因 rate limit 或 HTML 结构变化返回空结果或异常。plan 说这是 diagnostic-only，但 smoke output 仍会因外部因素波动。对 pytest，如果走 callable 链路，需要 monkeypatch `requests.get` 或 `search_public_web`，但 plan 没说明怎么 monkeypatch。
- **为什么有问题**: Slice 5 的价值是证明 search provider 能通过生产装配链路被调用。但 callable 链路深达 `requests.post/get`，monkeypatch 粒度不明确。
- **直接证据**: `web_search_providers.py` L530 `requests.post("https://api.tavily.com/search", ...)`；L669 `requests.get("https://duckduckgo.com/html/", ...)`。
- **影响**: 实施 Agent 可能写出依赖真实网络的 smoke/pytest，或过度 monkeypatch 导致测试失去意义。
- **建议改法和验证点**: plan 应明确：(a) smoke 中 search provider cases 真实调用网络，结果 diagnostic-only，输出波动可接受；(b) pytest 中 monkeypatch `web_search_providers.search_public_web` 为 fake，只验证 config → callable → search_public_web 参数传递链路，不验证真实搜索结果。验证：pytest 在无网络环境通过；smoke 在无 API key 环境下 `provider_key_missing` bucket 正确。
- **修复风险（低/中/高）**: 中
- **严重程度（中）**

### F06-未修复-低-README 更新条件过于保守

- **位置**: Slice 1 §实施步骤 4, Slice 6 §实施步骤 2
- **问题类型**: 最佳实践偏离
- **当前写法**: "若 README 已准确声明字段且无需补充默认值表，则不修改 README；若实现选择补默认值说明，必须只更新 `dayu/config/README.md` 的 `tool_discovery.json` 职责范围。"
- **反例/失败场景**: README L188 已经声明了全部七个字段及其语义。plan 给实施 Agent 留了"若实现选择补默认值说明"的口子，可能导致不必要地扩展 README。
- **为什么有问题**: README 已经准确且完整。plan 应直接确认不需要改 README，而不是留给实施 Agent 判断。
- **直接证据**: `dayu/config/README.md` L188 完整声明了 `web-tools` config 的七个字段。
- **影响**: 低。最坏情况是实施 Agent 多写了几行 README。
- **建议改法和验证点**: Slice 1 直接写"README L188 已准确声明全部字段，本 slice 不修改 README"。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

### F07-未修复-低-Slice 5 错误分类关键词可能随 provider 版本变化

- **位置**: Slice 5 §实施步骤 6
- **问题类型**: 脆弱错误分类
- **当前写法**: "HTTP 401 / 403 或错误文本含 unauthorized / forbidden / invalid key -> `provider_auth_failure`" 等基于关键词匹配的分类。
- **反例/失败场景**: Tavily/Serper 的错误消息格式可能随 API 版本变化。DuckDuckGo HTML 搜索的异常是 `requests.HTTPError`，其 `str(exc)` 格式取决于 `response.text`，可能不含预期关键词。
- **为什么有问题**: 关键词匹配是 fragile 的。如果分类失败，错误落入 `provider_unavailable` 或 `search_tool_execution_error`，不影响 diagnostic-only 语义，但会降低诊断精度。
- **直接证据**: `web_search_providers.py` L516 `raise RuntimeError("TAVILY_API_KEY 未配置")` — 这个可以精确匹配；但 L539 `response.raise_for_status()` 抛出的 `HTTPError` 的 message 格式不确定。
- **影响**: 低。分类失败不影响 smoke gate，只降低诊断 artifact 的 bucket 精度。
- **建议改法和验证点**: plan 应说明：分类逻辑优先匹配确定性信号（`RuntimeError` message、`HTTPError.response.status_code`），关键词匹配只作为 secondary heuristic，分类失败 fallback 到 `provider_unavailable`。验证：Tavily key missing 时 bucket 一定是 `provider_key_missing`（基于 `RuntimeError` message 精确匹配）。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

### F08-未修复-低-Slice 3 Playwright fallback 测试未覆盖空 storage_state_dir 默认路径

- **位置**: Slice 3 §实施步骤 3
- **问题类型**: 测试缺口
- **当前写法**: "用临时 storage state dir 和 host 对应 JSON 文件；断言 callable 传入配置的 channel，并按 URL host 解析到 `<host>.json`。"
- **反例/失败场景**: 默认 `playwright_storage_state_dir: ""` 表示不使用 storage state。plan 的测试只覆盖非空 dir 的路径解析，不覆盖空 dir 时 Playwright fallback 不注入 storage state 的行为。
- **为什么有问题**: 默认配置是空 dir，如果空 dir 处理有 bug（例如传空字符串给 Playwright 导致路径错误），测试不会发现。
- **直接证据**: `WebToolsConfig.playwright_storage_state_dir: str = ""` L64；plan Slice 1 设定默认值为 `""`。
- **影响**: 低。空 dir 是默认路径，但 Playwright fallback 本身是低频路径。
- **建议改法和验证点**: Slice 3 应增加一个测试用例：`playwright_storage_state_dir=""` 时，Playwright fallback 不收到 storage state path 参数。验证：monkeypatch `_fetch_and_convert_with_playwright` 记录的 `playwright_storage_state_path` 为 `None` 或不传入。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**

## Open Questions

1. **`utils/` → Service import 是否被项目约束允许？** AGENTS.md 说"分析辅助代码仅放在 `utils/`"，但 `discover_service_tools()` 位于 `dayu.service.host_assembly`。如果 `utils/` 不允许 import Service，Slice 4/5 需要改用其他方案（如子进程调用或在 Service 层提供 smoke entry point）。**建议**: 在 plan 中显式确认 `utils/smoke_web_ci.py` 可以 import `dayu.service.host_assembly.discover_service_tools`。
2. **DuckDuckGo HTML 搜索在 CI 环境中的可达性？** 如果 CI 环境有网络限制，DuckDuckGo search diagnostic case 会始终失败。plan 应说明这是可接受的 diagnostic-only 行为。**建议**: 在 plan 中注明 DuckDuckGo 搜索失败只写 diagnostic artifact，不影响任何 gate。
3. **Slice 4 assembly smoke 是否需要 `resolve_runtime_locations()`？** 如果只用 `ConfigLoader(package_config_dir=..., workspace_config_dir=...)` 直接指定路径，可以避免 location 解析的复杂性。plan 应明确是否需要 location resolution。**建议**: Slice 4 可以直接构造 `ConfigLoader` 路径，不依赖 `resolve_runtime_locations()`。

## Residual Risks

1. **DuckDuckGo HTML 结构变化**: 搜索结果解析依赖 `div.result` / `a.result__a` CSS 选择器。DuckDuckGo 改版会导致所有 DuckDuckGo provider 路径静默返回空结果。追踪方式：smoke diagnostic artifact 的 `provider_no_results` bucket。
2. **Tavily/Serper API 变更**: API endpoint 或认证方式变化会导致 provider 路径全面失败。追踪方式：smoke `provider_auth_failure` / `provider_unavailable` bucket。
3. **Playwright 环境缺失**: CI 环境可能没有 Playwright browser binary。追踪方式：smoke `local_browser` case 的 `browser_backend_not_observed` bucket（已有机制）。

## Verdict: pass-with-fixes

plan 的动机成立、分层边界判断正确、真 blocker / diagnostic-only 分类合理。**允许进入 implementation**，但需先解决以下 blocking issues：

1. **F01** (高): 明确 smoke 脚本 import 架构边界 — `utils/smoke_web_ci.py` 是否可以 import Service 层。
2. **F02** (高): 明确 Slice 4/5 pytest 的 monkeypatch 策略，确保 deterministic。
3. **F03** (中): 收敛 SmokeSummary schema 设计，选择方案 (a) 新增 `search_cases`。

F04-F08 为 non-blocking 建议，可在 implementation 中一并处理。
