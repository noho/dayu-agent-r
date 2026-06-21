# WU-CM-14 Protected Recent Floor Plan

## 1. Plan Gate Verdict

WU-CM-14 的动机成立，且不是单纯补测试即可关闭。

核心问题真实存在：当前 compact boundary 后，ordinary `RunInput` 不能保证把 protected recent raw tail 投影给 Engine；fallback 路径中 proactive fallback 已经部分复用 protected floor，但 reactive 路径仍会在 frozen material assembly 处丢失历史 raw tail。该问题会直接影响“第 N 轮 final answer 列出 4 条详细内容，第 N+1 轮用户问‘详细解释第三条’，且 dispatch 前触发 compact”的语义连续性。

本 WU 不新增 WU-CM-14 专属 floor、不新增 ordinal follow-up floor、不做 prompt-pattern-specific retention、不做 deterministic final answer outline parser。修复方向是复用现有 `MemoryProjectionPolicy.selected_recent_window_turn_floor` 与 `protected_recent_turn_group_ids_for_material_blocks(...)`，让 compact selection、ordinary RunInput rendering 与 fallback rendering 对同一个 protected recent floor 语义收敛。

## 2. Direct Evidence

设计真源约束：

- `docs/host/design.md:2528-2583`：RunInputBuilder 是 memory / EventLog / Service 场景输入进入 Engine 的唯一运行态入口；selected recent window 中用户输入保持 `user` role，assistant final answer 保持 `assistant` role，current input 仍是最后的 `user` message。
- `docs/host/design.md:2591-2603`：accepted compacted view 只能作为业务摘要 / semantic material；Answer Anchor Memory 只能写历史回答轮廓，不得当作事实证明；evidence / internal refs 不得作为 LLM-facing material。
- `docs/host/design.md:3193-3206`：tier 0 normal 的 `assemble(...)` 输入是 `latest_accepted_compacted_view + post_compact_delta_material + current_input_anchor + normal_selected_recent_window_policy + protected_recent_floor_policy`，输出 ordinary RunInput 或 compact input。
- `docs/host/design.md:3284-3292`：proactive / reactive compact selection 都必须保留 current input anchor 与 protected recent floor；selection 候选集合是 `post_compact_delta_material`，不从 `latest_accepted_compacted_view` 重新选择 raw recent window；LLM-facing material 缩小时只能 whole-block keep/drop。
- `docs/host/design.md:3296-3300`：`previous_compacted_view` 只来自 latest accepted compacted view；`trace_material` 渲染 user / assistant continuity 与 user-visible Run state；`answer_material` 渲染 assistant final answer。
- `docs/engine/design.md:487-501`：Engine 不做 compact / retry / Host budget；context overflow 后如何压缩和重构 messages 属于 Host。

代码证据：

