# WU-SEMANTIC-OWNERSHIP-01 设计真源 / 过度设计专项审查

## 结论

审查范围严格限定为 `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`（实际 parent `3410d7422655c56bdf13c643f77c27f40b9d4550`，HEAD `01bbf74c3c408b1b8eaafae20b5a9c68cb733c3f`），包含 `b1a0631f` 本身；共 1,317 个文件、`+191,967/-19,116`。唯一设计真源只采用 `docs/host/design.md` 与 `docs/engine/design.md`。

本轮确认 **22 个 material findings：11 个高、11 个中**。问题动机成立，而且严重性高于上一轮：上一轮把 accepted plan 当成授权，因而错误放行了 Doc/Web/Fins/CLI 的公开策略、状态机与 schema。本轮把 plan、review、implementation/control artifact、README 和测试只作为被审对象或漂移证据，不再作为授权依据。

没有修改生产代码或测试；唯一新增文件是本 review artifact。

## Findings

### F-01 — 高 — `TOOL_CALL_REQUESTED` 的安全参数真源被下游参数名黑名单替代

- **语义 / contract**：`TOOL_CALL_REQUESTED` 应同时保存原始 normalized arguments identity 与 producer 生成的 LLM-safe 参数投影；二者 digest 可以不同。当前 ordinary ToolRuntime 却保存原参数并强制两者 digest 相等，随后 accepted-result projection 再按 key 拼写猜测“是否安全”，任一命中便丢弃整个业务 query。
- **正确 owner**：先由 `docs/host/design.md` 解决自身 `:1613`（安全投影 digest 不要求等于 raw digest）与 `:1629`（又要求相等）的矛盾；代码 owner 应是 ToolRuntime / tool producer 的 accept atom，projection 只校验、消费，不重新定义敏感字段 taxonomy。
- **漂移与直接证据**：`dayu/host/tool_runtime.py:4357-4365,4406-4424,5338-5348` 直接持久化 accepted arguments 并强制 digest 等同 raw normalized digest；`dayu/host/waiting.py:2336-2383` 反而已有 `llm_safe_replay_arguments` 的正确 producer-side 路径。`dayu/host/accepted_result_projection.py:540-576` 新增 `api_key/token/secret/password/*path*/path_` 递归黑名单。`tests/host/test_accepted_result_projection.py:751-796,941-969` 固化 limited signal，并证明同一 projection 扩散到 RunInput、Memory、Compact、Trace；实际消费者还见 `dayu/host/durable/memory.py:421-429`、`dayu/host/compact_material.py:2561-2598`、`dayu/host/run_input.py:3147-3181`、`dayu/host/tool_trace.py:1101`。
- **为什么失败 / 成本放大**：合法 `file_path`、`scope_token` 会整段不可读；未列入的秘密别名仍可泄露。安全语义由 producer、wait producer、projection 三处不一致地产生，再被四个消费者共同固化。
- **推荐修正边界**：先裁决设计真源矛盾，再由唯一 producer 产出 typed safe arguments / semantic query；删除 projection 层 key blacklist 与兼容分支。
- **验证点**：raw digest 与 safe-projection digest 可独立校验；敏感值在 producer atom 已脱敏；合法路径/token 名业务字段仍有可读业务投影；四个消费者只读同一 atom。

### F-02 — 高 — Service 用工具选择隐式签发 wait-poller 权限，并硬编码 30s / 5s / 8 策略

- **语义 / contract**：同步 wait observation 的单次超时、close drain 和 outstanding cap 会决定 wait 是否永久进入 `LOST`，以及 Host 关闭是否有界返回。当前只要 scene 选中 Fins awaiting tool，Service 就自动构造启用态 policy。
- **正确 owner**：Host 拥有 wait runtime 机制和状态语义；composition root 只能在显式 registry **与显式 policy** 存在时启动。`docs/host/design.md:2386-2394` 只授权 finite-positive 机制，`:2437` 明确“显式配置后启动；默认不启动”，没有授权 30/5/8 或 tool-selection 即授权。
- **漂移与直接证据**：`dayu/host/wait_adapter.py:90-97,427-459` 固定 30 秒、5 秒和 8 个调用；`:1093-1154,1736-1766` 把超时映射为 durable LOST / close 行为。`dayu/service/host_assembly.py:268-291` 在 override 为 `None` 时因 scene 工具选择自动 `WaitPollerRuntimePolicy()`；`tests/service/test_host_assembly.py:335-381` 固化自动启用。
- **为什么失败 / 成本放大**：工具可见性同时变成后台 runtime authority；慢但有效的 provider 超过隐式 30 秒会从“未知”被升级成 durable LOST，调用方从未选择该政策。
- **推荐修正边界**：保留 Host typed mechanism，但 Service 不从工具选择合成治理政策；policy 数值必须来自设计批准的显式 assembly/config input。
- **验证点**：无显式 policy 时不启动 poller；显式 policy 端到端生效；timeout、capacity、close 对状态的影响与同一 policy snapshot 同源。

