# P3 OLD / NEW Conversation Memory Code Review

## 复查结论（2026-05-07）：不通过

本次复查动机成立：`pinned_state`、older raw turns 消费顺序、EvidenceAnchor / tool fact 的 LLM-facing source cursor 都属于 P3 已声明的 #48 / OLD 兼容不变量，不是 P4+ 持久化、compaction 或 governance 才能判断的后续能力。

原文标注“已修复，待复查”的三项 finding 复查结果：通过。

- `pinned_state` 独立全量路径已真实修复：当前 `ConversationPinnedState` 明确承载 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions` 四槽，并作为 `ConversationMemorySnapshot.pinned_state` 存在：`dayu/host/_conversation_memory.py:188`、`dayu/host/_conversation_memory.py:269`、`dayu/host/_conversation_memory.py:473`。RunInputBuilder 在 memory block 开头调用 `_append_pinned_state`，通过 `include_stable_without_provenance` 预算外注入：`dayu/host/_run_input_builder.py:178`、`dayu/host/_run_input_builder.py:373`、`dayu/host/_run_input_builder.py:569`。测试覆盖 `memory_block_char_budget=1` 时 pinned state 仍全量出现：`tests/host/test_phase3_run_input_builder.py:389`。
- older raw turns 已改为“从新到旧预算消费、时间顺序渲染”：`_append_older_raw_turns` 对 `snapshot.older_raw_turns` 使用 `reversed(...)` 抢预算，成功预留后再反转追加文本：`dayu/host/_run_input_builder.py:741`。测试证明预算不足时保留 newest older、排除 oldest older，且若 middle older 同时存在则在 newest 前渲染：`tests/host/test_phase3_run_input_builder.py:410`。
- EvidenceAnchor / tool fact 的 LLM-facing source cursor 已真实修复：`_format_anchor` 输出 `source_event_cursor={anchor.origin_event_cursor.sequence}`，`_format_tool_fact` 输出 `source_event_cursor={fact.provenance.source_event_cursor.sequence}`：`dayu/host/_run_input_builder.py:801`、`dayu/host/_run_input_builder.py:818`。测试断言 system memory block 包含 `source_event_cursor=4`：`tests/host/test_phase3_run_input_builder.py:282`。

不计为 P3 bug 的后续能力：自动从用户输入 / tool facts / compaction 生成 pinned state patch、持久化 archive、多进程恢复、完整 compaction scene 与 governance 更新路径，仍属于设计中明确后移的 P4+ 范围；当前 P3 只要求结构、注入路径和不变量可用。

### [已修复，待复查] Finding: Medium - `design.md` 第 12 节声明 verified claims / assumptions 属于预算外 stable layer，但当前 builder 会按 memory block 预算裁剪

证据位置：

- `docs/host/design.md` 第 12 节把 `verified claim ledger` 与 `assumption register` 放在 `pinned / stable layer` 下，并声明该层“永远全量，不参与历史 token 池”：`docs/host/design.md:1197`。
- 同节又明确：`pinned_state`、task frame、verified claims、assumptions 等 stable layer 不参与历史池竞争：`docs/host/design.md:1258`。
- 当前实现只有 `pinned_state` 与 `TaskFrame` 使用 `include_stable_without_provenance` 预算外写入：`dayu/host/_run_input_builder.py:373`、`dayu/host/_run_input_builder.py:541`、`dayu/host/_run_input_builder.py:569`。
- `verified_claims` 与 `assumptions` 使用普通 `collector.include(...)`，会在 `_has_budget_for` 失败时被 `memory_block_budget_exhausted` 排除：`dayu/host/_run_input_builder.py:281`、`dayu/host/_run_input_builder.py:595`、`dayu/host/_run_input_builder.py:622`。
- 现有测试只验证 pinned state 在极小预算下仍全量注入，未验证 verified claim ledger / assumption register 是否符合 `design.md` 的 stable layer 口径：`tests/host/test_phase3_run_input_builder.py:389`。

问题：

若以 `docs/host/design.md` 第 12 节作为当前 P3 已落地语义，当前实现会在预算紧张时裁掉 verified claims / assumptions，这与“stable layer 全量、不参与历史池竞争”的声明不一致。对财报 Agent 来说，verified claim ledger 是已验证事实账本，assumption register 是用户假设 / 待验证假设边界；如果它们被普通 history budget 裁剪，模型可能保住 raw turn 摘要，却丢掉更应稳定注入的事实 / 假设状态。

影响：

该问题不推翻本次复查的三项修复结论，也不属于 #48 对 `pinned_state` 的最低不变量缺口；但它属于当前 P3 文档声明与实现不一致。后续如果 P4 接入 compaction / verified projection，会遇到“verified ledger 到底是 stable truth layer 还是 budgeted history item”的语义分叉。

建议：

二选一收敛语义：如果最佳财报记忆语义要求 verified claims / assumptions 与 pinned/task frame 同属 stable layer，则改 builder 使用预算外注入并补极小预算测试；如果 P3 出于 memory 克制只要求 `pinned_state` / task frame 预算外，则应修订 `docs/host/design.md` 第 12 节，把 verified claims / assumptions 明确标为有预算的受控 ledger，避免文档把后续目标写成当前事实。

---

## 原审查结论：不通过；以下 finding 已由修复 Agent 处理，待复查确认。

当前 P3 实现守住了多项关键禁区：`USER_INPUT_ACCEPTED` 已作为 Engine 启动前的 canonical 用户输入事实；RunInputBuilder 生产路径不再从 `StartRunRequest.input` 回放历史；assistant final answer 没有自动进入 verified claim ledger；tool facts / evidence anchors 以 system memory block 的独立 section 注入，没有混入 assistant history；Host 也没有 import `dayu.fins`。

但仍有一个阻塞语义缺口：#48 / OLD / P3 plan 要求继承 `pinned_state` 独立全量路径，而当前 NEW 只实现了 `TaskFrame`，没有承载 OLD `current_goal / confirmed_subjects / user_constraints / open_questions` 的 pinned_state slot。因此当前实现尚未真正守住 #48 的核心不变量。

## Findings

### [已修复，待复查] Critical: 缺失 OLD / #48 要求的 `pinned_state` 独立全量路径

证据位置：

- GitHub issue #48 明确 `pinned_state` 是会话稳定目标的核心，包含 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions` 四字段，并要求永远全量渲染、不参与池竞争。
- OLD 定义四槽 pinned state：`/Users/leo/workspace/dayu-agent/dayu/host/conversation_store.py:228`。
- OLD 渲染独立 pinned block：`/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py:213`。
- P3 plan 要求继承 `pinned_state` 独立路径：`docs/host/phase3-plan.md:345`、`docs/host/phase3-plan.md:382`。
- 当前 NEW `ConversationMemorySnapshot` 只有 `task_frame`，没有 `ConversationPinnedState` / `pinned_state` 字段：`dayu/host/_conversation_memory.py:252`。
- 当前 RunInputBuilder 只注入 `TaskFrame`：`dayu/host/_run_input_builder.py:446`。

