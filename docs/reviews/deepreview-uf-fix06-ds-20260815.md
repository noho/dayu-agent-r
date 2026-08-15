# Code Review

## Scope

- Mode: current changes（第二路独立 aggregate deepreview，AgentDS）
- Branch: `codex/upload-filing-oracle`
- Base: `main`
- Review target: UF-FIX06 converter-capability-owner（commits `c1db7b49`、`affa665b`、`8033a56e`、`f61ddb95`，基线 `a3d584fc`）
- Output file: `docs/reviews/deepreview-uf-fix06-ds-20260815.md`
- Included scope:
  - 生产：`dayu/documents/docling_runtime.py`、`dayu/fins/upload_format_contract.py`（新增）、
    `dayu/fins/direct_events.py`（新增）、`dayu/fins/upload_failure.py`、
    `dayu/fins/ingestion_runtime.py`、`dayu/fins/upload_batch.py`、`dayu/fins/tools/upload_tools.py`、
    `dayu/cli/arg_parsing.py`、`dayu/cli/commands/fins.py`、
    `dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、
    `dayu/fins/pipelines/cn_pipeline.py`、根 `README.md`、`dayu/fins/README.md`、`tests/README.md`
  - 测试：`tests/documents/test_docling_runtime.py`、`tests/fins/test_upload_format_contract.py`（新增）、
    `tests/fins/test_upload_failure.py`（新增）、`tests/fins/test_upload_batch.py`、
    `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、
    `tests/cli/test_arg_parsing.py`、`tests/cli/test_fins_commands.py`、
    `tests/fins/test_docling_upload_service.py`、`tests/fins/test_sec_pipeline_upload_filing_stream.py`、
    `tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`
  - 只读输入：`docs/host/design.md`、`docs/engine/design.md`、UF-FIX06 accepted plan、goal confirmation、
    四个 slice 的 implementation/fix/acceptance artifacts；以代码与 main..HEAD diff 为真源
- Excluded scope: main..HEAD 中属于已 close out 的 UF-FIX01/02/03、calendar-year、ticker-alias 工作单元的
  既有改动（不在 UF-FIX06 四 commits 内）；未复读全部 354 个 diff 文件
- Parallel review coverage: 无（本路独立完成，未使用 subagent）

## 结论

**PASS**。未发现 blocking finding。capability 与 converter `allowed_formats` 同源、13 suffix 单一投影、
filing primary 单次转换 + companion 原样保存、material 全转换、USAGE/UNSUPPORTED_UPLOAD_FORMAT 投影、
原子/取消/计数 contract 均成立且无回退；UF-FIX07/PF/protected scope 未越界。两个低严重度 finding
（LLM-facing 文案的 companion-only 后缀硬编码、material CLI help 未投影）不阻塞合入。

## Findings

### 1-未修复-低-LLM-facing 文案硬编码 `.xsd`，companion-only 集合存在第二个真源
- **入口/函数**: `project_fins_upload_format_text()`（CLI help 与 upload tool schema 的共同文案 owner）
- **文件(行号)**: `dayu/fins/upload_format_contract.py:564`（文案字面量 `"随附文件支持这些后缀以及 .xsd"`），
  对照 capability 定义 `upload_format_contract.py:307-310`（`companion_only_suffixes=frozenset({".xsd"})`）
- **输入场景**: 未来任何 work unit 扩展 companion-only 集合（如新增已验证的 XBRL 附件类型）
- **实际分支**: primary 后缀经 `", ".join(FINS_UPLOAD_FORMAT_CAPABILITY.primary_suffixes)` 从 owner 投影，
  但 companion-only 后缀直接以字符串字面量写入文案
- **预期行为**: plan §3.5 与 §5.2 要求 help/schema 使用同一 typed contract/projection；
  `companion_suffixes` property 已存在于 capability 上，文案应机械消费
