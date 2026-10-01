# F5 v2 计划审查：总控当前裁决

当前 gate：plan review；MiMo2205/Kimi12721并行在途，未gate pass。输入plan SHA256 `40b5c8f0dfff1b4106ee5d00def7a0821a14c34de64aea92fbeb6dd877a716b6`，58项冻结 SHA256 `bb33abf812025d094d7371c7d083c5128aac7749dabf9a65aaaa1989006b0704`。主树/branch唯一，main未动。

## 作者交付核收

Sol19367 outer0；104可解析JSONL、42 completed command、turn.completed、无error/failed事件、stderr0、canary逐字匹配；45 current+45 originals实际哈希全匹配，仅新增两文档。完整凭据 `workspace/tmp/pr197-controller-collection-20261001/f5-plan-v2-author-root-receipt.json`。这是交付验收，不是plan pass。
两条outer非零item_28/item_36已解释：错误direct_messages路径由实际direct_event_text恢复；未创建的新plan/未含label协议的freeze检索无匹配。outer0复合命令内另有两次glob无匹配、observation.py/cn_download_integrity.py不存在，作者记录并实际定位observation_handle/domain/document_models/cn_download_workflow；不以复合命令0抹去失败。尺寸探针仅合成预算检查，不生产验证；没有pytest/type/cov claim。

## 已登记总控 finding（双审仍独立在途）

### F5-V2-A1-未修复-[中]-终态持久摘要要求与合法未执行路径相冲突

- 位置：候选§7 durable校验、§8取消/错误及其最后非目标。
- 直接证据：当前实际 reader 为 `ingestion_runtime.py:_record_from_json`（约8903行），候选写的 `_job_record_from_json` 不存在。`_save_failed_from_exception` 调 `_save_failed` 不给result，`_save_cancelled`/启动前取消及store原子取消同样可能留空；这些不是旧库兼容路径，而是当前fresh job合法分支。
- 反例：新job在执行前取消，或Q2本地读取异常在发现前原样终止。候选一面要求所有terminal DOWNLOAD都有完整新schema，一面要求无处理事实调用None、普通异常全局快照不扩入；若照写reader，已正常保存的FAILED/CANCELLED会无法再读取，二次终态化也失败。
- 裁决：accepted，未修；owner为download typed contract与runtime job生命周期，不修改消费者fallback，不为旧schema加兼容。
- 修复目标：精确列出fresh-schema无业务结果与已有typed结果两种当前合法状态及写/读规则；有结果必须严格新schema，正常完成/存在unknown不得空；开始前取消/发现前异常如何显式表示没有业务结果必须一致，不能由JSON反推/默认补字段。reader正确实际名字/所有writer迁移到位，测Q2原异常、启动前取消、A已提交后取消/故障及读取，保持scope对late ordinary完整快照的既有非目标。
- destination：本gate一次集中plan fix；MiMo/Kimi其他material findings收齐再同Sol批量修。不单独启动元数据修复循环。

## 技术裁决方向与未完事项

有未知时overall FAILURE、job FAILED、CLI exit1、wait failed，同时保全已确认处理行及A发布后的partial摘要，符合用户“明确未知而继续A”的决定；待双审后根据实际owner核定，取消/原typed原因优先。单完整F5-S1，不按模块拆。原N01/N02仍accepted未修，原upload17标签+XBRL及最终真实CLI在F5闭环后继续。两路报告/完整JSON/外层终态/关键源证据收齐后才final gate裁决。

## Kimi12721 终态与总控逐项裁决（MiMo2205仍在途）

outer0，完整JSON subtype success/is_error false/terminal completed，83turns，无permission_denials，modelUsage kimi-k3[1m]，stderr仅精确非致命unrecognized_model，canary match。58current+originals root再核全匹配。报告 `docs/reviews/plan-review-20261001-190945.md`；独立核收凭据 `workspace/tmp/pr197-controller-collection-20261001/f5-plan-review-kimi-root-receipt.json`。Claude仅汇总，不能声称逐中间tool全部成功；关键引用已root直接读源码和owner测试，没跑产品测试。

