# WU-CLI-01 / CLI-01-S6 Implementation Re-Review Controller Adjudication

## Gate / Scope

- Gate: re-review。
- Work unit: WU-CLI-01。
- Slice: CLI-01-S6，`upload_filings_from` batch plan generation。
- Controller review adjudication: `docs/reviews/wu-cli-01-s6-implementation-review-controller-adjudication.md`。
- Fix artifact: `docs/reviews/wu-cli-01-s6-implementation-fix-codex.md`。
- Re-review artifacts: `docs/reviews/wu-cli-01-s6-implementation-rereview-mimo.md`、`docs/reviews/wu-cli-01-s6-implementation-rereview-ds.md`。

## Controller Judgment

总控裁决：**PASS**。

两路 re-review 均确认 4 条 accepted findings 已修复，且 fix 未扩大到 controller rejected findings。S6 核心边界仍成立：Fins helper 返回结构化 plan，CLI 负责 shell quoting，不启动 ingestion job / Host Run，不导入 Host / Engine / Service / Fins storage。

## Accepted Findings Final Status

| Finding | Final status | Evidence |
|---|---|---|
| S6-REVIEW-F01 / S6-RV-F02：upload suffix allowlist 重复 | 已修复 | `FINS_UPLOAD_FILE_SUFFIXES` 已作为 `dayu.fins.upload_batch` public constant，并加入 `__all__`；`dayu/cli/commands/fins.py` 的 direct upload precheck 已复用该常量；旧 `_ALLOWED_UPLOAD_FILE_SUFFIXES` / `_RECOGNIZED_UPLOAD_SUFFIXES` 不再存在。 |
| S6-RV-F05：空 `--from` 错误路径无测试 | 已修复 | `tests/cli/test_upload_filings_from_command.py` 新增空 `--from` 返回 `EXIT_USAGE_ERROR` 并输出 `--from must not be empty` 的测试。 |
| S6-RV-F06：`material_forms` 空字符串错误路径无测试 | 已修复 | `tests/fins/test_upload_batch.py` 新增 `UploadBatchPlanRequest(material_forms=("",))` 抛 `UploadBatchPlanUsageError` 的测试。 |
| S6-RV-F07：`source_dir` 是普通文件错误路径无测试 | 已修复 | `tests/fins/test_upload_batch.py` 新增普通文件作为 `source_dir` 时抛 `UploadBatchPlanUsageError` 的测试。 |

## Scope Guard

- 未抽取 `_optional_stripped_text` 到 `dayu.runtime`。
- 未修改 recognition rule。
- 未修改 CLI async/sync 边界。
- 未修改 action cast、command name 常量比较或 output 具体错误文本断言。
- 未进入 S7 `init`、Host management commands 或旧 CLI parity。

## Validation

Controller 已复跑：

- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py -q`：31 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py --cov=dayu.fins.upload_batch --cov=dayu.cli.commands.fins --cov-report=term-missing -q`：31 passed；`dayu/fins/upload_batch.py` 97%，`dayu/cli/commands/fins.py` 90%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## Residual Risks

| Risk | Classification | Owner / Destination |
|---|---|---|
| 旧 CLI 完全 recognition parity | deferred-with-owner | Fins owner；沿用 `WU-CLI-01-RR-04` |
| `SUCCEEDED` direct command 输出缺少 `result_summary` 摘要 | deferred-with-owner | CLI / Fins product owner；沿用 `WU-CLI-01-RR-08` |
| 第三方 `edgar` deprecation warnings | known external | 非本次改动引入，不阻塞 S6 |

## Completion Status

CLI-01-S6 review loop passed. No accepted findings remain. Next gate: accepted slice commit for CLI-01-S6.
