# P10.5 Slice 2 Re-review

## Gate

当前 gate：P10.5 Slice 2 re-review。

## Inputs

- Fix artifact: `docs/reviews/phase10-5-slice2-fix-codex-20260518.md`
- Controller adjudication: `docs/reviews/phase10-5-slice2-code-review-controller-adjudication-20260518.md`
- Source reviews: MiMo (`phase10-5-slice2-code-review-mimo-20260518.md`), DS (`phase10-5-slice2-code-review-ds-20260518.md`)
- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Review target: 当前工作区 uncommitted diff after Slice 2 fix

## F1 Verification: `_PublicHostHandle.close()` try/finally 清理链路

### 证据

`dayu/host/open_host.py:310-329`：

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

### 逐项核查

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| scheduler.close 抛错时仍尝试 projection catch-up | PASS | 外层 `try/finally` 保证 `finally` 块在 scheduler close raise 后仍执行 |
| scheduler.close 抛错时仍关闭 command_handle | PASS | 内层 `try/finally` 保证 projection catch-up 后（即使其抛错）仍执行 `command_handle.close()` |
| 幂等 | PASS | `if self._closed: return` 在最前；第二次 close 不重复执行清理链路 |
| closed gate 在 close 开始时置位 | PASS | `self._closed = True` 在 try 块之前 |
| 不写 cancel/failed terminal facts | PASS | close 方法不接触 EventLog；无 CANCEL_REQUESTED/RUN_CANCELLED/RUN_FAILED 写入 |
| 测试覆盖 | PASS | `test_public_host_close_closes_command_handle_when_scheduler_close_raises` 验证 scheduler close 抛错后 catch-up 与 command handle close 各执行一次；二次 close 幂等 |

### Veredict: **FIXED**

## F2 Verification: context_budget_policy=None fallback 显式化

### 证据

`dayu/host/open_host.py:63-68`：

```python
_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE = 8192
"""``context_budget_policy=None`` 时内部 command options 使用的兜底窗口。"""

_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS = 1024
"""``context_budget_policy=None`` 时内部 command options 使用的兜底输出预留。"""
```

`dayu/host/open_host.py:486-516` — `_command_context_budget_fields_from_open_host_options` docstring：

> ``OpenHostOptions.context_budget_policy`` 为 ``None`` 时，本 helper 只为满足内部 ``HostCommandHandleOptions`` 必填字段构造 fallback；这不是生产 context budget 默认值。生产调用方需要显式预算治理时必须传入 ``ContextBudgetPolicy``，本路径不会从 Engine、extra payload 或 profile lookup 推导预算。

### 逐项核查

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| fallback 显式说明为内部 HostCommandHandleOptions fallback | PASS | 常量命名 `_INTERNAL_COMMAND_FALLBACK_`，docstring 明确"内部 command options 使用的兜底" |
| 未改变 public API | PASS | `OpenHostOptions.context_budget_policy` 类型仍为 `ContextBudgetPolicy \| None`，无新增 public fields |
| 明示不是生产默认值 | PASS | helper docstring 明确"这不是生产 context budget 默认值" |
| 不从 Engine 推导预算 | PASS | docstring 明确"不会从 Engine、extra payload 或 profile lookup 推导预算" |
| 不从 extra payload 推导 | PASS | 同上 |
| 不从 profile lookup 推导 | PASS | 同上 |
| 提取为独立 helper + 内部 dataclass | PASS | `_CommandContextBudgetFields` frozen dataclass + `_command_context_budget_fields_from_open_host_options` 独立函数 |

### Verdict: **FIXED**

## Scope Boundary Check

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 未新增 public API | PASS | `__all__ = ["open_host"]` 不变；`Host` Protocol 不变；无新 public 类型导出 |
| 未触及 schema | PASS | `git diff --stat` 未包含 `durable/schema.py` 或任何 schema 文件 |
| 未触及 state-machine | PASS | Engine contracts 未修改 |
| 未触及 Engine | PASS | `dayu/engine/` 目录无变更 |
| 未越界到 Slice 3 | PASS | `SubmitFollowupRequest` 仍使用旧 shape；无 `system_prompt`/`user_prompt`/`tool_names` per-run override |
| 未越界到 Slice 4 | PASS | `watch_session_events` 仍为 `NotImplementedError` 占位 |
| 未越界到 Slice 5 | PASS | steer/retry/replay/WAITING resume 语义未改变 |
| 未越界到 Slice 6 | PASS | 无 real-runner smoke matrix 变更 |
| api.py 变更属于 Slice 2 原始实现 | PASS | `HostLocalExecutionOptions` 新增的 `compactor_runner_spec`/`compactor_runner_options`/`compactor_policy_ref` 字段是 plan §Typed Options Shape 中 `CompactorExecutionBaseline` 的内部映射，非 fix 引入 |

## Tests / Pyright 独立验证

```
$ source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q
5 passed in 0.23s

$ source .venv/bin/activate && python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations
```

结果与 fix artifact 一致，可信。

## Deferred / Accepted Residual（来自 controller adjudication，fix 未触及）

| ID | 描述 | 状态 |
| --- | --- | --- |
| MiMo N1 | `HostLocalExecutionOptions` 构造冗余 | 未修；controller 允许不修 |
| MiMo N2 / DS O1 | 跨模块私有 import | 未修；controller 允许不修 |
| MiMo N4 | close docstring 粒度 | 已随 F1 自然细化（docstring 增加"scheduler close 失败时仍会尽力执行"说明） |
| MiMo N5 | `watch_session_events` placeholder | Slice 4 owner |
| MiMo N6 | 测试轮询等待 | 未修；controller 允许 |
| DS O2 | `_MemoryProjectionCatchupPort` 持有完整 `OpenHostOptions` | 未修；controller 允许 |
| DS O3 | 测试直读 SQLite | Slice 4/Slice 6 owner |

## New Findings

**无新增 finding。**

fix 未引入回归、未扩散变更范围、未新增公开类型、未触及 Engine/schema/state-machine。

## Residual Risks

- Python `finally` 语义：若 `scheduler.close()` 抛出异常 A，随后 `projection_catchup_port.catch_up_projection()` 抛出异常 B，A 会被 B 覆盖。当前 fix 按 F1 要求保证后续清理被尝试，未新增异常聚合机制。此风险概率极低（projection catch-up 为纯内存操作），且 fix artifact 已明确记录。
- `HostLocalExecutionOptions` 构造冗余（MiMo N1）未消除：`__aenter__` 调用 `_local_execution_options_from_open_host_options` 一次，`_command_options_from_open_host_options` 内部再调用一次。不影响正确性，后续 cleanup 可处理。

## Verdict

**PASS**

Blocking count: **0**

| Finding | Status |
| --- | --- |
| F1: close() try/finally 清理链路 | **FIXED** |
| F2: context budget fallback 显式化 | **FIXED** |
| 新 public API / schema / Engine / 越界变更 | **NONE** |
| tests 可信 | **YES** (5 passed) |
| pyright 可信 | **YES** (0 errors) |

## Artifact Path

`docs/reviews/phase10-5-slice2-rereview-ds-20260518.md`
