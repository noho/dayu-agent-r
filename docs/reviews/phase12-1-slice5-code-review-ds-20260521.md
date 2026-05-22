# Phase 12.1 Slice 5 Code Review

## Scope

- Mode: current changes (slice-scoped review)
- Branch: docs/phase12-design-discussion
- Base: main
- Output file: docs/reviews/phase12-1-slice5-code-review-ds-20260521.md
- Included scope:
  - `utils/smoke_host_public_multiturn.py`
  - `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - `tests/host/test_public_compact_smoke.py`
  - `README.md`
  - `tests/README.md`
  - `docs/host/implementation-control.md`
- Excluded scope: 其他不在 Slice 5 scope 内的文件变更
- Parallel review coverage: 无

## Verdict

**PASS**

## Findings

未发现实质性问题。

经逐条走读以下 review criteria 和对应代码路径，均未见违反：

### Criterion 1: smoke 默认路径使用 runtime assembly

`_prepare_runtime_assembly()`（`utils/smoke_host_public_multiturn.py:529`）调用链：
1. `resolve_runtime_locations(project_root, _PACKAGE_CONFIG_ROOT)` → `RuntimeLocations`（line 537）
2. `ConfigLoader(...).load(workspace_config_dir=locations.config_overlay_dir)` → `RuntimeConfig`（line 541）
3. `ToolsDiscovery().discover(...)` → `ToolsDiscoveryResult`（line 553）
4. `effective_tool_truncate_spec_from_policy(...)` 补齐截断默认值（line 556-559, helper at `dayu/runtime/assembly.py`）
5. `prepare_scene(ScenePrepareRequest(...))` → `PreparedSceneInputs`（line 560）
6. `select_runner_option_hint(...)` 选择 ordinary/compactor 模型（line 575, 583, helper at `dayu/runtime/assembly.py:262`）
7. `merge_agent_policy_config(...)` 合并 AgentPolicy（line 597, helper at `dayu/runtime/assembly.py`）
8. `provider_request_extension_from_json(...)` 解析 provider extension（line 1034, helper at `dayu/engine/provider_extensions.py:60`）

测试 `test_runtime_assembly_uses_workspace_tool_discovery_and_typed_overrides`（`tests/runtime/test_smoke_host_public_multiturn_assembly.py:38`）直接验证此完整链路。确认通过。

### Criterion 2: 删除 manual / old hardcoded assembly

`--assembly-mode manual/runtime` 参数已删除。命令行参数列表（`parse_args` line 356-440）只有 `workspace_root`、`scene_id`、`execution_profile_id`、`host_runtime_id`、`model_id`、`runner_option_hint_id` 等 typed override，不再有 assembly mode 选择器。

脚本内不再保留以下旧模式：
- 硬编码 DeepSeek runner spec / compactor spec
- 手工 mock `ToolBundle` 注入
- 脚本内 prompt asset / manifest root fallback
- 手工 provider extension parser（改用 `dayu.engine.provider_extensions.provider_request_extension_from_json`）
- 脚本内 system prompt guard（改用 `ScenePrepare` 输出 `system_messages`）

所有配置缺口（如默认 `tool_discovery.json` 中 provider disabled）会在调用 Host 前 fail fast（`ScenePrepareError: tool_tags_any matched no tools`），不用脚本默认值掩盖。

### Criterion 3: scene tool selection 在 discovered bundle 内选择子集

`_prepare_runtime_assembly` line 569-571：`SceneToolCatalog.from_tool_bundle(effective_tool_bundle)` 从已发现 bundle 投影出只含工具名与标签的目录。

`_compose_submit_followup_request`（line 761）的 `tool_names: frozenset[str] | None` 只传工具名集合；`SubmitFollowupRequest` 不包含 `ToolBundle`、`ToolDefinition`、callable 或 tool schema。

`_validate_tool_selection`（`dayu/runtime/scene_prepare.py:1118`）对 `select` 模式的 unknown tool names 抛出 `ScenePrepareError("unknown tool_names: ...")`（line 1129-1133），对 `tool_tags_any` 无匹配工具也 fail fast（line 1135-1138）。

### Criterion 4: diagnostics 在 Host 调用前输出

`_print_assembly_diagnostics`（line 1455）在 `_compose_open_host_options` 之前调用（`run_smoke` line 453-454），输出字段包括：
- `config_overlay`、`prompt_asset_root`、`scene_manifest_root`
- `host_runtime_id`、`execution_profile_id`
- `model_id` 与 `source`（来源层）
- `runner_option_hint_id` 与 `source`
- `compactor_model_id`、`compactor_runner_option_hint_id`
- `lane_name`
- `tool_provider_report`（每个 provider 一行）
- `tool_selection`（mode + names）
- `policy_refs`（context_budget / agent_policy_profile / tool_truncation）
- `agent_policy_sources`（每个字段:来源）
- `provider_extension_status`（ordinary / compactor 各自的模型:状态）
- `suggested_helpers`：`compose_open_host_options,compose_submit_followup_request,provider_extension_from_config`

confirmed: `AssemblyDiagnostics.suggested_helper_names`（line 998-1002）包含这三个 adapter/helper function 名称。

### Criterion 5: unknown override / unknown tool / unknown provider extension / disabled provider 均 fail fast

| 场景 | 入口 | 错误类型 | 位置 |
|------|------|----------|------|
| unknown override field | `parse_model_runner_hint_override` | `RuntimeAssemblyFieldError` | `dayu/runtime/assembly.py:243-247` |
| unknown model_id | `select_runner_option_hint` | `RuntimeAssemblySelectionError("model not found")` | `dayu/runtime/assembly.py:315-318` |
| unknown runner_option_hint_id | `select_runner_option_hint` | `RuntimeAssemblySelectionError("runner option hint not found")` | `dayu/runtime/assembly.py:320-323` |
| unknown tool names in scene | `_validate_tool_selection` | `ScenePrepareError("unknown tool_names")` | `dayu/runtime/scene_prepare.py:1129-1133` |
| unknown provider extension type | `provider_request_extension_from_json` | `ProviderExtensionConfigError("unsupported type")` | `dayu/engine/provider_extensions.py:91-93` |
| disabled provider | `ToolsDiscovery.discover` 跳过 disabled spec，scene `tool_tags_any` 无匹配时 `ScenePrepareError` | line 207 / scene_prepare.py:1135-1138 | 间接 fail fast |

均无静默 fallback。

### Criterion 6: public Host usage 只走 open_host(options) 和 Host handle

`run_smoke`（line 469）：`async with open_host(assembly.options) as host:` → `_PublicHostHandle`（`dayu/host/open_host.py:124`），通过 `ensure_session`、`submit_followup`、`watch_session_events`、`get_session` 等 `Host` 接口方法交互。不绕过 opener 直接操作 durable store、scheduler、admission 或 command handle。

### Criterion 7: context window fix 是测试 setup 修正

`tests/host/test_public_compact_smoke.py` 唯一改动：
- `_SOFT_CONTEXT_WINDOW_SIZE` 从 360 → 2400（line 30）
- 新增 `_SOFT_THRESHOLD_TOKENS = 70`（line 32）

这两个都是测试文件内的模块级常量，不影响任何生产代码。Host public contract（`open_host` → `_internal_reserved_output_tokens_for_policy` at `open_host.py:601`）和 Engine loop 均未修改。compact 语义未改变：测试仍验证真实 compactor 路径和 continuity。

### Criterion 8: README 同步用户可见当前事实

`README.md` diff 确认：
- 删除 `run.json` 引用，改为 `execution_profiles.json` / `host_runtime.json` / `tool_discovery.json`
- 删除 `llm_models.json` 引用，改为 `models.json`
- 模型配置说明改为当前 `models.json` + `execution_profiles.json` + scene manifest 的三层模型
- 保留"Host public 多轮闭环 smoke"入口和参数说明

`tests/README.md` diff 确认：
- 补充 `config_loader.py`、`scene_prepare.py`、`tools_discovery.py` 的 import boundary 覆盖声明
- 补充 config loader、runtime location、scene prepare、assembly helpers、scene asset migration 测试职责说明
- 无未来设计、版本记录或旧术语残留

### Criterion 9: strict typing / docstring / pyright / no Any/object

- `pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host` → **0 errors, 0 warnings, 0 informations**
- `utils/smoke_host_public_multiturn.py` 所有函数均有完整中文 docstring（参数、返回值、异常）
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py` 测试函数均有 docstring
- `git diff --check` → clean（无空白/冲突）

