# WU-CLI-INTERACTIVE-RESUME-01 修订 Implementation Plan

- Gate: plan-fix
- Work unit: `WU-CLI-INTERACTIVE-RESUME-01`
- 日期: 2026-06-17
- 状态: code-generation-ready；未实施
- 输入 artifact:
  - `docs/reviews/wu-cli-interactive-resume-01-plan-codex-20260617.md`
  - `docs/reviews/plan-review-20260617-183641.md`
  - `docs/reviews/plan-review-20260617-183910.md`
  - `docs/reviews/wu-cli-interactive-resume-01-plan-adjudication-20260617.md`

## 1. Goal / Motivation / Success Signal

目标是修复 CLI `prompt` 与 `interactive` 在已有 Session 上启动时的语义混淆：

- `prompt --label` 与 `session resume --mode prompt` 只提交并展示本次输入对应的 terminal / final answer；不读取旧 cursor、不补读旧 terminal、不等待或重放历史未完成 Run。
- `interactive --label` 与 `session resume --mode interactive` 在读取第一条用户输入前执行 attach / reconnect startup；该 startup 是 pre-input recovery barrier，必须处理 selected Session 已存在的离线 terminal、active Run 与 queued Run。
- 不修改 Host / Engine public API，不新增 Host / Engine public request / response 字段，不读取 Host durable internals；只使用 `get_session`、`watch_session_events`、`read_outbox_terminal_items`、`get_run`、`cancel_run` 等既有 public API。

成功信号：

- interactive existing-session 在进入 REPL 前不会漏投 startup 窗口内的 terminal / final answer。
- session-scoped Outbox backfill 能读取 selected Session 下所有离线 terminal，不按单个 `run_id` 过滤。
- queued-only Session 不被静默忽略：若 bounded promotion wait 后仍只有 queued Run，CLI 结构化启动失败并说明仍有未开始 queued Run。
- prompt startup 语义保持不变，但 prompt 成功展示本次 terminal 后会更新 CLI terminal cursor，避免后续 interactive 重复展示同一 terminal。
- async CLI 路径中的 cursor 文件读写和同步 file lock 通过 `asyncio.to_thread()` 或等价 executor 执行，不阻塞 event loop。
- LAGGED poll 和 queued promotion wait policy 均由调用参数或命名默认常量表达，不在底层 helper 中硬编码。

## 2. First-Principles 判断

动机成立。`prompt` 是 one-shot 提交器，启动时补读旧 terminal 或等待旧 Run 会把“执行本次 prompt”变成“先处理历史状态”，破坏调用者预期。`interactive` 是会话型入口，用户明确进入 selected Session，进入输入态前必须恢复该 Session 的可见性，否则旧 terminal、active Run 或 queued Run 会在用户未知的前提下影响后续输入顺序。

根因不是 Engine resume/replay 缺失，也不是 Host public API 缺失；根因是 CLI existing-session 入口缺少 attach/reconnect startup barrier，且原 plan 对 outbox backfill、live watcher attach、queued-only 状态和 cursor 写入边界定义不够严密。

本方案不过度设计：不引入 timeline replay、run retry/replay、Engine generator 恢复、Host schema 变更或新 public API；只在 Service entrypoint helper 和 CLI adapter 层补齐 Host 设计已要求的 attach/reconnect recipe。

## 3. Direct Evidence

