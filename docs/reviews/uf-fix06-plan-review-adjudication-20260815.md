# UF-FIX06 Plan Review Controller Adjudication

## Gate

- work unit：`UF-FIX06 converter-capability-owner`
- gate：`plan review -> fix`
- reviewed target：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`
- review artifacts：
  - `docs/reviews/plan-review-20260815-135206.md`（AgentMiMo，`pass-with-risks`）
  - `docs/reviews/plan-review-20260815-135414.md`（AgentDS，`fail`）
- completion status：`fix-required`
- next entry point：`fix`
- artifact path：`docs/reviews/uf-fix06-plan-review-adjudication-20260815.md`

## Finding Adjudication

| ID | 来源 | 裁决 | 理由与 required fix |
| --- | --- | --- | --- |
| M1 | MiMo medium：help projection lazy 边界未给实现路径 | `accepted` | 明确 capability 使用模块级不可变产品声明；help/schema 只读该声明，不 import Docling；converter construction 才 lazy import 并验证声明是第三方映射的受支持子集。 |
| M2 | MiMo low：`.xml` help 歧义 | `accepted` | help/schema 必须把 `.xml` 说明为 XBRL XML candidate，并明确 suffix 不保证内容成功；不得宣称任意 XML。 |
| D1 | DS high：material suffix admission owner 空洞 | `accepted` | Fins upload format contract 同时提供 filing 与 material 的 typed selection；material tool/Service 路径在 converter 前调用同一 owner，全部文件均为 converter-required；删除的是重复常量，不是 material admission。 |
| D2 | DS medium：`prepare_upload` 严格签名不明确 | `accepted` | 冻结为单一 closed union 参数：`FinsUploadFilingFiles | FinsUploadMaterialFiles`（最终类型名可等价调整），并校验 selection kind 与 `SourceKind` 一致；禁止 raw list 与 role selection 双输入。 |
| D3 | DS medium：与 `FormatToExtensions` 精确相等造成反向锁定和扩面 | `accepted` | 产品 suffix 是明确最小子集；construction-time 校验每个声明 suffix 属于对应第三方格式映射，缺失 fail-fast；第三方新增 suffix 不自动进入产品 contract，也不导致失败。constructor `allowed_formats` 仍与产品选定 format ids 精确一致。 |
| D4 | DS medium：batch companion 语义未声明 | `accepted`（仅边界澄清） | 明确 `upload_filings_from` 仍按单文件生成命令，只消费 `accepts_primary`；`.xsd` companion-only 文件稳定 skipped，不做同目录 companion 归组。归组会要求新 identity/association rule，属于后续 batch/UF-FIX07 类 work unit，不在本 work unit 扩 scope。direct `upload_filing --files primary companion...` 是本轮 XBRL companion 目标入口。 |
| D5 | DS low：companion 事件契约缺失 | `accepted` | companion 不产生 `conversion_started` 或任何伪转换事件；它只按现有 original publication 路径产生正常文件上传事件，不增加新 event type。测试必须断言。 |
| O1 | DS open question：用户可见首文件规则 | `accepted` | Slice 2/4 明确断言 CLI help、LLM-facing schema、README 三面一致说明首文件 primary、后续 raw companions。 |
| O2 | DS open question：多 converter-capable 输入 fixture | `accepted` | 增加 owner/service 级测试：DOCX + XLSX + DOCX 只转换首项，其余原样存储，primary document 与 requested/stored 同源。不得运行真实 PF evidence。 |

## Rejected / Deferred Scope

- `upload_filings_from` 自动把同目录 `.xsd` 与 HTML/XBRL 归为同一 filing：`deferred-with-owner`，由后续 batch association / UF-FIX07 类 work unit 决定；当前没有稳定 association identity，强行按 stem/顺序归组会违反本轮非目标。
- third-party 新增 suffix 自动公开：`rejected-with-reason`；产品 capability 不能被依赖升级静默扩面。

## Required Plan Fixes

1. 把 capability drift 校验从双向精确相等改为“产品 suffix 子集必须被第三方支持”，同时保持 format ids 与 constructor `allowed_formats` 同源。
2. 明确静态 product declaration / lazy third-party validation 两阶段，消除 implementation stop question。
3. 新增 typed `FinsUploadMaterialFiles`，冻结 `prepare_upload` closed union 签名和 `SourceKind` 一致性校验。
4. 明确 material CLI/tool/Service 均消费同一 owner，所有 material 输入仍逐个转换。
5. 明确 direct upload companion 事件、batch skip 边界和三面用户文案。
6. 增加多 converter-capable 输入测试与 material invalid-suffix tool-path test。
7. 更新风险表、slice exact changes/tests/stop conditions，使实现 agent 无需自行设计。

## Validation

- 两份 review artifact 均已完整读取。
- 所有 accepted findings 都有 plan-level fix direction。
- 未分类 residual risk：无。
- production/test/README/oracle/scenario/frozen evidence：本 gate 未修改。

## Residual Risks

| 风险 | 分类 | owner / destination |
| --- | --- | --- |
| batch companion association | assigned to later work unit | 后续 batch association / `UF-FIX07` 类 work unit |
| 真实格式与 XBRL companion CLI evidence | assigned to later work unit | `UF-PF06` |
| full-real mandatory matrix | assigned to later work unit | `UF-PF12` |
| 显式 primary、重复路径和 collision | assigned to later work unit | `UF-FIX07` |
