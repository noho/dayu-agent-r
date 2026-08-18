# Code Re-Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `267e90b1`
- Output file: `docs/reviews/code-re-review-slice1-mimo-20260815.md`
- Included scope:
  - `dayu/documents/docling_runtime.py`（完整 re-read）
  - `tests/documents/test_docling_runtime.py`（完整 re-read）
  - `docs/reviews/uf-fix06-slice1-code-review-adjudication-20260815.md`（Controller 裁决）
  - `docs/gateflow/uf-fix06-slice1-code-fix-20260815.md`（fix artifact）
  - `docs/gateflow/uf-fix06-slice1-implementation-20260815.md`（implementation artifact）
  - `docs/reviews/code-review-slice1-mimo-20260815.md`（初轮 MiMo review）
  - `docs/reviews/code-review-slice1-ds-20260815.md`（初轮 DS review）
- Excluded scope: 无
- Parallel review coverage: 无

## 验证范围

本次 re-review 只验证 Controller 裁决的四个 finding 是否完全修复、初轮 review 确认的正确性是否无回退；不扩大 later slice。

## Finding 状态验证

### F1：`primary_suffixes` / `accepts_primary_suffix` 命名改为角色中立

**裁决要求**：改为 `product_suffixes` / `accepts_product_suffix`，不得保留 alias/re-export。

**直接证据**：

- `docling_runtime.py:185`：property 名为 `product_suffixes`，docstring「投影稳定有序且去重的产品转换扩展名」——角色中立。
- `docling_runtime.py:200`：方法名为 `accepts_product_suffix`，docstring「判断候选扩展名是否属于产品转换能力」——角色中立。
- `test_docling_runtime.py:290-292`：测试断言 `capability.product_suffixes` 和 `capability.accepts_product_suffix(...)`。
- `grep -rn 'primary_suffixes\|accepts_primary_suffix' dayu/ tests/`：**无结果**。production、test、implementation artifact 内均无旧名残留。
- `test_docling_runtime.py:379`：子进程 no-import 测试打印 `DOCLING_CONVERTER_CAPABILITY.product_suffixes`——使用新名。

**结论**：F1 **已修复**。命名完全改为角色中立，无 alias、re-export 或 wrapper。

### F2：`FormatToExtensions` 整项缺失 typed fail-fast + 声明不变量测试

**裁决要求**：补齐 `FormatToExtensions` 整项缺失 typed fail-fast owner test；补空 suffix/空 formats/重复 format id/跨格式重复 suffix 四项最小声明不变量测试。

**直接证据**：

- `test_docling_runtime.py:438-463`：`test_converter_construction_fails_typed_when_format_extension_mapping_is_missing`——`monkeypatch.delitem(FormatToExtensions, InputFormat.PDF)` 后断言 `DoclingRuntimeInitializationError` 匹配「缺少产品格式 'PDF' 的扩展名映射」。这是初轮 review 缺失的第三分支（mapping 整项缺失），区别于已有的 format-id-missing 和 product-suffix-missing。
- `test_docling_runtime.py:326-359`：`test_product_capability_rejects_minimal_invalid_declarations`——四条 `pytest.raises(ValueError)` 断言：
  1. 空 suffix：`DoclingConverterFormat(format_id="PDF", suffixes=("",))` → 「扩展名不能为空」
  2. 空 formats：`DoclingConverterCapability(formats=())` → 「至少声明一个格式」
  3. 重复 format id：两个 `format_id="PDF"` → 「重复格式标识」
  4. 跨格式重复 suffix：两个格式共享 `.shared` → 「跨格式声明重复扩展名」

**结论**：F2 **已修复**。三个 fail-fast 分支全部有测试覆盖；四类声明不变量全部有测试覆盖。

### O1：`accepts_product_suffix` 对空串/空白/`.` 返回 `False`

**裁决要求**：admission predicate 对任意 `str` 全定义；空串、空白、`.` 均返回 `False`，不得抛 `ValueError`。补等价输入测试。

**直接证据**：

- `docling_runtime.py:214-217`：`accepts_product_suffix` 实现：
  ```python
  normalized_candidate = suffix.strip().lower()
  if not normalized_candidate or normalized_candidate == ".":
      return False
  return _normalize_docling_product_suffix(normalized_candidate) in self.product_suffixes
  ```
  空串/空白 → `not normalized_candidate` → `False`；`.` → `normalized_candidate == "."` → `False`。**不调用** `_normalize_docling_product_suffix`，因此不会触发其 `ValueError`。
- `test_docling_runtime.py:303-323`：`test_product_suffix_predicate_returns_false_for_inputs_without_effective_suffix`——6 个参数化 case：
  1. `""`（empty）
  2. `"   "`（blank）
  3. `"."`（dot）
  4. `" \t.\n"`（padded-dot）
  5. `Path("README").suffix`（no-suffix，值为 `""`）
  6. `Path(".DS_Store").suffix`（dotfile，值为 `""`）

  全部断言 `accepts_product_suffix(candidate) is False`。

**结论**：O1 **已修复**。predicate 对所有无有效 suffix 的输入安全返回 `False`，不抛异常。测试覆盖了裁决要求的所有等价类。