- `docs/host/design.md:953`：`watch_session_events(session_id)` 是 live watch，不接收 cursor，不负责离线补读；Service 必须把 Outbox terminal 增量补读与 live watch attach 作为同一个 attach / reconnect 协议，并用 `terminal_event_id` / `event_sequence` / `run_id` 去重。
- `docs/host/design.md:1183`：Service 取得 Session 后进入 attach / reconnect 流程，必须避免 Outbox drain 与 live watch attach 之间出现漏消息窗口。
- `docs/host/design.md:1818`、`docs/host/design.md:1824`、`docs/host/design.md:1825`：离线 terminal / final answer 通过 Outbox terminal watermark / seen ids 补读；客户端本地保存已展示 terminal watermark；实现可 watcher-first 或 drain-first，但必须证明无漏投。
- `dayu/host/api.py:2165`-`2182`：`SessionSnapshot` 已暴露 `active_run_id` 与 `queued_run_ids`，可用 existing public API 判断 selected Session 当前 pre-input barrier 状态。
- `dayu/host/api.py:2727`-`2889`：`OutboxTerminalCursor`、`OutboxTerminalItem` 与 `ReadOutboxTerminalItemsRequest` 已表达 terminal watermark、terminal identity、session id、run id、terminal status 和 seen terminal ids。
- `dayu/service/entrypoint_runtime.py:1089`-`1148`：现有 `_read_outbox_terminal(...)` 是 run-scoped fallback；它按 `run_id` 匹配，且 CAUGHT_UP 未命中时抛错，不能复用于 session-scoped startup backfill。
- `dayu/service/entrypoint_runtime.py:1152`-`1183`：现有 outbox scan 逻辑会推进 seen ids 和 dedupe keys，但当前 helper 按目标 Run 过滤；startup 需要新 helper 扫描所有 item。
- `dayu/cli/commands/interactive.py:300`-`336`：interactive existing-session 当前直接进入 REPL，缺少输入前 startup attach/reconnect。
- `dayu/cli/commands/prompt.py:252`-`282`：prompt existing-session 当前只提交本次 prompt 并渲染 terminal，符合“无 startup backfill”的目标边界。
- `dayu/cli/commands/session.py:235`-`289`：`session resume --mode prompt` / `--mode interactive` 分别复用 prompt / interactive existing-session 入口，因此修复应落在两条窄入口边界，而不是复制 session 命令逻辑。

## 4. Non-Goals / Scope Boundary

- 不修改 `dayu/engine/**`。
- 不修改 Host public API、Engine public API、Host durable schema、Outbox projection schema、admission、recovery、dispatch 或 EventLog 状态机。
- 不实现旧 Run retry / replay / resume，不恢复旧 Engine runner / provider request。
- 不补读中间 activity 历史；startup 只补读 terminal / final answer，并在线观察 startup 期间已有 active / promoted Run 的 live activity。
- 不为 fresh anonymous `prompt` / `interactive` 执行 startup backfill。
- 不修改 LLM-facing prompt、tool schema、memory / compact / evidence material。
- 不实现多 CLI 客户端 per-client cursor isolation；当前按 workspace-local CLI client state 处理。

Stop condition：

- 如 implementation 发现 existing Host public API 无法证明 watcher-first + outbox read 无漏投，必须停止，不得私读 Host DB 或新增 public API。
- 如 queued-only 状态无法通过 `get_session` + bounded wait 解释，必须停止并交 controller 裁决。
- 如 cursor store path ownership 与现有 workspace state policy 冲突，必须停止确认路径。

## 5. State Boundaries

### 5.1 Session Selection

- fresh anonymous `prompt`：创建新 Session；不读 cursor；不 startup backfill；成功展示本次 terminal 后可写 cursor。
- label `prompt`：选择 `cli.prompt.<label>` Session；不读 cursor；不 startup backfill；不等待旧 active / queued；成功展示本次 terminal 后写 cursor。
- `session resume --mode prompt`：解析 selected Session；语义等同 label prompt 的 existing-session submit；不 startup backfill；成功展示本次 terminal 后写 cursor。
- fresh anonymous `interactive`：创建新 Session；不 startup backfill。
- label `interactive`：选择 `cli.interactive.<label>` Session；进入 REPL 前必须 startup attach/reconnect。
- `session resume --mode interactive`：解析 selected Session；进入 REPL 前必须 startup attach/reconnect。

### 5.2 Interactive Startup Barrier

interactive existing-session startup 顺序固定为 watcher-first：

1. CLI 从 workspace-local cursor store 读取 selected `session_id` 的 terminal watermark 与 bounded seen terminal ids。
2. Service 打开 `watch_session_events(session_id)`，启动 drain task，把 live events 缓存在本地 queue 中。
3. Service 使用 caller cursor 调用 session-scoped Outbox backfill，读取 selected Session 下所有 terminal 增量；不按 `run_id` 过滤。
4. Service 将 Outbox item 与 watcher queue 已缓存的 terminal events 合并，用 `terminal_event_id` / `dedupe_key` / `event_sequence` / `run_id` 去重。Outbox 与 live overlap 只展示一次。
5. CLI 按 Service 返回顺序渲染 terminal；每个 terminal 成功渲染后立即通过 async cursor store 更新 watermark 与 seen ids。
6. Service 读取 `get_session(session_id)`：
   - 有 `active_run_id`：继续使用已经 attach 的 watcher 观察该 Run 到 terminal，必要时使用 outbox fallback；terminal 后重新读取 snapshot。
   - 无 active 但有 `queued_run_ids`：进入 bounded promotion wait，轮询 `get_session` 等待 queued Run promotion 为 active；promotion 后按 active Run 观察。
   - 无 active 且无 queued：startup barrier 完成，CLI 才进入 REPL。
