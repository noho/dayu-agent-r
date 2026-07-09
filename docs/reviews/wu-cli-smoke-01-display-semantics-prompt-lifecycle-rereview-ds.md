# WU-CLI-SMOKE-01 Prompt Thinking Lifecycle Re-review

## Scope

- Mode: adversarial narrow re-review (current changes)
- Work unit: WU-CLI-SMOKE-01 display semantics
- Role: AgentDS
- Base: `phase/host-issues-control` (current branch)
- Output file: `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-ds.md`
- Included scope:
  - `dayu/cli/commands/prompt.py` — `_cancel_prompt_turn_after_local_request` thinking renderer close fix
  - `tests/cli/test_prompt_command.py` — `test_prompt_cancel_helper_closes_thinking_renderer`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md` — deferred risk records
  - Cross-reference: `dayu/cli/commands/interactive.py` `_cancel_interactive_turn_after_first_sigint` for pattern comparison
  - Cross-reference: `dayu/cli/thinking.py` `CliThinkingRenderer.close()` for idempotency guarantee
- Excluded scope: Host ingest, Service entrypoint, interactive command, thinking renderer core implementation (not changed in this fix gate)
- Parallel review coverage: 无

## Adversarial Verification Points

本 re-review 只回答四个问题：

1. close 时机不会影响正常 submit thinking 输出
2. first cancel 与 second SIGINT/Esc 等路径没有行为回归或 task leak
3. 测试是否足以覆盖该 lifecycle 修复
4. artifact 的 deferred risk 记录是否仍准确

## Evidence Trail

### 正常 submit 路径

入口 `_submit_prompt_turn_handling_sigint` (`prompt.py:378-486`)：

```
L409: thinking = thinking_renderer
L414-438: submit_task = asyncio.create_task(submit_entrypoint_turn_and_wait(..., on_thinking=thinking.record))
L443-448: asyncio.wait(submit_task, sigint_task, key_task, FIRST_COMPLETED)
L448-449: if submit_task in done → return await submit_task  # 正常完成
L478-486: finally: thinking.close()  # 幂等关闭
```

正常 submit 路径 `_cancel_prompt_turn_after_local_request` 不会被调用。`thinking.close()` 仅在 finally 中执行一次，不影响 submit 期间的 thinking 输出。**确认安全。**

### Ctrl+C first SIGINT 路径

```
L467-477: sigint_task completes → _cancel_prompt_turn_after_local_request(thinking_renderer=thinking)
  L516-517: if thinking_renderer is not None: thinking_renderer.close()  ← 立即关闭
  L518: submit_task.cancel()
  L519-520: await submit_task (CancelledError suppressed)
L478-486: finally: thinking.close()  ← 幂等关闭（`self._closed = True` 再次赋值，无副作用）
```

close() 在 submit_task.cancel() 之前，确保 cancel 决议已下后不再有新 thinking 输出落到 stderr。外层 finally 的幂等关闭不产生额外效果。**确认安全。**

L516-517 与 interactive `_cancel_interactive_turn_after_first_sigint` L722-723 模式完全一致。

### Esc cancel 路径

```
L450-466: key_task completes with CANCEL_RUN → _cancel_prompt_turn_after_local_request(thinking_renderer=thinking)
```

入口传参与 Ctrl+C 路径相同（`thinking_renderer=thinking`），执行链路一致。`observed_sigint_count` 传入 cancel 前计数（Esc 不会被误计为 Ctrl+C 次数），这是已有行为，本 fix 未改变。**确认安全。**

### second SIGINT 路径

```
_cancel_prompt_run_waiting_for_terminal_or_second_sigint (L535-590)
```

该函数 **不接受** `thinking_renderer` 参数。此时 thinking 已在以下两处被关闭：
1. `_cancel_prompt_turn_after_local_request` 入口（L516-517）
2. 外层 finally（L481-482）

**确认安全。** 不接收 thinking_renderer 是正确的设计选择——二次 SIGINT 只关心 cancel_task vs second_sigint_task 的竞争。

### Task leak 检查

外层 finally (L478-486)：
```python
finally:
    if renderer is not None: renderer.close()
    if thinking is not None: thinking.close()
    monitor.close()
    sigint_monitor.close()
    await cancel_and_await_task(sigint_task)    # ← 清理
    await cancel_and_await_task(key_task)        # ← 清理
