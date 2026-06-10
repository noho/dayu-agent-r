# WU-TOOLS-01-F03-R3 Plan Review

**审查类型**: plan gate 严格审查
**审查日期**: 2026-06-10
**审查对象**: `docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`
**设计真源**: `docs/host/design.md`、`docs/engine/design.md`
**总控文档**: `docs/host/issues-implementation-control.md`
**参考约束**: `AGENTS.md`（项目 CLAUDE.md）

## 审查范围与方法

本审查只审查 plan gate 的计划本身，不修改生产代码、测试或总控文档。审查基于以下直接证据：

- 逐一核对了 plan 中每个 Slice 的断言与当前代码实际状态
- 检查了分层边界 (Runtime → Service → Provider) 的现有关卡
- 验证了现有测试覆盖与 plan 提出的测试增量是否重叠
- 挑战了 smoke design 的 hard gate / diagnostic-only 分类
- 检查了 secret 泄漏、弱类型扩散、脆弱分支的风险

## Findings

### F1 (HIGH) — Slice 4/5 的生产式 assembly 路径需要 ConfigLoader.load() 加载全部五类配置，plan 未明确 workspace overlay 的最小文件集

**证据**:

- `ConfigLoader.load()` (config_loader.py:639) 在内部调用 `load_models()`、`load_execution_profiles()`、`load_host_runtime()`、`load_runtime_lanes()`、`load_tool_discovery()` 五个方法，并且执行跨文件引用校验 `_validate_execution_model_references` 和 `_validate_host_runtime_lane_references`
- 包内默认 config 目录 (`dayu/config/`) 包含全部五类配置文件，其中 `models.json` 的模型引用必须与 `execution_profiles.json` 的 profile 引用一致
- 若 workspace overlay 仅提供 `tool_discovery.json` 且覆盖了一个新的 `provider_id`（如启用 `web-tools` 的 overlay），其余四类文件从包内默认读取，不会触发缺失文件错误
- 但若 workspace overlay 路径缺失或损坏，`ConfigLoader.load()` 会 fail-fast，导致 smoke 的 assembly config case 在 CI 环境中不可靠

**影响**: Slice 4 和 Slice 5 都依赖 `ConfigLoader.load()` 走完整 assembly 路径。如果 smoke 运行环境中包内默认 config 目录不可访问（例如通过符号链接或非标准安装），assembly case 会失败。plan 当前的 stop condition 只覆盖了"绕过 discover_service_tools()"的情况，没有覆盖 ConfigLoader 初始化失败的情况。

**建议**: 
1. Slice 4/5 的实现必须显式传入 `package_config_dir` 到 `ConfigLoader()`，不依赖隐式的 `_CONFIG_ROOT` 路径推导
2. 在 stop condition 中增加：若 `ConfigLoader` 因文件缺失或跨文件引用校验失败而无法初始化，该 case 应 skip（写入 diagnostic artifact），而不是让 smoke exit code 非 0
3. 或者：将 Slice 4 的 assembly case 降级为只调用 `ConfigLoader.load_tool_discovery()` + `_tool_discovery_specs()` + `ToolsDiscovery().discover()` 的部分 assembly 链路，同样能证明 config → provider spec → ToolDefinition 的闭包，且不依赖 models/execution_profiles 等无关配置

### F2 (MEDIUM) — Slice 3 的 Playwright fallback 参数测试策略有过度复杂的风险

**证据**:

- plan 描述："monkeypatch requests 主路径使其升级到 browser fallback；monkeypatch `_fetch_and_convert_with_playwright` 记录 `playwright_channel` 与 `playwright_storage_state_path`"
- 当前 `fetch_web_page` 的 browser escalation 逻辑分散在多处：`_should_escalate_stage_result_to_browser` (warmup/probe 之后)、`requests.Timeout` except 分支、`requests.RequestException` 的 timeout-like/SSL-like 分支、bot challenge 检测分支、`_should_escalate_http_status_to_browser`、`RuntimeError` 的多层检测（conversion failure、pipeline failure、challenge context）——总共约 10 处 browser fallback 触发点
- monkeypatch "requests 主路径使其升级"意味着需要精确理解哪一处 escalation 会被触发，patch 错位置会导致测试实际未覆盖目标路径
- 已有测试 `test_fetch_playwright_cancel_projects_to_cancelled_failure` 通过 monkeypatch `_warmup_domain` + `_should_escalate_stage_result_to_browser` 来触达 `_try_playwright_fallback`，证明了这种模式的可行性

**影响**: 实现者可能花费大量时间调试 monkeypatch 组合，而非直接验证目标行为。测试可能因 patch 了错误的 escalation 条件而给出假阴性或假阳性。