- **实际行为**: `companion_suffixes` 生产代码零消费（仅 `tests/fins/test_upload_format_contract.py:65` 断言）；
  companion-only 集合的真源（frozenset）与 LLM-facing 文案真源（字面量）分离，改 capability 不会自动更新文案
- **直接证据**: `rg "companion_suffixes|companion_only" dayu/` 在生产代码中仅命中 `upload_format_contract.py`
  自身定义与文案字面量；文案唯一引用 `.xsd` 的位置是硬编码字符串（line 564），当前由
  `test_upload_format_contract.py:286` 的字符串快照强制与 capability 一致
- **影响**: 当前值正确，无运行时错误；风险是未来扩展时 LLM-facing 文案与 owner 投影漂移，属于
  semantic owner drift 的种子而非已发生漂移
- **建议改法和验证点**: 文案改为从 `FINS_UPLOAD_FORMAT_CAPABILITY.companion_only_suffixes` 投影生成
  `.xsd` 片段（如 `", ".join(sorted(...))`），删除字符串字面量；验证点：既有
  `test_upload_format_contract.py` 的文案断言仍通过，且新增断言"改 companion_only 后文案自动变化"
- **修复风险（低）**: 纯文本投影机械改造，不影响 admission 行为
- **严重程度（低）**:

### 2-未修复-低-material CLI `--files` help 未投影支持格式与 delete 约束
- **入口/函数**: `_register_upload_material_command()`
- **文件(行号)**: `dayu/cli/arg_parsing.py:954`
- **输入场景**: 用户执行 `dayu-cli upload_material --help`
- **实际分支**: filing 命令的 `--files` help 已切换到 `FINS_UPLOAD_FORMAT_TEXT.filing_files`
  （`arg_parsing.py:921-925`），material 命令仍为旧文案 `"待上传文件路径。"`
- **预期行为**: material 用户应能从 help 得知：每个文件都必须使用 converter 支持的 13 个 suffix 且
  逐个实际转换、`.xsd` 不作为 material 接受、create/update 至少一个文件、delete 不得提供文件
- **实际行为**: material 用户可见入口没有任何格式/角色/空状态信息，只能靠失败时报错反推；
  LLM-facing tool schema 的 `upload_tool_files` 已自足覆盖这些约束（`upload_tools.py:238`），
  但 CLI material help 与 tool schema 之间形成不一致的投影完备度
- **直接证据**: `arg_parsing.py:954` 的 help 文本与 `FINS_UPLOAD_FORMAT_TEXT` 无任何引用关系；
  plan Slice 4 只断言"CLI `upload filing --help`、tool schema、根 README"三面一致，material CLI
  help 未被要求更新，故本 finding 不构成 plan violation
- **影响**: 用户可见文案缺口，无正确性问题；material 非法后缀仍会被 CLI 层
  `_validated_upload_files` 以 exit 2 有界拒绝，行为不受影响
- **建议改法和验证点**: material `--files` help 复用
  `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 的 material 分支或新增同源 material 文案字段；
  验证点：`tests/cli/test_arg_parsing.py` 新增 material help 断言
- **修复风险（低）**: 纯 help 文本
- **严重程度（低）**:

## Adversarial / Ownership / Coupling Evidence

### Capability 与 converter `allowed_formats` 同源（已核实，通过）

- 唯一静态声明 `DOCLING_CONVERTER_CAPABILITY`（`docling_runtime.py:220-232`）为 9 format / 13 suffix，
  与 plan §5.1 冻结表逐项一致，模块初始化不 import Docling（实测
  `import dayu.cli.arg_parsing` 后 `sys.modules` 无 docling）。
- `build_docling_pdf_converter` 直接调用 `_resolve_docling_allowed_formats(DOCLING_CONVERTER_CAPABILITY)`
  （`docling_runtime.py:591`）并传入 `DocumentConverter(allowed_formats=...)`，同一声明既驱动 help/schema
  又驱动真实 converter；`_resolve_docling_allowed_formats` 对每个已声明 suffix 做
  `suffix ∈ normalized(FormatToExtensions[InputFormat[format_id]])` 单向子集校验
  （`docling_runtime.py:353-399`），缺失即 `DoclingRuntimeInitializationError`，无 fallback。
- `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 直接委托 `converter_capability.accepts_product_suffix`
  （`upload_format_contract.py:223-236`）；batch `_discover_source_files` 只消费该入口
  （`upload_batch.py:418`），material admission 走同一 `require_material_path`。
