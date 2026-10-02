# upload_material G1 完整受理与稳定身份：合并计划准备

- 任务：`pr197-g1-plan-preparation-sol-20261001-01`；状态：**plan preparation 完成，非 accepted plan，未实施、未通过任何 gate**。
- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；branch：`codex/upload-material-oracle`；成果供 root 纳入现有 draft PR197，用户 merge，main 不动。
- 所有产品/裁决证据固定于 `3a836a463aab3eeffb050facd592e614801d6ca9`；不是当前 F5 交付版审查。
- `workspace/tmp/pr197-g1-plan-preparation-sol-20261001-01/freeze.json` SHA256：`948be6926a0a5dc93193e5143746d59c0a78bf5ce4f82848b2c53edc16f22b8b`；47 项逐件匹配，`absent=[]`。
- 必要补充也仅从该 commit 的 Git blob 读取至独占 `supplemental/`，非 worktree/clone；索引 `supplemental-index.json`，逐件证明 `read-proof.json`，身份调用图 `identity-callers-at-pin.txt` 均在上述临时根。
- 补充实存：CLI commands/fins、SEC façade、tool helper、SEC material stream/Service direct/batch/asset-plan/usage tests。候选 `dayu/fins/tools/common.py`、`tests/fins/test_sec_pipeline.py` 在该 commit 不存在；实际使用 `_ingestion_tool_helpers.py`、`test_sec_pipeline_upload_material_stream.py`，不假造 API。

## 1. 动机、授权与成功信号

动机成立：身份 builder 局部 canonical，工作流另行投影；共享受理尚未覆盖必填、长度、财年域及 ID 断言，delete 的原始文件可被丢弃。问题分别是生命周期迟报、非法身份固化和事实分叉，不能仅修 CLI 文案。8 个 labels 共同定义一个请求能否安全进入执行及其稳定身份，合成一个行为增量足够；不按模块/旧 WU 再拆十多条 slice。
依据优先级：本轮明确指令/用户最终裁决 > 正式 UM adjudication > accepted goal > 旧 plan/review/实现。下表路径分别位于 `docs/reviews/`、`docs/gateflow/`；旧 goal 中“另一 WU non-goal”仅为旧分割边界，本组同时覆盖 8 个已批准行为，成功信号不变。

| label | 正式裁决；accepted goal | 本组必须兑现 |
| --- | --- | --- |
| UM-O16-F01 | `upload-material-um-o16-oracle-adjudication.md`；`upload-material-o16-action-files-goal-20260928.md` | auto/create/update 有文件，delete 无文件；共享 typed 准入早于目标/文件读取、lifecycle 与业务写 |
| UM-O17-F01 | `upload-material-um-o17-oracle-adjudication.md`；`upload-material-o17-form-goal-20260929.md` | 唯一 form trim/upper 函数，身份/meta/manifest/有字段的事件与结果同源 |
| UM-O05-F01 | `upload-material-um-o01-o06-oracle-adjudication.md`；`upload-material-o05-required-identity-goal-20260929.md` | 所有动作 form/name 无条件必填，None/空串/纯白 typed 前置拒绝 |
| UM-O06-F01 | 同上；`upload-material-o06-name-length-goal-20260929.md` 的后续明确选择 | name trim 后 ≤240 Unicode 码点，不截断、不 NFC/NFD、不按字节或字形簇计数 |
| UM-O09-F01 | `upload-material-um-o09-oracle-adjudication.md`；`upload-material-fiscal-goal-20260929.md` | material 可选 year 1800..2100 含端点，非法值先于 seed |
| UM-O10-F01 | `upload-material-um-o10-oracle-adjudication.md`；同一 fiscal goal | 复用 FY/H1/Q1/Q2/Q3/Q4、trim/upper/空转 None；tool 原空文本拒绝保留 |
| UM-O07-F01 | `upload-material-um-o07-oracle-adjudication.md`；`upload-material-o07-ids-goal-20260929.md` | material 公开 internal_document_id 输入全链移除，持久/结果内部 ID 与 filing 身份保留 |
| UM-O07-F02 | 同上；同一 IDs goal（含已接受的显式空 ID 要求） | document_id 仅 owner 一致性断言；EMPTY/MISMATCH 早于 lifecycle/业务写 |

