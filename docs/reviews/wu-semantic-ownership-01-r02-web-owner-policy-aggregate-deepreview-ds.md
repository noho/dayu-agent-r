# WU-SEMANTIC-OWNERSHIP-01 / R02 Aggregate Deep Review (AgentDS)

## 1. 身份、Scope 与执行树

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；本文是内部 remediation `R02` 的 aggregate deepreview（AgentDS 路），不是新 WU。
- accepted plan：`2d42ceb6`（`gateflow: accept superseding R02 web owner policy plan`）。
- accepted slices：S1=`c7b01d82`、S2=`d8d6e9d9`、S3=`7e679796`。
- 当前 control gate：`R02 dual aggregate deepreview`（`docs/host/issues-implementation-control.md:158`）。
- 执行 HEAD：`4240ee75`。
- 审查范围：`2d42ceb6..7e679796` 的完整 product/config/utils/tests/README diff 及当前 aggregate artifacts。
- 固定输出路径：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-ds.md`。

本 review 不修改产品/测试/README/control/既有 artifacts，不 commit/push，不进入 completion/R03。

## 2. 必读真源与审查方法

本轮完整读取：

1. 根 `AGENTS.md`、`CLAUDE.md`；
2. accepted R02 plan（`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`）；
3. S1/S2/S3 各自的 implementation artifact、Controller validation、final code re-review Controller adjudication；
4. R02 aggregate validation artifact（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md`）；
5. R02 aggregate Controller validation（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-controller-validation.md`）；
6. `docs/host/issues-implementation-control.md` 当前 R02 gate 行；
7. controller discussion Topic 2（overdesign remediation 最高真源）。

审查方法：四路并行 subagent 深挖 + 主 reviewer 独立验证：

| 维度 | 覆盖方式 | 覆盖文件 |
|---|---|---|
| S1-S3 所有权链完整性 | subagent Explore（81 tool calls） | provider.py, web_resource_budget.py, web_tools.py, web_http_session.py, web_playwright_backend.py, web_diagnostics.py, web_egress_policy.py, web_search_providers.py, web_fetch_orchestrator.py |
| 安全组合 fail-close | subagent Explore（33 tool calls） | web_egress_policy.py, web_http_session.py, web_playwright_backend.py, web_fetch_orchestrator.py, web_diagnostics.py, web_challenge_detection.py |
| web_tools/playwright 覆盖缺口 | subagent Explore + 主 reviewer 直接 coverage | web_tools.py, web_playwright_backend.py，coverage JSON + --show-missing |
| plan/deferred scope/validation harness | subagent Explore（26 tool calls） | accepted plan §4/§6/§11/§14，控制文档，全部 diff 文件 |
| 主 reviewer 直接验证 | provider parser 行为、budget 默认值、旧类名残留、credential lifecycle 残留、deferred scope 泄漏、pyright、git diff --check | 全部 18 changed paths |

## 3. Findings

### R02-AGG-DS-F01 — web_playwright_backend.py `_get_playwright_browser` 双检锁浏览器单例零直接测试覆盖

- **入口/函数**: `dayu/tools/web/web_playwright_backend.py:_get_playwright_browser`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1048-1071`
- **输入场景**: 任何需要真实浏览器启动的 Playwright 路径（非 fake-injected worker）
- **实际分支**: 所有测试通过注入 fake `get_playwright_browser` callable 绕过真实实现；24 行双检锁逻辑（外层 null check、锁获取+内层 null check、旧 browser teardown、Playwright import、sync_playwright 启动、channel-based launch options、anti-detection args、`chromium.launch`、全局状态赋值、异常处理）全部 0% 覆盖
- **预期行为**: 双检锁应保证线程安全：首次调用创建 browser、后续调用返回缓存实例、channel 变更时 teardown 旧实例并重建
- **实际行为**: 这些行为从未被任何测试直接验证
- **直接证据**:
  1. coverage `--show-missing`：lines 1048-1071 全部在 missing 列表中
  2. `rg -n "get_playwright_browser" tests/` 确认所有测试只注入 fake，不调用真实函数
  3. `rg -n "_get_playwright_browser" dayu/tools/web/web_playwright_backend.py` 确认这是唯一实现
