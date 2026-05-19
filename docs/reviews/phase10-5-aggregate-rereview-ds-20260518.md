# P10.5 Aggregate Re-Review — AgentDS

## Verdict

**PASS** — AG1-AG4 aggregate fix 完整收口，blocking findings count = 0。

## Review Questions

### Q1 — dayu.host 包根不再作为模块属性或 `__all__` 暴露 AG1-AG4 低层符号

**PASS**。

证据：

- `dayu/host/__init__.py`：grep `start_run|create_host_command_handle|HostCommandFacet|HostCommandHandleOptions|HostLocalExecutionOptions|StartRunRequest` — 零命中。文件只从 `dayu.host.api` 导入 public API 类型、常量和 local worker protocols，从 `dayu.host.command` 导入 command facade function，从 `dayu.host.read_api` 导入 `get_run`/`get_session`，从 `dayu.host.open_host` 导入 `open_host`，从 `dayu.host.tooling` 导入工具输入边界类型。没有任何 AG1-AG4 涉及的符号出现在 import 语句或 `__all__` 中。
- `test_host_root_does_not_export_internal_services`：`FORBIDDEN_HOST_ROOT_EXPORTS` 包含 `HostCommandHandle`、`HostCommandFacet`、`HostCommandHandleOptions`、`HostLocalExecutionOptions`、`StartRunRequest`、`create_host_command_handle`、`start_run`、`HostEventStream`、`HostEventView`，且断言与 `vars(host)` 交集为空 — 通过。
- `test_removed_low_level_symbols_are_not_service_facing_all_exports`：`REMOVED_SERVICE_FACING_ALL_EXPORTS` 包含全部 AG1-AG4 目标符号及 `stream_run_events`，断言与 `host.__all__` 交集为空 — 通过。
- `test_removed_low_level_symbols_are_not_package_root_attributes`：同一 `REMOVED_SERVICE_FACING_ALL_EXPORTS` 断言与 `vars(host)` 交集为空 — 通过。

### Q2 — 低层测试改为从 dayu.host.api / dayu.host.command 导入，无兼容 re-export/wrapper

**PASS**。

证据：

- `tests/host/` 全量 grep `from dayu\.host import (start_run|create_host_command_handle|HostCommandHandle|HostCommandFacet|HostCommandHandleOptions|HostLocalExecutionOptions|StartRunRequest)` — 零命中。
- 需要低层符号的测试均从正确边界导入：
  - `HostCommandHandle`、`create_host_command_handle`、`start_run` → `from dayu.host.command import ...`（例如 `test_command_handle.py:52`、`test_public_cancel_session_runs.py:29`、`test_public_run_api.py:38`、`test_phase5_local_execution_integration.py:52`、`test_active_cancel_dispatch.py:50`、`test_public_event_stream.py:28`、`test_projection_read_model.py:30`、`test_logging.py:28`、`test_phase7_waiting_integration.py:55`、`test_public_steer.py:17`、`test_wait_adapter_polling.py:25`、`test_wait_cancel_late_result.py:23`、`test_public_session_api.py:27`、`test_public_resolve_wait_resume.py:10`、`test_resolve_wait_command.py:39`）
  - `HostCommandHandleOptions`、`HostLocalExecutionOptions`、`StartRunRequest`、`HostEventView`、`HostEventStream` → `from dayu.host.api import ...`（例如 `test_command_handle.py:47`、`test_public_cancel_session_runs.py:28`、`test_public_run_api.py:37`、`test_effective_execution_config.py:42`、`test_public_event_stream.py:27`、`test_projection_read_model.py:29`、`test_public_session_api.py:26`、`test_public_contracts.py:68`、`test_resolve_wait_command.py:38`）
- `dayu/host/__init__.py`：grep `re-export|wrapper|兼容|兼容性` — 零命中。不存在兼容 re-export 或透传 wrapper。

### Q3 — README 只描述当前 public contract，不把低层符号说成 root public surface

