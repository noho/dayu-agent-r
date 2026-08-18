# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `267e90b1`（gateflow: accept UF-FIX06 implementation plan）
- Review 对象：相对 base 的 `dayu/documents/docling_runtime.py`、`tests/documents/test_docling_runtime.py` 与新增 `docs/gateflow/uf-fix06-slice1-implementation-20260815.md`
- 已读取输入：accepted plan（`uf-fix06-converter-capability-owner-accepted-plan-20260815.md`）、完整 plan（含 §5.1 冻结契约与 Slice 1 Exact changes/Tests/Stop condition）、implementation artifact、两个 changed file 的完整 diff 与全文
- Parallel review coverage: 无
- Review 时间：2026-08-15 14:59 CST

### 已核验事实（直接证据）

- **9/13 冻结契约**：`docling_runtime.py:216-228` 的字面量 tuple 与 plan §5.1 冻结表逐项精确相等（9 个 format id、展平 13 个 suffix、顺序一致）；测试 `test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset` 以精确相等断言钉死。
- **静态能力唯一 owner 且无 eager import**：全仓仅一处 `DocumentConverter(` 构造点（`docling_runtime.py:591`），所有消费方经 `convert_pdf_bytes_with_docling` 汇入同一 builder；模块级 import 仅标准库（`os/logging/sys/dataclasses/typing`），`dayu/__init__.py` 与 `dayu/documents/__init__.py` 均无 docling 依赖；子进程测试以 `sys.modules['docling'] = None` 阻断后模块导入与 `primary_suffixes` 投影仍成功。
- **FormatToExtensions 单向子集**：已安装 docling 2.90.0 的 `FormatToExtensions` 逐项包含冻结的 13 个 suffix（如 `MD: ["md","txt","text","qmd","rmd","Rmd"]`，`XML_XBRL: ["xml","xbrl"]`）；生产代码只做「产品 ⊆ 第三方」校验（`docling_runtime.py:385-393`），第三方新增 suffix 不扩面、不失败（有测试钉死）。
- **allowed_formats 同源构造**：`build_docling_pdf_converter` 以 `_resolve_docling_allowed_formats(DOCLING_CONVERTER_CAPABILITY)` 的结果显式传入构造器；测试以真实 `DocumentConverter` 断言 `allowed_formats` 与 capability format ids 精确相等。
- **真实构造语义**（读安装版 `docling/document_converter.py:218-290`）：构造器无全局 `pipeline_options` 参数；`format_to_options` 恰好按 `allowed_formats` 逐项构造——PDF 用本产品自定义 `PdfFormatOption`，其余 8 个格式取 docling 默认 option（`_get_default_option`），构造期不加载模型；`convert()` 在 `in_doc.format ∉ allowed_formats` 时拒绝。
- **fallback/PDF options 无回退**：二维尝试链、`PdfFormatOption`、输入流重建、首因/末因逻辑与 base 完全一致；既有 13 条 regression 测试原样通过。
- **验证声称全部复现**：`20 passed in 2.52s`（artifact 声称 2.46s）；pyright 两文件 `0 errors, 0 warnings`；coverage 复现 `214/25/88%`、`173/1/99%` 与 artifact 数字逐行一致；ruff `All checks passed!`、black 无改动、`git diff --check` 通过；两文件内无 `Any/object/hasattr/getattr`。
- **Scope 干净**：相对 base 仅三个授权文件变更，无 README/registry/evidence 改动。

## Findings

### 1-未修复-低-`primary_suffixes`/`accepts_primary_suffix` 命名把 Fins 的 primary 角色语义烙进 Documents 层 capability owner
- **入口/函数**: `DoclingConverterCapability.primary_suffixes` / `accepts_primary_suffix`
- **文件(行号)**: `dayu/documents/docling_runtime.py:185-198, 200-213`
- **输入场景**: Slice 2 落地后，material 全转换 selection 与 batch admission 按 plan §5.2/§6.2 消费同一投影；material 文件没有 primary 概念。
- **实际分支**: 无运行时分支差异——问题是命名层，不是行为层。
- **预期行为**: Documents 层 capability 应暴露角色中立的「产品 converter suffix」投影；primary/companion 角色语义由 Fins 层（`FinsUploadFormatCapability`）叠加。
- **实际行为**: 角色中立投影被命名为 `primary_suffixes`，判定方法名为 `accepts_primary_suffix`，docstring 自称「产品 primary 扩展名」；plan §5.2 又规定 material admission 复用同一投影，造成「material 用 primary 判定」的语义误导。
- **直接证据**: plan §5.2「material 格式 admission 与全转换 selection……用 converter product suffix 子集校验」与 §4 owner 表（primary 角色 owner 是 `dayu.fins.upload_format_contract`）；plan §5.1 明确「最终命名可在不改变语义的前提下调整」，即改名在 accepted plan 授权范围内。
- **影响**: 仅维护性与语义误导，无运行时错误；Slice 2 consumer 绑定该名字后改造成本上升。
- **建议改法和验证点**: 在 Slice 2 绑定 consumer 前改为角色中立命名（如 `product_suffixes` / `accepts_product_suffix`）；改名后重跑 `tests/documents/test_docling_runtime.py` 与 pyright，同步实现 artifact。属建议项，不阻塞本 slice。
- **修复风险（低）**:
- **严重程度（低）**:

### 2-未修复-低-owner fail-fast 第三分支与全部声明不变量 ValueError 分支无测试
- **入口/函数**: `_resolve_docling_allowed_formats`、`_normalize_docling_product_suffix`、两个 capability dataclass 的 `__post_init__`
- **文件(行号)**: `dayu/documents/docling_runtime.py:379-384`（`FormatToExtensions[input_format]` KeyError 分支，miss 381-382）；`86, 90, 123, 125, 128, 130, 160, 163, 166`（normalizer 与 dataclass 不变量 ValueError 分支，均为 coverage miss）
- **输入场景**: 第三方删除整个 `FormatToExtensions` 映射项（与「删除单个 suffix」不同，现有测试只覆盖后者）；或未来有人修改冻结字面量引入空声明、未规范化 suffix、重复 suffix/format id。
- **实际分支**: 三条 typed fail-fast 分支中，「format id 缺失」与「产品 suffix 缺失」各有一条参数化测试；「映射项整体缺失」分支和所有声明不变量校验分支未被执行。
- **预期行为**: plan Slice 1 的 stop condition 要求「任一冻结 format id 或 suffix 无法由当前安装元数据证明」即 typed fail-fast；该契约的三个触发分支都应被 owner test 钉住。
- **实际行为**: 映射项缺失分支已实现 typed error 但零测试；dataclass/normalizer 的声明不变量同样零测试（仅靠模块级冻结字面量的现状隐式正确）。
- **直接证据**: `coverage report --show-missing` 复现 artifact 的 88%（25 miss），miss 行 86/90/123/125/128/130/160/163/166/381-382 全部落在本 slice 新增代码内。
- **影响**: 仅测试缺口，无运行缺陷；88% ≥ 80% 目标已满足，不阻塞。
- **建议改法和验证点**: 在现有参数化测试中补「映射项整体缺失」一例（monkeypatch 删除 `FormatToExtensions` 对应键），并各补一条 dataclass 空声明/重复声明与 normalizer 空输入的 ValueError 断言；补后重跑 coverage 确认 miss 收敛。
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

1. **`accepts_primary_suffix` 对空输入的契约（Slice 2 前必须裁决）**：该方法对空/纯点输入抛 `ValueError`（`docling_runtime.py:213` → `:84-90`）。plan §6.2 规定 batch 直接消费该 API，而现有 batch 传入的是 `Path.suffix`（`dayu/fins/upload_batch.py:436`）——对 `.DS_Store` 等 dotfile 或结尾带点的文件，`Path.suffix` 为 `""`，现有 `"" not in allow-list` 语义是安全 skip（`upload_batch.py:441` 甚至用 `suffix or '<none>'` 展示空 suffix，说明空 suffix 是已承认的常态输入）。若 Slice 2 原样替换为 `accepts_primary_suffix(path.suffix)`，目录含 dotfile 时 batch 扫描将抛 ValueError 崩溃。建议：本 API 对空输入返回 `False`（admission predicate 应对 str 全定义），或 Slice 2 consumer 显式前置空值 guard；必须在 Slice 2 实现前由 Controller 裁决其一。
2. **非 PDF 格式的 pipeline options 语义（Slice 2/3 前必须裁决）**：capability 声明 9 个格式进入 `allowed_formats`，但构造器只为 PDF 提供自定义 option；其余 8 个格式按 docling 2.90.0 源码（`document_converter.py:285-290`）取 docling 默认 option——`do_ocr/do_table_structure/table_mode/device_name` 对它们一律不生效。Slice 1 无影响（转换路径仍只走 PDF），但 Slice 2/3 一旦接纳 DOCX/PPTX/XLSX 等 primary/material，其 pipeline 行为由 docling 默认值隐式拥有，既未声明也未钉死。需明确：非 PDF pipeline options 的 owner 是 docling 默认值（并补测试钉住）还是 dayu 受控配置。

## Residual Risk

- **Slices 间三源并存（plan 已排序，非本 slice 缺陷）**：Slice 2 落地前，仓库同时存在新 capability（13 suffix）、`FINS_UPLOAD_FILE_SUFFIXES`（14 项，含 `.xls/.zip`、缺 `.pptx`）与 `SUPPORTED_UPLOAD_SUFFIXES`；在此期间任何新消费者不得绑定旧 allow-list。
- **子进程 no-import 测试的路径依赖**：`test_static_capability_projection_does_not_import_docling` 依赖子进程经 cwd 或 editable install 解析 `dayu`；在非仓库根目录运行 pytest 且未安装包时可能误报。现有运行约定下稳定，无行为风险。
- **第三方畸形映射项的异常类型**：若未来 docling 在 `FormatToExtensions` 中携带空串等畸形项，`_resolve_docling_allowed_formats` 会以裸 `ValueError` 逃出（而非 typed `DoclingRuntimeInitializationError`）；需要 docling 自身缺陷才触发，错误信息仍有界，且经 `_build_attempt_converter` 会被包装为 typed error。属低概率投机性风险，不要求修复。

## 结论

**pass-with-risks**。

无 correctness/stability 缺陷、无必须当前修复的 blocking finding。两个 low finding 均为建议项（命名调整建议在 Slice 2 绑定前执行；测试缺口不阻塞）。两个 Open Question 必须在 Slice 2 开工前由 Controller 裁决，否则后续 slice 有引入 batch 崩溃（O1）与非 PDF 转换语义失控（O2）的真实风险。artifact 中所有验证数字（20 passed、pyright 0、coverage 88%/99%）均已独立复现。