- **影响**: 浏览器生命周期中的线程安全缺陷（如竞态条件导致重复 `chromium.launch`、teardown 不完整导致资源泄漏、channel 变更后旧 browser 未正确关闭）在生产中可能触发但无法通过测试检测。浏览器单例是 R02 "browser capability owner" 的核心组件。
- **建议改法和验证点**: 补充直接测试 `_get_playwright_browser`：(a) 首次调用创建 browser，(b) 第二次调用返回缓存实例，(c) channel 变更触发 teardown+重建，(d) 异常时正确清理。由于依赖真实 Chromium，可考虑在 smoke 测试中添加 browser lifecycle 验证 case
- **修复风险（中）**: 需真实 Playwright 环境，不适合纯 CI unit test
- **严重程度（中）**:

### R02-AGG-DS-F02 — web_tools.py URL 归一化安全拒绝路径未覆盖

- **入口/函数**: `dayu/tools/web/web_tools.py:_normalize_url_for_http`
- **文件(行号)**: `dayu/tools/web/web_tools.py:1091, 1097, 1103, 1105, 1111`
- **输入场景**: (a) 无 scheme 或无 netloc 的 URL（如 `""`、`"not-a-url"`）；(b) 带嵌入式 credential 的 URL（如 `http://user:pass@example.com`）
- **实际分支**: 当前测试只覆盖合法 URL 路径；`ValueError` 拒绝路径（L1091 scheme/netloc 缺失、L1097 hostname 为空）和 credential 剥离路径（L1103/L1105/L1111）全部未覆盖
- **预期行为**: URL 归一化是第一道防线——在 egress policy、private network blocking 之前执行。非法 URL 应在此处被拒绝，不进入下游安全校验
- **实际行为**: 拒绝路径从未被测试触发
- **直接证据**: coverage `--show-missing`：lines 1091, 1097, 1103, 1105, 1111 在 missing 列表中
- **影响**: URL 归一化验证缺口为间接风险——当前输入路径（LLM tool call → URL 参数）通常在到达此处前已通过其他校验。但如果未来出现新的调用路径绕过上游校验，此处是最后防线
- **建议改法和验证点**: 补充参数化测试：空字符串、无 scheme、无 hostname、带 userinfo 的 URL
- **修复风险（低）**: 纯 unit test，无需外部依赖
- **严重程度（低）**:

### R02-AGG-DS-F03 — web_playwright_backend.py text budget 强制执行路径未覆盖

- **入口/函数**: `dayu/tools/web/web_playwright_backend.py:_materialize_bounded_page_projection`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1357`
- **输入场景**: 浏览器页面 DOM 在预算内但 text/Markdown 超出 `BrowserResourceBudget.text_chars` 上限
- **实际分支**: DOM budget exceeded 路径（`_BROWSER_DOM_TOO_LARGE_REASON`）有测试覆盖；text budget exceeded 路径（`_BROWSER_TEXT_TOO_LARGE_REASON`）从未触发
- **预期行为**: 当 text/Markdown 长度超过 `text_chars` 上限时，应 raise `_BrowserResourceBudgetExceeded`
- **实际行为**: 该路径从未被测试验证
- **直接证据**: coverage `--show-missing`：line 1357 在 missing 列表中；`test_playwright_budget_rechecks_dynamic_full_projection_lengths` 只覆盖 DOM 路径
- **影响**: text budget 是 R02 分 owner budget 的核心契约之一；虽然 `_BrowserResourceBudgetExceeded` 类本身被其他测试覆盖，但 text 维度的触发条件未经验证
- **建议改法和验证点**: 构造 DOM 在预算内但 text 超限的 synthetic page，验证 `_BROWSER_TEXT_TOO_LARGE_REASON` 被正确 raise
- **修复风险（低）**: 可用 synthetic mock page
- **严重程度（低）**:

### R02-AGG-DS-F04 — web_playwright_backend.py 路由安全处理器 2/3 分支未覆盖

- **入口/函数**: `dayu/tools/web/web_playwright_backend.py:_route_handler_abort_resources`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1115, 1119`
- **输入场景**: (a) 请求的资源类型为 image/font/media（应 abort）；(b) 请求的资源类型为 document 且 URL 通过 egress policy（应 continue）
- **实际分支**: 当前 FakeRoute/FakeRequest 测试只覆盖 egress rejection abort 路径（L1117）；resource-type-based abort（L1115）和 allowed-resource continue（L1119）未被测试
- **预期行为**: `_route_handler_abort_resources` 有三个分支：(1) 资源类型是 image/font/media → abort；(2) URL 被 egress policy 拒绝 → abort；(3) URL 被 egress policy 允许 → continue
- **实际行为**: 只有分支 (2) 被覆盖
- **直接证据**: coverage `--show-missing`：lines 1115, 1119 在 missing 列表中；`FakeRoute` 类不验证 `abort()`/`continue_()` 被调用的原因
- **影响**: 低——egress policy 拒绝路径（安全关键路径）已被覆盖；resource-type abort 和 allow continue 是功能路径，缺失不会造成安全漏判
- **建议改法和验证点**: 扩展 FakeRoute 测试覆盖三种资源类型和 allowed URL
- **修复风险（低）**: 纯 unit test
- **严重程度（低）**:

### R02-AGG-DS-F05 — web_playwright_backend.py 取消杀死开关与进程清理路径未覆盖

- **入口/函数**: `dayu/tools/web/web_playwright_backend.py:_run_playwright_worker_process` / `_close_playwright_browser`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:878-879, 883-886, 932-944`
- **输入场景**: (a) worker 进程运行中 cancellation token 触发；(b) worker 无结果退出；(c) worker 超时；(d) `atexit` 注册的 browser cleanup 触发
- **实际分支**: 取消杀死开关（`_terminate_playwright_process` + `raise CancelledError`）、worker 异常退出路径、`_close_playwright_browser` cleanup 实现全部未覆盖
- **预期行为**: Host 对 Agent/Runner 的取消是强约束真源（AGENTS.md 架构硬约束）
- **实际行为**: 取消路径从未被测试验证
- **直接证据**: coverage `--show-missing`：lines 878-879, 883-886, 932-944 在 missing 列表中
- **影响**: 取消不完整可能导致孤儿 browser 进程、资源泄漏。这是 Host→Engine 取消链的关键一环
- **建议改法和验证点**: 补充 cancellation token 触发时的 worker cleanup 测试；补充 browser cleanup 的 atexit 行为验证
- **修复风险（中）**: 进程管理测试较复杂，可能需要 subprocess 隔离
- **严重程度（低）**:

## 4. 所有权链完整性与语义漂移 — 对抗验证结果

### 4.1 Raw parser/default 唯一 owner：PASS

- `provider.py:_parse_config` (L96-176) 是唯一 raw config 入口
- `_CONFIG_FIELDS` frozenset (L42-55) 定义 12-field 精确闭集，在读取任何字段前拒绝 unknown key
- `_bool_default`、`_positive_float`、`_positive_int` 只在 `provider.py` 定义，无第二套 parser
- `_resource_budgets_default` 唯一委托 `web_resource_budgets_from_json`
- 直接执行验证确认：absent fields → typed defaults；unknown field → ValueError
- 搜索 `_DEFAULT` pattern 确认所有默认值仅在 `provider.py` 定义

### 4.2 三 child budget 唯一 typed 真源：PASS

- `HttpResourceBudget`、`BrowserResourceBudget`、`DiagnosticResourceBudget` 各自拥有自己的字段和默认值
- `DEFAULT_HTTP_RESOURCE_BUDGET`、`DEFAULT_BROWSER_RESOURCE_BUDGET`、`DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET` 是唯一默认常量
- `web_resource_budgets_from_json` 在字段缺失时只补对应 child owner 的 typed default
- 搜索 frozen budget 数值（134217728/268435456/1048576/16777216/8388608/8192/512）只在 `web_resource_budget.py` 中有匹配
- `WebResourceBudgets`（复数聚合）只在 `WebToolsConfig` 中停留，消费者只拿自己的 child：`web_tools.py` 取 `config.resource_budgets.http`，取 `resource_budgets.browser` 和 `resource_budgets.diagnostics`
- 旧 `WebResourceBudget`（单数）在 `dayu/tools/web/` 下零引用残留

### 4.3 Transport policy 单一真源：PASS

- `WebHttpTransportPolicy` 在 `provider.py:145-148` 唯一创建，字段来自同一 `_parse_config`
- `_send_authorized_request_attempt` 是唯一 transport 发送路径，消费 `transport_policy` 做 proxy、peer proof、trust_env 决策
- `web_search_providers.py` 正确导入 `_send_authorized_plain_request` 并传入同一 `transport_policy`，不复刻 proxy/peer 规则
- 所有 transport 消费者（fetch、search provider、browser）使用 keyword-only typed `transport_policy: WebHttpTransportPolicy` 参数，无 loose `**kwargs`

### 4.4 Browser capability 独立 owner：PASS

- Browser proof gate 在 `web_playwright_backend.py:1622-1627`，在 `import playwright` 之前 fail-closed
- `browser_enabled` 与 `allow_private_network_url` 双向解耦：`_browser_fallback_available` (L918-933) 只检查 `browser_enabled` 和 `transport_policy.dns_peer_proof_enabled`，不引用 private network
- Egress policy 使用相同的 `allow_private_network_url` 和 `allow_custom_port_url` 字段，独立于 browser
- Browser 不可用时不会静默降级：`_try_playwright_fallback` 在 proof-on 或 import 失败时 raise

### 4.5 Diagnostic lifecycle 只读 owner：PASS

- `web_diagnostics.py` 的 `to_json()` 只输出 length、SHA256 digest、header presence、error_code/error_message（已脱敏），不输出正文内容
- `project_response_headers()` 过滤敏感 header（cookie、authorization、api-key 等），只保留 4 个 observable header name
- Schema v2/revision 2 正确声明
- 扫描确认：`reconcile`、`publish`、`ttl_seconds`、`output_enabled`、`owner_final_name`、`storage_state_out` 在 `dayu/tools/web/` 下零命中
- Storage-state 文件只作为经 `os.path.isfile`、UTF-8、JSON object 校验的 read input

### 4.6 Egress policy 无下游重算：PASS

- `WebEgressPolicy` 只在 `web_tools.py` 中从 typed config 构造（search 和 fetch 两处），无下游独立端口/网络判定
- private 和 custom-port 字段独立存储（`_allow_private_network` 和 `_allow_custom_port` 分开），独立检查，无相互推导
- `authorize_http_target` 的五个拒绝点（URL parse、custom port、local hostname、DNS resolution、address category）全部由同一 owner 控制

### 4.7 无过渡设计/下游补偿/第二默认：PASS

- 无第二套 `_DEFAULT_*` 常量系统
- 无 `hasattr`/`getattr` 绕过 Dayu 自有类型边界（仅有的 `getattr` 用法均为访问 `requests.Response`/`requests.Session` 外部库属性或标准 Python 异常 introspection）
- `web_fetch_orchestrator.py` 的 `setattr(response, "_content", ...)` 和 `getattr(session, "__dayu_warmed_hosts__")` 是访问 `requests` 外部库的既有模式，非 R02 引入，非 Dayu 层间类型绕过
- 无 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS`/`1_024`/`default=80` 残留
- 无 utility-local 第二 transport constructor、raw bool inference 或 environment inference

