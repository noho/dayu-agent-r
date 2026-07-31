# WU-CLI-PROMPT-01 S2 Implementation

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `implementation`
- Slice: `S2 — Prompt repeated-SIGINT graceful terminal wait`
- Owner: `controller`
- Timestamp: `2026-07-31 18:33:55 +0800`
- Prerequisite accepted commit: `2f045e51`

## Root cause 与语义 owner

直接根因位于 `dayu.cli.session_execution` 的 prompt cancellation lifecycle owner：accepted Run 发出 graceful cancel 后，`_cancel_prompt_run_waiting_for_terminal_or_second_sigint` 把 Host terminal waiter 与第二次 SIGINT 竞赛；第二次 SIGINT 先到会取消 `cancel_entrypoint_run_and_wait` 并返回 `None`，允许 CLI 在 Host Run/attempt 仍非终态时退出。

Host 仍是 Run 生命周期与 canonical terminal 的唯一 owner。CLI prompt 只负责把首次 Ctrl+C/Escape 转换成一次 typed graceful cancel，并在 Host 返回 terminal 之前保持 signal handler 与资源 lifecycle。

## 修改文件

- `dayu/cli/session_execution.py`
  - 删除 prompt 专属 second-SIGINT competition 与 local-exit 分支。
  - `_cancel_prompt_run_and_wait_for_terminal()` 只发出一次 typed graceful cancel，并直接等待 `cancel_entrypoint_run_and_wait` 返回 canonical terminal。
  - 删除不再属于 cancel helper 输入的 SIGINT count/monitor 参数；Run accepted 前仍返回 `None` 且不伪造 Host cancel。
  - 保留外层 `CliSigintMonitor` 到 terminal 后 cleanup，因此快速后续 SIGINT 只被计数合并，不恢复成 `KeyboardInterrupt`。
- `tests/cli/test_prompt_command.py`
  - 用 `_ControlledCancelHost` 的 `asyncio.Event` barrier 精确冻结 Host terminal。
  - 用 `_ControlledSigintMonitor` 在 handler 安装后先后注入两次 SIGINT。
  - 断言首次中断只记录一次 graceful cancel；第二次中断后 operation 仍 pending、cursor 未推进；释放 canonical CANCELLED 后才退出 130、关闭 watcher/monitor 并推进 cursor。
  - 保留一次 SIGINT、Escape、Run accepted 前 no-Host-cancel、terminal arrival 和 interactive regression 覆盖。

## Scope 判定

没有修改 Service/Host cancel implementation、interactive state machine、runtime display 文案或任何 SQLite 状态；没有引入 timeout、sleep、CLI 假终态、下游补写或测试特例。测试中的 timeout 只用于防止异步断言永久挂起，不参与生产语义。

## 验证证据

1. 定向取消测试：
   - `pytest -q tests/cli/test_prompt_command.py -k 'sigint or esc or cancel_helper or cancel_terminal'`
   - `8 passed`。
2. 受影响 prompt/runtime-display/interactive 回归与覆盖率：
   - `pytest -q tests/cli/test_prompt_command.py tests/cli/test_runtime_display.py tests/cli/test_interactive_command.py --cov=dayu.cli.session_execution --cov-report=term-missing`
   - `102 passed`。
   - `dayu/cli/session_execution.py` 覆盖率 `80%`。
3. 静态类型：
   - `pyright dayu/cli/session_execution.py tests/cli/test_prompt_command.py`
   - `0 errors, 0 warnings, 0 informations`。
4. `git diff --check`：通过。

## README 判定

prompt 的用户取消生命周期说明需要与新 contract 同步，已按 accepted plan 留到 S6 统一更新根 README 与 tests README；本 slice 不提前修改文档。

## 残余风险与后续验证

- fake Host 已证明第二次 SIGINT 不越过 terminal barrier；真实 subprocess 的精确按键时序、Host/runtime SQLite、EventLog、Run/attempt terminal state 仍由最终 P44/P45/P46、PC-BD-02、PC-CN-07 frozen scenario 重放确认。
- interactive 二次 SIGINT 的既有本地退出 contract 未修改，并已包含在受影响回归中。

## Gate 结论

S2 实现与验证完成，进入独立 `deepreview` gate。
