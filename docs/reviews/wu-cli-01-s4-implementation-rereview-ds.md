# WU-CLI-01 CLI-01-S4 Implementation Re-Review — AgentDS

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S4, Interactive command
- Gate: re-review (deepreview after low-fix)
- Agent: AgentDS (主控)
- Date: 2026-06-14
- Review target: 未提交改动（`git diff HEAD` + untracked files），low-fix 后
- Prior art: `docs/reviews/wu-cli-01-s4-implementation-review-ds.md` (finding 1, 2), `docs/reviews/wu-cli-01-s4-implementation-review-mimo.md`, `docs/reviews/wu-cli-01-s4-implementation-codex.md`

## Re-Review Scope

仅复核以下四项，不做全量 review：

1. DS finding 1 — 输入态 Ctrl-C 行为是否已被测试固定为 exit 130 且不发 submit/cancel
2. DS finding 2 — 运行态 SIGINT task cleanup 是否已消除分支/finally 重复 cancel/await 代码异味
3. Controller pre-review blocker — 等待 run id 阶段 submit 先完成返回 terminal、submit 先失败透传异常、不误映射成 130
4. Low-fix 是否引入新的架构/类型/测试问题

---

## 1. DS Finding 1: 输入态 Ctrl-C 行为 — Pass（已关闭）

### 证据

**测试** `test_interactive_input_keyboard_interrupt_exits_without_run_requests`（`tests/cli/test_interactive_command.py:546–569`）：

- 使用 `_KeyboardInterruptInputReader`（line 375–386），其 `__call__` 始终抛出 `KeyboardInterrupt`
- `_read_user_input` 被 monkeypatch 为该 reader
- 断言：
  - `exit_code == EXIT_KEYBOARD_INTERRUPT`（130）
  - `fake_host.submit_requests == []`
  - `fake_host.cancel_requests == []`

**代码路径**：`_read_user_input`（`interactive.py:840–849`）不捕获 `KeyboardInterrupt` → `_run_interactive_repl`（line 409–411）仅捕获 `EOFError`，`KeyboardInterrupt` 向上传播 → `run_interactive_command`（line 252–253）捕获并返回 `EXIT_KEYBOARD_INTERRUPT`。全程未触达任何 submit/cancel 路径。

### 结论

行为固定为 exit 130，不发 submit/cancel。**Closed。**

---

## 2. DS Finding 2: 运行态 SIGINT task cleanup 代码异味 — Pass（已关闭）

### 原始异味

DS finding 2 指出 `_submit_interactive_turn_handling_sigint` 中 `_finish_completed_submit_task` 执行 `sigint_task.cancel()` 并 await，然后 finally block 再次执行 `sigint_task.cancel()` 和 suppress-await，构成双重取消。

### Low-fix 后的代码

**统一 cleanup helper**（`interactive.py:509–521`）：

```python
async def _cancel_and_await_task(task: asyncio.Task[_TaskResult]) -> None:
    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError):
        await task
```

- `task.done()` 守卫消除重复取消：已完成/已取消 task 不再被 cancel
- 所有 finally block 和分支清理统一使用此 helper

**`_submit_interactive_turn_handling_sigint` finally block**（line 504–506）：
```python
finally:
    sigint_monitor.close()
    await _cancel_and_await_task(sigint_task)
```
- 仅清理 `sigint_task`，`submit_task` 的结果由 `asyncio.wait` 完成后直接 `await submit_task` 或 `await _cancel_interactive_turn_after_first_sigint` 处理
- `_finish_completed_submit_task` 函数已不存在

**`_wait_for_run_id_or_local_exit` finally block**（line 610–612）：
```python
finally:
    await _cancel_and_await_task(run_id_task)
    await _cancel_and_await_task(second_sigint_task)
```
- 三个分支（submit/run_id/second_sigint 胜出）各自的清理集中在 finally 中
- 分支内仅做必要的 inline cancel（如 `second_sigint_task in done` 时 `submit_task.cancel()`），不再与 finally 重复

**`_cancel_interactive_turn_after_first_sigint`（line 561–565）**：
```python
if submit_task.done():
    return await submit_task
submit_task.cancel()
with suppress(asyncio.CancelledError):
    await submit_task
```
- `submit_task.done()` 检查在前，仅在未完成时才 cancel
- 这是该函数的局部逻辑，不与其他位置的 cleanup 构成重复

### 结论

双重取消代码异味已消除。统一 helper `_cancel_and_await_task` 内聚了 cancel+await 语义，所有调用点均通过 `task.done()` 守卫避免冗余操作。**Closed。**

---

## 3. Controller Pre-Review Blocker — Pass（仍关闭，未退变）

### 证据

三个关键测试仍然通过：

| 测试 | 场景 | 验证 |
|------|------|------|
| `test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first` | submit task 先完成，返回 SUCCEEDED terminal | 返回 `_SubmitCompletedWhileWaitingForRunId`，terminal 不映射为 130 |
| `test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first` | submit task 先失败（RuntimeError） | `await submit_task` 向上透传 RuntimeError，不吞异常 |
| `test_wait_for_run_id_returns_none_when_second_sigint_wins` | 第二次 SIGINT 先到 | 返回 `_LocalExitRequested`，上游映射为 None → 130 |

