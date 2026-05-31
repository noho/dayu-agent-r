# Phase 9 Conversation Memory / Session Memory Projection Handoff Plan

## 1. 动机判断

P9 的动机成立，但问题边界容易被高估或走偏。

真实问题不是“聊天太长，需要压缩历史”，而是买方财报分析会话需要一个可重建、可审计、可预算治理的工作台状态投影：下一轮 Run 必须稳定知道当前目标、主体、口径、工具已验证事实、仍待验证的假设与追问连续性。若继续只依赖 Phase 5 的 raw continuity messages，模型会把用户说法、assistant final answer、episode summary 和工具事实混在同一上下文层级，容易产生伪事实与跨轮归因漂移。

严重性判断：

- 高：verified facts 与 working assumptions 不分层会直接破坏财报分析 Agent 的反幻觉边界。
- 高：projection lag 若不可观测，会让同一 EventLog + policy 在不同进程 / 不同时间构造出不同 messages。
- 中：history pool 预算若不克制，会挤占当前问题、工具结果和财报材料预算。
- 低：长期记忆、跨多年 signal ledger 和 public edit / forget API 不是 P9 必要条件，提前实现会扩大 Host 业务语义和 schema blast radius。

因此 P9 应实施 session-level memory projection 与 RunInputBuilder provider 接线，不做长期 retrieval 或 LLM compaction 写 truth。

## 2. Scope

### Goals

- 实现 session-level Conversation Memory read model。
- Memory view 明确分为 `pinned_state`、`verified_facts`、`working_assumptions`、`conversation_continuity`。
- `verified_facts` 只接受工具事实，并保留 fact summary、producer / tool、`event_id` / `event_sequence`、tool result ref、digest / source ref、可选 evidence anchor 或 opaque subject refs。
- 实现 stable layer 与 history pool 的预算策略：
  - pinned / verified facts 不参与 history pool 竞争；
  - pinned / verified facts 有结构化尺寸上限、降级诊断；
  - recent raw turns floor 是下限；
  - older raw turns 与 episode summaries 共用单一 history pool；
  - 超预算先降级 episode summaries / older raw turns。
- 接入 `RunInputBuilder` 的 `MemorySnapshotProvider`，保持 typed provider boundary。
- projection lag 可观测：小 delta 从 EventLog 补齐并记录 diagnostic；缺失 / 损坏 / 超阈值进入 projection repair / context governance path；不得触发 Run recovery。
- 为 issue 39 预留 Host 中立 evidence anchor、claim status、provenance、trace included / excluded reason 边界。

### Non-goals

- 不实现长期 retrieval index。
- 不实现业务 signal ledger。
- 不实现 signal-to-outcome verification。
- 不实现 public memory edit / reset / forget API。
- 不实现 LLM proactive compaction；LLM 产物只能进入 candidate / assumption / continuity view。Phase 10 才负责 proactive compaction 编排。
- 不修改 Engine，不让 Engine 理解 Host memory。
- 不修改 EventLog canonical fact semantics。
- 不让 Host import `dayu.fins`。
- 不保存网页新闻、公告、研报摘录、财报 chunk 原文。
- 不把 company / business-line / technology release 等业务语义写入 Host memory schema。

## 3. Target Files

允许 implementation agent 新增或修改：

- `dayu/host/memory.py`：Conversation Memory typed contracts、projection consumer、policy、builder、repair service。
- `dayu/host/durable/memory.py`：memory projection-owned table 的 transaction-scoped read/write primitive。
- `dayu/host/durable/schema.py`：fresh schema 增加 memory projection tables，`HOST_SCHEMA_VERSION` 从当前版本递增；不写旧库兼容。
- `dayu/host/run_input.py`：扩展 `MemorySnapshotView` 与 durable `MemorySnapshotProvider` 接线；保持 provider protocol，不绕过读取 memory table。
- `dayu/host/projection.py`：只在确需通用扩展时修改；优先复用现有 `ProjectionConsumer` / `ProjectionRunner`。
- `dayu/host/dispatch.py` 或现有 scheduler composition root：只允许把 no-op memory provider 替换为 durable provider 的装配点，不改变 dispatch ownership。
- `dayu/host/README.md`：若 Host memory public/internal contract 已稳定，按 README 职责补充当前工作方式。
- `tests/host/test_memory_projection.py`：memory projection / rebuild / repair 单元与集成测试。
- `tests/host/test_run_input_builder_memory.py` 或扩展 `tests/host/test_run_input_builder.py`：RunInputBuilder memory 接入与反幻觉矩阵。
- `tests/host/test_durable_schema.py`：fresh schema table / index / version 测试。
- `tests/README.md`：仅当新增测试分层或运行方式有变化时更新。

禁止修改：

- `dayu/engine/**`。
- `dayu/fins/**`。
- `dayu/service/**`、`dayu/ui/**`。
- `dayu/runtime/**`，除非发现层中立 helper 缺失且先回到设计讨论。
- `EventLog` canonical event type / payload semantics。
- ToolRuntime accept barrier 的工具事实写入语义。
- Recovery state machine。
- Long-term retrieval、业务 evidence store、业务工具 provider。

