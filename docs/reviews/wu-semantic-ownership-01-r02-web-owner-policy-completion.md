# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy Completion

## 0. Gate 结论与证据规则

- 身份：既有 umbrella work unit `WU-SEMANTIC-OWNERSHIP-01` 内部的 `R02` completion artifact gate；不是新 WU、feature 或 issue。
- 产品裁决真源：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 的 Topic 2 与 Topic 9。Topic 2 冻结五项 bool、三组资源预算、diagnostics v2、challenge detection、storage-state lifecycle 删除与 Issue #178 后续所有权；Topic 9 明确本轮不建立统一 authorization framework，但现有 Web 安全机制必须保留。
- 实施计划真源：accepted plan commit `2d42ceb6bb8fc2b7ad29f5f20dc970a9b391307a` 中的 `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`，再叠加随后由 `R02-S2-DR-01` 精确接受并随 S2 accepted commit 固化的 plan drift 修订。当前 plan 比 `2d42ceb6` 多出的内容只属于该已裁决 S2 drift，不是未裁决计划漂移。
- accepted code：`62d3cfe7be848ac1ef54154240f2b744b707ad7c`。本 completion 只汇总已接受证据，不重跑昂贵完整验证，不修改产品、测试、README、control 或既有 artifact。
- Completion verdict：**R02 implementation/review evidence complete；本 follow-up 已在同一 artifact 中补齐 Controller accepted completion findings `R02-COMP-CV-F01/F02`，可交回 Controller 重新做 completion acceptance。** 这不关闭 umbrella WU，不授权 R03；Controller 重新裁决前不把本地 closure 记录写成 Controller PASS。
- 数字冲突规则：优先级为“较晚 Controller 独立验证或最终双路 re-review”高于“较早 implementation/reviewer 摘要”，精确 coverage JSON 高于整数化 `coverage report` 显示，accepted commit 图高于 artifact 中的短 SHA/working-tree 描述。已发现的冲突均在 §9.3 单独披露，不作猜测或静默取舍。

证据：上述边界来自 controller discussion、accepted plan §1/§15.4、`docs/host/issues-implementation-control.md` 当前 R02 gate 行，以及 `git show` / `git log --graph --decorate` 对下列 SHA 的直接核对。

## 1. 精确 SHA、身份与 review target

| identity | full SHA | parent / 证据含义 |
|---|---|---|
| R02 plan-time base | `02fcc5d8325fc7c3c2ef2f60a049910edb6ebfcb` | parent `d2036b16f82a73880d757ed97f63415c9a9b7712`；`docs: enter R02 remediation plan` |
| accepted plan | `2d42ceb6bb8fc2b7ad29f5f20dc970a9b391307a` | parent `4d2df7036367ec51891d893dcba42a468e3a921d`；`gateflow: accept superseding R02 web owner policy plan` |
| final S1 entry / diff base | `70ffc91742042fdef41068797b9791724ccf5921` | parent为accepted plan；`docs: enter R02-S1 implementation` |
| accepted S1 | `c7b01d824c2e1a48e4d070f34d809eb7c4f97d9f` | parent `70ffc917...`；config owners |
| final S2 entry / diff base | `1f03430e85f794a34e21b34dedfff8784a98f3b3` | parent为accepted S1；`docs: enter R02-S2 implementation` |
| accepted S2 | `d8d6e9d97b4dc0046cd04d0afe1e00af37519773` | parent `1f03430e...`；transport owners |
| final S3 entry / diff base | `08c2380a457292f2428fd990349a45bde61fa2c9` | parent为accepted S2；`docs: enter R02-S3 implementation` |
| accepted S3 | `7e679796657b98201175b38a84e5a9695add5354` | parent `08c2380a...`；diagnostics owners |
| aggregate validation entry / immutable initial review target | `4240ee75e180cc8c9bf534896aca9ee73881c872` | parent为accepted S3；`docs: enter R02 aggregate validation` |
| accepted R02 code | `62d3cfe7be848ac1ef54154240f2b744b707ad7c` | parent `4240ee75...`；包含aggregate finding fixes/re-reviews，`gateflow: accept R02 web owner policy remediation` |

历史 `4d2df7036367ec51891d893dcba42a468e3a921d` 是 superseding plan 接受前的旧 S1 entry，不能替代最终 S1 base `70ffc917...`。Aggregate 初始验证以 `4240ee75...` 为 target；最终 accepted code 由同一父提交上的 aggregate fix 链一次性收敛为 `62d3cfe7...`，所以 completion 的最终代码事实只认后者。

证据：`git show -s --format='%H|%P|%cI|%s'`；accepted plan §1.2/§15.4；S1/S2/S3 implementation 与 Controller validation artifacts；aggregate validation 与最终 post-fix Controller adjudication。

## 2. Plan-entry、S1 与 S2 drift 裁决

### 2.1 Plan-entry

- `R02-B01`：accepted/closed。Production allowlist 精确加入 `dayu/tools/web/web_search_providers.py`；只允许 S1 HTTP budget type 迁移与 S2 shared transport 迁移，不改变 provider 选择、credential、业务结果或 LLM-facing contract。
- `R02-B02`：accepted/closed。Test allowlist 精确加入 `tests/runtime/test_config_loader.py`；只验证 packaged 五 bool 与三组 budget projection，不建立第二份 expected-values 真源。

证据：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`。

### 2.2 S1 drift

- `R02-S1-DR-01`：accepted/closed。四个旧 aggregate type 直接消费者前移至 S1：`dayu/tools/web/web_fetch_orchestrator.py`、`dayu/tools/web/web_playwright_backend.py`、`utils/diagnose_web_access.py`、`tests/tools/web/test_diagnose_web_access.py`。授权仅限 child owner type/signature/forwarding/direct-test migration；不是把整个 S1 定义成“纯 annotation rewrite”。
- `R02-S1-DR-02`：accepted/closed。Aggregate `WebResourceBudgets` 只停在 `WebToolsConfig`；`web_tools.py` 是唯一 child projection point；HTTP、Browser、Diagnostic 不得被下游从 raw fields 重建。
- `R02-S1-DR-03`：narrowed-accepted/closed。S1 utility 的 HTTP/Browser default 直接复用 typed constants；utility-local `1_024` 与 `--max-network default=80` 暂留到 S3，且不得扩散。
- `R02-S1-DR-04`：accepted/closed。增加 direct diagnostic budget node、四文件测试/pyright/source/coverage 时序与两个新增 production coverage candidate。
- Re-review：`R02-S1-DRR-MIMO-01`、`MIMO-02`、`MIMO-Q02` 均 rejected/no-fix；`R02-S1-DRR-DS-01` rejected/no-plan-fix 但保留 implementation verification；`R02-S1-DRR-DS-02` accepted residual verification note、不扩 allowlist。

证据：S1 plan-drift Codex/fix、Controller adjudication、两路 re-review 与 final Controller adjudication；`git diff 2d42ceb6..c7b01d82` 对四文件的直接 diff。

### 2.3 S2 drift

- `R02-S2-DR-01`：accepted/closed-in-plan。`utils/diagnose_web_access.py` 与 `tests/tools/web/test_diagnose_web_access.py` 从 S3 精确前移到 S2，仅为 mandatory typed `WebHttpTransportPolicy` direct caller/fake propagation、同一 raw provider mapping 与 owner assertion；S3 的完整 typed diagnostic config、旧 CLI/default/lifecycle 删除不前移。
- `R02-S2-DR-CV-F01`：accepted/fixed/re-reviewed-closed。旧“全局 `**kwargs` 零命中”假 blocker 改为 transport-specific scan、两个 mandatory signature 的 target-specific AST audit，并把 Playwright Protocol 的两处 `**kwargs` 精确归属为非 transport seam。
- `R02-S2-RR-NOTE-01`：同一 S2 implementation 的执行说明；`NOTE-02`：S3-owned retained fact；`NOTE-03`：S2 docstring hard gate；MiMo 精确 coverage residual：release-blocking implementation gate。
- 历史 dirty implementation 在 drift gate 期间只读保存，plan fix/re-review 未以测试冒充 implementation 恢复；Controller 关闭 drift 后才在同一 S2 恢复实现。该事实由 S2 drift-fix、Controller validation、双 re-review及其 Controller adjudication共同记录。

证据：S2 plan-drift Controller adjudication/validation、Codex fix、两路 re-review、final Controller adjudication；`git diff c7b01d82..d8d6e9d9` 对 utility/test mandatory transport 传播的直接 diff。

### 2.4 逐文件 exact slice drift diff（`R02-COMP-CV-F01` closure）

| slice / file | accepted diff 前的 owner / type / signature | accepted diff 后的 child owner / typed forwarding / direct assertion | 明确未前移的 behavior |
|---|---|---|---|
| S1 `dayu/tools/web/web_fetch_orchestrator.py` | HTTP body helpers、warmup、probe 与 main fetch 都从 `resource_budget: WebResourceBudget` 读取 aggregate fields | `_decompress_limited_response_body`、`_read_limited_response_body`、`_materialize_response_body`、`_fetch_and_convert_content` 精确改为 `http_resource_budget: HttpResourceBudget`；`_warmup_domain` 精确改为 `browser_resource_budget: BrowserResourceBudget`；各 caller 以同名 typed keyword 直接转发；`_probe_content_type` 删除未消费的 budget 参数 | `_send_authorized_request` 仍无 `transport_policy`，仍是 pinned/no-proxy；redirect 逐 hop authorization、mixed DNS、response lease、timeout/cancellation、body materialization 算法不变；S2 sender/transport 未前移 |
| S1 `dayu/tools/web/web_playwright_backend.py` | `_WorkerKwargs.resource_budget`、`_PlaywrightWorkerProtocol`、DOM/text projection、sync worker、process/failure 都依赖 `WebResourceBudget`；process 从 worker aggregate 取 `diagnostic_error_chars` | worker payload key 改为 `browser_resource_budget: BrowserResourceBudget`；`_read_budgeted_dom_metrics`、`_materialize_bounded_page_projection`、`_playwright_sync_worker` 只接 Browser child；`_playwright_process_entry`、`_run_playwright_worker_process` 另增必填 `diagnostic_resource_budget: DiagnosticResourceBudget`；`_fetch_and_convert_with_playwright` 从一个 aggregate 参数拆为 Browser + Diagnostic 两个 child，worker kwargs 不携带 Diagnostic child | browser/private coupling、Playwright import/process start、browser availability、proxy environment、route/navigation、storage-state input 与 error reasons不变；S2 capability/proof/proxy 未前移 |
| S1 `utils/diagnose_web_access.py` | import/constant 为 `_DIAGNOSTIC_RESOURCE_BUDGET: WebResourceBudget = WebResourceBudget()`；requests materialization、Playwright response body 与 browser projection从同一 aggregate 读取 | 拆为 `_DIAGNOSTIC_HTTP_RESOURCE_BUDGET: HttpResourceBudget = DEFAULT_HTTP_RESOURCE_BUDGET` 与 `_DIAGNOSTIC_BROWSER_RESOURCE_BUDGET: BrowserResourceBudget = DEFAULT_BROWSER_RESOURCE_BUDGET`；requests materialization及 `_read_bounded_playwright_response_body(..., http_resource_budget: HttpResourceBudget)` 只收 HTTP child；`_build_playwright_profile` 以 `browser_resource_budget=` 直接转发 Browser child，response body 以 `http_resource_budget=` 直接转发 HTTP child | CLI、storage lifecycle/TTL/owner filename/publish/reconcile、ordinary writer、profile schema、browser availability、`_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 与 `--max-network default=80` 保持；S2 transport 与 S3 cleanup/default 未前移 |
| S1 `tests/tools/web/test_diagnose_web_access.py` | import `WebResourceBudget`；`test_playwright_response_body_projection_uses_exact_bytes_and_budget` 传 `WebResourceBudget(decoded_body_bytes=4)` 与 `resource_budget=` | import `HttpResourceBudget`及两个 owner typed defaults；直接断言 utility HTTP/Browser constants与 owner constants同一；该 node 显式构造 `HttpResourceBudget(wire_body_bytes=4, decoded_body_bytes=4)` 并以 `http_resource_budget=` 转发，exact `4 B`、declared-over、actual-over 三条断言不变 | 其他 lifecycle/storage/CLI/artifact expectations 未改写为 S3 终态；S1 direct node 为 `tests/tools/web/test_diagnose_web_access.py::test_playwright_response_body_projection_uses_exact_bytes_and_budget` |
| S2 `utils/diagnose_web_access.py` | `_build_requests_profile(..., egress_policy: WebEgressPolicy)` 无 transport 参数，调用 `_request_with_safe_redirects` 时也无 policy；tool discovery 在 `_fetch_web_page_definition(options)` 内部自行调用 `_provider_config(options)`，raw requests path 无 parser-owned transport projection，single-diagnostic orchestration 没有一份共享 raw mapping | import owner `_parse_config` 与 `WebHttpTransportPolicy`；`_build_requests_profile(..., *, transport_policy: WebHttpTransportPolicy)` 为无 default 必填 typed keyword，原样转发给 `_request_with_safe_redirects(..., transport_policy=transport_policy)`；`_build_single_diagnostic_payload` 只调一次 `_provider_config(options)`，以 `_parse_config(provider_config).transport_policy` 投影，并把同一 raw mapping 以 `provider_config=` 交给 tool discovery | S3 仍保留未删的 lifecycle/CLI/TTL/owner filename/publish/reconcile、local `1_024/default=80`、`DiagnosticResourceBudget`同源、ordinary writer/profile schema、browser storage input、containment/challenge；`utils/smoke_web_ci.py`、batch 与根 README 零 diff |
| S2 `tests/tools/web/test_diagnose_web_access.py` | exact `_request_with_safe_redirects` fakes 无 transport 参数，没有 parser-owned transport direct assertion | every affected exact fake 增加无 default `transport_policy: WebHttpTransportPolicy`，无 `**kwargs`/shim；`test_requests_profile_forwards_provider_owned_transport_policy` 以 raw `{dns_peer_proof_enabled: true, allow_environment_proxy: false}` 证明 fake 收到的值精确等于 `web_provider._parse_config(raw_provider_config).transport_policy`，并断言 discovery 收到同一 raw object | S3 lifecycle/CLI/default/storage/artifact tests 仍保持原 expectation，包括旧 `browser_egress_policy_unavailable` retained assertion；S2 direct node 为 `tests/tools/web/test_diagnose_web_access.py::test_requests_profile_forwards_provider_owned_transport_policy` |

