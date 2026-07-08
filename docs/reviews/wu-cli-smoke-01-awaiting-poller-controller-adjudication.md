# WU-CLI-SMOKE-01 Awaiting Poller Controller Adjudication

## Scope

本 follow-up 修复 `dayu-cli interactive` 中 Fins download 已完成但 CLI 仍停在
`Activity: waiting` 的问题。用户提供的 debug log 已显示 SEC pipeline 完成多个
filing 下载，但 Host Run 没有从 `WAITING` 恢复。

## Root Cause

根因成立：Fins awaiting tool 只登记 lightweight observation handle 并返回
`ToolAwaitingOutcome`。Host 接受 awaiting fact 后创建 wait record，并将 Run 推进到
`WAITING`。后续恢复必须通过 `resolve_wait` 管线。此前 `dayu-cli interactive`
实际选择了 `start_fins_download` / `start_fins_preprocess`，Service 也已装配
`HostToolingOptions.wait_poll_adapter_registry`，但 entrypoint runtime 传给
`compose_open_host_options` 的 `ServiceAssemblyOverrides.wait_poller_policy` 仍为
`None`，导致 `open_host` 不启动 production wait poller。Fins observation terminal
后无人轮询 wait record，因此不会进入 `resolve_wait` 恢复。

## Accepted Fix

- 在 `dayu.service.host_assembly` 新增
  `with_entrypoint_wait_poller_policy(...)`。
- helper 基于本次 `PreparedSceneInputs.tool_selection.tool_names` 与
  `ServiceDiscoveredTools.effective_provider_configs` / `ToolBundle` 中可绑定的
  Fins awaiting 工具交集判断是否需要 poller。
- `tool_names=None` 表示 scene 暴露全量业务工具；若存在 Fins awaiting provider，
  启用 poller。
- 空工具选择或未选择 Fins awaiting 工具时保持 no-poller。
- 显式 `ServiceAssemblyOverrides.wait_poller_policy` 优先，不被自动补齐覆盖。
- `prepare_entrypoint_runtime(...)` 在 scene prepare 与 tool discovery 完成后调用
  该 helper，再组合 `OpenHostOptions`。

该方案符合设计真源：不让 Fins tool 直接通知 Host，不改变 Host 默认
`wait_poller_policy=None` 契约，不让 Engine 持有 wait / poller 生命周期，poller
仍只通过 `resolve_wait` command path 提交结果。

## Review Inputs

- Implementation artifact:
  `docs/reviews/wu-cli-smoke-01-awaiting-poller-fix-codex.md`
- AgentMiMo review:
  `docs/reviews/wu-cli-smoke-01-awaiting-poller-review-mimo.md`
- AgentDS review:
  `docs/reviews/wu-cli-smoke-01-awaiting-poller-review-ds.md`

## Findings Adjudication

| Finding | 裁决 |
|---|---|
| Root cause: CLI interactive did not enable production wait poller for selected Fins awaiting tools | accepted-fixed |
| Keep Host default no-poller contract | accepted |
| Keep Fins tool out of Host notification / resolve ownership | accepted |
| Use actual scene tool selection instead of CLI scene id branch | accepted-fixed |
| AgentDS ALL-mode over-enable concern | rejected-by-evidence; `_fins_awaiting_registry_inputs_from_provider_configs` already requires actual bindable Fins awaiting tools |
| Explicit `WaitPollerRuntimePolicy(enabled=False)` override lacks direct unit test | accepted-deferred; explicit override is preserved by first branch and current risk is low |
| Real SEC end-to-end validation not rerun by controller | accepted-residual; user manual validation remains the final signal for this environment-dependent path |

## Validation

- `pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q`
  - Result: `157 passed`, with existing third-party `edgar` deprecation warnings.
- AgentCodex also reported:
  - `pytest tests/service tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q`
  - Result: `265 passed`, with existing third-party `edgar` deprecation warnings.
- `python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors`.
- `git diff --check`
  - Result: passed.

## Final Decision

Accepted. No required code fix remains before user real-environment re-validation.
