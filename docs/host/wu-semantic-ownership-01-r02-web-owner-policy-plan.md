# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy 独立实施计划

## 0. Gate 身份、base、结论与硬边界

- **umbrella**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **内部 remediation sub-WU**：`R02`，slug 固定为 `r02-web-owner-policy`；它不是新 WU、feature、issue，也不改变 umbrella 身份。
- **artifact 身份**：本文是 R02 的独立 plan gate artifact；不是 implementation、review、completion 或 control artifact。
- **mandatory temporal baseline**：分支 `phaseflow/host-issues-control`，plan-time HEAD `02fcc5d8325fc7c3c2ef2f60a049910edb6ebfcb`；证据审计范围 `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`。
- **当前 gate verdict**：`PLAN REVIEW FINDING FIX AUTHORED — WAITING CONTROLLER / NOT ACCEPTED / NO IMPLEMENTATION`。`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md` 已精确接受并关闭 `R02-B01`、`R02-B02`；两路完整 plan review 已完成，且 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md` 是 `R02-PF-01..10` finding disposition 的唯一真源。本文已消费全部 accepted/narrowed finding，但尚未经过 controller validation、双路完整 re-review 或 accepted-plan commit，因此仍不是 accepted/code-generation execution truth，绝不授权 implementation。
- **plan-entry blocker 状态**：`R02-B01=accepted/closed`、`R02-B02=accepted/closed`。只按 adjudication 增加一个 production file和一个 test file；不得用旧类型名、兼容 property、跳过受影响测试或 inherited-failure 声明绕过，也不得再扩展其它 allowlist。
- **本 gate 写权限**：AgentCodex只修改本文并新增固定 fix artifact `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md`；plan-entry adjudication、两路 review与plan-review controller adjudication均为只读输入。AgentCodex不得改产品代码、测试、README、design、control或既有review/controller artifact；不得 commit、push、建 PR、启动 re-review 或进入任一 implementation slice。
- **执行终点**：本轮只消费 plan-review controller adjudication、完成plan finding fix与只读验证，随后立即停止等待controller。只有controller validation、双路完整re-review及其controller裁决闭合并产生accepted-plan commit后，R02才可进入S1 implementation。
- **Issue 178**：`WU-SEMANTIC-OWNERSHIP-01-WEB-STORAGE-R1` / GitHub Issue #178 是未来 credential storage-state lifecycle 的唯一 owner。R02 只删除提前实现的 lifecycle，保留显式路径输入，并保持现有普通诊断/smoke artifact writer语义不变；不实施、部分实施或预埋 Issue 178。

## 1. 必读真源、三路指定证据与冲突规则

### 1.1 裁决优先级

本文按以下顺序冻结 contract；低优先级材料不能覆盖高优先级裁决：

1. 本轮用户指令与 `AGENTS.md` 的语义 owner、LLM-facing、分层、类型、测试和 README 硬约束。
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 2 / Topic 9 的最终 controller discussion。
3. 永久设计真源：`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
4. `docs/host/issues-implementation-control.md` 与 `docs/phaseflow-umbrella-optimization-control.md` 的 gate、baseline failure、成本和 handoff 纪律。
5. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` 的全局规则、R02 mandatory starting baseline、闭集和 retained-security 约束。
6. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`：只拥有 `R02-B01/B02` 的 plan-entry allowlist disposition与精确授权边界；不接受计划中的其它设计项，也不授权 implementation。
7. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`：`R02-PF-01..10` finding disposition与rejected边界的唯一真源；两路review建议不得覆盖它。
8. 下表精确指定的三路原始 overdesign review；它们只提供当前代码证据和反例，发生冲突时必须服从 controller discussion。
9. 当前 HEAD 的 production code、tests、fixtures、README 与可执行 smoke；它们是 temporal evidence 或被修复对象，不是产品授权真源。

### 1.2 精确指定的三路原始 review evidence table

| route | 精确文件 | 本计划用途 | 冲突 disposition |
|---|---|---|---|
| Codex designtruth | `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-codex.md` | Web private/browser、proxy/peer、budget、diagnostics/storage lifecycle 的代码位置与反例 | 仅代码证据；controller discussion 优先 |
| DS designtruth | `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-ds.md` | 跨层 owner、过度耦合与 deferred 边界的独立证据 | 仅代码证据；controller discussion 优先 |
| MiMo designtruth | `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-mimo.md` | Web 默认、resource contract、诊断 overdesign 的独立证据 | 仅代码证据；controller discussion 优先 |

`docs/reviews/wu-semantic-ownership-01-overdesign-audit-codex.md` 已完整读取，只作为补充历史审计索引；它不替代上表 Codex designtruth review，也不是第四路裁决来源。

### 1.3 Plan-entry controller adjudication evidence

| artifact | accepted decision | exact boundary | gate effect |
|---|---|---|---|
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md` | `R02-B01=accepted` | production allowlist只增加`dayu/tools/web/web_search_providers.py`：S1仅收窄到`HttpResourceBudget`；S2仅复用同一Web HTTP transport policy且不改变provider业务语义 | production allowlist drift关闭 |
| 同上 | `R02-B02=accepted` | test allowlist只增加`tests/runtime/test_config_loader.py`：仅更新packaged Web五bool/三budget groups精确断言 | test allowlist drift关闭 |

该adjudication把ordinary writer边界、数值gate sequencing与具体transport API设计留给双路完整plan review挑战；最终disposition以§1.4的controller artifact为准。无其它allowlist扩展。

### 1.4 双路 plan review 与 Controller finding adjudication