该表的 S1 事实来自 accepted `git diff 2d42ceb6..c7b01d82`、accepted plan §8.2/§8.4 与 S1 plan-drift-fix；S2 事实来自 accepted `git diff c7b01d82..d8d6e9d9`、accepted plan §9.4/§9.6、S2 implementation 与 Controller validation。因此这里记录的是已接受 diff，不是对当前代码的新解释。

## 3. Exact changed files、分类与无额外 drift 证明

### 3.1 Accepted R02 产品/验证闭集（`02fcc5d8..62d3cfe7`）

`git diff --name-status` 给出以下 18 个非治理文件，全部为 `M`：

- Config（2）：`dayu/config/tool_discovery.json`、`dayu/config/README.md`。
- Production Web owner（9）：`dayu/tools/web/provider.py`、`web_diagnostics.py`、`web_egress_policy.py`、`web_fetch_orchestrator.py`、`web_http_session.py`、`web_playwright_backend.py`、`web_resource_budget.py`、`web_search_providers.py`、`web_tools.py`。
- Utility（2）：`utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`。
- Tests（4）：`tests/runtime/test_config_loader.py`、`tests/tools/web/test_diagnose_web_access.py`、`tests/tools/web/test_smoke_web_ci.py`、`tests/tools/web/test_web_tools_provider.py`。
- README（1 additional）：`tests/README.md`。连同 Config README，共两份 README。

治理文件为 `docs/host/issues-implementation-control.md`、R02 plan 与 66 份 R02 review/validation artifacts；accepted commit 总 changed path 为 86。66 份 artifact 的精确路径见 Appendix A。

### 3.2 Slice 分类

- S1 `70ffc917..c7b01d82`：Config 2、九个 production owner、`utils/diagnose_web_access.py`、三份 tests（config loader/diagnose/provider）、两份 README；四个 S1 drift 文件仅承担接受的 type/owner propagation 时序。
- S2 `1f03430e..d8d6e9d9`：五个 production transport/browser consumer（fetch/session/playwright/search/tools）、diagnostic utility、diagnostic/provider tests、两份 README；mandatory transport drift 的 utility/test包含在此。
- S3 `08c2380a..7e679796`：两个 utilities、diagnose/smoke tests、`tests/README.md`；无 `dayu/**` production code 变化。
- Aggregate `4240ee75..62d3cfe7`：仅 `dayu/tools/web/web_playwright_backend.py`、`tests/tools/web/test_web_tools_provider.py` 加 review finding fixes；未扩大产品闭集。

### 3.3 无额外 drift

- `README.md` 根文档、`utils/diag_web_batch.sh`、`dayu/tools/web/web_challenge_detection.py`、R03、Issue #178 replacement lifecycle、proxy credential schema与统一 authorization production/test实现均不在 accepted changed path。
- `git diff --name-status` 按 S1/S2/S3/aggregate 四区间与各 Controller allowed-file audit一致；aggregate validation记录 exact allowed-file set 为18、extras=0。
- 当前 completion 不把本地预存的 `docs/host/issues-implementation-control.md` working-tree modification纳入自身改动；该 dirty path 在本 gate 前已存在且未被修改。

证据：上述各区间 `git diff --name-status`；aggregate validation §9/§12；各 slice Controller validation 的 allowed-file/zero-diff scan。

## 4. Owner contract

### 4.1 唯一 parser/default/config snapshot

`dayu.tools.web.provider._parse_config` 是 raw Web provider record 的唯一 parser/default owner；它产生 immutable `WebToolsConfig`。ConfigLoader 的 record-replace 语义不改，缺失 field/group 的 local defaults只在 provider parser完成；unknown top-level key在该 owner boundary fail fast。Production `WebToolsConfig(...)` 只有 parser 一个构造点，无第二 default/parser、deep merge、environment inference、compatibility alias或 downstream fallback。

五个 bool：

| field | packaged/typed default | execution owner |
|---|---:|---|
| `allow_private_network_url` | `true` | `WebEgressPolicy` private/local address decision |
| `allow_custom_port_url` | `true` | 同一 egress policy 的独立 custom-port decision |
| `dns_peer_proof_enabled` | `false` | `WebHttpTransportPolicy` numeric peer proof；browser fallback前typed unavailable |
| `allow_environment_proxy` | `true` | attempt-local environment settings、actual selected proxy与browser process proxy env |
| `browser_enabled` | `true` | browser capability；不再从 private permission反推 |

三组预算：

- `HttpResourceBudget(wire_body_bytes, decoded_body_bytes)`：HTTP wire/decoded/search response与direct raw requests materialization。
- `BrowserResourceBudget(warmup_body_bytes, dom_chars, text_chars)`：warmup bounded consume、DOM/text/Markdown与browser worker payload。
- `DiagnosticResourceBudget(error_chars, events)`：failure/process diagnostics投影与network event cap。
- `WebResourceBudgets` 只是无 default/validator/facade 的 frozen pure composition，只存在于 `WebToolsConfig.resource_budgets`；child owners各自校验。`web_tools.py` 是 aggregate到child的唯一 production projection point；probe不消费body budget。

### 4.2 Transport/browser/diagnostics

- `WebHttpTransportPolicy` snapshot 从同一次 parser投影到 fetch/search/raw diagnostic；`_send_authorized_request` / `_send_authorized_plain_request` 每次 attempt 使用同源的 `merge_environment_settings`、`select_proxy` 与 `Session.send` settings。proof+actual proxy在发送前以 `ProxyPeerProofIncompatibleError` fail closed；proxy deny 使用 `trust_env=false` 与空 proxies。
- Browser capability只读 `browser_enabled`；private/custom policy用于导航/route授权，但不拥有 capability。proof-on browser在import/process启动前以 `browser_peer_proof_unavailable` fail closed。Worker payload只持 Browser child；process/failure wrapper另接 Diagnostic child。
- Diagnostics v2/revision2由 `web_diagnostics.py` 拥有；utility/smoke只消费 typed snapshot与投影。Challenge detection owner仍是零 diff 的 `web_challenge_detection.py`。

证据：accepted plan §4、§8-§10；S1/S2/S3 implementation与Controller validation；aggregate validation §6；S2 transport propagation/AST scan。

## 5. Deleted contract 与零残留 scans

