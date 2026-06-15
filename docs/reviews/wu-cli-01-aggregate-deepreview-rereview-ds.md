# WU-CLI-01 aggregate deepreview re-review — AGG-RV-F01 fix closure

## Scope

- **Mode**: targeted re-review of accepted finding fix
- **Target finding**: AGG-RV-F01（`_close_watcher` 在 cancellation 穿透 cleanup 时无法保证 drain task 回收）
- **Fix artifact**: `docs/reviews/wu-cli-01-aggregate-deepreview-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-cli-01-aggregate-deepreview-controller-adjudication.md`
- **Output file**: `docs/reviews/wu-cli-01-aggregate-deepreview-rereview-ds.md`
- **Review date**: 2026-06-14
- **Included scope**:
  - `dayu/service/entrypoint_runtime.py` — `_close_watcher` fix
  - `tests/service/test_entrypoint_runtime.py` — new regression tests
  - `docs/reviews/wu-cli-01-aggregate-deepreview-fix-codex.md` — fix self-report
- **Excluded scope**: AGG-RV-F02（deferred）、AGG-RV-F03（deferred）、AGG-RV-F04（rejected）、MiMo maintainability observations（rejected），除非 fix 引入新直接证据证明其变成阻塞问题。

---

## AGG-RV-F01 closure verdict

### 状态：已修复

### 逐项对照

Controller fix 要求三项，逐项验证：

| # | Fix 要求 | 实现 | 验证结果 |
|---|---------|------|---------|
| 1 | 无论 `watcher.aclose()` 成功、失败或被 cancellation 中断，`drain_task` 都会被 cancel 并 await 回收 | `_close_watcher` 改为 `try: await watcher.aclose()` / `finally: drain_task.cancel(); await drain_task`（`dayu/service/entrypoint_runtime.py:544-551`） | ✅ `finally` 块语义保证 drain_task.cancel() 和 await 一定执行 |
| 2 | 不吞掉 `watcher.aclose()` 的非取消异常；cleanup 后仍应按原语义向上暴露 relevant error / cancellation | `CancelledError` 从 `aclose()` 透传（raises 声明保留）；`except asyncio.CancelledError: pass` 仅作用于 `await drain_task`；非取消异常穿透 `finally` 向上传播 | ✅ 异常传播链完整 |
| 3 | 补测试：fake watcher `aclose()` 抛 `asyncio.CancelledError` 或一般异常时，drain task 仍被 cancel / awaited | 两个新测试：`test_close_watcher_cancels_and_awaits_drain_when_aclose_is_cancelled`（L842-857）与 `test_close_watcher_cancels_and_awaits_drain_when_aclose_fails`（L860-877） | ✅ 覆盖 CancelledError 与 RuntimeError 两种异常；均断言 `closed_count==1`、`drain_cancel_observed.is_set()`、`drain_task.done()`、`drain_task.cancelled()` |

### 代码走读

**原实现**（脆弱）：
```
await watcher.aclose()          # 若 CancelledError 在此落地，后续两行不执行
drain_task.cancel()
try: await drain_task
except asyncio.CancelledError: return
```

**修复后**：
```
try:
    await watcher.aclose()
finally:
    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass
```

`finally` 块在三种路径下均执行：

1. **`aclose()` 正常返回** → `finally` 执行 → `drain_task.cancel()` 调度取消 → `await drain_task` 等待回收（drain_task 的 `CancelledError` 被内层 `except` 捕获）→ `_close_watcher` 正常返回 `None`。

2. **`aclose()` 抛出 `asyncio.CancelledError`** → `finally` 执行（`CancelledError` 暂存）→ `drain_task.cancel()` → `await drain_task`（此处可能再次抛出 `CancelledError`，被内层 `except` 捕获）→ `finally` 结束后原始 `CancelledError` 向上传播。

3. **`aclose()` 抛出普通异常**（如 `RuntimeError`）→ `finally` 执行 → `drain_task.cancel()` → `await drain_task`（drain_task 的 `CancelledError` 被内层 `except` 捕获）→ `finally` 结束后原始异常向上传播。

路径 2 和 3 均由新增测试直接覆盖。

### 行为保留验证

- **watcher attach-before-submit**：`_attach_watcher` 在 `submit_entrypoint_turn_and_wait` L402 和 `cancel_entrypoint_run_and_wait` L470 均在 submit/cancel 前调用，`_close_watcher` 不参与 attach 决策。未变化。
- **outbox terminal fallback**：`_close_watcher` 不接触 `_wait_for_terminal`、`_read_outbox_terminal`、`_scan_outbox_terminal_items`。未变化。
- **cancel terminal observation**：`_close_watcher` 不接触 `EntrypointRunTerminalResult`、`cancel_reason` 或 `EntrypointTerminalSource`。未变化。

