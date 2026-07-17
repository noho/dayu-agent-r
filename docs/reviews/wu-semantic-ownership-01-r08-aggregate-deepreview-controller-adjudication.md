# WU-SEMANTIC-OWNERSHIP-01 / R08 aggregate deepreview Controller adjudication

## 1. 结论

`PASS / ZERO_ACCEPTED_AGGREGATE_FINDING / ALL_R08_FINDINGS_CLOSED / READY_FOR_EXACT_SCOPE_ACCEPTED_IMPLEMENTATION_COMMIT`。

本裁决只接受 R08 cumulative immutable tree；不关闭 umbrella `WU-SEMANTIC-OWNERSHIP-01`，不授权 R09-R12 implementation，不实施 Issue 142/151/175/177/178、统一 tool authorization framework、push 或 PR。

Immutable target 与最终 review artifacts：

- `git diff --binary -- dayu/fins tests` SHA-256：`01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d`
- guards 单文件 SHA-256：`44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a`
- 23 tracked product/test/README paths；staged empty；`git diff --check` PASS
- AgentMiMo final artifact：`docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-mimo.md`，final evidence-normalized SHA-256 `2e50f2a31059dc81432b59923e802512ae36bae072e2c53f6932ad64f4902bfb`，verdict `PASS / ZERO_ACCEPTED_FINDING / ZERO_MATERIAL_DEFECT`
- AgentDS final artifact：`docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-ds.md`，final evidence-normalized SHA-256 `f34af1e1d54e2141c5200fee50a781728e7464c657f0e18e7becf339d9eb7e77`，verdict `PASS / 零 accepted candidate / 零 material finding`

Accepted-commit staged audit发现 prior DS cumulative code-rereview artifact 仅有三处 Markdown line-ending spaces。AgentDS删除这三处空格后，artifact SHA 变为 `d9e27c9f...3c064`；Controller code-rereview adjudication仅刷新该hash并记录 semantic content/verdict不变，新SHA为 `9fb0afe8...8f82e`。两路 aggregate reviewers均在同任务中核验并只刷新此lock，产生上述final hashes。产品/test/README binary diff始终保持 `01c2a1d5...092d`；这不是新review target、finding或产品mutation。

两路均审查完整 cumulative tree，并覆盖 S1+S2、code-review corrections、candidate exhaustion、prefix-six exact drift、pyright test-owner fix、accepted finding ledger、Topic 6 owner 时序、R07 no-regression、LLM-facing/README/tests、security/no-code/deferred/no-compat boundaries。Reviewer verdict 本身不授权 commit；本 artifact 是 Controller 的最终 finding 裁决。

## 2. 已接受 finding 最终闭包

| Finding | Final status | Direct evidence |
|---|---|---|
| `R08-CR-CF01` | `已修复` | shared guards test 四个 generic/compat nodes 与九 imports/symbols 零命中；shared hash `01db5538...6692` |
| `R08-CR-PCF02` | `已修复` | dead `_collect_available_document_types` definition/caller/import 全零；actual typed/sorted owner definition/caller 各一 |
| `R08-CR-PCF03` | `已修复` | candidate 6 public resolver test、唯一 import、material/other/CN-FY 三条精确断言保留 |
| `R08-CR-PCF04` | `已修复` | prefix-five `387/485`；prefix-six `391/485`；新增执行行 `[344,346,348,442]` |
| `R08-VAL-PY-F01` | `已修复` | optional public keys 先做 membership proof |
| `R08-VAL-PY-F02` | `已修复` | test processor constructor 对 protocol-valid calls 可调用 |
| `R08-VAL-PY-F03` | `已修复` | test-local XBRL success TypeGuard 只按必有 public field 收窄 |

此前 plan-review、plan-correction、code-review 与 validation findings 也全部保持 closed；两路 aggregate review 未发现 regression。

## 3. Reviewer artifact 证据纠正

### 3.1 AgentMiMo

