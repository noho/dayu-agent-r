# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2a

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: HEAD (已提交 batch D1 b13caa1d)
- Output file: docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-code-review-ds.md
- Included scope: D2a workspace changes only（20 个文件，见 diff stat）
- Excluded scope: D2b batch（cancelled raw_tool_outcome, compaction evidence_kind, memory session summary/fallback, reactive compact budget）
- Parallel review coverage: 无

## Review Method

沿以下链路逐条走读：

1. `TERMINAL_RUN_STATUSES` / `is_terminal_run_status` → Host public contract → durable state 委托 → Service 消费者
2. `RunSnapshot.__post_init__` / `TerminalResultSummary.__post_init__` → durable `_terminal_result_summary_from_status` → Service fake construction
3. `decode_run_started_payload` → `count_recovery_dispatches_for_run` → `_resume_wait_messages_from_current_start` → `_runner_call_kind_and_trigger`
4. `WaitPollerRuntimePolicy` Protocol → `_validate_wait_poller_policy` → `OpenHostOptions.__post_init__` → `open_host._enabled_wait_poller_configuration`
5. `HostToolingOptions` wait registry Protocols → `HostToolingOptions.__post_init__`
6. 所有 `RunSnapshot(...)` 构造点（生产 + 测试），按终态约束逐行检查

## Findings

### D2a-F1-未修复-中-CLI 测试固定件未适配 RunSnapshot 终态约束

- **入口/函数**: `_run_snapshot` helper
- **文件(行号)**:
  - `tests/cli/test_prompt_command.py:2234-2253`
  - `tests/cli/test_interactive_command.py:2314-2333`
- **输入场景**: `_FakeHost` 使用默认 `run_statuses=(RunStatus.SUCCEEDED,)`（或任何终态值）时，`get_run` 路径调用 `_run_snapshot(run_id=run_id, status=RunStatus.SUCCEEDED)`，该 helper 始终传 `terminal_result_summary=None`。
- **实际分支**: `RunSnapshot.__post_init__` 判定 `is_terminal_run_status(RunStatus.SUCCEEDED)` 为 True → 进入 `if self.terminal_result_summary is None: raise ValueError("...required for terminal status")`（`dayu/host/api.py:2458-2461`）。
- **预期行为**: 与 Service 测试固定件 `tests/service/test_entrypoint_runtime.py:2032-2043` 已做适配一致 —— 当 status 为终态时构造匹配的 `TerminalResultSummary`。
- **直接证据**:
  - `tests/cli/test_prompt_command.py:2248` — `terminal_result_summary=None`（无条件）
  - `tests/cli/test_prompt_command.py:256` — 默认 `run_statuses=(RunStatus.SUCCEEDED,)`（终态）
  - `tests/cli/test_prompt_command.py:1260` — 显式 `run_statuses=(RunStatus.SUCCEEDED,)`
  - `tests/cli/test_interactive_command.py:2328` — `terminal_result_summary=None`（无条件）
  - `tests/cli/test_interactive_command.py:206` — 默认 `run_statuses=(RunStatus.SUCCEEDED,)`（终态）
- **影响**: 所有使用终态 status 的 CLI 测试在 `RunSnapshot` 构造期抛 `ValueError` 失败。控制器的 `pytest` 命令仅覆盖 `tests/host/` 与 `tests/service/`，未包含 `tests/cli/`，故未检出。
- **建议改法和验证点**:
  - 按 `tests/service/test_entrypoint_runtime.py:2032-2043` 模式改写两个 CLI `_run_snapshot` helper：当 `is_terminal_run_status(status)` 时构造 `TerminalResultSummary(status=status, summary_ref=None, summary_digest=None)`。
  - 改写后运行 `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` 确认通过。
  - 改写后复核 pyright 零报错。
- **修复风险（低）**: 改动局限于测试固定件，不触及生产代码；改动模式与已完成的 Service 测试适配完全一致。
- **严重程度（中）**:

## Open Questions

无。

## Residual Risk

- **CLI 测试覆盖缺口**: 控制器的 D2a 验证命令 `pytest tests/host/... tests/service/...` 未包含 `tests/cli/`，导致 D2a-F1 未被检出。建议 D2b 或后续 batch 的控制器验证命令包含 `tests/cli/` 或全量 `tests/`。
- **`_FakeHost` 其他变体**: 若 `tests/cli/` 下还有其它 `_FakeHost` 子类或变体使用默认终态 `run_statuses`，同样受影响。建议在修复 D2a-F1 时对 `tests/cli/` 下所有 `_run_snapshot` 调用做一次全局 grep 确认。
- **`_terminal_result_summary_from_status` 不投影 durable terminal refs**: `RunRow` 有 `terminal_event_id` / `terminal_event_sequence` 字段，但 `_terminal_result_summary_from_status` 始终创建 `TerminalResultSummary(summary_ref=None, summary_digest=None)`。当前 `TerminalResultSummary.summary_ref` 设计为 artifact-level 引用（非 lifecycle event id），故语义无误。此模式已在 D1 batch 引入，不属于 D2a 引入，但需关注未来若 artifact 系统需要填充 summary_ref 时是否会与现有投影路径冲突。
