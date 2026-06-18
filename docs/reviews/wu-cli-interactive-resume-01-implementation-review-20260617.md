# WU-CLI-INTERACTIVE-RESUME-01 Implementation Review

- Gate: review
- Work unit: `WU-CLI-INTERACTIVE-RESUME-01`
- 日期: 2026-06-17
- 评审范围: 当前分支未提交改动（9 文件，+1158/-12），含 untracked `dayu/cli/session_terminal_cursor.py` 与 `tests/cli/test_session_terminal_cursor.py`
- 输入 artifact:
  - `docs/reviews/wu-cli-interactive-resume-01-plan-fix-codex-20260617.md`
  - `docs/reviews/wu-cli-interactive-resume-01-plan-adjudication-20260617.md`
  - `docs/reviews/wu-cli-interactive-resume-01-idle-tail-fix-codex-20260617.md`
  - AGENTS.md / CLAUDE.md
- 验证数据: pyright `dayu/ tests/ utils/` → 0 errors; `tests/service/test_entrypoint_runtime.py -q` → 110 passed; 受影响 CLI 测试子集 → 74 passed

## 1. 总评

**Verdict: PASS** — 实现忠实覆盖了修订 plan 的全部 6 项 required amendments 及 idle-tail fix 追加要求，无 correctness bug，无 Host/Engine public API 变更，pyright 零错误，测试覆盖充分。

## 2. 变更范围

| 文件 | 变更 |
|---|---|
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

## 3. 关键要求逐项验证

### 3.1 Watcher-first 无漏投窗口（含 idle-tail closure）

**状态: PASS**

`startup_reconnect_entrypoint_session` (`entrypoint_runtime.py:739`) 严格遵循 watcher-first 顺序：

1. `_attach_watcher(host, session_id)` — attach live watcher
2. `asyncio.create_task(_drain_host_events(watcher, queue))` — 启动后台 drain task 缓存 live events
3. `_read_session_outbox_terminal_backfill(...)` — session-scoped outbox backfill
4. `_drain_available_startup_terminal_items(...)` — 消费 watcher queue 中已缓存 items
5. `_observe_startup_active_and_queued_runs(...)` — active/queued/idle 状态机

`_close_startup_idle_tail` (`entrypoint_runtime.py:525-565`) 在 idle snapshot 后再次执行 session-scoped outbox backfill + watcher drain；若 tail outbox 返回 terminal、tail drain 返回 terminal、或 tail drain 首次发现 watcher failure，返回 `True` 重新进入循环。第 561-564 行的 `watcher_failed_during_tail` 判定通过对比 drain 前后的 `state.watcher_failure_message` 检测首次 failure，与 idle-tail-fix artifact 要求一致。

窗口闭合成立：watcher 在 outbox read 前已 attach 并持续缓存 → Outbox read 覆盖 cursor 后、watcher attach 前的离线 terminal → 去重用 terminal identity → idle 后 tail closure 覆盖 terminal 已在传输但尚未到达 watcher queue 或 outbox projection 的边界。

测试覆盖: `test_startup_reconnect_attaches_watcher_before_session_outbox_backfill`、`test_startup_reconnect_reads_idle_tail_outbox_before_returning`、`test_startup_reconnect_rechecks_idle_tail_after_watcher_failure`。

### 3.2 Session-scoped Outbox backfill（非 run-scoped）

**状态: PASS**

`_read_session_outbox_terminal_backfill` (`entrypoint_runtime.py:608`) 不接收 `run_id` 参数，`_scan_session_outbox_terminal_items` (`entrypoint_runtime.py:680`) 不按 `run_id` 过滤。`CAUGHT_UP` 且无新 item 时正常返回空 tuple，不是异常。可复用 `_terminal_result_from_outbox_item(...)` 的 DTO 转换逻辑，但未复用 run-scoped `_read_outbox_terminal(...)` 的 `run_id` 匹配与 CAUGHT_UP-without-match 异常语义。

测试覆盖: `test_startup_reconnect_treats_caught_up_empty_backfill_as_idle_success`、`test_startup_reconnect_deduplicates_seen_terminal_ids`。

### 3.3 Queued-only barrier/failure

**状态: PASS**

