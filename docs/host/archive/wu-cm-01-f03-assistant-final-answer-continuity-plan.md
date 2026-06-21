# WU-CM-01-F03 Assistant Final Answer Continuity Fidelity Closeout Plan

## Goal / Motivation / Success Signal

目标：收窄 LLM-facing Trace / Answer material 中 assistant final answer / conclusion continuity 的文本来源，只允许 `RUN_SUCCEEDED` payload 中明确的 `final_answer`，或 digest-checked terminal summary artifact 中由 Engine `FinalAnswerData.content` 写入的 `content`。不得再把 `summary_text` 或 nested `summary` 当作 assistant final answer fallback。

动机成立。当前代码中的 `assistant_summary_from_payload()` 名称和行为都把 “assistant final answer / conclusion” 与 “summary” 混在一起，并按 `final_answer -> content -> summary_text -> nested summary` 搜索。对 selected recent window、fallback recent window、compact history material 和 `answer_material` 来说，这会把用户实际看到的最终回答替换成摘要文本，导致后续 LLM-facing continuity 丢失结构、序号、措辞和细节。

成功信号：

- 任何 assistant final answer / conclusion continuity 只来自 `final_answer` 或 terminal summary artifact 的 `content`。
- `summary_text`、nested `summary`、payload ref / digest、event id 不会进入 assistant selected recent window、fallback assistant message、compaction history material 或 `ConversationCompactInputVNext.answer_material[*].answer_text`。
- 缺失 final answer / terminal content 的历史 `RUN_SUCCEEDED` 被跳过对应 assistant continuity item；不能用 summary 或 ref 文本补洞。
- Session Summary Memory 的来源保持不变：只来自 accepted `CONTEXT_COMPACTED.accepted_candidate.session_summary.summary_text`。
- focused tests 覆盖 run input、memory projection、compaction evidence / material 和 terminal summary payload helper；pyright 0 errors。

## Non-goals / Scope Boundary

非目标：

- 不修改 compact output schema、Conversation Memory snapshot schema、section 顺序、Host 状态机或 Engine contract。
- 不重定义 terminal summary artifact 的持久化职责。
- 不把 compact `session_summary`、answer anchor、reference continuity、forward intent 或 fallback summary 回填成 assistant final answer。
- 不实现深历史 recall、semantic search、prompt-conditioned recall 或 operator final-answer search。
- 不让 assistant final answer 自动成为 `evidence_backed_fact`。
- 不保留旧 helper 的兼容 wrapper、re-export 或 alias。

Plan gate 只写本文档。Implementation gate 预计只允许 Host memory / run input / compaction helper 边界及对应 tests；若实现需要 schema、public contract、state-machine 或 Host 外层 owner 变更，必须停止并回到设计 / 总控裁决。

## Design Document Alignment

Host 设计对齐：

