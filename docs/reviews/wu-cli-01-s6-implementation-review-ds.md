# WU-CLI-01 / CLI-01-S6 Implementation Review (DS)

## Gate

- 当前 gate：code review。
- Review target：WU-CLI-01 S6 implementation（workspace 未提交变更）。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- 总控文档：`docs/host/ui-implementation-control.md`。
- Accepted plan：`docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report：`docs/reviews/wu-cli-01-s6-implementation-codex.md`。

## 审查范围

| 文件 | 变更性质 |
|---|---|
| `dayu/fins/upload_batch.py` | 新增 Fins typed boundary：批量上传计划生成 |
| `dayu/cli/commands/fins.py` | 移除 `upload_filings_from` unsupported 分支；新增 plan generation / script rendering |
| `tests/fins/test_upload_batch.py` | 新增 Fins batch helper 测试 |
| `tests/cli/test_upload_filings_from_command.py` | 新增 CLI command 集成测试 |
| `dayu/fins/README.md` | 新增 Batch upload plan 小节 |
| `tests/README.md` | 更新 CLI 测试分层说明 |
| `docs/host/ui-implementation-control.md` | 更新 S6 状态 |

## 独立验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| S6 相关测试 | `pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py -q` | 28 passed, 3 warnings (第三方 edgar deprecation) |
| 类型检查 | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| diff 格式 | `git diff --check` | clean（实现报告声明） |
| upload_batch.py 覆盖率 | `--cov=dayu.fins.upload_batch` | 96%（5 uncovered lines: 153, 158, 167, 290, 362） |
| fins.py 合并覆盖率 | `--cov=dayu.cli.commands.fins`（含 fins_commands + upload_filings_from 测试） | 90%（30 uncovered lines，多数为非 S6 命令的 hard-to-reach 分支） |

## 逐项裁决

### 1. 迁移旧 upload_filings_from 的业务语义到当前 Fins typed boundary，不搬迁旧实现或旧隐式目录规则

**PASS。** 证据：

- `dayu/fins/upload_batch.py` 是全新的 typed batch plan helper，使用 `UploadBatchPlanRequest` → `UploadBatchPlanResult` + `UploadBatchPlanEntry` 结构化数据流。
- 文件识别规则是当前 Fins domain 自洽的保守规则：只处理已知可上传后缀普通文件（`_RECOGNIZED_UPLOAD_SUFFIXES`，L19-36），基于文件名中常见 SEC filing form token（`_DEFAULT_FILING_FORMS`，L37-47）和用户显式传入的 `material_forms` 做 token 匹配。
- 没有引用旧 `dayu-agent` 的 `cli_support.py` 或任何旧识别 helper。
- 没有读取旧隐式目录结构、环境变量或 cwd 推断。

### 2. upload_filings_from 不启动 ingestion job，不创建 Host Run，不写 Host EventLog，不走 FinsDirectCommandService start/wait/cancel

**PASS。** 证据：

- `_run_upload_filings_from`（`dayu/cli/commands/fins.py` L249）是纯同步函数，调用 `generate_upload_batch_plan` → 渲染脚本 → 写入 stdout 或文件后返回。
- S6 路径不经过 `_run_fins_direct_command_async`（L224），不经过 `_start_direct_job`（L355），不调用 `FINS_DIRECT_SERVICE_FACTORY`。
- AST import 测试（`tests/fins/test_upload_batch.py` L127-154、`tests/cli/test_upload_filings_from_command.py` L261-282）显式确认两个模块均未导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins.storage`。
- CLI 测试（`tests/cli/test_upload_filings_from_command.py` L298-320）通过 monkeypatch `FINS_DIRECT_SERVICE_FACTORY` 为断言失败的 factory，验证 `upload_filings_from` 路径不会触发 Service helper 创建。

### 3. Fins helper 必须返回结构化 UploadBatchPlanEntry/Result，不返回 shell text；shell quoting 只能在 CLI formatter

**PASS。** 证据：

