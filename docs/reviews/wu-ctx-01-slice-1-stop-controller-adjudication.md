# WU-CTX-01 Slice 1 Stop Condition Controller Adjudication

## Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- interrupted gate：`implementation / Slice 1`
- implementation handoff：
  `docs/reviews/wu-ctx-01-slice-1-implementation-codex.md`
- accepted plan commit：`06c143f2`
- Controller decision：`accepted blocker / reopen plan`
- blocking user question：None
- next gate：`plan amendment`

## Decision

AgentCodex 正确命中了 accepted plan §8.2 的 stop condition：

> candidate refactor 改变 memory/evidence/LLM-facing 内容，而不是只改变组装时点。

本 blocker 不是实现困难，也不是可以在 `run_input.py` 加局部过滤规避的测试问题。
accepted plan 对 compact boundary 后的 Conversation Memory 状态作了错误假设，因此
当前 plan 已过期，必须先回到 plan gate 修订 owner scope、状态决策与验证矩阵。

当前 partial implementation 未完成 focused tests、full pyright 或 coverage，不进入
code review，不得 commit。

## Direct root-cause evidence

### Design truth

`docs/host/design.md` 已明确：

- §24：`selected_recent_window_policy` 只从 `post_compact_delta_material` 选择，
  不从 accepted compacted view 覆盖范围重新展开 raw recent window；
- §24：`selected_recent_window` 是 post-compact delta 的 bounded recent view，
  不是第六类 Semantic Memory；
- §24：compact boundary 之后才允许 raw delta 进入 selected recent window；
- §24：protected recent floor 是 post-compact delta 的保底，不得跨 compact boundary
  replay 已被 accepted compact 覆盖的旧 raw history；
- §25：同一 Run/input snapshot 的 proactive trigger 最多启动一个 durable
  compaction operation，不得对同一 snapshot启动第二次 proactive compact。

### Production truth

- `dayu/host/memory.py::project_conversation_memory_event` 处理
  `CONTEXT_COMPACTED` 时更新 summary/facts/anchors/intents/reference continuity 与
  `latest_compaction_event_ref`，但没有从 `selected_recent_window` 移除 compact
  已覆盖 raw items。
- `dayu/host/run_input.py::_memory_messages` 无条件渲染 snapshot 中的
  `selected_recent_window`。
- `dayu/host/compact_payload.py::ContextCompactedSemanticPayload` 当前没有投影
  persisted `source_boundary_refs`，所以 memory projection 无 typed coverage
  evidence可消费。
- `dayu/host/compact_payload.py::source_boundary_refs` 已有 deterministic producer
  contract：第一项是 `request.current_input_ref`，后续去重 refs 来自本次 selected
  compact material、previous compacted view、evidence/fact provenance。当前 input
  anchor不是 compact-covered raw history。

因此 accepted compact 前后 exact candidate 仍然相同，是 owner contract 缺失的直接
结果；不能用 estimator、threshold fixture、RunInput 下游过滤或第二次 compact掩盖。

## Semantic owner adjudication

### Compact coverage truth

唯一 typed read boundary仍是 `dayu.host.compact_payload`：

- strict parser必须读取并验证 persisted `source_boundary_refs`；
- typed semantic view必须显式区分：
  - `current_input_ref`：source boundary第一个 ref；
  - `compacted_source_refs`：其余由本次 accepted compact覆盖的 canonical refs；
- consumer不得自行索引 raw payload list、按字符串前缀猜 ref角色，或从时间戳/sequence
  推断覆盖范围。

不新增 compatibility reader。仍按全新 schema/workspace处理。

### Selected recent window truth

唯一 owner是 `dayu.host.memory` 的 Conversation Memory projection：

- 处理 accepted `CONTEXT_COMPACTED` 时，移除 source refs与
  `compacted_source_refs` 相交的既有 selected recent items；
