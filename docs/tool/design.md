# Tool Design

本文是 Tool 层稳定设计真源。Host / Engine 设计分别归 `docs/host/design.md` 与 `docs/engine/design.md`；Tool 层拥有工具发现配置、工具 schema、工具 LLM-facing 文本、工具输入输出边界、工具网络策略、工具资源预算与工具诊断契约。

Tool 默认通过 `dayu/config/tool_discovery.json` 注册和配置。该文件中的 provider config 是 Tool 策略的配置 owner；Service / Host 只能消费装配后的 ToolBundle 与工具调用结果，不应在下游重新解释或修补 Tool 策略语义。

## 1. LLM-facing Tool Contract

工具 schema 的 name、description、参数说明、枚举说明、错误说明，以及工具返回给 Host 后会进入 RunInput、Memory、Compact、Trace 或 Evidence material 的文本，必须遵守 `AGENTS.md` 的 LLM-facing 文本约束。

工具 schema 必须直接给模型业务可读、当前任务自足的字段含义。不得要求模型理解 Python 类型名、Host / Engine 内部模块名、EventLog id、payload ref、digest、cursor、tool_call_id、内部 policy 名称、临时兼容别名或实现路径。

Tool 层如果需要向 LLM 解释工具请求，必须从工具 schema、参数说明、工具 provider 或工具结果 owner 产生业务可读 query / 参数文本。下游 Host projection 不负责通过字段名黑名单、路径/token 猜测、兼容 fallback 或字符串解析把 raw arguments 补救成 LLM-safe 文本。

## 2. Doc Tools

Doc tools 的稳定输入语义是“读取调用方授权路径下的文档内容并返回有界输出”。Tool 层不拥有未被产品需求授权的单文件 source hard cap 或目录遍历 hard cap。

Doc tools 不得把以下行为作为稳定产品语义、LLM-facing schema 文本或测试契约：

- 单个文档 source 超过固定字节数即失败，例如 `32 MiB`。
- 单次目录遍历观察超过固定 entry 数即停止并返回 partial result，例如 `10,000` entries。
- 因 source byte budget 或 directory entry budget 跳过文件，然后要求模型换小文件或拆目录。

允许的稳定控制是输出侧和调用侧约束：

- `list_files_max`、`get_sections_max`、`search_files_max_results` 等返回项数量上限。
- `read_file_max_chars`、`read_file_section_max_chars` 等返回文本上限。
- 调用方授权路径、文件存在性、文件类型支持、读取错误、取消和超时。

`tool_discovery.json` 中上述 Doc `max` / `limit` 配置实际是 `ToolTruncateSpec` 的配置真源，表示单次工具结果首次返回给模型时的可见项数或字符数，不是单个工具可处理数据总量、Agent / Run 累计额度或工具生命周期上限。工具参数 schema 如需暴露 `limit` / `maximum`，只能从同一份 effective `ToolTruncateSpec` 投影调用校验和 LLM-facing 说明，不得形成第二套独立限制语义。

Doc producer 必须把可截断的完整目标值交给 ToolRuntime；`TruncationManager` 是应用 `ToolTruncateSpec`、保存当前 Run 内剩余内容并生成 opaque `cursor` / `scope_token` 的唯一 owner，模型通过 framework tool `fetch_more` 继续读取。Doc producer 不得在 `TruncationManager` 之前按同一 `max` / `limit` 预先截断或丢弃剩余内容，也不得自行实现另一套 pagination / continuation contract。

如果未来需要输入侧预算，必须先进入本设计文档，明确 owner、用户可见失败语义、LLM-facing 文案、测试契约与绕过/配置方式；不得由实现或测试临时引入。

## 3. Web Tool Configuration Ownership

Web tool 的网络访问、浏览器能力、资源预算、challenge 识别和诊断策略由 `dayu/config/tool_discovery.json` 中的 `web-tools.config` 拥有。默认值属于产品设计，不是 adapter 层私有实现细节。

配置 overlay 仍遵循 ConfigLoader 的整条 record 替换和 typed validation 规则。Tool provider 读取到的 effective config 是执行 Web 策略的唯一配置输入；下游 Host / Memory / Trace 不得从 URL 字符串、错误文本、日志或诊断 artifact 反推 Web 策略。

## 4. Web Egress Policy

Web egress policy 是可配置 Tool 策略，不是 repository-wide tool-security framework。

稳定策略如下：

- 私网 / 本地网络访问控制由配置控制，默认 allow。启用阻断时，Tool 必须拒绝 localhost、private IP ranges、link-local、metadata endpoint 等非公网目标。
- 自定义端口访问控制由配置控制，默认 allow。启用阻断时，Tool 才拒绝非默认 HTTP / HTTPS 端口。
- DNS pin / numeric peer proof 由配置控制，默认 off。启用时，它服务于“实际 socket 连接地址仍符合 egress policy”的证明，避免 DNS rebinding、redirect 或 numeric-address trick 绕过已启用的网络阻断策略。
- Proxy 行为由配置控制，默认不 ban。Tool 可以在检测到 proxy 生效时给出 operator warning，但不得默认禁止企业代理或用户环境代理。

DNS pin / peer proof 不替代 TLS，也不承诺比 `curl` / `wget` 更通用的网络安全模型。它只在对应配置启用时证明“此 LLM-driven Web tool 没有把已禁止的私网/本地目标当作公网 URL 访问”。

## 5. Browser Capability

`browser_enabled` 是独立 Web 能力开关，不能与私网访问权限绑定。现代网页经常需要 JavaScript、cookie、redirect、challenge 页面或浏览器渲染才能取得真实内容；启用 public browser fetch 不应要求同时放开 private-network access。

