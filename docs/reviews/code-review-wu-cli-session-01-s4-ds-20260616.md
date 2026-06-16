# Code Review — WU-CLI-SESSION-01 S4

## Scope

- Mode: current changes
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-review-wu-cli-session-01-s4-ds-20260616.md
- Included scope:
  - `dayu/cli/arg_parsing.py` — `COMMAND_SESSION`、二级 action 注册、`ParsedCliArgs` 新字段
  - `dayu/cli/main.py` — `COMMAND_RUNNERS` 注册
  - `dayu/cli/commands/session.py`（新文件）— `run_session_command`、list/purge 完整链路
  - `dayu/cli/host_context.py` — `build_session_host_context`、`session_purge_client_request_id`、`CLI_SESSION_OPERATION_KIND`
  - `dayu/cli/output.py` — `render_session_list`、`render_session_purge_result`（S3 已加入，S4 补充 `__all__`）
  - `tests/cli/test_arg_parsing.py` — session help 预期、`--new-session` 删除验证
  - `tests/cli/test_session_command.py`（新文件）— 12 个测试（含 S3 延续的 5 个 helper 测试 + S4 新增 7 个端到端命令测试）
  - `tests/README.md` — Session command 测试覆盖描述
  - `docs/reviews/wu-cli-session-01-s4-implementation-codex.md`
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（controller bookkeeping）
  - S1/S2/S3/S5/S6 slice 文件（不在 S4 scope）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项确认

**1. 只通过 Host public API，不读 durable、不自动 close/cancel**

- `_run_session_list` → `host.list_sessions()`（`session.py:199`）
- `_run_session_purge` → `host.purge_session(target.session_id, request)`（`session.py:232`）
- `_resolve_session_id_for_slot` → `host.list_sessions()` → 遍历 `item.slot == slot`（`session.py:302-306`）
- 无 `dayu.host.durable.*` import
- `_FakeSessionHost.close_session` 与 `cancel_session_runs` 仅递增 `close_cancel_calls` 计数器；INVALID_STATE 测试断言 `host.close_cancel_calls == 0`（`test_session_command.py:1292`）

**2. Runtime assembly 使用已有 `prompt` scene carrier，未伪装成 LLM scene**

- `_prepare_session_runtime` → `scene_id=CLI_PROMPT_SCENARIO`（即 `"prompt"`）（`session.py:182`）
- `_session_context_slot_values` 填充 `fins_default_subject`、`base_user` 两个 required slots（`session.py:401-411`）
- `new_cli_invocation` 的 scenario 为 `_SESSION_CONTEXT_SCENARIO = "session"`（`session.py:140`）
- `build_session_host_context` 的 operation_kind 为 `CLI_SESSION_OPERATION_KIND = "cli_session"`（`host_context.py:278-282`）
- 测试 `_assert_session_runtime_uses_prompt_carrier` 断言 `request.scene_id == "prompt"` 且两个 slot 值正确（`test_session_command.py:1463-1477`）
- `prompt` scene 仅作为 Host opener carrier；session 命令不提交 prompt Run、不持有 LLM scene 语义

**3. Parser shape 包含 list/resume/purge；S4 仅让 resume 返回 not implemented**

- `_register_session_command` 注册 `list`、`resume`、`purge` 三个二级 action（`arg_parsing.py:127-155`）
- `resume` 的 parser surface 完整冻结：`--session-id`/`--label` selector、`--kind`、`--mode`（required）、positional `session_prompt`、agent execution arguments（`arg_parsing.py:205-238`）
- `run_session_command` 首行判断 `args.session_action == SESSION_ACTION_RESUME` → `EXIT_NOT_IMPLEMENTED`（`session.py:105-107`）
- 测试 `test_session_resume_execution_is_left_not_implemented` 断言 exit code `EXIT_NOT_IMPLEMENTED` 且 stderr 含 `"not implemented"`（`test_session_command.py:1353-1377`）

**4. Purge selector 正确实现**

- `--session-id`：`_resolve_purge_target` 直接返回 session_id，`resolved_from_label=False`（`session.py:257-267`）
- `--label + --kind`：先 `slot_ref_for_cli_label(kind, label)` → `_resolve_session_id_for_slot(host, slot)` → `host.list_sessions()` 匹配 slot → 返回 session_id，`resolved_from_label=True`（`session.py:268-286`）
- `--yes` 双重门禁：argparse `required=True`（`arg_parsing.py:261-264`）+ 运行时校验 `if not args.yes: raise CliSessionUsageError(...)`（`session.py:220-221`）
- 缺 `--kind` → `_require_label_kind(None)` → `CliSessionUsageError("--label requires --kind prompt|interactive")`（`session.py:317-318`）
- label 无匹配 → `_resolve_session_id_for_slot` 返回 `None` → `CliSessionUsageError("no session found for label ...")`（`session.py:279-281`）
- 测试覆盖：`test_session_purge_missing_yes_returns_usage_error`、`test_session_purge_by_session_id_calls_host_purge`、`test_session_purge_by_label_resolves_slot_then_purges`

