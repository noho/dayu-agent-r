# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 plan drift fix（Codex）

## 1. Gate、状态与边界

- **work unit**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **sub-WU / slice**：既有 `R02 / R02-S2`；不是新 WU、feature或implementation follow-up。
- **gate**：narrow plan-drift fix。
- **finding**：`R02-S2-DR-01=accepted / plan-fix-required`。
- **Controller validation follow-up**：旧§9.6/§14.3把全文件`**kwargs`纳入零命中，误伤两处既有合法browser Protocol；本轮只修正该假blocker并补齐精确签名/docstring gate，不改变finding scope或产品语义。
- **状态**：`AUTHORED — WAITING CONTROLLER VALIDATION`。
- **写入文件**：
  - `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`；
  - 本 artifact。
- **只读且保持原样**：当前未提交S2 implementation diff、产品代码、测试、README、control、S2 implementation stop artifact、Controller adjudication及全部既有review artifact。
- **禁止动作**：未commit、未push、未启动re-review、未恢复implementation、未进入S3/R03。

## 2. 第一性原理判断、直接证据与 owner

问题真实且是material plan drift，不是新产品需求。当前未提交S2实现已把
`_request_with_safe_redirects(..., transport_policy=...)` 收紧为无default必填named contract；
`utils/diagnose_web_access.py:_build_requests_profile` 仍以旧签名调用，direct fake也仍按旧签名定义。
因此三个deterministic raw diagnostic cases在artifact生成前稳定缺参失败；该失败与网络、Playwright、预算或环境无关。

直接source evidence：

- `dayu/tools/web/provider.py:96`：既有`_parse_config`是raw provider config到`WebToolsConfig`的唯一parser owner；当前typed snapshot在同文件构造`WebHttpTransportPolicy`。
- `dayu/tools/web/web_fetch_orchestrator.py:800`起：当前未提交实现已要求mandatory typed transport policy。
- `utils/diagnose_web_access.py:1461`与`:1499`：raw requests profile是遗漏的direct caller，调用未传`transport_policy`。
- `tests/tools/web/test_diagnose_web_access.py:730`起：对应exact fake仍缺mandatory parameter。
- `utils/diagnose_web_access.py:689`与`:718`：既有`_BrowserTypeProtocol.launch(**kwargs)`和`_BrowserProtocol.new_context(**kwargs)`精确镜像Playwright browser API，均已有完整中文`Args/Returns/Raises`；它们不是raw requests transport direct-caller seam。
- `docs/host/issues-implementation-control.md:158`与`:174`：当前gate与next entry point均明确为同一R02-S2 narrow plan-drift fix，现有implementation diff必须保留。

语义owner不变：provider `_parse_config`产生typed `WebToolsConfig.transport_policy`；diagnostic utility只消费并传播该snapshot；orchestrator/sender执行attempt transport。utility不是bool default、raw parser、environment selection或transport constructor owner。

## 3. `R02-S2-DR-01` 闭合矩阵

