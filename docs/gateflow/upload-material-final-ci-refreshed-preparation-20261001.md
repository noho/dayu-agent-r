RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-9100c558

# PR197 最终真实 CLI CI 刷新预备方案

任务 `pr197-final-ci-refresh-preparation-sol-20261001-01`；**proposal，未 accepted，所有真实 CLI CI not-run**。精确运行模型无独立遥测，记unknown，不从路由/canary推断。
本轮仅静态取证与新增本方案/独占证据，保留首版 `upload-material-final-ci-preparation-plan-20261001.md` 原件；不推进 gate。
唯一 workspace `/Users/leo/workspace/dayu-agent-r`、branch `codex/upload-material-oracle`；main 不动，全部成果归 PR197，用户手工 merge。产品唯一 writer 为 F5 Sol97574；
G4/G5 Sol61298 仅准备其自有 docs，本方案不读取在途报告或可变产品。

## 1. 权威、对象和当前信号

只读对象为 `3a836a463aab3eeffb050facd592e614801d6ca9`；freeze SHA256=`9e6c40aad16ec7954d7f7d4068f79ede408e6f65b446b36bb5f1e6d574f06c96`。49件 pinned 文件逐件与清单及精确 git OID 同字节，包含31件正式裁决；
必要补源只由该 OID `git show` 写入独占 supplemental 并记录 hash。
本轮用户输入覆盖旧文档时间线：F2/F3/F4/F6/F7 正式闭环；F5 已绑定“能推断则推断，否则 A 继续、B 单列不猜”，202行 accepted plan 已进上述 OID，代码仍实施中。F5 不能继续列 Q1 pending，也不能把 accepted plan 当产品完成。
F5 `unknown/uncertain>0`：整体 FAILURE、job FAILED、CLI exit 1、wait failed；已发布 A 保全，适用摘要为 partial_failure；纯未知与空发现分开。取消及 F6 原 cause/完整性失败优先。
新类型/API 以 accepted plan 为待实施契约，本 pinned 产品尚未实现者不能称现存。
原17label和受控 XBRL 尚未完成；最终实际 head、parser/runtime/capability/source/corpus/完整矩阵均未冻结。现有 registry 的 Fins ready scope 只有 download/upload_filing，不证明 material ready；
其它 init/prompt/interactive 既有记录保全。
动机成立：旧 Raw 已确认删除，旧160次与历史 digest不能支撑最终代码验收。以36项正式 accepted 段重建新 run lineage，不问备份、不伪造历史核验，不重裁既有业务，也不把160设为上限。
静态证据根 `E=workspace/tmp/pr197-final-ci-refresh-preparation-sol-20261001-01/`；
`static-freeze-verification.json`、`supplemental-index.json`、`label-matrix.json`、`public-source-candidates.json` 为本方案引用。它们不是 formal registry/proof；本轮 observed execution 为空。

## 2. 实际 owner 与 C02 修正

下列简称在逐label表和JSON中使用；JSON记录实际符号、行号、SHA及正式裁决段，不以文件重叠推断业务依赖。