| deleted contract | final evidence |
|---|---|
| aggregate `WebResourceBudget` 与七个 legacy flat budget fields | 对 `dayu tests utils README.md` 零命中；由三个 child type + pure composition取代 |
| diagnostic `_StorageStateLifecycle`、output/TTL/owner filename/prepare/reconcile/publish/cleanup | utility/test lifecycle scan零 producer/parser/state/artifact value；只保留negative guards |
| `--storage-state-out`、`--storage-state-ttl` | utility/smoke/batch零命中 |
| diagnostic `--allow-private-network-url` | production utility/smoke/batch零命中；test仅有“命令不得包含旧flag”的negative assertion |
| utility-local `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024` 与 `--max-network default=80` | S3后对utility及其test零命中；`--max-network` absent=`None`，typed `events`为真源 |
| ordinary artifact 新 atomic writer/fsync/replace/rollback contract | added-line writer scan零命中；既有ordinary writers未改 |
| compatibility/default wrapper、第二 transport constructor、raw bool/environment parser、`getattr/hasattr`补偿 | S2/S3 utility scans零命中 |
| Issue #178 replacement storage lifecycle、R03、proxy credential schema、统一 authorization framework/policy DSL/capability token | accepted product/config/utils/tests/root README added-lines零命中 |

证据：S1 legacy scans；S2 type/signature/source scans；S3 lifecycle/CLI/default/ordinary-writer scans；aggregate validation §8、§10、§12；最终 aggregate re-review retained scans。

## 6. Retained contract 与 security closure

- Storage-state只保留显式 read input：`--storage-state-in` 必须是常规文件、UTF-8、JSON object；artifact只投影 `input_used` 等安全事实，不写内容、完整路径、credential或lifecycle字段。`--storage-state-dir` 仍进入provider config并由production resolver读取；credential refresh/retention/publish/cleanup归Issue #178。
- 初始URL与每个redirect hop重做DNS/address/custom-port authorization；dangerous、unspecified、multicast、mixed DNS与按配置private/custom-port deny均fail closed。
- proof-on执行numeric pinned peer match/mismatch；proxy active + proof typed fail；proxy deny直连；browser proof不可用时启动前typed fail。
- Browser navigation/route逐URL egress；process cancel/timeout/no-result/queue/global browser cleanup；browser proxy environment清理。
- HTTP/browser/diagnostic budget exact/+1边界；challenge facts；diagnostics v2/revision2；header/cookie/URL/query/proxy/error redaction；storage containment与symlink防御。
- DuckDuckGo challenge regression保留，challenge detector零diff；root README、batch script零diff。

Controller retained-security matrix：`93 passed, 1 skipped, 81 deselected`；最终aggregate owner tests扩展后相关矩阵记录为 `98 passed, 1 skipped`，两者不是冲突：前者是固定aggregate `-k`命令，后者是aggregate fix后 reviewer引用的扩展集合。唯一 skip是既有 opt-in live browser cleanup pytest；真实本地Playwright gate零skip。

证据：aggregate validation §3/§10；S3 Controller validation；aggregate final MiMo/DS re-review与post-fix Controller adjudication。

## 7. Frozen budget 与 observed metrics

### 7.1 Frozen values

| owner field | frozen value |
|---|---:|
| HTTP wire | `134,217,728 B`（128 MiB） |
| HTTP decoded | `268,435,456 B`（256 MiB） |
| Browser warmup | `1,048,576 B`（1 MiB） |
| Browser DOM | `16,777,216 chars` |
| Browser text | `8,388,608 chars` |
| Diagnostic error | `8,192 chars` |
| Diagnostic events | `512` |

### 7.2 Final representative filing metrics

| metric | observed | ceiling / verdict |
|---|---:|---|
| source / local Content-Length | `1,503,780 B` | fixture exact |
| HTTP wire | `1,503,780 B` | 1.12%，below |
| HTTP decoded | `1,503,780 B` | 0.56%，below |
| Playwright origin response | `1,503,780 B` | below decoded child ceiling |
| rendered DOM | `1,515,212 chars` | 9.03%，below |
| rendered text | `209,272 chars` | 2.49%，below |
| diagnostic events | `6` | below 512 |
| diagnostic error chars | `0` | below 8,192 |
| production warmup | raw diagnostic filing不执行tool warmup | 未观测；direct owner cap=`7 B` case证明bounded consume并close |

S2普通local Playwright补充指标：response `367 B`、DOM `510 chars`、text `118 chars`、events `2`；local HTML/PDF/challenge requests分别为 `238 B`、`652 B`、`75 B`。所有真实case均未出现ceiling-induced business failure，故不触发plan唯一budget stop rule。

Exact/+1 nodes参数化后 `10 passed`：decoded codec `16/17 B`、identity decoded `13/14 B`、warmup `7 B`、DOM/text preflight后actual `limit+1`、Playwright response `4/5 B`、typed diagnostic override `error_chars=37/events=13`且run override events=`7`。

证据：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md` §4/§7；S2 implementation/Controller validation；S3 implementation/Controller validation。

## 8. Slice 与 aggregate tests

以下 Python 命令均在 `source .venv/bin/activate` 后执行。`failed=0` 由各历史 artifact 的 pytest 成功结果和exit `0`直接给出；若 artifact 只保存了一组 direct nodes 的合并结果而没有保存组合 shell 行，下文显式说明，不反向拼造历史命令。

### 8.1 S1 targeted / direct / full

Accepted §8.4 targeted 命令与 implementation 结果：

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'config or resource_budget or egress_policy or provider' -q
```

- exit `0`；`159 passed, 1 skipped, 0 failed`。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md` §5；该命令字面来自 accepted plan §8.4。

S1 diagnostic direct budget node（必填 node id）：

```bash
pytest tests/tools/web/test_diagnose_web_access.py::test_playwright_response_body_projection_uses_exact_bytes_and_budget -q
```

- exit `0`；该非参数化 node 未 skip/未 fail。S1 implementation artifact 保存的执行结果是“该 node + utility local-custom-port node”合并 `2 passed, 0 skipped, 0 failed`，未保存那次合并 shell 行；accepted plan 保存了上述 exact direct command，而后续 final full-file command再次包含该 node。
- 证据 artifact：accepted plan §8.4；`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md` §5。这不声称整份 S3 lifecycle suite 在 S1 已迁移。

Accepted-plan S1 matrix exact command：

```bash
pytest tests/tools/web/test_web_tools_provider.py \
  tests/runtime/test_config_loader.py \
  tests/tools/web/test_diagnose_web_access.py::test_playwright_response_body_projection_uses_exact_bytes_and_budget -q
```

- exit `0`；`212 passed, 1 skipped, 0 failed`；同 target 的 coverage run 产生 `workspace/tmp/.coverage-r02-s1` 与 `workspace/tmp/coverage-r02-s1.json`。
- 证据 artifact：accepted plan §8.4 的命令字面；`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md` §5 的“Accepted-plan coverage test run”。

S1 后续 code-review fix 的最终权威 full command：

```bash
pytest tests/tools/web/test_web_tools_provider.py \
  tests/runtime/test_config_loader.py \
  tests/tools/web/test_diagnose_web_access.py -q
```

- exit `0`；`249 passed, 1 skipped, 0 failed`；唯一 skip 为既有 conditional smoke，不是 owner/direct node。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-codex.md` §4 及其 Controller validation。该较晚命令 supersede corrected implementation/Controller 的 `247 passed, 1 skipped`，所以 S1 final 只认 `249/1/0`。
- 耐久 coverage paths：`workspace/tmp/.coverage-r02-s1-cr-fix`、`workspace/tmp/coverage-r02-s1-cr-fix.json`；早期但非最终的 `workspace/tmp/.coverage-r02-s1`、`workspace/tmp/coverage-r02-s1.json` 保留用于 §9.3 数字冲突裁决。

### 8.2 S2 targeted / direct / full

Accepted §9.6 的四条 exact pytest 命令与 final slice 结果：

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'private or custom_port or proxy or peer or redirect or browser or challenge' -q
pytest tests/tools/web/test_web_tools_provider.py -q
pytest tests/tools/web/test_diagnose_web_access.py::test_requests_profile_forwards_provider_owned_transport_policy -q
pytest tests/tools/web/test_diagnose_web_access.py -q
```

| exact command（按上述顺序） | exit | passed / skipped / failed | 其他 count |
|---|---:|---|---|
| provider focused | `0` | `69 / 1 / 0` | `105 deselected` |
| provider full | `0` | `174 / 1 / 0` | 无 |
| typed transport diagnostic direct node | `0` | `1 / 0 / 0` | 无 |
| complete `test_diagnose_web_access.py` | `0` | `37 / 0 / 0` | 无 |

S2 implementation/Controller artifacts 记录 ConfigLoader 独立 regression 为 exit `0`、`52 passed, 0 skipped, 0 failed`，但没有保存该次执行的原样 shell 行；因此本 completion 不拼造它。该文件随后明确包含在 §8.3/§8.4 已原样归档的 S3/aggregate 四文件命令中。Joint coverage pytest target由 accepted §9.6 的 `coverage run ... -m pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py -q` 执行：exit `0`、`211 passed, 1 skipped, 0 failed`。

证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md` §5/§6 与 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-controller-validation.md` §4；命令字面闭集来自 accepted plan §9.6。耐久 paths：`workspace/tmp/.coverage-r02-s2`、`workspace/tmp/coverage-r02-s2.json`；Controller 独立覆核为 `workspace/tmp/.coverage-r02-s2-controller`、`workspace/tmp/coverage-r02-s2-controller.json`。

### 8.3 S3 targeted / full / initial aggregate

```bash
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -k 'diagnostic or storage_state or challenge' -q
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -q
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
```

| exact command（按上述顺序） | exit | passed / skipped / failed | 其他 count |
|---|---:|---|---|
| S3 focused | `0` | `49 / 0 / 0` | `210 deselected`、3 dependency warnings |
| S3 full | `0` | `258 / 1 / 0` | 3 dependency warnings |
| S3 initial aggregate | `0` | `310 / 1 / 0` | 3 dependency warnings |

证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md` §3 与 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md` §3。Coverage 命令对同三份 S3 tests 得 `258/1/0`，耐久 paths 为 `workspace/tmp/.coverage-r02-s3`、`workspace/tmp/coverage-r02-s3.json`。

### 8.4 Aggregate initial / retained / final

Initial aggregate 命令：

```bash
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
```

- initial exit `0`；`310 passed, 1 skipped, 0 failed, 3 warnings`。
- retained proxy/peer/security exact command：

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'private or custom_port or proxy or peer or redirect or browser or challenge or budget or dns or redact or containment or symlink' -q -rs
```