| Controller要求 | plan写回 | 状态 |
|---|---|---|
| 前移`utils/diagnose_web_access.py` | §4.3、§6.1/6.3/6.6、§9.4明确只迁移raw requests direct caller的mandatory typed transport传播 | 已闭合 |
| 前移direct test | §6.2/6.3/6.6、§9.4/9.5明确只同步exact fake/signature并新增或收紧owner assertion | 已闭合 |
| transport复用既有provider parser owner | §4.3、§9.4冻结`_provider_config -> provider._parse_config -> WebToolsConfig.transport_policy -> _build_requests_profile -> orchestrator` | 已闭合 |
| 禁止第二default/parser/environment inference/compat shim | §4.3、§9.4/9.6、§14.3、§15.3与completion明确禁止constructor、raw field parsing、environment inference、default/wrapper/`getattr`/test shim | 已闭合 |
| 消除`**kwargs`全局scan假blocker | §9.6/§14.3的零命中scan只检查utility transport constructor/raw bool/environment/`getattr`；两处既有browser Protocol `**kwargs`单独精确命中并归属为非transport seam | 已闭合 |
| 精确证明mandatory caller/fake签名 | §9.6增加target-specific AST audit，要求`_build_requests_profile`与`fake_request_with_safe_redirects`各自只有无default typed keyword-only `transport_policy`且没有loose kwargs | 已闭合 |
| 完整中文docstring gate | §9.6/§9.7与completion要求对全部added/signature-touched production+test definitions逐qualified name审计；function/method/nested helper完整`Args/Returns/Raises`，class/Protocol/TypedDict完整职责/fields/call contract，一行摘要不得通过 | 已闭合 |
| diagnostic direct-node与整份test | §9.5/9.6、§14.4、completion item 8精确加入direct node和完整`test_diagnose_web_access.py` | 已闭合 |
| deterministic local smoke exit 0 | §13将S2 closure与S3最终矩阵分开；S2要求现有脚本零diff、三个先前`artifact_missing` case产出artifact、local零skip/failure、exit 0 | 已闭合 |
| utils免coverage但行为闭环不可省略 | §9.6、§14.1/14.4和completion保留所有changed production文件`>=80%`，并强制direct/full diagnostic tests与真实smoke | 已闭合 |
| 保留现有S2 diff与恢复时序 | §0、§3、§6.6、§9.7、§15.1/15.2/15.4、§17明确只在Controller validation与双路完整re-review裁决后恢复同一个S2 implementation | 已闭合 |

## 4. Exact plan diff

仅修改plan，具体section disposition如下：

- **§0、§1.1/§1.6、§3.1/§3.2、§17**：把当前事实更新为S1已由`c7b01d82`接受、S2因`R02-S2-DR-01`停止、当前只做plan fix并等待Controller validation；不重开S1或产品裁决。
- **§4.3**：增加diagnostic raw requests direct caller；transport只来自既有provider parser owner的typed snapshot；禁止utility第二default/raw parser/environment inference/constructor/wrapper/`getattr`/loose signature。
- **§6.1-§6.3、§6.6**：只把`utils/diagnose_web_access.py`和`tests/tools/web/test_diagnose_web_access.py`前移到S2；明确smoke/batch脚本S2零diff，并保留所有S3语义。
- **§9.4-§9.7**：冻结utility与exact fake的最小传播、非默认typed owner assertion、provider focused/full与diagnostic direct/full tests；把错误的global `**kwargs`零命中改成transport-specific零命中、合法protocol归属与target-specific AST签名证明；新增added/signature-touched production+test逐定义中文docstring gate。
- **§13**：区分S2现有脚本零diff smoke closure与S3最终fixture/lifecycle矩阵；S2不能把三个`artifact_missing`归为环境失败。
- **§14**：增加S2 utility exemption对应的mandatory behavior evidence、三份Controller allowlist共同扫描、typed propagation与第二owner零残留source checks；明确两处browser Protocol variadic签名不是transport seam并在completion重跑精确签名/docstring audit。
- **§15与completion**：加入S2 drift artifact/state machine/stop conditions；completion必须记录`R02-S2-DR-01`、两个文件的exact S2 diff、direct/full diagnostics、smoke、pyright/coverage/source/README、target-specific signature和逐定义中文docstring evidence及现有diff保持。

没有修改accepted五bool、三budget、proxy/peer/browser产品终态、S3或deferred scope。

## 5. 明确保留与未前移范围

S2不得提前或改变：

- storage-state lifecycle、CLI、TTL、owner filename、publish、reconcile；
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS`、`--max-network default=80`、`DiagnosticResourceBudget`同源；
- diagnostic ordinary writer、profile schema、challenge detector、browser storage input、containment；
- `utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根README；
- Issue 178、R03、proxy credential schema、统一authorization或public permission/config framework。

