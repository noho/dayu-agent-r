# Code Review

## Scope

- Mode: current changes (Slice S1 of `docs/host/phase8-cleanup-plan.md`)
- Branch or PR: workspace HEAD (last commit `0362f79` 是 plan accept commit；S1 实施位于 unstaged changes)
- Base: HEAD (`0362f79`)
- Output file: `docs/reviews/code-review-s1-20260510.md`
- Parallel review coverage: 无（scope 较小，主 reviewer 一次走读）

## Verification Summary

- pyright（全仓）: `0 errors, 0 warnings, 0 informations`
- pytest tests/host -q: `303 passed in 2.38s`
- `grep -RIn "LocalRunHarness(" dayu`：3 处命中（docstring + `_build_default_harness` + `build_durable_harness`），后两处构造点均显式传 `is_durable=`
- `grep -RIn "InMemoryToolRuntime(" dayu tests utils`：12 个真实构造点全部显式传 `is_durable=`
- 旧测试 / smoke（phase1/1.5/2/3/3multi/4/5/8 + utils/smoke_*）所有 `LocalRunHarness(...)` 与 `InMemoryToolRuntime(...)` 构造点均已 migrate
- §D7 N05 中文注释（`isinstance` 用于装配契约校验、非类型逃避）位于 `dayu/host/_run_harness.py:494-495`，紧邻 `event_store` isinstance 检查
- `PlainRunEventAppender` 类 docstring 含 “test-only fallback; never used in durable harness; durable path always uses AttemptScopedRunEventAppender via AttemptSupervisor.scoped_appender”（`dayu/host/_tool_runtime.py:169-170`）
- S1 禁区未触动：`_handle_owner_lost` body / `_finish_attempt_if_durable` legacy 分支 / supervisor / lease store / public API 在本 diff 中均无修改（`git diff` 未命中相关符号）；`dayu/host/__init__.py` 未变，`start_run` / `fetch_more_tool_result` 等仍在 `__all__`（与 S1 “保留 functional” 一致）

## Findings

### F01-未修复-[accepted→fixed-in-S1]-低-durable harness 未校验 tool_runtime 与自身 is_durable 双源一致性
- **入口/函数**: `LocalRunHarness.__post_init__`
- **文件(行号)**: `dayu/host/_run_harness.py:489-518`
- **输入场景**: 装配方调用 `LocalRunHarness(is_durable=True, ..., tool_runtime=InMemoryToolRuntime(is_durable=False, event_store=...))`，即 harness 声明 durable，但注入的 ToolRuntime 是 non-durable 装配。
- **实际分支**: harness invariant 仅校验 `attempt_supervisor` / `event_store` / `attempt_state_store` / `storage`，不校验 `tool_runtime.is_durable`。构造直接放行。
- **预期行为**: §D7 把 `is_durable` 定义为「装配显式真源」，且要求 ToolRuntime 与 harness 「与 harness 同源」。durable harness 注入 non-durable runtime 应在 __post_init__ fail fast，避免运行期才在 `_resolve_appender` 上沉默退化为 `PlainRunEventAppender`（即「invariant 立住后任何残留 plain-fallback 在测试上立即抛 RuntimeError」的设计意图被 mismatch 装配绕过）。
- **实际行为**: harness 声明 durable，但运行期 ToolRuntime 路径走 non-durable fallback，`_resolve_appender` 命中 `PlainRunEventAppender` 而不是 RuntimeError；durable 不变量在 ToolRuntime 这一面不收敛。
- **直接证据**: `_run_harness.py:489-518` 没有 `tool_runtime` 任何字段检查；`_tool_runtime.py:380-396` 的 `_resolve_appender` 仅依据自身 `self.is_durable`。`build_durable_harness` 装配同时传 True（`_durable_harness.py:243-244` / `265-266`）只是「装配方自律」而非 invariant 强制。
- **影响**: 局部行为错误：装配错误时不变量缺一道闸；不会导致已有路径回归（build_durable_harness 自己装配正确），但减弱 S1 设定的「双源契约」强度。CLAUDE.md「下层接口设计需假设上层不存在」原则下，harness 应主动验证 runtime 注入。
- **建议改法和验证点**: 在 `__post_init__` durable 分支增加 `if self.tool_runtime is not None and not self.tool_runtime.is_durable: raise RuntimeError("durable harness invariant violated: tool_runtime.is_durable must be True")`；非 durable 分支增加对称校验。新增测试两条：(a) `LocalRunHarness(is_durable=True, tool_runtime=InMemoryToolRuntime(is_durable=False, ...))` → RuntimeError；(b) 反向 mismatch → RuntimeError。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F02-未修复-[accepted→fixed-in-S1]-低-durable harness 未要求 tool_runtime 必填
- **入口/函数**: `LocalRunHarness.__post_init__`
- **文件(行号)**: `dayu/host/_run_harness.py:441` 字段声明 `tool_runtime: InMemoryToolRuntime | None = None`
- **输入场景**: durable 装配漏传 `tool_runtime`。
- **实际分支**: invariant 不检查 `tool_runtime`，构造通过；后续走 `start_run` 触发任意工具调用时 `_run_harness.py:2059/2074` 报 `tool_runtime_not_configured`。
- **预期行为**: durable 路径下 `tool_runtime` 是构造期硬约束（`build_durable_harness` 永远会传），缺失应在 __post_init__ 期暴露而非延迟到工具调用时。
- **实际行为**: 错误延后；invariant 套件不完整。
- **直接证据**: `_run_harness.py:441`、`489-518`。
- **影响**: 小：production 装配仍正确；仅在自定义装配路径下错误延迟。
- **建议改法和验证点**: durable 分支加 `if self.tool_runtime is None: raise RuntimeError("durable harness invariant violated: tool_runtime is required when is_durable=True")`；新增测试用例覆盖。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F03-未修复-[deferred→S2]-低-durable `_resolve_attempt_appender` 在 active_attempt 缺失但 ContextVar 命中时返回 active appender，未额外校验 active appender 类型
- **入口/函数**: `LocalRunHarness._resolve_attempt_appender`
- **文件(行号)**: `dayu/host/_run_harness.py:545-558`
- **输入场景**: 测试或异常路径下，durable harness 上下文里 `active_tool_runtime_appender()` 被人为安装为 `PlainRunEventAppender`（例如错误的 monkey-patch 或 ToolRuntime fallback 后污染 ContextVar），同时 `active_attempt is None`。
- **实际分支**: 走 `active = active_tool_runtime_appender(); if active is not None: return active`，会把 plain appender 当作合法返回值。
- **预期行为**: §D7「durable 路径永不返回 PlainRunEventAppender」是强约束。当前实现假设 ContextVar 永远只装载 `AttemptScopedRunEventAppender`（由 `ToolRuntimeOwnerScope` 安装），但 invariant 没有 isinstance 反向兜底。
- **实际行为**: 与 §D7 「永不返回 PlainRunEventAppender」原则有 1 个理论窗口被「ContextVar 装载错误对象」绕过。production 路径无现实触发，但削弱 invariant 强度。
- **直接证据**: `_run_harness.py:552-557`，无 isinstance 校验。
- **影响**: 局部；现实 path 无触发。adversarial 评估为「设计强约束未被代码强制」。
- **建议改法和验证点**: 在 durable 分支返回 `active` 前 `if isinstance(active, PlainRunEventAppender): raise RuntimeError(...)`；测试添加污染 ContextVar 的 case。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无（plan §S1 明确允许的 4 块改动 + 8 处构造点 migrate 与 invariant 测试，全部对照证据可裁决）。

