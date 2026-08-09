# Code Re-Review

## Scope

- Mode: current changes (re-review after fix)
- Branch: `codex/interactive-oracle`
- Base: `25400fba` (entry HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s4-code-rereview-mimo.md`
- Included scope:
  - `dayu/cli/session_execution.py` (unstaged, post-fix)
  - `tests/cli/test_interactive_command.py` (unstaged, post-fix)
  - `tests/host/test_session_attachment_registry.py` (unstaged, unchanged)
- Excluded scope: Host production, composer, Service, Engine, README, design, oracle/scenario
- Review input:
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-mimo.md` (original review)
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-controller-adjudication.md` (controller adjudication)
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-fix-codex.md` (fix artifact)
- Parallel review coverage: 无

## Finding 逐项最终状态

### 1-已修复-中-`close()` 失败后 `_closed` 未设置，幂等性违约

- **入口/函数**: `_InteractiveSessionAttachmentController.close()` (session_execution.py:445-462)
- **文件(行号)**: `dayu/cli/session_execution.py:456-462`
- **触发输入**: `close_current(current)` 抛出异常
- **实际分支**: 修复前 `self._closed = True` 在 await 之后；修复后移至 await 之前
- **预期行为**: 无论底层 close 成功或失败，controller 进入 terminal closed 状态，后续调用 no-op
- **实际行为**: `self._closed = True` 和 `self.current = None` 现在在 `await asyncio.shield(self.close_current(current))` 之前原子提交
- **直接证据**: `session_execution.py:458-461`——`self._closed = True`、`current = self.current`、`self.current = None` 均在 await 前执行
- **验证**: `test_attachment_controller_close_failure_is_terminal_and_attempted_once` 断言：
  - `exc_info.value is close_error`（异常 identity 保留）
  - `probe.close_attempts == [initial]`（恰好一次 close attempt）
  - `probe.close_states == [(None, False, True)]`（close callback 期间：current=None, refresh_required=False, _closed=True）
  - `controller.current is None`、`controller._closed is True`
  - 第二次 `close()` 不触发额外 close attempt
- **最终状态**: **已修复**

### 2-已修复-低-`attachment_for_mutation()` refresh close 失败后 stale state 导致 double-close

- **入口/函数**: `_InteractiveSessionAttachmentController.attachment_for_mutation()` (session_execution.py:416-443)
- **文件(行号)**: `dayu/cli/session_execution.py:436-437`
- **触发输入**: `refresh_required=True` 且 `close_current(previous)` 抛出异常
- **实际分支**: 修复前 `self.current = None` 在 await 之后；修复后移至 await 之前
- **预期行为**: close 失败后 `current=None`、`refresh_required=True`、不 open fresh；下一次 mutation 直接 fresh open
- **实际行为**: `self.current = None` 在 close await 前提交；close 失败异常传播，`open_fresh()` 不被调用
- **直接证据**: `session_execution.py:436-437`——`previous = self.current`、`self.current = None` 在 await 前；`session_execution.py:440`——`open_fresh()` 在 close 成功后才调用
- **验证**: `test_attachment_controller_refresh_close_failure_retries_with_fresh_open` 断言：
  - close 失败：`current=None`、`refresh_required=True`、`open_attempt_count=0`
  - `probe.close_states == [(None, True, False)]`（close callback 期间：current=None, refresh_required=True, _closed=False）
  - 下一次 mutation：`probe.close_attempts` 仍为 `[initial]`（不 double-close），`open_attempt_count=1`，返回 fresh attachment
- **最终状态**: **已修复**

### 3-已修复-低-`_InteractiveSessionAttachmentController` 缺少 close/refresh failure 的测试覆盖

- **入口/函数**: 新增 5 个 controller owner tests
- **文件(行号)**: `tests/cli/test_interactive_command.py:2707-2867`
- **触发输入**: close/open failure、close-before-open ordering、raw string enum rejection
- **实际分支**: 新增 `_AttachmentControllerLifecycleProbe` 提供可控 close/open callbacks，精确观测 await 前状态
- **预期行为**: 测试锁定 close attempt count、await 前状态、异常 identity、no double-close、no premature open、fresh retry
- **实际行为**: 5 个新 tests 全部通过，覆盖：
  1. `test_attachment_controller_close_failure_is_terminal_and_attempted_once`——close 失败后 terminal state、exactly-once attempt
  2. `test_attachment_controller_refresh_close_failure_retries_with_fresh_open`——refresh close 失败后 no open、next mutation fresh open
  3. `test_attachment_controller_refresh_never_opens_before_close_completes`——close 未完成时 open count 为零
  4. `test_attachment_controller_open_failure_keeps_refresh_for_fresh_retry`——open 失败后 None/refresh state、再次 fresh open
  5. `test_session_mutation_detail_rejects_raw_string_enum_values`——裸字符串被 typed detail owner 拒绝
- **直接证据**: `pytest -k 'attachment_controller or session_mutation_detail_rejects_raw_string'` → `5 passed`
- **最终状态**: **已修复**

## 额外验证项

| 验证项 | 最终状态 | 证据 |
|---|---|---|
| close 在 await 前 terminal/take-clear | 已修复 | `session_execution.py:458-461`；probe `close_states` 断言 |
| 失败后第二次 no-op | 已修复 | `test_...close_failure...` 第二次 `close()` 不增加 `close_attempts` |
| refresh close 失败不 open | 已修复 | `probe.open_attempt_count == 0` |
| refresh close 失败不 double-close | 已修复 | `probe.close_attempts == [initial]`（下一次 mutation 不再 close） |
| 下一次 mutation fresh open | 已修复 | `probe.open_attempt_count == 1`，返回 fresh |
| open 失败 state | 已修复 | `test_...open_failure...`：`current=None`、`refresh_required=True` |
| open 失败后显式 retry | 已修复 | 第二次 `attachment_for_mutation()` 返回 fresh，`open_attempt_count=2` |
| 异常 identity | 已修复 | `assert exc_info.value is close_error`（`is` identity check） |
| typed enum identity 严格 | 已修复 | `_is_read_only_mutation_rejection` 使用 `is`，无变更 |
| 裸字符串在 typed schema boundary 被拒 | 已修复 | `test_session_mutation_detail_rejects_raw_string_enum_values`：`TypeError` with `cast` raw string |

## Open Questions

- 无。

## Residual Risk

- **MEDIUM / deferred to S8**: 真实两个独立 CLI 进程的 owner 退出与 B 下一次 Enter 的 OS 调度窗口、PTY screen 文本和完整 evidence bundle，留给已批准 S8 真实并发 CLI evidence 收敛。
- **LOW**: `aclose()` 协议未显式声明幂等性。当前 fix 通过 controller 层面的 exactly-once attempt 保证不 double-close，但 protocol 层面未承诺。若 Host implementation 的 `aclose()` 非幂等且 controller 被绕过直接调用，仍有风险。本 fix 不改变此约束。

## Verdict

Controller adjudication 要求的三项 fix（close terminal/take-clear、refresh close no-open/double-close、failure test coverage）均已实现并通过独立 evidence 验证。typed enum identity 匹配保持不变，裸字符串在 schema boundary 被拒。所有 94 个 focused tests 通过，pyright 0 errors。未修改 production/tests/plan/oracle/scenario，未 stage/commit/push。

本 re-review 未发现新的实质性问题。Fix 可以 ship。
