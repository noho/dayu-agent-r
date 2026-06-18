# WU-CLI-INTERACTIVE-RESUME-01 Plan

Gate: plan
Work unit: WU-CLI-INTERACTIVE-RESUME-01
日期: 2026-06-17
状态: code-generation-ready；未实施

## Goal

对齐 CLI `prompt` / `interactive` 在已有 Session 上启动时的语义边界：

- `prompt` 永远不做离线 terminal / final answer 补读，也不做未完成 Run 的 resume / replay / 接管；即使使用 `prompt --label` 或 `session resume --mode prompt` 也只提交本次新的 prompt。
- `interactive` 的已有 Session 入口必须执行 Host 设计里的 attach / reconnect startup 行为；包括 `interactive --label` 与 `session resume --mode interactive`。
- `prompt` / `interactive` 未带 label 时创建新的 anonymous Session，不存在旧 Session startup 补读。
- 不默认修改 Host / Engine public API；如果实现中发现现有 public API 不足以证明无漏投、无重复或无法定位 selected Session 的未完成 Run，必须停止，交 controller 确认 public API 变更。

成功信号：

- `prompt --label` 和 `session resume --mode prompt` 不读取旧 terminal outbox，不观察旧 active Run，不 replay / retry / resume 旧 Run。
- `interactive --label` 和 `session resume --mode interactive` 在读取第一条用户输入前，先对 selected Session 执行离线 terminal 补读与 active Run 观察；旧 active Run 到达 terminal 后才进入输入态。
- offline 补读不把 Host 内部 id / cursor 当成业务事实展示；只展示 terminal final answer / failure / cancelled / lost 的用户结果。
- Service 仍只通过 Host public API 工作，不读 Host durable internals。

## First-Principles 判断

动机成立。

根因不是 Engine resume/replay 缺失，也不是 prompt 需要补读；根因是 CLI 目前把“选择已有 Session 后提交新输入”和“attach/reconnect 到已有 Session”混在同一 existing-session 执行入口里，但只有提交新输入的 submit/cancel terminal wait helper，没有进入已有 interactive Session 时的 startup attach/reconnect 阶段。

从用户视角，`prompt` 是 one-shot 提交器，若启动时自动补读旧 terminal 或等待旧 active Run，会把“执行这次 prompt”变成“先处理历史状态”，增加非预期输出和阻塞；因此 prompt 不应实现 attach/reconnect startup。`interactive` 是会话型入口，用户明确进入 selected Session，启动时必须先恢复可见性：补读离线 terminal / final answer，并观察已提交但未完成的 active Run，否则用户会在同一会话里继续输入时错过旧回答或把新输入排在未知旧 Run 后面。

当前方案不过度设计：不新增 Host/Engine API，不引入 timeline replay，不重放中间 activity，不做旧 Run retry/replay，不改变 admission / recovery / dispatch。只在 CLI/Service entrypoint 边界补齐已有 Host 设计要求的 attach/reconnect recipe，并新增 CLI 客户端 terminal watermark 状态。

## Direct Evidence

