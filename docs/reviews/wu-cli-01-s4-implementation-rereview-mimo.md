# WU-CLI-01 CLI-01-S4 Implementation Re-Review — AgentMiMo

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S4, Interactive command using the same Service session semantics
- Gate: implementation re-review (after low-fix)
- Agent: AgentMiMo
- Date: 2026-06-14
- Review target: 未提交改动（当前 workspace，含 low-fix）

## Review Scope

本轮仅重点复核 4 项：

1. DS finding 1 是否关闭：输入态 Ctrl-C 行为已被测试固定为 exit 130，并且不发 submit/cancel。
2. DS finding 2 是否关闭：运行态 SIGINT task cleanup 不再有分支和 finally 重复 cancel/await 代码异味，语义不变。
3. controller pre-review blocker 仍关闭：等待 run id 阶段 submit 先完成返回 terminal，submit 先失败透传异常，不误映射成 130。
4. low-fix 是否引入新的架构/类型/测试问题。

---

## Finding-by-Finding Verdict

### 1. DS Finding 1 — 输入态 Ctrl-C 测试覆盖 → **Pass (Closed)**

**直接证据：**

测试 `test_interactive_input_keyboard_interrupt_exits_without_run_requests`（`test_interactive_command.py:546-569`）：

```python
class _KeyboardInterruptInputReader:
    def __call__(self, _prompt: str) -> str:
        raise KeyboardInterrupt

# 测试断言：
assert exit_code == EXIT_KEYBOARD_INTERRUPT      # 130
assert fake_host.submit_requests == []            # 无 submit
assert fake_host.cancel_requests == []            # 无 cancel
```

**生产代码路径：**

`_read_user_input`（`interactive.py:849`）调用裸 `input(prompt)`，输入态 Ctrl-C 抛 `KeyboardInterrupt`，穿透 `_run_interactive_repl` → `_run_interactive_command_async`，由 `run_interactive_command`（`interactive.py:253`）的 `except KeyboardInterrupt` 捕获并返回 `EXIT_KEYBOARD_INTERRUPT`（130）。`_submit_interactive_turn_handling_sigint` 从未被调用，submit/cancel 零发出。

**结论：** 行为固定为 exit 130 + 无 submit/cancel。测试覆盖到位。Pass。

---

### 2. DS Finding 2 — 运行态 SIGINT task cleanup 重复 cancel/await → **Pass (Closed)**

**DS 原始问题：** `sigint_task` 在分支内显式 `cancel()` 后，`finally` 又无条件 `cancel()`，产生双重取消代码异味。

**low-fix 改动分析：**

引入 `_cancel_and_await_task` helper（`interactive.py:509-522`）：

```python
async def _cancel_and_await_task(task: asyncio.Task[_TaskResult]) -> None:
    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError):
        await task
```

该 helper 内含 `task.done()` 守卫，对已完成/已取消 task 的 `cancel()` 调用是 no-op。

**各函数的 cleanup 模式：**

| 函数 | 分支内 cancel | finally cleanup | 重复？ |
|------|-------------|----------------|--------|
| `_submit_interactive_turn_handling_sigint` (L487-506) | 无显式 sigint_task.cancel | `_cancel_and_await_task(sigint_task)` | 无重复 |
| `_cancel_interactive_turn_after_first_sigint` (L563-565) | `submit_task.cancel()` + await | 无（调用方 finally 负责 sigint_task） | 无重复 |
| `_wait_for_run_id_or_local_exit` (L604-606) | `submit_task.cancel()` + await | `_cancel_and_await_task(run_id_task)` + `_cancel_and_await_task(second_sigint_task)` | 无重复 |
| `_cancel_run_waiting_for_terminal_or_second_sigint` (L664-666) | `cancel_task.cancel()` + await | `_cancel_and_await_task(second_sigint_task)` | 无重复 |

每个 asyncio task 只有一个明确的 cancel 点：要么在分支内显式 cancel，要么在 finally 由 helper 统一清理。`_cancel_and_await_task` 的 `task.done()` 守卫确保即使边界重叠也不会产生副作用。

**结论：** 重复 cancel/await 代码异味已消除，语义不变。Pass。

---

### 3. Controller Pre-Review Blocker — 等待 run id 阶段 submit 先完成/失败 → **Pass (Still Closed)**

**直接证据（代码）：**

`_wait_for_run_id_or_local_exit`（`interactive.py:584-612`）用 `asyncio.wait` 同时等待三个 task：