| 简称 | pinned 实际入口/责任 | 后续必须重绑的边界 |
|---|---|---|
| P | `arg_parsing.build_parser/_register_upload_material_command`；`commands/fins._prevalidate_upload_material_request/_upload_material_stream` | 参数清单必须最终运行 parser 导出；本轮不构造 parser。静态源码不证明动态分支已触达。 |
| W | `workspace_root.resolve_workspace_root` | O03普通文件base已在此owner修复；F3是分析utils显式输入路径owner，不能给O03记F3完成票。 |
| A | `ingestion_runtime._admit_material_upload_facts/admit_fins_upload_material_request` → `ValidatedFinsUploadMaterialRequest` | 已有静态selection/asset-plan handoff；当前不能证明公司/目标/全部身份前置规则完成。 |
| I | `docling_upload_service.build_material_ids/validate_material_upload_ids/evaluate_upload_overwrite_precondition`；`upload_company_meta.resolve_upload_company_meta_decision` | 稳定身份、动作和条件公司名分别由真源产生；不能在CLI或adapter重算。 |
| N | `upload_asset_plan.plan_upload_assets/docling_storage_name`；`upload_format_contract` | 全资产命名/选择与格式投影；当前material selector未落实，最终参数名不得预造。 |
| D | `DoclingUploadService.prepare_upload/_build_original_assets/_build_pending_assets/publish_prepared_upload` | 逐原件读取、真实转换、typed reason、安全标签与文档发布；上游内容识别准确性不属本项目修复。 |
| S | `FsSourceDocumentRepository.read_source_snapshot/classify_source_integrity/get_source/get_primary_source`；core状态/发布 | 仓储公共读、完整性、原件/派生/primary/版本/已发布manifest；CI不得解析私有布局补业务真源。 |
| R | `ProductionFinsUploadRunner._run_material_upload` → SEC或CN(含HK) `upload_material_validated`；runtime direct/observed/job | 真正material路径，direct与job/Host lane分开；共享模块不等于共享业务owner。 |
| C | `FinsDirectCommandService.process_material` → `_preprocess(SourceKind.MATERIAL)`；CLI `_process_material_stream` | 同base、exact发布身份独立process；generic process使用FILING，不能代替material。 |
| L | `arg_parsing._finalize_log_level_selection`、`cli.main._open_log_file`；CLI direct output/SIGINT | 日志selector/append、业务screen、signal清理分别取实际事实。 |
| H | `utils/cli_ci_run_observation` | 已有Host terminal observer、dependency helper、public path分类/secret scan；不是完整material campaign。 |

C02：O24归 A/N/D/S 和 O25 primary/fingerprint；O28归 R/C direct路径与真实locator查询；O36归CI输入展开/前置核验/lineage owner。三者不归F4/F7。
F4仅 `read_source_meta_view` 同guard成功前缀/read_error、`build_cn_download_identity_index` 及实际HK download/rebuild消费者；raw view不是COMPLETE证明。
F7仅 `cn_download_models.CnDownloadTerminalStatus` 的 `ok/cancelled/integrity_failed` 与normal子集及workflow/rebuild/adapter实际消费者，不拥有generic upload admission。
F4/F7/F6/F5的必要download/rebuild回归依最终diff/调用链纳入，不重做其已闭环裁决。F5新增同窗integrity API/unknown契约待final源码确认；不能拿旧F4 raw view加另一窗口classify拼出可信证据。

F5后续真实回归至少覆盖以下已绑定行为；这些是download/rebuild的依赖回归，不给material labels抵扣coverage：

| 输入/时序 | 必需事实与可复核链 |
|---|---|
| 同公司可信原始年度+季度，窄/宽窗口与本地rebuild | 同可用证据集合推断一致；远年证据不压制合法明确季度；原始日期/可信分类同窗。 |
| 可确定A与证据不足/真实冲突B | A正常处理/发布，B单列真实source引用且不虚构ID/财期；unknown>0整体失败且A不被清零。 |
| 纯未知与确无候选 | 前者FAILED/CLI1/waitfailed，后者正常空发现；不得unknown→missing。 |
| rebuild未知B，及已有processed的确定A | B原source/blob/manifest/processed字节不写；A日期/来源按accepted三步契约核，不能要求正常download自动同步processed。 |
| 本地读异常、完整性异常与取消竞争 | 保原读cause/F6公共原因、F7入口子集；取消按runtime真源优先，真实已发布A计数保全。 |
| direct、legacy job、真实Host awaiting | 同源unknown/omission/count/terminal，job严格新schema读写；direct CLI1、jobFAILED、waitfailed各有真实lane证据，不能用一个lane投票代另一个。 |

## 3. 36项逐label obligations

