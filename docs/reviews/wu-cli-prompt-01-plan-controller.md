# WU-CLI-PROMPT-01 Implementation Plan

## Gate

- Work Unit：`WU-CLI-PROMPT-01`
- gate：`plan`
- decision：`pass`
- prerequisite：`goal confirmation pass`
- accepted review：`docs/reviews/plan-review-20260731-182140.md`
- next entry point：`implementation S1`

## Goal / Motivation / Success Signal

在不修改冻结 oracle/scenario expected behavior、不改 Host canonical cancellation owner、
不扩张到其它产品语义的前提下，使现有 CLI prompt 实现符合六项已确认 contract：取消 UI
不泄漏内部 reason；重复 Ctrl+C 必须等待 Host terminal；启动期 Ctrl+C 稳定退出 130；公共
日志 selector/debug-stream contract 完整；缺失日志父目录为资源失败 1；非法 UTF-8 argv
在 CLI 输入边界以 usage 2 拒绝且无 primary-operation 副作用。

完成信号：六项 frozen correctness surfaces 全部通过；取消场景不存在 running Run/attempt，
存在 canonical cancelled terminal；parser misuse、resource failure、interrupt 分别稳定为
2/1/130；完整 pyright 为 0 errors；`git diff --check` 通过；README 触发检查完成。

## Non-goals / Scope Boundary

- 不修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 的 expected behavior。
- 不修改 Host watchdog reason、Run/Attempt/EventLog terminal producer、事务或 recovery 语义。
- 不通过 sleep、SQLite 补写、CLI 假终态、reason blacklist 或宽松编码修复。
- 不改变 Engine `force_answer tools=()`、Host frozen Tool Trace schema snapshot 或 resolved
  credential persistence。
- 不新增 process、interactive、context compaction 产品行为。共享 owner 改动只做必要回归；
  interactive 的既有二次中断本地退出 contract 保持不变。
- 不新增 migration、文件系统竞态/回滚、兼容 shim、抽象 registry 或通用 signal framework。

## Design / Architecture Alignment

- `UI -> Service -> Host -> Engine` 保持不变。
- CLI argv、bootstrap、输出目的地与用户文案属于 UI/process adapter owner。
- `dayu.runtime` 继续只承载层中立日志能力，不 import CLI/Service/Host/Engine/Fins。
- Host 继续是 accepted Run cancellation、Run/Attempt terminal truth 与 durable EventLog 的唯一
  owner；CLI 只发 typed graceful cancel 并等待 public terminal observation。
- Service terminal DTO 保持 typed 透传，不在 Service 重写 UI 文案或重算日志语义。

## First-principles Judgment / Direct Evidence

- `dayu/cli/output.py::_public_cancel_message` 对非 `cli_sigint` reason 原样返回，直接造成
  watchdog reason 泄漏。
- `dayu/cli/session_execution.py::_cancel_prompt_run_waiting_for_terminal_or_second_sigint`
  在第二次 SIGINT 后取消 `cancel_entrypoint_run_and_wait` task 并返回 `None`；旧测试也固化
  “terminal 前本地退出”。
- `pyproject.toml` 公开 entrypoint 指向重型 `dayu.cli.main:main`；`main.py` 的 command/runtime
  顶层 imports 位于 `KeyboardInterrupt` 捕获范围外。
- `dayu/cli/arg_parsing.py` 缺少完整公开日志 spelling/shortcuts，selector 不互斥，quiet 被
  写成 error；root/subparser 两个位置使单个 argparse mutually-exclusive group 不足以覆盖
  跨 command 冲突。
- `dayu/runtime/log.py` 把 `debug_stream` 当成唯一 level 的最高优先级，导致它隐式放出普通
  DEBUG/VERBOSE。
- `dayu/cli/main.py::_open_log_file` 把空白 usage 与 `OSError` 都折叠成 `None`/exit 2。
- `parse_cli_args` 未校验 strict UTF-8；surrogateescape 字符先创建 Host Session，随后才在
  durable canonical JSON encoding 失败并 exit 1。

## Contract / Public Interface Decisions

### Terminal cancellation projection

