# WU-TOOLS-01-F01-02-R3 Plan Fix — Codex

## 基本信息

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: plan fix
- Agent: Codex
- Timestamp: `2026-06-10T17:57:18+0800`
- Plan artifact: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- Review inputs:
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-review-controller-adjudication.md`

## 修复总览

本次只修复 plan artifact，并新增本 fix artifact。未修改生产代码、测试代码、control doc，未 commit / push / PR / merge，未进入 re-review gate。

动机判断：Controller 接受的 PF-01 到 PF-09 均属于计划可执行性和验证闭环缺口，不需要新的 Host / Engine 架构决策；因此可以通过补充 plan 文本修复。

## PF 修复状态

| PF | 状态 | Changed plan section | Exact summary |
|---|---|---|---|
| PF-01 | 已修复 | §7 `决策 5：错误类型迁移但不兼容` | 增加旧类型到新表达 / 新位置 / outcome 投影迁移表，区分 `ToolArgumentValidationFailure`、`ToolBusinessFailure`、Doc/Web/Fins 领域本地错误、`host_cancelled_outcome(...)`。明确 Web 额外诊断字段不扩展 `ToolResultMeta`，Fins 不从 `dayu.tools` 跨包导入错误类型。 |
| PF-02 | 已修复 | §7 `决策 4：取消用专门语义表达`，§7 callable 模板 | 明确选择直接返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` 作为 native callable 主路径。私有 cancellation exception 不作为跨 helper / callable / ToolRuntime 边界主路径；深层同步 helper 若需提前退出，返回 typed cancelled result 并由 callable 映射 outcome。 |
| PF-03 | 已修复 | §7 `决策 3`，§8 Slice 1/2/3 `Exact changes` | 明确每个 `build_*_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`，同 provider 返回的所有 callable 共享。明确 lock 获取在参数 / 路径 / URL / workspace 校验和 pre-cancel checkpoint 后、阻塞业务或 `asyncio.to_thread` 前。 |
| PF-04 | 已修复 | §7 `代表性 native callable 模板` | 增加代表性 async callable 模板，覆盖闭包捕获 config、参数校验、读取 `context.cancellation_token`、pre-cancel、路径校验、共享 provider lock、`asyncio.to_thread`、业务失败 / 取消 / 成功到 outcome 的映射。 |
| PF-05 | 已修复 | §8 Slice 0 `Exact changes` / `Slice 0 helper API 草案` / `参数校验范围` | 给出 helper API 签名草案、typed success/failure 字段、固定 `invalid_argument`。参数校验范围改为从 legacy adapter 和 Doc/Web/Fins 实际 schema 倒推，并显式排除当前未使用的 JSON Schema 高级特性。 |
| PF-06 | 已修复 | §8 Slice 1/2/3 `Tests`，§8 Slice 4 `tests/tools/test_legacy_tool_adapter.py 行为迁移清单`，§9 validation matrix | 明确 adapter 测试删除前，参数校验、path projection、concurrency、outcome/meta、truncate/display/tags/schema 等 current 行为分别由 Slice 0/1/2/3 覆盖；adapter-only decorator / collector 细节可删除。 |
| PF-07 | 已修复 | §8 Slice 3 `Exact changes` / `Tests` / `Completion signal` | 增加 Fins fixture helper 迁移要求：`tests/fins/test_fins_storage_provider.py` 不再通过 legacy collector / adapter 获取 definitions，改用 native provider / builder，同时仍通过 `DefaultFinsRuntime` / `dayu.fins.storage` 边界准备材料。 |
| PF-08 | 已修复 | §8 Slice 2 `Completion signal` / `Stop condition`，§11 residual risk closeout expectation | 增加 Web live smoke 残余追踪要求：未运行真实网络 / Playwright smoke 时必须记录未验证场景、原因、owner / destination；本地 fixture / offline 模式可用时优先运行。 |
| PF-09 | 已修复 | §6 `Outcome`，§8 Slice 0 `host_cancelled_outcome`，§8 Slice 1/2/3 `Tests`，§9 validation matrix | 明确 `host_cancelled_outcome(...)` 构造 `ToolResultMeta(tool_name, started_at, finished_at)` 并放入 `ToolCancelledOutcome.meta`；测试要求 meta 非空且不泄露 Host governance 字段。 |

## Validation performed

- `sed` 复读更新后的 plan 关键 sections，确认 PF-01 到 PF-09 均有明确落点。
- `git diff --check -- docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`：无输出；由于两个目标 artifact 当前为 untracked，另用 no-index 模式检查实际内容。
- `git diff --check --no-index /dev/null docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`：无 whitespace warning 输出；exit code 1 是 no-index 比较新增文件时的预期差异返回。
- `git diff --check --no-index /dev/null docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`：无 whitespace warning 输出；exit code 1 是 no-index 比较新增文件时的预期差异返回。

## Residual risks / uncovered areas

- 本次未运行 pytest 或 pyright，因为用户明确要求只修复 plan artifact，不实施生产代码或测试代码。
- Web live smoke 的真实网络 / Playwright 覆盖仍是 implementation closeout 风险；plan 已要求 Slice 2 / R3 closeout 在未运行时记录 owner 和未验证场景。
- 当前没有需要用户或 design source 决策才能修复的 accepted PF。

## Completion status

- Completion status: plan fix completed.
- Next recommended gate: plan re-review.
