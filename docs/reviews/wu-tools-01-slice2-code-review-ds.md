# Code Review

## Scope

- Mode: current changes (workspace uncommitted diff for WU-TOOLS-01 Slice S2)
- Branch: phaseflow/wu-tools-01
- Base: main
- Output file: docs/reviews/wu-tools-01-slice2-code-review-ds.md
- Included scope:
  - `dayu/tools/` (new package, all 8 modules)
  - `dayu/runtime/config_loader.py` (modified)
  - `dayu/service/host_assembly.py` (modified)
  - `dayu/config/tool_discovery.json` (modified)
  - `tests/tools/test_legacy_tool_adapter.py` (new)
  - `tests/runtime/test_config_loader.py` (modified)
  - `tests/service/test_host_assembly.py` (modified)
  - `dayu/README.md`, `dayu/config/README.md`, `tests/README.md` (modified)
- Excluded scope: S1/S3/S4/S5/S6 implementation files, unmodified contracts/modules
- Parallel review coverage: 无

## Key Review Dimensions Verified

- **Contract compliance**: Adapter uses current `ToolDefinition` / `ToolCallable` / `ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolTruncateSpec` exclusively. `ToolDefinition.__post_init__` name-schema consistency validated through collector registration guard. `_AdaptedLegacyCallable.__call__` signature matches `ToolCallable` protocol (async, receives `ToolCallRequest` + `BatchToolExecutionContext`, returns `ToolExecutionOutcome`).
- **No OLD registry migration**: `test_tools_adapter_import_boundary_excludes_old_runtime_owners` AST-scans all adapter `.py` files for `dayu.engine.tool_registry` / `dayu.engine.truncation_manager` / `dayu.engine.tool_result` imports. Zero violations.
- **Collector is not OLD registry**: `LegacyToolDeclarationCollector.register_allowed_paths()` records call facts only; `_project_paths` enforces path safety through explicit `ToolPathValidationPolicy`, not collector records. Verified by `test_path_projection_uses_explicit_policy_not_collector_allowed_paths`.
- **OLD ok/value unwrapping**: `project_legacy_return` detects `{"ok": True, "value": ...}` and extracts `value` only; OLD projection fields (`truncation`, `fetch_more_args`) are discarded. Verified by `test_legacy_return_envelopes_project_to_current_outcomes`.
- **fetch_more reserved**: `adapt_collected_tool` raises ValueError for `"fetch_more"`; `adapt_collected_tools` filters it silently. Verified by `test_fetch_more_is_not_emitted_as_business_tool`. `ToolsDiscovery._validate_reserved_tool_names` provides a second defense at the discovery layer.
- **Config pass-through**: `ConfigLoader` parses optional `config` as `Mapping[str, JsonValue]`, defaults to `{}`. `_tool_discovery_specs` passes `provider_config.config` to `ToolsDiscoveryProviderSpec.config`. End-to-end chain verified by `test_tool_discovery_provider_config_survives_loader_and_service_mapping`.
- **Default per-tool serialization**: `test_default_per_tool_serialization_prevents_concurrent_entry` proves concurrent `asyncio.gather` calls to the same adapted callable do not enter the sync function concurrently (concurrent_entries == 0).
- **Input projection fails before callable invocation**: `test_projection_coerces_defaults_and_rejects_invalid_arguments` proves validation failures return `ToolFailedOutcome` and `calls == []` (migrated function never entered).
- **No ToolRuntime/Engine contract changes**: Confirmed zero diffs to `dayu/contracts/tool_declaration.py`, `dayu/contracts/tool_outcome.py`, `dayu/contracts/tool_result.py`, `dayu/contracts/tool_schema.py`, `dayu/contracts/tool_call.py`, `dayu/host/tool_runtime.py`.
- **No Doc/Fins/Web business tools**: `dayu/tools/` contains only `_legacy_adapter/` package. No `doc_tools.py`, `doc_provider.py`, `web/`, or `dayu/fins` additions.
- **Provider config remains layer-neutral JSON**: `_optional_mapping_field` returns `Mapping[str, JsonValue]` without interpreting Doc/Fins/Web semantics. `dayu/config/tool_discovery.json` disabled providers carry provider-owned keys (`allowed_paths`, `workspace_root`, `request_timeout_seconds`) but ConfigLoader treats them as opaque JSON.

## Findings

### 1-未修复-低-OLD envelope 检测依赖单一 `ok` 键，存在误判风险

