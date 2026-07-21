# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Stop Plan Fix

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`plan-amendment-slice-3`
- Base：accepted Slice 2 commit `5ac328f0`
- Stop artifact：`docs/reviews/wu-host-session-event-delivery-01-slice3-stop-scope-codex.md`
- Controller adjudication：`docs/reviews/wu-host-session-event-delivery-01-slice3-stop-condition-controller-adjudication.md`
- 修订对象：`docs/host/wu-host-session-event-delivery-01-plan.md` S3
- 执行边界：只修订accepted plan并新增本artifact；不修改production、tests、control doc或phaseflow umbrella，不继续implementation，不commit、push或创建PR。

## 第一性原理与直接证据

动机成立。完整pyright直接证明`tests/host/test_projection_read_model.py`与`tests/host/test_public_host_admin.py`各有两个required terminal port缺失错误；全测试constructor callsite scan证明两者都绕过standalone `create_host_command_handle`，直接构造`HostCommandHandle`与`create_host_admission_service`，且没有第三个必须新增授权的caller。

正确owner是各自direct test composition root。required terminal port是S3 item 9/10用于暴露漏接装配的fail-fast contract；不能把production port改成optional/default/fallback，也不能在下游增加兼容分支、临时port或runtime rebind。

## 精确修订

1. S3 Allowed tests只新增：
   - `tests/host/test_projection_read_model.py`
   - `tests/host/test_public_host_admin.py`
2. 两个文件仅获授权在各自现有direct test composition root创建test-private、显式no-local-delivery final endpoint，并把同一实例同时传入`create_host_admission_service`与`HostCommandHandle`；不得改变业务场景、断言语义、production constructor或terminal flags/dataflow。
3. S3 focused validation加入上述两个完整测试文件；`tests/host/test_command_handle.py`的standalone exact-notice runtime fake仍为必过项。
4. 完整pyright与全测试constructor callsite scan成为显式gate：required terminal port错误必须归零，且不得出现第三个漏列caller。
5. `tests/host/test_admission_multiprocess.py`的4个旧字段断言错误与`tests/host/test_phase7_waiting_integration.py`的1个required factory参数错误继续在原S3 allowlist内按owner contract修复；本amendment不为其扩大scope。

## Caller manifest审计

Plan §5.3的static manifest按production terminal writer/producer qualified callsite定义，不按composition path定义。上述两个文件是test composition caller，不是新的terminal writer/producer；因此§5.3集合无需也不得加入test caller row。除S3 Allowed tests、direct composition授权与validation scan外，没有扩大其它caller manifest。

## 冻结边界

- 不授权optional/default/fallback port、临时no-op过渡、rebind、兼容wrapper或下游补偿。
- 不授权修改新增caller的业务场景或断言。
- 不授权修改production、tests、control doc、phaseflow umbrella或accepted plan其它slice。
- partial S3 workspace changes及既存Controller-owned修改全部保留，不撤销、不格式化、不stage、不提交。

## 文档验证

- 只对accepted plan与本artifact执行diff、whitespace和scope审计。
- 不运行implementation tests或pyright；这些是恢复S3 implementation后必须执行的validation，本次plan amendment不修改代码。
- 本artifact完成后状态为`READY_FOR_PLAN_REVIEW`，交回AgentMiMo与AgentDS独立plan re-review及Controller裁决。

## 结论

最小scope缺口已在composition owner边界补齐，无blocking open question。

READY_FOR_PLAN_REVIEW
