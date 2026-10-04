# upload_material registry plan review 总控裁决

2026-10-04T01:50:31.012589+00:00

**当前门禁未 pass，进入一次集中 plan fix；仍唯一行为 S1，不进入实现。** 冻结计划5c95926bbf7ef2dab07499462c730bd071c83aec90133819685f71d36c6cc31c、HEAD22eca6c313005e3c5185340f2d6b535ab2583056。MiMo38533 actual0/10840events40tools；DS42328 actual0/66164events63tools；完整指令Read、CANARY/报告/源身份/全轨迹与失败恢复已root核，私有双归档。两路推荐不自动变 accepted；下面为唯一总控裁决。

## 已登记修复项（先登记再实施，全部同一次planfix）

| ID | 状态/严重度 | owner及直接问题 | 修法/验证点 |
|---|---|---|---|
| REG-PLAN-R01 | accepted/未修复/中 | focused-source retention_receipt不在四publicroot，而source-root只允许源码，必填无法解析 | S1精确复制原D/root-code-fix-sol-01-retention.json到bounded docs/gateflow/evidence/upload-material-registry-20261003/retention-receipt.json；给fixedrepo相对ref/bytes/SHA、source-root严格containment/无symlink读取此列明治理receipt，明确source-root可读取的源码/批准authority来源与列明receipt，不能作publicroot或任意private读入口。不读取receipt内部archive paths、不把private保全当publiccredit；缺/错receipt拒绝定位。 |
| REG-PLAN-R02 | accepted/未修复/中 | 叙述报告混裁决、WARN数/Doclinghash成为业务threshold两项负例没有机器判定contract | 改为code review/root逐predicate及报告语义人工检查，删除相应pytest自动语义承诺；不加NLP/字符串启发式、固定样本数字禁入或新semanticframework。机器仍校typed结构/路径/hash/来源/refs/coverage，人工失败作为codefinding先登记集中fix，不能假机器全能。 |
| REG-PLAN-R03 | accepted/未修复/低 | 新material子shape/applicable_from/review-target产生gate、CLI --check与v6历史边界需可生成代码 | observed_behavior明确复用现有upload_filing publication六键形状（run_ids/report_ids/report_digest_sha256/adjudication_artifacts/report_frozen/scenario_refs），不发明frozen别名/不存在provider数据；具体types/对应来源与配对定义。oracle applicable_from={date,target}，scenario为next-upload-material-conformance-run字符串。review-target锁定schema/gate与必要SHA/ID，不自指或把未来review写pass。CLI唯一 --check 模式，缺flag/参数误用exit2；candidate bootstrap只函数API，strictCLI总要求已有proof/status投影。每份historical_ready_proofs仅本registry旧proof原值；v6全文件去顶层status/proof的新basis明确，v5 records-only仅历史说明，旧proof opaque全值比较保留、不重算或兼容解析。§1补§11.2投影owner。 |
| REG-PLAN-R04 | accepted/未修复/中 | root同源反例：current_reviewed_source要求当前11SHA同、allowedfile却允许testsREADME加登记测试条目，source11实际含testsREADME SHA52a12daf… | 区分真实测量5模块的live产品source guard与旧11 review identity的冻结metadata，不把历史source SHA冒当前、不因授权docs/test增加误判产品漂移。保实际5模块逐bytesSHA必同；旧11原review身份/当时历史测试差异如实留存、proof ref anchor校验；无需通用profile/分类framework，不重跑802，不新增source漂移容错。相关负例是生产模块漂移拒绝、授权README新增允许且历史descriptor不改。 |

## 未采纳与收窄

DS PR-DS-01高风险digest错误 **rejected-with-reason**：root实测旧arrays b99a7339…/9de64adb…与整文件去顶层9561322d…/264b42be…都正确但输入范围不同。现有计划明确新增proofv6/currentformula/旧basis immutablehistory，docs/cli_ci.md §4.6未规定records-only公式，且无既有代码proof消费者。不能据历史数值推出新current公式错误或强制旧算法；不改新basis、不重算旧proof、不引入compat。说明不够显式的低成本文案纳R03而非高产品错误。

MiMoF3a「旧observed_behavior没有adjudication_artifacts/13键」事实前提 **rejected-with-reason**：root完整查看6oracles，13是顶层record keys；现有cli.upload_filing.document-publication的observed_behavior恰含adjudication_artifacts，6内键。仍采纳锁定新material子shape的生成规格需要，纳R03。DS两OQ合并R03，不增加fixloop。MiMoQ1充分性锚点：每surface必须有唯一适用已批准authority+真实测量/requiredrefs，不能写入唯一owner时登记gap/停止root裁决，不以两票替代用户；现成已裁不重问。

## 证据、工具及残余

DS原结果称数处outer非零/未遮蔽，但实际6621/18216/64722被后续命令遮为0，2真实is_error7025/7422恢复，最后JSON实际可解析；root单独reporting-corrections与原alltools/双archive保全。MiMo截断页字段恢复、其报告文件写入方式以实际command为准，不凭时钟假O_EXCL。没有重跑产品、网络写、main变更；两registry全值仍before相等。

receipt易失性在R01同scope boundedcopy解决，不另未来WU；focused导出/卫生/实际validator与有意义负例属于本S1；跨平台、上游质量、历史日期及22residual沿旧owner/目的地，不拉入。本轮无新业务裁决或unclassified risk。所有修复仅plan必要contract澄清，19predicate/31authority/oneS1/两source/fourroot边界不变。

Current gate=plan fix；gpt-6-sol一次集中处理R01–R04与整合OQ，之后精确delta同版两路re-review→acceptedplancommit。新review-target/helper/data均只在S1实施，不在planfix偷做。报告SHA/完整审计/备份receipts见workspace/tmp/upload-material-registry-20261003/root-plan-review-*-02-*，原报告不覆盖。

## 同版复审后最终状态（2026-10-04）

REG-PLAN-R01–R04现均 accepted / 已修复，由MiMo32518与DS34390同SHA89676282 delta复审验证、root全工具/真实来源独判通过；上表未修复保原登记历史。MiMoQ1 routine envelope确定 historical_ready_proofs 为只装自身原proof的单元素数组，S1锁测试，不新业务规则。详见 plan-review-acceptance-20261004.md / plan-review-proof.json。Current gate=accepted plan commit；next=唯一S1 implementation，不停普通gate、不重开产品裁决。
