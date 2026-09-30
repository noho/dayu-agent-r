# PR197 handoff 语义漂移修正

## Finding HANDOFF-F01 与裁决

accepted / 已修复（controller文档）。接续总控检查依赖时发现 handoff prompt第3节仍写“O14/O15依赖O12公司/source单batch”，直接违背已接受O34及O12最新分阶段计划。该错误在实施前即应纠正，不能让下一位Agent据旧handoff覆盖用户裁决。

直接真源：`docs/reviews/upload-material-um-o34-oracle-adjudication.md` 公司独立合法事实/材料无manifest未成功；`docs/gateflow/upload-material-o12-company-plan-20260929.md` 第3行声明单batch旧裁决由O34覆盖，第15/29/68/90/98/102行明确公司独立提交、材料同版guard、失败取消不删除公司；主队列2026-09-29 O12/O14/O15与O34冲突及随后accepted checkpoint时间线。

修复：handoff该行改为同版状态读取、分阶段公司/材料guard、可信tombstone，明确旧单batch已撤销，并保持O18用户既定amended/overwrite行为原文。原历史artifact与旧快照不改写；没有实施任何O12/O14/O15/O18产品代码。

验证：总控直接逐句核对上述owner/用户裁决，检查本次handoff diff仅目标句及此前已知路由/进度更新；文档修改无需代码测试。该修正不改F3/F4冻结输入或HEAD。

当前gate：controller证据修正完成、待随下一accepted checkpoint提交。残余：O12/O14/O15实施和同版集成测试归原WU（assigned to later work unit），不能据本doc修正宣告代码已修。
