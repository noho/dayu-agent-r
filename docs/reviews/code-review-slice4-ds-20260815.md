# Code Review

## Scope

- Mode: current changes（第二路独立 review，AgentDS）
- Branch: `codex/upload-filing-oracle`
- Base: `8033a56eb0f44ae5664c510b84ebe448050888eb`（与 Slice 4 implementation artifact 声明一致）
- Work unit: `UF-FIX06 converter-capability-owner` Slice 4（文档、全局审计与验证收口）
- Included scope:
  - `README.md`（+8/-1，用户手册上传章节）
  - `dayu/fins/README.md`（+14/-6，capability owner / role overlay / batch scanner / Service data flow）
  - `tests/README.md`（+35，focused 回归命令与 owner coverage 声明）
  - `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`（untracked implementation artifact）
- Excluded scope:
  - 生产代码与测试 diff：`git diff 8033a56e --name-only` 仅含上述三个 README，无生产/测试变更；走读只覆盖与声明相关的代码路径。
  - 未重跑 pytest / coverage / pyright（数字来自 implementation artifact 的运行声明，只做可复核性核查，未复核数值真伪）。
  - 未运行 UF-PF06 / UF-PF12 / 真实 CLI evidence（用户明确禁止）。
  - 冻结 evidence bundle 位于 workspace 外，未读取或复核 SHA；仓库内无该 bundle 痕迹，与 artifact 声明一致。
- 对照基准：accepted plan（`uf-fix06-converter-capability-owner-accepted-plan-20260815.md`）、原 plan §8 Slice 4 与 §9 验证计划、plan-fix M2/O1 冻结文案、三个 README 的 Agent更新约束（tests/README.md 以第 3 行职责声明为准）。
- Parallel review coverage: 无（本路独立完成）。

## Findings

### 1-未修复-中-根 README 把 companion 后缀准入误写为转换资格，错误涵盖 companion-only `.xsd`

- **入口/函数**: 根 README §5.2 上传说明；同源文案 owner 为 `dayu/fins/upload_format_contract.py::project_fins_upload_format_text`（`FINS_UPLOAD_FORMAT_TEXT.filing_files`），CLI help（`dayu/cli/arg_parsing.py:924`）与 LLM-facing upload tool schema（`dayu/fins/tools/upload_tools.py:238`）直接消费同一文本
- **文件(行号)**: `README.md:319-320`；同源缺陷位于 `dayu/fins/upload_format_contract.py:565`
- **输入场景**: 用户或 LLM 阅读该段判断 `--files` 后缀规则；或上传 `.xsd` 作为 companion
- **实际分支**: companion 准入为 `accepts_companion = accepts_primary ∪ companion_only_suffixes`（`upload_format_contract.py:254`），`.xsd` 因此通过准入；但 `.xsd` 无转换资格（`accepts_primary` 只接受 converter capability，`upload_format_contract.py:236`）；filing 的 converter inputs 只含 `selection.require_primary()`（`docling_upload_service.py:1020`），companion 永不进入转换循环
- **预期行为**: 文案应区分两种准入——主文件后缀通过 = 具备转换资格（且不保证转换成功）；随附文件后缀通过 = 只具备随批原样保存资格，其中 `.xsd` 完全不具备转换资格，converter-capable companion 具备资格但不被转换
- **实际行为**: 文案写成通用断言“后缀通过只表示文件具备转换资格，不保证其内容一定转换成功”。对 companion 该句为假：`.xsd` 通过准入但不具备任何转换资格；且“不保证其内容一定转换成功”暗示会对通过后缀检查的文件尝试转换，与同段首句“后续项是 companions，只保留原始文件，不执行 Docling 转换”（`README.md:318`）自相矛盾。根 README 将这句话排在“XBRL companion 可以作为后续文件随同一批上传并原样保存”之后，通用主语“后缀通过/文件”天然把 companion 纳入承诺范围，比 owner 文案中紧贴 `.xml` 专属句的排列更易误读
- **直接证据**: 三处角色语义（`upload_format_contract.py:236/254`、`docling_upload_service.py:1020`）与文案（`upload_format_contract.py:565`、`README.md:319-320`）的同源对照；plan-fix M2 冻结文案为“suffix 通过不表示任意 XML 或内容必然转换成功”，实现新增了 plan 未授权的正向断言“只表示具备转换资格”，并扩散到根 README
- **影响**: 用户/LLM 对 companion 是否被转换形成错误判断；违反 CLAUDE.md LLM-facing 文本自足约束（不得依赖隐式规则，规则必须自解释）；该句同时进入 CLI help 与 LLM-facing tool schema，影响面覆盖用户与模型两路
- **建议改法和验证点**:
  - owner 一处修复（help/schema 自动同源更新）：`upload_format_contract.py:565` 改为“主文件后缀通过只表示具备转换资格，不保证其内容一定转换成功；随附文件只校验可随批保存的后缀，不做转换。”
  - 根 README 投影同步：`README.md:319-320` 改为“`.xml` 只是 XBRL XML candidate；主文件后缀通过只表示具备转换资格，不保证其内容一定转换成功；随附文件（含 `.xsd`）只按可随批保存的后缀准入，不做转换。”
  - 验证点：重跑 help/schema/根 README 三面对照，确认不再出现把 companion 准入描述为转换资格的措辞
