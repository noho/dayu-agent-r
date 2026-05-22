# Phase 12.2 Service Assembly Implementation Artifact

## Scope

- 当前 work unit：Phase 12.2 follow-up plan + implementation handoff。
- 未执行：commit、push、PR、PR comment、full gateflow。
- Plan artifact：`docs/reviews/phase12-2-service-assembly-plan-codex-20260522.md`。

## 动机判断

动机成立。`utils/smoke_host_public_multiturn.py` 原先把 SQLite write retry、payload inline threshold、worker startup timeout 等 Host construction tuning 写成脚本私有常量；这些字段直接进入 `OpenHostOptions`，应由 Host runtime profile 配置驱动，再由 Host 外部 Service composition helper 映射为 typed input。

## 实现摘要

- 扩展 `host_runtime.json` schema：
  - `sqlite.write_busy_retry_count`
  - `sqlite.write_retry_initial_delay_seconds`
  - `sqlite.write_retry_backoff_multiplier`
  - `sqlite.write_retry_max_delay_seconds`
  - `payload_inline_threshold_bytes`
  - `worker_startup_timeout_seconds`
- `ConfigLoader` 保持层中立，只加载与校验 typed config view；不构造 Host / Engine typed object，不解析 secret。
- `PreparedSceneInputs` 新增 `system_prompt`，保留 `system_messages` 用于 debug/source tracing。
- 新增 `dayu.service.host_assembly`：
  - `discover_service_tools(config)`
  - `compose_open_host_options(request)`
  - `compose_submit_followup_request(...)`
  - helper 在 Service 边界内把 runtime config、locations、工具发现、prepared scene、explicit override 与 env/secret mapping 转为 `OpenHostOptions` / `SubmitFollowupRequest`。
- `utils/smoke_host_public_multiturn.py` 删除 smoke-local Host opener adapter，改用正式 Service helper；per-run request 直接使用 `PreparedSceneInputs.system_prompt`。

## Changed Files

- `README.md`
- `dayu/README.md`
- `dayu/config/README.md`
- `dayu/config/host_runtime.json`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/scene_prepare.py`
- `dayu/service/__init__.py`
- `dayu/service/README.md`
- `dayu/service/host_assembly.py`
- `tests/README.md`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_scene_prepare.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/service/__init__.py`
- `tests/service/test_host_assembly.py`
- `utils/smoke_host_public_multiturn.py`
- `docs/reviews/phase12-2-service-assembly-plan-codex-20260522.md`
- `docs/reviews/phase12-2-service-assembly-implementation-codex-20260522.md`

## Validation

- `source .venv/bin/activate && pytest tests/runtime -q`
  - 结果：208 passed。
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q`
  - 结果：11 passed。
- `source .venv/bin/activate && pytest tests/service -q`
  - 结果：2 passed。
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`
  - 结果：8 passed。
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - 结果：通过，退出码 0。
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host dayu/service tests/runtime tests/engine tests/host tests/service utils/smoke_host_public_multiturn.py`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

## Residual Risk

- `dayu.service.host_assembly` 当前只支持 `worker_backend="local"`，与现有 default config 和 smoke-local adapter 行为一致；remote worker backend 仍需单独设计。
- `create_parent_dirs=True` 与 compactor artifact parent dir creation 保持 Service helper 稳定默认，本轮未新增 schema 字段。
- 默认包内 `tool_discovery.json` 仍不会提供真实财报工具；真实财报 provider / Fins workflow 接入仍属于后续 Service / Fins work unit。

## Untouched Files

- 预先存在的 untracked repo review artifacts 保持未触碰。

## Fix Addendum — DS Finding 1

### Scope

- 当前 gate：Phase 12.2 service assembly code review accepted fix。
- Source review artifact：`docs/reviews/phase12-2-service-assembly-code-review-ds-20260522.md`。
- Controller accepted finding：DS Finding 1，`_agent_fallback_mode_from_config` 手工 if/elif 映射应改为 `AgentFallbackMode(value)`。
- 明确 deferred/out-of-scope：DS Finding 2 根 README 死链，本轮未修复。

### Fix Summary

- `dayu/service/host_assembly.py`
  - `_agent_fallback_mode_from_config` 改为直接返回 `AgentFallbackMode(value)`。
  - 合法值继续由 Engine enum 映射，非法值继续由 enum 构造抛出 `ValueError`。
- `tests/service/test_host_assembly.py`
  - 新增 focused 测试覆盖 `"force_answer"`、`"raise_error"` 的 enum 映射，以及非法值保持 `ValueError` 语义。

### Validation

- `source .venv/bin/activate && pytest tests/service -q`
  - 结果：3 passed。
- `source .venv/bin/activate && python -m pyright dayu/service tests/service`
  - 结果：0 errors, 0 warnings, 0 informations。

### Residual Risk

- 无新增 residual risk。
- `fallback_mode` 在 runtime schema 侧仍需因 runtime 不得依赖 Engine enum 而保留独立字符串校验；这属于既定分层约束，不在本轮 fix 范围内。