**建议**: 直接将 `_try_playwright_fallback` 作为 monkeypatch 目标，在 fake 中记录传入的 `playwright_channel` 和 `playwright_storage_state_path`，然后通过 monkeypatch `_try_playwright_fallback` 返回成功结果。这样不需要理解 escalation 逻辑就能验证参数闭包。已有的 `test_fetch_playwright_cancel_projects_to_cancelled_failure` 测试使用了类似的模式（monkeypatch `_fetch_and_convert_with_playwright`），可参照。

### F3 (MEDIUM) — Slice 5 的错误分类使用 HTTP 状态码 + 错误文本关键词，在 provider API 变更时可能产生脆弱分支

**证据**:

- plan 的分类规则："HTTP 401 / 403 或错误文本含 unauthorized / forbidden / invalid key -> `provider_auth_failure`"；"HTTP 429 或错误文本含 quota / rate limit / too many requests -> `provider_quota_or_rate_limited`"
- Tavily API 和 Serper API 的错误响应格式未在代码中契约化——当前 `web_search_providers.py` 的 provider 函数直接 `response.raise_for_status()` 然后期望 JSON body，没有对 error response body 做结构化解析
- DuckDuckGo HTML 搜索的失败模式（HTML 结构变化、反爬虫页面）更不可能通过 HTTP 状态码稳定分类

**影响**: 分类 bucket 可能在 provider API 变更后产生分类漂移，但不影响 local hard gate（因为 diagnostic-only）。风险可控但需要文档记录。

**建议**: 
1. 分类失败时统一落入 `provider_unavailable`，plan 已提及此策略——实现时必须严格遵守，不能让未分类异常逃逸
2. 对于 Tavily/Serper 的 HTTP 错误，优先用 `response.status_code` 分类；关键词匹配仅作为补充，且必须 case-insensitive
3. 在 smoke artifact 的 `error_summary` 中保留原始异常类型名（如 `requests.HTTPError`），方便后续诊断

### F4 (MEDIUM) — `SmokeSummary` 的 frozen dataclass 扩展方式存在弱类型扩散风险

**证据**:

- plan 第 4 节建议 "`SmokeSummary.to_json()` 增加 `search_cases`" 或 "暂放入 `external_cases`，但必须用 `case_kind="search_provider"` 区分"
- 当前 `SmokeSummary` 是 frozen dataclass（smoke_web_ci.py:305），添加 `search_cases` 字段需要修改类定义、`_summary_from_cases()` 构造、`to_json()` 序列化、`_summary_markdown()` 渲染
- plan 提到 "`SmokeCaseResult` 可新增可选 `metadata` 只在 summary 中保留 provider / api_key_present 等简短字段；如果这会引入弱类型扩散，则不要改 dataclass"
- `metadata` 作为 `Mapping[str, JsonValue]` 实际上就是弱类型袋，违反了 AGENTS.md 的"禁止把显式参数放进 extra payload"精神

**影响**: 若选择新增 `metadata: Mapping[str, JsonValue] | None` 字段，会引入一个逃逸类型检查的口袋字段。若选择新增 `search_cases` 字段，则变更面更广但类型安全。

**建议**: 优先选择 plan 中的备选方案——search provider cases 放在 `external_cases` 中，用 `case_kind="search_provider"` 区分；`SmokeSummary` 的 frozen dataclass 不新增字段。这样既满足"search cases 与 URL external cases 不混淆"的需求（通过 `case_kind` 区分），又不引入弱类型扩散。

### F5 (LOW) — Slice 1 的 `playwright_storage_state_dir: ""` 空字符串语义需要明确注释

**证据**:

- plan 提议 `"playwright_storage_state_dir": ""`
- `provider.py` 的 `_text_default()` 返回 `value.strip()`，`""` → `""`
- `web_tools.py` 的 `_resolve_playwright_storage_state_path()` 在第一行检查 `if not playwright_storage_state_dir or not playwright_storage_state_dir.strip()` → 返回 `""`
- `web_playwright_backend.py` 的 `_resolve_playwright_storage_state_path()` 也需要接收空字符串并正确返回空字符串

**影响**: 空字符串 `""` 的正确语义是"不启用 storage state"，但 JSON 中 `""` 和 `null` 的语义差异可能让后续维护者困惑。当前代码对空字符串和 None 都做了防御处理，但 JSON 配置中无法表达 `null`（ConfigLoader 的 `_optional_mapping_field` 在字段值为 `null` 时返回 `{}`，不影响）。

**建议**: 在 `tool_discovery.json` 中为该字段添加注释，或在 plan 的 Slice 1 实施步骤中说明 `""` 的语义。不影响 plan 通过。

### F6 (LOW) — Slice 2 的 web-specific 测试与已有通用测试存在部分重叠

**证据**:

- 已有测试 `test_tool_discovery_provider_config_survives_loader_and_service_mapping` (test_host_assembly.py:817) 已经用 doc-tools 证明了 `ConfigLoader → _tool_discovery_specs → ToolsDiscoveryProviderSpec.config` 的原样保留
- `_tool_discovery_specs()` 函数对 doc-tools 和 web-tools 使用完全相同的映射路径——`provider_config.config` 直接赋值给 `ToolsDiscoveryProviderSpec.config`
- 新增 web-specific 测试的价值在于提供 domain-specific 的可读证据，但技术上不是必需的

**影响**: 低。web-specific 测试增加了可读性和针对性，不违反任何约束。

**建议**: 保留 plan 中的 web-specific 测试，但明确其定位是"可读证据"而非"发现未知 bug"。如果实现成本过高，可以降级为对已有通用测试的扩展（增加 web-specific assert）。

### F7 (INFO) — Slice 4 的 assembly config case 与现有 smoke 架构的 subprocess 模式不一致，但 plan 已正确识别

**证据**:

- 当前 smoke 的所有 local/external cases 都通过 subprocess 调用 `utils.diagnose_web_access` 完成（smoke_web_ci.py:2003-2093）
- Slice 4 的 assembly case 改为 in-process 调用 `ConfigLoader → discover_service_tools → ToolDefinition.callable`
- plan 的 stop condition (line 206): "若为了 smoke 需要新增生产特殊入口或绕过 discover_service_tools()，停止"

**影响**: 信息性。这是 plan 的有意设计选择——assembly case 的价值正是证明"不经过 diagnostics 子进程"的生产式装配。plan 已正确识别这个差异并设置了 stop condition。

**建议**: 实现时注意清理——assembly case 的 artifact 格式应与现有 diagnostics artifact 保持 schema 独立（使用 `web-smoke-assembly-v1` 而非 `web-diagnostics-v1`），不试图兼容 `_classify_loaded_artifact()` 的现有分类逻辑。

## Open Questions

1. **Q1**: Slice 4 的 assembly config case 是否需要通过 `resolve_runtime_locations()` 解析 workspace 路径？如果 smoke 在非标准项目结构中运行（如 `pip install -e .`），`resolve_runtime_locations()` 的行为需要验证。

2. **Q2**: Slice 5 的 search diagnostic cases 默认使用什么 provider config？如果默认 `provider: "auto"` 且环境没有 Tavily/Serper key，auto 会 fallback 到 DuckDuckGo。四个独立的 provider case（`tavily`/`serper`/`duckduckgo`/`auto`）是否需要各自独立调用 `discover_service_tools()` 并传入不同的 provider 参数，还是复用同一次 discovery？

3. **Q3**: 如果 DuckDuckGo HTML 搜索结果页面临时改版（HTML 结构变化），导致 `_search_with_duckduckgo` 返回空结果而非抛异常，分类会落入 `provider_no_results` 而非 `provider_response_parse_failure`。这是否符合预期？DDG HTML 爬取本质上是脆弱的，plan 是否有考虑将这个 case 的稳定性预期写入 artifact？

## Verdict: **PASS-WITH-FIXES**

**允许进入 implementation gate，但必须在 Slice 1 开始前解决以下问题：**

1. **F1 (HIGH) 必须解决**: 明确 Slice 4/5 中 `ConfigLoader.load()` 的 workspace overlay 策略。建议方案：assembly config case 显式传入 `package_config_dir`，并在 `ConfigLoader` 初始化失败时 skip（写 diagnostic artifact）而非 fail。或者将 assembly case 降级为 `load_tool_discovery()` 部分链路，仍能证明 config → spec → ToolDefinition 闭包。

2. **F4 (MEDIUM) 必须解决**: 确认 search provider cases 使用 `external_cases` + `case_kind="search_provider"` 方案，不在 `SmokeSummary` frozen dataclass 上新增 `search_cases` 字段或 `metadata` 弱类型字段。

**以下问题建议在实现过程中关注，但不阻塞进入 implementation：**

3. **F2 (MEDIUM)**: Slice 3 的 Playwright fallback 测试建议直接 monkeypatch `_try_playwright_fallback`，避免通过多层 escalation 条件触达。

4. **F3 (MEDIUM)**: Slice 5 的错误分类优先用 HTTP 状态码，关键词匹配仅作补充。

5. **F6 (LOW)**: Slice 2 的 web-specific 测试可以与已有通用测试合并，降低重复。

## 审查结论摘要

Plan 对问题根因的识别准确（证据链完整，从 config 缺口到 smoke 缺口逐层追溯），分层边界的把握正确（Runtime 不解析 Web 字段、Service 原样映射、Provider 拥有解析权），hard gate / diagnostic-only 的区分合理。主要风险集中在 Slice 4/5 的 production assembly 路径对 ConfigLoader 全量加载的隐式依赖上，以及 SmokeSummary 扩展方式的类型安全选择上。上述两处修正后即可进入 implementation。