下表是必要predicate/新输入族与**明确未知**，不是本轮观察结果。`label-matrix.json`另存每项正式accepted/修复段、历史观察边界、owner定位、独立surface及required evidence；
每个surface至少一个独立有效coverage claim，同一run/case可支持多个claim，不能用同组成功抵扣另一label。

| label | 必要predicate与新场景族 | owner；明确不确定/边界 |
|---|---|---|
| O01 | final help/默认action/public surface实际展示；help不证明转换/状态正确 | P/N；最终参数与动态inventory待冻结 |
| O02 | 已裁parser usage exit2、无普通traceback；重复scalar最后值；逐非法类独立场景 | P/L；不外推所有业务字段exit2 |
| O03 | base别名/相对/default/Unicode/空格/受控symlink；regular-file明确路径拒绝、原文件不变 | W；已修owner，真实回归not-run，与F3无对应完成票 |
| O04 | 数量边界/重复path/basename/规划后真实冲突转换前typed拒绝 | A/N；数量由final唯一owner公开界限重绑，不从101样本猜阈值 |
| O05 | form/name无条件必填，缺/空/白前置typed拒绝，无started/材料发布 | A/I；其它入口同规则，非CLI真实lane另证 |
| O06 | trim后240 Unicode码点，上限内/等值/241/emoji/组合字符；无截断/新增归一化 | A/I；240来自后续用户选择(scope)，不是241历史样本反推 |
| O07 | 移除公开internal ID全输入链，保留持久内部ID；document ID仅正确性断言，mismatch零业务写 | A/I/P；最终schema/help及实际有效ID待重绑，不固定摘要字面值 |
| O08 | document ID显式空exit2零副作用；旧internal ID空/非空移除 | P/A；与O07共用case仍独立coverage，不保留旧参数兼容 |
| O09 | year 1800..2100含端点；1799/2101/-1/0拒绝、身份前零业务写 | A/I；不把F5财政推断规则混入material输入域 |
| O10 | period trim/upper/空→null；FY/H1/Q1..Q4；nonsense/超长拒绝 | A/I；不新增长度阈值，tool空文本入口差异按最终契约 |
| O11 | 两日期非空严格ISO且公历存在；非法公司/材料零写；空filing→null | A；显式空report_date尚无独立accepted规则，final若触达需定位具体合同 |
| O12 | fresh/需刷新缺company-name前置typed usage；既有可省略；alias conflict不污染公司/材料 | I/A/S；名称状态感知，不设无条件parser必填；FS辅助文件另记 |
| O13 | auto创建/同内容skip/异内容升版；delete tombstone幂等字节/时间；同内容恢复原ID/版本 | S/I；不同内容/并发恢复不得从窄观察推广 |
| O14 | active create无overwrite同/异内容拒绝零业务写；overwrite明确替换 | I/A/S；tombstone显式create未由该裁决定义 |
| O15 | missing update含overwrite、never-existed delete前置typed拒绝；tombstone重删独立 | I/A/S；不能将所有OSError当missing，竞争最终校验另证 |
| O16 | auto/create/update至少1文件；delete零文件，非法组合先于目标状态且不忽略输入 | A/N；fresh/active对照，非CLI同源输入另证 |
| O17 | 一个form trim/upper真源进入ID/meta/manifest/事件；等价输入配对 | A/I；不加form枚举，period仍O10 owner |
| O18 | amended为持久布尔，与ID/内容版本独立；同字节改标记仅metadata；overwrite强制转换/发布 | D/S；后续binding在scope/batching；首次/skip/delete/restore规则必须final accepted owner计划精确重绑 |
| O19 | PDF/DOCX/PPTX/HTM/HTML/XHTML/MD/TXT/CSV/XLSX每原件真实转换且original+JSON发布 | N/D/S；仅这些有效样本、.TXT路径；旧F15不是symlink证据，新lexical symlink单列 |
| O20 | .json仅Docling JSON；.xml/.xbrl实例候选；有效正例+taxonomy、普通JSON/XML/linkbase负例 | N/D；真实能力/依赖/OS gap，不把部署缺失说成文件损坏，不自选移除支持 |
| O21 | corrupt PDF/DOCX与valid+corrupt：typed content+当前安全标签，全材料stored originals=0 | D/R；company独立，不能承诺任意commit故障全workspace零写 |
| O22 | 0字节Docling前content/empty_input_file、safe label/非空提示、零材料发布 | D/R；单/多文件、filing共享回归，company不由此回滚 |
| O23 | 完整original identity→统一derived命名，全集唯一；same-stem异basename成功，真冲突前拒绝 | N/D/S；不固化旧stem字符串，逆序/交叉原派生名冲突独立 |
| O24 | 两原件全转换2+2完整发布；同selector逆序ID/fingerprint相同、不同selector role-aware不同 | A/N/D/S；旧无selector成功需新证替代，不依赖F4/F7 |
| O25 | 多文件显式唯一exact原件selector，单文件自动；角色进入skip/primary/read | N/D/S/C；缺/重复/错/删除带selector拒绝；final真实参数名未冻结 |
| O26 | 三市场新公开真实材料单文件source成功；按公司/source/manifest各自字段归属断言 | R/D/S；新源不是旧私有DOCX/PDF字节，版本/hash待采；不复用旧固定ID/抽取计数 |
| O27 | upload后无processed；另一次同base process_material消费exact ID/version/fingerprint/primary | C/S；逐市场与选主变更对应；内容准确性上游，不代表Host路径 |
| O28 | direct可持久Fins业务、相关Host/EventLog/Trace/Memory/runtime/job/SQLite逐locator查询缺席 | R/C/H；保queried/exists/owner_scope/候选模式；不泛化到真实Host lane，不归F4/F7 |
| O29 | UI业务print与log分开；quiet/debug-stream合法，冲突两顺序exit2；append前缀；pipe不替files | L；不从debug-stream无额外stdout推出诊断是否生效 |
| O30 | SIGINT优雅有界退出、不假成功；early/活动转换与原argv重试，实际时间/worker证据 | L/R/D；不要求任意取消零FS/公司回滚，不以sleep证明Docling阶段 |
| O31 | publication前进程组SIGKILL、-9无业务终态、同base原argv重试；快照衔接 | OS/采集器/S；无残留归killpg条件，不证明parent-only/任意commit强杀 |
| O32 | 同ticker异材料/异ticker同步并发，每成员终态、最终完整文档共存/manifest无丢更新 | I/S；pair共享diff不能计为每成员独写，不承诺并行commit/公平性 |
| O33 | fresh identical auto竞争一create一verified skip；权威identity/fingerprint/integrity确认、不重写 | I/S；真实I/O仍failure；旧新异常解释分别保留，不改通用storage_io成skip |
| O34 | 文档全部转换后权威已发布manifest条目为成功必要条件；company独立合法事实可保留 | D/S/R；缺条目⇒未成功，有条目不推出CLI成功；post-commit异常未有实际证据 |
| O35 | raw/index/双流/exit/signal/timeout/residual真实完整；汇总与业务verdict独立 | CI采集器/H；旧160/500ms非保证；新timeout实际触发后才声称覆盖 |
| O36 | 新前置与exact argv相符；同stem/异stem按实际文件；历史15归因+3标签替代独立lineage | CI矩阵/采集器；S12/S16是基线、S18–22诊断，不机械25全失效；非F4/F7 |

