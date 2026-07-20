# WU-SEMANTIC-OWNERSHIP-01 Overdesign / Design-Truth Gate Review

## Scope

- Mode: all repository (专项范围)
- Branch: `phaseflow/host-issues-control`
- Review commit range: `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`（含 b1a0631f）
- Design truth sources: **only** `docs/host/design.md` and `docs/engine/design.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-mimo.md`
- Review date: 2026-07-13
- Parallel review coverage: 4 subagents 覆盖 DocResourceBudget/BoundedSourceSnapshot、Web egress/resource/budget、LLM-facing tool descriptions、测试固化；主 reviewer 直接验证设计真源并整合

## 审查原则

- 唯一设计真源只有 `docs/host/design.md` 和 `docs/engine/design.md`
- WU plan、review artifact、implementation artifact、control doc、README、测试都不能作为"授权该设计正确"的真源
- 若设计真源没有，且代码把它变成用户可见 contract / public API / schema / LLM-facing 文本 / durable projection / test contract，就按 evidence gate 报告

## 设计真源检索确认

主 reviewer 对 `docs/host/design.md`（3654 行）和 `docs/engine/design.md`（546 行）做了以下关键词全量 grep：

| 关键词 | 命中 |
| --- | --- |
| `DocResourceBudget` | 0 |
| `BoundedSourceSnapshot` | 0 |
| `max_source_bytes` | 0 |
| `max_directory_entries` | 0 |
| `SourceBudgetExceeded` | 0 |
| `egress` | 0 |
| `private_network` | 0 |
| `bot_challenge` | 0 |
| `challenge_detect` | 0 |
| `WebResourceBudget` | 0 |
| `resource_budget` | 0 |
| `allow_private_network` | 0 |
| `32 * 1024 * 1024` / `32MiB` | 0 |
| `10_000` / `10000`（作为 directory limit） | 0 |
| `wire_body_bytes` | 0 |
| `decoded_body_bytes` | 0 |

设计真源中存在 `tool_truncation_policy`（host/design.md:97），但该 policy 只覆盖 `text_chars.max_chars`、`text_lines.max_lines`、`list_items.max_items`、`binary_bytes.max_bytes` 四类结果截断默认值，不覆盖文档源字节预算、目录遍历上限、HTTP response body 预算、浏览器 DOM 预算或 egress policy。

---

## Findings

### 01-未修复-高-DocResourceBudget 32MiB/10000 无设计真源授权

- **语义/contract**: `DocResourceBudget(max_source_bytes=32*1024*1024, max_directory_entries=10_000)` 是 Doc 工具内部资源预算，硬编码为模块级常量 `_DOC_SOURCE_MAX_BYTES` 和 `_DOC_DIRECTORY_MAX_ENTRIES`。`BoundedSourceSnapshot` 在 `__enter__` 时检查声明长度和实读长度，超限抛 `SourceBudgetExceeded`。`list_files` 和 `search_files` 的 `directory_entry_limit` / `source_limit` partial contract 直接消费此预算。
- **正确 owner**: 设计真源应定义文档工具资源预算的治理边界和配置化策略。
- **漂移位置**: `dayu/tools/doc_tools.py:87-88`（常量定义）、`dayu/tools/doc_tools.py:119-150`（DocResourceBudget dataclass）、`dayu/documents/processors/bounded_source.py:276-313`（BoundedSourceSnapshot.__enter__ 超限检查）。
- **为什么设计真源缺失**: `docs/host/design.md` 和 `docs/engine/design.md` 均未提及文档源字节预算、目录遍历上限或 BoundedSourceSnapshot 概念。设计真源的 `tool_truncation_policy`（host/design.md:97）只覆盖工具结果截断，不覆盖源读取预算。32MiB 和 10000 是 implementation agent 自行决定的硬编码值。
- **为什么失败或成本放大**: 这些值成为 LLM-facing tool description 的产品语义（`list_files` description 写 `truncated_reason=directory_entry_limit`；`search_files` description 写 `truncated_reason=source_limit`），模型必须理解并遵循。测试 `tests/tools/test_doc_tools_provider.py` 固化这些值。若设计真源决定不同预算或配置化策略，需要同时改常量、tool description、测试断言和 BoundedSourceSnapshot 异常语义。
- **推荐修正边界**: 设计真源补充文档工具资源预算治理边界；或明确这些为 implementation detail，从 LLM-facing tool description 中移除 budget 语义，改为内部错误处理。
- **验证点**: `docs/host/design.md` 或 `docs/engine/design.md` 是否有文档源预算授权；LLM-facing description 是否暴露了无设计真源的 budget 语义。
- **修复风险**: 中
- **严重程度**: 高

