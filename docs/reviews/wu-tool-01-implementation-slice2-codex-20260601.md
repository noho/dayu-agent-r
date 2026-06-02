# WU-TOOL-01 Implementation Slice 2 Report

## Changed Files

- `dayu/host/tooling.py`
- `dayu/host/dispatch.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-tool-01-implementation-slice2-codex-20260601.md`

## Implemented Items

- `HostToolingOptions` 新增 `duplicate_governance_policy`，默认使用 `DuplicateGovernancePolicy` 的 `default_factory`。
- `HostToolingOptions.__post_init__` 校验 `duplicate_governance_policy` 必须是 `DuplicateGovernancePolicy` 实例，未使用 lazy import 或兼容 re-export。
- `HostDispatchScheduler` 在构造 `ToolRuntimeBuildRequest` 时传入 `tooling_options.duplicate_governance_policy`。
- `test_tooling_options.py` 覆盖默认 policy、零配置默认消息、custom message policy、custom justification 参数名、空消息与空 argument name validation、非法 policy 类型校验。
- `test_dispatch_scheduler.py` 将 reactive recovery duplicate 行为测试改为 attempt-scoped 行为证明：同一 Attempt 内 custom `reuse` policy 生效；reactive recovery 接收的新 snapshot 有新 `attempt_id`；第二个 Attempt 中同 tool/args 作为 fresh request 真实执行，不访问私有 duplicate state。
- 清理 scheduler close lifecycle matrix 中旧 duplicate registry cleanup 文案。

## Tests Run

- `source .venv/bin/activate && python -m pytest tests/host/test_tooling_options.py tests/host/test_dispatch_scheduler.py`
  - Result: `70 passed`

## Pyright Result

- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

- 本 slice 不更新 README。按 approved plan，README 同步放在 Slice 4；本次变更未改变用户命令、配置入口文档或已发布 README 的稳定说明。

## Terminology Check

- duplicate governance 相关源码/测试未残留 run-scoped/run-local/RunScoped/RunLocal/同 Run 语义。
- `rg` 仍能在 `tool_runtime.py` 命中 `run-scoped` / `run-local`，均为 truncation / fetch_more cursor 相关文案，不属于 duplicate governance，本 slice 按计划不修改。
- `registry` 命中均为 active worker registry 或 wait adapter registry，不是 duplicate governance registry。

## Residual Risks

- `TOOL_CALL_GOVERNED` payload 与 tool trace summary 的 machine-readable attempt scope 仍属于 Slice 3，未在本 slice 处理。
- README 中 Host duplicate governance 的稳定说明仍按 Slice 4 统一同步。

## Stop Conditions

- 未触发 stop condition。`HostToolingOptions` 从 `dayu.host.tool_duplicate_governance` 直接导入 `DuplicateGovernancePolicy` 未产生 import cycle。
