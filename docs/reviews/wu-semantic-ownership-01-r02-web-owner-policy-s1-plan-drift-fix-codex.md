# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 plan drift finding fix — Codex

## 1. 身份、范围与唯一裁决真源

- umbrella：既有`WU-SEMANTIC-OWNERSHIP-01`；内部 remediation sub-WU：既有`R02`。本轮只修订R02 accepted plan的S1 drift，不是新WU、feature、issue或implementation。
- 历史accepted-plan commit：`6e2a76b3`；它保留为历史证据，但已被S1 direct-consumer drift裁决supersede，不再是可执行S1 truth。
- 唯一修改目标：`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`。
- 唯一新增artifact：本文。control、产品、测试、README、design与既有plan/review/adjudication/fix/rereview artifacts均未修改。
- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-controller-adjudication.md`是`R02-S1-DR-01..04`唯一disposition真源；drift evidence、原plan review链与历史accepted plan不能覆盖它。
- 生成时间：`2026-07-14 22:17:40 +0800`（本机系统时钟）。

## 2. 第一性原理与root cause

动机成立且严重性判断准确。S1同时要求删除`WebResourceBudget`、旧符号零残留、无dual schema/facade和完整pyright，但历史S1 changed-file table遗漏四个直接import/annotation/constructor consumer。由于`pyrightconfig.json`覆盖`dayu/tests/utils`，把两个production consumer留到S2、把utility/test consumer留到S3会在S1立即破坏import、test collection或type-check；不能靠alias、compatibility default、test exclusion或后续slice补救。

正确修复不是扩大R02，也不是提前实现S2/S3，而是把四文件的最小budget-type propagation移入S1，并同步其owner map、测试、coverage、source scan、completion与gate state machine。Controller已确认四文件原本都在R02总闭集内。

## 3. `R02-S1-DR-01..04`逐项写回

### `R02-S1-DR-01` — 四文件S1 allowlist/propagation漏项 — closed-in-plan

Plan §0、§1.5、§3、§6.1-6.5、§8.1-8.4、§14、§15/§17已统一写明以下四个精确S1 type-only consumer：

| 文件 | S1唯一授权 |
|---|---|
| `dayu/tools/web/web_fetch_orchestrator.py` | HTTP body helpers改接`HttpResourceBudget`；warmup改接`BrowserResourceBudget`；删除probe无语义budget参数；只同步import/annotation/name/docstring/forwarding |
| `dayu/tools/web/web_playwright_backend.py` | DOM/text/markdown/worker改接`BrowserResourceBudget`；process/failure projection显式接`DiagnosticResourceBudget`；拆开worker kwargs与process diagnostic input |
| `utils/diagnose_web_access.py` | 只拆旧budget import/constant/calls为HTTP与Browser child owner，并复用owner typed defaults；不改S1 CLI/lifecycle/writer/profile/browser availability |
| `tests/tools/web/test_diagnose_web_access.py` | 只迁移旧import和`test_playwright_response_body_projection_uses_exact_bytes_and_budget`的显式HTTP budget输入；其它S3 tests不动 |

§6.3的S1/S2/S3 changed-file table、§8逐文件步骤、§14 coverage/source scan、§15 completion与§17完成信号均已同步，不再只补一句allowlist。

### `R02-S1-DR-02` — child type、参数与worker/process payload owner map — closed-in-plan

Plan §4.2、§8.2-8.3、§9.4、§15.4已冻结：

- `WebResourceBudgets` aggregate只停留在`WebToolsConfig` immutable snapshot，由`web_tools.py`作为唯一projection point拆分；下游不接aggregate、不重读raw config。
- HTTP wire/decoded materialization、search provider body、diagnostic Playwright response body只接`HttpResourceBudget`。
- warmup、browser DOM/text/markdown与browser worker callable只接`BrowserResourceBudget`。
- browser process/failure diagnostic projection只接`DiagnosticResourceBudget`或其显式owner field。
- `_probe_content_type`删除budget参数；不能为接口对称保留无语义输入。
- worker callable kwargs只含Browser budget；process wrapper独立持有Diagnostic budget并精确构造worker kwargs。不得用extra payload、`**kwargs`、loose fake或compatibility default掩盖签名。

### `R02-S1-DR-03` — utility defaults时序 — narrowed-accepted/closed-in-plan

Plan §4.2/§4.4、§5、§6、§8、§10、§12、§14、§15/§17已统一写明：

- `web_resource_budget.py`暴露`DEFAULT_HTTP_RESOURCE_BUDGET`、`DEFAULT_BROWSER_RESOURCE_BUDGET`、`DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET`三个唯一typed owner constants；aggregate无default。
- S1 utility HTTP/Browser defaults必须直接复用前两个owner constants；禁止本地数值、`HttpResourceBudget()`/`BrowserResourceBudget()`隐式constructor default或第二套source。
- utility-local`_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`与`--max-network default=80`在S1保持原行为，只登记为S1→S3临时状态，不得扩散或描述为最终contract。
- S3删除上述两个本地diagnostic defaults；utility/profile默认分别同源到`DiagnosticResourceBudget.error_chars/events`。`--max-network`仅保留显式单次override，未提供态不再承载业务default；同步CLI/profile/tests/README。
- S3仍不修改credential lifecycle以外的ordinary writer contract。

### `R02-S1-DR-04` — tests/validation漏项 — closed-in-plan

Plan §6.2-6.5、§7、§8.3-8.4、§14、§15.4、§17已统一写明：

- S1 targeted/full matrix加入`test_playwright_response_body_projection_uses_exact_bytes_and_budget` direct node，不提前改写整份S3 lifecycle suite。
- S1旧类型source scan覆盖`dayu tests utils`并要求`WebResourceBudget`零残留；不得skip/exclude utility/test。
- S1 coverage候选加入实际有diff的`web_fetch_orchestrator.py`与`web_playwright_backend.py`，逐changed production file`>=80%`。
- `utils/**`继续按AGENTS.md免coverage，但S1 direct behavior node不可省略。
- 完整pyright继续覆盖`dayu/tests/utils`，completion必须记录无skip/exclude结果。

## 4. 保持不变的行为与scope边界

Plan §6.5、§8.2-8.3、§9.4、§15.3、§17已明确S1只做type propagation，并冻结以下现有行为：

- `_send_authorized_request`签名、numeric pin与no-proxy行为不变；transport policy threading留在S2。
- `web_search_providers.py`三个模块级raw `requests.get/post`、endpoint、redirect、credential、fallback、challenge与result semantics不变；sender迁移留在S2。
- browser/private coupling、`browser_enabled` gate、`browser_peer_proof_unavailable`、proxy env、Playwright import/process start、route/navigation与error reasons不变；全部行为改造留在S2。
- diagnostic utility lifecycle、CLI、ordinary writer、profile schema、browser availability与`1_024/default=80`行为在S1不变；credential cleanup和typed diagnostic default替换留在S3。
- 不实施或预埋Issue #178、R03、统一authorization framework、其它deferred Issue；不创建旧类型alias/re-export/facade、flattened property、dual schema或兼容test shim。

## 5. 只读验证与handoff

### 5.1 执行记录

| check | command / result |
|---|---|
| plan whitespace | `git diff --check -- docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`：exit `0`、无输出 |
| fix artifact whitespace | `git diff --no-index --check /dev/null <本artifact>`：exit `1`仅表示新增文件与`/dev/null`有内容差异；whitespace输出为空 |
| DR IDs | 对plan与本文扫描`R02-S1-DR-01..04`：四项均命中；plan §6.5、§17与本文逐项闭合表一致 |
| 四文件S1闭集 | 扫描S1 changed-file行与§8逐文件步骤：`web_fetch_orchestrator.py`、`web_playwright_backend.py`、`utils/diagnose_web_access.py`、`tests/tools/web/test_diagnose_web_access.py`四项同处S1且均有type-only边界；无第五个drift文件 |
| owner/payload map | `WebToolsConfig` aggregate-only projection、HTTP/Browser/Diagnostic child map、probe无budget、Browser worker kwargs与独立Diagnostic process input均命中 |
| defaults时序 | 三个owner typed constants、S1 utility HTTP/Browser复用、S1保留`1_024/default=80`、S3由`DiagnosticResourceBudget.error_chars/events`删除/同源均命中 |
| validation闭集 | diagnostic direct node、`dayu tests utils`旧类型scan、两个新增production coverage候选、utils exemption/direct test与完整pyright均命中 |
| S1非行为不变量 | sender pinned/no-proxy、search raw requests、browser/private coupling、diagnostic lifecycle/CLI/writer/profile保持及no Issue178/R03/统一authorization均命中 |
| stale gate / rereview | 旧`PLAN REVIEW FINDING FIX AUTHORED — WAITING CONTROLLER`状态在plan中零命中（`rg -q` exit `1`）；预定义的drift rereview artifacts均不存在，未自行启动rereview |
| authored paths / status | turn-entry既有`docs/host/issues-implementation-control.md` tracked diff与两份drift evidence/controller untracked artifacts保持；本轮只新增plan tracked diff与本文。final status无产品、测试、README、design或既有artifact新diff |

不运行pytest/coverage/pyright：本轮没有implementation，旧代码baseline不能验证修订后的S1终态；这些命令已作为未来S1 gate精确写入plan。

### 5.2 Handoff

本轮完成后停止等待controller validation。AgentCodex不自行启动MiMo/DS drift re-review，不commit、不更新control、不修改产品/测试/README、不进入S1/S2/S3、Issue #178或R03。