### 02-未修复-高-WebEgressPolicy 私网阻断无设计真源授权

- **语义/contract**: `WebEgressPolicy(allow_private_network=False)` 默认阻断所有私网 IP（`is_private`、`is_loopback`、`is_link_local`、`is_reserved`、`is_multicast`、`is_unspecified`）、benchmark 网段 `198.18.0.0/15`、metadata 地址 `169.254.169.254` / `100.100.100.200`。`allow_private_network=True` 时只排除 unspecified 和 multicast。`AuthorizedHttpTarget` 冻结 numeric destination，HTTP session 只连接 approved_addresses。
- **正确 owner**: 设计真源应定义 Web 工具出站网络边界。
- **漂移位置**: `dayu/tools/web/web_egress_policy.py:18-27`（benchmark/metadata 常量）、`dayu/tools/web/web_egress_policy.py:128-151`（_is_public_address 判断）、`dayu/tools/web/web_egress_policy.py:252-298`（WebEgressPolicy 类）。
- **为什么设计真源缺失**: `docs/host/design.md` 和 `docs/engine/design.md` 均未提及 Web egress policy、私网阻断、IP 分类或 SSRF 防护。设计真源的 tool governance 只覆盖截断、fetch_more、等待与重复调用治理（host/design.md:55），不覆盖网络出站策略。
- **为什么失败或成本放大**: 这是安全-like policy，但没有设计真源授权其具体阻断范围。`allow_private_network` 作为 provider config 暴露（`dayu/tools/web/provider.py:_CONFIG_ALLOW_PRIVATE_NETWORK_URL_FIELD`），意味着部署者可以绕过默认阻断。阻断范围（哪些 IP 类被拒绝、metadata 地址列表、benchmark 网段）是 implementation agent 自行决定的。
- **推荐修正边界**: 设计真源补充 Web 工具出站网络策略边界；或明确这是工具实现层的局部防御，不作为 Host/Engine 治理真源。
- **验证点**: `docs/host/design.md` 是否有 Web egress policy 授权；阻断范围是否由设计真源定义。
- **修复风险**: 中
- **严重程度**: 高

### 03-未修复-高-WebResourceBudget 无设计真源授权

- **语义/contract**: `WebResourceBudget` 定义 7 个硬上限：`wire_body_bytes=25MiB`、`decoded_body_bytes=50MiB`、`warmup_body_bytes=64KiB`、`browser_dom_chars=5_000_000`、`browser_text_chars=1_000_000`、`diagnostic_error_chars=1024`、`diagnostic_events=80`。这些值硬编码为 dataclass 默认值，通过 provider config `resource_budget` 字段可覆盖。
- **正确 owner**: 设计真源应定义 Web 工具资源预算治理边界。
- **漂移位置**: `dayu/tools/web/web_resource_budget.py:19-72`（WebResourceBudget dataclass）、`dayu/tools/web/provider.py:_CONFIG_RESOURCE_BUDGET_FIELD`（config 暴露）。
- **为什么设计真源缺失**: `docs/host/design.md` 和 `docs/engine/design.md` 均未提及 Web 工具的 HTTP body 预算、浏览器 DOM 预算或诊断输出预算。设计真源的 `tool_truncation_policy` 只覆盖工具结果截断的 `text_chars`/`text_lines`/`list_items`/`binary_bytes`，不覆盖 HTTP response body 或浏览器 DOM 的资源预算。
- **为什么失败或成本放大**: 25MiB/50MiB/5M/1M 等值是 implementation agent 自行决定的。`web_resource_budget_from_json` 要求完整 7 字段 object，不允许 partial override，增加了配置复杂度。这些值通过 provider config 暴露给部署者，但没有设计真源定义其合理范围或配置化策略。
- **推荐修正边界**: 设计真源补充 Web 工具资源预算治理边界；或将这些值明确为工具实现层的内部 detail，不通过 provider config 暴露。
- **验证点**: `docs/host/design.md` 是否有 Web 资源预算授权。
- **修复风险**: 中
- **严重程度**: 高

