# UF-FIX06 aggregate deepreview re-review（AgentDS）

## Scope

- Mode: current changes（仅 re-review UF-FIX06 aggregate accepted findings 修复）
- Branch: `codex/upload-filing-oracle`
- Base: `f61ddb95`（code-fix 文档声明的修复基线，未提交 diff 相对当前 HEAD）
- 裁决输入：`docs/reviews/uf-fix06-deepreview-adjudication-20260815.md`
- 修复说明输入：`docs/gateflow/uf-fix06-deepreview-code-fix-20260815.md`
- Included scope：仅本 work unit 两项 accepted finding（DS-F1、DS-F2）的 owner-boundary 修复，
  即 `dayu/fins/upload_format_contract.py`、`dayu/cli/arg_parsing.py`、
  `tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py` 未提交四文件 diff。
- Excluded scope：MiMo-F1（DEFERRED）、MiMo-F2/F3（rejected-with-reason）裁决维持不变；
  runtime admission、workflow、converter、storage、failure contract、registry、oracle、scenario、
  design 文档不属于本次 re-review；UF-FIX07 及 UF-PF06/UF-PF12 继续 deferred。
- Parallel review coverage: 无，单人逐行复核。

## Findings

未发现实质性问题。

核验结论（逐条对照裁决要求）：

### DS-F1：companion-only 文案硬编码 `.xsd` — 已从 owner boundary 修复

- `project_fins_upload_format_text` 现在显式接收 `FinsUploadFormatCapability`
  （`dayu/fins/upload_format_contract.py:549-551`），companion-only 文案由
  `", ".join(sorted(capability.companion_only_suffixes))` 机械投影
  （`dayu/fins/upload_format_contract.py:565-570`），文案中不再出现 `.xsd` 字面量。
- 排序与同一模块 `FinsUploadFormatCapability.companion_suffixes` property
  （`dayu/fins/upload_format_contract.py:221`）使用一致的 `sorted(...)` 语义，两处投影顺序同源。
- `.xsd` 字面量在全仓 production 代码中仅剩 `_XSD_COMPANION_SUFFIX` 常量
  （`dayu/fins/upload_format_contract.py:24`），位于 `FINS_UPLOAD_FORMAT_CAPABILITY` 构造点
  （`dayu/fins/upload_format_contract.py:307-310`）——即 companion-only 集合的取值 owner 处，
  不再是文本第二真源。其余 `.xsd` 出现点（`xbrl_file_discovery.py`、`sec_downloader.py`、
  `sec_fiscal_fields.py`）属于 SEC 下载/XBRL 发现管线，与上传格式投影无关。
- 新测试 `test_text_projection_mechanically_consumes_companion_only_suffixes`
  （`tests/fins/test_upload_format_contract.py:330-351`）用替代集合 `{".schema"}` 构造 capability，
  断言文案随 contract 输入变化（`.schema` 出现）且不残留 `.xsd`，满足裁决
  “测试应断言投影随 contract 输入变化，而不是仅快照当前字面量”的要求；该测试已复跑通过。

### DS-F2：`upload_material --files` help 未消费 contract — 已从 owner boundary 修复

- `FinsUploadFormatTextProjection` 新增 `material_files` 字段
  （`dayu/fins/upload_format_contract.py:544-545`），文案自足且与 runtime owner 语义逐项一致：
  - “auto/create/update 必须至少提供一个文件” ↔ `FinsUploadMaterialFiles.from_upsert_paths`
    对空 paths 抛 `ValueError`（`dayu/fins/upload_format_contract.py:494-495`）；
  - “每个文件都必须使用转换器支持的后缀：{primary_suffixes}” ↔ `require_material_path`
    走 `accepts_primary`（converter product suffixes，`dayu/fins/upload_format_contract.py:284-304`）；
  - “逐个实际转换成功” ↔ material 分支把全部文件放入 converter inputs：
    `_prepare_upload_selection` 的 MATERIAL 分支 `converter_inputs=selection.files`
    （`dayu/fins/pipelines/docling_upload_service.py:1024-1028`），每个 material 文件都实际转换，
    与文案“逐个”一致；
  - “delete 不得提供文件” ↔ `for_delete()` 空 selection 与 service 侧
    `normalized_action == "delete" and not is_empty` 校验（`docling_upload_service.py:289-292`）。
- `upload_tool_files` 机械复用同一 `material_files`（`dayu/fins/upload_format_contract.py:583-587`），
  material 分支不再维护独立文案；且把旧 tool schema 中“上述主文件支持后缀”（要求模型跨引用上文）
  改为自足后缀列表，符合 LLM-facing 文本约束，无信息丢失。