必要组合：O04/O23命名×O25 selector，O05/O06/fiscal/ID多非法优先级，O12/14/15条件state，O18角色/内容/overwrite，O21/22标签×普通/debug，O30/31 publication阶段，O32/33真实pair。其余参数做单维全覆盖与pairwise；
每label/surface输出covered/missing/ambiguous证据，不汇总成一张“组完成票”。
O11空report_date、O14 tombstone create、O13不同内容/并发恢复、O18未给出的状态转换、新动态交互与post-commit/parent-only/timeout公开承诺：先查final accepted合同；
仍无法合并原判准时以具体predicate+反例+owner blocked交root，不选新业务、不要求重述36项。

## 4. 新输入和来源规划

输入manifest每资产必记recipe或public URL、发行人/报告名/期次/发布版本、来源响应/重定向、媒体类型/长度、采集/生成器及依赖版本、真实new SHA256、父资产hash、允许根/域和场景映射；未生成/采集的version/hash为null+not-run，不能拿旧摘要冒充新hash。

| 输入族 | 最小可复现recipe与新lineage |
|---|---|
| TXT/MD/CSV | 固定UTF-8“合成CI材料”正文、两版明确不同字节；CSV含固定header/两行；记录换行/BOM。不同stem、同stem异后缀、两个目录同basename、Unicode/空格/.TXT、N−1/N/N+1按final上限展开。 |
| HTM/HTML/XHTML | 同合成业务正文；HTML真实doctype/表格；XHTML合法XML namespace/闭合标签；不能只改后缀冒充格式。 |
| PDF/DOCX/PPTX/XLSX | 用冻结生成器生成合法文本页、段落、slide、sheet；保存脚本recipe/生成器版本和newhash；活跃转换取消用可控页数/复杂度与真实事件确认，不按固定sleep认阶段。 |
| 负例/路径 | 0字节；合法母本定点截断/损坏容器并保父hash；普通JSON/XML、独立linkbase、非支持后缀；CI-owned symlink保lexical path/target/lstat/目标hash，argv不能替换成target。 |
| Docling JSON | 同一新campaign先真实转换成功，经S公共read取得真实JSON/母本/hash/schema/Docling版本；再作为.json正例真实upload。禁止手拼JSON、mock converter或沿用旧产物。 |
| 公开US/CN/HK | 下列定位候选由root按既有公开真实CI授权合理选择，不另列“公共采集未授权”；私有材料没有现成访问授权则不读。旧R01–03仅historical-reference，新source各配真实process。 |
| XBRL | SEC真实instance及schema/linkbase/taxonomy完整bundle，记录解析引用清单/每件hash、catalog/cache/允许域、backend依赖和支持OS；资源不可用明确gap，不以普通XML成功替代。 |