## Residual Risk

- F01 / F02：S1 的 invariant 闸只建在 supervisor / event_store / attempt_state_store / storage 四个字段，`tool_runtime` 这一面缺一道；若 S2 删除 `_default_harness_for_running_loop` 时未补 tool_runtime invariant，自定义装配可能继续 mismatch。建议在 S2 一并补齐。
- F03：production 无触发，但 ContextVar 装载约束应被 invariant 强制，避免后续 slice 修改 ToolRuntime fallback 行为时引入回归。
- 测试覆盖只断言 invariant 阴性 + 构造成功；未对 `_resolve_attempt_appender` 在「durable + active_attempt 携带 owner_context」的阳性路径做单元断言（确认返回的是 `AttemptScopedRunEventAppender` 实例）。已有 phase8 supervisor 集成测试覆盖此路径，但单元 isolation 仍欠一条；non-blocking。
- `_NoopExec` 与 `_make_proxy` 在新增测试文件中通过 `# type: ignore[arg-type]` 绕开 `ToolExecutor` 协议，符合「测试用最小桩」惯例，但在 strict pyright 演进下属于潜在去 `ignore` 项；low priority。

---

## Controller Decisions + Fix Status (after re-review)

- **F01 (低)**: `accepted` → **fixed** in S1 fix pass. `LocalRunHarness.__post_init__` 现在校验 `tool_runtime.is_durable` 与 harness 同源（durable + tool_runtime non-durable / 反向 mismatch 均 RuntimeError）。新测试 `test_durable_rejects_non_durable_tool_runtime` / `test_non_durable_rejects_durable_tool_runtime` 覆盖。
- **F02 (低)**: `accepted` → **fixed** in S1 fix pass. durable 路径 `tool_runtime` 现在为构造期硬约束（`tool_runtime is None` → RuntimeError）。新测试 `test_durable_requires_tool_runtime` 覆盖。
- **F03 (低)**: `deferred-with-owner: S2`. `_resolve_attempt_appender` 对 ContextVar 装载 `PlainRunEventAppender` 的反向 isinstance 兜底，等到 S2 删除 `_default_harness_for_running_loop` 后随 ToolRuntime fallback 行为收紧时一并加。Plan §Risks R1 涵盖装配 mismatch 残留风险。

## Re-review Validation

- `pytest tests/host -q`: **306 passed in 2.38s**（新增 3 个测试：`test_durable_requires_tool_runtime` / `test_durable_rejects_non_durable_tool_runtime` / `test_non_durable_rejects_durable_tool_runtime`）
- `pyright dayu/host tests/host utils`: **0 errors / 0 warnings / 0 informations**
- `git diff --check`: 干净
- 所有 review accepted findings 已 fixed 或 deferred-with-owner，S1 review loop 通过。