- 静态审计 `rg 'FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES|_pick_primary_docling_file' dayu tests` 零命中；
  对 `dayu/` 中 `.xsd/.xbrl/.docx/.pptx` 字面量的扫描未发现上传 admission 之外的重复 suffix 集合
  （命中的 xbrl_file_discovery、sec_downloader、sec_fiscal_fields 均属下载/处理域，非上传 admission）。

### filing companion 不转换且 XBRL 可存、material 全转换（已核实，通过）

- `_prepare_upload_selection` 按 source_kind 收窄：filing 的 `converter_inputs=(primary,)`，
  material 的 `converter_inputs=全部 files`（`docling_upload_service.py:995-1028`）。
- `_build_pending_assets` 只遍历 `converter_inputs`：companion 不产生 `conversion_started`、
  不进入 converter、不产生 Docling 资产（`docling_upload_service.py:775-815`）；
  companion 仍作为 `source=original` 的 `_PendingFileAsset` 进入同一 pending batch 并经
  `_store_upload_assets` 循环以 `file_uploaded` 落盘（`docling_upload_service.py:528-554`），
  XBRL/XSD companion 可原样存储。
- `primary_document` 由首项 converter input 的 `f"{file_path.stem}{DOCLING_FILE_SUFFIX}"` 直接产生
  （`docling_upload_service.py:802-806`），`_pick_primary_docling_file` 已删除，
  不再从 stored entry 名称反推业务角色。
- companion 参与存在性/regular 校验（`_validate_source_files`）、FILING 空内容检查与 source
  fingerprint（`_build_original_assets`，`docling_upload_service.py:687-732`），任一 companion
  读取或空内容失败都在 batch 前终止。

### typed failure / atomic / cancel / requested-stored（已核实，无回退）

- `FinsUploadFailureKind.USAGE` 与 `UNSUPPORTED_UPLOAD_FORMAT` 通过模块级分组完整性检查强制
  kind/code 互斥且完整（`upload_failure.py:172-208` 三处 import-time RuntimeError 守卫）；
  `FinsUploadFailureReason.__post_init__` 强制 kind/code 一致（`upload_failure.py:104-115`），
  `upload_failure_reason_from_json` 对未知 code/kind/错配均拒绝（`upload_failure.py:366-392`），
  closed contract 未放宽。
- `fins_upload_failure_from_exception` 首个分支显式匹配 `FinsUploadFormatError`，投影为固定
  USAGE/UNSUPPORTED_UPLOAD_FORMAT + 固定 bounded/path-free message + canonical `file_label`
  （`upload_failure.py:224-231`）；SEC/CN workflow catch-all 均消费该投影
  （`sec_upload_workflow.py:298-307`、`cn_pipeline.py:927-934`），无 workflow 级重写。
- material workflow 的 selection 构造是 try 块第一行，先于 `previous_meta` 读取、UPLOAD_STARTED、
  company batch staging 与 prepare_upload（`sec_upload_workflow.py:459-463`、`cn_pipeline.py:1071-1076`），
  非法 suffix 零副作用；filing 静态校验顺序保持 basename → exists → regular → 按位置角色校验 →
  构造 selection（`ingestion_runtime.py:994-1025`），delete 由 validator 直接产生 `for_delete()`。
- `DoclingConversionCancelledError` 与 `DoclingConversionError` 是兄弟类
  （`docling_process_converter.py:216,242`），`_build_pending_assets` 的取消不再 `break` 而是 raise
  （`docling_upload_service.py:771`），被 `prepare_upload` 精确捕获为 cancelled result
  （`docling_upload_service.py:357-361`），取消不会被误映射为 content failure。
