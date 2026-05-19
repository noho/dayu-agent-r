# P10.5 Slice 2 Code Review

## Gate

- Gate: P10.5 Slice 2 code review
- Slice: Production Composition Root, Handle Lifecycle And Command Wakeup
- Review scope: uncommitted workspace diff relative to HEAD (`d0e79a6`)
- Reviewer: MiMo
- Date: 2026-05-18

## Changed Files

- `dayu/host/open_host.py` — production composition root, public handle delegation, handle lifecycle
- `dayu/host/api.py` — `HostLocalExecutionOptions` compactor fields + validation
- `dayu/host/README.md` — current-fact sync
- `docs/host/implementation-control.md` — gate state sync
- `tests/host/test_open_host_runtime.py` — submit_followup queue auto-wakeup, compactor baseline fail-closed
- `tests/host/test_public_lifecycle_smoke.py` — close_session vs host.close vs cancel, idempotent close, no terminal facts on opener close

## Scope Boundary Check

Slice 2 allowed items (from plan §Slice 2):

| Item | Implemented | Evidence |
|------|-------------|----------|
| Build internal `HostCommandHandleOptions` from `OpenHostOptions` | Yes | `_command_options_from_open_host_options` (open_host.py:422-475) |
| Build internal `HostLocalExecutionOptions` from `OpenHostOptions` | Yes | `_local_execution_options_from_open_host_options` (open_host.py:478-538) |
| Public async handle delegation with handle-open validation | Yes | `_PublicHostHandle` class (open_host.py:93-317) |
| Shared `ActiveWorkerRegistry` for command handle and scheduler | Yes | `active_registry = ActiveWorkerRegistry()` passed to both (open_host.py:357,366,379) |
| After-commit wakeup from mutating commands to scheduler | Yes | `admission_service = create_host_admission_service(..., wakeup_port=scheduler, ...)` (open_host.py:370-373) |
| Memory projection catch-up wiring | Yes | `_MemoryProjectionCatchupPort` (open_host.py:68-90), flushed on close (open_host.py:305) |
| Compactor baseline mapping to internal options | Yes | `_local_execution_options_from_open_host_options` maps all 6 compactor fields (open_host.py:500-530) |
| `compactor_baseline=None` fail-closed | Yes | All compactor fields map to `None`, no fake defaults (open_host.py:500-530) |
| Idempotent `host.close()` / `__aexit__` | Yes | `_closed` flag guard, scheduler/projection/handle close (open_host.py:291-307) |
| No cancel/failed terminal facts on opener close | Yes | `close()` only sets `_closed`, closes scheduler, flushes projection, closes handle (open_host.py:300-307) |
| `watch_session_events` placeholder with closed-handle validation | Yes | Raises `NotImplementedError` after `_raise_if_closed()` (open_host.py:274-289) |

**No scope creep detected.** Slice 2 does not implement Slice 3 request contract migration, Slice 4 live HostEvent fanout, Slice 5 steer/retry/replay semantics, or Slice 6 smoke matrix.

## Findings

### N1. `HostLocalExecutionOptions` 构造冗余（Non-blocking）

**Severity**: Non-blocking / Improvement

**Evidence**: `open_host.py:349-351` — `__aenter__` 先调用 `_local_execution_options_from_open_host_options(self._options)` 构造 `local_execution`，再把同一 `self._options` 传给 `_command_options_from_open_host_options(self._options)`。后者内部再次调用 `_local_execution_options_from_open_host_options(options)`（open_host.py:431），同一对象构造两次。

**影响**: 不影响正确性，但每次 `open_host` 进入 runtime 都多构造一次完整的 `HostLocalExecutionOptions`，包含所有校验逻辑。功能无害，属于性能浪费。

**修复建议**: 在 `__aenter__` 中构造一次 `local_execution`，传入 `_command_options_from_open_host_options` 作为参数；或在 `_command_options_from_open_host_options` 内部只构造一次并同时返回 command options 与 local execution options。

### N2. 跨模块私有函数 import（Non-blocking）

**Severity**: Non-blocking / Code smell

**Evidence**: `open_host.py:50-52` — `from dayu.host.command import _durable_options_from_public_options as _durable_options_from_command_options`。导入 `command.py` 中的私有函数 `_durable_options_from_public_options`。

**影响**: `open_host.py` 依赖 `command.py` 的内部实现。若 `command.py` 重构该函数签名，`open_host.py` 会静默断裂。但该函数是将 `HostCommandHandleOptions` 映射为 `HostDurableStoreOptions` 的唯一规范实现，复制逻辑更差。

**修复建议**: 可接受当前状态；若后续 `open_host.py` 不再需要 `command.py` 的 command handle 依赖，考虑将 durable options mapper 提取到共享内部模块。

### N3. `context_budget_policy=None` 时隐式默认 context window 值（Non-blocking）

**Severity**: Non-blocking / Design note

**Evidence**: `open_host.py:63-64` — `_DEFAULT_CONTEXT_WINDOW_SIZE = 8192` 和 `_DEFAULT_RESERVED_OUTPUT_TOKENS = 1024` 在 `context_budget_policy is None` 时被使用（open_host.py:434-448）。