- `docs/host/design.md:953`：`watch_session_events(session_id)` 是 live watch，不接收 cursor，不负责离线补读；Service 取得 Session 后必须把 Outbox terminal 增量补读与 live watch attach 视为同一个 attach / reconnect 协议，并用 `terminal_event_id` / `event_sequence` / `run_id` 去重。
- `docs/host/design.md:1183`：Service 进入 attach / reconnect 流程时，先按客户端保存的 terminal watermark / seen ids 补读 Outbox terminal 增量，再进入或保持 session live watch。
- `docs/host/design.md:1818`、`docs/host/design.md:1825`：离线期间错过的 terminal / final answer 通知通过 Outbox terminal watermark / seen terminal ids 补读；业务语义上先补离线 terminal，再接入 live watch，必须证明两步之间没有漏投 terminal 窗口。
- `docs/host/design.md:3397`-`3431`：已 accepted prompt 的恢复语义由 Host startup recovery 负责；旧 Attempt 不恢复，最终 answer 可通过 Host event stream / read model / Outbox 可见。
- `dayu/cli/commands/prompt.py:301`-`328`：`prompt --label` 当前通过 `ensure_session` 选择 slot Session；无 label 时 `create_session` 创建 anonymous Session。
- `dayu/cli/commands/prompt.py:252`-`282`：prompt existing-session 入口直接提交本次 turn 并渲染 terminal，没有 startup attach/reconnect 阶段。
- `dayu/cli/commands/interactive.py:355`-`382`：`interactive --label` 当前通过 `ensure_session` 选择 slot Session；无 label 时创建 anonymous Session。
- `dayu/cli/commands/interactive.py:300`-`336`、`385`-`445`：interactive existing-session 入口直接进入 REPL，读取用户输入后才 submit，没有进入输入态前的 Session startup attach/reconnect。
- `dayu/cli/commands/session.py:235`-`289`：`session resume --mode prompt` 和 `--mode interactive` 都路由到 prompt / interactive existing-session 窄入口。
- `dayu/service/entrypoint_runtime.py:513`-`578`：submit helper 在 submit 前 attach watcher，只处理本次 accepted Run terminal；`allow_outbox_terminal_fallback=False`，不做旧 Session startup。
- `dayu/service/entrypoint_runtime.py:580`-`648`：cancel helper 可在已终态时用 public outbox fallback；这是单个 Run cancel path，不是 Session startup。
- `dayu/host/api.py:2164`-`2183`、`2200`-`2224`：`SessionSnapshot` / `SessionListItem` 已暴露 `active_run_id` 和 `queued_run_ids`，可在现有 public API 内发现 selected Session 当前 active Run。
- `dayu/host/api.py:3241`-`3478`：Host Protocol 已有 `get_session`、`list_sessions`、`get_run`、`read_outbox_terminal_items`、`watch_session_events`；无须默认新增 Host API。
- `dayu/host/api.py:2864`-`2891`：Outbox read request 的语义是 caller 提供 `after` cursor 与 `seen_terminal_event_ids`；这要求 CLI 作为客户端保存 terminal watermark，而不是让 Host 猜 UI 状态。
- `dayu/host/api.py:2661`-`2666`、`dayu/host/read_api.py:270`-`279`：Outbox item drain state 不表达 Service / UI / channel 投递成功事实；CLI startup 不应把 Host drain state 伪装成 CLI 已展示状态。
- `tests/cli/test_prompt_command.py:726`-`775` 和 `tests/cli/test_interactive_command.py:626`-`689`：现有 tests 明确 existing-session 入口不会 create / ensure，但也证明它们当前没有 startup attach/reconnect。
- `tests/cli/test_session_command.py:720`-`821`：session resume 目前只解析 existing Session 后调用 prompt / interactive existing-session 执行入口。

## Non-Goals / Scope Boundary

- 不实现 prompt 离线补读、旧 active Run 观察、retry、replay、resume 或 timeline replay。
- 不把 `session resume --mode prompt` 的名字解释为 Host resume / replay；它只是“在 selected Session 上提交一个 prompt follow-up”。
- 不修改 Engine。
- 不修改 Host admission、recovery、dispatch、EventLog、Outbox projection schema 或 public Host Protocol，除非后续实施发现现有 API 无法满足无漏投要求；一旦需要 public API 变更，立即停止。
- 不补读或重放离线期间的中间 activity；startup 只补 terminal / final answer 通知。
- 不为 anonymous fresh Session 做 startup backfill。
- 不新增业务 prompt 文案，不修改 LLM-facing scene prompt。
- 不用 Host durable internals、projection table、timeline internals 或直接 SQLite 查询绕过 public API。

## State Boundaries

### Session Selection

- fresh anonymous prompt: `prompt` 无 `--label`，创建新 Session；startup backfill 不适用。
- label prompt: `prompt --label X`，选择 `cli.prompt.X` Session；仍不执行 startup backfill，只提交本次 prompt。
- session prompt resume: `session resume ... --mode prompt`，先解析 selected Session；仍不执行 startup backfill，只提交本次 prompt。
- fresh anonymous interactive: `interactive` 无 `--label`，创建新 Session；startup backfill 不适用。
- label interactive: `interactive --label X`，选择 `cli.interactive.X` Session；必须执行 startup attach/reconnect。
- session interactive resume: `session resume ... --mode interactive`，先解析 selected Session；必须执行 startup attach/reconnect，不论 selector 是 `--session-id` 还是 `--label/--kind`。

### Startup Attach/Reconnect

对 interactive existing-session only：

