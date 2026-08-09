# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `25400fba` (entry HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-mimo.md`
- Included scope:
  - `dayu/cli/session_execution.py` (unstaged)
  - `tests/cli/test_interactive_command.py` (unstaged)
  - `tests/host/test_session_attachment_registry.py` (unstaged)
- Excluded scope: Host production, composer, Service, Engine, README, design, oracle/scenario, frozen plan
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`close()` 失败后 `_closed` 未设置，幂等性违约

- **入口/函数**: `_InteractiveSessionAttachmentController.close()` (session_execution.py:442-457)
- **文件(行号)**: `dayu/cli/session_execution.py:453-457`
- **输入场景**: `close_current(current)` 抛出异常（attachment `aclose()` 失败）
- **实际分支**: `await asyncio.shield(self.close_current(current))` 抛出异常 → `self._closed = True` 永远不执行
- **预期行为**: docstring 声明"幂等关闭 controller 当前仍存活的 attachment"——无论底层 close 成功或失败，controller 应进入 terminal closed 状态，后续调用不再尝试 close
- **实际行为**: `_closed` 保持 `False`；若 caller 再次调用 `close()`，会再次尝试关闭同一个（可能已半关闭的）attachment
- **直接证据**: `dayu/cli/session_execution.py:453-457`——`self._closed = True` 在 `close_current` 之后，无 `try/finally` 保护
- **影响**: 违反 docstring 幂等承诺；当前 outer lifecycle 只调用 `close()` 一次（line 841），实际 double-close 不触发，但后续维护者若假设幂等安全再次调用会 double-close
- **建议改法和验证点**: 将 `self._closed = True` 放入 `finally` 块，确保无论 close 成功或失败都进入 terminal 状态；同时考虑 `self.current = None` 也应在 finally 中设置，避免 stale reference。验证：构造 `close_current` 抛出异常的测试，断言 `_closed` 为 `True` 且第二次 `close()` 为 no-op
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-`attachment_for_mutation()` refresh close 失败后 stale state 导致 double-close

- **入口/函数**: `_InteractiveSessionAttachmentController.attachment_for_mutation()` (session_execution.py:416-440)
- **文件(行号)**: `dayu/cli/session_execution.py:432-440`
- **输入场景**: `refresh_required=True` 且 `close_current(previous)` 抛出异常
- **实际分支**: `await asyncio.shield(self.close_current(previous))` 抛出异常 → `self.current` 仍为 `previous`，`self.refresh_required` 仍为 `True`
- **预期行为: close 失败后 controller 应进入可恢复状态或明确传播错误，不留 stale attachment reference
- **实际行为**: `self.current` 仍指向可能已半关闭的 `previous`；下次调用 `attachment_for_mutation()` 会再次尝试关闭同一个 attachment
- **直接证据**: `dayu/cli/session_execution.py:432-436`——`self.current = None` 在 `close_current` 成功后才执行；`self.refresh_required = False` 在 `open_fresh` 成功后才执行
- **影响**: 若 `aclose()` 非幂等，会导致重复关闭错误；当前 outer lifecycle 在 submit failure 后终止 invocation 并调用 `close()`，实际 double-close 路径被阻断，但 controller 内部状态不一致
- **建议改法和验证点**: 在 `close_current` 失败时，将 `self.current` 设为 `None`（attachment 已不可用），保持 `refresh_required=True` 使下次调用走 fresh open 路径。验证：构造 close 抛异常的测试，断言 `current` 为 `None`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-`_InteractiveSessionAttachmentController` 缺少 close/refresh failure 的测试覆盖

- **入口/函数**: `_InteractiveSessionAttachmentController.close()` 和 `attachment_for_mutation()`
- **文件(行号)**: `tests/cli/test_interactive_command.py` (新增测试区域)
- **输入场景**: `close_current` callback 抛出异常
- **实际分支**: 无测试覆盖此路径
- **预期行为**: 测试应证明 close 失败后 controller 状态正确（`_closed` 设置、`current` 清除、后续调用行为）
- **实际行为**: 现有测试只覆盖 happy path 和 composer error path，未覆盖 close/open failure
- **直接证据**: 新增 5 个测试均使用 `_test_attachment_controller` 构造正常工作的 controller，无 close failure 场景
- **影响**: Findings #1 和 #2 的修复缺少 regression 保护
- **建议改法和验证点**: 新增测试：(1) close 失败后 `_closed=True` 且第二次 close 为 no-op；(2) refresh close 失败后 `current=None` 且下次 mutation 走 fresh open。验证：使用抛异常的 `close_current` callback
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- **MEDIUM / covered by later S8**: 真实两个独立 CLI 进程的 owner 退出与 B 下一次 Enter 的 OS 调度窗口、PTY screen 文本和完整 evidence bundle，留给已批准 S8 真实并发 CLI evidence 收敛。
- **LOW**: `aclose()` 协议未显式声明幂等性。当前 Host implementation 应为幂等（attachment close 释放锁），但 protocol 层面未承诺。Findings #1/#2 的 double-close 风险依赖于此隐式假设。
- **LOW**: queued followup 的 READ_ONLY rejection 路径未有独立测试覆盖。代码路径与 current turn READ_ONLY 共享同一 `HostApiError` except 分支（line 1881-1897），逻辑正确但缺少显式 regression 断言。

## Verdict

实现严格遵守 accepted plan §6 的 typed contract、状态机不变量和 owner boundary：

- `_InteractiveSessionAttachmentController` 不写 `access_mode`，不原地 promotion，不后台 attach/poll；fresh attach 只由下一次 mutation 触发。
- `_InteractivePendingMutation` 冻结 identity；同 draft/revision 复用 `client_request_id`；编辑后产生新 turn identity。
- `_is_read_only_mutation_rejection` 使用 `is` 枚举 identity 检查，三重 typed detail 精确匹配；其它 Host 错误原样传播。
- composer ack/history 严格在 Host accepted callback 后；READ_ONLY 路径不 ack、不清 draft/cursor/history。
- 真实 Host 双 attachment 测试证明 RO rejection 零 Run/EventLog、mode 不变、close-before-open 顺序、fresh RW 后恰好一个 Run。
- 外层 exception/EOF/terminal 路径的 finally 块正确清理 acceptance tasks、submit tasks 和 composer/sigint tasks。
- attachment controller close 通过 `asyncio.shield` 保护，cancel 不中断底层 close。

三个 findings 均为 controller 内部 close failure 路径的幂等性/状态一致性问题，当前 outer lifecycle 调用模式下不触发实际 double-close，但违反 docstring 承诺且缺少测试保护。建议在本 slice 修复 Finding #1（`_closed` finally 保护），其余可作为 follow-up。

所有 89 个 focused tests 通过，pyright 0 errors。未修改 production/tests/plan/oracle/scenario，未 stage/commit/push。