- `docs/host/design.md:2915` 明确 `trace_material` 只包含用户输入、助手最终回答和用户可见 Run 状态，`answer_material` 只包含可读 assistant final answer / conclusion。
- `docs/host/design.md:3026` 明确 Trace Memory 来源包括 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED.final_answer` 和用户可见 Run 状态。
- `docs/host/design.md:3030` 明确 Session Summary Memory 只来自 accepted `CONTEXT_COMPACTED`。
- `docs/host/design.md:3040`-`3042` 明确 compact 前 / delta 的 Trace Memory 与 compact 后 Session Summary Memory 生产者不同，不能互相 fallback。
- `docs/host/design.md:3196` 明确 `answer_material` 渲染 assistant final answer / conclusion，且不得作为 evidence-backed fact source。

Engine 设计对齐：

- `docs/engine/design.md` 定义 Engine 是单次 run 执行层，final answer 由 EngineEvent `final_answer` 表达；Engine 不拥有 Host memory、compact 或 session summary。
- `dayu/host/engine_ingest.py:4275`-`4306` 当前把 Engine `FinalAnswerData.content` 写入 terminal summary payload 的 `content` 字段。这是 terminal content 可作为 assistant final answer continuity 的直接事实来源，但只能在通过 `terminal_summary_ref` / `terminal_summary_digest` 读取到对应 artifact 时使用，不能泛化为任意 payload 的 `content`。

## First-principles Judgment and Direct Code Evidence

第一性原理判断：

- assistant final answer continuity 的任务是让下一轮模型看见用户刚看到的 assistant answer / conclusion；summary 是压缩或导航材料，不是同一语义。
- Host 可以用 terminal summary artifact 的 `content` 恢复 final answer continuity，是因为该字段由 Engine final answer content 写入，并由 durable ref / digest 证明来源；`summary_text` 没有这个同源关系。
- Session Summary Memory 是 compact accept barrier 后的 rollup view。它服务长对话连续性，但不能伪造成 assistant answer，也不能作为 compact 前 Trace Memory 的生产者。
- 缺失 answer 文本时跳过 assistant continuity 比注入 ref / digest 更正确，因为 LLM-facing 文本必须是业务可读语义，不应让内部治理标识替代内容。

直接代码证据：

- `dayu/host/terminal_summary_payload.py:31`-`58` 的 `assistant_summary_from_payload()` 依次读取 `final_answer`、`content`、`summary_text`，并递归 nested `summary`。
- `dayu/host/run_input.py:3007`-`3051` 的 `_payload_with_terminal_summary()` 用该 helper 判断 RUN payload 是否已有文本，并把 terminal summary 中读到的文本合并到 `content`。
- `dayu/host/run_input.py:3428`-`3440` 的 `_continuity_message_from_event()` 用同一 helper 生成 assistant history message。
- `dayu/host/compaction_evidence.py:401`-`429` 的 `_assistant_history_materials()` 用同一 helper 生成 `ASSISTANT_FINAL_ANSWER` history material。
- `dayu/host/durable/memory.py:217`-`258` 的 `_payload_with_terminal_summary()` 在 durable memory projection 路径也用同一 helper 合并 terminal 文本。
- `dayu/host/memory.py:1621`-`1627` 的 `_selected_assistant_item()` 用同一 helper 读取 selected recent window 文本，并在缺失时 fallback 到 `_ref_summary_text(event)`。
- `dayu/host/durable/run_transition.py:4209`-`4238` 的 `RUN_SUCCEEDED` canonical payload 主要保存 `terminal_summary_ref` / `terminal_summary_digest`、reason、finish fields；不稳定内联 final answer。
- `dayu/host/engine_ingest.py:4301`-`4306` 证明 terminal summary artifact `content` 来自 Engine final answer content。
- `dayu/host/memory.py:1686`-`1712` 的 `_session_summary_from_accepted_event()` 只从 accepted compact candidate 的 `session_summary.summary_text` 物化 Session Summary Memory；该路径必须保持不变。

## Affected Files / Modules

Plan gate 已写：

- `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md`

Implementation gate 预计修改：

- `dayu/host/terminal_summary_payload.py`
- `dayu/host/run_input.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `dayu/host/compaction_evidence.py`
- focused tests under `tests/host/`

Implementation gate 预计只读 / 验证：

- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/compact_material.py`
- `docs/host/design.md`
- `docs/engine/design.md`
- `dayu/host/README.md`
- `tests/README.md`

## Contract / Schema / State-machine / Public-interface Changes

Expected none.

- 不新增或修改 EventLog schema。
- 不修改 `RUN_SUCCEEDED` canonical payload contract。
- 不修改 terminal summary artifact 持久化职责；仍由 existing terminal summary ref / digest 指向 artifact。
- 不修改 Engine `FinalAnswerData`、Host public API、Conversation Memory snapshot schema、compact input/output schema 或 Host state machine。
- 若实现发现必须新增 public field、schema migration 或 terminal closeout state transition，停止，不进入 implementation。

## Exact Implementation Decisions

1. 新增独立 helper，替换旧 summary helper。
   - 在 `dayu/host/terminal_summary_payload.py` 中删除 `assistant_summary_from_payload` 和 `PayloadSummaryTextPolicy`。
   - 新增 `PayloadTextReadPolicy`，只保留 `STRICT_NON_EMPTY` 与 `LENIENT_NON_EMPTY` 两种策略。
   - `STRICT_ALLOW_EMPTY` 策略明确删除，不保留兼容 alias；空白 `final_answer` / terminal `content` 不是有效 assistant continuity。
   - durable memory hydration 与 run input inline delta hydration 均使用 non-empty 语义；空白 `final_answer` 应被视为缺失，并继续尝试读取 digest-checked terminal summary artifact `content`。
   - 新增 `assistant_final_answer_text_from_run_payload(payload, *, text_policy)`：只读取 `final_answer`。
   - 新增 `terminal_summary_content_text_from_payload(payload, *, text_policy)`：只读取 terminal summary artifact 的 `content`。
   - 新增 `assistant_final_answer_continuity_text(transaction, run_payload, *, text_policy)`：先读 RUN payload 的 `final_answer`；缺失时读取 `terminal_summary_ref` / `terminal_summary_digest` 指向的 artifact，并只从 artifact 读 `content`。
   - 以上 helper 均不得读取 `summary_text` 或 nested `summary`；disallowed fields 即使存在也忽略。
   - strict 策略只对允许字段的非法类型抛 `HostDurableError`；lenient 策略把允许字段非法类型、空白文本或缺失都视为无 continuity 文本。

2. terminal content 只能在 digest-checked artifact 解析后进入 assistant continuity。
   - `RUN_SUCCEEDED` payload 中裸 `content` 不作为 final answer 来源。
   - `_payload_with_terminal_summary()` 应改名为 `_payload_with_assistant_final_answer()` 或等价语义名。
   - `_payload_with_assistant_final_answer()` 的 early-return guard 只检查 RUN payload 的非空 `final_answer`；不得因为 RUN payload 中存在 `content`、`summary_text` 或 nested `summary` 而跳过 terminal artifact lookup。
   - 空白 `final_answer` 不得阻止 terminal artifact `content` hydration；若 artifact `content` 非空且 digest 校验通过，应使用 artifact `content` 作为 transient `final_answer`。
   - 当 helper 从 terminal artifact 读到 `content` 时，合并到 transient projection payload 的 `final_answer` 字段，而不是 `content` 字段。该合并只服务 memory/run-input projection，不改写 EventLog canonical payload。

3. selected recent window 缺失 assistant final answer 时跳过。
   - `dayu/host/memory.py` 中 `_selected_assistant_item()` 改为返回 `SelectedRecentWindowItem | None`。
   - `project_conversation_memory_event()` 调用 `_selected_assistant_item()` 后必须显式 guard `None`；在 `RUN_SUCCEEDED` 且无 final answer continuity text 时跳过 `_replace_item_by_id(...)`，不替换 selected recent window。
   - 删除 `_selected_assistant_item()` 对 `_ref_summary_text(event)` 的 fallback；payload refs / digests / event ids 不得进入 assistant recent window。

4. RunInputBuilder 与 fallback message 只消费已收窄的 memory/material。
   - `dayu/host/run_input.py` 的 inline delta memory projection 使用新的 `_payload_with_assistant_final_answer()`。
   - review 阶段直接 grep 已确认 `_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event` 整条链无 production caller；implementation gate 需在最终 grep 确认后直接删除三者，不保留窄化迁移版本，也不留下条件迁移措辞。
   - fallback selected recent window 不需要另加字段过滤；只要 upstream `RunInputMaterialBlockKind.ASSISTANT_FINAL_ANSWER` 不再由 summary/ref 生产，fallback message 自然收窄。

5. Compaction answer material 只从 final answer continuity 生成。
   - `dayu/host/compaction_evidence.py` 的 `_assistant_history_materials()` 使用 `assistant_final_answer_continuity_text(...)`。
   - 只在读到 final answer / terminal content 时返回 `InitialHistoryMaterial(kind=ASSISTANT_FINAL_ANSWER)`。
   - 仅 `summary_text` / nested `summary` / ref 可用时返回空 tuple。
   - `dayu/host/compact_material.py` 不需要 schema 或 section 改动；它已经只把 `ASSISTANT_FINAL_ANSWER` block 映射到 `answer_material`。

6. Session Summary Memory 不改源。
   - 不修改 `_session_summary_from_accepted_event()` 的生产者语义。
   - 可增加负向测试，证明 `RUN_SUCCEEDED.summary_text` 和 terminal summary `summary_text` 不会生成 `session_summary_memory`。
   - 不把 terminal summary artifact 的 `content` 写入 `session_summary_memory`。

## Small Implementation Slices

### Slice 1: Helper Contract Replacement

Allowed files/modules:

- `dayu/host/terminal_summary_payload.py`
- `tests/host/test_terminal_summary_payload.py`（新建测试文件）

Exact actions:

- 删除旧 helper 与旧 enum 的 exports。
- 实现 `PayloadTextReadPolicy` 与三个新 helper。
- 覆盖测试：
  - run payload `final_answer` 可读。
  - run payload 空白 `final_answer` 返回 `None`，不算有效 continuity。
  - run payload `content`、`summary_text`、nested `summary` 均不被 run helper 读取。
  - terminal artifact payload `content` 可读。
  - terminal artifact payload 空白 `content` 返回 `None`，不算有效 continuity。
  - terminal artifact payload `summary_text`、nested `summary` 均不被 terminal content helper 读取。
  - allowed field 非字符串时 strict 抛错、lenient 返回 `None`。
  - disallowed `summary_text` 非字符串不触发 strict error。

### Slice 2: Memory Projection Source Narrowing

Allowed files/modules:

- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `tests/host/test_memory_projection.py`
- durable memory projection focused tests if existing fixtures require them

Exact actions:

- durable projection hydration 改用 `assistant_final_answer_continuity_text(...)` 并把 terminal content 合并为 transient `final_answer`。
- durable projection 原 `STRICT_ALLOW_EMPTY` 路径迁移为 non-empty 语义；空白 `final_answer` 必须继续尝试 terminal artifact `content`，不得 early return。
- direct memory projection 中 assistant event 无 final answer 时跳过 selected assistant item。
- 移除 assistant selected item 的 ref fallback。
- 覆盖测试：
  - `RUN_SUCCEEDED` 同时有 `final_answer` 与 `summary_text` 时 selected recent window 使用 `final_answer`。
  - `RUN_SUCCEEDED` 有空白 `final_answer` 与有效 terminal artifact `content` 时，selected recent window 使用 terminal artifact `content`。
  - 只有 `summary_text` / nested `summary` 时不生成 assistant selected recent item。
  - 缺失 final answer 时不出现 `payload_ref=`、`payload_digest=` 或 `event_ref=` 文本。
  - accepted `CONTEXT_COMPACTED.session_summary.summary_text` 仍能生成 Session Summary Memory。
  - `RUN_SUCCEEDED.summary_text` 不能生成 Session Summary Memory。

### Slice 3: RunInput / History / Fallback Projection

Allowed files/modules:

- `dayu/host/run_input.py`
- `tests/host/test_run_input_builder.py`

Exact actions:

- inline delta projection hydration 改用新 helper。
- 在最终 `rg` 确认后删除 dead helper 链：`_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event`。不得保留只读 `final_answer` 的迁移版本。
- 保持 fallback renderer 不变，但通过 tests 证明 upstream block 不再由 summary/ref 生产。
- 覆盖测试：
  - RUN_SUCCEEDED payload 有 terminal_summary_ref/digest 且 artifact 同时含 `content` 与 `summary_text` 时，后续 run input / selected recent assistant message 使用 artifact `content`。
  - artifact 只有 `summary_text` 或 nested `summary` 时，不生成 assistant history message。
  - fallback selected recent window 只渲染 final answer content，不渲染 summary/ref fallback。

### Slice 4: Compaction History / Answer Material

Allowed files/modules:

- `dayu/host/compaction_evidence.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compact_material.py` if needed for direct material mapping assertion

Exact actions:

- `_assistant_history_materials()` 通过新 helper 读取 final answer continuity。
- 保持 `CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER` 是进入 `answer_material` 的唯一 block kind。
- 覆盖测试：
  - RUN_SUCCEEDED `final_answer` 进入 `InitialHistoryMaterial(kind=ASSISTANT_FINAL_ANSWER)`。
  - RUN_SUCCEEDED terminal summary artifact `content` 进入 history material。
  - RUN_SUCCEEDED 只有 `summary_text` / nested `summary` 时 history material 为空。
  - `ConversationCompactInputVNext.answer_material[*].answer_text` 不来自 `summary_text`。

### Slice 5: Imports, Dead Names, README Check

Allowed files/modules:

- touched Host modules and tests above
- `dayu/host/README.md` and `tests/README.md` only if inspection finds current docs contradict implementation

Exact actions:

- `rg -n "assistant_summary_from_payload|PayloadSummaryTextPolicy|summary_text.*assistant|nested summary" dayu/host tests/host`，确认旧 helper 和旧 summary fallback 不残留。
- `rg -n "STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu/host tests/host`，确认旧 empty 策略与 dead helper 链无残留。
- 不新增 compatibility alias。
- 检查 `dayu/host/README.md` 与 `tests/README.md` 是否描述旧 summary fallback；若无不一致，不改 README。

