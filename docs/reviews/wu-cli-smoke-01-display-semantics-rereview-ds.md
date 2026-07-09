# WU-CLI-SMOKE-01 Display Semantics — AgentDS Adversarial Re-Review

## 结论

**pass**

上一轮三个 required findings（F01 dead param、F02 README 不实、F03 缺测试）均已通过真实实现路径修复。本轮新增实现——Engine REASONING_DELTA → Host PREVIEW row → HostThinkingView → Service EntrypointThinking → CLI CliThinkingRenderer——链路完整、分层正确、`--thinking` 仅作为展示开关不进入 model/runner/provider config。三个 LOW findings 均不需要当前 work unit 修复。

---

## Review 上下文

- **Mode**: current changes（未提交 workspace diff）
- **Branch**: `phase/host-issues-control`
- **Base**: `main`
- **设计真源**: `docs/host/design.md`, `docs/engine/design.md`
- **上一轮 review**: `docs/reviews/wu-cli-smoke-01-display-semantics-review-ds.md`（verdict: pass-with-required-fixes, 含 F01 CRITICAL / F02 HIGH / F03 MEDIUM）
- **本轮 Codex fix**: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`
- **Review target**: 当前 workspace diff 中 thinking 展示链路相关改动

---

## 五大挑战逐条裁决

### 挑战 1: 上一轮 required findings 是否真的被修复

**裁决: 全部修复，不是只改文档或测试。**

| Finding | 上一轮状态 | 本轮证据 | 裁决 |
|---------|-----------|---------|------|
| F01 (CRITICAL) `--thinking` dead param | 无消费者 | `engine_ingest.py:897-901` REASONING_DELTA → `_append_preview_event`; `read_api.py:1106-1120` `_thinking_from_row` → `HostThinkingView`; `entrypoint_runtime.py:1215-1239` `_emit_entrypoint_thinking_from_host_event` → `on_thinking` callback; `prompt.py:437` / `interactive.py:634` 注册 `thinking.record` | **已修复** |
| F02 (HIGH) README 声称 thinking 展示但无实现 | README 不实 | `README.md:302` "控制是否在终端回显运行态思考展示；默认 `--thinking`" — 现在有实际实现支撑; `arg_parsing.py:690` help text "在终端显示运行态思考展示" — 有实际链路 | **已修复** |
| F03 (MEDIUM) 缺少 thinking 展示端到端测试 | 无测试 | `test_thinking_renderer.py` 3 tests; `test_prompt_command.py:998` thinking on/off 输出差异; `test_interactive_command.py:1223` 同上; `test_entrypoint_runtime.py:678` thinking callback 投影; `test_engine_ingest_mapping.py:2231` REASONING_DELTA→PREVIEW; `test_host_activity_event_projection.py:757` thinking view 投影 | **已修复** |

### 挑战 2: REASONING_DELTA 持久写 PREVIEW row 是否引入新风险

**裁决: 不引入功能正确性风险，但存在可接受的持久化隐私/存储风险（见 F01）。**

详细分析：

- **不污染 durable replay**: PREVIEW row 的 `EventClass` 是 `PREVIEW`，不是 `CANONICAL_FACT`。replay/resume 路径只消费 CANONICAL_FACT 事件，thinking 文本不会进入 recovered conversation。
- **不污染 outbox**: Outbox 只追踪 terminal event（SUCCEEDED/FAILED/CANCELLED/LOST）。PREVIEW row 不在 outbox projection 范围内。
- **不污染 activity**: `_activity_from_row()` (read_api.py:1067) 的 allowlist 不包含 `REASONING_DELTA`，thinking 不会作为 activity 展示。
- **不污染 transcript**: CLI `TerminalInteractiveRunView` 的 transcript buffer 只记录 terminal result 的 stdout/stderr 输出。thinking 由独立的 `CliThinkingRenderer` 直接写 stderr，不进入 transcript buffer。
- **不破坏 late-event governance**: `_ingest_validated()` 中 REASONING_DELTA 的 early return (L897) 位于 `_validate_durable_context` 和 `_duplicate_terminal_result` 和 `_late_rejection_reason` 之后。终态后的迟到 reasoning delta 会被 `_late_rejection_reason` 拒绝。测试 `test_late_reasoning_delta_is_rejected_before_preview_append` (test_engine_ingest_mapping.py:2347) 验证了这一点。
- **持久化风险**: 模型 thinking 文本现在写入 durable SQLite EventLog 的 `payload_json` 字段（`_preview_payload` L4632-4634: `{"delta": data.delta}`）。这遵循现有 PREVIEW 持久化模式（其它 PREVIEW 事件也持久化），但 reasoning text 可能包含敏感信息、业务推理中间步骤，且对 verbose reasoning 模型可能产生大量数据。这在当前设计边界内是可接受的（PREVIEW ≠ CANONICAL_FACT），但未来 session purge / retention 治理需要考虑 PREVIEW 行的清理策略。

### 挑战 3: Service/CLI thinking callback 是否有 race/dedupe/乱序/终态后显示/cancel path/interactive 多轮残留

**裁决: 无 race/dedupe/乱序/终态后显示/多轮残留问题。cancel path 存在一个次要设计注意点（见 F03）。**

逐项分析：

- **Dedupe**: Service 层 `_emit_entrypoint_thinking_from_host_event` (entrypoint_runtime.py:1236) 检查 `event.dedupe_key in state.seen_thinking_dedupe_keys`。CLI 层 `CliThinkingRenderer.record` (thinking.py:72) 检查 `thinking.dedupe_key in self._seen_dedupe_keys`。双重去重保证不重复输出。
- **乱序**: `CliThinkingRenderer.record` (thinking.py:74-78) 检查 `thinking.event_sequence < self._last_event_sequence` 并拒绝乱序事件。
- **终态后显示**: `_emit_entrypoint_thinking_from_host_event` (entrypoint_runtime.py:1232) 第一行检查 `event.terminal_status is not None`，终态事件不触发 thinking callback。`HostEvent.__post_init__` 中 `_validate_host_event_terminal_payload` (api.py:3115-3116) 在构造时拒绝 terminal kind 携带 thinking。两者共同确保终态后不会错误显示 thinking。
- **多轮残留**: interactive 每轮 `_submit_interactive_turn_handling_sigint` (interactive.py:573) 创建新的 `CliThinkingRenderer` 实例，finally 块中调用 `thinking.close()` (L677)。`_TerminalObservationState` 中的 `seen_thinking_dedupe_keys` 是每轮新创建的。无跨轮残留。
- **Cancel path**: prompt 的 `_submit_prompt_turn_handling_sigint` (prompt.py:378) 在 finally 块中关闭 thinking renderer (L479-480)；SIGINT 路径中 thinking renderer 保持打开直到 finally。cancel 后 `cancel_entrypoint_run_and_wait` 不使用 thinking callback（因为 cancel 路径不需要展示运行态 thinking）。cancel 路径不泄漏 thinking 状态。
- **Race**: thinking 事件通过 `asyncio.Queue` 单线程消费，`_drain_available_watcher_items` 中 get_nowait() 批量处理。不存在并发写入。

### 挑战 4: --thinking/--no-thinking 是否仅显示层语义

**裁决: 确认仅显示层语义，完全没有进入 model config / runner config / provider request。**

证据链：

- `arg_parsing.py:687-700`: `--thinking/--no-thinking` 注册为 mutually exclusive group，存入 `args.thinking`（bool）
- `agent_entrypoint.py:232-263`: `unsupported_execution_option_names()` 不包含 `--thinking/--no-thinking`
- `agent_entrypoint.py:266-298`: `service_run_overrides_from_args()` 不映射 `args.thinking`
- `prompt.py:189`: `thinking=args.thinking` 仅用于决定是否创建 `CliThinkingRenderer`
- `interactive.py:247`: `thinking=args.thinking` 同上
- `prompt.py:437`: `on_thinking=None if thinking is None else thinking.record` — thinking renderer 仅作为 callback 注入 `submit_entrypoint_turn_and_wait`
- `entrypoint_runtime.py:628`: `on_thinking: EntrypointThinkingCallback | None = None` — 仅作为可选 callback，不进入 Engine request
- 全链路无 `args.thinking` 进入 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`AgentRunRequest`、`provider_request` 或任何 provider extension

### 挑战 5: 测试是否有伪测试或 mock 只覆盖 adapter

**裁决: 测试覆盖了真实 projection path，不是伪测试。**

分析：

- `test_engine_ingest_mapping.py:2231` (`test_reasoning_delta_is_accepted_as_preview_for_live_display`): 使用真实 `EngineEventIngestor` + 真实 `EventLogStore`（SQLite in-memory），验证 REASONING_DELTA → PREVIEW row → `payload["delta"]`。**覆盖真实 ingest path。**
- `test_engine_ingest_mapping.py:2347` (`test_late_reasoning_delta_is_rejected_before_preview_append`): 验证终态后 REASONING_DELTA 被 late-event governance 拒绝。**覆盖真实 late-event path。**
- `test_host_activity_event_projection.py:757`: 使用真实 `_host_event_from_row`，直接构造 EventLogRow(event_type="REASONING_DELTA")，验证 projection → `HostEvent.thinking.text_delta`。**覆盖真实 projection path。**
- `test_entrypoint_runtime.py:678` (`test_submit_entrypoint_turn_emits_host_public_thinking`): 使用 FakeHost 注入 HostEvent（thinking 非 None），验证 `on_thinking` callback 收到正确的 `EntrypointThinking`。**覆盖 Service projection path**，但 `_emit_entrypoint_thinking_from_host_event` 内部逻辑（dedupe, terminal filter, run_id filter）是通过真实函数路径测试的。
- `test_prompt_command.py:998` 和 `test_interactive_command.py:1223`: 端到端测试，使用 FakeHost 注入 thinking event，验证 `--thinking` vs `--no-thinking` 的 stderr 输出差异。**覆盖 CLI 端到端路径。**
- `test_thinking_renderer.py`: 3 个测试覆盖 enabled 输出、disabled 静默、dedupe + 乱序过滤。**覆盖 CLI renderer 路径。**

FakeHost 是 Host Protocol 的测试替身，这是分层架构中 Service 层测试的标准做法——测试 Service 对 Host public contract 的消费行为，不重复测试 Host 内部实现。各层内部实现由各自层的 focused tests 覆盖。

---

## Findings

### F01 [LOW] REASONING_DELTA 同时在 early return 与 `_is_preview_event` 中分类

- **入口/函数**: `EngineEventIngestor._ingest_validated` / `_is_preview_event`
- **文件(行号)**: `dayu/host/engine_ingest.py:897-901`（early return）与 `dayu/host/engine_ingest.py:4582-4584`（`_is_preview_event`）
- **输入场景**: Engine 产出 `EngineEvent(type=REASONING_DELTA, data=ReasoningDeltaData)`
- **实际分支**: REASONING_DELTA 在 L897 被 early return 拦截，`_append_preview_event` 执行后返回 `_single_event_result(row)`。L984 的 `_is_preview_event(event)` 也会对 REASONING_DELTA 返回 `True`，但因 early return 先执行，永远走不到 L984。
- **预期行为**: 每个 EngineEventType 应有唯一且明确的 handler 位置。
- **实际行为**: REASONING_DELTA 在两个位置被分类为 "应写 PREVIEW row"。当前因 handler 顺序（early return 在前），行为正确；但代码读者和维护者需要同时理解两处才能确认处理逻辑。
- **直接证据**: L897 显式检查 `event.type == EngineEventType.REASONING_DELTA`；L4582-4584 `_is_preview_event` 也检查同一条件。两者都是本次 Codex fix 新增的代码。
- **影响**: 结构性混淆——若未来有人重构 handler 顺序或提取公共分类逻辑，可能意外改变 REASONING_DELTA 的处理方式。当前无功能影响。
- **建议改法和验证点**: 将 REASONING_DELTA 从 `_is_preview_event` 中移除，保留 L897 的 early return 作为唯一 handler；或在 `_is_preview_event` 的 docstring 中注明 REASONING_DELTA 已在上游 early return 处理。验证：现有 REASONING_DELTA 相关测试全部通过。
- **修复风险（低）**: 仅删除 `_is_preview_event` 中的一个条件分支，early return 路径不变。
- **严重程度（低）**: 无功能影响，仅结构性债务。
- **建议裁决**: `accepted`（可选修复，不阻塞 merge）

### F02 [LOW] 模型 thinking 文本持久化在 durable SQLite EventLog 中

- **入口/函数**: `_preview_payload` → `_append_preview_event` → EventLogStore.append_event
- **文件(行号)**: `dayu/host/engine_ingest.py:4632-4634`（delta 写入 payload），`dayu/host/engine_ingest.py:2538-2570`（PREVIEW row append）
- **输入场景**: 模型产生 reasoning/thinking 增量文本
- **实际分支**: `_preview_payload` 将 `data.delta` 写入 payload JSON `{"delta": data.delta}`，随后 `_append_preview_event` 通过 `_event_request` 写入 `EventClass.PREVIEW` 的 EventLog row。
- **预期行为**: thinking 文本作为运行态展示数据，在 final answer 后不再保留在 transcript 中。当前设计确实不在 transcript 中保留。
- **实际行为**: thinking 文本被持久化在 durable SQLite EventLog 的 `payload_json` 字段中。虽然 EventClass 是 PREVIEW（非 CANONICAL_FACT），但数据仍然存在于 durable store 中，会随 session 生命周期保留。
- **直接证据**: `_preview_payload` L4633 `common["delta"] = data.delta`；EventLogStore 写入 SQLite `TABLE_EVENT_LOG`。
- **影响**:
  - 隐私/安全：模型内部推理可能包含对财报数据的中间分析、假设或敏感推断，这些内容现在持久化存储。
  - 存储增长：verbose reasoning 模型（如 DeepSeek-R1、OpenAI o1）可产生大量 thinking token，全部写入 SQLite。
  - 未来 session purge / retention 治理需考虑 PREVIEW row 的清理策略。
- **建议改法和验证点**: 当前设计是可接受的——PREVIEW row 是运行态展示的 durable 投影，不影响 replay/outbox/final answer。建议在 Host 设计真源中记录 PREVIEW row 包含 thinking 文本的持久化语义；若未来实现 session purge，PREVIEW row 应可安全清理。验证：确认 PREVIEW row 不进入 replay/outbox/transcript 路径（当前已验证）。
- **修复风险（低）**: 无需当前代码修改。属于设计文档补充。
- **严重程度（低）**: 设计权衡，无功能正确性影响。
- **建议裁决**: `deferred`（后续 retention/purge work unit 中考虑）

### F03 [LOW] interactive cancel path 中 thinking renderer 在 finally 关闭前不感知 cancel 状态

- **入口/函数**: `_submit_interactive_turn_handling_sigint` / `_cancel_interactive_turn_after_first_sigint`
- **文件(行号)**: `dayu/cli/commands/interactive.py:573-681`
- **输入场景**: interactive 运行中用户第一次 SIGINT
- **实际分支**: first SIGINT → `_cancel_interactive_turn_after_first_sigint` → cancel submit_task → 调用 `cancel_entrypoint_run_and_wait`。在此过程中，thinking renderer 仍保持打开（未 close），但 `cancel_entrypoint_run_and_wait` 不传 `on_thinking` callback。
- **预期行为**: cancel 后不应再有新的 thinking 增量显示。
- **实际行为**: thinking renderer 在 finally (L676-677) 才 close。从 first SIGINT 到 finally 之间，如果 watcher queue 中还有未消费的 thinking event，`_drain_available_watcher_items` 不会处理它们（因为 `on_thinking` callback 只在 `submit_entrypoint_turn_and_wait` 中传递，cancel 路径不传）。实际上 cancel 路径重新 attach watcher 但不注册 thinking callback，所以 cancel 期间不会有新 thinking 输出。这是正确的，但依赖隐式假设（cancel 路径不传 callback）而非显式状态管理。
- **直接证据**: `interactive.py:634` 传递 `on_thinking=None if thinking is None else thinking.record`；`_cancel_interactive_turn_after_first_sigint` 调用 `cancel_entrypoint_run_and_wait` 时不传 `on_thinking`；thinking renderer 在 finally L676-677 关闭。
- **影响**: 当前无功能问题，但 thinking renderer 的 "open but unused" 状态在 cancel→finally 窗口期内存在，未来如果有人在 cancel 路径中也想展示 thinking，可能意外复用已部分消费的 renderer 状态。
- **建议改法和验证点**: 可考虑在 first SIGINT 时主动关闭 thinking renderer（如在 `_cancel_interactive_turn_after_first_sigint` 开头调用 `thinking.close()`），使状态转换更显式。当前设计可接受，不需立即修复。
- **修复风险（低）**: 增加一行 `thinking.close()` 调用，不影响功能。
- **严重程度（低）**: 无当前功能影响，仅代码可读性/可维护性。
- **建议裁决**: `accepted`（可选改进，不阻塞 merge）

---

## 架构与分层检查

### 分层边界 ✓

完整链路分层正确：

```
CLI (arg_parsing.py, thinking.py, prompt.py, interactive.py)
  → 消费 args.thinking，创建 CliThinkingRenderer，注入 on_thinking callback

