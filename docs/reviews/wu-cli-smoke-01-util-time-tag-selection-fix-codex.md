# WU-CLI-SMOKE-01 util time + tag-only selection fix

## 结论

status: completed

本 fix gate 只处理 controller adjudication 中的两个 accepted findings。动机成立：`infer.json` 的 tag-only 迁移相对旧显式 `tool_names` 缩小了工具暴露面，且没有设计依据；`get_current_time` 对非字符串 `timezone` 返回空字符串会产生不可恢复性较差的 LLM-facing 错误消息。

## 修复内容

### Accepted finding A

- 修复 `dayu/config/prompts/manifests/infer.json`：
  - 保持 tag-only：`tool_names=[]`。
  - `tool_tags_any` 改为 `fins-read`、`fins-download`、`fins-preprocess`、`utils`。
  - 未加入 `web`，因为旧 infer manifest 没有 web 工具暴露面。
- 更新 `tests/runtime/test_scene_assets_migration.py`：
  - fake catalog 加入 `start_fins_upload`，让排除断言有真实负例。
  - 新增 `test_infer_manifest_selects_read_download_preprocess_and_utils_without_upload`，验证 infer 选择 read/download/preprocess/utils，且不选择 `start_fins_upload` 或 web。

### Accepted finding B

- 修复 `dayu/tools/utils/provider.py`：
  - `_timezone_argument` 对缺省值仍返回 `Asia/Shanghai`。
  - 对非字符串 `timezone` 返回 `None`，由调用方转为 `ToolFailedOutcome(error="invalid_argument")`。
  - LLM-facing message 改为明确类型错误：`timezone 参数类型错误：必须是字符串，或省略以使用 Asia/Shanghai。`
- 更新 `tests/tools/test_utils_tools_provider.py`：
  - 新增非字符串 `timezone` 用例，验证仍返回 `ToolFailedOutcome`，并包含清晰类型错误 message 和可恢复 hint。

### Controller-found follow-up fix

- 修复 `dayu/tools/utils/provider.py`：
  - `started_at` / `finished_at` 元信息改用标准库 UTC aware 时间，不再通过 `ZoneInfo(DEFAULT_TIMEZONE)` 构造。
  - 业务时区加载仍在参数校验之后执行；`ZoneInfo(timezone)` 抛出 `ZoneInfoNotFoundError` 时返回 `ToolFailedOutcome(error="timezone_load_failed")`。
  - 成功路径、unsupported timezone、非字符串 timezone 行为保持不变。
- 更新 `tests/tools/test_utils_tools_provider.py`：
  - 新增 monkeypatch 用例，模拟 provider 内 `ZoneInfo` 抛 `ZoneInfoNotFoundError`，验证 callable 返回 `ToolFailedOutcome(error="timezone_load_failed")` 且不抛异常。

## 未处理项

- 按 controller 要求，未处理既有格式化 noise。
- 未做 commit / push / PR。

## 验证

- `source .venv/bin/activate && pytest tests/tools/test_utils_tools_provider.py tests/runtime/test_scene_assets_migration.py::test_packaged_select_manifests_use_tag_only_tool_selection tests/runtime/test_scene_assets_migration.py::test_infer_manifest_selects_read_download_preprocess_and_utils_without_upload -q`
  - result: `6 passed`
- `source .venv/bin/activate && pytest tests/tools/test_utils_tools_provider.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/runtime/test_scene_tool_selection.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/fins/test_fins_storage_provider.py -q`
  - result: `158 passed, 3 warnings`
  - warnings: 仅来自 `edgar` 依赖的 deprecation warnings。
- `source .venv/bin/activate && pytest tests/tools/test_utils_tools_provider.py -q`
  - result: `5 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed

### Controller-found follow-up validation

- `source .venv/bin/activate && pytest tests/tools/test_utils_tools_provider.py -q`
  - result: `5 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed

## README 决策

- `dayu/config/README.md`: 已检查，无需更新。本次只是把 `infer` 恢复为文档已描述的非上传 scene 窄标签选择规则。
- `tests/README.md`: 已检查，无需更新。本次没有新增测试层级、运行方式或维护规则。

## 剩余风险

- fixed in current slice: `infer.json` 旧工具暴露面恢复为 read/download/preprocess/utils，并通过 packaged manifest 测试覆盖。
- fixed in current slice: 非字符串 `timezone` 不再生成空时区错误消息，并通过 provider 单测覆盖。
- assigned to later work unit: `get_current_time` 仍只支持 `Asia/Shanghai`，如需支持其它时区，应单独设计 schema、prompt 指引和运行时校验。
- assigned to later work unit: workspace 自定义 scene 仍可自行使用 broad `fins` tag；本轮只约束包内 packaged manifest。
