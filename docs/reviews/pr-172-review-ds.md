# PR Review — Draft PR #172

## Gate

- **Review type**: adversarial PR review (AgentDS)
- **Date**: 2026-07-06
- **PR**: https://github.com/noho/dayu-agent-r/pull/172
- **Branch**: `phase/host-issues-control` → `main`
- **Work unit**: WU-CLI-SMOKE-01 dayu-cli core usability smoke and display semantics
- **Design sources**: `docs/host/design.md` (line 1602 mapping table), `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`

## Scope

Full PR diff (62 files, +5695/−112) against `main`. Focused adversarial review on the five specified challenge areas. Key implementation files reviewed:

- `dayu/cli/arg_parsing.py`, `dayu/cli/agent_entrypoint.py`, `dayu/cli/commands/prompt.py`, `dayu/cli/commands/interactive.py`
- `dayu/cli/run_view.py`, `dayu/cli/thinking.py`
- `dayu/host/api.py` (HostThinkingView, HostEvent.thinking), `dayu/host/engine_ingest.py`, `dayu/host/read_api.py`
- `dayu/host/durable/state.py` (WaitSnapshotRef snapshot_digest hardening)
- `dayu/service/entrypoint_runtime.py` (EntrypointThinking, on_thinking callback)
- `tests/cli/test_thinking_renderer.py`, `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py`, `tests/cli/test_interactive_run_view.py`, `tests/cli/test_arg_parsing.py`
- `tests/service/test_entrypoint_runtime.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_toolruntime_executor.py`, `tests/host/test_wait_awaiting_accept.py`, `tests/host/test_wait_record_state.py`
- `docs/host/issues-implementation-control.md`, `docs/host/wu-cli-smoke-01-dayu-cli-core-usability-plan.md`
- Review chain artifacts (`docs/reviews/wu-cli-smoke-01-*`)

## Findings

### DS-F01-未修复-中-设计真源 EventLog 映射表与 REASONING_DELTA PREVIEW row 实现不一致

- **入口/函数**: `Host.engine_ingest._ingest_validated(...)` / `_is_transient_delta_event(...)`
- **文件(行号)**: `dayu/host/engine_ingest.py:897-923` (新 PREVIEW row 写入), `dayu/host/engine_ingest.py:4593-4601` (从 transient 集合移除 REASONING_DELTA), `docs/host/design.md:1602` (设计真源映射表)
- **输入场景**: Engine 产生 `EngineEventType.REASONING_DELTA` 事件。
- **实际分支**: 实现现在将 REASONING_DELTA 从 transient delta 集合中移除，并在 `_ingest_validated` 中显式写入 EventLog PREVIEW row（event_class=PREVIEW，event_type="REASONING_DELTA"）。Host README 已更新以反映这一行为（第 534 行："reasoning delta 写入 PREVIEW row 只用于 live thinking 展示"）。
- **预期行为**: 设计真源 `docs/host/design.md` 第 1602 行的 EngineEvent 映射表明确规定 `reasoning_delta -> accepted non-durable delta; no EventLog row by default`。
- **实际行为**: 实现现在为 REASONING_DELTA 写入 PREVIEW row，这与设计真源的映射表表项矛盾。尽管设计真源的通用原则（第 1444 行 "preview event 可以进入 Host event stream"）与 PREVIEW 行为兼容，但具体表项现在已过时。
- **直接证据**:
  - 设计真源 `docs/host/design.md:1602`: `reasoning_delta -> accepted non-durable delta; no EventLog row by default`
  - 实现 `engine_ingest.py:897-903`: `if event.type == EngineEventType.REASONING_DELTA: row = self._append_preview_event(transaction, context)`
  - Host README `README.md:534`: 已正确反映新行为
  - Control doc `issues-implementation-control.md:233`: WU-CLI-SMOKE-01-R1 承认 PREVIEW row 持久化，但将其推迟到 retention
- **影响**: 可维护性风险。未来开发者阅读设计真源时，会期望 REASONING_DELTA 不生成 EventLog row。如果后续有人依据设计真源将 REASONING_DELTA 恢复为 transient 处理，HostEvent projection、Service callback 和 CLI thinking renderer 都会静默断裂（thinking 输出消失，无错误——因为 on_thinking=None 是合法配置）。影响分类为"中"而非"高"，因为 control doc 和 Host README 正确记录了当前行为，且 review chain 明确接受了这一设计变更。
- **建议改法和验证点**:
  1. 将 `docs/host/design.md` 第 1602 行更新为 `reasoning_delta -> preview (live thinking display only); transient delta 子集已缩小为 content_delta 和 tool_call_delta`
  2. 可选：在 design.md 第 1593 行附近的 per-delta EngineEvent 章节中添加注释，解释 reasoning delta 现在由于 live thinking projection 需求而生成 PREVIEW row
  3. 验证：确认设计真源更新后，实现行为和设计真源之间不再有矛盾
