# UF-FIX06 Plan Re-Review（第二轮，R1/R2/R3 验证）

## Review Metadata

- **Reviewed target**：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（第二轮 plan review fix 后修订版）
- **Reviewer**：AgentMiMo（第二轮 re-review）
- **Timestamp**：20260815-143122（系统时钟生成）
- **Baseline commit**：`a3d584fcf1444fcf5d633f2dd8bdb83eaf5adab9`
- **Review scope**：只验证第二轮 Controller 冻结决策 R1/R2/R3 是否在修订 plan 中完全修复，同时确认第一轮 findings（M1/M2/D1–D5/O1/O2）无回退
- **输入 artifacts**（均已完整读取至 EOF）：
  - 原 plan（第二轮 fix 后）：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（571 行）
  - Plan fix 记录：`docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`（119 行）
  - MiMo 第一轮 re-review：`docs/reviews/plan-re-review-mimo-20260815.md`（284 行）
  - DS 第一轮 re-review：`docs/reviews/plan-re-review-ds-20260815.md`（153 行）
  - 第二轮 Controller 裁决：`docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md`（47 行）
- **Binding scope contract**：goal confirmation SHA-256 `2e2729c3…`、oracle `88b04ca4…`、scenario `a357e5a1…`、frozen UF-O12 `fe3029cd…`/`e2d3b589…`——均已按 SHA-256 定位并复核一致
- **Lenses applied**：goal-bound minimal design / architecture boundary / best-practice / overcoupling

## 1. R1 验证：usage failure owner / try 时序 / allowed files

### Controller 冻结决策

> `FinsUploadFailureKind` 增加 `USAGE`，`FinsUploadFailureCode` 增加格式不受支持的 closed code；`fins_upload_failure_from_exception` 将 `FinsUploadFormatError` 投影为 bounded/path-free usage failure。把 `dayu/fins/upload_failure.py` 及其测试加入 Slice 3 allowed files。material workflow 在现有 `try` 内、任何 published-state 读取/company staging/file read/converter 前构造 typed selection；catch-all 由 failure owner 保持正确 usage 投影。Slice 3 端到端断言投影后的 kind/code/message 与零副作用。不得让异常逃逸绕过既有 event/job failure contract。

### 逐条验证

| # | Controller 要求 | plan 证据 | 结论 |
|---|---|---|---|
| 1 | `FinsUploadFailureKind` 增加 `USAGE` | §5.2："`FinsUploadFailureKind` 增加 `USAGE`" | ✅ |
| 2 | `FinsUploadFailureCode` 增加 closed code | §5.2："`FinsUploadFailureCode` 增加唯一格式不受支持 code `UNSUPPORTED_UPLOAD_FORMAT`" | ✅ |
| 3 | `fins_upload_failure_from_exception` 投影 `FinsUploadFormatError` | §5.2："将 `FinsUploadFormatError` 唯一投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，产生 bounded、path-free 的稳定用户消息；`file_label` 取 error 已校验的安全 basename，`retry_hint` 固定为 `请查看上传帮助中的支持格式后重试`" | ✅ |
| 4 | `upload_failure.py` 加入 Slice 3 allowed files | Slice 3 Allowed production files 明确列出 `dayu/fins/upload_failure.py`；Allowed test files 明确列出 `tests/fins/test_upload_failure.py`（新增） | ✅ |
| 5 | material workflow 在现有 `try` 内、任何 published-state read 前构造 typed selection | §5.3："material create/update 在 SEC/CN workflow 现有 `try` 内，且在任何 published-state 读取、company staging、其他业务 mutation、文件读取或 converter call 前构造 typed selection" | ✅ |
| 6 | catch-all 由 failure owner 保持正确 usage 投影 | §5.3："非法 suffix 必须留在既有 catch-all 与 event/job failure contract 内，并由 `fins_upload_failure_from_exception` 投影为上述 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，不得让异常逃逸绕过该契约" | ✅ |
| 7 | Slice 3 端到端断言投影后 kind/code/message 与零副作用 | Slice 3 Tests："经 failure owner 投影为 `kind=USAGE`、`code=UNSUPPORTED_UPLOAD_FORMAT`、`message=文件格式不受支持，请选择支持的文件后重试`、`file_label=safe_basename`；同时断言 published-state read、company/source mutation、文件读取、converter call 与 batch open 均为 0，且既有 event/job failure contract 收到该投影，异常没有逃逸" | ✅ |

### R1 裁决：**已修复**。failure owner 的闭合 contract（kind/code/message/file_label/retry_hint）、allowed files、try 内时序、端到端投影断言与零副作用断言均已明确。DS re-review 指出的"投影链未闭合"缺口——`upload_failure.py` 不在 allowed files、构造点与 try/except 关系不明、投影后断言缺失——全部消除。