### F-03 — 高 — Doc 单源 32 MiB 硬失败与 `source_budget_exceeded` 无设计授权

- **语义 / contract**：所有 Doc processor、章节、读取和搜索输入都被固定为 32 MiB；声明长度超限立即拒绝，实读 `limit+1` 也拒绝；read/section 路径向工具调用方公开稳定错误码和 LLM retry 文案。
- **正确 owner**：产品是否存在该输入预算、默认值、declared/observed 判定和 outcome 必须先由唯一设计真源授权；代码执行 owner 才是 Doc provider / document source boundary。当前不能用一个自称“内部、不可配置”的 dataclass 替代设计裁决。
- **漂移与直接证据**：`dayu/tools/doc_tools.py:87-88,118-150,1200-1208,1247-1293` 固定并贯穿全部工具；`dayu/documents/processors/bounded_source.py:26-58,164-205,276-314` 新增 `BoundedSourceSnapshot` 生命周期与 declared/actual hard fail；`tests/documents/test_processors.py:206-261`、`tests/tools/test_doc_tools_provider.py:387-412,953-971` 固化 exact/overflow 和公开失败。
- **为什么失败 / 成本放大**：合法大财报在 processor/转换前整体失败；不准确或不可信的 `content_length` 可制造假阳性；部署方无法按来源、机器或文档类型调整。错误码、hint、processor 状态机和测试共同形成迁移面。
- **推荐修正边界**：无设计授权时移除硬上限和公开错误 contract；如确需预算，先设计 policy owner、值来源、override 与 outcome，再以 typed input 注入 Doc producer。
- **验证点**：exact/+1、声明大但实际小、实际大但声明缺失、read/section/search outcome、LLM error 文本和配置 override 同源。

### F-04 — 高 — Doc 10,000-entry partial scan / source skip 依赖文件系统前缀，却被提升为 LLM contract

- **语义 / contract**：`list_files` / `search_files` 观察 10,000 个 entry 后停止；list 返回 `total=null` / `directory_entry_limit`，search 跳过大文件并返回 `source_limit` / `skipped_oversized_files`，另有 `result_limit` 闭集原因。
- **正确 owner**：partial / complete 是 Doc tool result 的业务事实，应由一个 Doc result producer 产生；其存在、上限、遍历顺序、reason enum 与 retry 语义仍需设计真源先授权。
- **漂移与直接证据**：LLM-facing 文本在 `dayu/tools/doc_tools.py:698-705,846-854`；`list_files` 在 `:1535-1586` 对 `iterdir/rglob` 的已观察前缀达到 cap 即 break；`search_files` 在 `:1684-1757` 依次处理 directory cap、oversize skip、result cap。`tests/tools/test_doc_tools_provider.py:818-847,1027-1078,1109-1134,1184-1196` 固化字段和枚举。
- **为什么失败 / 成本放大**：cap 后的匹配文件不可见；同一逻辑目录可因文件系统枚举顺序不同得到不同 partial 结果。模型被要求围绕实现偶然顺序重试，schema、提示和测试又把这些原因变成稳定产品语义。
- **推荐修正边界**：无授权时恢复 deterministic complete scan，只保留已设计的输出截断；若确需 partial，设计 continuation / stable traversal、complete owner、reason enum 与 oversized-source 语义。
- **验证点**：匹配位于 cap 前后、不同创建顺序同树一致、oversized 文件不被误报为无命中、continuation 完整性、LLM schema 与 runtime payload 同源。

### F-05 — 高 — Web egress / DNS pin / custom-port / proxy 禁令成为未授权权限 contract

- **语义 / contract**：本范围把原有粗粒度 local/private 拒绝强化为：公网 profile 禁止自定义端口、local suffix、benchmark/metadata/private/reserved 地址；DNS 任一 answer 非公网即整体拒绝；连接固定 numeric destination；transport 明确禁用环境和显式 proxy；工具公开 `permission_denied`，搜索过滤 URL。
- **正确 owner**：威胁模型、地址/端口/proxy authority 和 policy fields 属于 Host/ToolRuntime 权限政策；Web transport 只执行 attempt-local typed decision。`docs/host/design.md:2205-2213` 授权 ToolRuntime 拥有 policy，但没有授权上述具体规则。
- **漂移与直接证据**：`dayu/tools/web/web_egress_policy.py:1-4,16-27,128-151,192-223,252-367` 自称唯一 owner；custom port / mixed DNS fail 在 `:312-350`。`dayu/tools/web/web_http_session.py:281-313,448-511` 拒绝 proxy 并禁 `trust_env`；`dayu/tools/web/web_tools.py:1907-1943,2132-2139` 投影公开权限失败；`tests/tools/web/test_web_tools_provider.py:1116-1422` 固化端口、benchmark、mixed DNS 和 transport。
- **为什么失败 / 成本放大**：合法 8080/8443 公网站点失败；混合 DNS 即使有可用公网地址也失败；企业必须经 HTTP(S) proxy 的部署全面失去 Web 访问。基础设施选择被冒充业务权限事实。
- **推荐修正边界**：先在 design truth 定义威胁模型，再把 port/address/mixed-DNS/proxy 拆为 typed policy，由 Host snapshot 决策，transport 机械执行。
- **验证点**：公网自定义端口、mixed DNS、redirect、mandatory proxy、搜索过滤、拒绝原因与 policy decision digest 同源。