共同成功信号：合法 canonical 输入贯通 direct/job/observation/CLI/tool/Service/独立 SEC/CN/HK；所有非法输入止于各入口准入，零 started/handle/job/executor、零公司/材料业务发布；新写或同版创建的合法状态中身份、摘要与仓储事实一致。真实 CLI 最终验收仍由整体修复收口完成，不能用单元测试或本准备文件替代。
非目标：O12 状态、O25 primary、O18 amended、O33 并发、XBRL、F5 日期/来源财期推断、下载规则、历史身份迁移、全局 usage 清理、批量派生名称新规则；不新增 manifest/observation 字段或更换身份摘要算法。

## 2. pinned 实际 API 与必要重绑

简称 R=`dayu/fins/ingestion_runtime.py`，D=`dayu/fins/pipelines/docling_upload_service.py`，U=`dayu/fins/upload_usage_contract.py`。

| 直接源码证据 | 计划判断 |
| --- | --- |
| R:1419/1460/1526/1565：raw request、validated handoff、`_admit_material_upload_facts`、`admit_fins_upload_material_request` | 已有公开准入/不可变 handoff；扩展它，不再造平行请求或 validated 体系 |
| R:7827/4748：ticker→action→source→日期；所有 runtime 上传入口受理前调用共同边界 | 保留既有首错，加组合与完整身份；不能把新 form 校验挪到 ticker 前 |
| D:1764/1803：`build_material_ids`、`validate_material_upload_ids`；1971：私有 period 仅 upper | 身份及断言 owner 在 D；旧 tuple API 无 canonical 事实，须做明确 API 迁移 |
| U:18/140/213：enum、唯一 messages、`fins_upload_usage_failure` | code/message 已在 U，旧计划指向 R 的指令失效；禁止 `dayu.runtime` 副本 |
| SEC workflow:417；CN:985/1012/1037/1065；SEC façade:805/832/857/885 | raw façade 已准入；validated 工作流仍重算 period/ID/auto，改消费 handoff |
| `upload_asset_plan.py:379`、D:1449 | 既有 selection/asset plan 与 full-basename Docling 命名继续复用；material 不在 D 再规划 |
| CLI:1129/1203/1219；batch:799；tool:344/489 | CLI 已 preFactory 受理但先解析 ticker，batch CLI 独立 upper，tool 独立组合/必填；分别按裁决修 owner/机械解析 |
| `service_runtime.py:197`、`service/fins_direct.py:297` | 实际已传 validated request；**不存在**旧计划的 `_pipeline_upload_action`，不能为迁移创造 wrapper |

必要旧 finding 全部保留，集中在本 plan 消化，不改旧文件或伪称其 re-review 已通过：

| 旧 `*-plan-review-adjudication-20260929.md`（前缀 `upload-material-`） | 本组必修映射 |
| --- | --- |
| `o05` F1/F2/F3/Q1、C1/C2/C3 | 单条空 forms 进入共享 owner；tool strip 投影；runner fixture；中立文案；完整独立准入与 U 重绑 |
| `o06` PR-F1/F2/F4 | 完整名称准入，组合→form 必填→name 必填→长度；240 码点自足提示；PR-F5 留独立 batch 名称残余 |
| `o07` F1–F4/实施检查点 | 完整 seed 后 EMPTY 再 MISMATCH、移除公开内部 ID、中立提示、CLI 证据模板、历史身份单列 |
| `o16` F1–F5、二/三轮 F1/F2/OQ、四轮旧 fixture、C3 | filing 分支隔离、D 类型不变量、复用 MISSING_FILES、入口局部顺序、真实批次测试、typed requested/pipeline pair 与 U |
| `o17` F1/F2、PR4-F1/F2、PR5-F1、PR6-F1/F2/F3 | 合组覆盖 O05/09；只断言有 form 的投影；跨命令 owner read；batch 共享 canonical/raw parser/真测试、独立首错 |
| `fiscal` F1/第三轮两项/PR4-F1/F2 | tool 空文本及 filing/material schema 区分、日期回归不改、锁定环境、fiscal→ID、material 专属中立 code |