- **修复风险**: 低。设计真源更新是文档级变更，无生产影响。
- **严重程度**: 中

### DS-F02-未修复-低-`_validate_host_event_terminal_payload` thinking 防卫检查无测试覆盖

- **入口/函数**: `HostEvent.__post_init__()` → `_validate_host_event_terminal_payload(...)`
- **文件(行号)**: `dayu/host/api.py:3115-3116`
- **输入场景**: 具有 `kind in HOST_EVENT_TERMINAL_KINDS` 和 `thinking is not None` 的 HostEvent。
- **实际分支**: `_validate_host_event_terminal_payload` 在第 3115 行检查：`if event.thinking is not None: raise ValueError("HostEvent terminal kind must not include thinking")`。如果 REASONING_DELTA PREVIEW row 错误地映射到终端事件（例如，未来 EventLog schema 迁移或投影错误），会触发此 panic。
- **预期行为**: 只要 event_class 和 kind 映射保持正确，此防卫检查在生产中永远不会触发。仍然值得测试：if 分支和 defensive `raise` 都未被执行。
- **直接证据**:
  - `tests/host/test_host_activity_event_projection.py:753-758` 测试 non-terminal REASONING_DELTA 的 thinking 投影（happy path）。无测试验证将 thinking 放入 terminal HostEvent 是否被拒绝。
  - `_validate_host_event_terminal_payload` 函数本身有 3 个检查（host event terminal validation 的三元组）—— thinking 检查，`HostFinalAnswerView` 检查和 `terminal_status` 检查。前两个在测试中未被执行。
- **影响**: 极低——在生产中这永远不会被触发。缺失的测试是防御性覆盖，而非行为缺口。但如果未来有人向 terminal event payload 错误添加 thinking 字段，此防卫会 panic 而不是静默损坏 terminal projection。
- **建议改法和验证点**:
  1. 添加测试：构造一个在非 None thinking 上的 terminal-kind HostEvent，断言抛出 `ValueError` 且消息包含 "terminal kind must not include thinking"
  2. 对 HostFinalAnswerView 检查同样
  3. 验证：在 `tests/host/test_host_activity_event_projection.py` 中运行受影响的测试
- **修复风险**: 低。仅测试新增。
- **严重程度**: 低

### DS-F03-未修复-低-CliThinkingRenderer._seen_dedupe_keys 在单轮内无界增长

- **入口/函数**: `CliThinkingRenderer.record(...)`
- **文件(行号)**: `dayu/cli/thinking.py:69-81`
- **输入场景**: 单轮内大量 distinct thinking delta（例如，模型通过 reasoning_delta 生成数千个增量）。
- **实际分支**: 每个新的 dedupe key 都会添加到 `self._seen_dedupe_keys` set 中。此 set 在整个 renderer 生命周期内单调增长，直到调用了 `close()`。
- **预期行为**: 在实践中，renderer 为每轮创建新实例（`_new_thinking_renderer()`），每轮 thinking delta 数量有限（通常 < 100）。如果提供者行为改变，开始为单个 turn 发送数万个 distinct delta，set 可能增长到可测量的内存消耗。目前这不是生产风险，但值得在 CLI UI 层记录。
- **直接证据**:
  - `dayu/cli/thinking.py:674`: `self._seen_dedupe_keys = set()` —— 从不清理，从不封顶
  - 计数器 pattern（`event_sequence`）提供了基于 sequence 的替代过滤策略，但不会替代或缩减 set 增长
- **影响**: 当前回合中对每个增量都很低——thinking delta 数量受 token 生成限制，在典型模型调用中 < 1000。内存影响可以忽略不计。仅作为可维护性注释值得注意。
- **建议改法和验证点**:
  1. 可选——如果未来模型产生极大 thinking delta 流，用 `deque(maxlen=N)` 或定期 `clear()` 替换无界 set
  2. 或保持原样——当前行为正确，对于任何实际模型调用内存安全
  3. 无需验证：不是 bug，只是可维护性注释
- **修复风险**: 低（可选）。
- **严重程度**: 低

## 挑战领域逐项审查

### 1. `--thinking` 是否可能影响 execution config 或只是 display flag

**结论：仅作为 display flag。** 证据链：