### F-06 — 高 — Browser capability 与 private-network authority 被同一个 bool 耦合

- **语义 / contract**：默认 `allow_private_network_url=false` 同时使 Playwright public path 返回 `browser_egress_policy_unavailable`；要启用 browser fallback，调用方反而必须打开私网访问。
- **正确 owner**：browser availability/capability 与 address authority 是两个独立事实，应由 Host/ToolRuntime 的两个 typed decision 拥有；browser transport继续逐请求执行 public/private policy。
- **漂移与直接证据**：`dayu/tools/web/web_tools.py:180-203,919-998,1907-1973` 由同一 bool 构造 policy并公开错误；`dayu/tools/web/web_playwright_backend.py:1013-1060,1385-1391,1570-1575` 在非-private profile下 worker前 fail closed；`tests/tools/web/test_web_tools_provider.py:4065-4112` 明确锁定 public/default browser worker不执行。
- **为什么失败 / 成本放大**：正常公网 JS、SSL、编码或 challenge fallback 默认不可用；开启 browser 却扩大到 localhost/private/metadata 类地址，形成 capability 与 authority 的反向绑定。
- **推荐修正边界**：拆分 `browser_enabled/public_browser_profile` 与 `allow_private_network`；启用 browser 不得授予私网权限。
- **验证点**：private=false + public JS 页面可 browser 成功；private URL 仍拒；browser 不可用保留原始失败；启用 browser 不改变地址 authority。

### F-07 — 高 — `WebResourceBudget` 把七个无关限制绑成 complete-object 公共 schema

- **语义 / contract**：25 MiB wire、50 MiB decoded、64 KiB warmup、5M DOM、1M text、1024 error chars、80 diagnostic events 被放进一个必须一次写全、拒绝未知/缺失字段的 provider config；超限公开 `response_body_too_large` / browser DOM/text 错误。
- **正确 owner**：资源治理必须先有 design truth；HTTP、browser、diagnostics 各自消费 owner-specific policy projection，不应由一个 tool-local god budget锁死共同演进。
- **漂移与直接证据**：`dayu/tools/web/web_resource_budget.py:1-5,18-44,75-139` 固定值和全对象解析；`dayu/tools/web/provider.py:110-136` 暴露 config；`dayu/tools/web/web_tools.py:169-203,979-990,2140-2148` 暴露稳定错误；`dayu/config/README.md:204-226` 发布完整 schema；`tests/tools/web/test_web_tools_provider.py:2780-2824,2905-2968,3174-3257,3988-4025` 固化。
- **为什么失败 / 成本放大**：合法大 PDF/HTML 在转换前失败；只调整诊断字段也必须复制全部 HTTP/browser 字段；任一字段演进要求 config、provider、多个 backend、README、测试同步。
- **推荐修正边界**：无授权时不承诺这些上限/错误 schema；如需治理，拆分 typed policy并由 attempt snapshot 注入，设计默认、override 和错误投影。
- **验证点**：wire/decoded exact/+1、错误 Content-Length、各编码、多层解码、大 PDF、DOM/text；单 owner override不要求重声明无关字段。

### F-08 — 高 — Fins batch 同时使用显式 token 与隐式 task/thread owner，形成双重 authority

- **语义 / contract**：本范围给 `BatchToken` 增加 `owner_token/owner_scope_id`，又从 `asyncio.current_task()` / thread id 派生 hidden scope；begin/commit/rollback/所有 staging write 同时要求两者匹配，并把进程内 owner 信息写入 journal。范围内还改变了 SWAPPED 前后的 commit-point/recovery 语义。
- **正确 owner**：Fins storage transaction 应由一个显式 transaction/token owner定义；设计真源需先授权最小 transaction contract。Host design 明确 Host 不承载 Fins 仓储规则（`docs/host/design.md:41`），并不等于允许本地代码自行增加第二 authority。
- **漂移与直接证据**：`dayu/fins/domain/document_models.py:415-443` 扩展 public token；`dayu/fins/storage/_fs_storage_infra.py:64-108,180-255,385-522` 绑定 ContextVar/task/thread scope并拒绝 non-owner；`:709-739` 持久化 owner token/scope/PID/hostname/path；`tests/fins/test_fins_storage_provider.py:2388-2436` 固化 child task 即使共享 repository 也失败；`tests/fins/test_fins_storage_atomicity.py:575-601` 固化 recovery phase结果；`dayu/fins/README.md:103,456-460` 发布为稳定 contract。
- **为什么失败 / 成本放大**：合法 begin→helper/child task 委派被拒；显式 token 无法完整表达 authority；durable journal保存无跨进程恢复意义的 task id/随机 token，形成隐藏第二真源。
- **推荐修正边界**：使用显式 transaction object/token 作为唯一 authority；若需要 scope限制也必须成为显式 contract；journal只保留 crash recovery必需事实。
- **验证点**：同一显式 transaction可按授权跨 helper/task使用；非持有者拒绝；recovery不依赖进程内 owner id；每个 phase的 commit事实唯一。