- `dayu/host/compact_material.py:454-545` 的 `build_pre_dispatch_compact_material_view(...)` 已经从 EventLog durable truth 构造 `previous_compacted_view` 和 current input 之前的 `post_compact_delta_material`，且不读取 Conversation Memory snapshot。
- `dayu/host/compact_material.py:2037-2139` 的 delta source 目前读取 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`，排除了 current input 本身。
- `dayu/host/compact_material.py:2179-2239` 已能把历史 user prompt 和 assistant final answer 映射为 turn-group material block。
- `dayu/host/compact_material.py:2242-2327` 已能把 accepted readable tool evidence 映射为 evidence material，并保留 readable tool name / query / source text。
- `dayu/host/compact_material.py:1658-1742` 已有按 Host Run `turn_group_id` 计算 protected recent floor 的实现，eligible block 包括 user input、assistant final answer、accepted tool evidence。
- `dayu/host/run_input.py:1759-1819` 的 ordinary path 在 `fallback is None` 时只拼接 `memory.messages + compact.messages + continuity.messages`，没有读取 EventLog-backed `post_compact_delta_material`，因此 compact-success 后不能保证 protected recent raw tail 进入 Engine messages。
- `dayu/host/run_input.py:2300-2333` 只渲染 memory snapshot 中已有的 selected recent window；这受 memory policy caps / snapshot state 影响，不等价于 design 要求的 post-compact delta protected floor。
- `dayu/host/run_input.py:2650-2859` 的 fallback renderer 能把 selected material blocks 渲染为 Engine messages，并会跳过 current input anchor；这部分可复用为 raw tail rendering 的实现基础。
- `dayu/host/dispatch.py:1515-1530` 的 proactive compact recovery tier 已传入 `selected_recent_window_turn_floor`，但 `dayu/host/dispatch.py:1853-1859` 的 normal proactive compact selection 未传入 floor，默认值为 0，导致 normal compact 可能把最近 raw turn 也送入 compactor。
- `dayu/host/dispatch.py:2192-2224` 的 proactive dispatch fallback 已传入 memory policy 的 `selected_recent_window_turn_floor`，所以 proactive fallback selection 本身没有丢 floor。
- `dayu/host/engine_ingest.py:3795-3801` 的 reactive root compact selection 未传入 floor，默认值为 0。
- `dayu/host/engine_ingest.py:4009-4072` 的 reactive frozen material assembly 用空 memory / compact / continuity 构造 material，实际只保留 current input anchor，不能从 post-compact delta 取得历史 assistant final answer；`dayu/host/engine_ingest.py:3883-3918` 虽然 fallback selection 传入了 floor，但 source material 已经缺失历史 raw tail。

补充只读核对说明：除用户指定范围外，仅对 `tests/host/test_context_compact_events.py` 和 `tests/host/test_context_budget.py` 做过关键词检索，用于确认 fallback payload / budget 术语；plan 结论不依赖这些文件。

## 3. Root Cause Conclusion

Root cause 不是 Answer Anchor Memory 不够聪明，也不是需要识别“第三条”的 prompt pattern。问题发生在 Host material / RunInput pipeline：

1. compact material selection 吞掉了 floor：normal proactive selection 和 reactive root selection 没有把现有 `selected_recent_window_turn_floor` 传给 `select_compact_segment(...)`。
2. ordinary RunInput assembly 吞掉了 floor：compact-success 后 no-fallback ordinary path 没有从 EventLog-backed `post_compact_delta_material` 渲染 protected recent raw tail，只依赖 memory snapshot 与 compact artifact semantic lines。
3. reactive path 的 fallback material assembly 吞掉了 floor：reactive overflow 后冻结的 material list 没有重建 EventLog-backed post-compact delta，fallback selection 虽然有 floor 参数，但没有可保护的历史 turn group。

因此当前 compact 后 Engine messages 可能退化为 `latest_accepted_compacted_view + current user prompt`，缺少解释“第三条”所需的完整第 N 轮 assistant final answer raw context。

## 4. Minimal Implementation Boundary

Allowed production files for implementation slice:

- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compact_material.py` only if an existing private helper must be reused or narrowly exposed through `__all__`

No changes planned to public API, schema, EventLog event types, compact payload schema, memory kind, policy fields, prompt parser, or ordinal-specific rules.

Implementation outline:

1. Pass the existing memory policy floor into normal compact selection.
   - In proactive normal compact request creation, pass `memory_policy.selected_recent_window_turn_floor` to `select_compact_segment(...)`.
   - In reactive root compact request creation, pass `pending.selected_recent_window_turn_floor` to `select_compact_segment(...)`.
   - Stop condition: protected recent turn groups are excluded from compact selected block ids by reason `protected_recent_raw_floor`.

