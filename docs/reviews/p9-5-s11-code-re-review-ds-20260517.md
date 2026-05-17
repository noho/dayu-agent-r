# P9.5 S11 ToolRuntime Boundary Cleanup — Re-Review (Fix Verification)

## Gate

- **Work unit**: P9.5 Pre-P10 Cross-Repository Hardening
- **Slice**: S11 ToolRuntime Boundary Cleanup — fix re-review
- **Source review artifact**: `docs/reviews/p9-5-s11-code-review-ds-20260517.md`
- **Accepted finding**: Finding 1 LOW — Engine tool ownership import-boundary 测试未覆盖 `from X import *`
- **Fix artifact**: `docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-fix-20260517.md`
- **Reviewer**: AgentDS (re-review agent)
- **Review target**: `tests/engine/test_import_boundary.py` 的 fix diff + fix artifact

## Fix Summary

对 accepted Finding 1，fix 做了以下变更（仅 `tests/engine/test_import_boundary.py`）：

1. 新增 4 个模块级常量：`ENGINE_TOOL_DECLARATION_MODULE`、`ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS`、`ENGINE_TOOL_DECLARATION_STAR_IMPORT_FORBIDDEN_SYMBOLS`、`STAR_IMPORT_SYMBOL`
2. 新增 `_imported_symbol_refs()` — 从源码 AST 提取 `from X import Y` 的 `(module, symbol)` 对
3. 新增 `_engine_tool_ownership_import_violations()` — 集中判定工具 owner 导入违规，包含 star import 展开逻辑
4. 新增 `test_engine_does_not_import_toolruntime_or_tool_declaration_owners()` — 扫描全 Engine 目录
5. 新增 `test_engine_tool_ownership_boundary_detects_tool_declaration_star_import()` — 合成源码证明 star import 检测有效

无 production code 变更，无 Host 侧测试变更。

## Finding Disposition

### Finding 1 LOW — star import 覆盖缺口

**状态**: **fixed**

**验证**:

| 验证项 | 预期 | 实际 | 结论 |
|---|---|---|---|
| 显式导入 `from X import ToolRuntime/ToolBundle/ToolDefinition` 被检测 | 违规 | `ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS` 集合匹配 | 已覆盖 |
| `from dayu.contracts.tool_declaration import *` 被展开检测 | 违规（展开为 ToolBundle + ToolDefinition） | `_engine_tool_ownership_import_violations()` 展开逻辑 | 已覆盖 |
| 其他模块 star import 不被误判 | 不违规 | 仅 `module == ENGINE_TOOL_DECLARATION_MODULE` 触发展开 | 窄范围，无假阳性 |
| 合成测试证明检测逻辑有效 | `assert == [...]` | 精确匹配预期违规列表 | 已证明 |

**窄范围确认**:
- Star import 展开仅针对 `dayu.contracts.tool_declaration`，不全局禁止所有 `import *`
- `ENGINE_TOOL_DECLARATION_STAR_IMPORT_FORBIDDEN_SYMBOLS` 仅含 `{ToolBundle, ToolDefinition}`，不含 `ToolRuntime`（`ToolRuntime` 不在 `dayu.contracts.tool_declaration` 中，其显式导入仍由 `ENGINE_TOOL_OWNERSHIP_FORBIDDEN_SYMBOLS` 覆盖）
- 与 `dayu.contracts.tool_declaration.__all__` 对照确认：`__all__ = ["ToolBundle", "ToolCallable", "ToolDefinition", "ToolDisplayInfo", "tool"]`，star import 确实会导出 `ToolBundle` 和 `ToolDefinition`

**无新 blocker 确认**:
- 无 production code 变更
- 无 Host 侧测试变更
- `_engine_tool_ownership_import_violations()` 中文 docstring 完整，类型标注严格
- `_imported_symbol_refs()` 中文 docstring 完整
- `STAR_IMPORT_SYMBOL` 为模块级命名常量，非魔法字符串
- 合成测试使用 `_engine_root() / "synthetic_star_import.py"` 作为路径标签，该文件不存在于磁盘，不会与真实文件扫描冲突

## Validation Reproduction

```text
$ source .venv/bin/activate && pytest tests/engine/test_import_boundary.py \
    tests/host/test_import_boundary.py -v
13 passed in 0.52s

$ source .venv/bin/activate && python -m pyright \
    tests/engine/test_import_boundary.py tests/host/test_import_boundary.py
0 errors, 0 warnings, 0 informations

$ git diff --check
<clean>
```

## Residual Risks

1. **Star import 检测仅覆盖 `dayu.contracts.tool_declaration`**：其他模块的 star import 不触发违规。这是 fix 的明确窄范围设计——如 fix artifact 所述，全局 star import 禁令应由独立 lint / import-boundary 策略处理，不属于本 finding 的修复范围。

2. **合成测试不创建真实文件**：`test_engine_tool_ownership_boundary_detects_tool_declaration_star_import` 使用合成源码字符串，不依赖磁盘文件。这正确测试了检测逻辑本身，但若 `_iter_engine_python_files()` 的 glob 逻辑有 bug 导致遗漏真实文件，合成测试无法发现。已有 `test_engine_does_not_import_toolruntime_or_tool_declaration_owners` 对真实文件做扫描，二者互补。

## Conclusion

- **Fix status**: fixed
- **Blocking 数量**: 0
- **Artifact 路径**: `docs/reviews/p9-5-s11-code-re-review-ds-20260517.md`
- **建议**: 通过

Finding 1 已完整修复：star import 检测逻辑窄范围覆盖 `dayu.contracts.tool_declaration`，合成测试证明检测有效，全 Engine 扫描测试保持通过，无 production code 变更，无新增 blocker。