- `generate_upload_batch_plan`（`dayu/fins/upload_batch.py` L139）返回 `UploadBatchPlanResult`，其中 `entries: tuple[UploadBatchPlanEntry, ...]` 是结构化 dataclass，每个 entry 的 `files: tuple[Path, ...]` 保持 `Path` 对象。
- Fins helper 不包含任何 `shlex`、`print`、字符串拼接或 shell 文本生成逻辑。
- Shell quoting 完全在 CLI formatter 中：`_render_upload_batch_command`（`dayu/cli/commands/fins.py` L302）使用 `shlex.join(parts)` 生成单行命令，`_render_upload_batch_script`（L290）拼接多行并以 `\n` 结尾。
- 测试 `test_upload_filings_from_writes_quoted_script_to_stdout`（`tests/cli/test_upload_filings_from_command.py` L23-71）验证含空格路径被正确 quote。

### 4. CLI 只做 argparse -> UploadBatchPlanRequest 和 script rendering，不能成为 Fins business recognition 真源

**PASS。** 证据：

- CLI `_run_upload_filings_from`（`dayu/cli/commands/fins.py` L260-280）构造 `UploadBatchPlanRequest` 后调用 `generate_upload_batch_plan(request)`，不做文件名解析、form 识别或文件分类。
- filing/material 识别逻辑全部在 `dayu/fins/upload_batch.py` 的 `_matched_form`、`_normalized_form_token`、`_form_patterns` 等私有 helper 中。
- CLI 的 `_normalized_text_tuple`（L674）只做 argparse list/CSV 拆分和空白 strip，不包含业务识别语义。

### 5. 不导入 Host / Engine / Service / dayu.fins.storage；只扫描用户显式传入的本地 source dir

**PASS。** 证据：

- AST import boundary 测试通过（见第 2 项）。
- `generate_upload_batch_plan` 从 `request.source_dir` 扫描文件，不调用任何仓储协议、不解析 workspace root。
- 文件迭代通过 `Path.rglob("*")` 或 `Path.iterdir()` + `path.is_file()` 完成，不涉及 Fins storage 的任何 repository。

### 6. 错误语义验证

| 错误场景 | 要求 | 实现位置 | 测试覆盖 | 裁决 |
|---|---|---|---|---|
| source dir 不存在 | exit 2 | `upload_batch.py` L155-156 → `UploadBatchPlanUsageError` → CLI L208-210 → `EXIT_USAGE_ERROR` | `test_missing_source_dir_raises_usage_error` + `test_upload_filings_from_missing_source_dir_exits_usage_error` | **PASS** |
| 无可识别文件 | exit 1 | `upload_batch.py` L187-190 → `UploadBatchPlanEmptyError` → CLI L211-213 → `EXIT_FAILURE` | `test_no_recognizable_files_raises_empty_error` + `test_upload_filings_from_no_recognizable_files_exits_failure` | **PASS** |
| output 写失败 | exit 1 | `fins.py` L286 `write_text` 异常 → L219-221 generic `Exception` → `EXIT_FAILURE` | `test_upload_filings_from_output_write_failure_exits_failure` | **PASS** |
| 扫描阶段 KeyboardInterrupt | exit 130 | `fins.py` L217-218 `KeyboardInterrupt` → `EXIT_KEYBOARD_INTERRUPT` | `test_upload_filings_from_keyboard_interrupt_exits_130` | **PASS** |

额外验证：

- `source_dir` 是文件（非目录）：`upload_batch.py` L157-158 → `UploadBatchPlanUsageError` → exit 2。路径存在但无测试覆盖（见 S6-RV-F07）。
- 空 ticker：`upload_batch.py` L152-153 → `UploadBatchPlanUsageError` → exit 2。路径存在但无测试覆盖。
- 空 `--from`：`fins.py` L261-262 → `CliFinsUsageError` → exit 2。路径存在但无测试覆盖（见 S6-RV-F05）。

### 7. Recognition rule 保守性、自解释性与测试覆盖

**保守性裁决：PASS。**