## Tests Run

```text
pytest tests/host/test_public_open_host_multiturn_smoke.py \
      tests/host/test_public_tool_wiring_smoke.py \
      tests/host/test_public_compact_smoke.py -q
→ 8 passed

pytest tests/runtime/test_config_loader.py \
      tests/runtime/test_scene_prepare.py \
      tests/runtime/test_tools_discovery.py \
      tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
→ 59 passed

python utils/smoke_host_public_multiturn.py --help
→ 退出码 0，参数列表完整

python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ clean
```

## Open Questions

无。

## Residual Risk

- **真实 provider 网络调用未验证**：默认 `tool_discovery.json` 的 `financial-tools` provider 为 disabled，真实 smoke 在 Host 调用前即 fail fast。若 workspace overlay 启用 provider 并配置有效 API key/quota/network，需要人工复跑三轮真实 smoke 验证端到端闭合。
- **Service assembly helper 提取延后**：`_compose_open_host_options`、`_compose_submit_followup_request` 仍为 smoke-local private adapter；diagnostics 已输出建议 helper 名称，但提取为正式 Service 层 helper 属于后续 work unit。
- **test_public_compact_smoke 小窗口测试覆盖缺失**：修复前的 360 token context window 已无法通过 opener 内部 command validation，但没有新增等价的小窗口专项测试；当前 2400 token 窗口的 compact 触发阈值已通过 `_SOFT_THRESHOLD_TOKENS=70` 保持小阈值语义，但极端小 context window（如 ≤1280 tokens）的 ratio-first policy behavior 没有专门覆盖。
