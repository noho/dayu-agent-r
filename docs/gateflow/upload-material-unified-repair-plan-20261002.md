RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-4dd6e50a

# upload_material 统一修复 WU 正式候选计划

## 1. 计划身份、授权与可生成性结论

- 任务 label：`upload-material-unified-plan-sol-20261002-01`；唯一计划作者：本轮 Codex。实际模型未由运行时暴露，`unknown` 不由路由或 canary 补推。
- 本次集中恢复label：`upload-material-macos-boundary-recovery-sol-20261002-01`；本轮RUNTIME/PROVIDER/MODEL=`codex/gpt-6-sol/unknown`，CANARY=`gpt-6-sol-193e0877`；报告为`upload-material-macos-boundary-recovery-report-20261002.md`。模型未由运行事件暴露，不以canary/provider推断；原件抬头保留原作者身份。
- 本次macOS补证label：`upload-material-macos-plan-completion-sol-20261002-01`，本轮CANARY=`gpt-6-sol-7d716624`，原件抬头CANARY属于准备轮，不能当本轮证明。
- 当前 Gate：正式 `plan review → fix` 候选交付；**不是 accepted plan，不是 plan gate pass**。正式双审已终态，binding 裁决为 `upload-material-unified-plan-review-root-adjudication-20261002.md`。本轮 label=`upload-material-unified-plan-fix-sol-20261002-01`，RUNTIME/PROVIDER/MODEL=`codex/gpt-6-sol/unknown`，CANARY=`gpt-6-sol-97b2d1bc`；模型未暴露，不由路由反推。完成集中修订与必要技术验证后停，由 root 冻结复审，不执行下 gate 或产品实施。原件抬头与前三轮 label/canary 仅为历史。
- 本轮修前 plan SHA-256=`2fc3d1911737e4afcd964a2cb586a2e661c5fd38a55cf62480c15ce6c3a9f9d7`，冻结原件 `workspace/tmp/upload-material-unified-repair-20261002/formal-plan-review-01/plan-frozen.md`；新候选 hash 写本轮fix report及独占delivery清单，不自嵌动态hash。本轮允许写入只为本文、新fix report和新独占tmp。
- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；branch：`codex/upload-material-oracle`；source HEAD：`619d092ab4278645203c7ebe08515f7697d92b71`；base main：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- Binding scope：`docs/gateflow/upload-material-unified-repair-control-20261002.md`，正式审查冻结读入版本（historical snapshot）SHA-256 `232c397b9a5a281a9b22aeacf3990aa843666d8372d9ad82ce57e61808a352fd`，由 `workspace/tmp/upload-material-unified-repair-20261002/formal-plan-review-01/input-sha256.json` 绑定；该 manifest 自身 SHA-256=`b685cc42b56cc3dff0f4a88c9f7ede09d987581cef8f1fad2ba5a1632e5a1356`。live control 后续 current-gate/行政核收变化不等于 goal 变化；本文不滚动追 live hash，避免 plan/control 相互哈希循环。用户最新具体选择优先于正式 UM adjudication，随后为既有 goal／有效后续裁决；旧 preparation、旧 API 草案与旧 gate 状态不能赋予新接口 accepted 身份。
- 收口时发现总控新落盘`docs/gateflow/upload-material-unified-repair-goal-amendment-20261002.md`，SHA-256 `17c0d804d459091a5c5909f42511a75e7ab2e7a9250072b9bc8e5f6e15adc290`，明确记录用户选择macOS先验收、Linux/Windows延期。本候选按该正式后续修订重绑：当前S3验收macOS arm64/Python3.11；其余两平台的实装、lock回读、强制边界/进程继承交平台部署/依赖与Documentsruntime后续项，由总控排程，不冒已验证。这个范围变化不是计划作者自行选退支持；其它原XBRL必要成功信号保持。
- **整份计划 generation-ready = true（总控必要机制可行性核证完成）；正式 plan review 候选，非 accepted plan**：S1、S2 的实现边界、拟新增接口、调用顺序和断言在本文冻结为可生成候选；本轮macOS补证已取得完整候选依赖实装、真实合法positive Path/Stream及同次load/ZIP/关闭证据，配置/API候选见§7；集中harness已按root直接证据纳literal根目录/祖先metadata/Python.app/otool declared.parent+resolved.parent精确库目录/独占cwd/现有Queue必需POSIX信号量类别许可，root 已核 parent97张票据及同策略 continuation10条关系case（另managed-cancel） 的必要边界/继承/取消机制，见§7.4/§8.1；资源独占假设已由用户正式修订撤销，不能以启动成功冒通过。不得取前两片代替全部 WU，或把 S3 变成独立 residual／退支持。具体 B-X1～B-X5 在 §8。
- 用户已确认 goal，不重问 form、name、period、amended、公司事务、并发或 XBRL 支持选择。原准备轮仅允许新增本文、preparation report和其独占tmp；本次macOS补证仅改S3/整体状态/必要交叉引用、新增completion report与独占 `workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/`（公开证据按用户授权双份保全）；下述产品白名单只约束未来经正式接受后的实施，不是本轮写入授权。

## 2. 目标、非目标与第一性原理判断

目标是让同一次材料请求在准入、身份／角色生成、Docling 转换、独立公司提交、材料条件发布与终态投影之间持有一条权威事实链。全部支持材料经 Docling；全部原件与派生资产完成且 source manifest 提交正常返回后才报告材料成功。公司是独立业务事实，合法公司提交不随随后材料失败反向删除。

动机成立：真实 HEAD 的 material handoff 只有 request／selection／asset_plan；身份校验仍在市场工作流晚期重算，材料指纹不携主角色，内容原因在 typed resolver 被重新分类，材料缺状态感知受理与并发再裁决。直接代码证据支持契约分叉与迟报；不能由旧 CLI `storage_io` 文案推断无锁、半发布或所有失败均无公司副作用。

成功信号：18 个标签逐项 owner contract、真实入口贯通、真实 FS 权威读回、失败／取消／竞态闭合；受影响测试、逐改生产文件覆盖率 ≥80%、全量 pyright、职责内 README、同版双审与总控裁决、全部 slices 后 aggregate deepreview，最后正式 PR review／普通 push/readback／final closeout。**真实双 CLI O33 探针及合法真实 XBRL instance 上传是本 WU 验收；完整 upload_material CLI CI campaign 和正式 oracle/scenario 登记在 WU 完成后另行执行，不是 slice 或本 WU closeout 条件。**

非目标：不重做 F2–F7、#198、O03/O04/O11/O20F01/O23 等已闭环业务；22 个独立 residual 不自动纳入；不改 main／开分支／worktree／clone；不自行 merge／mark ready／外部 issue/comment；不做历史库兼容或历史日期迁移；不修 Docling 财务抽取准确率，不写第二套 XBRL parser；不添加财期推断、form 新枚举、名称 Unicode 归一化、自动 retry 框架或跨公司全局长锁。对本轮明禁外发的要求，旧 XBRL goal 中条件上游授权不能用于本轮发送；现有 #4437 仅只读查状态。

## 3. 当前真实源码绑定与证据索引

证据根 `workspace/tmp/upload-material-unified-plan-sol-20261002-01/evidence/`。`source-index.json` 逐文件记录现读路径、SHA、大小、HEAD blob 是否相等与独立副本；`symbols.json` 为当前源码 AST 行号；`official-source-index.json` 记录公开官方 URL／时间／HTTP／SHA；`environment.json` 是本轮元数据探测，未 import／运行 Docling。旧 `3a836...` preparation 仅作反例和设计素材。

| 当前源码定位 | 直接事实／本计划落点 |
| --- | --- |
| `dayu/fins/ingestion_runtime.py:1421,1462,1528,1567,4782,7889,7977,8338` | raw material 仍有公开 internal ID；handoff 无身份／状态；normalize 只有 ticker/action/source/date；摘要仍读 raw。扩现有 handoff，不另造请求体系。SHA `1d6d286b04d428f81c11e38f09d9ec54e9f9e654e63b73ad71b229d4bbf7f100`。 |
| `pipelines/docling_upload_service.py:246,357,880,932,1360,1560,1595,1689,1764,1803,1971`（前缀 `dayu/fins/`） | precondition 仅 create/update；material create 不执行拒绝；material 提前 skip、不含角色、首转换项 primary；空字节 filing-only；两段身份 API。SHA `ed0833ab567a473f22f4c57b53a3506593cd9aaec2362570b1a24787620b56c5`。 |
| `dayu/fins/pipelines/sec_upload_workflow.py:417` | raw form/period/ID/action 重算、started 后公司 commit、后材料准备。SHA `80b59a05f846cd47f7d7bdbad8406c1d5918c14ef0fb2d3a5d8391f024fa8f28`。 |
| `dayu/fins/pipelines/cn_pipeline.py:989,1016,1041,1069`；SEC façade `sec_pipeline.py:805,832,857,885` | 独立 raw／validated 两类真实入口，CN/HK 共用 CN pipeline。CN SHA `549a65e19293f9cf754fa5de2e81e5d339456701e15b932f22295734ef6bb59c`。 |
| `dayu/fins/upload_asset_plan.py:85,174,202,267,379`；R `:885` | 已有路径 identity、full-basename→Docling helper 与 exact filing selection；material plan 禁止 role。迁移选择纯算法、扩现有 plan，不复制命名。 |
| `dayu/fins/upload_usage_contract.py:18,55,140,213`；`upload_failure.py:228,424` | usage code/message 已迁出 R；public reason 有既有 `source_publication_conflict`，resolver 未透传 typed reason。不存在旧 R 第二 messages owner。 |
| `dayu/fins/storage/repository_protocols.py:401,444,683,702` | 同版 state／batch read 仅 filing；batch 正常提交回公司 outcome 或 None。SHA `206cafee6b470bd66c6e68729b246d7de4be4fd9bb88f4c0a843d6e8b840bb65`。 |
| `storage/_fs_filing_upload_state_core.py:73,131`；`_fs_source_integrity.py:1043` | 单 guard + exact inspector 已有可复用机制，publication identity 只 filing。不能 material 拼两次读取。 |
| `storage/_fs_storage_infra.py:417,533,676,740` | writer 在 begin_batch 取得且持到终态；swap/journal COMMITTED 后 release 可抛，不能用异常证明未提交。SHA `f4d1e9ecd94dab2cb2e82ea7f65c85e09eefee34cfcc13ffde9db1adf2f4001f`。 |
| `storage/_fs_source_document_core.py:1931`；`source_meta_contract.py` | delete 每次重新取时间／写 meta、manifest。canonical deletion 与 provenance owner 必须先校验再 no-op。 |
| `domain/document_models.py:1029`；`tools/read_runtime.py:3020` | material manifest 无 primary/amended；snapshot／processor 已消费已登记 primary，read 不应重选。 |
| `tools/upload_tools.py:344,398,489,518`；CLI `commands/fins.py:1129,1203,1219` | tool 拒 material primary、st_size 截胡空文件；CLI delete 仍检查丢弃的 raw files；batch 独立 upper。 |
| `service_runtime.py:62,197,311`；`dayu/service/fins_direct.py:297` | 现有 workspace prevalidator 装配模式及 `_run_material_upload`／同 request 透传；旧 `_pipeline_upload_action` 等名称不存在，不补 wrapper。 |
| R `:2157,3078,5093,5146` | 已有 `save_accepted_upload_terminal_if_active`；正常上传采用；no-runner／generic exception 仍走共享 message-only 收口。仅 upload 分支修同源终态，不重做下载。 |
| `dayu/documents/docling_runtime.py:222,554,856`；`docling_process_converter.py:99,256` | XML_XBRL 是候选；仅 PDF 注入 options；生产输入走 bytes/DocumentStream，配置无 taxonomy。Documents SHA `e111a1afc69d3bdc72cc987bd0e357a38eaa70c837e153caa2b2a4ad054c7ce1`。 |
| `pyproject.toml:35–65`；三个平台 lock + common | `docling>=2.127,<3` 无 xbrl extra；当前 Arelle metadata 缺席。pyproject SHA `28429056b51e29c672f029723d3bbef0db0d781b6bc72d0cb8c2d3e823c79474`。 |

未用猜测路径：`dayu/documents/docling_conversion.py`、`dayu/documents/README.md`、`dayu/runtime/subprocess.py`、`storage/_fs_company_meta.py` 不存在；实际转换、runtime 进程和公司 commit 真源分别是上述 `docling_runtime.py`、`dayu/runtime/interruptible_process.py`、`domain/company_meta_contract.py`／`_fs_storage_infra.py`。这些 locator 失败不是产品失败或 pass。

## 4. 完整 scope 映射及切片理由

下表 adjudication 名称均在 `docs/reviews/`；goal 名称均在 `docs/gateflow/`。全称前缀分别为 `upload-material-um-` 和 `upload-material-`。

| 标签 | 正式语义来源（adjudication；goal／补充） | slice／精确成功断言 |
| --- | --- | --- |
| O05F01 | `o01-o06-oracle-adjudication.md`；`o05-required-identity-goal-20260929.md` | S1：所有 action 的 form/name 缺失、空、纯白在 ID／lifecycle 前 typed 拒绝。 |
| O06F01 | 同上；`o06-name-length-goal-20260929.md` 后续 240 选择 | S1：trim 后 239/240 接受、241 拒；emoji/组合字符按码点；不截断、不 NFC。 |
| O07F01 | `o07-oracle-adjudication.md`；`o07-ids-goal-20260929.md` | S1：所有 material 公开输入 internal ID 移除；持久字段／结果内部 ID 保留。 |
| O07F02 | 同上、`o08-oracle-adjudication.md` 与 ID goal | S1：完整 seed 后 document_id None 自动生成、显式空拒、mismatch 拒、exact 接受。 |
| O09F01 | `o09-oracle-adjudication.md`；`fiscal-goal-20260929.md` | S1：可选 year，整数（拒 bool），1800..2100 含端点，非法先于 seed。 |
| O10F01 | `o10-oracle-adjudication.md`；同 fiscal goal | S1：唯一 normalize_fiscal_period；六值／空转 None；tool 显式空文本原参数拒绝。 |
| O16F01 | `o16-oracle-adjudication.md`；`o16-action-files-goal-20260928.md` | S1：auto/create/update ≥1 files、delete=0；非法组合不读目标／丢弃 files。 |
| O17F01 | `o17-oracle-adjudication.md`；`o17-form-goal-20260929.md`、PR6-F1/F2/F3 | S1：form 唯一 strip/upper，direct、市场、batch、事件/meta/manifest 同值。 |
| O25F01 | `o25-oracle-adjudication.md`；`o25-primary-goal-20260929.md` | S1：exact 唯一 role、全原件转换；A→B→B（末次逆序）ID 稳定、v1/v2/v2，read/process 消费 B。 |
| O21F01 | `o21-oracle-adjudication.md`；`content-failure-goal-20260929.md` | S1：当前损坏原件 safe label、既有 content code、五字段贯通、stored=0、无部分材料。 |
| O22F01 | `o22-oracle-adjudication.md`；同 content goal | S1：filing/material 真实 read_bytes 的 0-byte 共同 empty_input_file、hint/label 同源。 |
| O12F01 | `o12-oracle-adjudication.md`；`o12-company-goal-20260929.md`、PR5-F1/F2/F3、O34 | S2：同版状态下条件 name 受理、独立公司 commit、alias 最终 guard、active-only 同源双摘要。 |
| O13F01 | `o13-oracle-adjudication.md`；`o13-tombstone-goal-20260929.md` | S2：首删／重删／恢复／再删，重删业务字节、revision、时间、manifest 不改。 |
| O14F01 | `o14-oracle-adjudication.md`；`state-goal-20260929.md` | S2：active create 非overwrite same/diff 均前置 target exists，零业务写。 |
| O15F01 | `o15-oracle-adjudication.md`；同 state goal | S2：missing update 含 overwrite、never delete 前置 target missing，tombstone 不当 missing。 |
| O18F01 | `o18-oracle-adjudication.md` 补充裁决；`o18-amended-goal-20260929.md`、PR4-F1～F6 | S2：八格、metadata_updated、实际 published_amended；true 发布后默认 false delete 仍投影 true。 |
| O33F01 | `o33-oracle-adjudication.md`；`o33-concurrency-goal-20260929.md`、E01 | S2：同 exact identity/role/amended/company+aliases 并发才 verified skip；真实双 CLI 一成功一 skip。 |
| O20F02 | `o20-oracle-adjudication.md`；`o20-xbrl-runtime-goal-20260929.md`、最新 PR10-F1/F2、§1正式平台修订 | S3：macOS候选组合/真实positive已可核＋受控taxonomy/隔离＋合法真实instance CLI→Docling→manifest；必要同版外层边界/继承/取消机制已核收、可生成候选；产品部署/production spawn/真实CLI→manifest仍由S3验收，不删O20F02；Linux/Windows按用户修订后续验证。 |