## 4. Typed Contracts

Implementation agent 应先落 typed contract，再做 projection / provider 接线。所有 public 或 internal dataclass / enum / protocol 都必须完整中文 docstring，禁止 `Any` / `object` / untyped signature。

### 4.1 Memory Snapshot

建议在 `dayu/host/memory.py` 定义：

```text
ConversationMemorySnapshot
  snapshot_id: str
  session_id: str
  cursor: MemorySnapshotCursor
  policy_digest: MemoryPolicyDigest
  pinned_state: PinnedStateView
  verified_facts: tuple[VerifiedFactView, ...]
  working_assumptions: tuple[WorkingAssumptionView, ...]
  conversation_continuity: ConversationContinuityView
  diagnostics: tuple[MemoryDiagnostic, ...]
  built_at: str
  snapshot_digest: str
```

`snapshot_digest` 必须由 canonical JSON 计算，覆盖 cursor、policy digest、四类 view 和 diagnostics 中影响 messages 的字段。不得包含非确定性字段；`built_at` 若参与 digest 会破坏稳定性，默认不参与。

`PinnedStateView` 必须显式包含：

```text
PinnedStateView
  current_goal: str | None
  confirmed_subjects: tuple[OpaqueMemoryRef, ...]
  user_constraints: tuple[str, ...]
  open_questions: tuple[str, ...]
```

`open_questions` 只存放在 `PinnedStateView`，不得在 `WorkingAssumptionView` 或其它顶层字段中重复存储。Memory provider messages 中的 “open questions / working assumptions” 表示先渲染 pinned state 中的 open questions，再渲染 working assumptions。

### 4.2 Claim Status

Host 中立 `MemoryClaimStatus`：

- `TOOL_VERIFIED`：只允许 `TOOL_RESULT_ACCEPTED` canonical fact 产生。
- `ASSUMPTION`：用户说法、assistant 推断、LLM patch candidate。
- `CANDIDATE`：早期弱信号或待验证线索。
- `CONFLICTED`：同一中立 subject / source refs 存在冲突，但未由当前 Run 解决。
- `STALE`：因 policy 或事件 supersede 被标记为陈旧。
- `SUPERSEDED`：被后续 canonical fact 或 stronger claim 替代。

P9 不实现业务归因 verification；`TOOL_VERIFIED` 只表达“该 item 来自工具 accepted fact”，不表达财报业务结论正确性。

P9 projection 主动产生的 claim status 只有两类：

- `TOOL_VERIFIED`：由 `TOOL_RESULT_ACCEPTED` canonical fact 产生。
- `ASSUMPTION`：由用户输入、assistant conclusion / final answer、LLM patch candidate 进入 working assumption 或 continuity view 时产生。

`CANDIDATE`、`CONFLICTED`、`STALE`、`SUPERSEDED` 是为 issue 39 / 后续长期 memory 与 query-time retrieval 预留的 enum 值；P9 不主动合成 conflict / stale / supersede。只有当前 canonical fact 已显式携带 Host 中立 claim status 时，P9 才能按该中立状态投影，不得自行推断业务冲突、陈旧或替代关系。测试必须覆盖 P9 不合成 `CONFLICTED`、`STALE`、`SUPERSEDED`。

### 4.3 Provenance Refs

建议定义：

```text
MemoryProvenanceRef
  producer_kind: MemoryProducerKind
  producer_name: str
  event_id: str
  event_sequence: int
  run_id: str | None
  attempt_id: str | None
  execution_id: str | None
  tool_result_ref: HostEventRef | None
  payload_ref: HostPayloadRef | None
  digest_ref: MemoryDigestRef
  source_refs: tuple[OpaqueMemoryRef, ...]
```

`MemoryProducerKind` 至少包含 `TOOL`, `USER`, `ASSISTANT`, `HOST_PROJECTION`。`verified_facts` 只能使用 `TOOL`。

`OpaqueMemoryRef` 只允许中立字段：

```text
ref_kind: HostNeutralRefKind
ref_id: str
digest: str | None
```

`HostNeutralRefKind` 应是小集合 Host 中立 enum / `StrEnum`，例如 `SOURCE`、`CHUNK`、`ENTITY`、`SUBJECT`、`TOPIC`、`EVIDENCE`、`PAYLOAD`、`EXTERNAL`。不要实现脆弱的业务词 blocklist；测试应断言 schema / contract 不包含业务专有字段，且 Host 不解释 `ref_kind` 的财报业务语义。若业务工具提供 company / business-line / technology release 等信息，Host 只能保存业务方生成的 opaque ref id / digest。

### 4.4 Verified Fact View