## 2. R2 验证：13 suffix 精确集合

### Controller 冻结决策

> 静态产品声明逐格式冻结为：PDF=`(.pdf)`；DOCX=`(.docx)`；PPTX=`(.pptx)`；HTML=`(.htm,.html,.xhtml)`；MD=`(.md,.txt)`；CSV=`(.csv)`；XLSX=`(.xlsx)`；XML_XBRL=`(.xbrl,.xml)`；JSON_DOCLING=`(.json)`。所有 suffix 统一小写且 tuple 顺序稳定。明确排除 `.doc/.ppt/.xls/.zip` 及第三方同 format 的未选择扩展。help/schema/batch 只投影这 13 个 suffix；补全精确集合与 batch enter/skip 测试。`.xml` 仍只能声明为 XBRL XML candidate，`.json` suffix 也不承诺任意 JSON 内容可转换。

### 逐条验证

| # | Controller 要求 | plan 证据 | 结论 |
|---|---|---|---|
| 1 | 逐格式冻结 suffix tuple | §5.1 冻结表格：PDF=`(".pdf",)`、DOCX=`(".docx",)`、PPTX=`(".pptx",)`、HTML=`(".htm", ".html", ".xhtml")`、MD=`(".md", ".txt")`、CSV=`(".csv",)`、XLSX=`(".xlsx",)`、XML_XBRL=`(".xbrl", ".xml")`、JSON_DOCLING=`(".json",)`。"静态产品声明必须直接使用以下模块级字面量 tuple；格式、suffix 成员和 tuple 顺序均已冻结，implementation agent 不得现场增删或重排" | ✅ |
| 2 | 13 个 suffix 展平精确集合 | §5.1："上述投影按表格顺序展平后恰为 13 个 suffix，全部小写且顺序稳定：`.pdf, .docx, .pptx, .htm, .html, .xhtml, .md, .txt, .csv, .xlsx, .xbrl, .xml, .json`" | ✅ |
| 3 | 排除 `.doc/.ppt/.xls/.zip` | §5.1 特别约束："`.doc`、`.ppt`、`.xls` 是冻结证据证明不可靠的 legacy 声明，不得保留。`.zip` 未被真实 converter capability 证明，不得保留。" | ✅ |
| 4 | 排除第三方未选择扩展 | §5.1："第三方同一 format id 还映射的 `.text/.Rmd/.qmd/.xlsm/.potx` 等未选择扩展不进入产品声明；归一化比较后对应的 `.text/.rmd/.qmd/.xlsm/.potx` 也不得被 consumer 接纳。" | ✅ |
| 5 | help/schema/batch 只投影 13 个 suffix | §5.1："help/schema/batch 只能投影上述 13 个 suffix"；§6.2："batch enter 集合精确等于以下 13 个 suffix" | ✅ |
| 6 | batch enter/skip 测试 | Slice 2 Tests："batch 参数化覆盖 §5.1 每个格式：13 个冻结 suffix 的文件都 enter 并分别生成 standalone command；`.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx` 都稳定 `unsupported_suffix` skip，不生成 command、不自动归组；断言 enter 集合与 13 个 suffix 精确相等" | ✅ |
| 7 | `.xml` 仅是 XBRL XML candidate | §5.1："`.xml` 的多格式歧义必须通过'本产品明确选择的 `XML_XBRL` + constructor allowed_formats'消除…help/schema 投影 `.xml` 时必须明说'`.xml` 仅是 XBRL XML candidate，suffix 通过不代表任意 XML 或内容必然转换成功'" | ✅ |
| 8 | `.json` 不承诺任意 JSON 内容 | §5.1："`.json` 同样只表示 Docling JSON candidate，不承诺任意 JSON 内容可转换" | ✅ |

### R2 裁决：**已修复**。DS re-review 指出的"用户可见 suffix 清单由实现 agent 现场决定"缺口——逐 format 的 suffix tuple 未枚举——已消除。§5.1 冻结表格是字面量级的精确声明，implementation agent 不得增删或重排；batch enter/skip 测试以 13 个 suffix 为精确锚点。

## 3. R3 验证：non-Optional typed delete 与双向 action/emptiness 测试

### Controller 冻结决策

> `ValidatedFinsUploadFilingRequest.file_selection` 改为必需、非 Optional 的 `FinsUploadFilingFiles`；delete 由 validator 直接产生 `for_delete()`，workflow 不再把 `None` 转成 selection。Service 明确拒绝 create/update + empty selection 与 delete + non-empty selection，均在读文件/converter/batch 前 `ValueError`。两个方向都加零副作用测试。material delete 同样使用 `FinsUploadMaterialFiles.for_delete()`。