### 04-未修复-中-BotChallengeDetection 无设计真源授权

- **语义/contract**: `BotChallengeDetectionResult` 包含 `BotChallengeDecision`（none/suspected/confirmed）、`BotChallengeEvidenceClass`（5 类证据来源）和 `ChallengeFallbackAction`（continue/try_browser/fail_blocked）。检测逻辑基于 HTTP status codes（401/403/429/503）、vendor-specific header signals（Cloudflare/Akamai/DataDome/Datadome）和 vendor-specific content signals（13 个 pattern）。
- **正确 owner**: 设计真源应定义 Web 工具对挑战页/反爬页的处理策略。
- **漂移位置**: `dayu/tools/web/web_challenge_detection.py:64-108`（信号集和枚举定义）、`dayu/tools/web/web_challenge_detection.py:120-139`（detect_bot_challenge 函数）。
- **为什么设计真源缺失**: `docs/host/design.md` 和 `docs/engine/design.md` 均未提及 bot challenge detection、反爬页处理或 vendor-specific 信号集。这是一个完整的检测+判定+fallback 状态机，没有设计真源授权。
- **为什么失败或成本放大**: vendor-specific 信号集（Cloudflare/Akamai/DataDome 的 header 和 content pattern）是 implementation agent 自行决定的，没有设计真源定义检测范围、误判容忍度或 fallback 策略。`ChallengeFallbackAction.TRY_BROWSER` 引入了浏览器回退语义，但设计真源未定义何时应使用浏览器 vs HTTP。
- **推荐修正边界**: 设计真源补充 Web 工具挑战页处理策略；或将检测逻辑明确为工具实现层的内部 heuristic，不作为产品 contract。
- **验证点**: `docs/host/design.md` 是否有挑战页检测授权。
- **修复风险**: 低
- **严重程度**: 中

### 05-未修复-高-LLM-facing tool descriptions 暴露无设计真源的 budget/partial 语义

- **语义/contract**: `list_files` description 写 `truncated_reason=directory_entry_limit，必须缩小目录、关闭递归或收紧 pattern 后重试`；`search_files` description 写 `truncated_reason 会是 result_limit、directory_entry_limit 或 source_limit，应分别收紧关键词/目录或改用较小文件后重试`，以及 `skipped_oversized_files 是因单文件字节预算跳过的文件数`。这些文本把无设计真源的 `DocResourceBudget` 限制写成了模型必须遵循的产品语义。
- **正确 owner**: LLM-facing tool description 应只描述设计真源授权的行为 contract。
- **漂移位置**: `dayu/tools/doc_tools.py:700-705`（list_files description）、`dayu/tools/doc_tools.py:848-853`（search_files description）。
- **为什么设计真源缺失**: 设计真源未定义 `directory_entry_limit`、`source_limit`、`skipped_oversized_files` 或 `单文件字节预算` 概念。这些是 implementation agent 为 `DocResourceBudget` 发明的 LLM-facing 语义。
- **为什么失败或成本放大**: 模型会依赖这些 description 做决策（如"必须缩小目录"、"改用较小文件"）。若设计真源决定不同策略（如允许 partial results 不报错、或用不同 budget），需要同时改 description、工具实现和测试。模型对 `directory_entry_limit` / `source_limit` 的理解完全来自这些 description，没有设计真源 backing。
- **推荐修正边界**: 从 LLM-facing description 中移除无设计真源的 budget 语义，改为内部错误处理；或由设计真源明确授权这些 partial contract。
- **验证点**: tool description 是否暴露了设计真源未定义的 budget/limit 语义。
- **修复风险**: 中
- **严重程度**: 高

