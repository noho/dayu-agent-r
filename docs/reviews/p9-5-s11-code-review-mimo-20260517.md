# P9.5 S11 ToolRuntime Boundary Cleanup — Code Review

## Gate

- Work unit: P9.5 S11 ToolRuntime Boundary Cleanup code review
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` §S11
- Design source: `docs/host/design.md`
- Control source: `docs/host/implementation-control.md`
- Implementation artifact: `docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-implementation-20260517.md`
- Role: review agent only; no code changes, commits, pushes, PRs, or gate transitions

## Reviewed Diff Scope

- `dayu/host/tool_runtime.py` — 删除 8 私有 schema projection / digest helper，改为从新私有模块导入 5 个
- `dayu/host/tool_runtime_schema_projection.py` — 新增私有 Host schema projection owner
- `tests/host/test_import_boundary.py` — 新增 2 个边界测试
- `tests/engine/test_import_boundary.py` — 新增 1 个边界测试 + 辅助函数
- implementation artifact — 完整性与准确性审查

## Review Checklist

### 1. 新私有 helper 是否真的是 Host 私有 schema projection owner

**结论：是。**

直接证据：

- `tool_runtime_schema_projection.py` 模块 docstring 明确声明不拥有 accept barrier、truncation cursor、duplicate governance、diagnostic emitter 或 factory 生命周期。
- 模块内 8 个函数全部是纯 schema projection 或 digest 计算：`validate_reserved_name_conflicts`、`definitions_by_name`、`business_bundle_digest`、`tool_schemas_digest`、`tool_definition_digest_json`、`tool_schema_json`、`parameters_json`、`truncate_spec_json`。
- 无状态持有、无 Host runtime 状态机引用、无 EventLog 写入。
- import 边界测试 `test_toolruntime_schema_projection_stays_private_host_owner` 验证该模块不依赖 `dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins`、`dayu.host.dispatch`、`dayu.host.engine_ingest`、`dayu.host.projection`、`dayu.host.waiting`。
- 实际仅依赖 `dayu.contracts.*`、`dayu.host.durable.codec`、`dayu.host.tooling`，符合 Host 私有 helper 定位。

### 2. ToolRuntimeHandle、factory、accept barrier 行为不变

**结论：不变。**

直接证据：

- diff 中 `ToolRuntimeHandle`、`EffectiveToolBundle`、`_build_tool_runtime`（factory）、accept barrier 逻辑无任何修改。
- `tool_runtime.py` 中 `_validate_reserved_name_conflicts`（L2077）、`_definitions_by_name`（L2088）、`_business_bundle_digest`（L2107）、`_tool_schemas_digest`（L2110）、`_tool_schema_json`（L4611）的调用点全部改为从新模块导入的同名符号，调用签名和语义完全一致。
- `grep` 确认 tool_runtime.py 中不再有 `_tool_definition_digest_json`、`_parameters_json`、`_truncate_spec_json` 的定义或调用——它们仅作为 `tool_runtime_schema_projection.py` 的内部 helper 存在。

### 3. diagnostics 行为不变

**结论：不变。**

直接证据：

- `_business_bundle_digest` 和 `_tool_schemas_digest` 的实现从 `tool_runtime.py` 原样迁移到 `tool_runtime_schema_projection.py`，算法不变（仍调用 `sha256_digest_json`）。
- `_tool_schema_json` 的实现原样迁移，JSON 投影结构不变。
- `tool_runtime.py` 中 diagnostics 调用点（L2107、L2110、L4611）改为导入版本，行为等价。

### 4. duplicate governance 行为不变

**结论：不变。**

直接证据：

- diff 中 duplicate governance 相关逻辑（`_decide_duplicate_outcome`、`_DuplicatePolicyKind` 等）无修改。
- `definitions_by_name` 的重复检测逻辑（`raise ValueError` on duplicate name）从原模块原样迁移到新模块，无语义变化。

### 5. truncation / fetch_more 行为不变

**结论：不变。**

直接证据：

- diff 中 truncation cursor、`TruncationManager`、`fetch_more` 注入逻辑无修改。
- `truncate_spec_json` 从原模块原样迁移，JSON 投影结构不变。
- truncation cursor scope 未扩展。

### 6. import-boundary 测试是否有假阳性或缺口

**结论：无假阳性，覆盖充分。**

逐项审查：

| 测试 | 覆盖 | 假阳性风险 |
|---|---|---|
| `test_host_root_does_not_export_toolruntime_or_tool_declaration_owners` | 检查 `host.__all__` 和 `vars(host)` 不含 `ToolRuntime`/`ToolRuntimeHandle`/`ToolBundle`/`ToolDefinition` | 无。精确检查包根导出 |
| `test_toolruntime_schema_projection_stays_private_host_owner` | AST 扫描新模块禁止 import 8 个前缀 | 无。新模块确实只依赖 contracts/durable/tooling |
| `test_engine_does_not_import_toolruntime_or_tool_declaration_owners` | AST 扫描 Engine 所有 .py 文件的 `from ... import` 符号级检查 | 低。符号级检查比模块级检查更精确，但理论上同名符号可能出现在无关模块中——当前代码库不存在此情况 |

缺口评估：

- 新增 `test_engine_does_not_import_toolruntime_or_tool_declaration_owners` 使用 `_imported_symbol_refs` 做符号级检查，比已有的 `_imported_module_names` 更严格。这是合适的，因为 Engine 可能合法导入 contracts 模块但不应导入 `ToolRuntime` 等具体符号。
- 已有的 `test_engine_does_not_import_engine_core_forbidden_modules` 使用前缀级检查 `dayu.host`，已覆盖模块级边界。新测试补充了符号级粒度。
- `test_host_root_does_not_export_toolruntime_or_tool_declaration_owners` 同时检查 `__all__` 和 `vars()`，防止命名空间泄漏，覆盖充分。

### 7. 新增函数是否满足中文 docstring、严格类型和架构边界

**结论：全部满足。**

逐函数审查 `tool_runtime_schema_projection.py`：

| 函数 | 中文 docstring | 参数类型 | 返回值类型 | 异常说明 | 架构边界 |
|---|---|---|---|---|---|
| `validate_reserved_name_conflicts` | 完整（含 param/returns/raises） | `ToolBundle`, `FrameworkToolPolicyView` | `None` | `ValueError` | 仅依赖 contracts + tooling |
| `definitions_by_name` | 完整 | `list[ToolDefinition]` | `dict[str, ToolDefinition]` | `ValueError` | 仅依赖 contracts |
| `business_bundle_digest` | 完整 | `ToolBundle` | `str` | — | 仅依赖 contracts + durable codec |
| `tool_schemas_digest` | 完整 | `tuple[ToolSchema, ...]` | `str` | — | 仅依赖 contracts + durable codec |
| `tool_definition_digest_json` | 完整 | `ToolDefinition` | `JsonValue` | — | 仅依赖 contracts |
| `tool_schema_json` | 完整 | `ToolSchema` | `JsonValue` | — | 仅依赖 contracts |
| `parameters_json` | 完整 | `ToolParametersSchema` | `JsonValue` | — | 仅依赖 contracts |
| `truncate_spec_json` | 完整 | `ToolTruncateSpec \| None` | `JsonValue` | — | 仅依赖 contracts |

- 无 `Any`、`object`、无类型参数或无类型返回值。
- 无 `hasattr`/`getattr` 滥用。
- 无魔法数字/字符串（schema 投影字段名为字典 key，属于 schema 定义，按项目约束允许）。
- 无嵌套函数/嵌套类。
- 无胶水 seam 或无理由的 lazy import。

### 8. README 不更新的决策是否正确

**结论：正确。**

直接证据：

- 本次只新增 Host 私有 helper 模块并补 import-boundary 测试。
- `dayu/host/README.md` 中 ToolRuntime boundary、public import、accept barrier、truncation、duplicate 与 diagnostics 描述仍与当前代码一致——未涉及 public API 或 stable boundary 变化。
- `tests/README.md` 的测试分层与运行方式未发生职责变化。
- 按 README 触发规则，`dayu/host/` 修改触发 `dayu/host/README.md` 检查，但当前 README 内容仍准确。
- 按 README 触发规则，`tests/` 修改触发 `tests/README.md` 检查，但测试分层未变化。

### 9. EventLog fact 变化

**结论：无变化。**

- diff 中无 EventLog append、canonical fact、event_sequence 相关修改。
- 新模块只做 schema→JSON 投影和 digest 计算，不接触 EventLog。

### 10. public API 变化

**结论：无变化。**

- `dayu/host/__init__.py` 未修改。
- `ToolRuntimeHandle`、`EffectiveToolBundle` 等 public 类型的导入路径不变。
- 新模块 `tool_runtime_schema_projection` 是私有模块，不出现在任何包根 `__all__`。

## Findings

**Blocking findings: 0**

无 blocking finding。

## Residual Risks

### R1: 新模块无直接单元测试

- 描述：`tool_runtime_schema_projection.py` 中的函数没有直接单元测试。它们通过已有 ToolRuntime 行为测试（45 passed）间接验证。
- 影响：低。行为测试覆盖了这些 helper 的实际使用路径；若内部实现变化但行为不变，现有测试仍能捕获回归。
- 建议验证点：后续 S12 增加 truncation/duplicate hardening 测试时，可考虑为 `tool_definition_digest_json` 和 `truncate_spec_json` 增加直接单元测试。
- 严重程度：信息（不阻塞）

### R2: tool_runtime.py 仍为 5028 行

- 描述：文件从 ~5150 行减至 5028 行（净减 ~122 行），accept barrier、truncation、duplicate、diagnostics 与 executor 仍在同一公开模块内。
- 影响：低。implementation artifact 已记录此为有意决策——避免 public type 迁移触发 compatibility re-export 或 public API 变化。S12/S16 若需进一步拆分，必须先重新裁决公开导入路径。
- 建议验证点：S16 Contract Ownership audit 可重新评估是否需要进一步拆分。
- 严重程度：信息（不阻塞）

### R3: digest helper 复用 dayu.host.durable.codec

- 描述：新模块通过 `sha256_digest_json` 依赖 `dayu.host.durable.codec`，未将 digest helper 下沉到 runtime 或 contracts。
- 影响：低。implementation artifact 已记录此为有意决策——避免扩大架构变更。
- 建议验证点：S16 可评估 digest helper 的正确归属层。
- 严重程度：信息（不阻塞）

### R4: 新模块 8 个函数中有 3 个未被 tool_runtime.py 直接导入

- 描述：`tool_definition_digest_json`、`parameters_json`、`truncate_spec_json` 是 `tool_runtime_schema_projection.py` 的公共函数，但未被 `tool_runtime.py` 导入。它们仅被同模块内的 `business_bundle_digest` 和 `tool_schema_json` 内部调用。
- 影响：极低。这些函数作为模块内公共 API 存在是合理的——它们是可独立使用的 schema projection helper，供模块内其他函数复用。不是 compatibility re-export。
- 建议验证点：无。
- 严重程度：信息（不阻塞）

## Conclusion

S11 实现严格遵循 plan §S11 的目标与边界：

1. 只抽取了 schema projection / digest helper 到私有模块，移除了真实耦合（8 个函数从 5000+ 行聚合模块中分离）。
2. 未引入 compatibility re-export、test-only private re-export、facade、lazy import seam。
3. 未改变 public API、EventLog facts、duplicate semantics、truncation cursor scope。
4. 未将 ToolRuntime 移到 contracts/runtime 或让 Engine 拥有工具声明/执行治理。
5. ToolRuntimeHandle、factory、accept barrier、diagnostics 行为不变。
6. import-boundary 测试覆盖充分，无假阳性。
7. 新函数满足中文 docstring、严格类型和架构边界要求。
8. README 不更新的决策正确。
9. 未触发 S11 stop condition。

**建议：通过。**