- `dayu/cli/arg_parsing.py:254`: `namespace.thinking = True` —— 默认为 `True`（之前为 `None`）
- `dayu/cli/arg_parsing.py:693-700`: help 文案"在终端显示运行态思考展示"——明确的展示语义
- `dayu/cli/agent_entrypoint.py:240-241`: `--thinking/--no-thinking` 已从 `unsupported_execution_option_names(...)` 中**移除**。旧代码（在 diff 中删除）曾将其列为 unsupported execution option，暗示历史上可能被误读为执行参数。移除后，`--thinking` 永远不会进入 execution config 裁决路径。
- `dayu/cli/commands/prompt.py:432`: `thinking_renderer=_new_thinking_renderer() if thinking else None` —— 仅控制是否实例化 CLI renderer
- `dayu/cli/commands/interactive.py:292-293`: 相同模式；`thinking` 被传入 `_submit_interactive_turn_handling_sigint`，仅作为 renderer 工厂参数
- `dayu/service/entrypoint_runtime.py:628`: `on_thinking: EntrypointThinkingCallback | None = None` —— Service 层将其作为可选 display callback 消费
- 未找到 `args.thinking` 进入 `ServiceRunOverrides`、`Host.submit_followup` 请求、Engine 请求或任何 provider/model config 的代码路径

**结论：无风险。** 旧执行参数语义已被完全移除。CLI 参数 `--thinking` 现在仅影响是否将 thinking renderer 注册到 Service callback。对模型配置或 provider 请求零影响。

### 2. REASONING_DELTA 写 PREVIEW row 是否破坏 Host/EventLog/replay/outbox/activity/transcript 语义

**结论：不破坏核心语义，但设计真源映射表需要更新（参见 DS-F01）。** 详细分析：

- **EventLog 语义** (`docs/host/design.md:1375`): "preview / reasoning / display-only event 可以用于 Host event stream，但不能成为 memory / audit / resume 真源"。PREVIEW row 符合此规则——它不被 memory、audit 或 resume 消费。
- **Replay 语义** (`docs/host/design.md:1376-1378`): "preview 可以按 event_sequence 补读以恢复 UI 体验，但 preview 丢失、压缩或清理不得影响 Run terminal、messages rebuild 或 memory。" ✅ PREVIEW row 丢失是可以接受的。
- **Outbox 语义** (`docs/host/design.md:1824-1828`): "Outbox 不包含完整 run timeline，不补 preview / progress / reasoning / streaming content。" ✅ Outbox 不提供 REASONING_DELTA 行，它们仅用于 live session watch。
- **Activity 语义**: `HostActivityView` 明确**不**承载 reasoning delta 内容。`HostHostingView` 是独立字段。content/reasoning delta 不通过 activity path 投影。✅
- **Transcript 语义**: Terminal result（stdout）仅包含 final answer 文本。Thinking 输出到达 stderr，仅在运行态展示，不进入 transcript buffer。`run_view.py:582-583` 中的更改确保 terminal result 始终写入 stdout/stderr，无论运行态模式如何。✅
- **Engine ingest**: `engine_ingest.py:897-903` 中，REASONING_DELTA 被显式处理，通过 `_append_preview_event` 写入 PREVIEW row（event_class=PREVIEW）。它不再被 `_is_transient_delta_event` 分类为 transient delta——transient 集合现在仅包含 CONTENT_DELTA 和 TOOL_CALL_DELTA。✅
- **Late-event safety**: `tests/host/test_engine_ingest_mapping.py:2347-2382` 测试 `test_late_reasoning_delta_is_rejected_before_preview_append` 确认终态后的 reasoning delta 被拒绝，不在 Run 完成后写入 PREVIEW row。✅
- **Terminal event validation**: `api.py:3115-3116` 在 `_validate_host_event_terminal_payload` 中显式拒绝终端事件上的 thinking，防止分类错误。✅

**结论：PREVIEW row 设计合理。** HostEvent projection 链（PREVIEW row → HostThinkingView → EntrypointThinking → CliThinkingRenderer）是完整的且每一层都被验证。唯一值得注意的是设计真源映射表的不一致（DS-F01）。

### 3. prompt/interactive cancel、Ctrl+C、detail/no-detail、thinking/no-thinking 竞态或回归

**结论：无竞态，无回归。** 已审查取消流程图。

