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
