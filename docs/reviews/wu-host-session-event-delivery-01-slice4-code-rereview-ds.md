# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 Code Re-Review — AgentDS

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-host-session-event-delivery-01`
- Base: `24efe9bd` (accepted Slice 3)
- Output file: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-ds.md`
- Review timestamp: `20260722-032323`
- Role: AgentDS，原独立 reviewer，进入 code re-review gate
- Controller adjudication: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-controller-adjudication.md`
- AgentCodex fix artifact: `docs/reviews/wu-host-session-event-delivery-01-slice4-fix-codex.md`
- 排除：AgentMiMo 首次 review (`wu-host-session-event-delivery-01-slice4-code-review-mimo.md`) 与本轮 re-review — 保持独立
- 本 review 只验证 accepted findings (S4-CR-F01/F02/F05) closure、确认 rejected findings (S4-CR-F03/F04) 边界未被实施，并做新 material correctness/stability/ownership finding scan
- Included scope: 所有相对于 `24efe9bd` 的 workspace changes（staged + unstaged + uncommitted），覆盖 S4 allowlist 所列 production/test/README 文件
- Excluded scope: `docs/host/issues-implementation-control.md`（Controller-owned）；S1–S3 冻结 Host production/test 文件（仅检查 S4 消费其 public contract 的一致性）
- Design documents consulted: `docs/host/design.md`, `docs/host/wu-host-session-event-delivery-01-plan.md` (S4), `AGENTS.md`/`CLAUDE.md`

## Accepted Finding Closure Verification

### S4-CR-F01 — CLOSED ✅

**事实**：`dayu/cli/session_execution.py` 独立覆盖率不足 80%。

**验证**：

- 使用独立 `COVERAGE_FILE` 重新执行：
  ```
  COVERAGE_FILE=workspace/tmp/.coverage-ds-rereview-s4-session-execution \
    pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
    --cov=dayu.cli.session_execution --cov-report=term-missing --cov-fail-under=80 -q
  ```
- 结果：`432 statements / 84 miss / 80.56%`，达到 `>=80%` ✅
- 新增测试 `test_prompt_terminal_surfaces_display_close_failure_from_caller_lifecycle`（`tests/cli/test_prompt_command.py:1937`）包含业务 identity、close-count、no-Host-cancel 断言，不是无业务断言的 coverage fixture

**证据文件**：
- `tests/cli/test_prompt_command.py:1937-1974` — display close failure 从 caller lifecycle 原 identity 传播
- `tests/cli/test_prompt_command.py:1866-1933` — finish-thinking race test（同时服务于 F02）

### S4-CR-F02 — CLOSED ✅

**事实**：`_cancel_prompt_turn_after_local_request` 缺少 `submit_task.done()` 提前返回，与 interactive 路径不一致。

**验证**：

- 生产修复位于 `dayu/cli/session_execution.py:963-966`：
  ```python
  if runtime_display is not None:
      await runtime_display.finish_thinking_display()
  if submit_task.done():          # ← 新增 done barrier
      return await submit_task    # ← 直接返回自然完成的 terminal
  submit_task.cancel()            # ← 只在未完成时 cancel
  ```
- interactive 路径 `dayu/cli/session_execution.py:1294-1310` 已有同源 done barrier（line 1309），两路径一致 ✅
- deterministic test `test_prompt_cancel_returns_submit_terminal_completed_during_finish`（`tests/cli/test_prompt_command.py:1866`）：
  - 使用 `_BlockingFinishThinkingDisplay` 冻结 finish-thinking 窗口
  - 冻结期间释放 submit_task 自然完成（line 1909）
  - 断言 `result is terminal`（同一 identity，line 1914）
  - 断言 `result.source is EntrypointTerminalSource.LIVE_EVENT`（line 1930）
  - 断言 `result.terminal_event_id == "terminal-run-1-finish-race"`（line 1931）
  - 断言 `fake_host.cancel_requests == []`（零 Host cancel，line 1932）
  - 断言 `thinking_display.close_count == 1`（精确一次 close，line 1933）

**关键验证点**：返回原 terminal identity/source，不多 cancel ✅

### S4-CR-F05 — CLOSED ✅

**事实**：event-processing exception 未被 consumer 捕获，会导致 consumer task 静默崩溃，coordinator 永久 hang。

**验证**：

- 生产修复位于 `dayu/service/entrypoint_runtime.py:1376-1396`：
  ```python
  try:
      result = await _observation_result_from_event(
          event, target_generation=target_generation, ...
      )
  except asyncio.CancelledError:
      raise                        # ← CancelledError 继续原样传播
  except Exception as error:
      runtime_state.try_commit(
          _IteratorFailed(          # ← first-commit 为既有 exact-five member
              target_generation=target_generation,
              error=error,
          ),
          target_run_id=target_run_id,
      )
      return                        # ← 立即退出 consumer
  ```
- 没有新增第六类 outcome、Future、queue、task callback 或 `task.exception()` 旁路 ✅
- deterministic test `test_submit_event_projection_failure_first_commits_iterator_failed`（`tests/service/test_entrypoint_runtime.py:2220`）：
  - 在 Host activity → Service DTO 投影 owner 注入原始 failure（line 2235-2238）
  - 使用 `asyncio.wait_for(timeout=1.0)` 证明不 hang（line 2254）
  - 断言 stable reason 精确为 `"session_event_iterator_failed_before_terminal"`（line 2266）
  - 断言 `__cause__ is projection_error`（原异常保持 direct cause，line 2267）
  - 断言 `fake_host.read_outbox_requests == []`（不走 durable recovery，line 2268）
  - 断言 `watcher.closed_count == 1`（iterator 精确一次关闭，line 2270）
  - 断言 `watcher.close_observed_active_anext is False`（aclose 时无 active anext，line 2271）

**关键验证点**：不 hang、不第六 outcome、不 side channel，iterator cleanup 精确 ✅

## Rejected Finding Boundary Verification

### S4-CR-F03 — 边界保持 ✅

Controller 明确 REJECTED：startup delivery recovery 成功 + watcher close 失败时不新增 operator log。

**验证**：

- `startup_reconnect_entrypoint_session`（`dayu/service/entrypoint_runtime.py:1105-1173`）中 `cleanup_error`（line 1125）仅在 recovery 失败时进入异常链（line 1140-1144）；recovery 成功时 `continue`（line 1145），cleanup_error 被丢弃
- 没有新增 operator logging 调用 ✅
- 没有新增 `_emit_cleanup_diagnostic` 在 startup 路径的调用 ✅
- rg scan `startup.*log|operator.*log|_emit_cleanup_diagnostic.*startup|cleanup_error.*log` 在 `entrypoint_runtime.py` 结果为空 ✅

### S4-CR-F04 — 边界保持 ✅

Controller 明确 REJECTED：`_wait_for_durable_terminal` 不增加 retry 次数、timeout、backoff 或其它 fail-fast 预算。

**验证**：

- `_wait_for_durable_terminal`（`dayu/service/entrypoint_runtime.py:1864-1897`）仍是简单 `while True` 循环，按 `poll_interval_seconds` 固定间隔 sleep ✅
- `_read_outbox_terminal`（line 2218-2248）LAGGED 时无条件返回 `None`，没有新增 `max_retries`/`max_attempts` 参数 ✅
- `outbox_lagged_max_attempts` 仍只出现在既有 `startup_reconnect` 的 session-scoped backfill 路径（`_read_session_outbox_terminal_backfill`），未扩散到 `_wait_for_durable_terminal` 或 `_read_outbox_terminal` ✅

## New Material Finding Scan

按 deepreview adversarial failure pass 对全部 S4 workspace changes 做 correctness/stability/ownership scan。

### 逐项验证结果

| 检查项 | 结果 | 证据 |
|---|---|---|
| exact-five 成员冻结 | ✅ 仍为 5 个 | `entrypoint_runtime.py:519-559` |
| 无第六类 outcome | ✅ | `_ServiceObservationResult` union 只有 5 个 member（line 558-560） |
| sole consumer | ✅ | capacity-one slot + `try_commit` 严格 first-commit（line 636-662） |
| CLI executor isolation | ✅ | `ThreadPoolExecutor(max_workers=1)` + private thread prefix（`runtime_display.py:150-153`） |
| 无 default executor leakage | ✅ | rg scan `run_in_executor(None` 在 `dayu/cli/` 结果为空 |
| relay deletion | ✅ | 无 `asyncio.Queue`、`_WatcherFailure`、`_drain_host_events` 残留 |
| 无 task.exception() 旁路 | ✅ | rg scan `task\.exception\(\)` 在 `entrypoint_runtime.py` 结果为空 |
| 旧 delivery 语义清除 | ✅ | `_TRANSIENT_WATCH_BUFFER_CAPACITY` 等 stale scan 结果为空 |
| 无 hasattr/getattr loose parsing | ✅ | rg scan 在 S4 production 文件结果为空 |
| 无 cast/Any/type-ignore | ✅ | rg scan 在 S4 production 文件结果为空 |
| dayu.runtime 无反向依赖 | ✅ | rg scan `from dayu\.(engine\|host\|service)` 结果为空 |
| dayu.engine 无 delivery contract | ✅ | rg scan `TerminalPostCommit\|session_event_delivery` 结果为空 |
| 状态机正确 | ✅ | 6 phase: ATTACHED_UNBOUND → CONSUMING → RESULT_READY → (ack) → ATTACHED_UNBOUND; stop → STOPPING → CLOSED |
| finish-thinking race done barrier | ✅ | prompt（line 965）和 interactive（line 1309）路径一致 |
| event-processing exception first-commit | ✅ | `_IteratorFailed`（line 1388-1396），CancelledError 原样传播（line 1386-1387） |
| CancelledError 不被 Exception 误吞 | ✅ | `_consume_host_events` line 1337-1338 和 line 1386-1387 均显式 `raise` |
| iterator cleanup 精确 | ✅ | `_close_watch_and_wait_runtime` 顺序：stop → cancel consumer → await → aclose → mark_closed（line 1834-1861） |
| caller-finally close flow | ✅ | `RuntimeDisplayController.aclose`：serial gate → renderer close → executor shutdown（line 288-327） |

### 结论：未发现新的 material finding

所有关键 correctness、stability、ownership 检查项均通过。未发现：
- data loss/corruption/duplication
- race condition/ordering violation
- semantic ownership drift
- state machine violation
- resource leak
- observability gap（在 frozen S4 scope 内）
- statically provable performance problem
- architecture boundary violation

## Verification Commands and Results

所有命令在 `source .venv/bin/activate` 后运行。

### Focused Tests

```
# S4-CR-F02 + S4-CR-F05 focused
pytest tests/cli/test_prompt_command.py::test_prompt_cancel_returns_submit_terminal_completed_during_finish \
  tests/service/test_entrypoint_runtime.py::test_submit_event_projection_failure_first_commits_iterator_failed -q
→ 2 passed
```

### S4 Focused Matrix

```
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_transient_delivery_interruption_path.py \
  tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_runtime_display.py \
  tests/cli/test_activity_renderer.py tests/cli/test_interactive_run_view.py tests/cli/test_thinking_renderer.py -q
→ 196 passed
```

### Full Affected Suites

```
pytest tests/host tests/runtime tests/service tests/cli -q
→ 3443 passed, 9 skipped, 6 deselected
```

### Stress Tests

```
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py tests/host/test_transient_delta_stress.py -q
→ 6 passed
```

### Single-File Coverage

```
# session_execution.py
COVERAGE_FILE=workspace/tmp/.coverage-ds-rereview-s4-session-execution \
  pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
  --cov=dayu.cli.session_execution --cov-report=term-missing --cov-fail-under=80 -q
→ 432 statements / 84 miss / 80.56%  ✅

# entrypoint_runtime.py
COVERAGE_FILE=workspace/tmp/.coverage-ds-rereview-s4-entrypoint \
  pytest tests/service/test_entrypoint_runtime.py \
  --cov=dayu.service.entrypoint_runtime --cov-report=term-missing --cov-fail-under=80 -q
→ 820 statements / 111 miss / 86.46%  ✅
```

### pyright

```
→ 0 errors, 0 warnings, 0 informations  ✅
```

### ruff (S4 changed Python allowlist)

```
→ All checks passed!  ✅
```

### git diff --check

```
→ (clean)  ✅
```

### Stale Scans

| Scan | Result |
|---|---|
| 旧 delivery 语义 (`_TRANSIENT_WATCH_BUFFER_CAPACITY` 等) | 空 ✅ |
| relay/queue/task.exception side channel | 空 ✅ |
| default executor leakage | 空 ✅ |
| startup operator log (S4-CR-F03 边界) | 空 ✅ |
| reverse dependency in dayu.runtime | 空 ✅ |
| delivery contract in dayu.engine | 空 ✅ |

## Open Questions

无。所有关键路径已沿真实代码走读完成，无阻碍判断的未决问题。

## Residual Risk

1. **不同 capacity 值的 E2E overflow 覆盖**：`tests/cli/test_transient_delivery_interruption_path.py` 仅覆盖 mailbox capacity=32 的单点 overflow 场景。不同 capacity 值（如 512/4 的边界）、多 subscription 并发 overflow 以及 activity（非 thinking）renderer 上的 overflow 未被 E2E 覆盖。这是既有 test scope 限制，不是 regression。

2. **`BaseException.__cause__` 跨版本兼容性**：Service 异常链使用 `raise primary from cleanup`，其中 primary 可能为 `asyncio.CancelledError`（`BaseException`）。Python 3.11+ 已验证支持，但未来版本的隐式行为变化未被测试覆盖。风险低，因为这是 Python 语言规范保证的行为。

3. **全仓 ruff baseline**：Codex 报告全仓 ruff 有 141 项既有跨域 lint baseline。本 review 确认 S4 changed Python allowlist 内零错误，且基线项不属于 S4 文件。不是 S4 regression。

## 结论

**PASS** — 无未关闭的 material finding。

| Finding | 最终状态 | 证据 |
|---|---|---|
| S4-CR-F01 | CLOSED | 隔离 coverage 80.56% ≥ 80% |
| S4-CR-F02 | CLOSED | finish-thinking barrier test；同一 live terminal identity/source；零 Host cancel |
| S4-CR-F03 | REJECTED（边界保持）| 无 startup operator log 新增 |
| S4-CR-F04 | REJECTED（边界保持）| 无 retry/timeout/backoff 语义新增 |
| S4-CR-F05 | CLOSED | projection failure fail-fast；stable disposition；exactly-once close |

**新 findings**：0 个 material finding。

核心验证项全部通过：
- finish-thinking race 返回原 terminal identity/source，不多 cancel ✅
- event-processing exception first-commit frozen `_IteratorFailed`，不 hang、不第六 outcome、不 side channel ✅
- iterator cleanup 精确 ✅
- exact-five 仍然精确五个 ✅
- sole consumer ✅
- CLI executor isolation ✅
- relay deletion ✅

Artifact path: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-ds.md`

**READY_FOR_CONTROLLER**
