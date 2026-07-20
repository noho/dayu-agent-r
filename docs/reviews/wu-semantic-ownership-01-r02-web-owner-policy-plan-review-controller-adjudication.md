# WU-SEMANTIC-OWNERSHIP-01 / R02 plan review controller adjudication

## 1. 身份、证据与总裁决

- 本文裁决既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU `R02` 的两路完整 plan review；不是新 WU、feature 或 issue。
- immutable review target：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` 与 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-entry-controller-adjudication.md`。
- review artifacts：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-mimo.md` 与 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-ds.md`。
- 裁决真源依次为用户已完成的产品裁决、`AGENTS.md`、controller discussion、五份 design truth、umbrella remediation plan、plan-entry adjudication、当前代码直接证据。reviewer 建议不能重新打开已裁决产品值或删减 retained security。
- 总结：接受九组 plan fix，缩窄接受一组，拒绝六组。R02 plan 当前不通过，进入 AgentCodex plan-fix gate；任何 implementation 仍未授权。

## 2. Accepted findings

### R02-PF-01 — 修复 pre-S1 / S3 循环

来源：MiMo `R02-PR-F01`、DS `R02-DS-F01`、DS Q1。

裁决：接受 finding，拒绝新增 pre-S1 micro-slice。计划必须：

- 删除 S1 entry 对未来 `--filing-fixture` 或任何 S3 代码的依赖；不得在 accepted-plan commit 前修改 smoke 代码。
- 删除新增 `--filing-fixture` 公共 CLI 参数及其 containment/grammar；S3 直接在现有 `smoke_web_ci.py` 内用模块级私有 fixture case/常量接入版本化 SEC AAPL HTML，不新增用户输入协议。
- 用户/controller 已冻结 umbrella initial ceilings。plan-time 现有 smoke、版本化 AAPL 与 22 MiB 当前样本没有证明这些值不足，因此 S1 直接使用冻结值；它们是 configurable safety ceilings，不承诺所有财报业务完整。
- S3/aggregate 真实 fixture smoke 记录 observed metrics/headroom；若直接证据显示冻结值不足，立即 stop 回 controller，不在 backend 藏第二默认。

### R02-PF-02 — 删除未经授权的 ordinary artifact atomic-write 扩展

来源：MiMo `R02-PR-F02`、DS `R02-DS-F02`、DS Q2。

裁决：接受事实 finding，采用比 reviewer 建议更窄的 owner-bound fix。HEAD 证明普通 JSON/JSONL/markdown diagnostics 当前非原子；umbrella 只允许保留既有普通原子写，不授权新建。计划必须：

- 从 root cause、保留 contract、S3 文件清单、tests、smoke、coverage、source scan、completion 与 residual 中删除新增 ordinary atomic writer、fsync/replace/rollback及其测试要求。
- 明确 R02 只删除 credential storage-state lifecycle 自带的 publish/permission/reconcile 原子状态机；不把它迁移或复用成普通 artifact helper。
- 保持当前 ordinary diagnostic/smoke output writer 语义不变。本 WU 不设计新的临时文件命名、fsync 或恢复 contract。
- Issue 178 仍只拥有 future credential lifecycle；普通 artifact 原子化不是本 WU residual obligation，也不得偷塞给 Issue 178。

MiMo “新增 helper 只是措辞修正”与 DS “补齐更详细 atomic contract”的方案均不采纳，因为二者仍会实施未经产品裁决的额外功能。

### R02-PF-03 — 明确 environment proxy 实际选择 owner

来源：MiMo `R02-PR-F03`。

裁决：接受。计划必须指定 `web_http_session.py` 在一次 attempt 内使用 `requests.Session.merge_environment_settings(...)` 取得将要传给同一次 `Session.send(...)` 的 proxies settings，再用 Requests 的 proxy selection helper 对当前 URL 选择实际 proxy；warning 与 proof incompatibility 均基于这个同源 selected proxy。不得只检查环境变量是否存在、不得使用 urllib3 私有状态、不得二次解析 proxy credentials。proxy disabled 时 `trust_env=false` 且传空 proxies；warning 仅含非敏感布尔/稳定 reason。

### R02-PF-04 — 明确 S1/S2 transport policy 数据流

来源：MiMo `R02-PR-F06`。

裁决：接受。S1 只在 config snapshot 中构造并保存 frozen `WebHttpTransportPolicy`，当前 secure pinned/no-proxy行为不变；S2 原子修改 `_send_authorized_request` / plain sender 的 named parameter 和全部 fetch/search callers，按 policy 选择 standard 或 proof-on transport。不得在 S1 留半迁移 sender，也不得用默认参数兼容旧 caller。

### R02-PF-05 — browser proof-on fail-close exact contract

来源：MiMo OQ-1、DS `R02-DS-F04`。

裁决：接受。config 允许 `dns_peer_proof_enabled=true` 与 `browser_enabled=true` 共存，因为 HTTP proof path仍有效；只有 browser fallback 真正将要启动时，在启动 Playwright 进程前 early fail。使用 browser-owned typed outcome 的独立稳定 reason `browser_peer_proof_unavailable`（或等义、在 plan 中冻结的唯一字面值），不得复用 private-network reason。LLM-facing message 只说明当前浏览器访问无法验证目标连接，不暴露 Playwright、socket、Host/runtime术语。challenge detection事实仍保留，HTTP结果/失败不被回写。

### R02-PF-06 — provider parser local override owner

来源：DS `R02-DS-F05`、DS Q6。