## 5. 安全组合完整性 — 对抗验证结果

### 5.1 Private/custom-port deny：PASS（代码级） + 设计说明

- `WebEgressPolicy.__init__` 默认 `allow_private_network=False`、`allow_custom_port=False`（fail-closed）
- `provider.py` 默认 `_DEFAULT_ALLOW_PRIVATE_NETWORK_URL=True`、`_DEFAULT_ALLOW_CUSTOM_PORT_URL=True`（业务需要）
- 打包配置 `tool_discovery.json` 显式设置 `allow_private_network_url: true`、`allow_custom_port_url: true`
- 这是分层默认设计：class 级 fail-closed 提供深度防御，provider 级 permissive 满足买方财报分析需要访问内部 filing 服务器的业务需求。不是安全缺陷，是 accepted plan 明确要求的设计
- private 和 custom-port deny 均经正式 `ConfigLoader → effective provider assembly → discovery → ToolDefinition.callable` 链执行，smoke 验证通过

### 5.2 Browser/private 解耦：PASS

- `browser_enabled` 不从 `allow_private_network_url` 推导，也不反向推导
- Browser fallback 可用性由 `_browser_fallback_available` 独立判定
- Egress policy 在 requests 和 Playwright 两路径使用同一实例，不因 backend 不同而改变授权