### F-09 — 高 — Fins 用业务 source meta 实现未授权的两阶段 acknowledgement 子状态机

- **语义 / contract**：`stage_source_document()` 用 `ingest_complete=false`、空 files/primary meta 表达 blob 写入前“已承认但未完成”；重入必须匹配六个稳定字段，完成态/冲突拒绝；blob写入必须先看到该 meta。
- **正确 owner**：Fins storage 应拥有 source发布原子性，但产品是否需要可见 acknowledgement 子状态必须由 design truth 先决定。最小实现应让 transaction/staging object持有临时 blob，commit时一次发布 final source fact，而不是让业务 meta 兼任 transaction marker。
- **漂移与直接证据**：public API 在 `dayu/fins/storage/repository_protocols.py:190-212`；稳定字段与持久化状态在 `dayu/fins/storage/_fs_source_document_core.py:61-69,1071-1130`；blob 前置检查在 `dayu/fins/storage/_fs_blob_core.py:115-152`；`tests/fins/test_fins_storage_provider.py:1115-1263` 固化 missing handle、幂等、冲突及 false→true；`dayu/fins/README.md:101,456-460` 声明 acknowledgement truth。
- **为什么失败 / 成本放大**：所有 producer 被迫理解隐式两阶段协议；稳定字段、完成态冲突和失败残留成为额外 durable 状态，并与 batch state machine耦合。
- **推荐修正边界**：把 staging 与业务 source fact分离；若保留子状态，先设计可见性、cleanup、retry、recovery和唯一 commit point。
- **验证点**：失败/取消不留下对 read path 可见的半文档；blob不提前发布；唯一 commit一次发布 final source；producer无需各自重造 stable-field规则。

### F-10 — 高 — Fins provenance / revision / LLM citation / read-error 被一次性固化为跨层 contract

- **语义 / contract**：新增四值 durable provider enum，source revision canonical digest，read前后双读 revision、变化即零重试失败，LLM citation 的 `source_type/source_provider`，以及四个稳定 read failure codes。
- **正确 owner**：storage只拥有 canonical provenance/revision；read projection从该事实派生 LLM citation和错误。产品值域、revision字段集合、并发策略和错误语义仍需唯一 design truth授权。`docs/host/design.md:3145` 只要求业务可读 source，不授权这些 Fins 字段和枚举。
- **漂移与直接证据**：`dayu/fins/domain/document_models.py:82-183` 固定 provider/provenance；`dayu/fins/storage/repository_protocols.py:252-285` 新增 public revision/provenance；`dayu/fins/storage/_fs_source_document_core.py:71-75,169-224,499-553` 固定 digest preimage；`dayu/fins/tools/read_runtime.py:137-151,2137-2170,2193-2253,2809-2829` 生成 citation并零重试 fail closed；`dayu/fins/tools/error_contract.py:8-27` 固定错误码。README在 `dayu/fins/README.md:97-99` 冻结，测试见 `tests/fins/test_fins_storage_provider.py:880-964,1001-1112,1440-1519` 与 `tests/fins/test_processor_read_consistency.py:1295-1316,1385-1432,1515-1534`。
- **为什么失败 / 成本放大**：增加 provider 需同步 storage enum、producer、citation label、schema与测试；meta字段演进会改变 cache identity；短暂并发更新直接转成用户可见失败。
- **推荐修正边界**：设计最小 provenance 与 snapshot/read-consistency contract；storage producer、revision helper、read projection各自单一 owner，不从 document id/ingest method反推。
- **验证点**：provider扩展、revision字段演进、并发 snapshot/retry、tool outcome和LLM citation从同一 typed projection派生。

### F-11 — 高 — Fins financial / XBRL 新增整套 public schema 与 LLM 质量语义

- **语义 / contract**：financial schema固定 scale四值、九个 reason、periods/locator/result必填字段及 `partial`矩阵；XBRL schema固定 raw total、deduped count、partial/all-failed规则。两套规则进入 public result types和LLM-facing tool description。
- **正确 owner**：业务 producer事实应由Fins domain contract拥有，LLM自解释投影由tool projection拥有；但字段/值域/质量语义必须先被唯一设计真源授权。Engine design `:18-26` 排除财报语义，不是对任意Fins schema的空白授权。
- **漂移与直接证据**：financial在 `dayu/fins/domain/financial_result_contract.py:25-39,60-89,151-245`，public projection与LLM文本在 `dayu/fins/tools/result_types.py:246-260`、`dayu/fins/tools/fins_tools.py:851-860`；XBRL在 `dayu/fins/domain/xbrl_result_contract.py:17-32,49-68,82-121`、`dayu/fins/tools/read_runtime_helpers.py:1170-1223`、`dayu/fins/tools/fins_tools.py:928-936`。`dayu/fins/README.md:111-113` 自称真源；`tests/fins/test_financial_read_contracts.py:427-580,782-903` 固化矩阵。
- **为什么失败 / 成本放大**：把证据缺失统一解释为 `partial`、封闭reason和全部required字段扩散到每个processor/tool/LLM consumer；raw total加dedup count又增加模型认知和兼容面。
- **推荐修正边界**：先批准最小业务result contract；删除无明确消费者的字段/reason；tool schema和LLM文本从同一个批准的projection helper生成。
- **验证点**：各producer owner-level contract、未知/缺失证据、partial/all-failed、tool schema与LLM文本同源，read side不补写producer事实。