裁决：接受澄清。不得修改 ConfigLoader 的 record-replace contract或实现 deep merge。`provider._parse_config` 只对 ConfigLoader 给出的最终 provider record逐字段读取：缺失 bool/group/field取 typed default，存在值精确校验；一个 sibling override不改变其它 sibling的 typed default。测试必须证明 workspace record replacement仍成立，同时 final partial record在 provider parser边界获得缺失字段 defaults。

### R02-PF-07 — custom-port search result visibility 同源

来源：DS `R02-DS-F09`。

裁决：接受。S1 必须让 search result URL visibility 同时消费 private/custom-port 两个 typed policy事实；不得继续由单一 `allow_private_network_url` 代签 custom port，也不得从 raw config重读。增加 owner-level test证明 custom-port allow/deny与 fetch egress decision一致。

### R02-PF-08 — DuckDuckGo challenge retained regression

来源：DS `R02-DS-F10`。

裁决：接受。S2 在允许的 Web provider test 中加入 deterministic DuckDuckGo challenge response，证明迁移 transport 前后仍调用同一个 challenge detector、仍不跟随 redirect、provider business failure/result semantics不变。`web_challenge_detection.py` 仍无 diff；若必须修改则 stop 回 controller。

### R02-PF-09 — aggregate budget type 纯组合

来源：MiMo OQ-2。

裁决：接受为低风险自足性修复。计划明确 `WebResourceBudgets` 只是 frozen typed composition，不做 `__post_init__`、跨 owner validation、default或facade；三个 child budget parser/constructor分别拥有正数校验。

## 3. Narrowed finding

### R02-PF-10 — budget evidence wording 与 S3 stop

来源：MiMo `R02-PR-F04`、DS `R02-DS-F08`、DS Q1。

裁决：只接受计划内部证据/时序矛盾，不接受重新裁决数值或要求证明对所有真实站点普遍充分。

- 128/256 MiB、1 MiB、16/8 Mi chars、8 Ki/512 是用户/controller 已冻结且可配置的 safety ceilings；包括 1 MiB warmup，不恢复旧 64 KiB。
- 删除“必须在 pre-S1 普遍证明充分”以及任何把 ceiling 描述为业务完整性的文本。
- 保留 plan-time 已观测事实与证据边界；S3/aggregate 记录版本化 fixture metrics。只有直接命中/不足证据才 stop 回 controller。
- residual 只记录 live-site规模变化由 Web config owner未来基于直接证据调整，不把缺少万能证明列为未完成 finding。

## 4. Rejected findings and questions

### MiMo `R02-PR-F05` — rejected

§4.1 已逐字段冻结五 bool 与三 budget group exact values，§8.3 引用 packaged/typed conformance；code-generation无需在测试章节重复同一字面值。不得为减少推导而复制第二份真源。

### DS `R02-DS-F03` / Q3 — rejected

固定 search provider endpoint 仍是不可信网络目标。DNS/address/custom-port policy、dangerous/unspecified/multicast防御与 proof-on verification 是 retained security，不能因 endpoint 固定而绕过，也不能添加 known-safe hostname bypass。S2 必须复用同一 HTTP transport与egress owner；`allow_redirects=false` 只表示无需 redirect loop，不表示跳过初始 URL authorization。plan-entry adjudication中“egress决定”保持有效。

### DS `R02-DS-F06` / Q4 — rejected

当前 diagnostic CLI 只有 `store_true --allow-private-network-url`，不能表达 false；packaged default改为true后它是无效第二入口，不是一个合法 deny override。用户已裁决 private/custom由 `tool_discovery.json` 控制。删除该 flag正确；显式 deny由 typed config/provider owner tests与 smoke internal overlay验证，不新增 `--no-*` 或第二 parser。

### DS `R02-DS-F07` / Q5 — rejected

AGENTS.md 要求每个 changed production file coverage目标 `>=80%`，不能按 changed lines、import boundary或外部API依赖豁免。Tavily/Serper/DDG 路径可通过 monkeypatch environment、HTTP sender与deterministic response fixture测试，无需真实 key或外网。允许的 `test_web_tools_provider.py` 可以补齐 owner tests；不得降低门禁。

### DS `R02-DS-F11` — rejected as superseded

`R02-PF-01` 删除新增 `--filing-fixture` 用户输入，因此不再存在该 CLI path containment/error contract。S3 只用模块级私有、版本化仓库 fixture constant；若 constant 不存在或不是 regular file，test/smoke直接失败，不创建新的通用 path authority。

### DS Q6 — closed by R02-PF-06

ConfigLoader record replacement保持；local defaults只归 provider parser。

## 5. Plan-fix verification requirements

AgentCodex 必须只修改 plan并新增固定 fix artifact `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-fix-codex.md`；不得改两个 review、controller artifacts、产品、测试、README或control。Fix artifact逐项记录 `R02-PF-01` 至 `R02-PF-10` 的修改位置，并证明：

- 所有 `--filing-fixture`、pre-S1 S3依赖与 ordinary atomic-writer新增语义零残留；
- frozen ceilings字面值未被重新打开或改变；
- search endpoint仍保留初始 DNS/egress/peer安全检查；
- diagnostic private CLI flag仍计划删除；
- coverage `>=80%`未降低；
- Issue 178、统一 authorization、其它 deferred Issue与R03边界未改变；
- `git diff --check`通过，工作区除既有plan/control/review artifacts与fix artifact外无其它diff。

完成后只能进入 MiMo/DS 对最终完整计划的双路 re-review；不得 implementation或 accepted-plan commit。
