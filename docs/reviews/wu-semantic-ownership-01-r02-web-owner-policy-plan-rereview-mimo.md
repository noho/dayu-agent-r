# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy Plan Re-Review — MiMo (第一路)

## 1. 身份、范围与证据

- **审查类型**：第一路完整 re-review（plan finding fix 后、controller validation 前）。
- **审查目标**：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（fix 后最终全文）。
- **裁决真源**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`（`R02-PF-01..10` 唯一 disposition 真源）。
- **Fix 记录**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md`。
- **初始 reviews**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-ds.md`。
- **Plan-entry adjudication**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`。
- **证据来源**：AGENTS.md、controller discussion Topic 2/9、五份 design truth、当前 HEAD production code/tests/config。
- **Temporal baseline**：2026-07-14，当前分支 `phaseflow/host-issues-control`，HEAD `02fcc5d8`。
- **审查姿势**：逐项验证 `R02-PF-01..10` 是否按 controller adjudication 真正关闭；验证 rejected 项是否未实施；验证 owner/依赖/slice/验证/安全/deferred scope 是否一致。不把 reviewer 原建议覆盖 controller 裁决。

## 2. 逐项 Closure 验证

### R02-PF-01 — pre-S1 / S3 循环 — ✅ 已关闭

- **Adjudication 要求**：删除 S1 entry 对 S3 smoke 能力的依赖；S3 用模块级私有 fixture constant/`LocalFixtureCase`，不新增 `--filing-fixture` CLI 参数。
- **Plan 实际状态**：§8.1 已删除 S1 entry 对 §11 数值裁决的依赖，改为 "controller 冻结的全部 budget values 直接进入 S1，不再设置 implementation 前的数值充分性裁决"。§10.3.2 明确 "以模块级私有常量和 `LocalFixtureCase` 直接接入版本化 SEC AAPL HTML；不新增 fixture CLI 或任何用户输入协议"。§11.2 删除了 pre-S1 数值裁决 gate，S3/aggregate 只记录 metrics。§13.1 执行命令不包含 `--filing-fixture` 参数，只使用现有 CLI 协议。
- **当前代码验证**：`utils/smoke_web_ci.py` 的 `_parse_args` 不含 `--filing-fixture` 参数（HEAD 确认）。plan 不要求在 S1 前修改 smoke 代码。
- **Rejected 项确认**：controller 拒绝了新增 pre-S1 micro-slice 的方案，plan 中未实施该方案。
- **结论**：循环依赖已消除。S1 entry 不依赖任何 S3 代码变更。

### R02-PF-02 — 删除 ordinary artifact atomic-write — ✅ 已关闭

- **Adjudication 要求**：从 plan 中删除所有新增普通 atomic writer、fsync/replace/rollback 及其测试要求；保持当前 ordinary writer 语义不变。
- **Plan 实际状态**：§2.3 "ordinary diagnostic write" 行明确 "当前 JSON/JSONL/summary 直接写 final path"，"R02 保持现有普通 writer 语义不变；只删除 credential lifecycle 自带的 publish/permission/reconcile 状态机，不迁移或复用该状态机"。§4.4 "保留" 段声明 "ordinary JSON/JSONL/markdown diagnostic/smoke artifact 继续使用当前 writer 语义；R02 不新增任何普通 artifact writer contract"。§10.3.1 明确 "`_write_json`、`_write_jsonl` 和 summary writer 保持当前普通写语义；不得新增普通 writer helper，也不得复用待删 credential lifecycle"。§10.3.2 同样要求 "普通 run artifact writer 保持当前语义，不新增普通 artifact 行为"。
- **零残留验证**：plan 全文搜索 `fsync`、`os.replace`、`rollback`、`atomic`（排除语义描述 context）——只在 §0 gate verdict 的 "PLAN REVIEW FINDING FIX AUTHORED" context 和 §10.3.1 的 "不得新增普通 writer helper" 禁止性描述中出现，不构成新增 atomic writer 实施指令。
- **Rejected 项确认**：controller 拒绝了 MiMo "新增 helper 只是措辞修正" 和 DS "补齐更详细 atomic contract" 两个方案。plan 中未实施这两个方案——没有新增 atomic helper 定义、fsync 策略、临时文件命名约定或恢复策略。
- **Issue 178 边界确认**：§0、§4.4、§5.3、§16 均明确 Issue 178 只拥有 future credential lifecycle，普通 artifact 原子化不是 R02 residual obligation。
- **结论**：ordinary artifact atomic-write 扩展已完全删除。当前 ordinary writer 语义保持不变。