### O2：非 PDF 格式使用 Docling constructor 默认 options + docstring + 真实 converter 测试

**裁决要求**：docstring/注释明确意图；owner test 断言真实 converter 的 `format_to_options` keys 覆盖且只覆盖 `allowed_formats`；PDF 继续使用 Dayu 自定义 option。

**直接证据**：

- `docling_runtime.py:562-564`：`build_docling_pdf_converter` docstring 新增：
  > Dayu 只为 PDF 注入受控的 pipeline 与 backend 配置。其余允许格式不在本函数中
  > 重建第三方默认配置，而由 Docling DocumentConverter constructor 按
  > allowed_formats 生成当前版本的默认 format options。
- `docling_runtime.py:599`：行内注释：
  > 非 PDF 格式故意不传 option：默认值由 Docling constructor 拥有，Dayu 不复制第三方默认表。
- `test_docling_runtime.py:421-435`：`test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix` 断言：
  - `converter.allowed_formats` format name 序列与 capability `format_ids` 精确一致（line 421-423）
  - `tuple(converter.format_to_options) == tuple(converter.allowed_formats)`——keys 精确覆盖（line 424）
  - `converter.format_to_options[InputFormat.PDF]` 是 `PdfFormatOption`（line 425-426）
  - PDF pipeline 使用 `DoclingParseDocumentBackend`（line 429）
  - `do_ocr is False`、`do_table_structure is False`（line 430-431）
  - `AcceleratorDevice.CPU`（line 433）

**结论**：O2 **已修复**。意图注释/docstring 已补齐；真实 converter 测试断言 `format_to_options` keys 与 `allowed_formats` 精确相等；PDF 仍使用 Dayu 自定义配置。未复制第三方默认表。

## 正确性回退检查

| 检查项 | 结果 |
|---|---|
| 9/13 冻结契约精确相等 | `test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset` 通过 |
| FormatToExtensions 单向子集 | 同上测试中 `issubset` 断言通过 |
| allowed_formats 同源构造 | `test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix` 通过 |
| 子进程 no-import | `test_static_capability_projection_does_not_import_docling` 通过 |
| 平台/device fallback 矩阵 | `test_plan_conversion_attempts_preserves_platform_and_device_order` 5 个 case 通过 |
| PDF pipeline options 投影 | `test_build_docling_pdf_pipeline_options_projects_supported_settings` 3 个 case 通过 |
| 设备规范化 | `test_resolve_docling_device_name_uses_default_and_canonicalizes_environment` 3 个 case 通过 |
| 非法设备拒绝 | `test_resolve_docling_device_name_rejects_unsupported_environment` 通过 |
| 首档失败 + 第二档独立流 | `test_convert_pdf_bytes_rebuilds_stream_after_closed_first_attempt_and_second_succeeds` 通过 |
| auto 三档独立流 + 首因/末因 | `test_convert_pdf_bytes_auto_three_attempts_use_distinct_streams_and_preserve_failure_chain` 通过 |
| 非法 table mode 拒绝 | `test_build_docling_pdf_pipeline_options_rejects_invalid_table_mode` 通过 |
| format-id-missing typed fail | `test_converter_construction_fails_typed_when_product_metadata_is_missing` format-id-missing case 通过 |
| product-suffix-missing typed fail | `test_converter_construction_fails_typed_when_product_metadata_is_missing` product-suffix-missing case 通过 |

全部 28 个测试通过，无回退。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行。

### Focused tests

```text
python -m pytest tests/documents/test_docling_runtime.py -q
............................                                             [100%]
28 passed in 2.50s
```

### Pyright

```text
python -m pyright dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py
0 errors, 0 warnings, 0 informations
```

### 旧名扫描

```text
grep -rn 'primary_suffixes\|accepts_primary_suffix' dayu/ tests/
NO MATCHES
```

## Open Questions

- 无。F1/F2/O1/O2 均由直接代码路径证据支撑完整修复，无阻碍 confident judgment 的未决问题。

## Residual Risk

与初轮 review 相同的低 residual risk，无新增：

1. **`FormatToExtensions` mapping-missing 测试依赖 monkeypatch**：`test_converter_construction_fails_typed_when_format_extension_mapping_is_missing` 通过 `monkeypatch.delitem` 触发；正常安装不会缺失已定义 `InputFormat` 的映射。风险等级：低。
2. **已知第三方未选 suffix 列表可能过期**：`_KNOWN_UNSELECTED_THIRD_PARTY_SUFFIXES` 硬编码。核心 subset 校验由运行时检查保证。风险等级：低。
3. **later slices 尚未删除旧 allow-list**：属 accepted plan 排序，非本 slice 缺陷。

## Conclusion

**pass**

F1（角色中立命名）、F2（mapping 整项缺失 + 声明不变量测试）、O1（admission predicate 全定义）、O2（意图注释 + 真实 converter format_to_options 断言）均已完整修复，由直接代码路径证据支撑。初轮 review 确认的 13 条既有正确性断言全部通过，无回退。28 passed、pyright 0 errors、旧名扫描无残留。