**Prompt 取消路径**：
1. `_submit_prompt_turn_handling_sigint` 实例化 renderer + thinking（行 472-473）
2. 在 SIGINT 上，`_cancel_prompt_turn_after_local_request` **在** `submit_task.cancel()` **之前**调用 `thinking_renderer.close()`（行 525-526），确保在 cancel 请求发送前停止 thinking 输出
3. Finally 块再次调用 `thinking.close()`（行 502-503）—— idempotent，因为 `close()` 只设置 `_closed = True`
4. 相同模式适用于 Esc cancel（`test_prompt_esc_requests_cancel_after_run_id`，行 1256-1309 验证了这一路径）

**Interactive 取消路径**：
1. `_cancel_interactive_turn_after_first_sigint` 调用 `thinking_renderer.close()`（行 722-723）
2. `_submit_interactive_turn_handling_sigint` finally 块再次调用 `thinking.close()`（行 693-694）—— idempotent
3. 取消后的 thinking 记录被静默抑制——已验证（`test_cancel_after_first_sigint_returns_completed_submit_terminal`，行 1720-1752）

**Thinking renderer 生命周期**：
- 对于 prompt：`_new_thinking_renderer()` 仅在 `thinking=True` 时调用；`think_renderer=None` 时 `on_thinking=None`，正确跳过 thinking 处理
- 对于 interactive：在 `_run_interactive_repl` 中，`thinking_renderer=_new_thinking_renderer() if thinking else None`（行 563）；取消路径遵循与 prompt 相同的模式
- 所有取消路径都关闭 thinking renderer——双重关闭通过 `_closed` 标志安全地变得幂等

**Detail/activity cancel**：
- `activity_renderer`（prompt）/ `run_view`（interactive）在取消路径中由现有 `renderer.close()` 调用关闭（行 500-501, 690-691）
- 没有新的竞态——thinking renderer 完全独立于 activity renderer

**Ctrl+C 空闲/运行态交互**：
- 空闲 Ctrl+C 逻辑（`_run_interactive_repl`，行 522-562）保存在 `dayu/cli/commands/interactive.py`——与 thinking 更改隔离
- idle_interrupt_exit_pending 计数器在终端结果后的每个正常 turn 提交时重置（行 282 `idle_interrupt_exit_pending = False`）
- 没有 thinking renderer 与空闲输入状态机交互

**已审查回归测试覆盖**：
- `test_prompt_cancel_helper_closes_thinking_renderer`（行 1178-1210）
- `test_prompt_esc_requests_cancel_after_run_id`（行 1256-1309）
- `test_prompt_second_sigint_exits_after_cancel_request`（行 1312-1350）
- `test_prompt_cancel_terminal_wins_over_second_sigint`（行 1353-1384）
- `test_cancel_after_first_sigint_returns_completed_submit_terminal`（interactive，行 1720-1752）

**结论：无竞态。** Thinking renderer 在所有取消路径中都被正确关闭——包括 prompt SIGINT、prompt Esc、interactive SIGINT、second SIGINT 和 cancel terminal race。关闭是幂等的。Renderers 是 per-turn 的，不会在 turn 之间泄漏。

### 4. 测试覆盖评估

**已覆盖**：
- `test_thinking_renderer.py`（4 个测试）：renderer enabled output、dedup with sequence ordering、disabled suppression ✅
- `test_prompt_command.py`（8+ 个测试）：default detail output、no-detail suppression、thinking/no-thinking output difference、detail with non-TTY、detail-to-log-file isolation、cancel closes thinking、Esc closes thinking、second SIGINT ✅
- `test_interactive_command.py`（3+ 个测试）：no-detail output、thinking/no-thinking output difference、thinking not in old execution params、cancel closes thinking ✅
- `test_entrypoint_runtime.py`：`test_submit_entrypoint_turn_emits_host_public_thinking` ✅
- `test_engine_ingest_mapping.py`：`test_reasoning_delta_is_accepted_as_preview_for_live_display`、`test_late_reasoning_delta_is_rejected_before_preview_append` ✅
- `test_host_activity_event_projection.py`：terminal REASONING_DELTA projection with HostThinkingView ✅
- `test_arg_parsing.py`：thinking 默认值、detail 默认值 ✅

**未覆盖/覆盖不足**：
- 无测试覆盖 `_validate_host_event_terminal_payload` 对 terminal 事件上的 thinking 的拒绝（DS-F02）
- 无显式测试 thinking renderer `close()` 调用的幂等性——虽然实现是安全的，但没有测试验证在已关闭的 renderer 上调用两次 `close()` 不会抛出异常
- 无测试 interactive run view `show_activity=True` 参数——`new_interactive_run_view(show_activity=True)` 路径仅通过集成测试间接测试

**结论：覆盖充足且无阻塞性缺口。** 核心 thinking、detail 和 cancel 路径被良好覆盖。记录的缺口是低严重性防御性测试，而非行为风险。

