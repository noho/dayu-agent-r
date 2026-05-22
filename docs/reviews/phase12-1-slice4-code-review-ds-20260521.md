# Phase 12.1 Slice 4 Code Review

## Scope

- **Mode**: current changes（Slice 4 intended files）
- **Branch**: docs/phase12-design-discussion
- **Base**: main
- **Output file**: docs/reviews/phase12-1-slice4-code-review-ds-20260521.md
- **Included scope**:
  - `dayu/engine/provider_extensions.py`
  - `dayu/runtime/assembly.py`
  - `dayu/runtime/__init__.py`
  - `tests/engine/test_provider_extension_config_adapter.py`
  - `tests/runtime/test_assembly_helpers.py`
  - `tests/runtime/test_import_boundary.py`
  - `tests/runtime/test_weak_typing_guard.py`
  - `dayu/engine/README.md`
  - `tests/README.md`
  - `docs/host/implementation-control.md`
- **Excluded scope**（pre-existing dirty, not reviewed as Slice 4 findings）:
  - `README.md`
  - `utils/smoke_host_public_multiturn.py`

## Verdict: PASS

未发现阻塞级或实质性问题。

## Findings

未发现实质性问题。

逐项审查结论：

### 1. dayu.runtime.assembly 层中立性 — 通过

`assembly.py` 的 import 仅包含：`math`、`collections.abc.Mapping`、`dataclasses`、`typing`（stdlib）、`dayu.contracts`（公共契约）、`dayu.runtime.config_loader`、`dayu.runtime.scene_prepare`、`dayu.runtime.tool_truncation`。无 Engine/Host/Service/UI/Fins 导入。

返回类型全部为 `dayu.runtime.assembly` 自有 dataclass 或 `dayu.runtime.config_loader` / `dayu.runtime.scene_prepare` 的 runtime-neutral typed config。测试 `test_runtime_assembly_helpers_do_not_construct_host_or_engine_objects`（`test_assembly_helpers.py:192-224`）通过运行时 module 前缀检查确认返回值不来自 `dayu.engine` 或 `dayu.host`。

`dayu/runtime/__init__.py` 在包概览中描述了 `assembly` 模块，包根不做 re-export（`__all__: list[str] = []`）。

### 2. Override 语义 — 通过

`_select_value`（`assembly.py:640-662`）固定四层优先级：`run_value > scene_value > baseline_value > default_value`，字段独立合并。未知字段通过 `_require_exact_field_names`（`assembly.py:679-695`）fail fast。所有 dataclass 使用 `frozen=True, slots=True`，无 `**kwargs` / extra payload 袋。

### 3. Runner option hint 选择 — 通过

`select_runner_option_hint`（`assembly.py:262-336`）从 `model.runtime_hints.runner_option_hints` 字典查找 hint，缺失时以包含 model_id 和 hint_id 的结构化消息抛出 `RuntimeAssemblySelectionError`。测试覆盖正向四层优先级（`test_assembly_helpers.py:45-74`）和缺失快速失败（`:77-106`）。

### 4. Agent policy 合并 — 通过

白名单字段 `_AGENT_POLICY_OVERRIDE_FIELDS`（`assembly.py:54-65`）覆盖 8 个字段。`fallback_mode` 在 `merge_agent_policy_config` 入口处对 `code_default` 和 `execution_profile` 做 `_validate_fallback_mode` 校验（`:426-434`）；scene 层 fallback_mode 来自 `SceneAgentFallbackMode` 枚举（值 `"force_answer"` / `"raise_error"`），已在枚举构造时约束。`MergedAgentPolicyConfig.field_sources` 记录每个字段的来源层。返回的是 `MergedAgentPolicyConfig`（runtime-neutral），不构造 Engine `AgentPolicy`。

### 5. 工具截断 helper — 通过

`effective_tool_truncate_spec_from_policy`（`assembly.py:587-607`）委托 `dayu.runtime.tool_truncation.effective_tool_truncate_spec`，该函数（`tool_truncation.py:19-64`）仅在 limit key 缺失时补默认 limit、仅在 TTL 为 None 时补默认 TTL，完整保留 `declaration.strategy`、`declaration.target_field`、`declaration.field_path`。测试 `test_tool_truncation_policy_defaults_fill_declaration_without_target_drift`（`test_assembly_helpers.py:160-189`）确认不漂移。