**影响**: 当 `OpenHostOptions.context_budget_policy=None` 时，`HostCommandHandleOptions` 仍会获得 `context_window_size=8192` 和 `reserved_output_tokens=1024`。这些值不是从设计文档推导的，也没有在 `OpenHostOptions` 中暴露为可配置字段。若生产环境需要不同默认值，调用方无法通过 public contract 覆盖，除非显式传入 `ContextBudgetPolicy`。

**修复建议**: 当前 Slice 2 使用这些默认值是 pragmatic 选择，可在 Slice 3 或后续 slice 中决定是否将这些默认值提升为 `OpenHostOptions` 的可选字段或从设计文档获取。不阻塞当前 slice。

### N4. `_PublicHostHandle.close()` docstring 与实现关闭顺序描述不完全匹配计划（Non-blocking）

**Severity**: Non-blocking / Docstring accuracy

**Evidence**: `open_host.py:293-294` — docstring 写"关闭顺序为 public gate、scheduler、projection flush、durable store"，但实际实现（open_host.py:300-307）顺序为 `_closed = True`（gate）→ `scheduler.close()`（含 active workers/lane waits）→ `projection_catchup_port.catch_up_projection()` → `command_handle.close()`（含 durable store）。计划描述为"close public gate, stop scheduler / promotion / supervisor, close live watch fanout, cancel / close active worker tasks and lane waits, flush projection catch-up, close durable store"。

**影响**: 实现正确地完成了计划要求的所有关闭步骤，只是 docstring 粒度较粗。`scheduler.close()` 内部已包含停止 promotion、supervisor、active workers 和 lane waits。无功能影响。

**修复建议**: 可选地细化 docstring 以更精确反映内部关闭步骤。不阻塞。

### N5. `watch_session_events` 返回类型声明为 `AsyncIterator[HostEvent]` 但实际抛出 `NotImplementedError`（Non-blocking）

**Severity**: Non-blocking / Expected placeholder

**Evidence**: `open_host.py:274-289` — 方法签名声明返回 `AsyncIterator[HostEvent]`，但实际在 `_raise_if_closed()` 后立即 `raise NotImplementedError("watch_session_events is owned by P10.5 Slice 4")`。

**影响**: 类型检查器和调用方看到的返回类型与实际行为不符。但这是 Slice 2 计划内的占位行为，Slice 4 才实现真实 fanout。docstring 已明确说明此为 Slice 4 占位。

**修复建议**: 无需修复。Slice 4 实现时自然解决。

### N6. 测试 `_wait_for_run_status` 使用轮询等待（Non-blocking）

**Severity**: Non-blocking / Test pattern

**Evidence**: `test_open_host_runtime.py:198-217` 和 `test_public_lifecycle_smoke.py:241-260` — 使用 `for _ in range(100): ... await asyncio.sleep(0.01)` 轮询 Run 状态，总超时约 1 秒。

**影响**: 测试可能在极端慢环境下 flaky。但 1 秒超时对本地 SQLite + mock worker 来说足够宽裕。这是测试代码，不影响生产。

**修复建议**: 可接受。若后续出现 flaky，可增加超时或改用事件驱动等待。

## Blocking Findings

**无 blocking finding。**

所有实现严格遵循 Slice 2 scope 边界，composition root 正确装配了 durable store、scheduler、shared registry、memory catch-up、compactor baseline 和 command wakeup。public handle delegation 完整，handle-open validation 和 post-close `HostClosedError` 正确实现。idempotent close 幂等且不写 cancel/failed terminal facts。`compactor_baseline=None` 正确 fail-closed。测试覆盖了计划要求的核心场景。

## Verdict

**PASS** — blocking count = 0

## Accepted / Non-blocking Findings

| ID | Summary | Severity |
|----|---------|----------|
| N1 | `HostLocalExecutionOptions` 构造冗余 | Improvement |
| N2 | 跨模块私有函数 import | Code smell |
| N3 | `context_budget_policy=None` 隐式默认值 | Design note |
| N4 | close docstring 粒度较粗 | Docstring accuracy |
| N5 | `watch_session_events` 占位返回类型 | Expected placeholder |
| N6 | 测试轮询等待模式 | Test pattern |

## Residual Risks

- `watch_session_events(...)` 仍为 Slice 4 占位；Service 当前无法通过 public contract 观察事件。
- `SubmitFollowupRequest` typed fields 迁移和 per-run effective config/tool-set freeze 仍属 Slice 3。
- Steer/retry/replay command 语义和 WAITING public resume smoke 仍属 Slice 5。
- Opener close 后已运行的 durable Run 状态不受影响；Recovery/orphan classification 属 Phase 11。
- `_DEFAULT_CONTEXT_WINDOW_SIZE` / `_DEFAULT_RESERVED_OUTPUT_TOKENS` 非设计文档推导值，后续 slice 需确认是否需要可配置。

## Artifact Path

`docs/reviews/phase10-5-slice2-code-review-mimo-20260518.md`