问题：

当前实现把 stable layer 收缩成 `TaskFrame(topic_ref/entity_refs/period_refs/basis_refs/unit_ref)`，没有 OLD / #48 的会话目标、已确认对象、用户约束、未决问题四槽。`TaskFrame` 可以是财报分析任务框架，但不能等价替代 `pinned_state`：它缺少用户约束和 open questions 等跨轮治理语义。

影响：

这会破坏 #48 的核心不变量：“目标稳定”必须由 pinned_state 独立全量注入保证。财报追问中，“用 IFRS 口径”“先保留这个估值假设”“毛利率下滑原因待解释”等信息可能无法进入稳定区，只能退化为 raw turn 摘要或未来未定义 projection，后续 P4 compaction 接入时也缺少同源 slot。

建议：

在 `ConversationMemorySnapshot` 增加 Host 中立 `ConversationPinnedState` 或等价结构，字段至少覆盖 OLD 四槽，并在 RunInputBuilder 的 stable section 全量注入。`TaskFrame` 可以保留，但应与 `pinned_state` 并列，而不是替代它。

### [已修复，待复查] Medium: older raw turns 预算消费顺序与 #48 “从新到旧”不一致

证据位置：

- issue #48 的总池算法要求更老 raw turn 按预算从新到旧回放。
- P3 plan 固定输入顺序为“更老 raw turn 按预算从新到旧”：`docs/host/phase3-plan.md:371`。
- OLD `DefaultWorkingMemoryPolicy.select_turns` 对 older turns 使用 `reversed(older_turns)`，预算消费从新到旧：`/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py:728`。
- 当前 NEW `_append_older_raw_turns` 直接按 `snapshot.older_raw_turns` 原顺序遍历：`dayu/host/_run_input_builder.py:620`。