Service (entrypoint_runtime.py)
  → EntrypointThinking DTO, on_thinking callback 协议
  → 从 HostEvent.thinking 投影为 EntrypointThinking
  → 按 run_id / dedupe_key 过滤

Host (api.py, read_api.py, engine_ingest.py)
  → HostThinkingView typed contract
  → _thinking_from_row 从 EventLog REASONING_DELTA PREVIEW row 投影
  → EngineEventIngestor 将 REASONING_DELTA EngineEvent 提升为 PREVIEW EventLog row
  → HostEvent 新增 thinking 字段（HostThinkingView | None, default None）

Engine (无修改)
  → REASONING_DELTA 是已有 EngineEventType，本轮无 Engine 层修改
```

- `args.thinking` 不进入 `service_run_overrides_from_args()` → 不泄漏到 Service/Host/Engine 层 ✓
- `args.detail` 仅在 CLI 层消费 → 不跨层泄漏 ✓
- `--thinking` 不进入 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`provider_request` → 不改变模型配置 ✓
- `HostThinkingView` 仅含 `text_delta: str` → 不承载内部治理 id、cursor 或 digest ✓

### 项目指令合规

| 指令 | 状态 | 说明 |
|------|------|------|
| 禁止魔法数字/字符串 | ✓ | `_TEXT_MAX_CHARS = 160` 有命名常量 |
| 函数 docstring | ✓ | 所有新增 public 函数有完整中文 docstring |
| 禁止 `Any` / 无类型签名 | ✓ | `thinking: bool = True` 类型明确 |
| 禁止兼容性代码 | ✓ | 无兼容性 wrapper |
| 禁止 God object | ✓ | `HostThinkingView` 仅含 `text_delta` 一个字段 |
| 分层架构 | ✓ | 见上 |
| 测试覆盖 | ✓ | 5 层测试覆盖完整链路 |
| pyright | ✓ | Codex 报告 0 errors |
| README 同步 | ✓ | 见挑战 1 F02 |

### HostEvent 终端校验

`HostEvent.__post_init__` → `_validate_host_event_terminal_payload` (api.py:3115-3116):
```python
if event.thinking is not None:
    raise ValueError("HostEvent terminal kind must not include thinking")