US明确文件候选：`https://www.sec.gov/Archives/edgar/data/789019/000095017025100226/msft-ex99_1.htm`，pinned公共fixture来源manifest提供定位；
候选为MSFT业绩附件，实际版本/发布日期/媒体字节与hash待重新采集核验，不声称旧private DOCX相同。允许root换为更适合的公开财报但须在final source manifest说明。
CN定位候选：`http://www.cninfo.com.cn/new/hisAnnouncement/query`（POST），600519、2025Q1全文；静态依据为pinned CNInfo downloader。
实体PDF须从正式响应adjunctUrl与`http://static.cninfo.com.cn/`绑定，**当前尚无实体URL/新hash**，属于source-selection gap。
HK定位候选：`https://www1.hkexnews.hk/search/titleSearchServlet.do`，0700、季度/年度正式公告；stock mapping为同域`/ncms/script/eds/activestock_sehk_c.json`。实体URL从真实FILE_LINK同源构造；
新公告版本/URL/hash待采集，是来源定位待完成而非公共访问授权缺失。
XBRL实例候选：按pinned SEC `ARCHIVES_BASE`与public AAPL fixture accession定位 `https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928_htm.xml`；这是待验证URL，不承诺存在/有效。
须重新取得instance+所引依赖；fixture自身不替代新run真实公共来源。
合法内容的抽取准确性归Docling上游；本项目只核原件传入、实际产物持久化/读取同源。失真先排除本项目传写读错误，确认上游后保input/version/output证据转上游issue，不修本地抽取特例。

## 5. 完整CI tooling行为增量（待正式计划，当前不创建）

