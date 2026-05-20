# Phase 12 Slice 1 Re-Review — AgentDS

## Verdict: PASS

P12-S1-F1 已修复，无回归，无新增阻塞性 finding。

## P12-S1-F1 Status: FIXED

**Finding**: 显式 provider import path 模块缺失时 `ModuleNotFoundError` 直接向上传播，未归一为 `ToolsDiscoveryError`。

**Fix** (`dayu/runtime/tools_discovery.py:305-308`):

```python
try:
    module = importlib.import_module(module_name)
except ModuleNotFoundError as exc:
    raise ToolsDiscoveryError(f"provider import_path cannot import module: {module_name}") from exc
```

**验证**:

- `ModuleNotFoundError` 被包裹为 `ToolsDiscoveryError`，异常消息包含 `cannot import module` 与模块名。
- 通过 `from exc` 保留异常链，`__cause__` 指向原始 `ModuleNotFoundError`。
- 仅包裹 `ModuleNotFoundError`，不扩大捕获范围到通用 `ImportError` 或 `SyntaxError`——这些是代码/环境错误，不应该被静默包裹。

**新增测试** (`tests/runtime/test_tools_discovery.py:232-243`):

`test_import_path_missing_module_raises_tools_discovery_error` 覆盖完整路径 `discover_tools` → `_resolve_import_path`，验证：
1. 抛出 `ToolsDiscoveryError`，消息匹配 `cannot import module`
2. `__cause__` 是 `ModuleNotFoundError` 实例

**无回归**:

| 验证项 | 结果 |
|---|---|
| 原有 malformed import path 报错链路（无冒号） | `ToolsDiscoveryError` + `__cause__ is None` |
| 原有非 callable 报错链路 | `ToolsDiscoveryError` + `__cause__ is None` |
| 原有 valid import path 成功解析 | 正常（`test_import_path_resolution_to_callable` 通过） |

## New Blocking Findings: 0

## Validation Commands/Results

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_tools_discovery.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` | 27 passed in 0.58s |
| `python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 6 passed in 0.58s |
| 手动验证：missing module → ToolsDiscoveryError + __cause__ | PASS |
| 手动验证：malformed path → ToolsDiscoveryError (no cause) | PASS |
| 手动验证：non-callable → ToolsDiscoveryError (no cause) | PASS |

## Scope Notes

- 仅验证 P12-S1-F1 修复范围；Slice 2 digest/reserved-name、Slice 3 ConfigLoader、Slice 4 ScenePrepare 不在本次 re-review 范围。
- `_resolve_import_path` 函数仅 catch `ModuleNotFoundError`，不扩大捕获 `ImportError` 或其他异常——这是有意设计，broken module（例如循环导入、语法错误）应作为环境/代码错误直接暴露，不应被静默归一。

## Final Blocking Findings Count: 0