## 3. G1-S1 唯一行为增量：从完整准入到稳定身份消费

前提：F5-S1 唯一产品 writer 完成并闭环后，root 按第 8 节重绑真实最终 API，形成同版正式 planreview 目标；本文件只给 pinned 设计。组内动作是一次实施/一次审查的连贯步骤，不是独立 slice/gate。

### 3.1 owner、typed API 与 required fields

1. **D 继续拥有身份**。新增纯函数 `normalize_material_form_type(value: str) -> str`，只 `strip().upper()`，不增枚举/长度；batch 与身份 owner 共享。必填判断属于完整身份准入，不属于各消费者。
2. 将 D 的 `build_material_ids` 改为完整纯准入：`(*, form_type: str | None, material_name: str | None, fiscal_year: int | None, fiscal_period: str | None, document_id: str | None) -> MaterialUploadIdentity`，参数均显式 required（可空不等于有默认值）。这是替换旧 tuple API，不是兼容 wrapper。
3. `MaterialUploadIdentity` 是 frozen/slots typed fact；六个 required 字段：`form_type: str`、`material_name: str`、`fiscal_year: int | None`、`fiscal_period: FiscalPeriod | None`、`document_id: str`、`internal_document_id: str`。构造时由 D 的同一私有纯校验/seed helper 拒绝非法、非 canonical 或 ID 不一致的人工 fact；不允许默认 ID/extra payload。
4. D 准入顺序：form 缺失/空白→name 缺失/空白→trim 后 name 长度→可选 year（整数、拒 bool，1800..2100）→既有 `domain.filing_semantics.normalize_fiscal_period`（非法映射 U 的 `UNSUPPORTED_FISCAL_PERIOD`）→完整 canonical seed→显式 document_id EMPTY→MISMATCH。缺失 ID (`None`) 自动生成；非空 ID trim 后精确比较。校验失败不计算非法 seed。新增具名业务常量 `MAX_MATERIAL_NAME_CODE_POINTS=240`、`MIN_MATERIAL_FISCAL_YEAR=1800`、`MAX_MATERIAL_FISCAL_YEAR=2100`，不拿 usage 展示预算充当名称规则。
5. seed 保持现算法：canonical form/name，提供的 year、非空 canonical period 按现顺序以 `|` 拼接、UTF-8、SHA-1、`mat_`；两个 owner ID 相同。不加入 ticker、日期、amended 或其它字段。删除旧独立 `validate_material_upload_ids` 及仅供 material 的 `_normalize_optional_upload_fiscal_period`、对应 exports；所有真 caller 迁移，不留 re-export/旧参数接收。
6. **R 拥有 action/files 准入**：新增 `validate_fins_upload_material_action_files(action: str, files: tuple[Path, ...]) -> FinsUploadMaterialActionDecision`。frozen/slots 返回必填 `requested_action: Literal['auto','create','update','delete']` 与 `pipeline_action: Literal['create','update','delete'] | None`，auto→None，其余同值；构造器校验 pair，不允许半个事实。未知动作 leaf 使用 U `INVALID_ACTION`；入口已有更早词法错误保留。
7. leaf 只查动作及原始 tuple 的有无，不 resolve/stat/open，不读目标。auto/create/update 空 tuple 复用 `MISSING_FILES`，delete 非空复用 `FILES_NOT_ALLOWED_FOR_DELETE`；不得新增同义 missing-files code。
8. **U 唯一 code/message owner**：补 `MISSING_FORM_TYPE`、`MISSING_MATERIAL_NAME`、`MATERIAL_NAME_TOO_LONG`、`INVALID_MATERIAL_FISCAL_YEAR`、`EMPTY_DOCUMENT_ID`、`DOCUMENT_ID_MISMATCH`；所有文案渠道中立、字段明确、可行动且 bounded。名称提示明确“去首尾空白后最多 240 个 Unicode 码点”，year 明确 1800..2100；ID 提示是字段一致性断言，不能称可覆盖身份。共享缺文件提示覆盖 auto/create/update；delete 提示 files 不允许；period 使用六值提示。不清理其它 scope 外 messages。
9. **扩 R 既有 handoff**：`ValidatedFinsUploadMaterialRequest` 加 required `identity: MaterialUploadIdentity`、`action_decision: FinsUploadMaterialActionDecision`，与原 required request/selection/asset_plan 同源。`_admit_material_upload_facts` 返回这五项；factory/`__post_init__`/`validate` 复用同一 owner 验证，并拒绝手工/replace 漂移，不能 optional identity 或下游补字段。
10. 归一化 request 中 action 保持字符串 auto，form/name/year/period 为 owner canonical；document_id 保留用户可选断言的含义，不把生成 ID 填入 raw 输入字段。删除 raw `FinsUploadMaterialRequest.internal_document_id`。执行 ID、`_upload_request_summary`、`_upload_request_document_id` 及其 progress/job/durable 消费者从 `identity` 投影；无显式 ID时也投影已生成的 owner ID。摘要不得再从已删除字段读内部 ID或重算 form/period/name。
11. 准入依赖 DAG 保持无环：R→D/U/asset-plan；D→U/filing-semantics/既有底层依赖，绝不 D→R；batch→D 的纯 form API，D 无 batch 依赖。不新增 profile/factory/callback、runtime 包业务副本或下游兼容 seam。