- **修复风险（低）**: 纯文案，不动生产逻辑、selection 类型或 workflow；唯一风险是改动 owner 文案后需重跑 `test_upload_format_contract.py::test_text_projection_is_self_contained_and_uses_exact_suffix_order` 确认投影不变量仍通过
- **严重程度（中）**

### 2-未修复-低-根 README 失败触发枚举收窄为 filing 词汇，material 转换失败不再被描述

- **入口/函数**: 根 README §5.2 上传终态摘要段（同时服务 `upload_filing` 与 `upload_material` 两个入口）
- **文件(行号)**: `README.md:334`
- **输入场景**: material 上传时某文件内容无法转换（含空文件经转换路径失败）
- **实际分支**: material 转换失败在 `docling_upload_service.py:790-791` 原样重抛 `DoclingConversionError`，workflow 映射为 failed，无 source/blob 发布，stored 为 0
- **预期行为**: 用户手册继续说明 material 任一文件转换失败同样整批失败、stored 为 0（旧文案“损坏文件或一组文件中任一文件无法解析时”覆盖两种 source kind）
- **实际行为**: 新文案触发清单为“空文件、原始文件读取失败或 primary 内容无法成功转换时”，并新增“也不会回退为只保存原文件或 companions”；“primary/companions”是 filing-only 词汇，material 转换失败这一触发被移出描述。行为本身未回退（代码未变、原子性成立），但用户手册对 material 的失败契约描述出现空洞
- **直接证据**: diff 对照（旧句“空文件、损坏文件或一组文件中任一文件无法解析时”被替换）+ 代码路径 `docling_upload_service.py:790-791`（material 转换失败零发布）
- **影响**: material 用户的失败语义文档缺失；属文档覆盖回归，非行为回归
- **建议改法和验证点**: 恢复 source-kind 中立表述，例如“空文件、原始文件读取失败或（filing 主文件 / material 任一文件）转换失败时，整批上传失败且 `stored files` 为 `0`，不会把先处理成功的文件计为已保存；filing 也不会回退为只保存原文件或 companions。”验证点：重读该段确认两种 source kind 的失败触发均有覆盖
- **修复风险（低）**
- **严重程度（低）**

### 3-未修复-低-Fins README 删除 material 独立 company publication 语义条款，且全文无替代说明

