# WU-CLI-01 / CLI-01-S6 Implementation Fix Report

## Gate

- 当前 gate：fix。
- Slice：CLI-01-S6 `upload_filings_from` batch plan generation。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- Accepted plan：`docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- Controller adjudication：`docs/reviews/wu-cli-01-s6-implementation-review-controller-adjudication.md`。

## First-principles judgment

Accepted findings 成立。

- upload 输入后缀是 Fins upload boundary 的业务规则。Batch plan 扫描和 CLI direct upload precheck 分别定义同一 allowlist，会让未来新增或移除后缀时出现 direct upload 与 batch plan 漂移。真源应收敛到 Fins public constant，CLI 只复用该 boundary。
- 三条测试缺口都对应当前已有错误分支：空 `--from`、`material_forms` 空字符串、`source_dir` 是普通文件。补测试可以固定用法错误语义，不需要改变识别规则或 CLI async/sync 边界。

## Changed files

- `dayu/fins/upload_batch.py`
  - 将 upload 输入后缀集合提升为 public constant `FINS_UPLOAD_FILE_SUFFIXES`。
  - `generate_upload_batch_plan(...)` 复用该 public constant。
  - 将 `FINS_UPLOAD_FILE_SUFFIXES` 加入 `__all__`。
- `dayu/cli/commands/fins.py`
  - 移除 CLI 本地重复后缀 allowlist。
  - direct upload file precheck 改为复用 `dayu.fins.upload_batch.FINS_UPLOAD_FILE_SUFFIXES`。
- `tests/fins/test_upload_batch.py`
  - 补充 `source_dir` 为普通文件时抛 `UploadBatchPlanUsageError`。
  - 补充 `UploadBatchPlanRequest(material_forms=("",))` 抛 `UploadBatchPlanUsageError`。
- `tests/cli/test_upload_filings_from_command.py`
  - 补充空 `--from` 返回 `EXIT_USAGE_ERROR`。
- `dayu/fins/README.md`
  - 最小同步 `FINS_UPLOAD_FILE_SUFFIXES` 是 upload 输入后缀真源。

## Fixed findings

- Fixed：S6-REVIEW-F01 / S6-RV-F02，upload suffix allowlist 已收敛到 Fins boundary 的单一 public constant，CLI direct upload precheck 已复用。
- Fixed：S6-RV-F05，空 `--from` 错误路径已测试，返回 exit 2。
- Fixed：S6-RV-F06，`material_forms` 含空字符串错误路径已测试，抛 `UploadBatchPlanUsageError`。
- Fixed：S6-RV-F07，`source_dir` 是普通文件错误路径已测试，抛 `UploadBatchPlanUsageError`。

## Scope guard

本 fix gate 未处理 controller rejected findings，未扩 scope：

- 未抽取 `_optional_stripped_text` 到 `dayu.runtime`。
- 未修改 recognition rule。
- 未修改 CLI async/sync 边界。
- 未修改 action cast、command name 常量比较或 output 具体错误文本断言。
- 未进入 S7 init、Host management commands 或旧 CLI parity。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py -q`
  - 结果：31 passed，3 warnings（第三方 `edgar` deprecation warnings）。
- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py --cov=dayu.fins.upload_batch --cov=dayu.cli.commands.fins --cov-report=term-missing -q`
  - 结果：31 passed，3 warnings。
  - `dayu/fins/upload_batch.py` 覆盖率：97%。
  - `dayu/cli/commands/fins.py` 覆盖率：90%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors，0 warnings，0 informations。
- `git diff --check`
  - 结果：通过，无输出。

## README decision

- 已更新 `dayu/fins/README.md`：因为 `FINS_UPLOAD_FILE_SUFFIXES` 是新增 Fins public constant，需要在 Fins package developer boundary 中最小说明。
- 未更新 `tests/README.md`：本次只补已有测试层的错误路径覆盖，当前 README 已说明 CLI Fins direct tests 覆盖 `upload_filings_from` 错误码，不需要机械扩写。

## Residual risks

- `deferred-with-owner`：旧 CLI 完全 recognition parity 仍沿用 `WU-CLI-01-RR-04`，本 fix gate 未改变当前保守识别规则。
- `deferred-with-owner`：`SUCCEEDED` direct command 输出缺少 `result_summary` 摘要仍沿用 `WU-CLI-01-RR-08`，本 fix gate 未进入 direct job output 设计。
- `known external warning`：验证中仍有第三方 `edgar` deprecation warnings，非本次改动引入。

## Completion status

CLI-01-S6 accepted findings fix 完成。未 commit、未 push、未打开 PR，未进入 re-review gate。
