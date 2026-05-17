# P9.5 S11 ToolRuntime Boundary Cleanup — Fix Artifact

## Gate

- **Gate**: P9.5 S11 fix
- **Role**: fix agent
- **Source review artifact**: `docs/reviews/p9-5-s11-code-review-ds-20260517.md`
- **Accepted finding**: Finding 1 LOW — `tests/engine/test_import_boundary.py` 的 Engine tool ownership import-boundary 测试未覆盖 `from X import *`

## Fix

- 在 Engine 工具 owner import-boundary 测试中补充 `dayu.contracts.tool_declaration` 模块常量与 star import 哨兵常量。
- 将 Engine 工具 owner 违规判定集中到 `_engine_tool_ownership_import_violations()`。
- 对 `from dayu.contracts.tool_declaration import *` 做窄范围处理：只将其展开为 `ToolBundle` / `ToolDefinition` 违规，不全局禁止所有 star import。
- 增加合成源码测试 `test_engine_tool_ownership_boundary_detects_tool_declaration_star_import()`，证明该 star import 会被识别为 Engine tool ownership violation。
- 未修改 production code，未修改 S11 helper 模块，未扩大 Host 侧边界测试。

## Validation

```text
$ source .venv/bin/activate && pytest tests/engine/test_import_boundary.py tests/host/test_import_boundary.py
13 passed in 0.53s

$ source .venv/bin/activate && python -m pyright tests/engine/test_import_boundary.py tests/host/test_import_boundary.py
0 errors, 0 warnings, 0 informations

$ git diff --check
<no output>
```

## Residual Risk

- 当前修复只覆盖 accepted finding 指定的 `dayu.contracts.tool_declaration` star import 路径；没有引入全局 star import 禁令。若后续需要全仓禁止 star import，应由独立 lint / import-boundary 策略处理。
- `ToolRuntime` 不在 `dayu.contracts.tool_declaration` 的 star import 展开列表中；显式导入 `ToolRuntime` 仍由既有 forbidden symbol 集合覆盖。