**只分三片**：S1 是“同一合法输入稳定地转换并登记主源，非法内容同源失败”；G1/G2/G4 相互贯通一次完成，避免只修 owner 而消费者仍重算／截断。S2 是“已接受请求对当前状态只做被授权的发布，竞争仍得可信终态”；G3/G5 共用同版 view／公司阶段／双 guard／amended，不能把幂等规则分成下一片让竞态修复重复改状态机。S3 是“受控部署环境中的真实 XBRL 转换并提交”，其成立依赖第三方／平台资源，不应把 platform、taxonomy、探针分别拆产品 slice。

不减为一片：三种完整验收分别为输入→转换→默认源、状态→条件发布→并发终态、部署→真实 XBRL；把XBRL外部资源及技术证据阻塞与全部本地状态修复放在一次implementation/review pass会扩大同次重叠变更和证据归因，且不能独立评估本地contract。S1/S2连续串行集成，不按文件、模块或标签设gate；S3前置P0是plan/fix内证据工作，不是第四片或自造gate。后续PR review只在S1+S2+S3与aggregate全完成后做。

## 5. S1：完整准入、显式主源与内容失败传播

### 5.1 目标／前提／完成边界

目标：合法请求的 canonical 业务身份和 exact primary 从入口贯穿转换、存储和默认读取；非法静态输入与损坏内容在正确 owner 被识别。前提是本文与真实源码同版 planreview 接受，已有资产／日期／取消合同保持。S1 不实现 state-aware 目标／条件 company name／amended 发布／并发再裁决，它们全在 S2；S1 验收健康 fresh 和已存在合法材料、成功/内容失败链，不声称 S2 的晚期状态错误已修。

### 5.2 契约、函数和明确迁移

1. **身份 owner 不迁下游**：在 `pipelines/docling_upload_service.py` 定义 frozen/slots `MaterialUploadIdentity`，required 字段 `form_type: str`、`material_name: str`、`fiscal_year: int | None`、`fiscal_period: FiscalPeriod | None`、`document_id: str`、`internal_document_id: str`。纯 `normalize_material_form_type(value: str) -> str` 只 strip/upper。`build_material_ids(*, form_type: str | None, material_name: str | None, fiscal_year: int | None, fiscal_period: str | None, document_id: str | None) -> MaterialUploadIdentity` 替换旧 tuple API，无兼容 overload／re-export。
2. 该 builder 依次校验 form 必填→name 必填→trim 名称 ≤240→year 域→复用 `domain.filing_semantics.normalize_fiscal_period`→完整合法 seed→显式 ID 空→mismatch。身份 owner 对六新 code 直接抛 typed `FinsUploadUsageError`，failure 只由 U factory 产生（REQUEST），保 cause；period 非法复用 U 的 `UNSUPPORTED_FISCAL_PERIOD`，不留通用 ValueError 供各入口自行分类。六 code 与具体触发依次对应 form缺失、name缺失、trim后超240、year类型/域非法、显式document_id空、与完整seed生成ID不符；identity fact 构造也复用这一校验 owner，不新建异常映射。period 缺省/null/空/纯白为None；非空仅`FY/H1/Q1/Q2/Q3/Q4`，strip/upper后判枚举；任意值与超长值均`UNSUPPORTED_FISCAL_PERIOD`，不新增材料财期长度规则、不使用filing的`FISCAL_PERIOD_TOO_LONG`。具名常量 `MAX_MATERIAL_NAME_CODE_POINTS=240`、`MIN_MATERIAL_FISCAL_YEAR=1800`、`MAX_MATERIAL_FISCAL_YEAR=2100`；不借摘要展示 budget 充业务规则。fiscal_year 与 period 均可独立省略，不引入互相依赖／默认值。seed 保现 `canonical form|trim name|提供 year|提供 canonical period` UTF-8 SHA-1 + `mat_`，两 ID 相同；ticker、primary、amended、日期不入 seed。
3. fact 的构造校验使用同一私有 pure normalizer／seed helper 拒非 canonical／ID 漂移；`validate_material_upload_ids` 和 material 专属 `_normalize_optional_upload_fiscal_period` 删除，所有真实调用迁移；不要为测试保旧 builder。
4. R 拥有 `validate_fins_upload_material_action_files(action: str, files: tuple[Path, ...]) -> FinsUploadMaterialActionDecision`。decision 仅 required `requested_action: Literal['auto','create','update','delete']`、`pipeline_action: Literal['create','update','delete'] | None`；auto→None，其余同值。leaf 不 resolve/stat/open、不读目标。缺 files 复用 `MISSING_FILES`，delete+files 复用 `FILES_NOT_ALLOWED_FOR_DELETE`，pair 构造校验防非法手工 fact。
5. `FinsUploadMaterialRequest` 删除 `internal_document_id`，增加 `primary_selectors: tuple[Path, ...]=()`，保留输入 occurrence。raw 入口保留输入直到 admission；handoff 中的 request.files/primary_selectors 保存 A 一次规范化后的同序路径（raw document_id 仍是断言），constructor/replace 校验只做 canonical facts 的纯比较，不再次 resolve/expanduser。filing handoff 同样保存首次 A 规范结果，不能 constructor 再规范一次。`ValidatedFinsUploadMaterialRequest` 增 required identity／action_decision；保原 request／file_selection／asset_plan。factory 与 constructor/validate 使用同一静态事实 owner，拒 `dataclasses.replace` 的 request/role/identity 漂移。规范化 request form/name/year/period 与 identity 同值，raw document_id 仍是可选断言，不把生成 ID 填成“用户输入”。
6. R 的 `_admit_material_upload_facts`：ticker/alias→action→source kind→action/files→既有日期→完整 identity→现资产 planner 含 primary，全部早于目标读取、job/handle/producer/lifecycle。`_upload_request_summary`、`_upload_request_document_id`、progress 读取 identity，不对 raw 再 strip/upper/hash；request intent 的 auto 保留，与 resolved_action 独立。
7. 唯一 exact selection 纯算法从 R `_project_fins_upload_filing_selection` 迁到 A=`upload_asset_plan.py`，名 `project_upload_primary_selection(*, files: tuple[Path, ...], primary_selectors: tuple[Path, ...]) -> UploadPrimarySelection | UploadPrimarySelectionFailure`。projection 的 required primary/companions 为 Path 和 tuple；closed `UploadPrimarySelectionFailure` 恰为原五项 `MISSING_FILES/DUPLICATE_FILE_PATH/MULTIPLE_PRIMARY_SELECTORS/MISSING_MULTI_FILE_PRIMARY/PRIMARY_NOT_IN_FILES`。所谓四 selector code 是后三项加 delete 专用 `PRIMARY_NOT_ALLOWED_FOR_DELETE`，不是五项之外再加四项；映射/失败出口见§5.2.1。算法只比较 A 已规范 path identity，不读字节、不规范路径第二次、不产生 UI 文案。filing caller 机械迁移，移除旧私有算法/类型，不留 wrapper。
8. `UploadAssetPlan.filing_primary_original_name` 替换为中性 `primary_original_name: str | None`。upsert 必须 exact 对应一个 pair，delete 必为 None。material `converter_pairs == ordered_pairs`；filing converter 仅 primary。`plan_upload_assets` 增 required material selector 参数（filing caller 显式空 tuple），保原数量→路径／名称／格式的已裁顺序后做 selector projection；delete+primary 在合法零 files 下直接抛 typed `UploadPrimarySelectionError(UploadPrimaryDeleteFailure.PRIMARY_NOT_ALLOWED_FOR_DELETE)`，不解析该 selector 的目标文件。正常 upsert 先完成数量→路径/名称/格式，再规范 selector 并调用同一 pure selector；其失败由 A typed error 退出、U 唯一映射、R 消费；不得 material selector 整体前移至 planner 前。不要因新 selector 改 O04/O23 首错或去重 occurrence。
9. `_build_pending_assets` primary 由 plan 所选 pair.docling_name 赋值，非首项也转换所有原件。`docling_storage_name`（A:267）原样复用 full-basename；不在 D/read/CLI 重建 stem 命名。
10. D `_build_upload_source_fingerprint` 入参改中性 primary 名。filing 序列化与 skip-safe 字节保持；material 用已读 originals 的 `{name, sha256, size, source}` descriptor：单文件保现列表 payload（唯一 role）；多文件 role payload 具名版本常量 `MATERIAL_PRIMARY_ROLE_FINGERPRINT_VERSION=1`、`fingerprint_version/primary/companions`，companions 按 original name 排序，primary exact descriptor 一份。同 B 正逆序同指纹，A/B 异指纹；amended 不入。材料 basename 已唯一，skip-safe=true，不造不可达 unsafe-material 支路。版本继续 `_resolve_document_version`，不新建版本算法。
11. `MaterialManifestItem`增required `primary_document: str`。`source_meta_contract.py`新增`require_material_source_meta_primary_document(meta: Mapping[str, JsonValue]) -> str`只严格读取非空文本；缺字段KeyError、类型/空值ValueError。exact Docling成员验证在现`_fs_source_integrity.py`新增`validate_material_source_primary(*, source_meta: Mapping[str, JsonValue], source_directory: Path) -> None`，复用现`:636 _parse_declared_source_files`及`:964 _trusted_primary_document`，要求selected声明角色为既有DOCLING常量，非法声明/未命中/错角色ValueError；不复制files parser，不读/转换字节。source mutation在持writer、已有完整files声明的source创建/replace/delete投影前调用该校验；inspector同一声明链复用，不能只比primary字符串。
12. manifest字段投影保在storage owner，避免domain模型import仓储eager `__init__`形成repo/domain环。新增`storage/source_manifest_contract.py`的pure `project_material_manifest_item(meta: Mapping[str, JsonValue]) -> MaterialManifestItem`：读strict primary（S2再读amended/is_deleted），调用`MaterialManifestItem.from_source_meta(meta, *, primary_document: str)`（S2增required amended/is_deleted）完成唯一projection；模型接显式typed fact、无下游默认。现source-core六个投影点与integrity`:1220 _canonical_manifest_item`消费该helper，不另拼字段。S1修改`to_dict`触及签名为`JsonValue`可严格检查返回。新schema起库，不迁移旧material角色；其它material producer真实caller必须供已有source primary，无法提供则具体blocked，不fixture默认。这里两函数分别做字段投影与完整声明验证，不能把projection helper当完整资产inspection。
13. 内容 owner `_build_original_assets` 对两 kind 读到 `b''` 均抛 `FinsUploadFailureError(fins_upload_empty_input_failure(canonical label))`，转换次数=0。`_build_pending_assets` 每文件 catch `DoclingConversionError` 时按 `pair.path.name` 用 `direct_events.canonicalize_fins_public_file_label` 包装既有 reason，`raise ... from exc` 保 cause。取消异常独立，不投成 content。两处 owner log 由 Filing 改成上传中立文案。
14. `fins_upload_failure_from_exception` 第一分支对 `FinsUploadFailureError` 返回 **同一 `.failure` 对象**；不得再覆盖 label/hint。普通 Docling/I/O/公司冲突分类保持。tool `_validate_upload_file_path` 仅检查路径存在／普通文件，删除 st_size 内容断言（filing 同样走共同原始字节 owner）。
15. U=`upload_usage_contract.py` 唯一新增 code：`MISSING_FORM_TYPE`、`MISSING_MATERIAL_NAME`、`MATERIAL_NAME_TOO_LONG`、`INVALID_MATERIAL_FISCAL_YEAR`、`EMPTY_DOCUMENT_ID`、`DOCUMENT_ID_MISMATCH`；既有财期 code 与四 selector code 复用，不从 CLI 发明同义枚举；selector factory 显式 required source_kind，由 U 唯一持有 code/category/message/hint，material 提示“多文件材料必须明确指定唯一主文件”，不输出 filing 业务对象；filing 原 REQUEST 类别与 message 逐字保持。required `FinsUploadUsageFailure.hint: str`、`file_label: str | None`，category/code 双向约束保留；普通／planner／format factory 均显式赋值。format owner 提供自己 typed message/hint/label，U `fins_upload_format_usage_failure(error: FinsUploadFormatError) -> FinsUploadUsageFailure` 统一装箱；原 `(usage,hint)` planner 接口改为单 fact，全部 caller 迁移，不双真源。
16. 新增六 code 映入 public failure reason 的 usage code 集，wire值依次冻结为`missing_form_type/missing_material_name/material_name_too_long/invalid_material_fiscal_year/empty_document_id/document_id_mismatch`；S2新增`DELETE_TARGET_MISSING="delete_target_missing"`。这些是本计划拟实现的技术命名，不冒充正式裁决已规定的新API；对应业务拒绝已由goal确认。identity提示说明“document_id 仅验证生成身份一致，不能覆盖”，name 提示说明去首尾白后 240 Unicode 码点，year 提示说明 1800..2100，period明确列六值。具体可行动中文由 U 单点拥有，不把旧笼统文案当 oracle。`FinsUploadFailureReason.retry_hint: str | None` 全局 contract 保留；只有 usage／target／format fact 自己 hint 必填。既有content五字段文案／hint保`upload_failure.py`当前owner逐字值；usage target正式裁决没有冻结字面文案或CLI exit，不创造额外验收。


### 5.2.1 A/U/R 的封闭失败出口与一次路径规范化