```

- `sigint_task`：finally 中 cancel + await ✓
- `key_task`：finally 中 cancel + await ✓
- `submit_task`：正常路径已完成；cancel 路径在 `_cancel_prompt_turn_after_local_request` 中 cancel + await（L518-520）✓

一个**已有边界**（非本 fix 引入）：如果 `_cancel_prompt_turn_after_local_request` 在 `await submit_task`（L520）处因非 CancelledError 异常抛出，submit_task 不会被外层 finally 清理。但此时 submit_task 已经完成（以异常方式），不是 leak。此模式在 prompt 和 interactive 中均有，是已知设计。

**确认无新增 task leak。**

### 测试覆盖

新增测试 `test_prompt_cancel_helper_closes_thinking_renderer` (`test_prompt_command.py:1177-1211`)：

- 直接调用 `_cancel_prompt_turn_after_local_request(thinking_renderer=...)`
- 验证 `result is None`（run_id 未记录 → 不发 Host cancel）
- 验证后续 `thinking_renderer.record(...)` 不产生 stderr 输出
- 与 interactive 对应测试 `test_cancel_after_first_sigint_returns_completed_submit_terminal` 模式一致

**覆盖盲区**：无集成测试覆盖完整路径 `_submit_prompt_turn_handling_sigint(thinking_renderer=...)` → SIGINT → cancel helper → close。现有的 `test_prompt_sigint_after_run_id_cancels_host_run`、`test_prompt_esc_requests_cancel_after_run_id` 等测试均不传 `thinking_renderer`。

**评估**：该盲区严重性 LOW。原因：
1. 传参代码极简单——两处 cancel 分支各传 `thinking_renderer=thinking`（L465, L476），无分支逻辑
2. `_cancel_prompt_turn_after_local_request` 的入口行为已被单元测试充分覆盖
3. 外层 finally 的幂等关闭逻辑也被单元测试间接验证（`close()` 是纯 boolean 赋值，不会抛异常）
4. interactive 测试采用相同策略（直接测 helper），已通过上一轮 re-review

### Deferred risk 准确性

`wu-cli-smoke-01-display-semantics-codex.md` L150-154 记录的 residual risks：

| Risk | Status | 准确性 |
| --- | --- | --- |
| DS F02: thinking text 存为 PREVIEW row | deferred | ✅ 未变，本 fix 不涉及 EventLog 持久化 |
| MiMo F02: 160 字符单行截断 | deferred | ✅ 未变，本 fix 不涉及 renderer 展示策略 |
| No unclassified residual risk | — | ✅ 本 fix gate 的 residual risk 仅限于测试覆盖盲区（见上文），已在 review 中记录 |

**确认 deferred risk 记录准确。**

## Findings

### 001-未修复-LOW-prompt cancel 集成测试未传 thinking_renderer 验证完整链路

- **入口/函数**: `_submit_prompt_turn_handling_sigint`
- **文件(行号)**: `tests/cli/test_prompt_command.py:1122-1175`（现有 SIGINT 集成测试）
- **输入场景**: 用户传 `--thinking` 后 Ctrl+C 中断 prompt
- **实际分支**: 现有 SIGINT/Esc 集成测试均不传 `thinking_renderer` 参数（使用默认 `None`）
- **预期行为**: 应有至少一个集成测试传 `thinking_renderer` 通过完整 `_submit_prompt_turn_handling_sigint` → SIGINT → cancel helper → close 链路
- **实际行为**: 唯一覆盖 thinking renderer close 的测试直接调用 `_cancel_prompt_turn_after_local_request`，跳过了 `_submit_prompt_turn_handling_sigint` 中的传参和分支选择
- **直接证据**: `test_prompt_sigint_after_run_id_cancels_host_run` (L1122) 调用 `_submit_prompt_turn_handling_sigint` 不传 `thinking_renderer`；`test_prompt_esc_requests_cancel_after_run_id` (L1256) 同样不传；`test_prompt_second_sigint_exits_after_cancel_request` (L1304) 同样不传
- **影响**: 无法通过测试自动捕获 thinking_renderer 传参回归（如未来重构误删 cancel 分支中的 `thinking_renderer=thinking` 参数）
- **建议改法和验证点**: 为现有 `test_prompt_sigint_after_run_id_cancels_host_run` 增加 `thinking_renderer` 参数并在 cancel 后验证 `record()` 不输出，或新增独立集成测试；修复后运行 `pytest tests/cli/test_prompt_command.py -q`
- **修复风险（低）**: 只需在现有测试中增加一个 `CliThinkingRenderer` 参数和一行 assertion
- **严重程度（低）**: 当前代码简单可读，传参逻辑不易出错；单元测试已覆盖 helper 入口行为；与 interactive 采用相同测试策略

## Open Questions

无。

## Residual Risk

- 测试覆盖盲区：无集成测试覆盖 `_submit_prompt_turn_handling_sigint(thinking_renderer=...)` → cancel → close 完整链路。与 interactive 测试策略一致，风险 LOW。
- DS F02 (PREVIEW row persistence) 与 MiMo F02 (160 char truncation) 继续 deferred，不在本 fix gate scope。
- 本 fix gate 无新增 unclassified residual risk。

## Verdict

**pass**

本 fix 正确且安全：
- `_cancel_prompt_turn_after_local_request` 入口立即关闭 thinking renderer，时机正确，不影响正常 submit 输出
- Ctrl+C / Esc / second SIGINT 三条 cancel 路径均无行为回归或 task leak
- `close()` 的幂等性（纯 boolean 赋值）保证外层 finally 重复关闭安全
- 实现与 interactive `_cancel_interactive_turn_after_first_sigint` 模式完全一致
- 全部 CLI 测试通过（225 passed），pyright 零错误

仅有一个 LOW 测试覆盖盲区（001-未修复-LOW），与 interactive 测试策略一致，不阻塞 merge。
