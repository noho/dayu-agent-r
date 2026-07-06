# WU-CLI-SMOKE-01 Display Semantics Fix

## 结论

本次问题真实存在，且严重性评估成立：`--thinking/--no-thinking` 已经被解析和文档化为 CLI 展示开关，但旧实现没有任何消费者，导致有 reasoning / thinking event 时两者输出完全相同。问题属于 UI 展示链路缺失，不是请求启用模型思考能力，也不应进入 Engine 执行配置裁决。

## Root Cause

- `dayu/cli/arg_parsing.py` 将 `detail` 默认值设为 `False`，只给 `prompt` 注册了 `--detail/--no-detail`，导致 `prompt` 默认不显示 activity，`interactive` 没有同等开关。
- `dayu/cli/agent_entrypoint.py` 的 `unsupported_execution_option_names(...)` 把 `--thinking/--no-thinking` 当作旧执行参数拒绝，实际语义错误地接近“模型思考能力请求”。
- `dayu/cli/run_view.py` 在 activity view 下收到 terminal result 时只写 transcript buffer，不输出 final answer；这会让运行态展示和最终回答展示边界不清晰。
- follow-up 根因：`EngineEventType.REASONING_DELTA` 在 Host ingest 中被当作 transient delta 接受后丢弃，不写 EventLog；`watch_session_events(session_id)` 基于 EventLog public read，因此 Service 和 CLI 没有可消费的 thinking public event。
- follow-up 根因：`entrypoint_runtime` 只有 activity callback，没有 thinking callback；`prompt` / `interactive` 也没有 thinking renderer，所以即使测试直接注入 Host public thinking event，`args.thinking` 仍不会改变输出。

## 改动

- 将 CLI parser 默认改为 `--thinking` 和 `--detail`，并将 thinking 参数文案改为终端展示语义。
- 为 `dayu-cli interactive` 补齐 `--detail/--no-detail`，与 `prompt` 对齐。
- 从 unsupported 旧执行参数集合中移除 `--thinking/--no-thinking`，确保它不再参与执行期模型配置裁决。
- 调整 interactive run view：默认 detail 路径可初始显示 activity；terminal result 到达后始终写 stdout/stderr 用户通道，并回到 transcript mode，activity 不进入 final transcript buffer。
- 在 Host public contract 中增加 `HostThinkingView`，让 `REASONING_DELTA` 写入 `PREVIEW` row，并由 read API 投影为独立 thinking view；content delta 与 tool-call delta 仍保持 transient，不污染最终 transcript 或 activity view。
- 在 Service `entrypoint_runtime` 中增加 `EntrypointThinking` 与 `on_thinking` callback，只消费 Host public thinking view，并按 run id / dedupe key 过滤。
- 新增 CLI thinking renderer；`prompt` 与 `interactive` 在 `--thinking` 下注册 thinking callback，在 `--no-thinking` 下不注册。renderer 只写 stderr 运行态展示，final answer 仍走原 terminal result 输出。
- 更新 CLI、Service、Host tests、README、Host/Service/tests README。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_thinking_renderer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime.py tests/host/test_engine_ingest_mapping.py tests/host/test_host_activity_event_projection.py -q`
  - `191 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli -q`
  - `224 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## 风险与未覆盖项

- `REASONING_DELTA` 现在会写入 `PREVIEW` EventLog row，目的是支持现有 public watcher 的最小投影路径；该 row 只投影为运行态 thinking view，不作为 final answer、activity 或 transcript 内容。
- CLI thinking renderer 当前按单行 stderr 展示增量并做 dedupe / 乱序过滤；如果未来需要 TTY 原地刷新，可以在 CLI UI adapter 内演进，不需要改 Engine 执行契约。
- activity 在非 TTY 捕获流中会作为默认 detail 输出到 stderr；stdout final answer 保持干净，activity 和 thinking 不写入 `--log-file`。

## Fix Gate Follow-up（2026-07-06）

### Gate