### 06-未修复-中-测试固化无设计真源限制

- **语义/contract**: `tests/tools/test_doc_tools_provider.py` 对 `DocResourceBudget`、`BoundedSourceSnapshot`、`SourceBudgetExceeded`、`directory_entry_limit`、`source_limit` 的断言固化了 32MiB/10000 等无设计真源限制为 contract。`tests/tools/web/test_web_tools_provider.py` 对 `WebResourceBudget`、`WebEgressPolicy`、`BotChallengeDetection` 的断言固化了 25MiB/50MiB 等无设计真源限制。
- **正确 owner**: 测试应断言设计真源授权的行为 contract。
- **漂移位置**: `tests/tools/test_doc_tools_provider.py`（DocResourceBudget/BoundedSourceSnapshot 相关断言）、`tests/tools/web/test_web_tools_provider.py`（WebResourceBudget/WebEgressPolicy 相关断言）。
- **为什么设计真源缺失**: 测试断言的限制值（32MiB、10000、25MiB、50MiB 等）没有设计真源授权。测试把 implementation agent 自行决定的值固化为 contract，导致修改这些值需要同时修改测试。
- **为什么失败或成本放大**: 若设计真源后续授权不同值或配置化策略，需要同时改常量、tool description、测试断言和异常语义。测试固化增加了修改成本。
- **推荐修正边界**: 测试断言应基于设计真源授权的行为，不固化 implementation-specific 数值；或由设计真源明确授权这些值。
- **验证点**: 测试断言的限制值是否有设计真源授权。
- **修复风险**: 低
- **严重程度**: 中

---

## 工具安全单独说明

已有的 `docs/reviews/wu-semantic-ownership-01-tool-security-artifact-code-audit.md` 确认：WU-SEMANTIC-OWNERSHIP-01 范围内没有添加 tool-security 代码。upload allowlist、file authority、URL/TLS/redirect/SSRF provenance、remote byte-budget policy、LLM-facing upload/download security schema 均未实现。

本次 review 发现的 WebEgressPolicy（Finding 02）和 BotChallengeDetection（Finding 04）属于**局部业务设计**，不是 tool-security policy：
- WebEgressPolicy 是 Web 工具的出站 URL 授权，不是 Host/Engine 层的安全治理
- BotChallengeDetection 是 HTTP 响应的启发式检测，不是安全策略引擎

这些模块的设计真源缺失问题已在各自 finding 中报告。它们不是 tool-security-like policy，但确实缺乏设计真源授权其具体阻断范围和检测策略。

---

## Open Questions

- 设计真源是否计划补充文档工具资源预算和 Web 工具出站策略的治理边界？
- `DocResourceBudget` 和 `WebResourceBudget` 是否应通过 provider config 暴露给部署者，还是作为工具实现层的内部 detail？
- `BotChallengeDetection` 的 vendor-specific 信号集是否需要设计真源授权其维护范围？

## Residual Risk

- 本 review 只覆盖了 `b1a0631f^..HEAD` 范围内的代码。范围外的已有 overdesign 未检查。
- 4 个 background agent 的完整结果未全部返回；主 reviewer 基于直接代码阅读和设计真源 grep 完成了核心证据收集。
- `dayu/runtime/config_loader.py` 中的 `ContextBudgetConfig`、`ToolTruncationPolicyConfig` 等配置类未深入审查是否与设计真源对齐。