2. Add ordinary RunInput protected recent raw tail rendering for post-compaction dispatch.
   - Add a module-private typed provider/view in `run_input.py`; do not make `RunInputBuilder.build()` read durable store directly.
   - Provider contract:
     - `_ProtectedRecentRawTailView(messages: tuple[AgentMessage, ...], material_blocks: tuple[RunInputMaterialBlock, ...], source_refs: tuple[str, ...])`.
     - `_ProtectedRecentRawTailProvider.load_protected_recent_raw_tail(snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts, memory: MemorySnapshotView, compact: CompactArtifactView) -> _ProtectedRecentRawTailView`.
     - `_NoopProtectedRecentRawTailProvider` returns an empty view for tests / legacy assembly.
     - `_DurableProtectedRecentRawTailProvider` owns `HostTransactionRunner`, `EventLogStore`, and the already-resolved `MemoryProjectionPolicy`; it mirrors `DurableAcceptedToolEvidenceMaterialProvider`, opens a read transaction, and calls `build_pre_dispatch_compact_material_view(...)` inside that provider-managed transaction.
   - Inject the provider into `RunInputBuilder.__init__` as an internal dependency with a noop default, alongside the existing provider set. `RunInputBuilder.build()` only calls the provider and consumes the returned typed view.
   - Inject rendered raw-tail messages only in the no-fallback ordinary branch:
     - current code shape becomes `memory.messages + compact.messages + protected_recent_raw_tail.messages + continuity.messages`;
     - fallback branch remains exclusively `_fallback_context_messages(...)` and must not also call/render the raw-tail provider.
   - Definitive call-site activation condition for post-compaction ordinary path:
     - `compact.compact_artifact_ref is not None`;
     - `fallback is None` at the `RunInputBuilder.build()` call site, so tier 4/5 fallback cannot double-render;
     - these conditions mean the current dispatch is an ordinary post-compaction dispatch, not current-input-only first dispatch and not fallback dispatch.
   - Definitive provider-side validation before returning non-empty messages:
     - the compact artifact was loaded by `DurableCompactArtifactProvider` for the current `run_id` and before the current Attempt start cursor, so it represents an accepted compact for this Run rather than an older Session artifact;
     - post-compact delta has eligible protected turn-group material under `MemoryProjectionPolicy.selected_recent_window_turn_floor`.
   - This covers both proactive compact-success and reactive compact-success: after accepted reactive compact, recovery dispatch creates a new Attempt for the same Run and still enters the same ordinary `RunInputBuilder.build()` no-fallback branch; `DurableCompactArtifactProvider` reads the current Run's accepted compact before that recovery Attempt start cursor.
   - Older compact artifact mis-trigger prevention comes from the provider query boundary: `dayu/host/run_input.py` currently reads `CONTEXT_COMPACTED` with `run_id = current_facts.run.run_id` and `event_sequence < current_facts.attempt.started_event_sequence`, not arbitrary Session history. If implementation changes that provider contract, it must add an equivalent current-run check or stop.
   - Source must be `build_pre_dispatch_compact_material_view(...)`, because it reads current input before-boundary EventLog material and does not use memory snapshot as raw material source.
   - Raw tail rendering must select only from `post_compact_delta_material`, never from `latest_accepted_compacted_view`; accepted compacted view remains semantic memory / summary material.
   - Select protected turn groups with `protected_recent_turn_group_ids_for_material_blocks(..., selected_recent_window_turn_floor=policy.selected_recent_window_turn_floor)`.
   - Render user prompt blocks as `UserMessage`, assistant final answer blocks as `AssistantMessage`, accepted readable tool evidence as system `Recent Evidence` / accepted tool evidence material, reusing existing rendering semantics where possible.
   - Never render the current input anchor as history. Current input remains the final `UserMessage`.
   - Avoid duplicate history messages between memory selected recent window and EventLog-backed raw tail:
     - extend the internal `MemorySnapshotView` with defaulted private provenance fields sufficient for dedupe, such as selected recent source refs / content digests, without changing public API or durable schema;
     - drop a raw-tail block when its canonical event/evidence provenance or rendered content digest is already represented by memory selected recent window;
     - for accepted evidence, compare both evidence id and tool-result event ref when available, because compact material uses canonical evidence id while memory selected evidence may carry the event id.
   - Do not expose event ids, tool_call_id, payload refs, digests, cursor, fallback diagnostics, Host governance state, or Engine state in LLM-facing content.
   - Re-reading EventLog in this provider is acceptable for WU-CM-14: EventLog / payload truth is immutable after commit, and the provider uses a short read transaction. Passing an already-built `PreDispatchCompactMaterialView` through dispatch state would be broader WU-CM-13 pipeline convergence and is not required here.

3. Repair reactive frozen material assembly enough for WU-CM-14 preservation.
   - `_frozen_reactive_material_blocks(...)` must no longer freeze only current input when prior committed post-compact delta material exists.
   - Reuse `build_pre_dispatch_compact_material_view(...)` plus current input anchor so reactive selection and fallback have eligible turn-group material.
   - Concrete WU-CM-14 stop condition: after repair, `_frozen_reactive_material_blocks(...)` must produce material blocks for the most recent `selected_recent_window_turn_floor` eligible turn groups from post-compact delta material, including committed user prompt, assistant final answer, and accepted readable tool evidence when those events exist.
   - The focused reactive material assembly test must prove those three block classes are present before `build_recent_window_fallback_selection(...)` runs; merely proving current input anchor exists is insufficient.
   - Keep deeper “exactly freeze the original overflow ordinary material list” convergence as WU-CM-13-owned residual if broader material unification is needed; WU-CM-14 must still ensure protected recent raw tail semantics do not drift.

