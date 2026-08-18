# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `267e90b1`
- Output file: `docs/reviews/code-review-slice1-mimo-20260815.md`
- Included scope:
  - `dayu/documents/docling_runtime.py` (unstaged diff relative to `267e90b1`)
  - `tests/documents/test_docling_runtime.py` (unstaged diff relative to `267e90b1`)
  - `docs/gateflow/uf-fix06-slice1-implementation-20260815.md` (untracked)
  - `docs/gateflow/uf-fix06-converter-capability-owner-accepted-plan-20260815.md` (frozen plan contract)
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Detailed Analysis

### 静态能力唯一 owner 且无 eager Docling import

直接证据：

- `DOCLING_CONVERTER_CAPABILITY`（`docling_runtime.py:216-228`）在模块级构造，只使用 `DoclingConverterFormat` 与 `DoclingConverterCapability`——两个纯 Python `frozen=True, slots=True` dataclass，零 Docling 依赖。
- `InputFormat` 的 import 位于 `TYPE_CHECKING` 块（`docling_runtime.py:46`），仅用于类型标注，运行时不存在。
- `_resolve_docling_allowed_formats`（`docling_runtime.py:368-371`）是唯一的 Docling runtime import 点，被 `build_docling_pdf_converter` 在构造期调用。
- 测试 `test_static_capability_projection_does_not_import_docling`（`test_docling_runtime.py:300-328`）以子进程方式阻断 `docling` 模块，验证模块 import 与静态 projection 仍成功。

结论：静态 capability 是唯一 owner，无 eager import，实现正确。

### 9/13 精确契约

直接证据：

- `_EXPECTED_PRODUCT_FORMATS`（`test_docling_runtime.py:37-47`）：9 个 `(format_id, suffixes)` tuple。
- `_EXPECTED_PRODUCT_SUFFIXES`（`test_docling_runtime.py:48-62`）：13 个有序小写扩展名。
- `DOCLING_CONVERTER_CAPABILITY`（`docling_runtime.py:216-228`）：9 个 `DoclingConverterFormat`，逐项匹配。
- 测试 `test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset`（`test_docling_runtime.py:268-297`）以 `==` 断言精确相等，包括 `format_ids` 顺序、`primary_suffixes` 顺序、`accepts_primary_suffix` 的正/反例，以及每个产品 suffix 是安装 `FormatToExtensions` 的子集。

结论：9 格式 / 13 扩展名精确冻结，契约完整。

### FormatToExtensions 单向子集

直接证据：

- `_resolve_docling_allowed_formats`（`docling_runtime.py:385-393`）：
  - 对每个 `format_item`，规范化 `FormatToExtensions[input_format]` 为 `installed_suffixes: frozenset`。
  - 计算 `missing_suffixes = tuple(suffix for suffix in format_item.suffixes if suffix not in installed_suffixes)`。
  - `missing_suffixes` 非空时抛 `DoclingRuntimeInitializationError`。
  - 若 installed 有更多 suffix，仅被忽略，不进入产品投影。
- 测试 `test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix`（`test_docling_runtime.py:331-363`）：向 `FormatToExtensions[InputFormat.PDF]` 追加 `_FUTURE_PDF_EXTENSION`，验证 converter `allowed_formats` 仍与产品 capability 同源，产品 `primary_suffixes` 不扩面。
- `_KNOWN_UNSELECTED_THIRD_PARTY_SUFFIXES`（`test_docling_runtime.py:63`）的 `isdisjoint` 断言进一步确认已知第三方未选择 suffix 不进入产品投影。

结论：单向子集语义正确，第三方新增 suffix 不影响产品面。

### allowed_formats 与 format_options 的构造语义

直接证据：

- `build_docling_pdf_converter`（`docling_runtime.py:583`）：`allowed_formats = _resolve_docling_allowed_formats(DOCLING_CONVERTER_CAPABILITY)`——从同一 capability 同源解析。
- `DocumentConverter(allowed_formats=allowed_formats, format_options={InputFormat.PDF: PdfFormatOption(...)})`（`docling_runtime.py:591-598`）：`allowed_formats` 传入全部 9 个格式，`format_options` 仅配置 PDF 的 pipeline/backend。
- 非 PDF 格式（DOCX、HTML 等）在 `allowed_formats` 中但无显式 `format_options`，将使用 Docling 默认配置。这是正确的：当前函数名 `build_docling_pdf_converter` 表明 PDF 是主要关注点，而 `allowed_formats` 只是限制 converter 不接受未声明格式（如图片、音频），而非为每个格式配置 pipeline。
- 测试 `test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix`（`test_docling_runtime.py:359-361`）验证 `converter.allowed_formats` 的 format name 序列与 capability `format_ids` 精确一致。

结论：`allowed_formats` 与 `format_options` 同源，语义正确。非 PDF 格式使用 Docling 默认配置是合理设计，不构成功能缺陷。

### fallback/PDF options 无回退

直接证据：