### 5.3 Proxy + peer proof 冲突：PASS（typed fail-closed）

- `web_http_session.py:722-727`：proxy selected + proof required → `ProxyPeerProofIncompatibleError`，在 `session.send()` 之前
- 无静默降级、无 warning 后继续
- proxy deny 时 assert `settings["proxies"]` 为空（L720-721）

### 5.4 Peer proof 真实验证：PASS

- `_PinnedHTTPConnection._new_conn()` → `_connect_to_approved_addresses` (L216-261)
- `sock.getpeername()` 获取真实连接 peer，与 approved addresses 比较
- IPv4-mapped IPv6 归一化、不匹配时关闭 socket
- DNS resolution 过滤 unspecified/multicast/private/loopback/link-local

### 5.5 Browser peer proof：PASS（启动前 fail）

- `web_playwright_backend.py:1622-1627`：proof-on → return `unprocessable`，在 `import playwright` 之前
- `_browser_fallback_available`（`web_tools.py:933`）也阻止 proof-on 时尝试 browser

### 5.6 Redirect 每跳重新授权：PASS

- `web_fetch_orchestrator.py:866-870`：每跳调用 `_authorize_http_target(egress_policy, url=next_url, reason="http_redirect")`
- 完整的 URL normalize → scheme → userinfo → custom port → local hostname → DNS → address category 链
- 最大 30 hops（`_MAX_HTTP_REDIRECT_HOPS`）

### 5.7 Challenge detection：PASS

- `web_challenge_detection.py` 完整保留：三级决策（NONE/SUSPECTED/CONFIRMED）、vendor signal（Cloudflare/Alibaba/DataDome/Akamai）、combinatorial logic
- 在 requests 路径、Playwright 路径、主 flow 中均被调用
- Challenge decision 被投影到 diagnostics v2

### 5.8 Redaction：PASS

- URL projection 剥离 userinfo/query/fragment
- Header projection 只暴露 4 个 observable header name；敏感 header（cookie/authorization/api-key/secret/token）只记录 presence
- Error message 四层 redaction：known sensitive values、hex tokens、runtime redact primitive、truncation
- Playwright response headers 经 `_sanitize_response_headers` 白名单过滤

### 5.9 Dangerous address rejection：PASS

- `_is_public_address()` 和 `_is_local_profile_address()` 均拒绝 unspecified/multicast
- IPv4-mapped IPv6、scoped IPv6 被拒绝
- 空解析地址列表 raise error

### 5.10 安全结论

无 fail-open 或静默降级证据。所有安全关键路径均为 typed exception fail-closed。一个 WARNING（`web_http_session.py:729`）是 proxy-active-without-peer-proof 信息性诊断，不改变安全决策。

## 6. Plan Compliance 与 Deferred Scope

### 6.1 Plan §6 allowed-file 闭集：PASS

18 changed product/config/utils/tests/README paths 与 plan §6 闭集精确一致：

```
dayu/tools/web/provider.py
dayu/tools/web/web_diagnostics.py
dayu/tools/web/web_egress_policy.py
dayu/tools/web/web_fetch_orchestrator.py
dayu/tools/web/web_http_session.py
dayu/tools/web/web_playwright_backend.py
dayu/tools/web/web_resource_budget.py
dayu/tools/web/web_search_providers.py
dayu/tools/web/web_tools.py
dayu/config/tool_discovery.json
dayu/config/README.md
utils/diagnose_web_access.py
utils/smoke_web_ci.py
tests/tools/web/test_web_tools_provider.py
tests/tools/web/test_diagnose_web_access.py
tests/tools/web/test_smoke_web_ci.py
tests/runtime/test_config_loader.py
tests/README.md
```

零越界文件。plan §6 闭集中预期零 diff 的文件（`web_challenge_detection.py`、`web_recovery.py`、`web_tool_projection_text.py`、`web_search_projection.py`、`utils/diag_web_batch.sh`、root/分层 README）均零 diff。

### 6.2 Plan §4 owner boundary：全部实现

7 个 owner boundary 均有实现和测试/扫描证据。无遗漏。

