# UF-FIX06 accepted plan gate

## Gate 结论

- Work unit：`UF-FIX06 converter-capability-owner`
- 日期：2026-08-15
- 结论：`PLAN ACCEPTED`
- 下一入口：implementation Slice 1

## 接受依据

- Goal confirmation 已由用户确认。
- 第一轮 plan review findings M1、M2、D1–D5、O1、O2 已修复。
- 第二轮 re-review findings R1、R2、R3 已修复。
- 第三轮专项 finding N1 已修复。
- 最终双路 re-review：
  - AgentMiMo：`docs/reviews/plan-re-review-3-mimo-20260815.md`，结论 `pass`；
  - AgentDS：`docs/reviews/plan-re-review-3-ds-20260815.md`，结论 `pass`。
- 两路均确认此前 findings 无回退，当前 plan code-generation-ready。

## 冻结实施契约

- `dayu.documents.docling_runtime` 是产品 converter capability 唯一 owner；静态 9 format/13 suffix
  声明驱动 help/schema，converter construction lazy 校验该声明并用同源 `allowed_formats`。
- `dayu.fins.upload_format_contract` 是 filing primary/companion 与 material 全转换 selection owner；
  filing 首项是隐式 primary，后续仅原样保存，不执行 Docling 转换；`.xsd` 仅 companion。
- `DoclingUploadService.prepare_upload` 只接收 filing/material closed typed union，并双向校验
  `SourceKind` 与 action/empty state。
- material 非法格式经 `dayu.fins.upload_failure` 投影为
  `USAGE/UNSUPPORTED_UPLOAD_FORMAT`；JSON round-trip 守卫同步扩展。
- 原子发布、typed bounded failure、requested/stored summary、共享可中断 converter、日期与 ticker
  alias contract 不得回退。

## Scope 边界

- 不处理 UF-FIX07 的显式 primary、重复路径及 basename/stem collision。
- 不执行 UF-PF06/UF-PF12，不刷新 oracle/scenario registry，不修改冻结 evidence。
- `upload_filings_from` 不做 companion 自动归组；`.xsd` 继续稳定 skip。

## Gate 状态

Plan gate 已关闭，blocking finding 为 0。允许 AgentCodex 按 accepted plan 的四个 slices 开始实现；
每个 slice 仍需双路 code review、finding fix/re-review 与 accepted slice commit。