- Work unit: `WU-CLI-SMOKE-01`
- Gate: implementation/fix for accepted re-review findings
- Scope: 只修复总控裁决接受的 DS F01、MiMo F01、DS F03；不 commit、不 push、不创建 issue/PR。
- Artifact path: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`

### First-principles judgment

三个 accepted finding 的动机成立，但严重性均为 LOW：它们不改变 Host / Engine 公共契约，也不影响当前 final answer correctness。最佳修复路径是收窄现有实现状态机，而不是引入新的 pubsub、watcher 架构或 UI 抽象。

### Findings status

| Finding | 裁决 | Fix 状态 | 证据 |
| --- | --- | --- | --- |
| DS F01 LOW：`REASONING_DELTA` 在 `engine_ingest.py` early return 与 `_is_preview_event` 双重分类 | accepted | 已修复 | 保留 `_ingest_validated(...)` 中 `REASONING_DELTA` early return 作为唯一明确 handler，并从 `_is_preview_event(...)` 删除该分支。 |
| MiMo F01 LOW：interactive `--no-detail` 时冗余创建 unused `run_view` | accepted | 已修复 | `_run_interactive_repl(...)` 仅在 `detail=True` 且调用方未提供 `run_view` 时创建 `new_interactive_run_view(show_activity=True)`；`detail=False` 时直接用 `render_interactive_terminal_result(...)` 渲染 final answer。 |
| DS F03 LOW：interactive first SIGINT/cancel path 中 thinking renderer 生命周期不够显式 | accepted | 已修复 | `_cancel_interactive_turn_after_first_sigint(...)` 接收可选 `thinking_renderer`，进入 first SIGINT/cancel helper 后立即 `close()`；外层 finally 仍保留幂等关闭。 |
| DS F02 LOW：thinking 文本持久化在 `PREVIEW` EventLog row | deferred | 未修改 | 这是当前 watcher 架构下支持 live public thinking projection 的设计权衡；不在本 fix gate 引入新 pubsub 或重写持久化路径。Owner：后续 retention / purge / storage governance work unit。 |
| MiMo F02 LOW：`CliThinkingRenderer` 160 字符单行截断 | deferred | 未修改 | 当前保留运行态单行展示策略；完整可展开 thinking UI 属于后续 CLI UI 增强，不属于本 fix gate。 |

### Changed files in this fix gate

- `dayu/host/engine_ingest.py`
- `dayu/cli/commands/interactive.py`
- `tests/cli/test_interactive_command.py`
- `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`

### Tests added or updated

- 更新 `test_interactive_no_detail_omits_activity_and_keeps_final_answer_stdout`：验证 `--no-detail` 不创建 interactive run view factory，且 final answer 仍输出到 stdout。
- 更新 `test_cancel_after_first_sigint_returns_completed_submit_terminal`：验证 first SIGINT helper 会关闭 thinking renderer，后续 `record(...)` 不再输出。

### README decision

- 已检查 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`：本轮未新增 Host 公共契约、架构边界或稳定执行路径说明，不需要更新。
- 已检查 `tests/README.md`：当前 CLI thinking / interactive no-detail / cancel 覆盖已在现有测试分层说明内，不需要更新。

### Validation

- `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/host/test_engine_ingest_mapping.py -q`
  - `103 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli/test_thinking_renderer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime.py tests/host/test_engine_ingest_mapping.py tests/host/test_host_activity_event_projection.py -q`
  - `191 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli -q`
  - `224 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

### Residual risks

- DS F02 remains deferred: `REASONING_DELTA` thinking text is stored as `PREVIEW` row for live watcher projection. It does not enter final answer, activity, transcript, outbox terminal projection, or canonical replay, but future retention / purge governance should classify PREVIEW cleanup explicitly.
- MiMo F02 remains deferred: CLI thinking output remains single-line and truncated at the existing renderer limit. This is a display tradeoff, not a correctness issue.
- No unclassified residual risk remains for this fix gate.

## Prompt Thinking Lifecycle Follow-up（2026-07-06）

### Gate

- Work unit: `WU-CLI-SMOKE-01`
- Gate: follow-up implementation/fix for final DS re-review LOW finding
- Scope: 只修复 prompt cancel path thinking renderer lifecycle symmetry；不改变 PREVIEW row persistence，不改变 160 字符截断，不 commit、不 push、不创建 issue/PR。
- Artifact path: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`

### First-principles judgment

该 finding 动机成立但严重性为 LOW：当前 prompt path 已通过取消 `submit_task` 和外层 finally 保证安全，不会继续消费 thinking callback；但与 interactive 相同生命周期模式下，first local cancel/SIGINT helper 入口显式关闭 optional thinking renderer 更清晰，也降低未来维护者在 cancel path 复用 renderer 状态的风险。

### Findings status

| Finding | 裁决 | Fix 状态 | 证据 |
| --- | --- | --- | --- |
| Final DS LOW：`prompt.py` cancel path 未显式关闭 thinking renderer | accepted | 已修复 | `_cancel_prompt_turn_after_local_request(...)` 接收可选 `thinking_renderer`，helper 入口立即 `close()`；`_submit_prompt_turn_handling_sigint(...)` 在 Ctrl+C 与 Esc cancel 分支传入同一 renderer；外层 finally 保留幂等关闭。 |
| DS F02 LOW：thinking 文本持久化在 `PREVIEW` EventLog row | deferred | 未修改 | 继续保留当前 watcher 架构下的 PREVIEW projection 权衡。Owner：后续 retention / purge / storage governance work unit。 |
| MiMo F02 LOW：`CliThinkingRenderer` 160 字符单行截断 | deferred | 未修改 | 继续保留当前运行态单行展示策略；可展开 UI 不属于本 fix gate。 |