```text
VerifiedFactView
  item_id: str
  fact_summary: str
  claim_status: MemoryClaimStatus.TOOL_VERIFIED
  provenance: MemoryProvenanceRef
  evidence_anchor: OpaqueMemoryRef | None
  subject_refs: tuple[OpaqueMemoryRef, ...]
  included_reason: MemoryIncludedReason | None
  excluded_reason: MemoryExcludedReason | None
  size_units: MemorySizeUnits
```

Fact summary 来源优先级：

1. `TOOL_RESULT_ACCEPTED` payload 中已有的 summary / display text / result summary 字段。
2. 可安全读取的 tool result payload descriptor 中的中立 summary 字段。
3. 中立 fallback：`tool_name + outcome_digest + payload_ref/digest` 组成的可审计摘要。

不得把原始财报 chunk、网页新闻、公告、研报摘录复制进 `fact_summary`。若没有业务摘要，使用中立 fallback 并记录 `MISSING_FACT_SUMMARY_FALLBACK` diagnostic，不得由 Host 生成业务结论。

实现 guidance：

- 先检查现有 `dayu.host.tool_runtime` 与 `dayu.host.run_input` 中的 `TOOL_RESULT_ACCEPTED` payload helper，不重新发明 payload shape。
- 映射 `event_id`、`event_sequence`、`tool_name`、`tool_call_id`、result id / accepted result ref、`payload_ref`、`payload_digest`、`outcome_digest`、`tool_identity_digest`、`normalized_arguments_digest` 等已存在字段。
- `tool_result_ref` 使用当前 `TOOL_RESULT_ACCEPTED` event ref；payload descriptor 只保存 ref / digest，不复制大 payload。
- 缺失 summary 时使用 `tool_name + outcome_digest + payload_ref/digest` 的中立 fallback，并写 item-level 或 snapshot diagnostic。

### 4.5 Conversation Continuity Item

`RUN_SUCCEEDED` / assistant final answer 只能产生 continuity item，不得进入 `verified_facts`。

```text
ConversationContinuityItem
  item_id: str
  item_kind: ConversationContinuityKind
  producer_kind: MemoryProducerKind.ASSISTANT | MemoryProducerKind.USER | MemoryProducerKind.HOST_PROJECTION
  claim_status: MemoryClaimStatus.ASSUMPTION
  event_id: str
  event_sequence: int
  run_id: str | None
  summary_text: str | None
  payload_ref: HostPayloadRef | None
  payload_digest: str | None
  included_reason: MemoryIncludedReason | None
  excluded_reason: MemoryExcludedReason | None
  size_units: MemorySizeUnits
```

`RUN_SUCCEEDED` 的 `final_answer` 投影为 `ConversationContinuityItem` / assistant conclusion，`producer_kind=ASSISTANT`，语义是 continuity / assumption，不是 verified claim。优先保存 `payload_ref` / `payload_digest`；只有小型 summary text 已在 canonical payload 中且预算允许时，才可存入 `summary_text`，并且该文本只服务连续性。

### 4.6 Snapshot Cursor

```text
MemorySnapshotCursor
  consumer_id: str
  checkpoint_event_sequence: int
  checkpoint_event_id: str | None
  session_id: str
```

Provider 消费前必须校验：

- `snapshot.session_id == current_facts.run.session_id`。
- `checkpoint_event_sequence >= required_event_sequence`，或 lag 在 policy 阈值内且可从 EventLog delta 补齐。
- `checkpoint_event_id` 与 durable EventLog row 匹配，除非 cursor 为 0。

`required_event_sequence` 必须用现有 durable Attempt 边界计算：

```text
required_event_sequence = current_facts.attempt.started_event_sequence - 1
```

它表示当前 Attempt 启动前 session memory 需要覆盖的最大 committed canonical fact sequence。当前 `USER_INPUT_ACCEPTED` 仍由 `CurrentRunFactProvider` 读取，不靠 memory snapshot 替代。

### 4.7 Policy Digest

```text
MemoryProjectionPolicy
  max_pinned_items: int
  max_verified_facts: int
  max_working_assumptions: int
  recent_raw_turns_floor: int
  max_raw_turn_size_units: int
  history_pool_size_units: int
  stable_layer_size_units: int
  max_lag_events_for_inline_delta: int
  max_delta_repair_events: int
```

`MemoryPolicyDigest` 必须由 policy canonical JSON 生成。RunInputBuilder messages 稳定性以“同一 EventLog + 同一 policy digest”为判定条件。

第一版 size units 可以是保守字符数或简化 token estimator，不能依赖 provider tokenizer；需要留 safety margin。

History pool 算法必须具体但克制：