- `stored_file_count=stored_original_count` 只统计 `source=original` 资产，companion 计入、
  Docling 派生不计（`docling_upload_service.py:541-542,581`）；requested 继续来自原始输入。
- Service 入口对 source_kind/selection 类型不匹配、action/emptiness 双向不匹配均在文件读取、
  converter 与 batch 前以 ValueError 拒绝（`docling_upload_service.py:282-293,995-1028`）。

### calendar/ticker/UF-FIX07/PF/protected scope（已核实，未越界）

- UF-FIX06 四 commits 的 diff 未触碰 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、
  `docs/host/design.md`、`docs/engine/design.md`、`dayu/host`、`dayu/engine`、`dayu/runtime`、
  `dayu/config`（`git diff 267e90b1~1..HEAD --stat` 对 registry/design 为空）。
- 无显式 primary 参数、无同目录 `.xsd` 自动归组；batch 对 `.xsd` 与 legacy/未选择 suffix 稳定
  `unsupported_suffix` skip（`upload_batch.py:418-427`），`test_upload_batch.py:427` 钉死 13 个
  enter suffix 精确集合。
- strict typing：pyright 全量 `0 errors, 0 warnings, 0 informations`；四个核心文件无
  `hasattr/getattr/Any/object` 签名；中文 docstring 齐全。

### 测试证据

- 本路独立复跑：`tests/documents/test_docling_runtime.py` + `test_upload_format_contract.py` +
  `test_upload_failure.py` + `test_upload_batch.py` = **108 passed**；
  `test_docling_upload_service.py` + SEC filing/material stream + `test_cn_pipeline.py` +
  `test_fins_ingestion_tools.py` = **215 passed**（合计 323 passed，3 warnings 为第三方 deprecation）。
- 按用户约束未运行 UF-PF06、UF-PF12 与真实 CLI evidence；未运行完整 14 文件 focused matrix
  （slice 4 acceptance 记录的 1235 passed / 11 文件覆盖率 ≥80%（合计 92%）作为 gateflow 记录引用，
  本路未独立复跑该矩阵与逐文件 coverage）。
- 未修改任何生产/测试/既有 artifacts；未 commit。

## Open Questions

- 无。未发现阻碍 confident judgment 的问题。

## Residual Risk

- delete + 提供文件被静默丢弃（filing validator 与 material workflow 均为 delete 构造
  `for_delete()`，非空输入不再被消费，也无显式拒绝）；与 UF-FIX06 前的既有行为一致（旧 service
  delete 分支同样忽略 files），非本 work unit 回退，但"delete 不得提供文件"目前只是文案规则，
  无 enforcement。若后续要收紧，应归 usage 校验类 work unit，不在本 work unit 内修。
- material create/update 空文件列表（CLI `--files` 缺失或 tool 未传 files）经
  `from_upsert_paths` 的 ValueError 落入 catch-all 投影为 RUNTIME/UNEXPECTED_RUNTIME，而非
  USAGE 级文案；与旧行为（service `_validate_source_files` ValueError 同路径）等价，非回退，
  但用户可修正输入被投影为 runtime 分类，可作后续 usage contract 收口项。
- 每个 fallback attempt 构造 converter 时都会重跑一次 `_resolve_docling_allowed_formats` 的
  静态解析（lazy import 有缓存，仅重复 9 项字典遍历），成本可忽略，未计入 finding。
- companion-only `.xsd` 文案硬编码与 material CLI help 缺口见 Findings 1/2，建议 controller
  裁决 accepted 或 deferred-with-owner。
- 真实全格式矩阵与 mandatory CLI scenario 未复跑（按约束），UF-PF06/UF-PF12 与冻结 evidence
  刷新不属于本 work unit；UF-FIX07（显式 primary、重复路径、basename/derived-name collision）
  与 batch 自动归组继续 deferred。