```
确保 terminal event 不可能携带 thinking view。这是构造期校验，防止 Service 层错误地将终端状态与运行态 thinking 混合。

### REASONING_DELTA late-event governance

`_ingest_before_reactive_compaction` (engine_ingest.py:735-737):
```python
late = _late_rejection_reason(context)
if late is not None:
    return self._append_rejected_diagnostic(...)
```
此检查在 REASONING_DELTA early return (L897) 之前执行。终态后的迟到 reasoning delta 被拒绝写 REJECTED diagnostic，不进入 PREVIEW row。测试 `test_late_reasoning_delta_is_rejected_before_preview_append` 验证。

---

## Open Questions

1. **PREVIEW row 生命周期**: 当前 PREVIEW row（包括 REASONING_DELTA）在 session purge 时是否被清理？如果未来实现 purge，thinking 文本的清理策略需要明确。这不阻塞当前 WU。
2. **非 TTY 场景下的 thinking 输出**: `CliThinkingRenderer` 默认构造（options=None）按 `stderr.isatty()` 决定是否启用。但 prompt/interactive 通过 `--thinking` 显式传入 `enabled=True`，不受 TTY 影响。对于 CI/pipe 场景，thinking 文本会写入 stderr，这可能符合预期（stderr 是诊断通道），但值得在文档中说明。

---

## Residual Risk

1. **thinking 文本持久化增长**: 对 verbose reasoning 模型，EventLog 的 PREVIEW 行可能快速增长。当前无 PREVIEW row 的 retention/rotation 策略。这属于 storage governance lane（#43/#36/#78/#156/#96），不阻塞当前 WU。
2. **REASONING_DELTA 分类结构性债务**: F01 描述的双重分类，未来重构时可能引入回归。风险低，可通过小重构消除。
3. **未覆盖的 thinking 路径**: 当前 thinking 展示仅通过 live HostEvent watcher（`watch_session_events`）路径工作。如果 watcher 失败后 fallback 到 outbox terminal read，thinking 增量不会在 outbox 中补读（因为 outbox 只追踪 terminal event）。这是设计上的有意限制（thinking 只是运行态展示，不需要补读），但值得注意的是用户在 watcher 失败后看不到 thinking 输出（只会看到 watcher failure diagnostic activity）。

---

## 验证摘要

- 代码走查: `dayu/cli/thinking.py`, `dayu/cli/arg_parsing.py`, `dayu/cli/agent_entrypoint.py`, `dayu/cli/commands/prompt.py`, `dayu/cli/commands/interactive.py`, `dayu/cli/run_view.py`, `dayu/host/api.py` (HostThinkingView, HostEvent.thinking), `dayu/host/engine_ingest.py` (REASONING_DELTA handling, _is_preview_event), `dayu/host/read_api.py` (_thinking_from_row, _host_event_from_row), `dayu/service/entrypoint_runtime.py` (EntrypointThinking, _emit_entrypoint_thinking_from_host_event, on_thinking)
- `--thinking` 参数生效链追踪: args.thinking → prompt/interactive → CliThinkingRenderer(enabled=True/False) → on_thinking callback → Service → Host → Engine → 全程不进入 model/runner/provider config
- 持久化检查: PREVIEW row 不进入 replay (CANONICAL_FACT only)、不进入 outbox (terminal only)、不进入 activity (_activity_from_row allowlist)、不进入 transcript (独立 stderr)
- late-event governance: `_late_rejection_reason` 在 REASONING_DELTA handler 前执行，迟到 reasoning 被拒绝
- 测试覆盖确认: 5 层 focused tests + 2 层端到端 tests 覆盖完整 thinking 链路
- 上一轮 findings 逐条复核: F01/F02/F03 全部修复

---

## Verdict

**pass**

三个 LOW findings（F01 结构性重复分类、F02 thinking 文本持久化、F03 cancel path thinking renderer 生命周期）均不需要当前 work unit 修复，可作为后续改进或 deferred 到对应 work unit。

上一轮 CRITICAL finding（`--thinking` dead param）已通过完整 Engine→Host→Service→CLI 链路修复，不是只改文档或测试。`--thinking` 确认仅显示层语义，完全不进入 model/runner/provider config。测试覆盖真实 projection path，不是伪测试。
