# Code Re-Review（UF-FIX06 Slice 1）

## Scope

- Mode: current changes re-review（只验证 Controller 裁决的 F1/F2/O1/O2 修复状态与既有正确性无回退，不扩大 later slice）
- Branch: `codex/upload-filing-oracle`
- Base: `267e90b1`（gateflow: accept UF-FIX06 implementation plan，与初轮 review 相同）
- Output file: `docs/reviews/code-re-review-slice1-ds-20260815.md`
- Included scope:
  - `dayu/documents/docling_runtime.py`（相对 base 的完整 diff 与全文走读）
  - `tests/documents/test_docling_runtime.py`（相对 base 的完整 diff 与全文走读）
  - `docs/gateflow/uf-fix06-slice1-code-fix-20260815.md`（fix 声称与 finding 状态）
  - `docs/gateflow/uf-fix06-slice1-implementation-20260815.md`（同步后的实现契约）
- Excluded scope: 无（未复核 accepted plan §5.1 冻结契约与 plan 对齐——初轮已通过，本轮范围只含裁决项）
- Parallel review coverage: 无
- Review 时间：2026-08-15 15:12 CST
- 输入：初轮 `code-review-slice1-ds`（pass-with-risks，F1/F2/O1/O2 来源）、`code-review-slice1-mimo`（pass）、Controller 裁决 `uf-fix06-slice1-code-review-adjudication-20260815.md`（CODE FIX REQUIRED）

### 复跑验证结果（均在 `source .venv/bin/activate` 后，coverage data 写入 `mktemp -d` 临时目录）

- `pytest tests/documents/test_docling_runtime.py -q`：`28 passed in 2.45s`（fix artifact 声称 2.57s，同 28 条）
- pyright 两文件：`0 errors, 0 warnings, 0 informations`
- 逐文件 coverage：`docling_runtime.py 217/19/91%`、`test_docling_runtime.py 202/1/99%`、`TOTAL 419/20/95%`，与 fix artifact 数字逐行一致
- ruff：`All checks passed!`；black --check：两文件保持不变；`git diff --check`：通过
- 旧名扫描：production/test/implementation artifact 内 `primary_suffixes` / `accepts_primary_suffix` 无结果（唯一命中是 code-fix artifact 自身的扫描记录行）
- Scope：相对 base 仅两个 code/test 文件修改 + implementation/code-fix 两个 artifact 新增；初轮三份输入未改；未 commit

## 裁决项核验（F1/F2/O1/O2）

### F1 — `primary_suffixes`/`accepts_primary_suffix` 改名：已修复

- 直接证据：`docling_runtime.py:185` 唯一公开投影为 `product_suffixes`（docstring「投影稳定有序且去重的产品转换扩展名」），`docling_runtime.py:200` 判定方法为 `accepts_product_suffix`，均无角色语义；`docling_runtime.py:1-11` 模块 docstring 以「产品允许的输入格式与扩展名」表述，不再自称「产品 primary 扩展名」。
- 无兼容 alias/re-export/wrapper：全仓扫描（production/test/两 artifact）仅 code-fix artifact 的扫描记录行出现旧名，代码与测试零命中。
- 测试同步：`test_docling_runtime.py:290-292` 以 `product_suffixes`/`accepts_product_suffix` 断言；implementation artifact §Implementation decisions 第 2 条声明「未保留 primary 兼容 alias」。

### F2 — 整项 mapping 缺失 typed fail-fast 测试 + 最小声明不变量测试：已修复

- 整项缺失分支：生产 `docling_runtime.py:383-388`（`FormatToExtensions[input_format]` KeyError → `DoclingRuntimeInitializationError("Docling 缺少产品格式 … 的扩展名映射")`）；owner 测试 `test_docling_runtime.py:438-463` 以 `monkeypatch.delitem(FormatToExtensions, InputFormat.PDF)` 走真实 `build_docling_pdf_converter` constructor path 断言 typed error 与稳定消息。初轮 coverage miss `381-382` 现已覆盖。
- 四项最小声明不变量：`test_docling_runtime.py:326-359` 分别断言空 suffix（`suffixes=("",)` → `docling_runtime.py:86`）、空 formats（`formats=()` → `:160`）、重复 format id（`:163`）、跨格式重复 suffix（`:166`）均抛 `ValueError`。初轮 miss 的 `86/160/163/166` 现已覆盖。
- coverage 收敛：初轮 miss `86/90/123/125/128/130/160/163/166/381-382` 中 `86/160/163/166/381-382` 已覆盖；剩余 `90/123/125/128/130` 属同一声明不变量家族的等价分支（纯点 suffix、空 format_id、零 suffix tuple、未规范化、格式内重复），裁决明确「无需为每个等价 ValueError 分支堆机械 case」，不构成 F2 未修复。逐文件 coverage 91%/99% ≥ 80%。

### O1 — admission predicate 对任意 `str` 全定义：已修复