**代码路径**（`interactive.py:576–612`）：
- `_wait_for_run_id_or_local_exit` 用 `asyncio.wait` + `FIRST_COMPLETED` 同时等待 `submit_task`、`run_id_task`、`second_sigint_task`
- 返回 typed outcome：`_SubmitCompletedWhileWaitingForRunId` | `_RunIdAccepted` | `_LocalExitRequested`
- `_cancel_interactive_turn_after_first_sigint`（line 556–560）按 outcome 类型分发：
  - `_SubmitCompletedWhileWaitingForRunId` → 直接返回 terminal（不参与 130 映射）
  - `_LocalExitRequested` → 返回 None（由 REPL 映射为 130）
  - `_RunIdAccepted` → 继续 cancel 流程

**补充验证**：`test_cancel_after_first_sigint_returns_completed_submit_terminal` 覆盖了第一次 SIGINT 竞争中 submit 已完成的路径（`_cancel_interactive_turn_after_first_sigint` line 561–562），submit 终态原样返回。

### 结论

Controller pre-review blocker 仍然关闭，low-fix 未引入退变。**Pass。**

---

## 4. Low-Fix 是否引入新问题 — Pass

### 4.1 架构边界

- `_cancel_and_await_task` 是 `interactive.py` 模块级私有函数（`_` 前缀），不跨层暴露
- 无新增 `dayu.engine`、`dayu.fins.storage` 导入
- 无新增跨层依赖或反向依赖

**Pass。**

### 4.2 类型系统

- `_cancel_and_await_task` 使用 `TypeVar("_TaskResult")` 泛型，签名 `async def _cancel_and_await_task(task: asyncio.Task[_TaskResult]) -> None`，类型完整
- `_KeyboardInterruptInputReader.__call__` 签名为 `def __call__(self, _prompt: str) -> str`，docstring 明确标注 `:raises KeyboardInterrupt:`
- 无新增 `Any`、`object`、无类型参数
- pyright：0 errors, 0 warnings

**Pass。**

### 4.3 测试

- 新增 `test_interactive_input_keyboard_interrupt_exits_without_run_requests` — 覆盖输入态 Ctrl-C 路径
- 全量测试：130 passed（含 S4 专属 20 tests + Service path 3 tests + 回归）
- 覆盖率：`interactive.py` 88%（≥ 80%）
- 未覆盖行分析：`install()` 的 `NotImplementedError`/`RuntimeError` fallback（117–120）、`wait_run_id()` 的 RuntimeError 防御（202–204）、异常 handler（250–256）、REPL exit 路径（426–431）、`_cancel_interactive_turn_after_first_sigint` 中 `run_id is None` 的 `_LocalExitRequested`/`_RunIdAccepted` 分支（550–560）— 均为平台相关或时序相关的 hard-to-trigger 路径，与原始 DS review 的 coverage gap 一致，未引入新的未覆盖关键路径

**Pass。**

### 4.4 代码质量

- `_cancel_and_await_task` 职责单一（cancel + await 一个 task），不是 god function
- 无新增魔法字符串、兼容性代码、`hasattr`/`getattr` 逃逸
- 中文 docstring 完整，参数/返回值/异常说明齐全
- `git diff --check` clean

**Pass。**

---

## Verification Commands Executed

| # | Command | Result |
|---|---------|--------|
| 1 | `pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q` | **130 passed** |
| 2 | `pytest tests/cli/test_interactive_command.py::test_interactive_input_keyboard_interrupt_exits_without_run_requests -v` | **1 passed** |
| 3 | `pytest tests/cli/test_interactive_command.py::test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first tests/cli/test_interactive_command.py::test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first tests/cli/test_interactive_command.py::test_wait_for_run_id_returns_none_when_second_sigint_wins tests/cli/test_interactive_command.py::test_cancel_after_first_sigint_returns_completed_submit_terminal -v` | **4 passed** |
| 4 | `pytest tests/cli/test_interactive_command.py --cov=dayu.cli.commands.interactive --cov-report=term-missing -q` | **88% coverage** |
| 5 | `pyright` | **0 errors, 0 warnings** |
| 6 | `grep -rn 'hasattr\|getattr' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py tests/cli/test_interactive_command.py` | **No hits** |
| 7 | `grep -rn ': Any\b\|: object\b' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py tests/cli/test_interactive_command.py` | **No hits** |
| 8 | `grep -rn 'from dayu.engine\|import dayu.engine\|dayu.fins.storage' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | **No hits** |
| 9 | `grep -rn 'compat\|legacy\|old_\|_old' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | **No hits** |
| 10 | `git diff --check` | **clean** |

---

## Conclusion

四项复核全部 **Pass**：

- **DS finding 1** 已关闭：输入态 Ctrl-C 有明确测试固定为 exit 130 + 无 submit/cancel
- **DS finding 2** 已关闭：统一 `_cancel_and_await_task` helper + `task.done()` 守卫消除重复 cancel/await 代码异味
- **Controller pre-review blocker** 仍关闭：typed outcome 模式正确区分 submit terminal、异常透传、本地 130，未退变
- **Low-fix 未引入新问题**：架构边界清晰、类型完整、测试充分（130 passed / 88% coverage）、pyright 零报错

无 blocker，无 residual finding 需要跟踪。
