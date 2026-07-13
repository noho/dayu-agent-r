# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Web / Documents Egress、资源上限、诊断与 Oracle 实施计划

## 1. Work unit 与 gate

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E - Web And Document Tool Egress, Resource Caps, Diagnostics, And Oracles`
- 类型：production-high semantic ownership / correctness / resource-boundary issue slice
- 当前 gate：accepted plan
- 下一 gate：Slice 1 implementation；plan review、plan fix 与 plan re-review 均已通过，进入逐 slice implementation / review / fix 闭环
- Design truth：`docs/host/design.md`、`docs/engine/design.md`
- Control truth：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- Goal confirmation：`docs/reviews/wu-semantic-ownership-01-round3-r3-e-goal-confirmation.md`
- Source adjudication：`docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` 的 Round3 R3-E 裁决表
- 风险：production-high；所有生产 slice 必须逐 slice review，accepted finding 修复后必须 re-review，最后执行 aggregate deepreview。

## 2. 第一性原理判断

### 2.1 动机是否成立

成立，且不是普通性能优化。

安全 URL 字符串、输出截断、工具 timeout 或进程隔离都不能替代输入 owner 在分配、连接和持久化前执行的边界：

1. URL 预解析与实际 connect 是两个时点；若 transport 不绑定已校验地址，DNS rebinding 可令“预检公网”与“实际连接私网”同时为真。
2. `stream=True` 只约束 requests 何时读取 body，不约束随后调用整包 `gzip.decompress()`、`page.content()` 或 `readlines()` 的分配。
3. tool truncate 位于业务值产生和跨进程传输之后，不能保护 producer 进程免于先构造完整对象。
4. 诊断前缀即使限长，仍是可逆原文；登录页面、URL query、Cookie 或 storage state 不能因“仅用于诊断”而失去最小披露约束。
5. PASS 若只读取被测诊断脚本自行写出的 `ok=true`，producer 可同时制造错误行为与“成功证据”，因此不是独立 oracle。

### 2.2 目标

在 Web 与 Documents 现有工具边界内建立唯一 owner，使下列事实在直接 producer 边界成立，而不是由下游 adapter、ToolRuntime truncate、测试 fixture 或日志补救：

- Web egress：初始 URL、每一 HTTP redirect、实际 connect peer、浏览器导航 / subrequest 和诊断 raw path 都由同一策略裁决。
- HTTP response ownership：每个未返回给 caller 的 response，以及 caller 完成消费后的 response，在 redirect reject、取消、安全拒绝、probe、warmup、异常和成功路径确定关闭。
- Web resource budget：wire、每层 decoded bytes、warmup、Python DOM serialization、诊断 material 均在完整物化前受限。
- Web challenge/search：challenge 证据强度与 fallback 动作同源；DuckDuckGo 响应 shape drift 不再变成空成功。
- Web diagnostics：只落安全 URL 投影、长度、状态、稳定 digest、有限枚举与脱敏错误；默认不落正文、HTML、query/userinfo 或登录态。
- Documents：read/list/search/processor source 在工具业务上限前有界，且 tool 输出明确表达 partial / scan incomplete / resource failure。
- Smoke：passed / failed / skipped / diagnostic-only 来自独立 fixture 事实和负控，不由 diagnostics artifact 的自报字段决定。

### 2.3 成功信号

- 公网 hostname 在 DNS 第一次返回公网、transport 第二次被诱导到私网时，连接不会发生；混合 A/AAAA、literal IPv4/IPv6、`198.18.0.0/15`、redirect 和 subrequest 均 fail closed。
- 公网 Playwright direct 模式若无法提供 connect-peer enforcement，明确返回 typed unavailable，而不把 URL route 预检伪装成 peer 安全；显式 private/local test profile 只用于调用方已授权的本地 smoke。
- 取消或安全拒绝发生在 `session.request(...)` 返回之后时，response close 仍恰好执行；成功 main response 也不泄漏。
- gzip/deflate/brotli/zstd 压缩炸弹、伪 `Content-Length`、chunked body、warmup 大 body 与大 DOM 都在 owner cap 处停止；不会先生成超限 decoded bytes / Python HTML 字符串。
- Web DEBUG 和 diagnostic JSON 中不出现 secret sentinel、正文 sentinel、HTML sentinel、URL query/userinfo；只出现 digest / length / safe URL projection；持久化文件权限符合约束。
- challenge 普通正文引用（例如新闻正文中的 “access denied”）不单独判 blocked；confirmed challenge 无论 HTTP status 是否恰好在旧集合内都走同一 fallback 决策。
- DuckDuckGo 显式 no-results 是合法空结果，已知 result shape 正常解析，未知 HTML shape 是 `search_provider_response_invalid`，不是 `total=0` 成功。
- 超大/稀疏文档、单行超长文件和超大目录不会在 business cap 前构造完整 file/tree/results；输出或 typed failure 可解释是否扫描完成。
- smoke 的伪造 `ok=true`、错误 sentinel、challenge、Playwright 未执行、negative-control 未失败等扰动不能得到 PASS。

## 3. 设计与控制真源对齐

- `docs/engine/design.md` 的“边界与职责”、“ToolDefinition 与 ToolCallable”和“ToolExecutionOutcome”章节明确：Engine 只消费 schema 与 `ToolExecutor` outcome，不持有具体业务工具实现、工具内部资源治理或 batch 执行策略。因此本计划不修改 Engine/Host，只沿现有 `ToolDefinition` / typed outcome 投影资源和 provider 失败，不把显式参数或安全事实塞进 `extra payload`。
- `dayu/tools/__init__.py` 模块 docstring 把 `dayu.tools` 定位为 Host / Engine 之外的业务工具实现与 provider；`dayu/documents/__init__.py` 模块 docstring 把 `dayu.documents` 定位为不属于 Host、Engine、Service、UI 或 Fins 的共享文档处理基础包。因此 Web policy 留在 `dayu.tools.web`，有界 Source 读取 primitive 才进入 `dayu.documents`，后者不得 import tools/Host/Engine/Fins。
- `dayu/runtime/__init__.py` 模块 docstring 明确列出层中立 `diagnostic_text`、`json_redaction` 与 digest 能力；Web diagnostic projection 复用这些 primitive，不复制另一套通用 redaction 规则，也不把 Web URL/正文语义下沉到 runtime。
- `dayu/tools/doc_tools.py` 中的 `_ProcessBackedDocToolCallable` / `_build_doc_process_target` 是 Doc 工具 process-backed execution 的直接代码真源；Web 路径的 process target 同样以 `dayu/tools/web/web_tools.py` 的现有实现为准。本计划不把进程 kill 当输入 cap，而让 child 在分配前自行收口。
- `docs/phaseflow-umbrella-optimization-control.md` 的 Slice 切分约束要求按 semantic owner、validation matrix 和 failure blast radius 切分，小型 cleanup 默认不超过 3 slices，超过时必须用直接证据说明不能合并。本计划使用 4 slices，因为 Web OOM/provider outcome、secret 持久化/CI oracle 与 Documents temp/resource 是三组不同 blast radius；详见 §8。

## 4. Scope、最小扩展与非目标

### 4.1 实施允许范围

计划内生产/诊断 consumer 文件仅限：

- `dayu/tools/web/`
- `dayu/tools/doc_tools.py`
- `dayu/documents/`
- `utils/diagnose_web_access.py`
- `utils/smoke_web_ci.py`
- 对应测试：`tests/tools/web/`、`tests/tools/test_doc_tools_provider.py`、`tests/documents/`
- 按 README trigger 决策需要时：`dayu/config/README.md`、`tests/README.md`；最终 accepted plan / gate bookkeeping 由 controller 更新 `docs/host/issues-implementation-control.md`，不由 implementation slice 越权修改。

`dayu/tools/doc_tools.py` 是 `read_file/search_files/list_files` business cap 的直接 owner（见 §5 DR-019）；`utils/diagnose_web_access.py` 是诊断 raw egress、artifact 和 storage-state 直接 owner；`utils/smoke_web_ci.py` 是 Web smoke PASS classifier 的直接 owner。三者不是 broad scope expansion，也不能由允许目录内新建孤立 helper 替代。若 implementation handoff 未明确授权这三个直接 consumer，必须停止，不得只实现未接线的 helper。

### 4.2 非目标

- 不实现 Fins upload allowlist、CN/HK downloader provenance、upload symlink policy 或 LLM-facing upload/download security schema。
- 不实现仓库级通用 tool-security framework、capability system、通用代理服务或 OS sandbox。
- 不修改 Host/Engine lifecycle、EventLog、memory、trace、tool accept barrier、ToolRuntime timeout 或 UI/Web app。
- 不修 `docs/reviews/repo-review-20260712-093647.md` 中 DR-016 的 OpenAI invalid-UTF8 payload；R3-E 只闭合 Web tool/diagnostic 直接 owner，Engine runner diagnostic 归属对应 Engine diagnostic WU。
- 不把 DR-032 中 `smoke_async_agent_providers.py`、Host multiturn/conversation-memory smoke 的广义 oracle 一并带入；它们分别归 provider smoke / Host memory smoke owner。R3-E 只修直接消费 Web diagnostic schema 的 `smoke_web_ci.py`。
- 不承诺外部站点 live smoke 稳定；外部 URL 保持 diagnostic-only，local deterministic fixture 才能成为 hard gate。
- 不保持旧 diagnostic artifact schema、旧自动 storage-state 输出或旧 silent-empty DuckDuckGo 行为的兼容分支；按全新 contract 更新 producer 与 consumer。

## 5. Finding ownership、直接证据与唯一裁决

| Finding | Semantic fact | Correct owner | Drifted location 与直接代码证据 | 裁决 | 计划落点 |
|---|---|---|---|---|---|
| DR-004 | “本次网络连接目标是否允许”必须由 connect-time owner 对原 URL、redirect 和实际 peer 一次性承诺；DNS 预检不是连接事实。 | `dayu.tools.web` 的 Web egress policy + HTTP transport；Playwright 只能消费可证明的 safe profile。 | `web_tools.py:2869-2901` 先独立 DNS；`:2904-2945` 把检查结果当 URL 安全事实并启发式放行 `198.18/15`；`web_fetch_orchestrator.py:693-707` 随后让 requests 再解析/连接且只复查字符串；`web_playwright_backend.py:928-934` subrequest 同样只跑谓词。 | accepted | S1 |
| DR-015 | wire/decoded/warmup/DOM 上限必须在对应完整 materialization 前生效。 | Web resource budget owner；codec 流式 decoder、warmup reader、browser serialization gate。 | `web_fetch_orchestrator.py:552-578` 对整包调用 `gzip.decompress`/brotli/zstd 后才 `len`；`:1127-1149` warmup `stream=False` 且未关闭 response；`:1416-1419` main path 才有 bounded materialize；`web_playwright_backend.py:1241-1246` 先 `page.content()`/完整 innerText，无 DOM cap。 | accepted | S2 |
| DR-016 | 生产 Web diagnostic 不得记录完整业务正文；限长可逆前缀也不是安全投影。 | `dayu.tools.web` Web diagnostic projection owner；日志 caller 只能传 projection。 | `web_tools.py:1194-1207` 无条件 stringify payload；`:2264-2293` 把含完整 `content` 的 `success` 展开进 DEBUG；`web_fetch_orchestrator.py:739-748` conversion context 保存完整 `raw_content_text`。 | accepted（仅 Web owner 部分） | S3 |
| DR-019 | read/search/list 的输入分配预算必须先于 file/tree/results 物化；ToolRuntime truncate 不能反向保护 producer。 | `dayu.tools.doc_tools` 的工具业务预算/输出 contract；`dayu.documents` 只提供层中立 bounded Source snapshot primitive。 | `doc_tools.py:1364-1387` 收集并排序全部 tree 后切片；`:1581-1621` `readlines()` 后才选范围/构造 content；`:1921-1963` processor 全量 search 后才投影；`:1991-2002` `read()`/split 全文件；`:2412-2432` truncate 仅是后置声明。`markdown_processor.py:418-431` processor 构造也会整文件 `read_text().splitlines()`。 | accepted | S4 |
| DR-032 | PASS 必须由独立可扰动 oracle 证明；artifact producer 的 `ok` 只能是 observation，不能自签 PASS。 | `utils/smoke_web_ci.py` local fixture/oracle classifier；测试提供 negative controls。 | `smoke_web_ci.py:1207-1231` 只要求 producer 自报字段存在；`:1393-1425` 直接信任 requests/fetch `ok`；`:1583-1641` 据此产出 PASS；`:1593-1603` browser 失败降 diagnostic-only；`tests/tools/web/test_smoke_web_ci.py:72-104` fake runner 可直接写 synthetic success。 | accepted（Web smoke 范围） | S3 |
| DR-033 | diagnostic raw requests/browser 必须复用生产 egress/diagnostic owners；登录态持久化须显式 opt-in、0600、可过期。 | 共享 Web egress/diagnostic contract；`utils/diagnose_web_access.py` 仅做 CLI wiring 与 artifact lifecycle。 | `diagnose_web_access.py:1132-1152` 自建 literal-host policy；`:1287` 自动 redirect；`:1302-1317` 完整 response 后保存原文前缀；`:1672-1699` storage dir 自动推导输出；`:1931-1952` browser 完整 DOM 并明文写 storage state；`:1981-1987` 保存 text/html 前缀和 network URLs。 | accepted | S1（egress）+ S3（projection/lifecycle） |
| DS：redirect response leak | 非最终 response 的唯一 owner 必须在任意离开路径关闭它。 | HTTP redirect/request response lease owner。 | `web_fetch_orchestrator.py:696-723` 在 request 返回后，`:704` cancel、`:707` response URL reject、`:710-717` hop/Location/next URL reject 都可在 `:723` close 前抛出；`probe :1187-1207` HEAD success 不 close，GET 在 `:1222` cancel 时也先于 `:1224` close 抛出。 | accepted | S1 |
| DS：challenge false positives | blocked 是证据组合后的业务结论，普通文本引用/基础设施 header 不是单独充分条件。 | `web_challenge_detection.py` challenge evidence/decision owner。 | `web_challenge_detection.py:17-49` 含宽泛 `not a robot`、`access denied`；`:135-146` 任一 content signal或 vendor header直接 `True`；`web_fetch_orchestrator.py:1453-1462` 原始 HTML命中即失败。 | accepted | S2 |
| DS：challenge/status mismatch skips fallback | fallback 动作由 challenge decision 决定，不应再依赖另一处分散的 status allowlist。 | challenge fallback decision owner，`web_tools.py` 只执行动作。 | `web_tools.py:2029-2054` 只有 `challenge_detected and status in {401,403,429,503}` 才 fallback；例如 challenge + 500 既不进入该分支，`:2054` 的 escalation status 集合也不含 500，最终落 generic HTTP failure。 | accepted | S2 |
| DS：DuckDuckGo shape drift silent empty | “明确零结果”与“无法识别 provider response”是不同事实。 | `web_search_providers.py` DuckDuckGo parser outcome owner；tool adapter 投影 typed failure。 | `web_search_providers.py:691-728` 对任意 HTTP 200 HTML只遍历 `div.result` 后直接返回列表；selector shape 变化与真实 no-results 都返回 `[]`；`search_public_web :271-283` 立刻把它提交为 `total=0` 成功。 | accepted | S2 |

Source finding 计数：accepted **10**；rejected-with-reason **0**；deferred-with-owner **0**；needs-more-evidence **0**。表中 DR-016/DR-032 的括号是当前 WU 的 owner 范围裁剪，不改变该源 finding 在 R3-E 的 accepted 状态；其非 Web 子问题列在 §4.2，不能被解释为已修复。

## 6. 核心实现决策（不重新设计 Host/Engine）

### 6.1 Web egress contract

在 `dayu/tools/web/web_egress_policy.py` 建立局部、强类型 owner：

- `WebEgressPolicy` 冻结 scheme/port/private-network/browser mode 与 resolver；`authorize_http_target(url, stage)` 返回 `AuthorizedHttpTarget(normalized_url, hostname, port, approved_addresses)`。
- 默认只允许 `http:80` / `https:443`；userinfo 一律拒绝。非默认端口如确有产品需求，必须成为显式 provider config allowlist，不能由 URL 自行扩权。
- hostname 的所有 A/AAAA 必须均属于允许集合；混合公网/私网 fail closed。删除 `_looks_like_public_hostname` + fake-IP 启发式；`198.18.0.0/15` 默认拒绝。未来 fake-IP/proxy 部署由独立显式 deployment profile owner 设计，不在本轮用兼容分支放行。
- S1 按当前锁定的 `requests==2.33.1` / `urllib3==2.6.3` 实现 target-bound transport：每一 hop 先产生不可变 `AuthorizedHttpTarget`，再为该 target 建立私有 `HTTPAdapter` + `HTTPConnectionPool` / `HTTPSConnectionPool`。自定义 `HTTPConnection` / `HTTPSConnection` 只 override `_new_conn()`：它从 `approved_addresses` 中按确定顺序选择 numeric IPv4/IPv6，使用 urllib3 的 socket timeout/options 建立直连 socket，且底层 `getaddrinfo` 如被调用也只允许接收 numeric literal，不得再接收原 hostname。
- `_new_conn()` 在返回 socket 前用 `getpeername()` 规范化 IPv4/IPv6（含 IPv4-mapped IPv6）并验证 peer 仍属于该 target 的 `approved_addresses`；peer mismatch 立即关闭 socket 并抛 typed egress failure。urllib3 只在 `_new_conn()` 成功后才进入 TLS handshake / HTTP request，因此 peer proof 先于 HTTP request bytes。
- connection pool 的 `host` 仍是 `AuthorizedHttpTarget.hostname`，不替换为 IP；这保证 HTTP `Host` header、`HTTPSConnection.server_hostname` / TLS SNI 与 certificate `assert_hostname` 都使用原始 IDNA hostname，只有 TCP destination 使用 approved numeric address。不支持 ambient/environment proxy；若未来需要 proxy，必须由独立可证明 egress profile 所有。
- 每个 target-bound pool 把同一 immutable `approved_addresses` 传给每个新 connection；现有 urllib3 `Retry(connect=3, read=3, status_forcelist=...)` 可保留，但 connect retry 只能在该 pool 内重建 socket，不得重新 resolve/authorize，也不得切换到 approved set 之外。redirect 则不属于同一 target retry；每个 Location 必须重新产生新 target 和新 target-bound pool。
- target-bound adapter/pool 的 lifetime 由 response lease 持有；成功返回时随 response 一起 transfer，拒绝/取消/异常时在同一 `finally` 关闭 response 和 pool。不将 target 藏入模块全局、thread-local/contextvar 或 requests `extra`，不 monkeypatch 全局 DNS，不暴露 urllib3 对象给 caller。若上述 2.6.3 扩展点无法在发送 request 前证明 peer，S1 停止，不能退化为 response 后检查。
- Playwright route URL 预检保留为 defense-in-depth，但不再宣称 connect-peer 安全。默认公网 direct Playwright 在没有可证明 egress enforcement 时返回 typed `browser_egress_policy_unavailable`；`allow_private_network_url=True` 仅作为调用方明确授权的 local/dev profile供 deterministic fixture 使用。可信 egress proxy/profile 是后续部署能力，本轮不伪造。
- `utils/diagnose_web_access.py` 删除自建 `_validate_url_safety` 决策，raw requests、tool fetch、Playwright 采样均由同一个 `WebEgressPolicy` 决定；diagnostic CLI 只选择 policy profile。

### 6.2 Response lease 与资源预算

- `_request_with_safe_redirects` 的 contract 改为返回明确 response lease/context manager。response 一旦创建，除最终 lease transfer 外的所有退出都在当前函数 `finally` 关闭；caller 在复制必要 status/header/body facts 后关闭 lease。
- fetch result 不再携带 live `requests.Response`。challenge detector 接受复制后的 status/header/有界 evidence；成功、challenge、empty、exception 均不延长 socket 生命周期。
- `WebResourceBudget` 是 Web 局部唯一真源，至少包含 `wire_body_bytes`、`decoded_body_bytes`、`warmup_body_bytes`、`browser_dom_chars`、`browser_text_chars`、`diagnostic_error_chars`、`diagnostic_events`；构造期校验为非 bool 正整数。provider config 若开放 override，必须一次性形成完整 typed value并传入 HTTP/Playwright/diagnostic，不允许各 caller 自设常量。
- wire body 按 chunk 累计；gzip/deflate/brotli/zstd 使用增量 decoder，每次 decoder 输出前只允许 `remaining + 1`，每层 content-encoding 的 intermediate output 同样受 decoded cap。没有可用 streaming API 的 codec fail closed 为 unsupported encoding，不回退整包 decompress。
- `Content-Length` 只做早拒绝；伪长度、无长度、chunked 仍以实读字节为真源。超限路径关闭 response 并返回稳定 `response_body_too_large`。
- warmup 使用 `stream=True`，只消费 owner 声明的小预算（Cookie 只需 response headers 时可零 body关闭）；probe HEAD/GET 全部使用 lease并关闭。
- Playwright 预检只允许一次 `page.evaluate(_BUDGETED_DOM_METRICS_SCRIPT, limits)`；script 使用 `document.createTreeWalker()` 遍历 element/text/comment node，只累加 tag/attribute name/value 的保守序列化上界与各 text node `nodeValue.length`，达到对应 `limit + 1` 立即停止，只返回有界 counters/booleans。预检 script 不得拼接 HTML/text，不得读取 `outerHTML`、`innerHTML`、`textContent` 或 `innerText`，也不得调用 `page.content()`。
- `_BUDGETED_DOM_METRICS_SCRIPT` 的计数公式冻结为：element 加 `2 * localName.length + 5`（即使 void element 也保守计 closing overhead）；每个 attribute 加 `name.length + 6 * value.length + 4`；text node 对 DOM 加 `5 * nodeValue.length`、对 text 加 `nodeValue.length`；comment 加 `nodeValue.length + 7`；doctype 加 name/publicId/systemId 长度与固定 32 字符 overhead。乘数是 HTML escaping 的保守上界，不是精确 serializer；任一 counter 超限后不再遍历后续 node。实现若证明该公式对当前 `page.content()` 并非保守上界，必须更严格地 fail closed 或回到 plan/re-review，不得改用 `outerHTML.length`。
- DOM 保守上界或 text counter 超限时，在调用 `page.content()` / full text extraction 前关闭 context/process result，并分别返回 `browser_dom_too_large` / `browser_text_too_large`。预检通过后才允许做一次完整投影，并在返回 Python caller 前再验证实际长度，用于捕获动态 DOM 变化。该 contract 保证“预检不自行生成完整 HTML/text，且超限时不跨进程传输完整值”；不承诺控制 Chromium 已构造 DOM 的内存、遍历 CPU，也不消除预检与投影之间的动态变更，这些由现有 process-backed timeout/kill 降低风险并列为 residual。

### 6.3 Diagnostic projection 与 storage state

- 在 `dayu/tools/web/web_diagnostics.py` 定义 Web 专属 `WebDiagnosticProjection` builder，复用 `dayu.runtime.diagnostic_text` / `json_redaction` / digest primitive；不把 URL/HTTP业务规则下沉到 runtime。
- URL 只保存 `scheme + IDNA host + allowed port + path`；删除 userinfo/query/fragment。正文、HTML、raw bytes、tool success `content`、page text 和 stdout/stderr 中任意业务 payload不保存可逆 prefix，只保存 `length` 与 `sha256` digest。错误文本先替换敏感值再有界截断。
- response header 使用最小 allowlist；`set-cookie`、authorization及任何 secret-like key 不保存值，必要时只保存 header presence/name。network event同样只保存安全 URL投影、method/resource type/status，不保存 request headers/body。
- `web_tools._log_fetch_diagnostics` 只接受 projection type；success log不得展开 `success` payload。`_FetchContentRuntimeContext` 删除完整 `raw_content_text`，只持有 bounded、不可逆或已脱敏 evidence。
- diagnostic artifact schema bump，不兼容读取旧 schema。`utils/smoke_web_ci.py` 与 tests 同步更新；禁止旧字段 fallback。
- storage state 默认不输出；`storage_state_dir` 不再自动推导 output。只有显式 output + 正 TTL opt-in 才允许持久化，父目录固定 `0700`。写入流程必须在目标同目录创建本 run 专用 `0600` temp，序列化后 flush + `fsync`，用 `os.replace()` 原子替换 final，再确认 final `0600`；禁止让 Playwright 直接写 final path。
- 每次 diagnostic 启动时，artifact lifecycle owner 先扫描显式目标目录中本 owner 命名的 orphan temp 和过期 final；orphan temp 直接删除，final 按正 TTL + mtime/自身 metadata 过期删除，不对任意文件做宽泛 cleanup。正常 exception/cancel 删除本 run temp，失败且已 publish 的 final 也删除；成功 final 保留到 TTL。artifact 只记录 sanitized path label/是否使用，不记录绝对 secret path或内容。
- `SIGKILL` / 主机崩溃时 Python cleanup 不保证；可能留下有界 temp 或尚未过期的 final。此 residual 的当前 owner 是 `utils/diagnose_web_access.py` storage-state lifecycle，当前 destination 是 S3 的原子写 + startup cleanup + TTL contract；若产品要求无下次启动也能强制删除，则进入后续 workspace secure-artifact cleanup WU，不在本计划伪称已保证。

### 6.4 Challenge 与 DuckDuckGo outcome

- `BotChallengeDetectionResult` 增加封闭 decision（`none` / `suspected` / `confirmed`）和 evidence class；兼容 boolean property 不保留，所有 consumer穷尽匹配 decision。
- vendor-specific challenge token/明确 challenge endpoint可单独 confirmed；`access denied`、`not a robot`、普通基础设施 header等宽泛信号只有与 error status、vendor gate header或第二个独立信号组合才 confirmed。suspected 只进入有界 diagnostic，不把正常 2xx正文改成 blocked。
- `challenge_fallback_action(decision, browser_availability)` 是唯一动作 owner；confirmed challenge无论 status是否在旧集合都尝试可用的安全 browser profile，browser不可用后统一 typed blocked/unavailable；caller不再重复 status gate。
- DuckDuckGo HTML parser 先做 challenge/login shape 判定，再独立返回 `results`、`explicit_empty` 或抛 `WebSearchProviderResponseError(reason=response_shape_changed)`。已知 result shape 冻结为：顶层 `div.result`，每项必须有 `a.result__a`、非空规整 title，且 `href` 必须能解析为非空 `http` / `https` 目标；`a.result__snippet` / `div.result__snippet` 可选。parser 必须检查全部 container 后再按 `max_results` 投影，不得因早停跳过 malformed ratio。
- malformed item 定义为缺 anchor、title 为空、href 非字符串/为空或解析后不是 HTTP(S)。存在 result container 时，若有效项为 0，或 `malformed_count * 2 > container_count`（严格超过 50%），整个 response 为 shape drift；否则丢弃少数 malformed 并返回有效项，同时产生有界 diagnostic count。
- explicit no-results 只在“没有 `div.result`、没有 challenge/login 证据，且存在唯一 `.no-results` 元素，其规整文本精确命中封闭 allowlist `No results.` / `No more results.`”时成立。标记缺失或未知文本不是空成功。
- challenge/login shape 任一成立都覆盖 result/no-results：共享 challenge owner 返回 `confirmed`；或 DOM 含已知 anomaly/challenge form/marker；或存在 password input、form action 命中 `login` / `signin` / `auth`。这些统一投影 typed provider failure，不得与普通空结果共用 `[]`。上述 selector/文本是 provider contract；DuckDuckGo 形状变更时应 fail closed 并通过独立 provider 更新修订，不使用 loose parsing。
- provider fallback loop保留，但记录各 candidate的 typed failure；最终若 shape drift是唯一/最后决定性失败，tool adapter投影 `search_provider_response_invalid` 与业务可读换源 hint，不返回 `total=0`。

### 6.5 Documents bounded input contract

- `DocToolLimits.read_file_max_chars` / `read_file_section_max_chars` 同时传入 business owner，不再只生成后置 truncate declaration。另建不可由 provider 放宽的内部 `DocResourceBudget(max_source_bytes, max_directory_entries)` 作为安全 ceiling；本轮不扩展 packaged config schema。
- `dayu.documents` 增加层中立 `BoundedSourceSnapshot`：只依赖 `Source.open()`，按 chunk复制到有界 `SpooledTemporaryFile`，需落盘时只使用系统 `TMPDIR` 且不在 workspace 创建 durable temp；读取第 `limit + 1` byte即抛 typed `SourceBudgetExceeded`，正常/异常/协作取消 cleanup 由 context manager拥有。它不理解工具名、allowed root或LLM output。
- `SIGKILL` / 主机崩溃时 `BoundedSourceSnapshot` 的 context cleanup 不保证；最多可残留 `max_source_bytes` 内的系统 temp。当前 owner 是 `dayu.documents.processors.bounded_source`，destination 是 S4 使用系统 temp lifecycle 并在 artifact 记录这一 operational residual；若后续需要跨进程 durable janitor，归 Documents temp-artifact cleanup WU，不在 R3-E 引入 daemon。
- `create_doc_file_processor` 接受已受限 Source snapshot；Doc tool在 processor构造前完成 source byte cap。不得先构造 Markdown/HTML/Docling processor再检查。
- raw `read_file` 使用有界增量 decoder/line scanner；单行也按 chunk处理，最多累积 `read_file_max_chars + 1`。指定 line range仍统计必要 line metadata，但不保留范围外内容。返回 `content_truncated`、`returned_chars`、`scan_complete`；只有完整扫描时 `total_lines` 为精确整数，否则为 `null`，不得伪造总行数。
- `list_files` 用 bounded iterator + 固定大小 heap维护确定性结果；最多扫描 `max_directory_entries`。完整扫描时返回精确 `total` / `scan_complete=true`；命中 entry cap时返回已有 bounded结果、`total=null`、`scan_complete=false`、`truncated_reason=directory_entry_limit`，并给出缩小 directory/pattern的业务提示。不构造全 tree list。
- `search_files` 对目录 entry、每个 source bytes、累计 matches同时计数；raw text按 chunk/行窗口检索，processor只消费 bounded snapshot，投影最多 remaining hits。entry/source cap使 `scan_complete=false`并列出有界 skipped count/reason；不得把资源跳过伪装成“无命中且完整扫描”。
- 不在 `dayu.documents` 中 import tools；`tests/documents/test_import_boundary.py`继续锁定层中立边界。

### 6.6 冻结的配置、输出与错误 contract

为避免 implementation 再次临场发明双份真源，本计划冻结以下第一版 contract；plan review 若认为某个数值不合适，应直接提出 finding，而不是允许各 consumer 自行选值。

**Web 默认 budget**

| 字段 | 类型 / 默认值 | 语义 |
|---|---|---|
| `wire_body_bytes` | positive int / `25 * 1024 * 1024` | 单次 main HTTP response 实读 wire bytes 上限；沿用当前 ceiling。 |
| `decoded_body_bytes` | positive int / `50 * 1024 * 1024` | 每一 content-encoding 解码层与最终 body 上限；沿用当前 ceiling。 |
| `warmup_body_bytes` | positive int / `64 * 1024` | warmup 最多消费一个现有 fetch chunk；通常收到 header 后立即关闭。 |
| `browser_dom_chars` | positive int / `5_000_000` | `page.content()` 前由 bounded TreeWalker 计算的保守 HTML 序列化字符上界；不是先读取 `outerHTML.length`。 |
| `browser_text_chars` | positive int / `1_000_000` | full text 投影前由 bounded TreeWalker 累加的 text-node 字符上限；不是先读取 `textContent` / `innerText`。 |
| `diagnostic_error_chars` | positive int / `1_024` | 脱敏后错误文本上限；正文/HTML不使用该字段保存前缀。 |
| `diagnostic_events` | positive int / `80` | 单 artifact network event 摘要数；与当前 CLI 默认一致。 |

第一版只在 `WebToolsConfig` 中保存一个完整 `resource_budget: WebResourceBudget` typed value。packaged/effective provider JSON 的唯一路径固定为 `providers["web-tools"].config.resource_budget`；`provider.py::_parse_config` 从已定位到 `web-tools` 的 `spec.config["resource_budget"]` 解析整个 object。object 缺字段、未知字段、bool/零/负数均 fail fast，不做 partial fallback；只有整个 `resource_budget` 缺失时才使用上表的完整默认对象。最小完整示例：

```json
{
  "providers": {
    "web-tools": {
      "config": {
        "resource_budget": {
          "wire_body_bytes": 26214400,
          "decoded_body_bytes": 52428800,
          "warmup_body_bytes": 65536,
          "browser_dom_chars": 5000000,
          "browser_text_chars": 1000000,
          "diagnostic_error_chars": 1024,
          "diagnostic_events": 80
        }
      }
    }
  }
}
```

`allow_private_network_url=false` 时 public Playwright direct固定 unavailable；`true` 时表示调用方显式授权local/private direct profile。第一版不新增声明了却无法执行的proxy字段。

**Diagnostic artifact v2**

- `schema_version` 与 `diagnostic_schema_version` 必填字符串，固定 `web-diagnostics-v2`；`diagnostic_schema_revision` 必填整数 `2`。
- 每个采样 path 必填：`sampled: bool`、`outcome: "completed" | "failed" | "cancelled" | "skipped"`、`safe_url: str`、`elapsed_seconds: non-negative number`。
- 成功内容只允许 `content_length: non-negative int`、`content_digest: "sha256:<64 lowercase hex>"`、`http_status: int | null`、`backend: "requests" | "playwright" | "tool"`。
- 可选 failure 字段只允许封闭 `error_code: str`、脱敏有界 `error_message: str`、`challenge_decision: "none" | "suspected" | "confirmed"` 与枚举 evidence；禁止 `text_prefix`、`content_prefix`、`html_prefix`、raw query/userinfo/header values。
- 最小正例：`{"sampled":true,"outcome":"completed","safe_url":"https://example.com/report","elapsed_seconds":0.1,"content_length":123,"content_digest":"sha256:<64hex>","http_status":200,"backend":"requests"}`。

**Doc tool limits 与 LLM-facing outputs**

- 新建内部冻结 `DocResourceBudget(max_source_bytes=32 * 1024 * 1024, max_directory_entries=10_000)`；字段为非 bool 正整数，实例由 `build_doc_tool_definitions` 创建并随 process target显式传递。它是不可由provider config放宽的security ceiling，因此不修改 `dayu/tools/doc_provider.py`、packaged config或Service assembly。现有 `DocToolLimits`继续只拥有用户可配置的结果/字符限制。
- `read_file` success必填：`file_path: str`、`content: str`、`returned_chars: int`、`content_truncated: bool`、`scan_complete: bool`、`total_lines: int | null`；按范围读取时额外返回必填二元整数数组 `line_range`。`scan_complete=false` 时 `total_lines` 必须为 `null`。
- `list_files` success必填：`directory: str`、`files: list`、`total: int | null`、`returned: int`、`scanned_entries: int`、`scan_complete: bool`、`truncated_reason: "directory_entry_limit" | null`。
- `search_files` success必填：`query: str`、`directory: str`、`matches: list`、`total_matches: int`（只表示本次已返回命中数）、`scanned_entries: int`、`skipped_oversized_files: int`、`scan_complete: bool`、`truncated_reason: "result_limit" | "directory_entry_limit" | "source_limit" | null`。
- 三个 tool description必须在当前schema文本中说明这些字段与“`scan_complete=false`/`total=null` 表示未扫描完整，需要缩小目录、pattern、line range或source”的下一步；不能只引用内部dataclass。
- 最小partial list示例：`{"directory":"/allowed","files":[],"total":null,"returned":0,"scanned_entries":10000,"scan_complete":false,"truncated_reason":"directory_entry_limit"}`。

**稳定 failure codes**

- Web：`permission_denied`、`response_body_too_large`、`browser_dom_too_large`、`browser_text_too_large`、`browser_egress_policy_unavailable`、`search_provider_response_invalid`。
- Doc：`source_too_large` 只用于单一显式read/section source无法产生安全结果；directory search/list优先返回上述partial success，不能把跳过伪装成完整空结果。
- 所有message/hint只写模型下一步所需业务动作，不暴露resolver、adapter、lease、heap、snapshot等内部术语。

## 7. Implementation slices

### Slice 1 — Web egress 与 response ownership

**Owner 闭环**

`WebEgressPolicy -> authorized/pinned HTTP transport -> redirect/cancel response lease -> Playwright safe-profile gate -> diagnostic raw-path wiring`。该 slice先冻结“能否连接、连接到谁、谁关闭 response”，不混入 body/diagnostic内容策略。

**具体文件/模块**

- 新增 `dayu/tools/web/web_egress_policy.py`
- 修改 `dayu/tools/web/web_http_session.py`
- 修改 `dayu/tools/web/web_fetch_orchestrator.py`
- 修改 `dayu/tools/web/web_playwright_backend.py`
- 修改 `dayu/tools/web/web_tools.py`
- 如 provider config需新增封闭 profile字段，修改 `dayu/tools/web/provider.py`
- 修改必要 consumer wiring：`utils/diagnose_web_access.py`
- 测试：`tests/tools/web/test_web_tools_provider.py`、`tests/tools/web/test_diagnose_web_access.py`

**Contract / invariant**

- 每 hop只有 `AuthorizedHttpTarget` 能进入 transport；connect不重新解析未绑定 hostname。
- mixed A/AAAA、fake-IP、userinfo、非法 port、redirect/subrequest拒绝均在发送目标 request bytes前失败。
- 任一 response恰有一个 lease owner；transfer前异常由 callee close，transfer后由 caller close；close异常不覆盖原业务异常。
- public Playwright direct无法证明 peer时 typed unavailable；local private opt-in不外推为公网安全证明。
- diagnostic raw path与生产 fetch使用同一 policy instance/profile。

**Tests 与 expected assertions**

- 用当前 `requests==2.33.1` / `urllib3==2.6.3` 的真实 adapter/pool/connection 类跑 loopback HTTP 与本地 CA HTTPS 集成测试；断言 TCP destination 是 approved literal，HTTP Host、TLS SNI 和 certificate hostname 均是原 hostname，peer mismatch 在 HTTP request bytes 前关闭 socket。
- 注入 resolver/socket connector fake：owner 第一次解析公网，之后若有人尝试解析原 hostname则返回私网；断言 target-bound transport只使用 approved IP，resolver 每 hop 仅调用一次，底层只见 numeric literal。
- connect retry 固定测试 `test_egress_pinned_retry_uses_same_approved_addresses`：第一个 socket 模拟 timeout/RST，后续 retry 成功；断言每次 `_new_conn()` 都收到同一 immutable approved set，实际 connect 从未离开该 set，原 hostname 没有第二次 resolve，且 retry 中的 SNI/cert host 仍为原 hostname。另测一个所有 approved address 都失败的路径，断言 retry 耗尽后 typed failure 且无 fallback DNS。
- literal/private/link-local/metadata IPv4、IPv6、IPv4-mapped IPv6、mixed A/AAAA、`198.18/15`、userinfo、自定义端口矩阵全部 fail closed；显式 local profile仅放行local fixture。
- 302 public→private、response.url private、meta refresh private、Playwright subrequest private均拒绝。
- response spy覆盖：request后 cancel、response URL reject、missing/invalid Location、next-hop reject、too many redirects、HEAD success、HEAD fail→GET cancel、warmup success/error、main success/error；每个非空 response `close_count == 1`。
- diagnostic URL策略测试不再 monkeypatch自建 literal predicate，而断言共享 policy调用与安全错误投影。

**精确 validation commands**

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py -q -k 'url or egress or redirect or response or peer or playwright'
pytest tests/tools/web/test_diagnose_web_access.py -q -k 'url or egress or redirect'
pyright
git diff --check
```

