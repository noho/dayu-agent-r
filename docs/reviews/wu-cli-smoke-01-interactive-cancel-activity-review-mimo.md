# Code Review — interactive cancel/activity 修复 (AgentMiMo)

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`（未提交 diff）
- Output file: `docs/reviews/wu-cli-smoke-01-interactive-cancel-activity-review-mimo.md`
- Included scope: `dayu/cli/output.py`, `dayu/cli/run_view.py`, `dayu/host/durable/run_transition.py`, `dayu/host/read_api.py`, `dayu/host/waiting.py`, `tests/cli/test_interactive_run_view.py`, `tests/host/test_host_activity_event_projection.py`, `tests/host/test_resolve_wait_command.py`
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

### F-1-未修复-低-_failed_wait_terminal_message 的 hint 拼接分支无测试覆盖

- **入口/函数**: `_failed_wait_terminal_message`
- **文件(行号)**: `dayu/host/waiting.py:1329-1339`
- **输入场景**: `outcome.result.hint is not None` 时走 `f"{outcome.result.message} {outcome.result.hint}"` 分支。
- **实际分支**: 当前 `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` 的 `_failed_request` fixture 使用 `hint=None`（`tests/host/test_resolve_wait_command.py:643`），只覆盖 `hint is None` 分支。
- **预期行为**: 两个分支均应有测试覆盖，尤其是 hint 拼接逻辑（字符串拼接格式、空格分隔）属于可回归的显式行为。
- **实际行为**: `hint is not None` 分支从未被执行。`f"{outcome.result.message} {outcome.result.hint}"` 的空格拼接格式无断言保护。
- **直接证据**: `tests/host/test_resolve_wait_command.py:643` — `hint=None`；全文搜索无其它 `hint=` 非 None fixture。
- **影响**: 若 hint 拼接格式变更（如分隔符、换行），无测试捕获回归。当前功能正确，风险低。
- **建议改法和验证点**: 在 `_failed_request` 中增加一个 `hint="try again"` 的变体，断言 `failed_payload["message"] == "provider failed try again"`。
- **修复风险（低）**: 仅补充测试 fixture。
- **严重程度（低）**: 功能正确，仅测试覆盖缺口。

## 公共投影规则审查

### ATTEMPT_STARTED 不上层可见

**正确。** `_activity_from_row`（`read_api.py:1078-1084`）的 lifecycle allowlist 从 `_EVENT_TYPE_RUN_ACCEPTED, _EVENT_TYPE_RUN_QUEUED, _EVENT_TYPE_RUN_STARTED, _EVENT_TYPE_ATTEMPT_STARTED, _EVENT_TYPE_RUN_RECOVERING` 收窄为去除 `_EVENT_TYPE_ATTEMPT_STARTED`。`ATTEMPT_STARTED` 是 `admission.py:3391` 发出的 attempt 治理 canonical fact，不携带用户可读语义，移除合理。

`_run_lifecycle_activity`（`read_api.py:1130-1135`）对应去除 `_EVENT_TYPE_ATTEMPT_STARTED` 分支，`elif row.event_type == _EVENT_TYPE_RUN_STARTED` 仍保留。`None` 兜底仍存在（`read_api.py:1139+`）。✓

测试 `test_non_terminal_run_lifecycle_activity_projection` 新增 `ATTEMPT_STARTED` 投影断言 `assert attempt_started.activity is None`。✓

### TOOL_AWAITING 为唯一 waiting activity，RUN_WAITING 不重复投影

**正确。** `_activity_from_row`（`read_api.py:1091-1092`）从 `row.event_type in (_EVENT_TYPE_TOOL_AWAITING, _EVENT_TYPE_RUN_WAITING)` 收窄为 `row.event_type == _EVENT_TYPE_TOOL_AWAITING`。

`RUN_WAITING` 仍作为 canonical fact 发出（`engine_ingest.py:3453`, `waiting.py:1795`），仍存在于 timeline read model（`read_model.py:75`），仍存在于 tool trace canonical 列表（`tool_trace.py:209`）。仅 activity 投影层不再重复展示，避免同一等待产生两个 activity 条目。✓

`_tool_awaiting_activity` docstring 更新为只接收 `TOOL_AWAITING` row。✓

测试 `test_tool_awaiting_projects_activity_and_run_waiting_stays_silent` 断言 `run_waiting.activity is None`，名称精确描述行为。✓

### 架构分层评估

投影层收敛正确：`RUN_WAITING` 是 Host 内部 canonical fact（记录 wait 创建事件），`TOOL_AWAITING` 是面向工具等待的 activity 投影源。两者解耦后，activity 层只展示一条等待记录，不泄漏 Host 内部事件治理细节。符合 CLAUDE.md「不得把系统状态、调度状态、Host / Engine 内部治理信息伪装成财报事实、业务事实或用户可见结论」。

## Waiting failed/lost terminal message 审查

### 从同源 outcome 贯通是否架构正确

**正确。** 数据链路：

1. `ResolveWaitFailedOutcome.result: ToolResultFailure` → `ToolResultFailure.message: str` + `ToolResultFailure.hint: str | None`（`tool_result.py:78-107`）
2. `_failed_wait_terminal_message(outcome)` → 拼接 `message` + 可选 `hint`（`waiting.py:1329-1339`）
3. `WaitingRunTerminalInput(message=...)` 新增字段（`run_transition.py:654`）
4. `_waiting_run_terminal_event_request` 条件写入 `payload["message"]`（`run_transition.py:3811-3812`）
5. `_validate_waiting_terminal_input` 校验 `_require_optional_non_empty_text`（`run_transition.py:6002`）

同源：failed/lost 的 message 始终来自 `ResolveWaitFailedOutcome.result` / `ResolveWaitLostOutcome.message`，不经过中间转换或外部注入。✓

### schema/类型安全

- `WaitingRunTerminalInput.message: str | None` — 类型正确，`None` 表示不写入 payload。✓
- `_require_optional_non_empty_text` 校验非空字符串或 `None`。✓
- `isinstance` 守卫（`waiting.py:1001-1002`, `1067-1068`）确保 failed path 只接收 `ResolveWaitFailedOutcome`，lost path 只接收 `ResolveWaitLostOutcome`。✓
- payload 构造条件写入：`if request.message is not None`，避免 payload 出现 `null` 值。✓

### 测试验证

- `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` 新增 payload message 断言：
  - `failed_payload["message"] == "provider failed"`（来自 `ToolResultFailure.message`，`hint=None`）
  - `lost_payload["message"] == "adapter cannot confirm external job"`（来自 `ResolveWaitLostOutcome.message`）
- `_single_event` helper 简化断言写法，`assert len(matched) == 1` 保证唯一性。✓

## CLI SIGINT 用户回显审查

### 只在 CLI 输出层映射是否合理

**合理。** `_public_cancel_message`（`output.py:143-156`）是纯函数映射：

- `cancel_reason == CLI_SIGINT_REASON` → `_USER_CANCELLED_MESSAGE = "Cancelled."`
- 其它 → `cancel_reason or _CANCELLED_FALLBACK_MESSAGE`

映射点在 `render_prompt_terminal_result`（`output.py:97`）和 `render_interactive_terminal_result`（`output.py:137`），均为 CLI 输出层。Host 内部 `cancel_reason` 保持 `"cli_sigint"` 原始值，不被覆盖。符合 CLAUDE.md LLM-facing 文义约束的 spirit：内部治理标识不暴露给终端用户。✓

fallback 路径安全：`cancel_reason or _CANCELLED_FALLBACK_MESSAGE` 覆盖 `None` 和非 `CLI_SIGINT_REASON` 的情况。✓

测试覆盖：
- `test_prompt_terminal_result_hides_internal_sigint_reason` — prompt 路径，断言 `stderr == "Cancelled.\n"`。✓
- `test_interactive_terminal_result_hides_internal_sigint_reason` — interactive 路径，断言 `stderr == "Cancelled.\n"`。✓

## Interactive detail 默认模式审查

### _default_mode 保持是否有副作用

**无副作用。** `run_view.py` 变更：

- 新增 `_default_mode` 字段（`run_view.py:169`），在 `__init__` 中设置为 `initial_mode`（启用时）或 `TRANSCRIPT`（未启用时）。
- `render_terminal_result` 结束后从 `self._mode = InteractiveRunViewMode.TRANSCRIPT` 改为 `self._mode = self._default_mode`（`run_view.py:323`）。

语义：用户配置 `initial_mode=ACTIVITY` 时，单轮结束后不静默降级为 TRANSCRIPT，保持用户选择的展示模式。未配置时仍默认 TRANSCRIPT，行为不变。✓

测试覆盖：
- `test_run_view_activity_mode_outputs_terminal_and_returns_to_default_mode` — 原测试更新名称和断言。✓
- `test_run_view_detail_mode_keeps_activity_after_terminal_result` — 新增测试，配置 `initial_mode=ACTIVITY`，断言 `view.mode is InteractiveRunViewMode.ACTIVITY` 且 activity sink 仍可记录。✓

## Open Questions

无。

## Residual Risk

- `_failed_wait_terminal_message` 的 `hint is not None` 分支无直接测试覆盖（见 F-1）。功能正确，风险低。
- 本轮未涉及 `RUN_WAITING` 在 timeline / trace 层的投影变更，仅收窄 activity 投影。已验证 `read_model.py` 和 `tool_trace.py` 未受影响。

## 结论

**PASS.**

四项审查点均正确收敛：

1. **公共投影规则**：`ATTEMPT_STARTED` 不上层可见（治理事件静默），`TOOL_AWAITING` 为唯一 waiting activity（`RUN_WAITING` 保留 canonical 但不重复投影），符合 Host 架构分层约束。
2. **waiting failed/lost terminal message**：从同源 `ResolveWaitFailedOutcome.result` / `ResolveWaitLostOutcome.message` 贯通到 `RUN_FAILED` / `RUN_LOST` payload，`isinstance` 守卫 + `_require_optional_non_empty_text` 校验 + 条件写入保证类型安全。
3. **CLI SIGINT 用户回显**：`_public_cancel_message` 在 CLI 输出层映射，Host 内部 reason 不被覆盖，测试覆盖 prompt 和 interactive 两条路径。
4. **interactive detail 默认模式**：`_default_mode` 保持用户配置，不静默降级，测试覆盖。

38 项受影响测试全部通过，pyright 0 errors。存在一个低严重度测试缺口（F-1：hint 拼接分支无覆盖），不阻塞 ship。
