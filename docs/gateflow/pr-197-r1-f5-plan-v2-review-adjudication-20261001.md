# F5 v2 计划审查：总控当前裁决

当前 gate：plan review / re-review 已由总控接受，待 accepted plan commit 及 F5-S1 实施。以下初次输入记录为历史：输入plan SHA256 `40b5c8f0dfff1b4106ee5d00def7a0821a14c34de64aea92fbeb6dd877a716b6`，58项冻结 SHA256 `bb33abf812025d094d7371c7d083c5128aac7749dabf9a65aaaa1989006b0704`。主树/branch唯一，main未动。

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
- MiMo OQ1 root技术裁决：已确定财期但原标题无唯一截止日时，当前report_date为None；同一次既有metadata事务把source/manifest/processed的report_date与report_date_source同步置None，不能公开None而durable保旧事实。`repository_protocols.FilingUploadPublicationIdentity.report_date`与inspector接受None，processed manifest从merged_meta同源投影。未知B仍不写源/processed，不混这两条路径。补known-no-end旧日期反例；不新enum字段/历史迁移。
- root取证中两个猜测的storage文件路径rg不存在，实际protocol/inspector/processed core已定位直接读；复合outer0不抹去检索失败，无剩余证据gap。
- 其余MiMo风险按v2已有owner/实施验收，不重复注册：366所有消费点、4096真实边界、取消/typed中止保全必须实测；超窗/过渡财年仍信息边界。

**本轮plan review gate=failure，next entry=plan fix。** A1/A2/A3 accepted未修，N01/N02尚未产品修复。Sol一次集中修正v2，并显式落实原selector测试迁移、remote未知existingID=None、rebuild原真实ID、audit版本v3、总体unknown FAILURE+保全partial与取消优先。修正后同版MiMo/Kimi窄re-review这些关键差异及关联owner，不重读全部旧计划/全仓/已closedWU，不为报告元数据单开fixloop。作者仅plan，不产品写；accepted plan checkpoint后才F5-S1实现。

## 集中planfix交付核收（未re-review pass）

Sol18548 outer0、55可解析JSONL/19 completed commands/turn.completed、无error/failed事件或outer非零工具、stderr空、canary逐字匹配。60 readonly current+61 originals root逐件核不变，唯一现存修改是plan，唯一新件fix说明；完整凭据 `workspace/tmp/pr197-controller-collection-20261001/f5-v2-plan-fix-author-root-receipt.json`。复式检索不存在manifest_models/假类型名已定位domain真实manifest/FilingUploadPublicationIdentity及nullable/processed owner；没有据缺失符号作实施设计。更正本裁决的旧类型名，nullable事实来自实际类型和inspector，不为此另开reportfix。

修后plan SHA `6c5a18d292537a7942f4a383c66c95d971beec1d7aed4659340a290670ac52cd`，198行；A1/A2/A3及root身份/v3/known-no-end/真实迁移项文本已修，状态暂为“已交付，待同版复审确认”，不是accepted plan。保存原快照diff `workspace/tmp/pr197-f5-v2-plan-fix-sol-20261001-01/plan-v2.diff`。root直接核新fresh有/无结果区分、writer+reader双向校验、明确None与原子取消投影路径，以及保持协议核心错误/英文证据规则。下一入口plan re-review，仅审这组差异与真实关联owner，不重读全仓/旧plan/closedWU，无产品writer；通过后accepted plan checkpoint，立即F5-S1实现。

## 同版窄复审终态与新增 owner 遗漏

Kimi87476 outer0、24422有效streamJSONL/51turns/50tool calls-results全配对；MiMo32468 outer0、18920有效streamJSONL/60turns/59tools全配对；各单一result success/is_error false/completed，无permission_denials，64current+64originals root核全一致。两个stderr仅精确非致命unrecognized_model。Kimi最终简报省略runtime/canary，但正式报告header与实际当前Read凭据逐字匹配，满足本轮报告协议，不是canary mismatch，不为简报元数据另开fix。完整配对trace与collection分别在 `workspace/tmp/pr197-controller-collection-20261001/f5-narrow-{kimi,mimo}-complete-tool-records.json`/`f5-narrow-{kimi,mimo}-collection.json`。未发现tool error或输出失败诊断，复式shell隐藏子exit仍有限，关键owner root独立核。

报告 `docs/reviews/plan-review-20261001-194823.md` 与 `docs/reviews/plan-review-20261001-200817.md` 全读。A1/A2/A3修后计划经双方确认且root复核，标为**plan已修复**（非产品已修）；runtime“两个”to_json调用措辞不准确实际四点，必填签名+明确迁移/全pyright覆盖，作为实施义务，不单开reportfix。

### F5-V2-A4-未修复-[中]-HK 日期来源规范遗漏正常 download 发布 writer