### 逐条验证

| # | Controller 要求 | plan 证据 | 结论 |
|---|---|---|---|
| 1 | `file_selection` 必需、非 Optional | §5.3："`ValidatedFinsUploadFilingRequest` 增加必需、非 Optional 的 `file_selection: FinsUploadFilingFiles`；不存在 `None` 状态" | ✅ |
| 2 | delete 由 validator 直接产生 `for_delete()` | §5.3："validator 对 create/update 直接产生非空 `from_upsert_paths(...)` selection，对 delete 直接产生 `FinsUploadFilingFiles.for_delete()`" | ✅ |
| 3 | workflow 不再把 `None` 转成 selection | §5.3："workflow 只转交 authoritative selection，不再把 `None` 转换成 delete selection"；§6.1："不再把 `list(raw_request.files)` 作为无角色输入，也不在 workflow 中把 `None` 转换为 selection。delete selection 已由 validator 直接产生" | ✅ |
| 4 | Service 拒绝 create/update + empty selection | §5.4："create/update + empty selection 拒绝…发生在文件读取、converter call 与 batch open 前" | ✅ |
| 5 | Service 拒绝 delete + non-empty selection | §5.4："delete + non-empty selection 也拒绝，二者均抛 `ValueError`，并且发生在文件读取、converter call 与 batch open 前" | ✅ |
| 6 | 两个方向都加零副作用测试 | Slice 3 Tests："另对 filing/material 两类 selection 分别覆盖 create/update + empty 与 delete + non-empty 两个方向，全部在 Service 入口以 `ValueError` 拒绝；所有非法组合均断言零文件读取、零 converter、零 batch" | ✅ |
| 7 | material delete 使用 `for_delete()` | §5.3："material delete 在同一位置直接产生 `FinsUploadMaterialFiles.for_delete()`" | ✅ |
| 8 | 不变式固化 | §7 #13："validated filing selection 永远非 Optional；create/update 只能配 non-empty selection，delete 只能配 empty-for-delete selection，Service 双向拒绝 action/emptiness 不一致" | ✅ |

### R3 裁决：**已修复**。DS re-review 指出的两处缺口——§5.2/§5.3 的 `None` vs empty-for-delete 表述张力、delete + non-empty selection 拒绝规则缺失——已消除。`file_selection` 明确为非 Optional，validator 直接产生 delete typed empty，Service 双向拒绝均有零副作用测试。

## 4. 第一轮 findings 回退检查

| ID | 第一轮 re-review 状态 | 本轮回退检查 | 结论 |
|---|---|---|---|
| M1 | 已修复 | §5.1 两阶段设计（模块级静态声明 + 构造期 lazy 校验）、stop condition、Slice 1 测试均保持不变 | 无回退 |
| M2 | 已修复 | §5.1 特别约束、§5.2 projection、§6.2 三面文案、Slice 2/4 测试均保持 `.xml` XBRL candidate 限定 | 无回退 |
| D1 | 已修复（R1 为其残留） | §3.1 #8、§5.2–§5.4、§6.2、Slice 2/3 均保持 `FinsUploadMaterialFiles` + `MATERIAL_SUFFIX_UNSUPPORTED` + CLI/tool/Service 同一 owner 构造入口 | 无回退 |
| D2 | 已修复（R3 为其相邻边界） | §5.4 closed union 签名、§7 #11、Slice 3 Tests 均保持 selection 与 `SourceKind` 一致校验 + 非法组合 `ValueError` | 无回退 |
| D3 | 已修复（R2 为其声明内容残留） | §5.1 单向子集校验、Slice 1 Tests 三态断言（缺失 fail-fast、新增不扩面、allowed_formats 同源）均保持 | 无回退 |
| D4 | 已修复 | §6.2 batch `.xsd` 稳定 skip + deferred、§3.2 非目标、Slice 2 Tests/Stop condition 均保持 | 无回退 |
| D5 | 已修复 | §5.4 companion 事件契约、§7 #12、Slice 3 双 fixture 事件断言均保持 | 无回退 |
| O1 | 已修复 | §5.2 projection helper、§6.2 三面文案、Slice 2/4 Tests 均保持逐面对照断言 | 无回退 |
| O2 | 已修复 | Slice 3 Tests DOCX+XLSX+DOCX fixture 保持 | 无回退 |

**回退检查结论**：9 个第一轮 findings 全部维持"已修复"状态，无任何回退。