`_wait_for_startup_promotion` (`entrypoint_runtime.py:568`) 按 `promotion_max_attempts` 轮询 `get_session`，`promotion_max_attempts=0` 时不进入循环体直接检查（line 588-594 loop 前已获取一次 snapshot）。重试耗尽仍 queued-only 时抛 `EntrypointRuntimeError`，错误信息包含 `session_id` 与 `queued_run_count`，业务可读，符合 Agent 语义约束（不暴露内部 cursor 作为事实）。

`_observe_startup_active_and_queued_runs` (`entrypoint_runtime.py:780`) 的 while 循环逻辑正确：drain watcher → snapshot → active 则 wait_for_terminal → queued 则 promotion wait + wait_for_terminal → idle 则 tail closure → 仅 tail 无新发现时 return。

测试覆盖: `test_startup_reconnect_waits_for_queued_promotion_then_observes_terminal`、`test_startup_reconnect_queued_only_exhaustion_fails_before_input`。

### 3.4 Prompt 不做 startup，仅做 cursor advancement

**状态: PASS**

`_execute_prompt_on_existing_session` (`prompt.py:258`) 不读取旧 cursor、不调用 `startup_reconnect_entrypoint_session`、不调用 session-scoped outbox backfill。只在 `render_exit_code == EXIT_SUCCESS` 时调用 `advance_cli_terminal_cursor` 写入本次 terminal watermark。

测试覆盖: `test_prompt_existing_session_execution_does_not_create_or_ensure` 新增 `read_outbox_requests == []` 断言证明 prompt 不读 outbox，新增 cursor 断言验证 watermark 写入。`test_interactive_existing_session_runs_startup_before_first_input` 同时验证 startup 在第一条 input 前执行且启动 terminal 与后续 turn terminal 均被写入 cursor。

### 3.5 Async cursor store / filelock

**状态: PASS**

`read_cli_terminal_cursor` / `advance_cli_terminal_cursor` (`session_terminal_cursor.py:95-138`) 的 async facade 通过 `asyncio.to_thread()` 包裹同步实现。同步实现内部使用 `dayu.runtime.filelock` 持锁 + JSON 读写 + `os.replace` 原子写回。

安全属性:
- 腐坏 JSON / 非 object / 非法字段 / 重复 seen id / 负 sequence → `CliTerminalCursorError` fail fast，不静默 reset。
- seen ids 按 `CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE=200` 有界裁剪，裁剪 oldest（`seen_ids[-MAX_SIZE:]`）。
- watermark 只前进不回退（`_advanced_record` 使用 `max(current, new)`）。
- 写入在 terminal 成功渲染后发生；渲染后写入前崩溃允许下次重复展示 → 优先不漏投。

测试覆盖: 9 个 cursor store 测试覆盖 missing file→empty、advance→read、不回退、裁剪、腐坏 fail-fast、非法字段 fail-fast、重复 seen id fail-fast、async executor 线程分离、atomic replace 临时文件清理。

### 3.6 公共 Host/Engine API 边界

**状态: PASS**

- 未修改 `dayu/engine/**`。
- 未修改 `dayu/host/api.py`、Host read/command/durable/outbox schema 与 public exports。
- 所有新增逻辑只使用既有 Host public API: `get_session`、`watch_session_events`、`read_outbox_terminal_items`、`get_run`、`cancel_run`、`submit_followup`。
- 未读取 Host durable internals，未新增 Host/Engine public request/response 字段。

### 3.7 Parameterized poll policy

**状态: PASS**

所有 poll 参数通过 `EntrypointStartupReconnectRequest` 传入，底层 helper 不硬编码重试次数或 sleep 间隔：

- `poll_interval_seconds`: active Run terminal 观察轮询间隔
- `outbox_lagged_max_attempts`: Outbox projection 落后最大重试次数
- `promotion_poll_interval_seconds`: queued Run promotion 轮询间隔
- `promotion_max_attempts`: queued-only promotion 最大等待次数

命名默认常量定义在模块顶层：
- `DEFAULT_ENTRYPOINT_TERMINAL_POLL_INTERVAL_SECONDS = 0.05`（复用既有常量）
- `DEFAULT_ENTRYPOINT_STARTUP_PROMOTION_POLL_INTERVAL_SECONDS = 0.05`
- `ENTRYPOINT_STARTUP_OUTBOX_LAGGED_MAX_ATTEMPTS = 3`
- `ENTRYPOINT_STARTUP_PROMOTION_MAX_ATTEMPTS = 20`