| artifact | role | 本计划消费方式 |
|---|---|---|
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-mimo.md` | 第一路完整plan review | 只提供finding与直接证据，不拥有disposition |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-ds.md` | 第二路完整plan review | 只提供finding与直接证据，不拥有disposition |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md` | 唯一finding disposition真源 | 精确接受/缩窄`R02-PF-01..10`并拒绝六组替代方案；本文不得重新裁决 |

本轮只实施controller接受或缩窄接受的plan文字修复。固定provider endpoint仍执行初始DNS/address/custom-port与proof防御；diagnostic `--allow-private-network-url`仍删除；changed production file coverage仍逐文件`>=80%`；不恢复64 KiB、不新增fixture path authority、不实施Issue #178、统一authorization、其它deferred Issue或R03。

## 2. 第一性原理判断、root cause 与 owner

### 2.1 动机成立，但不授权统一 framework

缺陷真实且为 `production-high`：当前 Web config 把互不等价的部署事实压成一个 private bool 和一个七字段 budget object；HTTP transport 又把 DNS pin、peer proof、proxy 选择绑定成单一路径；browser 把 private permission 当成 browser capability；diagnostic utility 则自行成为 credential retention/publish/cleanup owner。后果不是代码风格问题，而是合法 private/custom-port/proxy/browser 组合被拒绝、独立预算不能局部配置，以及未获产品授权的 credential lifecycle 被对外承诺。

正确修复是把现有 Web owner 内部事实拆回各自 owner，并删掉无授权 lifecycle。它不需要角色、policy DSL、capability token、sandbox 或统一 tool authorization framework；Topic 9 仍是 no-code。

### 2.2 同源 root cause 证据

| 错误语义 | owner-side 直接证据（HEAD） | 真实传播链 | 正确 owner |
|---|---|---|---|
| private 同时代签 custom port | `web_egress_policy.py::WebEgressPolicy` 只有 `allow_private_network`；false 时 custom port 与 private address 同时拒绝 | `provider._parse_config -> WebToolsConfig -> URL decision -> every redirect` | packaged Web config + typed `WebEgressPolicy` |
| private 同时代签 browser | `web_playwright_backend.py::_playwright_sync_worker` / `_fetch_and_convert_with_playwright` 在 `allows_private_network == false` 时直接返回 `browser_egress_policy_unavailable` | HTTP fail/challenge -> `_try_playwright_fallback` -> browser 永不运行，即便公网 JS URL | `browser_enabled` 的 config owner；地址权限仍归 egress policy |
| peer proof 与 proxy 被硬绑定为“永远 pin、永远禁 proxy” | `web_http_session.py::_TargetBoundHTTPAdapter` 拒绝 proxies；`_send_authorized_request` 强制 `trust_env=false` 和 `proxies={}`；连接始终走 numeric pinned pool | HTTP attempt -> adapter -> pinned connection -> response | attempt-local HTTP transport policy；config 只提供 bool snapshot |
| 七个预算由一个完整对象代签 | `web_resource_budget.py::WebResourceBudget` 同时含 HTTP 2、browser 3、diagnostic 2 字段；`web_resource_budget_from_json` 要求七字段 complete object | provider -> search/fetch/browser/diagnostics 共用一个 bag | 三个小型 typed budget；各 executor 只接自己的 owner type |
| credential lifecycle 无产品 owner | `utils/diagnose_web_access.py::_StorageStateLifecycle`、`_storage_state_owner_final_name`、`_reconcile_storage_state_directory`、`_prepare_storage_state_lifecycle` 产生 TTL、owner filename、权限、orphan/expired、publish/reconcile | CLI -> browser context -> credential publish/cleanup -> diagnostic artifact fields | Issue #178；R02 只负责删除 |

根因不在 UI、Engine、Host 或 README。下游 warning、兼容字段、测试 shim 或额外 fallback 都不能修正 owner；实现必须在 config/parser、HTTP/browser executor 和 diagnostic producer 边界完成。

### 2.3 当前代码 evidence baseline

| baseline item | HEAD 直接证据 | plan disposition |
|---|---|---|
| packaged private/default | `tool_discovery.json` 只有 `allow_private_network_url=false`；没有 custom-port、peer-proof、proxy、browser capability 字段 | S1 改为五个独立 bool；private/custom/proxy/browser 默认 true，peer proof 默认 false |
| packaged budgets | config 没有显式 `resource_budget`；代码默认 25/50 MiB、64 KiB、5M/1M chars、1024 chars/80 events | S1 由 config 显式投影三 owner groups，删除旧数值 |
| parser | `provider._parse_config` 只解析 private bool 和 complete `resource_budget`，未对所有新增 top-level 字段形成 typed snapshot | S1 exact-field parser + group/field local override + precise error path |
| URL safety | `WebEgressPolicy` 每 hop resolve，mixed DNS 只要含危险地址即拒绝；dangerous/unspecified/multicast 检查存在 | 保留；仅把 private/custom-port decision 拆成独立字段 |
| redirect | `web_fetch_orchestrator._request_with_safe_redirects` 每跳重新授权 | 原样保留并复测 |
| HTTP transport | pinned numeric connection 与 actual peer comparison 当前恒开；environment proxies 当前恒禁 | S2 按 `dns_peer_proof_enabled` / `allow_environment_proxy` 选择 attempt-local path |
| browser | private=false 前置拒绝 browser；route/URL recheck、DOM/text budget、challenge evidence 已存在 | 删除 capability coupling；保留 address policy、challenge 和 budgets |
| challenge | `web_challenge_detection.py` 独立 producer；fetch/search fallback 消费 typed decision | 保留；该文件不在 R02 allowlist且预期无 diff |
| diagnostics | `WEB_DIAGNOSTIC_SCHEMA_VERSION="web-diagnostics-v2"`、revision `2`、redaction/allowlist/budgets 已存在 | S3 保留 exact schema/revision 与 challenge evidence |
| storage read input | production `_resolve_playwright_storage_state_path` 是 pre-range 的 host-candidate read-only lookup；显式 path/dir 被 HTTP cookie/browser context 消费 | 保留显式 input；不把它误删或扩建成 Issue #178 |
| storage lifecycle | diagnostic TTL/output/owner/reconcile/publish 在 `94a12c9e` 引入 | S3 全删及 artifact/test contract 删除 |
| ordinary diagnostic write | 当前 JSON/JSONL/summary 直接写 final path | R02保持现有普通writer语义不变；只删除credential lifecycle自带的publish/permission/reconcile状态机，不迁移或复用该状态机 |

## 3. Temporal audit 与 baseline drift

### 3.1 `b1a0631f^..02fcc5d8` 关键历史

| commit | 当前 R02 相关语义 | disposition |
|---|---|---|
| `a20efac7` | R3-E S1 Web egress owner：private deny、DNS/pin/redirect 防御 | 保留安全机制，拆开默认与独立 policy |
| `728e73af` | R3-E S2 Web resource owner：七字段 complete object、旧小 ceilings | 以三 owner typed budgets 替换 |
| `94a12c9e` | R3-E S3 diagnostics/storage lifecycle | diagnostics v2 保留；credential lifecycle 删除 |
| `02fcc5d8` | control 进入 R02 independent plan gate | 只定义 gate，不改变 Web code |

`01bbf74c..02fcc5d8` 在 R02 Web production、允许测试和 README 路径上无 diff，因此 umbrella 编写后的 Web 行为没有 silent product drift。存在的两类 plan-time drift 是：

1. umbrella对ordinary diagnostic artifact既有writer行为的假设与HEAD不一致；Controller已裁决这不授权R02新增普通artifact行为，因此当前普通writer保持不变，也不构成R02 residual obligation；
2. 当前调用链/packaged-default consumer 暴露 umbrella closed allowlist 漏项；该 material drift 已由 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md` 精确接受并关闭，最终边界见 §6.4。

### 3.2 当前 owner/contract 判定

- config owner、HTTP transport owner、browser capability owner、diagnostics v2 owner与 Issue #178 destination 均清晰，没有 owner blocker。
- private/custom/proxy/peer/browser 与三组 budget 的产品裁决没有漂移。
- `R02-S1 -> R02-S2 -> R02-S3` 的依赖顺序没有漂移。
- plan-entry allowlist blocker已全部关闭，没有其它allowlist扩展。双路完整plan review、controller finding adjudication与本轮plan fix已完成；implementation仍被controller validation、双路完整re-review及accepted-plan commit gate阻止，禁止提前启动re-review或编码。

## 4. Exact target config 与 typed owner contract

### 4.1 Packaged Web config

`dayu/config/tool_discovery.json` 的 Web provider 必须显式包含以下值；它是部署默认的 packaged projection：

```json
{
  "allow_private_network_url": true,
  "allow_custom_port_url": true,
  "dns_peer_proof_enabled": false,
  "allow_environment_proxy": true,
  "browser_enabled": true,
  "playwright_channel": "chrome",
  "playwright_storage_state_dir": ".dayu/web_tools_storage_states",
  "resource_budget": {
    "http": {
      "wire_body_bytes": 134217728,
      "decoded_body_bytes": 268435456
    },
    "browser": {
      "warmup_body_bytes": 1048576,
      "dom_chars": 16777216,
      "text_chars": 8388608
    },
    "diagnostics": {
      "error_chars": 8192,
      "events": 512
    }
  }
}
```

`provider._parse_config` 是唯一 raw JSON parser owner：

- 五个 bool 独立解析；bool-as-int、字符串和 null 均 fail fast，错误消息含精确字段路径。
- `ConfigLoader`继续保持workspace同id provider record整条替换、record内不做deep merge的既有contract；R02不修改该owner语义。`provider._parse_config`只读取ConfigLoader交付的final provider record：final record缺失任一bool、`resource_budget` group或group field时，由provider parser为该缺失项补对应typed default；final record中已存在的sibling值保持原值。
- group/object 类型错误、unknown group/field、bool 数值、零/负数均 fail fast；不得 loose parse、静默忽略或 whole-object fallback。
- 一次 discovery 产生 immutable `WebToolsConfig` snapshot；同一 tool attempt 不重新读取 JSON/environment 配置。
- packaged JSON 与 typed defaults 的同源含义固定为：后端只接收 parser 生成的 typed values，不拥有任何数值默认；conformance test 逐字段证明 packaged projection 等于 typed constants。不得在 HTTP/browser/diagnostic backend 再写一份 fallback literal。

### 4.2 三个 budget owner

`web_resource_budget.py` 只定义以下 frozen typed values、默认常量和 parser helper：

- `HttpResourceBudget(wire_body_bytes, decoded_body_bytes)`：只由 HTTP fetch/search response materialization 消费。
- `BrowserResourceBudget(warmup_body_bytes, dom_chars, text_chars)`：只由 browser warmup/DOM/text producer 消费。
- `DiagnosticResourceBudget(error_chars, events)`：只由 diagnostics v2 projection 消费。
- `WebResourceBudgets(http, browser, diagnostics)`：只作为无default的frozen typed composition；不实现`__post_init__`、跨owner validation、flattened property、validator facade或第二组defaults。三个child budget各自在自身constructor/parser边界拥有非bool正整数校验。

删除 `WebResourceBudget` 七字段 class、旧 flattened JSON field、complete-object requirement 和所有旧默认。不得保留 alias、re-export、`max_*` compatibility property 或接收 old/new 两种 schema。

### 4.3 Egress、transport 与 browser capability

`WebEgressPolicy` 只拥有地址/端口决定：

- `allow_private_network_url=true` 默认允许合法 private/local addresses；false 时拒绝 private/local。
- `allow_custom_port_url=true` 默认允许合法非标准 HTTP(S) port；false 时仅允许标准 port。
- dangerous、unspecified、multicast、非法 scheme/host/port 始终拒绝，不能被 private/custom allow 放开。
- 每个初始 URL 和 redirect hop 都重新 resolve/authorize；mixed DNS 在任一答案危险或被 private policy 拒绝时整组拒绝。
- authorization result 继续携带本 attempt 的 approved numeric addresses，供 peer proof 开启时使用；关闭 proof 不等于跳过 DNS/address policy。

HTTP transport policy 是 attempt-local typed snapshot，字段只为：