### 6.3 Plan §11 frozen budget values：PASS

直接执行验证确认所有 7 个 frozen values 与 typed constants 一致。真实 filing fixture (1,503,780 B) 未命中任何 ceiling。

### 6.4 Deferred scope leakage：PASS（零偷带）

- `Issue #178`、`R03`、`authorization.framework`、`policy DSL`、`capability token`、`proxy credential schema`、`unified auth`、`storage state refresh/retention`：在生产/测试 ADDED 行中零命中
- Issue 178 只在 `docs/reviews/` artifacts 中作为非目标声明出现
- Credential lifecycle 符号（`_StorageStateLifecycle`、`--storage-state-out`、`--storage-state-ttl-seconds` 等）在 diff 中全部为 deletions（21 行），零 additions

## 7. Validation Harness 归因可信度

### 7.1 三次 harness 错误归因：可信

| # | 错误 | 归因 | 可信度 |
|---|------|------|--------|
| 1 | zsh `path` 变量覆盖 `PATH` → exit 127 | Shell 调用错误，非产品缺陷 | 可信：修正后 11 个 `--fail-under=80` 全部 exit 0 |
| 2 | `ast.dump` TypeError | 审计器编程错误，在判定前崩溃 | 可信：无 source pass/fail 结果产生 |
| 3 | Sphinx doc 误判为 Google section，38 假阳性 | 审计器口径错误 | 可信：修正后 aggregate 236/S2 99/S3 36 issues 均为 0 |

三次错误均为只读验证器调用/口径错误，未修改产品/测试/docstring 来"修"审计。Controller 独立重新运行并验证了修正结果。

### 7.2 236/99/36 qualified-name 数量级验证：一致

- 粗略 `def/class` 计数：283（含装饰器、嵌套函数、重复定义、diff 上下文噪声）
- 唯一 qualified-name 计数：236（去重、仅 added_or_signature_changed）
- 差异 47 在合理范围内
- S2 99（Controller 确认精确匹配）、S3 36（完整 qualified-name 列表已提供）

## 8. 覆盖率深度分析

### 8.1 80% 阈值有效性

`web_tools.py` (80.056%, 712 stmts, 142 uncovered) 和 `web_playwright_backend.py` (80.488%, 533 stmts, 104 uncovered) 均通过 `--fail-under=80`。但未覆盖代码组成存在结构性关注点：

**web_tools.py 未覆盖关键区域**：
- URL 归一化安全拒绝路径（L1091, L1097, L1103, L1105, L1111）— 见 F02
- 多个 browser fallback 编排分支（L2095-2097, L2130, L2162, L2194-2200 等）
- process-backed fetch 执行路径（L1766, L1796-1802）
- 约 28 行 dead code / thin delegation wrapper 膨胀分母

**web_playwright_backend.py 未覆盖关键区域**：
- `_get_playwright_browser` 双检锁单例 24 行零覆盖 — 见 F01
- 路由安全处理器 2/3 分支 — 见 F04
- text budget 强制执行 — 见 F03
- 取消杀死开关 + 进程清理 — 见 F05
- synthetic doubles 掩盖真实 browser lifecycle：所有测试注入 fake `get_playwright_browser`

### 8.2 Synthetic doubles 评估

- `monkeypatch`-based fakes 替换整个 pipeline stage（`_warmup_domain`、`_probe_content_type`、`_fetch_and_convert_content`、`_try_playwright_fallback`）— 可接受但限制了端到端验证
- `_get_playwright_browser` 注入 fake — **关注点**：真实 browser lifecycle 零覆盖
- `FakeRoute`/`FakeRequest` — 部分覆盖，缺少 resource-type 和 continue 分支
- `_run_synthetic_playwright_worker` — 可接受，避免 CI 中的 Chromium 依赖

### 8.3 覆盖率结论

两个接近阈值文件的未覆盖代码中，有 5 个可独立验证的 gap（F01-F05）。这些不是所有权漂移缺陷，但代表了测试套件对关键安全/正确性路径的覆盖不足。当前 80% 逐文件 gate 通过，但建议在后续工作中补充这些测试（见 §10 residual）。

## 9. 已排除的潜在关注点

以下项目经过直接验证后确认不是缺陷：

