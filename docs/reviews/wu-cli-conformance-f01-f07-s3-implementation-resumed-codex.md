# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Resumed Implementation 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S3 / F03 — graceful cancel and escape sequences`
- Gate：`implementation resumed`
- Entry HEAD：`fc1b494694e585e46e688fecdf76036abee50ade`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-02（Asia/Shanghai）
- 状态：`IMPLEMENTATION COMPLETE — next: controller-dispatched independent code reviews`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s3-implementation-resumed-codex.md`

本记录只覆盖 implementation 与 implementation validation。按总控 follow-up，不执行
自我 deep review，不记录 review/fix/re-review 结论，也不替代后续 MiMo/DS 独立 durable
code-review artifacts。

## Preflight、直接证据与语义 owner

本次 resumed entry 的 HEAD 精确为 `fc1b4946`，其中 accepted plan §5 与 S3
correction/fix/controller artifacts 已把此前 blocker 收口为 public parser resolution
batch 分类。当前环境为 Python 3.11、`prompt_toolkit==3.0.52`；直接 public seam 证据为：

- `Vt100Parser.feed("\x1b")` 不回调，随后一次 `flush()` 回调唯一
  `KeyPress(Keys.Escape, "\x1b")`；
- `feed("\x1bx")` 以及跨 chunk 的 `feed("\x1b")` / `feed("x")` 在最终一次
  feed resolution 中同步形成 `Escape, x` callbacks；
- 因而 standalone Escape 的唯一正确 owner 判据是 deadline-triggered flush 的完整
  batch，而不是 callback 到达时刻或 raw byte 特判。

语义边界保持不变：CLI input owner 只把 parser resolution 投影为
`RunningKeyAction`；`_ActiveTurnCloseout` 只协调本 turn 的 acceptance、cancel intent、
exactly-once Host cancel 与 canonical terminal observation；Host 仍唯一拥有 Run lifecycle、
graceful cancel 和 terminal truth。composer/display/cursor/attachment 与 monitor teardown
仍由 prompt/interactive outer driver 拥有。

## 实际 scope

production/test 修改严格只有 accepted plan §5.1 的七个路径：

- `dayu/cli/run_keys.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/composer.py`
- `tests/cli/test_run_keys.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`

另新增本 resumed implementation artifact。未修改 Host、Service、Engine、registry、
design、README、依赖声明或其它文件；未 stage、commit、push 或操作 PR。

## 实现 contract

### 单一 VT100 parser / decoder owner

- `TtyRunningKeyMonitor._read_loop()` 在 reader thread 内恰好创建一个 public
  `Vt100Parser`、一个标准库 UTF-8 incremental decoder 与一个 thread-local callback
  collector；parser、decoder、collector drain 全部留在该线程。
- stdin 改为 chunk read。raw bytes 只用于判断是否 arm/refresh ESC ambiguity deadline，
  不解析 Alt、CSI、SS3、Home/Delete 或 paste；decoded text 只进入唯一 public parser。
- ambiguity 常量精确为 `0.1s`。deadline 一旦 armed，只能在无新输入且到期后的一次
  `parser.flush()` 返回时无条件清除；readable 与 deadline 同轮时先 read/decode/feed 并
  refresh。close/EOF 不合成 flush 或 action。
- 每次 public `feed()` 或 `flush()` 的同步 callbacks 冻结为一个 resolution batch，
  batch 完整分类后才经 `call_soon_threadsafe` 投递 typed action。

分类真值表：

| resolution batch | typed action |
|---|---|
| deadline flush 的唯一 `Keys.Escape`，且 `data == "\x1b"` | `CANCEL_RUN` 一次 |
| feed/flush 的 `Escape + ordinary continuation` | 不取消 |
| CSI / SS3 / Home / Delete / known Alt / bracketed paste | 不取消 |
| 任意 batch 内独立 `Keys.ControlT` | `TOGGLE_ACTIVITY` 一次 |
| paste payload 内的 Ctrl+T | paste data，不产生 action |
| Ctrl+C control byte | 不产生 cancel；不成为 signal owner |

`RunningKeyAction` 保持唯一 typed key contract；删除了 raw-byte action helper，没有引入
`KeyProcessor`、private parser state、第二套 byte parser 或等价 key enum。

### Acceptance barrier 与 graceful closeout

- `_AcceptedRunBarrier` 唯一发布 exact accepted Run id：同 id 幂等，冲突 id fail fast；
  pre-accept intent 不从 task 顺序、日志或时间戳反推 Run identity。
- `_ActiveTurnCloseout` 冻结首个 cancel reason，最多创建一个
  `wait_accepted_then_cancel` task。Escape/first SIGINT 只登记
  `CANCEL_REQUESTED`；只有 SIGINT monitor 观察到的 second Ctrl+C 单调升级为
  `EXIT_AFTER_CANCEL`。
- cancel intent 可跨 acceptance barrier；accepted 后只调用一次对应 prompt/interactive
  Host graceful cancel public path，并等待 Host canonical terminal。terminal 若先成立，
  保留真实 terminal 且不发迟到 cancel。
- second/third Ctrl+C 不本地取消 Host wait、不伪造 `CANCELLED`、不立即返回 130；
  130 只在同一 closeout 返回 canonical terminal，且 outer driver 完成 display、render、
  cursor、composer/key/signal/attachment cleanup 后可见。
- coordinator 字段只包含 barrier、typed intent、cancel reason/task 与 terminal
  observation；不持有 composer、display、cursor、attachment、generation、queued draft、
  History 或 monitor。

核心状态 trace：

```text
SUBMITTING + Escape/first SIGINT -> CANCEL_PENDING_ACCEPT
CANCEL_PENDING_ACCEPT + accepted -> exactly-once Host graceful cancel
CANCEL_* + second SIGINT          -> EXIT_AFTER_CANCEL intent only
Host canonical terminal          -> closeout complete
outer UI/resource cleanup        -> normal terminal mapping / exit 130
```

### Prompt / interactive outer owner

- prompt 直接消费 `RunningKeyAction`；Ctrl+C 只由 `CliSigintMonitor` 计数。key/signal 与
  submit terminal 同一 event-loop batch 时先登记 control intent，再让 closeout 按
  canonical terminal 收敛。
- interactive composer 的 Escape/Ctrl+T 统一发送 typed `RUNNING_KEY_ACTION` event；
  Ctrl+C binding 只 raise `SIGINT`，由 invocation 已安装的唯一 SIGINT monitor 消费，
  composer 不再产生或计数 Ctrl+C cancel enum。
- interactive current turn 与 queued follow-up 原样携带同一 closeout identity；outer
  state 独占 composer phase、generation、queue promotion、display/render/cursor 和资源
  teardown，不把这些副作用塞进 shared coordinator。

## Owner-level deterministic tests

`tests/cli/test_run_keys.py` 覆盖 public feed/flush seam、classifier key+data 双条件、
Alt ASCII/Unicode、CSI arrows、SS3、Home/Delete、bracketed paste、paste payload Ctrl+T、
同 batch Ctrl+T、Ctrl+C no-op；可控 monotonic/select/read 脚本覆盖 0.1s deadline、
readable priority、refresh、空 flush、尾随 ESC、close-wins 与不重复 cancel；记录构造和
线程 id，证明一个 parser、一个 decoder、同 reader-thread owner，并覆盖 PTY action 投递、
termios 恢复和幂等 close。

`tests/cli/test_prompt_command.py` 覆盖 closeout identity/reason/exactly-once/terminal-first/
冲突 contract，pre-accept Escape 与 durable pre-accept SIGINT 跨 barrier，Ctrl+T、
standalone Escape、repeated SIGINT 及 canonical terminal/cleanup 后返回。

`tests/cli/test_interactive_composer.py` 覆盖 typed Escape/Ctrl+T event 与 Ctrl+C 仅 raise
SIGINT；`tests/cli/test_interactive_command.py` 覆盖 TTY/non-TTY pre-accept cancel、
first/second/third SIGINT、Escape 幂等、queued accepted follow-up、terminal race、
Ctrl+T 独立、canonical terminal 与 outer cleanup 偏序。

## 验证结果

### Focused pytest 与单文件 coverage

```bash
source .venv/bin/activate
pytest -q \
  tests/cli/test_run_keys.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py \
  --cov=dayu.cli.run_keys \
  --cov=dayu.cli.session_execution \
  --cov=dayu.cli.composer \
  --cov-report=term-missing