4. Keep Answer Anchor Memory unchanged.
   - It remains useful for resolving “第三条” to an anchor.
   - It must not carry full raw final answer context or become a deterministic outline parser.

## 5. Test Plan

Allowed test files for implementation slice:

- `tests/host/test_run_input_builder.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_memory_projection.py` only for existing memory contract assertions if needed

Required tests:

1. End-to-end proactive regression in `tests/host/test_dispatch_scheduler.py` or `tests/host/test_run_input_builder.py`.
   - Seed turn N user prompt and assistant final answer containing four detailed numbered items.
   - Seed turn N+1 user prompt `详细解释第三条`.
   - Force pre-dispatch compact before dispatch.
   - Assert final Engine messages contain the protected recent raw tail: the turn N user prompt and the complete assistant final answer including all four items, especially the full third item text.
   - Assert current user prompt appears exactly once and remains the final message.

2. Reactive compact-success regression in `tests/host/test_run_input_builder.py` or `tests/host/test_dispatch_scheduler.py`.
   - Use the same four-item final answer / `详细解释第三条` scenario.
   - Simulate or drive accepted reactive compact, then build the recovery Attempt request through ordinary `RunInputBuilder.build()` with `fallback is None`.
   - Assert the same protected recent raw tail appears in Engine messages.
   - Code evidence for equivalence: reactive compact-success dispatch still creates a new Attempt for the same Run and reaches ordinary `RunInputBuilder.build()`; the distinguishing state is `RUN_STARTED(start_reason=recovery)`, while the message assembly owner is the same no-fallback ordinary branch.
   - If a full scheduler-level reactive E2E is not used, the focused test must explicitly construct the recovery Attempt state and call the same public/internal builder path used by dispatch, not only test helper functions.

3. Compact selection floor regression in `tests/host/test_compact_material.py` / `tests/host/test_dispatch_scheduler.py`.
   - Verify normal proactive compact passes `selected_recent_window_turn_floor` and excludes all blocks in the protected recent turn group from selected compact ids.
   - Verify reactive root compact selection passes `selected_recent_window_turn_floor` and excludes protected blocks in the same way.
   - Include user prompt, assistant final answer, and accepted readable tool evidence in the same recent turn group.

4. Ordinary RunInput raw tail boundary regression in `tests/host/test_run_input_builder.py`.
   - Build post-compaction ordinary RunInput with memory selected recent window capped or missing.
   - Assert raw tail still comes from EventLog-backed post-compact delta material, not from current input anchor or compact artifact semantic lines.
   - Assert Answer Anchor Memory may be present but is not the only carrier of the four-item answer text.
   - Assert activation is skipped when `compact.compact_artifact_ref is None`.
   - Assert activation is skipped when `fallback is not None`, because fallback owns its own selected material rendering.

5. Duplicate prevention regression in `tests/host/test_run_input_builder.py`.
   - Build a memory snapshot whose selected recent window already includes the same historical user / assistant messages that the EventLog-backed protected raw tail would select.
   - Assert final Engine messages contain each historical user prompt and assistant final answer exactly once.
   - Include accepted evidence overlap and assert evidence is not duplicated when represented by matching evidence id or tool-result event ref.
   - Assert current user prompt still appears exactly once as the final message.

6. Eligible material boundary regression.
   - Include history `USER_INPUT_ACCEPTED.display_text`.
   - Include `RUN_SUCCEEDED.final_answer`.
   - Include accepted readable `TOOL_RESULT_ACCEPTED` evidence with a corresponding `TOOL_CALL_REQUESTED` atom.
   - Include the existing user-visible outcome material boundary using the current supported terminal material; if implementation identifies an already-defined `USER_VISIBLE_RUN_STATE` projection path, assert it is rendered as business-readable trace material without Host state refs.

7. Negative LLM-facing boundary regression.
   - Assert bare `TOOL_CALL_REQUESTED` / tool request atoms do not enter Engine messages by themselves.
   - Assert `tool_call_id`, `event_id=`, `payload_ref=`, digest, cursor, Attempt id, execution id, fallback diagnostic refs, Host governance state, and Engine state do not appear in LLM-facing tail/system envelope.

