RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6
CANARY=gpt-6-sol-5007bdac

# PR197-R1/F3：A1解析后basename与C02样本产物身份计划fix

## 身份、权威、范围与当前状态

- label：`pr197-f3-planfix2-sol-20261001-01`，仅为本轮引用标签，不作业务证据。runtime为Codex；provider为用户指定路由gpt-6-sol；系统可见基础型号GPT-6，精确部署变体未提供可核验信息。首条commentary“未知”指精确型号／部署标识；这里明确可见基础型号，不从canary或旧报告猜部署，不另起业务审批。
- 指定本轮canary文件 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.yi22SR/canary.txt` 已工具独立读取、exit0，内容逐字见首行（文件无尾部换行）。旧轮canary不作为本轮证明。
- 唯一workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；起点HEAD `2a8c5d3e3c14b26e2d1e28efb66448b567c21465`。终检branch／HEAD及暂存集合见本报告冻结节及 `closeout.json`；HEAD只记现场，不以允许的root/F4无关治理checkpoint制造阻碍。
- 用户已授权成立findings优先fix，本轮明确只plan。binding goal `docs/gateflow/pr-197-r1-f3-goal-20260930.md` 保持；原accepted plan `a88dcf8e84ba4371b9081714aa736e043b95fea4395d68a5cacf1250130bb172` 的S1输入增量已批准。当前plan起始SHA `7a53f5a3983d068e33e6140f79e0d079249e5b751e09a00df0e9e51586eef6da`，尚未accepted candidate。
- 根权威 `docs/gateflow/pr-197-r1-f3-amendment-review-adjudication-20261001.md` 已完整读到**最后排程校正**；两报告 `005120/005207`、C01末节、PA01fix及质量回执实读只读。A1／C02为accepted／未修，拒绝两review把C02自动延后新issue／重新业务审批的建议；也不复议上传下载行为。旧“未来F3-S2”已由根校正，当前gate不能借未approved slice放行。
- 使用 `gateflow` skill（`/Users/leo/.codex/skills/gateflow/SKILL.md`）：最小code-generation-ready计划、单一可验证输入增量、成立finding不以风险分类替代真修。用户明确本轮完成两文档后停止，优先于skill自动推进；本轮不派Agent、不提交、不实施。
- 唯一持久修改 `docs/gateflow/pr-197-r1-f3-plan-20260930.md`；唯一新增正式artifact为本文件 `docs/gateflow/pr-197-r1-f3-plan-collision-fix-20261001.md`。临时控制／设计探针及双流仅写 `workspace/tmp/pr197-f3-planfix2-sol-20261001-01/`；freeze／originals／旧轮probe保持，只读源码。无source/tests/README/goal/旧amendment/fix/review/rootcontroller/queue/handoff改动，无stage/commit/push/PR/merge/comment、新branch/worktree、子Agent、私人语料、真实转换／下载／网络／依赖升级。

作者状态：**已修复（A1/C02计划文字候选，待同版窄双审与根回写）**。plan gate尚未解除；C01/C02真实源码仍accepted／未修复，implementation blocked。本报告和设计探针不是产品已修、gatepass或slice完成证明。

## 动机、四真实命名owner与counterexample

动机成立，按根维持低严重性：开发分析脚本允许明确给出的两份样本静默共用一个产物，错归属／双计是真correctness缺口，而非生产上传下载规则问题。root cause同源：共享loader仅精确`set[str]` stem查重；各入口用resolved PDF stem拼接扁平JSON路径，缓存／汇总／报告没有证明记录间实际目标身份不同。

根独立证据 `workspace/tmp/pr197-controller-collection-20261001/f3-c02/result.json` 及`cli.stdout/cli.stderr`实读：loader接受两个目录alias/ALIAS；待生成0／CLI0，唯一20字节同inode摘要却total2／bytes40，字节不变。A1同证据记录原names比较false，resolved names比较true。

本轮另外自建合成root／manifest／合法基线及结果缓存，以真实loader和四个真实模块CLI走全缓存分支，不初始化converter、不跑进程池。所有材料由TemporaryDirectory放本task tmp并自行清理；完整CLI双流另保存。

| 实际命名owner／直接源码位置 | 真实路径及worker/cache/write | 本轮独立观测／设计边界 |
| --- | --- | --- |
| schema `utils/docling_schema_regression.py:127,221-237,247-248,281` | `<out>/results/<stem>.json`；ProcessPool `_process_one(pdf,baseline,out)`写；main判存／回读／写根下summary | alias/ALIAS结果samefile，真实CLI0／待处理0／total2。C02检查每记录result；不扩C01固定保留名 |
| digest `utils/build_semantic_digests.py:425,435,444,454` | `<out>/digests/<stem>.json`；ProcessPool `_build_one(pdf,baseline)`返回，main判存／写／统计／写_manifest | 真实CLI0／待生成0／total2，单摘要双计。C01单独保留固定汇总规则，C02查记录间digest |
| verify `utils/verify_missing_tokens.py:114-123,129-133,194-201` | 读digests/<stem>.json；ThreadPool `_verify_one(pdf,baseline,data_root)`判cache／缺失转换并写verify-cache/<stem>.json | 真实CLI0打印两条STEM，共用同cache及digest；C02同时查digest与cache，包括不同记录跨角色 |
| A/B `utils/ab_ocr_compare.py:103-104,123-124,162-163`；臂producer `utils/ab_ocr_convert.py:94-95,142-144` | compare读r/v/<stem>.json，写单份ab-summary.md，无worker；普通臂命名来自另一个producer | 真实CLI0生成first/second两个样本段，r同物理文件（v也同），是compare消费身份混用。C02查r/v并检查不同记录跨臂；不改producer或-noocr规则，不冒称已实跑臂并发写 |

四入口缓存CLI0均为**缺陷被证实**，不能算修后验收通过；未实跑cache-miss并发覆写。后者只由真实读写路径直接分析，竞争细节不冒称实测。A/B比较器不能保证外部producer历史内容来源真实性，仍需原同stem同输入／新out操作约束。

## 方案、最小替代及goal映射

A1只钉死C01第三判据：`resolved_target.name/resolved_summary.name`作ASCII小写比较，`resolved_target.parent/resolved_summary.parent`作文字／samefile判断，不用原basename或原parent。保留digest两Final、`_digest_path`与`_require_distinct_digest_targets`两本地helper，以及原保留名／resolve／resolved parent+ASCII name／现存samefile四判据、N1～N7／P1～P4。N5补原name不匹配而resolved name匹配的具名断言。

C02仍为**同一F3-S1必要correctness**。各入口最小本地实际路径helper把预检、缓存查址、写出／读取收归同规则；调用方把每条记录的真实Path组交既有输入模块。新增公共 `analysis_targets_alias(first: Path, second: Path) -> bool` 与 `require_distinct_sample_targets(samples: list[AnalysisSample], targets: list[tuple[Path, ...]]) -> None`，加私有 `_stat_if_present(path: Path) -> stat_result | None`；不向load_samples添out／producer名称，AnalysisSample三字段不变。分组等长且非空，单记录也查元数据／环，不同记录全部路径两两检查（含verify digest对另一cache、r对另一v）；不增加同记录双臂物理不同规则。

公共身份真源按resolve相等、**解析后父目录已确认同一时的ASCII解析后basename名族**、现存samefile判断；C01身份部分复用它，保留名和固定产物语义仍在digest私有owner。元数据stat只允许FileNotFoundError表示缺失，权限／NotADirectoryError／其它OSError失败；链接环具名ValueError。中文错误含双方1-based记录／PDF／实际目标；C01错误含记录／PDF／样本与固定目标。各main现有输入try／parser.error整体exit2，完整预检早于mkdir／缓存业务消费／worker／转换／write；坏后条不先执行好前条。

| 决策 | goal／success signal映射及最小替代判断 |
| --- | --- |
| resolved name／parent明确取值 | 原C01已声称覆盖dangling ALIAS/alias；是文字澄清，不是新命名规范 |
| 各实际Path＋共享身份预检 | 原显式正常输入驱动同一分析路径／保全扁平产物；只做唯一性，不改布局、算法、字段或转换默认 |
| 限定同解析父目录ASCII名族 | 只有samefile漏未创建目标；此窄规则在out不存在时可确定拒alias/ALIAS。case-sensitive卷也拒这一同父ASCII名族，是有限可移植性代价；不能伪称samefile实测 |
| Unicode／正常文件／合法cache或目录链接保全 | 不casefold/normalize/strip全stem；不同正常名、中文、相近前缀、无实际别名的_manifest/_manifeſt保持。禁止全链接禁令或FS探针文件 |
| 本地命名helper＋朴素Path分组 | 多消费者复用公共身份语义，sharedloader不猜out／固定名称；无需policy/callback/factory/Godbag或新产品架构 |
| 完整写前exit2及原harness＋新增矩阵 | 缺必需输入明确拒绝／现成产物保持。统计去重、下游重算、重命名、丢一条成功继续、串行覆盖、改fake都不能修同源root cause |

完整签名／位置／callsite顺序／中文docstring与异常规则／数据流／C2-N1～N5与C2-P1～P3均在新plan C02节。原A1类型block与落地表、A2selected-only/parity披露、A3id/kind owner及重复id边界、A4_number_counters纯搬迁、默认2/4/2、module entry、Path worker与原1～10项验收逐字保留。PA01原整段逐字保留，再补C02同样承担未来真实源码义务：source venv、原完整harness＋C01/C02新增矩阵、默认全量pyright exit0／0errors；780/504历史绿色不替代，utils永久tests/cov豁免不变。

## 实际validation、失败与恢复（不是产品验收）

所有Python／pyright探针先 `source .venv/bin/activate`；Python3.11.15，`pyright --version`与`python -m pyright --version`均1.1.409／各exit0，1.1.414可用版本通知仅原工具提示，未升级。临时严格配置 `design-pyright.json`：relative include=`identity_design.py/design_probe.py`，exclude=[]，typeCheckingMode=strict、仓库extraPaths／当前venv；实际filesAnalyzed=2，0 errors/warnings/informations。没有ignore／Any／cast／伪源码验收。它只验证本轮路径设计及探针，不是冻结产品代码通过。

| 本轮真实操作／子命令 | exit与结果 | 留存位置（相对本task tmp） |
| --- | --- | --- |
| canary独立cat、branch／HEAD／status、freeze初检 | 各0；指定branch／起点HEAD，21live+21originals匹配 | `sha-start.json`、`git-before-edit.json`；canary工具双流 |
| 首个17项设计矩阵＋四冻结CLI | 探针0；四CLI各0，仅证明缺陷；17项均拒绝／接受与零写入符合预期 | `design-result.json`及`frozen-<module>.stdout/.stderr` |
| 初始独立严格临时pyright | 0；filesAnalyzed2／0errors | 工具完整输出；配置已保存 |
| 扩大到19项时记录子进程，漏PYTHONPATH | **1**；ModuleNotFoundError: utils，在导入阶段未跑矩阵／CLI；不是产品失败 | `validation-commands.json`、`validation-4.stderr`；前三版本命令均0 |
| 恢复：明确PYTHONPATH=.，不加源码兼容import | 0；19项设计矩阵／四冻结CLI各0。两新增为A1确切resolved basename及非ASCII现存hardlink | `validation-recovery-commands.json`、`design-result-expanded19.json`、`frozen-expanded19-<module>.stdout/.stderr`；原17项结果不覆盖 |
| 恢复后的独立严格pyright与summary断言 | 各0；filesAnalyzed2，0errors/warnings/informations | `validation-recovery-2.stdout/.stderr` |
| 计划按冻结原件做精确修订及受保护文字比较 | 0；A1完整类型／落地、A2、A3owner、A4与1～10验收、README／历史段保全 | `edit_plan.py`及终检protected_contracts |
| 原plan→本轮最终plan独立git diff --no-index --unified=0 | **1**（预期差异），完整stdout保存，stderr空；21hunk／+134/-25行 | `plan-final-exact-v2.diff/.stderr`、`preclose-final-plan.json`；不把外层0写成diff0 |
| 两完整artifact各no-index --check | 各**1**、stdout/stderr均空；没有排除围栏 | `closeout.json`逐命令记录；plan对冻结原件，本artifact对/dev/null，另查plan全文件对/dev/null |
| 两完整artifact结构／围栏及JSON/Python语法检查 | 0；全文UTF-8／结尾换行／无CR/NUL／围栏闭合，Python围栏AST与JSON围栏解析、shell围栏token化；原契约逐字断言 | `closeout.json`，结构检查不代类型或产品验收 |
| tracked scoped git diff --check | 0／零双流；仅指定两个docs | `closeout.json` |
| 首次收尾脚本 | **1**；20只读SHA、21originals及两docs结构／no-index检查已通过，错误地assert HEAD仍等于起点，遇允许的F7推进而失败。该断言与用户本轮只记现场规则不符，删除伪依赖后恢复，保留原工具失败及`closeout-head.stdout`等首次双流 | 本报告记录失败归因；首次各子命令双流保留，不声称整轮0 |
| 20只读live SHA／21originals／freeze首尾、branch与stage恢复终检 | 0；逐项符合，允许plan自身新SHA与无关HEAD推进；不掩盖其它WU现场 | `sha-start.json`、`preclose.json`、`closeout.json` |

19项只读设计矩阵：absent ASCII变体拒绝；普通absent／Unicode无casefold／不同中文接受；现存大小写名族、不同stem symlink、hardlink、双dangling、resolved ASCII dangling、**C01 A1原basename不匹配而resolved name匹配**、非ASCII hardlink、目录symlink到同父的absent、跨角色、前普通后碰撞、单记录链接环、注入PermissionError、非目录组件均拒绝；独立无冲突cache链接、不同父目录且无物理别名的同名目标接受。每例全部自建文件／链接／目录快照前后相同，无创建不存在out。stat权限仅注入验证传播，不冒称实际OS权限实测；父目录samefile在resolved文字不等时的独立分支、其它文件系统差异与修后四main时点sentinel仍待修后矩阵，未拿mock证明生产已修。

读取首次大批量输出被工具展示截断；拆分重读关键plan、四源码、两新review、root末节、goal与PA01等。没有将截断当命令非零，也没有假称全部中间命令成功：本轮导入失败1、首次收尾的错误HEAD断言1和所有no-index预期1明确列出。未重跑无变化全仓pytest／fullpyrightbaseline，未运行原504harness；真实源码fix后必须重新按PA01执行完整受影响验收及默认全量0。

## 冻结、候选身份与只读SHA

本轮freeze SHA-256：`9dc8d1aebd2b11fbc4de4cb5fe9be762e4e23c399b07b9fe5f72e22090880364`，freeze与21originals保持原字节。首检包括plan共21live逐项匹配；收尾除plan20只读live继续匹配，21originals均匹配；没有用旧planSHA判断作者合法修订失败。

plan起始SHA：`7a53f5a3983d068e33e6140f79e0d079249e5b751e09a00df0e9e51586eef6da`。

plan候选SHA：`38d115621fc81ebeba7d06af88331ed2439ef076670897b93e171b5a297a1bed`。本artifact自身SHA在`closeout.json`记录，不自引用；新plan仍待根核收与同版双审。

首尾branch均`codex/upload-material-oracle`；起点HEAD `2a8c5d3e3c14b26e2d1e28efb66448b567c21465`，收尾现场HEAD `31473fe1cb0f0af5062c3074aee87157bcaa0252`；stage集合均空，本Agent未stage／commit。只读git log/show确认中间`89ed474b`保存既有F3碰撞／F7取证docs，`31473fe1`接受F7 S1（CN源码／README／测试及F7review）；未包含本轮plan/newfix，不改变20只读live／21originals内容。非冻结root/F4现场治理dirty保留；不把这些改动归成本轮写入或作停止条件。

下表20项只读输入首尾逐项一致；plan原件作为第21项仍匹配起始SHA，见两份完整receipt。

| 只读输入 | SHA-256（开始／结束／original一致） |
| --- | --- |
| `utils/analysis_sample_inputs.py` | `021e777e263a87d8389741819f933d61bcca0e2f9762d49b116ed9f36580e296` |
| `utils/build_semantic_digests.py` | `4eab095a838d21fd63dbf7402b7dc872ccc43cf0aa761bccc7f5835c0aa98fd0` |
| `utils/docling_schema_regression.py` | `c6a16716acdcbaf879d2ea2b1276c3eb73f42c8557968e5732cd99e63e95d208` |
| `utils/verify_missing_tokens.py` | `2cf113b92fa7723c24e064eb8f8c8f8ed36743865bc7b7b17b92361f65e3a339` |
| `utils/ab_ocr_compare.py` | `b28ad6f4d6119609290d3cd7f1683fe8de74255a78ddb487ea5695269e98d175` |
| `docs/gateflow/pr-197-r1-f3-goal-20260930.md` | `fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935` |
| `docs/gateflow/pr-197-r1-f3-implementation-20260930.md` | `41b2f50d57f30e333af3daceb2ad5ed51a84154deaae3d4eca20fea2f7475c1a` |
| `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| `docs/gateflow/pr-197-r1-f3-plan-amendment-20260930.md` | `93b03af2cebb4b7b65d60e58a557cf75670b1b86c015ad818425ce2859c8f071` |
| `docs/gateflow/pr-197-r1-f3-plan-validation-fix-20261001.md` | `dc8b3b34ab8393694ba994897af94403f08b94aec09090350b5e28c13c7450a1` |
| `docs/gateflow/pr-197-r1-f3-plan-quality-receipt-20261001.md` | `9c841d143b153278ddf8a09f864ed56fa82ad281f4a8beeeadfa6c96ecf0d8e5` |
| `docs/gateflow/pr-197-r1-f3-reserved-artifact-collision-20260930.md` | `45372ab7723c6e1dbbdc1da5d6db3555a8653de5fea75c2556c217013807688e` |
| `docs/gateflow/pr-197-r1-f3-plan-fix-20260930.md` | `806f11dc9f5f7a576fac33ade5a1da077abe267dc343792c21eae91208f9b850` |
| `docs/reviews/plan-review-20260930-215517.md` | `2675a6b2c4755b966c7d38f3e3f3d5adc47058d9b66387b74c9b3c0690218dd2` |
| `docs/reviews/plan-review-20260930-215618.md` | `2d612e272cfbaeaa866e475f619b3bfb4730829d808ff258bd0bcae94074368a` |
| `pyrightconfig.json` | `661d7c531f7cacc7038f570675b43052ed800cd87915a1a218504dbfe6d4357c` |
| `pyproject.toml` | `28429056b51e29c672f029723d3bbef0db0d781b6bc72d0cb8c2d3e823c79474` |
| `docs/reviews/plan-review-20261001-005120.md` | `4922a1d95d75783efeb1700773d41f62779712f1f86bf335f790bd4364fa0139` |
| `docs/reviews/plan-review-20261001-005207.md` | `c1736b57685fdac4dfbac15990b7ec0906f81d7e6dc2b631c3458aba6aef6ee5` |
| `docs/gateflow/pr-197-r1-f3-amendment-review-adjudication-20261001.md` | `0c0d309fde9cfdbe0468fb06a481e419cae86ff8381691acdf6e4d54ff5042e6` |

