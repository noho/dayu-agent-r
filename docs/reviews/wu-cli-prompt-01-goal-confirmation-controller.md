# WU-CLI-PROMPT-01 Goal Confirmation

## Gate

- Work Unit：`WU-CLI-PROMPT-01`
- 类型：六项已确认 CLI prompt implementation findings 的 production bug fix / public-contract change
- gate：`goal confirmation`
- decision：`pass`
- 用户确认：2026-07-31
- next entry point：`plan`

## Preflight

- 当前分支：`codex/prompt-oracle-adjudication`。
- 工作树在调查开始时为 clean。
- 当前分支不是受保护分支；未发现其它 work unit 的未提交改动或 ownership 冲突。
- 本 gate 只读取需求、冻结 oracle/scenarios、Host 设计、生产代码与现有测试；除本
  goal-confirmation artifact 外未修改生产代码、测试或冻结 registry。

## 已读取真源

- `AGENTS.md`
- `docs/cli_ci.md`
- `docs/cli_ci_oracles.json` 中 `cli.prompt.core-execution@1`
- `docs/cli_ci_scenarios.json` 中全部 400 条 `command=prompt` accepted scenarios
- `docs/host/design.md`

冻结前提保持不变：不改 oracle/scenario expected behavior；init、process、interactive、
context compaction 不主动扩入；Host SQLite resolved credential 明文与 Engine
`force_answer tools=()` / Host frozen Tool Trace schema snapshot 均不是本 Work Unit 的 bug。

## 第一性原理判断

目标成立，六项严重性均未被高估。冻结场景已经提供实现级反例，而生产代码存在与反例
同源的直接控制流：内部 reason 被 UI 原样投影；第二次 SIGINT 主动取消 canonical cancel
waiter；公开 console entrypoint 在捕获边界外加载完整 runtime；日志 argv grammar 与 runtime
admission 把不同事实混为一个 level；日志路径格式错误与资源打开失败被折叠为同一个
`None`；POSIX surrogateescape 参数未在 parser 前被拒绝。

这些问题不能通过修改 Host durable reason、下游补写 SQLite、CLI 假终态、字符串黑名单、
sleep、宽松编码或测试 fixture 修复。正确路径是在各自唯一 owner boundary 恢复冻结 contract，
并让共享入口的消费者复用同一个事实。

## Finding 1：cancel closeout reason UI leak

### Root cause 与 owner

- Host `dayu/host/durable/run_transition.py` 正确持久化 typed watchdog closeout reason 与
  `RUN_CANCELLED`；这是 durable lifecycle owner，不应修改。
- `dayu/cli/output.py::_public_cancel_message(...)` 只特判 `cli_sigint`，随后把其它
  `cancel_reason` 原样返回。内部 reason 因而跨过 CLI terminal UI projection boundary。
- 唯一修复 owner 是 `dayu/cli/output.py` 的公共取消终态投影。用户文案应由 typed
  `HostTerminalStatus.CANCELLED` 派生，不能由 raw reason code 派生或维护黑名单。

### 成功信号

- prompt、interactive 与 `session resume --mode prompt` 的 cancelled terminal 只显示用户
  可理解的取消/清理状态。
- durable EventLog、Host diagnostics 与内部 trace 继续保留 typed reason。
- `P44`、`P45`、`PC-CN-07` 的 screen evidence 不含 reason code、watchdog、closeout 或状态机
  标识。

## Finding 2：repeated Ctrl+C not graceful

### Root cause 与 owner

- `dayu/cli/session_execution.py::_cancel_prompt_run_waiting_for_terminal_or_second_sigint(...)`
  把第二次 SIGINT 实现为本地退出竞争者；竞争获胜时取消
  `cancel_entrypoint_run_and_wait(...)` task 并返回 `None`。
- `execute_prompt_on_session(...)` 又把 `None` 直接映射为 130，因此进程可在 Host 提交
  cancellation 或写入 canonical terminal fact 前关闭。
