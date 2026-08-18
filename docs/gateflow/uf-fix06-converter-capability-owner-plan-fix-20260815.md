# UF-FIX06 converter-capability-owner plan review fix

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`plan review -> fix`
- 日期：2026-08-15
- 修订目标：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`
- Controller 输入：`docs/reviews/uf-fix06-plan-review-adjudication-20260815.md`
- Review 输入：
  - `docs/reviews/plan-review-20260815-135206.md`
  - `docs/reviews/plan-review-20260815-135414.md`
- Completion status：`plan-fix-complete / re-review-pending / implementation-not-started`
- Blocking open question：无
- Next entry point：`re-review`
- Artifact path：`docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`

## 边界与裁决原则

本 gate 完整读取原 plan、两份 plan review artifact 与 Controller adjudication，只落实
Controller accepted findings，不重新裁决 goal 或扩大 scope。冻结决策保持为：产品 suffix
是第三方格式映射的受控子集；help 使用静态声明，constructor 做 lazy 支持性校验；
Fins 同时拥有 filing/material typed selection；`prepare_upload` 只接收 closed union 并校验
`SourceKind`；material 保留 converter 前 admission 且全转换；direct upload companion 没有
`conversion_started`；batch `.xsd` 稳定 skip，自动归组 deferred。

## Finding 修复状态

| ID | Controller 裁决 | Fix 状态 | 具体 plan 位置 | 修订与 validation |
| --- | --- | --- | --- | --- |
| M1 | accepted | 已修复 | §4 owner table；§5.1；Slice 1 Exact changes / Tests / Stop condition | 冻结为模块级不可变产品声明，help/schema 只读静态对象且不 import Docling；仅 constructor path lazy import 并校验。Slice 1 断言 help 无 Docling import，stop condition 不再要求 implementation agent 自行设计。 |
| M2 | accepted | 已修复 | §5.1 特别约束；§5.2 projection；§6.2；Slice 2 Tests；Slice 4 Exact changes / Tests | 三面文案明确 `.xml` 仅是 XBRL XML candidate，suffix 通过不表示任意 XML 或内容必然转换成功。 |
| D1 | accepted | 已修复 | §3.1 #2/#5/#8；§4 material owner row；§5.2–§5.4；§6.2；Slice 2/3 | 新增 `FinsUploadMaterialFiles` 与 `MATERIAL_SUFFIX_UNSUPPORTED`；CLI 与 tool/Service workflow 在 converter 前消费同一 owner，material 所有输入仍逐个转换。invalid-suffix tool/Service test 断言 mutation/read/converter 均为 0。 |
| D2 | accepted | 已修复 | §5.2 delete typed state；§5.4 exact signature；§7 #11；Slice 3 Exact changes / Tests | 冻结单一 `selection: FinsUploadFilingFiles \| FinsUploadMaterialFiles`，删除 raw-list/双输入设计空间；Service 校验具体 selection 与 `SourceKind` 一致，非法组合以 `ValueError` 在副作用前拒绝。 |
| D3 | accepted | 已修复 | §4 converter owner row；§5.1；Slice 1；§10 Capability/Operational risks；§11 | 取消与 `FormatToExtensions` 的双向精确相等；改为产品 suffix 最小子集逐项受支持校验。第三方新增 suffix 不 fail、不自动进入 help；已声明 suffix 缺失才 typed fail-fast。constructor `allowed_formats` 仍与产品 format ids 精确同源。 |
| D4 | accepted（边界澄清） | 已修复 | §3.2；§6.2；Slice 2 Tests / Stop condition；§10 Batch association residual | `upload_filings_from` 保持单文件命令，`.xsd` 稳定 `unsupported_suffix` skip，不自动归组；direct `upload_filing --files primary companion...` 是本轮 companion 目标入口。测试固化含 HTML/XBRL + XSD 目录的 skip 行为。 |
| D5 | accepted | 已修复 | §5.4；§7 #12；Slice 3 Exact changes / Tests | companion 不产生 `conversion_started` 或新 event type，只产生 source=`original` 的既有 `file_uploaded`；HTML+XSD 与多 converter-capable fixture 均断言事件序列。 |
| O1 | accepted | 已修复 | §5.2 projection；§6.2；Slice 2；Slice 4 Exact changes / Tests | CLI `upload filing --help`、LLM-facing upload tool schema、根 README 三面一致承诺首文件 primary、后续 raw companions 且 companions 不转换；Slice 4 要求逐面对照。 |
| O2 | accepted | 已修复 | Slice 3 Tests / assertions | 新增 DOCX + XLSX + DOCX owner/service 级 fixture：只转换首项，后两项原样存储，唯一 derived asset 和 `primary_document` 均来自首项，requested/stored 均为 3，companions 无伪转换事件。 |

上表 9 个 Controller accepted findings 全部为“已修复”；无“部分修复”、“未修复”或“证据失效”。

## Validation

- 输入完整性：原 plan 422 行、MiMo review 131 行、DS review 110 行、Controller adjudication 59 行，均已读到 EOF。
- 决策一致性：plan 已同时覆盖静态声明/lazy 校验、suffix 子集、filing/material selections、closed union + `SourceKind`、material 前置 admission/全转换、direct companion events、batch stable skip、三面文案与多 converter-capable fixture。
- 反向冲突检查：plan 不再要求 product suffix 与第三方完整映射精确相等，不再保留 material raw-list 或“删除 material admission”的实现空间，不把 batch 自动归组纳入本 work unit。
- 文件完整性：两个修改 artifact 已通过 whitespace check；本 gate 的文档 diff 无 whitespace error。
- No-touch 检查：本 gate 未修改 goal artifact、生产代码、测试、README、oracle/scenario/frozen evidence，未运行 UF-PF06/UF-PF12，未 commit。
- 未运行 pytest/coverage/pyright：本 gate 只修改 Markdown plan artifacts，且用户限定只执行 plan review fix gate；实现验证命令仍完整保留在 plan §9。

## Docs decision

- 已修改：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`。
- 已新增：`docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`。
- 未修改 README：当前是 plan fix gate，尚无生产/测试行为落地，且用户明确禁止本 gate 修改 README。原 plan Slice 4 已冻结实现后 CLI help、LLM-facing schema 与根 README 三面一致的文档决策。
- 未修改 review/adjudication/goal/oracle/scenario/frozen evidence：它们是本 gate 的只读证据。