7. bounded promotion wait 到期仍 queued-only：返回结构化 startup failure，CLI 输出“Session 仍有未开始的 queued Run，未进入输入态”的错误并退出，不允许用户在未知队列前提下继续输入。

窗口闭合证明：

- watcher 在 Outbox read 前已经 attach 并持续缓存 live events；因此 Outbox read 之后、snapshot 之前、active/queued 处理期间产生的 terminal 会进入 watcher queue。
- Outbox read 覆盖 cursor 之后 watcher attach 之前已经存在的离线 terminal。
- 去重使用 terminal identity，而不是依赖读取顺序；重复来源只展示一次。

### 5.3 Session-Scoped Outbox Backfill

新增 private helper，例如 `_read_session_outbox_terminal_backfill(...)`：

- 输入：`Host`、`session_id`、`OutboxTerminalCursor`、`seen_terminal_event_ids`、poll policy。
- 输出：`tuple[EntrypointRunTerminalResult, ...]`、next cursor、updated seen ids / dedupe keys。
- 不接收目标 `run_id`，不按 `run_id` 过滤。
- `CAUGHT_UP` 且没有新 item 是正常结束。
- `FAILED` 是 startup failure，抛 `EntrypointRuntimeError` 或返回 typed failure，不降级为静默进入 REPL。
- `LAGGED` 按参数化 bounded poll 重试；重试耗尽后是 startup failure，不静默忽略。
- 可复用 `_terminal_result_from_outbox_item(...)` 的 DTO 转换逻辑；不得复用 `_read_outbox_terminal(...)` 的 run-scoped 匹配与 CAUGHT_UP-without-match 异常语义。

### 5.4 Queued-Only Barrier

queued-only 是 startup pre-input barrier 的一部分，不是 residual risk：

- 若 snapshot 有 `active_run_id`，优先观察 active 到 terminal，再刷新 snapshot。
- 若 snapshot 无 active 但有 `queued_run_ids`，等待 promotion。
- promotion wait policy 使用调用参数，例如 `promotion_poll_interval_seconds` 与 `promotion_max_attempts`，默认值为命名常量。
- promotion 后按 active Run path 观察 terminal；terminal 后继续刷新 snapshot，直到 selected Session 无 active 且无 queued。
- promotion wait 到期仍 queued-only 时，CLI 结构化失败退出；不进入 REPL，不提交新 prompt。

### 5.5 Prompt Cursor Boundary

prompt 不做 startup，但可以标记已展示 terminal：

- prompt 不读取旧 cursor，不传 cursor 给 startup helper，不调用 session-scoped outbox backfill。
- prompt 不观察旧 active / queued Run；本次 follow-up 仍按既有 submit 行为排队。
- prompt 成功渲染本次 terminal / final answer 后，写入 CLI terminal cursor，语义是“本 CLI 已展示过该 terminal watermark”。
- cursor 写入失败应作为 CLI runtime error 暴露；不得影响 Host truth，不得补读历史 terminal。

## 6. Poll / Cursor Policies

命名默认常量建议：

- `CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE`: cursor store 保留最近 terminal ids 的上限，避免无限增长；具体值在实现中以命名常量定义，并用测试覆盖裁剪行为。
- `ENTRYPOINT_STARTUP_OUTBOX_LAGGED_MAX_ATTEMPTS`: Outbox projection `LAGGED` 最大重试次数。
- `ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS`: queued-only promotion 最大等待次数。
- `DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS`: queued-only promotion 轮询间隔；可复用或对齐现有 `DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS`。

参数化规则：

- Service helper 接收 `outbox_lagged_max_attempts`、`poll_interval_seconds`、`promotion_max_attempts`、`promotion_poll_interval_seconds`，并校验为有限正数 / 非负整数。
- CLI 负责选择是否使用默认值；Service 负责解释 Host projection status 与 Session snapshot 状态，不让 CLI 直接理解 `OutboxProjectionStatus`。
- 底层 helper 不硬编码重试次数或 sleep 间隔。

Cursor store 规则：

