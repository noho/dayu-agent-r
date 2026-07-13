# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Plan Review — AgentMiMo

## Reviewed Target

- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- Scope: 10 accepted R3-E findings across Web egress, resource budget, diagnostic redaction, challenge/search, document bounded input, and smoke oracle
- Slices: 3 (S1 Web egress/response ownership, S2 Web resource/challenge/diagnostic/oracle, S3 Documents bounded input)

## Assumptions Tested

1. All 10 accepted R3-E findings have correct semantic owner — **verified**
2. All code evidence citations (24 total) are accurate against actual source — **verified**
3. Design truth references (`docs/host/design.md:68-81`, `:86`, `:108`) — **3 citation errors found**
4. requests/urllib3 can support connect-before-request peer proof — **unverified; no concrete strategy provided**
5. Slice count (3) complies with optimization control — **verified** (control allows 1-3)
6. Owner boundary doesn't expand into Fins/Host/Engine — **verified**
7. Deferred items correctly classified — **verified**
8. Diagnostic schema v2 contract is self-contained — **verified**
9. Smoke oracle negative controls are testable — **partially; fixture design underspecified**

## Findings

### 01-未修复-中-design.md 行号引用全部错误

- **位置**: §3 "设计与控制真源对齐" 三处 `docs/host/design.md` 引用
- **问题类型**: 不可直接实施
- **当前写法**: plan 引用 `docs/host/design.md:68-81` 说定位了 `dayu.tools` 为业务工具实现、`dayu.documents` 为层中立文档处理基础包；引用 `:86` 说声明了 `dayu.runtime` 提供层中立诊断文本脱敏/JSON 脱敏/截断/digest；引用 `:108` 说说明了 Doc/Web blocking 工具使用 process-backed execution
- **反例/失败场景**: implementation agent 按行号去 design.md 对齐时找不到对应内容，需要自行搜索定位，浪费时间且可能遗漏上下文
- **为什么有问题**: 实际 `design.md:68-81` 是 runtime 组件描述（lane/filelock/ToolsDiscovery/ScenePrepare/ConfigLoader）；`:86` 是 models.json 模型目录配置；`:108` 是 tool_selection 语义。三处均不包含 plan 声称的内容
- **直接证据**:
  - `docs/host/design.md:68-81` 实际内容为 Phase 1 runtime scope、lane/filelock/ToolsDiscovery/ScenePrepare/ConfigLoader 描述
  - `docs/host/design.md:86` 实际内容为 `models.json` 模型目录描述
  - `docs/host/design.md:108` 实际内容为 `tool_selection` 语义
  - plan 声称的概念实际位于：`dayu/tools/__init__.py` docstring（"业务工具包。本包承载 Host / Engine 之外的业务工具实现与 provider"）、`dayu/documents/__init__.py` docstring（"Dayu 共享文档处理基础包...不属于 Host、Engine、Service、UI 或 Fins 任一业务层"）、`dayu/runtime/__init__.py:6,32`（diagnostic_text/json_redaction）、`dayu/tools/doc_tools.py:272,325`（process-backed）
- **影响**: implementation agent 对齐设计真源时定位失败；若 agent 不自行验证可能引用错误行号继续推进
- **建议改法和验证点**: 修正 §3 引用为实际存在对应内容的行号或模块 docstring。如 `dayu.tools` 定位改为引用 `dayu/tools/__init__.py` docstring；`dayu.runtime` 诊断能力改为引用 `dayu/runtime/__init__.py:6,32`；process-backed 改为引用 `dayu/tools/doc_tools.py:272`
- **修复风险（低/中/高）**: 低（纯引用修正）
- **严重程度（低/中/高/严重）**: 低（不影响技术决策正确性，只影响可追溯性）

### 02-未修复-高-S1 requests/urllib3 peer proof 无具体实现策略