MiMo 初稿有四项 artifact evidence drift：guards 单文件 lock 被误按全树组合 hash 计算、Controller artifact 只写 present 未核 SHA、R09 direct-stream validator 被误写为 R08 processor reason PASS、23-path 分类少算一个 tests/fins Python path。Controller 提供直接命令与 owner 时序后，MiMo 在同任务中修正：

- guards 与 Controller SHA 均实际 `MATCH`；伪 residual 删除；
- Topic 6 direct-stream validator 改为 `N/A / deferred to R09`；
- path 分类改为 15 Fins Python + Fins README + 6 tests/fins Python + tests README；
- 最终 verdict、finding ledger 与产品判断不变。

这些是 review artifact evidence corrections，不是产品 finding，不产生 fix gate。

### 3.2 AgentDS

DS 初稿曾把 R09/R10/R11 planned scope 写成 R08 已通过/残余，把 R07 opaque identity mapping 误写成 future work，并使用较早 stopped tree 的 `857/390` 计数。Controller 以当前 code、R07 accepted commits 与最终 immutable validation 提供直接证据后，DS 在同任务中修正：

- R06/R07 已交付 owner、R08 financial/XBRL、R09 direct stream、R10 HKEX、R11 upload 的时序分开记录；
- `_fs_identity.py` external identity → private locator + descriptor round-trip owner 与 exact opaque tests正确恢复；
- final evidence 改为 aggregate `392 passed`、full Fins `859 passed / 1 existing environment skip`、15/15 coverage；
- planned next sub-WUs、reviewer candidates 与 R08 actual residual 分栏；最终 verdict不变。

这些同样是 review artifact evidence corrections，不是产品 finding。

## 4. DS reviewer candidates 最终裁决

### 4.1 Semantic ownership / overcoupling candidates

| Candidate | Final decision | Reason |
|---|---|---|
| `O1` SEC fiscal fields fallback chain | `REJECT / NO R08 FIX` | R08 diff只删除 obsolete financial-payload helper并收窄 typed XBRL protocol；fiscal extraction chain仍在 SEC pre-publication pipeline owner。没有证据表明 storage published fact被consumer重猜或当前 R08 contract输出错误；改写会扩大到未裁决 ingestion product semantics。 |
| `O2` CN form-type mapping | `REJECT / ACCEPTED OWNER BEHAVIOR` | `resolve_document_type_for_source(form_type="FY", source_kind=filing) -> annual_report`正是 accepted candidate-6 exact owner test，且 material先走独立 branch；没有 collision反例。增加 speculative source-kind gate会推翻已接受 proof。 |
| `O3` `resolve_has_financial_data` compatibility chain | `REJECT / UNRELATED PRE-EXISTING CODE` | 当前 R08 accepted plan明确禁止新增/恢复该 compatibility evidence，且本 tree未修改该函数。用户同时禁止修改与 accepted findings无关既有代码；本轮不借 aggregate review扩大为未裁决 cleanup。 |
| `O4` material aliases | `REJECT / NO DEFECT EVIDENCE` | 只有“历史 typo”推断，没有错误投影、双真源或 consumer failure反例；当前 normalization owner未由R08修改。 |
| `O5` 两个 domain contract 的私有 validation helpers重复 | `REJECT / OWNER-LOCAL HELPERS` | 两个独立 domain owners各自拥有小型 exact-key/type validation；抽到共享模块会制造跨contract耦合，且无语义漂移或维护故障证据。 |

### 4.2 Adversarial candidates

