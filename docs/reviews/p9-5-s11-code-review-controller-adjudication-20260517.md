# P9.5 S11 ToolRuntime Boundary Cleanup Controller Adjudication

日期：2026-05-17
总控 Agent：AgentController

## 审查对象

- Implementation artifact：`docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-implementation-20260517.md`
- AgentMiMo review：`docs/reviews/p9-5-s11-code-review-mimo-20260517.md`
- AgentDS review：`docs/reviews/p9-5-s11-code-review-ds-20260517.md`
- Fix artifact：`docs/reviews/p9-5-s11-toolruntime-boundary-cleanup-fix-20260517.md`
- AgentDS re-review：`docs/reviews/p9-5-s11-code-re-review-ds-20260517.md`
- 当前 S11 diff：
  - `dayu/host/tool_runtime.py`
  - `dayu/host/tool_runtime_schema_projection.py`
  - `tests/host/test_import_boundary.py`
  - `tests/engine/test_import_boundary.py`

## 设计真源裁决

S11 的动机成立。`dayu/host/tool_runtime.py` 已超过 5000 行并同时承载 effective bundle / schema projection、accept barrier、truncation / `fetch_more`、duplicate governance、diagnostics 与 factory wiring，存在真实 owner 聚合压力。但 S11 的最佳实践不是机械大拆，而是只抽取能降低真实耦合且不改变 public import surface 的私有 owner。

当前实现只把 ToolRuntime effective schema projection / digest helper 抽到 `dayu.host.tool_runtime_schema_projection`，保留 `ToolRuntimeHandle`、factory、accept barrier、EventLog facts、duplicate semantics、truncation cursor scope、diagnostics 和 `dayu.host.tool_runtime` public `__all__` 不变。该取舍符合 S11 stop condition：不创建 compatibility re-export，不创建 test-only private re-export，不改变 public API，不把 ToolRuntime 移到 `contracts` / `runtime`，也不让 Engine 拥有工具声明或工具执行治理。

## Review Finding 裁决

| 来源 | Finding | 裁决 | 处理 |
|---|---|---|---|
| AgentMiMo | R1 新模块无直接单元测试 | rejected-with-reason | 当前 helper 是私有 projection helper，已由 effective bundle / executor / diagnostics 行为测试覆盖；直接单测不是 S11 blocker。S12 若触及 projection 细节可补。 |
| AgentMiMo | R2 `tool_runtime.py` 仍较大 | accepted-as-non-blocking | 这是有意保留 public owner 的结果，避免 public type 迁移导致 re-export 或 API 变化；S16 可重新评估进一步拆分。 |
| AgentMiMo | R3 digest helper 复用 Host durable codec | accepted-as-non-blocking | digest 真源当前在 Host durable codec；下沉到 runtime / contracts 会扩大架构变更，不属于 S11。 |
| AgentMiMo | R4 新模块部分函数只在模块内调用 | rejected-with-reason | 这些函数是同一私有 helper 模块内的可复用 projection helper，不是 compatibility re-export。 |
| AgentDS | Finding 1 LOW：import-boundary 测试未覆盖 `from X import *` | accepted | Controller 接受该 proof gap。Fix 已把 `from dayu.contracts.tool_declaration import *` 展开为 `ToolBundle` / `ToolDefinition` 违规，并由合成源码测试证明。DS re-review 确认 fixed。 |
| AgentDS | Finding 2 INFO：`tool_runtime.py.__all__` 未反映新私有模块 | rejected-with-reason | 新模块为私有实现细节，不应进入 `__all__`；当前 public surface 不变是正确行为。 |

## 验证

Controller 复跑验证：

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py tests/host/test_import_boundary.py tests/engine/test_import_boundary.py`：46 passed。
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_*.py`：55 passed。
- `source .venv/bin/activate && pytest tests/host tests/engine`：897 passed。
- `source .venv/bin/activate && python -m pyright dayu tests`：0 errors / 0 warnings / 0 informations。
- `git diff --check`：clean。

## 文档裁决

本 slice 修改 `dayu/host/` 与 `tests/`，已检查 README 触发条件。`dayu/host/README.md` 现有 ToolRuntime boundary、accept barrier、truncation、duplicate、diagnostics 和 public import 描述仍然准确；`tests/README.md` 的测试分层与运行方式没有变化。当前不更新 README 是正确决策。

## 结论

P9.5 S11 code review / fix / re-review gate passed。S11 可进入 accepted slice commit。

剩余风险均有 owner：

- `tool_runtime.py` 仍较大：S16 Contract Ownership audit 或后续真实 owner-driven refactor 可重新评估。
- `tool_runtime_schema_projection.py` 只有间接行为测试：S12 若修改 schema / truncation projection 细节，应补更直接测试。
- 全局 star import 禁令不属于本 finding；当前只覆盖 `dayu.contracts.tool_declaration` 这条会隐式导入 `ToolBundle` / `ToolDefinition` 的路径。