- **位置**: §6.1 "Web egress contract" 第 4-5 段、§7 Slice 1 "Residual risks" 与 "Stop condition"
- **问题类型**: 不可直接实施
- **当前写法**: "HTTP transport 在一次 hop 内使用 `AuthorizedHttpTarget` 的地址建立 socket，并保留原 hostname 作为 HTTP Host / TLS SNI / certificate hostname；不得在 connect 时重新对原 hostname 做不受控 DNS。连接后 peer 必须等于 approved address；不满足时在发送 HTTP request bytes 前失败。" "连接 pinning 封装在 Web 私有 adapter/connection class 中，不进入 `dayu.runtime`，不暴露 urllib3 私有对象给 caller。若 requests/urllib3 版本无法在'发送 request 前'证明 peer，S1 停止，不能退化为 response 后 peer 检查。"
- **反例/失败场景**: implementation agent 开始 S1 后发现 requests/urllib3 的 `HTTPAdapter.send()` 方法在内部完成 DNS 解析→socket connect→发送 request bytes→接收 response 的完整流程，不暴露"连接后、发送前"的拦截点。自定义 `HTTPAdapter` 可以在 `send()` 内部用 `create_connection(dest_addr)` 指定 IP 地址建立 socket，但这是 urllib3 内部 API，跨版本稳定性不确定。agent 可能在实现中途发现方案不可行，触发 stop condition 回退
- **为什么有问题**: plan 定义了严格的安全要求（peer 必须在发送 request bytes 前验证）和明确的 stop condition，但没有提供哪怕一个具体的实现技术路径。implementation agent 需要自行研究 urllib3 内部 API 来判断可行性，这不是 code-generation-ready 的 plan
- **直接证据**:
  - `requests` 的 `HTTPAdapter.send()` 调用 `urllib3.HTTPConnectionPool._make_request()`，内部流程为 DNS→connect→send→recv，不暴露 connect 后/send 前的 hook
  - urllib3 的 `create_connection()` 接受 `dest_addr` 参数（IP 元组），自定义 adapter 可预解析为 IP 后传入
  - TLS 场景下 `ssl.SSLSocket` 需要在 `server_hostname` 参数传入原 hostname，但 socket 已连接到指定 IP
  - plan 的 stop condition 说"需要 monkeypatch 全局 DNS / lazy import seam / broad proxy framework 时停止"，但自定义 adapter 不属于这三类，是否可接受未定义
- **影响**: S1 可能实现中途触发 stop condition；或者 implementation agent 采用未经验证的方案后在 code review 阶段被质疑安全性
- **建议改法和验证点**:
  1. 在 §6.1 或 §7 S1 中明确首选实现路径：自定义 `HTTPAdapter`，在 `send()` 内部调用 `urllib3.util.connection.create_connection(dest_addr=(approved_ip, port))` 建立 socket，再交给 urllib3 的 connection pool 使用
  2. 明确该路径的版本约束：需验证当前 `requirements.txt` 中 urllib3 版本是否暴露 `create_connection`
  3. 明确 TLS hostname 处理：socket 连接到 IP 后，TLS handshake 的 `server_hostname` 必须传入原 hostname 以通过 SNI/certificate 验证
  4. 若首选路径不可行，列出备选方案（如 `urllib3` 的 `assert_fingerprint`、raw socket + `http.client`）并评估 stop condition 触发条件
- **修复风险（低/中/高）**: 中（需要验证 urllib3 API 可用性）
- **严重程度（低/中/高/严重）**: 高（S1 的核心安全行为，且 stop condition 可能导致整个 S1 无法实施）

### 03-未修复-中-Smoke oracle fixture 设计未规格化

- **位置**: §6.4 末段、§7 Slice 2 "Tests 与 expected assertions" 末段
- **问题类型**: 契约缺失
- **当前写法**: "local smoke PASS 至少需要独立 fixture request observation + expected sentinel/digest + backend execution evidence；artifact `ok` 只是辅证。" "正例必须由 parent-owned fixture request ledger 和固定 expected digest 确认。"
- **反例/失败场景**: implementation agent 需要自行设计 fixture server、request ledger、sentinel 值和 expected digest 的具体形态。可能设计过于简单（如只检查 HTTP 200）或过于复杂（如需要完整 mock server），导致 smoke oracle 的独立性不足或维护成本过高
- **为什么有问题**: plan 声称 PASS 不能由 producer 自签，必须由独立 oracle 证明。但"parent-owned fixture request ledger"这个关键概念没有任何接口定义、数据结构或生命周期说明。这是 S2 的核心 oracle 设计，却留给 implementation agent 临场发明
- **直接证据**:
  - `utils/smoke_web_ci.py:1207-1231` 当前只检查 producer 自报字段存在
  - `utils/smoke_web_ci.py:1393-1425` 当前直接信任 `ok` 字段
  - plan 要求改为"独立 fixture request observation"，但未定义 fixture 的构造方式