| Candidate | Final decision | Reason |
|---|---|---|
| `A1` blank XBRL concepts回到default | `REJECT / NO MATERIAL FAILURE` | concepts是可选输入；owner normalization把全空白视为未显式提供并选择typed taxonomy/form default。Producer `query_params.concepts`仍由terminal validator保证非空；没有错误fact或静默partial证据。 |
| `A2` XBRL filters缺input pre-validation | `REJECT / NO NEW PRODUCT RULE` | callable/schema已校验JSON类型并拒绝bool；producer terminal exact-validates实际执行的flat query params。要求正财年、min/max关系或其它范围会新增未裁决product semantics；没有invalid completed result反例。 |
| `A3` period/document-type helper可接收非字符串Python元素 | `REJECT / TYPED/PUBLIC BOUNDARY HOLDS` | 函数签名是`list[str]`，真实tool JSON入口由`_optional_string_list`拒绝非字符串。候选只依赖越过typed/public boundary的非法Python调用，未形成LLM-facing path。 |
| `A4` CN mapping缺额外source-kind gate | `REJECT / SAME AS O2` | accepted candidate-6精确证明当前owner行为；无collision反例。 |
| `A5` `_to_optional_float` broad exception | `REJECT / UNRELATED PRE-EXISTING NORMALIZER` | 输入为有界JSON scalar，候选未提供被掩盖的业务异常或R08 regression；本tree未修改该helper。 |
| `A6` dedup sort fallback不可达 | `REJECT / DEFENSIVE NO-OP` | fallback不改变任一可达选择/排序结果，且没有错误输出；删除不提升semantic ownership。 |
| `A7` fiscal-period defensive `None` branch | `REJECT / TYPE NARROWING GUARD` | shared normalizer返回类型仍是optional；membership校验后分支是fail-closed类型收窄，不是兼容或业务fallback。 |
| `A8` `query_params.copy()`冗余 | `REJECT / PREVIOUSLY ADJUDICATED OWNERSHIP COPY` | validation input copy与public projection output copy属于不同ownership boundaries，保证raw/public不alias；此前 `F-04` 已以同一直接证据拒绝删除。 |
| `A9` internal quality mismatch消息不含expected/actual | `REJECT / NO PUBLIC CONTRACT` | 该消息表达producer invariant violation，不是业务reason或LLM-facing contract；当前tool failure边界保留有界通用错误，新增内部值没有用户动作价值。 |

Final aggregate ledger：`accepted 0 / rejected-with-reason 14 / deferred finding 0 / blocker 0`。R09/R10/R11是既定 planned sub-WUs，不是由本 review 新建的deferred findings。

## 5. Validation 与 temporal truth

最终 immutable tree 的 current evidence 为：

- guards `24 passed`；prefix-six `392 passed`，exact `391/485 = 80.61855670%`；
- focused contracts/read/consistency、public/forced-truncation/real smoke matrices通过；
- aggregate `392 passed`；full Fins `859 passed / 1 existing environment skip`；
- 15/15 changed production files exact-key line coverage `>=80.00%`；
- full pyright `0 errors`；21 changed Python Ruff `All checks passed`；
- §6.7 source/AST/LLM/README/security/no-touch scans 与 `git diff --check`通过。

较早 stopped tree 的 `390/857` 只作历史证据，不得覆盖上述 final-tree结果。

## 6. Security / no-code / deferred boundaries

- Topic 8：Engine generic exception 240字符硬编码、脱敏和截断后缀保持不变。
- Topic 9：未设计或实现统一 tool authorization framework、permission schema、policy DSL、role/capability或sandbox。
- Containment、symlink、R07 opaque identity mapping、typed provenance/citation、DNS/peer、resource budget、atomic publication、process fencing与Host truncation owner未删除或弱化。
- R09 direct-stream validator、R10 HKEX cumulative rowRange、R11 upload/placeholder、R12 init仍按既定顺序进入后续独立plan gates。
- Issues 142/151/175/177/178及Web/WeChat/render trackers未偷带。

## 7. Next gate

Controller 只可对本 artifact列明的 exact R08 implementation/evidence/control paths执行staged-scope audit、`git diff --cached --check`与一个accepted local implementation commit。不得在commit前修改reviewed product/test/README tree；任何树漂移都会使两路aggregate deepreview失效。真实commit SHA落盘后再进入R08 completion evidence/Controller validation；R09 plan在R08 completion accepted local commit之前不授权。