- `dns_peer_proof_enabled=false`：默认走标准 `requests.Session` transport；仍在发送前做 DNS/address/custom-port policy，但不强制 numeric pin/peer comparison。
- `dns_peer_proof_enabled=true`：走当前 numeric pin + actual peer proof；mismatch fail closed。
- `allow_environment_proxy=true`时设置attempt-local `Session.trust_env=true`。同一次attempt只prepare一次request；调用`Session.merge_environment_settings(prepared.url, proxies, stream, verify, cert)`得到将原样传给同一次`Session.send(prepared, ..., **settings)`的settings，再用`requests.utils.select_proxy(prepared.url, settings["proxies"])`得到该URL的selected proxy。warning与proof incompatibility只消费这个同源selected proxy，不检查环境变量是否存在、不读urllib3私有状态、不二次解析proxy credentials。
- `allow_environment_proxy=false`：attempt使用`trust_env=false`，清空session/per-call proxies并保证传给同一次`Session.send`的settings中`proxies={}`；不得读取environment proxy。browser worker同样收到剥离proxy env。
- proof=true 且环境/显式 proxy 实际生效：返回 typed `proxy_peer_proof_incompatible`，不得静默关闭 proof或绕过 proxy。R02 不新增显式 proxy URL/credential config。
- selected proxy只作为attempt-local存在性事实使用；warning只含非敏感bool与稳定reason，不记录proxy值、URL/query、userinfo、headers、cookies或storage path。
- S1只在`WebToolsConfig` snapshot内构造并保存frozen `WebHttpTransportPolicy`，`_send_authorized_request`与所有caller仍保持当前secure pinned/no-proxy行为。S2在一个原子diff内给`_send_authorized_request`、plain search sender及全部fetch/search caller增加必填named parameter `transport_policy: WebHttpTransportPolicy`；不得提供兼容default，也不得留下半迁移caller。

Browser capability 直接由 `WebToolsConfig.browser_enabled: bool` 表达，不为一个 bool 创建一字段 class：

- false 时不尝试 Playwright，返回现有 browser-disabled/unavailable 类 typed reason；challenge detection 事实仍保留。
- true 时 browser 可独立运行；它不授予 private/custom-port 权限。`browser_enabled=true`与`dns_peer_proof_enabled=true`是合法config组合，HTTP proof path仍照常运行。
- `allow_private_network_url=false` 只拒绝 private browser request，不能阻止公网 JS 页面执行。
- browser route/navigation 继续逐 URL 应用 `WebEgressPolicy`；browser backend分别接收`BrowserResourceBudget`处理rendered input、`DiagnosticResourceBudget`处理其typed error/event投影，不能把两类字段重新合成browser bag。
- 只有HTTP结果/challenge事实已经决定进入browser fallback、且fallback真正将要启动时，caller才检查proof-on；若`dns_peer_proof_enabled=true`，在调用任何会import/启动browser的路径以及`_run_playwright_worker_process(...).process.start()`之前返回browser-owned typed failure，稳定reason唯一冻结为`browser_peer_proof_unavailable`。不得在config构造时拒绝该组合，不启动Playwright进程，不复用private-network reason，也不得把browser当proof bypass。
- 该typed failure不回写或改写既有HTTP结果、HTTP失败或challenge detection事实。面向LLM的message只表达“当前浏览器访问无法验证目标连接”，不得暴露Playwright、socket、Host/runtime或内部治理术语。

### 4.4 Diagnostics 与 storage-state exact contract

保留：

- `web-diagnostics-v2`、revision `2`、typed header/error allowlist、敏感值 redaction、challenge detection/evidence、`DiagnosticResourceBudget`。
- 显式 `--storage-state-in <file>` 和 `--storage-state-dir <dir>` 作为只读输入；显式file按普通输入存在/可读/JSON-shape诊断处理。packaged默认目录或显式directory不存在/无匹配host file时表示“本次无storage input”并继续，不能因默认目录尚未创建而让普通fetch失败。`--storage-state-dir`只投影到既有`playwright_storage_state_dir` config，由production resolver选择`<host>.json`/`www.<host>.json`只读候选；diagnostic utility不再调用`_storage_state_owner_final_name`派生`dayu-web-state-<host>.json`。R02不借删除lifecycle新增credential或fixture path authority；现有普通output/storage-input containment与symlink防御原样保留、回归。
- production pre-range host candidate read-only lookup、storage cookies 注入、Playwright context read input；不新增 refresh/retention/publish。这里保留的是显式目录下的现有input selection，不是credential final owner命名contract。
- ordinary JSON/JSONL/markdown diagnostic/smoke artifact继续使用当前writer语义；R02不新增任何普通artifact writer contract。

删除：

- CLI `--storage-state-out`、`--storage-state-ttl-seconds` 及 batch command propagation。
- diagnostic CLI `--allow-private-network-url` 及`CliOptions.allow_private_network_url`：accepted packaged default已经allow，保留它会成为无效兼容开关；显式deny由Web config owner-level tests/smoke overlay验证，不在diagnostic CLI建立第二个policy parser。
- `_StorageStateLifecycle`、host-derived owner final filename、0700/0600 credential authority、temp/final credential publish、TTL、orphan/expired scan、startup reconciliation、cancel/failure cleanup/publish state machine。
- diagnostic artifact 的 `output_enabled`、`output_label`、`ttl_seconds`、`published` 或同义 lifecycle fields。
- lifecycle test doubles、permissions/replace/cleanup/reconcile tests和 README 承诺。

credential lifecycle自带的publish/permission/reconcile状态机直接删除，不迁移、不复用为普通artifact helper。Issue #178只拥有未来credential lifecycle；现有普通artifact行为不是R02 residual obligation，也不得转交Issue #178。

## 5. 删除、保留与明确非目标

### 5.1 必须删除

- private/custom/browser coupling 和 browser 的 `allows_private_network` 前置禁用。
- HTTP 的 unconditional pinned transport、unconditional proxy ban、unconditional `trust_env=false`。
- 七字段 `WebResourceBudget` god dataclass、flat complete-object config和旧默认数值。
- diagnostic credential TTL/owner filename/0700/0600/orphan/expired/publish/reconcile lifecycle 全链与 artifact/test/README contract。
- `storage_state_out`/TTL 的 CLI/batch command projection。
- 任何为保持旧 import、旧 config、旧 test 所加的 alias、property、wrapper、fallback、dual parser 或 test shim。

### 5.2 必须保留并有 owner-level 回归

- 初始 URL 与每一 redirect hop 的 scheme/host/port/address 重检。
- dangerous、unspecified、multicast、显式 private deny、显式 custom-port deny。
- mixed DNS fail closed。
- peer proof 开启时的 numeric target/actual peer verification与 mismatch fail closed。
- proxy 禁用时不读 environment；proxy+proof 不兼容时 typed fail closed。
- HTTP wire/decoded、browser warmup/DOM/text、diagnostic error/event budgets。
- challenge detection、HTTP→browser fallback 的 challenge reason、diagnostics v2/revision 2。
- `browser_enabled` 与 private permission 的双向独立性。
- 显式 storage-state path/dir read input。
- header/cookie/URL/proxy credential redaction、diagnostic containment，以及现有普通artifact writer行为。
- 现有storage-input/output directory containment与symlink防御。

### 5.3 明确非目标

- 统一 tool authorization framework、policy DSL、角色/租户权限、capability token 或 sandbox。
- Issue #178 的 credential refresh、retention、并发 publish、owner naming、cleanup。
- 任何其它 deferred Issue、R03 accepted-call/evidence projection或后续 sub-WU。
- 新 proxy credential schema、PAC、proxy health manager、browser numeric peer-proof 发明。
- 修改 challenge detector、Host/Engine/Service/UI/Fins、durable schema或 LLM prompt。
- 把 safety ceilings 宣称为业务 complete/财报完整性或写入 LLM-facing 文本。
- 为旧 config/schema/import/tests 保留兼容行为。

## 6. Controller-final closed allowlist、预期 diff 与已关闭 drift

### 6.1 Controller-final production/config/scripts 闭集

| 文件 | exact disposition |
|---|---|
| `dayu/config/tool_discovery.json` | S1 修改 packaged defaults/groups |
| `dayu/tools/web/provider.py` | S1 修改 raw config parser与 typed assembly |
| `dayu/tools/web/web_resource_budget.py` | S1 以三 owner budgets/aggregate 替换七字段 class |
| `dayu/tools/web/web_egress_policy.py` | S1 拆 private/custom policy；S2 retained-security fix 仅在 test 证明必要时 |
| `dayu/tools/web/web_http_session.py` | S1只定义最小frozen transport policy并由config snapshot保存，sender保持secure pinned/no-proxy；S2原子增加必填named policy参数并实施proxy/proof分支 |
| `dayu/tools/web/web_tools.py` | S1 接收 typed snapshot；S2 按 owner 分发 HTTP/browser/diagnostic budgets/capabilities |
| `dayu/tools/web/web_playwright_backend.py` | S2 删除 private/browser coupling，改接 browser budget与 transport constraints |
| `dayu/tools/web/web_fetch_orchestrator.py` | S2 传递 transport/http budget并保留每跳重检 |
| `dayu/tools/web/web_recovery.py` | 闭集内 inspect-only，预期无 diff；只有真实 challenge/capability reason 传播缺口才允许 S2 修改 |
| `dayu/tools/web/web_diagnostics.py` | S1/S3 改接 diagnostic budget；schema/revision/redaction预期无语义 diff |
| `dayu/tools/web/web_tool_projection_text.py` | inspect-only，预期无 diff；R02 不改 LLM-facing schema |
| `dayu/tools/web/web_search_projection.py` | inspect-only，预期无 diff；R02 不改 search business projection |
| `dayu/tools/web/web_search_providers.py` | plan-entry adjudication精确新增，plan-review adjudication再以`R02-PF-07`冻结同文件owner修复：S1把budget依赖收窄到`HttpResourceBudget`并让result visibility消费private/custom-port typed policy；S2只复用Web HTTP transport owner的proxy/peer-proof/egress决定与脱敏warning；provider选择、业务结果、credential读取、query/domain语义和LLM-facing projection不得改变 |
| `utils/diagnose_web_access.py` | S3 删除 lifecycle、消费新 config；现有ordinary artifact writer保持不变 |
| `utils/smoke_web_ci.py` | S3 更新 deterministic/real smoke与模块私有版本化fixture case；现有ordinary artifact writer保持不变 |
| `utils/diag_web_batch.sh` | S3 删除已删 CLI 参数传播；无命中则预期无 diff |

