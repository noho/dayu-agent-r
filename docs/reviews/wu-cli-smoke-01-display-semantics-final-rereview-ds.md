# WU-CLI-SMOKE-01 Display Semantics — Adversarial Re-Review (AgentDS, Final)

## Scope

- Mode: current changes (adversarial re-review of Codex fix gate final diff)
- Role: AgentDS, Claude Code adversarial review lane
- Work unit: WU-CLI-SMOKE-01 follow-up display semantics
- Design sources of truth: `docs/host/design.md`, `docs/engine/design.md`
- Control document: `docs/host/issues-implementation-control.md`
- Prior fix gate artifact: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`
- Output file: `docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-ds.md`
- Review date: 2026-07-06

### Reviewed files

| File | Focus |
|---|---|
| `dayu/host/engine_ingest.py` | REASONING_DELTA ingest: dual classification, PREVIEW projection, _preview_payload |
| `dayu/cli/commands/interactive.py` | --no-detail run_view lifecycle, --thinking/--no-thinking renderer wiring, first SIGINT thinking close |
| `dayu/cli/commands/prompt.py` | thinking renderer wiring, cancel path consistency (cross-reference) |
| `dayu/cli/thinking.py` | CliThinkingRenderer.close() idempotency |
| `dayu/cli/run_view.py` | TerminalInteractiveRunView.close() idempotency |
| `dayu/host/read_api.py` | HostThinkingView projection from PREVIEW row |
| `tests/cli/test_interactive_command.py` | Fix-gate test additions |
| `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md` | Prior accepted findings baseline |

### Excluded scope

- Service layer changes (`entrypoint_runtime.py`) re-reviewed indirectly via their integration paths in CLI and Host tests; no standalone adversarial pass.
- `tests/cli/test_thinking_renderer.py`, `tests/cli/test_prompt_command.py` — verified passing but not individually re-reviewed line-by-line.

---

## Prior Accepted Findings Status

| Finding | Status in This Fix Gate | Evidence |
|---|---|---|
| DS F01 LOW: `REASONING_DELTA` 在 `engine_ingest.py` early return 与 `_is_preview_event` 双重分类 | **已修复** | `_ingest_validated()` L897-901: 专用 early return；`_is_transient_delta_event()` L4585-4599: REASONING_DELTA 已移除；`_is_preview_event()` L4554-4582: 不含 REASONING_DELTA。 |
| MiMo F01 LOW: interactive `--no-detail` 时冗余创建 unused `run_view` | **已修复** | `_run_interactive_repl()` L528-530: 仅 `detail=True` 且 `run_view=None` 时创建；`detail=False` 时不创建且直接调用 `render_interactive_terminal_result()`。 |
| DS F03 LOW: interactive first SIGINT/cancel path 中 thinking renderer 生命周期不够显式 | **已修复** | `_cancel_interactive_turn_after_first_sigint()` L722-723: 进入后立即 `thinking_renderer.close()`；外层 finally L686-687 幂等关闭。 |
| DS F02 LOW: thinking 文本持久化在 `PREVIEW` EventLog row | **deferred**（合理） | 后续 retention/purge/storage governance work unit 处理。不属于本 fix gate。 |
| MiMo F02 LOW: `CliThinkingRenderer` 160 字符单行截断 | **deferred**（合理） | CLI UI 增强后续 work unit 处理。不属于本 fix gate。 |

---

## Findings

### 1-未修复-低-prompt.py cancel 路径未显式关闭 thinking renderer（与 interactive 不对称）

- **入口/函数**: `_cancel_prompt_turn_after_local_request`（prompt.py L487）
- **文件(行号)**: `dayu/cli/commands/prompt.py:487-526`
- **输入场景**: prompt 命令运行态第一次 SIGINT 或 Esc 取消。
- **实际分支**: `_cancel_prompt_turn_after_local_request` 不接收 `thinking_renderer` 参数；仅依赖外层 finally `_submit_prompt_turn_handling_sigint` L479-480 关闭。
- **预期行为**: 与 interactive 一致，cancel helper 入口显式关闭 thinking renderer，防止异步等待期间（如 `_cancel_prompt_run_waiting_for_terminal_or_second_sigint` L529-584）thinking 增量泄露。
- **实际行为**: prompt cancel 路径先 cancel `submit_task`（L512-514）再进入异步等待。由于 submit_task 取消后 Service watcher 已停止，不会有新的 thinking event 到达 renders，因此 thinking renderer 开放期间无实际泄露。行为当前正确，但生命周期控制不对称。
- **直接证据**: `_cancel_prompt_turn_after_local_request` 签名 L487-495：无 `thinking_renderer` 参数。对比 `_cancel_interactive_turn_after_first_sigint` 签名 L694-704：有 `thinking_renderer` 参数并在 L722-723 显式关闭。
- **影响**: 当前无运行时影响（submit_task 已取消）。但如果后续 prompt cancel 路径重构为不立即取消 submit_task（例如先等待 run_id 再取消），thinking 增量可能在异步等待期间泄露到 stderr。
- **建议改法和验证点**: 不要求本 gate 修复。建议在后续 prompt cancel 路径改动时，将 `thinking_renderer` 作为显式参数传入 cancel helper，并在入口处关闭，与 interactive 保持一致。当前行为正确，仅标记为 maintainability asymmetry。
- **修复风险（低）**: 本 gate 不修复，无需评估。
- **严重程度（低）**: 当前行为正确，仅结构性不对称。

---

## Open Questions

无。

---

## Residual Risk

1. **prompt/interactive thinking close 不对称**：见 Finding 1。prompt cancel helper 未显式传入 `thinking_renderer`，依赖外层 finally。当前安全（submit_task 先 cancel），但重构风险存在。

2. **DS F02 deferred**：PREVIEW EventLog row 中的 thinking 文本缺乏独立的 retention/purge 治理。后续 work unit 需要明确清理策略。

3. **MiMo F02 deferred**：CLI thinking 输出保持单行 160 字符截断。后续 TTY 原地刷新等增强需要 UI adapter 层演进。

4. **`_new_thinking_renderer` 代码重复**：`interactive.py:428` 和 `prompt.py:322` 分别定义了相同的函数。两个模块均属于 `dayu.cli.commands` 包，可抽取为共享 helper。当前无功能影响，标记为 maintainability note。

5. **Test coverage note**：测试验证了 thinking/no-thinking 输出差异、no-detail 不创建 run_view、cancel 后 thinking close 不输出。但 `test_interactive_no_detail_omits_activity_and_keeps_final_answer_stdout` 使用 mock `new_interactive_run_view` 验证 factory 未被调用，而非验证运行态行为。已通过 `test_interactive_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it`（端到端 FakeHost 注入 thinking event）补充覆盖。

---

## Verdict

**pass**

所有三个 accepted fix-gate findings 均已正确修复，证据确凿。REASONING_DELTA 双重分类已消除，`--no-detail` 不再创建 unused run_view，first SIGINT/cancel path 显式关闭 thinking renderer 且双层关闭幂等安全。Deferred risks 合理分类，不应当前 gate 修复。无 blocking 或 required-fix 发现。

