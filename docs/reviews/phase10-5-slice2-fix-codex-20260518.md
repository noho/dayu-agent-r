# P10.5 Slice 2 Fix - Codex

## Gate

当前 gate：P10.5 Slice 2 fix。

## Accepted Findings

### F1. `_PublicHostHandle.close()` must close durable resources even if scheduler close raises

已修复。`_PublicHostHandle.close()` 现在先关闭 public gate，再使用外层 `try/finally` 包住 `scheduler.close()`，确保 scheduler close 抛错时仍会继续尝试 projection catch-up，并在内层 `finally` 中关闭 `command_handle` 持有的 durable store。

保留语义：

- `host.close()` 不写 cancel / failed terminal facts。
- `_closed` 在 close 开始时置位，重复 close 仍幂等。
- scheduler close 原异常继续向调用方暴露，除非后续 catch-up / command close 自身抛出更晚的清理异常。

新增聚焦测试 `test_public_host_close_closes_command_handle_when_scheduler_close_raises`，覆盖 scheduler close 抛错后 projection catch-up 与 command handle close 仍被调用，且第二次 close 不重复执行清理链路。

### F2. Make context budget fallback explicit

已修复。`context_budget_policy=None` 的 command options fallback 从隐式三元表达式收口为 `_command_context_budget_fields_from_open_host_options(...)`，并用 `_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE` 与 `_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS` 命名解释内部 fallback 数值。

helper docstring 明确：

- fallback 只用于构造内部 `HostCommandHandleOptions` 的必填字段。
- 这不是 production context budget 默认值。
- 生产调用方需要显式预算治理时必须传入 `ContextBudgetPolicy`。
- 不从 Engine、extra payload 或 profile lookup 推导预算。

## Changed Files

- `dayu/host/open_host.py`
- `tests/host/test_open_host_runtime.py`
- `docs/reviews/phase10-5-slice2-fix-codex-20260518.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q`
  - Result: `5 passed in 0.24s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`

## Residual Risks / Open Questions

- 本次未改变 public API、schema/state-machine 或 Engine behavior。
- 若 projection catch-up 或 command handle close 本身抛错，Python 的 `finally` 语义可能覆盖先前 scheduler close 异常；当前 fix 只按 F1 要求保证后续清理被尝试，没有新增异常聚合机制。
- `dayu/host/README.md` 当前已有未归属本次 fix 的工作区改动；本次按 allowed files 限制未修改 README。

## Artifact Path

`docs/reviews/phase10-5-slice2-fix-codex-20260518.md`