- 生产证据：`docling_runtime.py:214-217` 先 `strip().lower()`，空串或 `"."` 直接返回 `False`，再调用 `_normalize_docling_product_suffix`。normalizer 仅有的两个 `ValueError` 分支（`:86` 空串、`:90` 纯点）均被前置短路覆盖——纯点已被 `== "."` 拦下，非空非点输入规范化后要么带点返回、要么补前缀后至少两字符，不可能再触发 raise。因此 predicate 对任意 `str` 输入不可能抛 `ValueError`（类型边界仍为 `str`，`None` 属类型错误而非契约输入）。
- 严格 normalizer 保留：`_normalize_docling_product_suffix`（`:71-91`）对空串/纯点的 `ValueError` 未放宽，声明侧 fail-fast 语义不变，符合裁决「严格 normalization helper 仍可对非法声明抛 ValueError」。
- 等价输入测试：`test_docling_runtime.py:303-323` 参数化覆盖 `""`、`"   "`、`"."`、`" \t.\n"`、`Path("README").suffix`（无 suffix）、`Path(".DS_Store").suffix`（dotfile）六类，全部断言 `is False`，且断言使用 `is False` 而非真值比较，不会把非布尔值当通过。

### O2 — 非 PDF 默认 format options 语义显式化 + 真实构造器断言：已修复

- 生产语义注释：`docling_runtime.py:562-564` docstring 明确「Dayu 只为 PDF 注入受控的 pipeline 与 backend 配置。其余允许格式……由 Docling constructor 按 allowed_formats 生成当前版本的默认 format options」；`docling_runtime.py:599` 行内注释「非 PDF 格式故意不传 option：默认值由 Docling constructor 拥有，Dayu 不复制第三方默认表」。构造调用只传 `format_options={InputFormat.PDF: PdfFormatOption(...)}`（`:600-608`），未复制或重建任何第三方默认 option 表。
- owner 测试：`test_docling_runtime.py:424` 对真实构造的 `DocumentConverter` 断言 `tuple(converter.format_to_options) == tuple(converter.allowed_formats)`——双向精确相等，同时满足「覆盖且只覆盖」；`:425-433` 断言 PDF 项为 `PdfFormatOption`、backend 为 `DoclingParseDocumentBackend`、`do_ocr`/`do_table_structure` 投影 Dayu 传入值、device 为 `AcceleratorDevice.CPU`。既有 PDF option 投影测试（`:611-711`）与回退/流测试原样通过，PDF option 无回退。

## 正确性无回退核验

- 回退链与流语义：`_plan_conversion_attempts`（`docling_runtime.py:497-548`）、`run_docling_pdf_conversion`（`:720-812`）、`_build_docling_document_stream`/`convert_pdf_bytes_with_docling`（`:815-878`）相对 base 零改动（diff 仅触及模块 docstring、新增 capability 段与 `build_docling_pdf_converter` 尾部）。既有尝试顺序矩阵、独立流重建、首因/末因 identity 测试全部原样通过。
- `build_docling_pdf_converter` 新增行为：构造前调用 `_resolve_docling_allowed_formats`（`:591`），typed 失败时不回退 Docling 默认全格式（无 try/except 吞异常路径）；三个 typed 失败分支均有 owner 测试走真实 constructor path。此前 DS review 确认的「fallback/PDF options 无回退」依旧成立。
- 初轮全部验证数字独立复现，测试无削弱（diff 相对 base 仅新增，无删除或放宽断言）。

## Findings

未发现实质性问题。F1/F2/O1/O2 全部修复，既有正确性无回退。

## Open Questions

无。

## Residual Risk

- 声明不变量等价分支无逐条测试：`docling_runtime.py:90`（纯点声明）、`:123`（空 format_id）、`:125`（零 suffix tuple）、`:128`（未规范化声明）、`:130`（格式内重复 suffix）仍为 coverage miss。裁决已授权不机械堆 case；每类不变量均至少有一个代表测试，且这些分支仅由未来人工修改冻结字面量触发，风险低。
- 子进程 no-import 测试的 cwd 路径依赖：`test_docling_runtime.py:362-390` 依赖子进程经 cwd/editable install 解析 `dayu`，非仓库根目录运行且未安装包时可能误报。既有运行约定下稳定，初轮已记录，无行为风险。
- 第三方畸形 mapping 值（如空串）可能先产生裸 `ValueError`：Controller 已裁决不接受为产品 finding，保留为低概率 residual，aggregate review 可再检查。
- 第三方未选择 suffix 硬编码列表（`test_docling_runtime.py:66`）可能随版本过期：`isdisjoint` 断言在列表失效时静默通过，仅失去增强置信度，核心 subset 校验仍由生产代码保证。Controller 已明确保留为低 residual。
- later slices 尚未删除旧 allow-list、9 格式真实转换矩阵与 137 条 full-real matrix 未运行：属 accepted plan 排序与 `UF-PF06`/`UF-PF12` 归属，不是 Slice 1 缺陷；本轮按用户要求未运行 PF。

## 结论

**pass**

F1/F2/O1/O2 四项裁决全部修复且各有直接代码/测试证据：F1 无旧名残留与兼容 alias；F2 整项 mapping 缺失 typed fail 测试与四项最小声明不变量测试齐备，初轮 miss 的 typed 分支已收敛；O1 predicate 对任意 `str` 全定义（严格 normalizer 抛错语义保留），六类等价输入测试钉死；O2 生产语义显式化且真实构造器断言 `format_to_options` keys 与 `allowed_formats` 双向精确相等、PDF 继续使用 Dayu 自定义 option。既有回退链、流重建与首因/末因行为零改动，28 条测试、两文件 pyright、逐文件 coverage（91%/99%）、ruff/black、`git diff --check` 全部复现通过，未发现新增回退或未修复 finding。