### R02-PF-03 — proxy 实际选择 owner — ✅ 已关闭

- **Adjudication 要求**：指定 `web_http_session.py` 使用 `Session.merge_environment_settings(...)` + `requests.utils.select_proxy(...)` 检测实际 proxy；warning 与 proof incompatibility 基于同源 selected proxy。
- **Plan 实际状态**：§4.3 明确 "调用 `Session.merge_environment_settings(prepared.url, proxies, stream, verify, cert)` 得到将原样传给同一次 `Session.send(prepared, ..., **settings)` 的 settings，再用 `requests.utils.select_proxy(prepared.url, settings['proxies'])` 得到该 URL 的 selected proxy。warning 与 proof incompatibility 只消费这个同源 selected proxy，不检查环境变量是否存在、不读 urllib3 私有状态、不二次解析 proxy credentials"。§9.2 进一步细化了 "每个 attempt 只 prepare 一次 request" 的流程。
- **proxy disabled 路径确认**：§4.3 明确 "`allow_environment_proxy=false`：attempt 使用 `trust_env=false`，清空 session/per-call proxies 并保证传给同一次 `Session.send` 的 settings 中 `proxies={}`；不得读取 environment proxy"。
- **warning 脱敏确认**：§4.3 明确 "warning 只含非敏感 bool 与稳定 reason，不记录 proxy 值、URL/query、userinfo、headers、cookies 或 storage path"。
- **结论**：proxy 选择检测方案已明确且可实施。

### R02-PF-04 — S1/S2 transport policy 数据流 — ✅ 已关闭

- **Adjudication 要求**：S1 只在 config snapshot 中构造 frozen `WebHttpTransportPolicy`，sender 保持 secure pinned/no-proxy；S2 原子修改 `_send_authorized_request` / plain sender 的必填 named parameter 和全部 callers。
- **Plan 实际状态**：§8.2.5 明确 "新增最小 frozen `WebHttpTransportPolicy(dns_peer_proof_enabled, allow_environment_proxy)`；不在此定义部署默认数值。S1 不修改 `_send_authorized_request` 签名或行为，继续 secure pinned/no-proxy"。§8.2.6 明确 "S1 只保存 transport policy，不把它 thread 到 sender"。§4.3 明确 "S2 在一个原子 diff 内给 `_send_authorized_request`、plain search sender 及全部 fetch/search caller 增加必填 named parameter `transport_policy: WebHttpTransportPolicy`；不得提供兼容 default，也不得留下半迁移 caller"。§8.3 确认 "S1 sender 仍是当前 pinned/no-proxy 行为，`_send_authorized_request` 尚无 transport policy 参数；防止在 S1 留下半迁移 transport"。
- **结论**：S1/S2 边界清晰，transport policy 数据流路径已明确。

### R02-PF-05 — browser proof-on fail-close exact contract — ✅ 已关闭