闭集内不代表必须产生 diff。`web_recovery.py`、两个 projection 文件、`diag_web_batch.sh` 若没有 owner-side必要性必须保持无 diff。

### 6.2 Controller-final tests/docs 闭集

- tests：`tests/tools/web/test_web_tools_provider.py`、`tests/tools/web/test_diagnose_web_access.py`、`tests/tools/web/test_smoke_web_ci.py`；plan-entry adjudication精确新增`tests/runtime/test_config_loader.py`，仅允许更新packaged Web五bool与三budget groups的精确断言，不得改其它ConfigLoader行为。
- README：`dayu/config/README.md`、`tests/README.md`；根 `README.md` 仅在最终用户诊断 CLI 工作流变化时允许。
- inspect/run-only：其它 tests、README、design、control 不得产生 diff。

最终闭集由umbrella baseline与`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`共同确定；除上述一个production file与一个test file外没有其它扩展。

### 6.3 每 slice 在当前授权内的预期 changed files

- S1：`tool_discovery.json`、`provider.py`、`web_resource_budget.py`、`web_egress_policy.py`、`web_http_session.py`、`web_tools.py`、`web_diagnostics.py`、精确授权的`web_search_providers.py`、`test_web_tools_provider.py`、精确授权的`tests/runtime/test_config_loader.py`、`dayu/config/README.md`、`tests/README.md`。
- S2：`web_http_session.py`、`web_playwright_backend.py`、`web_tools.py`、`web_fetch_orchestrator.py`、精确授权的`web_search_providers.py`、必要的 `web_egress_policy.py`/`web_recovery.py`、`test_web_tools_provider.py`。
- S3：`utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、必要的 `utils/diag_web_batch.sh`、三份允许 Web tests、`tests/README.md`；若 `dayu/config/README.md` 的诊断段受影响则同 slice closure。根 README 经 §12 决策，当前预期无 diff。

### 6.4 Material allowlist drift controller adjudication（accepted/closed）

| finding | 直接调用链证据 | accepted decision | exact authorization boundary |
|---|---|---|---|
| `R02-B01=accepted/closed` | `web_search_providers.py`直接import/消费`WebResourceBudget`；模块级`requests.get/post`会使search与fetch产生不同proxy/peer-proof事实 | 精确增加该production file | S1仅迁移`HttpResourceBudget`；S2仅复用同一Web HTTP transport policy。不得改变provider选择、业务结果、credential读取、query/domain语义、LLM-facing projection或复制DNS/proxy/peer rule |
| `R02-B02=accepted/closed` | `test_packaged_config_loads_expected_provider_metadata`直接断言旧private默认false | 精确增加该test file | 仅更新packaged Web五个独立bool与三组resource budget projection精确断言；不得改其它ConfigLoader行为、兼容旧schema或skip |

`R02-B01/B02`的唯一裁决artifact是`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`。两项drift均已关闭且无其它allowlist扩展；任何超出上表的新增文件或语义仍触发§15.3 stop，不得采用alias、旧类残留、test exclusion或baseline waiver。

其后`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`以`R02-PF-07`要求同一已授权production file在S1修复search result visibility；这不新增文件，也不授权provider业务语义变化。最终S1边界以§6.1、§8.2和该后续controller adjudication为准。

## 7. Umbrella R02 mandatory baseline 逐项映射

| umbrella baseline | mapping | 本计划 exact 项 |
|---|---|---|
| R02 production allowlist | 基于直接代码证据细化，已获精确adjudication | §6.1保留umbrella闭集，并只增加`web_search_providers.py`的S1/S2窄边界；`R02-B01`已关闭 |
| tests/docs allowlist | 基于直接代码证据细化，已获精确adjudication | 三份Web tests/两README保留，并只增加`tests/runtime/test_config_loader.py`的packaged snapshot断言；`R02-B02`已关闭 |
| 三 slices `config -> executors -> diagnostics cleanup` | 保留 | §8、§9、§10 严格串行；S1 accepted commit前不得进入 S2，S2 accepted commit前不得进入 S3 |
| private/custom 默认 allow | 保留 | packaged + typed defaults true；显式 deny owner tests |
| DNS peer proof 默认 off | 保留 | standard transport默认；proof-on numeric pin/mismatch tests |
| environment proxy 默认 allow | 保留 | trust_env path +非敏感 warning；显式 disable与proof conflict tests |
| browser/private 解耦 | 保留并细化 | `browser_enabled` 直接 bool；public JS/private=false成功，private URL仍拒绝 |
| resource owner split/local override | 保留 | 三小 dataclass + aggregate snapshot；field/group local default；backend零默认 |
| 128/256 MiB、1 MiB、16/8 Mi chars、8 Ki chars/512 events | controller已冻结 | S1直接使用全部冻结值；S3/aggregate只记录observed metrics，只有直接不足证据才stop，不得backend second default |
| redirect、dangerous/mixed DNS、deny、proof-on、budgets | 保留 | §9 owner/security matrix + §13 smoke/scan |
| challenge + diagnostics v2 | 保留 | detector无 diff；v2/revision2 exact tests |
| storage path input | 保留并细化 | 保留 explicit file/dir read input；不把 pre-range host lookup误判为 lifecycle |
| 删除 credential lifecycle | 保留 | S3 删除符号、CLI、artifact、tests、README全链；转交 Issue #178 |
| ordinary diagnostic writers | 按controller finding adjudication缩窄 | HEAD直接写语义保持不变；S3只删除credential lifecycle publish/permission/reconcile状态机，不新增普通writer contract |
| S1 `-k` command | 保留并加强 | 先跑 umbrella filter，再跑完整 owner file与新增 config-loader node；coverage逐 changed production file |
| S2 `-k` command | 保留并加强 | 先跑 umbrella filter，再跑完整 provider file与 deterministic proxy/peer/browser nodes |
| S3 `-k` command | 保留并加强 | 先跑 umbrella filter，再跑三份完整允许 test；v2/lifecycle deletion exact assertions |
| coverage include baseline | 基于直接代码证据细化 | include 只是上界；§14 必须从 JSON逐个 changed production file `>=80%`；utils按 AGENTS 免覆盖但必须行为测试 |
| pyright/diff/allowed/source/README | 保留 | 每 slice和aggregate都执行；任一新增/扩散 error或越界 diff stop |
| 本地 + real Playwright/diagnostic smoke | 保留并细化 | §13 同时要求 deterministic local、真实 Playwright、真实 diagnostic v2和财报 budget probe；external只补充不替代 |

没有 umbrella 项被静默遗漏或降级。

## 8. R02-S1 — Config owner 与 typed policy split

### 8.1 Entry 与原子目标

`R02-B01/B02`已由plan-entry adjudication关闭。S1 entry仍必须同时满足：本文完成双路完整plan review、controller finding adjudication、accepted finding fix、双路完整re-review并有accepted-plan commit。controller冻结的全部budget values直接进入S1，不再设置implementation前的数值充分性裁决。S1在一个reviewable diff中建立packaged config、typed defaults、parser、immutable tool snapshot与三个budget owner；不得留下旧/new双schema或一半consumer仍接七字段类型。

### 8.2 逐文件、符号与 call chain

1. `dayu/config/tool_discovery.json`
   - 写入 §4.1 五个 bool和三组显式 initial ceilings；保留现有 channel/storage dir。
2. `web_resource_budget.py`
   - 删除 `WebResourceBudget` 与 complete flat parser；新增 §4.2 四个 frozen dataclasses、typed default constants和精确 nested parser。
   - 三个child constructor/parser分别只验证本owner字段；aggregate是无default、无`__post_init__`、无validator的纯frozen组合。中文docstring完整；不得收 `Mapping[str, object]`/`Any` 或loose cast。
3. `provider.py`
   - `_parse_config`只读取ConfigLoader交付的final provider record，解析五bool、channel/storage dir与nested budgets；final record中缺失field/group补typed default，存在值exact validate，unknown/invalid precise fail fast。
   - `_resource_budget_default` 替换为 owner-group local parser；不得修改ConfigLoader record-replace contract或在ConfigLoader做deep merge；tool definition只接typed `WebToolsConfig`。
4. `web_egress_policy.py`
   - `WebEgressPolicy` 增加独立 `allow_custom_port`；保留 address resolution/result type与所有 unconditional deny。
5. `web_http_session.py`
   - 新增最小 frozen `WebHttpTransportPolicy(dns_peer_proof_enabled, allow_environment_proxy)`；不在此定义部署默认数值。S1不修改`_send_authorized_request`签名或行为，继续secure pinned/no-proxy。
6. `web_tools.py`
   - `WebToolsConfig`保存由parser构造的frozen `WebHttpTransportPolicy`、private/custom/browser typed facts、`WebResourceBudgets`纯组合及现有browser/storage设置；不存raw JSON。S1只保存transport policy，不把它thread到sender。
   - `_search_web_business`只传`http_resource_budget`，并把同一typed `WebEgressPolicy(private, custom-port)`直接交给search result visibility；移除由raw `allow_private_network_url`单独代签visibility的接口。fetch path按consumer分发各自budget。browser同时产生rendered input与diagnostic error，因此显式接收browser/diagnostic两个小类型，不接aggregate。
7. `web_diagnostics.py`
   - diagnostics projection signatures只接 `DiagnosticResourceBudget`或两个显式 owner fields；schema/revision/redaction不改。
8. `web_search_providers.py`（plan-entry adjudication已精确授权）
   - S1 import/signatures/docstrings由 `WebResourceBudget` 改为 `HttpResourceBudget`；response materialization逻辑不变。
   - `search_public_web`/`_filter_visible_results`消费caller已构造的typed `WebEgressPolicy`，由其`is_url_allowed`同源决定private/custom-port visibility；不得重读raw config或保留只接private bool的旧checker contract。
   - S2再把三个模块级`requests.get/post`调用迁到`web_http_session.py`的同一typed attempt sender，使proxy-disable/proof/sanitized-warning对search与fetch同源；不得在S1提前混入transport行为。
9. tests/README
   - 将 complete-object tests改为 group/field local override、unknown/invalid、packaged/typed conformance；更新 config/tests README实际 contract。

目标调用链：

```text
ConfigLoader
  -> packaged tool_discovery.json
  -> provider._parse_config (only raw config owner)
  -> WebToolsConfig immutable snapshot
       -> WebEgressPolicy(private, custom-port)
       -> WebHttpTransportPolicy(peer-proof, environment-proxy)
       -> browser_enabled
       -> HttpResourceBudget / BrowserResourceBudget / DiagnosticResourceBudget
  -> tool definitions/callables