问题：

`_split_turns` 产出的 `older_raw_turns` 是从旧到新保存；builder 再按原顺序消费，预算不足时会优先保留最旧历史，反而丢掉更接近当前追问的 older turns。

影响：

这不影响 recent floor 的 oversized 降级，但会削弱 #48 的“预算允许则向更老历史扩展”的语义。长会话中，recent floor 之外最相关的历史通常是离当前最近的 older turn，当前顺序会让较旧内容抢占预算。

建议：

`_append_older_raw_turns` 应从 `reversed(snapshot.older_raw_turns)` 开始尝试纳入，并在最终渲染时保持模型可读的时间顺序，或显式记录按相关性/时间倒序消费的设计理由并补测试。

### [已修复，待复查] Medium: EvidenceAnchor 的 LLM-facing 文本缺少 source event cursor

证据位置：

- P3 plan review gate 要求检查 RunInputBuilder 输出是否保留 anchor id / source cursor：`docs/host/phase3-plan.md:652`。
- 当前 `EvidenceAnchor` 数据结构包含 `origin_event_cursor`：`dayu/host/_conversation_memory.py:132`。
- 当前 `_format_anchor` 输出 `anchor_id`、`tool_call_id`、`source_ref`、`chunk_ref`、`fingerprint`、`summary`，未输出 `origin_event_cursor`：`dayu/host/_run_input_builder.py:675`。
- 当前 `_format_tool_fact` 同样未输出 source event cursor：`dayu/host/_run_input_builder.py:691`。

问题：

结构层和 trace 层保留了来源 cursor，但进入模型上下文的 Evidence Anchors section 没有显式 source cursor。这样 LLM 只能看到 anchor id 和摘要，看不到该 anchor 对应的 canonical EventLog 位置。

影响：

这会降低后续回答中引用证据锚点的可追溯性，也让“anchor 不被自然语言 summary 替代”的语义不够完整。对财报 Agent 来说，source cursor 是 audit / replay / 后续补查的重要稳定引用。

建议：

在 `_format_anchor` 和 `_format_tool_fact` 的文本中加入 `origin_event_cursor.sequence` / `source_event_cursor.sequence`。同时保留当前 trace 中的来源记录，并补一个断言 RunInput system block 包含 source cursor 的测试。

### Info: `USER_INPUT_ACCEPTED` canonical gate 基本守住

证据位置：

- `LocalRunHarness.start_run` 先从 ingress request 提取当前用户输入，再 append `USER_INPUT_ACCEPTED`：`dayu/host/_run_harness.py:176`。
- append 成功后才读取 snapshot 并调用生产 `run_input_builder.build`：`dayu/host/_run_harness.py:186`。
- Engine 实际收到的是 `replace(request, input=build_result.run_input)`：`dayu/host/_run_harness.py:194`。
- builder 强校验当前用户事件必须是 canonical Host-owned `USER_INPUT_ACCEPTED`：`dayu/host/_run_input_builder.py:425`。
- append 失败不启动 Engine 的测试覆盖：`tests/host/test_phase3_boundary.py:230`。

问题：

未发现投影 / replay 从 `StartRunRequest.input` 旁路读取历史的路径。`_extract_current_user_text` 仍读取 `request.input.messages`，但它位于 ingress 边界，用于生成 canonical event，符合设计中“StartRunRequest.input 仅作为 ingress 材料”的口径。