## 残余风险、owner／destination与README决定

| 风险／未覆盖 | 分类 | owner／destination及边界 |
| --- | --- | --- |
| F3-PR2-A1／F3-C02计划文字候选待同版复审 | fixed in current slice（作者计划已修候选；根未回写） | plan判据／实际路径与共享身份owner；根核收本版→MiMo/Kimi窄同版双审→根裁决／必要fix、re-review→accepted amendment commit；不因分类放行 |
| C01/C02真实源码仍未修；修后完整矩阵／默认全量pyright未执行 | fixed in current slice（同一原S1必要correctness，candidate尚未accepted） | digest专属owner及四入口输入／实际产物owner；accepted amendment之后才能Sol源码fix／双路code review。不称新S2或未来slice已approved |
| 检查与写入之间外部更换输入／链接、并发事务 | requiring new issue or explicit user decision（沿原风险） | 总控另定并发／事务goal；当前不加锁／回滚，操作者运行中不替换输入链接 |
| 尚不存在且解析父目录无法确认同一身份的别名（含缺失parent拼写、非ASCII归一化／case规则） | requiring new issue or explicit user decision（原未实测absent alias目的地） | 总控按新的直接反例裁决文件系统规则；当前不猜通用Unicode／卷语义。已证四入口同扁平parent的ASCII反例必须在S1修，不借残余延后 |
| 同stem跨运行缓存来源、失败缓存仍skip、schema统计quirk | requiring new issue or explicit user decision（原限制） | 原缓存／统计owner；保留规则，换输入／配置用新out。不声称A/B可以认证外部producer历史内容来源 |
| selected-only／diagnose历史parity影响 | fixed in current slice（既有A2披露逐字保全） | 操作者全量manifest与对应数据根；consumer参数化／历史parity重现仍另定goal |
| 历史公开locator、真实OCR／转换质量性能、永久回归保障 | requiring new issue or explicit user decision（原范围） | 用户／总控另定目标；合成全缓存／设计probe不能作真实转换证据；utils永久tests/cov豁免保持 |
| F4/F5/F6/F7及其它原WU | assigned to later work unit | 总控及各WU owner；本轮只读观察，不改／不裁决 |

无未分类风险；未遇branch／20只读SHA或必要owner不可读的blocking条件，未发现必须改binding goal业务命名／新架构的必要性。这里记录的是已授权correctness设计，不擅自改变用户目标。

README不更新：已读根README第9～16行`Agent更新约束`，其职责是最终用户手册且禁止内部gate／未来计划。此次只有内部计划／fix artifact与临时设计代码，无产品入口、用户工作流、生产分层、source/tests变化，不命中AGENTS更新触发。未来utils开发入口用其自身中文docstring／help说明，不往产品README写未落地能力。

## 当前candidate、下一入口与停止

本轮两个正式文档完成、作者计划fix候选已自验。**plan gate fail尚未解除**，F3产品finding和C01/C02代码仍accepted／未修复。下一入口是根核收本版planSHA、本artifact、20只读／21originals和完整diff后，派MiMo/Kimi对**同一版本A1＋C02**窄审，同时核C01／PA01与原A1～A4保持；根裁决／必要fix与re-review、accepted amendment commit后才可源码fix。

本Agent到此停止；未派review／子Agent、不写治理controller／queue、不提交／stage／push／PR，不把设计probe记作产品修复，也不以未来未approved slice绕当前gate。