```

结果：`182 passed, 3 warnings in 11.32s`；warnings 均来自 `edgar` 依赖的既有
deprecation warning。单文件 coverage：

- `dayu/cli/run_keys.py`：`190 statements / 13 missing / 93%`
- `dayu/cli/session_execution.py`：`665 statements / 82 missing / 88%`
- `dayu/cli/composer.py`：`370 statements / 35 missing / 91%`

三者分别满足 `>=80%`，未使用总平均掩盖单文件缺口。

### Pyright

focused production/test allowlist：`0 errors, 0 warnings, 0 informations`。

全仓 `python -m pyright`：`0 errors, 0 warnings, 0 informations`。

### Integrity、allowlist 与 frozen registry

- `git diff --check`：通过。
- 两个 registry 的 `python -m json.tool`：通过。
- `docs/cli_ci_oracles.json` SHA-256：
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json` SHA-256：
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- Registry inventory：3/3 oracle id 唯一且 accepted；1051/1051 scenario id 唯一且
  accepted；F03 的 10 个 frozen scenario refs 全部存在；interactive readiness 为
  `mandatory=700 / covered=700 / gap=0 / unresolved=0`。
- 两个 registry 的 working-tree status 与 staged path 均为空；index 整体为空。
- production source scan：恰好一个 `Vt100Parser(...)` 和一个
  `getincrementaldecoder(...)`；`KeyProcessor`、private parser state、旧 accepted-state
  类型与 raw-byte action helper 均零命中。

## Docs decision

用户明确禁止本 slice 修改 README/design，accepted plan 也把 aggregate documentation
同步留给后续 S8。本次未修改任何 README/design/registry；本 implementation artifact
是唯一新增文档。

## Residual risk 与未覆盖项

- `MEDIUM / covered by later approved S8 evidence`：真实终端分块、ESC/Alt 固有的
  0.1s ambiguity、不同 provider/tool/closeout timing 与完整 live PTY scenario evidence。
- ESC 后在 ambiguity window 内紧接 ordinary character 与 Alt+该字符具有相同终端
  bytes；本实现按 frozen oracle 抑制该 batch 的 Escape cancel，不把不可区分输入扩展为
  新产品承诺。
- 当前 implementation 验证无 blocker；独立 code-review findings 尚未产生，也不在本
  artifact 中预判或处置。

## Completion 与下一入口

S3/F03 resumed implementation、owner tests、coverage、focused/full pyright、diff、
allowlist 与 frozen registry 检查均完成。工作树保持未 staged；未 commit、push 或操作
PR。按总控 follow-up 在此停止，下一合法入口是总控另行派发的 MiMo/DS 两路独立
code review。
