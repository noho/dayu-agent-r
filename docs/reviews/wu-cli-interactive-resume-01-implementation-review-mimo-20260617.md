# WU-CLI-INTERACTIVE-RESUME-01 Implementation Review (MiMo)

- Work unit: `WU-CLI-INTERACTIVE-RESUME-01`
- Review date: 2026-06-17
- Review scope: 当前未提交实现（9 文件，+1158/-12）
- Verdict: **PASS（附带低优先级建议）**

## 1. 审查范围

| 文件 | 变更 |
|------|------|
| `dayu/service/entrypoint_runtime.py` | +481 行：startup reconnect helper、session-scoped outbox backfill、idle-tail closure、queued-only barrier |
| `dayu/cli/session_terminal_cursor.py` | +378 行（新文件）：workspace-local CLI terminal cursor store |
| `dayu/cli/commands/interactive.py` | +85 行：existing-session startup wiring、cursor advancement |
| `dayu/cli/commands/prompt.py` | +16/-3 行：cursor advancement（不做 startup） |
| `tests/service/test_entrypoint_runtime.py` | +446 行：startup reconnect 全路径覆盖 |
| `tests/cli/test_session_terminal_cursor.py` | +229 行（新文件）：cursor store 测试 |
| `tests/cli/test_interactive_command.py` | +122 行：startup before first input 测试 |
| `tests/cli/test_prompt_command.py` | +8 行：cursor advancement 断言 |
| `tests/cli/test_session_command.py` | +2 行：workspace_root 参数传递 |
| `dayu/service/README.md` | 更新 entrypoint_runtime 描述 |
| `tests/README.md` | 更新测试覆盖描述 |

## 2. 正确性审查

### 2.1 Watcher-first no terminal gap ✅

`startup_reconnect_entrypoint_session` 的执行顺序完全符合 plan §5.2：

1. `_attach_watcher(host, session_id)` — attach live watcher
2. `asyncio.create_task(_drain_host_events(watcher, queue))` — 启动后台 drain task 缓存 live events
3. `_read_session_outbox_terminal_backfill(...)` — session-scoped outbox backfill
4. `_drain_available_startup_terminal_items(...)` — 消费 watcher queue 已缓存 items
5. `_observe_startup_active_and_queued_runs(...)` — active/queued/idle 处理

**证据**：`entrypoint_runtime.py:739-759`，watcher attach 在 outbox read 之前，drain task 在 watcher attach 后立即启动。

**窗口闭合证明**：watcher 在 outbox read 前已 attach 并持续缓存 live events；outbox read 覆盖 cursor 之后 watcher attach 之前已存在的离线 terminal；去重使用 terminal event id + dedupe key，outbox 与 live overlap 只展示一次。

### 2.2 Idle-tail closure ✅

`_close_startup_idle_tail` 在 idle snapshot 后执行：

1. 再次 session-scoped outbox backfill
2. drain watcher queue
3. 若发现 terminal 或首次 watcher failure → 返回 `True` → 重新进入循环

**证据**：`entrypoint_runtime.py:861-901`

**测试覆盖**：
- `test_startup_reconnect_reads_idle_tail_outbox_before_returning`：idle 后 tail outbox 返回 terminal
- `test_startup_reconnect_rechecks_idle_tail_after_watcher_failure`：tail drain 发现 watcher failure 后重新进入 outbox

### 2.3 Session-scoped outbox backfill（非 run-scoped）✅

`_read_session_outbox_terminal_backfill` 不接收 `run_id` 参数，扫描所有 `OutboxTerminalItem`。

**证据**：`entrypoint_runtime.py:1376-1445`，函数签名无 `run_id`，`ReadOutboxTerminalItemsRequest` 不传 `run_id`。

**对比**：既有 `_read_outbox_terminal` 是 run-scoped fallback（接收 `run_id`、CAUGHT_UP 未命中时抛错），新 helper 完全独立。

### 2.4 Queued-only barrier ✅

`_wait_for_startup_promotion` 实现 bounded promotion wait：

- 按 `promotion_max_attempts` 次数轮询 `get_session`
- 耗尽仍 queued-only → 抛 `EntrypointRuntimeError`
- `promotion_max_attempts=0` 时不进入循环，直接检查并可能抛错

**证据**：`entrypoint_runtime.py:904-934`

**测试覆盖**：
- `test_startup_reconnect_waits_for_queued_promotion_then_observes_terminal`
- `test_startup_reconnect_queued_only_exhaustion_fails_before_input`

### 2.5 Prompt 不做 startup 但 cursor advancement ✅

`_execute_prompt_on_existing_session` 不读取旧 cursor、不调用 startup helper、不调用 session-scoped outbox backfill。成功渲染 terminal 后调用 `advance_cli_terminal_cursor`。

**证据**：`prompt.py:275-296`

**测试覆盖**：
- `test_prompt_existing_session_execution_does_not_create_or_ensure`：断言 `read_outbox_requests == []`（无 startup backfill），断言 cursor 写入正确
- `test_interactive_existing_session_runs_startup_before_first_input`：验证 startup 在 input 之前执行

### 2.6 Async cursor store / filelock ✅

`read_cli_terminal_cursor` 和 `advance_cli_terminal_cursor` 使用 `asyncio.to_thread()` 包裹同步实现。

**证据**：`session_terminal_cursor.py:95-138`

**同步实现**内部使用 `dayu.runtime.filelock.file_lock` 和原子 `os.replace`。