```

### 8.3 S1 owner tests

- packaged JSON逐字段等于 typed defaults；old数值/flat字段零残留。
- 五 bool每个 default、true/false override、bool-as-int/string/null拒绝，且final record中改变一个不改变其余四个typed defaults。
- 保持并运行ConfigLoader既有record-replace test且不修改其contract；provider owner test把final partial record直接交给`_parse_config`，证明整体budget缺失、单group缺失、单field缺失只补对应typed default，已有sibling不变；unknown group/field、wrong object type、bool、0、negative拒绝并指向精确path。
- HTTP search/fetch只收到 `HttpResourceBudget`；browser只收到 `BrowserResourceBudget`；diagnostics只收到 `DiagnosticResourceBudget`。
- `WebResourceBudgets`无default、无`__post_init__`/validator、无flattened compatibility properties；三个child各自拒绝非bool正整数；全仓旧class/import零残留。
- search result visibility对private/custom-port allow/deny的决定与fetch使用同一typed policy；无raw config重读。
- S1 sender仍是当前pinned/no-proxy行为，`_send_authorized_request`尚无transport policy参数；防止在S1留下半迁移transport。
- config-loader packaged snapshot更新为 accepted default，而不是跳过旧断言。

### 8.4 S1 gate commands

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py -k 'config or resource_budget or egress_policy or provider' -q
pytest tests/tools/web/test_web_tools_provider.py tests/runtime/test_config_loader.py -q

coverage run --data-file=workspace/tmp/.coverage-r02-s1 -m pytest \
  tests/tools/web/test_web_tools_provider.py \
  tests/runtime/test_config_loader.py -q
coverage json --data-file=workspace/tmp/.coverage-r02-s1 \
  -o workspace/tmp/coverage-r02-s1.json

python -m pyright
git diff --check
rg -n 'WebResourceBudget|max_wire_body_bytes|max_decoded_body_bytes|max_browser_warmup_body_bytes|max_browser_dom_chars|max_browser_text_chars|max_diagnostic_error_chars|max_diagnostic_events' dayu tests README.md
rg -n '26214400|52428800|65536|5000000|1000000|1024|"events"[^0-9]*80' dayu/config/tool_discovery.json dayu/tools/web tests/tools/web dayu/config/README.md tests/README.md
```

第一条 semantic scan 预期对旧 class/flat field零命中；数值 scan逐条分类，`1000000` 若命中无关 timeout/fixture必须在 artifact记录，不能用泛化数值 grep冒充语义证明。逐文件 coverage命令见 §14。

### 8.5 S1 accepted gate

S1 implementation artifact、两路完整 code review、controller adjudication、accepted finding fix、两路完整 rereview均闭合后，由 controller 创建只含 S1授权文件的 accepted local commit。没有 accepted commit不得开始 S2。

## 9. R02-S2 — HTTP/proxy/peer 与 browser 独立执行

### 9.1 原子目标

基于 S1 typed snapshot，在一次 slice 内完成 HTTP transport选择、proxy warning/proof冲突、browser capability解耦与 retained-security回归。任何时刻都不得形成“允许 proxy但仍使用 pinned peer自称已 proof”或“browser启用即绕过 egress”的可接受终态。

### 9.2 HTTP exact flow

```text
web tool/search provider
  -> authorize initial URL (scheme/host/port/DNS/mixed-address)
  -> choose attempt transport
       proof off + proxy allowed  -> standard Session, trust_env=true
       proof off + proxy denied   -> standard Session, trust_env=false
       proof on + no proxy        -> numeric pinned adapter + peer compare
       proof on + active proxy    -> typed proxy_peer_proof_incompatible
  -> materialize body under HttpResourceBudget
  -> redirect? authorize new hop and repeat transport decision
  -> HTTP result/challenge decision
```

- proxy active detection必须来自 `requests` 对当前 URL/environment的实际 selection，不根据环境变量是否存在就误报。
- 每个attempt只prepare一次request。proxy允许时，sender以空的per-call proxies输入调用`Session.merge_environment_settings(prepared.url, proxies, stream, verify, cert)`，用`requests.utils.select_proxy(prepared.url, settings["proxies"])`选择当前URL的proxy，并把同一个settings原样传给同一次`Session.send(prepared, timeout=..., allow_redirects=False, **settings)`；proxy禁用时`trust_env=false`、session/per-call proxies均为空，merge后的同一次send settings也必须是`proxies={}`。不得再次读取环境、从proxy URI解析credential或查看urllib3私有状态。
- warning只消费selected-proxy存在性，说明“本attempt使用环境proxy，numeric peer proof未启用”；结构只含非敏感bool与稳定reason，不得包含完整URL、query、proxy URI/userinfo、headers、cookies、storage path。
- redirect到 private/custom-denied/mixed DNS在发送下一跳前拒绝。
- proof-on路径复用当前 approved-address/peer compare owner，不重新发明 resolver。
- Tavily/Serper/DuckDuckGo固定provider endpoint虽然`allow_redirects=false`，仍在首次发送前执行同一DNS/address/custom-port authorization，并在proof-on时执行同一peer防御；不得因endpoint固定而known-safe bypass。
- S2原子修改`_send_authorized_request`和plain search sender：二者都新增无default的必填named `transport_policy`参数，并同步修改全部fetch/search callers；不存在旧caller兼容分支。

### 9.3 Browser exact flow

```text
HTTP terminal/challenge
  -> challenge detection retained
  -> browser_enabled?
       false -> typed browser_disabled/no-attempt
       true  -> browser fallback即将启动?
                  proof-on -> typed browser_peer_proof_unavailable/no process
                  proof-off -> browser backend
                  -> every route/navigation applies WebEgressPolicy
                  -> BrowserResourceBudget
                  -> challenge evidence + converted result
```

- 删除 `allows_private_network == false -> browser_egress_policy_unavailable` 前置 return。
- public JS + private=false必须运行；private request + private=false仍拒绝。
- private=true + browser=false不得运行；二者无单向或反向授权关系。
- proof-on/browser-enabled config本身合法，HTTP proof path先独立执行。只有`_try_playwright_fallback`真实被调用且即将进入会import/启动browser的路径时，才以独立typed reason `browser_peer_proof_unavailable` early fail；断言`_run_playwright_worker_process`与`process.start()`均未调用。不得复用`browser_egress_policy_unavailable`。
- browser proof failure的LLM-facing message只说明当前浏览器访问无法验证目标连接；不得出现Playwright、socket、Host/runtime术语。HTTP成功/失败与challenge decision保持原事实，不被该browser outcome回写。
- browser worker在 environment proxy disabled时得到清理后的 proxy环境；enabled时沿用运行环境，但 warning仍由不含敏感值的 typed diagnostic产生。
- all challenge call sites不再硬编码 `browser_available=True`；它们从 `browser_enabled`和当前 proof compatibility推导是否可尝试，但 challenge detection本身不依赖 capability。

### 9.4 逐文件改动

