# WU CLI Conformance F01-F07 — S3B F03 Real-evidence Regression Implementation

## 1. Gate result

- **Status:** `READY-FOR-DUAL-S3B-CODE-REVIEW`
- **Slice:** PR 190 / F03 real-evidence regression fix
- **Scope:** prompt very-early standalone Escape、prompt pre-accept SIGINT、interactive Enter 后 very-early SIGINT，以及 CLI-owned terminal/signal lifecycle。
- **Boundary:** Host 仍是 Run acceptance、cancel、Attempt、canonical terminal 与 cleanup 的唯一 owner；没有修改 Host、Engine、Service、frozen registry 或 F01/F02/F04-F07 语义。
- **Workspace:** 未 stage、commit、push 或操作 PR；保留进入本 slice 前已有的四份 S8 README diff 与 `wu-cli-conformance-f01-f07-s8-implementation-codex.md`，其 `FAILED-CONFORMANCE-OBSERVATION` 未改写。

## 2. 动机与直接证据

本 slice 的动机成立，且不是 harness 误报。只读输入为：

- `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-20260802T212755Z-eae09be97963/summary.md`
- 同 bundle 的 `bundle-index.json`
- F03 redacted `command-result.json`、`sqlite-selected-rows.json` 与 terminal capture
- accepted S3 plan / implementation / review artifacts
- frozen `docs/cli_ci_scenarios.json` 中 `readiness_proof.prompt` 与 `readiness_proof.interactive`

失败 harness 的发送时序符合 frozen 场景：

- prompt standalone Escape 在进程启动后 `0.0615s` 发送；120 秒内只有 `SESSION_CREATED`，无 Run/Attempt/terminal；
- interactive composer 在 `1.2960s` 可见，`submit-double-SIGINT` 在 `1.3699s` 执行；进程最后 exit 130，但只有 `SESSION_CREATED`，无 Run/Attempt/cancel/terminal；
- active prompt double-SIGINT 与完整 CSI/Home/Delete、Alt、bracketed paste 已有真实成功证据，不是本次缺陷。

因此不能把产品缺陷降级为 harness 问题，也不能通过放宽 frozen oracle 修复。

## 3. Root cause 与语义 owner

### 3.1 Prompt invocation input owner 安装过晚

`dayu/cli/commands/prompt.py` 原先在 runtime prepare、Host open、Session ensure 与 attachment 之后，才由 turn helper 创建/启动 Escape monitor 并安装 SIGINT handler。启动窗口内的 input 没有 owner；同时 helper 以安装时的 SIGINT count 作为 baseline，会主动丢弃 invocation 已记录的 pre-accept SIGINT。

修复后 prompt 命令在 runtime/Host 状态之前创建并启动两个 input owner，durable action/count 穿过 prepare 与 acceptance barrier，最终只作用于随后同一 accepted Run。第二次 Ctrl+C 只升级本地 `exit-after-cancel`，仍等待 Host canonical terminal 与 attachment cleanup。

### 3.2 `tty.setcbreak` 默认清空 prestart 输入

第一次真实修复验证提供了更直接的代码/数据同源证据：即使 monitor 已提前到 async command 起点，启动后 60ms 写入的 Escape 仍被丢失，真实 Run 到达 `RUN_SUCCEEDED`。Python 3.11 的 `tty.setcbreak(fd)` 默认使用 `TCSAFLUSH`；monitor 安装时会清空已经到达 slave input queue 的字节。

`TtyRunningKeyMonitor` 现在以 `TCSANOW` 安装完全相同的 cbreak flags。terminal input owner 因而保留 invocation 启动后已到达的 chord/sequence，再交给既有 public VT100 parser 与 0.1 秒 ambiguity window：窗口内出现 continuation 时仍按 Alt/完整序列，只有无 continuation 的单独 Escape 才产生 cancel intent。

### 3.3 Interactive 把 pending submit 错判为 idle

interactive 原状态机只看 `current is None`。普通 Enter 已被 prompt-toolkit key binding 解码、但 `prompt_async` task 尚未把 typed `SUBMIT` 交付给 REPL 时，紧随其后的两次 SIGINT 会走 idle 分支并直接 exit 130。

正确 owner 是 composer：key binding 在 ordinary Enter callback 内同步记录“非空 submit 已解码但尚未被 REPL 确认”的 typed state；REPL 只在这个状态下暂存 early SIGINT，并在同一 typed SUBMIT 创建 turn 后把意图绑定到该 turn。该状态在 `accept_submit` 时清除，不依赖 sleep、时间窗口、raw-field 猜测或 downstream fallback。

### 3.4 PTY lflag 判定

旧 bundle 的 full lflag 为 `1483 -> 536872395`，XOR 是 `536870912 / 0x20000000`。本机 Darwin `termios.PENDIN` 恰为同一 bit。隔离新鲜 PTY 的 owner tests 与真实 lane 均证明 Dayu 安装的 `ECHO/ICANON/ISIG/IEXTEN` 完整恢复；full lflag 唯一差异仍为 kernel pending-input 状态 `PENDIN`。

