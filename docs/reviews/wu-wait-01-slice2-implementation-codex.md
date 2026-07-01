# WU-WAIT-01 / issue-89 Slice 2 Implementation Artifact

## 实现结论

已实现 framework-neutral Service wait callback completion mapper，未实现真实 HTTP server、route registration 或 Web framework 绑定。

## 改动范围

- 新增 `dayu/service/wait_callback_endpoint.py`
  - 定义 `HeaderEntry`、`WaitCallbackHttpRequest`、`WaitCallbackHttpResponse`。
  - 定义 `handle_wait_callback_completion(request, adapter)`。
  - 校验 method、content-type、path/body wait id mismatch，并在 Service 层返回 `transport_rejected`。
  - 将 body JSON 与 headers/body transport 字段转换为 `WaitCallbackCompletionEnvelope`、`WaitCallbackAuthInput` 和现有 Host outcome dataclass。
  - 将 Host `WaitCallbackAdapterResult.status` 映射为 plan 指定 HTTP-like status code。
  - `AUTH_FAILED` 按 diagnostic/reason code 映射：missing/malformed/invalid/expired 等非认证成功为 401，forbidden/permission 类为 403。
  - response body 只包含 typed `status`、`diagnostic_code`、`message`、`retryable` 与可选 `run_id` / `run_status`，不回显 outcome payload。
- 新增 `tests/service/test_wait_callback_endpoint.py`
  - 覆盖 valid request、accepted/replayed、path/body mismatch、content-type、malformed outcome、四类 outcome dataclass 转换、AUTH_FAILED 401/403、adapter status mapping 和 payload 不回显。
- 更新 `tests/service/test_import_boundary.py`
  - 明确禁止 Service 导入 `dayu.host.durable` 与 FastAPI / Flask / Starlette / Django / aiohttp。
  - 补齐现有 approved Fins Service boundary allowlist，避免新边界测试误伤既有 Service assembly。
- 更新 `dayu/service/README.md` 与 `tests/README.md`
  - 记录新增 Service mapper 入口与测试覆盖范围。

## README 判断

- `dayu/service/README.md`：命中 `dayu/service/` 修改触发；新增 mapper 是 Service 稳定入口，属于 README 当前读者范围，已更新。
- `tests/README.md`：命中 `tests/` 修改触发；新增 service 测试类型属于测试分层事实，已更新。
- 根 README 与 `dayu/README.md`：未暴露真实用户可见 route、CLI/Web 命令或分层关系变更，不更新。
- `docs/host/issues-implementation-control.md`：按任务禁止项未修改。

## 验证

- `source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py -q`
  - 28 passed
- `source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q`
  - 29 passed
- `source .venv/bin/activate && pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
  - 56 passed
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - passed

## 风险与未覆盖项

- 本 slice 只提供 framework-neutral mapper，不提供真实 HTTP route、secret backend、HMAC/bearer verifier 或 Web app assembly；这些仍属于后续 Service/Web deployment owner。
- Host 现有 `ToolCancelledOutcome.reason` 是封闭集合；mapper 对不可表达的 cancelled reason fail closed 为 `malformed_payload`，不做兼容别名。
- failed/cancelled outcome 的 `meta` 仅接受现有 `ToolResultMeta` 可表达形态；任意 provider-specific meta 不进入 Host outcome dataclass。