- `web_http_session.py`：把当前 pinned-only adapter变为 proof-on strategy；standard path、trust_env、基于同一次`merge_environment_settings`/`send` settings的selected proxy、typed incompatibility与sanitized warning。`_send_authorized_request`及plain sender的`transport_policy`都是必填named参数且无default。
- `web_fetch_orchestrator.py`：每 redirect hop重复 authorization/transport选择并传 `HttpResourceBudget`与必填transport policy；保留 redirect cap/error。
- `web_search_providers.py`（plan-entry adjudication精确授权）：Tavily/Serper/DuckDuckGo固定endpoint不跟随redirect，但初始URL仍走同一egress与peer防御；实际I/O改调`web_http_session`的plain typed sender，传`HttpResourceBudget`、egress/transport policy和原headers/json/params。API key不得进入warning/diagnostic；search module不自行解释环境变量、DNS或peer，不新增known-safe endpoint bypass。
- `web_playwright_backend.py`：删 private/browser coupling，接 `browser_enabled`前由 caller gate；route policy与browser budget分离；rendered input只读`BrowserResourceBudget`，错误/事件投影只读`DiagnosticResourceBudget`。proof-on reason由fallback启动前的browser owner产生，backend不得启动进程后再补偿。
- `web_tools.py`：在 fetch/challenge/recovery path分发 capability、egress、transport和三个 budgets；challenge availability不再硬编码。
- `web_egress_policy.py`：仅修直接测试暴露的 custom/private/standard-port decision，不能移动 transport authority。
- `web_recovery.py`：只有 challenge/recovery reason当前丢失 capability事实时修改；否则无 diff。

### 9.5 S2 owner/security tests

| case | expected |
|---|---|
| default loopback + custom port | HTTP成功 |
| private=false | loopback/private拒绝；public address允许 |
| custom-port=false | public/private合法host的非标准port拒绝；standard允许 |
| dangerous/unspecified/multicast | 无论两个allow均拒绝 |
| mixed public+private DNS, private=false | 整组拒绝 |
| redirect public -> denied private/custom/mixed | 下一跳发送前拒绝 |
| proxy allow + proof off | recorder观察到请求；只出现sanitized warning |
| proxy deny | recorder零请求，direct path执行 |
| proof on + no proxy | numeric target使用且actual peer匹配成功 |
| proof on + peer mismatch | typed fail closed |
| proof on + active proxy | typed incompatibility，不静默降级 |
| search provider + proxy allow/deny/proof | 与fetch使用同一transport decision；固定endpoint初始DNS/egress/peer检查保留，结果语义不变，credential不进warning |
| browser=true/private=false + public JS | real/fake-browser owner test成功 |
| browser=true/private=false + private subrequest | route拒绝 |
| browser=false/private=true | no Playwright attempt |
| browser=true + proof=true | HTTP proof path不受影响；仅实际fallback启动前返回`browser_peer_proof_unavailable`，Playwright import/process start零调用，LLM-facing message无内部术语 |
| DuckDuckGo deterministic challenge response | plain sender返回固定challenge HTML；同一个`detect_bot_challenge` recorder被调用、`allow_redirects=false`、仍产生原`challenge_response`业务失败语义；`web_challenge_detection.py`零diff |
| challenge | detection/evidence保持，fallback仅按真实 capability执行，browser failure不改写HTTP/challenge事实 |
| resource budgets | HTTP/browser各自在 exact/+1 boundary fail；互不读取 sibling budget |

### 9.6 S2 gate commands

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py -k 'private or custom_port or proxy or peer or redirect or browser or challenge' -q
pytest tests/tools/web/test_web_tools_provider.py -q

coverage run --data-file=workspace/tmp/.coverage-r02-s2 -m pytest \
  tests/tools/web/test_web_tools_provider.py -q
coverage json --data-file=workspace/tmp/.coverage-r02-s2 \
  -o workspace/tmp/coverage-r02-s2.json

python -m pyright
git diff --check
rg -n 'allow_private_network_url|allow_custom_port_url|dns_peer_proof_enabled|allow_environment_proxy|browser_enabled' dayu/config/tool_discovery.json dayu/tools/web tests/tools/web dayu/config/README.md tests/README.md
rg -n 'browser_egress_policy_unavailable|browser_available=True|trust_env\s*=\s*False|proxies\s*=\s*\{\}' dayu/tools/web tests/tools/web
git diff --exit-code -- dayu/tools/web/web_challenge_detection.py
```

第一条 scan逐字段证明一个 parser owner和对应 consumer；不得简单要求全局单一命中。第二条命中必须逐条归属：显式 proxy-deny分支可保留 `trust_env=false`，unconditional路径与 hardcoded browser availability必须零残留。challenge detector diff命令必须为0；若必须修改该文件，立即stop回controller。

### 9.7 S2 accepted gate

按 S1同样的 implementation/review/fix/rereview/controller accepted local commit闭环。retained DNS/redirect/peer/budget/browser-route任一失败均 release-blocking，不能作为 residual进入 S3。

## 10. R02-S3 — 删除 storage-state lifecycle，保留 diagnostics v2

### 10.1 原子目标

删除 diagnostic utility 对 credential生成、命名、TTL、权限、发布、回收的全部 authority；同时保留显式 read input、diagnostics v2/challenge evidence和现有普通artifact writer行为。不能只隐藏CLI字段而留下后台reconcile，也不能误删pre-range read-only input；不得把credential publish状态机迁移成普通writer。

### 10.2 目标调用链

```text
diagnose_web_access CLI
  -> explicit --storage-state-in file / --storage-state-dir directory (optional, read-only)
  -> typed Web config/policies/budgets
  -> HTTP and optional real Playwright attempt
  -> diagnostics-v2 revision 2 projection
  -> existing ordinary JSON/JSONL/markdown writer

smoke_web_ci
  -> module-private versioned filing fixture case + deterministic local cases
  -> real browser/diagnostic calls + existing run artifact writers
```

不存在 output credential path、owner filename、TTL、publish、reconcile或 credential cleanup状态。

### 10.3 逐文件删除/保留

1. `utils/diagnose_web_access.py`
   - `CliOptions`、arg parser、command render删除 storage-state out/TTL；保留 in/dir。
   - 删除`--allow-private-network-url`与对应option/config overlay；诊断默认直接消费packaged private=true，显式deny测试通过smoke的typed provider overlay进入唯一parser。
   - 删除 `_StorageStateLifecycle`及 owner name/permission/reconcile/prepare/publish/cancel cleanup helpers。
   - raw Playwright profile只消费显式`--storage-state-in` file；`--storage-state-dir`只传给tool provider的既有production resolver，不在diagnostic中派生host filename。profile不再投影 lifecycle fields。
   - `_write_json`、`_write_jsonl`和summary writer保持当前普通写语义；不得新增普通writer helper，也不得复用待删credential lifecycle。
2. `utils/smoke_web_ci.py`
   - packaged overlay不再需要 `allow_private_network_url=true` 才能访问默认loopback/custom-port；新增显式deny cases。
   - 以模块级私有常量和`LocalFixtureCase`直接接入版本化SEC AAPL HTML；不新增fixture CLI或任何用户输入协议。固定常量缺失或不是regular file时test/smoke直接失败，不建立通用resolve/containment/path authority。
   - `_write_json`与summary/blocker等普通run artifact writer保持当前语义，不新增普通artifact行为。
   - 不生成或刷新credential state。
3. `utils/diag_web_batch.sh`
   - 删除 out/TTL forwarding/usage；若当前无命中则保持无 diff。
4. `web_diagnostics.py`
   - 保持 v2/revision2、redaction、challenge fields；只确认 `DiagnosticResourceBudget`消费，不引入storage lifecycle字段。
5. tests
   - 删除 owner filename、permissions、TTL、orphan/expired、publish/reconcile、replace-failure credential tests。
   - 新增explicit input可读/缺失/非法、artifact无lifecycle字段，以及模块私有版本化fixture case存在/regular-file与真实执行测试；普通artifact writer不新增测试要求。
   - v2/revision2/challenge/redaction/budget tests原样或迁移到新的 diagnostic type。

### 10.4 S3 gate commands

```bash
source .venv/bin/activate
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -k 'diagnostic or storage_state or challenge' -q
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -q

coverage run --data-file=workspace/tmp/.coverage-r02-s3 -m pytest \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/tools/web/test_web_tools_provider.py -q
coverage json --data-file=workspace/tmp/.coverage-r02-s3 \
  -o workspace/tmp/coverage-r02-s3.json

