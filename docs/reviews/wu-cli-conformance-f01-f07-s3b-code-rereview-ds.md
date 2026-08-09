# S3B Code Re-Review — Accepted READ_ONLY pending-submit-intent Fix（第二路独立复审）

## Scope

- **Mode:** working-tree changes（未提交）
- **Branch:** `codex/interactive-oracle`
- **Base:** `eae09be97963382c49fbf71195820637a4baa948`
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-rereview-ds.md`
- **Reviewed finding source:** Controller adjudication accepted Mimo finding 1（`docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-controller-adjudication.md`）
- **Fix implementation:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-fix-codex.md`
- **First-round DS review:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-ds.md`
- **Included scope (production):**
  - `dayu/cli/composer.py` — `reject_submit_delivery()` typed contract + owner implementation
  - `dayu/cli/session_execution.py` — READ_ONLY branch integration + `pending_submit_sigint_count` drain
  - `dayu/cli/agent_entrypoint.py` — `CliSigintMonitor.install()` 幂等 guard（无新 diff）
  - `dayu/cli/commands/prompt.py` — invocation 起点 input owner 提前安装（无新 diff）
  - `dayu/cli/run_keys.py` — TCSANOW cbreak（无新 diff）
- **Included scope (test):**
  - `tests/cli/test_interactive_composer.py` — owner tests（`test_reject_submit_delivery_clears_only_intent_and_restores_exact_draft`、`test_ordinary_enter_records_submit_intent_until_repl_accepts`）
  - `tests/cli/test_interactive_command.py` — integration tests（`test_interactive_idle_sigint_after_read_only_does_not_cancel_retry_run`、`test_interactive_very_early_sigint_binds_pending_submit_to_accepted_run`、updated `test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw`）
  - `tests/cli/test_prompt_command.py` — prompt early input owner tests（无新 diff）
  - `tests/cli/test_run_keys.py` — TCSANOW prestart tests（无新 diff）
- **Excluded scope:**
  - 四份 S8 README 与 S8 artifact — controller 明确排除
  - 已被 controller 拒绝的 DS findings（TCSANOW 极端 burst、孤儿 cancel task、cleanup shield、空白 draft intent 等）— 无新证据，不重提
- **Parallel review coverage:** 无（单路独立复审）

## Findings

### 1-未修复-低-`reject_submit_delivery()` 的 `_pending_submit` guard 允许二次幂等调用但语义不完整

- **入口/函数:** `PromptToolkitInteractiveComposer.reject_submit_delivery()`
- **文件(行号):** `dayu/cli/composer.py:399-401`
- **输入场景:** `reject_submit_delivery()` 被调用时 guard 检查 `if not self._pending_submit`。第一次调用后 `_pending_submit_intent = False` 但 `_pending_submit` 仍为 `True`。如果在同一 pending submit 生命周期内再次调用（例如 READ_ONLY 分支因异常 retry 被意外二次进入），第二次调用会通过 guard 并再次执行 `self._pending_submit_intent = False`——这是一个安全的幂等 no-op，但 guard 的语义（"没有 pending submit 时拒绝"）与 intent（"只终结 delivery intent"）之间存在轻微错位：guard 不区分"从未有过 submit"和"submit delivery 已被 reject 一次"。
- **实际分支:** 行 399 `if not self._pending_submit:` → `_pending_submit` 为 `True`（未清除）→ 通过 guard → 行 401 `self._pending_submit_intent = False`（已是 `False`，再赋值为 `False`）。
- **预期行为:** 第一次调用 guard 通过并清 intent；重复调用也应安全吸收（不抛异常、不破坏状态）。
- **实际行为:** 重复调用确实安全——`_pending_submit_intent` 重复赋值为 `False` 是幂等的。但 guard 的异常消息 "no pending submit" 在重复调用时不会触发（因为 `_pending_submit` 仍为 `True`），这意味着无法通过异常检测到"delivery 已被 reject 过一次"这一事实。如果未来某调用方需要区分"首次 reject"和"重复 reject"，当前 guard 不支持。
- **直接证据:** 行 399 `if not self._pending_submit:` 只检查 `_pending_submit` 存在性，不检查 `_pending_submit_intent` 是否已被清过。行 401 无条件赋值 `False`。`accept_submit` 中 `_pending_submit_intent = False`（行 378）同样是幂等赋值，两处设计一致。
- **影响:** 无外部可见缺陷。当前唯一的 READ_ONLY branch 在调用 `reject_submit_delivery()` 后立即 `current = None` 并切换 phase 为 IDLE，不存在同一 submit 生命周期内重复调用的路径。Severity 定为"低"是因为 guard 语义不完整但不产生错误行为，且与同一类中 `accept_submit` 的 guard 设计一致。
- **建议改法和验证点:** 可在 docstring 中显式声明"重复调用安全且幂等"。不需要代码修改。
- **修复风险（低）:** 仅文档说明。
- **严重程度（低）:** 语义边界——无错误行为，无外部可见影响。

## Fix Verification：Accepted Finding 闭环确认

以下逐条验证 controller adjudication 接受的 Mimo finding 已在 composer owner 正确闭环。

### 验证 1：`reject_submit_delivery()` 只清 intent，exact 保留 draft/cursor/revision/pending draft/history

**直接证据：**
- `dayu/cli/composer.py:401` — 实现仅一行 `self._pending_submit_intent = False`
- `dayu/cli/composer.py:389-401` — docstring 明确声明"`_pending_submit`、草稿、光标、input revision 与 history 均保持原样"
- `tests/cli/test_interactive_composer.py:443-509` (`test_reject_submit_delivery_clears_only_intent_and_restores_exact_draft`) — 断言：
  - 无 pending submit 时 `reject_submit_delivery()` → `RuntimeError("no pending submit")`
  - `reject_submit_delivery()` 后 `has_pending_submit_intent() == False`
  - `_pending_submit` 仍为 `True`
  - `_draft == "abc"` 精确保留
  - `_cursor_position == 2` 精确保留
  - `_input_revision` 与首次 `SUBMIT` event 完全一致
  - `_history` 仍为空
  - 不编辑直接 Enter 重提 → draft 原样恢复为 `"abc"`、revision 不变

**结论：PASS。** `reject_submit_delivery()` 仅修改 `_pending_submit_intent`，所有其他 composer 状态字段均原样保留。

### 验证 2：READ_ONLY 分支唯一调用 `reject_submit_delivery()`

**直接证据：**
- `dayu/cli/session_execution.py:1913-1918` — 调用点位于 exact READ_ONLY rejection 分支内，guard 为：
  ```python
  if (
      completed.closeout.barrier.accepted_run_id is not None
      or not _is_read_only_mutation_rejection(error)
  ):
      raise
  composer.reject_submit_delivery()
  ```
- `dayu/cli/session_execution.py:1636-1651` (`_is_read_only_mutation_rejection`) — 精确匹配 `HostSessionMutationErrorDetail` 的 `kind=="session_mutation_access"`、`reason is READ_ONLY`、`actual_mode is READ_ONLY`
- 全文件搜索 `reject_submit_delivery` 仅命中行 1918 一处调用

**结论：PASS。** `reject_submit_delivery()` 仅在 typed READ_ONLY + accepted_run_id 为 None 的条件下调用，不泄漏到其他异常路径。

### 验证 3：idle SIGINT 不跨 turn（READ_ONLY rejection 后 intent 已清）

**直接证据：**
- `dayu/cli/session_execution.py:1874-1877` — idle SIGINT handler：
  ```python
  if current is None:
      if composer.has_pending_submit_intent():
          pending_submit_sigint_count += 1
          continue
  ```
- `dayu/cli/session_execution.py:1918` — READ_ONLY rejection 后立即调用 `composer.reject_submit_delivery()`
- `dayu/cli/session_execution.py:1927-1929` — 随后 `current = None`、`composer.set_phase(IDLE)`
- `tests/cli/test_interactive_command.py:3023-3111` (`test_interactive_idle_sigint_after_read_only_does_not_cancel_retry_run`) — 断言：
  - `rejected_delivery_count == 1`（恰好调用一次）
  - `not composer.has_pending_submit_intent()`（intent 已清）
  - 注入一次 SIGINT → `host.cancel_requests == []`（未创建 cancel）
  - `_wait_for_sigint_rearm(monitor, 1)` 确认 driver 已消费信号并重新建立 waiter（不使用 sleep 猜调度）

**结论：PASS。** READ_ONLY rejection → `reject_submit_delivery()` → intent cleared → 后续 idle SIGINT 走 idle exit 路径，不污染重提 turn。

### 验证 4：fresh attach + resubmit 使用 stable `client_request_id` 且只产生一个 Run

**直接证据：**
- `dayu/cli/session_execution.py:1753-1756` — `same_semantic_submission` 检查 draft 与 revision 均未变化
- `dayu/cli/session_execution.py:1764` — `pending_mutation` 不变 → `next_turn_index` 不递增
- `dayu/cli/session_execution.py:1604-1633` (`_new_interactive_pending_mutation`) — `client_request_id` 由 `turn_index` 派生
- `tests/cli/test_interactive_command.py:3100-3109` — 断言：
  - `len(request_ids) == 2`（两次 mutation attempt）
  - `request_ids[0] == request_ids[1]`（相同 `client_request_id`）
  - `len(host.submit_requests) == 1`（Host 只接受一个 Run）
  - `host._submit_index == 1`（只产生一个 Run）
  - `host.cancel_requests == []`（无 cancel）
  - `composer.accepted_history_flags == [True]`（只有最终 accepted submit 进入 history）

**结论：PASS。** 同语义重试复用 stable `client_request_id`，Host 只创建一个 Run，无冗余 cancel。

### 验证 5：修复是否引入新 correctness/ownership/type/test 问题

**correctness:**
- `reject_submit_delivery()` 后 `_pending_submit` 仍为 `True`，下一次 `read_event()` 进入 stale pending 路径（行 411-415），清除 `_pending_submit` 和 `_pending_submit_intent`，然后用 `_draft`/`_cursor_position` 重构 `Document` 传给 `prompt_async`。这是正确的恢复流程——用户看到 exact 原草稿和光标位置。
- `accept_submit` 在行 377-378 同步清 `_pending_submit_intent`，与 `reject_submit_delivery` 不会冲突——两者在不同路径调用，互斥（acceptance barrier 跨过后走 accept，READ_ONLY rejection 走 reject）。

**ownership:**
- `reject_submit_delivery()` 属于 `InteractiveComposer` Protocol（行 245-252），是 typed contract，不包含 READ_ONLY/Host 术语。正确 owner 边界：composer 拥有 pending delivery intent 状态，driver 只按业务条件调用 typed method。
- Host 仍独占 READ_ONLY typed reason（`HostSessionMutationRejectionReason.READ_ONLY`），CLI 精确消费该 typed reason 但不接管其语义。

**type:**
- `reject_submit_delivery()` 返回 `None`，无泛型参数，无类型擦除。
- `_ScriptedComposer` 实现同一 contract（`tests/cli/test_interactive_command.py:1113-1125`），类型签名一致。
- pyright: `0 errors, 0 warnings, 0 informations`

**test:**
- Owner test: `test_reject_submit_delivery_clears_only_intent_and_restores_exact_draft` — 使用真实 `PromptToolkitInteractiveComposer` + pipe input，验证完整生命周期。
- Integration test: `test_interactive_idle_sigint_after_read_only_does_not_cancel_retry_run` — 使用 `_ReadOnlyRetryHost` + `_BarrierScriptedComposer` + `_InvocationManualSigintMonitor`，端到端验证 READ_ONLY → reject → idle SIGINT → retry 全链路。
- Updated test: `test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw` — 在既有真实 composer 测试中增加 intent/pending/revision 断言。
- 所有测试 206 passed, 3 warnings（既有 deprecation）。

**结论：PASS。** 修复未引入新 correctness/ownership/type/test 问题。

## Open Questions

无。

## Residual Risk

1. **`reject_submit_delivery()` 后的 `read_event()` stale pending 路径清除 `_pending_submit` 的时序窗口。** 在 `reject_submit_delivery()` 返回后、下一次 `read_event()` 的 stale pending 路径（行 411-415）执行前，`_pending_submit` 仍为 `True`。如果在此期间某代码路径调用 `accept_submit(record_history=False)`，会通过 guard（检查 `_pending_submit`）并错误清空 draft/cursor。当前 driver 在 READ_ONLY 后立即创建新 `composer_task`，`accept_submit` 只会从 `current_acceptance_task` 路径（行 1851-1858）调用，而 READ_ONLY 分支已提前 cancel 了 `current_acceptance_task`（行 1919-1921）。此窗口在当前代码中不可达，但作为一个隐式时序依赖，值得在 composer 模块文档中记录。

2. **`test_interactive_idle_sigint_after_read_only_does_not_cancel_retry_run` 使用 `_BarrierScriptedComposer` 而非真实 `PromptToolkitInteractiveComposer`。** 这是首轮 review 已记录的"测试未覆盖真实 OS 信号竞态"的延续——`_BarrierScriptedComposer` 在受控 asyncio 调度点交付事件，不模拟真实 prompt_toolkit 内部的 application/event loop 交互。Mimo PTY 手动验证提供了两条 lane 的真实证据，但 READ_ONLY + idle SIGINT + retry 组合尚未有真实 PTY 证据。

3. **`_wait_for_sigint_rearm` 使用有界 polling。** 新测试 helper 轮询 `monitor.wait_requests`（最多 1000 次 `asyncio.sleep(0)`），在极端慢的事件循环下可能误报 timeout。但 1000 次调度应远超任何合理延迟。