- Service 的 `cancel_entrypoint_run_and_wait(...)` 与 Host watchdog 已拥有正确的 cancel +
  terminal observation / closeout 语义。唯一修复 owner 是 prompt accepted-Run 的 CLI 本地
  中断编排；第二次中断不得终止该 canonical waiter。

### 成功信号

- 第一次 Ctrl+C 或 Escape 只发起一次幂等 graceful Host cancel；后续 Ctrl+C 合并为同一
  退出意图。
- CLI 取得 Host cancelled terminal 后才关闭 caller-local 资源并退出 130。
- `P46` 与 `PC-BD-02` 均为 exit 130，Run/attempt 非 running，存在唯一等价
  `RUN_CANCELLED` canonical terminal fact；`P44`、`P45`、`PC-CN-07` 保持回归通过。
- 不改变 interactive 自身的二次中断产品语义；若实现抽取共享 helper，则同步验证
  interactive。

## Finding 3：startup Ctrl+C traceback / signal exit

### Root cause 与 owner

- `pyproject.toml` 的 console script 直接指向 `dayu.cli.main:main`；`dayu/cli/main.py` 在
  `main()` 的 `KeyboardInterrupt -> 130` 边界建立前，模块顶层已加载 parser、全部 commands、
  Service、Host、Engine/Fins 依赖链。
- `python -m dayu.cli` 的 `dayu/cli/__main__.py` 也先 eager import 同一重型模块。
- 唯一修复 owner 是公共 CLI process bootstrap / startup signal lifecycle，不是 prompt
  command。公开 console command 与 module entry 必须复用轻量、受控的顶层中断边界，再在
  边界内加载 runtime。

### 成功信号

- `P47`、`PC-CN-01` 至 `PC-CN-06` 的精确启动时序稳定 exit 130，不出现 `-2`、traceback
  或裸 `KeyboardInterrupt`。
- Run 创建前的中断不遗留半初始化 Session、Run、attempt 或其它业务状态；尚未 accepted
  Run 时不伪造 Host cancel。冻结启动场景若信号发生在任何业务提交前，则 Host SQLite
  不新增业务记录或 provider 调用。
- 公共入口变更不改变 help/parser、init 与其它命令的业务语义。

## Finding 4：logging selector / debug-stream contract

### Root cause 与 owner

- argv grammar、公开 spelling、selector 互斥与归一 owner 是
  `dayu/cli/arg_parsing.py`。当前缺少 `warning`/`quiet` 的 `--log-level` choice 与
  `--warn`、`--warning`、`--error`、`--critical` 快捷项；selector 未处于同一互斥 contract，
  `--quiet` 还被归一为 `error`。
- effective ordinary level 与 stream diagnostic admission owner 是
  `dayu/runtime/log.py`。当前 `debug_stream` 直接把唯一 logger threshold 改为
  `STREAM_DEBUG`，从而同时放出普通 DEBUG，违反“正交且不改变普通等级”。
- `dayu/cli/main.py` 只是两个 typed facts 的组合调用者，不应自行重算语义。

### 成功信号

- 七个 canonical level 与 `warn` spelling 形成 16 个公开 selector entry；全部 selector
  在 command 前后位置、重复与有序两两组合中都互斥并于 primary operation 前 exit 2。
- `warn` 与 `warning` 都归一为 canonical warning；quiet 是关闭 ordinary diagnostics 的
  policy，不再伪装为 error。
- `--debug-stream` 独立于 selector，不改变 ordinary threshold；仅放行 exact stream-debug
  diagnostics，可与全部非 quiet selector 组合，与 quiet 两种顺序均 exit 2。
- `--log-file` 与任意合法组合独立。
- 重跑冻结 `PC-LS` 32 条、`PC-DS` 15 条、`PC-DQ` 4 条、`PC-LC` 256 条，共 307 条日志场景。

## Finding 5：log-file missing parent exit code

### Root cause 与 owner

