# WU-CLI-01 / CLI-01-S6 Implementation Review (MiMo)

## Gate

- 当前 gate：implementation review。
- Slice：CLI-01-S6 upload_filings_from batch plan generation。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- Accepted plan：`docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Implementation report：`docs/reviews/wu-cli-01-s6-implementation-codex.md`。

## Review scope

Review target 是当前未提交 workspace changes 中的 CLI-01-S6 范围：

- `dayu/fins/upload_batch.py`（新增）
- `dayu/cli/commands/fins.py`（修改）
- `tests/fins/test_upload_batch.py`（新增）
- `tests/cli/test_upload_filings_from_command.py`（新增）
- `dayu/fins/README.md`（修改）
- `tests/README.md`（修改）
- `docs/host/ui-implementation-control.md`（修改）

## Review 标准逐项裁决

### 1. 迁移旧 upload_filings_from 业务语义到当前 Fins typed boundary

**PASS。** `dayu.fins.upload_batch` 是新增 Fins typed boundary，提供 `UploadBatchPlanRequest` / `UploadBatchPlanEntry` / `UploadBatchPlanResult` 结构化数据，不返回 shell text。CLI 只做 argparse → `UploadBatchPlanRequest` 转换和 script rendering。未搬迁旧实现或旧隐式目录规则，采用当前 Fins domain 可自洽的保守文件名 token 识别。

### 2. upload_filings_from 不启动 ingestion job / Host Run / EventLog

**PASS。** `_run_upload_filings_from()` (fins.py:249-287) 只调用 `generate_upload_batch_plan()` 和 `print()` / `write_text()`，不调用 `FinsDirectCommandService`，不创建 Host Run，不写 Host EventLog。测试 `_install_forbidden_direct_service()` 断言 upload_filings_from 不创建 Fins direct service。

### 3. Fins helper 返回结构化结果，shell quoting 只在 CLI formatter

**PASS。** `upload_batch.py` 返回 `UploadBatchPlanResult` / `UploadBatchPlanEntry`，不包含任何 shell text。`_render_upload_batch_script()` / `_render_upload_batch_command()` (fins.py:290-327) 在 CLI 层使用 `shlex.join()` 做 shell quoting。

### 4. CLI 只做 argparse → UploadBatchPlanRequest 和 script rendering

**PASS。** `_run_upload_filings_from()` (fins.py:249-287) 只做：(1) parse ticker CSV，(2) 校验 source dir，(3) 构造 `UploadBatchPlanRequest`，(4) 调用 `generate_upload_batch_plan()`，(5) 渲染 script，(6) 输出。不做 filing/material 识别——识别是 `upload_batch.py` 的职责。

### 5. 不导入 Host / Engine / Service / Fins storage；只扫描用户显式传入的本地 source dir

**PASS。** `upload_batch.py` 只导入 `re`、`collections.abc`、`dataclasses`、`pathlib`、`typing`（标准库）。AST 边界测试 `test_upload_batch_module_has_no_host_engine_or_storage_imports()` 和 `test_cli_fins_command_has_no_host_engine_or_storage_imports()` 验证无 forbidden import。`generate_upload_batch_plan()` 只扫描 `request.source_dir`，不读取 Fins storage。

### 6. 错误语义

**PASS。**

- source dir 不存在 → `UploadBatchPlanUsageError` → `EXIT_USAGE_ERROR` (exit 2)：fins.py:209-210，测试 `test_upload_filings_from_missing_source_dir_exits_usage_error`。
- 无可识别文件 → `UploadBatchPlanEmptyError` → `EXIT_FAILURE` (exit 1)：fins.py:211-213，测试 `test_upload_filings_from_no_recognizable_files_exits_failure`。
- output 写失败 → `OSError` → `EXIT_FAILURE` (exit 1)：fins.py:219-220，测试 `test_upload_filings_from_output_write_failure_exits_failure`。
- 扫描阶段 KeyboardInterrupt → `EXIT_KEYBOARD_INTERRUPT` (exit 130)：fins.py:217-218，测试 `test_upload_filings_from_keyboard_interrupt_exits_130`。

### 7. recognition rule 保守性与测试覆盖

**PASS with observation。** 识别规则采用保守 Fins typed approach：

- 只处理 `_RECOGNIZED_UPLOAD_SUFFIXES` 中的普通文件。
- 文件名规范化后匹配 `_DEFAULT_FILING_FORMS` token → `upload_filing`。
- 文件名规范化后匹配用户传入 `material_forms` token → `upload_material`。
- 无法识别的文件跳过；全部跳过时 raise `UploadBatchPlanEmptyError`。
- 测试覆盖 recursive/non-recursive、filing/material 识别、空结果、source dir 不存在、import boundary。

Observation：识别规则的保守性是 intentional deviation（WU-CLI-01-RR-04），不要求旧 CLI 完全 parity。

### 8. AGENTS.md 编码约束

**PASS。**

- 中文 docstring：所有公开函数和类均有完整中文 docstring，包含参数、返回值、异常说明。
- 严格类型：所有参数和返回值均有类型注解，无 `Any` / `object` 逃逸。
- `hasattr` / `getattr`：未使用。
- README 更新：`dayu/fins/README.md` 和 `tests/README.md` 均按约束更新。
- pyright：0 errors。
- 覆盖率：`upload_batch.py` 96%，`fins.py` 90%，均达标。

## Findings

按 severity 排序。

### S6-REVIEW-F01（Low）：suffix allowlist 跨模块重复定义

**文件/行号：** `dayu/fins/upload_batch.py:19-36` 与 `dayu/cli/commands/fins.py:76-93`

**描述：** `_RECOGNIZED_UPLOAD_SUFFIXES` 和 `_ALLOWED_UPLOAD_FILE_SUFFIXES` 是两个独立定义但值完全相同的 `frozenset[str]`。违反 DRY 原则；若未来新增后缀，需要同步两处，容易遗漏。

**影响：** 维护风险。当前值一致，功能无误；但后续扩展时可能产生不一致。

**建议修复：** 在 `dayu.fins.upload_batch` 中导出 `RECOGNIZED_UPLOAD_SUFFIXES` 作为公共常量，CLI 层导入复用。或在 `dayu.cli.commands.fins` 中从 `upload_batch` 导入。

**Severity rationale：** Low——当前功能正确，不阻塞 review pass；属于可维护性改进。

### S6-REVIEW-F02（Low）：`_optional_stripped_text` 跨模块重复

**文件/行号：** `dayu/fins/upload_batch.py:350-363` 与 `dayu/cli/commands/fins.py:769-782`

**描述：** 两个模块各自定义了相同逻辑的 `_optional_stripped_text()` 辅助函数。与 F01 同属 DRY 问题。

**影响：** 维护风险。逻辑简单且一致，但重复代码增加维护负担。

**建议修复：** 提取到公共位置（如 `dayu.fins.upload_batch` 导出或 `dayu.cli` 内部 shared helper），或在 CLI 层导入 Fins helper。

**Severity rationale：** Low——功能正确，不阻塞 pass。

### S6-REVIEW-F03（Info）：`_run_upload_filings_from` 是同步函数，被 async 函数调用

**文件/行号：** `dayu/cli/commands/fins.py:224-234` 调用 `fins.py:249`

**描述：** `_run_fins_direct_command_async()` 是 async 函数，但 `_run_upload_filings_from()` 是同步函数，直接在 async context 中执行文件 I/O（`source_dir.rglob()` / `write_text()`）。对大目录可能阻塞事件循环。

**影响：** 当前 upload_filings_from 是唯一使用者，且 CLI 进程只有一个 async task，无实际阻塞风险。

**建议修复：** 无需修复。CLI 进程中只有一个 async task，同步 I/O 不影响正确性。若未来有并发需求，可用 `asyncio.to_thread()` 包装。

**Severity rationale：** Info——当前无实际影响，仅记录设计决策。

### S6-REVIEW-F04（Info）：output 写入到目录的错误路径无测试覆盖

**文件/行号：** `dayu/cli/commands/fins.py:286`

**描述：** 当 `--output` 指向一个已存在的目录时，`Path.write_text()` 会抛出 `IsADirectoryError`，被 `run_fins_direct_command()` 的 `except Exception` 捕获，exit 1。当前测试只覆盖了 `tmp_path`（目录）作为 output 路径的场景（`test_upload_filings_from_output_write_failure_exits_failure`），但未验证具体错误消息内容。

**影响：** 低。错误路径功能正确（exit 1 + stderr 输出），但测试断言只检查了 `"dayu-cli upload_filings_from:"` 前缀，未检查具体错误类型。

**建议修复：** 可选——在现有测试中补充 `assert "IsADirectory" in capsys.readouterr().err` 或类似断言。

**Severity rationale：** Info——功能正确，测试覆盖了 exit code 和错误前缀，不阻塞 pass。

## 审查通过项总结

| 审查维度 | 结论 |
|---|---|
| 业务语义迁移 | PASS：Fins typed boundary，不搬迁旧实现 |
| 不启动 ingestion job / Host Run / EventLog | PASS：测试断言禁止创建 Fins direct service |
| 结构化返回 + CLI quoting 分离 | PASS：Fins 返回 typed entry，CLI 用 shlex.join |
| CLI 不做业务识别 | PASS：识别是 upload_batch.py 职责 |
| Import boundary | PASS：AST 扫描验证，只导入标准库 |
| 错误语义 | PASS：exit 2/1/130 均有测试覆盖 |
| Recognition rule 保守性 | PASS：intentional deviation (RR-04) |
| AGENTS.md 编码约束 | PASS：中文 docstring、严格类型、无逃逸 |
| README 更新 | PASS：fins/README.md 和 tests/README.md 均按约束更新 |
| pyright | PASS：0 errors |
| 覆盖率 | PASS：upload_batch.py 96%，fins.py 90% |

## Residual risks

| 风险 | 分类 | 说明 |
|---|---|---|
| 文件名识别规则保守性 | deferred-with-owner (WU-CLI-01-RR-04) | 当前采用 Fins domain 可自洽的保守 token 识别；若需旧 CLI 完全 parity，由 Fins owner 定义更完整 typed recognition contract |
| suffix allowlist 跨模块重复 | non-blocking (S6-REVIEW-F01) | 当前值一致，后续扩展时需同步两处 |

## 结论

**PASS。** 无 blocking finding。4 个 findings 均为 Low 或 Info severity，不阻塞 review pass。S6 实现正确迁移了旧 `upload_filings_from` 的业务语义到当前 Fins typed boundary，满足 accepted plan 所有约束，错误语义、import boundary、测试覆盖率和 README 更新均达标。