- 保留 current input item；
- 保留未被本次 selected compact material覆盖的 protected recent raw items；
- compact event之后新提交的 eligible items自然形成 post-compact delta；
- `recent_evidence_items`继续从更新后的 selected recent window同源派生；
- rebuild、incremental projection、inline delta repair与 persisted snapshot必须得到
  相同结果。

`run_input.py` 只消费修正后的 typed memory view并执行既有 raw-tail source/digest
dedupe；禁止新增另一套 compact-coverage filter。

该改变会修正实际 LLM-facing messages，但它不是 scope扩张出的新产品语义，而是使生产
实现符合现有 design truth。必须由 owner-level memory tests冻结。

## Post-compact / fallback action adjudication

accepted plan 把 pressure与 action错误地固定为一一对应。正确 contract是：

- `pressure_level`始终只由 predicted tokens与 soft/hard thresholds派生；
- `budget_decision`还必须消费 `ContextSizingStage`：
  - `ORDINARY`：normal=`ALLOW_DISPATCH`，soft=`COMPACT_SOFT_THRESHOLD`，
    hard=`BLOCK_HARD_THRESHOLD`；
  - `POST_COMPACT`：normal或soft均=`ALLOW_DISPATCH`；hard=
    `BLOCK_HARD_THRESHOLD`并显式 fail closed，不得让 Run静默停在 accepted；
  - `DISPATCH_FALLBACK`：normal或soft均=`ALLOW_DISPATCH`；hard=
    `BLOCK_HARD_THRESHOLD`并沿既有 fallback/failure policy fail closed。

理由：

- soft threshold 的动作语义是“先尝试 compact”，不是永久禁止 dispatch；
- 同一 input snapshot已经完成唯一 proactive operation后，不得启动第二次 operation；
- public pressure仍应如实报告 soft exceeded；
- hard threshold仍是不可 dispatch边界；
- post-compact hard不得普通返回 `None`留下无 terminal transition的 accepted Run。

不得新增第二次 proactive request、无界 compact loop或“soft 就假装 normal”的
projection。

## Required plan amendment

保持 3 slices与两项独立修改不变，但 Slice 1必须扩充：

- production owner scope至少新增：
  - `dayu/host/compact_payload.py`
  - `dayu/host/memory.py`
- test scope至少新增：
  - `tests/host/test_memory_projection.py`
  - `tests/host/test_memory_repair.py`（若 rebuild/repair owner路径受影响）
  - compact payload strict parser所在的既有 owner tests
- `ContextSizingResult` invariant与 tests改为 stage-aware action；
- post-compact/fallback soft允许 dispatch、hard显式 fail closed；
- exact candidate tests必须区分：
  - compact-covered older raw items被移除；
  - current input保留一次；
  - protected recent raw items若未被 selected compact material覆盖则保留；
  - compact后新 delta继续进入 selected recent；
  - memory-selected与ordinary protected raw tail按 source ref/content digest去重；
  - pre/post conservative size在确有 covered material时下降；
  - 没有可压缩 covered material时不得伪造下降。

设计真源还需补一句明确 stage-aware action，消除 §25 当前只描述 pressure比较、但未明确
post-compact/fallback soft action的歧义。

## Partial implementation disposition

- 当前 partial code保留在 worktree，供 plan amendment完成后继续修复；它不构成
  accepted implementation。
- AgentCodex在 plan amendment gate只能修改 design/plan/amendment artifact，不得继续
  修改 production/tests。
- plan amendment必须重新经过 AgentMiMo / AgentDS 双路 plan review。
- re-review pass后创建新的 protected local accepted-plan-amendment commit，再恢复
  Slice 1 implementation。

## Completion

- status：`complete`
- decision：`reopen-plan`
- motivation：成立；blocker证明当前 plan假设不成立，并未推翻 WU目标
- owner：compact payload typed boundary + Conversation Memory projection
- blocking questions：None
- next entry point：AgentCodex修订 design/plan并产出 plan amendment artifact