- **A 唯一算法/资产 owner**：`normalize_upload_asset_path` 保现 expanduser/resolve 规则。material `plan_upload_assets(*, source_kind: SourceKind, operation: Literal['upsert','delete'], files: tuple[Path, ...], material_primary_selectors: tuple[Path, ...], filing_selection: FinsUploadFilingFiles | None = None) -> tuple[FinsUploadMaterialFiles | FinsUploadFilingFiles, UploadAssetPlan]` 保 success 返回，不以 failure 塞 success tuple。filing caller 显式 material selector 空 tuple；material 不传 filing selection。成功时 primary/companions、plan.pairs、canonical request paths 来自同一规范结果。
- material 保原数量/空files/duplicate路径与名称/格式 owner 及首错；A `_normalize_material_upload_paths` 对每个 files occurrence 一次调用同 helper，保原索引/形状错误；完整 `_validate_material_asset_names`（包括实际 format 校验）完成后，才对每个 selector occurrence 一次调用同 helper，交 pure projection。`~/x`、symlink selector 与 canonical files 使用同一身份规则；不去重 selector occurrence，不用 basename/stem匹配。selector 解析失败由 A 新 typed `UploadPrimarySelectionPathError(input_path: Path)` 包原 OSError/ValueError cause，不并入资产规划枚举；U 映既有 FILE_NOT_FOUND/REQUEST，安全标签仍同 U owner。files 原 OSError 透传及名称/格式失败出口保留，不借 selector 吞掉。
- `UploadPrimarySelectionError` 持 required `reason: UploadPrimarySelectionFailure | UploadPrimaryDeleteFailure`；前者为 pure 算法实际五元 enum，后者只含 delete code。material planner pure projection 返回 enum 时立即抛该 typed error；filing R 在原 static 顺序调用同 A pure projection，遇 enum 同样构造 typed error 交 U；delete+files 先 R leaf 拒，合法零 files 的 delete+primary 再由 A 无I/O拒。filing delete 保原 static 先 files 后 primary 的位置，复用 U 的同一 delete selector 映射。
- **U 唯一语义 owner**：`fins_upload_primary_selection_usage_failure(error: UploadPrimarySelectionError | UploadPrimarySelectionPathError, *, source_kind: SourceKind) -> FinsUploadUsageFailure`，required kind，不从 raw请求、异常文本猜 kind；返回完整 code/category/message/hint/file_label。同 `fins_upload_asset_plan_usage_failure` 与 format factory 都改为单 fact，R 仅 `raise FinsUploadUsageError(failure) from error`，public resolver/tool/CLI 只消费。`_PLANNER_USAGE_CODES/_PLANNER_EXCLUSIVE_USAGE_CODES` 不新增 selector code；ASSET_PLAN 仍仅原规划 reason。U 可 import A 的 typed出口，A 禁止 import U/R。
- 删除 R `_FinsUploadFilingSelectionFailure`、`_FinsUploadFilingSelectionProjection`、`_FILING_SELECTION_FAILURE_USAGE_CODES`、`_project_fins_upload_filing_selection` 的算法/映射真源，迁移 R static与constructor两组调用至 A projection/U factory。R `_normalize_fins_upload_paths`/filing adapter 不保第二套 normalization 算法；filing原规范化失败仍由 U FILE_NOT_FOUND 提示，原首次规范结果传静态 facts/constructor，纯一致性校验不触 FS。D/read/tool 不重选/重规范。保持 filing 原 selector→角色路径/格式顺序，不能把 material planner 顺序套到 filing。

| 实际失败 | A 产生/入口 | U 公开 code / category | 消费/首错承诺 |
| --- | --- | --- | --- |
| MISSING_FILES | pure五元之一；material R action/files先拒、A保规划防绕过 | missing_files；filing REQUEST，material leaf REQUEST，裸 material planner ASSET_PLAN | 原共享 code，不重复计作 selector 新项 |
| DUPLICATE_FILE_PATH | pure五元之一；material A在名称/格式前规划拒 | duplicate_file_path；filing REQUEST，material规划 ASSET_PLAN | 原shared-planner例外保留，两类别合法 |
| MULTIPLE_PRIMARY_SELECTORS | pure五元之一 | multiple_primary_selectors / REQUEST | 多次相同selector也拒；数量不去重 |
| MISSING_MULTI_FILE_PRIMARY | pure五元之一 | missing_multi_file_primary / REQUEST | material/filing 文案按显式kind；filing原字面保持 |
| PRIMARY_NOT_IN_FILES | pure五元之一 | primary_not_in_files / REQUEST | exact canonical path身份，不做basename fallback |
| PRIMARY_NOT_ALLOWED_FOR_DELETE | delete专用typed reason，非pure五元成员 | primary_not_allowed_for_delete / REQUEST | 不规范/访问delete selector目标 |
| selector路径解析失败 | UploadPrimarySelectionPathError（保cause） | file_not_found / REQUEST | 唯一U安全label/hint；不扩大规划枚举 |
| 数量/名称规划失败 | 原 FinsUploadAssetPlanError | 原 code / ASSET_PLAN | U原planner映射，保数量→名称分类优先级 |
| 路径角色/后缀失败 | 原 FinsUploadFormatError | 原 format code / REQUEST | format owner事实经U一次装箱，不改format语义 |

V1/V3 必测 joint-invalid 的数量→路径/名称/格式→selector顺序及上述每个code/category/message/hint；对 normalize helper 的调用次数和canonical路径同源做owner断言（files与selector每occurrence一次，constructor为0），不以 mock重写生产分类。

同一次规范化也包括 A 当前 `UploadAssetPlan.validate:149` 和 `filing_original_storage_name:256`：删除它们再次调用 normalize 的FS检查，改为同 A 私有 pure lexical validator（Path/absolute/no `..`，exact pair/selection身份比较）；规范绝对路径的产生只在 admission 的 A normalizer 边界。constructor不通过“重新解析仍相等”证明规范性，也不重新检查symlink。裸plan的原名称/格式校验仍同owner；material planner先完成该校验再selector，形成最终plan后仅复用pure不变量，不将第二次resolve藏在helper内。原R两处normalize/旧primary类型及所有真实caller全部迁移，验证调用次数须包含plan.validate/filing naming/constructor路径。

### 5.3 实际入口调用图与首错

```text
CLI raw args → _prevalidate_upload_material_request → 共享 admission → 同一 handoff → Service
tool raw JSON → _upload_request_from_arguments → 共享 admission → prepare_observed_upload
Runtime upload/start_upload/start_observed_upload/prepare_observed_upload → _validate_runtime_upload_request
SEC/CN/HK raw façade → 原 ticker/market/company-id 纯准入 → 共享 admission
Service/ProductionFinsUploadRunner → validated façade → SEC/CN workflow
handoff.identity + asset_plan → D.prepare_upload → read originals → 每原件 Docling → prepared mutation
→ commit_prepared_upload_batch → source仓储资产/meta/manifest → storage commit → terminal
terminal.failure → strict parser → summary → direct/CLI/observation 或真实 job 双摘要
source snapshot → get_primary_source → process_material/read（不重选）
```

| 入口 | 锁定顺序／变化 |
| --- | --- |
| CLI 单条 | 原 workspace-path 准入保留；prevalidator raw files tuple 先组合 leaf，再 ticker CSV／机械字段解析，再完整 admission；合法才 `_prevalidated_upload_paths`。delete+files 不 normalize/stat 被拒输入。单个不含逗号的 form 空／纯白传 owner；`,`／`A,` 等 item 结构错误、多个 forms 仍由 CLI 原 parser；显式空 document_id 原 CLI 参数拒绝保留。 |
| Runtime | ticker/alias→action→source kind 的原首错保留；组合→日期→identity→资产/selector。filing 分支不加 material 域。 |
| tool | kind/action/primary 类型词法仍先；material files 只机械投影，组合 leaf 早于目标；form/name 缺失/null→None、字符串 strip 后保空串给 owner；ID 显式空保空串；period 缺省/null→None，显式空文本仍 `_optional_nullable_text` 参数层拒绝。非字符串原错误保留。 |
| 独立 SEC | raw façade 先原 normalize_ticker→US market→build_upload_company_id 纯校验，再共享组合/完整受理；CN/HK 保原 ticker/company-id 顺序，不新增 US 规则。validated 消费者防绕过，但不重算 identity/period/action pair。 |
| batch | `_single_batch_material_form` 机械逗号 split：遍历全部 item 用 stripped 副本判空、保存 raw，先逐项空错后多值错；单 raw 交 batch `_validated_material_form`，它复用唯一 form 函数后保原三类封闭 routing。regeneration argv 保 raw，typed entry→生成 --forms→真实 material handoff canonical 同值。单条 parser 不复用 batch 规则。 |

CLI material 新 `--primary` 复用 ParsedCliArgs.primary append，tool `primary` 对 filing/material 都开放为可选单值 string/null（无 duplicate-key 假合同）；删除 `_upload_primary_selectors_from_arguments` 的 material 拒绝分支，以及 `upload_tool_material_primary_failure` 的否定文案/无消费者字段，不保兼容拒绝。`upload_format_contract.py` 同一文案 owner 同步 CLI material --primary help、tool primary/files/schema：单文件可省略并自动选该文件，多文件必须明确恰好一个精确文件路径，delete不得携files或primary。files说明只要求已存在普通文件；不再说“非空文件才参数合法”。空内容由 S1 真实read_bytes owner 在转换前统一内容失败，stored0；LLM文案只说“文件为空，无法上传；请提供非空文件后重试”，不给模型 planner/原始字节owner/内部error类型等实现术语。CLI material `--internal-document-id` 注册删除；ParsedCliArgs 其它真实消费者若有独立用途保留其自身字段，不能删 filing 内部事实。tool schema 删除此输入且 raw known-field 校验拒旧字段（空／非空都拒），不静默忽略。Service 与 SEC/CN raw façade 删除公开 parameter；结果/source/manifest 仍输出 owner 内部 ID。

LLM-facing schema 在当前字段说明中自足写 form/name 对 material 每动作必填、trim/240码点、可选year为1800..2100整数、可选period为`FY/H1/Q1/Q2/Q3/Q4`（trim/upper；空白为未提供；工具显式空文本仍参数拒）、action/files、单／多文件 primary 与 delete、document_id 断言含义；不让模型理解内部类名。例：`{"upload_kind":"material","ticker":"AAPL","action":"auto","form_type":"MATERIAL_OTHER","material_name":"Deck","files":["a.txt","b.txt"],"primary":"b.txt"}`。例只说明结构，不算真实转换证据。

### 5.4 S1 精确白名单

产品既有文件：

- `dayu/fins/pipelines/docling_upload_service.py`、`sec_upload_workflow.py`、`sec_pipeline.py`、`cn_pipeline.py`：身份消费、primary/fingerprint、内容 reason；保持公司/状态流程待 S2。
- `dayu/fins/ingestion_runtime.py`、`upload_asset_plan.py`、`upload_usage_contract.py`、`upload_failure.py`、`upload_format_contract.py`、`upload_batch.py`。
- `dayu/fins/domain/document_models.py`、`dayu/fins/storage/source_meta_contract.py`、新`source_manifest_contract.py`、`_fs_source_document_core.py`、`_fs_source_integrity.py`：只primary manifest的strict字段/已声明Docling成员校验、唯一projection及触及签名；不改完整性分类/事务策略。
- `dayu/cli/arg_parsing.py`、`dayu/cli/commands/fins.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/tools/_ingestion_tool_helpers.py`、`dayu/fins/service_runtime.py`、`dayu/service/fins_direct.py`：仅真实参数/类型/事实投影与中立错误路径；无需要则零 diff，不造 facade。

测试：`tests/fins/test_upload_asset_plan.py`、`test_upload_format_contract.py`、`test_upload_usage_contract.py`、`test_upload_failure.py`、`test_docling_upload_service.py`、`test_docling_upload_service_integration.py`、`test_upload_batch.py`、`test_sec_pipeline_upload_material_stream.py`、`test_sec_pipeline_upload_filing_stream.py`、`test_cn_pipeline.py`、`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_fins_service_runtime.py`、`test_fins_storage_atomicity.py`、`test_fins_read_runtime.py`、`test_source_meta_contract.py`、`test_filing_upload_publication.py`、`tests/cli/test_fins_commands.py`、**`tests/cli/test_upload_filings_from_command.py`**、`tests/service/test_fins_direct.py`。允许新增 `tests/fins/test_material_identity_contract.py` 集中 pure owner contract，避免把大文件用 fake 表面验收掩盖。fixture 只在这些真实测试模块创建全新合法 schema，不修改历史 Raw／既有 official fixture。

另新增`tests/fins/test_source_manifest_contract.py`验证投影、strict字段、实际创建/replace/delete调用和manifest/model依赖无新环；成员校验用真实file声明，不fakeparser。文档允许`README.md`、`dayu/fins/README.md`、`tests/README.md`，按§10判断；registry不在白名单。

### 5.5 S1 验证断言／停止

| 验证 ID | owner 级完整断言 |
| --- | --- |
| V1 输入／首错 | 全动作 form/name None/空/纯白；239/240/241，emoji/组合码点，year None/1799/1800/2100/2101/-1/0/10000/bool；六 period、padded、empty、任意/241；有无 year×有无 period 四格；joint-invalid 按上表首错。禁止 builder seed、target read、started、Service factory（CLI）、job/handle、executor、公司/材料发布。 |
| V2 IDs/canonical | None/exact/empty/mismatch document_id；material public old internal 参数空/非空均未知；全有字段表面 canonical 等于 identity；无 raw 再算。batch typed entry→实际 argv parser→共享 handoff 是真实路径，不只断言 fake service 捕获值。 |
| V3 role | 单文件默认/显式、非首 primary、pure五元/四selector code逐项及类别/文案、重复同 selector仍拒、同 basename不同路径不误命中；100 全转换/101拒保持；same-stem异后缀 helper不变；constructor/replace漂移拒。 |
| V4 publish/read | 真实 Fs新库 A→B→B末次逆序：ID/internal ID稳定、v1/v2/v2、末次零转换、原件/Docling/meta/manifest/snapshot同角色；旧 snapshot保持旧primary，新snapshot看B；真实 processor factory默认源B。filing仍只转主源、伴随原样、指纹字节及 skip-safe不变。 |
| V5 content链 | 单空、有效+空、空+有效，真实 bytes判定converter=0；单损坏PDF/DOCX及换位置多原件，当前 label/cause、stored=0、无材料source/blob/meta/manifest部分发布；长/控制字符标签复用canonicalizer，不泄露绝对路径；typed resolver对象identity不变。 |
| V6 入口/取消 | 真实tool调用（经过schema/参数投影/admission/生产workflow与真实Fs，只对转换outcome作受控注入）：material双文件+primary=b成功且登记b；无primary报missing_multi_file_primary/REQUEST与material文案；primary不在files、单文件默认/显式、delete+files/primary及0-byte内容失败分别锁owner。schema/help/files断言单/多/delete规则，反例断言不再包含“material不得提供primary”“必须非空文件”等旧否定句，不只测试selector函数。US/CN/HK、CLI、tool/direct均五字段同owner；tool observation FAILED且无job（queried-but-absent）；另 start_upload真job双摘要；转换前/中取消走cancelled，晚取消不覆写已提交。合法公司后内容失败保留公司。 |

使用真实 Fs和受控 converter只注入转换 outcome，不能 fake 仓储证明提交。现有“第一项 primary”“material role=None”“tool空文件 invalid_argument”“转换原异常无label”的偶然断言迁往新 owner contract。S1一个 implementation pass 集中完成V1～V6，再一次正式 slice review/fix/re-review/accepted commit闭环；可内部保存技术进度/证据，但不增gate/checkpoint、不按字段/文件微拆。完成信号是 V1～V6、受影响测试、覆盖率、pyright及docs decision有实证，slice review findings闭环；正确 owner／公开分类／合法 producer 无法表达时明确 blocked，不在下游补默认。

## 6. S2：同版受理、独立公司与材料条件发布、并发可信终态

### 6.1 目标／前提／唯一 owner

前提 S1 accepted+integrated 后核真实接口/hash；同一 WU内串行，不采用旧 G1/G2 proposal 的“已存在类型”。本片实现 O12/O13/O14/O15/O18/O33 一个状态发布行为，既有 S1输入／role／failure合同不重裁。公司 pure decision归 `upload_company_meta.py`；公司 identity/alias/commit归 storage与`company_meta_contract.py`；材料完整性/opaque revision/meta/manifest归 storage；材料行动与竞争skip归新增 `pipelines/material_upload_publication.py`；取消能力仍归 Host/runtime与既有D publication lifecycle，不新建取消真源。