建议：

后续若 public API 从 `RunInput` 改成更明确的 `user_text` / `SessionRunRequest`，可以减少多条 `UserMessage` 被拼接成当前输入的歧义；P3 当前不构成阻塞。

### Info: assistant final answer 没有自动升级 verified claim

证据位置：

- final answer 只投影到 `ConversationRawTurn.assistant_final`，trust level 为 `ASSISTANT_CONCLUSION`：`dayu/host/_conversation_memory.py:531`。
- `_project_canonical_events` 没有把 final answer 写入 `verified_claims`：`dayu/host/_conversation_memory.py:493`。
- 测试覆盖 final 不进入 verified / assumptions：`tests/host/test_phase3_conversation_memory_projection.py:252`。

问题：

未发现 final -> verified ledger 的自动投影。

建议：

保留该边界。后续 user-confirmed correction / evidence-backed projection 进入 verified ledger 时，应继续要求显式 provenance 与 status。

### Info: tool facts / evidence anchors 没有混入 assistant history

证据位置：

- builder 只输出 system memory block + current user message，不生成 assistant / tool history message：`dayu/host/_run_input_builder.py:210`。
- evidence anchors 与 tool facts 有独立 section：`dayu/host/_run_input_builder.py:528`。
- raw turns 只包含 user 与 assistant_final 摘要：`dayu/host/_conversation_memory.py:903`。
- 测试确认没有 assistant / tool message：`tests/host/test_phase3_run_input_builder.py:270`。

问题：

未发现 OLD `_render_tool_summary_block` 那种“工具摘要拼进 assistant history”的迁回。

建议：

保持 tool facts / evidence anchors 独立 section，并修复上面的 source cursor 输出缺口。

### Info: recent floor oversized 降级已实现

证据位置：

- recent raw turn 的原文超过 `_RECENT_TURN_INLINE_CHAR_LIMIT` 时先记录 excluded，再注入摘要：`dayu/host/_run_input_builder.py:583`。
- raw turn 摘要分别限制 user 与 assistant final 字符数：`dayu/host/_conversation_memory.py:903`。
- 测试覆盖超大 recent turn 被降级且当前用户问题不被挤掉：`tests/host/test_phase3_run_input_builder.py:312`。

问题：

未发现“recent floor = 超大旧轮全文无限保底”的实现。

建议：

补充 older raw turns 从新到旧消费测试后，该块即可较完整覆盖 #48 recent floor 语义。

### Info: Host 中立边界守住，未 import `dayu.fins`

证据位置：

- Host import boundary 测试扫描 `dayu.host` 禁止 `dayu.fins` / `dayu.service` / `dayu.ui`：`tests/host/test_import_boundary.py:10`。
- 当前 `rg` 未发现 `dayu/host/*.py` import `dayu.fins`。
- NEW memory 结构使用 opaque `TaskFrame` / `EvidenceAnchor` / `MemoryClaim`，生产代码未内嵌公司、期间、页码、XBRL 等财报业务抽取规则：`dayu/host/_conversation_memory.py:118`、`dayu/host/_conversation_memory.py:142`、`dayu/host/_conversation_memory.py:170`。

问题：

未发现 Host 反向理解财报语义或绕过 `dayu.fins.storage` 的生产代码。

建议：

保持由 fins / tool facts 产生业务引用，Host 只承载 opaque typed reference。

## OLD / NEW 对照表

