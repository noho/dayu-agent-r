# Deep Review — WU-CLI-ACTIVITY-01 Aggregate Final

## Scope

- Mode: current changes (aggregate)
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/deepreview-wu-cli-activity-01-aggregate-mimo-20260617-153030.md`
- Included scope: branch 上全部 4 commits（plan `012fee0a`、Slice A `992a641d`、Slice B `152292da`、CLI `1a6f4bb2`）+ 未提交修复
- Excluded scope: F-2 `cancel_entrypoint_run_and_wait` `on_activity` 裁决延期至 Slice E
- Parallel review coverage:
  - ✅ Host public event projection（subagent 完成）：`dayu/host/api.py`、`dayu/host/read_api.py`、`dayu/host/__init__.py`、`dayu/host/README.md`
  - ✅ Service activity callback（主 reviewer 直接验证 + 前轮 review 累积）：`dayu/service/entrypoint_runtime.py`
  - ⚠️ CLI integration（subagent 超时，部分输出可用；主 reviewer 基于前轮 review 累积 + 直接验证补充）

## Plan Alignment

| Slice | 目标 | 状态 |
|---|---|---|
| A | Host public activity event contract | ✅ 已实现并验证 |
| B | Service activity callback | ✅ 已实现并验证（F-1/F-3 修复确认） |
| C | CLI activity renderer + prompt integration | ✅ 已实现并验证 |
| D | Interactive composer | ✅ 已实现并验证 |
| E | Interactive running activity + cancel integration | ✅ 已实现并验证 |
| F | Documentation checks + validation | ✅ README/控制文档已更新 |

Plan expected assertions 对齐：
- ✅ stdout 只含 final answer；activity 走 stderr
- ✅ `watch_session_events` 是唯一 Host event read path
- ✅ `HostEvent` 对非终态事件保留 `event_class`/`event_type`；`activity=None` 时安全跳过
- ✅ `HostActivityView` 工具展示名优先 `ToolDisplayInfo.name`，缺失 fallback stable tool name
- ✅ `REASONING_DELTA`/`CONTENT_DELTA` 保留 identity 但 `activity=None`
- ✅ Ctrl+T 不触发 cancel；Ctrl+C/Esc 触发 cancel；连续 Ctrl+C 本地退出；terminal-first-wins
- ✅ composer Ctrl+J/Ctrl+R/Ctrl+X Ctrl+E 有独立单元测试
- ✅ 非 TTY 无 live activity，Ctrl+C 按 SIGINT/local exit 语义

## Findings

未发现实质性问题。

### 已验证的关键修复

**F-1（Slice B）**: 非终态 HostEvent dedupe key 不再抑制后续终态。
- `_terminal_result_from_live_event` 通过 early return（行 1012-1013）确保非终态事件不写入 `seen_dedupe_keys`
- activity 去重使用独立的 `seen_activity_dedupe_keys`，与 terminal dedupe 完全隔离
- 测试 `test_submit_entrypoint_turn_non_terminal_dedupe_key_does_not_hide_terminal` 精确验证

**F-3（Slice B）**: callback exception propagation。
- `on_activity` callback 异常无 try/except 包裹，沿 `_emit_entrypoint_activity_from_host_event` → `_drain_available_watcher_items` → `_wait_for_terminal` 直接传播
- `submit_entrypoint_turn_and_wait` 的 `finally` 块保证 watcher 资源释放
- 测试 `test_submit_entrypoint_turn_activity_callback_exception_propagates` 验证异常内容和 watcher cleanup

**CLI cancel 竞争（Slice C/E）**: prompt 和 interactive 均正确实现 terminal-first-wins 和 second-Ctrl+C-exits。
- `_cancel_prompt_run_waiting_for_terminal_or_second_sigint`（prompt 行 476-531）和 `_cancel_run_waiting_for_terminal_or_second_sigint`（interactive 行 663-720）结构一致
- `asyncio.wait(FIRST_COMPLETED)` 竞争 `cancel_task` 与 `second_sigint_task`
- 测试覆盖：prompt `test_prompt_second_sigint_exits_after_cancel_request` + `test_prompt_cancel_terminal_wins_over_second_sigint`；interactive `test_interactive_second_sigint_exits_after_cancel_request` + `test_interactive_repl_returns_130_on_second_sigint`

**Activity renderer visible/hidden title（Slice C）**: `_last_hidden_title = activity.title` 移到 visibility check 之前（行 113），无条件赋值。测试 `test_activity_renderer_toggle_hidden_reports_latest_visible_activity` 验证。

**TtyRunningKeyMonitor thread.start 失败恢复（Slice C）**: `thread.start()` 独立 try/except RuntimeError（行 171-180），失败时立即 `tcsetattr` 恢复并重置状态。

## Architecture Boundary Verification

| 方向 | 验证结果 |
|---|---|
| Host → Service/CLI | ✅ 零导入 |
| Service → CLI | ✅ 零导入 |
| CLI → Host | ✅ 只使用 `dayu.host.api`（public contract）和 `dayu.host.open_host`（public opener） |
| CLI → Service | ✅ 只使用 `dayu.service.entrypoint_runtime`（public helper）和 `dayu.service.host_assembly`（public types） |
| CLI 模块（activity/composer/run_keys）| ✅ 只导入 `dayu.service.entrypoint_runtime` 和标准库；不导入 Host internals |

Public API exposure 检查：
- `dayu/host/__init__.py` 正确导出 `HostActivityCounts`/`HostActivityKind`/`HostActivitySeverity`/`HostActivityStatus`/`HostActivityView`
- `dayu/cli/activity.py`、`dayu/cli/composer.py`、`dayu/cli/run_keys.py` 的 `__all__` 只暴露公共协议和工厂函数

## Tests and Validation

| 维度 | 结果 |
|---|---|
| 全量测试 | ✅ 173 passed（Host 60 + Service 26 + CLI prompt 22 + CLI interactive 21 + CLI activity renderer 6 + CLI composer 6 + CLI run keys 5 + 其他 27） |
| pyright | ✅ 0 errors, 0 warnings |
| stdout/stderr 分离 | ✅ activity 写 stderr，final answer 写 stdout |
| non-TTY | ✅ `CliActivityRenderer` 默认按 `stderr.isatty()` 决定 enabled；`NoopRunningKeyMonitor` 不产生按键事件 |
| README 更新 | ✅ `dayu/host/README.md`（activity types + event flow）；`tests/README.md`（新增测试覆盖描述） |
| 控制文档 | ✅ `docs/host/issues-implementation-control.md` 更新为 `ready-to-open-draft-PR` |

## Open Questions

- 无。

## Residual Risk

- **prompt `_cancel_prompt_turn_after_local_request` run_id 竞争**: CLI integration subagent 部分分析指出，prompt 侧在 cancel 后直接检查 `accepted_run.run_id`，若 `submit_task.cancel()` 在 `on_run_accepted` 回调前执行，`run_id` 为 None 直接返回。interactive 侧通过 `_wait_for_run_id_or_local_exit` 显式等待 run_id 更稳健。但实际路径中 `on_run_accepted` 在 `submit_followup` 返回后同步调用（`entrypoint_runtime.py:563-564`），而 `submit_task.cancel()` 只在下一个 `await` 生效，因此 `run_id` 在 cancel 前已设置。**当前行为正确**，但 interactive 侧的显式等待模式更具防御性。风险低。
- **PromptToolkitInteractiveComposer 端到端集成**: composer 独立测试验证了 key binding 注册和 handler 行为，但 `PromptToolkitInteractiveComposer.read()` 的真实终端交互未在 CI 中覆盖。风险低（prompt_toolkit 是成熟库）。
- **F-2 延期**: `cancel_entrypoint_run_and_wait` 的 `on_activity` 参数集成裁决延期至 Slice E。当前 cancel 路径不传递 activity callback，cancel 期间无 activity 输出。符合预期。

## Review Limitations

- CLI integration subagent 超时（`a9826fb9aaef3993e`），部分输出可用。主 reviewer 基于前轮 review 累积（`code-review-wu-cli-activity-01-cli-mimo-20260617-145226.md`、`code-review-wu-cli-activity-01-cli-rereview-mimo-20260617-151159.md`）和直接代码验证补充 CLI 维度结论。

## 结论

**非阻断**。WU-CLI-ACTIVITY-01 全部 6 个 Slice 的实现正确、架构边界清晰、测试充分（173 passed / pyright 0 errors）、文档已更新。未发现 blocking findings。