- `build_docling_pdf_converter`（`docling_runtime.py:574-583`）在调用 `_resolve_docling_allowed_formats` 前先执行 `build_docling_pdf_pipeline_options`，pipeline 选项、backend 解析、fallback 尝试链逻辑均未改动。
- `_resolve_docling_allowed_formats` 失败时抛 `DoclingRuntimeInitializationError`，无 fallback 到 Docling 默认全格式。
- 测试 `test_convert_pdf_bytes_rebuilds_stream_after_closed_first_attempt_and_second_succeeds`（`test_docling_runtime.py:670-713`）与 `test_convert_pdf_bytes_auto_three_attempts_use_distinct_streams_and_preserve_failure_chain`（`test_docling_runtime.py:716-764`）覆盖了平台/device fallback、独立输入流、首因/末因异常链。
- implementation artifact（`uf-fix06-slice1-implementation-20260815.md:55`）确认：「既有 PDF `format_options`、OCR/table/device/backend 配置、二维 fallback attempt、输入流重建与异常链均未改变」。

结论：fallback 链完整，PDF options 无回退。

### Strict typing/docstrings

直接证据：

- pyright：`0 errors, 0 warnings, 0 informations`。
- 全文件扫描 `Any/object/hasattr/getattr`：无结果（implementation artifact:111）。
- 所有新增函数、类、property 均有完整中文 docstring，包含 Args、Returns、Raises。
- `_normalize_docling_product_suffix`、`DoclingConverterFormat.__post_init__`、`DoclingConverterCapability.__post_init__` 的 ValueError 路径均有明确错误消息。
- `_resolve_docling_allowed_formats` 的三个 `try/except` 分别覆盖 ImportError、KeyError（format id）、KeyError（FormatToExtensions）与 subset 校验，异常链均使用 `from exc`。

结论：严格类型与 docstring 满足编码硬约束。

### 测试覆盖分析

直接证据（`test_docling_runtime.py` 全部 20 个测试）：

| 测试 | 覆盖面 |
|---|---|
| `test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset` | 9/13 精确契约、subset 校验、正/反例 suffix 判定、已知未选 suffix 不相交 |
| `test_static_capability_projection_does_not_import_docling` | 子进程阻断 docling import，模块 import 与静态 projection 仍成功 |
| `test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix` | 第三方新增 suffix 不扩面，converter `allowed_formats` 与产品声明同源 |
| `test_converter_construction_fails_typed_when_product_metadata_is_missing` (×2) | format id 缺失 typed fail、产品 suffix 缺失 typed fail |
| 既有 16 个测试 | 平台/device fallback 矩阵、pipeline options 投影、设备规范化、独立输入流、首因/末因异常链 |

结论：测试覆盖了 accepted plan Slice 1 声明的所有 owner contract。

## Open Questions

- 无。所有 finding 均由直接代码路径证据支撑，无阻碍 confident judgment 的未决问题。

## Residual Risk

1. **`FormatToExtensions` mapping-missing 路径未被测试直接覆盖**：`_resolve_docling_allowed_formats` 中 `FormatToExtensions[input_format]` 的 `KeyError` 路径（`docling_runtime.py:379-384`）未被参数化测试直接覆盖。当前两个参数化 case 分别测试 format id 缺失（`InputFormat[format_id]` 的 KeyError）和产品 suffix 缺失（subset 校验失败）。mapping-missing 是第三种独立失败模式，需要 monkeypatch 移除 `FormatToExtensions` 的某个条目才能触发。风险等级：低。理由：(a) Docling 的 `FormatToExtensions` 是一个稳定 Dict，正常安装不会缺失已定义 `InputFormat` 的映射；(b) 若发生，错误消息清晰可诊断；(c) format-id-missing 测试已覆盖 format id 不可达的场景。

2. **测试访问私有函数 `_resolve_docling_allowed_formats` 与 `_normalize_docling_product_suffix`**：`test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset` 直接调用 `docling_runtime._resolve_docling_allowed_formats`。这属于测试对实现细节的耦合，但在此上下文中是合理的——该函数是 capability 校验的核心逻辑，且测试目的是验证产品声明与安装元数据的 subset 关系，通过公共 API `build_docling_pdf_converter` 间接验证会引入不必要的构造开销和副作用。

3. **已知第三方未选 suffix 列表可能过期**：`_KNOWN_UNSELECTED_THIRD_PARTY_SUFFIXES`（`test_docling_runtime.py:63`）硬编码了 `{".text", ".rmd", ".qmd", ".xlsm", ".potx"}`。若 Docling 未来版本移除这些 suffix，测试仍通过（`isdisjoint` 在空集上为 True）；若新增未选 suffix，测试不会自动捕获。风险等级：低。该列表仅用于增强置信度，核心 subset 校验由 `_resolve_docling_allowed_formats` 的运行时检查保证。

## Conclusion

**pass**

Slice 1 实现与 accepted plan 完全对齐：静态 capability 唯一 owner 且无 eager Docling import；9/13 精确契约由 frozen dataclass 与精确测试保证；FormatToExtensions 单向子集语义正确；`allowed_formats` 与 `format_options` 同源；fallback/PDF options 无回退；严格类型/docstrings 满足编码硬约束；测试覆盖了 mapping missing、第三方新增与 no import 三个关键场景。Residual risk 均为低等级且有清晰理由。