- cancelled terminal UI 只由 typed `HostTerminalStatus.CANCELLED` 投影固定用户文案。
- `cancel_reason` 继续存在于 Service/Host DTO 与 durable evidence，但 UI projection 不读取或
  返回 raw reason。

### Prompt accepted-Run cancellation state machine

```text
RUNNING + first Ctrl+C/Escape
  -> exactly one CancelMode.GRACEFUL request
  -> Host RUN_CANCELLING / watchdog-or-cooperative closeout
  -> Host CANCELLED terminal observation
  -> close caller-local display/key/signal/attachment/log resources
  -> process exit 130

additional Ctrl+C while cancelling
  -> coalesced local intent only
  -> MUST NOT cancel canonical cancel-and-wait task
  -> same terminal/cleanup/exit path
```

- prompt path 不再产生“second SIGINT local exit before terminal” outcome。
- accepted Run 之前的单次本地中断仍不得伪造 Host cancel；本 slice 不发明新的 submission
  rollback/race 语义。

### Startup signal boundary

- `dayu/cli/__main__.py::run_module` 成为公开轻量 bootstrap；同一个受控
  `KeyboardInterrupt -> EXIT_KEYBOARD_INTERRUPT` 边界同时包围 lazy import 与随后完整的
  `dayu.cli.main.main()` 调用。因此它覆盖 import、parser、配置/日志准备、runner startup、
  Host open 与 command-local signal monitor takeover 前的未处理中断，而不只覆盖 import。
- `pyproject.toml` console script 与 `python -m dayu.cli` 都进入同一 `run_module`。
- lazy import 仅用于覆盖 startup signal lifecycle，具有明确边界理由；不引入通用 loader。

### Invocation UTF-8 boundary

- `parse_cli_args` 先把显式 argv 或 `sys.argv[1:]` 物化为 tuple，再逐 token 执行 strict
  UTF-8 encode validation，之后才调用 argparse。
- 任一 token 含 surrogate 时调用 parser error path：静态 ASCII-safe、脱敏错误，exit 2；
  不包含 token、raw byte、`repr` 或底层异常文本。

### Log-file error classification

- `dayu/cli/errors.py` 增加明确的 CLI resource-preparation typed error；它与
  `CliUsageError` 不共享 fallback code。
- `_open_log_file` 对空白路径抛 usage error；对 `open(..., "a", encoding="utf-8")`
  的 `OSError` 抛 resource-preparation error，并保留可行动 path/OS reason。
- `main` 只对这两个 typed class 分别映射 exit 2/1；不做 blanket exception remap，不创建
  parent。

### Logging public selector and runtime admission

- `dayu.runtime.log` 增加 canonical string enum `DiagnosticLogLevel`：
  `debug/verbose/info/warning/error/critical/quiet`。CLI `ParsedCliArgs.log_level` 直接保存该
  typed canonical value。
- `warn` 只在 CLI parser 的公开 spelling map 中映射为
  `DiagnosticLogLevel.WARNING`；不存在第二份 warning 业务事实。
- `dayu.runtime.log.LogLevel` 继续表示 stdlib numeric threshold，但 canonical member 使用
  `WARNING`，并新增由 `dayu/runtime/log_levels.py::QUIET_LOG_LEVEL` 提供的 `QUIET`
  threshold；不保留旧名字 re-export。
- 删除只被 CLI 使用且混合六个 flags 的 `set_level_from_flags`，改为朴素
  `configure_selected_diagnostics(level: DiagnosticLogLevel,
  debug_stream: bool, stream: TextIO | None) -> LogLevel`。该 helper 在 runtime owner 中把
  canonical selection 映射为 numeric ordinary threshold，并调用 `configure`。
- `configure` 新增正交 `debug_stream: bool = False` 参数：debug-stream 开启时 namespace/root
  logger 与自有 handler 的前置 level gate 都设为 `STREAM_DEBUG`，关闭时二者都使用 ordinary
  threshold；随后自有 handler filter 只接受
  `record.levelno == STREAM_DEBUG_LOG_LEVEL`（开关为真时）或
  非 quiet 且 `record.levelno >= ordinary threshold`。因此 info+debug-stream 不放出普通
  DEBUG/VERBOSE，quiet 明确拒绝所有 ordinary record，而不是依赖“高于 critical”的偶然值。