| 语义点 | OLD 参考 | NEW 当前实现 | 结论 |
|---|---|---|---|
| 运行态 / 展示态分离 | `ConversationSessionArchive` 明确 `runtime_transcript` 供 memory / prompt，`history_archive` 承载 reasoning 且仅展示：`conversation_session_archive.py:5`；`ConversationSessionState.record_reasoning_delta` 也声明不进运行态：`scene_preparer.py:224`。 | preview / reasoning 事件在 EventLog 中为 preview，memory projection 只消费 canonical：`dayu/host/_conversation_memory.py:383`；测试覆盖 reasoning / content completed 不进 RunInput：`tests/host/test_phase3_boundary.py:278`。 | 通过 |
| 用户输入 canonical 真源 | OLD transcript 直接持有 user_text；NEW plan 要求提升为 EventLog 事实。 | `start_run` append `USER_INPUT_ACCEPTED` 后才 build / start Engine：`dayu/host/_run_harness.py:176`；builder 只接受 canonical Host event：`dayu/host/_run_input_builder.py:425`。 | 通过 |
| `pinned_state` 独立全量 | OLD `ConversationPinnedState` 四槽独立：`conversation_store.py:228`；`_render_pinned_state_block` 独立渲染：`conversation_memory.py:213`；#48 要求永远全量、不参与池竞争。 | 当前只有 `TaskFrame`，没有 `pinned_state` 四槽；stable section 只输出 topic/entity/period/basis/unit：`dayu/host/_run_input_builder.py:446`。 | 不通过 |
| assistant final vs verified claim | OLD episode summary 有 confirmed_facts，但 final 本身不是 verified 真源；P3 plan 明确禁止 final 自动升级 verified。 | final 只进入 raw turn，`verified_claims` 不变：`dayu/host/_conversation_memory.py:531`、`dayu/host/_conversation_memory.py:493`。 | 通过 |
| tool summary / evidence anchors | OLD `_render_tool_summary_block` 把工具摘要拼入 assistant_text；P3 plan 要求改为独立结构化事实。 | NEW 以 Evidence Anchors / tool facts section 注入，未生成 assistant/tool message：`dayu/host/_run_input_builder.py:528`、`tests/host/test_phase3_run_input_builder.py:270`。 | 基本通过；source cursor 输出缺口 |
| recent floor | OLD #48 将 `working_memory_max_turns` 反转为 `recent_turns_floor` 下限，并有 oversized 兜底：`conversation_memory.py:674`。 | recent raw turn 超大时摘要化并记录 trace：`dayu/host/_run_input_builder.py:583`。 | 基本通过 |
| older pool 消费顺序 | OLD older turns 从新到旧消费预算：`conversation_memory.py:728`。 | NEW 按 older_raw_turns 原顺序消费，倾向先保留最旧历史：`dayu/host/_run_input_builder.py:620`。 | 不通过 |
| compaction / persistent archive | OLD 有 file archive、同步 / 后台 compaction、LLM compaction scene：`conversation_store.py:501`、`conversation_memory.py:1318`。 | P3 只保留 in-memory projection 与 episode summary slot，没有迁回 file archive / compaction：`dayu/host/_conversation_memory.py:357`、`dayu/host/_run_input_builder.py:182`。 | 通过 |
| Engine 内 memory 禁止迁回 | OLD scene preparer 强耦合 Agent / memory / archive。 | Engine 代码不 import Host memory，Host 通过 `EngineWorker` 只传最终 messages：`dayu/host/_worker.py:41`；边界测试扫描 Engine import：`tests/host/test_phase3_boundary.py:263`。 | 通过 |
| Host 中立 | 设计要求 Host 不懂 fins/doc/web 业务语义。 | Host 生产代码未 import `dayu.fins`，memory 结构为 opaque refs。 | 通过 |

## Open Questions

1. P3 是否接受用 `TaskFrame` 替代 OLD `pinned_state`？如果接受，需要修订 issue #48 / P3 plan 的验收口径；如果不接受，应补 `ConversationPinnedState` 并作为 stable layer 第一等结构。
2. EvidenceAnchor 的 `source_event_cursor` 是否必须 LLM-facing？P3 plan 的 review gate 写的是 RunInputBuilder 输出保留 anchor id / source cursor；当前只有 trace 保留 cursor。
3. `ClaimCorrectionPatch` 当前可以把任意 `MemoryClaim` 追加进 verified ledger。P3 是否需要在 internal patch 层校验 status / provenance / ingestion policy，还是留给后续 public correction API？
4. 失败 / 取消 run 是否应该把 `USER_INPUT_ACCEPTED` 投影进 memory？当前 harness 只在 `terminal_seen` 为 true 时投影，而 worker failure append 后不会设置 `terminal_seen`。

## Review Notes