python -m pyright
git diff --check
rg -n 'storage_state_out|storage-state-out|storage_state_ttl|storage-state-ttl|_StorageStateLifecycle|owner_final_name|orphan|expired|reconcile|output_enabled|output_label|published' utils/diagnose_web_access.py utils/smoke_web_ci.py utils/diag_web_batch.sh tests/tools/web dayu/config/README.md tests/README.md README.md
rg -n -- '--allow-private-network-url|options\.allow_private_network_url' utils/diagnose_web_access.py utils/smoke_web_ci.py utils/diag_web_batch.sh tests/tools/web tests/README.md README.md
rg -n '0700|0600|chmod|fchmod' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py
rg -n 'web-diagnostics-v2|diagnostic_revision|revision' dayu/tools/web/web_diagnostics.py utils/diagnose_web_access.py tests/tools/web
```

前三条删除scan预期零语义残留；若 `expired` 等命中无关 HTTP header/test文字，必须逐条归属。diagnostics scan必须证明 schema version与revision 2仍由单一 producer定义并被consumer断言。

### 10.5 S3 accepted gate

除 slice code review闭环外，必须先通过 §13全部 deterministic/real smoke、§14 aggregate gates和§15 completion字段。controller accepted R02 commit产生后才能 handoff R03；AgentCodex不创建该 commit、不更新 control、不启动 R03。

## 11. Frozen budget values 与 metrics evidence

### 11.1 Plan-time 已执行的直接证据

| evidence | execution/observed maximum | 结论 |
|---|---|---|
| `utils/smoke_web_ci.py --external-limit 0 --include-playwright`，真实本地HTTP +真实Playwright | 7 local cases全过；HTML 238 B、PDF 652 B、browser response 367 B、rendered HTML 510 chars、text 118 chars、2 network events | 记录当前执行链的plan-time metrics；不把ceiling描述为业务完整性承诺 |
| 版本化 SEC fixture `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm` 经本地HTTP和真实Playwright | source 1,503,780 B；rendered HTML 1,515,212 chars；text 209,272 chars；6 network events。旧 5M DOM默认的另一诊断路径曾触发 `browser_dom_too_large`；注入冻结值后成功 | 记录该版本化fixture在16/8 Mi chars内成功；不外推到所有站点 |
| 当前 workspace filing-derived Docling JSON 经本地HTTP | 22,243,642 wire bytes；冻结HTTP values下注入诊断成功 | 仅为plan-time观测，不作为版本化回归输入或新增fixture authority |

128/256 MiB、1 MiB warmup、16/8 Mi chars、8 Ki chars/512 events是用户/controller已冻结且可配置的safety ceilings；S1直接按§4.1字面值实施，不恢复64 KiB，不要求在S1前证明对所有财报或站点普遍充分，也不在R02重新裁决数值。

### 11.2 S3/aggregate metrics 记录与唯一 stop 规则

S3以`smoke_web_ci.py`模块级私有版本化fixture constant/case把现有SEC AAPL HTML接入ephemeral-port server；不新增fixture CLI/path参数、通用containment/parser或前置micro-slice。S3与aggregate只记录以下observed metrics：

1. 版本化AAPL fixture的wire/decoded bytes、browser warmup bytes、DOM/text chars、diagnostic error chars与events count；
2. local compressed/decoded受控case的wire/decoded bytes；
3. challenge、proxy recorder与peer-proof受控case的预算观测是否仍来自同一typed snapshot。

只有真实fixture或受控case直接命中/超过对应冻结ceiling、或直接产生由该ceiling导致的业务失败，才立即stop回controller；缺少万能充分性证明或live-site未来可能变化都不阻塞S1/S2/S3。R02内所有数值保持§4.1冻结值，metrics不得触发backend、CLI、fixture或test内第二默认/局部放大。

## 12. README 决策

- `dayu/config/README.md`：S1 必须更新 Web config字段、五 bool默认、三 owner groups/local override、initial values、proxy+proof typed incompatibility、browser/private独立；先读取并遵守其 Agent更新约束。不得承诺 Issue #178 lifecycle。
- `tests/README.md`：S1/S3更新 owner-level config、transport/browser matrix、diagnostics v2、lifecycle deletion、deterministic/real smoke意图；先读取其约束。
- 根 `README.md`：当前不描述 `utils/diagnose_web_access.py` 的developer CLI参数，R02不改变安装/初始化/最终用户Web入口，因此预期无 diff。若 implementation scan发现根README实际列出被删out/TTL workflow，S3才可按umbrella条件更新；否则记录“无需更新+零命中”。
- `dayu/README.md`、Host/Engine/Fins/UI README：层级、装配和这些模块contract未变，且不在R02文档allowlist，必须无 diff。

## 13. Deterministic local、真实 Playwright 与 diagnostics smoke

### 13.1 Deterministic local hard gate

`utils/smoke_web_ci.py` 必须提供一个不依赖外网的固定run label/output dir矩阵，至少覆盖：

- loopback + 非标准端口在packaged default下HTTP/fetch成功，不传旧allow-private flag；
-显式 private deny、custom-port deny分别失败；dangerous/unspecified/multicast、mixed DNS与redirect recheck保持；
- local proxy recorder：proxy allow观察请求且warning无敏感值；proxy deny recorder零请求；proof on + proxy typed fail；
- controllable resolver/socket peer：proof on match成功、mismatch失败；proof off不宣称peer proof；
- exact/+1 HTTP wire/decoded、browser DOM/text、diagnostic error/event boundaries；
- explicit storage-state input只读；artifact无lifecycle fields；普通artifact writer行为不变；
- challenge confirmed/control两路，diagnostics v2/revision2保持。

执行命令只使用现有CLI协议，不新增fixture参数：

```bash
source .venv/bin/activate
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-local \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-local
```

退出码必须为0、local case零skip/零failure；真实Playwright缺依赖不是local hard gate的可接受skip，实施环境必须安装项目声明的browser依赖或停止。

### 13.2 真实 Playwright/diagnostic hard gate

1. `smoke_web_ci.py`通过模块级私有版本化fixture constant/`LocalFixtureCase`，以自身`_LocalFixtureServer((127.0.0.1, 0), ...)`提供SEC AAPL HTML，并用现有diagnostics子进程runner以packaged default执行HTTP+Playwright comparison；保存v2 artifact到`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/`。constant不存在或不是regular file时test/smoke直接失败；不得新增用户path输入、通用fixture path authority、fixed port、外部server或旧`--allow-private-network-url`。
2. 断言 HTTP与browser completed、schema=`web-diagnostics-v2`、revision=2、challenge evidence存在，并记录DOM/text/wire/decoded/warmup/error/events metrics与冻结config值；只有直接命中/超限或因此失败才stop。
3. 同一真实browser分别运行：`browser_enabled=false/private=true` 不启动；`browser_enabled=true/private=true` 启动。`browser_enabled=true/private=false` 对公网JS的独立性由owner-level可控public resolver test证明；可用外网时再跑真实public JS作为补充，但外网失败不替代本地确定性证据。
4. diagnostic artifact扫描不得含cookies、authorization、proxy credential、query secret、storage-state内容或完整credential path。

### 13.3 External smoke 边界

可选 external search/fetch只作为实时provider补充；DNS、网站challenge、proxy可用性变化不得替代local hard gate，也不得为了通过而放宽policy/budget。external failure必须归入环境证据，不能改写accepted semantics。

## 14. Coverage、pyright、source/propagation 与 aggregate gates

### 14.1 Changed production file逐文件 coverage

每 slice先生成 coverage JSON，再从 `files[<path>].summary.percent_covered` 逐一核对所有实际 changed production `.py` 文件 `>=80%`。禁止用总体 `--fail-under`、umbrella include上界或高覆盖文件掩盖低覆盖文件。

实现 artifact 必须对每个实际 changed production file执行等价命令：

```bash
coverage report --data-file=workspace/tmp/.coverage-r02-sN \
  --include='dayu/tools/web/<exact-file>.py' --fail-under=80