## Required Tests / Validation Commands

Implementation gate 必须在 `source .venv/bin/activate` 后运行 focused tests 与 pyright。

Focused validation:

```bash
source .venv/bin/activate && pytest \
  tests/host/test_terminal_summary_payload.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_compact_material.py \
  tests/host/test_engine_ingest_mapping.py
```

Expected assertions:

- final answer helper 不读取 `summary_text` / nested `summary`。
- selected recent window 在 `summary_text` only case 不生成 assistant item。
- terminal summary artifact `content` 被 digest-checked 后可作为 assistant final answer continuity。
- compact `answer_material` 只含 final answer / terminal content，不含 summary fallback。
- Session Summary Memory 仍只由 accepted `CONTEXT_COMPACTED.session_summary` 生产。
- Engine ingest final answer mapping 仍写 terminal summary artifact `content`，无行为回退。

Type validation:

```bash
source .venv/bin/activate && pyright
```

Search validation:

```bash
rg -n "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests
rg -n "STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu tests
rg -n "summary_text" dayu/host/run_input.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compaction_evidence.py
```

Expected search result:

- 旧 helper / old enum 无残留。
- `STRICT_ALLOW_EMPTY` 与 `run_input.py` dead helper 链无残留。
- `summary_text` 只保留在 accepted compact session summary、compact candidate、test fixtures 或明确非 assistant-final-answer 语义处。