- runtime helper 对 quiet+debug-stream 也 fail closed；CLI parser 更早以 usage 2 拒绝。
- parser 为 root、command、二级 action 三个 argparse scope 分别建立 scope-local typed dest：
  `_root_log_level_selectors`、`_command_log_level_selectors`、
  `_action_log_level_selectors`。`build_parser()` 分别构造三套 common/runtime parent，每套都由
  同一个 module-level option-to-canonical spec 注册公开 selector，但写入本 scope 的 dest；
  `session` 与 `tool_trace` 的二级 parser 必须使用 action-scope parent，而不是再次复用
  command-scope parent。各 scope 内可使用 built-in `append/append_const` 和互斥 group，因为不会
  再假设跨 namespace 共享 dest。parse 完成后，公共 finalizer 合并三份
  `list[DiagnosticLogLevel]`，统一要求总 occurrence count <= 1，再写入 canonical
  `log_level`。每次 `_new_default_namespace()` 都创建三份新 list；parser/action 对象不保存跨
  invocation mutable collector。这样覆盖 command 前后、二级 action 前后、重复同一 selector
  与有序两两冲突，不扫描 raw argv。
- 公开 selector entry 精确为：
  `--log-level` 的八个 spelling（七 canonical + `warn`）以及
  `--debug/--verbose/--info/--warn/--warning/--error/--critical/--quiet` 八个快捷项。
- `--debug-stream` 不进入 selector occurrence list；parse 后单独拒绝 quiet 组合。
  `--log-file` 完全独立。

## Affected Files / Modules

预期生产范围：

- `dayu/cli/output.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/__main__.py`
- `dayu/cli/main.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/errors.py`
- `dayu/runtime/log.py`
- `dayu/runtime/log_levels.py`
- `pyproject.toml`

预期测试范围：

- `tests/cli/test_output.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_public_package_entrypoints.py`
- `tests/runtime/test_log.py`
- 仅当共享入口回归需要时，读取并运行现有 interactive/init/Fins CLI 测试；不为其新增产品
  contract。

文档候选：根 `README.md`、`tests/README.md`。修改前先读取各自更新约束；其它 README
触发条件未命中。

## Implementation Slices

### Slice S1 — Cancelled terminal UI projection

- **Objective**：修复 finding 1，确保任何内部 cancel reason 都不进入用户屏幕。
- **Allowed files**：`dayu/cli/output.py`、`tests/cli/test_output.py`。
- **Exact changes**：移除基于具体 reason 的 UI 分支；prompt/interactive cancelled render 共用
  typed-status-derived固定文案；测试至少传入 `cli_sigint`、watchdog reason、任意未来 internal
  reason 与 `None`，断言 raw reason 均不出现且退出码保持 prompt=130、interactive=0。
- **Non-goals**：不改 DTO、Host reason、EventLog、activity 文案。
- **Validation**：
  `pytest tests/cli/test_output.py`；覆盖率报告中 `dayu/cli/output.py >= 80%`。
- **Completion/stop**：owner contract 通过且无 raw reason 消费；否则停在当前 slice fix loop。

### Slice S2 — Prompt repeated-SIGINT graceful terminal wait

- **Objective**：修复 finding 2，取消 accepted Run 后不允许第二次 SIGINT越过 Host lifecycle。
- **Allowed files**：`dayu/cli/session_execution.py`、`tests/cli/test_prompt_command.py`，必要时
  `tests/cli/test_runtime_display.py` 仅更新同一 prompt caller lifecycle 断言。
- **Prerequisite**：S1 accepted commit。
- **Exact changes**：prompt cancel helper 在发出一次 typed graceful cancel 后无条件 await
  `cancel_entrypoint_run_and_wait` terminal；删除 prompt 的 second-SIGINT competition/local-exit
  分支与不再需要的参数/return semantics；保留 monitor handler 使额外 SIGINT 被合并而不转成
  `KeyboardInterrupt`；cleanup 仍发生在 terminal 之后。
