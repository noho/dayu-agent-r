RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-46dee354

# PR197-R1/F3：异常 contract 文字 fix 候选

## 身份、授权与交付状态

- label：`pr197-f3-planexception-sol-20261001-01`。runtime为Codex，provider为用户指定任务路由gpt-6-sol；没有本轮可核验的canonical精确model证据，记unknown。canary从本轮指定文件读取，18字节、无尾部换行；不从canary或旧artifact推断model，不另起业务审批。
- 唯一workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`。依 `/Users/leo/.codex/skills/gateflow/SKILL.md` 记录fix artifact，用户本轮已明确目标／边界／停止条件，完成即停止，不沿技能自动推进下一gate。
- 当前gate：plan amendment fix候选；F3-PR3-A1为根accepted低。本轮作者状态为**已修复（文字候选，待根核收与同版窄re-review）**，不回写根最终finding状态、不宣布gate accepted。C01/C02产品源码仍accepted／未修复，implementation blocked。
- 唯一修改 `docs/gateflow/pr-197-r1-f3-plan-20260930.md`；唯一新增本报告。验证日志仅写 `workspace/tmp/pr197-f3-planexception-sol-20261001-01/`，freeze/originals不写。其余源码、tests、README、goal、旧reports、rootcontroller、queue、handoff与其它WU只读；未stage/commit/push/PR/merge/comment/newbranch/worktree、未派发Agent。
- 本任务为技术文字修复，用户现成upload/download裁决优先；不重裁businesschoice、不新增目标／验收／S2／类型门禁／异常类／运行策略。F4共享主树只读review与F5已退出proposal/Q1待用户不构成本任务依赖；并发dirty不纳入本Agent修改或暂存。

## 权威、动机与直接证据

完整读取AGENTS、binding goal、740行当前plan（C01/C02/PA01与原A1～A4）、异常裁决38行及最后“双路合并裁决”；读取031804/031805的必要finding、非阻塞问题、风险和验证限制；完整读取五utils actualcaller（analysis_sample_inputs、schema、digest、verify、A/B），另只读核普通臂producer相关来源。长输出的展示截断后以分段读取恢复，未将截断当完整可见证据。

动机成立且严重性低：同一公共分组函数docstring同时承诺OSError向caller传播与具名ValueError原因链，判据段及C2-N5已选后者。这是code-generation-ready文字的互斥读法，属于共享输入分组预检owner；没有产品源码新缺陷裁决。最小路径是在该docstring消除互斥承诺，公共alias接口继续按原文向直接caller传播OSError。两项非阻塞澄清只明确委托和真实来源，不新增技术规则。

- binding goal SHA：`fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935`。
- 原plan SHA：`38d115621fc81ebeba7d06af88331ed2439ef076670897b93e171b5a297a1bed`。
- 新plan SHA：`05729875b12bcf78a7518ed462b93cd582c056fb849321e38fed11e7fc09f126`。
- 最终合并裁决 SHA：`001a2e1f35d3c7fd428087c858ab9b927968869e155b855426008b837192c356`。

## 三类文字hunk与逐项最小性

原件exactdiff：`workspace/tmp/pr197-f3-planexception-sol-20261001-01/plan-exact.stdout`（u0，真实exit1，stderr0字节）。5个授权替换块形成7个实际hunk：头部3个，技术文字4个；不把替换块数量冒称diff hunk数量。

| 原件→候选行 | 允许类别 | 精确变化及保留 |
| --- | --- | --- |
| 3–4、6、8–15 | 本轮头部元信息（3 hunk） | 更新本轮身份/canary/label、27items冻结、起点HEAD、唯一写入与最终合并裁决入口；记录候选与blocked，不放行 |
| 135→135 | 非阻塞公共委托（1 hunk） | 仅把私有stat符号引用改为公共analysis_targets_alias内部保证；digest不import私有helper、不复制判据。仅FileNotFoundError缺失、OSError失败和全部C01既定行为原文保持 |
| 182→182、185→185 | 非阻塞来源位置（2 hunk） | 只校schema/A-B表第一列行号；两行owner内容、证据叙述与分组字段逐字保持 |
| 227–228→227 | F3-PR3-A1异常contract（1 hunk） | 删除分组raises OSError承诺；ValueError明列检查失败、相关记录/PDF/目标及OSError或ValueError原因链。底层alias docstring与两个公共签名逐字／AST保持 |

来源当前冻结源码逐点核对：schema写址127，todo判存215–219，ProcessPool/worker区块224–238，所选回读243–244，固定summary281；A/B precheck r/v拼址110，报告路径推导123–124，真实read_text/JSON读取126–127，固定报告写址/写出161–163。plan记A/B连续123–127，包含构造与实际读取，未把123–124说成read_text。普通臂producer94–95及142–144原引用保留；digest425/435/444/454与verify114–123/129–133/194–201未改。

授权替换正向重建候选、逆向还原原件均严格相等，证明**完整artifact除5个授权替换块外逐字保持**，不是只检索锚点。参数／返回值／raises docstring在围栏内静态解析，未执行未实施API，未创建Any/cast/ignore/stub类型替身。公共alias的完整AST保持；分组参数及返回类型AST保持，raises唯一为ValueError，与原判据/C2-N5一致。

以下保护段直接逐字比较，无需撤回授权文字：

| 保护段 | 字符数 | SHA-256（原件=候选） |
| --- | --- | --- |
| ### 结果类型落地范围 | 7894 | `a20b85fd9908da2f6d9b1ae90ee57eb44449426717b0790ff8bb5caaf07ef19a` |
| 本轮A1/C02只计划授权不改变上述PA01义务： | 125 | `1e26b24e03d36661d07577ac1fad838f0623c729c7ad56ee346f78b77106f606` |
| ### C02 必须新增的临时验收矩阵与最小替代 | 2286 | `732097e4a1d541ba533a50b5d5dceae402e3bf19a93f675e85ace70f5ef696aa` |
| ## 验收命令与预期断言 | 4458 | `6905e61fb8c7b7e7cab8fb22df1d05d7eeda1cc1842dbe5922991255d07c2846` |
| ## 风险、分类与停止条件 | 2218 | `2ebd117a706608cfc35c47cd6c8a753bd7997df82b2d56a7848c80e0ad3813bd` |
| ## 目标、动机、成功信号与非目标 | 7189 | `37a8812e7cda631b666a9ec0b2ac68cf46618cccc82aafe750d6b2c0ba8e7545` |
| ## Owner 与共享 helper | 5603 | `b145cf894b8360c7361086810848e9d6a221f69683b7b84b3e9254bd6d9fd677` |
| ### 数据流与状态 | 1080 | `7ff148d10ee44b4c047e41833f0e0ef7cdb6c1617b43081913ebd221135b6984` |
| ### 必须运行的临时非空验收（C01 增量矩阵） | 3830 | `71172242b5dca497ccbff5bf58a9ae839a211c02d39ff90a6207696a977b5c55` |
| ### 确定判据、错误与完整 caller 顺序 | 2659 | `af6ed908f871f3a67f880865e41dae47f0ac9d0cd7cffd846309acae6f50aa02` |

原A1最大类型块、A2 selected-only、A3 id/kind、A4数字纯搬迁、默认2/4/2、cache exists-skip、worker Path/module entry、布局/字段/算法/全部原验收/残余目的地均由整件可逆比较保持。C01判据3的resolved basename/parent、限定ASCII名族、C02元数据在早返回前查、不同记录全跨role、自记录不强制双臂不同、complete预检时点、C01专属规则/C2完整矩阵均保持；新增句只澄清已裁异常contract及公共委托。

## 实际命令、退出与失败恢复

以下分别记录子命令真实退出，不把组合读取命令的最后exit0当作各子命令exit0。早期浏览输出仅证明实际读到内容；验证命令均由subprocess独立捕获stdout/stderr。

| 命令／检查 | 真实exit | 证据／恢复 |
| --- | --- | --- |
| 开始 `git branch --show-current`、`git rev-parse HEAD`、`git status --short` | 工具组合exit0；实际branch/HEAD见首尾记录 | 不另声称组合中每个子命令退出均独立捕获；后来branch/status/index由subprocess逐项核验 |
| `cat <本轮canary>` | 所在组合exit0；后续独立Python read_bytes/assert exit0 | 内容逐字匹配本轮18字节，无尾部换行 |
| 27items live+originals SHA独立inline脚本 | 0 | 开始27/27 live、27/27 originals匹配；冻结文件和整个originals文件库存入start-state.json |
| 编辑前冻结复核＋5个精确替换inline脚本 | 0 | 编辑仅plan及允许tmp日志；每个旧文本恰好出现一次，新SHA见上 |
| 首版静态验证inline脚本 | **1** | 误断言u0 hunk=5，实际7，AssertionError: 7；已通过的静态段与两个独立git子命令不因此冒称整脚本成功 |
| `cat <plan-exact.stdout>` | 0 | 实读确认头部拆3 hunk＋技术文字4 hunk，授权范围无漂移 |
| 恢复版静态验证inline脚本 | 0 | 正反严格整件比较、10保护段、公共签名/文档、10围栏行（5完整块）与实际7个hunk坐标验证通过；validation.json保留失败与恢复 |
| `git diff --no-index --unified=0 <original-plan> <plan>` | **1**（预期有差异） | stdout11708字节，stderr0；独立捕获plan-exact双流 |
| `git diff --no-index --check /dev/null <完整plan>` | **1**（新增文件差异） | stdout0、stderr0；完整artifact，无fence/context豁免；plan-noindexcheck双流 |
| 完整report noindexcheck与结束冻结／branch／HEAD／index | 收尾实值见下节 | 未以尚未运行命令冒称通过 |

本轮无source改动：按任务不重跑19/22设计probe、不跑全仓pytest／全量pyright基线、不作真实转换／download／private corpus／network／依赖升级。后续真实产品source的PA01义务**不豁免**：accepted amendment后激活venv，原完整harness＋C01/C02新增矩阵＋默认全量pyright exit0/0errors。仅文档静态检查不能作为产品通过证据。

## README 判定

只修改内部gate计划文字并新增fix artifact，未改源码/tests/安装/初始化/产品入口/参数/默认输出/日志定位/最终用户工作流/分层装配；未命中AGENTS的README触发条件，**不修改任何README**。保持plan原README职责判断与未来source docstring/help义务。

## 五类风险、owner与destination

| 风险／未覆盖 | Gateflow分类 | owner／destination |
| --- | --- | --- |
| F3-PR3-A1异常contract与两项精确性文字 | fixed in current slice（已修文字候选；未gate accepted） | 共享分组预检contract／plan owner；根核收→MiMo/授权backup同版仅已改句窄re-review→根裁决→accepted amendment commit |
| C01/C02真实源码accepted未修、完整harness/矩阵与默认全量pyright尚未运行 | covered by later approved slice（原F3-S1，须先accepted amendment） | digest固定汇总owner／各入口命名与共享身份owner；同一S1后续Sol源码fix及授权双路code review，不新增S2 |
| F4/F5/F6/F7与其它原WU | assigned to later work unit | 根总控及对应WU owner；原各WU队列，本任务不回写、不派发，F5/Q1待用户不作本任务依赖 |
| PR197首轮F3输入修复的原队列闭环 | tracked by existing issue | 根总控／既有issue #198及PR197修复队列；本轮仅交文字候选，不改issue/queue/PR状态 |
| 同记录双角色物理分离、尚不存在且父目录无法证同身份的别名／非ASCII等价、外部换链接／输入、跨运行同stem来源、失败缓存skip、schema统计quirk、历史公开locator／真实OCR质量性能／永久回归与历史parity重现 | requiring new issue or explicit user decision（原残余，不新增本轮目标） | 按plan原风险及A2目的地由用户/根总控与原缓存／统计／并发／consumer owner另定goal；本轮原风险段及消费者操作前提逐字保持，不建新issue/不重裁business |

无未分类风险；候选修文不等于finding经re-review最终已修或产品已修。原残余目的地以plan冻结保护段原文为准，本表不替换原风险裁决。

## 完整SHA表与read-only冻结首尾

freeze含27items：初检27live和27originals均匹配；收尾仅plan允许变化，26readonly与27originals必须保持。原freeze文件及originals全文件库存SHA另在start-state.json，结束复核见end-state.json；未修改freeze/originals。

| 冻结路径 | 原件／起点SHA-256 | 收尾规则 |
| --- | --- | --- |
| `utils/analysis_sample_inputs.py` | `021e777e263a87d8389741819f933d61bcca0e2f9762d49b116ed9f36580e296` | live/original保持原SHA |
| `utils/build_semantic_digests.py` | `4eab095a838d21fd63dbf7402b7dc872ccc43cf0aa761bccc7f5835c0aa98fd0` | live/original保持原SHA |
| `utils/docling_schema_regression.py` | `c6a16716acdcbaf879d2ea2b1276c3eb73f42c8557968e5732cd99e63e95d208` | live/original保持原SHA |
| `utils/verify_missing_tokens.py` | `2cf113b92fa7723c24e064eb8f8c8f8ed36743865bc7b7b17b92361f65e3a339` | live/original保持原SHA |
| `utils/ab_ocr_compare.py` | `b28ad6f4d6119609290d3cd7f1683fe8de74255a78ddb487ea5695269e98d175` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-20260930.md` | `38d115621fc81ebeba7d06af88331ed2439ef076670897b93e171b5a297a1bed` | live→`05729875b12bcf78a7518ed462b93cd582c056fb849321e38fed11e7fc09f126`；original保持 |
| `docs/gateflow/pr-197-r1-f3-goal-20260930.md` | `fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-implementation-20260930.md` | `41b2f50d57f30e333af3daceb2ad5ed51a84154deaae3d4eca20fea2f7475c1a` | live/original保持原SHA |
| `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-amendment-20260930.md` | `93b03af2cebb4b7b65d60e58a557cf75670b1b86c015ad818425ce2859c8f071` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-validation-fix-20261001.md` | `dc8b3b34ab8393694ba994897af94403f08b94aec09090350b5e28c13c7450a1` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-quality-receipt-20261001.md` | `9c841d143b153278ddf8a09f864ed56fa82ad281f4a8beeeadfa6c96ecf0d8e5` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-reserved-artifact-collision-20260930.md` | `45372ab7723c6e1dbbdc1da5d6db3555a8653de5fea75c2556c217013807688e` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-fix-20260930.md` | `806f11dc9f5f7a576fac33ade5a1da077abe267dc343792c21eae91208f9b850` | live/original保持原SHA |
| `docs/reviews/plan-review-20260930-215517.md` | `2675a6b2c4755b966c7d38f3e3f3d5adc47058d9b66387b74c9b3c0690218dd2` | live/original保持原SHA |
| `docs/reviews/plan-review-20260930-215618.md` | `2d612e272cfbaeaa866e475f619b3bfb4730829d808ff258bd0bcae94074368a` | live/original保持原SHA |
| `pyrightconfig.json` | `661d7c531f7cacc7038f570675b43052ed800cd87915a1a218504dbfe6d4357c` | live/original保持原SHA |
| `pyproject.toml` | `28429056b51e29c672f029723d3bbef0db0d781b6bc72d0cb8c2d3e823c79474` | live/original保持原SHA |
| `docs/reviews/plan-review-20261001-005120.md` | `4922a1d95d75783efeb1700773d41f62779712f1f86bf335f790bd4364fa0139` | live/original保持原SHA |
| `docs/reviews/plan-review-20261001-005207.md` | `c1736b57685fdac4dfbac15990b7ec0906f81d7e6dc2b631c3458aba6aef6ee5` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-amendment-review-adjudication-20261001.md` | `0c0d309fde9cfdbe0468fb06a481e419cae86ff8381691acdf6e4d54ff5042e6` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-collision-fix-20261001.md` | `aa0a04ca00173cff84e65687bf56b8baf54454c3db958405de9d3b69af638182` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-plan-collision-receipt-20261001.md` | `32b1870732662021b003e1b139f3eeb880b73bb0fe7de89975d7e3eca19fd739` | live/original保持原SHA |
| `utils/ab_ocr_convert.py` | `d7909e7747b3cb320e0861ef9d34b542a2c75c6a0934a015c66552c14531e548` | live/original保持原SHA |
| `docs/reviews/plan-review-20261001-031804.md` | `ff27926dbb9415c05aa8b026d68741244ee3d1c5c988321a777f9d2077ba765c` | live/original保持原SHA |
| `docs/reviews/plan-review-20261001-031805.md` | `5c94ab7b504e1dbafce761dfff905e25d2fd518291722b12068d9db49d459a90` | live/original保持原SHA |
| `docs/gateflow/pr-197-r1-f3-exception-contract-adjudication-20261001.md` | `001a2e1f35d3c7fd428087c858ab9b927968869e155b855426008b837192c356` | live/original保持原SHA |

## 收尾实值与停止

- branch：`codex/upload-material-oracle`（独立子命令exit0，未变）；暂存集合首尾为空（独立子命令exit0，本Agent未stage）。
- HEAD仅首尾记录：开始 `2cc2f5ed76e23086762c88095731165f7f815cee`；结束 `49d044f01d54c2d0ba590cf09bac3862e2c9c53e`（独立子命令exit0）。根checkpoint `gateflow: preserve F3 review and F5 proposal receipts` 仅归档11份docs；`git show --stat`及起尾`git diff --name-only`直接核实，无源码/本plan提交，已冻收据由untracked变tracked但live字节不变；26readonly/27originals冻结不解除。本Agent未stage/commit。
- 结束实算26/26 readonly、27/27 originals匹配，freeze及originals整个文件库存SHA保持；仅plan live变化为上列新SHA。证据 `workspace/tmp/pr197-f3-planexception-sol-20261001-01/end-state.json`。
- 本轮canary独立字节核验为18字节、无换行；报告草稿曾误写17，交付前按真实len修正，不作为旧令牌证据。
- 首轮收尾status相对进入快照新增本报告及并发 `docs/gateflow/pr-197-r1-f4-plan-narrow-adjudication-20261001.md`；后者不在冻结范围，只观察路径、不读取改写其内容、不stage，不归本Agent产物。后续根checkpoint归档既有dirty/收据的Git状态变化按授权记录，live冻结字节不变；其它dirty不纳入本Agent写入，plan以冻结原件exactdiff确定本轮增量。
- 收尾inline首版**exit1**：错误要求全树status只能新增本报告，被上述并发F4文档新增触发；该assert属于验证脚本scope错误，已删除对非冻结并发docs的错误不变约束并记录实值，未改技术内容或冻结。恢复版**exit0**。此前branch、26readonly、27originals与整个库存核验均通过，不把组合末0冒称首版成功。
- 最终验证inline首版**exit1**：错误要求HEAD等于起点，被上述允许docs checkpoint触发；独立诊断exit0核实branch/HEAD/index，`git show --stat`及起尾路径差异读取exit0核实仅docs归档。恢复版只记录首尾HEAD、严格复核branch/26readonly/27originals及空index，不要求已授权checkpoint的HEAD不变；该失败不改写为成功。
- 报告元信息修订inline首版**exit1**：误以旧收尾HEAD行仍写2cc，精确旧串assert不匹配（该行已记录49但“首尾相同”评语未同步），无文档写入；读取实际报告尾段exit0后按唯一行前缀修正元信息，恢复版exit0。
- Agent实际写入仅两指定文档与task tmp日志；未stage/commit、未派发review或推进gate。
- 完整plan与完整report各自 `git diff --no-index --check /dev/null <artifact>` 实际**exit1且stdout0/stderr0字节**；各自独立捕获，未过滤fence/context。report写入本实值后再次整件复核，最终日志为 `plan-noindexcheck.stdout/.stderr`、`report-noindexcheck.stdout/.stderr` 与 `final-verification.json`；整件UTF-8、无CR/NUL、末尾换行通过，plan5个围栏块全部闭合。

交付下一入口由根核收后进入**re-review**：MiMo/授权backup同版仅已改句窄双审，根裁决／必要fix/re-review，accepted amendment commit后才恢复产品sourcefix。本Agent完成唯一plan文字与唯一fixreport后停止；未派Agent、未推进下一gate。