### 5. Control doc / residual risk / PR body 流程合规性

**Control doc 状态**：
- PR body 声明"Deferred residuals are tracked in docs/host/issues-implementation-control.md" ✅
- Control doc 表（第 228-234 行）列出了：
  - `WU-CLI-SMOKE-01-R1`：deferred-with-owner → WU-RET-03 / GitHub Issue #78，"PREVIEW row 清理策略待 retention 分类" ✅
  - `WU-CLI-SMOKE-01-R2`：deferred-with-owner → 未来 CLI UI 增强，"160 字符截断待用户决定" ✅
- Control doc 的 WU-CLI-SMOKE-01 部分（第 269-324 行）记录了完整的 review chain ✅
- Control doc 状态行（第 159 行）标记 gate 为 "PR review"，next entry point 为 "Run PR review for draft PR #172" ✅

**PR body 合规性**：
- PR body 声明 "No GitHub issue is linked by design" ✅——与 WU-CLI-SMOKE-01 作为 user-directed immediate residual WU without GitHub Issue 的定位一致
- PR body 记录了 validation evidence：`tests/cli` 225 passed、Host/Service focused 126 passed、pyright 0 错误 ✅
- PR body 正确记录了 deferred residuals 及其 owners ✅

**流程合规性**：
- Control doc 状态行正确记录了 WU-CLI-SMOKE-01 为 `review` 状态，next entry point 为 PR review ✅
- 所有前置门禁（goal confirmation、plan、plan review、implementation、code review、aggregate deepreview、manual validation fix）均已记录并通过，具有完整的 artifact chain ✅
- 未创建 GitHub Issue——user ruling 明确表示无 GitHub Issue 要求 ✅
- PR body 不包含 `Closes` footer——符合 WU 无独立 GitHub issue 的定位 ✅

**结论：Control doc、residual risk tracking 和 PR body 满足 no-issue WU 的流程要求。** 所有 deferred residuals 都有明确的 owner/destination。Review chain 完整。

## Open Questions

1. 设计真源 `docs/host/design.md` 应在本次 PR 的 fix gate 中还是在一个独立的 design doc sync commit 中更新，以反映 REASONING_DELTA PREVIEW row 行为（DS-F01）？设计真源变更是否会触发比本 WU scope 更广的 review cycle？
2. `_single_line_text` 的 160 字符限制——这是否应通过 `CliThinkingRendererOptions` 变为可配置项，而不是 `dayu/cli/thinking.py` 中的模块级常量？Control doc 将可展开 UI 推迟为 future enhancement（WU-CLI-SMOKE-01-R2）；是否需要在本 WU 中进行任何 config plumbing？

## Residual Risk

| Risk | Classification | Owner / Destination |
|---|---|---|
| Design doc mapping table stale（DS-F01） | open-in-review | 本 review；应在 PR closeout 前修复或明确推迟 |
| Thinking renderer defensive test gaps（DS-F02） | deferred-with-owner | 未来 CLI test hardening |
| `_validate_host_event_terminal_payload` thinking/final_answer 检查未测试 | deferred-with-owner | 未来 Host API test hardening，非阻塞性 |
| PREVIEW row cleanup policy | deferred-with-owner | WU-RET-03 / GitHub Issue #78（已在 control doc 中追踪） |
| 160-char CLI thinking truncation UX | deferred-with-owner | 未来 CLI UI enhancement（已在 control doc 中追踪） |

## Verdict

**pass-with-required-fixes**

**Required fix（DS-F01）**：将 `docs/host/design.md` 第 1602 行的 EngineEvent 映射表条目从 `reasoning_delta -> accepted non-durable delta; no EventLog row by default` 更新为反映 REASONING_DELTA 现在为 live thinking display 生成 PREVIEW EventLog row 的新行为。这是文档级修复，无生产影响。应在 draft PR 解除前完成。

**Rationale**：DS-F01 是唯一需要当前解决的 finding。DS-F02 和 DS-F03 是低严重性防御性测试/可维护性注释，不阻塞 merge。所有五个挑战领域均已审查——`--thinking` 执行隔离得到确认，REASONING_DELTA PREVIEW row 语义上合理，cancel 路径无竞态，测试覆盖充足，control doc 与 PR body 合规。设计真源不一致是唯一需要注意的实质性 gap。

核心实现变更——HostThinkingView public contract、REASONING_DELTA PREVIEW row ingest、Service callback projection、CLI thinking renderer、prompt/interactive display flag semantics、cancel path lifecycle——均正确并经过良好测试。未发现生产竞态、语义破坏或架构违规。