### 3.2 各入口顺序与 dataflow（不是全局统一首错）

| 入口/真实 caller | 定位、順序与消费合同 |
| --- | --- |
| CLI `run_fins_direct_command`→`_prevalidate_upload_material_request`→`_upload_material_stream` | 在 prevalidator 内从 raw args.files 构 tuple，**先共享组合 leaf，再 `_parse_ticker_csv`/字段机械解析**，均 preFactory；workspace 路径原前置顺序保留。完整准入后只检查 selection 的合法路径；删除 delete+raw 路径额外 normalize/检查分支 |
| R `upload/start_upload/start_observed_upload/prepare_observed_upload`→`_validate_runtime_upload_request` | 保留 ticker/alias→action→source 首错；material 组合→原 filing_date/report_date 校验→完整 D 身份→现资产 planner→handoff。身份错误不得拖到 summary/producer/job/observation；filing 分支不接 material 规则 |
| tool `FinsUploadToolCallable.__call__`→`_upload_request_from_arguments` | 保留 kind/action/primary 与类型词法错误；material 文件 tuple 机械解析→共享组合 leaf→请求→完整准入→原文件存在/非空预检→prepare observation。拆共用 `_upload_files_from_arguments` 的 material 自行组合判断；filing 原判断/文案保留，不借组改空字节语义 |
| tool form/name/ID/period | form/name 共用模块级私有可空 text 投影：缺失/null→None，字符串 strip（空白→空串）交 owner，非字符串原参数错误。ID 显式空串也交 owner，不能折叠 None；period 继续 `_optional_nullable_text` 的空文本参数层拒绝、省略/null→None，零 awaiting handle |
| 独立 SEC `upload_material`→`upload_material_stream` | raw façade 在共享完整准入前保留原 normalize_ticker→US market→build_upload_company_id 的纯校验；再 action/files→完整受理。错误类型/原提示保留，非法 ticker/market/company 与空 form 并存不能先报 form。同步/异步复用同一入口，不读目标 |
| 独立 CN/HK `upload_material`→`upload_material_stream` | 同理先现 `_normalize_upload_ticker`→`build_upload_company_id` 纯校验；再共享受理；CN/HK 不新增 SEC 市场规则。validated stream 原 ticker/company 检查保留在其原位置，不调用新的 form 叶子抢首错 |
| SEC/CN `upload_material_validated`→`upload_material_validated_stream`→SEC workflow/CN workflow | 既有 handoff validation 防绕过；消费者只读 identity/action_decision，不再 form/name None guard、period upper、build/validate ID 或 `None↔auto` 重算。`resolve_upload_action(decision.pipeline_action, previous_meta)` 仍拥有目标状态解析；requested_action 始终 decision.requested_action（auto），resolved_action 独立 |
| `FinsDirectCommandService.upload/upload_material`、Service runtime `ProductionFinsUploadRunner.run_upload/_run_material_upload` | 原样传同一 handoff、selection/asset_plan/identity/pair；取消/计数/summary 从 owner fact 取值。不存在的 `_pipeline_upload_action` 不补建。需要改的只是实际 summary/中文 Raises；不改 runner 生命周期 |
| batch CLI `_single_batch_material_form`→`_run_upload_filings_from`→`generate_upload_batch_plan/_validated_material_form` | CLI 独立机械 raw-preserving split loop：None/空列表→None；每个 value 按逗号 split，逐 item 用 stripped 副本判空、保存 raw；全部扫描后判多值；`['a','']` 先空值错误。单 raw 候选原样到 batch，CLI 不 upper |
| batch canonical/routing/argv | batch `_validated_material_form` 复用唯一 form 函数后检查现 closed routing（FINANCIAL_STATEMENTS/EARNINGS_CALL/EARNINGS_PRESENTATION），unsupported 提示仍引用 raw 候选；typed entry canonical→生成单份 `--forms`→R handoff 同值。regeneration argv 保留 raw 用户候选；不将 routing 枚举扩到 direct material |

