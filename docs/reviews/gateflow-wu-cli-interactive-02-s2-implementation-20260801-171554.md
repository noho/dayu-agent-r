# Gateflow S2 implementation — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：`implementation`
- Slice：`S2`，仅 F05-F09
- S2 授权起点 / 当前基线：`d210444f`
- Accepted plan commit（plan artifact 元数据）：`34127db4`
- Accepted plan：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` §6.1-§6.9
- Branch：`codex/interactive-oracle`
- 状态：S2 implementation 完成，停在 `implementation review` 前
- 本次未执行 review、S3-S6、commit、push 或 PR 操作。

## Preflight 与 scope

实施前完整读取了根 `AGENTS.md`、accepted plan §6.1-§6.9、冻结 controller、S1
implementation/review/adjudication/fix/re-review artifacts，以及 composer、interactive command、
session execution、run keys、Service acceptance/cancel public helper 和七个 §6.1 allowed test owner。
直接代码证据确认根因成立：旧 interactive 在输入态和 Run 中分别由 composer 与
`RunningKeyMonitor` 读取 stdin，non-TTY 又按行循环，导致 ESC prefix 误取消、type-ahead
丢失和 pipe 换行误分帧。没有发现 blocking plan contradiction。

本次只修改以下 §6.1 allowed files，并新增本 collision-safe artifact。

### Modified production files

- `dayu/cli/composer.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/run_keys.py`

### Modified owner tests

- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

`dayu/cli/agent_entrypoint.py` 的现有计数通知已足够；其余三个 allowed test owner 无需修改。
未修改 registry、oracle、README、design、冻结 artifact 或其它生产模块。

## Contract implemented

### F05 — exact Shift+Enter

- composer 定义命名常量 `XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER`，`c-m` 只在单个
  `KeyPress` 的 raw data 完整等于 `\x1b[27;2;13~` 时插入 LF。
- Ctrl+J 保持插入 LF；普通 CR/Enter 提交；不修改 prompt_toolkit 全局 ANSI 表，也不猜测
  未知 CSI-u。
- 完整 CSI、Alt、bracketed paste 继续进入默认 parser/edit 语义，不投影 cancel。

### F06 — non-TTY whole stdin

- non-TTY 使用显式 `BinaryIO` 或已验证的标准 `TextIOWrapper.buffer`，只调用一次
  `read()` 到真实 EOF，不创建 prompt_toolkit session、不输出 `dayu> `、不进入 REPL 循环。
- strict UTF-8 decode；失败只投影稳定的
  `interactive stdin is not valid UTF-8`，不携带原 bytes、codec repr 或 traceback。
- whole batch 依次执行 CRLF→LF、CR→LF、一次 outer trim；内部 Unicode、换行和 literal
  `0x04` 保留。
- blank batch 为 0 Run / exit 0；非空 batch 只提交一个 `QUEUE,target_run_id=None`，等待
  canonical terminal、render、cursor 和 cleanup 后结束。

### F07/F08/F09 — typed TTY lifecycle

- 删除 `InputReaderComposer` 与 interactive `RunningKeyMonitor` seam；TTY invocation 只有一个
  `PromptToolkitInteractiveComposer` stdin owner。`run_keys.py` 明确收窄为 prompt one-shot。
- 新增封闭的 composer phase/event/cancel-source 类型；draft、cursor、history 和输入 revision
  由 composer 独占。只有 REPL 接受 submit 后才清 draft；真实 submit 才写 history。
- standalone Escape 使用 prompt_toolkit 非 eager sequence resolution；active pre-accept、
  provider、tool、closeout/cancelling 均跨 acceptance barrier 合并为 single graceful cancel。
- Ctrl+D 按 phase 分流：idle 空 buffer 为 EOF，idle 非空删除光标下字符，active/cancelling
  一次或连续输入均 no-op。
- composer Ctrl+C 与 OS SIGINT 统一进入 invocation state machine：首次 active 中断只建立
  single cancel intent；第二次只登记 exit-after-cancel；第三次及之后 no-op。用户中断不会
  cancel submit/cancel canonical waiter、强关 Host 或提前关闭 attachment。
- startup reconnect 一次 SIGINT 只取消 caller-local observation，统一 cleanup 后 exit 130，
  不创建 Run。
- active composer 持续接收 Unicode/paste/edit/type-ahead；第一份非空 Enter 只建立 sole
  `QUEUE,target=None`，第二份 draft 原样保留并给出有界提示，绝不 STEER。
- current terminal 固定先 finish display、render、advance cursor，再提升已存在 sole queued
  task。terminal/composer 同批完成使用 terminal-first 与 generation 去重；stale cancel/toggle
  丢弃，不重复 submit/cancel。
- exit-after-cancel 停止新输入但不取消 sole queued submit；当前 cancel terminal 收口后，已
  durable accepted 的 queued Run 复用原 waiter、恰好执行一次并等待 terminal 后才 exit 130。

## Owner tests 与 smoke

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Focused S2 owner matrix

```text
pytest tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py tests/cli/test_run_keys.py \
  tests/cli/test_runtime_display.py tests/cli/test_interactive_run_view.py \
  tests/cli/test_session_command.py \
  tests/service/test_entrypoint_runtime_interactive_path.py -q -x
```

结果：`141 passed, 3 warnings`。warnings 均来自 edgartools deprecated module。

矩阵包含：typed event 构造约束、Ctrl+J/exact Shift+Enter/ordinary Enter、CSI/Alt/paste、
standalone Escape timeout、Ctrl+D/Ctrl+C phase matrix、draft/cursor/history、editor error
脱敏、pipe 全矩阵、invalid UTF-8、Escape/Ctrl+C active stages、OS SIGINT 三阶段、type-ahead、
sole QUEUE、terminal/Enter 双序、exit-after-cancel queued acceptance 前后和 startup SIGINT。
另有 cancel waiter 先失败的确定性反例，证明该 owner 立即传播 primary error，不会永久等待
submit terminal。

### Integration / POSIX smoke 与 affected regression

- `tests/service/test_entrypoint_runtime_interactive_path.py` 走真实
  `CLI -> Service -> Host -> Engine worker request`，验证 interactive 继续复用 public
  `QUEUE,target=None` contract；没有改 Service 语义。
- `test_real_posix_pty_exact_sequences_and_terminal_mode_restore` 在当前 Darwin/POSIX 真实 PTY
  写入 Shift+Enter、Up CSI、Alt、bracketed paste 与 standalone Escape exact bytes，并验证
  draft 及 ECHO/ICANON/ISIG/IEXTEN 恢复；该用例本机实际执行通过，未被 skip。
- 扩大到完整 CLI affected regression：

```text
coverage run --branch -m pytest tests/cli \
  tests/service/test_entrypoint_runtime_interactive_path.py -q
```

结果：`1113 passed, 7 skipped, 3 warnings`。7 个 skip 是既有平台/capability 条件；没有新增
S2 contract skip。

## Static、type、coverage 与 safety validation

### Type / lint / format / diff

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `python -m compileall -q dayu/cli tests/cli tests/service/test_entrypoint_runtime_interactive_path.py`：通过。
- `ruff check` 对四个 production 与四个 modified owner test：`All checks passed!`。
- `ruff format --check` 对相同文件：`8 files already formatted`。
- `git diff --check`：通过。
- artifact 写入前 `git diff --name-only` 精确只有上述八个 allowed code/test 文件。

### Per-file branch coverage

完整 CLI affected regression 的 coverage.py branch report：

| Production file | Coverage |
|---|---:|
| `dayu/cli/commands/interactive.py` | 90% |
| `dayu/cli/composer.py` | 93% |
| `dayu/cli/run_keys.py` | 91% |
| `dayu/cli/session_execution.py` | 84% |

全部 modified production files 均达到 `>=80%`；未添加 pragma、omit 或 coverage exclusion。

### Seam、payload 与 secret checks

- production/test contract scan 对 `InputReaderComposer`、`input_reader`、`_read_user_input`、
  interactive `key_monitor_factory` 零命中；唯一 `RunningKeyMonitor` consumer 位于保持不变的
  prompt one-shot 执行路径。
- 新增 production diff 对 `Any`、`object`、`getattr`、`hasattr` 零命中。
- production 中没有把 raw bytes、draft 或 `user_prompt` 写入 print/log/trace；rejected sole queue
  只输出不含 payload 的固定提示。
- invalid UTF-8 与 editor failure 使用不同 canary payload 验证 stderr 不含 secret、原 bytes、
  exception type 或 traceback。
- 新增 diff 对 AWS access-key、`sk-` token、Authorization Bearer 与长 Bearer token 形态扫描
  零命中；未打印环境变量值，也未调用上传 workspace 内容的工具。

## README / stable artifact decision

本 slice 命中 CLI 行为与测试描述触发，但 accepted plan 将 registry、oracle、README、design
稳定同步冻结到 S6，且本次授权明确禁止进入 S3-S6 或修改这些文件。因此 S2 只新增本
implementation artifact，不机械更新 README，也不把当前测试结果写入冻结 oracle/registry。

## Residual risk

- 当前机器已提供真实 POSIX PTY evidence；真实 Windows console 差异仍由既有 Windows CI
  owner boundary 负责，本地 pipe 测试没有冒充 Windows 实证。
- 未运行真实外部 provider CLI scenario；该证据属于 plan S6，当前 deterministic public-path
  integration 没有被表述为 provider evidence。
- S3-F10、S4-F11/F12、S5-F13 与 S6 registry/docs/oracle/真实 scenario 均未实施、未验证、
  未宣称关闭。
- 尚未执行独立 implementation review；本 artifact 不包含 review 结论。

没有 implementation blocker、unclassified residual risk 或 blocking open question。

## Completion 与 next gate

- Completion status：`S2 implementation complete`。
- F05-F09：实现与本 slice owner evidence 完成。
- Next entry point：`implementation review`。
- 本次按授权停在 review 前；未 commit、push、创建 PR 或进入 S3-S6。