- **入口/函数**: Fins README upload 章节（production upload 段落）
- **文件(行号)**: `dayu/fins/README.md:572`（diff 删除句尾“material 仍保留自己的既有 generic failure 与 company publication 语义”）
- **输入场景**: 开发者依据该段理解 filing/material 的 publication batch 结构
- **实际分支**: 两个 material workflow 都在 `prepare_upload` 前以独立 `company_batch` 提交 company meta（`sec_upload_workflow.py:492-505`、`cn_pipeline.py:1107-1120`），material 转换失败时已提交的 company meta 不回滚；filing 才由 company/source/blob 共享同一 caller batch（`sec_upload_workflow.py:227-247`，Fins README:123 的共享 batch 声明是 filing-scoped）
- **预期行为**: 文档保留 material 与 filing 的 publication batch 差异，避免读者把 filing 的单 batch 模式外推到 material
- **实际行为**: 删除后全文不再说明 material 的独立 company batch 语义；新句“mixed input 在首个失败处 fail-fast，先转换成功的内存产物不形成 company/source/blob publication”读起来 filing/material 统一，会诱导读者得出 material 同样单 batch、company meta 随 source 一起失败的错误结论。该删除不在 plan §8 Slice 4 exact change #3 的授权清单内（授权只含 documents capability、Fins role overlay、首文件一次转换、全部 originals 原子保存、计数与取消不变）
- **直接证据**: 两个 material workflow 的 company batch 代码位置与 diff 中该句的删除；plan Slice 4 exact change #3 的授权范围
- **影响**: 开发文档与代码语义漂移；无行为回退
- **建议改法和验证点**: 在 `dayu/fins/README.md:574` 附近补回 material 范围说明，例如“material 仍保持既有独立 company batch 语义：company meta 在 prepare 前于独立 batch 提交，转换/存储失败不回滚已提交 company meta，source/blob 保持零部分发布。”验证点：重读确认 filing 共享 batch（line 123）与 material 独立 company batch 两处事实并存且各自 scoped
- **修复风险（低）**
- **严重程度（低）**

## 已核查且未发现问题的事项