### 6.2 精确新增类型与接口（均为本候选设计，非现存 API）

| 文件／接口 | 必须实现的合同 |
| --- | --- |
| `storage/repository_protocols.py`：`MaterialUploadPublishedState` | frozen/slots required `company_meta: CompanyMeta | None`、`source_integrity: SourceIntegrityClassification`、`source_meta: Mapping[str, JsonValue] | None`、`publication_identity: MaterialUploadPublicationIdentity | None`。meta深层不可变；revision仅用classification，不复制。MISSING/UNSAFE无meta/identity，COMPLETE可信active/tombstone有meta，REPAIR_REQUIRED可信meta可用但无identity且受理拒。 |
| 同文件：`MaterialUploadOriginalDescriptor`／`MaterialUploadPublicationIdentity` | 前者required `name: str/sha256: str/size: int/source: Literal['original']`（复用现仓储original资产标记，区别于source provenance的user_upload），来源同次inspector；后者required `ticker: str/document_id: str/internal_document_id: str/form_type: str/material_name: str/fiscal_year: int \| None/fiscal_period: FiscalPeriod \| None/source_fingerprint: str/primary_document: str/originals: tuple[MaterialUploadOriginalDescriptor, ...]/amended: bool/is_deleted: bool/document_version: str`。frozen/slots，构造拒重复/空／非法enum/type，不计算业务ID或重新hash指纹；全部由source meta＋同次完整资产inspection产生。存储不从文件名反推primary role，直接用已验证primary Docling名；candidate由D已产生的同一descriptor/plan投影。 |
| 同文件：`MaterialUploadStateRepositoryProtocol.read_material_upload_state(ticker: str, document_id: str) -> MaterialUploadPublishedState` | published同一publication guard内strict company/identity＋exact material inspector；无公司目录时只读MISSING，create_directories=false，不发布company descriptor。复用底层path/lock/JSON机制，不新造parser。 |
| 同协议：`read_material_upload_state_in_batch(batch: BatchToken, document_id: str) -> MaterialUploadPublishedState` | begin取得writer后、尚未stage材料时读取acquisition-copy同版view；不能把自己staged内容当竞争winner。 |
| 同协议：`validate_material_upload_state(*, ticker: str, document_id: str, expected_source_state: MaterialUploadPublishedState, expected_company_meta: CompanyMeta | None) -> MaterialUploadPublishedState` | 一个guard内复验source presence/opaque revision/business identity与company exact事实/identity，再返同版实际state；用于执行前与无mutation skip。source条件只比较source部分，company只比较显式期望，防把自己合法公司提交当漂移。 |
| 同协议：`register_material_upload_preconditions(*, batch: BatchToken, expected_source_state: MaterialUploadPublishedState, expected_company_meta: CompanyMeta | None) -> None` | 当前writer view先校验并登记required typed条件，publication guard内swap前再次复验；无需callback/profile。登记与final guard复用同一个仓储条件校验owner，保既有最终guard，不新第二状态机、不让publication反读重算；writer保护不是删除final guard的理由。source变动用`SourceIntegrityRevisionConflictError`，company变动用`CompanyMetaConcurrentUpdateError`；alias占用仍原alias error先于material相同性。 |
| 同协议：`commit_material_upload_batch(batch: BatchToken) -> MaterialUploadPublishedState` | 只接已经登记材料条件的batch，消费一次capability；共享现commit底层；guard内从实际stage→published事实形成final快照，正常提交/cleanup/release完成后才能返。它增加材料条件与publication-final值，是有效语义接口，不是commit透传wrapper。首删/重删published_amended必须来自该实际meta。 |
| 同协议：`commit_material_upload_company_batch(batch: BatchToken) -> CompanyMetaCommitOutcome` | 只接有显式company intent、尚open的材料公司阶段batch；按原company identity/alias锁序做同源merge；结果等于当前published且无identity/alias增量时不swap/更新时间，正常终态关闭后返回现meta，否则原独立公司提交。这个material专属no-op合同不改变filing/general commit的返回／warning语义。 |
| `storage/fs_material_upload_state_repository.py`、`_fs_material_upload_state_core.py` | 显式core-backed material仓储实现；仿filing机制，复用exact inspector与锁、immutable JSON，不复制路径/公司parser；通过 `_fs_storage_core.py` 与`storage/__init__.py`正常装配/导出新公共合同，不兼容旧API。 |
| `ingestion_runtime.py`：`MaterialUploadStateAdmission` | required `observed_state: MaterialUploadPublishedState/resolved_action: Literal['create','update','delete']/company_decision: UploadCompanyMetaDecision`，目标取S1identity，不复制ID/日期/role为godbag。validated handoff加required state_admission，pure构造一致性检查，不做I/O。 |
| R：`admit_fins_upload_material_request(request: FinsUploadMaterialRequest, *, state_repository: MaterialUploadStateRepositoryProtocol) -> ValidatedFinsUploadMaterialRequest` | S1静态facts→读exact state→完整性→action/target→pure公司decision→完整handoff。CLI workspace prevalidator在Service factory前用同owner；Runtime/独立pipeline显式注入同仓储set，所有create/constructorcaller迁移。不能 optional repository或fallback。 |
| D：`_PreparedMaterialMetaMutation` | required ticker/document/internal ID与desired_amended；不塞request日期/company/revision。content／delete／metadata三类封闭mutation保明确union，不做多nullable字段godbag。 |
| source仓储：`update_material_amended(*, batch: BatchToken, document_id: str, amended: bool) -> None` | 已登记条件的batch中从可信既有meta为基底只改amended及维护updated_at/revision/manifest字段；其它业务字段、资产、日期、form/name/ID/version/fingerprint/首次时间逐字段不变。 |
| publication owner：`arbitrate_material_upload_publication(*, request: ValidatedFinsUploadMaterialRequest, fresh_state: MaterialUploadPublishedState, candidate: MaterialUploadPublicationIdentity, expected_company_meta: CompanyMeta | None) -> MaterialUploadPublicationDecision` | pure闭集PUBLISH／IDENTICAL_SKIP／CONFLICT，仅同auto非overwrite健康active允许竞争skip，§6.5锁条件；不捕获I/O当状态。decision不产生新公开status/code。 |
| 同owner：`execute_material_upload_company_stage(...) -> CompanyMeta \| None`及`execute_prepared_material_publication(...) -> MaterialUploadPublicationOutcome`（唯一完整签名见§6.7） | 公司阶段先完成，转换后材料阶段消费required expected_company_meta；outcome仅actual published_state＋UploadOperationResult（取消无published_state）；生命周期复用D同一个commit/rollback机制，市场只机械消费。不得第二套token终态helper。 |

`MaterialUploadPublicationIdentity` 不需要新的持久 primary-original字段或重新解析 raw名字；source meta已有files/source/hash/size/primary，S1角色指纹已承诺角色，严格inspector给完整性。新增持久业务字段仅 S1 manifest primary、S2 source/manifest required amended。opaque revision、manifest维护时间是storage治理，不进入LLM推理依据。

source_meta_contract新增 `require_material_source_meta_amended(meta: Mapping[str, JsonValue]) -> bool`（严格bool缺字段KeyError、错类型ValueError），所有source／manifest／read／terminal复用该reader；不默认false。MaterialManifestItem required amended，S1唯一projection helper读出strict primary/amended/is_deleted并调用模型最终`from_source_meta(meta: Mapping[str, JsonValue], *, primary_document: str, amended: bool, is_deleted: bool) -> MaterialManifestItem`；模型不importstorage。所有合法materialproducer显式提供布尔值（非upload按该producer已成立的修订事实），不以fixture默认反推产品规则。若存在producer无法提供真实值，列caller/schema所有权blocker，不能新造业务默认。

O13共享严格删除事实：source_manifest_contract新增`project_filing_manifest_item(meta: Mapping[str, JsonValue]) -> FilingManifestItem`，调用现strict is_deleted reader后传模型新required参数`FilingManifestItem.from_source_meta(meta, *, is_deleted: bool)`；material同helper已读strict删除事实。删除两模型`.get(...) is True`默认；source-core与integrity全部旧classmethod caller迁唯一projection helper，无兼容签名。仅对完整source的canonical投影收口，不扩processed快照/一般文档加载规则。重删no-op在source ownerstrict true且整份source/manifest可信后成立，不能先no-op吞缺字段/nonbool。

### 6.3 时序、guard与异常

1. 完整受理只读状态；UNSAFE/REPAIR_REQUIRED先fail closed；稳定非法action/target先公司name决策。缺name用U既有`COMPANY_NAME_REQUIRED`。prevalidation抛typed usage／typed integrity/operational，早于started/job/handle/company/material业务写。必要read lock与业务副作用区分记录。
2. 接收到执行开始之间用storage只读validator复验source/company。除§6.5受控auto竞争特例外，已接收后漂移映射既有`source_publication_conflict`，不重新投稳定输入缺name/target错误。alias优先原company owner。
3. 独立公司阶段消费已经受理的`UploadCompanyMetaDecision`，不调用旧`stage_company_meta_for_upload`重读重判；删除旧helper及其唯一SEC/CN使用/exports。stage意图以单独company batch，经`commit_material_upload_company_batch`提交，正常outcome.company_meta为post-company期望；keep/skip无intent只读guard验证观察值，不开启空公司batch重写树。`company_meta_contract.merge_company_meta_for_commit`负责canonical merge／时间不变／别名真源。
4. 完成公司阶段后D读取originals一次并形成role-aware fingerprint；健康同指纹同amended非overwrite得到待验证skip候选（不得D提前返回最终skip）。同指纹异amended得到metadata-only候选，不转换；overwrite或异指纹／tombstone恢复转换全部原件。失败/取消可保独立合法公司，材料无本请求成功。
5. 材料mutation先begin取得ticker writer、read同一次fresh view，判相同性／漂移，register source+post-company条件→stage一文档→最终cancel checkpoint→commit。writer锁持有期间不能让另一个同tickerwriter“先提交”；所有漂移测试的B提交在A begin之前。
6. 普通顺序skip或健康重删no-op使用同一guard核实际source/company，严格完整性/alias/state通过后，无业务swap/新revision；若已开空batch则rollback/释放全部成功后才返回skip/deleted。rollback/release失败是operational，不保成功。首次delete的final bool与重删同源，不读request默认amended。
7. storage final guard在原recovery／company identity／publication锁序内复验登记条件，源时间/JSON不当revision；final投影来自实际已发布source。prepare/meta/manifest staged均不算上传成功。
8. D`commit_prepared_upload_batch`扩封闭material mutation与typedfinal消费；filing分支原返回与取消线性化保持。caller进入commit前标记capability转交，此后不读取消、不rollback、不catch异常重试，不“读回碰巧相同”改skip。
9. 真I/O、锁、cleanup/release异常保主异常/次因及durable事实；COMMITTED后release可使命令failed，但不能说“必未发布”。本片不要求新增全局indeterminate成功状态，不实施download certainty residual；因不对异常裁success/skip，既有异常合同足够fail closed，不把旧preparation B2当必须新建泛化协议的理由。
10. material company-concurrent/source-guard失败由publication owner包装既有typed public conflict；filing旧CompanyMetaConcurrentUpdateError→storage_io投影保持。不在global mapper按异常文本猜request kind。

### 6.4 状态与 amended 完整矩阵

| 权威source状态／请求 | 结果 |
| --- | --- |
| MISSING：auto/create、有合法files/company | create v1。 |
| MISSING：update（overwrite任意）／delete | 前置UPDATE_TARGET_MISSING／新增DELETE_TARGET_MISSING typed usage；公司和材料零业务写。 |
| COMPLETE active：create、overwrite=false | 同／异bytes均CREATE_TARGET_EXISTS前置拒。 |
| COMPLETE active：auto/update，或create overwrite | 动作先合法，再按下表八格。 |
| COMPLETE tombstone：delete | deleted no-op，现周期meta/manifest/assets/revision/times原字节不动。 |
| COMPLETE tombstone：auto/update | 恢复同ID/首次时间、清删除态；同指纹保版，异指纹按既有版本owner升版；恢复不能因删除本身升版。 |
| tombstone：显式create无overwrite | O14未裁新语义，保现source create拒绝，不新增typed规则／自动恢复。sharedprecondition区分active/tombstone，保仓储拒绝；测试只锁该existing owner拒绝，不把它升新oracle。 |
| UNSAFE/REPAIR_REQUIRED：任意action | typed完整性/operational fail closed；不当MISSING、不借delete修坏source。 |

`evaluate_upload_overwrite_precondition`扩显式source-kind／typed状态输入与DELETE_TARGET_MISSING；不拿自由meta None猜COMPLETE。filing原语义/文案保持，material只在上述已裁格前置拒绝。U producer target code显式required `source_kind: SourceKind`，一码双kind文案／hint同owner：filing CREATE/UPDATE原文逐字保持，material中立业务目标；DELETE仅material。public code集含三target code并映usage；不加同义runtime enum。

| role-aware指纹 | amended | overwrite | 业务status／Docling／内容版本 |
| --- | --- | --- | --- |
| 同 | 同 | false | skipped／0／保 |
| 同 | 异 | false | metadata_updated／0／保 |
| 同 | 同 | true | ok／全部／保 |
| 同 | 异 | true | ok／全部／保，实际标记改 |
| 异 | 同 | false | ok／全部／升 |
| 异 | 异 | false | ok／全部／升 |
| 异 | 同 | true | ok／全部／升 |
| 异 | 异 | true | ok／全部／升 |

首次为v1；amended不参与身份／内容指纹。metadata-only不得用`_build_upsert_meta`与request dates覆写已有其他业务字段。source/manifest内部字段`amended: bool`；material request摘要/started为`requested_amended: bool`；material结果、summary、LLM read现有`documents`／`recommended_documents`为required `published_amended: bool | null`：ok/skipped/deleted/metadata_updated必storage-final bool，failed/cancelled为null（不否定以前durable材料）。不得给filing改名或processed快照冒当前事实。

metadata_updated→terminal completed，requested≥1/stored=0；ok stored=requested≥1，skipped requested≥1/stored=0，delete 0/0。`FinsUploadPipelineResult`增加required `source_kind: SourceKind`和`published_amended: bool | None`，校验material新状态（所有真实constructor显式供kind）、filing拒metadata_updated；`from_pipeline_json`沿现required caller source_kind传参，不能从payload猜kind，不要求为此在pipeline JSON新增source_kind。材料JSON必含published_amended，缺字段拒、非bool/non-null拒；filing保持既有JSON形状且typed值为None。summary本已有source_kind，消费同typed fact；Service/direct投影同步，material warning限制不扩。LLM自足例：`{"status":"metadata_updated","requested_file_count":2,"stored_file_count":0,"published_amended":true}`；失败例`{"status":"failed","published_amended":null,"failure":{"kind":"content","code":"empty_input_file","message":"文件为空，无法上传","retry_hint":"请提供非空文件后重试","file_label":"empty.txt"}}`。解释skip/delete中的标记是当前／最后发布材料事实，并非这次请求写入。

upload job no-runner与generic exception都产生单typed reason→同一result_summary.failure／failure_summary→已有save_accepted_upload_terminal_if_active；CANCELLED仍既有active-only取消保存，终态已落盘则不改。终态后progress发射异常只记录／保原record，不能进入共享message-only覆写路径；不改download/preprocess `_save_failed`。observation无job和真job分开验证。

