# WU-TOOLS-01-F01-02-R3 Slice 4 Code Review — MiMo

## Review Scope

- Gate: code review
- Slice: Slice 4, Legacy Adapter Deletion and Boundary Closeout
- Work unit: WU-TOOLS-01-F01-02-R3
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice4-implementation-codex.md`
- Reviewer: MiMo (independent)
- Date: 2026-06-10

## Review Dimensions

### 1. Adapter 目录删除安全性

**结论: PASS**

`dayu/tools/_legacy_adapter/**` 共 8 个文件全部删除。经确认：

- 全量 `grep` 搜索 `_legacy_adapter`、`LegacyToolDeclarationCollector`、`adapt_collected_tools`、`from dayu.tools._legacy_adapter`、`dayu.tools._legacy_adapter` 在 `dayu/` 生产代码下零命中。
- 被删除的 8 个模块仅 import `dayu.contracts.*` 子包（`json_value`、`tool_call`、`tool_schema`、`tool_declaration`、`tool_outcome`、`tool_result`），不 import `dayu.host`、`dayu.engine`、`dayu.runtime`。
- 包内交叉引用全部自闭环：`definition_adapter.py` → `argument_validator`、`exceptions`、`registry_collector`、`tool_errors`；`argument_validator.py` → `registry_collector`；`tool_contracts.py` → `exceptions`；`tool_decorator.py` → `registry_collector`、`tool_contracts`。
- 无隐藏生产依赖。删除安全。

**证据**: `dayu/tools/_legacy_adapter/*.py`（git HEAD 版本），`grep` 结果零命中。

### 2. Legacy Adapter 专属测试删除安全性

**结论: PASS**

`tests/tools/test_legacy_tool_adapter.py`（804 行，14 个 test function）已删除。行为迁移清单逐项验证：

| 行为 | 当前覆盖 | 判定 |
|---|---|---|
| 参数 schema validation / default / unknown / missing / enum / range / array item | `tests/runtime/test_tool_call_projection.py` — 12+ test functions 覆盖全部场景，均断言 `INVALID_ARGUMENT_ERROR` | ✅ 已迁移 |
| exception-to-outcome mapping 业务失败 | `test_tool_call_projection.py:test_completed_failed_and_cancelled_outcomes_share_meta` + Doc/Web/Fins provider failure tests | ✅ 已迁移 |
| legacy `tool_cancelled` → failed outcome | 不迁移；Doc/Web/Fins cancellation tests 全部断言 `ToolCancelledOutcome(host_cancelled)` | ✅ 正确删除 |
| path projection / allowed roots / must_exist | `test_doc_tools_provider.py` — `test_disallowed_path_returns_failed_outcome`、`test_disallowed_nonexistent_path_returns_permission_denied`、`test_path_args_are_projected_to_validated_absolute_paths`、`test_path_validation_failure_does_not_enter_migrated_function_body` | ✅ 已迁移 |
| per-tool / per-provider serialization | `test_doc_tools_provider.py:test_same_provider_different_doc_callables_are_serialized`、`test_web_tools_provider.py:test_web_provider_serializes_search_and_fetch_business`、`test_fins_storage_provider.py:test_same_provider_read_tools_do_not_enter_read_runtime_concurrently`、combined acceptance `test_web_provider_serial_policy_holds_under_concurrent_calls` | ✅ 已迁移 |
| truncate / display / tags / schema conversion | Doc/Web/Fins provider tests 覆盖 `ToolTruncateSpec`、tags、schema 不泄露治理字段；combined acceptance 覆盖 bundle 稳定工具名 | ✅ 已迁移 |
| `fetch_more` reserved 防御 | `test_combined_tools_acceptance.py:test_combined_discovery_returns_single_bundle_without_reserved_names` + `test_combined_truncate_specs_and_fetch_more_owner` + `test_doc_tools_provider.py:test_no_old_fetch_more_business_tool` + `test_import_boundary.py:test_fetch_more_token_stays_inside_toolruntime_owner_modules` | ✅ 已迁移 |
| collector / decorator OLD metadata | 不迁移；adapter-only 实现细节 | ✅ 正确删除 |

**证据**: 逐项对应到 `test_tool_call_projection.py`、`test_doc_tools_provider.py`、`test_web_tools_provider.py`、`test_fins_storage_provider.py`、`test_combined_tools_acceptance.py`、`test_import_boundary.py` 中的具体 test function。

### 3. Combined Acceptance 更新

**结论: PASS**

变更内容：

1. `_migrated_tool_source_paths()` 重命名为 `_native_tool_source_paths()`，docstring 从"迁移 provider / adapter 源文件"改为"原生 provider 源文件"。
2. 扫描 roots 移除 `repo_root / "dayu" / "tools" / "_legacy_adapter"`，仅保留 `web` 和 `fins/tools`。
3. `test_migrated_providers_and_adapter_do_not_import_old_runtime` 重命名为 `test_native_providers_do_not_import_old_runtime`，docstring 从"迁移 provider / adapter"改为"当前原生 provider"。
4. 多处 docstring 将"迁移工具"改为"当前工具"。

重命名语义准确：adapter 删除后，剩余被扫描对象确实是 native provider。扫描范围缩减为 `web` + `fins/tools` 覆盖了全部剩余生产 provider。Doc provider 由 `test_doc_tools_provider.py` 单独覆盖 OLD runtime import 防线。

**证据**: `tests/tools/test_combined_tools_acceptance.py` diff。

### 4. Host Import Boundary 更新

**结论: PASS**

变更内容：

1. 删除 `FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES` frozenset（3 个 adapter 路径）。
2. `test_fetch_more_token_stays_inside_toolruntime_owner_modules` docstring 从"owner 或 legacy adapter 防御性引用"改为"ToolRuntime owner 模块"。
3. 测试逻辑移除 `if relative_path in FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES: continue` 分支。

`FETCH_MORE_ALLOWED_RELATIVE_FILES` 保留不变（`host/tool_runtime.py`、`host/tooling.py`、`runtime/tools_discovery.py`），ToolRuntime owner 边界未被误伤。删除 defensive allowlist 后，若 adapter 文件仍存在则会被扫描命中——但 adapter 已删除，所以逻辑自洽。

**证据**: `tests/host/test_import_boundary.py` diff，确认 `FETCH_MORE_ALLOWED_RELATIVE_FILES` 三元组未变。

### 5. test_doc_tools_provider.py 额外清理

**结论: PASS**

移除的 4 行断言：

```python
assert "_legacy_adapter" not in doc_tools_source
assert "_legacy_adapter" not in doc_provider_source
assert "LegacyToolDeclarationCollector" not in doc_provider_source
assert "adapt_collected_tools" not in doc_provider_source
```

分析：

- 这些断言检查 `_legacy_adapter` 相关字符串不出现在 Doc provider 源码中。
- adapter 删除后，这些符号在全仓库不存在，断言变成永真条件（tautology），不再提供防线价值。
- 保留的断言仍覆盖关键防线：OLD runtime import（`dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tool_result`）、`fetch_more` token、`TruncationManager` token。
- 同时移除了 `doc_provider_source` 的读取（不再需要），减少无用 I/O。

不削弱关键防线。删除合理。

**证据**: `tests/tools/test_doc_tools_provider.py` diff，确认保留的 5 个 assert 语句（OLD runtime import + fetch_more + TruncationManager）未变。

### 6. README 更新

**结论: PASS**

#### tests/README.md

- 新增 tool call projection 测试说明行，描述 `ToolCallable` 共享参数投影与 outcome 构造 helper 覆盖范围。
- `tests/tools/` 章节重写：移除 legacy adapter 三条描述，改为 Doc/Web/Fins 三条原生 provider 描述。
- Host import boundary 描述移除 `_legacy_adapter` defensive allowlist 提及。
- 内容准确反映当前代码事实。

触发规则：`tests/` 修改 → 检查 `tests/README.md`。已触发并正确更新。

#### dayu/fins/README.md

- 3 处将 `register_fins_read_tools(...)` 更新为 `build_fins_read_tool_definitions(...)`。
- 变更位置：provider discovery 流程图、assembly 流程图、扩展点说明。
- 反映当前代码真源函数名，不含旧 adapter 引用。

触发规则：`dayu/fins/` 修改 → 检查 `dayu/fins/README.md`。虽本 slice 未修改 `dayu/fins/` 生产代码，但 README 中旧函数名与当前代码不一致，更新为正确收口。

#### dayu/README.md 不更新

- 检查确认：当前 `dayu/README.md` 已描述 `dayu.tools` 输出 current `ToolDefinition` / `ToolBundle`，未提 OLD / legacy adapter。
- 不更新合理。

**证据**: 三个 README diff，对照 AGENTS.md README 更新触发规则。

### 7. rg 零命中验证

**结论: PASS**

Controller 已验证：`rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests` 零命中。

Review 独立确认：`grep` 搜索 5 个 pattern 在 `dayu/` 生产代码下零命中。

**证据**: Controller 验证记录 + 独立 grep 结果。

### 8. AGENTS.md 合规性

**结论: PASS**

| 约束 | 检查结果 |
|---|---|
| 无兼容 re-export / wrapper / facade | ✅ 删除而非保留兼容转发 |
| README 更新边界 | ✅ 仅更新触发规则命中的 README，`dayu/README.md` 检查后不更新 |
| 无跨层反向依赖 | ✅ adapter 仅依赖 `dayu.contracts.*`，删除后无残留依赖 |
| 无 God object / God function | ✅ 删除是净减少，不引入新复杂度 |
| 无胶水 seam | ✅ 删除 adapter 而非保留 facade |
| 测试跟着实现边界迁移 | ✅ 旧测试删除，行为由新测试覆盖 |
| pyright 零报错 | ✅ Controller 验证 0 errors |

## Findings

### Finding 1: `_native_tool_source_paths` 未扫描 Doc provider（信息级）

- **文件**: `tests/tools/test_combined_tools_acceptance.py:957`
- **描述**: `_native_tool_source_paths()` 的 scan roots 包含 `web` 和 `fins/tools`，但不包含 `doc_tools.py` / `doc_provider.py`。Doc provider 的 OLD runtime import 防线由 `test_doc_tools_provider.py:test_read_tools_expose_current_truncate_spec_and_no_old_imports` 单独覆盖。
- **风险**: 无。Doc provider 有独立防线，combined acceptance 扫描 web + fins 覆盖了其余 provider。
- **建议**: 无需修改。如果未来 combined acceptance 需要统一覆盖所有 provider 的 import 扫描，可考虑将 Doc provider 加入 roots，但当前分工合理。

### Finding 2: `dayu/fins/README.md` 更新未在 plan Slice 4 "Exact changes" 中显式列出（信息级）

- **文件**: `docs/reviews/wu-tools-01-f01-02-r3-slice4-implementation-codex.md`、`dayu/fins/README.md`
- **描述**: Plan Slice 4 "Exact changes" 列出 `dayu/fins/README.md` 为 "按 README 触发规则必要时" 更新。Implementation artifact 正确记录了此更新。但 plan 的 "Allowed files/modules" 也包含此文件，所以不越界。
- **风险**: 无。更新内容准确，符合触发规则。
- **建议**: 无需修改。

## Conclusion

**PASS**

Slice 4 实现完整、边界清晰、测试覆盖充分。legacy adapter 目录和专属测试安全删除，行为迁移清单逐项关闭，import boundary 和 combined acceptance 正确收口，README 更新符合触发规则且内容准确，无 AGENTS.md 违规。