- retained exit `0`；`93 passed, 1 skipped, 0 failed, 81 deselected`。
- exact/+1 gate 在 aggregate validation §7 保存了 7 个 exact node id 与执行结果：exit `0`、参数化后 `10 passed, 0 skipped, 0 failed`；该 artifact 没有保存一条可原样引用的 shell 行，故本 completion 不拼造。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md` §3/§7；耐久 coverage paths 为 `workspace/tmp/.coverage-r02-web-owner-policy-aggregate`、`workspace/tmp/r02-web-owner-policy-aggregate/coverage-r02-web-owner-policy-aggregate.json`。

Aggregate finding fixes 增加 direct-owner tests，使历史 count 从 `310 -> 329 -> 330`。最终权威 command 仍是上述四文件 aggregate target，后续 fix artifact 原样记录为：

```bash
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
```

- final exit `0`；`330 passed, 1 skipped, 0 failed, 3 warnings`；最终 focused owner matrix `21 passed, 0 skipped, 0 failed, 174 deselected`。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-codex.md` §4.1、`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-codex.md` §4.1 及 final post-fix MiMo/DS/Controller artifacts。最终 coverage JSON 为 `workspace/tmp/coverage-r02-controller-rereview-fix.json`。`330/1/0` supersede `310/1/0` 与 first-fix `329/1/0`。

### 8.5 Count 解释

三条 warning均来自 `edgar` dependency deprecation。所有表中的唯一 skip是环境变量控制的既有 live browser cleanup pytest，不替代且不削弱本轮真实 Playwright hard gate。历史数量变化均为后续 accepted finding direct-owner tests 加入后的预期增长，未用早期 count 覆盖最终命令。

## 9. Per-file coverage 与 JSON

### 9.1 Final accepted tree（权威最终值）

最终值直接读取较晚的 `workspace/tmp/coverage-r02-controller-rereview-fix.json`；该JSON包含全部11个R02 production/utility owner。Aggregate final artifact显式报告其中实际被fix再改的`web_tools.py` / `web_playwright_backend.py`，其余九项与 `workspace/tmp/r02-web-owner-policy-aggregate/coverage-r02-web-owner-policy-aggregate.json` 相同：

| changed production / utility file | covered / statements / missing | exact % | JSON |
|---|---:|---:|---|
| `provider.py` | `106 / 114 / 8` | `92.98245614035088` | final JSON；同aggregate |
| `web_diagnostics.py` | `168 / 182 / 14` | `92.3076923076923` | final JSON；同aggregate |
| `web_egress_policy.py` | `119 / 139 / 20` | `85.61151079136691` | final JSON；同aggregate |
| `web_fetch_orchestrator.py` | `422 / 517 / 95` | `81.6247582205029` | final JSON；同aggregate |
| `web_http_session.py` | `254 / 285 / 31` | `89.12280701754386` | final JSON；同aggregate |
| `web_playwright_backend.py` | `486 / 540 / 54` | `90.0` | final JSON/rereview-fix |
| `web_resource_budget.py` | `72 / 72 / 0` | `100.0` | final JSON；同aggregate |
| `web_search_providers.py` | `258 / 295 / 37` | `87.45762711864407` | final JSON；同aggregate |
| `web_tools.py` | `575 / 712 / 137` | `80.75842696629213` | final JSON/rereview-fix |
| `utils/diagnose_web_access.py` | `721 / 887 / 166` | `81.28523111612176` | final JSON；同aggregate/S3 |
| `utils/smoke_web_ci.py` | `1028 / 1264 / 236` | `81.32911392405063` | final JSON；同aggregate/S3 |

所有最终 production files精确 `>=80%`。`utils/**` 按根AGENTS免覆盖率，但R02仍直接验证，两个utility均大于81%。

### 9.2 Slice JSON

- S1：`workspace/tmp/coverage-r02-s1.json`、`workspace/tmp/coverage-r02-s1-cr-fix.json`；九个production owner逐项存在。
- S2：`workspace/tmp/coverage-r02-s2-controller.json`；五个changed production分别为 HTTP session `89.12280701754386`、fetch `81.6247582205029`、search `87.45762711864407`、Playwright `80.48780487804878`、Web tools `80.0561797752809`。
- S3：`workspace/tmp/coverage-r02-s3.json`；本slice无`dayu/**` production变化，两个changed utilities分别 `81.28523111612176`、`81.32911392405063`。
- Aggregate initial：`workspace/tmp/r02-web-owner-policy-aggregate/coverage-r02-web-owner-policy-aggregate.json`；aggregate final override见上一节。

### 9.3 历史数字冲突裁决

S1 implementation/code-review artifacts把 `web_tools.py` 以coverage默认整数精度显示为 `80%`，并记录 `--fail-under=80` exit 0；但两份现存S1 JSON都给出精确 `550 / 691 = 79.59479015918959%`。这是实际数字冲突，不能把整数显示当成精确 `>=80%`。较晚的 S2 drift re-review Controller adjudication已独立把“约79.9%”登记为release-blocking implementation gate；S2 Controller JSON升至 `80.0561797752809%`，最终accepted tree升至 `80.75842696629213%`。因此本completion：

1. 如实记录S1历史 gate以当时工具整数精度通过，但精确JSON未达80；
2. 不声称S1 JSON exact pass；
3. 以S2已明确关闭的release blocker及最终accepted tree exact JSON作为R02 completion的权威释放证据。

其它显示冲突均属精度/时序：S1 `247` 后续为 `249`、aggregate `310 -> 329 -> 330`、Playwright coverage `80.4878 -> 89.8687 -> 89.9814 -> 90.0`，均采用较晚Controller/final JSON。

## 10. Pyright、baseline、diff、allowlist、docstring、source/transport scans

### 10.1 Pyright 与 baseline registry

- S1、S2、S3、aggregate与aggregate fixes的完整 `python -m pyright` / `pyright dayu tests utils` 均为 `0 errors, 0 warnings, 0 informations`（final摘要写作`0 errors`），覆盖 `dayu/tests/utils`，无exclude/skip/baseline waiver。
- Baseline registry delta：**empty**。没有失败可登记、继承或从baseline移除。
- Accepted plan所谓“六项同指纹”不是“六个历史报错”，而是umbrella plan §7.2定义的六维匹配：命令、test/node、错误类型、首个稳定栈帧/pyright rule、文本指纹、基线 SHA；只有六维相同且与changed owner/propagation无交集才可inherited。本R02 pyright为0，因此六维继承判断未触发，也没有伪造六个failure。

证据：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §7.2；accepted R02 plan §14/§15.4；各slice与aggregate Controller validations。

### 10.2 Mechanical gates

- 每个slice与aggregate/fix均记录 `git diff --check` exit 0。
- Aggregate exact allowed-file audit：18 actual、extras=0；四段commit区间的直接 `git diff --name-status` 与§3一致。
- S1：`WebResourceBudget`及legacy flat fields对`dayu/tests/utils/README.md`零；added-line `lambda|**kwargs|type: ignore|hasattr|getattr`零；production constructor只剩parser。
- S2：provider raw mapping只parse一次；`_build_requests_profile`与`fake_request_with_safe_redirects`有mandatory、无default、typed keyword-only `transport_policy`，无loose `**kwargs`；`transport_signature_audit=2 issues=0`。Utility无第二`WebHttpTransportPolicy(...)`、raw transport bool parser、environment inference、compatibility default/wrapper、`getattr/hasattr`。
- S2 propagation：`_provider_config -> provider._parse_config -> WebToolsConfig.transport_policy -> _build_requests_profile -> _request_with_safe_redirects`；同一raw mapping继续交provider discovery。Production fetch/search callers从同一config snapshot向senders传播。
- 两处保留`**kwargs`：`_BrowserTypeProtocol.launch(**kwargs)`、`_BrowserProtocol.new_context(**kwargs)`；它们镜像Playwright API，归browser Protocol owner，不是transport seam或兼容逃生口。
- S3/aggregate：lifecycle/CLI/default/ordinary writer/deferred/security scans见§5-§6；harness曾有zsh `path`覆盖`PATH`、错误AST `ast.dump(list)`与错误source command等三次调用错误，均在产生pass/fail判定前失败，corrected canonical runs与Controller独立复核通过，不能算产品失败或隐去。

### 10.3 中文 docstring audit

| gate | scope/count | final |
|---|---:|---:|
| S1 added-definition conservative | `89` | `issues=0` |
| S1 function signature-touched exact | `132` | `issues=0` |
| S2 implementation conservative | `100` | `issues=0` |
| S2 Controller semantic exact | `99` | `issues=0` |
| S3 implementation conservative | `38` | `issues=0` |
| S3 Controller signature exact | `36` | `issues=0` |
| aggregate validation union | `236` | `issues=0` |
| final rereview-fix changed-definition | `60` | `issues=0` |

S2的100比exact 99多外层`test_playwright_budget_failure_projects_stable_tool_error`；S3的38比exact 36多body/doc同时变化的外层定义。保守集合没有漏项，exact集合用于计数。S1的89来自added-definition算法，132来自“function signature span与`git diff -U0 70ffc917` added lines相交”的Controller算法；二者不是同一口径。全部qualified-name inventory见Appendix B。

## 11. Deterministic/local/proxy-peer/真实 Playwright/diagnostics v2/filing smoke

### 11.1 S2 deterministic local smoke（旧脚本零 diff）

S2 implementation 原样命令：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-local \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-local
```

- exit `0`，`status=passed`，local `7 passed / 0 failed / 0 skipped`；4 search cases为 `diagnostic_only`。
- summary：`workspace/tmp/r02-web-owner-policy-local/summary.json`、`workspace/tmp/r02-web-owner-policy-local/summary.md`。
- 三个原 `artifact_missing` case 均恢复为 `web-diagnostics-v2` / revision `2`：`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-html-requests.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-pdf-requests.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-challenge-control.json`；三者 outcome 均 completed/HTTP 200，challenge 依次为 `none/none/confirmed`。
- 真实 ordinary Playwright：`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-browser-playwright.json`，completed/HTTP 200，`browser_executed=true`，response `367 B`、DOM `510 chars`、text `118 chars`、events `2`。
- 上述 `...-local/` 路径是 S2 implementation artifact 当时的原样记录；S3 后续按 accepted plan 复用同一目录生成 11-case 终态，因此当前磁盘上的 `...-local/summary.json` 只按 S3 解读，不反向当作 S2 7-case 终态。S2 的可持久权威复核是下述 Controller 独立目录。

S2 Controller 较晚的独立权威命令（supersede implementation 运行作为 gate 裁决，但不抹去上述逐 artifact paths）：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-controller \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-controller
```

