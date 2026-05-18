# P10.5 Slice 2 Re-Review

## Gate

- Gate: P10.5 Slice 2 re-review
- Fix artifact: `docs/reviews/phase10-5-slice2-fix-codex-20260518.md`
- Controller adjudication: `docs/reviews/phase10-5-slice2-code-review-controller-adjudication-20260518.md`
- Source reviews: `docs/reviews/phase10-5-slice2-code-review-mimo-20260518.md`, `docs/reviews/phase10-5-slice2-code-review-ds-20260518.md`
- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Reviewer: MiMo
- Date: 2026-05-18

## F1 Verification: close() resource safety

### 要求

scheduler.close() 抛错时仍尝试 projection catch-up 与 command_handle.close；保持幂等、closed gate、无 cancel/failed terminal facts。

### 实现证据

`open_host.py:300-307`（当前 diff）:

```python
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    try:
        await self._scheduler.close()
    finally:
        try:
            self._projection_catchup_port.catch_up_projection()
        finally:
            self._command_handle.close()
```

### 逐项验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| scheduler.close() 抛错后仍执行 projection catch-up | PASS | 外层 `try/finally`：scheduler 抛错 → 进入 `finally` → 执行 `catch_up_projection()` |
| scheduler.close() 抛错后仍执行 command_handle.close() | PASS | 内层 `try/finally`：无论 projection 是否抛错，`finally` 始终执行 `command_handle.close()` |
| 幂等 | PASS | `if self._closed: return` 在首行，第二次 close 直接返回 |
| closed gate | PASS | `self._closed = True` 在 close 开始时置位，后续 public method 调用均 raise `HostClosedError` |
| 无 cancel/failed terminal facts | PASS | close 方法不接触 EventLog，scheduler.close 只 cancel worker tasks 不写 canonical facts |
| 原异常继续向调用方暴露 | PASS | Python `finally` 语义：scheduler 异常在 finally 执行后继续传播（除非 finally 自身抛出更晚异常） |

### 测试覆盖

`test_open_host_runtime.py:254-272` — `test_public_host_close_closes_command_handle_when_scheduler_close_raises`:

- 使用 `_RaisingSchedulerClose`（close 始终抛 `RuntimeError`）、`_RecordingCommandHandleClose`、`_RecordingProjectionCatchupPort` 构造 `_PublicHostHandle`
- 第一次 `close()` 验证 `RuntimeError` 被抛出（`pytest.raises`）
- 第二次 `close()` 验证幂等（不抛错、不重复执行清理）
- 断言 `scheduler.close_count == 1`、`projection_catchup_port.catch_up_count == 1`、`command_handle.close_count == 1`

**F1 状态：PASS — 修复正确，测试充分。**

## F2 Verification: context budget fallback explicitness

### 要求

`context_budget_policy=None` fallback 显式说明为内部 HostCommandHandleOptions fallback，未改变 public API，未从 Engine/extra payload/profile 推导预算。

### 实现证据

1. **常量命名**（`open_host.py:62-67`）：

```python
_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE = 8192
"""``context_budget_policy=None`` 时内部 command options 使用的兜底窗口。"""

_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS = 1024
"""``context_budget_policy=None`` 时内部 command options 使用的兜底输出预留。"""
```

`_INTERNAL_COMMAND_FALLBACK_` 前缀 + docstring 明确标注"内部 command options 使用的兜底"。

2. **专用 helper**（`open_host.py:478-510`）：

`_command_context_budget_fields_from_open_host_options(...)` 返回 `_CommandContextBudgetFields` dataclass。docstring 明确：

- fallback 只用于构造内部 `HostCommandHandleOptions` 必填字段
- 不是生产 context budget 默认值
- 生产调用方需显式传入 `ContextBudgetPolicy`
- 不从 Engine、extra payload 或 profile lookup 推导预算

3. **`_CommandContextBudgetFields` dataclass**（`open_host.py:70-82`）：frozen、slots，字段类型严格。

### 逐项验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 显式说明为内部 fallback | PASS | 常量名 `_INTERNAL_COMMAND_FALLBACK_*` + helper docstring 四点声明 |
| 未改变 public API | PASS | `OpenHostOptions` shape 未变；`_CommandContextBudgetFields`、`_command_context_budget_fields_from_open_host_options` 均为模块私有 |
| 未从 Engine/extra payload/profile 推导预算 | PASS | fallback 仅使用硬编码常量，无 Engine/extra payload/profile 查询路径 |
| helper 职责收口 | PASS | 从 `_command_options_from_open_host_options` 中抽取独立 helper，原三元表达式替换为显式 dataclass 构造 |

**F2 状态：PASS — 修复正确，契约清晰度显著提升。**

## New Findings Check

### 是否引入新 public API？

未引入。新增符号均为模块私有（`_` 前缀）：

- `_CommandContextBudgetFields`（frozen dataclass）
- `_command_context_budget_fields_from_open_host_options`（helper）
- `_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE`（常量）
- `_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS`（常量）

### 是否引入 schema/state-machine/Engine 变更？

未引入。变更范围限于 `open_host.py` 和 `test_open_host_runtime.py`，不触及 `durable/schema.py`、Engine contracts 或状态机。

### 是否越界到 Slice 3/4/5？

未越界。F1 只修改 close 清理链路，F2 只收口 context budget fallback 常量命名与 helper docstring。均属于 Slice 2 lifecycle root scope。

### 新的 non-blocking findings？

无新 non-blocking finding。F1 fix 的嵌套 `try/finally` 结构清晰；F2 的 `_CommandContextBudgetFields` dataclass 比原三元表达式更可读。Controller adjudication 中标记的 deferred items（MiMo N1/N2/N4/N5/N6、DS O2/O3）均未被本次 fix 触及，状态不变。

## Tests / Pyright

- `pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q` → **5 passed in 0.24s** ✓
- `python -m pyright dayu/host tests/host` → **0 errors, 0 warnings, 0 informations** ✓

结果与 fix artifact 报告一致，可复现。

## Verdict

**PASS**

Blocking count: **0**

## F1/F2 Status

| Finding | Status | 说明 |
|---------|--------|------|
| F1: close() resource safety | **FIXED** | 嵌套 try/finally 保证 scheduler 抛错后 projection catch-up 与 command_handle.close 仍被尝试；幂等、closed gate、无 terminal facts 均保持 |
| F2: context budget fallback explicitness | **FIXED** | 常量名 `_INTERNAL_COMMAND_FALLBACK_*`、专用 helper `_command_context_budget_fields_from_open_host_options`、显式 docstring 四点声明；public API 不变 |

## Residual Risks

- F1 嵌套 `finally` 中若 projection catch-up 或 command_handle.close 自身抛错，Python 会覆盖先前 scheduler 异常（fix artifact 已记录）。当前按 F1 要求只保证"后续清理被尝试"，未新增异常聚合机制，可接受。
- `watch_session_events` 仍为 `NotImplementedError` 占位，Slice 4 owner。
- `_DEFAULT_CONTEXT_WINDOW_SIZE` / `_DEFAULT_RESERVED_OUTPUT_TOKENS` 现已改名为 `_INTERNAL_COMMAND_FALLBACK_*`，语义清晰，但数值本身仍非设计文档推导值。后续 slice 需确认是否需要可配置。
- Controller adjudication 中 deferred items（MiMo N1 构造冗余、N2 跨模块 import、N4 docstring、N5 占位、N6 轮询、DS O2/O3）状态不变，均不阻塞当前 gate。

## Artifact Path

`docs/reviews/phase10-5-slice2-rereview-mimo-20260518.md`