单条 `--forms` 与 batch parser 不混用：`_single_optional_form` 对恰一、不含逗号的 `''`/纯白原样交 owner；其余保留 `_normalized_text_tuple` 的逐项空值/多值结构拒绝。`None`→owner missing；`,`/`' ,'`/`'A,'`→CLI 空 item；`'A,B'`→多值。CLI 空 document_id 原 argv 结构拒绝保留，不强行统一 runtime/tool 首错。
所有新增 material 输入错误在 workflow 的业务 `try`、目标读取、begin_batch、公司保存、文件读取/转换/发布之前抛 `FinsUploadUsageError`；CLI/tool 仅投影 `.failure`。Service/内部 ID输出、事件、source meta/manifest 中已有字段保留；不新增 form 到 observation/result-summary、period 到无该字段的 manifest。
D `prepare_upload` 的四个实际 caller：SEC filing/material（workflow:210/519）、CN filing/material（CN:859/1164）。两 material caller 只传同源 identity 与原 asset_plan；filing 原样。D action/selection mismatch 保留程序不变量 `ValueError`；非法 raw 组合必须以禁止 prepare/target-read 的测试证明不可到达，不下游转 unexpected_runtime 补救。

### 3.3 允许文件与 API 迁移清单

以下是后续 G1-S1 的白名单，**本准备任务只新增本文件与独占 tmp**；实现不得顺手改其它产品/裁决/总控/registry。

| 文件（仓库相对路径） | 必要修改 |
| --- | --- |
| `dayu/fins/pipelines/docling_upload_service.py` | 纯 form/完整身份 fact、builder API、删除旧 validator/private period/exports；不改转换/版本/发布/状态 |
| `dayu/fins/ingestion_runtime.py` | typed action decision、完整准入/handoff/构造防绕过、raw 内部 ID移除、canonical request 与已有摘要投影 |
| `dayu/fins/upload_usage_contract.py` | 唯一 codes/messages；对应共享 filing 文案断言同步 |
| `dayu/fins/pipelines/sec_pipeline.py` | raw 独立入口首错位置、validated 透传及 Raises；不改 download/F5 |
| `dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py` | 移除两套 material ID/period/action 消费重算，使用 handoff facts；CN raw/validated 首错保留 |
| `dayu/fins/upload_batch.py` | form helper 同源后 closed routing；不改名称推导、财期推断/排序/扫描 |
| `dayu/fins/tools/upload_tools.py` | material raw 文本/路径投影、shared combination、schema/公开内部 ID移除；不改 filing 检查 |
| `dayu/cli/arg_parsing.py`、`dayu/cli/commands/fins.py` | material 内部 ID flag、ParsedCliArgs 字段与初始化全部移除；preFactory 组合/空值/ID/parser/实际 call fixture 迁移 |
| `dayu/fins/service_runtime.py`、`dayu/service/fins_direct.py` | 仅真实 handoff annotations/docstring/必要 owner projection；已纯透传者可零 diff，不造适配层 |
| `tests/fins/test_docling_upload_service.py`、`test_upload_usage_contract.py`、`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_fins_service_runtime.py` | owner 与 runtime/tool/job/summary 矩阵，旧 raw 字段/API/fake 身份迁移 |
| `tests/fins/test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py`、`test_upload_batch.py`、`test_upload_asset_plan.py` | 独立 US/CN/HK、batch canonical、资产回归；不改格式/Docling owner |
| `tests/cli/test_fins_commands.py`、`tests/cli/test_upload_filings_from_command.py`、`tests/service/test_fins_direct.py` | 真 CLI parser/Service 消费/raw batch 与旧非法夹具迁移 |
| `README.md`、`dayu/fins/README.md`、`tests/README.md` | 按第 6 节职责，仅写实施后真实行为 |