**Residual risks**

- requests/urllib3 pinning依赖 2.33.1/2.6.3 的 adapter/pool/connection 扩展点；S1 completion artifact 必须记录 tested versions，任一依赖升级都由 Web transport owner 重跑 HTTP/HTTPS/retry 集成矩阵。若只能在收到 response后验证 peer，该方案不成立。
- 默认公网 Playwright direct fail closed会降低部分 client-rendered站点可用性；这是无法证明 peer安全时的明确产品降级，不得静默恢复旧行为。可信浏览器 egress proxy由后续 deployment WU拥有。

**Stop condition**

- 无法在发送 HTTP request bytes前证明实际 peer属于 authorized set；或实现需要 monkeypatch全局 DNS / lazy import seam / broad proxy framework时，停止并回到 design，不进入 S2。
- 任一 redirect/cancel/safety负例的 response close次数不确定，停止。

**Completion signal**

- 上述 egress/close matrix通过；生产与 diagnostic consumer都已接线；没有新增 Host/Engine/runtime import反向依赖。

### Slice 2 — Web 资源预算与 challenge/search outcome

**Owner 闭环与 blast radius**

`WebResourceBudget -> bounded HTTP/codec/warmup/browser producer -> challenge decision / DuckDuckGo parser outcome -> tool typed outcome`。本 slice 的直接 blast radius 是 Web child 进程内存/稳定性与 Web 搜索/抓取业务 outcome；不修改持久化 diagnostic schema 或 CI PASS classifier。