- 已对照 `docs/host/design.md` 第 12 节、`docs/host/phase3-plan.md`、GitHub issue #48、OLD `conversation_memory.py`、`conversation_store.py`、`conversation_session_archive.py`、`scene_preparer.py` 与当前 NEW `dayu/host` / `tests/host` 实现。
- 本 review 只写文档，未修改生产代码。
- 本次未运行测试或 pyright；审查以静态证据和现有测试内容为准。

---

## 复查结论（2026-05-07 第二轮）：通过

本次复查动机成立：`design.md` 已把 verified claim ledger / assumption register 定义为 pinned / stable layer，若 RunInputBuilder 仍按普通 history budget 裁剪，会造成财报分析中“已验证事实账本 / 假设边界”与运行态输入不一致。当前实现、测试、README / design 已收敛到同一语义，复查结论：通过。

新增 Medium finding 已修复：

- `DefaultRunInputBuilder` 已提供 `include_stable(...)`，该路径不调用 `_has_budget_for(...)`，直接把带溯源 stable item 写入 memory block，并在 trace 中保留来源 cursor：`dayu/host/_run_input_builder.py:409`。
- `_append_verified_claims(...)` 对非空 verified claims 使用 `collector.include_stable(...)`；空 ledger 占位也使用 `include_stable_without_provenance(...)`：`dayu/host/_run_input_builder.py:645`、`dayu/host/_run_input_builder.py:652`。
- `_append_assumptions(...)` 对非空 assumptions 使用 `collector.include_stable(...)`；空 register 占位也使用 `include_stable_without_provenance(...)`：`dayu/host/_run_input_builder.py:672`、`dayu/host/_run_input_builder.py:679`。
- 测试已覆盖 `memory_block_char_budget=1` 时 verified claim 与 assumption 仍进入 system memory block，且对应 trace item 不出现 excluded：`tests/host/test_phase3_run_input_builder.py:413`。
- `docs/host/design.md` 仍声明 verified claim ledger / assumption register 位于 pinned / stable layer，且 stable layer 全量渲染、不扣 history pool budget：`docs/host/design.md:1199`、`docs/host/design.md:1262`、`docs/host/design.md:1270`。
- `dayu/host/README.md` 已同步当前事实：verified claims 与 assumptions 属于 stable ledger，全量注入且不参与 history pool 预算竞争：`dayu/host/README.md:50`。

三项已修复 finding 快速回归确认：

- `pinned_state` 独立全量未回归：`ConversationPinnedState` 仍保留 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions` 四槽，`ConversationMemorySnapshot` 仍包含 `pinned_state`；builder 通过 `include_stable_without_provenance(...)` 全量注入，测试覆盖极小预算下仍输出四槽：`dayu/host/_conversation_memory.py:191`、`dayu/host/_conversation_memory.py:275`、`dayu/host/_run_input_builder.py:608`、`tests/host/test_phase3_run_input_builder.py:392`。
- older raw turns 新到旧消费、时间顺序渲染未回归：`_append_older_raw_turns(...)` 仍对 `snapshot.older_raw_turns` 使用 `reversed(...)` 抢预算，成功预留后再反转追加文本；测试覆盖 newest older 保留、oldest older 被裁剪，且 middle / newest 若同时出现则按时间顺序渲染：`dayu/host/_run_input_builder.py:781`、`dayu/host/_run_input_builder.py:804`、`tests/host/test_phase3_run_input_builder.py:447`。
- EvidenceAnchor / tool fact 的 LLM-facing source cursor 未回归：`_format_anchor(...)` 输出 `source_event_cursor={anchor.origin_event_cursor.sequence}`，`_format_tool_fact(...)` 输出 `source_event_cursor={fact.provenance.source_event_cursor.sequence}`；测试断言 system memory block 包含 `source_event_cursor=4`，且不包含 `scope_token`：`dayu/host/_run_input_builder.py:840`、`dayu/host/_run_input_builder.py:857`、`tests/host/test_phase3_run_input_builder.py:286`。

本次仅做静态复查并追加 review 文档，未修改生产代码或测试，未运行测试 / pyright。
