# WU-SEMANTIC-OWNERSHIP-01 / R02 Web Owner Policy plan review finding fix — Codex

## 1. 身份、范围与裁决真源

- 本文记录既有umbrella `WU-SEMANTIC-OWNERSHIP-01`内部R02 plan review finding fix；不是新WU、feature或issue，不授权implementation。
- 修改目标仅为`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`；本文是唯一新增artifact。
- 已完整读取目标plan、MiMo/DS两路完整plan review、plan-entry controller adjudication、plan-review controller adjudication及直接相关代码。
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-plan-review-controller-adjudication.md`是finding disposition唯一真源；未重新裁决reviewer建议。
- 动机判断：R02 owner问题真实且为production-high，但Controller已把修复收窄到既有Web owner与credential lifecycle删除边界；无需统一framework、额外writer能力或新fixture CLI。
- 生成时间：`2026-07-14 21:41:53 +0800`（本机系统时钟）。

## 2. `R02-PF-01..10` 逐项闭合

| finding | plan修改位置 | 闭合内容 |
|---|---|---|
| `R02-PF-01` | §8.1、§10.2-10.3、§11.2、§13.1-13.2 | 删除S1 entry对未来S3 smoke能力的依赖；S3仅用`smoke_web_ci.py`模块级私有版本化fixture constant/`LocalFixtureCase`接入SEC AAPL HTML，不新增fixture CLI/path输入或前置micro-slice。 |
| `R02-PF-02` | §0、§2.3、§3.1、§4.4、§5.2、§6.1、§7、§10、§13、§15.4、§16 | 保持当前ordinary JSON/JSONL/markdown writer语义；删除所有新增普通writer helper、测试、smoke、completion与residual要求。R02只删除credential lifecycle自带的publish/permission/reconcile状态机，不迁移到普通artifact，也不转交Issue #178。 |
| `R02-PF-03` | §4.3、§9.2、§9.4-9.5 | 冻结一次attempt只prepare一次request；`Session.merge_environment_settings(...)`产生同一次`Session.send(...)`使用的settings，再由`requests.utils.select_proxy(...)`选择当前URL proxy。warning/proof conflict只消费该selected proxy存在性并脱敏；proxy禁用时`trust_env=false`且send settings为`proxies={}`。 |
| `R02-PF-04` | §4.3、§6.1、§8.2-8.3、§9.2、§9.4 | S1只构造并保存frozen `WebHttpTransportPolicy`，sender仍保持secure pinned/no-proxy；S2原子给`_send_authorized_request`、plain search sender和全部fetch/search callers增加无default的必填named `transport_policy`参数。 |
| `R02-PF-05` | §4.3、§9.3、§9.5 | 允许browser/proof-on config共存且HTTP proof path照常运行；仅实际fallback即将启动时，在任何browser import/process start前返回独立typed reason `browser_peer_proof_unavailable`，不启动Playwright、不复用private reason、不改写HTTP/challenge事实；LLM-facing message不暴露内部术语。 |
| `R02-PF-06` | §4.1、§8.2-8.3 | 明确ConfigLoader继续整条record replacement、无deep merge；`provider._parse_config`只消费final provider record，为缺失bool/group/field补typed default并exact validate已有值。既有ConfigLoader record-replace test保持，final partial record defaults在provider owner test证明。 |
| `R02-PF-07` | §6.1、§6.4、§8.2-8.3 | search result visibility直接消费同一个typed `WebEgressPolicy(private, custom-port)`，不再由private raw bool代签custom-port、不重读raw config；增加与fetch egress decision一致的owner test。 |
| `R02-PF-08` | §9.5-9.6 | 增加deterministic DuckDuckGo challenge response regression：同一detector被调用、redirect仍禁用、`challenge_response`业务失败语义不变；`web_challenge_detection.py`必须零diff，否则stop。 |
| `R02-PF-09` | §4.2、§8.2-8.3 | `WebResourceBudgets`冻结为无default、无`__post_init__`、无validator/facade的纯composition；三个child constructor/parser分别拥有正整数校验。 |
| `R02-PF-10` | §7、§8.1、§11、§13.2、§15.3-15.4、§16-17 | 128/256 MiB、1 MiB、16/8 Mi chars、8 Ki chars/512 events全部保持Controller冻结值；删除S1前普遍充分性裁决，S3/aggregate只记录metrics，只有直接命中/超限或由ceiling直接导致业务失败才stop。 |

## 3. Rejected 项保持未实施

| rejected boundary | plan证据与扫描结论 |
|---|---|
| 不为test章节复制第二份packaged expected-values真源 | 精确字面值只在§4.1 packaged projection集中冻结；§8.3引用该真源，不复制第二套值。 |
| 固定provider endpoint不得绕过初始DNS/egress/peer防御 | §9.2、§9.4-9.5明确Tavily/Serper/DuckDuckGo首次发送前仍授权并在proof-on时执行peer检查；无known-safe bypass。 |
| diagnostic private CLI flag继续删除 | §4.4、§10.3与S3 source scan继续要求删除`--allow-private-network-url`及对应option/overlay；未新增`--no-*`第二入口。 |
| changed production file coverage仍`>=80%` | §7与§14.1保留逐实际changed production file门禁；未引入changed-lines/import-boundary/外部API例外。 |
| 不恢复64 KiB | §4.1与§11保持warmup `1048576`；旧64 KiB只作为HEAD历史事实与明确不恢复边界出现。 |
| 不新增fixture path authority | plan中无fixture CLI参数；S3只引用模块私有版本化常量/case，缺失或非regular file时直接失败。 |
| 不实施Issue #178、统一authorization、其它deferred Issue或R03 | 仅在non-goal、stop、residual destination与handoff中保留边界说明；无implementation slice。 |
| ConfigLoader不改deep-merge语义 | §4.1、§8.2-8.3明确final record parser defaults归provider owner；ConfigLoader record replacement保持。 |

## 4. 验证记录

### 4.1 关键零残留与保留扫描

- plan零残留scan：fixture CLI旧字面值、旧S1前置标签、`fsync`、`os.replace`、`rollback`、ordinary atomic writer相关pattern均零命中。
- frozen values scan：`134217728`、`268435456`、`1048576`、`16777216`、`8388608`、`8192`、`512`均仍在§4.1，未改变。
- proxy同源保留scan：`merge_environment_settings`、`select_proxy`、同一次send settings、proxy-disabled `proxies={}`均命中§4.3/§9.2。
- S1/S2边界保留scan：S1 secure pinned/no-proxy、S2必填named/no-default/全部caller原子迁移均命中。
- browser保留scan：`browser_peer_proof_unavailable`、`process.start()`零调用断言与LLM-facing限制均命中。
- parser/search/aggregate/challenge保留scan：record replacement、final partial record defaults、private/custom visibility、DuckDuckGo deterministic challenge、aggregate无validator/default均命中。
- rejected边界scan：固定endpoint初始安全检查、diagnostic flag删除、coverage `>=80%`、不恢复64 KiB、Issue #178/统一authorization/R03非目标均保留。

### 4.2 Current diff / whitespace / status

- `git diff --check`：exit `0`，无输出。
- `git diff --no-index --check /dev/null <plan>`：exit `1`是新增文件存在内容diff的预期结果；whitespace输出为空。
- `git diff --no-index --check /dev/null <fix-artifact>`：exit `1`是新增文件存在内容diff的预期结果；whitespace输出为空。
- turn-entry status基线：既有tracked修改`docs/host/issues-implementation-control.md`；既有untracked plan、plan-entry adjudication、plan-review controller adjudication与MiMo/DS reviews。
- final `git diff --name-only`仍只列既有tracked `docs/host/issues-implementation-control.md`；final `git status --short`相对turn-entry只新增本文，目标plan为本轮另一项authored change。未出现产品、测试、README、control或既有review/controller artifact新路径。
- 未运行pytest/pyright：本轮严格为plan与fix artifact文字修改，用户指定验证集为diff/scan/status，且禁止进入implementation。

## 5. Handoff

本轮到此停止，等待controller validation；不自行进入双路re-review、不implementation、不commit、不更新control、不进入R03。