- **Tests**：使用 `asyncio.Event`/fake Host 精确控制：第一次中断后记录一次 cancel；注入第二次
  中断时 task 仍未完成；释放 cancelled terminal 后才返回；断言 terminal、单次 cancel、
  cleanup/cursor 顺序。保留一次 SIGINT、Escape、cancel-terminal race、Run accepted 前 no
  Host cancel 回归；现有 interactive 二次 SIGINT 测试必须不变并通过。
- **Non-goals**：不改 Service/Host cancel implementation，不增加 timeout/sleep，不改变
  interactive state machine。
- **Validation**：
  `pytest tests/cli/test_prompt_command.py tests/cli/test_runtime_display.py
  tests/cli/test_interactive_command.py`；`dayu/cli/session_execution.py >= 80%`。
- **Completion/stop**：第二次 SIGINT不能结束 waiter，terminal 后才清理；否则停在 fix loop。

### Slice S3 — Shared lightweight startup bootstrap

- **Objective**：修复 finding 3 的 import/startup signal gap。
- **Allowed files**：`dayu/cli/__main__.py`、`pyproject.toml`、
  `tests/cli/test_arg_parsing.py`、`tests/cli/test_prompt_command.py`、
  `tests/cli/test_public_package_entrypoints.py`。
- **Prerequisite**：S2 accepted commit。
- **Exact changes**：`run_module` 在 try 内 lazy import `main` 并统一映射
  `KeyboardInterrupt -> 130`；该 try 同时包围完整 `main()` 调用；console script 改指向该
  bootstrap；module invocation 继续复用同一函数。保持 `dayu.cli.main.main` 可直接测试，
  不建立兼容 wrapper API或新的 mutable signal registry。
- **Tests**：单元测试分别在 lazy import、parser/log resource、runtime prepare、Host open、
  Session ensure 与 prompt monitor takeover 前注入 `KeyboardInterrupt`；逐项断言 130、无
  traceback、已建立的 context/resource 精确 close，且无半初始化 Run/attempt/业务状态；正常
  help 仍调用 main；wheel/pyproject entrypoint 精确为新 owner；真实 subprocess 对
  `dayu-cli` 与 `python -m dayu.cli` 注入启动 SIGINT，断言 130、无 traceback/-2，并对
  P47/PC-CN-01..06 核对 filesystem/SQLite before-after。
- **Non-goals**：不移动业务 modules、不建立 plugin loader/signal registry、不新增 Host
  rollback/submission race、不改变命令语义。已经完整原子提交的 durable fact 仍由 Host 拥有；
  本 slice 只保证无半初始化状态与正确 cleanup。
- **Validation**：三个相关测试文件及现有 import-boundary tests。
- **Completion/stop**：两个公开入口覆盖 import 到 command-local monitor takeover 的未处理中断；
  phase-controlled tests 与 frozen timing evidence 均通过。若安装后的 console script 尚未刷新，
  先用 editable reinstall 更新生成入口再验证，不编辑 `.venv` 文件。

### Slice S4 — Invocation UTF-8 and log destination error ownership

- **Objective**：修复 findings 5/6 的 pre-primary 边界与退出码分类。
- **Allowed files**：`dayu/cli/arg_parsing.py`、`dayu/cli/main.py`、
  `dayu/cli/errors.py`、`tests/cli/test_arg_parsing.py`。
- **Prerequisite**：S3 accepted commit。
- **Exact changes**：实现 argv tuple materialization + strict UTF-8 validation + static parser
  diagnostic；实现 typed usage/resource log-file failures并在 main 精确映射；不 mkdir。
- **Tests**：surrogate 位于 command、option value、positional 三类；stderr strict UTF-8、脱敏、
  无 traceback；main 下默认/显式 log open、runtime configure、runner 均零调用；bytes argv
  真实 subprocess；missing parent exit 1 且 parent/target 不存在、runner/Host 状态零调用；
  空白 path 仍 exit 2；已有 parent create/append 成功。
- **Non-goals**：不验证 stdin/env/file/provider encoding，不改 Host codec，不新增 rollback/race。
- **Validation**：`pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py`；
  `arg_parsing.py/main.py/errors.py` 各自 coverage >=80%。