静态utils树只定位到 `cli_ci_run_observation.py`，未核得完整material campaign或registry校验实现；旧Raw collector不可恢复。必须补一条完整“新run展开→真实执行/观察→冻结report→refs/proof校验”tooling行为增量，同gate不按每文件拆slice。
后续最小允许tooling文件候选：`utils/cli_ci_material_campaign.py`（矩阵/输入/公共状态观察/报告）、`utils/cli_ci_process_capture.py`（子进程/TTY/双流/信号/进程树）、`utils/cli_ci_registry_validation.py`（唯一schema/refs/coverage/proof校验）；
临时启动脚本仅放新run `workspace/tmp/<run-id>/`。这些是拟新增模块，不是现存API；不将测试驱动/采集器放产品层。
朴素最小接口候选：`run_case(argv: tuple[str, ...], cwd: Path, workspace_root: Path, evidence_root: Path, stdin_bytes: bytes, tty: bool, timeout_s: float, signals: tuple[SignalAction, ...], limits: ObservationLimits) -> CaseEvidence`；
输入argv由final parser/矩阵展开，不经过shell拼串。
拟新增typed值至少明确：SignalAction=(signal:int,target:Literal["pid","pgid"],trigger:str,bounded_deadline_s:float)；
ObservationLimits=(max_files:int,max_bytes:int,max_rows:int,max_query_s:float,max_process_samples:int)；
CaseEvidence=(case_id:str,attempted:bool,executed:bool,returncode:int|None,timed_out:bool,evidence_refs:tuple[str,...],gaps:tuple[str,...])。不可把这些塞extra payload/Any；
trigger必须final真实public事件或进程条件，不宣称是Docling内部阶段。
`run_campaign(matrix_path: Path, input_manifest_path: Path, runtime_manifest_path: Path, policy_path: Path, run_root: Path) -> Path`只编排并返回冻结report路径；矩阵/authority与观察fact分离。
`validate_registry_pair(oracle_path: Path, scenario_path: Path, inventory_path: Path, evidence_manifest_path: Path, policy_path: Path) -> RegistryValidationResult`只读，结果含分维计数/错误/适用scope，不能写ready；
拟新增typed schema decoder由此模块唯一拥有，其他消费者复用。
拟新增RegistryValidationResult必填`scope: tuple[str,...]`、`dimension_counts: tuple[CoverageDimensionCount,...]`、`errors: tuple[str,...]`、`ready: bool`；
CoverageDimensionCount必填`dimension: str`、`mandatory: int`、`covered: int`、`gaps: int`，dimension严格限§6七个维度。schema/refs错误与product mismatch分别返回，不能用缺省空tuple吞未读文件；readiness proof只消费这一结果。
H可复用 `classify_public_evidence_path`（producer开始即排除raw DB/WAL/SHM及路径文本）、`scan_public_evidence_files/write_final_publication_scan_report`、真实Host `observe_run_terminals/evaluate_success_dependency`。
依赖helper只管能否尝试后继，不产产品verdict；不创建MockRun、手工memory或伪造EventLog。
双流与TTY：非TTY保存原始stdout/stderr分别的字节/exit；TTY需两条独立PTY分别观察流或经验证能保stream身份的采集器，冻结TERM/UTF-8/rows/cols、input/signal时间线/cast，回放关键与最终screen，不能把合并PTY输出拆成假双流。
若平台只能合流，记录evidence limitation并保所需双流独立真实case，TTY交互义务不能用非TTY替代。
FS：同算法bounded before/after/delta，只允许run marker所辖根；产物内容/状态通过S public repositories/public read tools取，company/source/processed按各owner字段。
已发布manifest必要信息若公共接口不足，记public-observability-gap交storage owner，不直接解析内部JSON或以staging文件认成功。
日志：run-owned路径，保normal/debug与同log追加前缀字节；进程：PID/PGID/祖孙启动退出、实际signal/timeout升级/清理窗口，pair同步before/after归属明确；harness超时与产品取消分别记录。
SQLite：按runtime/call path定位相关CI-owned DB；存在时read-only URI+connection-local query_only、allowlist SELECT/只读metadata，同query ID有界before/after/delta，限query/rows/fields/bytes/time；
不读财报body/section/table/fact/provider payload、不导rawDB。无相关DB须queried/not-applicable直接证明；归属或安全不足blocked，不能未查就记0。
Host lane仅实际prompt/interactive→真实provider/tool/awaiting：关联session/run/attempt/execution/tool call、canonical EventLog/public Host read/production tool_trace、memory与实际RunnerInput；
direct lane逐locator记录适用性，绝不凭空补HostRun。legacy job通过实际runtime API独立取证，不发明wait/job顶层CLI命令。
tooling质量证据：中文module/class/function docstring（参数/返回/异常）、严格typed；utils既有免永久unit/cov，但必须真实验证argv空格/Unicode不改写、双流/PTY回放、signals/timeout/进程树、bounded越界/拒读、hash/index/ref错误fail-closed。
采集器可用run-owned真实小子进程做传输检查，这不是产品证据；产品断言必须真实CLI。workspace临时脚本另用显式非空include pyright配置，不能被默认exclude误报0文件通过；后续源变更激活venv跑受影响测试/full pyright，产品文件按项目≥80%约束。

