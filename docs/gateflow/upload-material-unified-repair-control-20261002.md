# upload_material 统一修复 WU：总控与范围合同

## 当前平台验收修订

用户已选择 macOS 先验收、Linux/Windows 验证延期，binding 修订与后续 owner 见 `upload-material-unified-repair-goal-amendment-20261002.md`。该具体选择覆盖原三平台验收门槛；本机真实受控 XBRL 及其它业务成功信号保留。

用户随后确认明确运行库只读例外，见 `upload-material-xbrl-runtime-boundary-goal-amendment-20261002.md`；禁止工作区/其它私有文件内容和出站网络，taxonomy可信来源/完整性/受控复制复验保留，资源闭包解析器方案撤销。旧更强资源独占假设不能重新成为阻塞。

## 最新执行指令（覆盖旧排程）

用户 2026-10-02 明确：所有剩余修复项合为一个 WU；遵循 Gateflow，按完整可验证行为切尽量少的 slices，不按标签、文件、模块机械拆分；PR review 仅在全部 slices 及 aggregate deepreview 完成后进行。用户随后纠正：**upload_material CLI CI 与 oracle/scenario 正式登记在修复 WU 完成后单独执行，不并入本 WU**。旧 handoff 中六个候选 WU、findings 后停机及 MiMo/MiMo-flash 默认路由均为历史排程。

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，唯一开发分支 `codex/upload-material-oracle`。只普通提交/推送至已有 draft PR197；main 不动，不新增 branch/worktree/clone/detached。用户手工 merge。

外部子进程 runner：gpt-6-sol 负责 plan / implement / fix；MiMo 与 ds-flash 两路同时独立 review（用户书写 ds_flash 对应 runner provider `ds-flash`）。总控核完整结构化结果、独立复核关键事实并裁决。每次显式绝对 --cwd、全新独立 output/stderr/Codex last-message、唯一 label、preflight；禁止由子 Agent 提交/推送/派发其它 Agent。不得绕过审批或无限重试。

## 修复 WU 的 binding scope

已批准标签：O05F01 O06F01 O07F01 O07F02 O09F01 O10F01 O12F01 O13F01 O14F01 O15F01 O16F01 O17F01 O18F01 O21F01 O22F01 O25F01 O33F01；另 O20F02 受控 XBRL。精确业务语义以正式 UM adjudication、后续用户明确选择及已有 goal 为准，不沿用旧建议重裁。

目标：在唯一语义 owner 修正完整参数/稳定身份准入、exact primary 与角色指纹、材料状态及 overwrite/amended、内容失败同源投影、同 identity 并发权威裁决，以及受控 XBRL 部署/转换能力。材料仅在 Docling 生成且 manifest 登记提交成功后算成功；公司是独立事实。

成功信号：上述已裁行为的 owner contract、实际入口、失败/取消/并发及真实仓储读回验证成立；受影响测试、逐生产文件覆盖率与全量 pyright、对应 README、同版双审/总控裁决及完整 Gateflow artifacts/checkpoints；最后一次正式 PR review、普通 push/readback、final closeout。XBRL 保留原 goal 的有效 instance/受控 taxonomy/依赖与隔离证据要求，不用合成 happy path 或标题文档冒成功；外部资源/上游阻塞必须如实登记，不能擅自降验收。

非目标：不重做 F2–F7/#198/已实施上传标签；22 个独立 residual 候选不自动加入；不修 Docling 抽取准确性，不造新财期规则/旧库兼容/历史日期迁移；不 merge、不重复 #198 评论。最终全矩阵 CLI CI 与正式 registry 写入属于 WU 后阶段，不能列为本 WU slice 或 closeout pass 条件。修复本身所需真实 CLI 集成探针（例如真实双进程并发、XBRL instance 上传）仍是既有修复成功信号，不代替后续完整 campaign。

已登记全 PR diff-check 证据卫生项：`tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.log` 的原 stdout EOF 空行；只允许可逆字节/SHA 保全及引用同步，不能 trim 原 Raw 伪造历史。计划须明确其收口归属，不为该项单开产品 slice。

## 第一性原理与现场证据

本次实时核：HEAD/tracking/live/PR197=`619d092ab4278645203c7ebe08515f7697d92b71`；工作树 clean；main/local/live/PRbase=`fac32ecbff9bfe792b63ee9667c8697826b631f4`；PR OPEN/draft；旧 runner ledger active=[]。