- size units 使用 memory policy 中同一个保守 estimator helper；第一版可用字符数 / 简化 token estimator，但 stable layer、raw turn 和 episode summary 必须共用同一 helper，不能各自定义尺寸口径。
- `recent_raw_turns_floor` 是 count-based floor，并对单条 turn 设置 policy 定义的 per-turn safety cap；超过 cap 的单条 raw turn 先被截断 / 降级并记录 diagnostic，不能无限挤占预算。
- `older_raw_turns` 与 `episode_summaries` 共享 `history_pool_size_units`，不引入任意 40/60 或其它固定比例拆分。
- 降级顺序固定为：先降级 episode summaries，再降级 older raw turns；同类内部优先保留 newer / more useful context，并记录 item-level included / excluded reason。
- recent raw turns floor 最后降级；若极低预算下 floor 也无法完整容纳，必须保留可解释的最小连续性片段并记录 diagnostic。

Canonical digest 规则：

- policy digest 与 snapshot digest 均使用 canonical JSON：UTF-8、sorted keys、稳定 tuple/list 顺序、确定性 `null` 处理、无非确定性 whitespace。
- tuple/list 顺序必须来自 EventLog sequence 或 policy 明确排序，不得按 dict iteration 或物理读取偶然顺序。
- `built_at`、`updated_at`、projection 写入时间等非确定性字段不得进入 digest input。

### 4.8 Included / Excluded Reason

Host 中立 reasons 至少覆盖：

Included:

- `PINNED_STATE_REQUIRED`
- `VERIFIED_FACT_REQUIRED`
- `WORKING_ASSUMPTION_REQUIRED`
- `RECENT_RAW_TURN_FLOOR`
- `HISTORY_POOL_BUDGET_AVAILABLE`
- `INLINE_DELTA_REPAIR_INCLUDED`

Excluded:

- `OVER_STABLE_LAYER_LIMIT`
- `OVER_HISTORY_POOL_LIMIT`
- `OLDER_RAW_TURN_DEGRADED`
- `EPISODE_SUMMARY_DEGRADED`
- `MISSING_EVIDENCE_ANCHOR`
- `MISSING_FACT_SUMMARY_FALLBACK`
- `STALE_CLAIM`
- `CONFLICTED_CLAIM`
- `SNAPSHOT_LAG_OVER_THRESHOLD`
- `SNAPSHOT_MISSING`
- `SNAPSHOT_DAMAGED`

这些 reasons 应进入 `MemoryDiagnostic` 或 item-level metadata，供后续 Tool Trace / Trace projection 复用。P9 不创建独立 RunInputBuildTrace。

### 4.9 Lag Threshold 与 Repair Trigger

Lag 判断：

```text
lag_events = required_event_sequence - snapshot.cursor.checkpoint_event_sequence
```

规则：

- `lag_events <= 0`：直接使用 snapshot。
- `0 < lag_events <= max_lag_events_for_inline_delta`：从 EventLog canonical facts 补齐 stable layer，记录 `INLINE_DELTA_REPAIR_INCLUDED` diagnostic；实现上优先在 provider 内执行一次 projection catch-up / snapshot rewrite 后再返回。
- snapshot 缺失：触发 `SNAPSHOT_MISSING` repair trigger。
- snapshot digest 校验失败或 cursor 指向不存在 / 不匹配 event：触发 `SNAPSHOT_DAMAGED` repair trigger。
- `lag_events > max_lag_events_for_inline_delta`：触发 `SNAPSHOT_LAG_OVER_THRESHOLD` repair trigger。

Repair trigger 输出：

```text
MemoryRepairRequest
  session_id: str
  reason: MemoryRepairReason
  required_event_sequence: int
  observed_cursor: MemorySnapshotCursor | None
  policy_digest: MemoryPolicyDigest
```

Repair path 不得修改 Run / Attempt 状态，不得把 Run 推入 `RECOVERING`。若 dispatch path 因 repair required 无法构造 messages，应返回结构化 Host durable / context governance error，由 Phase 10 接入更完整治理。

## 5. Durable Schema 建议

在 `dayu/host/durable/schema.py` 增加 fresh tables，纳入 `PROJECTION_TABLES` 或新的 `MEMORY_PROJECTION_TABLES` 后合并进 `HOST_DURABLE_TABLES`：

- `host_memory_snapshots`
  - `snapshot_id` primary key
  - `session_id`
  - `consumer_id`
  - `checkpoint_event_sequence`
  - `checkpoint_event_id`
  - `policy_digest`
  - `snapshot_digest`
  - `snapshot_json`
  - `built_at`
  - `updated_at`
- `host_memory_items`
  - `item_id` primary key
  - `snapshot_id`
  - `session_id`
  - `item_kind`
  - `claim_status`
  - `event_id`
  - `event_sequence`
  - `producer_kind`
  - `producer_name`
  - `payload_ref`
  - `payload_digest`
  - `item_json`
  - `included_reason`
  - `excluded_reason`
- `host_memory_diagnostics`
  - `diagnostic_id` primary key
  - `session_id`
  - `snapshot_id`
  - `reason`
  - `event_sequence`
  - `policy_digest`
  - `diagnostic_json`
  - `recorded_at`

Snapshot 与 checkpoint 必须同事务提交。若实现选择只存 `snapshot_json`，仍需保留可索引的 session / cursor / policy 字段；若同时存 item table，`snapshot_json` 仍是 provider 读取的完整 canonical view，item table 用于测试、诊断和后续 trace/retrieval 复用。