### 6.5 O33 竞争窗口与公司事实

只有请求原意`auto`、非overwrite、非repair、fresh同identity竞争可将旧create意图裁verifiedskip。ordinary stale状态不得放宽：公司/alias先guard；fresh必须COMPLETE active user-upload、精确canonical ticker/document/internal ID/form/name/year/period与candidate相同、相同原件descriptor/role-aware fingerprint及primary_document、相同amended；所有原件／Docling／meta／manifest完整。不同bytes/role/amended、缺件/坏hash、tombstone、额外company字段/时间/alias变动均不skip。

fresh公司“从None变为这次相同请求本可产生的事实”与第三方漂移不能混淆：公司owner在其writer/identity guard下对已接受intent做commit-time merge（当前`merge_company_meta_for_commit`已有resolver同版保published分支），仅当canonical身份/名字等价、resolver、aliases与同一意图合并结果完全相同且无增量，返回现meta并不stage/swap／刷新时间；已有company输入时仍检查原non-identity snapshot，任何额外变化冲突。材料post-company期望取该owner正常final值。**不能publication层自行用名字/时间猜“winner刚写的公司”或重新调用name受理掩盖漂移**。必要的no-op判定扩在company commit owner当前intent边界，filing merge契约不改；无额外全局公司语义。

竞争state读取与判断发生在自己commit尚未开始且writer/guard保护同一view时；fresh一次，不从genericconflict/FileExistsError catch再读第二快照/retry。verifiedskip既不重转已做转换，也不stage/physicalswap材料或公司；关闭未提交capability成功才投影。允许竞争败者在winner提交前已转换过原件，不能断言所有竞争skip converter=0；顺序skip应0。一方业务成功，一方skip，只有一份completeactive source及一条manifest，winner后→loser终态业务字节/时间/revision/版本零diff。

### 6.6 S2 精确白名单与验证

产品：S1重叠文件中仅state/事实消费；另允许：

- `dayu/fins/pipelines/filing_upload_publication.py`：仅第5个真实commit caller显式传required `material_state_repository=None`，保原FilingUploadPublicationOutcome返回、warning及capability转交后的取消/rollback线性化；不得改filing规则。
- 新 `dayu/fins/pipelines/material_upload_publication.py`，新 `dayu/fins/storage/_fs_material_upload_state_core.py`、`fs_material_upload_state_repository.py`。
- `dayu/fins/storage/repository_protocols.py`、`_fs_source_integrity.py`、`_fs_source_document_core.py`、`_fs_storage_infra.py`、`_fs_storage_core.py`、`fs_batching_repository.py`、`fs_source_document_repository.py`、`source_meta_contract.py`、S1新增`source_manifest_contract.py`、`__init__.py`；只materialstate/条件/最终值、共享tombstone及公司no-op，不改download状态机。
- `dayu/fins/pipelines/upload_company_meta.py`、`dayu/fins/domain/company_meta_contract.py`、`dayu/fins/domain/document_models.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/tools/fins_tools.py`。
- `dayu/fins/ingestion_runtime.py`、`service_runtime.py`、`upload_usage_contract.py`、`upload_failure.py`、`upload_format_contract.py`、`pipelines/docling_upload_service.py`、`sec_upload_workflow.py`、`sec_pipeline.py`、`cn_pipeline.py`、`tools/upload_tools.py`、`dayu/service/fins_direct.py`、`dayu/cli/commands/fins.py`：同state_repository显式装配／同源summary，中立error，无下游状态机。

测试：S1受影响测试，加 `tests/fins/test_company_identity_storage_contract.py`、`test_company_meta_contract.py`、`test_fins_direct_stream.py`、`test_cn_download_runtime.py`（仅required装配机械迁移/原download回归），新增 `test_material_upload_state_repository.py`、`test_material_upload_publication.py`；`tests/service/test_fins_direct.py`。不开放整个tests重构；无必需rawfixture修改，历史记录保持。

| 验证 ID | 精确断言 |
| --- | --- |
| V7 state／company | active/create same/diff非overwrite、missingupdate含overwrite、neverdelete、freshname缺、已有fresh公司不需名、stale需名、目标错+缺名首目标；零started/job/handle/公司/材料业务写。UNSAFE/REPAIR_REQUIRED真实坏meta/manifest拒，不fakeCOMPLETE。 |
| V8 两阶段guard | A受理/合法company/prepare→Bsource或company提交→A begin+注册拒；delete/content/metadata-only/skip全部覆盖；原alias同时变化先原alias拒。注册前writer和finalpublicationguard真owner断言；boundedbarrier finally收进程，不A持writer等B。 |
| V9 amended／读回 | 八格真实Fs，docling次数/内容version/非marker业务字段；A→B→Brole保持；独立identity true发布→省略amended delete defaultfalse仍publishedtrue，首删/重删0/0；请求true失败/取消→null。两个LLM列表及schema同source reader；metadata_updated不可filing。 |
| V10 tombstone | filing/material首删→重删字节/SHA/revision/times/manifest/assets不变，恢复→再删新周期；损坏is_deleted缺字段/nonbool两方向KeyError/ValueError cause；不要求首次两个time字面相同，不按mtime/inode判业务no-op。 |
| V11 O33 owner | 两oldadmission，B完整commit后A取得writer，一uploaded一skipped；sameexactrole/amended/companyaliases；变bytes/role/amended、额外companytime/fields/aliases、缺original/Docling/manifest、同长度坏digest不能skip；真正read/writeIO、获取/rollback/release失败operational；COMMITTED后release异常不retry/rollback/改skip。 |
| V12 O33真实CLI | 多轮fresh独占base，同CLI真实生产转换/仓储；同步双进程stdinDEVNULL，normal/debug双流分存、PID/单调起止/启动差/exit/timeout/进程树；收终态恰一ok一skipped、完整manifest读回。共同oldadmission必须实际观测／独立受控进程级barrier证明；仅同步启动未观测窗口的轮次标顺序幂等，不能算竞态闭合。 |
| V13 job／取消 | no-runner同reason双摘要；新typed异常走active-only；终态SUCCEEDED/FAILED/CANCELLED已落盘＋progress异常状态/双摘要不变；observation无job单独验。precommit cancel rollback、commit开始后latecancel保actualoutcome；release故障保durable事实不伪零publication。 |
| V14 回归 | O32不同identity/ticker可共存；filing SEC/CN/HK身份/companions/单主转换/cancel/status/failure文案；download F5/F6不重写，assembly机械迁移原回归通过。 |

CLI集成探针recipe在唯一主树独占tmp实现，临时脚本不得产品hook／改源码；argv必须由实施后的实际parser冻结，基准形状：`dayu-cli upload_material --base <fresh-base> --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name 'Concurrent Same' --company-name 'Apple Inc.' --files <public-probe.txt>`；双文件同primary/amended时显式带实际旗标。barrier可在独立探针进程作用域包裹真实owner入口，仅控制暂停，不替换结果或储存实现；保存安装源码SHA、restore证据、每进程真实CLI双流与FS，包装失效不算pass，不把unitfakeevents当进程观察。完整mandatorycampaign仍在WU后。

#### V12 可执行独占启动/barrier recipe（在 S2 实施后运行）

S2 agent 在其全新独占tmp生成 `barrier_launch.py`（不是生产hook、site-packages patch或fake仓储）；两个主进程用同一实施环境解释器执行该脚本，脚本再运行真实 console owner `dayu.cli.__main__.exit_module`。只包 shared admission 的真实返回边界：原 admission 已读取真实Fs并返回完整handoff，此刻尚未进入lifecycle/公司提交/转换；包装保存原返回对象、只暂停，放行后原样返回。不能改返回值、状态、converter或repository。future required 签名已由§6.2冻结，启动核心如下（中文typed脚本，实施后需自身pyright0）：

```python
"""独占探针进程包裹真实CLI的受理返回边界，不修改产品文件。"""
import json
import os
from pathlib import Path
import sys
import time
import dayu.fins.ingestion_runtime as admission
from dayu.fins.storage.repository_protocols import MaterialUploadStateRepositoryProtocol
from dayu.fins.storage.source_integrity import SourceIntegrityStatus

GATE = Path(os.environ['DAYU_PROBE_GATE'])  # 必须是本次全新独占目录
ROLE = os.environ['DAYU_PROBE_ROLE']       # 只允许 a/b
TIMEOUT_S = 30.0
original_admit = admission.admit_fins_upload_material_request
armed = True

def paused_admit(
    request: admission.FinsUploadMaterialRequest,
    *, state_repository: MaterialUploadStateRepositoryProtocol,
) -> admission.ValidatedFinsUploadMaterialRequest:
    """参数：真实请求/仓储；返回：同一真实handoff；异常：原失败或barrier超时透传。"""
    global armed
    result = original_admit(request, state_repository=state_repository)
    if armed:
        armed = False
        state = result.state_admission.observed_state
        assert state.source_integrity.status is SourceIntegrityStatus.MISSING
        assert state.source_integrity.revision is None
        assert state.source_meta is None and state.publication_identity is None
        # fresh-base用例要求两者都观察到无公司；不以时间戳猜共同旧状态。
        assert state.company_meta is None
        identity = result.identity
        with (GATE / (ROLE + '.ready.json')).open('x') as stream:
            json.dump({'pid': os.getpid(), 'monotonic': time.monotonic(),
                       'source_status': state.source_integrity.status.value,
                       'revision': None, 'company': None,
                       'ticker': state.source_integrity.ticker,
                       'document_id': identity.document_id,
                       'internal_document_id': identity.internal_document_id,
                       'form_type': identity.form_type, 'material_name': identity.material_name}, stream)
        deadline = time.monotonic() + TIMEOUT_S
        while not (GATE / (ROLE + '.release')).exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('old admission barrier未放行')
            time.sleep(0.02)
    return result

def main() -> None:
    """参数：原CLI argv/明确探针环境；返回：无；异常：真实CLI退出/探针断言透传。"""
    assert ROLE in ('a', 'b') and GATE.is_absolute()
    admission.admit_fins_upload_material_request = paused_admit
    try:
        # 先安装owner包装再import消费者，核真实from-import绑定；无匹配就失败，不补fallback。
        import dayu.cli.commands.fins as cli_fins
        import dayu.fins.pipelines.sec_pipeline as sec
        import dayu.fins.pipelines.cn_pipeline as cn
        assert cli_fins.admit_fins_upload_material_request is paused_admit
        assert sec.admit_fins_upload_material_request is paused_admit
        assert cn.admit_fins_upload_material_request is paused_admit
        from dayu.cli.__main__ import exit_module
        sys.argv[0] = 'dayu-cli'
        exit_module()
    finally:
        admission.admit_fins_upload_material_request = original_admit
        assert admission.admit_fins_upload_material_request is original_admit
        (GATE / (ROLE + '.restored')).write_text('owner restored; process ending\n')

if __name__ == '__main__':
    main()
```

父driver以 `stdin=DEVNULL/start_new_session=True` 同时Popen a/b，环境只增加 `DAYU_PROBE_GATE` 与 `DAYU_PROBE_ROLE`，CLI argv由实施后真实parser读回。等两个ready真实写入且owned PID匹配，两份MISSING/revision=None/company=None及canonical身份相同；父层真实Fs公共仓储读回仍无source/company，保存before快照。先只写 `a.release`，实际wait a完成ok并读回winner完整原件/Docling/meta/manifest；b尚卡在旧handoff返回处。再写 `b.release`，实际wait b为skipped，核winner后→loser终态无业务字节/revision/版本/时间diff。两进程均在自己的真实admission返回处观察过旧state，这同时证明旧admission→winner提交→loser执行窗口，不靠启动时间推测。另多轮同时release作为补充，不替代此确定窗口。

每进程正常/debug双流、command/env允许摘要、实际PID/wait/timeout、restored文件/源码首末SHA、durable查询及真实仓储快照单独保存。超时finally只终止/wait自己Popen的session，不查询/操作其它进程；包装绑定/实际旧state/restore任一缺失不算竞态pass。实施后若装配不再经该owner则列精确caller差异，停在探针owner修recipe，不能加产品hook或换fake结果。仅同步启动但未证共同old admission的轮次仍标“顺序幂等skip”，不得计O33竞态闭合。

完成信号 V7～V14、覆盖率／pyright／docs与review闭环；guard或materialfinal不能可信表达则阻塞在storage owner，不补“读取像成功所以skip”。S2 release certainty不新增成功承诺，因此不是当前必须另开indeterminate WU的前置。

### 6.7 S2 生成接口补足与分支约束

新增publication模块直接依赖R validated contract、D prepared contract、storage公共协议及typedfailure；R不import该publication模块，D不importR／publication，storage不importR／D，避免新环。repository/core类型依赖仍单向底层。

`MaterialUploadPublicationDisposition`仅内部三枚举`PUBLISH/IDENTICAL_SKIP/CONFLICT`。frozen/slots `MaterialUploadPublicationDecision`仅required `disposition`和`failure: FinsUploadFailureReason | None`，CONFLICT必须有failure，其它必须None。`MaterialUploadPublicationOutcome`仅required `published_state: MaterialUploadPublishedState | None`、`result: UploadOperationResult`，成功/skip/metadata/delete必须COMPLETE同target state，取消为None；失败抛typedreason，由市场唯一catch投影，不能failure同时携successstate。

同模块两个操作分别拥有独立公司阶段和材料发布阶段。公司先验证／提交，市场消费返回值再调用D.prepare，随后材料executor执行guard／裁决／提交；市场不能自行重写任一阶段规则，不允许先prepare后补公司stage。唯一签名如下：

```python
def execute_material_upload_company_stage(
    *,
    request: ValidatedFinsUploadMaterialRequest,
    state_repository: MaterialUploadStateRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    batching_repository: BatchingRepositoryProtocol,
    cancellation: CancellationToken | None,
) -> CompanyMeta | None: ...

def execute_prepared_material_publication(
    *,
    request: ValidatedFinsUploadMaterialRequest,
    prepared: PreparedDoclingUpload,
    expected_company_meta: CompanyMeta | None,
    state_repository: MaterialUploadStateRepositoryProtocol,
    batching_repository: BatchingRepositoryProtocol,
    upload_service: DoclingUploadService,
    cancellation: CancellationToken | None,
) -> MaterialUploadPublicationOutcome: ...
```

D新增`_PreparedMaterialSkipCandidate`（required ticker/document/internal ID、publication_identity与file_events tuple），只在已产生一次original descriptor/fingerprint后返回，不能返回terminal skipped；`_PreparedMaterialMetaMutation`增加required同源`publication_identity`（没有任意requestmeta）。两者加入`PreparedDoclingUpload`精确union，filing subtype／已有资产mutation不变。`describe_prepared_material_publication(prepared: _PreparedAssetMutation | _PreparedMaterialSkipCandidate | _PreparedMaterialMetaMutation) -> MaterialUploadPublicationIdentity`只投影各prepared拥有的事实，不重新readbytes/seed/hash；delete独立分支不调用auto相同性arbiter，以observed目标条件注册，actualtombstone最终值由storage返回。

`commit_prepared_upload_batch`增加required `material_state_repository: MaterialUploadStateRepositoryProtocol | None`，由source kind强制双向约束（material必须有、filing必须None），不当optional fallback；现有五处真实caller全部显式迁移：`sec_upload_workflow.py:252,544`、`cn_pipeline.py:905,1193`、`filing_upload_publication.py:859`（行号绑定当前HEAD）。两处material路径将由新publication owner消费并传其显式仓储；三处filing调用显式传None，特别是filingpublication第5caller。迁移后新增material executor也是required caller，逐AST/rg核全集，不以旧“四处”断言放行。publication模块负责registration/arbiter，D仍唯一拥有stagedwrite→cancelcheckpoint→capability转移/rollback。material commit正常后D的`UploadOperationResult`增加required `published_amended: bool | None`与source kind（filing为None；material成功为finalbool，取消None），terminalpayload只从该typed字段投影；公司outcome字段维持filing原语义，不装材料state到extra payload。

