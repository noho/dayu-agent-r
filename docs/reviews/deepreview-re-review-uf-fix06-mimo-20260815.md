# UF-FIX06 aggregate deepreview re-review（AgentMiMo）

## Scope

- Mode: current changes（re-review，仅核验 DS-F1/F2 修复）
- Branch: `codex/upload-filing-oracle`
- Base: `main`
- 修复基线：`f61ddb95`
- 裁决输入：`docs/reviews/uf-fix06-deepreview-adjudication-20260815.md`
- Code-fix artifact：`docs/gateflow/uf-fix06-deepreview-code-fix-20260815.md`
- Output file：`docs/reviews/deepreview-re-review-uf-fix06-mimo-20260815.md`
- Included scope：当前未提交 diff 中的四文件
  - `dayu/fins/upload_format_contract.py`
  - `dayu/cli/arg_parsing.py`
  - `tests/fins/test_upload_format_contract.py`
  - `tests/cli/test_arg_parsing.py`
- Excluded scope：其它 UF-FIX06 文件、registry/oracle/scenario/design/README、UF-FIX07/PF
- Parallel review coverage：无

## 结论

**PASS**。DS-F1 与 DS-F2 的 root cause 均已在 owner boundary 修复，无新 regression、无 semantic owner drift、无受保护范围越界。

## Findings

未发现实质性问题。

## 核验详情

### DS-F1：companion-only 文案硬编码 `.xsd` — 已修复

**Adjudication 要求**：`project_fins_upload_format_text()` 必须从 capability 机械生成 companion-only 文案，测试应断言投影随 contract 输入变化，而不是仅快照当前字面量。

**修复证据**：

1. **函数签名变更**（`upload_format_contract.py:549-551`）：`project_fins_upload_format_text()` 新增 `capability: FinsUploadFormatCapability` 参数，从单一 typed owner 消费，不再隐式读模块级常量。

2. **机械投影**（`upload_format_contract.py:565`）：`companion_only_suffixes = ", ".join(sorted(capability.companion_only_suffixes))`。文案字符串（lines 569-570）以 f-string 插入该变量，消除了 `.xsd` 字面量真源。

3. **模块级实例化**（`upload_format_contract.py:591-593`）：`FINS_UPLOAD_FORMAT_TEXT` 显式传入 `FINS_UPLOAD_FORMAT_CAPABILITY`，保持单一 owner 委托。

4. **动态行为测试**（`test_upload_format_contract.py:332-353`）：构造 `companion_only_suffixes=frozenset({".schema"})` 的替代 capability，断言投影包含 `.schema` 且不含 `.xsd`，直接证明文案随 contract 输入变化。

5. **既有快照测试**（`test_upload_format_contract.py:289`）：`expected_filing_text` 中的 `.xsd` 是对真实 capability（`frozenset({".xsd"})`）的正确预期，不是第二真源——与动态行为测试互补，一个验证当前值正确，一个验证响应性。

6. **`__all__` 导出**（`upload_format_contract.py:606`）：`project_fins_upload_format_text` 已在公共 API 导出，测试可直接导入。

**owner boundary 确认**：修复仅触及 `upload_format_contract.py` 的文本投影函数与对应测试，未修改 `FinsUploadFormatCapability` 定义、admission、converter、storage 或 failure contract。

### DS-F2：`upload_material --files` help 未消费 contract — 已修复

**Adjudication 要求**：新增或复用 material 专用投影字段，明确每个文件必须真实转换成功以及 create/update/delete 的文件空状态；CLI help 必须直接消费该字段，并增加入口测试。

**修复证据**：

1. **新增投影字段**（`upload_format_contract.py:545`）：`FinsUploadFormatTextProjection` 新增 `material_files: str`。

2. **自足文案生成**（`upload_format_contract.py:575-578`）：
   - `"auto/create/update 必须至少提供一个文件"` → 空状态约束
   - `"每个文件都必须使用转换器支持的后缀：{suffixes}"` → converter-required + 动态后缀
   - `"并逐个实际转换成功"` → 逐文件转换要求
   - `"后缀通过只表示具备转换资格，不保证文件内容转换成功"` → 准确边界
   - `"delete 不得提供文件"` → delete 空状态