**PASS**。

证据：

- `dayu/README.md` 第 36-37 行："低层 command handle factory、`start_run`、`StartRunRequest`、command-handle construction types、`HostLocalExecutionOptions`、Host durable store、EventLog 内部实现、dispatch scheduler 实现、ToolRuntime 与 policy provider 不属于包根公共命名空间。" — 清晰声明 AG1-AG4 符号不在包根。
- `dayu/host/README.md` 第 7 行："低层同步 command handle、`start_run` / `StartRunRequest`、command-handle construction types、run-level event 补读与本地执行装配仍保留在内部模块路径，普通 Service 不应从包根依赖这些名字。" — 与实现一致。
- `dayu/host/README.md` 第 17 行："`HostLocalExecutionOptions` 是内部本地执行装配类型，不作为包根模块属性暴露。" — 明确 AG3 状态。
- `dayu/host/README.md` 第 19 行："`start_run` 与 run-level `stream_run_events` 已降级为低层 / diagnostic 路径，不再进入包根普通 Service-facing contract。" — 明确 AG1/AG4 状态。
- `dayu/host/README.md` 第 13-27 行包根导出列表不包含任何 AG1-AG4 目标符号。
- `dayu/host/README.md` 第 28 行："`dayu.host.api.__all__` 包含 request、snapshot、status、error、context、stream cursor、public opener options、HostEvent typed view，以及低层 `StartRunRequest`、command-handle construction types 与本地执行配置契约类型。" — 正确描述低层符号的保留位置（api 层而非包根）。

### Q4 — 是否引入新的 public contract、typing、import boundary、README mismatch 或测试缺口 blocker

**PASS** — 未发现新的 blocker。

详细检查：

- **新 public contract**：`dayu/host/__init__.py` 导出列表与 P10.5 冻结目标一致，未意外新增 public 符号。`__all__` 中每个符号在 `EXPECTED_HOST_EXPORTS` 测试中有对应期望项，反之亦然。
- **typing**：pyright `dayu/host tests/host` 0 errors, 0 warnings, 0 informations。无类型错误。
- **import boundary**：`test_import_boundary.py` 的 import 纪律守卫持续生效；无跨层反向 import。
- **README mismatch**：对比 `dayu/host/__init__.py` 的 `__all__` 与 README 导出列表 — 一致。README 描述的 `HostLocalExecutionOptions` 不作为包根模块属性暴露、`start_run`/`stream_run_events` 降级为低层路径，均与代码一致。
- **测试缺口**：`test_package_exports.py` 8 个测试覆盖白名单匹配、禁止导出、符号来源一致性、tooling/command 边界、移除符号的双重验证（不在 `__all__` 且不在 `vars(host)`）。测试足够覆盖 AG1-AG4 全部要求。
- **未覆盖项**（已知 residual，非 blocker）：
  - `HostEventView` / `HostEventStream` 仍在 `dayu.host.api.__all__`（controller 已 defer）。
  - 跨测试模块私有 helper 依赖（controller 已 defer 到 Phase 11）。
  - 未运行全仓测试（本次只验证 `dayu/host` + `tests/host`）。

## Verification

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py -q
# 8 passed

source .venv/bin/activate && pytest tests/host -q
# 696 passed, 1 skipped

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# (no output — no whitespace issues)
```

## Remaining Risk

- 全仓（非 host）测试未运行，若存在 Service/UI 层代码仍从 `dayu.host` 包根 import AG1-AG4 符号，会在其测试中暴露。按架构约束，Service/UI 层不应从包根依赖这些低层符号，此 risk 为低。
- `HostEventView` / `HostEventStream` 仍在 `dayu.host.api.__all__` 中，controller 已明确 defer，不阻塞本次 gate。
- 工作区在 aggregate fix 前已有未提交的 controller/review 文档，本次 re-review 仅验证代码变更，不审查文档变更质量。