**具体文件/模块**

- 新增 `dayu/tools/web/web_resource_budget.py`
- 修改 `dayu/tools/web/web_fetch_orchestrator.py`
- 修改 `dayu/tools/web/web_playwright_backend.py`
- 修改 `dayu/tools/web/web_challenge_detection.py`
- 修改 `dayu/tools/web/web_search_providers.py`
- 修改 `dayu/tools/web/web_tools.py`、`provider.py`，必要时修改 `web_tool_projection_text.py`
- 更新 `dayu/config/README.md` 的 `web-tools` provider config 契约；packaged `dayu/config/tool_discovery.json` 保持缺省 `resource_budget` 以测试“整体缺失使用完整默认”，不复制一份数值真源。
- 测试：`tests/tools/web/test_web_tools_provider.py`

**Contract / invariant**

- wire和每层 decoded count在 append/decoder output 前检查；任何路径不得调用无上限整包 decompress。
- warmup/probe/main/browser 消费同一 typed budget；browser 只使用 §6.2 冻结的 bounded `page.evaluate` DOM/text walker 做预检，预检不得读取 `page.content()` / `outerHTML` / `innerHTML` / `textContent` / `innerText`。
- challenge decision 是封闭枚举；fallback 不再二次依赖 status 集合。
- DuckDuckGo 只按 §6.4 的已知 result、explicit-empty、malformed threshold 和 challenge/login shape 分型；shape error 不能成为 completed empty result。