`MemoryDiagnostic` 写入 `host_memory_diagnostics` 并可同时进入 snapshot diagnostics；projection consumer 抛出的异常、EventLog row 无法投影等 runner-level failure 写入既有 `host_projection_failures`。两者职责不得混用：diagnostic 描述 memory item / budget / lag 决策，projection failure 描述 consumer 处理失败。

Schema 变更按全新库处理：递增 `HOST_SCHEMA_VERSION`，更新 fresh bootstrap tests，不写旧 schema migration / compat read。

## 6. Projection / Rebuild / Repair Strategy

复用 Phase 8 基座：

- 新增 `ConversationMemoryProjectionConsumer` 实现 `ProjectionConsumer`。
- `consumer_id` 使用稳定值，例如 `host.memory.session.v1`。
- `event_filter` 只消费 `EventClass.CANONICAL_FACT`，事件类型至少包含：
  - `USER_INPUT_ACCEPTED`
  - `RUN_SUCCEEDED`
  - `TOOL_RESULT_ACCEPTED`
  - wait resolution 产生的 `TOOL_RESULT_ACCEPTED`
  - 后续存在的 steer / resume input canonical facts，若当前代码已有对应 event type。
- `apply_event(transaction, event)` 只写 memory-owned tables，不能 append EventLog，不能更新 Run / Attempt / wait / dispatch。
- `RUN_SUCCEEDED` 的处理只创建 `ConversationContinuityItem` / assistant conclusion；若存在 `payload_ref` / digest，优先保留 ref；若只能读取小型 `final_answer` / summary text，也必须标记为 continuity / `ASSUMPTION`，不得进入 `verified_facts`。
- 每个 EventLog row 的 memory write 与 `advance_projection_checkpoint` 必须在同一个 write transaction 内完成；不得 checkpoint 先于 snapshot content。
- projection failure 使用现有 `host_projection_failures`，不影响 EventLog append 或 Run terminal。

Rebuild：

- 提供 `rebuild_conversation_memory(transaction_runner, session_id, policy)` 或同等 service。
- Rebuild 从 EventLog cursor 0 按 sequence 重放目标 session canonical facts，写入新的 snapshot / items / diagnostics，并在最后同事务更新 checkpoint 到已覆盖最大 sequence。
- Rebuild 后 provenance 必须保持原始 `event_id` / `event_sequence` / payload refs / digests，不得用 rebuild event 替代来源。
- Rebuild 不写 EventLog，不创建 Run recovery fact。

Repair：

- 小 lag：provider 调用 projection catch-up 或 delta builder 补齐，记录 diagnostic，返回覆盖 required cursor 的 snapshot。
- 缺失 / 损坏 / 超阈值：返回 / 抛出结构化 `MemoryProjectionRepairRequired`，并尽可能写 memory diagnostic；只有 projection consumer / runner 处理异常才写 projection failure row。
- Repair path 的 owner 是 P9 memory projection；full context governance orchestration owner 是 Phase 10。

Automatic after-commit projection catch-up：

- `implementation-control.md` 已把 automatic after-commit projection catch-up owner 指向 Phase 9。P9 可以在 Host command / dispatch composition root 中注册 memory consumer 的 catch-up hook，但必须发生在 EventLog commit 之后，不能参与或影响 command transaction 成败。
- 不要在 plan 中假设一个当前不存在的具体 hook 名称；implementation agent 应优先复用现有 projection notification / catch-up extension point。若现有扩展点不足，只能新增最小通用 projection catch-up extension，不得写 memory 专用旁路。
- hook 必须 best-effort、projection-local failure 可观测，不得阻塞 EventLog append 或 Run terminal。

## 7. RunInputBuilder 接入策略

保持 typed provider boundary，不让 RunInputBuilder 读取 memory table 私有结构。

建议修改：

- 扩展 `MemorySnapshotView`，provider protocol 仍返回 `MemorySnapshotView`，不改成 tuple / dict / extra payload：
  - `messages: tuple[AgentMessage, ...]`
  - `memory_snapshot_cursor: str | None`
  - `policy_digest: str | None`
  - `diagnostics: tuple[MemoryDiagnostic, ...]`
- 新增 `DurableMemorySnapshotProvider`：
  - 输入 `AttemptDispatchSnapshot`、`CurrentRunFacts`、`MemoryProjectionPolicy`、`HostTransactionRunner`。
  - 读取 / 修复 snapshot。
  - 只返回 typed view，不暴露 table row。