- 文件路径建议：`<workspace_root>/workspace/.dayu/cli/terminal_cursors.json`；implementation 前需确认与现有 workspace state path 一致。
- 顶层 JSON object：`session_id -> { "last_seen_terminal_event_sequence": int, "seen_terminal_event_ids": list[str] }`。
- 腐坏 JSON、非 object、非法字段、重复 seen id、负 sequence 必须结构化失败，不静默 reset。
- 写入只前进 watermark，不回退；seen ids 按命名窗口保留最近项。
- 写入发生在 terminal 成功渲染后；渲染后写入前崩溃允许下次重复展示，优先不漏投。
- async CLI 路径必须用 `asyncio.to_thread()` 或等价 executor 包裹同步 JSON 读写、`dayu.runtime.filelock` 持锁和原子 replace。

## 7. Affected Files / Modules

预计修改：

- `dayu/service/entrypoint_runtime.py`
  - 增加 startup reconnect request / result dataclass。
  - 增加 watcher-first startup helper。
  - 增加 session-scoped outbox backfill helper。
  - 增加 queued-only bounded promotion wait。
  - 参数化 poll policy。
- `dayu/cli/session_terminal_cursor.py`
  - 新增 CLI-local cursor store，包含 async facade + sync filelock/JSON 原子写实现。
- `dayu/cli/commands/interactive.py`
  - existing-session 入口在 REPL 前调用 startup helper，渲染 startup terminal，并成功渲染后更新 cursor。
- `dayu/cli/commands/prompt.py`
  - 保持不 startup；成功渲染本次 terminal 后更新 cursor。
- `dayu/cli/commands/session.py`
  - 不复制逻辑；保持路由到 prompt / interactive existing-session 入口。