- exit `0`，`status=passed`，local `7 passed / 0 failed / 0 skipped`；4 search cases仍为 diagnostic-only。直接路径核对存在：`workspace/tmp/r02-web-owner-policy-controller/summary.json`、`workspace/tmp/r02-web-owner-policy-controller/summary.md`、`workspace/tmp/r02-web-owner-policy-controller/diagnostics/local/local-html-requests.json`、`workspace/tmp/r02-web-owner-policy-controller/diagnostics/local/local-pdf-requests.json`、`workspace/tmp/r02-web-owner-policy-controller/diagnostics/local/local-challenge-control.json`、`workspace/tmp/r02-web-owner-policy-controller/diagnostics/local/local-browser-playwright.json`。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md` §9、`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-controller-validation.md` §4.4。

### 11.2 Proxy / peer deterministic owner gate

这一 contract 是 deterministic owner pytest，不是外网 smoke；精确命令/结果为：

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'private or custom_port or proxy or peer or redirect or browser or challenge' -q
```

- S2 exit `0`；`69 passed, 1 skipped, 0 failed, 105 deselected`。

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'private or custom_port or proxy or peer or redirect or browser or challenge or budget or dns or redact or containment or symlink' -q -rs
```

- aggregate exit `0`；`93 passed, 1 skipped, 0 failed, 81 deselected`。
- 直接覆盖 environment proxy allow/deny、actual selected proxy、proof+proxy 发送前 typed incompatibility、numeric pinned peer match/mismatch、browser proof 启动前 unavailable；唯一 skip 为既有 opt-in live cleanup test，不是上述 owner cases。
- 证据 artifact paths：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-controller-validation.md` §4.1、`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md` §3。

### 11.3 S3 canonical filing / deny / real Playwright smoke

S3 implementation 原样命令：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-local \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-local
```

- implementation exit `0`，`status=passed`，local `11 passed / 0 failed / 0 skipped`。该命令晚于 S2 在同目录的 7-case 历史运行，所以该目录的最终逐件 paths 只作 S3 11-case 证据解读。

Controller 以只替换 output-dir/run-label 的独立新目录复核，下列命令作为 S3 权威 gate：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-controller-s3 \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-controller-s3
```

- Controller exit `0`，`status=passed`，local `11 passed / 0 failed / 0 skipped`；summary 为 `workspace/tmp/r02-web-owner-policy-controller-s3/summary.json`、`workspace/tmp/r02-web-owner-policy-controller-s3/summary.md`；Controller filing artifacts 为 `workspace/tmp/r02-web-owner-policy-controller-s3/diagnostics/filing/local-filing-http.json`、`workspace/tmp/r02-web-owner-policy-controller-s3/diagnostics/filing/local-filing-playwright.json`。
- 11 cases：`local-html-requests`、`local-html-tool`、`local-pdf-requests`、`local-pdf-tool`、`local-browser-playwright`、`local-challenge-control`、`local-filing-http`、`local-filing-playwright`、`local-private-deny`、`local-custom-port-deny`、`local-assembly-config`。
- implementation 逐件耐久证据保存在 `workspace/tmp/r02-web-owner-policy-local/summary.json`、`workspace/tmp/r02-web-owner-policy-local/summary.md`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/local-filing-http.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/local-filing-playwright.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/explicit-storage-state-input.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-private-deny.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-custom-port-deny.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-challenge-control.json`、`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-browser-playwright.json`。
- filing HTTP/Playwright 均 completed/HTTP 200；Playwright `browser_executed=true`、`storage_state.input_used=true`，体量见§7。private overlay `private=false/custom=true` 与 custom-port overlay `private=true/custom=false` 均通过正式 assembly/callable 得到 `permission_denied`。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md` §5、`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md` §3.2。

### 11.4 Aggregate canonical 与 final superseding smoke

Initial aggregate exact command：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-aggregate \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-aggregate
```

- exit `0`，`status=passed`，local `11 passed / 0 failed / 0 skipped`，external fetch `0`，search `4 diagnostic_only`。
- summary：`workspace/tmp/r02-web-owner-policy-aggregate/summary.json`、`workspace/tmp/r02-web-owner-policy-aggregate/summary.md`。
- filing：`workspace/tmp/r02-web-owner-policy-aggregate/diagnostics/filing/local-filing-http.json`、`workspace/tmp/r02-web-owner-policy-aggregate/diagnostics/filing/local-filing-playwright.json`；challenge/private/custom-port：`workspace/tmp/r02-web-owner-policy-aggregate/diagnostics/local/local-challenge-control.json`、`workspace/tmp/r02-web-owner-policy-aggregate/diagnostics/local/local-private-deny.json`、`workspace/tmp/r02-web-owner-policy-aggregate/diagnostics/local/local-custom-port-deny.json`。

Aggregate final re-review fix 的较晚 exact command：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-codex \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-aggregate-rereview-fix-codex
```

- exit `0`，`status=passed`，local `11 passed / 0 failed / 0 skipped`；summary 为 `workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-codex/summary.json`，22 个 diagnostic JSON 的 sensitive/deferred scan 为 `issues=0`。
- Controller 随后在独立 `workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-controller/` 以同参数复核，记录 local `11 passed / 0 failed / 0 skipped`，真实 ordinary/filing Playwright 均执行；直接路径核对存在 `workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-controller/summary.json` 与 `workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-controller/summary.md`。Controller artifact 只保存 output root 与结果，未原样保存整条 shell 行，因此本 completion 不伪造第二条命令；以上 Codex exact command + Controller 独立结果共同作为 final authority，supersede initial aggregate smoke 作为最终 gate。
- 证据 artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md` §4，`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-codex.md` §4.4，及其 Controller validation §3。

### 11.5 Diagnostics v2 / security disposition

所有 mandatory artifacts 为 `web-diagnostics-v2`、revision `2`；challenge control 为 `confirmed` 且 signals 含 `content:bot challenge`、`content:verify you are human`。Filing 自身 challenge 为 `suspected`，这是内容事实，不是 smoke 失败。Artifact scans 对 cookie、authorization、proxy credential、query secret、storage content/full path 与 lifecycle fields 零命中。

## 12. README decision

| README | decision | basis |
|---|---|---|
| `dayu/config/README.md` | updated | Config读者需要五bool、三child budgets、local defaults、frozen values、proxy/proof与browser/private关系；不承诺Issue #178 lifecycle |
| `tests/README.md` | updated | 同步owner/security matrix、typed diagnostics、只读storage input、lifecycle删除、版本化filing与typed deny smoke |
| 根 `README.md` | no-update-with-evidence | 安装、初始化、CLI/Web入口、用户工作流、默认输出、日志/工作区路径均未变；accepted diff为零 |
| `dayu/README.md` | no-update-with-evidence | UI/Service/Host/Engine分层与装配边界未变 |
| `dayu/host/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md` | no-update-with-evidence | 对应模块未改 |
| UI README | not applicable | 无目标文件/无UI改动 |

两份实际更新README没有独立“Agent更新约束”章节，故按根AGENTS触发规则与读者职责审查；aggregate fixes只加Web production/test owner coverage，不再改README。证据：S1/S2/S3 README decision与aggregate validation §13。

## 13. 全 finding ID、disposition 与 accepted closure

### 13.1 Plan chain

- Plan-entry：`R02-B01`、`R02-B02` accepted/closed。
- Controller合并后的accepted plan findings全部closed：
  - `R02-PF-01` <= `R02-PR-F01` + `R02-DS-F01` + DS Q1；
  - `R02-PF-02` <= `R02-PR-F02` + `R02-DS-F02` + DS Q2；
  - `R02-PF-03` <= `R02-PR-F03`；
  - `R02-PF-04` <= `R02-PR-F06`；
  - `R02-PF-05` <= MiMo OQ-1 + `R02-DS-F04`；
  - `R02-PF-06` <= `R02-DS-F05` + DS Q6；
  - `R02-PF-07` <= `R02-DS-F09`；
  - `R02-PF-08` <= `R02-DS-F10`；
  - `R02-PF-09` <= MiMo OQ-2；
  - `R02-PF-10` narrowed-accepted/closed <= `R02-PR-F04` + `R02-DS-F08` + DS Q1。
- Rejected/no-code：`R02-PR-F05`（不复制第二expected-values真源）、`R02-DS-F03`/Q3（fixed endpoint不绕过egress）、`R02-DS-F06`/Q4（旧private CLI继续删除）、`R02-DS-F07`/Q5（coverage不放宽）、`R02-DS-F11`（不新增fixture CLI/path authority）；DS Q6由PF-06关闭。
- Plan re-review新项：`R02-RR-F01` rejected/no-fix。最终两路plan re-review PASS、无open question。

### 13.2 S1 drift/implementation/code review

- Drift：`R02-S1-DR-01`、`R02-S1-DR-02`、`R02-S1-DR-04` accepted/closed；`R02-S1-DR-03` narrowed-accepted/closed。`R02-S1-DRR-MIMO-01`、`R02-S1-DRR-MIMO-02`、`R02-S1-DRR-MIMO-Q02` rejected/no-fix；`R02-S1-DRR-DS-01`（DS artifact别名`R02-S1-DRR-F01`）rejected/no-plan-fix/implementation verification；`R02-S1-DRR-DS-02`（别名`R02-S1-DRR-F02`）accepted residual verification note/no allowlist expansion。
- Controller implementation：`R02-S1-CV-F01`、`R02-S1-CV-F02`、`R02-S1-CV-F03`、`R02-S1-CV-F04` accepted并closed（ordinary failure diagnostic owner、local custom-port retained behavior、第二default删除、精确test/callable/coverage边界）。
- Initial reviewers：MiMo Finding 01进入`R02-S1-CR-F01`；MiMo Finding 02为design confirmation/no-fix；MiMo Finding 03关于small cap的“无需suffix”被Controller拒绝并由`R02-S1-CR-F03`覆盖。`R02-S1-DS-F01`、`R02-S1-DS-F02`分别合并为`R02-S1-CR-F02`、`R02-S1-CR-F03`。
- Code review：`R02-S1-CR-F01`、`R02-S1-CR-F02`、`R02-S1-CR-F03` accepted/closed；Controller follow-up `R02-S1-CR-CV-F01` accepted/closed。两路final re-review PASS、new material finding=0；accepted S1 commit为`c7b01d82...`。

### 13.3 S2 drift/implementation/code review

- Drift：`R02-S2-DR-01` accepted/closed-in-plan；`R02-S2-DR-CV-F01` accepted/fixed/re-reviewed-closed；`R02-S2-RR-NOTE-01`、`R02-S2-RR-NOTE-02`、`R02-S2-RR-NOTE-03`按§2.3归属；`R02-S2-RR-PASS-01`、`R02-S2-RR-PASS-02`、`R02-S2-RR-PASS-03`、`R02-S2-RR-PASS-04`、`R02-S2-RR-PASS-05`、`R02-S2-RR-PASS-06`、`R02-S2-RR-PASS-07`、`R02-S2-RR-PASS-08`、`R02-S2-RR-PASS-09`均为re-review正向验证，不是defect。
- Implementation Controller finding：0。
- `R02-S2-MIMO-F01` reclassified为already-planned S3 observation/no S2 fix；`R02-S2-DS-F01`、`R02-S2-DS-F02` rejected as current defect/no fix。`R02-S2-DS-O01`与MiMo-F01同源归S3；`R02-S2-DS-O02`、`R02-S2-DS-O04`、`R02-S2-DS-O05`为positive facts；`R02-S2-DS-O03`为near-threshold coverage gate。`R02-S2-MIMO-RFnn`、`R02-S2-DS-RFnn`均none。
- Zero-change code-review fix与双路re-review确认Controller dispositions一致、new finding=0；accepted S2 commit为`d8d6e9d9...`。

### 13.4 S3 code review

- MiMo initial/final：`R02-S3-MIMO-RFnn` none。
- `R02-S3-DS-F01`、`R02-S3-DS-F02`、`R02-S3-DS-F03`、`R02-S3-DS-F04`、`R02-S3-DS-F05`、`R02-S3-DS-F06`、`R02-S3-DS-F07`、`R02-S3-DS-F08`全部verification-only/no-fix，分别验证lifecycle删除、read input、single parser、typed propagation、filing/deny smoke、v2/security、deferred zero leak、tests/coverage/docstring/README；不是defect finding。
- `R02-S3-DS-RFnn` none；accepted finding=0、fixed defect=0；zero-change fix/controller validation/双路re-review均PASS。Accepted S3 commit为`7e679796...`。

### 13.5 Aggregate

- 初始 MiMo findings=0。DS：`R02-AGG-DS-F01`、`R02-AGG-DS-F02`、`R02-AGG-DS-F03`、`R02-AGG-DS-F04`、`R02-AGG-DS-F05`全部accepted，其中F02带owner correction；分别为browser singleton lifecycle、URL normalizer+userinfo egress owner、browser text cap、route branches、process cancel/timeout/no-result/cleanup direct-owner tests。
- 首次fix后Controller新增`R02-AGG-CTRL-F01` accepted：launch failure local Playwright runtime未stop。第二fix在owner boundary关闭，globals不发布，stop failure不遮蔽原返回contract。
- Final re-review：`R02-AGG-RV-F01` accepted/closed（cleanup debug只含stable stage+exception type且整段日志无敏感哨兵）；`R02-AGG-RV-F03` accepted/closed（保留channel/headless、移除stealth tuning assertion）；`R02-AGG-RV-F02` rejected/no-code（inline comment已拥有复杂逻辑意图）；`R02-AGG-RV-F04` rejected/no-code（class中文概览满足AGENTS）。
- Post-fix双路final re-review findings=0；Controller final ledger：`R02-AGG-DS-F01`、`R02-AGG-DS-F02`、`R02-AGG-DS-F03`、`R02-AGG-DS-F04`、`R02-AGG-DS-F05`、`R02-AGG-CTRL-F01`、`R02-AGG-RV-F01`、`R02-AGG-RV-F03`全部closed；`R02-AGG-RV-F02`、`R02-AGG-RV-F04`保持rejected且未实施。Accepted R02 commit为`62d3cfe7...`。

### 13.6 Completion Controller validation follow-up

- `R02-COMP-CV-F01`：**accepted / closed-in-completion-artifact，pending Controller re-validation**。§2.4 现已按 S1 四文件和 S2 两文件记录 exact old owner/type/signature -> child owner/typed forwarding/direct assertion，且逐文件记录 sender/search/browser/lifecycle/config/default 未前移的边界；证据仅来自 accepted Git diff、accepted plan 与 slice artifacts。
- `R02-COMP-CV-F02`：**accepted / closed-in-completion-artifact，pending Controller re-validation**。§8 现已补齐 S1/S2/S3/aggregate exact pytest commands、exit、passed/skipped/failed/deselected/warning counts、S1/S2 mandatory direct node 与 coverage/review artifact paths；§11 现已补齐 S2/S3/aggregate deterministic/real Playwright/diagnostics v2/filing smoke 命令、exit、metric 与 artifact paths，并标明 S1 `247 -> 249`、aggregate `310 -> 329 -> 330` 及 smoke 的较晚权威复核。历史 artifact 未保存原样 shell 行的两处已明示披露，未猜测拼造。
- 该两 finding 的 disposition 真源为 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-completion-controller-validation.md`；它是 accepted code 之后的 completion-gate artifact，不计入 Appendix A 的 66 份 accepted-code 历史 artifact 闭集。