```

- S1候选：`provider.py`、`web_resource_budget.py`、`web_egress_policy.py`、`web_http_session.py`、`web_tools.py`、`web_diagnostics.py`、plan-entry adjudication精确授权的`web_search_providers.py`。
- S2候选：`web_http_session.py`、`web_playwright_backend.py`、`web_tools.py`、`web_fetch_orchestrator.py`、plan-entry adjudication精确授权的`web_search_providers.py`及实际有diff的`web_egress_policy.py`/`web_recovery.py`。
- S3若production `web_diagnostics.py`有diff则仍需逐文件>=80%；`utils/**`按AGENTS免coverage，但三份行为tests与真实smoke不可省略。
- JSON/config/README/tests不计production coverage；无diff候选不伪造coverage。

### 14.2 每 slice通用 gates

```bash
source .venv/bin/activate
python -m pyright
git diff --check
git diff --name-only <slice-base> --
```

- pyright必须0新增/扩散；触及的旧错误必须修复。只有与control中baseline registry六项同指纹且与changed owner/propagation无交集才可 inherited。
- allowed-file scan预期所有路径落入controller最终批准的R02闭集和固定artifact命名；任何其它路径立即stop。
- 每 slice记录 README decision；S3结束再跑aggregate decision。

### 14.3 Source/propagation scans

除各 slice scans外，R02 completion前运行：

```bash
rg -n 'WebResourceBudget|storage_state_out|storage-state-out|storage_state_ttl|storage-state-ttl|_StorageStateLifecycle|owner_final_name|reconcile' dayu utils tests README.md
rg -n 'allow_private_network_url|allow_custom_port_url|dns_peer_proof_enabled|allow_environment_proxy|browser_enabled' dayu/config/tool_discovery.json dayu/tools/web utils tests/tools/web tests/runtime/test_config_loader.py dayu/config/README.md tests/README.md
rg -n 'web-diagnostics-v2|WEB_DIAGNOSTIC_SCHEMA_REVISION|challenge' dayu/tools/web utils/diagnose_web_access.py utils/smoke_web_ci.py tests/tools/web
rg -n 'redirect|approved_addresses|peer|multicast|unspecified|contain|symlink' dayu/tools/web utils tests/tools/web
rg -n 'authorization framework|policy DSL|capability token|storage state refresh|storage state retention' dayu utils tests README.md docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md
```

- 第一条旧contract预期对production/test/README零残留；显式 storage input不在删除pattern内。
- 第二条逐字段建立“一个raw parser owner -> typed snapshot -> exact consumers”清单，不以零/单命中作为目标。
- 第三/四条逐条证明retained contracts仍有owner/tests。
- 最后一条只能命中本文非目标说明；production/tests/README零新增。不得进入R03 source、Host LLM projection或统一framework。

### 14.4 Aggregate validation

S3完成后，在code review前至少运行：

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
python -m pyright
git diff --check
```

再运行§13 smokes、逐文件coverage、allowlist/README/source scans。`tests/runtime/test_config_loader.py`已精确授权并是必跑target；不得删除、skip或扩写到其它ConfigLoader行为。

## 15. Artifact 命名、逐 slice review/commit gate 与 completion

### 15.1 固定 artifact stem

全 R02 固定 stem `wu-semantic-ownership-01-r02-web-owner-policy`：

```text
docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-{mimo,ds}.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-{mimo,ds}.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-rereview-controller-adjudication.md

docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-implementation-s{1,2,3}-codex.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s{1,2,3}-controller-validation.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s{1,2,3}-code-review-{mimo,ds}.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s{1,2,3}-code-review-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s{1,2,3}-code-review-fix-codex.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s{1,2,3}-code-rereview-{mimo,ds}.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s{1,2,3}-code-rereview-controller-adjudication.md

docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-{mimo,ds}.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-completion.md
```

花括号表示分别存在文件，不是literal filename。零accepted finding也必须有zero-change fix/adjudication记录；不得conversation-only pass。

### 15.2 每 slice 状态机

```text
previous accepted base
  -> implementation-sN artifact + exact validation
  -> MiMo/DS independent full-slice code review
  -> controller adjudication (every finding exactly one disposition)
  -> Codex fixes every accepted finding, regardless of severity
  -> MiMo/DS full final-slice rereview
  -> controller accepted-slice local commit
  -> next slice
```

- S1 base必须包含controller accepted plan commit；S2/S3 base分别是前一slice accepted commit。
- reviewer只能并发读同一immutable target，不并发改共享工作区。
- `needs-more-evidence`未裁决、任一accepted finding未修、任一retained security失败时不得commit/下一slice。
- commit、control更新、next-gate启动只归controller；AgentCodex不得自行执行。

### 15.3 Stop conditions

任一项出现立即停止回controller，不用fallback/compatibility继续：

- implementation diff超出plan-entry adjudication对`R02-B01/B02`的精确边界，或需要任何其它production/test/README allowlist扩展。
- owner、accepted contract、依赖或production/test allowlist发生新的material drift。
- 需要修改当前最终批准闭集外production/test/README。
- 需要设计Issue #178 lifecycle、统一authorization、proxy credential schema或进入R03。
- packaged/typed defaults无法同源，或backend出现第二默认。
- proxy+peer proof被静默降级、browser绕过egress、redirect/mixed DNS/deny/peer/budget/containment/symlink任一回归。
- diagnostics v2/revision2/challenge evidence被删改，或artifact泄漏敏感值。
- S3/aggregate真实fixture metrics直接证明冻结ceiling不足，但controller尚未裁决后续动作。
- pyright新增/扩散、changed production file coverage低于80%、新测试失败、allowed-file diff或`git diff --check`失败。
- accepted plan/code finding未闭合或两路rereview发现新material finding。

### 15.4 Completion artifact 必填项

`...-completion.md` 必须逐项填写，不得只写“all passed”：

1. umbrella/sub-WU/slug、plan/implementation base SHA、accepted plan SHA、S1/S2/S3 accepted SHA、最终 R02 accepted SHA。
2. 引用`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`，记录`R02-B01/B02=accepted/closed`、一个production/一个test精确新增、实际diff符合各自S1/S2边界，并证明无其它allowlist扩展。
3. exact changed files，按 production/config/scripts/tests/README/artifacts 分类；证明无R03/Issue178/其它diff。
4. owner contract：五 bool、三 budgets、parser/default同源、HTTP transport、browser capability、diagnostics v2。
5. 删除 contract：旧七字段type/config、unconditional proxy/pin、browser/private coupling、storage lifecycle符号/CLI/artifact/tests/README，附零残留scan。
6. 保留 contract：redirect、deny、dangerous/mixed DNS、proof-on、budgets、challenge、v2、explicit storage input、redaction、containment/symlink，附test/smoke证据。
7. frozen budget evidence：逐fixture记录observed wire/decoded/warmup/DOM/text/error/events与§4.1冻结值；证明数值未改、无backend second default，并在存在直接不足证据时记录stop。
8. 每 slice targeted/full/aggregate pytest命令、exit、passed/skipped/failed count和artifact路径。
9. 每个 changed production file的coverage百分比与coverage JSON；utils exemption及其行为test证据。
10. 全量pyright结果、baseline registry delta/六项同指纹证明、`git diff --check`、allowed-file和source/propagation scan结果。
11. deterministic local、proxy/peer、真实Playwright、真实diagnostic v2、财报fixture smoke命令/结果/metric/artifact。
12. README逐文件 `updated | no-update-with-evidence` 决定。
13. plan review/fix/rereview、每slice code review/fix/rereview、aggregate deepreview的所有finding ID和最终disposition；accepted全闭合。
14. residual risks的owner/destination/non-blocking依据；不得出现无owner residual。
15. handoff明确写“等待controller；不得自行commit/control update/进入R03”。

## 16. Residual risks 与 destination

| residual | 当前处理 | owner / destination |
|---|---|---|
| credential storage-state refresh/retention/concurrent publish/cleanup | R02删除提前实现，只保留read input | GitHub Issue #178 / `WU-SEMANTIC-OWNERSHIP-01-WEB-STORAGE-R1` |
| live网站DOM/event/error规模会变化 | 使用controller冻结且可配置的safety ceilings；runtime仍fail bounded并诊断，S3/aggregate只记录metrics | Web config owner；未来有直接超限证据时独立config change，不在backend |
| proxy下无法证明origin peer | proof+active proxy typed fail closed，不声称proof | Web HTTP transport/config owner；不在R02发明proxy-aware TLS proof |
| Playwright无法提供numeric peer proof | proof-on browser typed unavailable/fail closed | browser backend owner；未来需求另立设计，不绕过 |
| external provider/challenge波动 | local deterministic hard gate + external补充 | Web diagnostics/smoke owner；不改变accepted semantics |
| unified authorization愿景 | R02明确不设计、不预埋 | Topic 9 future controller decision，当前 no-code |
| R03 accepted-result/LLM projection | 本计划无diff、无依赖 | umbrella R03，必须在R02 accepted后另开独立plan gate |

## 17. 本 plan gate 完成信号与 handoff

本轮只有以下条件同时成立才算“plan review finding fix已authored并等待controller validation”，不等于R02 accepted/code-generation execution entry：

- 必读文档、三路精确designtruth reviews、补充audit与HEAD/range证据已记录；controller discussion优先级明确。
- root cause、owner、现状、baseline drift、三 slices、逐文件/符号/call chain、删除/保留contract、tests/coverage/pyright/README/scans/smokes均可直接执行。
- initial budgets保持controller冻结字面值；S1 entry无数值充分性gate，S3/aggregate只记录metrics且直接不足才stop，无backend第二默认。
- `R02-B01/B02`已按plan-entry adjudication精确写回为accepted/closed；新增闭集只含`web_search_providers.py`与`tests/runtime/test_config_loader.py`，未被兼容方案扩大或绕过。
- `R02-PF-01..10`均按plan-review controller adjudication闭合；rejected项保持未实施。
- AgentCodex authored changes恰好为本文与`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md`；其它既有control/plan-entry/review/controller artifacts不修改。无产品、测试、README、control、design改动，whitespace检查通过且无commit。

### 17.1 Plan-time read-only validation baseline

| check | HEAD result | interpretation |
|---|---|---|
| R02-S1 umbrella filter | `122 passed, 2 skipped` | 当前旧config/budget/egress/provider baseline可执行；skip不授权未来slice跳过新增owner cases |
| R02-S2 umbrella filter | `25 passed, 1 skipped, 98 deselected` | 当前private/proxy/peer/browser/challenge baseline可执行；accepted defaults/independence仍未实现 |
| R02-S3 umbrella filter | `36 passed, 163 deselected, 3 dependency deprecation warnings` | 当前diagnostic/storage/challenge baseline可执行；通过不代表lifecycle正确，测试正固化待删contract |
| full pyright | `0 errors, 0 warnings, 0 informations` | implementation不得新增或扩散 |
| deterministic local real Playwright smoke | exit `0`、7 local cases全过 | 证明当前browser/diagnostic executable path；budget规模结论受§11限制 |
| current plan diff whitespace | `git diff --check`无输出且exit 0；对未跟踪新增artifact的`git diff --no-index --check /dev/null <artifact>`无whitespace输出（no-index因“存在差异”返回1） | plan artifact自身无whitespace error；不能把no-index的expected difference exit误报为校验失败 |
| historical range whitespace | `git diff --check b1a0631f^..HEAD`命中既有review artifacts的trailing whitespace/blank EOF | 这些都在本轮唯一allowlist之外且不是本plan产生；不修改、不登记成R02 implementation baseline waiver |

历史range whitespace失败不削弱本轮current diff gate：R02 implementation仍必须以各slice base运行`git diff --check`并要求自身diff为0。

Handoff：当前AgentCodex到此停止并等待controller validation；本轮不自行启动双路re-review、不commit、不更新control、不进入implementation或R03。后续gate只能由controller授权。