1. CLI 从 workspace-local client cursor store 读取 selected `session_id` 的 terminal watermark 与 seen terminal ids。
2. Service 用 `read_outbox_terminal_items(session_id, after=watermark, seen_terminal_event_ids=seen)` 补读 terminal item page。
3. CLI 渲染每个 terminal item，并在渲染成功后更新 client cursor。
4. 若 projection `LAGGED` 且未追平，按 bounded poll 继续读取；`FAILED` 进入 CLI failure。
5. 读取 selected Session snapshot 的 `active_run_id`。
6. 若无 active Run，进入 REPL 输入态。
7. 若有 active Run，打开 live watcher 并以 outbox fallback 观察该 Run terminal；运行中 activity 可复用现有 activity renderer。
8. active Run terminal 渲染成功后更新 client cursor，再重新读取 Session snapshot；若 Host 因 queued promotion 产生新的 active Run，继续观察；否则进入 REPL 输入态。

### Terminal Cursor Store

新增 CLI-local client state，而不是 Host truth：

- 建议文件：`<workspace_root>/workspace/.dayu/cli/terminal_cursors.json`。
- key: Host `session_id`。
- value: `last_seen_terminal_event_sequence: int`，`seen_terminal_event_ids: tuple[str, ...]`。
- seen ids 只保留有限窗口，例如最近 100 个 terminal ids，用于 overlap 去重；窗口常量必须命名。
- 写入使用原子 replace；多进程并发使用 `dayu.runtime.filelock` 或等价已存在 runtime file lock wrapper。
- 文件损坏、JSON 非对象、字段非法时 fail fast 为 CLI usage/runtime error，不静默重置，避免重复或漏投被掩盖。
- 该状态只表达本 CLI 客户端已展示 terminal 通知，不是业务事实，不进入 LLM prompt，不进入 Host context。

### Active Run Semantics

- `RunStatus.SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST` 是 terminal。
- `ACCEPTED` / `QUEUED` / `RUNNING` / `WAITING` / `CANCELLING` / `RECOVERING` 都视为未终态。
- Startup 观察目标来自 selected Session 的 `active_run_id`；queued ids 不直接等待。观察一个 active terminal 后必须重新读取 Session snapshot，以覆盖 Host queue promotion 后的新 active Run。
- 如果 session snapshot 只有 `queued_run_ids` 且无 `active_run_id`，当前 plan 不直接等待 queued Run；这应作为 residual risk 记录，除非实施时已有 Host 行为能证明 queued 会被 promotion 成 active。

## Affected Files / Modules

预计修改：

- `dayu/service/entrypoint_runtime.py`
  - 新增 Session startup reconnect helper 与 typed request/result。
  - 复用现有 `_wait_for_terminal`、outbox terminal mapping、watcher drain、activity projection、poll interval 校验。
- `dayu/cli/commands/interactive.py`
  - 在 `_execute_interactive_on_existing_session(...)` 进入 `_run_interactive_repl(...)` 前调用 startup helper。
  - 对 startup active Run 复用运行态 activity renderer、SIGINT / Esc cancel 语义与 terminal renderer。
- `dayu/cli/commands/session.py`
  - `--mode interactive` 路径继续路由 interactive existing-session；无需复制 startup 逻辑。
  - `--mode prompt` 保持不调用 startup helper，并补测试锁定。
- `dayu/cli/commands/prompt.py`
  - 不接入 startup helper。
  - 可在本次 prompt terminal 渲染后更新 CLI cursor，用于避免后续 interactive selected session 重复展示已由 CLI 看过的 terminal；若这被认为越界，则只在 interactive startup/observe 中维护 cursor。
- `dayu/cli/host_context.py`
  - 如需构造 startup reconnect Host context / cursor store id，可增加命名 helper；不得使用魔法字符串散落在命令文件中。
- `dayu/cli/session_terminal_cursor.py` 或同等 CLI 层新模块
  - 管理 CLI terminal cursor store 的读取、校验、原子写入、有限 seen ids。
