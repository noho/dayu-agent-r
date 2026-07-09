# Code Review

## Scope

- Mode: current changes (narrow re-review)
- Branch: phase/host-issues-control
- Base: 78a26006 (gateflow: record accepted manual fins fix)
- Output file: `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-mimo.md`
- Included scope: `dayu/cli/commands/prompt.py` (prompt lifecycle fix delta), `tests/cli/test_prompt_command.py` (new test), `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md` (Prompt Thinking Lifecycle Follow-up section)
- Excluded scope: interactive path, engine_ingest, host read API, service entrypoint_runtime — 均已在前轮裁决通过
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Evidence

### 1. `_cancel_prompt_turn_after_local_request` 接收 optional thinking_renderer 并在入口关闭

`prompt.py:498` 新增参数 `thinking_renderer: CliThinkingRenderer | None = None`。`prompt.py:516-517` 在 helper 入口立即 close：

```python
if thinking_renderer is not None:
    thinking_renderer.close()
```

位于 `submit_task.cancel()` 之前（line 518），保证 cancel 期间不再消费 thinking callback。与 interactive `DS F03` 修复对称。

### 2. Ctrl+C 与 Esc 两个 cancel 分支均传入 thinking_renderer

- Ctrl+C 路径 (`prompt.py:468-477`)：`thinking_renderer=thinking`，传入 `_cancel_prompt_turn_after_local_request`。✓
- Esc 路径 (`prompt.py:457-466`)：`thinking_renderer=thinking`，传入同一 helper。✓

两处均使用 `_submit_prompt_turn_handling_sigint` 内局部变量 `thinking`（line 409），来源为调用方传入的 `thinking_renderer` 参数。无遗漏分支。

### 3. 外层 finally 仍幂等关闭

`prompt.py:481-482`：

```python
if thinking is not None:
    thinking.close()
```

`CliThinkingRenderer.close()` (`thinking.py:83-90`) 仅设置 `self._closed = True`，重复调用安全。正常 submit path 不经过 cancel helper，thinking renderer 保持开启直到 finally；cancel path 由 helper 先关闭、finally 再幂等关闭。两条路径均正确。

### 4. 正常 submit path 无回归

`_submit_prompt_turn_handling_sigint` 正常完成时（`submit_task in done`，line 448-449）直接返回，不经过 cancel helper。thinking renderer 在整个 submit 期间保持开启，`on_thinking` callback 正常工作，直到 finally 关闭。✓

### 5. 第二次 SIGINT 无回归

第二次 SIGINT 进入 `_cancel_prompt_run_waiting_for_terminal_or_second_sigint`（line 535），该函数不接收 thinking_renderer——因为第一次 cancel helper 已关闭。这是正确的：thinking renderer 生命周期在 first cancel helper 入口终止。✓

### 6. 测试覆盖有效

`test_prompt_cancel_helper_closes_thinking_renderer`（line 1178-1210）：

- 构造 thinking renderer 接入 `io.StringIO` stderr
- 构造永不完成的 submit task
- 调用 `_cancel_prompt_turn_after_local_request`（`accepted_run.run_id=None`，覆盖 Run accepted 前取消路径）
- 断言 `result is None`、`cancel_requests == []`
- 调用后执行 `thinking_renderer.record(...)` 并断言 `stderr.getvalue() == ""`

该测试直接验证：(a) helper 入口 close renderer，(b) close 后 record 不再输出。✓

### 7. pyright 风险

新增参数使用 `CliThinkingRenderer | None = None`，类型签名正确。`close()` 方法无返回值。测试中 `io.StringIO` 满足 `TextIO` 协议。无新增类型风险。

## Open Questions

无。

## Residual Risk

- `thinking_renderer.close()` 抛出异常时，cancel helper 会在 `submit_task.cancel()` 前退出。当前 `close()` 实现仅赋值 bool，此风险极低，但若未来 renderer 持有需要 flush 的资源，应确保 close 不抛。
- 现有 `_submit_prompt_turn_handling_sigint` 测试（如 `test_prompt_sigint_after_run_id_cancels_host_run`）未显式验证 thinking renderer 在 cancel 后的关闭行为，但这些测试未传入 thinking renderer，不覆盖本变更路径。新测试已直接覆盖。
