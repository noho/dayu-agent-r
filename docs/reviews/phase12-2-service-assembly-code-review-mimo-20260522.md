# Code Review

## Scope

- Mode: current changes
- Branch: docs/phase12-design-discussion
- Base: main
- Output file: docs/reviews/phase12-2-service-assembly-code-review-mimo-20260522.md
- Included scope: Phase 12.2 service assembly 相关变更
- Excluded scope: docs/reviews/repo-review-20260522-070034.md, docs/reviews/repo-review-20260522-070045.md
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Summary

### 1. dayu.runtime 仍不 import host/engine/service/ui/fins

**结论**: PASS - 直接证据: `grep -r "from dayu.host\|from dayu.engine\|from dayu.service\|from dayu.ui\|from dayu.fins" dayu/runtime/` 返回空。`dayu/runtime/config_loader.py` 和 `dayu/runtime/scene_prepare.py` 只导入标准库、`dayu.contracts` 和 `dayu.runtime` 内部模块。新增 Service helper 位于 `dayu/service/host_assembly.py`，符合架构边界。

### 2. host_runtime 新增字段与 ConfigLoader fail-fast

**结论**: PASS - `host_runtime.json` 新增 6 个字段:
- `sqlite.write_busy_retry_count`
- `sqlite.write_retry_initial_delay_seconds`
- `sqlite.write_retry_backoff_multiplier`
- `sqlite.write_retry_max_delay_seconds`
- `payload_inline_threshold_bytes`
- `worker_startup_timeout_seconds`

ConfigLoader 对每个字段使用 `_require_positive_int_field` / `_require_positive_float_field` 做 fail-fast 校验，无兼容旧 schema。`_require_exact_fields` 确保未知字段加载失败。

### 3. ScenePrepare 直接输出 system_prompt

**结论**: PASS - `PreparedSceneInputs` 新增 `system_prompt: str` 字段（scene_prepare.py:378），值为 `"\n\n".join(rendered_messages)`（scene_prepare.py:512）。Service helper `compose_submit_followup_request` 直接使用 `scene_inputs.system_prompt`（host_assembly.py:347），不再自行 join。smoke 脚本也使用 `scene_inputs.system_prompt`（smoke_host_public_multiturn.py:346）。

### 4. dayu.service.host_assembly 是真正的 Service assembly helper

**结论**: PASS - `host_assembly.py` 是完整的 Service composition helper:
- `discover_service_tools(config)`: 从 ConfigLoader typed view 执行工具发现
- `compose_open_host_options(request)`: 把 RuntimeConfig、RuntimeLocations、PreparedSceneInputs、ServiceDiscoveredTools、ServiceAssemblyOverrides 与 env mapping 映射为 OpenHostOptions
- `compose_submit_followup_request(...)`: 把 PreparedSceneInputs.system_prompt 与本轮输入映射为 SubmitFollowupRequest

helper 不是薄兼容 facade，不把 raw patch dict 或 extra payload 偷渡进 Host。所有 Host public typed inputs 都通过显式字段映射生成。

### 5. smoke_host_public_multiturn 模拟真实 Service-like assembly

**结论**: PASS - smoke 脚本 `_prepare_runtime_assembly` 使用:
1. `resolve_runtime_locations` - runtime location resolver
2. `ConfigLoader().load()` - 配置加载
3. `discover_service_tools(config)` - 工具发现
4. `prepare_scene(ScenePrepareRequest(...))` - scene 装配
5. `compose_open_host_options(ServiceOpenHostAssemblyRequest(...))` - Service helper
6. `open_host(assembly.options)` - public Host handle
7. `compose_submit_followup_request(...)` - per-run request

脚本不写生产默认值遮住 schema 或 public contract 缺口。未发现工具时在调用 Host 前 fail fast（测试 `test_runtime_assembly_fails_before_host_when_tools_not_discovered` 验证）。

### 6. config/scene schema 到 Host public contracts 映射

**结论**: PASS - 映射链路清晰:
- ConfigLoader 输出 typed config view（RuntimeConfig）
- ScenePrepare 输出 typed scene inputs（PreparedSceneInputs）
- Service helper 映射为 Host public typed inputs（OpenHostOptions、SubmitFollowupRequest）

无摩擦项。所有 Host public contract 字段都通过显式映射填充，不需要额外 adapter helper。

### 7. 测试和 README 覆盖当前事实

**结论**: PASS - 测试覆盖:
- `tests/service/test_host_assembly.py`: 2 个测试覆盖 host_runtime schema 字段映射和 system_prompt 使用
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`: 3 个测试覆盖 smoke assembly 成功路径和未发现工具 fail-fast
- `tests/runtime/test_config_loader.py`: 208 个测试覆盖配置加载
- `tests/runtime/test_scene_prepare.py`: 覆盖 scene 装配

README 更新:
- `dayu/service/README.md`: 描述 Service composition 边界和当前入口
- `dayu/config/README.md`: 更新 host_runtime.json 字段说明
- `tests/README.md`: 更新测试分层说明

### 8. AGENTS.md 合规

**结论**: PASS - 直接证据:
- 中文 docstring: 所有新增函数和类都有中文 docstring
- 严格类型: 无 `Any`、`object` 签名，所有参数和返回值都有类型注解
- 无魔法字符串: `_WORKER_BACKEND_LOCAL`、`_ENV_PLACEHOLDER_PATTERN` 等常量使用 `Final` 定义
- 无反向依赖: `dayu.runtime` 不 import `dayu.service`

## Blocking Finding Count

0

## Open Questions

无

## Residual Risk

1. `dayu.service.host_assembly` 当前只支持 `worker_backend="local"`，remote worker backend 仍需单独设计
2. `create_parent_dirs=True` 与 compactor artifact parent dir creation 保持 Service helper 稳定默认，本轮未新增 schema 字段
3. 默认包内 `tool_discovery.json` 仍不会提供真实财报工具；真实财报 provider / Fins workflow 接入仍属于后续 Service / Fins work unit

## 验证结果

- `pytest tests/runtime -q`: 208 passed
- `pytest tests/service -q`: 2 passed
- `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: 3 passed
- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`: 8 passed
- `python utils/smoke_host_public_multiturn.py --help`: exit 0
- `python -m pyright dayu/service tests/service`: 0 errors
- `git diff --check`: clean