## 6. 正式registries与readiness最小校验owner

formal schema仍依 `docs/cli_ci.md` §§4.3–4.7、5.1，当前JSON schema_version=1；oracle的command在scope.command，scenario在顶层command。拟新增validator严格解码两套形状，不靠getattr/默认值、scenario.scope或字符串出现次数统计。
至少核id+正整数version唯一、status合法；stable predicate恰好一个current accepted未superseded owner；accepted_oracle_refs保历史`id@version`，oracle_predicate_refs用于当前解析；双向supersedes/superseded_by无断链/循环；
每surface映射适用command/前置与accepted predicate或明确objective/hard contract。
每个mandatory obligation按command/parameter、precondition、branch/option、input-class、combination/high-risk、cross-command、required-evidence分别检查accepted claim；
每claim必须绑定真实case/同runidentity/输入newhash/充分frozen report raw refs。逆向检查所有current accepted record都可解析，不能有孤儿claim/未定义surface/重复current owner。
正式ID/version仅后续登记分配，本JSON本地surface标签不是accepted ID。旧Raw只历史不可复核引用；新evidence run/报告hash与historical-reference分栏，不能复制旧observed_evidence假装已采。旧accepted版本、其它command原记录及其历史proof不原地覆写；
material新scope/proof以版本化登记添加。
两registry proof同真源重算inventory身份/version/digest、mandatory/covered/gap与各维计数、current predicate解析、user decision身份、report digest集合、lineage、unclassified/dangling/unresolved/rejected replacement。
registry_status由validation_result派生，旧ready不供material借用；新branch发现使相关scope回calibration。
observation completeness、registry readiness、产品conformance分别报告：充分error/cancel可完整；已裁oracle的implementation failure可与registry ready并存且须列finding，不能伪作coverage gap。
最终大目标仍要求必要fix后真实conformance通过；两个ready字面值不等于CI pass。
登记docs改变head时保持被测run绑定原target，补产品source集合、parser/runtime/capability、dependency/build、inputs/source/corpus、matrix、policy、effective oracle **各自同字节**证明，才可由root批准复用事实并记录registration head与validation head。
任一相关字节变、新义务/依赖/运行语义变，重冻对象并真实新run；不能只凭“只改docs”重标旧report为新head运行。新的report/report-derived registry proof不能反过来改写effective oracle。

## 7. 后续顺序与可验证final signal