**Tests 与 expected assertions**

- codec table-driven tests：gzip/deflate/raw-deflate/brotli/zstd（依赖存在时）正常多 chunk、exact limit、limit+1、压缩炸弹、多层 encoding；断言超限前最大累计对象不超过 cap + 单 chunk 且 response 关闭。
- warmup 大 body/伪长度/chunked 测试断言不完整下载。DOM/text fake 必须 spy `page.evaluate` 的 script/arguments；断言只调用 bounded TreeWalker script，断言 script 不含 forbidden API，并断言预检超限时 `page.content()` 与 full text extraction 均零调用。另覆盖预检通过后动态 DOM 变大的二次实际长度拒绝。
- challenge 矩阵：强 vendor token、宽泛文本单信号、header 单信号、组合信号、2xx/401/403/429/500/503；普通正文不 blocked，confirmed + 500 仍调用一次 fallback，safe browser unavailable 产生稳定 typed outcome。
- DuckDuckGo parser：有效 known shape、snippet 缺失、封闭 explicit no-results 文本、未知 selector/no-results 文本、challenge/anomaly HTML、password/login form、malformed ratio 分别为 0%、50%、>50% 和 100%；只有明确 no-results 完成空成功，shape drift 投影 `search_provider_response_invalid`。
- provider config tests 断言 `providers["web-tools"].config.resource_budget` 完整对象成功，整体缺失使用默认，object 少任一字段、多未知字段或含 bool/非正整数均 fail fast。