- `create_no_tool_run_input_builder` 与 `create_tool_enabled_run_input_builder` 增加可选 `memory_snapshot_provider` 参数，默认仍可使用 no-op provider 以支持测试和未接线场景；生产 scheduler composition root 应传 durable provider。
- RunInputBuilder 全局 message ordering 必须继续遵循 `docs/host/design.md` §23：system / scene constraints、session memory stable layer、当前 `USER_INPUT_ACCEPTED` 与当前 Run canonical facts 按 `event_sequence` 投影、replay / retry / steer / resume guidance、tool schema snapshot 与 policy。P9 不重写 compact artifact、current user、guidance、tool schema 或 policy 的全局 provider 位置。
- P9 只定义 `MemorySnapshotProvider.messages` 内部顺序：
  1. 用户目标与约束。
  2. 已确认主体和口径。
  3. tool-verified facts。
  4. open questions / working assumptions。
  5. recent raw turns。
  6. episode summaries。
- 当前 `USER_INPUT_ACCEPTED` 仍由 `CurrentRunFactProvider` 读取并按 §23 进入当前 Run canonical facts；memory snapshot 不得替代当前用户输入事实入口。
- replay / retry / steer / resume guidance 与 tool schema / policy 继续保留在既有 provider 位置，P9 只补齐 memory provider 输出与诊断。

明确接线决策：

- P9 primary path 是把 historical raw turns 与 episode summaries 移入 `MemorySnapshotProvider` / history pool，由 memory policy 成为单一预算权威。
- `SessionContinuityProvider` 可以保留，但只允许承载非 raw history 的 continuity / resume-specific facts，例如当前 resume wait result message；或者对 raw history 返回 no-op。
- `SessionContinuityProvider` 不得再注入未经过 memory history pool 预算的历史 raw user / assistant turns。
- 全局 build order 仍遵循 §23；这里的决策只改变 raw history 的预算归属，不改变 current user、guidance、tool schema 或 policy provider 位置。

Messages 内容建议：

- 使用少量 `SystemMessage` 分块承载 stable layer，例如 `Memory pinned state:`、`Tool verified facts:`、`Open questions and assumptions:`。
- recent raw turns 继续用 `UserMessage` / `AssistantMessage`，但必须受 floor 与 history pool 控制。
- episode summaries 只能作为导航 `SystemMessage`，不得写成 evidence-backed claim。

## 8. Implementation Slices

### Slice 1. Durable Memory Contracts and Schema

输入：

- `docs/host/design.md` §24 / §26。
- 当前 `dayu/host/durable/schema.py`、`dayu/host/durable/projection.py`、`dayu/host/projection.py`。

输出：

- Memory typed contracts。
- Memory durable tables。
- Transaction-scoped read/write primitive。
- Fresh schema version bump and tests。

Allowed files/modules：

- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_memory_projection.py`

测试要求：

- schema 创建 memory tables / indexes。
- `HOST_SCHEMA_VERSION` fresh bootstrap 通过。
- typed contract 拒绝空 id、非法 cursor、非法 claim status、verified fact 非 TOOL provenance。
- `PinnedStateView` 包含 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions`，且 open questions 不在 working assumptions 中重复存储。
- `OpaqueMemoryRef.ref_kind` 只接受 Host-neutral enum 值；schema / contracts 不包含业务专有字段，Host 不解释 ref kind 的业务语义。
- `MemoryDiagnostic` 写入 memory diagnostics contract；projection exceptions 仍归 `host_projection_failures`。
- no `Any` / `object` signature；pyright 通过。

Stop condition：

- 可以在空 EventLog 上创建并读取空 snapshot。
- checkpoint / snapshot content 在同一 write transaction 内提交。
- 未接 RunInputBuilder，未做 projection catch-up。

### Slice 2. Projection Consumer and Stable Layer Builder

输入：

- Slice 1 contracts。
- Existing `ProjectionRunner` / `ProjectionConsumer`。
- ToolRuntime `TOOL_RESULT_ACCEPTED` payload shape。
- Existing RunInputBuilder continuity projection helper as参考，不复制不受预算的 raw history 行为。

输出：

- `ConversationMemoryProjectionConsumer`。
- Stable layer / history pool builder。
- Verified fact extraction with provenance refs。
- Working assumptions and continuity classification。
- Snapshot digest and policy digest。

Allowed files/modules：

- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `tests/host/test_memory_projection.py`

测试要求：

- `final_answer` 只进入 `conversation_continuity`，不进入 `verified_facts`。
- `RUN_SUCCEEDED` 产生 `ConversationContinuityItem`，`producer_kind=ASSISTANT`，claim status 为 `ASSUMPTION` / continuity semantics；优先保留 payload ref / digest，不复制大文本。
- `USER_INPUT_ACCEPTED` 可进入 pinned constraints / assumption / continuity，不进入 `verified_facts`。
- `TOOL_RESULT_ACCEPTED` 进入 `verified_facts`，保留 producer / tool、event refs、tool result ref、payload refs、digest refs。
- `TOOL_RESULT_ACCEPTED` 字段映射覆盖现有 payload 中的 `tool_name`、`tool_call_id`、result id / result ref、`payload_ref` / digest、`outcome_digest` 等可用字段；字段缺失时写中立 fallback diagnostic。
- 缺失 fact summary 时使用中立 fallback，并记录 diagnostic，不生成业务结论。
- P9 不主动产生 `CONFLICTED`、`STALE`、`SUPERSEDED`；除非 canonical fact 显式携带中立 status，否则 reserved statuses 不出现在 snapshot 中。
- episode summary 只能进入 continuity navigation，不能替代 evidence anchor。
- history pool 使用统一 size estimator；recent raw turns floor 是 count-based floor，older raw turns 与 episode summaries 共享预算，降级顺序为 episode summaries 后 older raw turns。
- snapshot rebuild 后 provenance 不丢。
- 固定 EventLog fixtures + 固定 policy 多次 rebuild / catch-up 产生相同 snapshot digest，且 digest 不受 `built_at` / `updated_at` 影响。