- **后缀 allowlist**：只接受 14 种已知可上传后缀（`.pdf`、`.xlsx`、`.docx`、`.html`、`.xml`、`.zip` 等），见 `_RECOGNIZED_UPLOAD_SUFFIXES`（`upload_batch.py` L19-36）。其他后缀文件被静默跳过（L166 `continue`）。
- **Filing 识别**：基于 8 种默认 SEC form tokens（10-K、10-Q、8-K、20-F、6-K、DEF 14A、SC 13D、SC 13G），通过 `_normalized_form_token` 去除非字母数字字符后做 token 包含匹配。是保守的子串匹配——例如 "10K" 作为 token 出现在文件名规范化 token 中才命中。
- **Material 识别**：仅当用户显式传入 `--material-forms` 时才匹配；无隐式 material 识别。material 匹配优先于 filing 匹配（`upload_batch.py` L168 先检查 material patterns）。
- **全部跳过失败**：无可识别文件时 `UploadBatchPlanEmptyError`（L187-190），不默默输出空脚本。

**自解释性裁决：PASS。**

- `_DEFAULT_FILING_FORMS` 为模块级 `Final` 常量，注释在函数 docstring 中。
- `_matched_form` / `_normalized_form_token` 有中文 docstring 说明匹配语义。
- `UploadBatchPlanResult.skipped_files` 记录被跳过的可接受后缀但无业务识别的文件，调用方可审计。

**测试覆盖充分性裁决：PASS with observations.**

| 场景 | 测试 |
|---|---|
| non-recursive scan | `test_non_recursive_scan_only_uses_top_level_files` |
| recursive scan | `test_recursive_scan_includes_nested_files` |
| material forms 识别 | `test_material_forms_generate_material_entries` |
| 无识别文件 → error | `test_no_recognizable_files_raises_empty_error` |
| source dir 不存在 → error | `test_missing_source_dir_raises_usage_error` |
| 无识别文件 → CLI exit 1 | `test_upload_filings_from_no_recognizable_files_exits_failure` |
| source dir 不存在 → CLI exit 2 | `test_upload_filings_from_missing_source_dir_exits_usage_error` |
| stdout 输出 + quoting | `test_upload_filings_from_writes_quoted_script_to_stdout` |
| non-recursive CLI | `test_upload_filings_from_respects_non_recursive_scan` |
| recursive CLI | `test_upload_filings_from_recursive_scan_includes_nested_files` |
| --output 文件写入 | `test_upload_filings_from_writes_output_file` |
| output write failure → exit 1 | `test_upload_filings_from_output_write_failure_exits_failure` |
| scan SIGINT → exit 130 | `test_upload_filings_from_keyboard_interrupt_exits_130` |
| Fins helper import boundary | `test_upload_batch_module_has_no_host_engine_or_storage_imports` |
| CLI import boundary | `test_cli_fins_command_has_no_host_engine_or_storage_imports` |

**未覆盖场景：**

- `source_dir` 是文件（非目录）→ `UploadBatchPlanUsageError`
- 空 ticker → `UploadBatchPlanUsageError`
- 空 `--from` → `CliFinsUsageError`
- `material_forms` 含空字符串 → `UploadBatchPlanUsageError`
- `skipped_files` 非空时的内容验证
- `action` 字段在 `UploadBatchPlanEntry` 中的传播验证
- `fiscal_period`、`amended=True`、`filing_date`、`report_date` 在渲染输出中的逐项验证

### 8. AGENTS.md 编码约束

| 约束 | 裁决 |
|---|---|
| 中文 docstring | **PASS。** `upload_batch.py` 所有函数/类均有中文 docstring，包含参数、返回值、异常说明。 |
| 严格类型 | **PASS。** 无 `Any`、`object`、无类型参数/返回值。所有 dataclass 使用 `frozen=True, slots=True`。公开类型别名 `BatchUploadCommandName`、`BatchUploadAction` 使用 `Literal`。 |
| 无 hasattr/getattr 逃逸 | **PASS。**全文未出现 `hasattr`、`getattr`。 |
| README 更新符合约束 | **PASS。** `dayu/fins/README.md` 新增 "Batch upload plan" 小节（L137），仅描述当前已实现 capability 和边界，不写未来计划或实现细节。`tests/README.md` 将 CLI 测试说明从 unsupported 更新为实际功能覆盖（L93-96）。 |
| pyright 0 errors | **PASS。** 独立验证 0 errors, 0 warnings, 0 informations。 |
| 覆盖率 >=80% | **PASS。** `upload_batch.py` 96%，`fins.py`（合并）90%。 |