**精确 validation commands**

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py -q -k 'body or decompress or warmup or playwright or challenge or duckduckgo or resource_budget'
pyright
git diff --check
```

对新增 owner 模块单文件覆盖率必须达到至少 80%；implementation artifact 记录：

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py -q --cov=dayu.tools.web.web_resource_budget --cov=dayu.tools.web.web_challenge_detection --cov=dayu.tools.web.web_search_providers --cov-report=term-missing
```

**Residual risks**

- DOM gate 不使用完整 serialization 做预检，但 Chromium 在检查前已构造浏览器内部 DOM；TreeWalker 也会消耗 CPU，且动态页面可在预检后变大。二次长度检查只防止超限值继续投影，不消除 Chromium 峰值；现有 process-backed timeout/kill 降低但不消除该风险。owner 是 Web Playwright backend，destination 是后续 browser sandbox/resource-lane WU。
- DuckDuckGo 是外部 HTML shape；本 slice 选择严格 fail closed，代价是 provider 改版时短期降级。后续 selector 更新归 Web search provider owner，不得临时 loose parse。

**Stop condition**

- 任一 codec 只能先整包解压才能检查上限，停止并将该 encoding 明确标为 unsupported，不准退回旧路径。
- Playwright 预检需要 `page.content()`、`outerHTML`、`innerHTML`、`textContent` 或 `innerText` 才能作出 cap 判定，停止并回到 plan/re-review。
- DuckDuckGo 只能通过未知 selector fallback 或把未知 HTML 当空结果才能继续时，停止并返回 typed provider failure。