- **XBRL/.xml/legacy 格式承诺精确**：capability 为 9 格式/13 后缀（`docling_runtime.py:220-232`），`.xml`/`.xbrl` 同属 `XML_XBRL`，`.xml` 作为 XBRL candidate 的表述成立；`.xbrl`/`.xml` 均属 primary 后缀，可作 companion 原样保存（`accepts_companion`）；legacy DOC/PPT/XLS 与 ZIP 不在 capability 内，`test_primary_rejects_legacy_unselected_and_companion_only_suffixes` 固化拒绝。
- **Fins README capability owner 声明同源**：`DOCLING_CONVERTER_CAPABILITY` 不可变静态声明，构造期 `_resolve_docling_allowed_formats` 延迟做“产品 suffix ⊆ 已安装 Docling 映射”的单向子集校验（`docling_runtime.py:353-399`），`allowed_formats` 由同一声明产生；第三方新增扩展名既不进投影也不致失败——README:67 表述准确。
- **role overlay 声明同源**：filing 首项 primary/后续 companion、`.xsd` 仅 companion、material 全转换，与 `upload_format_contract.py` 的 selection 不变量逐条一致；`DoclingUploadService._prepare_upload_selection` 双向校验 `SourceKind` 与具体 selection 类型（`docling_upload_service.py:1016-1032`）。
- **batch scanner 声明同源**：`upload_batch.py:418` 用 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 判定 standalone candidate，无本地后缀集合；`.xsd` 稳定 `unsupported_suffix` skip；无目录位置推断 primary/companion 的代码。
- **Service data flow 声明同源**：filing 静态校验（workspace read 前）即产生 typed `file_selection`，SEC workflow 消费 fresh validation 的 `authoritative_request.file_selection`（`sec_upload_workflow.py:209`）；material selection 在两个 workflow 内于 prepare 前构造；filing 只转换 primary、material 全转换、companion 无 `conversion_started` 事件、`primary_document` 由首次（filing 唯一）转换显式产生、全 originals + 唯一派生资产同 batch 发布——均与代码一致。
- **requested/stored 契约无回退**：`requested_file_count = len(validated request files)`，`stored` 只累计 original 资产（`docling_upload_service.py:541-542`），`ok` 摘要强制 `stored == requested` 不变式，`skipped/deleted/failed/cancelled` 固定 stored 0。
- **cancel 契约无回退**：根 README:341（Ctrl-C 协作取消语义）与 Fins README:662（claim-once summary、cancelled 终态不被迟到取消改写）在 diff 中未触碰；`commit_prepared_upload_batch` 的取消线性化点与 rollback 边界未变。
- **受保护资产无 diff**：`git diff 8033a56e --name-only` 仅三个 README；`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、`docs/engine/design.md` 无变更；untracked 文件仅 slice4 implementation doc。
- **静态 owner audit 复跑通过**：`rg 'FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES' dayu tests -g '*.py'` 与 `rg '_pick_primary_docling_file' dayu tests -g '*.py'` 均无结果；三个 README 与 slice4 doc 中无旧 allow-list 真源残留（slice4 doc 内仅为历史叙述）。
- **tests README 可复核**：新增 14 个测试文件全部存在且与 plan §9 命令逐字一致；coverage 表 11 个文件与 plan §9 `--include` 清单一致；pyright 命令与 tests README 标准命令一致；“deterministic owner-level 回归不替代 UF-PF06/UF-PF12”的边界声明诚实。两轮矩阵数字（1235/1338 passed、92% aggregate）为 implementation 运行声明，本路未重跑复核数值。
- **README 约束合规**：根 README 未写内部架构/治理术语（F1 属语义错误而非越界）；Fins README 未写用户安装命令；tests README 只描述既有测试事实。

## Open Questions

- 无。F1-F3 均由同一条代码路径的直接证据支撑，不影响结论置信度。

## Residual Risk

- 未重跑 pytest/coverage/pyright：implementation artifact 中的 1338 passed、11 文件 coverage 与 `0 errors` pyright 声明未被本路独立复核，只能确认命令与文件清单可复核。
- 未运行 UF-PF06 全格式 fixture 矩阵与 UF-PF12 全量 CLI scenario：真实格式矩阵证据仍由对应 PF work unit 承担（artifact 已如实分类）。
- 冻结 evidence bundle 位于 workspace 外，本路未复核其 SHA-256。
- material 独立 company batch 与“零部分发布”测试断言的边界：material 测试在 success 路径断言 company meta 已发布、admission 失败路径断言拒绝 company/source batch；转换失败后 company meta 已提交的既有语义未被本路单独核验测试覆盖，依赖 F3 修复后文档与代码的对照收敛。

## 结论

**BLOCKED**

- Blocking finding：F1（中）——根 README（及同源 CLI help / LLM-facing tool schema 文案 owner）将 companion 后缀准入误写为转换资格，错误涵盖 companion-only `.xsd`。这是本纯文档 Slice 交付物中的语义错误，且直接进入 LLM-facing 文本。
- Non-blocking findings：F2（低，根 README material 失败触发描述空洞）、F3（低，Fins README material 独立 company batch 语义条款被删且 plan 未授权）。
- 最小修复：F1 只需改 owner 文案一处（`upload_format_contract.py:565`，限定“主文件后缀通过……”并补随附文件准入说明）加根 README 投影一句（`README.md:319-320`）；F2 恢复 source-kind 中立触发表述；F3 在 Fins README upload 段落补回 material 独立 company batch 一句。三处均为纯文案，修复风险低，不需要动生产代码、测试或任何受保护资产。
- 无行为回退证据：原子发布、requested/stored、cancel 契约、受保护 registry/oracle/scenario/evidence/design 均经对照无 diff。