- `dayu/cli/output.py`
  - 如现有 terminal renderer 只接收 `EntrypointRunTerminalResult`，可新增从 outbox startup item 到统一 terminal result 的转换，优先放在 Service helper；避免在 output 层理解 Host outbox internals。
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_session_command.py`
- `tests/cli/test_session_terminal_cursor.py` 或并入现有 CLI 测试
- `dayu/service/README.md`
- `tests/README.md`
- 视最终边界变化决定是否检查 `dayu/README.md`；若只是 CLI/Service entrypoint helper 行为细化且不改变分层关系，可不更新总览。

不应修改：

- `dayu/engine/**`
- `dayu/host/api.py`、Host command/read/durable/Outbox schema；除非触发 stop condition 并获得 controller 确认。
- `dayu/config/prompts/**`
- `dayu/fins/**`

## Implementation Decisions

### 1. Service helper 只表达 Host public attach/reconnect，不保存 CLI 状态

新增 typed request/result，例如：

```text
EntrypointStartupReconnectRequest
  context: HostCallContext
  session_id: str
  terminal_cursor: OutboxTerminalCursor
  seen_terminal_event_ids: tuple[str, ...]

EntrypointStartupReconnectResult
  terminal_results: tuple[EntrypointRunTerminalResult, ...]
  next_terminal_cursor: OutboxTerminalCursor
  seen_terminal_event_ids: tuple[str, ...]
  active_run_terminal_results: tuple[EntrypointRunTerminalResult, ...]
```

字段名可在实施时按现有风格收敛，但必须避免 `Any` / `object` / 裸 dict。

Service helper 负责：

- page through `read_outbox_terminal_items` until caught up or bounded poll rules require retry；
- convert `OutboxTerminalItem` to `EntrypointRunTerminalResult(source=OUTBOX_READ)`；
- attach `watch_session_events` before observing active Run；
- call existing `_wait_for_terminal(..., allow_outbox_terminal_fallback=True)` for active Run；
- dedupe by `terminal_event_id` / `dedupe_key` / `run_id`；
- return terminal results for CLI rendering。

Service helper 不负责：

- 解析 CLI label；
- 读写 `terminal_cursors.json`；
- 输出 stdout/stderr；
- 安装 signal handler；
- 选择是否对 prompt 启动 backfill。

### 2. CLI cursor store 是 UI client state

CLI 负责把 workspace root 映射到 cursor store path。该模块属于 UI adapter 层：

- 可 import `dayu.runtime.filelock`；不能 import Host durable internals。
- 不把 cursor、event id、digest 或 item id展示给用户。
- 成功渲染 terminal 后再写 cursor；渲染前崩溃允许下次重复展示，优先不漏投。

### 3. Prompt 只保留 submit semantics

`_execute_prompt_on_existing_session(...)` 不调用 startup reconnect helper。新增负向测试：

- `prompt --label` 不调用 `read_outbox_terminal_items` 进行 startup backfill；
- `session resume --mode prompt` 不调用 startup helper；
- 若 selected Session 已有 active Run，prompt 本次 follow-up 仍以 `FollowupBehavior.QUEUE` 提交；不等待旧 active Run terminal。

### 4. Interactive startup 在输入态前运行

`_execute_interactive_on_existing_session(...)` 的顺序变为：

```text
load CLI cursor
run startup reconnect for selected session
render startup terminal results in order
persist cursor after each rendered terminal
if startup active run was terminal/lost/failure: renderer follows existing terminal exit policy
enter _run_interactive_repl(...)
```

建议 terminal exit policy：

- `SUCCEEDED` / `FAILED` / `CANCELLED`：startup 渲染后继续进入输入态，与 interactive 单轮现有语义一致。
- `LOST`：沿用 interactive 现有 fatal policy，返回 failure，不进入输入态。

### 5. Active Run cancel during startup

如果 interactive startup 正在观察旧 active Run，用户按 Ctrl+C / Esc 的语义应与运行态一致：

- 第一次请求 Host `cancel_run(...)`；
- terminal 先到则渲染 terminal；
- 第二次 Ctrl+C 本地退出 130，不改写 Host truth。

实现可复用现有 `_cancel_run_waiting_for_terminal_or_second_sigint(...)`，但应避免把 submit-specific `_AcceptedRunState` 泄漏到 startup path；startup 已有 `active_run_id`。

### 6. Public API stop condition

实施中若发现以下任一条件，停止并请求 controller 确认：

- `SessionSnapshot.active_run_id` 不能稳定表达 selected Session 当前 active Run。
- `read_outbox_terminal_items` 不能用 client watermark / seen ids 完成无漏投补读。
- 为了可靠 startup 必须新增 Host API，例如 pending-only outbox read、session event cursor watch、list runs by session 或 active-run observe helper。
- 需要 Engine 恢复旧 runner/generator/provider request。

## Implementation Slices

### Slice A - Service startup reconnect helper

Objective：提供 reusable Service helper，按 existing Host public API 完成 Session terminal backfill 与 active Run observation。

Allowed files:

- `dayu/service/entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

Exact changes:

- 增加 startup request/result dataclass，字段完整中文 docstring。
- 增加 `startup_reconnect_entrypoint_session(...)` 或同义 public helper。
- 复用 `_new_terminal_observation_state()`，但允许用 caller 提供的 `OutboxTerminalCursor` 和 seen terminal ids 初始化 state。
- 新增私有 helper 将 `OutboxTerminalItem` 转为 `EntrypointRunTerminalResult`。
- 对 projection `FAILED` 抛 `EntrypointRuntimeError`；`LAGGED` 未命中时继续 poll；`CAUGHT_UP` 完成当前 backfill。
- 读取 `host.get_session(session_id)` 获取 active_run_id；若 active Run 存在，attach watcher 后等待该 run terminal；terminal 后循环刷新 session snapshot。

Tests:

- backfill 从 caller cursor 开始读取 outbox pages，返回 terminal results 并推进 next cursor。
- seen terminal ids 被传入 request，重复 terminal 不返回。
- projection lagged 后继续读取，caught up 后停止。
- projection failed 报 Service error。
- active_run_id 存在时 attach watcher 并等待 live terminal。
- active run 已 terminal / watcher miss 时通过 outbox fallback 返回。
- active terminal 后重新读取 session；若新 active 出现继续观察。
- 无 active run 时不 attach active watcher。

Stop condition:

- helper 需要 Host public API 之外的数据才能判断 active Run 或 terminal backfill 完整性。

### Slice B - CLI terminal cursor store

Objective：实现 CLI-local terminal watermark / seen ids 持久化，供 interactive attach/reconnect 使用。

Allowed files:

- `dayu/cli/session_terminal_cursor.py` 或同名 CLI 层模块
- `tests/cli/test_session_terminal_cursor.py`

Exact changes:

- 定义 typed dataclass，例如 `CliTerminalCursorState`。
- 读取 `<workspace_root>/workspace/.dayu/cli/terminal_cursors.json`；目录不存在时创建。
- JSON schema 自足：顶层 object，session id -> object；字段 `last_seen_terminal_event_sequence` int、`seen_terminal_event_ids` list[str]。
- 写入时使用 file lock 与原子 replace。
- 更新时只前进 cursor；低 sequence 不回退；seen ids bounded。

Tests:

- missing file 返回空 cursor。
- update 后可读取。
- 多 terminal 只保留 bounded seen ids。
- corrupt JSON / 非 object / 非法字段 fail fast。
- atomic write 不生成半文件。

Stop condition:

- 如果 workspace `.dayu` state path ownership 需要 product policy 裁决，停止确认路径。

### Slice C - Interactive existing-session startup wiring

Objective：`interactive --label` 与 `session resume --mode interactive` 在输入前执行 startup reconnect。

Allowed files:

- `dayu/cli/commands/interactive.py`
- `dayu/cli/host_context.py` 如需 startup operation context / id helper
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`

Exact changes:

- `_execute_interactive_on_existing_session(...)` 在 `_run_interactive_repl(...)` 前调用 startup helper。
- CLI 从 cursor store 读取 state，传入 Service helper。
- 按返回 terminal results 顺序调用 `render_interactive_terminal_result(...)`。
- terminal 渲染成功后更新 cursor store。
- startup active Run observation 接入 activity renderer 与 cancel handling。
- `LOST` startup terminal 按现有 interactive fatal 退出。

Tests:

- `interactive --label` 在第一条 input 前先 backfill offline final answer。
- `session resume --mode interactive --session-id ...` 在 REPL 前 backfill。
- startup active Run live terminal 被渲染后才读取输入。
- startup active Run cancel 与第二次 SIGINT 语义复用运行态规则。
- startup `FAILED` / `CANCELLED` 渲染后继续读下一条输入。
- startup `LOST` 返回 failure，不读取输入。
- fresh anonymous `interactive` 不读取 cursor、不调用 startup helper。

Stop condition:

- 如果 startup active Run cancel 需要新的 Host cancel mode 或 run ownership API，停止确认。

### Slice D - Prompt negative boundary and optional cursor advancement

Objective：锁定 prompt 不做 startup backfill；如采用统一 CLI cursor，则只在本次 terminal 成功渲染后前进 cursor。

Allowed files:

- `dayu/cli/commands/prompt.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_session_command.py`

Exact changes:

- 不调用 startup reconnect helper。
- 新增测试 fake，若 prompt path 调用 startup helper / outbox startup read 则失败。
- `session resume --mode prompt` 保持只提交本次 prompt。
- 可选：本次 prompt terminal 渲染后更新 cursor store；不读取 cursor，不补读旧 terminal。

Tests:

- `prompt --label` 不 backfill old terminal。
- `session resume --mode prompt` 不 backfill old terminal。
- prompt selected Session 有 active_run_id 时仍只提交 queue follow-up，不主动观察旧 active。
- 若实现 cursor advancement：只记录本次 accepted Run terminal，不读取旧 cursor items。

Stop condition:

- 如果 cursor advancement 被认为改变 prompt 语义，移出本 WU，不阻塞 prompt 负向边界。

### Slice E - Docs sync

Objective：同步已落地的 Service / tests 文档，不机械扩写。

Allowed files:

- `dayu/service/README.md`
- `tests/README.md`
- `dayu/README.md` 仅当实现改变总览级边界时

Exact changes:

- `dayu/service/README.md` 补充 entrypoint runtime 覆盖 attach/reconnect startup helper，但仍不处理 CLI state / stdout / stderr / signal。
- `tests/README.md` 补充 CLI cursor、interactive startup reconnect 与 prompt negative boundary 测试覆盖。
- `dayu/README.md` 只有当总览里 Service entrypoint helper 描述已明显过期时才更新。

## Validation

每次实现后运行：

```bash
source .venv/bin/activate
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py -q
pytest tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py tests/cli/test_session_terminal_cursor.py -q
python -m pyright dayu/service/entrypoint_runtime.py dayu/cli/commands/interactive.py dayu/cli/commands/prompt.py dayu/cli/commands/session.py dayu/cli/host_context.py dayu/cli/session_terminal_cursor.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py tests/cli/test_session_terminal_cursor.py
```

如果没有新增独立 cursor 测试文件，则移除不存在的 test path。若 docs 更新触发总览或 service/test README，追加：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/
```

Expected assertions:

- prompt negative boundary tests 明确证明没有 startup backfill。
- interactive startup tests 明确证明输入态前先补 terminal / 观察 active Run。
- outbox cursor tests 明确证明 watermark / seen ids 按客户端状态推进，不依赖 Host drain state。
- pyright 无新增或扩散错误。

本 plan gate 未运行测试和 pyright，因为本轮只新增计划 artifact，未改生产代码。

## Docs Decision

计划实施后需检查并按职责更新：

- `dayu/service/README.md`：会修改 `dayu/service/entrypoint_runtime.py`，且 README 当前明确描述 entrypoint runtime 能力，需要同步 startup reconnect helper。
- `tests/README.md`：会新增/修改 service 与 CLI 测试覆盖，需要同步测试手册。
- `dayu/README.md`：仅当实现改变总览级 Service entrypoint 描述时更新；当前预判可不改，因为 UI -> Service -> Host 边界不变。

不更新 `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`，除非后续实施越界触发对应目录修改；默认方案不修改这些目录。

## Residual Risks

- CLI cursor store 是新 UI client state；路径、并发和损坏处理必须谨慎。分类：covered by approved Slice B。
- 多 CLI 客户端共享同一 workspace cursor 可能让一个客户端看过的 terminal 对另一个客户端不再 backfill。分类：requires explicit product decision if multi-client per-user notification isolation is required；当前按本机 CLI client 共享 workspace state 处理。
- `queued_run_ids` 无 active_run_id 时是否应阻塞 interactive startup 未完全由当前证据证明。分类：requiring controller decision if tests reveal queued-only Session can persist without promotion。
- Outbox read 不过滤 drained state，不能把 Host drain state当作 CLI unread truth。分类：fixed by current plan via CLI cursor store。
- Startup active Run 长时间 `WAITING` 会让 interactive 入口停在运行态。分类：accepted behavior for selected-session reconnect；用户可通过 cancel 语义退出或取消。
- prompt optional cursor advancement 可能被认为改变 prompt side effect。分类：covered by Slice D stop condition；可移出而不影响核心边界。

## Completion Report Format

实施完成后最终说明必须包含：

- 改了什么：按 Service helper、CLI cursor、interactive wiring、prompt boundary、docs 分组。
- 验证了什么：列出 pytest 与 pyright 命令及结果。
- README 决策：说明更新了哪些 README，哪些检查后未更新。
- 剩余风险：按本 artifact residual risk 分类回报，未关闭项必须有 owner / 后续 work unit。

