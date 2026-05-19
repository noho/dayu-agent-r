# P10.5 Aggregate Fix Completion - AgentCodex

## Scope

完成 controller adjudication AG1-AG4：

- `dayu.host` 包根不再导入或暴露低层 `start_run`、`create_host_command_handle`、`HostCommandHandle`。
- `dayu.host` 包根不再导入或暴露 command-handle construction types：`HostCommandFacet`、`HostCommandHandleOptions`。
- `dayu.host` 包根不再导入或暴露 `HostLocalExecutionOptions`。
- `dayu.host` 包根不再导入或暴露 `StartRunRequest`。

这些符号仍保留在低层边界：

- `dayu.host.api`：`HostCommandFacet`、`HostCommandHandleOptions`、`HostLocalExecutionOptions`、`StartRunRequest`。
- `dayu.host.command`：`HostCommandHandle`、`create_host_command_handle`、`start_run`。

## Changed Files

- `dayu/host/__init__.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_logging.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_public_resolve_wait_resume.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_cancel_late_result.py`
- `dayu/README.md`
- `dayu/host/README.md`
- `docs/reviews/phase10-5-aggregate-fix-codex-20260518.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_package_exports.py -q`：8 passed。
- `source .venv/bin/activate && pytest tests/host -q`：697 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors, 0 warnings, 0 informations。

## Residual Risk

- 本次只验证 `dayu/host` 与 `tests/host` 边界，未运行全仓测试。
- 工作区进入本任务前已有未提交的 controller / review 文档变更；本次未修改总控文档。