8. Fallback regression.
   - Proactive fallback: keep existing fallback tests and add a recent assistant final answer turn group, proving fallback selected floor renders the raw final answer and not only current input.
   - Reactive fallback is a committed focused test, not optional. Simulate reactive context overflow / compact failure path far enough to exercise `_frozen_reactive_material_blocks(...)`, `_reactive_fallback_decision(...)`, `build_recent_window_fallback_selection(...)`, and `_fallback_context_messages(...)`.
   - If a full scheduler-level reactive E2E is not used, the focused test is equivalent only if it uses the same frozen material assembly function, the same fallback selection function, the same active fallback payload/view shape, and the same RunInput fallback renderer that production uses.
   - Assert the recovery/fallback Engine-bound messages include protected recent raw tail for the same turn group, including user prompt, assistant final answer, and accepted readable tool evidence.
   - Assert fallback path does not also render the ordinary raw-tail provider output.

9. Reactive frozen material assembly stop-condition regression in `tests/host/test_run_input_builder.py` or `tests/host/test_dispatch_scheduler.py`.
   - Seed post-compact delta material with at least two turn groups and set `selected_recent_window_turn_floor` to 1 or 2.
   - Assert `_frozen_reactive_material_blocks(...)` produces material blocks for the most recent protected turn group(s), including user prompt, assistant final answer, and accepted readable tool evidence.
   - Assert it still appends exactly one current input anchor and does not treat that anchor as historical material.

10. Current input anchor regression.
   - Assert current input is never treated as historical material source.
   - Assert no duplicate current prompt appears when memory snapshot or inline delta already covers current input.

## 6. README Trigger Judgment

Plan gate does not modify README.

Future implementation will touch `dayu/host` and `tests`, so it must check:

- `dayu/host/README.md` Agent update constraints before deciding whether Host README needs updates.
- `tests/README.md` Agent update constraints before deciding whether test README needs updates.

Expected implementation likely changes internal Host behavior and tests but not user-facing CLI / Web / WeChat workflow, install steps, public commands, public schema, or root README scope. README changes should be made only if the target README constraints say this protected recent floor behavior belongs to that document's reader boundary.

## 7. Validation Commands

Plan gate validation:

```bash
git diff --check -- docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md
```

Implementation validation:

```bash
source .venv/bin/activate
pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

If implementation touches memory projection assertions:

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py -q
```

If coverage reporting is required for the touched files in the local workflow, run focused coverage against the modified Host modules and keep newly touched file coverage at or above the project target.

## 8. Slice Structure

Recommended: single implementation slice.

Slice 1: protected recent floor preservation convergence.

- Allowed files:
  - `dayu/host/run_input.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/compact_material.py` only for narrow helper reuse
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_compact_material.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_memory_projection.py` only if memory assertions need adjustment
- Required tests:
  - Add failing-first proactive compact-success ordinal follow-up regression.
  - Add reactive compact-success regression through ordinary `RunInputBuilder.build()`.
  - Add compact selection floor regression for normal proactive and reactive selection.
  - Add ordinary RunInput post-compaction protected raw tail regression.
  - Add memory selected recent window / raw tail dedupe regression.
  - Add proactive and reactive fallback preservation regressions.
  - Add reactive frozen material assembly stop-condition regression.
  - Add negative LLM-facing internal ref / bare tool request assertions.
- Stop condition:
  - Engine-bound messages contain protected recent raw tail after compact boundary for the four-item final answer scenario.
  - compact input excludes protected recent floor from selected compact ids.
  - reactive frozen material assembly produces the protected post-compact delta turn group blocks required by the configured floor.
  - ordinary RunInput and fallback RunInput preserve the same floor semantics.
  - overlapping memory selected recent window and EventLog-backed raw tail do not duplicate messages.
  - No public API/schema/EventLog changes.
  - Focused pytest and pyright pass.

Do not split unless the reactive path requires broader WU-CM-13 pipeline convergence. If that happens, stop before implementation expansion and raise a blocking question with direct state-machine evidence.

## 9. Blocking Questions

No blocking question for WU-CM-14 plan gate.

Residual risks:

- Reactive “freeze exact overflow ordinary material list” is larger than WU-CM-14 and overlaps WU-CM-13. WU-CM-14 fixes only the protected recent raw tail floor by reusing EventLog-backed post-compact delta material and existing floor policy.
- Full proactive / reactive material pipeline convergence, including passing an already-frozen material view from Context Governance into RunInputBuilder without a second EventLog read, remains WU-CM-13 scope.
- If implementation discovers recovery dispatch does not reach ordinary `RunInputBuilder.build()` after reactive compact-success, the plan's equivalence proof is invalid; stop and raise a blocking question with the state-machine evidence.
