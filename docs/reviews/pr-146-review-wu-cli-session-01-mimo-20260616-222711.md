# Code Review — PR #146 WU-CLI-SESSION-01

## Scope

- Mode: PR review
- PR: #146 — WU-CLI-SESSION-01 CLI session management
- URL: https://github.com/noho/dayu-agent-r/pull/146
- Author: noho
- Head branch: wu-cli-session-01
- Base branch: main
- Output file: `docs/reviews/pr-146-review-wu-cli-session-01-mimo-20260616-222711.md`
- Included scope: PR 完整 diff，涵盖 Host public list_sessions API、CLI session list/resume/purge、interactive --new-session 删除、docs/tests/readme 同步
- Excluded scope: 无
- Parallel review coverage: 无（单 reviewer PR-level 全量走读）
- Design/control sources: `docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`

## PR Facts

- 62 files changed, +7200 / -126 lines
- 涉及 6 个 implementation slices（S1-S6）+ aggregate validation
- 本地验证：`pytest ... -q` 120 passed，`pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean
- CI checks：draft PR 无 reported checks（本地验证已通过）

## Findings

### 1-未修复-低-session.py 跨模块 import prompt/interactive 私有窄入口函数

- **入口/函数**: `dayu/cli/commands/session.py` module-level imports
- **文件(行号)**: `dayu/cli/commands/session.py:36-45`
- **输入场景**: `session resume` 命令执行 prompt 或 interactive mode
- **实际分支**: session.py 导入 `_execute_prompt_on_existing_session`、`_prepare_prompt_existing_session_execution`、`_execute_interactive_on_existing_session`、`prepare_interactive_existing_session_execution` 四个 `_` 前缀私有函数，以及 `CliCommandUsageError`、`CliInteractiveUsageError` 两个异常类
- **预期行为**: plan Slice S5 明确接受此耦合为"CLI 命令包内部的 sibling module 依赖"，stop condition 要求"先在原模块内拆出窄入口，再让 session.py 编排 selector + mode + 窄入口路由"
- **实际行为**: 窄入口已在 prompt.py/interactive.py 中拆出（`_prepare_*_existing_session_execution` + `*_execute_*_on_existing_session`），session.py 只调用窄入口路由，不复制 submit/watch/cancel 业务路径
- **直接证据**: session.py 无 `submit_followup`、`_submit_prompt_turn_handling_sigint`、`_run_interactive_repl`、`watch_session_events` 调用；submit 逻辑仍在 prompt.py:364 和 interactive.py:463
- **影响**: 若 prompt.py/interactive.py 的窄入口签名变更，session.py 需同步更新；当前耦合程度可控但不为零
- **建议改法和验证点**: 当前无需修改。若未来 prompt/interactive 重构窄入口签名，应同时更新 session.py 的 import；或考虑将窄入口提升为 CLI 包内稳定 protocol
- **修复风险（低）**: 当前 plan 已接受此耦合
- **严重程度（低）**: 不影响正确性，是可维护性 observation

## Findings Review Against AGENTS.md Constraints

### 分层边界 UI → Service → Host → Engine

| 检查项 | 结果 | 证据 |
|---|---|---|
| CLI 不 import `dayu.host.durable.*` | 通过 | `grep -rn "durable" dayu/cli/` 返回零结果 |
| Host 不 import `dayu.cli.*` | 通过 | Host 层无 CLI import |
| CLI 不 import `dayu.engine` | 通过 | CLI 层无 Engine import |
| CLI Host imports 仅限 public DTO + opener | 通过 | session.py 只 import `Host` Protocol、`HostApiError`、`HostApiErrorCode`、`PurgeSessionRequest`、`SessionSlotRef`、`SessionStatus`、`ListSessionsResult` 等 public type + `open_host` |

### Host lifecycle truth / durable read truth

| 检查项 | 结果 | 证据 |
|---|---|---|
| `list_sessions` 是 durable read truth，不触发 projection | 通过 | read_api.py `_ListSessionsOperation` 只在 read transaction 内执行 SQL，不触发 projection catch-up |
| `list_sessions` 不触发执行 | 通过 | 不创建 Run、不 submit followup、不 resolve wait |
| purge 使用 Host public `purge_session`，不绕过 precondition | 通过 | session.py:232 调用 `host.purge_session(target.session_id, request)`；Host `purge_session` 的 durable transaction precondition 是最终 truth |
| resume 使用 `submit_followup(QUEUE)`，不是 Host wait-resume | 通过 | prompt.py:364 和 interactive.py:463 均使用 `FollowupBehavior.QUEUE, target_run_id=None` |

### No compatibility wrapper / no Any/object/untyped signatures

| 检查项 | 结果 | 证据 |
|---|---|---|
| 无兼容性 wrapper | 通过 | 无旧接口保持 wrapper |
| 无 `Any` / `object` 签名 | 通过 | 全部新增函数使用严格类型 |
| 无无类型参数/返回值 | 通过 | 所有函数签名完整 |

### Chinese docstring

| 检查项 | 结果 | 证据 |
|---|---|---|
| 新增 public API 有中文 docstring | 通过 | `SessionListItem`、`ListSessionsResult`、`Host.list_sessions`、`list_sessions` facade、`run_session_command` 等均有完整 `:param` / `:returns` / `:raises` |
| 新增 CLI 函数有中文 docstring | 通过 | session.py 所有函数、session_identity.py 所有函数、output.py 新增函数均有中文 docstring |

### Public API exposure

| 检查项 | 结果 | 证据 |
|---|---|---|
| Host public contract 只增加 `list_sessions` + 2 dataclass | 通过 | 无 `get_session_by_label`、无 `ListSessionsRequest`、无 filter/profile/query callback |
| 包根导出同步 | 通过 | `dayu/host/__init__.py` 的 `__all__` 包含 `SessionListItem`、`ListSessionsResult`、`list_sessions`；`test_package_exports.py` 锁定 |
| CLI output 不暴露内部治理字段 | 通过 | `render_session_list` 不渲染 `timeline_cursor`、`HostStreamCursor`；测试断言 `attempt-hidden`、`execution-hidden`、`payload-ref-hidden`、`digest-hidden` 不在输出中 |

### State / race / TOCTOU

| 检查项 | 结果 | 证据 |
|---|---|---|
| `session purge --label` TOCTOU | 已知、已接受 | plan 明确记录 list-resolve 与 purge 之间窗口；Host purge precondition 是最终 truth；stderr 包含原始 selector + resolved session_id + Host code/message |
| `session resume --label` TOCTOU | 已知、已接受 | 同上；Host submit precondition 是最终 truth |
| purge 不自动 close/cancel | 通过 | 测试断言 `host.close_cancel_calls == 0`；INVALID_STATE 消息说明 "no close/cancel was attempted" |
| resume 不 create/ensure Session | 通过 | session.py 无 `create_session`/`ensure_session`/`ensure_or_create_entrypoint_session` 调用；测试断言 `host.submit_requests == []` 对 CLOSED/missing |

### Session identity semantics

| 检查项 | 结果 | 证据 |
|---|---|---|
| label → slot ref 映射正确 | 通过 | `slot_ref_for_cli_label` 复用 `prompt_slot_key`/`interactive_slot_key` + scope 常量 |
| slot → display identity 反解正确 | 通过 | `display_identity_from_slot` 四分支覆盖 anonymous/prompt/interactive/other，含点号 label 不拆分 |
| `--kind` 必须与 `--label` 配合 | 通过 | `_require_label_kind` 在 `--label` 路径校验；缺 `--kind` 抛 usage error |

### Purge safety

| 检查项 | 结果 | 证据 |
|---|---|---|
| `--yes` 双重门禁 | 通过 | argparse `required=True` + 运行时 `if not args.yes: raise` |
| Host INVALID_STATE 消息清晰 | 通过 | "purge requires a closed Session with terminal Runs; no close/cancel was attempted" |
| purge tombstone 输出格式 | 通过 | `Purged session <id> (tombstone: <12-char-prefix>...)` |

### Resume execute-on-existing-session boundary

| 检查项 | 结果 | 证据 |
|---|---|---|
| resume 只解析已有 OPEN Session | 通过 | `_resolve_existing_session_target` 对 NOT_FOUND/CLOSED 抛 usage error，不 submit |
| resume 复用 prompt/interactive 窄入口 | 通过 | `_execute_prompt_on_existing_session` 复用 `_submit_prompt_turn_handling_sigint` + `render_prompt_terminal_result`；`_execute_interactive_on_existing_session` 复用 `_run_interactive_repl` |
| 默认 prompt/interactive 行为不变 | 通过 | `_run_prompt_command_async` 仍先 `_ensure_prompt_session`；`_run_interactive_command_async` 仍先 `_ensure_interactive_session` |

### Docs alignment

| 检查项 | 结果 | 证据 |
|---|---|---|
| `docs/host/design.md` 更新 | 通过 | `list_sessions` 加入 API 列表/行为矩阵/接口分层/phase 4 矩阵；CLI resume 术语区分 |
| `dayu/host/README.md` 更新 | 通过 | handle 方法、包根 facade、Host 专属契约、稳定边界加入 `list_sessions` |
| `dayu/README.md` 更新 | 通过 | Host public contract 总览加入 Session 列表读取结果 |
| `tests/README.md` 更新 | 通过 | CLI 段更新 `--new-session` 删除 + session 全命令面；Host 段更新 `list_sessions` |
| `docs/engine/design.md` 未改 | 正确 | Engine run-scoped 语义未变 |

## Open Questions

无。

## Residual Risk

| Risk | 严重程度 | Owner | 说明 |
|---|---|---|---|
| N+1 query（list_sessions 每 Session 额外 2 条 Run 查询） | 低 | Future pagination / performance hardening | plan §12 明确接受 |
| 无分页 | 低 | Future pagination | plan §12 明确接受，第一版有意最小设计 |
| Tab 分隔文本表列宽未对齐 | 低 | 后续 UX refinement | 不影响正确性 |
| `session.py` → prompt.py/interactive.py private import 耦合 | 低 | S5 plan accepted | 窄入口已先提取再 import |
| Draft PR 无 CI checks | 低 | Pre-merge gate | 本地验证已通过（120 passed, pyright 0 errors） |

## Validation Checked

- [x] `pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q` — **120 passed, 3 warnings**
- [x] `python -m pyright dayu/ tests/ utils/` — **0 errors, 0 warnings, 0 informations**
- [x] `git diff --check` — **clean**
- [x] CI checks — draft PR 无 reported checks（本地验证已通过）

## Conclusion

**PASS**

PR #146 的 WU-CLI-SESSION-01 实现通过 PR-level review。所有 AGENTS.md 约束检查通过，分层边界干净，Host durable read truth 语义正确，CLI 不暴露内部治理字段，purge/resume 的 TOCTOU 风险已被 plan 接受且有完整错误上下文。1 个低 severity finding（cross-module private import 耦合）为已知接受的 structural coupling，不阻断 merge。所有 residual risks 有明确 owner 且非阻断。