- CLI 消费点 `upload_material --files` 直接使用 `FINS_UPLOAD_FORMAT_TEXT.material_files`
  （`dayu/cli/arg_parsing.py:952-956`）。
- 新增测试 `test_upload_material_files_help_consumes_self_contained_format_projection`
  （`tests/cli/test_arg_parsing.py:418-452`）同时断言 argparse action 的 exact source 与
  渲染后 help 的必要业务语义（upsert 非空、converter 后缀、逐个转换成功、delete 空状态），
  已复跑通过。

### 无新 regression / owner drift

- 全部三处消费者（tool schema `upload_tools.py:238`、filing help `arg_parsing.py:924`、
  material help `arg_parsing.py:955`）均消费同一个 `FINS_UPLOAD_FORMAT_TEXT` 投影常量，
  单一真源未被破坏。
- filing 文案在 capability 值不变时文本等价（`.xsd` 展开形式相同），现有 filing 测试未改断言
  即通过，证明无行为回归。
- 旧文案“待上传文件路径”在 production 中仅剩 `ingestion_runtime.py:629、1170` 的内部
  dataclass docstring（非 CLI help、非 LLM-facing 投影），不构成 owner drift。
- diff 范围与 code-fix 文档声明一致，仅四文件；`git status` 确认 registry、oracle、scenario、
  design、README 及 frozen evidence 均未改动。

### 复跑验证（本 reviewer 独立执行）

- focused tests（`tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py`、
  `tests/fins/test_fins_ingestion_tools.py`）：`570 passed, 3 warnings in 6.87s`，
  与 code-fix 文档声明一致；3 条 warning 均为已安装 `edgar` 包 deprecated import，与本次改动无关。
- 两个新增关键测试单独复跑：`PASSED`、`PASSED`。
- pyright（四个改动文件）：`0 errors, 0 warnings, 0 informations`，exit 0。

## Open Questions

无。

## Residual Risk

- 非阻塞观察：`project_fins_upload_format_text` 的 Returns docstring 仍写
  “CLI filing help 与 upload tool schema 共用的不可变文本投影”，未提及 material help 消费者
  （`dayu/fins/upload_format_contract.py:557`）。属 docstring 精度滞后，不是行为或 owner 缺陷，
  不影响本次 PASS 结论。
- `test_text_projection_is_self_contained_and_uses_exact_suffix_order` 在测试内重复构造
  expected 文案（含 `.xsd` 字面量）；但该测试断言的是 frozen capability 值的 contract 行为
  （与 `test_capability_projects_exact_frozen_primary_and_companion_suffixes` 的冻结契约一致），
  且机械投影变化性已由新增 companion-only 测试独立覆盖，不构成测试固化偶然行为。
- 本次 re-review 未重跑覆盖率（code-fix 文档声明 contract 94% / CLI 99%，本 reviewer 未独立复核，
  但测试结果与 pyright 结果均已独立复现）；UF-PF06、UF-PF12 真实 CLI evidence 维持原裁决
  deferred，不在本 work unit。

## 结论

**PASS**

两项 accepted finding（DS-F1、DS-F2）均已从正确 owner boundary（`upload_format_contract`
文本投影 + 单一投影常量的 CLI/tool 消费点）修复，文案语义与 runtime typed contract 逐项一致，
无新 regression、无新 semantic-owner drift，测试与 pyright 独立复跑通过。

## Follow-up verdict（2026-08-15）

Residual Risk 中的 docstring 精度观察已消除，结论维持 **PASS**。

- 核验行：`dayu/fins/upload_format_contract.py:558` Returns 描述现为
  “CLI filing/material help 与 upload tool schema 共用的不可变文本投影。”，
  与实际三处消费者逐一对应：filing CLI help（`dayu/cli/arg_parsing.py:924`）、
  material CLI help（`dayu/cli/arg_parsing.py:955`）、upload tool schema
  （`dayu/fins/tools/upload_tools.py:238`），描述准确，观察消除。
- 范围核验：本次 follow-up 相对上轮 re-review 仅改动该 docstring 一行；`git diff --name-only`
  仍为原四文件，无新 scope creep、无行为改动。
- 验证：docstring 变更不影响行为或类型；`pyright dayu/fins/upload_format_contract.py`
  独立复跑 `0 errors, 0 warnings, 0 informations`，exit 0。
- PASS 结论不变：DS-F1、DS-F2 owner-boundary 修复本身未受任何影响。