- **影响**: implementation agent 可能设计出的 oracle 仍不够独立，或者 fixture 设计导致 smoke 测试变得脆弱/不可维护
- **建议改法和验证点**:
  1. 在 §6.4 或 §7 S2 中定义 fixture 的最小形态：如"本地 HTTP fixture server 记录所有收到的请求到内存列表；smoke 结束后检查列表是否包含预期请求（method、path、sentinel header）"
  2. 定义 sentinel 值的生成方式：如"每个 smoke run 生成随机 UUID 作为 request header sentinel"
  3. 定义 expected digest 的来源：如"fixture server 返回固定响应体，其 sha256 作为 expected digest"
  4. 定义 negative control 的具体扰动：至少列出 5 种扰动类型（ok=true 但无对应 fixture request、错误 sentinel、错误 digest、challenge 响应、browser 未执行）
- **修复风险（低/中/高）**: 中（需要定义 fixture 接口但不改变架构）
- **严重程度（低/中/高/严重）**: 中（oracle 独立性是 S2 的核心目标）

### 04-未修复-低-Storage state 异常退出清理未覆盖

- **位置**: §6.3 "Diagnostic projection 与 storage state" 末段
- **问题类型**: 状态机漏洞
- **当前写法**: "运行失败也执行 cleanup"
- **反例/失败场景**: `utils/diagnose_web_access.py` 中 `context.storage_state(path=...)` 在 line 1952 执行。若脚本在 storage state 写入后、cleanup 执行前被 SIGKILL 或进程崩溃，storage state 文件会残留。文件有 `0600` 权限但包含登录态
- **为什么有问题**: plan 要求"运行失败也执行 cleanup"，但只覆盖了 Python 异常路径，未覆盖进程级异常。storage state 包含敏感登录态，残留文件是安全风险
- **直接证据**: `utils/diagnose_web_access.py:1950-1952` 保存 storage state 后无 atomic rename + cleanup-on-start 机制
- **影响**: 极端情况下登录态 storage state 文件残留；实际风险低因为需要进程被 SIGKILL 且在同一 mtime 窗口内
- **建议改法和验证点**: 在 §6.3 中补充"storage state 使用 atomic write（写入临时文件后 rename）；每次诊断运行启动时清理目标目录下所有过期 storage state 文件（按 mtime 判断）"
- **修复风险（低/中/高）**: 低（标准 atomic write + startup cleanup 模式）
- **严重程度（低/中/高/严重）**: 低（需要进程级异常才会触发）

### 05-未修复-低-DuckDuckGo "已知 result shape" 判定标准未定义

- **位置**: §6.4 "Challenge 与 DuckDuckGo outcome" 第 4 段
- **问题类型**: 契约缺失
- **当前写法**: "DuckDuckGo HTML parser 独立返回 `results`、`explicit_empty` 或抛 `WebSearchProviderResponseError(reason=response_shape_changed)`。只有明确 no-results marker 可提交合法空结果；有 result container 但单项 malformed 超过确定阈值、完全未知 HTML、challenge/login page 均是 typed provider failure。"
- **反例/失败场景**: "有 result container" 和 "确定阈值" 未定义。implementation agent 需要自行决定什么 CSS selector 构成 "已知 result container"、malformed 比例阈值是多少
- **为什么有问题**: 这是 DuckDuckGo shape drift 检测的核心判定逻辑，plan 只描述了语义但没有给出判定规则
- **直接证据**: `web_search_providers.py:691-728` 当前只用 `div.result` selector；plan 要求区分 "已知 container + malformed items" 与 "完全未知 HTML"
- **影响**: implementation agent 可能设计出过于宽松（误报 shape drift）或过于严格（漏报）的检测
- **建议改法和验证点**: 在 §6.4 中定义最小已知 shape：如"已知 result container 为 `div.result`；`div.result` 存在但提取 title/snippet/URL 任一失败时计入 malformed；malformed 超过 50% 时抛 shape drift；`div.result` 不存在且无明确 no-results marker 时抛 shape drift"
- **修复风险（低/中/高）**: 低（明确阈值即可）
- **严重程度（低/中/高/严重）**: 低（影响搜索质量，不影响安全）

