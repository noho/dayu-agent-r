# WU-CLI-01 / CLI-01-S6 Implementation Re-Review (DS)

## Gate

- 当前 gate：re-review。
- Review target：fix gate 产出（workspace 未提交变更）。
- Implementation report：`docs/reviews/wu-cli-01-s6-implementation-codex.md`。
- Initial reviews：`docs/reviews/wu-cli-01-s6-implementation-review-mimo.md`、`docs/reviews/wu-cli-01-s6-implementation-review-ds.md`。
- Controller adjudication：`docs/reviews/wu-cli-01-s6-implementation-review-controller-adjudication.md`。
- Fix report：`docs/reviews/wu-cli-01-s6-implementation-fix-codex.md`。

## Re-Review Scope

只复核 controller accepted 的 4 条 findings，同时检查 fix 是否引入新问题。

## Accepted Finding Re-Verification

### Finding 1：upload suffix allowlist 收敛到 Fins boundary 单一 public constant

**要求：** 将 upload 后缀 allowlist 收敛为 `dayu.fins.upload_batch` 的单一 public constant，CLI direct upload precheck 复用该常量。

**证据：**

- `dayu/fins/upload_batch.py` L19-36：`FINS_UPLOAD_FILE_SUFFIXES: Final[frozenset[str]]` 是模块级 public constant，包含 14 个上传可接受后缀。
- `dayu/fins/upload_batch.py` L369：`FINS_UPLOAD_FILE_SUFFIXES` 已加入 `__all__`。
- `dayu/fins/upload_batch.py` L166：`generate_upload_batch_plan` 使用 `FINS_UPLOAD_FILE_SUFFIXES` 过滤可识别文件。
- `dayu/cli/commands/fins.py` L43-44：从 `dayu.fins.upload_batch` 导入 `FINS_UPLOAD_FILE_SUFFIXES`。
- `dayu/cli/commands/fins.py` L649：`_validated_upload_files` 使用 `FINS_UPLOAD_FILE_SUFFIXES` 校验 direct upload 文件后缀。
- `dayu/fins/README.md` L137：明确说明 `FINS_UPLOAD_FILE_SUFFIXES` 是 upload 输入后缀真源。
- 旧 `_RECOGNIZED_UPLOAD_SUFFIXES` 和 `_ALLOWED_UPLOAD_FILE_SUFFIXES` 已从两个模块中完全移除（全文 grep 确认）。

**裁决：已修复。** ✅

---

### Finding 2：空 --from 错误路径测试

**要求：** 空 `--from` 路径补充测试，返回 exit 2。

**证据：**

- `tests/cli/test_upload_filings_from_command.py` L183-196：`test_upload_filings_from_empty_source_dir_exits_usage_error`
  - 传入 `--from ""`。
  - 断言 `exit_code == EXIT_USAGE_ERROR`。
  - `dayu/cli/exit_codes.py` L10：`EXIT_USAGE_ERROR: int = 2`。
  - 断言 `"--from must not be empty" in capsys.readouterr().err`。

**裁决：已修复。** ✅

---

### Finding 3：material_forms 空字符串错误路径测试

**要求：** `UploadBatchPlanRequest(material_forms=("",))` 直接调用抛 `UploadBatchPlanUsageError`。

**证据：**

- `tests/fins/test_upload_batch.py` L143-157：`test_empty_material_form_raises_usage_error`
  - 构造 `UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir, action="create", material_forms=("",))`。
  - 断言 `pytest.raises(UploadBatchPlanUsageError, match="material_forms")`。
- `dayu/fins/upload_batch.py` L289-290：`if stripped == "": raise UploadBatchPlanUsageError(...)` 是该测试命中的生产代码路径。

**裁决：已修复。** ✅

---

### Finding 4：source_dir 是普通文件错误路径测试

**要求：** `source_dir` 为普通文件（非目录）时抛 `UploadBatchPlanUsageError`。

**证据：**

- `tests/fins/test_upload_batch.py` L127-140：`test_source_dir_is_file_raises_usage_error`
  - 创建普通文件 `tmp_path / "source.pdf"` 作为 `source_dir`。
  - 断言 `pytest.raises(UploadBatchPlanUsageError, match="source path is not a directory")`。
- `dayu/fins/upload_batch.py` L157-158：`if not source_dir.is_dir(): raise UploadBatchPlanUsageError(...)` 是该测试命中的生产代码路径。

**裁决：已修复。** ✅

---

## Scope Guard Verification

按 controller adjudication，fix gate 不得扩大至 rejected findings。逐项检查：

