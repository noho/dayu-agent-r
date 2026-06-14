# WU-CLI-01 / CLI-01-S6 Re-review (MiMo)

## Gate

- 当前 gate：re-review。
- Slice：CLI-01-S6 `upload_filings_from` batch plan generation。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- Accepted plan：`docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report：`docs/reviews/wu-cli-01-s6-implementation-codex.md`。
- Initial reviews：`docs/reviews/wu-cli-01-s6-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s6-implementation-review-ds.md`。
- Controller adjudication：`docs/reviews/wu-cli-01-s6-implementation-review-controller-adjudication.md`。
- Fix report：`docs/reviews/wu-cli-01-s6-implementation-fix-codex.md`。

## Re-review scope

只复核 controller adjudication 中 accepted 的 4 项 findings，同时检查 fix 是否引入新问题。

## Accepted findings 逐项复核

### 1. upload suffix allowlist 是否已收敛到 Fins boundary 单一 public constant，并由 CLI direct upload precheck 复用

**已修复。**

证据：

- `dayu/fins/upload_batch.py` L19-36：`FINS_UPLOAD_FILE_SUFFIXES` 是模块级 `Final[frozenset[str]]` 公开常量（无 `_` 前缀），包含 14 种后缀。
- `dayu/fins/upload_batch.py` L369：`FINS_UPLOAD_FILE_SUFFIXES` 已加入 `__all__`。
- `dayu/cli/commands/fins.py` L43-54：CLI 从 `dayu.fins.upload_batch` 导入 `FINS_UPLOAD_FILE_SUFFIXES`。
- `dayu/cli/commands/fins.py` diff：旧的 CLI 本地 `_ALLOWED_UPLOAD_FILE_SUFFIXES`（原 L76-93）已完全移除。
- `dayu/cli/commands/fins.py` L646（`_validated_upload_files`）：direct upload precheck 已改用 `FINS_UPLOAD_FILE_SUFFIXES`。
- `dayu/fins/upload_batch.py` L166：`generate_upload_batch_plan` 内部复用同一常量。

两处后缀校验现在同源于 Fins public constant，未来新增后缀只需改一处。

### 2. 空 --from 是否已测试并返回 exit 2

**已修复。**

证据：

- `tests/cli/test_upload_filings_from_command.py` L183-196：`test_upload_filings_from_empty_source_dir_exits_usage_error` 测试 `--from ""`，断言 `exit_code == EXIT_USAGE_ERROR` 和 `"--from must not be empty" in capsys.readouterr().err`。
- `dayu/cli/commands/fins.py` L241-242：`if args.source_dir is None or args.source_dir.strip() == "": raise CliFinsUsageError("--from must not be empty")` 被该测试覆盖。

### 3. UploadBatchPlanRequest(material_forms=("",)) 是否已测试并抛 UploadBatchPlanUsageError

**已修复。**

证据：

- `tests/fins/test_upload_batch.py` L143-157：`test_empty_material_form_raises_usage_error` 传入 `material_forms=("",)`，断言 `pytest.raises(UploadBatchPlanUsageError, match="material_forms")`。
- `dayu/fins/upload_batch.py` L289-290：`_normalized_forms` 中 `if stripped == "": raise UploadBatchPlanUsageError(...)` 被该测试覆盖。

### 4. source_dir 是普通文件是否已测试并抛 UploadBatchPlanUsageError

**已修复。**

证据：

- `tests/fins/test_upload_batch.py` L127-140：`test_source_dir_is_file_raises_usage_error` 创建普通文件作为 `source_dir`，断言 `pytest.raises(UploadBatchPlanUsageError, match="source path is not a directory")`。
- `dayu/fins/upload_batch.py` L157-158：`if not source_dir.is_dir(): raise UploadBatchPlanUsageError(...)` 被该测试覆盖。

## Fix scope guard 检查

| 禁止项 | 状态 |
|---|---|
| 未抽取 `_optional_stripped_text` 到 `dayu.runtime` | **PASS。** 两模块仍各自保留局部私有 helper，未引入新公共 API。 |
| 未修改 recognition rule | **PASS。** `_DEFAULT_FILING_FORMS`、`_matched_form`、`_normalized_form_token` 逻辑未变。 |
| 未修改 CLI async/sync 边界 | **PASS。** `_run_upload_filings_from` 仍为同步函数，`_run_fins_direct_command_async` 仍为 async wrapper。 |
| 未扩大到 rejected findings | **PASS。** 未处理 cast、command name 常量比较、output 具体错误文本断言。 |
| 未进入 S7 scope | **PASS。** 未触及 `init`、Host management commands 或旧 CLI parity。 |

## S6 核心边界检查

| 边界 | 状态 |
|---|---|
| Fins helper 返回结构化结果 | **PASS。** `generate_upload_batch_plan` 返回 `UploadBatchPlanResult`，不含 shell text。 |
| CLI shell quoting | **PASS。** `_render_upload_batch_command` 使用 `shlex.join(parts)`。 |
| 不导入 Host / Engine / Service / Fins storage | **PASS。** AST import boundary 测试覆盖两个模块。 |
| 不启动 ingestion job / Host Run | **PASS。** `_run_upload_filings_from` 只调用 `generate_upload_batch_plan` + 渲染 + 输出。测试通过 `_install_forbidden_direct_service` 断言。 |

## pyright / 覆盖率 / README 检查

| 项目 | 状态 |
|---|---|
| pyright | **PASS。** 0 errors，0 warnings，0 informations。独立验证通过。 |
| 覆盖率 | **PASS。** `upload_batch.py` 97%（3 uncovered lines: L153 空 ticker、L167 suffix continue、L362 strip 后空），`fins.py` 90%。均 >= 80%。Fix 后 upload_batch.py 覆盖率从 96% 提升到 97%。 |
| README | **PASS。** `dayu/fins/README.md` 新增 `FINS_UPLOAD_FILE_SUFFIXES` 作为 upload 输入后缀真源的说明。`tests/README.md` 未变，符合 fix report 说明（只补已有测试层的错误路径覆盖，不需要机械扩写）。 |

## Fix 引入新问题检查

**无新问题。**

- Fix 只做了两件事：(1) 将后缀常量从 CLI 私有提升为 Fins public 并让 CLI 导入复用；(2) 补充三条已有错误分支的测试。
- 未引入新模块、新依赖、新架构层交互。
- 测试数从 28 增加到 31（+3 条错误路径测试），全部通过。
- 覆盖率数值提升，无下降。

## 结论

**PASS。** 4 项 accepted findings 全部已修复，证据确凿。Fix 未引入新问题，未扩大 scope，未破坏 S6 核心边界。pyright、覆盖率和 README 说明均成立。无新 blocking finding。

| Accepted finding | 最终状态 |
|---|---|
| upload suffix allowlist 收敛到 Fins public constant | 已修复 |
| 空 --from 测试并返回 exit 2 | 已修复 |
| material_forms 含空字符串测试并抛 UploadBatchPlanUsageError | 已修复 |
| source_dir 是普通文件测试并抛 UploadBatchPlanUsageError | 已修复 |