公司等价no-op只能在material-specific公司commit owner判；puremerge仍现事实规则。observed company已存在时non-identity变化不得借现general“resolver同版保published”支路忽略；注册material阶段的expectedcompany严格保此约束。initialNone→freshsameintent的例外要求canonicalidentity/name-equivalence/完整aliases/resolver都同请求，没有额外company变化；该值来自companyfinal，不publication层猜时间。若这一guard不能表达“额外变化”与既有合并边界，本片须以具体反例blocked，不开新业务放宽。

## 7. S3：受控 XBRL 部署／转换／真实材料提交（必要机制已核收，generation-ready候选）

### 7.1 本轮直接证据与支持范围

补证 label `upload-material-macos-plan-completion-sol-20261002-01`，证据根 `workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/`；报告 `docs/gateflow/upload-material-macos-plan-completion-report-20261002.md`。当前范围仅 macOS arm64/Python3.11；Linux/Windows实装、锁回读、隔离/继承明确交后续平台WU，不能再列当前blocker，也不宣称pass。全部17标签＋O20F02仍为同一WU，仍三片；S1/S2契约不重裁。

fresh独占venv完整安装 `docling[xbrl]==2.127.0`、`docling-core==2.96.0`、`arelle-release==2.45.3`，使用现有common/macOS约束的独占副本；无`--no-deps`，无主.venv安装。`candidate-install.json` exit0、完整pip resolver `install-report.json`、全部已安装METADATA及hash `installed-metadata.json`、`pip-check.json` exit0、`pip-freeze.stdout`、`candidate-lock-readback-result.json`给出设计候选部署组合。**这是设计原型，不是修改后的标准产品安装通过**；最终标准安装在S3实施后验收，不把必须先实施产品改动设为plan循环前提。

公开真实输入选Docling官方固定commit `f1c42e394e3f5c40375c83edf01f8de762bb64f9` 的 `tests/data/xbrl/sources/mlac-20251231.xml`；官方notebook明确说明从SEC EDGAR取得。内部事实为MOUNTAIN LAKE ACQUISITION CORP./CIK0002029492/2025-12-31，只用于来源识别，不重裁Dayu材料身份。instance SHA256 `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`。taxonomy由同commit五份issuer XSD/linkbase及顶层catalogZIP组成；逐URL、获取UTC、响应、bytes/hash及ZIP每entry hash保存在`public/`与`mlac-input-manifest.json`。官方仓库MIT仅覆盖其贡献，包内FASB/XBRL/SEC权利分别保留；FASB官方授权使用页已采集`public/fasb-terms.html`，要求不修改taxonomy、保留notice及第三方条款。**原instance和混合许可taxonomy ZIP不入PR**；产品集成从双份证据根读受控输入，不把它们放进tests夹具。

`validate-mlac-closure.json`及XML日志：Arelle离线`--validate --validationExitCode` exit0，无error/warning。首次原型目录缺同级XSD导致exit3，后续只修布局，原失败保留。GRVE第二真实样本也离线合法性exit0，未据此冒其Docling结果。

MLAC同一input hash的无hook Path/Stream均exit0、SUCCESS、无errors、1个实际key_value_item；两路JSON SHA256均`c95431f8fd4321aea6276ff32dc179a81331b81325991726c5535d291e9e5c7c`。v4同次取证Path/Stream也SUCCESS，模型480facts、93contexts、typed_contexts=0，各有2211次实际`ModelDocument.load`调用与32次`ZipFile.read`调用。**这证明所选无typed真实样本的转换可行性，不等于任意XBRL、typed分支、实际CLI/manifest或强制边界验收**。#4437继续归Docling上游，不本地修抽取算法/假success，不重复issue。

### 7.2 唯一owner、管理员输入及typed配置候选（明确字段，无隐式sidecar）

以下接口属于本计划待同版review的产品设计，尚未实施；强制启动与策略的必要机制已由§7.4/§8.1 root同版证据核收，可以按本文生成；产品实施仍须accepted plan checkpoint。财报原件仍只能经Fins storage仓储取得bytes；taxonomy是管理员部署输入，不是material原件/角色/版本/财报事实，不能塞入上传files、extra payload或LLM输入。

- **Documents配置owner**新增 `dayu/documents/xbrl_config.py`：`TaxonomyArchiveEntry(relative_path: PurePosixPath, size_bytes: int, sha256: str)`；`TaxonomyFile(relative_path: PurePosixPath, size_bytes: int, sha256: str, archive_entries: tuple[TaxonomyArchiveEntry, ...] | None)`；`TaxonomyManifest(source_urls: tuple[str, ...], acquired_at: datetime, license_urls: tuple[str, ...], files: tuple[TaxonomyFile, ...])`；`XbrlConversionConfig(taxonomy_root: Path, manifest_path: Path, manifest_sha256: str)`；`PreparedXbrlInput(taxonomy_snapshot_root: Path, manifest: TaxonomyManifest, writable_root: Path)`。dataclass frozen/slots，字段无默认补值、无Any/object、无raw字段推断。archive_entries仅非ZIP可为None，ZIP包括目录entry显式size0；全部元数据为技术provenance，不投影成业务证据。
- 明确管理员位置：环境变量 `DAYU_XBRL_CONFIG` 的值为**workspace外**的绝对JSON配置文件；该文件显式含 `taxonomy_root`、`manifest_path`、`manifest_sha256` 三个必填字段。taxonomy/manifest也必须位于workspace外的管理员专用根；无默认目录、无猜父目录、无HOME taxonomy发现。unset表示无已配置XBRL部署输入，XBRL候选仍保留，但调用闭合地报初始化失败；非XBRL正常转换。管理员安装示例只写真实绝对路径占位说明，不代写用户既有目录。
- `load_xbrl_conversion_config(config_path: Path | None, forbidden_root: Path) -> XbrlConversionConfig | None`负责exact JSON shape、绝对/canonical路径、manifest digest/schema、来源/许可声明和trusted root检查。unknown字段/缺字段/相对路径/根内重叠/manifest不匹配拒绝，不loose parsing。管理员不属于敌对同uid写入者；目录不得group/world writable。首次部署需管理员核官方来源/许可与完整hash清单，LLM不能声明可信根。
- `prepare_xbrl_input(config: XbrlConversionConfig, *, snapshot_root: Path, writable_root: Path, stream_name: str) -> PreparedXbrlInput`负责只复制manifest列明文件；`open(O_NOFOLLOW)`与fstat拒symlink/非regular/st_nlink!=1，读后复验同fd size/digest，完整目录清单与manifest集合一致，禁止未声明条目及`instance.xml`/当前stream basename冲突。不沿原root symlink复制。Process分配三个不重叠的同请求兄弟区：readonly原件input、readonly taxonomy snapshot、writable work（backendtmp/output/Arelle配置）；snapshot_root与writable_root显式给定、canonical互不包含。private snapshot mkdir0700，不采用管理员原root作为worker读根；应用policy后snapshot无写权。ZIP拒绝绝对/..路径、重复entry、加密/非普通类型；逐entry名称/size/hash与manifest exact相等，按声明size有界读取。资源边界由管理员批准的完整manifest文件数/bytes和ZIP展开entry总量形成，不杜撰固定企业数据上限。复制后再逐文件/entry回读，worker启动后在解析前再从其可见snapshot复验；不匹配直接失败。新临时副本属于当前conversion，不修改原root/manifest。

### 7.3 实际接线、单次转换、失败及取消（已核收机制的产品实施合同）

`DefaultFinsRuntime`及CN/SEC实际三处默认converter装配统一调用新增 `dayu/fins/pipelines/docling_converter_factory.py:create_docling_converter(workspace_root: Path) -> ProcessDoclingConverter`。这个factory有具体理由：集中三处现存装配的管理员配置读取及workspace排除校验，避免三处各自猜部署事实；它不是透传兼容facade。Fins只在装配时读取`DAYU_XBRL_CONFIG`并把显式path/forbidden_root交Documents loader；唯一配置校验语义仍属Documents。

`ProcessDoclingConverter.__init__(*, xbrl_config: XbrlConversionConfig | None)`为显式必传参数；全部真实调用者及owner测试迁移，无兼容默认。现有每请求`DoclingConversionConfig`仍只承载PDF/通用转换选项；XBRL部署配置不混成材料业务字段。Process负责本请求独占input/output/temp生命周期；按共享capability的XML_XBRL候选suffix路由，调用Documents prepare，把`PreparedXbrlInput | None`显式加入`_DoclingProcessTarget`。无配置或prepare失败不启动未隔离XBRL。共享format owner已将普通`.xml`与`.xbrl`都定义为XML_XBRL候选，二者均只走此受控分支；不尝试默认DocumentConverter或普通XML/PDF fallback，README明确缺配置失败行为。

**配置/prepare失败唯一映射**：Documents loader/prepare持配置与可信copy校验语义，抛typed `XbrlConfigurationError`（合法config_path=None只表示未配置，不立即使非XBRL失败）。Fins factory在显式配置读取失败时将该typed异常装为既有 `DoclingConversionError(CONVERTER_CONSTRUCTION)`，保cause；Process对XML_XBRL请求且config=None、父侧prepare/copy复验失败同样由其converter construction owner投影CONVERTER_CONSTRUCTION；worker侧policy应用/可见snapshot复验失败在thirdparty构造前由`_DoclingProcessTarget`输出既有construction descriptor，父Process既有resolver还原。源内容实际解析/转换后才属EXECUTION。测试锁无配置/坏配置/准备复验/worker复验四面均CONVERTER_CONSTRUCTION，无新resource public code，无按字符串猜分类。

Documents新增 `convert_xbrl_bytes_with_docling(input_bytes: bytes, *, stream_name: str, xbrl_input: PreparedXbrlInput) -> ConversionResult`及专用构造helper，Process在XML_XBRL候选分支调用；现有通用`convert_pdf_bytes_with_docling`签名与web消费者不变，不能getattr补字段。XML_XBRL专用 `XBRLFormatOption(backend_options=XBRLBackendOptions(taxonomy=snapshot_root, enable_local_fetch=True, enable_remote_fetch=False))`，`allowed_formats=[InputFormat.XML_XBRL]`。Path/Stream的原件bytes保持一致；生产stream无需sidecar猜测，Docling临时`instance.xml`由backend生成。XBRL只一次转换，不进入PDF backend×device重复尝试；每份原件仍沿S1正常Docling资产/manifest必要条件。

**生命周期纠正**：已安装`SimplePipeline`继承`BasePipeline._unload`的no-op；`BasePipeline.execute finally`调用`_unload`不等于已调用XBRL backend.unload。不能继续用旧泛化推论描述XBRL。Documents XBRL转换helper持有该次result/实际backend，finally显式原backend.unload一次，成功/转换异常均关闭；构造拒绝无model时记录无model，不假造result。P0 v4在实际pipeline `_unload`入口copy普通值，之后显式原backend.unload一次、确认model.isClosed；不改变转换算法/状态。生产不装P0 profiler，也不为取证延长模型生命。

**spawn顺序明确**：现存`InterruptibleProcessHandle`使用multiprocessing spawn和Queue。spawn先重建Python、导入主模块/target所属Fins模块及中立runtime/契约，再反序列化target与预建IPC；现存Documents模块只有TYPE_CHECKING第三方导入，实际Docling/Arelle构造仍延迟。必须以实际入口importboundary验证，不承诺所有业务import都在policy之后。`_run_process_target`先建立session；`_DoclingProcessTarget.__call__`先chdir本请求独占work，在读取原件/snapshot和任何第三方导入之前应用父侧profile，随后复验/单次转换/export；最后现有Queue.put/feeder/join/close发生在policy之后。runtime源码/父入口重建路径只在受信bootstrap前可见，不能据exec继承宣称production spawn成立；应用后不得保留整个workspace读权。root实际spawn证据已定位Queue.put/_sem.acquire的EPERM，ownedPID91312内核明确ipc-posix-sem-wait /mp-tgb50ceh；profile纳本机实际支持的ipc-posix-sem类别许可，不新造IPC/事件总线。bootstrap/Queue在policy前建立，policy后完成既有put/feeder/join/close；类别许可不等于只允许该PID或单个Queue，不含ipc-posix-shm或出站网络。集中原型stdlib spawn+Queue只作机制对照，production target尚未测试，正常S3实施时验收。

父进程沿已有`InterruptibleProcessHandle`的spawn、独立process session及cancel→interrupt→join→group cleanup→close链；不另建业务取消状态机。唯一必要中立能力候选为 `dayu/runtime/macos_sandbox.py:apply_macos_sandbox(profile: str) -> None` 与 `MacosSandboxError`，只用stdlib ctypes调用`/usr/lib/libsandbox.dylib`的`sandbox_init(profile,0,&error)`，非0读取/free原错误并抛出，不回退。目标在任何Docling/Arelle导入、原件读取/解析前应用策略，再复验snapshot并转换；remote false只是额外应用设置，OS deny-network才是强制层。root已核direct-init exec startup/具体边界；direct-inprocess转换机制已由同版parent票据核收；production spawn仍待S3实施验收，不从startup推产品完整pass。

沙箱失败映射现有`CONVERTER_CONSTRUCTION`；同源解析/转换失败映射`CONVERTER_EXECUTION`；export映射`RESULT_SERIALIZATION`；取消、IPC、close/group cleanup继续现有owner语义，cleanup失败最高优先级且保首因。Process不可把失败变SUCCESS。任何失败本请求stored0/无material成功manifest（独立公司事实沿S2，不反向删除）。taxonomy/provenance只写技术诊断，不变成LLM财报证据。

### 7.4 已核收父层机制证据与本轮 P0-R09 独占采集器修订

label `upload-material-macos-runtime-consolidated-sol-20261002-01`；报告 `docs/gateflow/upload-material-macos-runtime-consolidated-report-20261002.md`；新独占根 `workspace/tmp/upload-material-macos-runtime-consolidated-sol-20261002-01/`。前轮harness/boundarychild/plain/profile逐文件复制后修正，不覆盖旧脚本、票据、父层run目录。运行脚本仅 `parent_harness.py`、`boundary_child.py`、`convert_plain.py`、`probe_convert.py` 和有限合同自检 `harness_contract_checks.py`；`pyrightconfig.json`只include上述5份。旧资源研究原型不加入执行清单或产品。复用既有公开input及freshvenv，不重复安装、公开MLAC合法性或业务裁决。

root前轮最终`parent-run-20261002-01`真实启动、文件/网络/exec边界成功，spawn-queue-boundary actualchild1；stdout已证child91312 policy后实际拒绝外部file/穿越/symlink/readonly写/network，stderr在Queue.put/_sem.acquire EPERM。root精确owned内核证据为ipc-posix-sem-wait /mp-tgb50ceh。P0-R08成立，owner为中立runtime policy及直接上游既有IPC装配；不误归财务内容/缺包，不拆slice。