| Rejected Finding | 状态 | 证据 |
|---|---|---|
| `_optional_stripped_text` 抽取到 `dayu.runtime` | **未发生。** | `dayu/fins/upload_batch.py` L350-363 与 `dayu/cli/commands/fins.py` L752-765 各保留私有副本，未抽取公共 helper。`__all__` 中未导出。 |
| CLI async/sync 边界改写 | **未发生。** | `_run_upload_filings_from`（`fins.py` L232）仍为同步函数，由 async wrapper 调用，未引入 `asyncio.to_thread`。 |
| Recognition rule 改变 | **未发生。** | `_DEFAULT_FILING_FORMS`（L37-46）、`_FORM_TOKEN_SEPARATOR_PATTERN`（L47）、`_matched_form`（L309-325）、`_normalized_form_token`（L328-336）均未修改。 |
| action cast 改写 | **未发生。** | `fins.py` L250 仍为 `cast(BatchUploadAction, args.action)`。 |
| command name 常量比较改写 | **未发生。** | `fins.py` L301 仍为 `entry.command_name == COMMAND_UPLOAD_MATERIAL`。 |
| output 错误消息具体断言 | **未发生。** | `test_upload_filings_from_output_write_failure_exits_failure` 仍只断言 `"dayu-cli upload_filings_from:"` 前缀。 |
| S7 init / Host management / 旧 CLI parity | **未发生。** | 无新文件、新模块或新 import 进入这些领域。 |

**裁决：Scope guard 成立。** ✅

---

## S6 Core Boundary Re-Verification

| 边界 | 状态 | 证据 |
|---|---|---|
| Fins helper 结构化返回 | **成立。** | `generate_upload_batch_plan` 返回 `UploadBatchPlanResult` + `UploadBatchPlanEntry`，不含 shell text、`print`、`shlex`。 |
| CLI shell quoting | **成立。** | `_render_upload_batch_command`（`fins.py` L285-309）使用 `shlex.join()` 生成单行命令。 |
| 不启动 ingestion job / Host Run | **成立。** | `_run_upload_filings_from` 不调用 `FINS_DIRECT_SERVICE_FACTORY`。`_install_forbidden_direct_service` 断言验证（`test_upload_filings_from_command.py` L314-336）。 |
| 不导入 Host / Engine / Fins storage | **成立。** | AST import boundary 测试通过（`test_upload_batch_module_has_no_host_engine_or_storage_imports`、`test_cli_fins_command_has_no_host_engine_or_storage_imports`）。 |
| 不导入 Service（upload_batch.py） | **成立。** | `upload_batch.py` 只导入标准库（`re`、`collections.abc`、`dataclasses`、`pathlib`、`typing`）。 |

**裁决：S6 核心边界完整成立。** ✅

---

## Validation Baseline Re-Verification

| 验证项 | 命令 | 结果 | 与 fix report 一致 |
|---|---|---|---|
| S6 相关测试 | `pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py -q` | **31 passed**，3 edgar deprecation warnings | ✅ 一致 |
| 类型检查 | `python -m pyright dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations** | ✅ 一致 |
| diff 格式 | `git diff --check` | **clean** | ✅ 一致 |
| upload_batch.py 覆盖率 | `--cov=dayu.fins.upload_batch` | **97%**（3 uncovered: L153 empty ticker, L167 continue, L362 optional_stripped_text None return） | ✅ 一致 |
| fins.py 覆盖率 | `--cov=dayu.cli.commands.fins` | **90%**（29 uncovered，多为非 S6 路径与 hard-to-reach 分支） | ✅ 一致 |

---

## New Issues Check

对 fix 引入代码做逐行检查，未发现新问题：

- `FINS_UPLOAD_FILE_SUFFIXES` 类型为 `Final[frozenset[str]]`，不可变，适合作为 public constant。✅
- `FINS_UPLOAD_FILE_SUFFIXES` 已加入 `__all__`，导入语义清晰。✅
- CLI import 从 `dayu.fins.upload_batch` 导入，该模块已在 CLI allowed import boundary 内（原已导入其他公开符号）。✅
- 三条新测试（`test_source_dir_is_file_raises_usage_error`、`test_empty_material_form_raises_usage_error`、`test_upload_filings_from_empty_source_dir_exits_usage_error`）互不干扰、无 side effect、命名遵循现有约定。✅
- 无新增 uncovered line、type error 或 pyright diagnostic。✅

---

## Residual Risks（不变）

| 风险 | 分类 | 状态 |
|---|---|---|
| 旧 CLI 完全 recognition parity | deferred-with-owner (WU-CLI-01-RR-04) | 未变。当前保守识别规则未修改。 |
| `SUCCEEDED` direct command 输出缺少 `result_summary` | deferred-with-owner (WU-CLI-01-RR-08) | 未变。fix gate 未涉及。 |
| `_optional_stripped_text` 跨模块重复 | controller rejected | 未变。controller 判定不属于当前 slice fix scope。 |
| 第三方 `edgar` deprecation warnings | known external | 未变。非本次改动引入。 |

---

## 最终裁决

**PASS。**

4 条 accepted findings 全部已修复：
1. upload suffix allowlist 已收敛为 `FINS_UPLOAD_FILE_SUFFIXES` 单一 public constant，CLI direct upload precheck 已复用。
2. 空 `--from` 已测试，返回 exit 2。
3. `UploadBatchPlanRequest(material_forms=("",))` 已测试，抛 `UploadBatchPlanUsageError`。
4. `source_dir` 是普通文件已测试，抛 `UploadBatchPlanUsageError`。

Scope guard 成立：未扩大至 rejected findings。S6 核心边界完整成立。pyright 0 errors、覆盖率达标（upload_batch.py 97%、fins.py 90%）、31 条测试全部通过。未发现 fix 引入的新 blocking finding。