### F-12 — 中 — Host 把未知 `OpaqueEvidenceRef` 默认升格为业务来源

- **语义 / contract**：只有七种私有 denylist kind 被视为内部；任何未知 kind默认渲染为 `kind:id` 并进入LLM source。
- **正确 owner**：`OpaqueEvidenceRef` 只拥有中性 provenance identity；业务 source必须由工具/Fins领域 producer的显式 typed atom产生。`dayu/host/evidence.py:80-102` 已明确“Host不解析语义”。
- **漂移与直接证据**：denylist在 `dayu/host/accepted_result_projection.py:61-71`，默认显示逻辑在 `:644-691`。ordinary/wait producer当前实际写空 refs（`dayu/host/tool_runtime.py:4925-4965`、`dayu/host/waiting.py:2029-2030`）；`tests/host/test_accepted_result_projection.py:534-602` 人工发明 `filing:MSFT-10K` 并固化。
- **为什么失败 / 成本放大**：新增或拼错内部 ref会默认泄给模型；测试承诺了生产者从未定义的业务taxonomy。
- **推荐修正边界**：opaque refs一律保持内部；新增显式 business-source atom和producer validator，Host仅渲染该类型。
- **验证点**：未知 kind永不显示；typed source在RunInput/Memory/Compact/Trace一致显示；内部refs不进入LLM。

### F-13 — 中 — `RunnerSpecificErrorCode` 公共扩展点被任意限制为128字符

- **语义 / contract**：provider/runner专有错误码超过128字符会在构造时抛 `ValueError`，但该类型正是未知runner的公共扩展点，并会进入`run_failed`及Host durable/public serializer。
- **正确 owner**：Engine error-code identity owner；`docs/engine/design.md:61-66,491`只定义value/source扩展契约，没有128限制。展示层若需有界摘要，应是独立diagnostic projection，不应拒绝identity。
- **漂移与直接证据**：`dayu/engine/contracts/error_codes.py:15,50-81,97-151` 定义、构造和序列化；`dayu/engine/__init__.py:114,222`导出；`tests/engine/contracts/test_runner_events.py:253-278`固化129拒绝。
- **为什么失败 / 成本放大**：合法provider code可能被替换成runner exception，丢失原始协议身份；第三方adapter必须适配Dayu任意数字。
- **推荐修正边界**：identity不设任意长度cap；另建design-owned bounded diagnostic view。
- **验证点**：长custom code完成RunnerEvent→EngineEvent→Host serialization；UI/log摘要独立有界且不改identity。

### F-14 — 中 — Challenge heuristic 被升级为三态/evidence/fallback公共状态机

- **语义 / contract**：本范围把旧boolean detector升级为 `none|suspected|confirmed`、六类evidence和 `continue|try_browser|fail_blocked`，再把decision写入diagnostics与smoke gate。
- **正确 owner**：heuristic detector可以是Web业务producer；若状态影响terminal/tool/CI，状态含义、阈值和fallback必须先由design truth授权。若仅为实现heuristic，应保持内部diagnostic。
- **漂移与直接证据**：本范围新增contract在 `dayu/tools/web/web_challenge_detection.py:65-109,164-231`；消费者在 `dayu/tools/web/web_tools.py:2087-2112,2178-2219,2228-2255`；diagnostic投影在 `dayu/tools/web/web_diagnostics.py:148-247`；`tests/tools/web/test_web_tools_provider.py:3388-3457` 与 `tests/tools/web/test_smoke_web_ci.py:891-945` 固化。
- **为什么失败 / 成本放大**：阈值演进需同步fetch、diagnostics、smoke、测试；旧heuristic的假阳性风险被重新分级并固化成公共枚举，而不是被限制在实现内。
- **推荐修正边界**：未获设计授权时只作为non-terminal diagnostic；若保留稳定状态，设计owner、evidence含义和terminal policy。
- **验证点**：正常200正文、vendor token/header、真实challenge、browser可用/不可用；tool、diagnostic、smoke只消费同一decision。

### F-15 — 中 — `web-diagnostics-v2/revision=2` 做了无迁移策略的严格breaking cutover

