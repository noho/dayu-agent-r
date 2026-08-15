# UF-FIX06 plan re-review Controller 裁决

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`plan re-review -> Controller adjudication`
- 日期：2026-08-15
- 输入：
  - `docs/reviews/plan-re-review-mimo-20260815.md`
  - `docs/reviews/plan-re-review-ds-20260815.md`
- 结论：`PLAN FIX REQUIRED`
- 下一入口：AgentCodex 只修订 plan 与 plan-fix artifact；不得进入实现。

## 第一性原理复核

AgentMiMo 判定 pass；AgentDS 判定 fail 并提出 R1/R2/R3。Controller 以当前代码的直接
异常投影链、用户可见格式契约和 typed state 不变量复核后，采纳 R1/R2/R3。三项均不改变
已确认 goal、owner 分层或四个 slice，只消除实现 agent 仍需自行决定的公共语义。

## Finding 裁决

| ID | 严重程度 | 裁决 | 必须落实的冻结决策 |
| --- | --- | --- | --- |
| R1 | 中 | accepted | `FinsUploadFailureKind` 增加 `USAGE`，`FinsUploadFailureCode` 增加格式不受支持的 closed code；`fins_upload_failure_from_exception` 将 `FinsUploadFormatError` 投影为 bounded/path-free usage failure。把 `dayu/fins/upload_failure.py` 及其测试加入 Slice 3 allowed files。material workflow 在现有 `try` 内、任何 published-state 读取/company staging/file read/converter 前构造 typed selection；catch-all 由 failure owner 保持正确 usage 投影。Slice 3 端到端断言投影后的 kind/code/message 与零副作用。不得让异常逃逸绕过既有 event/job failure contract。 |
| R2 | 中 | accepted | 静态产品声明逐格式冻结为：PDF=`(.pdf)`；DOCX=`(.docx)`；PPTX=`(.pptx)`；HTML=`(.htm,.html,.xhtml)`；MD=`(.md,.txt)`；CSV=`(.csv)`；XLSX=`(.xlsx)`；XML_XBRL=`(.xbrl,.xml)`；JSON_DOCLING=`(.json)`。所有 suffix 统一小写且 tuple 顺序稳定。明确排除 `.doc/.ppt/.xls/.zip` 及第三方同 format 的未选择扩展。help/schema/batch 只投影这 13 个 suffix；补全精确集合与 batch enter/skip 测试。`.xml` 仍只能声明为 XBRL XML candidate，`.json` suffix 也不承诺任意 JSON 内容可转换。 |
| R3 | 低 | accepted | `ValidatedFinsUploadFilingRequest.file_selection` 改为必需、非 Optional 的 `FinsUploadFilingFiles`；delete 由 validator 直接产生 `for_delete()`，workflow 不再把 `None` 转成 selection。Service 明确拒绝 create/update + empty selection 与 delete + non-empty selection，均在读文件/converter/batch 前 `ValueError`。两个方向都加零副作用测试。material delete 同样使用 `FinsUploadMaterialFiles.for_delete()`。 |

## 原 finding 状态

- M1、M2、D2、D4、D5、O1、O2：维持 `已修复`。
- D1：admission owner 已修复；R1 是其 failure projection 残留，当前为 `待修复`。
- D3：单向子集校验策略已修复；R2 是其产品声明内容残留，当前为 `待修复`。
- R3：D2 相邻 typed state 边界，当前为 `待修复`。

## 边界与验证要求

- 不修改 goal、生产代码、测试、README、oracle/scenario registry、冻结 evidence。
- 不运行 UF-PF06、UF-PF12，不 commit。
- 原 plan 与 plan-fix artifact 必须同步更新 finding 状态；不得另建替代 plan。
- 修订后必须由 AgentMiMo 与 AgentDS 同时 re-review；两路都通过前不得进入 implementation。
- 既有残留风险分类不变：batch 自动归组、显式 primary、重复/碰撞及真实 evidence 均保持 deferred。

## Controller 结论

当前 plan 尚未 code-generation-ready。R1/R2/R3 都有唯一、最小、可测试的修订路径，
不存在需要用户重新确认的目标变化。下一入口为 `plan review fix`。

## 第二轮 re-review 追加裁决

- 输入：
  - `docs/reviews/plan-re-review-2-mimo-20260815.md`：`pass`
  - `docs/reviews/plan-re-review-2-ds-20260815.md`：`pass-with-risks`
- R1/R2/R3：两路均确认 `已修复`，第一轮 findings 无回退。
- N1（低）：`accepted`。`USAGE/UNSUPPORTED_UPLOAD_FORMAT` 是 closed failure contract 的新成员，
  `upload_failure_reason_from_json` 的 kind/code 一致性推导必须同步识别 usage code；否则
  `FinsUploadFailureReason.to_json()` 产生的合法 usage failure 无法 round-trip。Slice 3 必须明确
  扩展该守卫，并在 `tests/fins/test_upload_failure.py` 增加 usage reason 的
  `to_json -> upload_failure_reason_from_json` 相等断言，同时保持未知/错配 kind-code 继续拒绝。

N1 不改变任何已冻结 owner、suffix、event 或 typed selection 决策，修复路径唯一。严格 gate 下，
N1 标记为 `已修复` 且两路 re-review 通过前仍不得进入 implementation。