Disposition真源分别是plan/S1/S2/S3/aggregate Controller adjudication artifacts；reviewer自报的PASS/non-blocking不覆盖Controller裁决。

## 14. Residual risk、owner、destination 与非阻塞理由

| residual | owner / destination | non-blocking basis |
|---|---|---|
| credential refresh/retention/concurrent publish/cleanup | GitHub Issue #178；control residual `WU-SEMANTIC-OWNERSHIP-01-WEB-STORAGE-R1` | R02删除提前实现，只保留显式read input；无ownerless lifecycle |
| live DOM/event/error/body规模未来变化 | Web config owner | 当前版本化fixture远低于ceiling，runtime fail bounded；只有直接ceiling failure才另立config change |
| raw filing diagnostic不执行production warmup | Browser budget owner | cap=`7 B` direct owner test与retained matrix覆盖；S3未改production warmup |
| active proxy无法证明origin peer | Web HTTP transport/config owner | proof+active proxy在发送前typed fail closed，无静默降级 |
| Playwright无numeric peer proof | browser backend owner | proof-on browser启动前typed unavailable/fail closed |
| external provider DNS/key/site/challenge波动 | Web diagnostics/smoke owner | deterministic local 11/11为hard gate；external search仅diagnostic-only |
| opt-in live cleanup pytest skip | Web Playwright cleanup test owner | 本轮ordinary与filing真实Playwright均执行且零skip |
| OS级线程调度/真实process signal | Python stdlib + real smoke | unit tests验证owner调用，真实Playwright验证可执行路径 |
| historical S1 exact coverage 79.5948 | 已由S2/aggregate test owner关闭 | S2 exact 80.0562、final exact 80.7584；不是final accepted tree residual |
| Doc LLM-facing truncation | Issue #177；control residual `WU-SEMANTIC-OWNERSHIP-01-DOC-TRUNC-R1` | 非R02 Web owner范围；已有destination |
| unified authorization愿景 | Topic 9 future Controller decision | 本轮明确no-code；现有Web local safety/security retained |
| accepted-result/LLM projection | umbrella R03 | 只允许R02 completion被Controller接受后另行启动；R02未改该owner |

没有未分配 residual、release blocker或需要在R02 completion中补代码的风险。

## 15. Controller handoff

本artifact完成 accepted plan §15.4 的15项清单：精确identity/SHA、三类drift、changed-file闭集、owner/deleted/retained contract、budget metrics、slice/aggregate测试、逐文件coverage/JSON、pyright/baseline/diff/allowlist/docstring/source/transport、deterministic与真实smoke、README、完整finding ledger、residual owners与本handoff。

**交回 Controller，等待其对 `R02-COMP-CV-F01/F02` 的补证做独立重新验证、接受 completion 并更新唯一 control 真源。** AgentCodex在本gate：

- 不commit、不push；
- 不修改`docs/host/issues-implementation-control.md`；
- 不修改代码、测试、README或既有artifact；
- 不开启R03、Issue #178、proxy credential schema或统一authorization；
- 不把本completion verdict当作Controller acceptance或umbrella closeout。

Controller若接受，应以accepted code `62d3cfe7be848ac1ef54154240f2b744b707ad7c`、accepted plan `2d42ceb6bb8fc2b7ad29f5f20dc970a9b391307a`与本artifact为R02 completion输入，再由Controller决定control更新及后续R03 entry。历史S2 dirty implementation只按已闭合drift链理解，不得重新解释成未审scope。

## Appendix A. 已读取的 R02 plan/review/validation artifact 闭集

计划：

- `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`

Plan entry/review/fix/re-review：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-controller-adjudication.md`

S1 plan drift / implementation / validation / review：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-controller-adjudication.md`

S2 plan drift / implementation / validation / review：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-rereview-controller-adjudication.md`

S3 implementation / validation / review：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-rereview-controller-adjudication.md`

