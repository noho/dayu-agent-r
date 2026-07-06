# WU-CLI-SMOKE-01 Display Semantics Final Re-Review

## Scope

- Mode: current changes (re-review after Codex fix gate)
- Branch: phase/host-issues-control
- Base: main
- Reviewer: AgentMiMo
- Timestamp: 20260706-204207
- Work unit: WU-CLI-SMOKE-01 follow-up display semantics
- Focus: 复核 Codex fix gate 后的最终 diff，验证 accepted findings 是否修好且无回归

## 上一轮 Accepted Findings 状态

| Finding | 上轮裁决 | 本轮验证状态 | 证据 |
| --- | --- | --- | --- |
| DS F01 LOW：`REASONING_DELTA` 在 `engine_ingest.py` early return 与 `_is_preview_event` 双重分类 | accepted | **已修复，无回归** | 见下方 Finding 1 详细证据 |
| MiMo F01 LOW：interactive `--no-detail` 时冗余创建 unused `run_view` | accepted | **已修复，无回归** | 见下方 Finding 2 详细证据 |
| DS F03 LOW：interactive first SIGINT/cancel path 中 thinking renderer 生命周期不够显式 | accepted | **已修复，无回归** | 见下方 Finding 3 详细证据 |

## Deferred Risks 状态

| Finding | 上轮裁决 | 本轮状态 | 说明 |
| --- | --- | --- | --- |
| DS F02 LOW：thinking 文本持久化在 `PREVIEW` EventLog row | deferred | 记录清楚，不需要当前 gate 修复 | Owner 明确为后续 retention / purge / storage governance work unit |
| MiMo F02 LOW：`CliThinkingRenderer` 160 字符单行截断 | deferred | 记录清楚，不需要当前 gate 修复 | 当前保留运行态单行展示策略；完整可展开 thinking UI 属于后续 CLI UI 增强 |

## Findings

未发现实质性问题。

以下为各 accepted finding 修复的详细验证：

### 验证 1：DS F01 — REASONING_DELTA 唯一 handler

- **文件**: `dayu/host/engine_ingest.py`
- **验证点**: `_ingest_validated()` 中 `REASONING_DELTA` early return 是唯一 handler，`_is_preview_event()` 不再包含该分支
- **直接证据**:
  - `_ingest_validated()` 第 897-901 行：`REASONING_DELTA` 在 dispatch 最前面以 early return 处理，调用 `_append_preview_event()` 写入 PREVIEW row 后返回 `_single_event_result(row)`
  - `_is_preview_event()` 第 4554-4582 行：只包含 `ITERATION_STARTED`、`CONTENT_COMPLETED`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE`、`ITERATION_COMPLETED` 七个分支，**无 `REASONING_DELTA`**
  - `_is_transient_delta_event()` 第 4585-4599 行：只包含 `CONTENT_DELTA` 和 `TOOL_CALL_DELTA`，**无 `REASONING_DELTA`**
- **路径完整性**: `_ingest_validated()` 的 dispatch 顺序保证 `REASONING_DELTA` 在 `_is_transient_delta_event()` 和 `_is_preview_event()` 之前命中，不存在 fallthrough 到后续分支的可能
- **结论**: 修复正确，REASONING_DELTA 有且仅有一个 handler

### 验证 2：MiMo F01 — interactive `--no-detail` 不创建 unused run_view

- **文件**: `dayu/cli/commands/interactive.py`
- **验证点**: `--no-detail` 时不创建 `run_view`，final answer 仍正确输出到 stdout
- **直接证据**:
  - `_run_interactive_repl()` 第 528-530 行：`if effective_run_view is None and detail:` — 只有 `detail=True` 且调用方未提供 `run_view` 时才创建 `new_interactive_run_view(show_activity=True)`
  - 第 557 行：`run_view=effective_run_view if detail else None` — `detail=False` 时传 `None` 给 `_submit_interactive_turn_handling_sigint`
  - 第 563-564 行：`if effective_run_view is None: render_exit_code = render_interactive_terminal_result(terminal)` — `--no-detail` 走此路径，直接用 `render_interactive_terminal_result` 渲染 final answer 到 stdout
  - 测试 `test_interactive_no_detail_omits_activity_and_keeps_final_answer_stdout`（第 1184-1219 行）验证：`--no-detail` 时 `run_view_factory_calls == []`（未调用工厂），`captured.out.strip() == "answer for run-1"`（stdout 正确）
- **结论**: 修复正确，`--no-detail` 路径无冗余对象创建

### 验证 3：DS F03 — first SIGINT/cancel path 显式关闭 thinking renderer

- **文件**: `dayu/cli/commands/interactive.py`
- **验证点**: `_cancel_interactive_turn_after_first_sigint()` 进入后立即关闭 thinking renderer
- **直接证据**:
  - `_cancel_interactive_turn_after_first_sigint()` 第 722-723 行：`if thinking_renderer is not None: thinking_renderer.close()` — 函数入口处显式关闭
  - `_submit_interactive_turn_handling_sigint()` 第 686-687 行：finally 块中 `if thinking is not None: thinking.close()` — 外层保留幂等关闭
  - 测试 `test_cancel_after_first_sigint_returns_completed_submit_terminal`（第 1719-1753 行）：
    - 构造 `CliThinkingRenderer(stderr=stderr, options=CliThinkingRendererOptions(enabled=True))`
    - 传入 `_cancel_interactive_turn_after_first_sigint(thinking_renderer=thinking_renderer)`
    - 返回后调用 `thinking_renderer.record(_entrypoint_thinking(dedupe_key="thinking-1"))`
    - 断言 `stderr.getvalue() == ""` — 证明 `close()` 后 `record()` 为 no-op，renderer 已被显式关闭
- **幂等性**: `_cancel_interactive_turn_after_first_sigint` 关闭后，外层 finally 的再次关闭是幂等的，无副作用
- **结论**: 修复正确，thinking renderer 生命周期在 first SIGINT 路径中显式管理

## Open Questions

无。

## Residual Risk

- DS F02 deferred：`REASONING_DELTA` thinking text 作为 `PREVIEW` row 持久化，用于 live watcher projection。不进入 final answer / activity / transcript / outbox terminal projection / canonical replay。后续 retention / purge governance 应显式分类 PREVIEW 清理。风险已被记录且有明确 owner。
- MiMo F02 deferred：CLI thinking 输出保持单行截断。这是展示权衡，不是正确性问题。已被记录且有明确 owner。
- 本轮 fix gate 未引入新的 residual risk。

## Verdict

**pass**

三个 accepted findings 均已正确修复，无回归。deferred risks 记录清楚且不需要当前 gate 修复。代码变更范围合理，测试覆盖了关键行为和 failure path。
