# S3B Real-evidence Regression Code Re-review — Mimo

## Scope

- **Mode:** S3B same-slice code re-review (working-tree changes vs eae09be97963382c49fbf71195820637a4baa948)
- **Branch:** `codex/interactive-oracle`
- **Base:** `eae09be97963382c49fbf71195820637a4baa948`
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-rereview-mimo.md`
- **Included scope:**
  - `dayu/cli/composer.py` (reject_submit_delivery fix)
  - `dayu/cli/session_execution.py` (READ_ONLY branch call site)
  - `tests/cli/test_interactive_composer.py` (owner test)
  - `tests/cli/test_interactive_command.py` (integration tests)
- **Excluded scope:** 四份 S8 README 与 S8 artifact 是既有保留基线，不在本 gate 范围。
- **Input artifacts:**
  - `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-fix-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-mimo.md` (首轮 review)
- **Parallel review coverage:** 无。

## Verification

- **pyright:** `0 errors, 0 warnings, 0 informations` ✅
- **pytest:** `206 passed, 3 warnings` (204 + 2 new fix tests) ✅
- **git diff --check:** pass ✅
- **staged diff:** empty ✅

## Findings

未发现实质性问题。

## Accepted Finding 闭环验证

### Finding #1: READ_ONLY rejection 后 `_pending_submit_intent` 残留

**Controller 裁决:** 接受，中

**Fix 验证结论:** ✅ 正确闭环

#### 1. reject_submit_delivery 只清 intent 且 exact 保留 draft/cursor/revision/pending draft/history

- **Protocol 定义:** `composer.py:245-252`，docstring 明确"结束被 REPL 拒绝的提交交付，同时保留 exact editable draft"。
- **实现:** `composer.py:389-401`：
  - `if not self._pending_submit: raise RuntimeError` → fail closed
  - `self._pending_submit_intent = False` → 唯一副作用
  - 不触碰 `_draft`、`_cursor_position`、`_input_revision`、`_pending_submit`、`_history`
- **Owner test:** `test_interactive_composer.py:469-508` 验证：
  - 无 pending submit 时 `reject_submit_delivery()` 抛出 `RuntimeError` ✅
  - rejection 后 `has_pending_submit_intent() == False` ✅
  - `_pending_submit` 仍为 `True` ✅
  - draft 精确为 `"abc"`、cursor 精确为 `2` ✅
  - input revision 与首次 SUBMIT event 一致 ✅
  - history 仍为空 ✅
  - 不编辑直接 Enter 时 draft/cursor/revision 原样恢复 ✅

#### 2. READ_ONLY 分支唯一调用

- **调用点:** `session_execution.py:1918`，位于 `if completed.closeout.barrier.accepted_run_id is not None or not _is_read_only_mutation_rejection(error): raise` 之后。
- **调用条件:** submit task 以 `HostApiError` 结束 + 未 accepted + 精确 READ_ONLY mutation rejection。
- **调用顺序:** `reject_submit_delivery()` → `cancel_and_await_task(current_acceptance_task)` → `cancel_and_await_task(cancel_task)` → `require_refresh()` → `set_phase(IDLE)`。正确：先终结 intent，再清理 task，再登记 refresh，最后切 phase。
- **其它路径不调用:** 非 READ_ONLY HostApiError 走 `raise`；accepted Run 走 `observe_terminal`；正常 terminal 走 `wait_closeout`。

#### 3. Idle SIGINT 不跨 turn

- **Integration test:** `test_interactive_command.py:3024-3099` 证明：
  - READ_ONLY rejection 后 `reject_submit_delivery()` 恰好调用 1 次 ✅
  - `has_pending_submit_intent() == False` ✅
  - 驱动 idle SIGINT 后 `monitor.notify()` → driver 消费并 re-arm waiter（`_wait_for_sigint_rearm`） ✅
  - `host.cancel_requests == []` — idle SIGINT 未绑定到后续 Run ✅

#### 4. Fresh attach/resubmit stable client_request_id 且唯一 Run

- **Integration test:** `test_interactive_command.py:3089-3099` 验证：
  - 两次 mutation attempt 的 `client_request_id` 完全相同 ✅
  - `len(host.submit_requests) == 1` — Host 只接受并创建一个 Run ✅
  - `host.cancel_requests == []` — 零 cancel ✅
  - `composer.accepted_history_flags == [True]` — 只有最终 accepted submit 进入 history ✅
  - 两个 attachment 各关闭一次 ✅

#### 5. read_event 也清除 intent（防御性）

- `composer.py:411-415`: `read_event` 在 `_pending_submit` 为 True 时也清除 `_pending_submit_intent = False`。这是防御性设计：即使 `reject_submit_delivery` 未被调用（例如其它 rejection 路径），下一次 `read_event` 也会重置 intent。

## 新增 correctness/ownership/type/test 问题检查

- **Type:** `reject_submit_delivery` 在 Protocol 和实现中签名一致 `() -> None`，pyright 0 errors ✅
- **Ownership:** 方法在 composer owner 内实现，不修改 Host/attachment/Run 状态，不泄漏 prompt_toolkit 类型 ✅
- **No compat shim:** 方法名和 contract 不包含 READ_ONLY/Host 术语，表达的是 composer consumer 拒绝 delivery 的通用事实 ✅
- **Scripted composer:** `test_interactive_command.py:1113-1123` 的 `_BarrierScriptedComposer` 实现同一 contract 并记录 `rejected_delivery_count` ✅
- **No regression:** 既有 204 测试全部通过，新增 2 测试覆盖 owner 和 integration ✅
- **No accept_submit misuse:** READ_ONLY path 不调用 `accept_submit`，不违反 F04 draft 保留 contract ✅

## Controller 已拒 findings（不重提）

以下 findings 在首轮 review 中由 Controller 裁决为 `rejected-with-reason`，本轮无新证据，不重提：

- DS: TCSANOW/kernel queue 极端 burst
- DS: terminal/cancel task 理论窗口
- DS: SIGINT/display cleanup（登记为独立 residual）
- DS: 空白 draft 不算 pending intent
- DS: reader join 超时后 terminal 访问
- DS: pending count drain 后新 SIGINT

## Open Questions

无。

## Residual Risk

- 完整 F03/F04 immutable real-evidence refresh 需在 clean-commit 后重跑。
- CLI runtime display async cleanup 为独立 residual，不属于 S3B。
- Authorization 持久化为独立安全 residual。

## Conclusion

Accepted Mimo Finding #1 已在 composer owner 层正确闭环。`reject_submit_delivery()` 只清除 pending-delivery intent，exact 保留 draft/cursor/revision/pending draft/history；READ_ONLY 分支是唯一调用点；idle SIGINT 不跨 turn 污染后续 Run；fresh attach/resubmit 保持 stable client_request_id 且 Host 只创建唯一 Run。修复未引入新 correctness/ownership/type/test 问题。206 tests passed，pyright 0 errors。