## Findings

### Severity: medium

#### S6-RV-F01 — `_optional_stripped_text` 在两层重复定义

- **文件/行号**：`dayu/fins/upload_batch.py:350-363` 与 `dayu/cli/commands/fins.py:769-782`
- **证据**：两个模块各自定义了语义完全相同的 `_optional_stripped_text(value: str | None) -> str | None`：strip 后若为空返回 `None`，否则返回 stripped 文本。函数体逐行一致。
- **影响**：违反 AGENTS.md "重复逻辑必须抽取"硬约束。如果未来需要改变 strip 语义（如 Unicode 空白处理），两处必须同步修改，存在维护漂移风险。
- **建议修复**：将 `_optional_stripped_text` 提取到层中立公共位置。`dayu.runtime` 是合适的位置——它是层中立运行期基础设施，`_optional_stripped_text` 是纯字符串规范化，不依赖任何业务语义。可考虑 `dayu/runtime/text_utils.py` 或等价模块，由 Fins 和 CLI 各自导入。当前 S6 之前 CLI 中已存在该函数，S6 在 Fins 中新增了副本——应在当前 slice 关闭此重复。
- **裁决**：**不阻塞**。功能正确，两处副本当前语义一致。但应在 fix gate 消除重复。

#### S6-RV-F02 — 文件后缀 allowlist 在两层重复定义

- **文件/行号**：`dayu/fins/upload_batch.py:19-36`（`_RECOGNIZED_UPLOAD_SUFFIXES`）与 `dayu/cli/commands/fins.py:76-93`（`_ALLOWED_UPLOAD_FILE_SUFFIXES`）
- **证据**：两个 `frozenset[str]` 包含完全相同的 14 个后缀字面量（`.csv`、`.docx`、`.htm`、`.html`、`.json`、`.md`、`.pdf`、`.txt`、`.xbrl`、`.xhtml`、`.xls`、`.xlsx`、`.xml`、`.zip`）。服务于不同目的：Fins 侧用于批量扫描过滤，CLI 侧用于单文件上传前置校验。
- **影响**：如果未来支持新文件类型（如 `.pptx`），两处必须同步更新。当前如果一个更新而另一个未更新，会导致 batch scan 和 direct upload 的 accept list 不一致——batch 会跳过而 direct upload 会拒绝，或反之。
- **建议修复**：将 allowlist 定义为 Fins public contract（例如 `dayu/fins/upload_batch.py` 中将 `_RECOGNIZED_UPLOAD_SUFFIXES` 改为公开常量并导出），CLI 从 Fins 导入。CLI 已在 accepted import boundary 内导入 `dayu.fins.upload_batch` 的公开符号——将后缀集合提升为公开常量即可。
- **裁决**：**不阻塞**。当前值一致，功能正确。但应在 fix gate 消除重复。

### Severity: low

#### S6-RV-F03 — `cast(BatchUploadAction, args.action)` 绕过类型检查

- **文件/行号**：`dayu/cli/commands/fins.py:267`
- **证据**：`args.action` 的运行时类型是 `str`（来自 argparse），通过 `cast(BatchUploadAction, args.action)` 告诉类型检查器它是 `Literal["create", "update"]`。虽然 argparse 的 `choices=("create", "update")` 保证运行时只有这两个值，但 `cast` 抹去了类型安全性——如果 argparse choices 被错误配置，类型检查器不会报警。
- **影响**：低。argparse choices 提供了运行时验证，且 `BatchUploadAction` 只有两个值，`generate_upload_batch_plan` 也不对 action 做额外校验。
- **建议修复**：在 `_run_upload_filings_from` 中增加运行时断言：`if args.action not in ("create", "update"): raise CliFinsUsageError(...)`。或者接受 `cast` 作为 argparse → typed boundary 的既定模式（本项目中其他 Fins direct commands 也使用此模式）。
- **裁决**：**不阻塞**。属于 argparse UI adapter 的既有模式，S5 的 `_start_upload_filing` / `_start_upload_material` 也使用相同方式传递 `args.action`。

#### S6-RV-F04 — command_name 比较使用 argparse 字符串常量而非 typed literal

