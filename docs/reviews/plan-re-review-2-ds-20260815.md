# Plan Re-Review（第二轮 · AgentDS）：UF-FIX06 converter-capability-owner 第二轮修订后计划

## Review Metadata

- **Reviewed target**：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（第二轮 plan review fix 后修订版，571 行）
- **Reviewer**：AgentDS（R1/R2/R3 原提出者，本轮为第二轮 re-review）
- **Timestamp**：2026-08-15T14:33:06+0800（系统时钟生成）
- **Baseline commit**：`a3d584fcf1444fcf5d633f2dd8bdb83eaf5adab9`
- **Review inputs**（均已完整读取至 EOF）：
  - 原 plan 修订版：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`
  - plan-fix 记录（含第二轮修复状态）：`docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`
  - 第一轮 re-review：`docs/reviews/plan-re-review-mimo-20260815.md`（pass）、`docs/reviews/plan-re-review-ds-20260815.md`（fail，R1/R2/R3 出处）
  - 第二轮 Controller 裁决：`docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md`（PLAN FIX REQUIRED，冻结 R1/R2/R3 决策）
- **Review scope**：只验证 R1/R2/R3 是否按 Controller 冻结决策完全修复、第一轮 M1/M2/D1–D5/O1/O2 是否无回退；不重裁 goal，不新增 scope 建议。只做 review；未修改 plan/代码/测试/README/registry/evidence，未 commit，未运行任何 PF。
- **核心判据**：Controller 冻结决策的每个可验证要点是否落到 plan 的 contract、slice、测试与验证计划文本中；实现 agent 是否仍存在用户可见语义上的自裁决空间。

## 一、R1/R2/R3 逐项验证（冻结决策 vs plan 证据）

### R1 — usage failure owner / try 时序 / allowed files

Controller 冻结决策要点：`USAGE` kind + closed code；`fins_upload_failure_from_exception` 投影 `FinsUploadFormatError` 为 bounded/path-free usage failure；`upload_failure.py` 及其测试进 Slice 3 allowed files；material 在现有 `try` 内、所有 published-state read/company staging/file read/converter 前构造；catch-all 保持正确 usage 投影；Slice 3 端到端断言投影后 kind/code/message 与零副作用；异常不得逃逸。

| 冻结要点 | plan 证据 | 状态 |
|---|---|---|
| `USAGE` kind + `UNSUPPORTED_UPLOAD_FORMAT` code | §5.2（152–157 行）扩展 closed contract 全部列出 | 已修复 |
| 投影 bounded/path-free、不落入 `RUNTIME/UNEXPECTED_RUNTIME`、workflow 不得复制映射 | §5.2（158–159 行）；§4 owner 表第三行（83 行）owner 唯一、SEC/CN catch-all 只消费该投影 | 已修复 |
| 固定 message/`file_label`/`retry_hint` | §5.2（155–157 行）：`文件格式不受支持，请选择支持的文件后重试`、error 安全 basename、`请查看上传帮助中的支持格式后重试` | 已修复 |
| material 构造点在现有 `try` 内、所有 published-state read/company staging/其他 mutation/file read/converter 前 | §5.3（176–178 行）、§6.2（263–264 行）、Slice 3 Exact changes #2（402–403 行）三处一致复述完整顺序 | 已修复 |
| material delete 同位置直接 `for_delete()` | §5.3（178–179 行）、Slice 3 #2（404 行） | 已修复 |
| `upload_failure.py` + owner test 进 Slice 3 allowed files | Slice 3 allowed production files 含 `dayu/fins/upload_failure.py`（384 行）；allowed test files 含 `tests/fins/test_upload_failure.py` 新增（393 行） | 已修复 |
| 端到端断言投影后 kind/code/message/file label 与零副作用，异常不逃逸 | Slice 3 Tests（418–425 行）：`kind=USAGE`、`code=UNSUPPORTED_UPLOAD_FORMAT`、精确 message、`file_label=safe_basename`；published-state read、company/source mutation、文件读取、converter call、batch open 均为 0；既有 event/job failure contract 收到投影；异常没有逃逸 | 已修复 |
| 验证计划覆盖 | §9 pytest 列表含 `tests/fins/test_upload_failure.py`（485 行）；coverage include 含 `dayu/fins/upload_failure.py`（507 行） | 已修复 |

代码事实核验：`FinsUploadFailureReason`（`upload_failure.py:72–88`）已具备 `retry_hint`/`file_label` 可选字段，R1 投影无需新增字段，只增 kind/code 枚举值与一个显式 `isinstance` 分支，实现可行。SEC material workflow 外层 `try` 起于 `sec_upload_workflow.py:457`，`try` 内第一动作即 published-state read（`:458` `_safe_get_document_meta`），catch-all 在 `:564`——构造点插入 `try` 首行完全满足"try 内、所有 read/mutation 前"的冻结时序。catch-all 现传 `file_label=None`，plan §5.2 措辞"`file_label` 取 error 已校验的安全 basename"明确指向投影函数从 `FinsUploadFormatError` 取 basename 而非依赖调用参数，语义自洽，catch-all 无需改动。

**R1 结论：已修复，无回退。**

### R2 — 13 suffix 精确集合

Controller 冻结决策要点：逐格式冻结 9 个 tuple、统一小写、顺序稳定、排除 `.doc/.ppt/.xls/.zip` 与第三方未选择扩展、help/schema/batch 只投影 13 个、精确集合与 batch enter/skip 测试、`.xml` XBRL candidate 与 `.json` 不承诺内容可转换。

| 冻结要点 | plan 证据 | 状态 |
|---|---|---|
| 逐格式 tuple 与裁决一致 | §5.1 表格（104–114 行）：PDF=`(".pdf",)`、DOCX=`(".docx",)`、PPTX=`(".pptx",)`、HTML=`(".htm",".html",".xhtml")`、MD=`(".md",".txt")`、CSV=`(".csv",)`、XLSX=`(".xlsx",)`、XML_XBRL=`(".xbrl",".xml")`、JSON_DOCLING=`(".json",)`——逐项与裁决完全一致 | 已修复 |
| 展平精确 13 个、小写、顺序稳定 | §5.1（116–117 行）：`.pdf, .docx, .pptx, .htm, .html, .xhtml, .md, .txt, .csv, .xlsx, .xbrl, .xml, .json` 恰 13 个 | 已修复 |
| 排除 legacy 与第三方未选择扩展 | §5.1（118–127 行）：`.text/.rmd/.qmd/.xlsm/.potx` 不得接纳；`.doc/.ppt/.xls` 不得保留；`.zip` 不得保留；`.xsd` 只属 companion overlay | 已修复 |
| help/schema/batch 只投影 13 个 | §5.1（126 行）、§6.2（254–258 行）batch enter 集合精确等于 13 个 | 已修复 |
| 精确集合与 enter/skip 测试 | Slice 1 Tests（311–313 行）逐格式精确相等 + 展平精确等于有序 13 个 + 未声明第三方 suffix 不出现在静态投影；Slice 2 Tests（362–365 行）13 个 suffix 全部 enter 并生成 standalone command、`.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx` 稳定 `unsupported_suffix` skip、enter 集合与 13 个精确相等 | 已修复 |
| `.xml`/`.json` 限定文案 | §5.1（129 行）`.xml` 仅 XBRL XML candidate、`.json` 仅 Docling JSON candidate 不承诺任意 JSON 可转换 | 已修复 |
| implementation agent 不得改动冻结声明 | §5.1（101–102 行）"必须直接使用以下模块级字面量 tuple……不得现场增删或重排"；Slice 1 Stop condition（321–322 行）无法证明时停止交 Controller 裁决 | 已修复 |

**R2 结论：已修复，无回退。** 第一轮对"HTML 是否含 `.xhtml`、MD 是否含 `.txt`"的未枚举质疑已被冻结字面量消除；`Slice 1 Stop condition` 为个别成员若不被安装的 `FormatToExtensions` 支持提供了停止裁决出口，不自相矛盾。

### R3 — non-Optional typed delete 与双向 action/emptiness 测试

Controller 冻结决策要点：`file_selection` 必需非 Optional；delete 由 validator 直接产生 `for_delete()`，workflow 不翻译 `None`；Service 双向拒绝 create/update + empty 与 delete + non-empty，读文件/converter/batch 前 `ValueError`；两个方向零副作用测试；material delete 用 `for_delete()`。

| 冻结要点 | plan 证据 | 状态 |
|---|---|---|
| `file_selection` 必需、非 Optional，不存在 `None` 状态 | §5.3（165–166 行）、Invariant 13（283–284 行）、Slice 2 Exact changes #3（350–351 行） | 已修复 |
| delete 由 validator 直接产生 `for_delete()`，workflow 不翻译 `None` | §5.3（167–169 行）、§6.1（246–248 行）、Slice 2 Tests（366–367 行）所有 action 下字段非 Optional | 已修复 |
| Service 双向拒绝 + `ValueError` + 读文件/converter/batch 前 | §5.4（197–199 行）create/update + empty 拒绝、delete + non-empty 拒绝，均 `ValueError` 且在文件读取、converter call、batch open 前；Invariant 13 固化 | 已修复 |
| 双向零副作用测试（filing/material 两类） | Slice 3 Tests（426–430 行）filing/material 两类 selection 分别覆盖两个方向，全部零文件读取、零 converter、零 batch；合法 delete typed empty 与既有无文件 delete 行为同时回归 | 已修复 |
| material delete 用 `FinsUploadMaterialFiles.for_delete()` | §5.3（178–179 行）、Slice 3 #2（404 行） | 已修复 |

**R3 结论：已修复，无回退。** 第一轮指出的 §5.2/§5.3 字面冲突（`None` 双表示）已被消除：§5.2 保留"不用 `None` 表示空状态"、§5.3 改为 validator 直接产生 typed empty，两节不再冲突；delete + non-empty 的拒绝规则与双向测试缺口均已补齐。

## 二、第一轮 findings 无回退检查（M1/M2/D1–D5/O1/O2）

以第一轮两份 re-review 记录的"修复证据"为基准逐条比对修订后原 plan，全部关键条款仍在位：

| ID | 关键条款 | 修订后位置 | 回退？ |
|---|---|---|---|
| M1 | 模块级静态声明不 import Docling + 构造期 lazy 子集校验 + help 不触发 Docling import 测试 | §5.1（98–99、130 行）、Slice 1 Tests/Stop condition（316、323 行） | 无 |
| M2 | `.xml` XBRL candidate 三面文案 + 逐面对照断言 | §5.1（129 行）、§6.2（266 行）、Slice 4 Tests（458 行） | 无 |
| D1 | `FinsUploadMaterialFiles` 同一 owner 构造入口覆盖 CLI 与 tool/Service，mutation 前准入、全转换 | §5.2（143 行）、§5.3（174–183 行）、§6.2（262–267 行）、Slice 2/3 Tests（358、418–425 行） | 无（R1 补全投影链后更完整） |
| D2 | closed union 签名 + `SourceKind` 一致性 + 非法组合 `ValueError` + 零读取/converter/batch | §5.4（190–202 行）、Slice 3 Tests（426–427 行） | 无（R3 补强双向拒绝） |
| D3 | 单向子集校验、缺失 fail-fast、第三方新增不 fail 不扩面、`allowed_formats` 与 format ids 同源 | §5.1（99、132 行）、Slice 1 Tests（315 行） | 无（R2 补全声明内容） |
| D4 | batch 单文件命令、`.xsd` 稳定 skip、不自动归组、direct upload 是 companion 入口 | §6.2（253–261 行）、Slice 2 Tests/Stop condition（362–364、375 行） | 无 |
| D5 | companion 无 `conversion_started`、仅 source=`original` 的 `file_uploaded`、不新增 event type | §5.4（210 行）、Invariant 12（282 行）、Slice 3 Exact changes #5（407 行）与 Tests（414–415 行） | 无 |
| O1 | 三面一致文案：首文件 primary、companions 不转换、`.xml` candidate、suffix 不保证内容成功 | §6.2（266 行）、Slice 2 Tests（368 行）、Slice 4 Tests（458 行） | 无 |
| O2 | DOCX+XLSX+DOCX fixture：只转首项、后两项原样存储、唯一派生资产、requested/stored=3、无伪转换事件 | Slice 3 Tests（415 行） | 无 |

**结论：九个第一轮 accepted findings 无回退。**

## 三、代码事实核验与 adversarial 检查

1. **failure 投影字段可行性**：`FinsUploadFailureReason` 已含 `retry_hint`/`file_label` 可选字段，R1 不需要动 dataclass 结构，只新增枚举成员与投影分支。✓
2. **try 时序可行性**：SEC material workflow 外层 `try`（`sec_upload_workflow.py:457`）内第一动作是 published-state read（`:458`），catch-all（`:564`）投影所有异常——构造点插在 `try` 首行即满足"try 内、所有 read/mutation/converter 前"，且非法 suffix 时 `UPLOAD_STARTED`（`:464`，在 read 之后）不会发出、直接走 `UPLOAD_FAILED`。这是冻结时序的自然结果，事件语义反而更干净。CN material workflow 结构同构（catch-all `cn_pipeline.py:1179`）。✓
3. **R3 结构可行性**：`ValidatedFinsUploadFilingRequest` 现为 `@dataclass(frozen=True, slots=True)`（`ingestion_runtime.py:713`），新增必需非 Optional 字段需迁移全部构造点——构造点集中在 validator 与 SEC/CN fresh validation，均在 Slice 2/3 allowed files 内。✓
4. **`_FAILURE_KEYS` exact-key 契约**：不受 USAGE 新增影响。✓

## 四、Findings

### N1-未修复-低-`upload_failure_reason_from_json` 的 kind 推导未随 USAGE 同步扩展（R1 closed contract 的一致性守卫遗漏）

- **位置**：plan §5.2（150–159 行，failure 投影扩展声明）、Slice 3 Exact changes #6（408–410 行）、Slice 3 Tests（新增 `tests/fins/test_upload_failure.py`，未列 round-trip 断言）。
- **问题类型**：契约缺失 / 不可直接实施（小）。
- **当前写法**：plan 要求 `FinsUploadFailureKind` 增加 `USAGE`、`FinsUploadFailureCode` 增加 `UNSUPPORTED_UPLOAD_FORMAT`，并扩展 `fins_upload_failure_from_exception`；但未点名 `upload_failure_reason_from_json` 的 kind/code 一致性推导需同步扩展，Slice 3 测试也未要求 USAGE failure 的 JSON 往返断言。
- **反例/失败场景**：实现 agent 按 plan 只改枚举与投影分支后，任何 USAGE failure reason 经 `to_json()` 进入 event payload（catch-all 中 `failure=failure_reason.to_json()`，`sec_upload_workflow.py:586` 同类路径），再由消费方经 `upload_failure_reason_from_json` 恢复时（真实调用方：`ingestion_runtime.py:1325` 从 raw failure JSON 恢复 failure reason）即抛 `ValueError("upload failure kind 与 code 不一致")`，失败恢复/审计路径损坏，且该错误本身信息误导（"kind 与 code 不一致"而非格式问题）。
- **为什么有问题**：`upload_failure.py:327–333` 的推导是三元封闭集合逻辑（code ∈ CONTENT 集合 → CONTENT，∈ STORAGE 集合 → STORAGE，否则 → RUNTIME），`UNSUPPORTED_UPLOAD_FORMAT` 不属于任何现有集合会被强制推导为 RUNTIME，与序列化的 `kind="usage"` 冲突。该函数是 closed contract 的一致性守卫，新增 kind 必须同步扩展推导（新增 usage code 集合并扩为三分支或查表）；既有测试（`test_company_identity_storage_contract.py:665`、`test_fins_ingestion_runtime.py:542/581`）证明 round-trip 是该 owner 的既有 public contract 行为。plan 声称"没有需要实现 agent 自行猜测的 open question"（§10），而此处实现 agent 需自行发现并扩展一个未点名的守卫函数。
- **直接证据**：plan §5.2/§10 原文；`dayu/fins/upload_failure.py:161–169`（`_CONTENT_FAILURE_CODES`/`_STORAGE_FAILURE_CODES` 集合）、`327–333`（三元 kind 推导）；`dayu/fins/ingestion_runtime.py:1325`（真实恢复调用方）；既有 round-trip 测试。
- **影响**：实现 agent 漏改则 USAGE failure 事件 JSON 往返抛 ValueError（恢复/审计路径损坏）；改对了但 plan 未点名，属于实现时现场决策，与 code-generation-ready 声称略有出入。不改任何已冻结决策。
- **建议改法和验证点**：plan §5.2 或 Slice 3 Exact changes 补一句"`upload_failure_reason_from_json` 的 kind/code 一致性推导随新增 usage code 同步扩展"；Slice 3 Tests 补一条 USAGE failure reason 的 `to_json` → `upload_failure_reason_from_json` 往返相等断言。均为文本级修订，无需回 Controller。
- **修复风险（低）**：仅 plan 文本补充，无架构影响。
- **严重程度（低）**：不改变用户可见语义或冻结决策；修复路径唯一且机械，实现 agent 在 Slice 3 修改 `upload_failure.py` 且运行既有 round-trip 测试时大概率自然收敛，但 plan 级点名可消除最后歧义。

## 五、Open Questions

无 blocking open question。R1/R2/R3 的冻结决策均已逐项落到 plan 文本；N1 为已定位、单句文本级修订即可收敛的小缺口。

## 六、Residual Risks and suggested tracking destination

| 风险 | 去向 |
|---|---|
| batch companion association（同目录归组） | 后续 batch association / UF-FIX07 类 work unit（plan §10 已分类） |
| 真实全格式矩阵与 XBRL companion CLI evidence | UF-PF06（plan 已声明不重跑） |
| 137 条 full-real mandatory matrix | UF-PF12（plan 已声明不重跑） |
| 显式 primary、重复输入、basename/derived-name collision | UF-FIX07（plan 已分类） |
| `.xsd` 以外 companion-only 类型 | 后续 Fins/XBRL 产品能力 work unit（plan 已分类） |
| 第三方删除已声明 suffix 时 help 静态展示但运行 fail-fast | plan §10 已定性为有意的安全失败；pinned dependency + owner test 管理 |
| 非法 suffix 的 material 事件序列中不发 `UPLOAD_STARTED`（冻结时序的自然结果，现有序列为 STARTED→FAILED） | 非契约破坏；如需保留 STARTED 需重新裁决构造点，不建议 |
| N1 的 round-trip 推导同步 | 建议随本轮 plan 文本修订一并处理，去向为本 work unit plan |

## 七、Final plan review conclusion

**pass-with-risks**

R1/R2/R3 均按 Controller 冻结决策**完全修复**：R1 的 failure owner（USAGE kind + closed code + bounded/path-free 固定投影）、try 内最前时序与 allowed files 全部落位；R2 的 9 format/13 suffix 冻结字面量、排除集、help/schema/batch 精确投影与 enter/skip 测试全部落位；R3 的非 Optional `file_selection`、validator 直接产生 `for_delete()`、Service 双向 action/emptiness 拒绝与双方向零副作用测试全部落位。第一轮 M1/M2/D1–D5/O1/O2 九项修复无回退。

唯一 finding N1（低）：`upload_failure_reason_from_json` 的 kind/code 推导守卫未在 plan 中点名同步扩展，且缺 USAGE round-trip 测试断言。该缺口不改任何冻结决策、不改变用户可见语义、修复路径唯一，不构成 implementation 阻断；但按"code-generation-ready、无自行猜测"的 claim 应在进入 implementation 前以一句 plan 修订收敛。

**允许的下一动作**：可授权 implementation（N1 为低风险文本级补丁）；若按严格 gate 纪律，先补 N1 的一句 plan 修订与一条测试断言再进入 implementation 为更稳路径。本 reviewer 不作单向否决。