## Residual risks

| Residual risk | 分类 | Owner / destination |
| --- | --- | --- |
| batch companion association 缺少稳定 identity/association rule | assigned to later work unit | 后续 batch association / `UF-FIX07` 类 work unit；当前 `.xsd` 稳定 skip |
| 真实格式矩阵与 XBRL companion CLI evidence 未重跑 | assigned to later work unit | `UF-PF06` |
| 137 条 full-real mandatory matrix 未重跑 | assigned to later work unit | `UF-PF12` |
| 显式 primary、重复路径、basename/derived-name collision | assigned to later work unit | `UF-FIX07` |
| `.xsd` 以外的 companion-only XBRL 附件类型未证明 | assigned to later work unit / explicit product decision | 后续 Fins/XBRL 产品能力 work unit；当前不猜测扩展 |
| plan fix 尚未经 re-review | process state，非产品 finding | 下一入口 `re-review`；未通过前不授权 implementation |

无 unclassified residual risk，无 blocking open question。

## Completion

- Controller accepted findings：M1、M2、D1、D2、D3、D4、D5、O1、O2 全部已修复。
- 修改范围：只有原 plan 与本 plan-fix durable artifact。
- Completion status：`plan-fix-complete / re-review-pending / implementation-not-started`。
- Next entry point：`re-review`。

## 第二轮 plan review fix 状态

### Gate 元数据

- Gate：`第二轮 plan review -> fix`
- Re-review 输入：
  - `docs/reviews/plan-re-review-mimo-20260815.md`
  - `docs/reviews/plan-re-review-ds-20260815.md`
- Controller 输入：`docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md`
- Controller 结论：`PLAN FIX REQUIRED`
- 本轮范围：只落实 R1/R2/R3 冻结决策；不重裁 goal，不改变 owner 分层、四个 slices 或既有 residual risk destination。
- Completion status：`second-plan-fix-complete / re-review-pending / implementation-not-started`
- Next entry point：`re-review`

### R1/R2/R3 修复状态