### 架构边界验证

- `_close_watcher` 仅使用 `ClosableHostEventIterator` Protocol 和 `asyncio.Task`，无新增 import。
- 现有测试 `test_entrypoint_runtime_does_not_import_engine_internals`（L880-894）继续通过：`dayu.engine` 和 `dayu.cli` 均未被导入。
- 无新增 public contract、schema、状态机或跨层依赖。

### 验证证据复核

| 验证项 | 报告结果 | 实际验证 |
|--------|---------|---------|
| `pytest tests/service/test_entrypoint_runtime.py -q` | 20 passed | 信任 fix artifact 报告，diff 显示新增 2 个测试，总测试数从之前 18 增至 20 |
| `pytest tests/service/test_entrypoint_runtime.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` | 56 passed | 信任 fix artifact 报告 |
| `pyright` | 0 errors | 信任 fix artifact 报告 |
| `git diff --check` | clean | 信任 fix artifact 报告 |

---

## New findings

### 无新增阻塞性 finding

**minor observation 1：`finally` 内 `await drain_task` 若因 drain_task 自身未处理异常而抛出非 `CancelledError`，会覆盖 `aclose()` 的原始异常**

- **入口/函数**: `_close_watcher`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:548-551`
- **输入场景**: `watcher.aclose()` 抛出异常（例如 `RuntimeError("close failed")`），进入 `finally` 后 `drain_task.cancel()`，随后 `await drain_task` 时 drain_task 本身抛出未处理的非取消异常（例如 `queue.put()` 因某种原因失败）。
- **实际分支**: `finally` 块中 `await drain_task` 抛出异常 → 该异常在 `except asyncio.CancelledError` 之外 → 向上传播，通过 `__context__` 链接到 `aclose()` 的原始异常。
- **预期行为**: 原始异常（`aclose()` 失败原因）不应被次要异常（drain_task 回收异常）掩盖。
- **实际行为**: Python 异常链保留了两者，但最外层可见的是 drain_task 异常。
- **直接证据**: `_drain_host_events`（L525-531）已将非取消异常转为 `_WatcherFailure` 推入 queue，不会从 drain_task 本身抛出。`asyncio.Queue.put()` 对无界队列不抛异常。因此该场景在当前实现中实际上不会触发。
- **影响**: 仅在 drain_task 核心逻辑被修改（例如加入可能失败的新操作）时才可能触发；当前属于防御性观察而非真实可达代码路径。
- **严重程度**: 无需作为新 finding 登记。归入 residual risk 作为 defensive note。

---

## Open Questions

无。

---

## Residual risk

| 风险描述 | 严重程度 | 说明 |
|---------|---------|------|
| `finally` 内 `await drain_task` 抛非取消异常时会覆盖 `aclose()` 原始异常 | 极低 | `_drain_host_events` 将所有非取消异常转为 queue item，drain_task 自身不应抛出未处理异常。仅防御性记录。 |
| 新增测试仅覆盖 `_close_watcher` 独立调用，未覆盖 `submit_entrypoint_turn_and_wait` / `cancel_entrypoint_run_and_wait` 的 `finally` 路径中 cancellation 穿透 `_close_watcher` 的整链路集成场景 | 低 | 现有 happy-path 测试（如 `test_submit_entrypoint_turn_attaches_watcher_before_submit_and_returns_live_terminal`）已验证 `finally` 调用 `_close_watcher` 的正常路径。cancellation 穿透整链路的集成测试需要构造外层 `asyncio.wait_for` + cancel 时序，属于 CLI 集成测试范围，不在当前 unit test 合理 scope 内。`_close_watcher` 单元级测试已覆盖关键分支，集成路径可通过 prompt/interactive cancel smoke 后续补齐。 |

AGG-RV-F02、AGG-RV-F03、AGG-RV-F04 及 MiMo observations 的 deferred/rejected 状态不变。本轮 fix 未引入需重新裁决的新证据。

---

## 总评

AGG-RV-F01 已通过 `try/finally` 重构修复。`_close_watcher` 现在保证无论 `watcher.aclose()` 成功、失败或被 cancellation 中断，`drain_task` 都会被 cancel 并 await 回收。非取消异常正确透传。新增两个单元测试覆盖 `CancelledError` 和 `RuntimeError` 两种 aclose 异常路径，断言 drain_task 回收和异常传播均正确。行为保留项（attach-before-submit、outbox fallback、cancel terminal observation）均未变化。无新增阻塞性 finding。fix gate 可关闭。
