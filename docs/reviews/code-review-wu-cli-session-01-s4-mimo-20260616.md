# Code Review: WU-CLI-SESSION-01 S4

## Scope

- Mode: current changes
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-review-wu-cli-session-01-s4-mimo-20260616.md`
- Included scope:
  - `dayu/cli/arg_parsing.py`
  - `dayu/cli/main.py`
  - `dayu/cli/commands/session.py`（新增）
  - `dayu/cli/host_context.py`
  - `dayu/cli/output.py`
  - `tests/cli/test_arg_parsing.py`
  - `tests/cli/test_session_command.py`
  - `tests/README.md`
  - `docs/reviews/wu-cli-session-01-s4-implementation-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Detail

### 1. session list / purge 是否只通过 Host public API

- `session list` 调用 `host.list_sessions()`（`session.py:199`），返回后直接渲染。
- `session purge` 调用 `host.purge_session(target.session_id, request)`（`session.py:232`）。
- `_FakeSessionHost` 追踪 `close_cancel_calls`，测试断言 `host.close_cancel_calls == 0`（`test_session_command.py:1292`），确认不自动 close/cancel。
- 测试断言 `host.calls == ["list_sessions"]` 和 `host.calls == ["purge:session-1"]`（`test_session_command.py:1119,1180`），确认只调用预期 API。
- **结论**：只通过 Host public API，不读 durable，不自动 close/cancel。

### 2. runtime assembly 是否真实可用且不伪装 LLM scene

- `_prepare_session_runtime` 使用 `scene_id=CLI_PROMPT_SCENARIO`（即 `"prompt"`）（`session.py:182`），这是已有 prompt manifest 的 scene id。
- 测试 `_assert_session_runtime_uses_prompt_carrier` 断言 `request.scene_id == "prompt"` 且包含 `prompt.json` 所需的 `fins_default_subject` / `base_user` slots（`test_session_command.py:1473-1477`），确认 carrier 真实可用。
- Host 调用上下文使用 `build_session_host_context(invocation, operation=_PURGE_OPERATION)`（`session.py:224-227`），`operation_kind=CLI_SESSION_OPERATION_KIND`（`host_context.py:377`），是 cli_session 语义而非 prompt scene。
- **结论**：prompt manifest 只是 Host opener carrier；Host context 使用 cli_session operation 语义。

### 3. parser shape 是否包含 list/resume/purge，resume 是否 not implemented

- `_register_session_command` 注册 list、resume、purge 三个 action（`arg_parsing.py:153-155`）。
- `COMMAND_HELP_EXPECTATIONS["session"]` 包含 `("list", "resume", "purge")`（`test_arg_parsing.py:76`）。
- `run_session_command` 对 `SESSION_ACTION_RESUME` 直接返回 `EXIT_NOT_IMPLEMENTED`（`session.py:105-107`）。
- 测试 `test_session_resume_execution_is_left_not_implemented` 验证 exit code 和 stderr（`test_session_command.py:1353-1377`）。
- **结论**：parser shape 完整，resume 只返回 not implemented。

### 4. purge selector 解析

- `--session-id` 和 `--label` 在 mutually exclusive group 中，`required=True`（`arg_parsing.py:280`）。
- `--session-id` 直 purge：`_resolve_purge_target` 返回 `_PurgeTarget(resolved_from_label=False)`（`session.py:263-267`）。
- `--label` + `--kind`：先 `_require_label_kind` 校验 kind，再 `slot_ref_for_cli_label` 构造 slot，再 `_resolve_session_id_for_slot` 通过 `list_sessions` 匹配 slot（`session.py:275-286`）。
- 缺 `--kind`：`_require_label_kind` 抛 `CliSessionUsageError("--label requires --kind prompt|interactive")`（`session.py:318`）。
- 找不到 label：`CliSessionUsageError("no session found for label ... kind ...")`（`session.py:279-281`）。
- **结论**：selector 解析完整且 fail closed。

### 5. TOCTOU Host error stderr 是否包含原始 selector / resolved session_id / Host code/message

- `_purge_host_error_message` 格式为 `selector={target.selector} session_id={target.session_id} host_code=... host_message=...`（`session.py:366-368`）。
- 测试 `test_session_purge_by_label_toctou_error_includes_selector_and_host_context` 断言 `"--label proj.v1 --kind prompt"`、`"session-A"`、`"conflict"`、`"slot changed before purge"` 均出现在 stderr（`test_session_command.py:1346-1349`）。
- **结论**：TOCTOU 错误上下文完整。

### 6. INVALID_STATE 是否说明 closed + terminal Runs 且不 close/cancel

- `_purge_host_error_message` 对 `INVALID_STATE` 输出 `"purge requires a closed Session with terminal Runs; no close/cancel was attempted"`（`session.py:361-363`）。
- 测试断言 `"closed Session"`、`"terminal Runs"`、`"no close/cancel"` 均在 stderr（`test_session_command.py:1287-1289`）。
- **结论**：正确说明前置条件且不 close/cancel。

### 7. PurgeSessionRequest client_request_id / reason / context

- `client_request_id` 使用 `session_purge_client_request_id(invocation)`，格式 `dayu-cli:session:{invocation_id}:session:purge`（`host_context.py:151-153`）。
- `reason` 使用用户 `--reason` 或默认 `DEFAULT_PURGE_REASON = "cli_session_purge"`（`session.py:341`）。
- `context` 使用 `build_session_host_context(invocation, operation=_PURGE_OPERATION)`（`session.py:224-227`）。
- 显式参数（reason、client_request_id、context）通过 `PurgeSessionRequest` 字段传递，不塞 extra payload。
- 测试断言 `request.reason == "cleanup"`、`request.client_request_id.startswith("dayu-cli:session:")`、`request.client_request_id.endswith(":session:purge")`（`test_session_command.py:1184-1186`）。
- **结论**：参数稳定且不违反 AGENTS 约束。

### 8. 测试是否覆盖真实风险

- carrier regression：`_assert_session_runtime_uses_prompt_carrier` 断言 scene_id 和 required slots（`test_session_command.py:1463-1477`）。
- purge by session id、purge by label、缺 `--yes`、INVALID_STATE、TOCTOU、resume not implemented 均有独立测试。
- `close_cancel_calls == 0` 确认不自动 close/cancel。
- **结论**：测试覆盖真实风险。

### 9. 类型签名 / docstring / AGENTS 约束

- 所有新增函数和类均有完整中文 docstring。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `_PurgeTarget` 为 `frozen=True, slots=True` dataclass（`session.py:83`）。
- `_FakeSessionHost.close_session` / `cancel_session_runs` 参数签名 `() -> None` 与 Host Protocol 一致。
- `_session_context_slot_values` 返回 `dict[str, JsonValue]`，不使用裸 dict。
- **结论**：符合 AGENTS 约束。

## Open Questions

无。

## Residual Risk

- `--kind` 可在无 `--label` 时传入（parser 层面不强制），但代码通过 `_require_label_kind` 只在 `--label` 路径校验，不会产生错误行为。这是 argparse 对条件必填参数的常见处理方式。
- `session purge --label` 的 list-resolve 与 purge 之间存在 TOCTOU，plan 已记录为可接受，Host purge precondition 是最终 truth。
- 仅运行 S4 指定测试（47 passed）与全项目 pyright（0 errors），未运行全量 pytest。