## Docs Decision

Plan gate 不更新 README。

Implementation gate 触发 Host 和 tests README 检查：

- 若 `dayu/host/README.md` 已只描述 Conversation Memory 的稳定五类视图、Session Summary 来源和 final answer continuity，不实际修改。
- 若发现 README 仍写 terminal summary / `summary_text` 可作为 assistant answer fallback，必须同步删除旧表述。
- 若 `tests/README.md` 不涉及该 helper 或 fallback 语义，不实际修改。

## Risks / Open Questions

- `run_input.py` 中历史 successful run pair helper 链已由 review grep 判定为 dead code；implementation 只做最终 grep 确认后删除，不再保留迁移选项。
- import-cycle 处理采用明确 fallback：静态分析显示 `terminal_summary_payload.py` 当前是轻量 reader module，`payload_resolution.py` / durable transaction 依赖链未反向导入它，可先尝试把 transaction-aware resolver 放在 `terminal_summary_payload.py` 并用 import smoke 验证；若出现 import cycle，则把 `assistant_final_answer_continuity_text(...)` 移入 `dayu/host/_terminal_answer.py`，`terminal_summary_payload.py` 只保留两个纯 field reader。不得使用 callback indirection，也不得复制字段读取策略。
- 旧测试 fixture 可能把 `display_text`、`content` 或 `summary_text` 当作 RUN_SUCCEEDED assistant 文本。implementation 应迁移 fixture 到 `final_answer` 或 terminal artifact content，而不是在生产代码里保留兼容读取。
- 如果现有 durable data 中存在只有 `summary_text` 的 `RUN_SUCCEEDED`，本 work unit 按全新 schema / fail-closed 处理，不做旧库兼容读取。

Blocking open questions: none. 现有设计真源足以裁决 final answer vs terminal content 来源，不需要 schema/public contract/state-machine 变更。

## Why This Is Not Over-designed

本计划只拆分一个混合语义 helper，并迁移现有调用点到显式字段读取。它不新增 memory category、不新增 state machine、不扩 schema、不引入 recall subsystem，也不把 terminal summary 重新设计成事实源。新增 helper 的原因是字段来源本身有不同 truth owner：RUN payload 的 `final_answer` 与 terminal artifact 的 `content` 必须分开读取，否则无法防止 `summary_text` 再次作为 assistant answer fallback 混入。

## Completion Report Format

Implementation / fix gate 完成后按以下格式报告：

- artifact path: `<implementation or fix artifact path>`
- implementation verdict: ready / blocked
- changed files: `<files>`
- key behavior changes: `<short bullets>`
- validation run: `<commands and results>`
- README decision: updated / checked-no-change
- residual risks or blocking open questions: `<none or listed>`

## Plan Verdict

ready