- **Adjudication 要求**：config 允许 `dns_peer_proof_enabled=true` 与 `browser_enabled=true` 共存；browser fallback 即将启动时 early fail，使用独立 reason `browser_peer_proof_unavailable`，不复用 private-network reason，不启动 Playwright 进程。
- **Plan 实际状态**：§4.3 明确 "`browser_enabled=true` 与 `dns_peer_proof_enabled=true` 是合法 config 组合，HTTP proof path 仍照常运行"。§4.3 明确 "只有 HTTP 结果/challenge 事实已经决定进入 browser fallback、且 fallback 真正将要启动时，caller 才检查 proof-on；若 `dns_peer_proof_enabled=true`，在调用任何会 import/启动 browser 的路径以及 `_run_playwright_worker_process(...).process.start()` 之前返回 browser-owned typed failure，稳定 reason 唯一冻结为 `browser_peer_proof_unavailable`"。§4.3 明确 "不得在 config 构造时拒绝该组合，不启动 Playwright 进程，不复用 private-network reason"。§4.3 明确 "该 typed failure 不回写或改写既有 HTTP 结果、HTTP 失败或 challenge detection 事实。面向 LLM 的 message 只表达'当前浏览器访问无法验证目标连接'，不得暴露 Playwright、socket、Host/runtime 或内部治理术语"。
- **§9.5 测试矩阵确认**：`browser=true + proof=true` case 要求 "HTTP proof path 不受影响；仅实际 fallback 启动前返回 `browser_peer_proof_unavailable`，Playwright import/process start 零调用，LLM-facing message 无内部术语"。
- **结论**：browser proof-on fail-close 的错误类型、检测时机和 LLM-facing 约束均已明确冻结。

### R02-PF-06 — provider parser local override owner — ✅ 已关闭

- **Adjudication 要求**：不得修改 ConfigLoader 的 record-replace contract；`provider._parse_config` 只对 final provider record 逐字段读取，缺失取 typed default，存在值 exact validate。
- **Plan 实际状态**：§4.1 明确 "`ConfigLoader` 继续保持 workspace 同 id provider record 整条替换、record 内不做 deep merge 的既有 contract；R02 不修改该 owner 语义。`provider._parse_config` 只读取 ConfigLoader 交付的 final provider record：final record 缺失任一 bool、`resource_budget` group 或 group field 时，由 provider parser 为该缺失项补对应 typed default；final record 中已存在的 sibling 值保持原值"。§8.2.3 确认 "不得修改 ConfigLoader record-replace contract 或在 ConfigLoader 做 deep merge"。§8.3 要求 "保持并运行 ConfigLoader 既有 record-replace test 且不修改其 contract；provider owner test 把 final partial record 直接交给 `_parse_config`，证明整体 budget 缺失、单 group 缺失、单 field 缺失只补对应 typed default，已有 sibling 不变"。
- **结论**：ConfigLoader record-replace 语义保持不变，local defaults 只归 provider parser。

### R02-PF-07 — custom-port search result visibility 同源 — ✅ 已关闭

- **Adjudication 要求**：S1 让 search result URL visibility 同时消费 private/custom-port 两个 typed policy 事实。
- **Plan 实际状态**：§8.2.6 明确 "`_search_web_business` 只传 `http_resource_budget`，并把同一 typed `WebEgressPolicy(private, custom-port)` 直接交给 search result visibility；移除由 raw `allow_private_network_url` 单独代签 visibility 的接口"。§8.2.8 明确 "`search_public_web` / `_filter_visible_results` 消费 caller 已构造的 typed `WebEgressPolicy`，由其 `is_url_allowed` 同源决定 private/custom-port visibility；不得重读 raw config 或保留只接 private bool 的旧 checker contract"。§8.3 要求 "search result visibility 对 private/custom-port allow/deny 的决定与 fetch 使用同一 typed policy；无 raw config 重读"。
- **结论**：search result visibility 已改为消费同一 typed policy，不再由单一 private bool 代签。

### R02-PF-08 — DuckDuckGo challenge retained regression — ✅ 已关闭

- **Adjudication 要求**：S2 加入 deterministic DuckDuckGo challenge response 回归用例；`web_challenge_detection.py` 零 diff。
- **Plan 实际状态**：§9.5 测试矩阵包含 "DuckDuckGo deterministic challenge response: plain sender 返回固定 challenge HTML；同一个 `detect_bot_challenge` recorder 被调用、`allow_redirects=false`、仍产生原 `challenge_response` 业务失败语义；`web_challenge_detection.py` 零 diff"。§9.6 gate commands 包含 `git diff --exit-code -- dayu/tools/web/web_challenge_detection.py`，明确 "若必须修改该文件，立即 stop 回 controller"。
- **结论**：DuckDuckGo challenge 回归用例已加入 S2 测试矩阵，challenge detector 零 diff 约束已明确。