### 06-未修复-低-WebResourceBudget provider config override 键名未定义

- **位置**: §6.6 "冻结的配置、输出与错误 contract" Web 默认 budget 段
- **问题类型**: 契约缺失
- **当前写法**: "第一版只在 `WebToolsConfig` 中保存一个完整 `resource_budget: WebResourceBudget` typed value，provider JSON 可以用同名 object 整体覆盖；object 缺字段、未知字段、bool/零/负数均 fail fast，不做 partial fallback。"
- **反例/失败场景**: "同名 object" 意味着 provider JSON 中键名为 `resource_budget`，但未说明这是在 `WebToolsConfig` 的哪个层级、JSON path 是什么
- **为什么有问题**: implementation agent 需要自行决定 provider JSON 结构中 `resource_budget` 的位置和格式
- **直接证据**: `dayu/tools/web/provider.py` 中 `WebToolsConfig` 的当前 JSON schema 未包含 `resource_budget` 字段
- **影响**: 轻微；implementation agent 可以合理推断，但可能导致不同 consumer 期望不同 JSON path
- **建议改法和验证点**: 在 §6.6 中补充一个最小 provider JSON 示例，如 `{"resource_budget": {"wire_body_bytes": 26214400, ...}}`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（实现时可自然确定）

## Open Questions

1. **S1 urllib3 peer proof 可行性**: 自定义 `HTTPAdapter` 在 `send()` 内部用 `urllib3.util.connection.create_connection(dest_addr=(approved_ip, port))` 建立 socket 的方案，是否满足 plan 定义的"发送 request bytes 前证明 peer"要求？需验证当前 urllib3 版本是否暴露此 API。这直接影响 S1 是否能通过 stop condition。
2. **S2 smoke fixture 形态**: "parent-owned fixture request ledger" 应设计为内存级（单次 smoke run 内有效）还是持久化级（跨 run 可审计）？前者更简单但独立性较弱，后者更安全但成本更高。

## Residual Risks

plan 已在各 slice 中正确识别以下 residual risks，本 review 确认其分类合理：

| Risk | Plan classification | Reviewer assessment |
|---|---|---|
| requests/urllib3 版本升级破坏 pinning | S1 residual | 正确；需集成测试覆盖 |
| 公网 Playwright direct fail closed 降低可用性 | S1 residual | 正确；明确产品降级 |
| Chromium 内部 DOM 仍可能峰值 | S2 residual | 正确；process timeout/kill 已覆盖 |
| digest 对低熵 secret 的字典猜测风险 | S2 residual | 正确；plan 已排除已识别 secret |
| 外部 live URL 不做 hard PASS oracle | S2 residual | 正确；diagnostic-only 合理 |
| Doc tool 通用 file-authority/symlink 竞态 | S3 residual | 正确；归后续 WU |
| exact directory total 需要完整扫描 | S3 residual | 正确；scan_complete=false 合理 |

建议额外追踪：

| Risk | Destination |
|---|---|
| urllib3 `create_connection` API 跨版本稳定性 | S1 implementation 前验证 |
| storage state atomic write + startup cleanup | S2 implementation 时一并处理 |

## Plan Review Conclusion

**pass-with-risks**

R3-E plan 是一个高质量的 semantic ownership plan。10 个 accepted findings 均有直接代码证据支持且 owner 裁决正确；24 个代码引用全部经验证准确；3 个 slice 按 owner boundary 切分且符合优化控制文件；scope 控制严格，deferred items 分类合理。

主要风险是 **S1 的 requests/urllib3 peer proof 实现策略缺口**（Finding 02）：plan 定义了严格的安全要求和 stop condition，但没有提供具体的实现技术路径。这不构成 blocking finding，因为 stop condition 明确要求不可行时停止，但 implementation agent 可能在 S1 中期才发现方案不可行，造成返工。建议在 implementation 前补充 urllib3 `create_connection` API 可用性验证。

其余 5 个 findings（design.md 引用错误、smoke fixture 设计、storage state cleanup、DDG shape 判定、budget override 键名）均为中/低严重程度，不影响 plan 的整体架构正确性。

**Verdict**: pass-with-risks | Findings: 6 (0 blocking, 1 high, 2 medium, 3 low) | Artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-mimo.md`