**测试覆盖**：
- `test_async_read_uses_executor_thread`：验证不在 event loop 线程执行
- `test_atomic_replace_failure_removes_temp_file`：验证原子写失败后清理临时文件

### 2.7 Public Host/Engine API boundary ✅

实现只使用既有 public API：
- `host.watch_session_events(session_id)`
- `host.read_outbox_terminal_items(session_id, request)`
- `host.get_session(session_id)`
- `host.get_run(run_id)`
- `host.submit_followup(session_id, request)`

未新增 Host/Engine public API、未修改 Host durable schema、未读取 Host durable internals。

### 2.8 Parameterized poll policy ✅

所有重试次数和轮询间隔通过 `EntrypointStartupReconnectRequest` 参数传入：

- `poll_interval_seconds`：active Run terminal 观察间隔
- `outbox_lagged_max_attempts`：LAGGED 重试上限
- `promotion_poll_interval_seconds`：queued promotion 轮询间隔
- `promotion_max_attempts`：queued-only promotion 最大等待次数

命名默认常量：
- `DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS = 0.05`
- `DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS = 0.05`
- `ENTRYPOINT_STARTUP_OUTBOX_LAGGED_MAX_ATTEMPTS = 3`
- `ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS = 20`

## 3. 类型 / Docstring / README 审查

### 3.1 类型 ✅

- 所有新增 dataclass 使用 `frozen=True, slots=True`
- 所有函数签名有完整类型注解
- `__post_init__` 校验使用 `isinstance` + 显式 `TypeError`/`ValueError`
- 未使用 `object`、`Any` 或无类型参数

### 3.2 Docstring ✅

- 所有新增公共函数和 dataclass 有完整中文 docstring
- 包含 `:param`、`:returns`、`:raises` 说明
- 复杂逻辑有中文行内注释

### 3.3 README ✅

- `dayu/service/README.md`：更新 entrypoint_runtime 描述，新增 startup reconnect helper 边界
- `tests/README.md`：更新 entrypoint runtime 和 interactive 命令测试覆盖描述

## 4. 低优先级建议（非阻塞）

### 4.1 session resume startup failure 错误处理

`session.py:278-289` 中 `session resume --mode interactive` 路径只 catch `HostApiError`，不 catch `EntrypointRuntimeError`。若 startup reconnect 因 queued-only 耗时失败，会以未捕获异常形式输出 stack trace，而非用户友好的错误消息。

当前行为与 `prompt` 和其他 CLI 路径一致（`EntrypointRuntimeError` 通常向上传播），不影响正确性。若需改进，可在 `session resume` 路径增加 `EntrypointRuntimeError` catch 并渲染结构化错误。

### 4.2 startup test 中 input 不发生的证明

`test_interactive_existing_session_runs_startup_before_first_input` 通过事件顺序 `events[:2] == ["startup:session-existing", "input:dayu> "]` 证明 startup 在 input 之前。但 `input_reader` 中第二个 input raise EOFError，测试依赖 startup 返回一条 terminal 使 cursor 前进。可考虑增加断言证明 startup 失败时不读取 input（当前由 startup failure return code 保证）。

## 5. 测试覆盖总结

| 路径 | 测试数 | 覆盖 |
|------|--------|------|
| watcher-first attach 顺序 | 1 | ✅ |
| CAUGHT_UP 空 backfill idle success | 1 | ✅ |
| idle-tail outbox closure | 1 | ✅ |
| idle-tail watcher failure re-entry | 1 | ✅ |
| seen terminal ids 去重 | 1 | ✅ |
| LAGGED 参数化重试 | 1 | ✅ |
| LAGGED 重试耗尽失败 | 1 | ✅ |
| projection FAILED 失败 | 1 | ✅ |
| active Run terminal 观察 | 1 | ✅ |
| queued-only promotion 成功 | 1 | ✅ |
| queued-only 耗尽失败 | 1 | ✅ |
| CLI cursor missing file → empty | 1 | ✅ |
| CLI cursor advance + read | 1 | ✅ |
| CLI cursor 只前进不回退 | 1 | ✅ |
| CLI cursor seen ids 裁剪 | 1 | ✅ |
| CLI cursor corrupt JSON fail-fast | 1 | ✅ |
| CLI cursor 非法字段 fail-fast | 1 | ✅ |
| CLI cursor 重复 seen id fail-fast | 1 | ✅ |
| CLI cursor async executor 包裹 | 1 | ✅ |
| CLI cursor atomic replace 失败清理 | 1 | ✅ |
| interactive startup before first input | 1 | ✅ |
| prompt cursor advancement（不含 startup） | 1 | ✅ |
| session resume workspace_root 传递 | 1 | ✅ |

**总计**：22 个新增测试，覆盖 plan 中所有 required amendments 和 Slice A-E 的关键测试点。

## 6. 结论

实现正确反映了 plan-fix 的所有 required amendments：

1. ✅ session-scoped outbox backfill（非 run-scoped）
2. ✅ watcher-first no-gap attach
3. ✅ queued-only pre-input barrier with bounded promotion wait/fail
4. ✅ prompt no startup but post-render cursor watermark update
5. ✅ async cursor filelock via `to_thread`
6. ✅ parameterized poll policy
7. ✅ idle-tail closure（idle-tail fix artifact 要求）
8. ✅ public Host/Engine API 未变更

无 correctness bug 或 regression 发现。PASS。