**Completion signal**

- Web 资源/challenge/parser 矩阵通过；没有无上限 codec/DOM 预检路径；未知 DuckDuckGo shape 不再投影为空成功。

### Slice 3 — Web diagnostic projection、storage-state lifecycle 与独立 smoke oracle

**Owner 闭环与 blast radius**

`WebDiagnosticProjection -> diagnostic artifact/storage-state lifecycle -> parent-owned local fixture ledger -> smoke classifier/negative controls`。本 slice 必须同时迁移 diagnostic producer 与它的唯一 Web smoke consumer，但不携带 S2 的 codec/challenge/parser 实现。直接 blast radius 是 secret/login-state 持久化与 CI 假 PASS。

**具体文件/模块**

- 新增 `dayu/tools/web/web_diagnostics.py`
- 修改 `dayu/tools/web/web_fetch_orchestrator.py`、`web_playwright_backend.py`、`web_tools.py`
- 修改必要 consumer：`utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`
- 测试：`tests/tools/web/test_web_tools_provider.py`、`tests/tools/web/test_diagnose_web_access.py`、`tests/tools/web/test_smoke_web_ci.py`

**Contract / invariant**

- diagnostic 正文只允许 length + digest，不允许 prefix；safe URL 投影不含 userinfo/query/fragment；storage state 默认零写入，显式 opt-in 严格执行 §6.3 的 atomic write / mode / TTL / startup cleanup。
- diagnostic schema v2 producer 与 `smoke_web_ci.py` 在本 slice 同步迁移，不保留旧字段 fallback。
- parent-owned fixture ledger 由 `smoke_web_ci.py` 父进程在启动 diagnostic child 前创建，与本地 `ThreadingHTTPServer` 共生；handler 只追加到父进程内存 typed ledger，child/artifact producer 不能写入。child 终止后先停止 server，再冻结 ledger 并分类；分类完毕后丢弃，不持久化 raw request、raw sentinel 或 header。summary 只能保存派生 count/booleans/digest。
- 每个 local smoke case 由父进程用 `secrets.token_hex(32)` 生成 256-bit run/case sentinel，作为 URL query 中的一次性 token；Web safe URL projection 会删除 query，fixture ledger 只记录 token 的 SHA-256、method、normalized path、response kind/digest、accepted/rejected 与有界 count。缺失/错误/重放 token 由 fixture 拒绝并记 negative observation。
- 父进程在 child 启动前从本次 fixture server 实际注册的 exact response bytes 计算 expected `sha256` 与 length，不从 diagnostic artifact、tool output 或 child stdout 反推。PASS 至少需要：对应 token/path 的 accepted ledger request、artifact content length/digest 等于父进程 expected value、必需 backend execution evidence、对应 negative-control 必须失败。artifact `ok` 只是 observation，不能单独使 case PASS。