| 项目 | 初始关注 | 验证结果 |
|---|---|---|
| 旧 `WebResourceBudget` 残留 | S1 删除后可能残留 | `dayu/tools/web/` 下零命中 |
| credential lifecycle 残留 | S3 删除后可能遗漏 | `reconcile\|publish\|ttl_seconds\|output_enabled\|storage_state_out` 在生产代码中零命中 |
| 第二 parser/default | 可能在下游重算 | 所有 `_DEFAULT_*` 仅 `provider.py`；所有 budget 默认仅 `web_resource_budget.py` |
| `hasattr`/`getattr` 类型绕过 | 违反编码硬约束 | 仅有的 `getattr` 用法访问 `requests` 外部库属性或 Python 异常 introspection，非 Dayu 层间类型绕过 |
| `__dayu_warmed_hosts__` dunder 注入 | 绕过 Session 类型边界 | 访问 `requests.Session` 外部库对象，非 Dayu 自有类型。既存模式，非 R02 引入 |
| `setattr(response, "_content")` | 修改私有属性 | `requests.Response._content` 是该库已知的半私有属性；既存模式 |
| provider.py permissive 默认 | 安全关注 | 打包配置显式设置所有值；`WebEgressPolicy.__init__` 默认 fail-closed 提供深度防御；accepted plan 要求该设计 |
| Issue 178/R03/unified auth 偷带 | 可能提前实现 | ADDED 行零命中 |

## 10. Open Questions

无。所有 subagent 和主 reviewer 的疑问均已通过直接代码/数据证据解决。

## 11. Residual Risk

| residual | classification | owner / destination | 理由 |
|---|---|---|---|
| `_get_playwright_browser` 零直接测试覆盖（F01） | verification gap | R02 aggregate fix gate 或后续 WU | 24 行双检锁逻辑无测试；所有测试注入 fake |
| URL 归一化拒绝路径未覆盖（F02） | low-risk test gap | 后续 web_tools 测试补充 | 当前输入路径已有上游校验 |
| text budget 强制执行未覆盖（F03） | low-risk test gap | 后续 web_playwright_backend 测试补充 | DOM budget 路径已覆盖 |
| 路由安全处理器分支未覆盖（F04） | low-risk test gap | 后续 web_playwright_backend 测试补充 | egress rejection 路径（安全关键）已覆盖 |
| 取消杀死开关未覆盖（F05） | low-risk test gap | 后续 web_playwright_backend 测试补充 | 进程管理测试复杂度较高 |
| credential refresh/retention lifecycle | deferred | GitHub Issue #178 | R02 已删除提前实现，只保留 read input |
| live DOM/event/error 体量变化 | future variability | Web config owner | 当前 fixture 未命中 ceiling |
| proxy/browser peer proof 限制 | accepted limitation | Web transport/browser owner | typed fail-closed |
| external provider 波动 | environment-only | Web diagnostics/smoke owner | local hard gate 已闭合 |
| accepted-result / LLM projection | deferred | umbrella R03 | 未启动 |
| unified authorization | no-code | Topic 9 future Controller decision | source/diff 零偷带 |

## 12. Final Verdict

**PASS — findings=5 (0 severe, 0 high, 1 medium, 4 low)，zero ownership drift，zero security regression，zero deferred scope leakage。**

R02 S1-S3 组合已将 raw parser/default、typed budgets、transport、browser 和 diagnostic lifecycle 放在唯一 owner。security fail-close 完整保留，无第二默认/下游补偿/过渡设计。18-path allowed scope 精确。validation harness 归因可信。5 个 finding 均为测试覆盖 gap，非所有权漂移或安全缺陷。

下一入口仅为 Controller adjudication 对本 deepreview 的逐项裁决。

---

**Review 执行信息**：
- 主 reviewer：AgentDS
- 并行 subagent：4 路（所有权链 81 tool calls、安全组合 33 tool calls、覆盖缺口 82 tool calls、plan/deferred scope 26 tool calls）
- 主 reviewer 直接验证：provider parser 行为、budget 默认值、旧类名残留、credential lifecycle 残留、deferred scope 泄漏、pyright、git diff --check
- 生成时间：2026-07-15 04:48:55 UTC+8
