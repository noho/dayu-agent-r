# WU CLI Conformance F01-F07 — S3B Code-review Fix

## 1. Gate result

- **Gate:** S3B implementation slice `code review → fix`
- **Status:** `READY-FOR-DUAL-S3B-CODE-REREVIEW`
- **Finding source:** Mimo code review finding 1
- **Controller decision:** `accepted / medium`
- **Scope:** composer-owned pending submit-delivery intent 与 exact READ_ONLY rejection consumer branch
- **Artifact:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-fix-codex.md`

本 fix 未 stage、commit、push 或修改 PR。四份 S8 README 与
`docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md` 是进入 fix 前的保留项，
本轮没有触碰或暂存；旧 S8 `FAILED-CONFORMANCE-OBSERVATION` 结论保持不变。

## 2. Accepted finding 与 root cause

READ_ONLY attachment rejection 已经终结本次 submit delivery，但原分支只要求 fresh
attachment 并把 REPL 切回 IDLE，没有通知 composer 结束 `_pending_submit_intent`。
因此 exact draft 仍正确保留时，stale delivery intent 也错误保留；idle SIGINT 可能被
`has_pending_submit_intent()` 误判为属于未来 submit，并污染下一次 Run。

语义 owner 是 composer：它唯一持有 pending submit、delivery intent、draft、cursor 与
input revision。READ_ONLY typed reason 仍由 Host contract 产生、CLI state machine 精确消费；
Host 不接管 composer state，CLI 也不直接修改 composer 私有字段。

## 3. Fix decision

### 3.1 Composer typed contract

`InteractiveComposer` 新增 `reject_submit_delivery()`：

- 仅在已有 pending `SUBMIT` 时合法，否则抛出 `RuntimeError`；
- 只把 pending delivery intent 置为结束；
- 原样保留 `_pending_submit`、draft、cursor、input revision 与 history；
- 下一次 `read_event()` 继续从 exact editable document 恢复；
- 不调用也不等价于 `accept_submit(...)`。

方法名和 contract 不包含 READ_ONLY/Host 术语；它表达的是 composer consumer 拒绝本次
delivery 的通用输入所有权事实，避免反向耦合。

### 3.2 READ_ONLY consumer branch

`_drive_interactive_tty_repl` 只在以下条件同时成立后调用该方法：

- submit 尚未发布 accepted Run id；
- `HostApiError` 具有 exact typed READ_ONLY mutation rejection detail。

调用发生在 attachment refresh 与提示输出之前，使 rejection 一经分类就立即终结旧
delivery intent。其它 submit failure、accepted Run、queued、terminal、SIGINT 与 cleanup
分支不变。

## 4. Changed files

- `dayu/cli/composer.py`
  - `InteractiveComposer.reject_submit_delivery()` typed protocol；
  - `PromptToolkitInteractiveComposer.reject_submit_delivery()` owner implementation。
- `dayu/cli/session_execution.py`
  - exact READ_ONLY rejection branch 调用 typed composer method。
- `tests/cli/test_interactive_composer.py`
  - owner contract：无 pending submit 时拒绝；rejection 后 intent cleared；draft、cursor、
    revision、history 与 pending editable draft 保留；无编辑重提恢复 exact document。
- `tests/cli/test_interactive_command.py`
  - scripted composer 实现同一 typed contract；
  - 既有真实 composer READ_ONLY retry 增加 intent/pending/revision 断言；
  - 新增 deterministic idle SIGINT/fresh attachment/resubmit integration；
  - manual SIGINT monitor 增加 waiter re-arm observation，区分“monitor 已返回 count”和
    “driver 已消费并重新建立 waiter”，不使用 sleep 猜调度。
- `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-fix-codex.md`
  - 本 durable fix artifact。

## 5. Test evidence

### Owner test

`test_reject_submit_delivery_clears_only_intent_and_restores_exact_draft` 证明：

- 无 pending submit 时 typed method fail closed；
- rejection 后 `has_pending_submit_intent() == False`；
- `_pending_submit` 仍为 true；
- draft 精确为 `abc`、cursor 精确为 `2`；
- input revision 与首次 SUBMIT event 完全一致；
- history 仍为空；
- 下一次不编辑、直接 Enter 时 draft/cursor/revision 原样恢复。

### Integration tests

`test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw` 继续使用真实
`PromptToolkitInteractiveComposer`，新增证明 rejection 后 intent 已结束、pending editable
draft 保留、fresh attach 重提前后 revision 不变。

`test_interactive_idle_sigint_after_read_only_does_not_cancel_retry_run` 证明：

- 第一次 RO mutation 被拒后 `reject_submit_delivery()` 恰好调用一次；
- driver 消费 idle SIGINT 并以新 observed count 重新建立 waiter；
- 后续同语义 submit 经 fresh RW attachment 重试；
- 两次 mutation attempt 的 `client_request_id` 完全相同；
- Host 只接受并创建一个 Run；
- Host cancel request 为零；
- 只有最终 accepted submit 进入 history；
- 两个 attachment 各关闭一次。

测试初稿只等待 monitor 返回 count，无法证明 driver 已消费该 count；同时释放第二个 submit
会形成既有 fixed-snapshot ordering，而不是 accepted stale-intent finding。测试现以 typed
waiter re-arm observation 建立明确 happens-before，不修改生产状态机或用 timing sleep 掩盖。

## 6. Validation

```text
pytest -q tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py
116 passed, 3 warnings

pytest -q tests/cli/test_run_keys.py tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py
206 passed, 3 warnings

pyright
0 errors, 0 warnings, 0 informations

ruff check <changed production/test files>
pass

git diff --check
pass
```

warnings 均为既有第三方 deprecation warning。

## 7. Finding status 与 non-goals

| Finding | Final fix status |
|---|---|
| Mimo F1：READ_ONLY rejection 残留 pending submit-delivery intent | **已修复** |
| DS：TCSANOW/kernel queue 极端 burst | 维持 Controller `rejected-with-reason`，未修改 |
| DS：terminal/cancel task 理论窗口 | 维持 Controller `rejected-with-reason`，未修改 |
| DS：SIGINT/display cleanup | 维持非 S3B blocker，未修改 |
| DS：空白 draft、reader join、pending count drain | 维持 Controller `rejected-with-reason`，未修改 |

没有调用 `accept_submit` 处理 READ_ONLY，没有改 Host、attachment owner、Run/Attempt/terminal
语义，没有增加 fallback/compatibility branch，也没有修改 frozen registry、F01/F02/F04-F07。

## 8. README 与 residual risks

README trigger 已核对。本 fix 恢复既有 READ_ONLY draft-preservation 与 stable retry contract，
不改变用户命令、参数、输出、配置、工作区位置或测试运行方式。用户明确要求四份 S8 README
保持不动，因此本轮没有 README diff。

Residual risks 均已分类：

- 完整 F03/F04 immutable real-evidence refresh：`covered by later approved S8 rerun`；owner tests
  与当前定向证据不替代 clean-commit external bundle。
- CLI runtime display async cleanup：`assigned to later work unit / CLI runtime display lifecycle`，
  维持 Controller 裁决，不在本 fix 扩张。
- Authorization 持久化：`assigned to independent security owner/work unit`，本 fix 不做下游脱敏补偿。

## 9. Next entry

Accepted Mimo finding 已修复，当前无 blocking open question。下一合法入口是两路独立
S3B code re-review；在 durable re-review artifacts 与 Controller 裁决完成前，不进入
accepted slice commit。按用户要求，本轮保持未 staged、未 commit、未 push。