root `root-controlled-runtime-library-01` command/policy/双流/actualchild0已证明真实Stream SUCCESS/errors=[]，inputSHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`，outputSHA `c95431f8fd4321aea6276ff32dc179a81331b81325991726c5535d291e9e5c7c`。library目录来自实际otool的declared.parent与resolved.parent；literal文件不足以覆盖mpdecimal多级alias。集中纳此目录只读、literal `/`本身、exact ancestor metadata、实际Python.app exec、独占work cwd与现有Queue信号量类别许可。只有一档证据支持的候选，无盲试扩大档，无整个Homebrew/home/workspace或network许可。

历史执行：root已在父层、cwd唯一workspace执行下列一次精确argv（97张child票据、外层exit1为P0-R09错误判据），原件保留，不再执行同一输出目录：

```text
/Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/venv/bin/python /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-runtime-consolidated-sol-20261002-01/parent_harness.py /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-runtime-consolidated-sol-20261002-01/parent-run-20261002-01
```

delivery-hashes.json与root-command-manifest.json绑定同版脚本/计划/公开input/必要source/解释器；每run另保存首末freeze及runtime依赖文件SHA。新public-root在本次全新run目录内，不重用前轮临时根。child显式cwd任务work；spawn先bootstrap及Queue，再worker chdirwork/apply，真实第三方导入之后。先native/Python/direct-init启动，再具体boundary；已启动但边界失败立即停止，一档失败/collector错误/timeout即停止保票据，不嵌套sandbox/log或提权。

该一次必要矩阵保留真实Path/Stream plain及同次profile、direct-inprocess、exec继承、stdlibspawn+Queue、file/穿越/symlink/readonly写/network/falseexec、hardlink复制owner合同、catalog/ZIP同次取证、fileURI/percent/remote/runtime-schema、ENTITY/XInclude/PI/unsupported-scheme、受管取消。转换退出不是资源拒绝证明；特殊引用未观察关系仍unknown；runtime-schema按用户运行库例外可读，不要求taxonomy独占。每ownedchild独立argv/cwd/env/actualwait/stdout/stderr/SHA。转换90秒、取消收口8秒、otool10秒/160文件、network2秒；失败仍落首末freeze/harness-final/owned-failure-manifest，内核精准诊断只由root外层针对新ownedPID执行，不ps/pgrep/kill0。

历史：原作者交付时只有有限selftest/静态合同及原型pyright0，尚待父层核证；当时完整状态在formal-plan-review-01/plan-frozen.md（修前SHA见§1正式fix身份）及旧报告保留。当前：root已核parent97票据与`root-continuation-20261002-01`剩余10条关系case及managed-cancel共11张owned收据actualwait0、同policy/source/input/profiler、managed取消parent0/child-15；原失败与补采分别保全，必要机制可行性闭合。不是原harness完整exit0，也不是产品pass。正式双审已终态，本轮只集中修采集判据/计划，不重跑昂贵macro/安装。标准产品install、productionspawn/cleanup、CLI→manifest、owner tests/coverage/README在S3实施阶段完成，不作为本次plan必须先实施产品的循环条件。

#### 7.4.1 P0-R09 采集器 owner、封闭字段与可执行判据

新独占修订根：`workspace/tmp/upload-material-unified-plan-fix-sol-20261002-01/`。复制 `parent_harness.py/boundary_child.py/convert_plain.py/probe_convert.py/harness_contract_checks.py` 后只在本副本接线新 `io_verdict.py`，保旧原件/Raw/harness不变。`IoObservation`/`KernelDenial`/`EvidenceRef` 为 frozen typed输入，`IoDecision`/`IoVerdict` 为唯一判据owner；转换exit/status与I/O裁决分离。新parent删除 `exit==0 → unexpectedly converted`，每关系case仅遇collector error/timeout或已证明的实际边界违反才停止；unknown/not-attempted保票据继续，不做产品拒绝。不重跑旧parent输出目录，不重装venv，不更改sandbox policy。

每case封闭证据包由 `command.json/actual-child.json/streams.json`、`*-judgment.json`、`*-io-verdict.json`、同次profile及首末freeze组成：case名/argv/cwd/环境允许摘要、owned PID、actualwait/exit/timeout/采集与cleanup错误、UTC起止及signal票据、input path/hash、policy path/hash、同版source/input/profiler/解释器hash（freeze），profile原件路径/hash与collector错误。`*-io-verdict.json`所有字段为：`owned_pid:int`、`event_pid:int|null`、`target:str`（实际精确文件/连接目标）、`request_target:str|null`（输入实际loader URI标签，不用于反推OS路径）、`operation:'file-read-data'|'network-connect'`、`request_observed:bool`、`returned_stream:bool|null`、`syscall_succeeded:bool|null`、`errno:int|null`、`kernel_denial: {pid:int,target:str,operation:同枚举,within_owned_window:bool,raw:{path:str,sha256:str}}|null`、`collection_complete:bool`、`expected_allowed:bool`、`evidence:list[{path:str,sha256:str}]`、`verdict:下列五值`、`boundary_violation:bool`、`basis:str`、`conversion_result_is_io_basis:false`。code无自由payload，不复制财报事实；技术model/graph/量阈不参与。

| typed verdict | 必要依据/反例 |
| --- | --- |
| collection-error | 未完成wait、timeout、collector/cleanup/profile错误，保原双流和失败退出；不得success掩盖 |
| not-attempted | 指定精确目标在此采集scope没有请求事件；只是未观察，不能宣称第三方所有路径都未尝试或OS拒绝 |
| unknown | 有loader/stream请求但缺匹配OSerrno/内核事件；false、ENOENT、loader返回None、listener未accept单独均不能证明denied；PID/原件不匹配同样unknown |
| denied | 真实目标请求 + 同owned PID/精确路径或connect目标的EPERM/EACCES，或同PID/路径/operation/owned时间窗的内核deny及原件hash；不是conversion非零。精准kernel事件由root外层独立核收，本脚本不提权、不刷日志、不从报告摘要制造raw |
| allowed | 同PID目标实际stream返回true或read/connect syscall成功；true stream证明允许访问，不冒已完整消费字节。expected_allowed=false则boundary_violation=true并停止，runtime公开XSD true在用户只读例外内，不是违规 |

conversion exit 0/非0、SUCCESS/FAILED/errors均只保留在conversion receipt，不参与以上五值。明确必要对照：①exit0+SUCCESS+stream=false无OS证→unknown；②相同false+同PID目标EPERM/精准kerneldeny→denied；③同false+ENOENT、错PID/路径/时间窗→unknown；④true+runtime例外→allowed；⑤无请求+listener未accept→not-attempted；⑥真实connect EPERM→denied；⑦实际连接成功→allowed并违反禁止边界；⑧collector timeout/错误→collection-error。合成合同测试必须标合成，不能代实际边界票据。

本轮真实原件读回使用 parent `file-uri` actual PID93381/exit0/profile false、continuation实际10条关系case及managed-cancel、基础boundary真实syscall及listener原件；另从profiler实际loader URI发现remote/encoded/FTP有请求但无OS拒绝证，记unknown，ENTITY/XInclude/PI未观察请求记not-attempted。encoded尝试字面`%6futside.xsd`不是已证读取canonical哨兵；不能自行decode反推。runtime-schema actual stream=true记allowed。root binding登记PID93381精准kernel data deny成立；本轮未把裁决摘要伪装成kernel原始日志，离线读回在未附该raw时file-uri仍unknown，和root外层含kernel裁决的denied适用证据集合明确不同。absolute/traversal false亦不单独冒denied。当前必要机制仍沿root核收，不以离线unknown重开昂贵机制准备。

本轮只执行 `source .venv/bin/activate` 后的新合同pytest、只读receipt replay和显式非空include自身脚本的pyright；原stdout/stderr/exit独立保存。自身config不改旧config，不对主产品做类型降格。S3将新判据用于其必要真实验收，production安装/spawn/cleanup/CLI→manifest仍依§7.5，不提前作为本轮plan pass条件。完整CLI campaign/registry仍WU后。

### 7.5 依赖、精确白名单、验收命令和README职责

最终拟依赖：pyproject标准声明改`docling[xbrl]>=2.127.0,<3.0.0`，common锁新增`arelle-release==2.45.3`、`bottle==0.13.4`、`isodate==0.7.2`、`jaconv==0.5.0`、`pyparsing==3.3.3`，保持本轮已有Docling/Core及平台tensor版本；macOS锁继续`-c common`，不重复pin。实际2.45.3METADATA为jaconv>=0,<1，0.5.0完整resolver/pipcheck成立，不能沿旧no-deps/import故事声称jaconv声明冲突。common新增pin被Linux/Windows包含是依赖图变化，未发现其已有pin同名矛盾，但其fresh实装/轮子/隔离未验，不外推。

生产精确允许文件：`pyproject.toml`、`requirements.txt`（仅安装说明必要同步）、`constraints/lock-common-py311.txt`、`constraints/lock-macos-arm64-py311.txt`；`dayu/documents/docling_runtime.py`，新增`dayu/documents/xbrl_config.py`；`dayu/fins/pipelines/docling_process_converter.py`，新增`dayu/fins/pipelines/docling_converter_factory.py`，`dayu/fins/service_runtime.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/sec_pipeline.py`（三处实际装配）；`dayu/fins/upload_format_contract.py`（唯一候选文案投影）；新增`dayu/runtime/macos_sandbox.py`。现有`dayu/runtime/interruptible_process.py`只在父层实际IPC/隔离继承证明需要通用原语调整时进入plan/fix另列准确变更，不授权实施者自扩。CLI/tool不用新增taxonomy参数或自己读配置；已有共享投影继续消费，候选格式不删除。

测试精确允许：`tests/documents/test_docling_runtime.py`、`tests/documents/test_import_boundary.py`，新增`tests/documents/test_xbrl_config.py`；`tests/fins/test_docling_process_converter.py`、`tests/fins/test_docling_upload_service_integration.py`、`tests/fins/test_upload_format_contract.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_sec_pipeline_upload_filing_stream.py`、`tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_sec_pipeline_download_stream.py`，新增`tests/fins/test_docling_converter_factory.py`与`tests/fins/test_xbrl_controlled_upload_integration.py`；新增`tests/runtime/test_macos_sandbox.py`。真实公开财报/taxonomy不进PR，机制fixture只能自行合成并明确非positive。不存在测试路径先按本plan创建，不以旧fake倒逼默认/兼容分支。

S3实施后的精确安装命令（fresh venv，不污染主.venv）：`python3.11 -m venv workspace/tmp/<S3-label>/standard-venv`；该venv `python -m pip install -e '.[test,dev,browser]' -c constraints/lock-macos-arm64-py311.txt --report workspace/tmp/<S3-label>/standard-install-report.json`；`python -m pip check`；完整metadata/lock回读。预期标准依赖真正包含上述xbrl closure，无resolver冲突。此断言属于最终改动后验收，不把本轮原型冒为已经通过。

先Arelle exact已验证参数 `venv/bin/arelleCmdLine --file <instance同级完整taxonomy目录中的instance> --packages <顶层taxonomy_package.zip> --validate --validationExitCode --internetConnectivity offline --logFile <run-log.xml>`，必须exit0且error/warning为空，再在强制策略下同bytes Path/Stream。真实生产CLI沿§9既有upload_material参数与S1/S2身份合同，以MLAC同hash公开input、实际管理员配置运行，核原件/实际Docling JSON（非标题-only）/source meta/权威material manifest，typed content负样本stored0/无本请求success。真实双CLI并发仍在S2及aggregate验收；完整CLI campaign和registry仍在WU之后。

`source .venv/bin/activate`后跑上述受影响owner tests及`python -m pyright`，每修改生产文件coverage>=80%。取消/cleanup/IPC破损、缺配置/根重叠/哈希或copy复验失败、目录与ZIP规模、路径越界/remote、普通XML/linkbase/JSON负样本、DoclingJSON回归全部断言owner contract。S3完成仍需真实macOS部署/边界/CLI→manifest及全WU正常gate，不因本轮positive或review共识通过。

README实施职责：根README安装、macOS当前验收范围与`DAYU_XBRL_CONFIG`管理员配置及排障，明确普通.xml/.xbrl同为受控候选、无配置/配置或准备复验失败为初始化失败，不存在默认converter回退；Fins README只解释候选instance/材料成功及失败，不暴露治理字段为财报事实；tests README明确许可原包external evidence和机制fixture区别；dayu README在中立runtime/装配变化职责内说明依赖方向。Documents无README不新增；不新增config默认文件，因此dayu/config README无触发。本轮全部README只读保留。

### 7.6 用户确认的运行库只读例外与唯一强制边界（不新增资源解析器）

本轮收尾时root新落盘`upload-material-xbrl-runtime-boundary-goal-amendment-20261002.md`，实际读取：用户questionItemId `call_HUYXbfgj3wEIbIhMkKWYi8F7`明确采用建议边界。该binding修订覆盖此前更强的“XML只能请求声明taxonomy”假设。`upload-material-xbrl-resource-boundary-decision-pending-20261002.md`已注明pending结束。不要求用户重复授权。

**现行合同**：允许明确列出的已安装运行库只读访问；XML也受同一OS读取边界，不另承诺它绝不能请求运行库公开文件；运行库文件不得投影为材料/财报事实。禁止读取用户workspace及其它private文件内容，禁止出站网络。任务原件与可信taxonomy snapshot只读，独占work/backend临时/输出可写。执行清单显式列明。不allow整个workspace/home/Homebrew、任意file-read或default。

旧runtime-schema反例保持actualexit0/真实openFileStream事实；它处在用户已确认runtime例外内，P0-R04改为rejected-with-reason，不是已修/读取被拒。研究原型保留在独占tmp，但**不进入S3产品**。删除`xbrl_resource_policy.py`、typed资源graph/namespace回补模拟、相关测试/文档白名单及其blocking要求。不产品monkeypatchArelle/Docling，不第二套财务/资源parser，不评抽取准确性。schema/base/catalog/ZIP/ENTITY/XInclude/PI由现有第三方处理，在实际OS边界内转换；未观察的关系只保留技术unknown，不变业务reject或额外目标。

保留§7.2管理员真实来源/许可/provenance、完整文件/ZIPmember size/hash、可信根、onlymanifest复制、链接/穿越拒绝、转换前同fd/副本复验。可信包输入校验属于Documents配置/prepare owner，**不是遍历XML关系的输入资源准入**。错误仍沿既有CONVERTER_CONSTRUCTION/EXECUTION、S1同源失败、stored0/无成功manifest，不新增资源reason枚举/兼容fallback。

**runtime policy typed生成合同**：`dayu/runtime/macos_sandbox.py`持有层中立`apply_macos_sandbox(profile: str) -> None`及`build_macos_sandbox_profile(*, readonly_roots: tuple[Path, ...], readonly_files: tuple[Path, ...], writable_root: Path, executable_files: tuple[Path, ...], allow_existing_posix_semaphores: bool) -> str`。追加层中立typed `RuntimeReadFile(declared_path: Path, resolved_path: Path, sha256: str)`及`inspect_macos_runtime_dependencies(executable_file: Path, python_base_root: Path) -> tuple[RuntimeReadFile, ...]`：信任bootstrap给出的实际解释器/已安装版本根，otool逐解释器/stdlib extension及递归Homebrew绝对dylib，保存原declared和strict resolved、同文件SHA；命令10秒/160binary固定有限预算，失败不猜根/全Homebrew fallback。@loader_path/@rpath若解析目标在声明venv/Python runtime根内则由根只读覆盖，出现根外未能绑定的真实加载路径闭合失败并回owner，不默认allow。readonly_roots必须纳每个RuntimeReadFile的declared_path.parent及resolved_path.parent（canonical去重），仅实际otool库目录只读，不上提Homebrew/home/workspace；readonly_files保实际加载declared alias和canonical文件；上游Documents/Fins的部署装配/解释器依赖清单确认alias与resolved确为同一批准runtime文件、记bytes/hash。builder只为显式清单中的路径与其canonical路径生成祖先literal file-read-metadata，不给祖先data/subpath读；literal `/`目录data是已证启动例外，不能推广其descendants。exact实际Python.app exec也显式传入，缺失或策略应用失败直接CONVERTER_CONSTRUCTION，不猜别的Python/fallback。allow_existing_posix_semaphores是显式必传权限选择：当前XBRL装配为True，只生成本机系统profile已有的`(allow ipc-posix-sem)`类别，不生成ipc/shm/network总许可，不承诺名称/PID独占。选该实际支持类别以完成既有Queue等待/通知/关闭，不发明未验证的细分operation/filter或访问Queue私有字段提取名称。Queue创建/重建在policy前；中立runtime只负责权限表达，既有InterruptibleProcessHandle继续负责IPC生命周期。runtime不读taxonomy/业务字段，不依赖Fins/Host/Engine。

root新直接证据见`upload-material-macos-literal-root-read-observation-20261002.md`：literal根目录修正native0；Python/direct1为realpath venv/bin权限。随后祖先metadata+现场Python.app exec的native/Python/direct/boundary四项全0，listener accepted=false，父/execchild真实file/穿越/symlink/readonly写/network/falseexec均EPERM、inside/work正常。这是明确启动/具体边界partialpass，不是全部转换/spawn/cancel通过。

同root真实转换plainPath1的rich os.getcwd指向继承workspacecwd拒绝；新harness所有受控child显式cwd为本任务work。production target在读取原件/第三方import前先chdir其独占work，再apply/reverify/单次Docling；不放开workspacedata。workingdir对照已进入XBRL backend但child1：_ssl/_decimal dlopen报实际`/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib`与`/opt/homebrew/opt/mpdecimal/lib/libmpdec.4.dylib`blocked。新inventory保留otool原declared alias及resolvedCellar文件，policy保literal二者并纳实际otool的declared.parent/resolved.parent精确library目录只读与exact祖先metadata；root-controlled-runtime-library-01已证该规则真实Stream成功，旧literal-only修复不足不冒已修；不整Homebrew read。两者绑定同runtime输入，不能归因缺arelle/财务算法。

当前plan必要同版OS矩阵的机制/权限合同已由root核收；productionspawn/cleanup及正常S3实施回归属于未来实施验收，不当前化为plan阻塞。旧namespace/xml关系研究不再blocking。所需owner测试在既有S3runtime/config/processconverter集合中增加alias/canonical/librarydir/祖先metadata/精确app exec、existingIPC权限选择与policy后Queue结果回传、workingcwd、hash不匹配失败、private内容拒绝/networkdeny、同实例正常提交/失败stored0断言，不新增资源graph测试。标准安装/CLI→manifest/README职责仍§7.5，在实施阶段按真实结果验。

## 8. 明确 blockers、owner 与解除证据

| ID | 本轮状态与直接依据 | 下一解除入口/owner |
| --- | --- | --- |
| B-X1 macOS依赖 | 设计候选已完整fresh安装/resolve/METADATA/pipcheck/适用pin回读；2.45.3/0.5.0成立，候选锁变化明确。不是最终产品标准安装pass。 | 包/锁owner在S3实施后按§7.5验收最终标准安装；不构成当前plan循环blocker。其它平台正式延期。 |
| B-X2 taxonomy/positive/配置 | MLAC真实来源、URL/UTC/hash、混合许可及完整闭包已取得；Arelle合法、无hook及取证Path/Stream成功。管理员显式位置/typed合同与copy复验候选在§7.2冻结。 | Documents/Fins配置owner；实际管理员产品配置与copy闭合测试属于S3实施。原件/许可包不入PR，来源是官方Docling再发布的SEC材料，不冒本轮SEC直取核验。 |
| B-X3 macOS强制隔离 | root已核startup/file-network-exec/direct-inprocess/Path/Stream及spawn+Queue必要机制；parent97票据保原外层exit1与P0-R09错误，continuation10条关系case及managed-cancel已完成。旧PID91312 Queue失败为历史反例，当前类别许可机制已核。P0-R04按用户运行库例外rejected-with-reason。 | 无未知可生成性blocker；本轮修P0-R09判据并交冻结复审。production spawn/cleanup/标准install/CLI由S3实施验收，不重复前置。 |
| B-X4 同次采集 | root已核同次load/ZIP/read/closed及实际边界/取消；file-uri ownedPID93381根外outside.xsd kernel data deny与returned_stream=false同源。runtime-schema true为允许；未观察请求的特殊关系仅not-attempted/unknown。 | 本轮新独占采集器封闭字段/typed verdict及正反合同验证见§7.4.1；不以转换exit、false单独或listener未accept证明denied，不重放冒同次新证据。产品生命周期测试仍S3。 |
| B-X5 上游/范围 | 无typed真实MLAC合法正样本成功；#4437原typed缺陷不重测/不patch、不退出XBRL scope、不宣称所有instance可转换。 | Docling上游既有issue跟踪；Dayu稳定投影失败并保证manifest语义。当前正样本可行性不再是plan blocker，抽取准确性上游。 |

当前必要macOS策略与同次边界机制已核收，整份generation-ready=true；正式plan review仍未通过，本轮集中fix后交root冻结同版re-review，之后才能accepted checkpoint。真实CLI/最终标准安装等未来实施断言不当前化为必须先改产品才能通过plan的条件。

### 8.1 总控可生成性核收（后于作者交付）

总控同版受限Path/Stream、Queue回传/实际join、exec/direct-init继承和真实取消核收，见 `upload-material-macos-runtime-consolidated-root-adjudication-20261002.md`。作者交付时的待核状态保持历史；当前不再有未知实现策略阻塞。file-uri的Docling SUCCESS不是OS读取成功，同次loader返回false及精确内核data拒绝已证。P0-R09为采集器错误退出码判据，本轮新独占副本与§7.4.1已集中修订，作者状态已修复、待root同版re-review验证；原失败不刷掉；不增加产品parser或内容准确性验收。其余必要未尝试的XML关系不当OS拒绝，不虚报任意资源闭包。当前为code-generation-ready候选，可进入正式双审，必须继续fix/re-review/checkpoint后才能实施。产品标准install/productionspawn/CLI验收仍属S3。

## 9. 验证命令、证据与覆盖门槛

原准备轮仅doc/evidence；历史集中收尾只执行无OS隔离自检/原型pyright，随后root完成必要同版机制采集；本轮plan fix仅新采集器合同测试/证据读回/自身explicit pyright，没有执行产品pytest/CLI/标准安装或重跑昂贵OS矩阵；以下是未来accepted实施命令。每slice在唯一workspace激活`.venv`后先记录 `sys.executable/Python/dayu.__file__/HEAD/CLI`，各自独占目录存command/stdout/stderr/exit，不合并双流。workspace临时script只在独占tmp，持久分析helper若确需新增只能在utils且先具体补白名单，不由本轮写产品工具。

```bash
source .venv/bin/activate
python -m pytest -q \
  tests/fins/test_material_identity_contract.py \
  tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py \
  tests/fins/test_upload_format_contract.py tests/fins/test_upload_failure.py \
  tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_upload_batch.py tests/fins/test_source_meta_contract.py \
  tests/fins/test_source_manifest_contract.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_service_runtime.py \
  tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_read_runtime.py \
  tests/fins/test_filing_upload_publication.py \
  tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py \
  tests/service/test_fins_direct.py \
  --cov=dayu --cov-report=json:workspace/tmp/<implementation-label>/coverage-s1.json --cov-report=term-missing