### 6. Engine provider extension helper — 通过

`provider_request_extension_from_json`（`provider_extensions.py:58-91`）映射全部 6 个 `ProviderRequestExtension` 联合成员，dispatch 表与 `runner_spec.py:211-218` 完全一致。未知 type（`:89-91`）、未知字段（`_require_exact_fields`）、非法枚举（`_parse_enum`）、字段组合非法（`_wrap_contract_error` + contract `__post_init__`）均以 `ProviderExtensionConfigError` fail closed。测试覆盖正向全类型映射、真实 model catalog 解析、以及 4 类 fail-closed 路径（`test_provider_extension_config_adapter.py`）。

### 7. 测试覆盖 — 通过

- `tests/engine/test_provider_extension_config_adapter.py`: 6 个测试覆盖正向 6 类 DSL + 真实 catalog 解析 + 4 类 fail-closed 路径。
- `tests/runtime/test_assembly_helpers.py`: 6 个测试覆盖 selection 优先级、缺失 fail fast、未知字段 reject、agent policy 合并优先级、截断默认值补齐、层中立性。
- `tests/runtime/test_import_boundary.py`: AST 扫描确认 runtime 无反向 import，且 `assembly.py` 被显式覆盖（`:132-136`）。
- `tests/runtime/test_weak_typing_guard.py`: AST 扫描确认 runtime 无 `Any`/`object`/无类型签名/裸容器。

### 8. 项目规则 — 通过

- 严格类型：pyright 0 errors, 0 warnings。
- 中文 docstring：所有公开函数、类、模块均有中文 docstring。
- 无 `Any`/`object`/无类型签名：`test_weak_typing_guard.py` AST 扫描通过。
- 无兼容性 wrapper/facade：两个模块均为全新实现，无兼容 re-export 或透传 wrapper。

## 测试运行结果

```
pytest tests/engine/test_provider_extension_config_adapter.py -q
  6 passed

pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
  17 passed

python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime
  0 errors, 0 warnings, 0 informations
```

## Open Questions

无。

## Residual Risk

1. **`_wrap_contract_error` 使用不完全一致**：`_parse_openai_reasoning`（`provider_extensions.py:94-113`）和 `_parse_mimo_thinking`（`:192-212`）直接构造 contract dataclass 而不包裹 `_wrap_contract_error`。当前无实际风险（这两个 contract 无 `__post_init__`），但若未来为 `OpenAIReasoningExtension` 或 `MimoThinkingExtension` 添加 `__post_init__` 校验，此路径的 `ValueError` 不会被转换为 `ProviderExtensionConfigError`。建议统一包裹，或将 `_wrap_contract_error` 的缺失视为 code review check 项。

2. **`_FALLBACK_MODES` 与 `SceneAgentFallbackMode` 值重复**：`assembly.py:69-71` 的 `_FALLBACK_MODES` frozenset 和 `scene_prepare.py:108-112` 的 `SceneAgentFallbackMode` 枚举值语义重复。当前值一致（`"force_answer"` / `"raise_error"`），但若枚举新增成员而未同步更新 frozenset，`code_default` / `execution_profile` 路径会被 `_validate_fallback_mode` 拦住，而 scene 路径不会。建议将 `_FALLBACK_MODES` 从 `SceneAgentFallbackMode` 枚举派生，消除双真源。

3. **Service composition helper 延后**：本 Slice 未实现 runtime config 到 `RunnerSpec` / `RunnerCallOptions` / Engine `AgentPolicy` 的最终映射，也未实现 context window / Host policy 注入。这些留给 Slice 5 或后续真实 Service 组合根。

4. **Provider DSL helper 扩展同步**：未来新增 `ProviderRequestExtension` 联合成员时，需同步扩展 `provider_request_extension_from_json` 的 dispatch、README 的 coverage matrix 和测试。
