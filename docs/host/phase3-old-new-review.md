# P3 OLD / NEW Conversation Memory Plan Review

## 结论

通过。

`docs/host/phase3-plan.md` 对 GitHub issue #48 的关键不变量、OLD conversation memory 的可继承语义，以及必须后移 / 禁止迁回的实现边界表达充分；当前未发现阻塞 P3 handoff 的 plan 问题。

## Findings

### Medium

无。

### Low

无。

### Info

#### OLD 当前 episode-first 预算消费细节不应被误当作 #48 必迁语义

- 证据位置：
  - GitHub issue #48 “最终方案 / 触发与消费算法”：历史单总池中先保最近 N 轮 raw turn，再按预算回放更老 raw turn，最后用剩余预算填 episode summaries。
  - OLD `/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py:1274`-`1291`：`build_messages` 先调用 `_build_memory_block` 扣 episode summaries，再把剩余预算交给 older raw turns。
  - OLD `/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py:1395`-`1439`：`_build_memory_block` 从最新 episode 开始消费 `total_budget`。
  - NEW `docs/host/phase3-plan.md:250`-`263`：RunInputBuilder 最小输入顺序要求 `recent_turns_floor` 保底后，按预算回放更老 raw turn / tool summary，并为后续 episode summaries 保留插入位；偏离顺序或把最近 N 轮做成上限必须停止修 plan。
- 问题：
  - 这不是 P3 plan 的缺陷，而是 review / 实施时容易混淆的 OLD/issue 差异。OLD 代码已经体现单总池与 `recent_turns_floor` 下限，但其 episode summary 消费顺序与 issue #48 文字方案并不完全一致。
- 影响：
  - 如果后续 code Agent 机械照搬 OLD `build_messages` 的 episode-first 扣预算细节，可能让 P3 实现偏离 #48 issue 与 NEW plan 对“更老 raw turn / tool summary 追问连续性优先”的表达。
- 建议：
  - P3 实施和 code review 以 issue #48 与 `phase3-plan.md` 的顺序为准；OLD 的可继承语义限定为 `pinned_state` 独立、单总池、recent floor 下限、tool summary 摘要参与 memory、reasoning 展示隔离，而不是逐行迁回 OLD episode-first 预算消费。

## OLD / NEW 对照表

