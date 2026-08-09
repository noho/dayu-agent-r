# Gateflow S2 accepted-finding fix — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：`implementation review -> fix`
- Slice：S2，仅 F05-F09 accepted finding fix
- Base / 授权起点：`d210444f226a34ea033f9c07487a87b7c320ec6c`
- Implementation artifact：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-implementation-20260801-171554.md`
- Review artifacts：
  - `docs/reviews/code-review-20260801-172926.md`
  - `docs/reviews/code-review-20260801-172515.md`
- Controller adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-code-review-adjudication-20260801-173202.md`
- Decision：S2-CR-001/002/003 已按 controller 要求修复，等待独立 re-review
- Next gate：`re-review`
- 本轮未执行 re-review、S3-S6、commit、push 或 PR 操作。

## Scope 与 first-principles judgment

三个 accepted finding 的动机均成立：

1. `CliSigintMonitor` 原实现只拥有 asyncio handler 模式；当
   `loop.add_signal_handler` 不可用时没有继续拥有 SIGINT 语义，原生
   `KeyboardInterrupt` 可以越过 interactive 状态机并取消 canonical waiter。
2. 固定 50ms 不是 PTY raw-mode 事实；慢调度环境下不能证明 bytes 是在
   prompt_toolkit 已接管终端后写入。
3. fake Host 手工调用 `finish_run` 只能证明 CLI 本地 task 未被取消，不能证明 fresh
   Session 的真实 Host admission、current canonical cancel、queued promotion 与 durable
   terminal truth。

语义 owner 分别是：

- 信号安装、计数与恢复：`dayu.cli.agent_entrypoint.CliSigintMonitor`；
- exact terminal bytes / raw-mode capability：真实 POSIX PTY composer owner test；
- fresh Session queue/cancel/promotion：真实 CLI -> Service -> Host public path、真实 worker
  barrier 与 Host durable `RunRow` / `AttemptRow` truth。

生产代码只新增 `dayu/cli/agent_entrypoint.py` 的 CR-001 最小 owner 修复；CR-002/003
只补强 allowed tests。没有修改 Host 生产代码，也没有把 queue、cancel 或 terminal
语义下沉到 UI 测试 seam。

### Fix 新增修改文件