3. **tool schema 机械复用**（`upload_format_contract.py:585`）：`upload_tool_files` 中 material 分支改为 `f"upload_kind=material 时，{material_files}"`，不再维护独立文案分支。

4. **CLI 消费**（`arg_parsing.py:952-956`）：`upload_material --files` 的 `help` 直接引用 `FINS_UPLOAD_FORMAT_TEXT.material_files`。

5. **CLI owner test**（`test_arg_parsing.py:418-451`）：
   - 断言 `files_action.help == FINS_UPLOAD_FORMAT_TEXT.material_files`（source 级同源校验）
   - 断言 help 文本包含六个业务语义片段（converter support、逐个转换成功、资格不承诺、delete 限制）

6. **tool schema 一致性**（`test_upload_format_contract.py:294-303,306,329`）：
   - `expected_material_text` 与 `material_files` 生成的文案一致
   - `expected_tool_text` 中 material 分支与 `material_files` 一致
   - `"逐个实际转换成功"` 断言从 `"逐个实际转换"` 更新为精确匹配新文案

**owner boundary 确认**：修复仅触及 `FinsUploadFormatTextProjection` 结构、文本投影函数、CLI 消费点与对应测试，未修改 admission 行为、tool schema 字段定义、runtime 或 failure contract。

### 变更一致性检查

- **四个文件均已修改且全部在 diff 中**：`upload_format_contract.py`、`arg_parsing.py`、`test_upload_format_contract.py`、`test_arg_parsing.py`。
- **未修改受保护范围**：registry、oracle、scenario、design、README、host/engine/runtime/config 未触及。
- **未引入新依赖或新 import**：测试文件仅新增 `FinsUploadFormatCapability` 和 `project_fins_upload_format_text` 的 import，均已在 `__all__` 导出。
- **pyright 零错误**：code-fix artifact 记录全量 `0 errors, 0 warnings, 0 informations`。
- **focused tests 全通过**：code-fix artifact 记录 `570 passed, 3 warnings`。

## Open Questions

无。

## Residual Risk

- `test_text_projection_is_self_contained_and_uses_exact_suffix_order`（line 289）仍硬编码 `.xsd` 作为 `expected_filing_text` 的一部分。这不是问题——它验证当前真实 capability 的投影正确性；但它不覆盖"capability 变化时 filing 文案自动更新"，该行为由 `test_text_projection_mechanically_consumes_companion_only_suffixes`（line 332）覆盖。两者互补，无需合并。
- `test_text_projection_mechanically_consumes_companion_only_suffixes` 仅验证 `filing_files`，未验证 `upload_tool_files` 中 companion-only 的变化。鉴于 `upload_tool_files` 直接拼接 `filing_files`（line 584），风险极低，但若要更严格可补充断言。
- `upload_format_contract.py:565` 使用 `sorted()` 确保 companion-only 后缀顺序确定，但 `capability.primary_suffixes`（tuple）未排序，直接 `", ".join()` 依赖 tuple 声明顺序。这不是本次修复引入的问题，且 `_PRIMARY_SUFFIXES` 测试已钉死顺序。

## Follow-up verdict

AgentDS 指出 `project_fins_upload_format_text()` 的 `Returns` docstring 未提及 material help。Controller 已将其从
`"CLI filing help 与 upload tool schema 共用的不可变文本投影。"` 改为
`"CLI filing/material help 与 upload tool schema 共用的不可变文本投影。"`（`upload_format_contract.py:558`）。

**核验结论：PASS 不变。** 理由：

- 纯 docstring 文字修正，无代码行为变更。
- 修正后文案准确反映 `FinsUploadFormatTextProjection` 的实际结构——该 dataclass 现含 `material_files` 字段，其产出已被 `arg_parsing.py:955` 的 `upload_material --files` help 直接消费。
- 不影响任何代码路径、测试断言、公共契约或受保护范围。
- 不引入新的 semantic owner drift、regression 或 architecture concern。