### R02-PF-09 — aggregate budget type 纯组合 — ✅ 已关闭

- **Adjudication 要求**：`WebResourceBudgets` 只是 frozen typed composition，不做 `__post_init__`、跨 owner validation、default 或 facade。
- **Plan 实际状态**：§4.2 明确 "`WebResourceBudgets(http, browser, diagnostics)`：只作为无 default 的 frozen typed composition；不实现 `__post_init__`、跨 owner validation、flattened property、validator facade 或第二组 defaults。三个 child budget 各自在自身 constructor/parser 边界拥有非 bool正整数校验"。§8.2.2 确认 "aggregate 是无 default、无 `__post_init__`、无 validator 的纯 frozen 组合"。§8.3 要求 "`WebResourceBudgets` 无 default、无 `__post_init__`/validator、无 flattened compatibility properties"。
- **结论**：aggregate budget type 已明确定义为纯 frozen composition。

### R02-PF-10 — budget evidence wording 与 S3 stop — ✅ 已关闭（narrowed）

- **Adjudication 要求**：保持 controller 冻结值；删除 "必须在 pre-S1 普遍证明充分" 文本；S3/aggregate 只记录 metrics，只有直接命中/不足证据才 stop。
- **Plan 实际状态**：§7 明确 "controller 已冻结" 行与 "S1 直接使用全部冻结值；S3/aggregate 只记录 observed metrics，只有直接不足证据才 stop，不得 backend second default"。§8.1 明确 "controller 冻结的全部 budget values 直接进入 S1，不再设置 implementation 前的数值充分性裁决"。§11.1 标题改为 "Plan-time 已执行的直接证据"，结论行改为 "不把 ceiling 描述为业务完整性承诺"。§11.2 标题改为 "S3/aggregate metrics 记录与唯一 stop 规则"，明确 "只有真实 fixture 或受控 case 直接命中/超过对应冻结 ceiling、或直接产生由该 ceiling 导致的业务失败，才立即 stop 回 controller；缺少万能充分性证明或 live-site 未来可能变化都不阻塞 S1/S2/S3"。§16 residual risks 表中 "live 网站 DOM/event/error 规模变化" 行改为 "使用 controller 冻结且可配置的 safety ceilings；runtime 仍 fail bounded 并诊断，S3/aggregate 只记录 metrics"。
- **冻结值确认**：§4.1 packaged config 中 128/256 MiB、1 MiB warmup、16/8 Mi chars、8 Ki chars/512 events 均保持未变。
- **结论**：pre-S1 普遍充分性要求已删除，frozen values 保持不变，stop 规则已明确。

## 3. Rejected 项验证

| rejected 边界 | 验证结果 |
|---|---|
| MiMo `R02-PR-F05`：不为 test 章节复制第二份 packaged expected-values 真源 | ✅ 未实施。§8.3 引用 §4.1 packaged projection，不复制第二套值。 |
| DS `R02-DS-F03` / Q3：固定 provider endpoint 不得绕过初始 DNS/egress/peer 防御 | ✅ 未实施。§9.2 明确 "Tavily/Serper/DuckDuckGo 固定 endpoint 虽然 `allow_redirects=false`，仍在首次发送前执行同一 DNS/address/custom-port authorization，并在 proof-on 时执行同一 peer 防御；不得因 endpoint 固定而 known-safe bypass"。 |
| DS `R02-DS-F06` / Q4：diagnostic private CLI flag 继续删除 | ✅ 保持删除。§4.4 和 §10.3.1 明确删除 `--allow-private-network-url`。 |
| DS `R02-DS-F07` / Q5：coverage 仍 `>=80%` | ✅ 保持。§7 和 §14.1 保留逐 changed production file `>=80%` 门禁。 |
| DS `R02-DS-F11`：不新增 fixture path authority | ✅ 未实施。§10.3.2 明确 "不新增 fixture CLI 或任何用户输入协议"。S3 只用模块级私有版本化常量。 |
| DS Q6：ConfigLoader 不改 deep-merge 语义 | ✅ 已由 R02-PF-06 关闭。§4.1 和 §8.2.3 确认。 |