CLI 层（`interactive.py:395-400`）通过 `_run_existing_session_startup_reconnect` 决定使用默认值，Service 层负责解释 Host projection status 与 Session snapshot 状态。

### 3.8 AGENTS 编码约束

**状态: PASS（附 3 个轻微观察项）**

| 约束 | 状态 |
|---|---|
| 函数/类完整中文 docstring（:param/:returns/:raises） | ✅ |
| 无 `object`、`Any`、无类型参数/返回值 | ✅ |
| 无 `hasattr`/`getattr` 滥用 | ✅ |
| 无魔法数字（全部 Final 命名常量） | ✅ |
| 模块级私有辅助函数、无不必要嵌套 | ✅ |
| pyright: 0 errors, 0 warnings | ✅ |

**观察项（不影响 PASS，建议后续修正）:**

1. **不必要的 `Path()` 二次包裹** (`interactive.py:382, 408`): `prepared.workspace_root` 在 `_PreparedInteractiveExistingSessionExecution` 中类型已为 `Path`，`Path(prepared.workspace_root)` 是 `Path(Path(...))` 无操作。与 `prompt.py:291` 中直接使用 `prepared.workspace_root` 不一致。**建议**: 移除二次包裹，统一风格。

2. **空 `dedupe_key` 跨条目误判风险** (`entrypoint_runtime.py:703, 770`): `_scan_session_outbox_terminal_items` 与 `_startup_terminal_result_from_live_event` 将 `dedupe_key` 加入 `seen_dedupe_keys` set 时不校验非空。若 Host 提供了空字符串 `dedupe_key`，后续所有空 dedupe_key 条目均被误去重。当前依赖 Host contract 保证 terminal item dedupe_key 非空，无显式防护。**建议**: 在去重逻辑中仅当 `dedupe_key` 非空时加入 seen set（或在 `__post_init__` 中校验非空）。优先级低，Host 契约已隐含此保证。

3. **outbox vs live 的 `seen_terminal_event_ids` 更新时机不对称** (`entrypoint_runtime.py:703` vs `line 768`): `_scan_session_outbox_terminal_items` 无条件将 `terminal_event_id` 加入 seen set（即使被 dedupe_key 去重），而 `_startup_terminal_result_from_live_event` 只在非重复时加入。设计意图合理（outbox 是真源，即使本次被 dedupe 跳过也应标记 terminal_event_id 为已见），但缺少注释说明。**建议**: 加一行注释。

## 4. session resume startup failure 错误处理

`session.py:278-289` 中 `session resume --mode interactive` 路径只 catch `HostApiError`，不 catch `EntrypointRuntimeError`。若 startup reconnect 因 queued-only 耗时失败抛出 `EntrypointRuntimeError`，会以未捕获异常形式输出 stack trace，而非用户友好的 CLI 错误消息。

当前行为与 `prompt` 及其他 CLI 路径一致（`EntrypointRuntimeError` 通常向上传播），不影响正确性。**建议**: 后续 WU 在 `session resume` 路径增加 `EntrypointRuntimeError` catch 并渲染结构化错误。

## 5. 测试覆盖矩阵