### Changed files in this follow-up

- `dayu/cli/commands/prompt.py`
- `tests/cli/test_prompt_command.py`
- `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`

### Tests added or updated

- 新增 `test_prompt_cancel_helper_closes_thinking_renderer`：直接覆盖 prompt local cancel helper 入口关闭 `CliThinkingRenderer`，并用 typed `EntrypointThinking` 验证后续 `record(...)` 不再输出。

### README decision

- 本轮只调整 CLI 内部 lifecycle 管理和已有 prompt 测试，不改变用户可见命令参数、输出通道、测试分层职责或 Host/Service 公共契约；`README.md`、`tests/README.md`、`dayu/host/README.md`、`dayu/service/README.md` 均不需要更新。

### Validation

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py -q`
  - `31 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_thinking_renderer.py -q`
  - `66 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli -q`
  - `225 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed after artifact update

### Residual risks

- DS F02 remains deferred: `REASONING_DELTA` thinking text is stored as `PREVIEW` row for live watcher projection. It does not enter final answer, activity, transcript, outbox terminal projection, or canonical replay, but future retention / purge governance should classify PREVIEW cleanup explicitly.
- MiMo F02 remains deferred: CLI thinking output remains single-line and truncated at the existing renderer limit. This remains a display tradeoff, not a correctness issue.
- No unclassified residual risk remains for this follow-up fix gate.

## Prompt Thinking Lifecycle Test-only Follow-up（2026-07-06）

### Gate

- Work unit: `WU-CLI-SMOKE-01`
- Gate: follow-up test-only fix for accepted DS LOW coverage finding
- Scope: 只补 `_submit_prompt_turn_handling_sigint(...) -> local cancel -> _cancel_prompt_turn_after_local_request(...) -> thinking renderer close` caller wiring 覆盖；不改生产代码，不改变 PREVIEW row persistence，不改变 160 字符截断，不 commit、不 push、不创建 issue/PR。
- Artifact path: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`

### First-principles judgment

该 finding 动机成立但严重性为 LOW：上一轮 helper 单测已经证明 close 行为本身正确，但缺少 caller wiring 覆盖，未来若 `_submit_prompt_turn_handling_sigint(...)` 的 Ctrl+C / Esc 分支漏传 `thinking_renderer`，helper 单测无法捕获。补一个 focused integration assertion 成本低，且直接防止同类回归。

### Findings status

| Finding | 裁决 | Fix 状态 | 证据 |
| --- | --- | --- | --- |
| DS LOW：缺少 `_submit_prompt_turn_handling_sigint(thinking_renderer=...)` 到 cancel helper 的 integration coverage | accepted | 已修复 | 扩展 `test_prompt_esc_requests_cancel_after_run_id`，传入真实 `CliThinkingRenderer`，走 `_submit_prompt_turn_handling_sigint(...)` 的 Esc cancel 分支；cancel path 返回后用 typed `EntrypointThinking` 调用 `record(...)`，断言 stderr 无输出。 |
| DS F02 LOW：thinking 文本持久化在 `PREVIEW` EventLog row | deferred | 未修改 | 继续保留当前 watcher 架构下的 PREVIEW projection 权衡。Owner：后续 retention / purge / storage governance work unit。 |
| MiMo F02 LOW：`CliThinkingRenderer` 160 字符单行截断 | deferred | 未修改 | 继续保留当前运行态单行展示策略；可展开 UI 不属于本 fix gate。 |

### Changed files in this follow-up

- `tests/cli/test_prompt_command.py`
- `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`

### Tests added or updated

- 更新 `test_prompt_esc_requests_cancel_after_run_id`：该测试现在传入真实 `CliThinkingRenderer`，覆盖 `_submit_prompt_turn_handling_sigint(...)` caller wiring，并在 cancel 返回后验证 `record(EntrypointThinking(...))` 是 no-op。

### README decision

- 本轮只补测试覆盖，不改变用户可见命令参数、输出通道、测试分层职责或公共契约；README 不需要更新。

### Validation

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py -q`
  - `31 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_thinking_renderer.py -q`
  - `66 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed after artifact update

### Residual risks

- DS F02 remains deferred: `REASONING_DELTA` thinking text is stored as `PREVIEW` row for live watcher projection. It does not enter final answer, activity, transcript, outbox terminal projection, or canonical replay, but future retention / purge governance should classify PREVIEW cleanup explicitly.
- MiMo F02 remains deferred: CLI thinking output remains single-line and truncated at the existing renderer limit. This remains a display tradeoff, not a correctness issue.
- No unclassified residual risk remains for this test-only follow-up.