## 4. Owner / 依赖 / Slice / 验证 / 安全 / Deferred Scope 一致性

### 4.1 Owner 一致性

| owner | plan 声明 | 代码事实 | 一致 |
|---|---|---|---|
| packaged Web config | `tool_discovery.json` + `provider._parse_config` | HEAD：`tool_discovery.json` 只有 `allow_private_network_url=false`；`provider._parse_config` 只解析 private bool 和 complete `resource_budget` | ✅ |
| HTTP transport policy | `WebHttpTransportPolicy` (S1 定义，S2 实施) | HEAD：不存在 `WebHttpTransportPolicy` | ✅ plan 新增，非已有 |
| browser capability | `WebToolsConfig.browser_enabled` (S1 新增) | HEAD：browser 被 `allows_private_network` 前置禁用 | ✅ plan 解耦 |
| egress policy | `WebEgressPolicy(private, custom-port)` (S1 拆分) | HEAD：只有 `allow_private_network`，custom port 与之耦合 | ✅ plan 拆分 |
| budget | 三个 typed budget (S1 替换) | HEAD：七字段 `WebResourceBudget` complete object | ✅ plan 替换 |
| diagnostics v2 | `web_diagnostics.py` 不变 | HEAD：`web-diagnostics-v2` revision 2 | ✅ |
| credential lifecycle | Issue #178 | HEAD：`_StorageStateLifecycle` 存在 | ✅ plan 删除，Issue #178 接管 |

### 4.2 依赖顺序一致性

- S1 → S2 → S3 严格串行：§8.5 "没有 accepted commit 不得开始 S2"，§9.7 同理。✅
- S1 不依赖 S3 代码：§8.1 已删除对 S3 smoke 能力的依赖。✅
- S2 不依赖 S3：transport policy / browser 解耦均在 S1/S2 完成。✅

### 4.3 Slice 边界一致性

- S1 changed files（§6.3）：`tool_discovery.json`、`provider.py`、`web_resource_budget.py`、`web_egress_policy.py`、`web_http_session.py`、`web_tools.py`、`web_diagnostics.py`、`web_search_providers.py`、tests、README。✅ 与 §6.1 闭集一致。
- S2 changed files（§6.3）：`web_http_session.py`、`web_playwright_backend.py`、`web_tools.py`、`web_fetch_orchestrator.py`、`web_search_providers.py`、必要的 `web_egress_policy.py`/`web_recovery.py`、tests。✅ 与 §6.1 闭集一致。
- S3 changed files（§6.3）：`utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、tests、README。✅ 与 §6.1 闭集一致。

### 4.4 安全 retained contracts 一致性

| retained contract | plan 位置 | 代码事实 | 一致 |
|---|---|---|---|
| redirect 每 hop 重检 | §5.2, §9.2 | `web_fetch_orchestrator._request_with_safe_redirects` 存在 | ✅ |
| dangerous/unspecified/multicast 拒绝 | §5.2, §4.3 | `web_egress_policy.py` 中存在 | ✅ |
| mixed DNS fail closed | §5.2, §4.3 | `web_egress_policy.py` 中存在 | ✅ |
| peer proof numeric pin | §5.2, §4.3 | `web_http_session.py` 中 `_TargetBoundHTTPAdapter` 存在 | ✅ |
| challenge detection | §5.2, §9.3 | `web_challenge_detection.py` 独立存在 | ✅ |
| diagnostics v2/revision 2 | §5.2, §4.4 | HEAD 确认 `WEB_DIAGNOSTIC_SCHEMA_VERSION="web-diagnostics-v2"` | ✅ |
| redaction/allowlist | §5.2, §4.4 | HEAD 确认 | ✅ |
| explicit storage input | §5.2, §4.4 | HEAD 确认 `_resolve_playwright_storage_state_path` 存在 | ✅ |

### 4.5 Deferred scope 一致性

| deferred item | plan 边界 | 一致 |
|---|---|---|
| Issue #178 | §0, §4.4, §5.3, §16：只删除提前实现，不实施、不预埋 | ✅ |
| 统一 authorization | §2.1, §5.3：Topic 9 no-code | ✅ |
| R03 | §5.3, §16：不在 R02 scope，必须在 R02 accepted 后另开独立 plan gate | ✅ |

## 5. Codex Fix Artifact 验证

- **Fix artifact 存在**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md` ✅
- **逐项闭合表**：R02-PF-01 至 R02-PF-10 均有 plan 修改位置和闭合内容记录 ✅
- **Rejected 项记录**：§3 逐项列出 rejected boundary 和 plan 证据 ✅
- **验证记录**：§4 包含零残留扫描、frozen values 扫描、proxy 同源扫描、S1/S2 边界扫描、browser 扫描、parser/search/aggregate/challenge 扫描、rejected 边界扫描 ✅
- **Handoff**：明确 "等待 controller validation；不自行进入双路 re-review、不 implementation、不 commit" ✅