- **入口/函数**: `project_legacy_return` → `definition_adapter.py`
- **文件(行号)**: `dayu/tools/_legacy_adapter/definition_adapter.py:209-214`
- **输入场景**: 迁移工具返回一个业务 dict `{"ok": True, "status": "ready", "count": 5}`，其中 `"ok"` 是业务字段而不是 OLD envelope 的判别字段。
- **实际分支**: `isinstance(raw_value, Mapping)` 为 True → `raw_value.get("ok")` 返回 `True` → 进入 OLD 成功 envelope 分支 → `raw_value.get("value")` 返回 `None` → LLM 收到 `null`。
- **预期行为**: 非 OLD envelope 的纯业务 dict 应原样透传为 `ToolResultSuccess.value`。
- **实际行为**: `value=None` 替代了原始业务 dict，数据静默丢失。
- **直接证据**: 代码行 209-214 仅检查 `ok_value is True`，不检查 `"value"` 键是否存在。OLD envelope 约定 `{"ok": True, "value": ...}` 要求同时存在 `ok` 和 `value` 键，但当前检测不验证 `"value"` 键。
- **影响**: S2 无业务工具，当前不触发。S3/S4/S5 迁移具体工具后，若某个 OLD tool 的返回 dict 恰好不遵循标准 envelope 形状（如 OLD tool 内部有自定义返回包装），会静默丢失数据。风险范围受限——OLD 工具应遵循标准 envelope 约定；但防御深度不足。
- **建议改法和验证点**: 在 `ok_value is True` 分支增加 `"value" in raw_value` 检查；若 `"value"` 不在 dict 中，fall through 到 plain dict 透传分支。测试需证明带 `ok=True` 但无 `value` 的业务 dict 不被误判。
- **修复风险（低）**: 仅增加一个条件判断，不改变现有正确路径行为。
- **严重程度（低）**: S2 无业务工具，当前无实际触发场景。是对 S3/S4/S5 的前瞻性防御建议。

### 2-未修复-低-`_project_paths` 未校验 `path_policy.file_path_params` 对 `declaration.file_path_params` 的完备性

- **入口/函数**: `_project_paths` → `definition_adapter.py`
- **文件(行号)**: `dayu/tools/_legacy_adapter/definition_adapter.py:413`
- **输入场景**: 工具声明 `file_path_params=("file_path", "output_path")`，但 provider 构造 `ToolPathValidationPolicy(file_path_params=("file_path",))` 时遗漏 `"output_path"`。
- **实际分支**: `path_policy is not None` → `path_param_names = path_policy.file_path_params` 只含 `("file_path",)` → 只校验 `file_path` → `output_path` 的原始值未被归一化/校验即传入迁移函数。
- **预期行为**: `path_policy.file_path_params` 是 provider 提供的显式策略；adapter 信任该策略完备但当前不做交叉校验。理想行为是在 debug/assert 层面发出警告，或至少要求 policy 的 param set 是 declaration set 的超集。
- **实际行为**: 不完整策略不会导致 adapter 报错，路径校验被部分跳过。
- **直接证据**: 第 413 行 `path_param_names = path_policy.file_path_params if path_policy is not None else declaration.file_path_params`，无后续完备性校验。
- **影响**: 需要 provider 构造错误的 policy 才会触发。S3 Doc provider 负责构造 policy，届时应有对应测试覆盖。当前 S2 无 provider 构造 policy 的代码。
- **建议改法和验证点**: 在 `_project_paths` 中增加 defensive check：若 `path_policy` 不为 None 且 `set(path_policy.file_path_params) < set(declaration.file_path_params)`，至少记录 warning 或 fail closed。S3 应测试 policy 完备性。
- **修复风险（低）**: 可加为 assertion 或 warning，不影响正确路径。
- **严重程度（低）**: 属于防御性检查缺失，不是逻辑错误。实际触发需要 provider 配置错误。

## Open Questions

- `project_legacy_return` 的 OLD envelope 检测是否需要更严格的二因子验证（同时检查 `ok` 和 `value` 键）？这取决于 S3/S4/S5 迁移的具体工具返回形状。建议在 S3 实现时重新评估。
- `_project_paths` 是否应在 adapter 层对 `path_policy.file_path_params` 与 `declaration.file_path_params` 做完备性校验，还是留给 provider 层的配置校验？当前设计倾向后者，由 provider 保证 policy 正确。若 S3 测试中发现 policy 遗漏风险，再加固 adapter 层。

## Residual Risk

- S3/S4/S5 provider 实现需要严格保证：构造的 `ToolPathValidationPolicy` 覆盖所有 `declaration.file_path_params`；迁移工具返回的 dict 不包含与 OLD envelope 冲突的 `"ok"` 键作为业务字段。
- 当前测试覆盖了 adapter 层的所有关键路径（直接透传、需要投影、投影失败、路径策略、envelope 解包、异常映射、fetch_more 过滤、truncate 转换、并发序列化、import boundary），但未覆盖 adapter 与 `ToolsDiscovery` / `ToolRuntime` 的集成路径——这部分属于 S6 范围，S2 不要求。
- `ConfigLoader` 新增的 `_require_required_and_optional_fields` 替代了原来的 `_require_exact_fields` 仅用于 provider record。如果未来其他 config record 也需要 optional field 支持，需要考虑是否统一升级所有 `_require_exact_fields` 调用点——当前改动仅触及 provider record，范围受控。

## Verdict

**pass-with-findings**

- 无 contract violation、无 import boundary violation、无类型错误、无逻辑缺陷。
- 两个 low-severity findings 均为防御性加固建议，不影响 S2 当前正确性。
- 建议直接进入 fix gate 结论为 **accepted slice commit**（无需额外 fix gate）。
- S2 可以提交，两个 low findings 在 S3 实现时一并关注即可。

## Validation Commands

Controller 已运行验证，reviewer 复核确认：

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py
# 89 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

Reviewer 未独立重复运行验证命令；controller 验证结果已记录在 implementation artifact 中且与 review 发现一致。
