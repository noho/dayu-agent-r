# WU-CLI-SMOKE-01 util time + tag-only selection implementation

## 结论

status: completed

本轮动机成立：包内 `base/tools.md` 已提示 `get_current_time`，但新仓默认工具发现没有对应工具；默认财报 scene 也仍用显式 `tool_names` 白名单选择工具，不符合本 follow-up 要求。实现已按新架构把 util time tool 放在 `dayu.tools.utils` provider，经 `ToolsDiscovery` 和 `dayu/config/tool_discovery.json` 默认启用；未把工具注册放回 Engine。

## 改动

- 新增 `dayu.tools.utils` provider：
  - `get_current_time`
  - tags: `utils`, `time`
  - 默认且唯一支持 `Asia/Shanghai`
  - 返回 `time`、`timezone`、`weekday`、`iso`
  - 非法 timezone 返回 current `ToolFailedOutcome`
- 更新 `dayu/config/tool_discovery.json`，默认启用 `utils-tools`。
- 给 Fins read tools 增加窄 tag：`fins-read`，保留原 `fins` tag。
- 将 packaged scene manifest 的 `mode=select` 改为 tag-only：
  - 财报默认 scene 使用 `fins-read`、`fins-download`、`fins-preprocess`
  - 需要联网的 scene 继续使用 `web`
  - 默认 prompt / interactive 等 scene 增加 `utils`
  - 不使用 broad `fins` 选择，避免把 `start_fins_upload` 暴露给非上传 scene
- 更新 `base/tools.md` 中 `get_current_time` 指引，使参数、返回字段和禁止用途与真实工具一致。
- 更新 `dayu/config/README.md`、`dayu/fins/README.md` 中默认 provider / scene tool selection 说明。

## 直接证据

- `docs/host/design.md` 明确 `ToolsDiscovery` 属于 `dayu.runtime`，工具包通过 `ToolDefinition` 暴露工具集合，Host / Engine 不拥有工具发现或注册生命周期。
- `docs/engine/design.md` 明确 Engine 不负责工具注册、工具发现或财报业务语义。
- `dayu/config/prompts/base/tools.md` 原有 `<when_tool get_current_time>`，本轮前没有默认 provider 提供该工具。
- 默认 CLI 真实验证日志显示本轮 prompt 暴露 `tool_schema_count=14`，模型发起 `tool_name=get_current_time`，Host ToolRuntime 接受 completed tool fact。

## 验证

- `source .venv/bin/activate && pytest tests/tools/test_utils_tools_provider.py tests/fins/test_fins_storage_provider.py::test_fins_provider_discovers_read_tools_with_fins_read_tag tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py::test_default_runtime_config_files_load_as_typed_views tests/tools/test_combined_tools_acceptance.py::test_combined_discovery_returns_single_bundle_without_reserved_names tests/tools/test_combined_tools_acceptance.py::test_scene_prepare_tags_select_doc_fins_web_and_utils_tools tests/service/test_entrypoint_runtime_prompt_path.py::test_prompt_runtime_uses_real_prompt_manifest_required_slots tests/service/test_entrypoint_runtime_interactive_path.py::test_interactive_runtime_uses_real_manifest_required_slots tests/cli/test_prompt_command.py::test_prompt_command_outputs_fast_live_terminal_and_converts_requests -q`
  - result: `18 passed`
- `source .venv/bin/activate && pytest tests/tools/test_utils_tools_provider.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/runtime/test_scene_tool_selection.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/fins/test_fins_storage_provider.py -q`
  - result: `156 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed
- `source .venv/bin/activate && dayu-cli init --base workspace/tmp/wu-cli-smoke-time-workspace --overwrite`
  - result: passed
- `source .venv/bin/activate && dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-util-time.log prompt --base workspace/tmp/wu-cli-smoke-time-workspace --ticker AAPL "等待10秒后输出现在是什么时间"`
  - result: passed。CLI 输出最终答案：`现在是2026年07月07日 13:51:06（星期二）。`
  - log evidence: `workspace/tmp/wu-cli-smoke-01-util-time.log` contains `tool_name=get_current_time` and `tool_fact_kind=completed`.

## README 决策

- `dayu/config/README.md`: 已更新。命中 `dayu/config/` 修改触发；默认 `utils-tools` 与 tag-only scene selection 语义属于该 README 职责。
- `dayu/fins/README.md`: 已更新。命中 `dayu/fins/` 修改触发；`fins-read` 与避免 broad `fins` 误选 upload 属于 Fins provider / tags 事实。
- `tests/README.md`: 已检查，无需更新。本轮新增/修改测试仍在现有 `tests/runtime`、`tests/service`、`tests/cli`、`tests/tools`、`tests/fins` 分层内，没有新增测试层级、运行方式或维护规则。
- 根 `README.md`、`dayu/README.md`: 已按触发条件检查，本轮没有改变用户可见安装/入口命令/工作流，也没有改变跨层架构边界；无需更新。

## 剩余风险

- `ScenePrepare` 公共语义未改，workspace 自定义 scene 仍可使用 `tool_names`；本轮只通过 packaged manifest 测试约束包内默认资产。
- `get_current_time` 当前只支持 `Asia/Shanghai`，这是本 work unit 明确要求；其它时区需后续单独设计。
- 真实 CLI 验证使用本地可用 provider 凭据和当前时间，结果是一次真实环境 smoke，不替代长期 CI 中的 provider mock / contract 测试。