## 6. Plan 与 HEAD 代码事实交叉验证

| plan claim | HEAD 代码事实 | 一致 |
|---|---|---|
| "当前只有 `allow_private_network_url=false`" (§2.3) | `tool_discovery.json:78` 确认 `false` | ✅ |
| "七字段 `WebResourceBudget`" (§2.2) | `web_resource_budget.py:18-44` 确认 7 字段 | ✅ |
| "custom port 与 private 耦合" (§2.2) | `web_egress_policy.py:312-313` 确认耦合 | ✅ |
| "browser 被 `allows_private_network` 前置禁用" (§2.2) | `web_playwright_backend.py:1385-1391` 确认 | ✅ |
| "search providers 用 raw `requests`" (§2.2) | `web_search_providers.py:654,739,816` 确认 | ✅ |
| "`_StorageStateLifecycle` 存在" (§2.2) | `utils/diagnose_web_access.py:210-355` 确认 | ✅ |
| "ordinary diagnostic write 非原子" (§2.3) | `utils/diagnose_web_access.py:2750-2765` 使用 `Path.write_text` | ✅ |
| "`test_config_loader.py` 断言 `is False`" (§6.4) | `tests/runtime/test_config_loader.py:471` 确认 | ✅ |
| "`_send_authorized_request` 无 transport policy 参数" (§8.2.5) | `web_http_session.py:448-511` 确认签名无 policy 参数 | ✅ |
| "`WebHttpTransportPolicy` 不存在" (§8.2.5) | 全库零命中 | ✅ |
| "`allow_custom_port` 不存在" (§8.2.4) | 全库零命中 | ✅ |

## 7. 新发现

### R02-RR-F01 — 低 — packaged config 与 HEAD code default 数值差异缺少显式映射

- **位置**: §2.3 "packaged budgets" 行、§4.1 packaged config、§11.1
- **问题类型**: 契约细节
- **当前写法**: §2.3 声称 "代码默认 25/50 MiB、64 KiB、5M/1M chars、1024 chars/80 events"。§4.1 packaged config 指定 `warmup_body_bytes: 1048576`、`error_chars: 8192`、`events: 512`。
- **事实**: warmup 从 64 KiB → 1 MiB（16×），error_chars 从 1024 → 8192（8×），events 从 80 → 512（6.4×）。这些放大缺少逐项直接证据或 rationale 显式记录。
- **为什么不是 blocker**: controller 已在 R02-PF-10 narrowed adjudication 中明确 "128/256 MiB、1 MiB、16/8 Mi chars、8 Ki chars/512 events 是用户/controller 已冻结且可配置的 safety ceilings；包括 1 MiB warmup，不恢复旧 64 KiB"。这些值已被 controller 冻结，不因证据不充分而重新打开。
- **影响**: 无。值已被 controller 冻结，S3/aggregate 记录 observed metrics，直接不足才 stop。
- **建议**: 可在 §11.1 中增加一行显式映射表，列出旧值 → 新值和 controller 冻结 rationale，方便 implementation agent 理解变更幅度。但不阻塞 plan 通过。
- **严重程度**: 低

## 8. Open Questions

