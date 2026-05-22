# Phase 12.2 Service Assembly Plan

## 动机判断

动机成立。`utils/smoke_host_public_multiturn.py` 仍把 SQLite write retry、payload inline threshold、worker startup timeout 等 `OpenHostOptions` construction-time 参数写成脚本私有常量；这些不是 smoke 业务逻辑，而是 Host runtime profile 的部署调优输入。继续留在 smoke 会让后续 Service 接入重复实现同一映射，也会把配置缺口藏在脚本里。

用户给定路径基本成立，但需要调整边界：`ConfigLoader` 只能继续输出层中立 typed config，不能构造 Host / Engine typed object；`dayu.runtime` 也不能导入 Host / Engine / Service。正式 helper 应放在新 `dayu.service` composition 边界内，由 Service 层导入 runtime、engine 与 host public contracts，完成 Host 外部 assembly。

## 模块落点

- 新增 `dayu/service/host_assembly.py`：正式 Service/composition helper。负责把 `RuntimeConfig`、`RuntimeLocations`、`ToolsDiscovery` 输出、`PreparedSceneInputs`、显式 override 与 env/secret mapping 转成 `OpenHostOptions` 和 `SubmitFollowupRequest`。
- 新增 `dayu/service/__init__.py` 与 `dayu/service/README.md`：声明 Service 只做 Host 外部 composition，不持有 Host truth。
- 不在 `dayu.runtime` 中创建 Host / Engine typed object，保持 runtime import boundary 不变。

## Schema 字段

在 `dayu/config/host_runtime.json` 的 runtime profile 中新增：

- `sqlite.write_busy_retry_count`
- `sqlite.write_retry_initial_delay_seconds`
- `sqlite.write_retry_backoff_multiplier`
- `sqlite.write_retry_max_delay_seconds`
- `payload_inline_threshold_bytes`
- `worker_startup_timeout_seconds`

依据：这些字段目前在 smoke `_compose_open_host_options(...)` 中硬编码，且直接映射到既有 `OpenHostOptions` 字段。`dispatch_poll_interval_seconds`、`memory_projection_catch_up_batch_size`、`truncation_manager_enabled`、`worker_backend` 已在 schema 中，无需重复设计。`create_parent_dirs=True` 和 compactor artifact parent dirs 属于本地 opener 稳定行为，不按本轮调优 schema 扩展。

`ConfigLoader` 只做 exact-field fail-fast 校验和 typed view 输出，不解释 worker factory、不解析 secret、不构造 Host。

## ScenePrepare 输出

在 `PreparedSceneInputs` 中新增 `system_prompt: str`，值为已渲染 `system_messages` 用空行连接的结果。保留 `system_messages` 用于 debug/source tracing。smoke 与 Service helper 后续使用 `scene_inputs.system_prompt`，不再各自 join。

## 允许修改文件

- `dayu/runtime/config_loader.py`
- `dayu/runtime/scene_prepare.py`
- `dayu/config/host_runtime.json`
- `dayu/service/__init__.py`
- `dayu/service/host_assembly.py`
- `dayu/service/README.md`
- `utils/smoke_host_public_multiturn.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_scene_prepare.py`
- 新增 focused Service helper tests under `tests/service/`
- README：按触发规则检查 `dayu/config/README.md`、`dayu/README.md`、`tests/README.md`
- `docs/reviews/phase12-2-service-assembly-implementation-codex-20260522.md`

## 验证计划

- `source .venv/bin/activate && pytest tests/runtime -q`
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q`
- `source .venv/bin/activate && pytest tests/service -q`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host dayu/service tests/runtime tests/engine tests/host tests/service utils/smoke_host_public_multiturn.py`
- `git diff --check`

## Blocking Questions

无阻塞问题。现有设计与控制文档已明确 Service / composition root 应在 Host 外部从 ConfigLoader、ScenePrepare、ToolsDiscovery 和 explicit override 装配 `OpenHostOptions` / `SubmitFollowupRequest`，且不得修改 Host public API 字段名。