- **语义 / contract**：新增production typed projection和closed schema；reader/smoke从宽松v1 minimum升级为精确v2/revision2并禁止legacy fields，旧artifact直接拒绝。
- **正确 owner**：若是durable operator contract，应由既有Host Observer/Projection/ToolTrace design授权版本演进；若只是smoke evidence，应保持ephemeral，不在production tool模块宣称稳定schema。
- **漂移与直接证据**：`dayu/tools/web/web_diagnostics.py:1-5,25-29,51-66,148-247,335-439`；`utils/diagnose_web_access.py:3028-3052,3341-3551`；`utils/smoke_web_ci.py:1887-1921,2420-2665`；测试将新schema作为consumer contract。
- **为什么失败 / 成本放大**：任何字段演进都要求tool owner、诊断CLI、smoke和两套测试同步；现有v1 artifact无法读取，且没有design-owned兼容/淘汰策略。
- **推荐修正边界**：先裁定ephemeral还是durable；durable则设计schema owner/version evolution，ephemeral则只验证本次smoke所需最小事实。
- **验证点**：v1处理策略、v2 exact fields、unknown/missing/legacy、producer/consumer版本同源、artifact不与Host trace形成双真源。

### F-16 — 中 — Web diagnostic storage-state 新增独立安全生命周期与file-authority规则

- **语义 / contract**：显式output必须配正TTL并使用host-derived owner filename；目录必须预先为0700，文件0600；运行前清理orphan temp/过期final；atomic publish失败再cleanup，并把状态写入artifact。
- **正确 owner**：这是credential-bearing browser storage的operator/security contract，必须由design truth定义authority、retention、ownership和failure semantics；diagnostic utility只能执行该policy。
- **漂移与直接证据**：`utils/diagnose_web_access.py:201-330,1942-2023`新增lifecycle、TTL、owner命名和权限；`tests/tools/web/test_diagnose_web_access.py:300-375`固化0700/0600、fsync/replace/cleanup。base仅有直接storage-state路径读写，本范围才加入该状态机。
- **为什么失败 / 成本放大**：合法共享私有目录因非0700整条失败；host命名、mtime TTL和cleanup authority均由utility本地决定；credential retention和artifact schema被耦合。
- **推荐修正边界**：由design-owned credential/storage policy提供明确directory authority、retention和atomicity；utility不自行发明owner grammar。
- **验证点**：共享目录、owner冲突、TTL边界、时钟变化、publish/cleanup失败、并发run、权限在不同平台的语义。

### F-17 — 中 — CLI `upload_filings_from` 新增版本化argv公共schema

- **语义 / contract**：CLI输出固定为 `{schema_version:1, commands:[argv...]}`，把`dayu-cli`可执行名、子命令、flag及排序再次编码成机器消费contract。
- **正确 owner**：若产品需要batch-plan，应先由design truth定义业务条目schema及consumer；CLI formatter不应成为schema owner。若只供人类预览，不应宣称versioned public contract。
- **漂移与直接证据**：`dayu/cli/commands/fins.py:73-75,294-330`；根 `README.md:232-265` 明称“公开格式固定”；`tests/cli/test_upload_filings_from_command.py:346-363`按v1解析，`tests/cli/test_fins_commands.py:1122-1141`锁定输出。
- **为什么失败 / 成本放大**：形成“CLI grammar + plan schema”双public API；未来命令改名/参数演进需schema version、migration和consumer同步。
- **推荐修正边界**：决定是否存在机器消费plan；需要时输出领域entry而不是嵌argv，不需要时去掉public/version承诺。
- **验证点**：业务plan round-trip不依赖flag排序；README/测试只承诺design-approved schema。

### F-18 — 中 — 未实现的 Web/WeChat/render 被先做成公开不可用状态机和未来grammar

- **语义 / contract**：未实现能力却固定命令、WeChat service子命令、render positional grammar、诊断文本与exit=1，并通过packaging/help/tests发布。
- **正确 owner**：UI入口必须在产品surface设计后按 `UI -> Service -> Host` 实现；`docs/host/design.md:23-42`只授权层次和多入口共享Host，不授权这些占位命令。
- **漂移与直接证据**：`dayu/wechat/main.py:17-30,34-114`；`dayu/web/__main__.py:16-55`；`dayu/render/render.py:16-65`；`tests/cli/test_public_package_entrypoints.py:103-137,172-217`固化；根 `README.md:7-10,63-70,346-348`发布限制。
- **为什么失败 / 成本放大**：不存在的UX先成为兼容负担；真正实现时要迁就假grammar/exit/text，而且这些stub完全不经Service/Host。
- **推荐修正边界**：未实现前不发布/不冻结子命令；或先设计准确surface再实现完整分层路径。
- **验证点**：公开entrypoint只包含真实能力；测试不再把占位grammar当产品contract。

### F-19 — 中 — `dayu-cli init` 新增whole-tree staging与symlink/containment policy状态机

