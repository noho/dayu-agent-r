# 601225-annual-fulltext：plan r1 re-review 总控裁决

- Gate：re-review → fix（r2）；r1 不通过，不进入 implementation。
- 被审 plan SHA256：37663c068ee5d6b3f39fd60642ecf4c8c134ff760d0649a0fe12c8a0bef34855。
- MiMo / DS 两个 runner 均实际退出0/completed，产物分别 docs/reviews/plan-review-20261012-142347.md（fail）、142348.md（pass-with-risks）。两份已读，需修订而非按多数放行。
- scope/owner：原 goal confirmation 与初轮 adjudication 保持；以下是具体合同收束，不新增其它公告、日期、OCR、历史恢复或 CLI/schema 目标。

## 裁决

| r1 finding | 裁决 | 当前状态 | 必须决策/修订 |
| --- | --- | --- | --- |
| MiMo-r1-01：不重下摘要措辞冲突 | accepted（明确阶段含义） | 未修复 | “不重下摘要”仅指不把它作为 repair target 重新提交，不覆盖/删除/修其旧资产；不禁止 discovery 为确认隐藏摘要取得原文。REPAIR_REQUIRED 本地不作可信完整输入，因此可对 raw FY source GET facts；确认 summary 后丢弃 payload，final unselected repair typed拒绝，源/公司零写入。明确该场景允许一次 facts GET，失败则按发现失败，不能凭未持久kind提前伪造selection。 |
| MiMo-r1-02：异常作用域不唯一 | accepted | 未修复 | local witness publication变化/存在变化用 SourceIntegrityRevisionConflictError；同revision变repair用 SourceIntegrityRepairRequiredError；UNSAFE用原preflight；三类由workflow显式 integrity-abort catch 立即停止后续candidate、保留已确认前缀，整体失败。当前per-filing特殊catch确实漏RepairRequired，必须加入。CnDownloadAnnualPublicationError的source_identity_conflict/period_metadata_mismatch/source_document_facts_mismatch只为单filing失败，普通candidate继续、整体终态FAILED；若是selected repair则repair gate终止后续且公司不发布。两组类型不可互相借reason升级/降级。 |
| MiMo-r1-03：无witness COMPLETE只看meta | accepted | 未修复 | 每个CN FY COMPLETE skip都须有该revision的实际原件full/year事实。已有witness同rev可复用其确认；无witness（预读筛掉、fresh retry、新出现COMPLETE）必须在filing owner读取exact当前target snapshot的声明original PDF，用同facts owner确认，再允许skip。角色缺省/歧义不能靠文件名、唯一PDF或URL猜原件：typed拒绝，不能metadata-only成功。不新增远端刷新/覆盖。共用实际原件读取projection，必要时新增窄cn_annual_report_source.py供workflow/filing复用；不把I/O塞进纯parser、不重复各自解析角色。 |
| DS-r1-01：遗漏HK借用夹具测试 | accepted | 未修复 | P5.5命令加入 tests/fins/test_hk_period_rebuild.py，并记录共享helper受影响回归。无需改该文件行为或增加HK业务目标。 |

MiMo关于Docling与provenance验证的open question也在r2补足：实际JSON使用现有Docling模型验证；source_meta.primary_document与声明docling角色/文件准确对应；实际PDF/JSON SHA分别对照当前schema实际声明，source_fingerprint复用公开build_content_fingerprint(bytes,bytes)验证，三新全文fiscal_year_source=source_document。不发明现有schema不存在的derived-from字段或从URI/文件名反推关系；转换实际入参与当前schema可提供的origin信息须按真实API明确验证及局限。coverage维持已确认实际改动生产/测试文件80%、utils免coverage但类型检查。

## 状态与修订边界

- 原DS1、DS3、DS4、MiMo2、MiMo4：两个r1 reviewer均验证计划层已修复；回写可参考两个r1 artifacts。DS2/MiMo1/MiMo5有部分修复，不能放行；r2仍须同版双路复审。
- MiMo6原scope漂移裁决仍 rejected-with-reason / 证据失效；不重开共同协议或既有来源字段的新抽象目标。
- allowed新增仅 exact原件读取的共享窄Fins owner（如必要）、对应owner测试；workflow异常catch/COMPLETE证明及验证工具规格均在原scope。没有storage schema/仓储实现/CLI改动，不修历史坏源；缺原件角色是明确安全失败而非新兼容分支。
- 所有完整性/业务事实检查仍从当前snapshot及facts owner派生；prepared远端facts不能证明旧本地PDF性质。身份与财期meta相等不是原件full性质的真源。
- Sol只修plan与r2 fix artifact，不实施生产代码/测试/依赖/README、不commit。修订的异常类型/catch/继续或停止/前缀/业务副作用矩阵必须可直接实施，不能留implementation再设计。

## 验证、风险与下一入口

总控已直接读取workflow的per-filing特殊catch和generic继续分支，确认证据同源；核对既有source_fingerprint公开helper只需要实际两文件bytes，原file entry没有需强行新增的derived-from字段。原文/历史限制、unknown布局、淘汰候选成本风险仍原分类/owner/destination；本轮四accepted缺口归 fixed in current slice（plan fix/re-review责任，尚未修复），owner Sol/总控，destination r2 plan/fix/re-review。不存在未分类风险或需要改变binding goal的具体问题。

current gate / next entry point：fix（plan r2）。本artifact：docs/gateflow/601225-annual-fulltext-plan-rereview-r1-adjudication.md。


## 总控最终回写（r3 同版复审后）

本轮历史结论保留；最终 finding 裁决与逐项状态以 [最终 plan 裁决](../gateflow/601225-annual-fulltext-plan-final-adjudication.md) 为准。全部 accepted 项已由后续双路同版复审验证为计划层已修复；MiMo-06 rejected-with-reason / 证据失效维持。r3 两路均 pass，不代表实施或真实验收完成。