直接源码：`ingestion_runtime.py` 的 material handoff 只带 request/selection/asset_plan，未包含统一身份事实；`docling_upload_service.py:build_material_ids` 独立 trim/upper 且未检查名称长度/财年域；`sec_upload_workflow.py:run_upload_material_stream` 仍从 raw 字段重算身份、公开 internal ID 断言及动作。对应正式裁决要求统一前置受理，动机成立。G1–G5 与 XBRL preparation 只是旧 pin 上的 proposal，必须按当前源重绑，不当 accepted plan。

根总控探索读取中若路径不存在/rg 无匹配，只是 locator 修正：不存在的 material_identity.py、tools/ingestion_runtime.py、ui/cli/fins_commands.py、xbrl-controlled-support-goal 均已改用实际 `pipelines/docling_upload_service.py`、`fins/ingestion_runtime.py`、`cli/commands/fins.py`、`upload-material-o20-xbrl-runtime-goal-20260929.md`。不据失败读取得通过结论。

## 当前 gate / 下一入口

- goal confirmation：沿用户已明确批准范围及最新排程纠正确认；本文件固定边界。
- current gate / next entry：accepted PR review commit；正式完整main...44双审及491delta双复审均已ended outer0/root核收，UPR-R01/R02已修，MiMo未来访问假设finding rejected-with-reason。详见formal-pr-final-root-adjudication与findings register。fullpyright0/生产source88同hash；当前remote44还未含localfix，继续普通commit/push/readback→draft-PR-pass→finalcloseout，后独立完整CLI/registry。

- planreview 必须挑战切片成本、机械拆分、可合并性与 future-slice 漂移；默认避免超过 3 slices，超过须直接理由。
- 所有成立新修复即时写 artifact/控制表；accepted finding 必须已修并经复审才通过。普通 gate 通过后继续固定顺序，不因 gate 完成停机。

## WU 完成后阶段（未启动）

按 `upload-material-repair-scope-and-ci-closeout-20261001.md` 与 `docs/cli_ci.md` 重建最终完整 mandatory upload_material campaign，冻结最终 commit/parser/corpus/policy，真实采集 stdout/stderr/exit/screen/FS/log/process/durable/manifest 等适用证据，再按用户裁决正式登记 oracles/scenarios、版本与 supersede lineage、双向覆盖及 readiness proof。旧 Raw 根用户确认删除，不索要同一备份、不编造旧 hash，不用其它命令 registry ready 代替本范围。

修复 WU closeout pass 不等于整体任务完成；继续后续 CLI CI/登记阶段，直到用户当前大目标完成，或遇到真实 blocking stop condition。

最新集中修复核收：upload-material-unified-s3-integration-fix-root-adjudication-20261003.md。此处记先前集中fix核收历史；后续T03/T04已修并通过同版双复审及当前完整42回归，S3已accepted checkpoint ec54351e。旧42 failed历史不改。

## Aggregate 当前补记（2026-10-03）

两路外层已actual0结束，DS170tools/MiMo119tools及113冻结输入0漂移已root核。DS三小项+Raw登记 UA-R01/R02/R03/UA-E01 accepted未修；MiMo无新finding。两路scope自述有部分不完整，root按实际证据部分采纳，复审须补DS ZIP尾/架构README及MiMo31tests/6docs完整diff。current gate=fix aggregate deepreview；一次gpt-6-sol集中fix，之后同版双复审并核实际covered，不新增slice。参见aggregate findings register及DS/MiMo root audit。

## Aggregate 集中fix核收后的当前入口

两原审scope自述仅部分采纳；当前四项已实施，671passed、fullpyright0、Raw exactbytes保全、9364保护项zero、gpt outer0/turn.completed/54actualcommands均root核。current gate=re-review aggregate deepreview；不得把报告交付当pass。四项和原审MiMo31tests/6docs、DS ZIP尾/dayu README缺口在本同版双审一起收口。

## Aggregate最终同版收口

MiMo44370/DS56153外层都actual0，完整70/81tools及必要证据root核；8236行diff和DS253/279行逐字coverage证明已核。四项accepted已修复，无新finding；aggregatepass，下一accepteddeepreviewcommit并普通push已有draft197进入正式PRreview，不停普通gate。旧状态段均历史。