- **语义 / contract**：普通init不再只是逐文件复制，而是复制现有树到私有staging、整树replace/backup/rollback，并对目标树、祖先、nested entry实施统一symlink和resolved-containment拒绝。
- **正确 owner**：CLI init workspace mutation和file authority应由design truth定义；CLI command可执行该事务，但不能用本地最小修复自行冻结安装/回滚/拒绝语义。
- **漂移与直接证据**：`dayu/cli/commands/init.py:38-39,157-183,256-377,399-467`；`tests/cli/test_init_command.py:109-189,196-282,343-397`固化whole-tree、rollback、SIGINT及symlink拒绝。范围前只有reset whitelist的较窄检查，本范围扩展为普通copy/install contract。
- **为什么失败 / 成本放大**：一次config写入变成额外文件事务状态机；合法symlink-managed workspace被默认拒绝；copy/install/backup/cleanup任一演进都与用户错误文本和测试绑定。
- **推荐修正边界**：先设计init管理哪些文件、是否允许symlink、atomicity与recovery；只对owner-managed路径实施最小必要guard，不把整个config tree变成隐式authority。
- **验证点**：用户自有文件保留、nested symlink、跨盘replace、SIGINT/ENOSPC/rename失败、backup recovery和权限边界。

### F-20 — 中 — Fins direct stream 的missing/duplicate terminal invariant在三层重复拥有

- **语义 / contract**：新增public `FinsDirectStreamProtocolError`；runtime、Service和CLI分别扫描missing/duplicate `RESULT`，原先可合成的failure收口被改为异常路径。
- **正确 owner**：direct stream若获设计授权，应由唯一stream validator / producer boundary拥有“唯一terminal”不变量；Service/CLI只消费typed终态或同一错误。
- **漂移与直接证据**：enum/error在 `dayu/fins/direct_events.py:81-133`；runtime在 `dayu/fins/ingestion_runtime.py:2712-2739`；Service重复在 `dayu/service/fins_direct.py:475-513`；CLI又在 `dayu/cli/commands/fins.py:189-205,675-694`兜底。README在 `dayu/fins/README.md:492-500`、`dayu/service/README.md:15`冻结；三层测试分别位于 `tests/fins/test_fins_ingestion_runtime.py:1564-1656`、`tests/service/test_fins_direct.py:470-495`、`tests/cli/test_fins_commands.py:892-944`。
- **为什么失败 / 成本放大**：同一状态机有三个owner，未来一层合成failure、另一层抛异常即可漂移；用户错误也可能在任一层被重复翻译。
- **推荐修正边界**：先授权direct protocol；只保留一个validator，入口机械映射其typed结果。
- **验证点**：missing/duplicate仅在owner判一次；CLI/Service获得同一terminal/error；取消和producer exception不产生第二terminal。

### F-21 — 中 — HKEX单页100条传输细节被升级为默认拒绝的complete事实

- **语义 / contract**：既有请求仍使用`rowRange=100`，本范围新增：有total且大于返回数失败；无total但恰好100条也推断“无法证明完整”并整体拒绝，没有pagination/continuation。
- **正确 owner**：HKEX discovery/provider pagination contract；complete只能由权威total或完整continuation证明，不能由`row_count == requested_size`反推。
- **漂移与直接证据**：`dayu/fins/downloaders/hkexnews_downloader.py:76-77,115-116,692-728`；`tests/fins/test_hkexnews_downloader.py:410-507`固定100无total拒绝、100且total=100接受、total>rows拒绝；`tests/README.md:186`发布该行为。
- **为什么失败 / 成本放大**：完整但省略total的合法100条响应被误拒；单页实现限制成为任务级失败，而不是partial/continuation或provider protocol error。
- **推荐修正边界**：实现provider continuation/pagination；只有权威证据确认遗漏才失败，未知完整性不得伪装成已知不完整。
- **验证点**：精确100无total、>100多页、total不一致、重复页、空页、取消与partial策略。

### F-22 — 中 — Fins storage 新增全仓路径组件allowlist/containment policy但无设计授权

- **语义 / contract**：document id、ticker、entry name、object key及local URI被集中限制为单路径组件/受控相对key，并对resolved root containment fail closed；规则扩散到source、processed、blob、maintenance和manifest。
- **正确 owner**：Fins storage确实是路径安全的正确执行owner，但允许的identifier grammar、层级ID能力和失败语义仍需design truth授权；“改在正确层”不能替代“设计已授权”。
- **漂移与直接证据**：`dayu/fins/storage/_fs_storage_utils.py:28-176,267-282`新增component/key/containment校验；各仓储调用点遍布 `_fs_source_document_core.py`、`_fs_processed_core.py`、`_fs_storage_infra.py`、`_fs_maintenance_core.py`；`tests/fins/test_fins_storage_provider.py:1335-1360`固化，`dayu/fins/README.md:109`将其声明为稳定边界。
- **为什么失败 / 成本放大**：合法层级document id、平台特定标识或未来namespace被整个仓储面拒绝；identifier grammar与文件布局被绑定，后续演进需迁移所有repository和durable records。
- **推荐修正边界**：保留防目录逃逸目标，但先设计opaque document-id grammar与storage key映射；外部ID不直接充当路径组件，统一编码/映射后再做containment。
- **验证点**：`.`/`..`/separator/drive/absolute、Unicode和合法opaque ID；所有repository共用同一映射；外部ID round-trip不依赖文件系统grammar。