Stop condition：

- Projection runner 可以从 committed EventLog 构建 session snapshot。
- Projection failure 只写 projection-local failure row。
- 未接 RunInputBuilder provider。

### Slice 3. RunInputBuilder MemorySnapshotProvider and Lag Fallback

输入：

- Slice 2 snapshot contract。
- Existing `RunInputBuilder` provider protocols。
- Phase 9 lag policy。

输出：

- `DurableMemorySnapshotProvider`。
- RunInputBuilder memory provider injection points。
- projection lag diagnostic / inline delta repair。
- structured repair-required error for missing / damaged / over-threshold snapshot。

Allowed files/modules：

- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `tests/host/test_run_input_builder_memory.py` 或 `tests/host/test_run_input_builder.py`

测试要求：

- `MemorySnapshotProvider.messages` 内部顺序固定为：用户目标与约束、已确认主体和口径、tool-verified facts、open questions / working assumptions、recent raw turns、episode summaries；全局 RunInputBuilder 顺序仍遵循 `docs/host/design.md` §23。
- `MemorySnapshotView` 保持 provider protocol 返回值，字段包含 `messages`、`memory_snapshot_cursor`、`policy_digest`、`diagnostics`；factories 支持可选 `memory_snapshot_provider`，默认 `NoopMemorySnapshotProvider`。
- snapshot cursor 覆盖 required cursor 时直接使用。
- `required_event_sequence` 使用 `current_facts.attempt.started_event_sequence - 1`；当前 `USER_INPUT_ACCEPTED` 仍归 `CurrentRunFactProvider`。
- 小 lag 从 EventLog 补齐并记录 diagnostic。
- snapshot 缺失 / 损坏 / 超阈值触发 repair-required，不触发 Run recovery 状态迁移。
- 同一 EventLog + 同一 policy 生成稳定 messages。
- low budget 下 recent raw turns floor 仍保留追问连续性，older raw turns / episode summaries 先降级。
- `SessionContinuityProvider` 不再注入未预算 historical raw turns；raw turns 和 episode summaries 必须由 `MemorySnapshotProvider` / history pool 统一预算。

Stop condition：

- Existing no-op provider tests 仍可通过。
- Production builder factory 或 scheduler composition root 能注入 durable provider。
- Historical raw user / assistant turns 只来自 memory history pool 或 no-op，不再从 `SessionContinuityProvider` 绕过预算进入 messages。
- `SessionContinuityProvider` 若保留，只处理 resume-specific / non-history continuity facts。
- Memory lag 不改变 Run / Attempt 状态机。

### Slice 4. Projection Repair and After-commit Catch-up Wiring

输入：

- Slice 3 provider and repair-required contract。
- Phase 8 projection runner。
- Current command / scheduler composition root。

输出：

- Memory rebuild / repair service。
- Best-effort after-commit memory catch-up hook。
- Projection repair diagnostics。

Allowed files/modules：

- `dayu/host/memory.py`
- `dayu/host/projection.py` only if generic extension is unavoidable。
- `dayu/host/command.py` or scheduler/composition root only for catch-up hook injection。
- `tests/host/test_memory_projection.py`
- relevant integration tests under `tests/host/`。

测试要求：

- after-commit catch-up 发生在 EventLog commit 之后，best-effort failure 不影响 EventLog append / Run terminal。
- implementation 复用现有 projection notification / catch-up extension point；若必须新增，只能新增最小通用 extension，不使用 memory 专用旁路。
- rebuild writes snapshot and checkpoint atomically。
- rebuild does not append EventLog。
- projection lag does not put Run into `RECOVERING`。
- repair-required path is observable through memory diagnostic；projection exception remains observable through projection failure row。

Stop condition：

- P9 exit condition satisfied: RunInputBuilder can consume memory snapshot stably; projection lag does not change same EventLog + policy messages except documented repair-required path。

### Slice 5. Docs and Verification Closure

输入：

- Final implementation surface from Slices 1-4。

输出：

- README sync only where responsibilities require it。
- Test / pyright command record。
- Residual risks routed to owners。

Allowed files/modules：

- `dayu/host/README.md`
- `tests/README.md` only if test workflow changed。
- `docs/host/implementation-control.md` only after implementation / review gate, not during this plan unless controller instructs。