- `dayu/cli/host_context.py`
  - 如需命名 startup operation context / client request id helper，可增加 CLI 层 helper。
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/cli/test_session_terminal_cursor.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_session_command.py`
- `dayu/service/README.md`
- `tests/README.md`
- `dayu/README.md` 仅在实现改变总览级边界描述时检查并按需更新。

禁止修改：

- `dayu/engine/**`
- `dayu/host/api.py`、Host read/command/durable/outbox schema 与 public exports。
- `dayu/config/prompts/**`
- `dayu/fins/**`

## 8. Implementation Slices

### Slice A - Service watcher-first startup helper

Objective：提供 interactive existing-session startup reconnect helper，使用 watcher-first 顺序关闭 live watch 与 Outbox backfill 的漏投窗口。

Allowed files:

- `dayu/service/entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

Exact changes:

- 新增 typed dataclass，例如 `EntrypointStartupReconnectRequest`、`EntrypointStartupReconnectResult`、`EntrypointStartupReconnectFailure` 或同等现有风格类型。
- request 字段必须包含 `context`、`session_id`、`terminal_cursor`、`seen_terminal_event_ids`、`poll_interval_seconds`、`outbox_lagged_max_attempts`、`promotion_poll_interval_seconds`、`promotion_max_attempts`。
- helper 先 `_attach_watcher(...)` 并启动 `_drain_host_events(...)`，再调用 session-scoped outbox backfill。
- helper drain watcher queue 中已缓存 terminal events，与 outbox results 按 terminal identity 去重，返回 CLI 应展示的 terminal results。
- helper 循环读取 session snapshot，处理 active / queued / idle 三种状态。
- active Run 观察复用 `_wait_for_terminal(...)`，但必须沿用已经 attach 的 watcher queue；terminal 后刷新 snapshot。
- queued-only 使用 bounded promotion wait；耗尽后抛 `EntrypointRuntimeError`，错误信息包含 session 仍有 queued Run 的业务可读说明，不暴露内部 cursor 作为事实。
- finally 中关闭 watcher / drain task。

Tests:

- watcher 在 outbox read 前 attach。
- terminal 发生在 outbox read 与 snapshot read 之间时，通过 watcher queue 展示，不漏投。
- Outbox 与 live watcher 返回同一个 terminal 时只展示一次。
- projection `FAILED` 导致 startup failure。
- projection `LAGGED` 按参数重试，耗尽后 failure。
- active_run_id 存在时先观察 active terminal，再刷新 snapshot。
- active terminal 后 promotion 出新 active 时继续观察。
- queued-only 等待 promotion；promotion 后观察 promoted run。
- queued-only bounded wait 耗尽时 startup failure，不进入 idle success。

### Slice B - Session-scoped Outbox backfill

Objective：实现 selected Session terminal 增量补读，不复用 run-scoped fallback 的匹配与异常语义。

Allowed files:

- `dayu/service/entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime.py`

Exact changes:

- 新增 `_read_session_outbox_terminal_backfill(...)` 或同义 private helper。
- 不接收 `run_id`，扫描每个 `OutboxTerminalItem` 并转为 `EntrypointRunTerminalResult`。
- 对每个 item 更新 `last_observed_event_sequence`、`seen_terminal_event_ids` 与 `seen_dedupe_keys`。
- `batch.has_more=True` 时继续分页。
- `projection_status=CAUGHT_UP` 且无更多 item 时正常返回。
- `projection_status=LAGGED` 且无更多 item 时由 bounded poll policy 决定 sleep/retry；不可无限循环。
- `projection_status=FAILED` 抛 structured startup failure。

Tests:

- 多个 run 的 terminal items 都返回。
- 无新 item 且 CAUGHT_UP 正常返回空 tuple。
- seen terminal ids 去重。
- dedupe key 去重。
- 不调用或不依赖 run-scoped `_read_outbox_terminal(...)`。

### Slice C - CLI terminal cursor store

Objective：实现 workspace-local CLI terminal watermark，供 prompt 与 interactive 记录“已展示 terminal”。

Allowed files:

- `dayu/cli/session_terminal_cursor.py`
- `tests/cli/test_session_terminal_cursor.py`

Exact changes:

- 定义 typed dataclass，例如 `CliTerminalCursorState`、`CliTerminalCursorRecord`。
- 提供 async API：读取 selected session cursor、成功渲染 terminal 后 advance cursor。
- async API 内部用 `asyncio.to_thread()` 包裹同步 JSON read/write、`dayu.runtime.filelock` 和 atomic replace。
- 定义命名常量：cursor 文件相对路径片段、lock 文件名、seen ids 窗口上限、临时文件前缀。
- 文件 missing 返回空 cursor；目录 missing 时创建。
- corrupt JSON / 非 object / 非法字段 fail fast。
- advance 只前进 sequence；低 sequence 不回退；seen ids bounded。

Tests:

- missing file 返回 empty cursor。
- update 后可读取。
- corrupt JSON / 非法字段失败。
- 低 sequence 不回退。
- seen ids 超过窗口时裁剪 oldest。
- async facade 在 executor 中调用同步实现；可用测试替身证明不在 event loop 中直接持同步 lock。
- 原子 replace 不留下半写文件。

### Slice D - Interactive existing-session wiring

Objective：`interactive --label` 与 `session resume --mode interactive` 在输入前执行 startup barrier。

Allowed files:

- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py` 仅当测试注入需要极小调整
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`

Exact changes:

- `_execute_interactive_on_existing_session(...)` 在 `_run_interactive_repl(...)` 前：
  - 根据 prepared/runtime workspace root 解析 cursor store。
  - 读取 selected session cursor。
  - 调用 Service startup helper。
  - 按返回顺序调用 `render_interactive_terminal_result(...)`。
  - 每个 terminal 成功渲染后 advance cursor。
- startup `SUCCEEDED` / `FAILED` / `CANCELLED` 渲染后继续进入 REPL。
- startup `LOST` 沿用 interactive terminal renderer 的 fatal exit policy，不进入 REPL。
- startup failure 使用 CLI 错误渲染并返回相应非零退出码。
- fresh anonymous interactive 不调用 startup helper、不读 cursor。

Tests:

- `interactive --label` 在第一条 input 前先 backfill offline final answer。
- `session resume --mode interactive --session-id ...` 在 REPL 前 backfill。
- startup active Run terminal 渲染后才读取输入。
- queued-only promotion 成 active 后先观察 terminal，再读取输入。
- queued-only wait 耗尽时不读取输入并返回 failure。
- duplicate terminal from outbox/live 只渲染一次。
- `LOST` startup terminal 返回 failure，不读取输入。
- fresh anonymous interactive 不调用 startup helper / cursor store。

### Slice E - Prompt negative boundary + cursor advancement

Objective：锁定 prompt 不做 startup，同时在本次 terminal 成功展示后更新 CLI cursor。

Allowed files:

- `dayu/cli/commands/prompt.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_session_command.py`

Exact changes:

- `_execute_prompt_on_existing_session(...)` 不读取旧 cursor，不调用 startup helper，不调用 session-scoped outbox backfill。
- terminal 成功渲染后调用 cursor store advance。
- fresh anonymous prompt 成功展示后也可写 cursor；若无法获得 session id 或 terminal result 缺必要 identity，则停止确认，不用隐式状态替代。
- cursor 写入失败作为 CLI runtime error；不补读旧 terminal，不修改 Host truth。

Tests:

- `prompt --label` 不读取旧 cursor、不 backfill old terminal。
- `session resume --mode prompt` 不调用 startup helper。
- selected Session 有 active_run_id 时，prompt 仍只提交本次 follow-up，不观察旧 active。
- prompt 展示当前 answer 后更新 cursor。
- 后续 interactive resume 使用该 cursor，不重复展示 prompt 已展示 terminal。

### Slice F - Docs sync

Objective：按 README 触发规则同步实际落地边界，不机械扩写。

Allowed files:

- `dayu/service/README.md`
- `tests/README.md`
- `dayu/README.md` 仅当总览边界描述已过期

Exact changes:

- 修改前先阅读目标 README 的 `Agent更新约束【必须遵守】` 或等价章节。
- `dayu/service/README.md` 只记录 entrypoint runtime 的 startup reconnect helper 边界：Service 编排 Host public API，不保存 CLI cursor，不输出 stdout/stderr。
- `tests/README.md` 记录新增 service / CLI startup reconnect 与 cursor store 测试覆盖。
- `dayu/README.md` 只有当 UI -> Service -> Host 总览描述需同步时才更新。

## 9. Validation

实施后优先运行：

```bash
source .venv/bin/activate
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py -q
pytest tests/cli/test_session_terminal_cursor.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q
python -m pyright dayu/service/entrypoint_runtime.py dayu/cli/session_terminal_cursor.py dayu/cli/commands/interactive.py dayu/cli/commands/prompt.py dayu/cli/commands/session.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_session_terminal_cursor.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py
```

若 README 或更大范围 helper 触发 broader check，追加：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/
```

Expected assertions:

- prompt negative boundary 测试证明没有 startup cursor read、没有 old terminal backfill、没有 old active/queued wait。
- interactive startup 测试证明 watcher-first、session-scoped backfill、active observation、queued-only barrier 和 no duplicate。
- cursor store 测试证明 async executor 包裹、腐坏文件 fail fast、atomic replace、bounded seen ids、只前进 watermark。
- pyright 无新增或扩散错误。

本 plan-fix gate 未运行测试和 pyright，因为本轮只新增计划 artifact，未改生产代码。

## 10. Docs Decision

本轮仅新增 `docs/reviews/**` artifact，不触发 README 更新。后续 implementation 若修改：

- `dayu/service/entrypoint_runtime.py`：必须检查并按需更新 `dayu/service/README.md`。
- `tests/**`：必须检查并按需更新 `tests/README.md`。
- 分层关系或装配方式：必须检查并按需更新 `dayu/README.md`。

默认不更新 `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`，因为本方案禁止修改对应目录和 public API。

## 11. Required Amendments Coverage

- session-scoped outbox backfill：覆盖于 §5.3、Slice B。
- watcher-first no-gap attach：覆盖于 §5.2、Slice A。
- queued-only pre-input barrier with bounded promotion wait/fail：覆盖于 §5.4、Slice A、Slice D。
- prompt no startup but post-render cursor watermark update：覆盖于 §5.5、Slice E。
- async cursor filelock via `to_thread` / executor：覆盖于 §6、Slice C。
- parameterized poll policy：覆盖于 §6、Slice A、Slice B。
- public Host/Engine API changes are not allowed：覆盖于 §1、§4、§7。

## 12. Residual Risks

- 多 CLI 客户端共享 workspace cursor 可能让一个客户端看过的 terminal 对另一个客户端不再 backfill。分类：deferred-with-owner；owner 为后续 product / CLI multi-client isolation work unit，本 WU 按 workspace-local CLI client state 处理。
- 渲染成功后、cursor 写入前崩溃会导致下次重复展示同一 terminal。分类：accepted residual risk；本 WU 明确优先不漏投。
- Startup active Run 长时间 `WAITING` 会让 interactive 入口停在运行态。分类：accepted behavior；用户可通过现有 cancel 语义退出或取消。
- queued-only bounded wait 的默认次数 / 时长需要在 implementation 中结合现有 CLI responsiveness 选择命名常量。分类：covered by Slice A tests and parameter validation。
- cursor store path ownership 需在 implementation 中确认现有 workspace state 约定。分类：stop condition if conflict found。

## 13. Completion Report Format

implementation 完成后的最终说明必须包含：

- 改了什么：按 Service startup helper、session-scoped outbox、CLI cursor、interactive wiring、prompt boundary、docs 分组。
- 验证了什么：列出 pytest 与 pyright 命令及结果。
- README 决策：说明更新了哪些 README，哪些检查后未更新。
- 剩余风险：按 §12 分类回报，未关闭项必须有 owner / 后续 work unit。