## 5. Adversarial 检查

### 5.1 R1 的 try 内时序与 catch-all 投影一致性

plan §5.3 规定 material selection 在 "SEC/CN workflow 现有 `try` 内" 构造，catch-all 继续走既有 event/job failure contract，`fins_upload_failure_from_exception` 将 `FinsUploadFormatError` 投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`。§5.2 明确 message 固定为 `文件格式不受支持，请选择支持的文件后重试`，file_label 取安全 basename，retry_hint 固定。Slice 3 测试断言投影后的完整 kind/code/message/file_label 与全部副作用为 0。

该设计的实质是：构造点在 try 内 → 异常被 catch-all 捕获 → failure owner 将 `FinsUploadFormatError` 投影为 usage failure（非 `UNEXPECTED_RUNTIME`）。这是 DS re-review 的核心担忧——现在已通过 owner test 路径闭合。

### 5.2 R2 的 batch 候选集精确性

§5.1 冻结 13 个 suffix，Slice 2 Tests 断言 enter 集合与 13 个 suffix 精确相等，同时断言 `.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx` 稳定 skip。该测试直接锚定 batch 行为，实现 agent 不可能在不修改冻结 tuple 的前提下改变候选集。

### 5.3 R3 的 non-Optional 与 §7 不变式一致性

§5.3 明确 `file_selection` 非 Optional，§7 #13 固化为不变式。validator 对 delete 产生 `for_delete()`，workflow 不再翻译 `None`，Service 双向拒绝。跨层表示从"validator 可选 + workflow 翻译"收紧为"validator 必选 + workflow 直传"——消除了 DS re-review 指出的表述张力。

## 6. Findings

无 material finding。第二轮 Controller 冻结决策 R1/R2/R3 的修复均基于直接 plan 文本证据，设计决策已明确冻结，implementation agent 无需自行裁决。

## 7. Open Questions

无。plan §10 "没有未分类风险，没有需要实现 agent 自行猜测的 open question" 经本轮验证成立。

## 8. Residual Risks

| # | 风险 | 分类 | Owner / destination |
|---|---|---|---|
| R1 | suffix tuple 为模块级字面量 hardcode（plan 未显式写明该短语，但"模块初始化不 import Docling"约束已收敛设计路径） | 实现歧义极低 | implementation agent 自行确认；建议 plan 补充一句 |
| R2 | Docling 版本升级可能导致 `FormatToExtensions` 变化 | capability residual | plan §10 已覆盖：subset fail-fast + 测试固化 |
| R3 | 非 PDF 格式实际转换成功率未经 UF-PF06 证明 | content residual | UF-PF06 |
| R4 | `.xsd` 以外的 companion-only XBRL 附件类型未知 | companion residual | 后续产品需求 |
| R5 | batch companion 自动归组 | assigned to later work unit | UF-FIX07 |
| R6 | 显式 primary、重复路径、basename/derived-name collision | UF-FIX07 | UF-FIX07 |
| R7 | 137 条 full-real mandatory matrix 未重跑 | PF residual | UF-PF12 |

全部 residual risks 均已在 plan §10 中分类并指定 destination，无新增或未分类项。

## 9. Final plan review conclusion

**pass**

第二轮 Controller 冻结决策 R1/R2/R3 全部实现真正修复：

1. **R1**（usage failure owner / try 时序 / allowed files）：`upload_failure.py` 及其测试已纳入 Slice 3 allowed files；`USAGE/UNSUPPORTED_UPLOAD_FORMAT` closed contract 已在 §5.2 完整定义（kind/code/message/file_label/retry_hint）；material selection 在 workflow 现有 `try` 内、所有 external read/mutation 前构造；catch-all 经 failure owner 保持正确 usage 投影；端到端测试断言投影后完整字段与全部副作用为 0。
2. **R2**（13 suffix 精确集合）：§5.1 冻结表格逐 format 枚举字面量 suffix tuple，展平为精确 13 个有序小写 suffix；help/schema/batch 只投影该集合；batch 测试断言 enter 集合与 13 个 suffix 精确相等，legacy/第三方未选择扩展稳定 skip。
3. **R3**（non-Optional typed delete 与双向 action/emptiness 测试）：`file_selection` 改为必需非 Optional；validator 直接产生 `for_delete()`；workflow 不再翻译 `None`；Service 双向拒绝 create/update + empty 与 delete + non-empty，两类 selection 均有 `ValueError` + 零副作用测试；不变式 §7 #13 固化。

第一轮 findings（M1/M2/D1–D5/O1/O2）全部维持"已修复"状态，无回退。

plan 可进入 implementation。