旧 `build_material_ids` 真 caller 只有 SEC/CN material workflow 与 `test_docling_upload_service.py`；workflow 全改读 handoff，owner 测试改验 typed identity。旧 validator 的同三处引用及 D exports 删除。request/handoff 真消费者已列第 3.2 节；`upload_provider.discover_tools` 只是注册 builder，schema 自动消费，无修复需求，配置/helper/storage/domain filing-semantics 不在写白名单。

## 4. owner 验证矩阵与旧测试迁移

| 合同/owner | 必需断言（共享参数化，避免每 label 重复 campaign） |
| --- | --- |
| R action decision | 四动作×空/非空；非法先于 target/read/prepare，delete+missing/目录/101/raw 循环路径均组合优先；unknown 动作独立入口 typed；合法 auto requested='auto'/pipeline=None，与运行时/独立 façade pair 同源 |
| D 完整身份 | all actions form/name 的 None/空/纯白；双空 form 优先；组合+空/超长先组合；缺 seed+空 ID先字段；长度+fiscal+ID依上述顺序，非法 seed 不进入 digest |
| D name/form | 239/240/241、emoji、组合字符分别按码点、trim 前后边界，无 NFC/截断；padded/lower 与 canonical form 同 ID、name trim 同源，不同合法类别不同 ID |
| D fiscal/ID | year None/1799/1800/2100/2101/-1/0/10000/bool；六 period/空/纯白/大小写/非法/241P；ID None/精确/padded精确/空/纯白/mismatch；typed reason/中立文案，ID 与内部 ID相同 |
| U/tool schema | 消息 bounded/字段可行动/无 CLI flag；共享 MISSING_FILES 覆盖 auto；schema 分清 filing 1000..9999 必填、material 1800..2100 可选、period 两类必填性及空文本差异、name240、ID只断言、无内部 ID输入；不造 observation form |
| R handoff/全部入口 | factory/手工构造/replace/validate 均拒绝 identity/pair/request/selection/plan 漂移；合法 handoff identity不重算；失败零 operation/observation/job/executor/started/company/material mutation，fresh/seeded 同拒；原取消与计数保持 |
| 独立 US/CN/HK 首错 | raw async/sync 与 validated 消费覆盖；非法 ticker/SEC 非US/company identity + 空 form 对照，保原类型/文案；合法 ticker 才身份 typed；未知动作/ID失败在 try 外，零目标读取/批次/转换 |
| 新写/同版状态同源 | fake converter+真实 Fs repository 验 ID/form/name/fiscal 到事件/result/source meta/manifest 的已有字段；repository 协议只读读回，合法 create/auto/update/delete 与无文件 delete；保 filing 两 ID/角色/日期/取消回归 |
| batch 机械解析/owner | None/[]/''/纯白/','/'A,'/'a,b'/['a','']/padded 小写；空 item先多值，raw 到 batch；routing拒绝 raw echo，supported entry canonical→生成 argv→实际 material admission 同值；regeneration 保 raw |