测试要求：

- Affected tests pass。
- `pyright dayu/host tests/host` passes。
- `git diff --check` passes。

Stop condition：

- README contains current behavior, not future design。
- Residual risks have owner: Phase 10, issue 39, or later public read enhancement。

## 9. Anti-hallucination Test Matrix

Required tests:

- `final_answer` 不进入 `verified_facts`；只能作为 assistant conclusion / raw continuity。
- `RUN_SUCCEEDED` final answer 进入 `ConversationContinuityItem`，`producer_kind=ASSISTANT`，语义为 continuity / `ASSUMPTION`，不是 verified fact；大内容优先以 payload ref / digest 表达。
- 用户输入不进入 `verified_facts`；只能成为 pinned constraints、working assumption 或 continuity。
- `TOOL_RESULT_ACCEPTED` 进入 `verified_facts`，并保留 event refs、tool result ref、payload ref、digest / source refs。
- P9 不合成 `CONFLICTED`、`STALE`、`SUPERSEDED` claim status。
- episode summary 不能替代 evidence anchor；缺失 anchor 时必须有 `MISSING_EVIDENCE_ANCHOR` 或等价 diagnostic。
- snapshot rebuild 后 provenance 不丢；原始 `event_id` / `event_sequence` 不被 rebuild identity 替换。
- projection lag 不改变 Run 状态，不触发 `RECOVERING`。
- 同一 EventLog + 同一 policy digest 生成稳定 snapshot digest 和 stable messages。
- recent raw turns floor 在低预算下保连续性；older raw turns 与 episode summaries 先被降级。
- `SessionContinuityProvider` 不注入未预算 historical raw turns；raw history 由 memory history pool 统一预算。
- preview / reasoning / display-only facts 不进入 memory。
- projection checkpoint 不是 memory truth；损坏 checkpoint 不允许伪造 snapshot coverage。
- Host memory schema / contracts 不出现业务专有字段；`OpaqueMemoryRef.ref_kind` 使用 Host-neutral enum，Host 不解释业务语义。
- `dayu.host.memory` import boundary 不依赖 `dayu.fins` / `dayu.service` / `dayu.ui` / `dayu.engine`，除 `run_input.py` 可使用 Engine message contracts 外，durable memory 层不得 import Engine。

## 10. Verification Commands

Implementation agent 每个 slice 后至少运行受影响测试；phase closure 运行：

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder_memory.py tests/host/test_durable_schema.py
pyright dayu/host tests/host
git diff --check
```

若实际测试文件名不同，使用 implementation 中新增 / 修改的等价 tests。若修改范围触及既有 RunInputBuilder 或 projection runner，追加：

```bash
source .venv/bin/activate
pytest tests/host/test_run_input_builder.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py
```

## 11. README 触发规则

- 修改 `dayu/host/**` 且新增 memory projection / provider contract：检查并按职责更新 `dayu/host/README.md`。
- 修改 tests 运行方式或新增测试维护约定：检查 `tests/README.md`。
- 不修改根目录 `README.md`，除非 public CLI / 用户使用方式发生变化。
- 不修改 `dayu/README.md`，除非分层关系、术语或装配边界发生变化。
- README 只写当前行为，不写后续长期 retrieval / issue 39 未来设计。

## 12. Residual Risks and Owners

- Tool result payload 未必总带业务 fact summary。P9 owner 使用中立 fallback + diagnostic；若业务工具需要更高质量 fact summary，应由 ToolRuntime / tool contract 后续 work unit 设计，不由 Host memory 生成业务结论。
- Trace / tool trace projection 尚未完整落地。P9 需保留 included / excluded reason typed boundary；实际 trace sink owner 为后续 Audit / Tool Trace phase。
- Context governance orchestration 尚未完整落地。P9 只提供 repair-required contract；full governance owner 为 Phase 10。
- Long-term retrieval、signal ledger、signal-to-outcome verification owner 为 issue 39 / 后续长期 memory phase。
- Public memory edit / reset / forget API 不在 P9；若用户可见产品需要该能力，必须先回写 `docs/host/design.md`。
- Provider-aware tokenizer 不在 P9；第一版使用保守 size estimator，精确预算 owner 为 Phase 10 或后续 provider budget work unit。

## 13. Blocking Open Questions

当前 `docs/host/design.md` §23 / §24 / §26 与 `implementation-control.md` Phase 9 条目足以生成 implementation-ready plan。无 blocking open question。

Implementation agent 若在代码中发现以下事实，应停下来回到 design / control 文档，而不是自行改架构：

- 现有 `TOOL_RESULT_ACCEPTED` 无法提供任何可审计 summary / ref / digest 组合。
- Scheduler / RunInputBuilder 无法在不改变 Run 状态机的情况下表达 repair-required。
- Memory provider 接入需要修改 Engine message contract。
- 需要 Host 理解财报业务 subject 类型才能完成 P9 schema。