**5. TOCTOU Host error stderr 包含完整上下文**

`_purge_host_error_message`（`session.py:345-369`）对所有 HostApiError 均输出：
```
selector={target.selector} session_id={target.session_id} host_code={code} host_message={message}
```
INVALID_STATE 额外前缀 `"purge requires a closed Session with terminal Runs; no close/cancel was attempted."`

测试 `test_session_purge_by_label_toctou_error_includes_selector_and_host_context` 断言（`test_session_command.py:1295-1350`）：
- `"--label proj.v1 --kind prompt" in captured.err` — 原始 selector
- `"session-A" in captured.err` — resolved session_id
- `"conflict" in captured.err` — Host error code
- `"slot changed before purge" in captured.err` — Host error message

**6. INVALID_STATE 明确说明前置条件且不 close/cancel**

- 错误消息明确 `"purge requires a closed Session with terminal Runs; no close/cancel was attempted"`（`session.py:360-362`）
- 测试断言 `"closed Session" in captured.err`、`"terminal Runs" in captured.err`、`"no close/cancel" in captured.err`、`host.close_cancel_calls == 0`（`test_session_command.py:1287-1292`）

**7. PurgeSessionRequest 字段稳定，无 extra payload**

- `client_request_id`：由 `session_purge_client_request_id(invocation)` 生成，格式 `"dayu-cli:session:<invocation_id>:session:purge"`（`host_context.py:339-354`）
- `reason`：显式提供时用用户值，否则 `DEFAULT_PURGE_REASON = "cli_session_purge"`（`session.py:327-342`）
- `context`：经 `build_session_host_context` 构造，operation_kind=`"cli_session"`，operation=`"purge_session"`（`session.py:224-227`）
- 测试断言 `request.client_request_id.startswith("dayu-cli:session:")`、`endswith(":session:purge")`、`request.reason == "cleanup"`（`test_session_command.py:1185-1186`）

**8. 测试覆盖真实风险**

| 测试 | 覆盖风险 |
|---|---|
| `test_session_action_help_contains_fixed_parser_shape` | parser surface 完整性 |
| `test_session_list_calls_host_public_api_and_renders_sessions` | list 端到端 + carrier 验证 + 不读 durable |
| `test_session_purge_missing_yes_returns_usage_error` | `--yes` 门禁 |
| `test_session_purge_by_session_id_calls_host_purge` | `--session-id` 直 purge + 输出格式 |
| `test_session_purge_by_label_resolves_slot_then_purges` | `--label` resolve → purge 链路 |
| `test_session_purge_invalid_state_explains_closed_terminal_precondition` | INVALID_STATE 消息 + 不 close/cancel |
| `test_session_purge_by_label_toctou_error_includes_selector_and_host_context` | TOCTOU 完整错误上下文 |
| `test_session_resume_execution_is_left_not_implemented` | resume not implemented 边界 |

所有 Host 调用测试均通过 `_assert_session_runtime_uses_prompt_carrier` 验证 carrier 正确性（`scene_id == "prompt"` + required slots）。

**9. docstring / 类型签名 / AGENTS**

- 所有新增函数均有中文 docstring
- 无 `Any`、`object`、裸 dict/list 签名
- 无反向依赖（CLI → Host 仅通过 public DTO 与 `open_host`）
- 无兼容 wrapper
- 无 God function：职责按 `run_session_command`（入口/错误映射）→ `_run_session_command_async`（async orchestration）→ `_run_session_list`/`_run_session_purge`（具体命令）→ `_resolve_purge_target`/`_resolve_session_id_for_slot`（selector 解析）清晰收敛
- pyright: 0 errors（implementation report 记录）

## Open Questions

无。

## Residual Risk

- `session purge --label` 的 list-resolve 与 purge 之间存在 plan 明确允许的 TOCTOU 窗口；S4 已在错误输出中保留 selector、resolved session_id 与 Host code/message，最终状态以 Host purge precondition 为真源。
- `session resume` 仅冻结 parser shape，执行逻辑留给 S5。
- 仅运行了 S4 指定 CLI 测试（47 passed）与全项目 pyright；未运行全量 pytest。