明确迁移：`test_upload_filings_from_command.py:197–236` 改断言 raw `' esg_report '` 与 raw echo，canonical/routing 在 batch owner；tool 旧 `files must be omitted` material 英文断言改同源 reason/message，filing 英文原断言保留；`test_fins_ingestion_tools.py` fiscal schema 的旧逐字断言随新自足文案迁移，覆盖 material null/空/纯白与 filing 必填。
R `test_material_identity_remains_outside_static_admission`、`test_material_missing_identity_keeps_workflow_failure_boundary` 改完整前置 typed 拒绝；handoff delete+raw-files“成功”与 SEC stream/CLI `test_real_cli_material_delete_restores_raw_file_guards` 改组合拒绝，再保合法零文件 delete。
`test_upload_requests_use_source_kind_for_filing_material_discrimination` 当前已含文件但仍无 form/name且硬编码 document_id：补合法 create/form/name、owner ID，保 source-kind 原断言，不用 missing delete 绕过。所有 material fixture、CLI `_UploadMaterialCall` 和 Service direct 旧 doc-1/internal-1 输入迁移；fake pipeline/result 的正常 material ID也与 owner一致，不能靠生产兼容承接非法 fixture。
Service runtime summary/warnings/handoff/early-cancel tests 补 form/name；deleted fixture files=()、requested_count=0，非 deleted 保原文件数；原 stored/summary/cancel/warnings 断言保留。纯输出模型/filing 的 internal ID断言不删除。

## 5. 后续实施验证命令（本轮未执行）

唯一 workspace 的 `.venv` 必须 Python3.11、editable `dayu` 指向本仓库；记录最终 HEAD/解释器/package/命令双流，不能复用其它 checkout 的通过票。以下运行一次完整受影响集合，失败才按原因修复/必要复跑。

```bash
source .venv/bin/activate
python -c 'import sys, dayu; print(sys.version); print(dayu.__file__)'
python -m pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_upload_usage_contract.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_service_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_upload_batch.py tests/fins/test_upload_asset_plan.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/service/test_fins_direct.py --cov=dayu --cov-report=json:workspace/tmp/pr197-g1-implementation/coverage.json --cov-report=term-missing
pyright
```

实现者按实际 production diff 从 coverage JSON 逐文件取 covered/missing/percent，**每个改动生产文件 ≥80%**，不得仅报 R/总覆盖或排除未覆盖行。大型旧文件不足时补有效 owner/入口测试并列明基线、新增覆盖与缺口，交 root 真实裁决；不能宣称达标或降低要求。测试通过与 full pyright 零新增/扩散错误必备，触及旧错误须一起解决。
真实 CLI 最终矩阵由 root 统一收口，按 `upload-material-repair-scope-and-ci-closeout-20261001.md` 固定整体顺序，后续读取 `docs/cli_ci.md` 绑定执行 policy。G1 提供其中一个场景子集，不逐小 label 再做全 campaign：`python -m dayu.cli upload_material --base <isolated-root> --ticker AAPL --action <action> --forms <form> --material-name <name> [--files <authorized-input>] [--fiscal-year <year>] [--fiscal-period <period>] [--document-id <owner-id>] --company-name 'Apple Inc.'`。
模板变量由冻结场景定义产生真实 exact argv，不直接 shell eval；delete 省略 files，旧内部 flag 的空/非空分别验证未知参数，help无该 flag；合法基线后配对 padded/canonical、year/period/name/ID/组合矩阵及受支持跨命令读取。完整输入、双流/exit/screen、Fs前后、repository meta/manifest、durable/Trace/process 证据按统一 run保存；非法 CLI预期 usage=2、无 started/业务写，合法 ID由真实 owner/仓储读回而非硬编码。
旧 Raw已删除，不复用为本轮实证；整体修复完成才冻结最终 commit、完整 mandatory 矩阵和新 evidence，按既有裁决核 oracle/scenarios/readiness与lineage。未裁新行为交 root，不改 oracle求通过；本 G1不编辑 registry。

## 6. README 职责与实施约束

