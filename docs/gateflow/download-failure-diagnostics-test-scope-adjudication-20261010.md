# S1 必要测试迁移：总控文件边界裁决

- Work unit：download-failure-diagnostics-20261010；gate：implementation S1，尚未pass。
- Approved plan commit：a1df000835c61d1acfa383532488746e1487ed7b；生产允许文件仍exact5不变。
- 直接证据：受影响测试round1，29 failed/1385 passed，其中 tests/fins/test_f5_workflow_rebuild.py::test_actual_adapter_observation_wait_and_cli_keep_a_and_unknown 四个参数实例均在283行旧物理行数断言失败。实际取消输出由4变5行，失败由6变7行；新增行是已批准的唯一完整 diagnostics JSON，不是新的业务行为。
- 裁决：此测试文件加入S1允许测试迁移范围，仅修旧总行数与增加同源唯一诊断行断言，保持真实adapter/仓储/未知报告语义与原通道断言。不得为保住旧测试撤销诊断或增加生产compat。原允许测试名单漏列此文件，两路计划review未识别该旧断言；后续代码review必须验证迁移并记录此证据。
- 授权依据：用户已确认CLI默认完整诊断及相关测试更新；这只是已确认行为导致的必要测试迁移，没有新goal/成功信号/下载逻辑、生产文件或生产数据权限扩展，范围与owner清楚，无需再问同一目标。
- 本artifact由总控owned；不改冻结plan内容/hash，不宣称实施验证通过。实现runner若尚未收到此补充，需在正常终态后派发限定continuation/fix完成验证，不越过code review。
- Risk：fixed in current slice，owner S1实现；未迁移测试前不接受完成。无其它新风险，无README触发。
