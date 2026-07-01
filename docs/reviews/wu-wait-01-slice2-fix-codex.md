# WU-WAIT-01 / issue-89 Slice 2 Fix Artifact

## 修复范围

- 修复 `S2-CR-F01`：
  - `handle_wait_callback_completion(...)` 在调用 Host adapter 前检查 request id。
  - 当 `X-Dayu-Callback-Request-Id` header 与 body `request_id` 均缺失时，Service 层返回 HTTP-like `400`，`diagnostic_code="missing_request_id"`，不构造 Host envelope，不调用 adapter。
  - `_request_id_from_transport(...)` 不再把缺失 request id 折叠为字面值 `"missing"`；若预检以外路径仍缺失，会 fail closed 为 malformed payload。
  - 保留 header 优先于 body 的策略，并覆盖 body fallback request id。
- 修复 `S2-CR-F02`：
  - 补充 non-POST method、non-object body、unknown outcome kind、invalid timestamp、unsupported cancelled reason 的直接 fail-closed 测试。
  - 补充 `run=None` response 不输出 `run_id` / `run_status` 的直接测试。

## README 判断

- `dayu/service/README.md`：已描述 `wait_callback_endpoint` 的 Service mapper 边界、transport rejection、malformed payload 与 response body 形态。本次只是修正同一 mapper 内的缺失 request id 诊断，不新增稳定入口或真实 route，不更新。
- `tests/README.md`：已描述 `tests/service/` 中 wait callback endpoint 覆盖 method / content-type / path-body transport rejection、malformed outcome shape、headers/body envelope 映射和 adapter status 映射。本次是同一测试层级内补充分支守卫，不新增测试层级，不更新。
- 根 README 与 `dayu/README.md`：未改变用户可见 CLI/Web 入口、安装方式、工作流、真实路由或分层关系，不更新。
- `docs/host/issues-implementation-control.md`：按任务禁止项未修改。

## 验证

- `source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q`
  - `47 passed`
- `source .venv/bin/activate && pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
  - `56 passed`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
  - pyright 仅输出新版本提示。
- `git diff --check`
  - passed

## 残余风险

- 本 fix 仍只覆盖 framework-neutral Service mapper，不提供真实 HTTP route、Web framework 绑定、secret backend、HMAC/bearer verifier 或生产 callback deployment。
- 缺失认证字段仍按既有设计传给 adapter/authenticator 分类；本次只把非认证字段 `request_id` 的缺失从不可区分 sentinel 改为 Service 层确定拒绝。
- header casing、重复 header、payload ref / provider status ref 更细粒度非法 shape 等低优先级测试缺口仍按 controller adjudication 归为后续 Web route hardening 范围。