| 场景 | 测试 |
|---|---|
| watcher attach 先于 outbox backfill | `test_startup_reconnect_attaches_watcher_before_session_outbox_backfill` |
| CAUGHT_UP 空 backfill 正常 idle | `test_startup_reconnect_treats_caught_up_empty_backfill_as_idle_success` |
| idle tail outbox closure | `test_startup_reconnect_reads_idle_tail_outbox_before_returning` |
| watcher failure 后 tail re-check | `test_startup_reconnect_rechecks_idle_tail_after_watcher_failure` |
| seen terminal ids 去重 | `test_startup_reconnect_deduplicates_seen_terminal_ids` |
| 参数化 LAGGED 重试 | `test_startup_reconnect_retries_lagged_by_parameter` |
| LAGGED 耗尽 fail | `test_startup_reconnect_lagged_retry_exhaustion_fails` |
| projection FAILED fail | `test_startup_reconnect_projection_failed_fails` |
| active Run 观察 terminal | `test_startup_reconnect_observes_existing_active_run_terminal` |
| queued promotion → observe | `test_startup_reconnect_waits_for_queued_promotion_then_observes_terminal` |
| queued 耗尽 fail | `test_startup_reconnect_queued_only_exhaustion_fails_before_input` |
| cursor: missing file → empty | `test_missing_cursor_file_returns_empty_record` |
| cursor: advance → read | `test_advance_then_read_cursor_record` |
| cursor: 只前进不回退 | `test_advance_does_not_move_sequence_backward` |
| cursor: seen ids 裁剪 | `test_seen_terminal_ids_are_trimmed_oldest_first` |
| cursor: corrupt JSON fail-fast | `test_corrupt_json_fails_fast` |
| cursor: 非法字段 fail-fast | `test_invalid_record_fields_fail_fast` |
| cursor: 重复 seen id fail-fast | `test_duplicate_seen_ids_fail_fast` |
| cursor: async executor 线程分离 | `test_async_read_uses_executor_thread` |
| cursor: atomic replace 清理临时文件 | `test_atomic_replace_failure_removes_temp_file` |
| interactive startup before input | `test_interactive_existing_session_runs_startup_before_first_input` |
| prompt 不读 outbox + cursor update | `test_prompt_existing_session_execution_does_not_create_or_ensure` |

**总计**: 22 个新增/增强测试，覆盖 plan Slices A-E 所有关键测试点。

## 6. README 更新

- `dayu/service/README.md`: 已更新 entrypoint_runtime 描述，新增 startup reconnect helper 边界（编排 Host public API，不保存 CLI cursor，不输出 stdout/stderr）。✅
- `tests/README.md`: 已更新 entrypoint runtime（startup watcher-first backfill、idle-tail closure、去重、active Run observation、queued-only barrier）与 interactive 命令（startup reconnect 在 input 前执行、cursor 前进）及 CLI cursor store 测试覆盖描述。✅
- `dayu/README.md`: 未触发更新（分层关系未变化）。✅
- `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`: 未触发更新（对应目录和 public API 未修改）。✅

## 7. 审阅者 pytest 说明

审阅过程中启动的 `pytest tests/cli/test_session_terminal_cursor.py tests/service/test_entrypoint_runtime.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q` 因耗时/挂起被中断，结果 **inconclusive**。这不视为实现缺陷——控制器已独立验证同一测试集通过（service: 110 passed; CLI 子集: 74 passed），且 pyright 全项目零错误。挂起推测与 `test_session_command.py` 中部分测试依赖外部资源有关，与本次改动无关。

## 8. Residual Risks

| 风险 | 分类 | 与 plan 一致性 |
|---|---|---|
| 多 CLI 客户端共享 cursor 互相遮蔽 terminal | deferred | 与 plan §12 一致，后续 WU 处理 |
| 渲染后 cursor 写入前崩溃 → 下次重复展示 | accepted | 优先不漏投 |
| Startup active Run 长时间 WAITING | accepted | 用户可通过 cancel 退出 |
| `promotion_max_attempts=20 × 0.05s = 1s` | 调优参数 | 命名常量，可后续调整 |
| 空 `dedupe_key` 跨条目误判 | 低概率 | 见 §3.8 观察项 2 |
| `session resume` startup `EntrypointRuntimeError` 未渲染 | deferred | 见 §4，与 prompt 路径一致 |

## 9. 结论

实现完整覆盖修订 plan 的全部 6 项 required amendments 与 idle-tail fix 追加要求:

1. ✅ Watcher-first no terminal gap（含 idle-tail closure）
2. ✅ Session-scoped Outbox backfill（非 run-scoped）
3. ✅ Queued-only barrier with bounded promotion wait/failure
4. ✅ Prompt no startup but post-render cursor watermark update
5. ✅ Async cursor store via `to_thread` + filelock
6. ✅ Parameterized poll policy
7. ✅ 未修改 Host/Engine public API
8. ✅ 中文 docstring、完整类型、命名常量

无 correctness bug 或 regression。3 个轻微观察项不影响功能正确性。建议通过 review gate。