这些语义仍由原S3/deferred owner负责；本fix没有引入兼容default、wrapper/facade、raw parser或speculative abstraction。

## 6. Source checks、diff checks 与验证

执行并核对：

- `rg` source定位确认唯一遗漏caller、exact fake、provider parser owner与current control gate，结果见§2。
- 关键一致性scan确认plan在§4.3、§6、§9、§13-15、completion与§17均包含`R02-S2-DR-01`、typed parser-owner传播、diagnostic direct/full test、smoke closure和明确S3非目标。
- plan exact stat：`1 file changed, 162 insertions(+), 52 deletions(-)`；只修改上节列出的plan sections，新增行包含本次Controller follow-up要求的inline target-specific audit与逐定义docstring gate。
- `git diff --check`：exit 0，无输出，覆盖全部tracked current diff。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-fix-codex.md`：exit 1（存在预期新增文件差异），无whitespace输出。
- 最终`git status --short`确认本gate只新增plan diff与本artifact；其它status均为进入本gate前的既有diff。
- 收窄后的utility transport零命中scan：exit 1、无输出，证明当前文件没有transport constructor、raw bool字段、environment读取或`getattr`；这里的exit 1表示无匹配，是预期结果。
- 合法protocol归属scan：exit 0，精确命中`689: _BrowserTypeProtocol.launch(**kwargs)`与`718: _BrowserProtocol.new_context(**kwargs)`两处；全文件`**kwargs` scan也只有这两处，因此旧命令的假blocker已由直接证据确认并移除。
- §9.6 inline AST audit与added/signature-touched docstring audit是恢复implementation后的hard gate；当前实现仍缺mandatory transport传播，故本plan-fix gate不执行并不把未通过状态误报为完成。

进入本gate前后，以下只读dirty/untracked文件的`git hash-object`逐项相同：

| path | hash |
|---|---|
| `dayu/config/README.md` | `a697642fe0bce1b7ff5e629502301458086257a8` |
| `dayu/tools/web/web_fetch_orchestrator.py` | `1019224a7f7b1a9130b14cd3d950e8c1766fcccf` |
| `dayu/tools/web/web_http_session.py` | `5917a298aa9b2c1cddae53780e9a818f892ea9f1` |
| `dayu/tools/web/web_playwright_backend.py` | `784bda8ab44e357a50228bb6816121a404d91c9d` |
| `dayu/tools/web/web_search_providers.py` | `fd278f527d8b7065dedb5cac65decd6b91b87d00` |
| `dayu/tools/web/web_tools.py` | `080b0baf31e158c655fe4c6da0f06ce863073a54` |
| `docs/host/issues-implementation-control.md` | `6c354da34b1b93dd3365513174737ad8b370f4fe` |
| `tests/README.md` | `f2630a1e449724c8f57b2f8b32afddab0d141056` |
| `tests/tools/web/test_web_tools_provider.py` | `dbd39decd2223ff0341cedfabb71f08cdc39de3c` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md` | `68ccf425902089032b746a8c649bdc5f07698d46` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-plan-drift-controller-adjudication.md` | `226b3f1587614185daa865ee01ddef75ddc66f67` |

这组hash证明现有implementation diff、control、README、tests与既有S2 artifacts内容未被本gate改写。

按narrow plan-fix gate约束未运行implementation pytest、coverage、pyright或smoke；S2 stop artifact中的旧结果只作直接证据，不能冒充本plan fix或恢复后的implementation validation。

## 7. Residual risks、completion 与 handoff

- 当前唯一release blocker仍是同一个S2 mandatory transport传播缺口；它已在plan中有明确owner、文件、tests、smoke与stop rule，等待后续恢复implementation实际闭合。
- 没有新增ownerless residual、产品问题或用户决策项。
- 本artifact不接受plan、不授权implementation，也不改变control gate。

Handoff：停止并等待Controller validation。不得自行启动AgentMiMo/AgentDS re-review、commit、push、control update、implementation、S3或R03。