```python
done, _pending = await asyncio.wait(
    (submit_task, run_id_task, second_sigint_task),
    return_when=asyncio.FIRST_COMPLETED,
)
if submit_task in done:
    return _SubmitCompletedWhileWaitingForRunId(terminal=await submit_task)
```

- **submit 先成功：** `await submit_task` 返回 `EntrypointRunTerminalResult`，包装为 `_SubmitCompletedWhileWaitingForRunId` 返回。调用方 `_cancel_interactive_turn_after_first_sigint`（L556-557）直接 `return wait_outcome.terminal`，不映射为 130。
- **submit 先失败：** `await submit_task` 抛出异常（如 `RuntimeError`），向上传播，不被吞掉或映射为 130。
- **第二次 SIGINT 先到：** `submit_task.cancel()` → 返回 `_LocalExitRequested()`，调用方返回 `None` → REPL 返回 130。

**直接证据（测试）：**

| 测试 | 场景 | 验证点 |
|------|------|--------|
| `test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first` | submit 先成功 | 返回 `_SubmitCompletedWhileWaitingForRunId`，`terminal is` 原始 terminal |
| `test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first` | submit 先失败 | `pytest.raises(RuntimeError, match="host fatal")` 向上透传 |
| `test_wait_for_run_id_returns_none_when_second_sigint_wins` | 第二次 SIGINT 先到 | 返回 `_LocalExitRequested`，`submit_task.cancelled()` |

**结论：** submit 先完成返回 terminal，submit 先失败透传异常，不误映射成 130。Pass。

---

### 4. Low-Fix 是否引入新问题 → **Pass（无新问题）**

**架构边界：**

```
grep -rn 'from dayu.engine\|import dayu.engine\|dayu.fins.storage' \
  dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py
```
→ 无命中。CLI 不直接触达 Engine 或 Fins storage。

**类型约束：**

```
grep -rn 'hasattr\|getattr\|: Any\b\|: object\b' \
  dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py
```
→ 无命中。无 `Any`/`object`/`hasattr`/`getattr` 逃逸。

**兼容性代码：**

```
grep -rn 'compat\|legacy\|old_\|_old' \
  dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py
```
→ 无命中。无兼容 wrapper 或 legacy 引用。

**pyright：** `0 errors, 0 warnings`。无新增或扩散类型错误。

**测试：** 64 passed（S4 专属），82 passed（回归），覆盖率 interactive.py 88%、host_context.py 99%、output.py 83%、arg_parsing.py 100%、main.py 94%。

**`_cancel_and_await_task` helper 设计评估：**

- 模块级私有函数，无嵌套。
- 内含 `task.done()` 守卫，对已完成 task 是 no-op。
- `suppress(asyncio.CancelledError)` 只吞取消异常，不吞其它异常（符合 docstring "task 已经以非取消异常结束时向上透传"）。
- 签名类型完整：`task: asyncio.Task[_TaskResult]` → `None`。
- 中文 docstring 含参数、返回值、异常说明。

**结论：** low-fix 未引入新架构/类型/测试问题。Pass。

---

## Verified Commands

| # | Command | Result |
|---|---------|--------|
| 1 | `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q` | 64 passed，interactive.py 88% |
| 2 | `source .venv/bin/activate && pyright` | 0 errors, 0 warnings |
| 3 | `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q` | 82 passed（回归） |
| 4 | `grep -rn 'from dayu.engine\|import dayu.engine\|dayu.fins.storage' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | 无命中 |
| 5 | `grep -rn 'hasattr\|getattr\|: Any\b\|: object\b' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | 无命中 |
| 6 | `grep -rn 'compat\|legacy\|old_\|_old' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | 无命中 |
| 7 | `git diff --check HEAD` | clean |

## Verdict

**Pass — 4 项复核点全部关闭，low-fix 未引入新问题。**

DS finding 1（输入态 Ctrl-C 测试覆盖）已通过 `_KeyboardInterruptInputReader` 测试固定为 exit 130 + 无 submit/cancel。DS finding 2（重复 cancel/await 代码异味）已通过 `_cancel_and_await_task` helper 消除，每个 task 只有一个明确 cancel 点。controller pre-review blocker（等待 run id 阶段 submit 先完成/失败不误映射为 130）的 typed outcome 设计与三项专用测试仍然完整。low-fix 的 `_cancel_and_await_task` helper 设计合理、类型安全、docstring 完整，未引入架构/类型/测试回归。