- **Completion/stop**：PC-BD-03/P62 owner-level evidence齐备且 pre-primary zero-call；否则停在
  fix loop。

### Slice S5 — Complete logging selector and debug-stream contract

- **Objective**：修复 finding 4 的 shared parser/config/runtime behavior。
- **Allowed files**：`dayu/cli/arg_parsing.py`、`dayu/cli/main.py`、
  `dayu/runtime/log.py`、`dayu/runtime/log_levels.py`、
  `tests/cli/test_arg_parsing.py`、`tests/runtime/test_log.py`；若真实调用签名变化触及 Fins CLI
  assertions，仅更新对应 `tests/cli/test_fins_commands.py` 断言，不改 Fins production。
- **Prerequisite**：S4 accepted commit。
- **Exact changes**：按上方 public selector/runtime admission 决策实现；删除旧 priority helper与
  反向固化测试；main 只传 canonical level + debug_stream + stream。重构 `build_parser()` 的
  parent assembly，使 root/command/action scope 使用不同 selector dest、相同 option spec；除
  selector occurrence 外的公共参数与现有 command 前后/二级 action位置语义保持不变。
- **Tests**：
  - 16 个 selector entry 全量 canonical normalization；
  - 16×16=256 个有序冲突（含相同 entry 重复）全部 exit 2、primary operation零调用；另外
    覆盖 selector 分处 root/command 两层的两个顺序，以及 `session resume` root/command/action
    三层任意两层，证明 occurrence 不在 namespace merge 时丢失；复用同一个 parser 连续解析
    两次并传入 fresh namespace，证明 occurrence 不跨 invocation 泄漏；
  - debug-stream standalone 与 14 个非 quiet selector entry 合法且普通 level 不变；
  - quiet 两种 entry与 debug-stream 两种顺序全部 exit 2；
  - log-file 与所有合法组合独立；
  - runtime 对每个 ordinary threshold 验证普通 records，与 exact STREAM_DEBUG admission；特别
    断言 info+stream 不输出 DEBUG/VERBOSE、quiet 不输出 CRITICAL、quiet+stream fail closed；
  - cleanup 恢复 stderr 时保留同一 canonical level/debug-stream facts。
- **Non-goals**：不改变业务 logging call sites、不增加多个 logger namespace、不用 argv string
  scan 或 prompt-only shim。
- **Validation**：`pytest tests/cli/test_arg_parsing.py tests/runtime/test_log.py
  tests/cli/test_fins_commands.py`；`runtime/log.py`、`runtime/log_levels.py` coverage >=80%。
- **Completion/stop**：全部 grammar/config/admission matrix 通过；否则停在 fix loop。

### Slice S6 — README contract synchronization

- **Objective**：执行已触发的文档更新，不把旧公开日志/取消测试语义留在用户手册或测试手册。
- **Allowed files**：`README.md`、`tests/README.md`。
- **Prerequisite**：S5 accepted commit，且先完整读取两个 README 内的 Agent 更新约束。
- **Exact changes**：根 README 只更新七个 canonical levels、`warn` spelling、八个快捷项、
  selector 互斥、debug-stream 正交/quiet 冲突、log-file parent 需预建；tests README 更新
  bootstrap SIGINT、prompt terminal-wait、UTF-8、typed resource error、parser/runtime matrix 与
  新 runtime helper。不得写 work-unit、内部 reason 或 Host 实现细节。
- **Validation**：`rg` 确认旧的 debug-stream“同时打开普通 DEBUG”、旧
  `set_level_from_flags` 与 prompt second-SIGINT terminal 前本地退出描述已消失；README 示例
  argv 可由 parser 接受。
- **Non-goals**：不扩写 Host/Engine/config/分层文档，不记录暂未实现行为。
- **Completion/stop**：README 与 accepted code/tests 同源；否则停在 docs fix loop。

## Review / Commit Sequence

严格按 Gateflow：每个 slice 都执行
`implementation -> deepreview code review -> fix -> re-review -> accepted slice commit`，commit
message 分别为：

