# US2-R04-T01：必填材料登记条件的 owner 错误合同

## 即时登记与证据

统一修复 WU/S2，HEAD f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235，唯一开发分支 codex/upload-material-oracle。MiMo83417/ds-flash2004 已开始对前一冻结候选独立 re-review，本文件为冻结之外的新总控登记，未改冻结输入、不干预其独立审查。不是新 slice 或新业务裁决。

总控直接读本轮 delta `test_explicit_none_validates_company_without_missing_source_claim`：强制 cast None 到必填完整状态后，测试要求 `AttributeError`。实际 core `register_material_upload_preconditions` 直接访问 expected_source_state.source_integrity，因此该异常只是当前实现偶然产生；不是公共合同声明的校验错误。新 readonly validate 的显式 None 已是公司阶段合法选择，registration 则必须是完整材料状态。若为保持这个测试而保 AttributeError，会固化偶然实现错误，违反 AGENTS 的 owner 级测试约束。

**accepted / 未修复 / 低；归入 R04 的 required 完整条件收尾，不独立计产品业务 finding。** 前一候选的七件修复/2017pass与真实CLI事实仍成立，不能据这条低项改写其历史；S2当前复审结束后与所有其它成立项集中一次 fix。

## 最窄生成合同

在 source 条件登记的直接输入 owner `_FsMaterialUploadStateCore.register_material_upload_preconditions` 校验必填值确为 `MaterialUploadPublishedState`；非该类型抛明确定义的 TypeError，早于 material condition 登记，不访问非法值的内部属性。不是 None 特例/fallback，不给 None 放行，不扩大 readonly None 选择到 writer。protocol/core/publicFs 的相关中文异常文档同步说明；签名继续非 None、无默认值。其它 source/company equality、锁、commit/final guard、正常业务分支都不变。

新测试断言该明确 TypeError、仍无条件可供 commit（公共 commit 按原合同拒未登记）、rollback后 published业务字节不变，不通过私有字段或 AttributeError 证明 owner 行为。保既有对具体 stale source、公司/alias漂移和 R04 正常 None 公司复验的测试。此项只涉及登记输入边界及测试，不新增 public upload字段、usage code、状态、取消生命周期、全仓类型硬化或新标准。

## 验证与下一入口

等待当前双 re-review真实终态，合并其全部成立项后 gpt-6-sol集中 fix。受影响state/publication测试、完整pyright、实际触及prod≥80，代码静态核只有输入校验增量；相同合法CLI数据不变，已有同版真实CLI结果以原codeSHA保留，不因内部非法值校验机械重跑三轮。新严格校验版需最终同版双复审，才能 accepted S2 commit。未变区域的前驱审核可按hash继承，禁止完整重复审查无改区。root总控裁决，main不动；S3仍待S2通过。
