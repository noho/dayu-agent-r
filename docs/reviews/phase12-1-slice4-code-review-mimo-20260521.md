# Code Review

## Scope

- Mode: role-scoped code review handoff
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice4-code-review-mimo-20260521.md`
- Included scope:
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
- Excluded scope: `README.md`、`utils/smoke_host_public_multiturn.py`（pre-existing dirty files）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项审查结果：

1. **dayu.runtime.assembly runtime-neutrality**：`assembly.py` 只 import `dayu.contracts` 和 `dayu.runtime.*` 子模块（`config_loader`、`scene_prepare`、`tool_truncation`），不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。返回值全部是 `assembly.py` 自身定义的 dataclass（`RunnerOptionHintSelection`、`MergedAgentPolicyConfig`、`ToolTruncationPolicyDefaults` 等），不返回 Host / Engine typed object。import boundary 测试 `test_runtime_does_not_import_business_layers` 和 `test_runtime_import_boundary_scan_covers_assembly_module` 提供了自动化保障。

2. **Override 语义**：`_select_value` 实现了 `run_override > scene_override > execution_profile > code_default` 四层优先级，每个字段独立选择。`_require_exact_field_names` 对未知字段 fail fast。无 extra payload。

3. **Runner option hint selection**：`select_runner_option_hint` 使用 `model.runtime_hints.runner_option_hints` 获取 hint，缺失 model 或 hint 时以 `RuntimeAssemblySelectionError` fail fast，错误消息包含具体 model/hint id。测试覆盖了这两个 fail path。

4. **Agent policy merge**：`_AGENT_POLICY_OVERRIDE_FIELDS` 白名单覆盖 8 个字段。`_validate_fallback_mode` 校验 fallback_mode 枚举值（`force_answer` / `raise_error`）。`field_sources` 字典保留每个字段的来源层诊断。不构造 Engine `AgentPolicy`。

5. **Tool truncation helper**：`tool_truncation_policy_defaults` 只投影 policy 默认值；`effective_tool_truncate_spec_from_policy` 通过 `effective_tool_truncate_spec` 补齐 declaration 缺省的 limit/TTL，不修改 strategy/target。

6. **Engine provider extension helper**：`provider_request_extension_from_json` 覆盖当前 `ProviderRequestExtension` 联合的全部 6 种类型。`_require_exact_fields` 校验未知字段；`_parse_enum` 校验非法枚举值；`_wrap_contract_error` 将 Engine contract `ValueError` 转换为 `ProviderExtensionConfigError`。未知 type 在主 dispatch 中 fail closed。

7. **Tests 覆盖**：
   - `test_provider_extension_config_adapter.py`：6 tests，覆盖 6 种 DSL type 正向映射、默认模型目录完整解析、未知 type/字段/枚举/组合 fail closed。
   - `test_assembly_helpers.py`：5 tests，覆盖字段级优先级选择、缺失 model/hint fail fast、未知字段 fail fast、Agent policy 合并与来源诊断、截断 policy 默认值补齐与 strategy/target 不漂移、返回值不构造 Host/Engine object。

8. **Project rules**：所有公共函数和 dataclass 有完整中文 docstring。类型标注完整，无 `Any` / `object` / 无类型签名。无兼容性 wrapper/facade。

## Open Questions

无。

## Residual Risk

- `_select_value` 使用 `is not None` 判断 falsy 值（`0`、`False`），逻辑正确但测试未覆盖 `continuation_max_attempts=0` 等非负零值场景的字段级选择路径。风险低，因为 `_optional_non_negative_int_field` 已校验 `>= 0`。
- `_ttl_seconds_as_int` 使用 `float.is_integer()` 检查整数秒，对 `inf` 由前置 `isfinite()` 拦截，无实际风险。
- Provider DSL 覆盖当前 union 全部成员；未来新增 `ProviderRequestExtension` 成员时需同步扩展 helper。

## Tests Run and Results

- `pytest tests/engine/test_provider_extension_config_adapter.py -q`：6 passed
- `pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`：17 passed
- `python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime`：0 errors, 0 warnings, 0 informations
- `git diff --check`：pass（仅 pre-existing dirty files 有 trailing whitespace）

## Verdict

**PASS**