python -m pyright
```

S2在上述受影响集合加入两个新materialstate/publication测试、companyidentity、directstream、CNdownloadruntime，以及companymeta实际owner测试；S3加Documentsruntime/importboundary/processconverter/XBRLintegration与被触及runtime测试。新增测试需先实施存在才运行，路径不是“已通过套件”。各slice只运行相应受影响集合；aggregate在最终全部slice源码上跑其并集。全量`python -m pyright`使用当前pyrightconfig覆盖dayu/tests/utils（非三文件检查），任何新增/扩散／触及旧类型错误须owner修正；不能exclude/ignore/Any降格。

逐实际修改生产`.py`从coverageJSON逐文件核summary≥80%，没有命中路径视缺覆盖失败，不用全包平均代替。大文件需要补有意义owner/真实入口测试，不照抄实现断言；utils/render脚本按项目例外。受控converter只用于注入失败/取消／确定性矩阵，实际成功链与O33/XBRL集成必须生产真实转换。barrier全部有timeout/finally收口，保存失败实际exit和修复后重跑，不删失败票据。

集成证据每run含输入来源/recipe/hash、argv/cwd/env允许摘要、解释器/版本/安装源码、独立双流/exit/screen、normal/debuglog、before/after/businessdiff、storage公共meta/manifest/assets/SHA、durablequery（无job/Host时queried-but-absent）、PID/时间窗/进程树及清理。材料成功与公司事实分别核。S3只可报告真实macOS适用向量结果，不生成伪跨平台“allpass”。

## 10. README、Raw 卫生和风险分类

已读README自身约束：根README:9是最终用户手册；FinsREADME:17只描述当前已实现包契约；dayuREADME:11只跨包关系；testsREADME是现存测试职责/运行方式。因此实施后：

- 根README §5.2更新实际material必填/name/year/period/document断言、删除internal输入、multi-primary、禁止deletefiles、状态/amended/错误和并发操作；删除当前“delete附files会忽略”的旧行为说明。§1仅在S3真实部署成立后写正确安装/平台配置，不写未落地XBRL承诺。
- FinsREADME只写已实现identity/role/state/two-phaseguard/failure/publishedamended，testsREADME写实际新增owner测试/运行范围，不能写proposal或gate流水。
- dayuREADME只有runtime/assembly跨包关系真的改变才改；S1/S2无Host/Engine/config语义改动，不机械更新其手册。若S3实际选管理员config文件，先读该README约束再职责内修改，本轮不写。

**全PR Raw卫生收口项**：`tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.log:4` 已复现 `git diff --check main...HEAD` exit2。归全部slices后最终PR收口证据资产owner，不另立产品slice、不重开F5。未来白名单仅该Raw及其真实引用：先枚举`rg -n 'final-pyright\.log' docs tests`并冻结所有引用/manifest。

可逆封装recipe：把原stdout exact bytes包成同目录`final-pyright.raw.json`，字段`encoding="base64"`、`size`、`sha256`、`payload`；原log替换成纯ASCII指向封装的说明（明确不是旧stdout），有效引用同步改为“解码后原stdout”及原SHA，不能改历史运行事实或把说明当Raw。先验证decode==原bytes、SHA匹配（含末尾空行），再核所有有效读者读取封装／原SHA，最后fullPRdiffcheck0。引用包含历史判定log的fixture_manifest则只更新载体hash/位置并保原decodedSHA，禁止trim原stdout。实际引用路径在收口时枚举纳窄白名单，不对未知文件预授权。本轮未实施封装，也未声称fullPRcheck已恢复。

| 风险／未覆盖 | 分类；owner／destination |
| --- | --- |
| 全部17标签与必要旧reviewfix | covered by approved-scope slices S1/S2（本候选尚未accepted，当前未修）；Fins/storage／未来实施复审。 |
| XBRL必要机制/资源冻结 | fixed in current plan机制；root已核B-X1～B-X5必要可行性，generation-ready=true；P0-R09本轮采集器/合同修订待复审。covered by later approved-scope S3：标准install/production spawn/CLI→manifest、owner测试/coverage/README，非当前可生成性blocker。 |
| Linux/Windows XBRL部署、lock回读、强制边界/继承 | 用户正式goal amendment已授权延期；平台部署/依赖与Documentsruntime／总控后续平台验证项；当前无环境未验证，不阻塞本WU macOS验收。 |
| typed XBRL上游分支 | tracked by existing issue #4437；Docling，S3不得自行修准确性/伪成功。 |
| COMMITTED后release失败 | 本WUfail-closed约束及故障回归覆盖；全局/下载indeterminate方案assigned to later work unit，storage residual，不新scope。 |
| processed amended是处理时点快照、filing identical amended、历史角色/名称/身份/日期迁移、batch自动名称过长、全局usage中立化 | assigned to later work unit（既有独立residual队列）；对应owner／总控原residual索引；不借本WU实施。 |
| 完整upload_materialCLI CI／正式oracles/scenarios/readiness | assigned to WU后独立阶段；CI/oracle owner／`upload-material-repair-scope-and-ci-closeout-20261001.md`＋`docs/cli_ci.md`。本WU成功不等整体大目标完成。 |
| RawEOF空行载体 | requiring reversible evidence closeout；验证资产owner／全slices后最终PR收口；不trim原证据。 |
| 产品测试/CLI/覆盖/全量pyright/README | covered by later approved-scope S1/S2/S3/aggregate/PR；本轮只执行新采集器自身测试/explicit pyright，不能记产品pass。双审已完成且本轮集中fix，仍待同版复审。 |

旧必要reviewfix追踪：S1覆盖O05完整sharedboundary、O06首错/码点、O07EMPTY与完整seed、O16filing隔离、O17PR6rawbatch/实际`test_upload_filings_from_command`、O25PR1role/read/filing、content两轮observation/job与log；S2覆盖O12PR5active-only/no-runner/selection不重复O16、statePR-C5source-kind/hint/rawformat、O13严格删除与共享filing回归、O18PR4-F1～F6正确writer时序/finaldeletebool/nonamended字段、O33company独立/certainty。S3保最新PR10窗口/结构化observed规则。映射表示已进入候选计划，**不是这些旧finding已修或旧review gate自动pass**。

## 11. Gate 顺序、最终收口与报告合同

用户latest scope已确认；当前generation-ready=true、正式plan review未通过。本轮集中fix完成后停止，由root冻结新候选，MiMo/ds-flash同时同版re-review、root独立核证/裁决，再accepted plan checkpoint；不重跑已核机制、不把未来安装/CLI前置为plan循环。未来实施按S1→S2→S3，每片一个完整implementation→code review（deepreview）→fix/re-review→accepted slice commit；全部完成后aggregate deepreview/fix/re-review/checkpoint，再既有draft PR197最后PR review/fix/re-review/checkpoint/普通push-readback/final closeout。用户merge，main不动，不新增PR。Raw可逆载体收口纳最终PR检查，不能scoped diffcheck冒fullPR pass。

每轮artifact记 reviewed/changed target hash、18标签状态、实际commands/exit（包含非零与恢复）、expected vs actual assertions、docs decision、finding裁决/最终状态、分类风险owner/destination、current gate／下一个未完成入口；成立新finding立即登记且同版验证。剩accepted未修/部分修/证据失效不能pass。review协议按最新control，计划作者不派评审或其它子Agent。

WU finalcloseout说明真实产品变化、受影响测试/逐文件覆盖/全pyright、README、所有slice+aggregate+PR review证据、普通push/readback及main保持、18标签与blocker状态、Raw可逆保全、remainingowners；只有全部满足才修复WU pass。随后完整CLI CI／registry另阶段，不能把未做登记当WU失败，也不能把WU pass冒整体任务完成。

本轮交付report额外核首末HEAD/branch/main、原有tracked源码/依赖/测试代码/README字节与产品diff；不为hash核验打开私有财报或凭据。本作者仅两个文档与独占证据。其他owner同时修改旧总控提示文档如实按首末hash列，不归本作者。最终停止，不进入review／实施gate。
