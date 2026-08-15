# UF-FIX06 Slice 3 acceptance

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：3（Service 与 workflow 消费 typed 文件角色）
- Gate：code re-review acceptance
- 日期：2026-08-15
- 基线：`affa665b0592aec54564d31b0cfeb4055dd7bd8a`
- 状态：`ACCEPTED / COMMIT PENDING`
- 下一入口：Slice 4 README 与全局 contract audit

## Controller 裁决

Slice 3 接受。两路独立复审结论均为 `PASS`，blocking finding 为 0：

- AgentMiMo：`docs/reviews/code-re-review-slice3-mimo-20260815.md`
- AgentDS：`docs/reviews/code-re-review-slice3-ds-20260815.md`

初轮裁决接受的 A1–A5 已全部闭环：failure 文档与 closed kind/code contract 同步；prepare-stage
取消会丢弃 partial 资产和事件；material 第 N 项转换失败保持 typed exception 并投影为无虚假文件归属的
content terminal；`FinsUploadFailureReason` 构造与 JSON parser 消费同一完整、互斥映射。

## 接受依据

- `DoclingUploadService` 只消费 `FinsUploadFilingFiles | FinsUploadMaterialFiles`，不维护 suffix allow-list。
- filing 只转换 primary，companion 仅原样存储；material 的全部文件均需转换。
- `primary_document` 由第一次成功转换直接产生并随 prepared plan 传递，不从 stored entries 反推。
- 非法 source/selection/action/emptiness 组合在文件读取、converter 与 batch publication 前拒绝。
- 格式错误统一投影为 closed `USAGE/UNSUPPORTED_UPLOAD_FORMAT`；未知或错配 failure fact fail closed。
- 原子 batch、取消、rollback、requested/stored summary、calendar/year 与 ticker alias contract 未回退。
- 未修改 registry、oracle/scenario、design document、冻结 evidence；未运行 UF-PF06 或 UF-PF12。

## 验证证据

- 受影响测试矩阵：`1235 passed, 1 skipped, 3 warnings`。
- 覆盖率矩阵：`1338 passed, 1 skipped, 3 warnings`；11 个计划生产文件均不低于 80%，合计 92%。
- AgentDS 独立复跑：`501 passed, 3 warnings`。
- changed-file Pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff、Black、`git diff --check`：通过。

## Non-blocking observations

- JSON parser 为保留解析语境文案，在构造前重复执行同一 kind/code 映射预检；映射对象同源，无漂移风险。
- prepare-stage 取消反例按检查次数触发，能精确锁定“第一项完成、第二项未开始”，但未来新增取消检查点时需同步测试。

## Residual risks

- README 旧能力常量引用归 Slice 4 更新。
- material empty、delete + files、显式 primary、重复路径及 basename/stem collision 不属于本 work unit。
- 真实 Docling 格式矩阵与真实 CLI evidence 归 UF-PF06/UF-PF12，本轮按约束未运行。
- 未分类 residual risk：无。

## Completion signal

Slice 3 已满足 implementation、review、fix、re-review gates；允许提交并进入 Slice 4。
