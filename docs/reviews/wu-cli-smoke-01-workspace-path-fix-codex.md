# WU-CLI-SMOKE-01 Workspace Path Public Contract Fix

## 背景

用户在真实 `dayu-cli prompt` 运行后观察到 `workspace/workspace` 被创建，并指出目录位置应收敛为 public contracts，避免在多个层级硬编码 `workspace`。

## 根因

问题不是单个 CLI cursor 文件路径，而是路径契约混淆：

- `--base` 解析后的路径已经是 workspace root。
- 旧 `resolve_runtime_locations` 把该路径当成 project root，再拼接 `workspace/config`。
- CLI terminal cursor 曾在 workspace root 下再拼 `workspace/.dayu/cli`。
- Web tools 默认 storage state 配置写成 `workspace/.dayu/...`，未在 Service effective config 阶段解析到 workspace root。

## 修复

- 新增 `dayu.runtime.workspace_paths`，提供层中立 workspace path public contract。
- `resolve_runtime_locations` 改为默认探测 `<workspace_root>/config`。
- `dayu-cli init`、CLI terminal cursor、Host assembly 相对路径解析改为复用 runtime public contract。
- 默认 Web tools `playwright_storage_state_dir` 改为 `.dayu/web_tools_storage_states`，并由 Service effective provider config 解析为 `<workspace_root>/.dayu/web_tools_storage_states`。
- 更新 README 与测试 fixture，使 `workspace/config` 的描述明确表示默认 `--base ./workspace` 下的用户可见路径，而不是在 workspace root 下再嵌套一层。

## 验证

- AgentCodex 受影响主路径测试：`236 passed`，仅第三方 `edgar` deprecation warnings。
- AgentCodex 补充受影响测试：`91 passed`，仅第三方 `edgar` deprecation warnings。
- AgentCodex `pyright`：`0 errors`。
- Controller 复核：
  - `pytest tests/runtime/test_workspace_paths.py tests/runtime/test_runtime_location.py tests/cli/test_session_terminal_cursor.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/service/test_host_assembly.py -q`：`125 passed`，仅第三方 `edgar` deprecation warnings。
  - `pyright`：`0 errors`。
  - `git diff --check`：通过。
  - 真实 `dayu-cli prompt --base workspace/tmp/wu-workspace-path-real-20260708 ...`：HTTP 200 真实模型调用完成，fresh base 下 `test ! -e <base>/workspace` 通过，状态文件落在 `<base>/.dayu/...`。

## Residual Risk

- 不迁移旧 `<workspace_root>/workspace/.dayu/cli/terminal_cursors.json`。旧 cursor 只影响 startup backfill 去重水位，影响有限。
- 不删除用户已有 `workspace/workspace` 残留目录。
- 如果用户曾把 workaround 配置放在 `<workspace_root>/workspace/config`，新契约不会读取该旧错误路径；正确路径是 `<workspace_root>/config`。