**Tests 与 expected assertions**

- secret sentinel 覆盖 success content、raw HTML、query/userinfo、headers、exception、network event、stdout/stderr；日志/artifact 全文均不含 sentinel 或其可逆 prefix，只含预期 length/digest。
- storage-state tests 断言默认不写、父目录 `0700`、temp/final `0600`、flush/fsync + `os.replace`、成功 TTL 保留、普通失败/cancel cleanup、下次 startup 删除 orphan temp/过期 final。不编写伪造 SIGKILL cleanup 保证的测试；用预置 orphan 证明 startup reconciliation。
- ledger 正例断言 lifecycle 顺序、内存范围、每 case 唯一 sentinel、父进程 expected digest 与 ledger freeze-before-classify。分类后任何 child/artifact 都不能改变 ledger。
- required negative controls：artifact 写 `ok=true` 但 ledger 无对应 request；缺失/错误/上一 run sentinel；错误 expected digest/length；challenge endpoint；Playwright 未执行或 wrong backend；negative-control endpoint 意外成功；伪造 schema/artifact。它们均不得 passed；只有独立环境证据证明可选 browser/Docling 依赖不可用时才能 skipped，其余 local negative 为 failed。
- 更新现有锁定 `challenge+ok -> all_success`、browser 缺失 diagnostic-only / exit 0 和 synthetic success artifact 的错误 oracle 测试，不能保留兼容分支。