- `dayu/cli/main.py::_open_log_file(...)` 把空白路径格式错误与任意 `OSError` 都折叠为
  `None`，调用边界再统一返回 usage exit 2。
- 唯一 owner 是 CLI process-level 输出目的地准备与紧邻错误分类：空白 invocation 仍是
  usage 2；合法路径的资源打开失败是 runtime resource failure 1。

### 成功信号

- `P62` 精确 exit 1，stderr 给出明确可行动错误。
- 缺失 parent 不被创建，目标 log 不被创建；runner、runtime log configure、Session、Run、
  provider 与 Host 业务状态均未进入。
- 已存在 parent 的 create/append 行为与空白路径 exit 2 保持正确。

## Finding 6：invalid UTF-8 owner / exit code

### Root cause 与 owner

- POSIX 将非法 raw argv byte 通过 surrogateescape 暂存为 surrogate 字符；当前
  `dayu/cli/arg_parsing.py::parse_cli_args(...)` 未在 `argparse` 前验证 effective argv 的
  strict UTF-8 可编码性。
- surrogate 因而进入 prompt runtime、Host Session 创建与 canonical JSON digest，最终在
  Host durable codec 才触发 `UnicodeEncodeError`，被 prompt 当作 runtime failure 1。
- 唯一 owner 是公共 `parse_cli_args(...)` invocation text boundary；Service、Host、Engine、
  digest codec 与 prompt-only command 都不拥有 POSIX argv 编码语义。

### 成功信号

- 所有 argv token 在 parser 前执行 strict UTF-8 validation；任何 surrogate 均走固定、
  脱敏、ASCII-safe 的 parser error，exit 2。
- 错误不回显原 token/raw byte/异常，不出现 traceback 或二次 `UnicodeEncodeError`。
- `PC-BD-03` 的 filesystem、Host/runtime SQLite、Session、Run、attempt、EventLog、Tool Trace
  与 provider evidence 均无 primary-operation side effect。
- 合法中文 argv、help、未知参数和各 command parser smoke 保持回归通过。

## 实现范围

预期 owner 范围：

- `dayu/cli/output.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/__main__.py`
- `dayu/cli/main.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/errors.py`（仅在需要 typed 错误分类时）
- `dayu/runtime/log.py` 与必要的层中立日志级别 contract
- `pyproject.toml`（公开 entrypoint 若需指向轻量 bootstrap）
- 对应 `tests/cli/`、`tests/runtime/` 测试
- 按触发规则核对并按需更新根 `README.md` 与 `tests/README.md`

Host durable cancel producer、Service terminal DTO 透传、Engine、provider、Fins storage 与冻结
oracle/scenario registry 不在修改范围。

## 非目标

- 修改 frozen oracle/scenario expected behavior，或用新 expected 迁就实现。
- 修改 Host watchdog reason、canonical cancel state machine、EventLog terminal producer 或用
  下游 SQLite 补写终态。
- 修改 Engine `force_answer tools=()`、Host public Tool Trace frozen schema snapshot 或
  resolved credential persistence。
- 为 process、interactive、context compaction 新增产品语义；共享 owner 改动只做必要回归。
- 新增文件系统竞态、事务回滚、migration、兼容 shim、loose encoding 或 reason blacklist。

## 总体验收信号

- 六项 frozen correctness surfaces 全部通过现有 oracle/scenarios。
- 真实取消场景退出时不存在 running Run/attempt，并有 canonical cancelled terminal。
- parser misuse 始终 exit 2 且 primary operation 零调用；资源准备失败 exit 1；用户中断
  exit 130。
- 受影响单元/集成测试、真实 CLI scenario evidence、完整 pyright、`git diff --check` 全部
  通过；README 触发检查完成。
- 冻结 registry 不修改；如记录 post-fix evidence，只绑定新 evidence/digest。

## Blocking Open Questions

None。

## Completion

用户已确认本目标、owner 边界、非目标与成功信号。`goal confirmation` gate 通过；下一未
完成 gate 为 `plan`。