无新增 open questions。初始 reviews 的 OQ-1（browser proof fail-close）已由 R02-PF-05 关闭；OQ-2（aggregate budget type）已由 R02-PF-09 关闭。DS Q1-Q6 均已由 controller adjudication 关闭或合并到 R02-PF-01..10。

## 9. Residual Risks

plan §16 的 residual risks 表已完整覆盖，本 re-review 确认其处置合理：

| residual | plan 处置 | 本 re-review 评估 |
|---|---|---|
| credential lifecycle → Issue #178 | 删除提前实现，保留 read input | 处置正确 |
| live 网站规模变化 | controller 冻结 safety ceilings + S3/aggregate 记录 metrics | 处置正确 |
| proxy 下无法证明 origin peer | proof+proxy typed fail closed | 处置正确 |
| Playwright 无法提供 numeric peer proof | browser typed unavailable/fail closed | R02-PF-05 已明确 contract |
| external provider/challenge 波动 | local hard gate + external 补充 | 处置正确 |
| unified authorization → Topic 9 | 不设计/不预埋 | 与 controller discussion 一致 |
| R03 | 本 plan 无 diff/无依赖 | 处置正确 |

## 10. Verdict

**`pass`**

R02-PF-01 至 R02-PF-10 全部按 controller adjudication 真正关闭。所有 rejected 项保持未实施。owner/依赖/slice/验证/安全/deferred scope 全部一致。plan 与 HEAD 代码事实交叉验证通过。无 blocker、无 high finding。

唯一新发现 R02-RR-F01（packaged config 数值差异映射）为低严重度且已被 controller 冻结裁决覆盖，不阻塞 plan 通过。

### Closure Summary

| finding | 状态 | 证据 |
|---|---|---|
| R02-PF-01 | ✅ closed | §8.1, §10.3.2, §11.2, §13.1 — 无 S1→S3 依赖 |
| R02-PF-02 | ✅ closed | §2.3, §4.4, §10.3 — 无新增 atomic writer |
| R02-PF-03 | ✅ closed | §4.3, §9.2 — `merge_environment_settings` + `select_proxy` |
| R02-PF-04 | ✅ closed | §4.3, §8.2.5-8.2.6 — S1 保存、S2 原子迁移 |
| R02-PF-05 | ✅ closed | §4.3, §9.3, §9.5 — `browser_peer_proof_unavailable` |
| R02-PF-06 | ✅ closed | §4.1, §8.2.3, §8.3 — ConfigLoader 不改、parser 补 default |
| R02-PF-07 | ✅ closed | §8.2.6, §8.2.8, §8.3 — private/custom-port 同源 visibility |
| R02-PF-08 | ✅ closed | §9.5, §9.6 — DuckDuckGo challenge 回归 + 零 diff |
| R02-PF-09 | ✅ closed | §4.2, §8.2.2, §8.3 — frozen pure composition |
| R02-PF-10 | ✅ closed (narrowed) | §7, §8.1, §11, §16 — frozen values + metrics-only stop |
| rejected: MiMo F05 | ✅ 未实施 | §8.3 不复制第二份真源 |
| rejected: DS F03/Q3 | ✅ 未实施 | §9.2 固定 endpoint 仍做 DNS/egress/peer |
| rejected: DS F06/Q4 | ✅ 未实施 | §4.4, §10.3 CLI flag 仍删除 |
| rejected: DS F07/Q5 | ✅ 未实施 | §7, §14.1 coverage 仍 >=80% |
| rejected: DS F11 | ✅ 未实施 | §10.3.2 无 fixture CLI |
| rejected: DS Q6 | ✅ closed | R02-PF-06 关闭 |

### Finding Count

- New findings: 1 (low)
- Open questions: 0
- Residual risks: 7 (all with owner/destination, non-blocking)

---

**审查完成时间**: 2026-07-14 21:50:29 +0800（本机系统时钟）
**审查分支**: `phaseflow/host-issues-control`
**审查基线**: `02fcc5d8325fc7c3c2ef2f60a049910edb6ebfcb`
**审查范围**: plan fix 后最终全文 + Codex fix artifact + 当前 HEAD code facts