- **F5-V2-A2，中，accepted未修（Kimi01）**：候选§4把同sourceID核心事实冲突变成一条财期未知，但实际 `_deduplicate_hk_announcements` 明确raise ValueError，owner测试约721行也断言同源完整性错误。此冲突不是财期证据不足；保持原协议错误/原测试，不软化为unknown。destination本gate一次集中planfix；补§9回归。
- **F5-V2-A3，低，accepted未修（Kimi02的有效部分）**：candidate排除副语言年度证据，会收窄现行先从全部去重raw汇总annual_ends、后排英文主候选的规则；保留可信英文原始年度截止日证据，但英文副本仍不生成主候选。destination同一集中planfix+同证据集合回归。Kimi声称local无language字段不采：root直接看到upsert持久化 `source_language=candidate.language`（约266行）。这里的修复依据是可信证据不应因语言丢失，不是该错误字段论据。
- Kimi03（直接selector测试迁移清单）：§9已包含selection测试，机械pyright/pytest也会暴露；不单立material blocker。作为同轮实施/计划明确义务补六直接调用，保持核心冲突测试，不另开报告修复loop。
- Q-A root最小技术裁决：远端unknown的existing_document_id恒None，source_id保真实provider来源引用；只在rebuild实际已知物理文档时带原ID。不新增未知canonical身份索引/分配/模糊反查，仅为可选定位不扩scope。
- Q-B root技术裁决：既有period_resolution_version由当前owner升级为hk-period-v3，记录真实新语义，保留document/content版本；不新字段或历史迁移。
- Q-C并入A1修正确实存在的 `_record_from_json` reader，绝非兼容别名。

新增A2/A3及A1均先登记，MiMo返回后统一裁决并交Sol一次集中planfix；目前无planpass/实施，N01/N02仍未修。

## MiMo2205 终态、组合门禁与集中修复范围

MiMo outer0、有效JSON success/is_error false/terminal completed，95turns，modelUsage mimo-v2.6-pro[1m]，canary match，无permission_denials；stderr精确非致命模型识别警告。完整报告 `docs/reviews/plan-review-20261001-191824.md` 已读；核收 `workspace/tmp/pr197-controller-collection-20261001/f5-plan-review-mimo-root-receipt.json`。58 current+originals root再核全匹配，报告初始HEAD b3不充当前58af。Claude中间逐工具可见性仅summary，关键事实root已独立读。

- MiMo F1与A2同根因，采纳“计划歧义需修”；不采“同来源核心冲突必须unknown继续A”：用户A/B裁决讨论财期推断，可信provider来源自身事实冲突属于原协议完整性，不能反向借该裁决弱化原错误。保持原ValueError与owner测试。MiMo条件性pass-with-risks不计gatepass。
- MiMo OQ1 root技术裁决：已确定财期但原标题无唯一截止日时，当前report_date为None；同一次既有metadata事务把source/manifest/processed的report_date与report_date_source同步置None，不能公开None而durable保旧事实。`repository_protocols.FilingSourcePublicationIdentity.report_date`与inspector接受None，processed manifest从merged_meta同源投影。未知B仍不写源/processed，不混这两条路径。补known-no-end旧日期反例；不新enum字段/历史迁移。
- root取证中两个猜测的storage文件路径rg不存在，实际protocol/inspector/processed core已定位直接读；复合outer0不抹去检索失败，无剩余证据gap。
- 其余MiMo风险按v2已有owner/实施验收，不重复注册：366所有消费点、4096真实边界、取消/typed中止保全必须实测；超窗/过渡财年仍信息边界。

**本轮plan review gate=failure，next entry=plan fix。** A1/A2/A3 accepted未修，N01/N02尚未产品修复。Sol一次集中修正v2，并显式落实原selector测试迁移、remote未知existingID=None、rebuild原真实ID、audit版本v3、总体unknown FAILURE+保全partial与取消优先。修正后同版MiMo/Kimi窄re-review这些关键差异及关联owner，不重读全部旧计划/全仓/已closedWU，不为报告元数据单开fixloop。作者仅plan，不产品写；accepted plan checkpoint后才F5-S1实现。