浏览器能力只表达“Tool 可以使用浏览器获取或渲染公网/允许访问的目标”。是否允许私网、自定义端口、DNS peer proof、proxy 等网络策略，仍由各自配置项独立决定。

## 6. Web Resource Budgets

Web resource budget 是合理的 Tool 资源控制，因为 Web 输入是远端不可信内容：响应体可以很大，压缩内容可以解压后膨胀，浏览器执行 JavaScript 后可以生成巨大 DOM / text，诊断事件也可能无限增长。

Web budget 必须由 Tool config 控制，并采用适合财报场景的较大默认值。财报网页、HTML、PDF 和 filing 附件常常较大，默认值不能按小网页假设设计。

Web budget 不应作为一个必须完整提供的七字段大对象冻结。设计上应按 owner 拆分或等价表达：

- HTTP / transport budget：wire bytes、decoded bytes、body read limit 等。
- Browser budget：DOM size、extracted text size、render wait / warmup body 等。
- Diagnostics budget：diagnostic error text、event count、artifact summary size 等。

配置应支持默认值和局部 override。修改一个预算项不应要求调用方重写其它 owner 的全部预算字段。

## 7. Challenge Detection

Challenge detection 是必需 Web 能力。Tool 必须能识别常见 anti-bot / challenge 页面，避免把 Cloudflare、Akamai 或类似 challenge 页面误当作目标网页正文。

稳定 contract 是能力语义，不是 vendor 规则细节。Tool 可以维护内部 heuristic 和 provider-specific 适配，但对外只承诺业务可理解状态，例如：

- 未发现 challenge，内容可按普通网页处理。
- 疑似 challenge，需要浏览器、重试或诊断。
- 确认 challenge，当前 fetch 未取得目标正文。

Web CI 可以覆盖 challenge 行为和回归，但测试不得把某个 vendor 文案、HTML 片段或临时 header 细节固化成公共语义。

## 8. Web Diagnostics V2

Web diagnostics v2 是 Tool-owned 诊断 artifact contract。它用于给 CI 和 operator 提供稳定的“fetch lab report”：请求策略、redirect、egress decision、challenge detection、browser fallback、错误、证据和摘要。

Web diagnostics v2 可以作为测试和诊断的稳定 schema，但不得成为 Host recovery、Memory truth、Run 状态迁移或业务事实真源。LLM-facing material 只能消费业务可读网页内容、来源文本和必要的中性 unavailable wording，不得要求模型理解 diagnostics schema version、内部事件、payload ref、digest 或 raw diagnostic ledger。

## 9. Browser Storage State Lifecycle

本 WU 不引入稳定 browser storage-state lifecycle。已实现的 owner naming、TTL、权限、atomic publish、cleanup 等 lifecycle 行为不属于当前 Tool design，应从当前实现范围移除。该能力已确认是未来必要需求，由 GitHub Issue [#178](https://github.com/noho/dayu-agent-r/issues/178) 负责先完成设计、再进入实现。

当前稳定设计只允许存在浏览器运行所需的配置输入，例如 storage state path / directory。该配置不等于稳定 credential/session lifecycle contract。未来若要支持登录态、challenge-cleared state 或长期 browser session state，必须先在本节补充：

- state 文件 owner 和用途。
- 存储位置、权限、命名规则和隔离边界。
- TTL、刷新、清理和并发写入规则。
- 对 CI、operator 和 LLM-facing material 的可见边界。

在 Issue #178 完成前，测试不得把 storage-state lifecycle 细节固化成当前 WU 的产品契约。

`<workspace_root>/.dayu/web_tools_storage_states` 属于 Dayu-owned 可重建运行态路径，因此
`dayu-cli init --reset` 随整个 `.dayu` 根删除它不属于本节延后的 lifecycle 实现。Reset 不表达
TTL、refresh、日常 cleanup、credential owner 或并发 publish 规则；这些仍全部由 Issue #178
设计。

## 10. Tool Authorization And Defensive Safety

统一 tool security 的主要目标是权限治理：某次 Host Run / Attempt 中，某个 tool call 被允许
读、写、执行或访问哪些资源。最终授权语义由 Host-owned ToolRuntime governance boundary 拥有；
Tool schema、LLM prompt、Service adapter 和业务工具不得自行成为最终 authorization owner。
具体统一权限模型尚未设计，当前 WU 不实现或猜测 permission schema、role/capability 模型、
sandbox backend 或 policy language。

现有 Tool/provider config 与执行校验保持现状，包括 Doc `allowed_paths`、Web private/custom-port/
DNS/proxy/egress 开关、Web resource budget，以及各工具已有的文件路径限制。它们在统一权限框架
落地前仍是有效约束；不得因为“未来由 Host 统一”而提前删除或绕过。

防御性安全由最接近实际 I/O 的 owner 持续执行：

- filesystem owner 负责 canonical resolve、containment、symlink 和原子写入/替换。
- network/provider owner 负责 redirect、DNS/peer、协议、response/DOM 资源和 challenge 防御。
- process/tool executor 负责实际 capsule、取消/终止、资源释放与 late-publication fencing。
- storage owner 负责 object-key containment、transaction publish 与 crash consistency。

这些机制防的是已获授权调用在真实 I/O 中发生路径逃逸、TOCTOU、资源失控或协议欺骗，不是
第二套业务授权。未来 Host effective authority 必须传到执行边界；Tool 只能在其范围内执行或
更严格地 fail closed，不能用本地配置放宽 Host deny。统一权限迁移完成时应删除旧权限真源，
但保留上述 defense-in-depth enforcement。