| 主题 | OLD 直接证据 | NEW plan 判断 | Review 结论 |
|---|---|---|---|
| `pinned_state` 独立全量 | OLD `_render_pinned_state_block` 独立渲染；`_build_memory_block` 注释说明不消耗 `total_budget`（`conversation_memory.py:1395`-`1402`）。issue #48 明确“会话灵魂，永远在、不参与池竞争”。 | `phase3-plan.md:237`-`248` 要求全量进入 `[Conversation Memory]`，不参与 pool 裁剪，并为 P4 pinned patch 预留接入点。 | 正确继承。 |
| 历史 memory 单总池 | issue #48 明确删除 working / episodic 双独立预算池；OLD `DefaultWorkingMemoryPolicy` 文档称“基于单总池预算”（`conversation_memory.py:675`-`681`）。 | `phase3-plan.md:239`-`241`、`407` 要求单总池，并要求测试区分双池误实现。 | 正确继承；测试 gate 足够明确。 |
| 最近 N 轮 raw turn 是下限保底 | issue #48 明确 `working_memory_max_turns` 上限反转为 `recent_turns_floor` 下限；OLD `select_turns` 强制保留 tail 后再按预算补 older turns（`conversation_memory.py:713`-`736`）。 | `phase3-plan.md:242`-`245`、`408` 要求预算充足时不能被固定 N 轮天花板截断。 | 正确继承。 |
| memory 克制 | issue #48 明确 1M 档 cap 主动下调、长上下文优先留给财报材料。 | `phase3-plan.md:244`-`245`、`411`-`412` 要求默认裁剪倾向最小可用历史，并用测试或实现注释说明财报材料 / 工具结果窗口优先。 | 正确继承。 |
| `assistant_reasoning` / history archive | OLD `ConversationSessionArchive` 模块说明 `history_archive` 承载 `assistant_reasoning`，绝不进入运行态（`conversation_session_archive.py:1`-`9`）；`ConversationHistoryTurnRecord` 标注仅展示（`conversation_session_archive.py:44`-`61`）；`ConversationSessionState` 的 reasoning buffer 只在 `persist_turn` 投影到 history（`scene_preparer.py:188`-`228`）。 | `phase3-plan.md:190`-`213`、`269`-`290` 要求 reasoning / preview / delta 只进展示 read model，不进 RunInput / memory / RunInputBuilder，并禁止把 `assistant_reasoning` 放回运行态 transcript。 | 正确继承展示 read model 语义，未迁回运行态。 |
| OLD tool summary 参与 memory | OLD `_render_tool_summary_block` 将 `name`、`arguments`、`result_summary` 拼为历史工具摘要，并并入 assistant 历史视图（`conversation_memory.py:331`-`371`）。 | `phase3-plan.md:108`-`110`、`180`-`188`、`272` 要求只消费 ToolRuntime canonical facts 的中性摘要，禁止 `scope_token`、cursor 原文、完整大结果进入 memory。 | 正确迁移为 NEW 事实层摘要语义，不迁回完整结果 / cursor / scope token。 |
| `prepare_transcript` 同步 compaction | OLD `prepare_transcript` 在当前轮开始前用 `system_prompt` 与 `user_text` 判定并同步压缩（`conversation_memory.py:1167`-`1249`）。 | `phase3-plan.md:31`-`32`、`276`-`283` 明确 P3 不实现 compaction scene / episode 压缩 LLM / token budget 参数，只预留结构。 | 正确后移到 P4+。 |
| `schedule_compaction` 后台压缩 | OLD `persist_turn` 后调度 compaction；`schedule_compaction` 说明当前 turn 已在 transcript，避免重复计 user_text（`scene_preparer.py:245`-`255`，`conversation_memory.py:1318`-`1337`）。 | `phase3-plan.md:305`-`317` 仅增加 terminal 后 memory projection；不实现后台 compaction、active Run admission 或完整 lifecycle。 | 正确后移，P3 结构未封死后续接入。 |
| OLD scene preparation / Agent builder 强耦合 | OLD `DefaultScenePreparer` 初始化 `DefaultConversationMemoryManager` 并持有 compaction runtime adapter（`scene_preparer.py:444`-`469`）。 | `phase3-plan.md:42`-`43`、`287`-`289` 禁止机械搬回 OLD `ConversationRuntimeProtocol`、scene preparation、Agent builder 强耦合。 | 正确禁止迁回。 |
| NEW design 总体边界 | `docs/host/design.md:400`-`402` 要求 reasoning read model 与 RunInputBuilder 隔离；`docs/host/design.md:928`-`943` 固定 #48 强参考与 Host-owned RunInputBuilder。 | `phase3-plan.md` 将这些边界细化为文件级改动、测试清单、review gate 和停止条件。 | 与 design 一致。 |

## Open Questions

- P3 是否新增最小 Session 级 public `start_session_run(session_id, user_text, options)` 测试入口，还是只在 `LocalRunHarness` 内部装配 RunInputBuilder。该问题已在 `phase3-plan.md` 待确认项中列出，不阻塞 plan review。
- P3 是否新增 Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent，或从 `StartRunRequest.input.messages` 稳定投影 user message。当前 plan 要求二选一并禁止从 preview 拼接，方向成立。
- P3 的 `pinned_state` 是只支持显式 seed / patch，还是做最小规则化更新。按 #48，LLM compaction 产出 pinned patch 后移 P4；P3 默认 seed / patch 更稳。
- ToolRuntime facts 的 memory 摘要粒度是否保留 `cursor fingerprint` / `scope_hash` 一类中性 provenance 字段。只要继续禁止 cursor 原文、`scope_token` 和 `ToolFetchMoreHandle`，不影响本轮通过结论。

## Review Notes

- 本轮只审 plan，未修改 `docs/host/phase3-plan.md` 或生产代码。
- 已对照 GitHub issue #48、OLD `conversation_memory.py`、`conversation_store.py`、`conversation_session_archive.py`、`scene_preparer.py`、NEW `docs/host/design.md` 与 `docs/host/phase3-plan.md`。
- plan 的测试清单已经覆盖用户特别要求的“语义和实际实现逻辑的差异”：包括 preview / reasoning 过滤、final answer 来源、scope token 泄漏、#48 单总池与 `recent_turns_floor` 下限、以及 OLD compaction / archive / Engine 内 memory 禁止迁回。
- P3 后续 code review 的重点应从“文档是否写了”转为“实现路径和测试是否真的共用同一 RunInputBuilder / projection 逻辑”，尤其防止测试 helper 伪造一条比生产更干净的路径。