| ID | Controller 裁决 | Fix 状态 | 原 plan 修订位置 | 冻结结果 |
| --- | --- | --- | --- | --- |
| R1 | accepted | 已修复 | §4 failure owner；§5.2 failure projection；§5.3 material workflow；§6.2；Slice 3；§9 | `dayu.fins.upload_failure` 增加 `USAGE/UNSUPPORTED_UPLOAD_FORMAT` closed mapping，固定 message/retry hint 与 safe `file_label`；`upload_failure.py` 和新增 `tests/fins/test_upload_failure.py` 纳入 Slice 3。material selection 在 SEC/CN 现有 `try` 内、任何 published-state read/company staging/其他 mutation/file read/converter 前构造；catch-all 继续维护既有 event/job failure contract。端到端测试精确断言投影后的 kind/code/message/file label 与全部副作用为 0，异常不得逃逸。 |
| R2 | accepted | 已修复 | §5.1；§6.2；Slice 1/2；§12 | 逐格式和稳定顺序冻结为 PDF=`(.pdf)`、DOCX=`(.docx)`、PPTX=`(.pptx)`、HTML=`(.htm,.html,.xhtml)`、MD=`(.md,.txt)`、CSV=`(.csv)`、XLSX=`(.xlsx)`、XML_XBRL=`(.xbrl,.xml)`、JSON_DOCLING=`(.json)`；展平后精确为 13 个小写 suffix。help/schema/batch 只投影该集合；batch 测试逐项断言 13 个 suffix enter，并断言 legacy、ZIP、`.xsd` 与已知第三方未选择扩展 skip。`.xml` 仅是 XBRL XML candidate，`.json` 不承诺任意 JSON 内容可转换。 |
| R3 | accepted | 已修复 | §5.3/§5.4；§6.1；§7；Slice 2/3；§12 | `ValidatedFinsUploadFilingRequest.file_selection` 冻结为必需、非 Optional；validator 对 delete 直接产生 `FinsUploadFilingFiles.for_delete()`，workflow 不再翻译 `None`；material delete 直接使用 `FinsUploadMaterialFiles.for_delete()`。Service 在任何 file read/converter/batch 前双向拒绝 create/update + empty 与 delete + non-empty，filing/material 两类均有 `ValueError` + 零副作用测试。 |

R1/R2/R3 均为 `已修复`；无 `部分修复`、`未修复` 或 `证据失效`。第一轮 M1/M2/D1–D5/O1/O2 的已修复状态不变。

### Validation 与边界

- 输入完整性：原 plan、原 plan-fix、MiMo re-review、DS re-review 与第二轮 Controller adjudication 均已完整读取到 EOF。
- 一致性检查：R1 的 failure owner/allowed files/try 内时序/投影断言，R2 的逐格式 13 suffix 与 batch enter/skip，R3 的 non-Optional/delete typed empty/Service 双向拒绝均已同步写入原 plan 的 contract、slice 与 completion report。
- Whitespace：仅对本轮允许修改的两个 Markdown artifacts 运行 `git diff --check --no-index /dev/null <file>`；结果见本轮最终报告。
- No-touch：不修改 goal、生产代码、测试、README、review、adjudication、oracle/scenario registry 或 frozen evidence；不运行 PF、pytest、coverage、pyright；不 commit。
- Docs decision：只更新原 plan 与原 plan-fix artifact；不新建替代 plan。README 属 implementation 后 Slice 4，本 gate 不触碰。
- Residual risks：沿用上一节已经分类的 batch association、UF-PF06、UF-PF12、UF-FIX07 与后续 XBRL 产品能力去向；没有新增或未分类 residual risk。

### 第二轮完成结论

- R1：`已修复`。
- R2：`已修复`。
- R3：`已修复`。
- Blocking open question：无。
- Completion status：`second-plan-fix-complete / re-review-pending / implementation-not-started`。
- Next entry point：`re-review`；两路 re-review 都通过前不得进入 implementation。

## N1 plan fix 状态

### Gate 元数据

- Gate：`第二轮 re-review -> fix`
- Re-review 输入：
  - `docs/reviews/plan-re-review-2-mimo-20260815.md`
  - `docs/reviews/plan-re-review-2-ds-20260815.md`
- Controller 输入：`docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md` 的追加裁决
- 本轮范围：只落实 accepted N1；不改变既有 owner、suffix、event、typed selection、slice
  边界或 residual risk destination。
- Completion status：`n1-plan-fix-complete / re-review-pending / implementation-not-started`
- Next entry point：`re-review`

### Finding 修复状态

| ID | Controller 裁决 | Fix 状态 | 原 plan 修订位置 | 修订结果 |
| --- | --- | --- | --- | --- |
| N1 | accepted | 已修复 | Slice 3 Exact changes #6；Slice 3 Tests / assertions | `upload_failure_reason_from_json` 的 kind/code 一致性推导明确同步识别 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`；owner 测试明确断言 usage failure reason 的 `to_json()` 经该函数恢复后与原值相等，并保持未知 code 与错配 kind/code 拒绝。 |

### 完成结论

- N1：`已修复`。
- Blocking open question：无。
- 修改范围：仅原 plan 与原 plan-fix artifact；未进入 implementation。
- 未运行：测试、PF、coverage、pyright；未 commit。
- Next entry point：`re-review`。
