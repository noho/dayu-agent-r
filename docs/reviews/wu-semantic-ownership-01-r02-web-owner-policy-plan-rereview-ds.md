# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy — 第二路完整 Re-Review (DS)

## 0. 审查身份与范围

- **审查类型**：第二路独立完整 adversarial plan re-review（非复述、非确认、非新 WU）。
- **审查目标**：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（经 Codex plan fix 后的最终 plan text）。
- **Immutable inputs**：
  - Controller plan-review adjudication：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`（R02-PF-01..10 唯一 disposition 真源）。
  - Plan-entry adjudication：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`（R02-B01/B02=accepted/closed）。
  - Codex plan fix artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md`。
  - 两路原始 plan review：MiMo（`plan-review-mimo.md`）、DS（`plan-review-ds.md`）——仅作原始 finding 证据；controller adjudication 优先。
  - Controller discussion：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 2 / Topic 9。
  - AGENTS.md、五份 design truth、umbrella remediation plan R02 章节。
  - 当前 HEAD production code/tests/config（`02fcc5d8`，`phaseflow/host-issues-control` 分支）。
- **审查姿势**：默认怀疑；逐项验证 R02-PF-01..10 是否真的在 plan text 中闭合，rejected 项是否未实施，owner/依赖/slice/验证/安全/deferred scope 是否一致；不把 reviewer 原建议覆盖 controller 裁决。
- **硬边界**：不得修改 plan、产品代码、测试、README、control、其它 artifact；不得 commit；Issue 178、统一 authorization、R03 均不得进入实现。
- **生成时间**：`2026-07-14 21:49:58 +0800`（本机系统时钟）。

## 1. 审查覆盖矩阵

| 维度 | 覆盖 |
|---|---|
| R02-PF-01..10 逐项 closure 验证 | §2 全文 |
| Rejected 六组未实施验证 | §3 全文 |
| 当前代码 evidence baseline 核对 | §4 全文 |
| Owner 唯一性 / 依赖链一致性 | §5.1 |
| Slice 边界 / S1→S2→S3 终态 | §5.2 |
| 验证 / smoke / coverage / pyright 可执行性 | §5.3 |
| 安全 / retained security 一致性 | §5.4 |
| Deferred scope / non-goal 边界 | §5.5 |
| Plan fix artifact 与 plan text 一致性 | §6 |
| 新发现 | §7 |

## 2. R02-PF-01..10 逐项 Closure 验证

### 2.1 验证方法

对每个 PF，以 controller adjudication 的精确裁决为真源，在 plan text 中定位对应修改，交叉验证 plan fix artifact 的声称是否与 plan 实际文字一致，并独立判断该修改是否充分闭合 finding。

### R02-PF-01 — pre-S1 / S3 循环依赖 — **已闭合**

- **Controller 裁决**：接受 finding，拒绝新增 pre-S1 micro-slice。删除 S1 entry 对未来 S3 smoke 的依赖；S3 用模块级私有 fixture constant/case；冻结值直接进入 S1。
- **Plan 修改位置**：§8.1（删除 pre-S1 S3 依赖）、§10.2-10.3（S3 用模块级私有 `LocalFixtureCase` 常量）、§11.2（S3/aggregate 只记录 metrics，只有直接不足才 stop）、§13.1-13.2（删除 `--filing-fixture` CLI 参数）。
- **独立验证**：
  - plan §8.1 当前文字："controller冻结的全部budget values直接进入S1，不再设置implementation前的数值充分性裁决"——pre-S1 数值 gate 已删除。
  - plan §10.3.2："以模块级私有常量和`LocalFixtureCase`直接接入版本化SEC AAPL HTML；不新增fixture CLI或任何用户输入协议"——无 `--filing-fixture` 残留。
  - plan §11.2："只有真实fixture或受控case直接命中/超过对应冻结ceiling...才立即stop回controller"——无 pre-S1 依赖。
  - `rg -n 'filing.fixture|--filing-fixture'` 在 plan 中仅命中 §10.2 的 "module-private versioned filing fixture case" 描述性文字和 §13.2 的 `LocalFixtureCase` 说明；无 CLI 参数定义。
- **闭合确认**：循环依赖已消除。S1 不再依赖 S3 的任何产物。

### R02-PF-02 — 删除未经授权的 ordinary atomic-write 扩展 — **已闭合**

- **Controller 裁决**：接受事实 finding，采用比 reviewer 建议更窄的 owner-bound fix。删除所有新增 ordinary atomic writer、fsync/replace/rollback 及其测试要求。保持当前 ordinary writer 语义不变。R02 只删除 credential lifecycle 自带的 publish/permission/reconcile 状态机。
- **Plan 修改位置**：§0、§2.3、§3.1、§4.4、§5.2、§6.1、§7、§10、§13、§15.4、§16。
- **独立验证**：
  - `rg -n 'fsync|os\.replace|rollback|ordinary.*atomic|原子写'` 在 plan 中零命中。
  - plan §4.4："ordinary JSON/JSONL/markdown diagnostic/smoke artifact继续使用当前writer语义；R02不新增任何普通artifact writer contract"。
  - plan §10.3.1："`_write_json`、`_write_jsonl`和summary writer保持当前普通写语义；不得新增普通writer helper，也不得复用待删credential lifecycle"。
  - plan §5.2 保留 contract 明确："现有普通artifact writer行为"。
- **闭合确认**：ordinary atomic writer 语义已完全删除。plan 明确保持现有直接写行为。

### R02-PF-03 — environment proxy 实际选择 owner — **已闭合**

- **Controller 裁决**：接受。指定 `web_http_session.py` 在一次 attempt 内使用 `Session.merge_environment_settings(...)` 取得同一次 `Session.send(...)` 的 settings，用 `requests.utils.select_proxy(...)` 选择当前 URL proxy。warning 与 proof incompatibility 基于同源 selected proxy。
- **Plan 修改位置**：§4.3、§9.2、§9.4-9.5。
- **独立验证**：
  - plan §4.3：完整指定流程——"proxy允许时，sender以空的per-call proxies输入调用`Session.merge_environment_settings(prepared.url, proxies, stream, verify, cert)`，用`requests.utils.select_proxy(prepared.url, settings["proxies"])`选择当前URL的proxy，并把同一个settings原样传给同一次`Session.send(prepared, timeout=..., allow_redirects=False, **settings)`"。
  - plan §9.2：同样精确描述同一次 `merge_environment_settings`/`send` settings 流程。
  - plan §4.3：明确 "selected proxy只作为attempt-local存在性事实使用；warning只含非敏感bool与稳定reason，不记录proxy值、URL/query、userinfo、headers、cookies或storage path"。
  - 无环境变量检查、无 urllib3 私有状态读取、无二次解析 proxy credentials。
- **闭合确认**：proxy 选择已绑定到 `requests` 公开 API 的同源 selected proxy。

### R02-PF-04 — S1/S2 transport policy 数据流 — **已闭合**

- **Controller 裁决**：接受。S1 只在 config snapshot 中构造并保存 frozen `WebHttpTransportPolicy`；S2 原子修改 `_send_authorized_request` / plain sender 的 named parameter 和全部 fetch/search callers，按 policy 选择 standard 或 proof-on transport。不得在 S1 留半迁移 sender，不得用默认参数兼容旧 caller。
- **Plan 修改位置**：§4.3、§6.1、§8.2-8.3、§9.2、§9.4。
- **独立验证**：
  - plan §8.2.5："S1不修改`_send_authorized_request`签名或行为，继续secure pinned/no-proxy"。
  - plan §9.2："S2原子修改`_send_authorized_request`和plain search sender：二者都新增无default的必填named `transport_policy`参数，并同步修改全部fetch/search callers；不存在旧caller兼容分支"。
  - plan §8.2.6：`WebToolsConfig` "S1只保存transport policy，不把它thread到sender"。
  - plan §8.3：S1 owner test 明确 "S1 sender仍是当前pinned/no-proxy行为，`_send_authorized_request`尚无transport policy参数；防止在S1留下半迁移transport"。
- **闭合确认**：S1/S2 边界清晰，无半迁移风险。

### R02-PF-05 — browser proof-on fail-close exact contract — **已闭合**

- **Controller 裁决**：接受。config 允许 browser/proof-on 共存；仅 browser fallback 真正将要启动时，在启动 Playwright 进程前 early fail。使用独立 typed reason `browser_peer_proof_unavailable`。LLM-facing message 不暴露内部术语。
- **Plan 修改位置**：§4.3、§9.3、§9.5。
- **独立验证**：
  - plan §4.3："只有HTTP结果/challenge事实已经决定进入browser fallback、且fallback真正将要启动时，caller才检查proof-on；若`dns_peer_proof_enabled=true`，在调用任何会import/启动browser的路径以及`_run_playwright_worker_process(...).process.start()`之前返回browser-owned typed failure，稳定reason唯一冻结为`browser_peer_proof_unavailable`"。
  - plan §4.3：明确 "不得在config构造时拒绝该组合，不启动Playwright进程，不复用private-network reason"。
  - plan §4.3：LLM-facing message "只表达'当前浏览器访问无法验证目标连接'，不得暴露Playwright、socket、Host/runtime或内部治理术语"。
  - plan §9.3 flowchart 明确 proof-on → `browser_peer_proof_unavailable` / no process start。
  - plan §9.5 test matrix 包含 "Playwright import/process start零调用，LLM-facing message无内部术语"。
- **闭合确认**：error type、检测时机、LLM-facing 约束均已冻结。

### R02-PF-06 — provider parser local override owner — **已闭合**

- **Controller 裁决**：接受澄清。不得修改 ConfigLoader 的 record-replace contract。`provider._parse_config` 只对 ConfigLoader 给出的最终 provider record 逐字段读取：缺失 bool/group/field 取 typed default，存在值精确校验；一个 sibling override 不改变其它 sibling 的 typed default。
- **Plan 修改位置**：§4.1、§8.2-8.3。
- **独立验证**：
  - plan §4.1："ConfigLoader继续保持workspace同id provider record整条替换、record内不做deep merge的既有contract；R02不修改该owner语义"。
  - plan §4.1："provider._parse_config只读取ConfigLoader交付的final provider record：final record缺失任一bool、resource_budget group或group field时，由provider parser为该缺失项补对应typed default；final record中已存在的sibling值保持原值"。
  - plan §8.3 test contract："保持并运行ConfigLoader既有record-replace test且不修改其contract；provider owner test把final partial record直接交给`_parse_config`，证明整体budget缺失、单group缺失、单field缺失只补对应typed default，已有sibling不变"。
- **闭合确认**：ConfigLoader 语义不变，local override 职责明确归属 provider._parse_config。

### R02-PF-07 — custom-port search result visibility 同源 — **已闭合**

- **Controller 裁决**：接受。S1 必须让 search result URL visibility 同时消费 private/custom-port 两个 typed policy 事实；不得继续由单一 `allow_private_network_url` 代签 custom port，也不得从 raw config 重读。
- **Plan 修改位置**：§6.1、§6.4、§8.2-8.3。
- **独立验证**：
  - plan §8.2.8："`search_public_web`/`_filter_visible_results`消费caller已构造的typed `WebEgressPolicy`，由其`is_url_allowed`同源决定private/custom-port visibility；不得重读raw config或保留只接private bool的旧checker contract"。
  - plan §8.3 test contract："search result visibility对private/custom-port allow/deny的决定与fetch使用同一typed policy；无raw config重读"。
  - plan §6.4 在 R02-B01 的授权边界中明确了 "S1修复search result visibility" 的窄边界。
- **闭合确认**：search visibility 已同源于 typed `WebEgressPolicy`，不再由 raw bool 代签。

### R02-PF-08 — DuckDuckGo challenge retained regression — **已闭合**

- **Controller 裁决**：接受。S2 在允许的 Web provider test 中加入 deterministic DuckDuckGo challenge response，证明迁移 transport 前后仍调用同一个 challenge detector、仍不跟随 redirect、provider business failure/result semantics 不变。`web_challenge_detection.py` 仍无 diff。
- **Plan 修改位置**：§9.5-9.6。
- **独立验证**：
  - plan §9.5 test matrix 包含完整 DuckDuckGo deterministic challenge case："plain sender返回固定challenge HTML；同一个`detect_bot_challenge` recorder被调用、`allow_redirects=false`、仍产生原`challenge_response`业务失败语义；`web_challenge_detection.py`零diff"。
  - plan §9.6 gate commands 包含 `git diff --exit-code -- dayu/tools/web/web_challenge_detection.py` 强制零 diff。
- **闭合确认**：DDG challenge regression test 已纳入 S2 test matrix，detector zero-diff 硬 gate。

### R02-PF-09 — aggregate budget type 纯组合 — **已闭合**

- **Controller 裁决**：接受为低风险自足性修复。`WebResourceBudgets` 只是 frozen typed composition，不做 `__post_init__`、跨 owner validation、default 或 facade。
- **Plan 修改位置**：§4.2、§8.2-8.3。
- **独立验证**：
  - plan §4.2："`WebResourceBudgets(http, browser, diagnostics)`：只作为无default的frozen typed composition；不实现`__post_init__`、跨owner validation、flattened property、validator facade或第二组defaults"。
  - plan §4.2："三个child budget各自在自身constructor/parser边界拥有非bool正整数校验"。
  - plan §8.3 test contract："`WebResourceBudgets`无default、无`__post_init__`/validator、无flattened compatibility properties；三个child各自拒绝非bool正整数"。
- **闭合确认**：aggregate 冻结为纯 composition，无 validator/facade/default。

### R02-PF-10 — budget evidence wording 与 S3 stop — **已闭合（缩窄接受）**

- **Controller 裁决**：只接受计划内部证据/时序矛盾，不接受重新裁决数值或要求证明对所有真实站点普遍充分。128/256 MiB、1 MiB、16/8 Mi chars、8 Ki/512 保持冻结值；删除 "必须在 pre-S1 普遍证明充分"；S3/aggregate 只记录 metrics，只有直接不足证据才 stop。
- **Plan 修改位置**：§7、§8.1、§11、§13.2、§15.3-15.4、§16-17。
- **独立验证**：
  - plan §8.1："controller冻结的全部budget values直接进入S1，不再设置implementation前的数值充分性裁决"。
  - plan §11.2："只有真实fixture或受控case直接命中/超过对应冻结ceiling、或直接产生由该ceiling导致的业务失败，才立即stop回controller；缺少万能充分性证明或live-site未来可能变化都不阻塞S1/S2/S3"。
  - plan §4.1 冻结值未改变：`134217728`、`268435456`、`1048576`、`16777216`、`8388608`、`8192`、`512`。
  - plan §16 residual risk："live网站DOM/event/error规模会变化...未来有直接超限证据时独立config change，不在backend"。
  - 无 "普遍充分"、"万能证明"、"pre-S1 裁决" 残留。
- **闭合确认**：冻结值保持、pre-S1 数值 gate 已删除、S3 stop 规则精确。

### 2.2 PF closure 汇总

| Finding | Controller 处置 | Plan 闭合状态 | 独立验证结论 |
|---|---|---|---|
| R02-PF-01 | 接受 | 已闭合 | 循环依赖消除；零 `--filing-fixture` 残留 |
| R02-PF-02 | 接受（缩窄） | 已闭合 | 零 atomic writer/fsync/replace 残留 |
| R02-PF-03 | 接受 | 已闭合 | `merge_environment_settings`+`select_proxy` 同源 |
| R02-PF-04 | 接受 | 已闭合 | S1 构造/S2 原子迁移边界清晰 |
| R02-PF-05 | 接受 | 已闭合 | `browser_peer_proof_unavailable` 冻结 |
| R02-PF-06 | 接受 | 已闭合 | ConfigLoader 不变；parser 补 defaults |
| R02-PF-07 | 接受 | 已闭合 | search visibility 同源 typed policy |
| R02-PF-08 | 接受 | 已闭合 | DDG challenge regression + zero-diff gate |
| R02-PF-09 | 接受 | 已闭合 | aggregate 纯 composition |
| R02-PF-10 | 缩窄接受 | 已闭合 | 冻结值保持；pre-S1 gate 删除 |

**全部 10 项 accepted/narrowed findings 已在 plan text 中闭合。零遗漏。**

## 3. Rejected 项未实施验证

Controller adjudication §4 明确拒绝六组。逐项验证 plan text 中未实施且未以兼容方式绕过：

| Rejected | Controller 裁决 | Plan text 证据 | 未实施确认 |
|---|---|---|---|
| MiMo `R02-PR-F05`（test 章节复制 expected values） | 拒绝：§4.1 已是真源，不得复制第二份 | §4.1 集中冻结 packaged projection 字面值；§8.3 引用该真源但不逐字段重复 | **未实施**：无第二套 expected values |
| DS `R02-DS-F03` / Q3（search endpoint egress bypass） | 拒绝：固定 endpoint 仍需 DNS/address/custom-port 与 proof 防御 | §9.2："Tavily/Serper/DuckDuckGo固定provider endpoint虽然`allow_redirects=false`，仍在首次发送前执行同一DNS/address/custom-port authorization，并在proof-on时执行同一peer防御；不得因endpoint固定而known-safe bypass" | **未实施**：无 known-safe bypass |
| DS `R02-DS-F06` / Q4（diagnostic CLI flag 保留） | 拒绝：flag 是无效兼容开关 | §4.4、§10.3 继续要求删除 `--allow-private-network-url` 及对应 option/overlay | **未实施**：flag 删除保持 |
| DS `R02-DS-F07` / Q5（search coverage 降低） | 拒绝：coverage 仍 ≥80% | §7 与 §14.1 保留逐 changed production file ≥80% | **未实施**：无例外 |
| DS `R02-DS-F11`（fixture path authority） | 被 R02-PF-01 替代 | plan 无 `--filing-fixture` CLI 参数；S3 用模块私有常量 | **未实施**：无新 path authority |
| DS Q6（ConfigLoader deep merge） | 被 R02-PF-06 闭合 | §4.1 明确 ConfigLoader record replacement 不变 | **未实施**：ConfigLoader 语义不变 |

**全部 6 组 rejected 项在 plan text 中保持未实施。无静默绕过或兼容替代。**

## 4. 当前代码 Evidence Baseline 核对

以下核对基于 HEAD `02fcc5d8` production code/tests/config 直接读取：

| Plan claim | HEAD code evidence | 一致性 |
|---|---|---|
| `WebResourceBudget` 是七字段 complete-object class（§2.2） | `web_resource_budget.py:19-44`：七字段 frozen dataclass；`web_resource_budget_from_json:88-139`：要求 complete object | ✅ 一致 |
| packaged `allow_private_network_url=false`（§2.3） | `tool_discovery.json:78`：`"allow_private_network_url": false` | ✅ 一致 |
| browser 被 `allows_private_network` 前置禁用（§2.2） | `web_playwright_backend.py:1386-1390`：`if not egress_policy.allows_private_network: return browser_egress_policy_unavailable`（两处） | ✅ 一致 |
| HTTP transport 无条件 `trust_env=false` + `proxies={}`（§2.2） | `web_http_session.py:480`：`call_session.trust_env = False`；line 500：`proxies={}` | ✅ 一致 |
| `_StorageStateLifecycle` 存在（§2.2） | `diagnose_web_access.py:211`：class 定义；line 1942：`_storage_state_owner_final_name`；line 2026：`_reconcile_storage_state_directory` | ✅ 一致 |
| `--storage-state-out`/`--storage-state-ttl-seconds` 存在（§2.2） | `diagnose_web_access.py:1202,1208`：CLI arguments | ✅ 一致 |
| `test_config_loader.py` 断言 `allow_private_network_url is False`（§6.4） | `test_config_loader.py:471`：`assert web_provider.config["allow_private_network_url"] is False` | ✅ 一致 |
| `web_search_providers.py` 直接 import `WebResourceBudget`（§6.4） | `web_search_providers.py:22`：`from .web_resource_budget import WebResourceBudget` | ✅ 一致 |
| 新五 bool 字段不存在于 config 或代码 | `rg 'allow_custom_port_url\|dns_peer_proof_enabled\|allow_environment_proxy\|browser_enabled' dayu/config/tool_discovery.json` 零命中 | ✅ 一致（未提前实施） |
| `WebToolsConfig` 只有 `allow_private_network_url: bool`，无独立 custom-port/peer/proxy/browser 字段 | `web_tools.py:200`：`allow_private_network_url: bool = False` | ✅ 一致 |

**全部 plan claim 与 HEAD code evidence 一致。无 silent drift。**

HEAD working tree status：
- `git diff --name-only HEAD`：仅 `docs/host/issues-implementation-control.md`（既有 tracked 修改，不在 R02 allowlist）。
- 未跟踪文件：plan、plan-entry adjudication、plan-review controller adjudication、两路 plan review、fix-codex artifact。**无产品、测试、README 修改。**

## 5. 跨维度一致性验证

### 5.1 Owner 唯一性 / 依赖链

| 语义 | Owner（plan 指定） | 依赖方向 | 一致性 |
|---|---|---|---|
| 五 bool config | `provider._parse_config` → `WebToolsConfig` snapshot | ConfigLoader → provider parser → typed snapshot | ✅ 单向 |
| 三 budget groups | `web_resource_budget.py` typed defaults → `WebResourceBudgets` | parser → aggregate → per-consumer typed budget | ✅ 单向 |
| HTTP transport policy | `WebHttpTransportPolicy` in `WebToolsConfig` → `_send_authorized_request` | snapshot → S2 sender | ✅ S1 不传递 |
| Browser capability | `WebToolsConfig.browser_enabled` → browser backend gate | snapshot → fallback caller → backend | ✅ 独立于 private |
| Egress policy | `WebEgressPolicy` → `authorize_http_target` → per-hop | snapshot → fetch/search/browser consumers | ✅ 唯一 |
| Diagnostics v2 | `web_diagnostics.py` producer | diagnostic budget → projection | ✅ 保留 |
| Credential lifecycle | 删除 → Issue #178 | 删除链完整 | ✅ 不迁移 |

无 owner 冲突、无双向依赖、无跨层穿透。

### 5.2 Slice 边界 / S1→S2→S3 终态

| Slice | Plan 定义 | 依赖 | 终态 |
|---|---|---|---|
| S1 | Config owner：packaged defaults、parser、typed snapshot、三 budget owners | 仅依赖 accepted plan commit | S1 accepted commit 后 config snapshot 完整；sender 仍 secure pinned/no-proxy |
| S2 | HTTP transport/browser executor：proxy/proof 分支、browser 解耦、challenge regression | 依赖 S1 accepted commit + typed snapshot | S2 accepted commit 后 transport/browser 行为完整；retained security 全回归 |
| S3 | Diagnostics cleanup：删除 credential lifecycle、保留 v2/read input/ordinary writer | 依赖 S2 accepted commit | S3 accepted commit 后 lifecycle 全删；v2 保留；ordinary writer 不变 |

- S1→S2→S3 严格串行：§8.1、§9.7、§10.5 均明确前一 slice accepted commit 前不得进入下一 slice。
- S1 不依赖 S3：已由 R02-PF-01 修复。
- S2 不依赖 S3：transport/browser 执行不依赖 diagnostic cleanup。
- 每 slice 形成完整终态：无 "等下一 slice 再补" 的悬挂 contract。

### 5.3 验证 / Smoke / Coverage / Pyright 可执行性

| 验证维度 | Plan 指定 | 可执行性判断 |
|---|---|---|
| S1 pytest | umbrella filter + full provider file + config-loader node | ✅ 命令明确（§8.4）；baseline 已验证可行（§17.1：122 passed） |
| S2 pytest | umbrella filter + deterministic proxy/peer/browser + DDG challenge | ✅ 命令明确（§9.6）；baseline 已验证（§17.1：25 passed） |
| S3 pytest | 三份完整 Web tests + lifecycle deletion assertions | ✅ 命令明确（§10.4）；baseline 已验证（§17.1：36 passed） |
| Deterministic local smoke | `smoke_web_ci.py --external-limit 0 --include-playwright` | ✅ 命令明确（§13.1）；baseline 已验证（§17.1：exit 0） |
| Real Playwright/diagnostic smoke | 模块私有 fixture constant + `LocalFixtureCase` + SEC AAPL HTML | ✅ 不依赖新增 CLI 参数 |
| Coverage | 逐 changed production file ≥80% | ✅ 命令明确（§14.1） |
| Pyright | 0 新增/扩散 | ✅ baseline 已验证（§17.1：0 errors） |
| Source/propagation scans | §8.4、§9.6、§10.4、§14.3 精确 rg 命令 | ✅ 每 scan pattern 明确 |
| Allowed-file scan | `git diff --name-only` 落入闭集 | ✅ 闭集在 §6.1-6.2 |

所有 gate command 均可直接执行，无循环依赖。

### 5.4 安全 / Retained Security 一致性

| Retained security | Plan 位置 | 验证要求 | 一致性 |
|---|---|---|---|
| Scheme/host/port/address 每跳重检 | §5.2、§9.2 | S2 test matrix | ✅ |
| Dangerous/unspecified/multicast 始终拒绝 | §4.3、§5.2 | S2 test matrix | ✅ |
| Mixed DNS fail closed | §4.3、§5.2 | S2 test matrix | ✅ |
| Peer proof mismatch fail closed | §5.2、§9.2 | S2 test matrix | ✅ |
| Proxy disabled 不读环境 | §4.3、§9.2 | S2 test matrix | ✅ |
| Proxy+proof typed incompatibility | §4.3、§9.2 | S2 test matrix | ✅ |
| Budget boundaries | §4.2、§9.5 | S2 test matrix（exact/+1） | ✅ |
| Challenge detection 保留 | §5.2、§9.5 | DDG regression test | ✅ |
| Diagnostics v2/revision 2 保留 | §4.4、§10.3-10.4 | S3 source scans | ✅ |
| Header/cookie/URL/credential redaction | §5.2 | S3 artifact scan | ✅ |
| Containment/symlink 防御 | §5.2、§4.4 | 保留现有 | ✅ |
| Fixed endpoint 不绕过 egress | §9.2、§9.5 | S2 test（controller rejected bypass） | ✅ |

无 retained security 被静默降级或遗漏。

### 5.5 Deferred Scope / Non-Goal 边界

| Non-goal | Plan 位置 | 边界确认 |
|---|---|---|
| Issue #178 credential lifecycle | §0、§5.3、§16 | 仅 residual destination；无 implementation |
| 统一 tool authorization framework | §2.1、§5.3、§16 | Topic 9 no-code；无设计/预埋 |
| R03 accepted-result/LLM projection | §5.3、§16、§17 | 无 diff、无依赖 |
| Policy DSL / capability token / sandbox | §2.1、§5.3 | 明确非目标 |
| 新 proxy credential schema / PAC | §5.3 | 明确非目标 |
| 修改 challenge detector | §6.1、§9.5 | zero-diff 硬 gate |
| 修改 Host/Engine/Service/UI/Fins | §5.3 | 明确非目标 |
| 兼容旧 config/schema/import/tests | §5.3 | 明确禁止 |

**所有 deferred scope 边界清晰，无泄漏到 implementation slices。**

## 6. Plan Fix Artifact 与 Plan Text 一致性

Codex fix artifact（`plan-fix-codex.md`）声称对 plan 的修改位置和闭合内容，与 plan 当前文本逐项核对：

| PF | Fix artifact 声称的 plan 修改位置 | Plan text 实际内容 | 一致性 |
|---|---|---|---|
| PF-01 | §8.1、§10.2-10.3、§11.2、§13.1-13.2 | 对应位置已更新 | ✅ |
| PF-02 | §0、§2.3、§3.1、§4.4、§5.2、§6.1、§7、§10、§13、§15.4、§16 | 对应位置已更新 | ✅ |
| PF-03 | §4.3、§9.2、§9.4-9.5 | 对应位置已更新 | ✅ |
| PF-04 | §4.3、§6.1、§8.2-8.3、§9.2、§9.4 | 对应位置已更新 | ✅ |
| PF-05 | §4.3、§9.3、§9.5 | 对应位置已更新 | ✅ |
| PF-06 | §4.1、§8.2-8.3 | 对应位置已更新 | ✅ |
| PF-07 | §6.1、§6.4、§8.2-8.3 | 对应位置已更新 | ✅ |
| PF-08 | §9.5-9.6 | 对应位置已更新 | ✅ |
| PF-09 | §4.2、§8.2-8.3 | 对应位置已更新 | ✅ |
| PF-10 | §7、§8.1、§11、§13.2、§15.3-15.4、§16-17 | 对应位置已更新 | ✅ |

Fix artifact §4.2 的零残留 scan 与实际 plan text 一致。fix artifact §4.2 的 frozen values scan（`134217728` 等七项）与 plan §4.1 一致。

## 7. 新发现

### 7.1 无新 Material Finding

本 re-review 在已闭合的 R02-PF-01..10 之外，对 plan text 做了完整的独立 adversarial 扫描。以下维度均未发现新的 material finding：

- **动机/root cause**：仍成立且同源（§2.1-2.2 未变）。
- **Owner 唯一性**：无新 owner 冲突或 ambiguity。
- **Slice 边界**：S1/S2/S3 严格串行，无循环依赖。
- **Contract 完整性**：五 bool、三 budget、HTTP transport、browser、diagnostics、credential lifecycle 删除——所有 contract 均已指定。
- **安全**：retained security 完整，无 bypass。
- **测试**：每 slice test matrix 完整覆盖 happy path 和 failure path。
- **Coverage/pyright**：逐文件门禁明确，命令可执行。
- **README**：决策表明确（§12），按 AGENTS.md 触发规则。
- **Stop conditions**：§15.3 覆盖全面，无遗漏。
- **Residual risks**：§16 每项有 owner/destination。
- **Deferred scope**：Issue 178、统一 authorization、R03 均无泄漏。

### 7.2 观察（非 Finding，不阻塞）

以下为 reviewer 对 plan 质量的观察，不构成 blocker 或 material finding：

1. **Plan 长度与 detail level**：plan 全文 852 行，对每个 file/symbol/call chain/test case 给出精确指令。这显著降低了 implementation agent 的推导空间，但也意味着 implementation agent 必须逐字遵循——偏离 plan 字面指令会导致违反 contract。建议在 implementation artifact 中引用 plan 具体行号以建立 traceability。

2. **S3 fixture constant 失败语义**：plan §11.2 说 "固定常量缺失或不是regular file时test/smoke直接失败，不建立通用resolve/containment/path authority"。这个 fail-fast 语义对于版本化仓库内 fixture 是合理的，但 implementation agent 应注意区分 "fixture 缺失"（环境配置错误）和 "fixture 内容变化"（版本升级导致的预期行为变更）。

3. **S1 Transport Policy 类型定义位置**：plan §8.2.5 要求在 `web_http_session.py` 中新增 `WebHttpTransportPolicy`。当前 `web_http_session.py` 主要承载 HTTP adapter/connection/pool 基础设施。新类型在概念上属于 config projection，放在 `web_http_session.py` 而非 `web_resource_budget.py`（后者承载 budget types）是可以接受的——transport policy 的 consumer 是 `_send_authorized_request`，与 HTTP session 模块同址。

## 8. Open Questions

本 re-review 未发现新的 open question。原始两路 plan review 的 open questions 处置如下：

| Original OQ | 状态 |
|---|---|
| MiMo OQ-1（browser proof-on 实现边界） | 被 R02-PF-05 闭合——plan §4.3 已指定 pre-process-start early fail + typed reason |
| MiMo OQ-2（aggregate type 行为） | 被 R02-PF-09 闭合——plan §4.2 已冻结为纯 composition |
| DS Q1（pre-S1 数值 gate 可执行性） | 被 R02-PF-01 闭合——pre-S1 gate 已删除 |
| DS Q2（atomic writer 是否需要产品裁决） | 被 R02-PF-02 闭合——ordinary atomic writer 已删除 |
| DS Q3（search endpoint egress bypass） | Controller rejected——plan 保留 DNS/egress/peer 防御 |
| DS Q4（diagnostic CLI flag 删除） | Controller rejected——plan 保持删除 flag |
| DS Q5（search coverage 是否降低） | Controller rejected——plan 保持 ≥80% |
| DS Q6（ConfigLoader deep merge） | 被 R02-PF-06 闭合——ConfigLoader 不变，parser 补 defaults |

**无未闭合 open question。**

## 9. Residual Risks

Plan §16 列出的 residual risks 经本 re-review 确认处置合理：

| Residual | Plan 处置 | 本 review 评估 |
|---|---|---|
| credential lifecycle → Issue #178 | 删除提前实现，保留 read input | ✅ 处置正确 |
| live 网站规模变化 | 冻结可配置 ceilings；S3/aggregate 只记录 metrics | ✅ 处置正确；R02-PF-10 已缩窄 |
| proxy 下无法证明 origin peer | proof+proxy typed fail closed | ✅ 处置正确 |
| Playwright 无法提供 peer proof | browser typed unavailable/fail closed | ✅ 处置正确；R02-PF-05 已精确化 |
| external provider/challenge 波动 | local deterministic hard gate + external 补充 | ✅ 处置正确 |
| unified authorization → Topic 9 | 不设计/不预埋 | ✅ 处置正确 |

无新增 residual risk。

## 10. Final Plan Re-Review Conclusion

**Verdict: `pass`**

### 通过理由

1. **全部 10 项 R02-PF 已闭合**：controller 接受的 9 组 fix 和 1 组 narrowed fix 均已在 plan text 中精确实施。逐项验证确认 plan 修改位置与 controller 裁决一致，修改内容充分闭合原始 finding。

2. **全部 6 组 rejected 项保持未实施**：controller 拒绝的替代方案未进入 plan text。无静默绕过、兼容替代或变通实施。

3. **当前代码 evidence baseline 与 plan claims 一致**：HEAD production code 的 `WebResourceBudget`、browser/private coupling、`_StorageStateLifecycle`、`--storage-state-out`、unconditional proxy/pin、packaged defaults、test assertions 均与 plan 根因分析一致。无 silent drift。无 premature implementation。

4. **Owner 链唯一且单向**：config → parser → typed snapshot → per-consumer 的依赖方向清晰，无跨层穿透、无双向依赖、无多 owner 冲突。

5. **Slice 边界可执行**：S1→S2→S3 严格串行，无循环依赖。每 slice 形成完整终态。所有 gate command 可直接执行。

6. **安全机制完整**：retained security（redirect recheck、dangerous/mixed DNS deny、peer proof、proxy/proof incompatibility、challenge detection、diagnostics v2、redaction、containment）均在 plan 中有 owner-level 测试和 gate command 覆盖。

7. **Deferred scope 清晰**：Issue #178、统一 authorization、R03 在 plan 中仅作为 non-goal、residual destination 或 stop condition 出现，不进入任一 implementation slice。

8. **Plan fix artifact 与 plan text 一致**：fix-codex.md 声称的修改位置与实际 plan text 逐项核对通过。

### 积极发现

- plan 的 root cause 分析（§2.2）仍然精确，六项错误语义与 HEAD 代码直接证据一一对应。
- plan 的 `WebEgressPolicy` 设计（§4.3）正确拆分了 private/custom-port，保留了所有 unconditional deny（dangerous/unspecified/multicast）。
- plan 的 S1/S2 transport policy 数据流设计避免了 "半迁移 sender" 的常见陷阱。
- plan 的 browser proof-on fail-close contract（R02-PF-05）精确指定了 error type、检测时机和 LLM-facing 约束。
- plan 的 stop conditions（§15.3）覆盖全面：owner drift、security regression、数值不足、pyright/coverage 失败、allowlist 越界、accepted finding 未闭合。

### Handoff

本 re-review 到此停止。不修改 plan、产品代码、测试、README、control 或其它 artifact；不 commit。

R02 plan 当前状态：`PLAN REVIEW FINDING FIX VERIFIED — ALL 10 PFs CLOSED — ALL REJECTED ITEMS ABSENT — WAITING CONTROLLER FOR FINAL ACCEPTED-PLAN COMMIT`。

后续 gate 只能由 controller 授权：MiMo 第二路 re-review 完成 → controller 消费两路 re-review 并裁决 → 产生 accepted-plan commit → 授权 S1 implementation。

---

**审查完成时间**: 2026-07-14 21:49:58 +0800
**审查分支**: `phaseflow/host-issues-control`
**审查基线**: `02fcc5d8325fc7c3c2ef2f60a049910edb6ebfcb`
**审查 artifact**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-ds.md`