已读 pinned 三 README 的边界：根 README只最终用户当前操作，改掉 delete“忽略 files”旧说明，写 form/name/240、两类 fiscal 域、ID断言/参数移除及可行动错误；不写内部治理。Fins README只稳定能力/contract：完整 admission/handoff、同源事实、入口局部差异，移除“form/name在工作流才检查”。tests README记录新增真实 owner/入口矩阵与运行方式，不报告未来通过票；其无单独 Agent更新章，按现职责与 AGENTS触发处理。
本组不改变分层/装配，故不触发 `dayu/README.md`；不改 Host/Engine/config。新改函数须完整中文参数/返回/异常 docstring，类/模块中文概览；严格 typed、模块级 helper，禁止 Any/object/loose parsing/getattr fallback/默认身份/隐式兼容。

## 7. 残余分类、依赖与停止条件

| 分类 | owner / destination / 本组处置 |
| --- | --- |
| fixed in current slice（待实施验证） | 8 labels及上述必要 review findings；本准备不标“已修复”，实现后逐项证据裁决 |
| covered by later approved slice | O12/14/15/13/18→状态与发布 owner；O25→角色/primary owner；O21/22→内容失败 owner；O33→并发 publication owner；XBRL→既有受控能力队列，不借 G1实现 |
| assigned to later work unit | `fins-material-legacy-identity-seed-disposition`：历史 seed/raw form、skip/delete旧数据一致性、新起算或迁移待独立裁决；不加双身份 lookup/alias、不声称存量兼容完成 |
| assigned to later work unit | `fins-upload-batch-derived-material-name-admission`：批量合法文件名可导出>240名，脚本执行由 G1 owner拒绝；不静默截断/另造阈值 |
| assigned to later work unit | `fins-filing-tool-combination-owner`、`fins-upload-usage-message-channel-neutral` 与旧通用摘要限制：保持既有 destination，本组仅必要共用消息/字段投影，不另设 material form长度或新全局限制 |
| covered by later approved slice / root现队列 | F5 日期/来源财期语义独立；同树 writer串行与闭环后API重绑是执行前提，不冒称业务依赖，也不读未来报告 |
| requiring explicit user decision（仅发生时） | 真实 owner/API缺失、首错合同无法保持、需要新增业务字段/历史迁移/改变 seed或公开语义，具体停止并给直接证据；已明确240/UM裁决无需重问 |

G1-S1行为完成信号：8标签与每个 accepted必要finding均有owner级实现/消费/无副作用证据，受影响pytest/full pyright/逐生产文件coverage与README职责已核。正式门禁由root按现流程同版独立审查/裁决推进，不由本准备接受；完整PR/CLI收口仍另需全部批准修复完成。

## 8. F5闭环后 root 最终重绑清单与交付

1. 绑定唯一分支最终已接受 F5源码 SHA，重新核 R admission/日期顺序/hand-off constructor/validate/summary 的真实位置与字段；不得拿本 pin 或 F5自报冒充最终代码证据。
2. 重绑 D `build_material_ids/validate_material_upload_ids/resolve_upload_action/prepare_upload`、U enum/message owner、planner与full-basename命名合同；确认上述 planned API替换与五字段required handoff，而非依旧照搬旧函数签名。
3. 重绑 CLI preFactory/parser/ParsedCliArgs、Service union与runner、SEC/CN/HK raw/validated调用图及原ticker/market/company首错；实际不存在的旧API不造回去。确认所有 builder/validator/raw内部ID caller/test fixture全迁移。
4. 重绑 batch raw parser→canonical routing→entry/argv、tool共用filing/material投影、实际测试文件名/覆盖白名单、README当前职责；复核旧findings每条仍可定位且有计划处理，失效证据由root分类，不直接丢失要求。
5. 锁同版候选plan+源码后进入正式 planreview；本准备不发Agent、不accepted gate、不更新controller/旧goal/plan/adjudication、不实施。实现/审查仍归root现队列与现draftPR197。

本轮交付仅本文件与独占证据副本/索引；核验 freeze/47 SHA、必要 pinned API与调用者/裁决，不运行网络/OCR/Docling/PDF/pytest/pyright/cov、不读私有输入或其它Agent F5报告、不推进Git。交付后停止。