- `dayu/cli/agent_entrypoint.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_interactive_composer.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- 本 collision-safe artifact

工作树中其余 S2 implementation 文件保持未提交状态；本 fix 没有进入 S3-S6。

## Finding fixes

### S2-CR-001 — 已修复

#### Owner fix

- `dayu/cli/agent_entrypoint.py:32` 新增封闭的
  `_CliSigintInstallationMode`：`NONE`、`ASYNCIO`、`SYNCHRONOUS`。
- `CliSigintMonitor.install()` 在 `add_signal_handler` 抛出
  `NotImplementedError` / `RuntimeError` 时，直接在同一 owner 内使用
  `signal.signal(SIGINT, self.notify)`；同步 handler 仍写入同一 `count + Event`
  状态机，不回退为原生 `KeyboardInterrupt`。
- `CliSigintMonitor.close()` 按安装模式恢复：asyncio 模式才调用
  `remove_signal_handler`，同步模式只恢复捕获的 previous handler；两条路径最终都回到
  `NONE`，没有在 consumer 或 interactive command 增加 fallback。

#### Direct tests

- `tests/cli/test_interactive_command.py:946` 的
  `_SyncSigintFallbackHarness` 让 `add_signal_handler` 确定性抛
  `NotImplementedError`，并让任何同步模式误调用 `remove_signal_handler` 立即失败。
- `test_interactive_startup_single_sigint_cleans_up_and_returns_130` 使用真实
  `CliSigintMonitor` fallback handler 触发 startup SIGINT，断言：count=1、startup
  observation 被 caller-local 取消、0 submit、0 Host cancel、attachment 恰好关闭一次、
  exit 130、previous handler 恢复。
- `test_interactive_os_sigint_first_second_and_third_follow_same_lifecycle` 使用同一真实
  fallback handler 三次触发 active lifecycle，断言 single canonical cancel、第二次只登记
  exit-after、第三次 no-op、canonical cancel waiter 未被取消、handler 同源恢复。
- 既有 asyncio-supported 回归
  `test_prompt_sigint_monitor_restores_previous_process_handler` 仍通过，证明 POSIX 安装语义
  未改变。

#### Residual risk

- 真实 Windows console 本机不可用；同步 fallback 的 owner contract 已确定性覆盖，但
  Windows 原生 console delivery 仍由 Windows CI owner 验证。分类：既有平台 CI owner。

### S2-CR-002 — 已修复

#### PTY evidence fix

- `tests/cli/test_interactive_composer.py:496` 新增有界
  `_wait_for_pty_raw_mode`，直接读取 PTY slave `termios.tcgetattr(...)[3]`；只有
  ECHO / ICANON / ISIG / IEXTEN 四项均关闭才允许写 bytes。timeout=2s，poll=5ms。
- `test_real_posix_pty_exact_sequences_and_terminal_mode_restore` 的三次写入前全部使用该
  observable readiness；该真实 PTY 用例内不再使用固定 `sleep(0.05)`。
- 同一 PTY 在 exact Shift+Enter 组合提交后，单独写入 exact bytes
  `b"ordinary\r"`，断言 typed event 为 `SUBMIT` 且 exact draft 为 `ordinary`；因此普通
  Enter 不被猜成 Shift+Enter。
- 每轮 submit 后调用真实 composer `accept_submit`，随后再次进入 raw mode；每轮退出都
  断言 terminal local flags 恢复到原值。

#### Version / capability evidence

- 本机：`Darwin-arm64`，`os.name=posix`。
- `prompt_toolkit=3.0.52`。
- capability 结果：
  - `\x1b[27;2;13~` 在真实 PTY 中保留 exact raw data 并按冻结 mapping 插入 LF；
  - 普通 `\r` 在同一 PTY 中提交 `ordinary`；
  - standalone Escape 仍经 parser timeout 投影 cancel；
  - test 未修改 prompt_toolkit 全局 ANSI mapping，未猜测未知 CSI-u。

#### Residual risk

- 非 POSIX 平台继续按既有 capability skip；Windows console 的 Shift+Enter 可区分能力不由
  本机 PTY 冒充。分类：既有平台 CI owner。

### S2-CR-003 — 已修复

#### Fake evidence removal

- 原 `test_interactive_escape_cancels_once_across_active_stages` 删除
  `"provider" / "tool" / "closeout"` 字符串参数，不再把只改变测试注入事件的字符串描述
  当作阶段事实。
- 收窄后的 `test_interactive_cancel_sources_merge_once_after_accepted_activity` 只承诺 CLI
  owner 事实：accepted active turn 收到 Escape / Ctrl+C 时合并为 single cancel。

#### Real CLI -> Service -> Host integration

`test_unlabeled_interactive_exit_after_cancel_closes_real_current_and_sole_queue` 走：

```text
cli_main.main("interactive", no label)
-> interactive command
-> Service runtime assembly / public entrypoint helpers
-> open_host(real SQLite Host)
-> real admission / dispatcher / worker cancel hook / terminal closeout
```

直接证据：

- CLI 参数不含 `--label`，因此使用 fresh Session owner path。
- 第一轮真实 worker `events()` 已开始后，composer 才提交 sole queued follow-up。
- `tests/service/test_entrypoint_runtime_interactive_path.py:593` 的 durable barrier 使用
  `read_non_terminal_runs_for_session`，只有同一 fresh Session 精确出现一个 `RUNNING` 与
  一个 `QUEUED` 才触发第一次 SIGINT；不是从字符串、顺序或 fake status 反推。
- 真实 Host `cancel_run` 把 canonical `cli_sigint` 传播到 current worker `on_cancel`；worker
  产出 typed `EngineEventType.RUN_CANCELLED`，不是测试直接写 Host terminal。
- 第二次 SIGINT 被 driver 消费后，冻结状态机继续创建第三个 no-op SIGINT waiter；test
  monitor 只在该 waiter 收到 `observed_count >= 2` 时释放 current terminal。因此测试没有
  停止 exit-after 后的 SIGINT waiter，也没有用固定 tick/sleep 猜测 exit intent。
- current canonical cancel closeout 后，真实 Host promotion 才 dispatch 第二个 worker；其
  typed `FINAL_ANSWER` 经真实 Host closeout 为 `SUCCEEDED`。
- CLI 最终 exit 130；关闭真实 Host 后读取同一 SQLite owner truth：
  - `read_non_terminal_runs_for_session(...) == ()`；
  - current：`RunStatus.CANCELLED / AttemptStatus.CANCELLED`；
  - queued：`RunStatus.SUCCEEDED / AttemptStatus.SUCCEEDED`；
  - 两个 real worker handle 均由 Host 关闭；queued Run 没有收到 cancel。

#### Provider / tool / closeout stage ownership

CLI 不拥有 provider、tool 或 durable closeout 的内部阶段分类；因此本 fix 不再用 CLI fake
参数证明这些阶段。阶段语义绑定既有 owner truth，并重跑：

- provider barrier：
  `tests/host/test_compaction_cancellation_scope.py::test_parent_cancel_is_visible_to_running_attempt_child`，
  在真实 blocked provider call 后验证 linked cancellation；
- tool barrier：
  `tests/host/test_toolruntime_executor.py::test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion`，
  在真实 process-backed tool execution 中验证 cancel；
- closeout truth：
  `tests/host/test_run_attempt_transitions.py::test_active_cancel_watchdog_closeout_first_committer_wins_after_cooperative_cancel`，
  由 durable transition owner 断言 cooperative cancel 与 watchdog closeout first-committer
  事实。

以上三项与真实 CLI -> Host worker integration 合计 `5 passed`；不再宣称字符串参数本身是
stage evidence。

#### Residual risk

- 未运行真实外部 provider CLI scenario；按 accepted plan 属 S6，不在 S2 伪报关闭。
  分类：covered by later approved slice S6。

## Rejected reviewer observations kept unchanged

- 未改变 `generation` 结构。
- 未抽取 TTY/non-TTY 宽 helper。
- 未用 `object`、无泛型或其它弱类型替换 heterogeneous task 联合类型。
- 未停止 exit-after 后的 SIGINT waiter；CR-003 integration 反而以第三个 waiter 作为第二次
  SIGINT 已被状态机消费的直接 barrier。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Focused S2

```text
pytest tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py tests/cli/test_run_keys.py \
  tests/cli/test_runtime_display.py tests/cli/test_interactive_run_view.py \
  tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q -x
```

结果：`138 passed, 3 warnings`。warnings 均为 edgartools deprecated module。

### Real Host / monitor / stage owners

- fresh Session real Host integration 单测：`1 passed`。
- fallback startup、fallback active、asyncio-supported restore：`3 passed`。
- prompt/Fins related `CliSigintMonitor` regressions：`4 passed`。
- CLI accepted-active + provider/tool/closeout owner truth：`5 passed`。

### Affected regression

```text
coverage run --branch -m pytest tests/cli \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
```

结果：`1110 passed, 7 skipped, 3 warnings`。7 个 skip 为既有平台/capability 条件。

### Modified production branch coverage

| Production file | Branch coverage |
|---|---:|
| `dayu/cli/agent_entrypoint.py` | 82% |
| `dayu/cli/commands/interactive.py` | 90% |
| `dayu/cli/composer.py` | 92% |
| `dayu/cli/run_keys.py` | 91% |
| `dayu/cli/session_execution.py` | 84% |

全部 modified production files 达到 `>=80%`，没有新增 pragma / no-cover exclusion。

### Type / lint / format / diff

- 全仓 `python -m pyright dayu/ tests/ utils/`：
  `0 errors, 0 warnings, 0 informations`。
- 本轮 9 个 production/test 文件 `ruff check`：`All checks passed!`。
- 本轮 9 个 production/test 文件 `ruff format --check`：`9 files already formatted`。
- `git diff --check`：通过。
- `python -m compileall -q dayu/cli tests/cli
  tests/service/test_entrypoint_runtime_interactive_path.py`：通过。

全仓 `ruff check .` 与 `ruff format --check .` 也已实际执行，但仓库既有 baseline 分别为
`136 errors` 与 `512 files would be reformatted`；输出没有列出本轮 9 个文件。本 fix 不得
越出 §6.1 清理这些 unrelated files。分类：pre-existing repository hygiene baseline，交由
仓库级 lint/format owner / 后续用户决策；不是本轮新增或扩散。

### Secret / payload safety

- 新增 diff 扫描 AWS access key、`sk-` token、Authorization Bearer、private-key header 与
  长 API-key assignment：零命中。
- `agent_entrypoint.py` 新增 diff 对 `Any`、`object`、`getattr`、`hasattr`、coverage pragma：
  零命中。
- production diff 中涉及 `draft` / `user_prompt` 的新增行只做 typed state/input 传递；实际
  `print` 仍只输出固定 editor/sole-queue 提示，不输出 draft、user prompt、raw bytes 或
  payload。
- 没有打印环境变量、上传 workspace 内容或把显式参数塞入 extra payload。

## README / stable artifact decision

本 fix 命中 tests/CLI 行为描述触发，但用户与 accepted S2 scope 明确禁止更新 README、
design、registry、oracle，并冻结到 S6。因此本轮只写该 collision-safe fix artifact；没有
机械同步稳定文档。

## Residual risks 与 uncovered areas

- Windows 真实 console delivery / Shift+Enter capability：既有 Windows CI owner。
- 真实外部 provider CLI scenario：covered by later approved slice S6。
- S3-F10、S4-F11/F12、S5-F13、S6 registry/docs/oracle：未实施、未验证、未宣称关闭；
  各自由 later approved slice owner。
- 全仓 ruff/format 既有 baseline：repository hygiene owner / 后续用户决策；本轮 touched
  files 已通过，不允许越界批量改写。

没有 Host production blocker、scope blocker 或未分类的 S2 correctness residual risk。

## Completion

- S2-CR-001：`已修复`。
- S2-CR-002：`已修复`。
- S2-CR-003：`已修复`。
- Completion status：`S2 accepted-finding fix complete`。
- Artifact：
  `docs/reviews/gateflow-wu-cli-interactive-02-s2-fix-20260801-175453.md`
- Next entry point：`re-review`。
- 按用户授权停止在 re-review 前；未 review、commit、push、创建 PR 或进入 S3-S6。