本实现没有清理或伪造 `PENDIN`。它不是 Dayu 安装的 terminal mode，且修改它会把 harness/audit 队列状态错误归给产品 owner。

## 4. Implementation

- `dayu/cli/commands/prompt.py`
  - invocation 起点安装 SIGINT 与 running-key owner；
  - 所有正常、异常与 monitor-start failure 路径均嵌套恢复 key terminal mode 和 signal handler；
  - 同一 monitor 实例传入 prompt turn，不重建 source of truth。
- `dayu/cli/agent_entrypoint.py`
  - `CliSigintMonitor.install()` 幂等，允许 command owner 与既有 turn helper 复用同一实例而不覆盖原 handler snapshot。
- `dayu/cli/run_keys.py`
  - cbreak 安装改用 `TCSANOW`，保留 prestart input；
  - decoder、ESC continuation、Alt/CSI/paste 规则不变。
- `dayu/cli/composer.py`
  - `InteractiveComposer` 增加 typed `has_pending_submit_intent()` contract；
  - ordinary Enter 同步记录非空 submit intent，REPL acceptance 后清除。
- `dayu/cli/session_execution.py`
  - prompt 从 invocation count `0` 消费 durable SIGINT，不把 early signal 当 baseline；
  - interactive 只依据 composer owner state 暂存 early SIGINT，随后绑定同一 turn；
  - cancel、Attempt、terminal 与 cleanup 继续全部走 Host public contract。

## 5. Owner tests

受影响矩阵覆盖：

- prompt runtime-prepare 前 standalone Escape、第一次 Ctrl+C、double Ctrl+C；
- prompt monitor install/start exception、handler/terminal restoration、acceptance barrier、single cancel 与 terminal 后 exit 130；
- interactive ordinary Enter typed intent 生命周期；
- interactive typed SUBMIT 尚未交付时第一次/double Ctrl+C、durable acceptance、provider/Run wait、Host cancel/Attempt/terminal、第二次 Ctrl+C 不强杀；
- active Run closeout、tool/activity execution 周边既有矩阵；
- fresh PTY prestart standalone Escape；
- fresh PTY prestart Alt+X、Home/Delete/CSI、bracketed paste；
- active完整序列、ESC ambiguity、terminal restore 与 start-failure restore。

最终 focused pytest：`204 passed, 3 warnings`。warnings 均为既有第三方 deprecation warning。

单文件 coverage：

- `dayu/cli/agent_entrypoint.py`: `94%`
- `dayu/cli/commands/prompt.py`: `93%`
- `dayu/cli/composer.py`: `91%`
- `dayu/cli/run_keys.py`: `93%`
- `dayu/cli/session_execution.py`: `85%`

## 6. 真实 PTY / Mimo 定向验证

验证使用当前 workspace 源码、真实 `.venv/bin/dayu-cli`、真实 POSIX PTY、Mimo plan 配置与两个自动清理的隔离临时 workspace。它是 implementation verification，不修改、替代或覆盖旧 immutable bundle。

| Lane | Input timing | Exit | Host/EventLog projection | Terminal owner flags |
|---|---|---:|---|---|
| prompt pre-accept Escape | 进程启动后 60ms 写入 standalone ESC | 130 | `RUN_ACCEPTED`、`ATTEMPT_STARTED`、唯一 `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED` | restored |
| interactive pre-accept double SIGINT | composer 可见后写入非空 prompt+Enter，随后 very-early 两次 SIGINT | 130 | `RUN_ACCEPTED`、`ATTEMPT_STARTED`、唯一 `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED` | restored |

两条 lane 都没有在 Host terminal 前退出。full lflag 均为 `1483 -> 536872395`，唯一 XOR `0x20000000 == termios.PENDIN`；owner mask 恢复为 true。临时 workspace 与临时 harness 已清理，未把包含 durable provider header 的 SQLite 持久化为新 artifact。

## 7. Static、integrity 与 README audit

- full `pyright`: `0 errors, 0 warnings, 0 informations`
- changed-file Ruff: pass
- `git diff --check`: pass
- staged diff: empty
- frozen registry working-tree diff: empty
- `docs/cli_ci_oracles.json` SHA-256: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
- `docs/cli_ci_scenarios.json` SHA-256: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`

README trigger 已核对：本修复恢复既有 documented cancel/terminal contract，不增加命令、参数、输出通道、配置、工作区位置或用户工作流。进入 slice 前已有的 `README.md`、`dayu/config/README.md`、`dayu/host/README.md`、`tests/README.md` S8 diff 已覆盖当前测试/用户说明并被原样保留；本 slice 不追加 README 改动。

## 8. Residual risk 与下一入口

- 独立 Authorization 持久化 residual 未处理，仍由原 owner/work unit 承担。
- 本 artifact 不是 S8 conformance pass；旧 S8 `FAILED-CONFORMANCE-OBSERVATION` 与其四份 README 保持不变。
- 尚未执行 dual code review，也不在本 implementation gate 自行预判 review 结果。

本 slice 在 `READY-FOR-DUAL-S3B-CODE-REVIEW` 停止。下一合法入口是总控派发两路独立 S3B code review；全 work unit 仍只在 final closeout 停止。