- 直接证据：实际 `cn_download_source_upsert.py:_build_base_meta` 约255行在report_date=None时写period_inferred；新rebuild计划在同一事实下写None。download→rebuild→overwrite download同文档来源标记翻转，非假想风险；源/processed元数据各是相同日期事实投影，不能各自定义。
- 裁决：MiMo finding1 accepted；Kimi无finding不替代此根因证明。**本窄re-review gate仍fail，下一入口集中plan fix A4**。A1/A2/A3保持已修不重开，N01/N02尚未产品实现。
- 最小实施合同：仅本F5 HK的原标题唯一截止日与来源标签由同一个已有财期/标题owner helper产生，正常download `_build_base_meta` 与rebuild复用；确定日期→原source_title，缺唯一日期→report_date及其来源均None。不得保留writer-specific例外、下游fallback或重新猜日期；保持CN/SEC原解析/既有独立来源语义，不借此扩其scope。现有nullable字段，非新schema字段/enum或历史迁移。
- 验收：同一HK known-no-end真实仓储文档 normal download→rebuild→overwrite download（已有processed则纳入）来源/日期稳定None，源/相关manifest/processed同源，content/document ID与版本按原规则保全；有明确截止日仍source_title；CN/SEC既有回归保持。只纳入本次必要owner/测试，不新增行为slice。
- 根取证一次额外猜测 `cn_download_one_filing.py` 路径不存在；实际本finding的writer源码 `_build_base_meta` 及其caller已直接读取，缺路径不作证据、不影响root裁决，后续仅实际imports定位，不据假名设计。

A4立即登记三controller与本artifact；交Sol仅补该owner规则/调用与回归一轮，之后双方仅复审该修正，不再重读整个job/取消已修合同。产品writer尚无，接受计划之前不可实施。

## A4 单点计划补修已交付，等待窄双审

Sol30256 outer0，50有效JSONL、17已完成commands、turn.completed、stderr空、当前canary逐字匹配；12 readonly current+13 originals root核不变。唯一内部exit127为zsh特殊path变量覆盖PATH，后续完整输入校验已恢复，root独立匹配；猜测路径检索恢复实际owner，未依赖缺失符号。凭据 `workspace/tmp/pr197-controller-collection-20261001/f5-a4-planfix-author-root-receipt.json`。

新202行计划SHA `e4b578807345593f0af6698189044963931b12ba5d13a76da94e553e581644d8`，本次真实差异5增1删；不是相对已提交旧计划的累计差异。root直接读取日期writer/实际rebuild与diff：共享既有calendar helper、正常HK与rebuild两writer、CN/SEC原边界、processed原状态机及三步回归已具体化。A4状态“补修交付，待同版复核”，A1–3保持plan已修。产品源码仍未修改，计划尚未gatepass。下一入口MiMo/Kimi仅复核此项，随后accepted plan checkpoint及单完整F5-S1。

## A4 双路核收与计划最终裁决：accepted

MiMo23705 outer0，33turns、32 tool calls/results全配对；Kimi43186 outer0，34turns、33全配对；两者有效完整streamJSONL、单一result success/is_error false/terminal completed，无permission_denials/子派发/未恢复tool失败。stderr仅精确非致命unrecognized_model。正式报告 `docs/reviews/plan-review-20261001-204809.md`、`docs/reviews/plan-review-20261001-204511.md` 完整读取；当前canary在报告与实际tool Read逐字匹配（Kimi最终简报省略不为mismatch）。13current+originals root逐件再次核同字节；完整工具凭据 `workspace/tmp/pr197-controller-collection-20261001/f5-a4-{mimo,kimi}-root-collection.json`。工具输出的历史文档内“mismatch”字样不是当前失败；无未解释关键失败。

**F5-V2-A4计划已修复，A1/A2/A3保持已修，plan review gate pass。** root独立日期owner/两个writer/processed机制取证与5增1删diff证据同源；不因两票直接放行。接受202行v2，SHA `e4b578807345593f0af6698189044963931b12ba5d13a76da94e553e581644d8`。保留该计划历史候选header不改审核字节，接受状态以本裁决及checkpoint为准。原产品F5/N01/N02尚未实施。

两路非阻塞测试时序提示root解读落实：正常download按§6不自动同步旧processed日期；已存在旧非None日期的processed在rebuild步清None，随后overwrite download保持None。自然新processed可从已修source产生；测试不得断言第1步自动改旧processed，不新状态机。rebuild版本v2→v3随updates写入，旧文档无来源键不因get(None)误跳过； fresh生产路径显式写None，实施真实回归核实。normal新同步、CN/SEC来源修改或扩解析语法均越本scope。

实施义务owner：F5-S1落实§3–9全链和N01/N02、真实Fs同窗/取消/日期旧值保全/4096/双omission/fresh schema/CNSEC/F6F7回归、受影响pytest、fullpyright、逐改prod覆盖≥80%、按职责README。reset非A4写点未由reviewers深入是已记录范围，root此前实际reset来源读证据支持normal边界，产品新风险由代码review核。原upload17标签+O20F02及最终完整真实CLI仍later approved queue，不能以本计划pass替代。

next entry=accepted plan commit→单完整F5-S1 Sol实施，不再停普通gate。