## 工具安全专项说明

本范围存在下列**未授权 tool-security-like / 工具安全代码**：

1. F-01 的 Host 参数名 blacklist：它把字段拼写当作secret/path authority，并影响所有工具的LLM投影。
2. F-05 的 Web egress/DNS pin/custom-port/mixed-address/proxy ban，以及F-06的browser capability/private authority耦合：这是直接的网络权限policy。
3. F-07 的Web硬资源caps属于resource-safety policy；不是权限判断，但会签发稳定失败。
4. F-16 的browser storage-state 0700/0600、TTL、owner命名与cleanup authority。
5. F-19 的CLI init symlink/containment/replace policy，F-22的Fins path-component/containment policy。
6. Web diagnostics header/error allowlist位于 `dayu/tools/web/web_diagnostics.py:34-48,335-439`；本轮未单独拆finding，它与F-15的稳定v2 schema一同构成迁移面。

Doc 32 MiB / 10,000 属于局部业务资源策略，不是repository-wide security framework；challenge三态是Web业务heuristic状态机，不应冒充安全证明。范围内没有发现新增的通用全仓tool-security framework、compat shim或Fins remote-egress framework。

## 上一轮候选纠偏

- 上一轮F-01（参数名blacklist）继续成立，但本轮增加了`docs/host/design.md:1613`与`:1629`内部矛盾，以及ordinary/wait producer分裂的直接证据。
- 上一轮F-02（opaque ref）继续成立；accepted plan中的stop condition不再作为授权或否决依据。
- 上一轮F-03只把`source_budget_exceeded`与plan中的另一个名字比较，口径仍错误。本轮不依赖plan字符串，已将该错误码并入F-03的整个未授权Doc输入预算contract。
- 上一轮以R3-E plan放行的`DocResourceBudget`、`BoundedSourceSnapshot`、partial scan、Web egress/resource/diagnostics现全部重新裁决为findings。
- 上一轮以plan放行的CLI upload schema、Fins direct/storage/read schemas也已重新报告；README与测试只证明漂移已固化，不证明设计正确。

## 重要非 Findings / 范围排除

- `dayu/engine/agent.py:_EXCEPTION_MESSAGE_MAX_LENGTH=240`及其异常截断早于本范围，虽当前文件仍存在，本轮不审。
- Web原有粗粒度`allow_private_network_url`、旧challenge字符串集合/boolean blocked、diagnostic CLI/batch/smoke整体存在均早于base；F-05/F-14/F-15只报告本范围新增或强化的contract。
- HKEX `rowRange=100`请求值早于base；F-21只报告本范围新增的“恰满且无total即整体拒绝”。
- CLI upload suffix allowlist主体早于范围；本范围只改错误常量，不报告。
- Runtime finite-number helper主要是对既有finite-positive校验的同义收敛；没有直接证据显示本范围新增不同产品语义，不报告。
- startup recovery batch size 64由 `docs/host/design.md:3505`明确授权，且实现继续分页至完成，不是partial cap。
- `BoundedSourceSnapshot`的1 MiB spool threshold、Fins processor/source-meta LRU容量等只影响内部缓存/物化，不单独签发业务complete/failure事实，未单报。

## 审查方法与覆盖

- 先读取仓库`AGENTS.md`、`CLAUDE.md`及两份design truth；设计授权检索覆盖budget/cap/partial/egress/browser/security/schema/state/error/source/directory/file-authority/compat词族。
- 对exact diff按Host/Engine/Runtime、Web/Documents/Tools、Fins/CLI/Service/WeChat/docs/tests分片；每个候选再用`git diff`/`git blame`核对是否确属范围，避免把base行为误报。
- 交叉读取README与测试只用于证明public/LLM/durable/test contract已固化；计划和既有review只用于候选发现与错误口径对照。
- adversarial pass重点验证了：默认拒绝的合法输入、partial结果的顺序依赖、能力与authority耦合、同一语义多owner、hidden ContextVar authority、breaking schema cutover、LLM-facing枚举扩散及错误码身份丢失。

## 验证

- 静态范围与证据核验：`git diff b1a0631f397967e7530b676a90ef7467d83a1817^ HEAD`。
- 设计真源负向检索确认：两份design均无`DocResourceBudget`、`BoundedSourceSnapshot`、`directory_entry_limit`、`source_limit`、Web egress/resource具体字段与数值、CLI batch schema、Fins financial/XBRL schema等授权。
- 本轮不修改代码，因此未运行pytest/pyright；完成artifact后执行Markdown diff检查与工作区边界检查。

## Residual Risk

- `docs/host/design.md:1613`与`:1629`本身矛盾；在设计真源先修正前，任何accepted-arguments代码修复都存在再次漂移风险。
- 22项finding中多项已同时进入code、README、tests、LLM schema或durable artifact；修复不能只删一个常量或改一段文案，必须先裁决设计，再沿唯一owner删除下游重复contract。
- 本轮只审exact range；base前已有的同类设计问题即使仍在当前文件中，也按用户要求排除。
