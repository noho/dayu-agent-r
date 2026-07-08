# WU-CLI-SMOKE-01 Awaiting Poller Fix - Codex

## 结论

本 follow-up bug fix 已完成。根因成立：`interactive` scene 已实际选择 `start_fins_download` / `start_fins_preprocess`，Service assembly 也已经为 Fins awaiting providers 绑定 `HostToolingOptions.wait_poll_adapter_registry`，但 `prepare_entrypoint_runtime` 传入 `compose_open_host_options(...)` 的 `ServiceAssemblyOverrides.wait_poller_policy` 仍为 `None`，导致 `open_host` 不启动 production wait poller。Fins SEC pipeline 完成后，没有 Host poller 观察 wait record，也就不会进入 `resolve_wait` 管线恢复 `WAITING` Run。

## 修复

- 在 `dayu.service.host_assembly` 新增 `with_entrypoint_wait_poller_policy(...)`。
- 判定依据是 `PreparedSceneInputs.tool_selection.tool_names` 与本次 `ServiceDiscoveredTools.effective_provider_configs` / `ToolBundle` 中可绑定的 Fins awaiting 工具交集。
- `tool_names=None` 表示 scene 暴露全量业务工具，若存在 Fins awaiting provider 则启用 poller。
- 空工具选择或未选择 Fins awaiting 工具时保持 no-poller。
- 显式传入的 `ServiceAssemblyOverrides.wait_poller_policy` 保持优先，避免覆盖调用方明确配置。
- `prepare_entrypoint_runtime(...)` 在 scene prepare 与 tool discovery 完成后调用该 helper，再组合 `OpenHostOptions`。

## 边界

- 未修改 Host 默认契约：`OpenHostOptions.wait_poller_policy=None` 仍不启动 poller。
- 未让 Fins tool 直接通知 Host；Fins completion 仍通过 `FinsIngestionWaitPollAdapter` 与 Host `resolve_wait` 管线恢复。
- 未让 Engine 持有 wait/poller 生命周期。
- 未按 CLI command 或 scene id 写魔法分支；`wechat` 等复用 `prepare_entrypoint_runtime` 且实际选择 Fins awaiting 工具的入口会自然覆盖。
- `prompt` 当前不选择 Fins awaiting 工具，保持 `wait_poller_policy is None`。

## 测试与验证

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_interactive_command.py -q`
  - 结果：`99 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/service tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q`
  - 结果：`265 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过

## 文档

- 更新 `dayu/service/README.md`：记录 product entrypoint helper 基于实际 scene 工具选择启用 production wait poller，prompt 等未选择长事务工具的 scene 保持 no-poller。
- 更新 `dayu/README.md`：同步 Service 总览边界。
- 更新 `tests/README.md`：同步新增 Service / entrypoint 覆盖。

## 残余风险

- 本轮没有依赖真实 SEC 网络做自动验证；自动验证停留在装配与入口路径。真实最小验证可用既有 provider credentials 运行 `dayu-cli interactive --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-manual/interactive.log`，输入“下载Visa财报”，观察 Fins completion 后是否出现 wait resolution / resumed terminal。
- Production poller 使用 Host `WaitPollerRuntimePolicy()` 默认轮询参数；本轮没有引入 entrypoint 专属短间隔。
