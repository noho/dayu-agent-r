# Gateflow S2 code review adjudication — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：`implementation review`
- Slice：S2，仅 F05-F09
- Base：`d210444f`
- Implementation artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s2-implementation-20260801-171554.md`
- AgentMiMo review：`docs/reviews/code-review-20260801-172926.md`
- AgentDS review：`docs/reviews/code-review-20260801-172515.md`
- Controller decision：`changes required`
- Next gate：AgentCodex 修复 accepted findings，随后 MiMo/DS 双路独立 re-review

## Controller validation

Controller 亲自读取 accepted plan §6.1-§6.9、冻结 F05-F09、implementation artifact、四个生产文件、四个测试文件和两份独立 review，并重跑：

```text
pytest tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py tests/cli/test_run_keys.py \
  tests/cli/test_runtime_display.py tests/cli/test_interactive_run_view.py \
  tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q -x
```

结果：`141 passed, 3 warnings`。定向 pyright 为 `0 errors`，`git diff --check` 通过。测试全绿只证明当前覆盖路径，不替代下述缺口裁决。

## Reviewer finding adjudication

### MiMo-001 — generation 参数语义

- Decision：`rejected-with-reason`
- Reason：`generation` 是 `_InteractiveActiveTurn` 的本地竞态身份，不是 submit DTO 输入；由 `_start_interactive_turn` 在构造 active turn 时写入、terminal 裁决时读取，owner 与用途清晰。把它移回 driver 赋值会拆散构造不变量，没有 correctness 收益。

### MiMo-002 — TTY/non-TTY 调用块重复

- Decision：`rejected-with-reason`
- Reason：重复仅为两条明确 control-flow 的参数投影；为消除这点重复新增一个宽参数 helper 会扩大耦合并弱化 startup barrier 可读性，违反本 work unit 的不过度设计边界。

### DS-001 — heterogeneous task 联合类型别名

- Decision：`rejected-with-reason`
- Reason：联合类型精确列出四种可等待结果；建议改成 `Task[object]` 与项目禁止 `object` 的严格类型约束冲突，省略泛型也不允许。该别名没有运行时或 owner 缺陷。

### DS-002 — exit-after-cancel 后继续创建 SIGINT waiter

- Decision：`rejected-with-reason`
- Reason：第三次及更多 OS SIGINT 必须被观察并显式 no-op；保留 waiter 正是该 contract 的实现，且 finally 有统一回收。停止创建 waiter 反而让进程级 signal 回退到不可控行为。

## Controller accepted findings

### S2-CR-001 — 高 — 不支持 asyncio signal handler 的平台退回原生 `KeyboardInterrupt`

- Status：`accepted`
- Owner：`dayu.cli.agent_entrypoint.CliSigintMonitor`，其直接 consumer 为 interactive invocation state machine。
- Direct evidence：`CliSigintMonitor.install()` 在 `loop.add_signal_handler(SIGINT, ...)` 抛出 `NotImplementedError` 或 `RuntimeError` 时只把 `_installed=False` 并返回。此后 startup reconnect、pre-accept、provider/tool/closeout 期间的 OS Ctrl+C 不进入计数 waiter，而会由原生 `KeyboardInterrupt` 中断 `asyncio.run()`。
- Counterexample：Windows 等不支持 `loop.add_signal_handler` 的事件循环中，第二次 Ctrl+C 可通过 task cancellation 取消 submit/cancel canonical waiter；startup 单次 SIGINT 也不走同一 cleanup owner。这直接违反 F08 的统一 graceful lifecycle，不能以本机 POSIX PTY 通过替代。
- Required fix：在 `CliSigintMonitor` owner 内增加最小、可恢复的同步 `signal.signal` fallback；显式记录安装模式，`close()` 按同一模式恢复 previous handler，不调用不支持的 remove API。不得把 fallback 放进 interactive command 或吞掉 signal。补确定性 owner test，模拟 `add_signal_handler` 不可用，证明 notify/count/wait/close 恢复与 interactive startup/active lifecycle 仍成立。

### S2-CR-002 — 中 — 真实 PTY evidence 依赖固定 50ms timing，且 capability/普通 Enter 实证不完整

- Status：`accepted`
- Owner：`tests/cli/test_interactive_composer.py` 的真实 POSIX PTY contract test。
- Direct evidence：`test_real_posix_pty_exact_sequences_and_terminal_mode_restore` 在两次写入前固定 `await asyncio.sleep(0.05)`，未等待 PTY 实际进入 prompt_toolkit raw mode；慢 CI 可在 standalone Escape 写入时仍处于 canonical mode并超时。该用例也没有在同一真实 PTY 中用普通 Enter bytes 证明不可区分输入仍提交，artifact 未记录实际 prompt_toolkit version/capability evidence。
- Required fix：用可观察的 PTY mode/readiness 条件替换固定 sleep，保留有界 timeout；在真实 PTY 用例中加入 ordinary Enter exact bytes 的正向提交证据，并把版本/capability结果写入 fix artifact。不得修改 prompt_toolkit 全局 ANSI mapping或猜测未知序列。

### S2-CR-003 — 高 — fresh Session 的 queued closeout 仍由 fake Host 手工终态冒充

- Status：`accepted`
- Owner：interactive CLI→Service→Host public path integration test；生产 owner 仍为现有 sole QUEUE state machine，不下沉 UI 语义。
- Direct evidence：`test_interactive_exit_after_cancel_waits_accepted_sole_queue_terminal` 使用 `_ControlledInteractiveHost` 并由测试直接调用 `finish_run("run-2")`；它只能证明本地 task 未被取消，不能证明真实 Host 在无 label fresh Session 中会在 current cancelled 后提升同一 queued Run并进入 terminal。`tests/service/test_entrypoint_runtime_interactive_path.py` 当前真实 Host tests只覆盖顺序完成与 label continuity，没有 exit-after-cancel + sole queued durable status 查询。
- Counterexample：若真实 Host promotion或 CLI attachment close顺序使 queued Run永久停留 `QUEUED`，fake 手工 terminal仍会绿；下一次 fresh invocation不会复用该 Session，正是 accepted plan §6.5/§6.7 禁止的孤儿状态。
- Required fix：在 S2 已允许的 integration owner中增加确定性真实 Host public-path test，覆盖无 label/fresh Session 的 current + sole QUEUE、当前 canonical cancel、queued promotion/terminal、CLI exit 130 后 durable `Run/Attempt` 无 `RUNNING/QUEUED` 残留；同时把 provider/tool/closeout 的阶段证据绑定到真实 Host/worker barrier或已有 owner-level stage truth，不得只用未改变行为的字符串参数冒充阶段。若现有 public test infrastructure 无法在不越界下构造该证据，必须报告 blocker，不得降低断言或修改 Host owner。

## Scope and residual risk

- Fix 仍严格限于 accepted plan §6.1 的生产/测试文件和一个 collision-safe fix artifact。
- 不更新 README、design、registry、oracle；这些继续由 S6 统一处理。
- S3-F10、S4-F11/F12、S5-F13 与真实 provider scenario 未实施，不能在 S2 宣称关闭。
- Windows 真实 console 仍可能需要 CI 实证，但同步 signal fallback 的 owner contract 必须在本 slice 先成立；不得把已知 production fallback 缺口仅记为 residual risk。
