# UF-FIX06 Slice 3 code review adjudication

## Gate 结论

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：3
- 日期：2026-08-15
- 输入：AgentMiMo 与 AgentDS 两路独立 code review
- 结论：`FIX REQUIRED`
- 下一入口：AgentCodex code review fix

## 双审结果

- AgentMiMo：`pass`，blocking finding 0；artifact：
  `docs/reviews/code-review-slice3-mimo-20260815.md`。
- AgentDS：`pass`，blocking finding 0；artifact：
  `docs/reviews/code-review-slice3-ds-20260815.md`。
- Controller 接受核心 correctness 结论，但按项目完整 docstring、测试迁移与 closed public fact 约束，
  以下 finding 必须在 Slice 3 内闭环后再 re-review。

## Accepted findings

### A1：failure kind 文档遗漏 USAGE

- 来源：AgentDS F1。
- 状态：`accepted / must-fix`。
- 修复要求：`FinsUploadFailureReason.kind` 的属性说明必须列出 usage、content、storage、runtime。

### A2：转换 helper 漏报 typed cancellation

- 来源：AgentDS F2。
- 状态：`accepted / must-fix`。
- 修复要求：`_build_pending_assets` 的 Raises 明确列出 `DoclingConversionCancelledError`，并把
  material `DoclingConversionError` 透传与取消语义分开说明。

### A3：新增 loop-top cancel 分支缺直接反例

- 来源：AgentDS F3。
- 状态：`accepted / must-fix`。
- 修复要求：增加 prepare 阶段 token 翻转测试，至少覆盖 material 两文件在第二个 converter input 前取消；
  断言 cancelled plan、空 file events、前一转换允许完成但所有 partial assets/events 被丢弃、零 batch、零发布。

### A4：material 第 N 个转换失败缺原子性反例

- 来源：AgentDS F4。
- 状态：`accepted / must-fix`。
- 修复要求：增加 `[ok.pdf, corrupt.docx]` material 反例，断言调用顺序、第二项 typed conversion
  failure、前序派生资产不发布；至少一条 workflow 级断言既有 catch-all 产生 content failure，且不把
  未经 owner 证明的文件名错误归给 failure。

### A5：closed public failure fact 本身未校验 kind/code

- 来源：Controller 对 failure owner 的直接复核；AgentDS residual note 佐证映射唯一性 guard 只验证完整性。
- 状态：`accepted / must-fix`。
- 修复要求：`FinsUploadFailureReason.__post_init__` 自身必须验证 enum 具体类型与
  `_FAILURE_KIND_BY_CODE` 一致性，使错误组合不能经直接构造后 `to_json()`；code 分组必须显式验证互斥与完整。
  JSON parser 继续复用同一映射，不复制判断。补 direct-construction mismatch/open-type 与 mapping
  completeness/disjointness contract tests。

## Deferred / no-action

- AgentDS F5：`dayu/fins/README.md` 的旧常量引用直接证据成立，但 accepted plan 明确归 Slice 4；
  本 fix 不修改 README。
- MiMo 对 material empty content 的观察：保持既有 converter-owned 行为，不在本 work unit 扩展 failure code。
- delete + files、collision、显式 primary、batch association 均保持既有 residual 分类。

## 保持条件

- 只修改 Slice 3 allowed production/test files，并可更新 implementation artifact、新增 code-fix artifact。
- 不修改旧 review artifact、README、registry、oracle/scenario、design doc、冻结 evidence。
- 不运行 UF-PF06/UF-PF12，不 commit。

Accepted must-fix 为 5 项；完成后必须进入 AgentMiMo/AgentDS 双路 re-review。