- **文件/行号**：`dayu/cli/commands/fins.py:318`
- **证据**：`if entry.command_name == COMMAND_UPLOAD_MATERIAL:` 用从 `dayu.cli.arg_parsing` 导入的 argparse 字符串常量 `COMMAND_UPLOAD_MATERIAL` 比较 `entry.command_name`（类型为 `BatchUploadCommandName = Literal["upload_filing", "upload_material"]`）。两者值相同（`"upload_material"`），功能正确，但语义上 `COMMAND_UPLOAD_MATERIAL` 是 CLI argparse 概念，不应与 Fins typed `BatchUploadCommandName` 混用。
- **影响**：低。仅影响代码可读性和语义清晰度，不影响运行时行为。
- **建议修复**：使用 `entry.command_name == "upload_material"` 直接字面量比较（type narrowing 生效），或定义 CLI 本地常量与 `BatchUploadCommandName` 值一致。
- **裁决**：**不阻塞**。属于代码风格改进，可在后续清理。

#### S6-RV-F05 — 空 `--from` 错误路径无测试覆盖

- **文件/行号**：`dayu/cli/commands/fins.py:261-262`
- **证据**：`if args.source_dir is None or args.source_dir.strip() == "": raise CliFinsUsageError("--from must not be empty")` 未被任何测试覆盖。覆盖率报告确认 L262 为 uncovered。
- **影响**：低。此错误路径简单直白，且 `UploadBatchPlanUsageError`（source_dir 不存在）已有覆盖。缺少覆盖不影响正确性信心。
- **建议修复**：补充一条 `test_upload_filings_from_empty_source_dir_exits_usage_error`。
- **裁决**：**不阻塞**。

#### S6-RV-F06 — `material_forms` 含空字符串错误路径无测试覆盖

- **文件/行号**：`dayu/fins/upload_batch.py:289-290`
- **证据**：`if stripped == "": raise UploadBatchPlanUsageError(...)` 在 `_normalized_forms` 中未被测试覆盖。覆盖率报告确认 L290 为 uncovered。
- **影响**：低。用户通过 CLI 传入空字符串需要经过 `_normalized_text_tuple`（CLI 侧）先行过滤，CLI 会先抛出 `CliFinsUsageError`。直接调用 Fins helper 时此路径有意义但概率低。
- **建议修复**：补充一条直接调用 `generate_upload_batch_plan` 且传入含空字符串 `material_forms` 的测试。
- **裁决**：**不阻塞**。

#### S6-RV-F07 — `source_dir` 为文件（非目录）错误路径无测试覆盖

- **文件/行号**：`dayu/fins/upload_batch.py:157-158`
- **证据**：`if not source_dir.is_dir(): raise UploadBatchPlanUsageError(f"source path is not a directory: {source_dir}")` 未被测试覆盖。覆盖率报告确认 L158 为 uncovered。
- **影响**：低。用户传入文件路径而非目录的概率低，但路径存在。
- **建议修复**：补充一条 `test_source_dir_is_file_raises_usage_error`。
- **裁决**：**不阻塞**。

### Observations（非 findings）

#### S6-RV-OB01 — `KeyboardInterrupt` 映射范围

CLI `run_fins_direct_command`（`fins.py` L217-218）对所有未捕获 `KeyboardInterrupt` 映射为 `EXIT_KEYBOARD_INTERRUPT`（130），覆盖了扫描阶段（明确要求）和 output 写入阶段（未明确要求但合理）。实现一致且简单，无需区分阶段。

#### S6-RV-OB02 — 识别规则保守性边界

当前规则是子串匹配 normalized token。SEC form token 经过 `_FORM_TOKEN_SEPARATOR_PATTERN = r"[^A-Z0-9]+"` 去除非字母数字字符后，token 如 `10K`、`20F`、`SC13D` 在文件名中的出现具有高度特异性。理论上的 false positive（如文件名包含 `ABC10KOW` 命中 `10K`）在实践中概率极低。这是合理的 conservative choice，总控 `WU-CLI-01-RR-04` 已将旧 CLI 完全 parity 列为 deferred-with-owner。

#### S6-RV-OB03 — Coverage 数值