- `gateflow: accept WU-CLI-PROMPT-01 S1`
- `gateflow: accept WU-CLI-PROMPT-01 S2`
- `gateflow: accept WU-CLI-PROMPT-01 S3`
- `gateflow: accept WU-CLI-PROMPT-01 S4`
- `gateflow: accept WU-CLI-PROMPT-01 S5`
- `gateflow: accept WU-CLI-PROMPT-01 S6`

plan review loop 通过后先创建
`gateflow: accept plan for WU-CLI-PROMPT-01`。所有 slice 完成后执行 aggregate deepreview、
fix/re-review 与 `gateflow: accept deepreview for WU-CLI-PROMPT-01`。

## Final Validation

所有命令均先 `source .venv/bin/activate`：

1. 运行所有受影响 unit/integration tests，以及共享 CLI 入口回归。
2. 生成 per-file coverage report，所有新增/修改生产 Python 文件目标 >=80%。
3. 用 `workspace/tmp/` 下临时 harness 从冻结 registry 读取 exact argv/key timing，至少重跑：
   - cancellation/UI：P44、P45、P46、PC-BD-02、PC-CN-07；
   - startup：P47、PC-CN-01..06；
   - logging：PC-LS 32、PC-DS 15、PC-DQ 4、PC-LC 256；
   - resource/encoding：P62、PC-BD-03。
4. 每条真实 scenario 核对 screen、exit、filesystem before/after、Host/runtime SQLite、EventLog/
   Tool Trace、Run/attempt terminal state；合法 provider场景保留真实调用证据。
5. 对 `dayu-cli` entrypoint 做 editable reinstall 后再跑 startup timing，确保不是旧 console
   launcher。
6. 运行完整 `pyright`，要求 0 errors。
7. 运行 `git diff --check`。
8. 确认 frozen oracle/scenario 文件 content digest 未变化；post-fix evidence 只写新 evidence
   bundle/artifact，不改 expected registry。

## Docs Decision

- 根 `README.md`：需要更新。用户可见日志 spelling、互斥、debug-stream 正交、quiet 冲突、
  log-file parent 预建要求发生修正。
- `tests/README.md`：需要更新测试矩阵与真实 scenario evidence 说明。
- `dayu/README.md`、`dayu/host/README.md`、`dayu/engine/README.md`、
  `dayu/config/README.md`：分层、Host/Engine/config contract 未改变，不更新。

## Risks / Open Questions

- argparse root/subparser 的 namespace merge 是主要实现风险；必须用三份 scope-local typed
  occurrence facts、parse 后合并与跨位置/连续调用矩阵证明，不能使用跨 scope 同 dest 或仅依赖
  单 scope mutually-exclusive group。
- debug-stream filter 必须同时降低 namespace logger gate 并在 handler 精确过滤；只改 handler
  level 会让 stream record 在 logger 处丢失，只降 logger 又会泄漏普通 DEBUG。
- startup subprocess timing 可能受旧 editable console launcher 影响；验证前必须刷新安装并记录
  exact executable/argv。
- 真实 provider availability 是外部 residual risk；transport/provider failure 不能替代
  parser/cancellation/state evidence，也不能通过改 oracle 消除。
- Blocking open questions：None。

所有 residual risk 已分别由当前 approved slice 或 final validation 覆盖；没有未分类风险。

## Why This Is Not Overdesigned

方案只在已有 owner 上修正七个事实：一个 UI projection、一个 prompt cancellation branch、一个
轻量 bootstrap、一个 argv validator、一个 typed resource error、一个 selector occurrence list、
一个 runtime handler filter。没有新增业务层、数据库 schema、migration、signal framework、logger
registry、transaction 或 compatibility layer；六个 slice 仅按独立 owner/reviewability 与必要
文档同步拆分。

## Completion Report Format

最终报告逐 finding 列出：root cause/owner、修改文件、owner-level tests、真实 frozen scenarios、
修复前后 screen/exit/filesystem/SQLite/EventLog/Tool Trace/terminal state 差异、remaining risk 与
owner；另列完整 pyright、coverage、`git diff --check`、docs 更新、commit 与 draft PR URL。