Aggregate validation / deepreview / fixes / final re-review：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-post-fix-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-post-fix-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-post-fix-rereview-controller-adjudication.md`

上述为accepted code区间内66份R02 review/validation artifacts；另读取根`AGENTS.md`、`docs/host/issues-implementation-control.md`、controller discussion与umbrella remediation plan §7.2。Completion自身不计入accepted code的66份历史artifact。

## Appendix B. Added/signature/body-touched qualified-name inventory

本appendix采用各Controller最终口径；文件标题是qualified name的一部分。S1 132项只计function/method/nested helper，随后单列class/TypedDict header inventory；S2列保守100项（Controller exact 99是其真子集）；S3列保守38项（Controller exact 36是其真子集）；aggregate 60项由`4240ee75..62d3cfe7` AST body/signature直接比较复现。

### B.1 S1 function/method/nested helper signature-touched（132）

`dayu/tools/web/provider.py`：

```text
_resource_budgets_default
```

`dayu/tools/web/web_egress_policy.py`：

```text
WebEgressPolicy.__init__
WebEgressPolicy.allows_custom_port
```

`dayu/tools/web/web_fetch_orchestrator.py`：

```text
_decompress_limited_response_body
_read_limited_response_body
_materialize_response_body
_warmup_domain
_fetch_and_convert_content
```

`dayu/tools/web/web_playwright_backend.py`：

```text
_PlaywrightWorkerProtocol.__call__
_playwright_process_entry
_run_playwright_worker_process
_read_budgeted_dom_metrics
_materialize_bounded_page_projection
_playwright_sync_worker
_fetch_and_convert_with_playwright
```

`dayu/tools/web/web_resource_budget.py`：

```text
_validate_positive_integer
HttpResourceBudget.__post_init__
DiagnosticResourceBudget.__post_init__
_parse_group
_parse_positive_integer_field
web_resource_budgets_from_json
```

`dayu/tools/web/web_search_providers.py`：

```text
search_public_web
_filter_visible_results
_search_with_tavily
_search_with_serper
_search_with_duckduckgo
_materialize_bounded_search_response
```

`dayu/tools/web/web_tools.py`：

```text
_try_playwright_fallback
_warmup_domain
_raise_fetch_failure
_fetch_and_convert_content
_playwright_sync_worker
_fetch_and_convert_with_playwright
```

`tests/tools/web/test_diagnose_web_access.py`：

```text
_preserve_materialized_response_body
test_single_diagnostic_private_mode_preserves_local_custom_port
test_single_diagnostic_private_mode_preserves_local_custom_port.fake_build_requests_profile
```

`tests/tools/web/test_web_tools_provider.py`：

```text
test_project_error_message_marks_small_cap_truncation_without_false_positive
test_ordinary_fetch_failure_consumes_config_diagnostic_error_cap
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner.fail_fetch
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner.controlled_browser_fallback
_IdentityZstdReader.__init__
_IdentityZstdReader.read
_IdentityZstdReader.close
_IdentityZstdDecompressor.stream_reader
_IdentityZstdModule.__init__
_IdentityZstdModule.ZstdDecompressor
_SyntheticPlaywrightPage.__init__
_SyntheticPlaywrightPage.add_init_script
_SyntheticPlaywrightPage.goto
_SyntheticPlaywrightPage.route
_SyntheticPlaywrightPage.wait_for_load_state
_SyntheticPlaywrightPage.wait_for_timeout
_SyntheticPlaywrightContext.__init__
_SyntheticPlaywrightContext.new_page
_SyntheticPlaywrightContext.close
_SyntheticPlaywrightBrowser.__init__
_SyntheticPlaywrightBrowser.new_context
_SyntheticPlaywrightBrowser.close
_counting_response
_QueuedSession.__init__
_http_resource_budget
_browser_resource_budget
_diagnostic_resource_budget
_resource_budgets
_resource_budget_json
_SocketWebServer._handle_connection
_SyntheticNestedPlaywrightWorker.__call__
_LiveBrowserLongRunningWorker.__call__
_BlockedPlaywrightWorker.__call__
_SyntheticProcessPlaywrightWorker.__call__
_stable_owner_warmup
_stable_owner_probe
_resolve_private_test_address
_convert_expected_fetch_html
_reject_non_html_conversion
_reject_fetch_html_conversion
_convert_expected_pdf
_raise_missing_optional_zstd
_import_identity_zstd
_convert_expected_browser_html
_reject_browser_html_conversion
_convert_oversized_browser_markdown
_run_synthetic_playwright_worker
_run_synthetic_playwright_worker.get_browser
_unavailable_browser
_accept_picklable_playwright_worker
_exhaust_browser_timeout
_process_entry_success_worker
_process_entry_blocked_worker
_process_entry_failed_worker
_skip_new_process_session
test_egress_custom_port_policy_is_independent_from_private_network_policy
test_search_visibility_consumes_same_private_and_custom_port_policy
test_search_public_web_provider_result_excludes_llm_guidance.fake_search_with_duckduckgo
test_search_web_receives_execution_context_and_passes_cancellation_token.fake_search_public_web
test_search_web_cancelled_before_provider_returns_host_cancelled.fake_search_public_web
test_search_web_deep_cancel_message_is_sanitized.fake_search_public_web
test_search_web_cancelled_between_provider_attempts_stops_fallback.fake_search_with_tavily
test_search_web_cancelled_between_provider_attempts_stops_fallback.fake_search_with_duckduckgo
test_fetch_private_url_fails_closed_with_explicit_false
test_fetch_http_budget_success_paths_keep_html_and_non_html_semantics
test_resource_budget_provider_config_applies_only_local_child_default
test_web_provider_config_rejects_unknown_typo_and_keeps_partial_defaults
test_resource_budget_provider_config_rejects_unknown_and_invalid_values
test_packaged_web_config_matches_typed_policy_and_budget_defaults
test_web_policy_config_defaults_and_overrides_are_independent
test_web_policy_config_single_override_preserves_four_sibling_defaults
test_web_policy_config_rejects_non_boolean_values
test_s1_budget_owner_signatures_and_worker_payload_are_closed
test_http_child_budget_owns_declared_length_and_bounded_codec_failures
test_decompress_zstd_streaming_uses_http_child_budget
test_playwright_worker_success_consumes_only_browser_budget
test_playwright_worker_success_consumes_only_browser_budget.get_browser
test_playwright_worker_browser_owner_controls_terminal_resource_paths
test_playwright_budget_failure_projects_stable_tool_error
test_playwright_budget_failure_projects_stable_tool_error.fake_fetch_with_playwright
test_challenge_confirmed_http_500_invokes_fallback_once.fake_playwright_fallback
test_playwright_public_direct_reports_typed_egress_policy_unavailable.unexpected_worker
test_playwright_process_wrapper_keeps_diagnostic_budget_out_of_worker_kwargs
test_playwright_process_wrapper_keeps_diagnostic_budget_out_of_worker_kwargs.fake_run_process
test_playwright_wrapper_retains_timeout_and_challenge_with_split_owners
test_playwright_wrapper_retains_timeout_and_challenge_with_split_owners.challenge_process_result
test_playwright_process_entry_projects_separate_diagnostic_owner
test_playwright_process_wrapper_projects_success_and_diagnostic_error
test_fetch_playwright_url_safety_projects_permission_denied.fake_fetch_and_convert_with_playwright
test_fetch_playwright_cancel_projects_to_host_cancelled.fake_fetch_and_convert_with_playwright
test_try_playwright_fallback_pre_cancel_does_not_start_playwright.fake_fetch_and_convert_with_playwright
test_playwright_unpicklable_worker_fails_closed.fake_worker
test_fetch_playwright_fallback_receives_channel_and_storage_state_path.fake_fetch_and_convert_with_playwright
test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty.fake_fetch_and_convert_with_playwright
```

`utils/diagnose_web_access.py`：

```text
_read_bounded_playwright_response_body
```

S1同一signature-header direct inventory中的class/TypedDict（不加进132 function count）：

```text
dayu/tools/web/web_http_session.py:WebHttpTransportPolicy
dayu/tools/web/web_resource_budget.py:HttpResourceBudget
dayu/tools/web/web_resource_budget.py:BrowserResourceBudget
dayu/tools/web/web_resource_budget.py:DiagnosticResourceBudget
dayu/tools/web/web_resource_budget.py:WebResourceBudgets
dayu/tools/web/web_tools.py:_WarmupFetchKwargs
tests/tools/web/test_web_tools_provider.py:_IdentityZstdReader
tests/tools/web/test_web_tools_provider.py:_IdentityZstdDecompressor
tests/tools/web/test_web_tools_provider.py:_IdentityZstdModule
tests/tools/web/test_web_tools_provider.py:_SyntheticPlaywrightResponse
tests/tools/web/test_web_tools_provider.py:_SyntheticPlaywrightPage
tests/tools/web/test_web_tools_provider.py:_SyntheticPlaywrightContext
tests/tools/web/test_web_tools_provider.py:_SyntheticPlaywrightBrowser
tests/tools/web/test_web_tools_provider.py:_SyntheticHtmlPipelineResult
tests/tools/web/test_web_tools_provider.py:_QueuedSession
tests/tools/web/test_web_tools_provider.py:_SyntheticNestedPlaywrightWorker
tests/tools/web/test_web_tools_provider.py:_LiveBrowserLongRunningWorker
tests/tools/web/test_web_tools_provider.py:_BlockedPlaywrightWorker
tests/tools/web/test_web_tools_provider.py:_SyntheticProcessPlaywrightWorker
```

### B.2 S2 conservative added/signature-touched（100；Controller exact=99）

Production/utility（27）：

```text
dayu/tools/web/web_fetch_orchestrator.py:_request_with_safe_redirects
dayu/tools/web/web_fetch_orchestrator.py:_warmup_domain
dayu/tools/web/web_fetch_orchestrator.py:_probe_content_type
dayu/tools/web/web_fetch_orchestrator.py:_fetch_and_convert_content
dayu/tools/web/web_http_session.py:_MergedEnvironmentSettings
dayu/tools/web/web_http_session.py:ProxyPeerProofIncompatibleError
dayu/tools/web/web_http_session.py:ProxyPeerProofIncompatibleError.__init__
dayu/tools/web/web_http_session.py:_send_authorized_request
dayu/tools/web/web_http_session.py:_send_authorized_plain_request
dayu/tools/web/web_http_session.py:_send_authorized_request_attempt
dayu/tools/web/web_playwright_backend.py:_playwright_process_entry
dayu/tools/web/web_playwright_backend.py:_clear_proxy_environment
dayu/tools/web/web_playwright_backend.py:_run_playwright_worker_process
dayu/tools/web/web_playwright_backend.py:_fetch_and_convert_with_playwright
dayu/tools/web/web_search_providers.py:search_public_web
dayu/tools/web/web_search_providers.py:_search_with_tavily
dayu/tools/web/web_search_providers.py:_search_with_serper
dayu/tools/web/web_search_providers.py:_search_with_duckduckgo
dayu/tools/web/web_tools.py:_browser_fallback_available
dayu/tools/web/web_tools.py:_try_playwright_fallback
dayu/tools/web/web_tools.py:_warmup_domain
dayu/tools/web/web_tools.py:_probe_content_type
dayu/tools/web/web_tools.py:_fetch_and_convert_content
dayu/tools/web/web_tools.py:_fetch_and_convert_with_playwright
utils/diagnose_web_access.py:_build_requests_profile
utils/diagnose_web_access.py:_fetch_web_page_definition
utils/diagnose_web_access.py:_build_tool_fetch_profile
```

Provider tests（57）：

```text
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner.fail_fetch
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner.controlled_browser_fallback
_queued_send_authorized_request
_plain_response_lease
_stable_owner_warmup
_stable_owner_probe
_process_entry_proxy_environment_worker
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_prepare
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_merge
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_select_proxy
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_send
test_http_transport_proxy_deny_ignores_environment_and_sends_direct
test_http_transport_proxy_deny_ignores_environment_and_sends_direct.record_direct_send
test_http_transport_proof_with_active_proxy_fails_typed_before_send
test_http_transport_proof_with_active_proxy_fails_typed_before_send.return_proxy_settings
test_http_transport_proof_with_active_proxy_fails_typed_before_send.select_active_proxy
test_http_transport_proof_with_active_proxy_fails_typed_before_send.reject_send
test_search_public_web_provider_result_excludes_llm_guidance.fake_search_with_duckduckgo
test_search_web_receives_execution_context_and_passes_cancellation_token.fake_search_public_web
test_search_web_cancelled_before_provider_returns_host_cancelled.fake_search_public_web
test_search_web_deep_cancel_message_is_sanitized.fake_search_public_web
test_search_web_cancelled_between_provider_attempts_stops_fallback.fake_search_with_tavily
test_search_web_cancelled_between_provider_attempts_stops_fallback.fake_search_with_duckduckgo
test_s2_owner_signatures_and_worker_payload_are_closed
test_playwright_budget_failure_projects_stable_tool_error
test_playwright_budget_failure_projects_stable_tool_error.fake_fetch_with_playwright
test_challenge_confirmed_http_500_uses_current_browser_capability
test_challenge_confirmed_http_500_uses_current_browser_capability.get_test_session
test_challenge_confirmed_http_500_uses_current_browser_capability.fake_playwright_fallback
test_tavily_provider_builds_typed_rows.fake_send
test_serper_provider_builds_typed_rows.fake_send
test_duckduckgo_provider_streams_budgeted_body_and_closes_response.fake_send
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics.resolve_provider
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics.return_challenge_response
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics.record_challenge_detection
test_search_provider_forwards_proxy_and_peer_policy_to_plain_sender
test_search_provider_forwards_proxy_and_peer_policy_to_plain_sender.record_plain_sender
test_search_proxy_peer_incompatibility_is_not_provider_fallback
test_search_proxy_peer_incompatibility_is_not_provider_fallback.fail_plain_sender
test_search_proxy_peer_incompatibility_projects_safe_tool_failure
test_search_proxy_peer_incompatibility_projects_safe_tool_failure.fail_search_business
test_playwright_public_direct_runs_without_private_permission
test_playwright_public_direct_runs_without_private_permission.run_public_process
test_browser_disabled_with_private_permission_does_not_start_backend
test_browser_disabled_with_private_permission_does_not_start_backend.record_backend_call
test_browser_peer_proof_fails_before_process_with_safe_projection
test_browser_peer_proof_fails_before_process_with_safe_projection.record_process_call
test_playwright_process_wrapper_keeps_diagnostic_budget_out_of_worker_kwargs.fake_run_process
test_playwright_wrapper_retains_timeout_and_challenge_with_split_owners.challenge_process_result
test_playwright_process_entry_controls_proxy_environment
test_fetch_playwright_url_safety_projects_permission_denied.fake_fetch_and_convert_with_playwright
test_fetch_playwright_cancel_projects_to_host_cancelled.fake_fetch_and_convert_with_playwright
test_try_playwright_fallback_pre_cancel_does_not_start_playwright.fake_fetch_and_convert_with_playwright
test_fetch_playwright_fallback_receives_channel_and_storage_state_path.fake_fetch_and_convert_with_playwright
test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty.fake_fetch_and_convert_with_playwright
```

Diagnostic tests（16）：

```text
_raise_diagnostic_request_exception
test_single_diagnostic_private_mode_preserves_local_custom_port.fake_build_requests_profile
test_requests_profile_forwards_provider_owned_transport_policy
test_requests_profile_forwards_provider_owned_transport_policy.fake_provider_config
test_requests_profile_forwards_provider_owned_transport_policy.fake_build_requests_profile
test_requests_profile_forwards_provider_owned_transport_policy.fake_build_tool_fetch_profile
test_requests_profile_records_raw_response_byte_length.fake_request_with_safe_redirects
test_current_fetch_adapter_completed_outcome_generates_ok_profile.fake_definition
test_docling_wrapper_records_invoked_true_and_restores_callable.fake_definition
test_html_fetch_profile_records_docling_invoked_false.fake_definition
test_pdf_fetch_success_without_docling_invocation_keeps_failure_evidence_for_smoke.fake_definition
test_docling_runtime_initialization_exception_becomes_skip_observed_item.fake_definition
test_generic_docling_conversion_exception_is_not_skip_observed_item.fake_definition
test_current_fetch_adapter_failed_outcome_generates_business_readable_profile.fake_definition
_fake_requests_profile
_fake_fetch_profile
```

### B.3 S3 conservative added/signature-touched（38；Controller exact=36）

Production/utility（10）：

```text
utils/diagnose_web_access.py:CliOptions
utils/diagnose_web_access.py:_BrowserContextProtocol
utils/diagnose_web_access.py:_build_requests_profile
utils/diagnose_web_access.py:_build_tool_fetch_profile
utils/diagnose_web_access.py:_resolve_explicit_storage_state_input
utils/diagnose_web_access.py:_append_bounded_network_event
utils/diagnose_web_access.py:_build_playwright_profile
utils/smoke_web_ci.py:_filing_artifact_gap
utils/smoke_web_ci.py:_diagnostic_command
utils/smoke_web_ci.py:_run_local_typed_egress_deny_case
```

Diagnostic tests（21）：

```text
test_storage_state_dir_only_flows_to_provider_config
test_explicit_storage_state_input_reads_valid_json_object
test_explicit_storage_state_input_rejects_missing_or_non_file
test_explicit_storage_state_input_rejects_invalid_json_shape
test_diagnostic_artifact_only_projects_storage_state_input_fact
test_single_diagnostic_packaged_defaults_allow_private_custom_port
test_single_diagnostic_packaged_defaults_allow_private_custom_port.fake_build_requests_profile
test_single_diagnostic_private_and_custom_port_denies_are_independent
test_single_diagnostic_private_and_custom_port_denies_are_independent.fake_provider_config
test_single_diagnostic_private_and_custom_port_denies_are_independent.authorize_in_requests_profile
test_requests_profile_forwards_provider_owned_transport_policy.fake_build_requests_profile
test_requests_profile_forwards_provider_owned_transport_policy.fake_build_tool_fetch_profile
test_single_diagnostic_uses_typed_budget_default_and_run_override
test_single_diagnostic_uses_typed_budget_default_and_run_override.fake_provider_config
test_single_diagnostic_uses_typed_budget_default_and_run_override.capture_requests_profile
test_cli_max_network_absent_is_none_and_invalid_override_fails
test_diagnostic_playwright_private_egress_rejection_precedes_browser
_options
_fake_requests_profile
_fake_fetch_profile
_fake_playwright_profile
```

Smoke tests（7）：

```text
test_versioned_filing_fixture_is_regular_and_registered_directly
test_diagnostic_command_has_no_private_cli_and_forwards_explicit_input
test_typed_egress_deny_cases_use_provider_overlay_and_callable
test_typed_egress_deny_cases_use_provider_overlay_and_callable.denied_fetch_callable
test_typed_egress_deny_cases_use_provider_overlay_and_callable.fake_load_runtime_config
test_typed_egress_deny_cases_use_provider_overlay_and_callable.fake_discover_tools
test_versioned_filing_http_and_playwright_execution_are_hard_gates
```

### B.4 Aggregate final changed-definition（60）

```text
dayu/tools/web/web_playwright_backend.py:_get_playwright_browser
tests/tools/web/test_web_tools_provider.py:test_normalize_url_for_http_rejects_missing_transport_parts
tests/tools/web/test_web_tools_provider.py:test_normalize_url_for_http_encodes_idna_and_userinfo_for_transport
tests/tools/web/test_web_tools_provider.py:test_web_egress_policy_owner_rejects_userinfo_url
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightBrowser
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightBrowser.__init__
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightBrowser.new_context
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightBrowser.close
tests/tools/web/test_web_tools_provider.py:_LifecycleChromiumLauncher
tests/tools/web/test_web_tools_provider.py:_LifecycleChromiumLauncher.__init__
tests/tools/web/test_web_tools_provider.py:_LifecycleChromiumLauncher.launch
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightInstance
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightInstance.__init__
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightInstance.stop
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightStarter
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightStarter.__init__
tests/tools/web/test_web_tools_provider.py:_LifecyclePlaywrightStarter.start
tests/tools/web/test_web_tools_provider.py:_LifecycleSyncPlaywrightFactory
tests/tools/web/test_web_tools_provider.py:_LifecycleSyncPlaywrightFactory.__init__
tests/tools/web/test_web_tools_provider.py:_LifecycleSyncPlaywrightFactory.__call__
tests/tools/web/test_web_tools_provider.py:_RecordingRouteRequest
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightRoute
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightRoute.__init__
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightRoute.abort
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightRoute.continue_
tests/tools/web/test_web_tools_provider.py:_playwright_worker_process_kwargs
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue.__init__
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue.put
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue.get
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue.get_nowait
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue.close
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightResultQueue.join_thread
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightProcess
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightProcess.__init__
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightProcess.start
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightProcess.is_alive
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightProcess.join
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightProcess.mark_terminated
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightMultiprocessingContext
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightMultiprocessingContext.__init__
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightMultiprocessingContext.Queue
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightMultiprocessingContext.Process
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightContextFactory
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightContextFactory.__init__
tests/tools/web/test_web_tools_provider.py:_FakePlaywrightContextFactory.__call__
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightProcessTerminator
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightProcessTerminator.__init__
tests/tools/web/test_web_tools_provider.py:_RecordingPlaywrightProcessTerminator.__call__
tests/tools/web/test_web_tools_provider.py:_ScriptedMonotonicClock
tests/tools/web/test_web_tools_provider.py:_ScriptedMonotonicClock.__init__
tests/tools/web/test_web_tools_provider.py:_ScriptedMonotonicClock.__call__
tests/tools/web/test_web_tools_provider.py:test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key
tests/tools/web/test_web_tools_provider.py:test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state
tests/tools/web/test_web_tools_provider.py:test_materialize_bounded_page_projection_owns_text_too_large_reason
tests/tools/web/test_web_tools_provider.py:test_route_handler_owner_selects_resource_policy_or_continue_action
tests/tools/web/test_web_tools_provider.py:test_run_playwright_worker_process_cancellation_terminates_and_cleans_queue
tests/tools/web/test_web_tools_provider.py:test_run_playwright_worker_process_no_result_exit_cleans_queue
tests/tools/web/test_web_tools_provider.py:test_run_playwright_worker_process_timeout_terminates_and_cleans_queue
tests/tools/web/test_web_tools_provider.py:test_close_playwright_browser_clears_singletons_after_success_or_error
```