**精确 validation commands**

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py -q -k 'diagnostic or log or redaction'
pytest tests/tools/web/test_diagnose_web_access.py -q
pytest tests/tools/web/test_smoke_web_ci.py -q
pytest tests/tools/web -q
pyright
git diff --check
```

新增 diagnostic owner 模块单文件覆盖率必须达到至少 80%；implementation artifact 记录：

```bash
source .venv/bin/activate
pytest tests/tools/web -q --cov=dayu.tools.web.web_diagnostics --cov-report=term-missing
```

**Residual risks**

- digest 对低熵 secret 存在字典猜测风险；因此 diagnostic 不对已识别 secret 字段计算 value digest，只记录 presence。正文 digest 只用于 deterministic fixture/内容关联，不作为机密保护承诺。
- `SIGKILL` / 主机崩溃后 storage-state temp/final 可能留到下次 startup/TTL；owner/destination 按 §6.3 执行，本 slice 不声称零残留。
- 外部 live URL 仍只是 diagnostic-only，不做 hard PASS oracle。

**Stop condition**

- diagnostic producer 与 smoke consumer 不能在同一 slice 完成 schema 迁移，停止，不生成兼容读取。
- PASS 无法由 parent-owned fixture ledger/expected sentinel/digest 与 negative controls 独立证明，停止，不保留 `ok=true` 判定。
- storage state 需要直接写 final path、不能限定 owner 命名的 startup cleanup 范围，或企图承诺 SIGKILL cleanup，停止并回到 plan/re-review。

**Completion signal**

- secret scan 为零命中；storage-state atomic/startup matrix 通过；旧 schema 与旧 self-certified PASS 测试已删除或改写为负例。

### Slice 4 — Documents source/read/list/search 预预算

**Owner 闭环**

`DocToolLimits -> bounded Source/directory iterator -> read/search/list producer -> partial/resource outcome`。`dayu.documents`只拥有层中立bounded Source primitive；工具配置、path authority、LLM-facing字段与failure仍由`doc_tools.py`拥有。

**具体文件/模块**

- 修改 `dayu/tools/doc_tools.py`
- 新增 `dayu/documents/processors/bounded_source.py`（名称可在review中调整，但职责不可扩张）
- 修改 `dayu/documents/processors/source.py` / `local_file_source.py` / `_doc_processor_factory.py` 仅为接入有界 Source snapshot所必需的最小接口
- 如 processor constructor确需适配，最小修改 `markdown_processor.py`、`bs_processor.py`、`docling_processor.py`；不得修改 Fins processor contract或引入兼容 facade
- 测试：`tests/documents/test_processors.py`、`tests/documents/test_import_boundary.py`、`tests/tools/test_doc_tools_provider.py`
- 在 S1-S4 行为全部 accepted 后更新 `tests/README.md` 的 Web/Documents 测试分层，不写 gate 流水账。

**Contract / invariant**

- `max_source_bytes`在processor/raw full read前检查实读字节；stat/Content-Length只早拒绝，不能代替stream cap。
- directory iterator和result accumulator分别受entry/result cap；partial必须显式，不能把unknown total写成精确值。
- `read_file_max_chars`是business owner输入；ToolTruncateSpec继续作为Host投影防线，但不再是唯一cap。
- source snapshot/context 在正常、Python exception、协作取消与 resource failure 路径中由 context manager cleanup；`SIGKILL` / 主机崩溃不作保证，只能依赖系统 temp lifecycle 与后续 owner reconciliation。
- `dayu.documents`保持层中立，不import `dayu.tools`/Host/Engine/Service/UI/Fins。

**Tests 与 expected assertions**

- sparse/declared-small-but-stream-large、exact byte limit、limit+1、单行超长、多编码fallback、指定line range；断言bounded read峰值、partial字段、total_lines可知性和cleanup。
- recursive tree超过entry cap；断言结果list长度有界、`scan_complete=false`、`total=null`、稳定reason；小tree保持精确total和确定排序。
- raw search超大无换行文件、late query、processor-supported超限文件、多文件累计match cap；断言不先`read()`/`readlines()`、不创建超限processor、partial/skipped语义正确。
- cancellation在source copy/directory iteration/search窗口发生时停止并cleanup；process target与direct callable投影一致。
- import boundary继续通过；测试不得用旧fixture反逼生产代码保留完整materialization。

**精确 validation commands**

```bash
source .venv/bin/activate
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py -q
pytest tests/tools/test_doc_tools_provider.py -q -k 'list_files or read_file or search_files or limit or bounded or cancellation'
pytest tests/documents tests/tools/test_doc_tools_provider.py -q
pyright
git diff --check
```

新增 bounded source模块单文件覆盖率至少80%：

```bash
source .venv/bin/activate
pytest tests/documents tests/tools/test_doc_tools_provider.py -q --cov=dayu.documents.processors.bounded_source --cov=dayu.tools.doc_tools --cov-report=term-missing
```

**Residual risks**

- exact directory total需要完整扫描；超entry cap时contract改为unknown total。调用方需要按hint缩小目录/pattern，本轮不设计持久cursor。
- path allowlist与open之间的通用file-authority/symlink replacement不是本WU的upload policy；stream cap仍保证资源安全，但本地文件授权竞态应归后续Doc tool file-authority WU。若implementation发现cap校验本身因path swap可被绕过，必须对同一open handle执行实读cap，不能只依赖pre-stat。
- Docling/HTML parser在限定source bytes内仍可能因结构复杂产生较高CPU/对象放大；本轮由source cap+process timeout治理，结构复杂度预算是后续processor-specific hardening。
- `SIGKILL` / 主机崩溃时可能残留一个 `max_source_bytes` 内的系统 temp；owner 为 `dayu.documents.processors.bounded_source`，当前 destination 是系统 `TMPDIR` lifecycle + S4 artifact 记录，需要更强 crash cleanup 时进入后续 Documents temp-artifact cleanup WU。

**Stop condition**

- 若正确实现要求修改`dayu.fins` processor/public contract，停止并请求重新裁决，不在Fins consumer加shim。
- 若partial结果不能在当前LLM-facing output中自足表达`scan_complete/total/reason`，停止并先修owner contract，不返回误导性旧字段。
- 若source cap只通过stat或后置truncate证明，停止。

**Completion signal**

- large/sparse/tree/processor/cancel矩阵通过；producer materialization在cap内；Documents import boundary与process/direct parity通过。

## 8. Slice 数量与依赖

共 **4 slices**，显式超过 control 对小型 cleanup 的 1-3 建议上限：

1. S1 先建立 Web egress、pinned transport、retry 与 response lifetime；S2/S3 的 warmup/diagnostic/browser 只能消费已 accepted 的 S1 contract。
2. S2 闭合 Web 内存/资源 cap 与 challenge/search provider outcome，blast radius 是 child OOM/稳定性和 LLM-facing Web 业务结果。
3. S3 闭合 diagnostic schema/storage-state producer 与它的直接 smoke consumer，blast radius 是 secret/login-state 持久化和 CI 假 PASS。S3 依赖 S2 已 accepted 的 budget/browser outcome，但单独 review，不把 S2 失败与 artifact/oracle 失败绑定在同一 gate。
4. S4 是独立 Documents source/tool budget owner，blast radius 是 Documents child 资源与系统 temp lifecycle；无 Web 业务依赖，按 gate 顺序在 S3 accepted 后单独实施/review。

第 4 个 slice 不是因为文件数或 reviewer ownership，而是 controller 已用直接失败证据裁决：OOM/provider outcome、secret persistence/CI oracle 和 Documents temp/resource 的影响边界不同，将它们留在 3 slices 会使一类 review failure 拖住其他已正确的 owner 闭环。本计划不再拆“每个 codec”“challenge”“diagnostic field”“oracle case”或“read/list/search”；这些在各自 slice 内共享单一 contract 与 validation matrix，继续拆分的 gate 成本高于风险隔离收益。四个 slices 均修改生产或发布门禁行为，必须 per-slice code review，不能合并到 aggregate review。

## 9. Aggregate validation 与 owner propagation audit

全部slice accepted后执行：

```bash
source .venv/bin/activate
pytest tests/tools/web tests/documents tests/tools/test_doc_tools_provider.py -q
pyright
git diff --check
```

并执行以下只读source audit（implementation artifact记录命中并逐项解释）：

```bash
rg -n "gzip\.decompress|\.readlines\(\)|content = file\.read\(\)|allow_redirects=True|page\.content\(\)|diagnostics=\{payload\}|content_prefix|html_prefix|storage_state\(path=" dayu/tools/web dayu/tools/doc_tools.py dayu/documents utils/diagnose_web_access.py utils/smoke_web_ci.py
rg -n "_is_safe_public_url|_validate_url_safety|challenge_detected.*http_status|div\.result" dayu/tools/web utils/diagnose_web_access.py
```

允许命中只能是：明确受budget/decision owner包裹的实现、负面测试fixture或解释性注释；不得存在第二套egress predicate、下游fallback或旧schema兼容读取。

## 10. README trigger 决策

已先读取目标README边界：

- 根 `README.md:14-21` 只面向最终用户，不写内部工具资源预算或developer smoke。R3-E不改变安装、CLI正式入口、工作区最终用户流程或日志位置，**不触发根 README**。
- `dayu/README.md:11-17` 只写已实现的总揽架构/稳定边界；本计划不改变 `UI -> Service -> Host -> Engine`、`dayu.tools`/`dayu.documents`依赖方向或装配关系，**默认不触发 dayu/README**。若implementation实际新增跨包public contract而非本计划的内部bounded Source接口，必须停止并重新做trigger判断。
- 仓库没有 `dayu/tools/README.md` 或 `dayu/documents/README.md`，不得为本WU机械新建。
- `dayu/config/README.md` 当前直接列出 `web-tools` provider config 字段；S2 新增可配置 `resource_budget` 后，**触发 `dayu/config/README.md` 更新**。只说明 `providers["web-tools"].config.resource_budget` 路径、完整字段和 fail-fast 规则，不写 work-unit 流程。
- `tests/README.md:164-179` 当前明确描述Documents/Web/Doc tools测试层级；新增SSRF peer、resource bomb、diagnostic redaction、oracle negative-control和document cap测试属于其读者职责，**触发 `tests/README.md` 更新**。只写accepted后当前测试覆盖，不写work unit流水账。

因此 implementation 预期 README 变化为 `dayu/config/README.md` 与 `tests/README.md`；若最终代码未新增对外 provider budget 字段或上述测试层级，必须在 implementation artifact 记录 no-update 理由，而不是提前修改 README。

## 11. Tool-security 边界与 deferred owner

### 当前 R3-E 必须实现

- Web fetch/redirect实际peer安全、response close、browser safe-profile fail-closed。
- Web wire/decoded/warmup/DOM/diagnostic budget。
- Web tool日志与diagnostic utility的不可逆投影、storage-state显式opt-in/权限/expiry。
- challenge/fallback与DuckDuckGo parser typed outcome。
- Doc tool source/directory/result预预算。
- Web local smoke独立oracle与negative controls。

### 明确未实现 / deferred

| 项目 | 裁决 | Owner / destination |
|---|---|---|
| Fins upload allowlist、upload symlink policy、CN/HK downloader provenance | deferred-with-owner | 独立 Fins ingestion/downloader/tool-security WU；不得借R3-E修改 `dayu.fins`。 |
| repository-wide tool-security framework / generic capability system | rejected-with-reason for R3-E | 当前仅两个局部owner，不需要全仓抽象。出现第三个证据充分consumer后再design。 |
| LLM-facing upload/download security schema | deferred-with-owner | 对应Fins tool schema WU；R3-E只更新本轮Web/Doc typed failure与partial字段。 |
| 可信 Playwright公网egress proxy / browser network sandbox | deferred-with-owner | deployment/browser sandbox WU；R3-E默认fail closed，不伪装安全。 |
| DR-032的provider/Host memory smoke其余部分 | deferred-with-owner | provider smoke与Host memory oracle各自WU；R3-E只闭合`smoke_web_ci.py`。 |
| Engine OpenAI invalid UTF-8 diagnostic | deferred-with-owner | Engine provider diagnostic/redaction WU。 |
| Doc tool通用file-authority/symlink竞态 | deferred-with-owner | 后续Doc tool file-authority WU；R3-E实读cap必须绑定同一open stream，不能因此泄漏资源。 |

这些deferred项不计入§5的10个R3-E源finding计数，也不得在final closeout中写成已修复。

## 12. 为什么没有过度设计

- Web policy/resource/diagnostic均留在单一业务包，只为现有requests、Playwright和diagnostic三个直接consumer提供窄typed接口；不新增全仓security service。
- `dayu.documents`只新增与层中立职责一致的bounded Source snapshot；工具配置和LLM-facing语义不下沉。
- 不引入durable cursor、数据库、后台cleanup daemon、通用proxy或Host状态机。
- 对无法证明peer安全的Playwright公网direct明确fail closed，不用URL重查、response后peer检查或测试特例制造表面安全。
- 不保留旧schema、旧空结果、旧诊断前缀或旧自签PASS兼容逻辑。

## 13. Blocking questions

无。Controller已补充确认：直接代码证据证明 `dayu/tools/doc_tools.py`、`utils/diagnose_web_access.py` 是正确owner/必要调用边界时可纳入plan；同理，`utils/smoke_web_ci.py`由§5 DR-032的直接证据证明为唯一Web PASS classifier，属于完成accepted finding不可省略的最小consumer。

若后续implementation handoff重新排除任一直接consumer，或requests transport无法满足“发送request bytes前peer证明”，则触发对应slice stop condition并返回controller，不允许fallback。

## 14. Plan acceptance 与实现 handoff

Plan-fix gate 只允许修改本 plan artifact 并新增 `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md`。该 gate 已由 `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md` 记录完成；plan re-review 已由 AgentMiMo / AgentDS 双路通过，controller 裁决 artifact 为 `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-rereview-controller-adjudication.md`。

进入 implementation 前，controller 执行：

```bash
git diff --check
git status --short
git diff --name-only
```

由于这两个 artifact 在未跟踪状态时不被普通 `git diff --check` 覆盖，另分别执行：

```bash
git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md
git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md
```

预期：相对 gate 启动时已记录的 dirty baseline，plan gate 只增加 plan、plan review、plan-fix、plan re-review、controller adjudication 与 control-doc bookkeeping；没有 production/test/README 变化；accepted plan commit 后进入 S1 implementation。

Completion report必须包含：

- plan/fix artifact paths
- 已修复 controller IDs
- slice count（及超过 3 slices 的 blast-radius 理由）
- accepted / rejected / deferred / needs-more-evidence source finding counts
- `git diff --check`、untracked no-index whitespace check、status/name-only scope验证
- blocking questions
- 明确确认 plan gate 无 production/test/README 变化，并列出下一步 S1 implementation handoff