1. root核F5产品闭环、原17label/受控XBRL及必要review fix实际成果；保既有F2/F3/F4/F6/F7完成状态。产品writer仍按root排程；本轮不dispatch/不改controller。
2. 在全部修复后绑定finalhead/base与本地/远端/PR197对象；冻结final源码/dependency/build。正式最终plan重新取实际parser顺序/default/choice/nargs/aliases、所有leaf分类、help、runtime、capability/OS、source/input/policy；
静态pinned清单不能替代final parser运行。
3. 完整矩阵与本表/JSON逐surface双向对照；合法/非法/边界/状态/交互/高风险组合/跨命令展开，输入先生成/公开采集并newhash，Docling/XBRL正例链完成。真实来源选择由root负责；taxonomies/OS/provider/model资产不可用按资源gap记录，不缩mandatory。
4. 将正式final plan/tooling接口/允许文件/测试类型/矩阵/source policy与精确字节交同版两路独立审查/root裁决。当前proposal不accepted、不运行、不登记formal registry；最终计划才具执行入口。
5. 实现完整tooling增量、真实传输/observer校验与非空include类型证据；建CI-owned marker/run manifest，准确argv后真实执行全部mandatory及实际共享owner回归，前置失败不假运行后继。非阻塞error/cancel仍继续其它已授权场景，未知动态branch扩矩阵/新补证。
6. 冻结一份run-level observed-behavior.md及JSON/raw manifests：主体内嵌screen literal、输入/实际选择、业务与诊断before/after/delta、SQLite适用性、process/timeout、跨命令消费、每label/surfacecoverage与gap；事实不混修复建议。
先freeze，再双审证据/已有predicate映射/root裁决。
7. 若真实CI暴露现成accepted oracle偏离，走正常必要owner fix、测试/类型/README和同版review，相关新head重新冻结并真实重跑完整最终范围；同gate必要修复集中处理，不按每file拆slice。仅新业务/无法合并的判准具体blocked交root，不改oracle迁就代码。
8. 后续正式登记material oracle/scenarios/lineage/proof，校验保其它command和旧版本；按§6复用或重新run规则绑定最终PR head。
最终报告精确target/base、完整矩阵数量/分维coverage、实际attempted/executed/not-run、来源/corpus/policy/registry/report hashes、primary verdict、三维结果和classified residual。
最终可核信号：无未分类mandatory leaf/branch，无not-run/blocked或不足证据；每label/surface有充分真实claim；所有适用effective已裁predicate符合；两registry proof可重新计算且material scope ready；
最终目标与被测source字节关系明确，才能报告full-real-pass。任何缺项保持对应gap/failure，不以测试绿、旧CI、accepted plan或PR MERGEABLE替代。

## 8. 文档职责、残余和本轮停点

后续tooling运行/证据/registry合同更新归 `docs/cli_ci.md`；根README仅final用户操作/参数/日志位置，Fins README仅已实现公共能力/执行路径，tests README仅现存测试维护/运行变化。本轮proposal不触发更新README；
后续产品变更按触发先读对应约束，不把future tooling/门禁流水写用户手册。
残余分类：**资源/来源gap**=新公开实体URL/version/hash、taxonomy完整包、支持OS/backend/model/provider资产与预算待final冻结；**证据gap**=所有真实CLI、TTY/动态分支、Docling JSON、并发/取消/timeout与final proof not-run；
**contract gap**=§3明确未给规则的surface，查final合同后仍缺则具体交root；**已批准待实施**=F5/原17label/XBRL，不能从本proposal生成完成票；**scope外**=52/53周/过渡财年、历史迁移、任意commit/parent-only kill等新承诺，保原destination，不自动实施。
本轮交付本新方案及E下静态sources/hash/逐label矩阵；
未改产品/tests/README/依赖/config/旧计划/正式registry/readiness/freeze/controller，未联网、下载、转换、OCR/PDF、安装、parser构造、真实CLI、pytest/pyright/cov、commit/push/PR/merge或派发Agent。完成静态核验后停止，不进入下一gate。