`upload_batch.py` 96%（5 uncovered lines）和 CLI fins.py 90% 均满足 >=80% 门槛。5 个 uncovered lines 对应上文 F05-F07 的未测错误路径和 `_optional_stripped_text(empty_string) -> None` 分支。

#### S6-RV-OB04 — `_iter_source_files` sorted() 顺序稳定性

`_iter_source_files`（`upload_batch.py` L199-211）对 `rglob("*")` / `iterdir()` 结果做 `sorted()` 排序，保证 `entries` 的生成顺序稳定。这是好的实践，确保同一目录多次扫描产生相同脚本。

## 审查结论

**PASS。**

所有 8 项审查标准均通过。没有发现 correctness、stability 或安全方面的 blocking finding。

2 个 medium severity findings（S6-RV-F01、S6-RV-F02）涉及代码重复，建议在 fix gate 消除。5 个 low severity findings（S6-RV-F03 至 F07）涉及测试覆盖缺口和代码风格，不阻塞。

## Residual Risks

| 类别 | 风险 | 状态 |
|---|---|---|
| **fixed in S6** | `upload_filings_from` 启动 ingestion job / 创建 Host Run / 写 Host EventLog | 已验证不启动。CLI 测试通过断言禁止 FinsDirectCommandService 创建。 |
| **fixed in S6** | Fins helper 返回 shell text | 已验证返回结构化 `UploadBatchPlanResult`，shell quoting 仅在 CLI formatter。 |
| **fixed in S6** | CLI 成为 Fins business recognition 真源 | 已验证 CLI 只做 argparse → Request 转换，识别逻辑在 Fins boundary。 |
| **fixed in S6** | 导入 Host/Engine/Service/Fins storage | AST import boundary 测试通过。 |
| **deferred-with-owner** | 旧 CLI 完全 recognition parity | 归入 `WU-CLI-01-RR-04`（总控 residual risk 表），当前保守规则可满足典型场景。 |
| **fix gate建议** | `_optional_stripped_text` 重复（S6-RV-F01） | 建议提取到 `dayu.runtime` 或等价层中立位置。 |
| **fix gate建议** | 文件后缀 allowlist 重复（S6-RV-F02） | 建议在 Fins 侧公开常量，CLI 导入。 |
| **coverage gap** | 未覆盖错误路径（S6-RV-F05/F06/F07） | 低风险，建议 fix gate 补测试。 |
| **design risk** | Recognition substring matching false positive | 低风险。SEC form token 高度特异，总控 `WU-CLI-01-RR-04` 覆盖后续 parity 需求。 |

## Appendix: 未覆盖行详情

### `dayu/fins/upload_batch.py`（5 uncovered lines）

| 行号 | 代码 | 原因 |
|---|---|---|
| 153 | `raise UploadBatchPlanUsageError("ticker must not be empty")` | 空 ticker 无测试 |
| 158 | `raise UploadBatchPlanUsageError(f"source path is not a directory: {source_dir}")` | source_dir 是文件无测试 |
| 167 | `continue`（suffix not in allowlist） | 此分支在正常测试中执行，但 coverage 报告将其标记为 uncovered——可能是分支覆盖工具对循环内 `continue` 的计数方式。实际在 non-recursive/material 测试中非 PDF 后缀文件未被创建。 |
| 290 | `raise UploadBatchPlanUsageError(f"{field_name} must not contain empty item")` | material_forms 空项无测试 |
| 362 | `return None`（strip 后为空字符串） | `_optional_stripped_text(empty_after_strip)` 无直接测试 |

### `dayu/cli/commands/fins.py`（S6 相关的 uncovered lines）

| 行号 | 代码 | 原因 |
|---|---|---|
| 262 | `raise CliFinsUsageError("--from must not be empty")` | 空 `--from` 无测试 |
| 344 | `parts.extend(("--fiscal-period", entry.fiscal_period))` | fiscal_period 渲染无测试 |
| 346 | `parts.append("--amended")` | amended=True 渲染无测试 |
| 348 | `parts.extend(("--filing-date", entry.filing_date))` | filing_date 渲染无测试 |
| 350 | `parts.extend(("--report-date", entry.report_date))` | report_date 渲染无测试 |
