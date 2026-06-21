# WU-PROJ-01 Compact Material Truth And Bounded Memory Catch-up Plan

## 元数据

- Work unit：`WU-PROJ-01`
- 类型：issue-backed bug fix / hardening
- 当前 gate：plan only
- 日期：2026-06-11
- plan gate 观察到的分支：`wu-proj-01`
- artifact path：`docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- 设计真源：`docs/host/design.md`；`docs/engine/design.md`
- 总控真源：`docs/host/issues-implementation-control.md`
- Issue owner：GitHub Issue #86，`WU-PROJ-01: Compact material truth and bounded memory catch-up`，OPEN，最新读取时间为 2026-06-11，`updatedAt=2026-06-11T04:37:56Z`
- 当前 gate 约束：本 gate 只创建本 plan artifact；不得 implementation、review、fix、commit、push、PR、修改控制文档、修改 issue 或改变 git 状态。

## Goal

修复 pre-dispatch compact / Conversation Memory projection 的职责错位，并把 ordinary dispatch 前的 memory projection catch-up / rebuild 收敛为 bounded 行为。

完成后必须满足：

- pre-dispatch compact input 从 EventLog / payload descriptor / artifact truth 构造，不依赖 Conversation Memory projection checkpoint 作为前置真源。
- proactive compact 预算估算、segment selection、compact request 使用同一份 material view。
- 第二次及后续 compact 使用 rolling compact：`previous_compacted_view + post_compact_delta_material + current_input_anchor`，不重展上一轮 accepted compact 覆盖的旧 raw history。
- accepted `CONTEXT_COMPACTED` 提交后，Conversation Memory projection 再消费该 canonical fact 并物化 ordinary RunInput read model。
- ordinary dispatch 读取 memory snapshot 时，catch-up / rebuild 有单次总预算；超预算或失败有结构化 diagnostic，且不进入 Run recovery。

## Motivation

动机成立，严重性没有被高估。

第一性原理上，compact 是 Host governance 接受 EventLog durable truth 后生成新 canonical compact fact 的过程，不能把 projection read model 放在 compact input 的事实链前面。正确事实链是：

```text
EventLog / payload descriptor / artifact truth
  -> EventLog-backed compact material builder
  -> ConversationCompactInputVNext
  -> Host-owned compactor
  -> Host accept barrier
  -> CONTEXT_COMPACTED canonical fact
  -> Conversation Memory projection read model
  -> ordinary RunInput
```

当前缺口会导致两个风险：

- Context Governance 用不完整 material 做预算和 compact 裁决，实际 ordinary input 与 compact input 不是同源视图。
- memory projection catch-up / rebuild 在 dispatch hot path 上只有 batch size，没有单次总预算，大量 EventLog 或 projection failure 可能拖垮 dispatch path。

本 WU 不是 context window token 超限修复，也不是把 projection runner 平台化。根因是 compact material truth 位置错误和 memory catch-up 无界，而不是 Audit / Tool Trace / Outbox 或 Run recovery 问题。

## Success Signal

- proactive compact 的预算估算不再只估当前 user prompt，而是估同源 material view。
- pre-dispatch compact builder 可由 EventLog / payload / artifact truth 构造：
  - latest accepted `CONTEXT_COMPACTED` -> `previous_compacted_view`。
  - latest compact cursor 之后、当前 input 之前的 committed canonical facts -> `post_compact_delta_material`。
  - 当前 `USER_INPUT_ACCEPTED` -> `current_input_anchor`。
- compact material build 不读取、不要求、不等待 Conversation Memory snapshot checkpoint。
- rolling compact 测试证明第二次 compact 不包含上一轮 accepted compact 覆盖的旧 raw turn / old tool result。
- accepted compact 后 memory projection 消费 `CONTEXT_COMPACTED` 并推进 snapshot / checkpoint，ordinary RunInput 能读取物化出的 summary / facts / anchors / intents / reference continuity。
- memory projection catch-up / rebuild 同时有单批大小和单次总预算边界。
- dispatch 前 catch-up / rebuild 超预算或失败时写出结构化 diagnostic，并按 pre-dispatch / worker-start failure 收口；不写 `RUN_RECOVERING`，不触发 recovery Attempt。
- pyright 无新增或扩散错误；受影响测试通过。

## First-Principles Judgment And Direct Code Evidence

问题真实存在，且当前代码证据与 design / issue 的动机同源。

直接证据：

- `dayu/host/dispatch.py:968-982` 的 proactive budget estimate 只把当前输入 `display_text` 放入 `BudgetEstimateInput.message_fragments`，没有估算 memory / compact / continuity / accepted evidence / post-compact delta 的完整 material。
- `dayu/host/dispatch.py:1508-1534` 的 `_prepare_compact_before_dispatch` 用 `_proactive_material_blocks(...)` 构造 material，再以 `memory_snapshot=None` 调用 `build_compact_material_pack(...)`，因此 proactive compact 当前不会形成 previous compacted view。
- `dayu/host/dispatch.py:3636-3670` 的 `_proactive_material_blocks` 只返回 bounded accepted tool evidence 和 current input anchor；没有构造 latest accepted compacted view，也没有构造 post-compact trace / answer delta。
- `dayu/host/dispatch.py:3691-3721` 的 `_proactive_represented_evidence_refs` 同时读取 memory snapshot 和 latest compact event 来排除 evidence。这里读取 memory snapshot 是为了去重，但会让 proactive material 的完整性语义混入 projection read model；compact truth 应从 latest accepted compact event / artifact 本身取得。
- `dayu/host/compact_material.py:673-726` 的 `build_compact_material_pack` 只从 `memory_snapshot` / inline delta 推导 `previous_compacted_view`，当前 proactive 传 `None`，所以无法用 latest accepted compact event 建立 rolling compact。
- `dayu/host/run_input.py:1951-1989` 已有 `RunInputBuilder.build_material_blocks(...)`，但它依赖 AttemptDispatchSnapshot 和 memory snapshot provider；pre-start proactive compact 尚无 attempt，不应通过 ordinary memory read model 绕路。
- `dayu/host/run_input.py:2412-2482` 已定义 ordinary Run input 的 material block 形态，可作为 material block 类型和 section 语义的复用点，但 pre-dispatch builder 必须由 EventLog-backed source 直接生成这些 block。
- `dayu/host/durable/memory.py:88-182` 的 Conversation Memory projection consumer 只消费 committed canonical facts，包括 `CONTEXT_COMPACTED`，并只写 memory-owned snapshot / item / diagnostic tables；这个方向是正确的，不应反转为 compact input truth。
- `dayu/host/projection.py:415-422` 与 `dayu/host/projection.py:587-606` 说明每个 EventLog row 在单个 write transaction 内完成 consumer apply 与 checkpoint advance；因此本 WU 不应把 ProjectionRunner 重写为大型调度系统。
- `dayu/host/memory_repair.py:153-198` 支持 `batch_size` 和可选 `max_event_sequence`，但 `dayu/host/memory_repair.py:201-252` 的 `_run_memory_projection_until_idle` 会循环到 idle 或 failure；`batch_size` 只是单批扫描上限，不是单次总预算。
- `dayu/host/dispatch.py:2832-2859` dispatch 前 catch-up 失败后会直接 full rebuild，仍没有总预算。
- `dayu/host/dispatch.py:2699-2745` lag repair rebuild 后立即重建 RunInput，rebuild 本身无总预算；若仍需 repair，外层以 worker startup failure 收口，但 diagnostic 粒度不足以区分 catch-up budget exhausted / rebuild budget exhausted。
- `dayu/host/open_host.py:136-158` after-commit memory catch-up port 直接调用无界 `catch_up_conversation_memory_projection(...)`；admission / command path best-effort hook 不应同步无界追平。
- `dayu/host/engine_ingest.py:3575-3620` reactive compact 也通过 `build_compact_material_pack(..., memory_snapshot=None)` 构造请求。Reactive path 不是本 WU 主目标，但共享 builder 设计不能让 reactive 路径继续依赖错误的 previous-view 来源；本 WU 只做与 pre-dispatch builder 收敛直接相关的最小改动，不重写 reactive multi-pass。

## Design Alignment

Host design 对齐：

- `docs/host/design.md` 明确 RunInputBuilder 是构造 `AgentRunRequest.messages` 的 owner，Conversation Memory 是 EventLog read model，不是事实真源；Context Governance 是预算 / compact 编排 owner，不直接写 memory。
- `docs/host/design.md` 明确 proactive compact material view 必须由 EventLog-backed builder 生成：latest accepted `CONTEXT_COMPACTED` -> previous compacted view，latest compact cursor 后到当前 input 前的 committed canonical facts -> post-compact delta，当前 `USER_INPUT_ACCEPTED` -> current input anchor。
- `docs/host/design.md` 明确 ordinary RunInput 的 memory section 仍依赖 Conversation Memory snapshot，但 snapshot lag 只能触发 bounded catch-up / rebuild / inline repair；失败或超预算不得触发 Run recovery。
- `docs/host/design.md` 明确 deterministic recent-window fallback 不提交 `CONTEXT_COMPACTED`，不物化 memory snapshot。
- `docs/host/design.md` 明确 read transaction 需要 fresh durable truth 时必须短事务读取，不得把 projection lag 或 memory snapshot 当 governance truth。

Engine design 对齐：

- `docs/engine/design.md` 明确 Engine 不做 Host context budget、proactive compact、context compact / retry 或 provider-aware budget policy。
- Engine 只在 provider context overflow 时产出 `context_compaction_requested` 和 recoverable `run_failed(context_compaction_required)`；本 WU 的 proactive material truth 与 ordinary memory catch-up 均属于 Host，不改变 Engine contract。

Issue / control doc 对齐：

- GitHub Issue #86 与 `docs/host/issues-implementation-control.md` 均把 scope 定位为 compact material truth 与 bounded memory catch-up。
- 本 plan 不处理 context window token 超限本身，不改变 EventLog truth，不把 Conversation Memory projection 升级为 compact input truth，不纳入 Audit / Tool Trace / Outbox，不重写 ProjectionRunner。

## Affected Files / Modules

本 gate 创建：

- `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`

后续 implementation 计划允许修改：

- `dayu/host/compact_material.py`
- `dayu/host/compact_material_source.py`，默认不新增；只有当 implementation 证据显示 `compact_material.py` 会明显膨胀或出现 import boundary 风险时才新增 Host 内部模块
- `dayu/host/dispatch.py`
- `dayu/host/memory_repair.py`
- `dayu/host/open_host.py`
- `dayu/host/engine_ingest.py`，仅限调用共享 builder / source view 的最小适配，避免 pre-dispatch 与 reactive 继续分叉
- `tests/host/test_compact_material.py`
- `tests/host/test_dispatch_scheduler.py`，现有 dispatch compact / proactive governance 测试入口
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_memory_repair.py`；若 implementation 证据显示需要更聚焦文件，可新增 `tests/host/test_memory_projection_repair.py`
- `tests/host/test_memory_projection.py` / `tests/host/test_logging.py`，按实际 regression 覆盖范围扩展
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_import_boundary.py`，仅当新增模块需要固定 import boundary
- `dayu/host/README.md`，仅在代码落地后确有稳定开发者语义变化且符合该 README 的更新约束时修改
- `tests/README.md`，仅当新增稳定测试入口或测试分类说明属于该 README 职责时修改

后续 implementation 不应修改：

- `dayu.engine` public contract 或 Engine runtime 行为
- `dayu.service` / `dayu.ui` / `dayu.fins`
- durable schema / EventLog event type / HostEvent public shape
- `docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`，除非 implementation 发现必须新增 public contract / schema / 状态机裁决；若发现，应停止并回报总控
- GitHub issue、commit、push、PR

## Contract / Schema / State-Machine / Public Interface Changes

- Public Host API：无计划变更。
- Engine public contract：无计划变更。
- Durable schema：无计划变更。
- EventLog event type / HostEvent：无计划变更。
- Run / Attempt 状态机：无计划变更；memory catch-up 超预算或失败不得进入 `RECOVERING`。
- Internal contract：允许新增或扩展 Host 内部 typed dataclass / enum：
  - `PreDispatchCompactMaterialView`：承载同源 material blocks、latest compact boundary、current input anchor、budget fragments、diagnostic refs。
  - `CompactMaterialSourceBoundary`：记录 latest compact event sequence、post-compact delta range、current input event sequence。
  - `MemoryProjectionCatchupBudget`：内部 catch-up / rebuild 总预算，第一版只支持 `max_batches` 和 `max_scanned_events`。本 WU 不加入 `timeout_seconds`，避免引入 clock / async 测试面；若后续 production profiling 证明单 row apply 时间不可控，再另起设计。
  - `MemoryProjectionRepairStopReason`：内部结果字段，值至少包括 `idle`、`target_reached`、`failure`、`budget_exhausted`。

这些 internal contract 不进入 `dayu.host` 包根 public exports，不进入 durable schema，不作为 Service / config public contract。若 implementation 证明必须新增 `OpenHostOptions` 字段或 config schema 字段才能满足需求，应触发 stop condition。

## Implementation Decisions

1. Compact material truth owner 是新的 EventLog-backed compact material source builder，而不是 `dispatch.py` private helper，也不是 Conversation Memory projection。

   该 builder 只读取 committed EventLog rows、payload descriptor / artifact refs 和已有 compact artifact payload；输出 typed material view。它不估算预算、不裁决 compact、不写 EventLog、不写 memory snapshot、不推进 projection checkpoint。

2. Context Governance 只消费 material view。

   `dispatch.py` 的 proactive gate 先构造 material view，再用同一 view 构造 budget fragments、segment selection 和 `CompactionRequest`。不再在 Context Governance 内临时拼 `accepted tool evidence + current input`。

3. `previous_compacted_view` 从 latest accepted compact event / artifact truth 生成。

   不从 latest memory snapshot 生成，也不得伪造 memory snapshot 只为喂给 compact pack builder。memory snapshot 可继续服务 ordinary RunInput，但不能成为 compact input 前置条件。

4. `post_compact_delta_material` 只覆盖 latest compact event 之后、current input 之前的 committed canonical facts。

   首次 compact 没有 latest accepted compact 时，delta 起点是当前 session 内第一条 relevant committed canonical fact 的 event sequence；如果 current input 之前没有 relevant fact，则起点等于当前 `USER_INPUT_ACCEPTED` 的 event sequence，且 delta 为空。后续 compact 时 delta 起点必须大于 latest accepted compact event sequence，不再展开上一轮 compact 已覆盖的旧 raw history。

5. Current input anchor 只来自当前 `USER_INPUT_ACCEPTED`。

   它在 compact input 中可读但不可作为 compact candidate source 引用；继续沿用现有 current anchor label 不可引用约束。

6. Memory catch-up / rebuild budget 是 Host 内部执行预算，不是 projection truth。

   `batch_size` 继续表示单批 transaction 扫描上限；新增总预算表示一次 command / dispatch / rebuild 最多执行多少批、扫描多少事件。budget exhausted 是可解释退出，不是 projection failure，也不是 Run recovery trigger。

7. After-commit catch-up 只能 bounded best-effort。

   `ConversationMemoryProjectionCatchupPort` 构造或调用时接收 internal budget；`open_host.py` 的 `_MemoryProjectionCatchupPort.catch_up_projection()` 注入 after-commit best-effort budget。耗尽预算只记录 structured log / result，不阻塞 command path 追到 idle，也不保留 hot path 无界追平。

8. Dispatch 前 catch-up / rebuild 是 bounded required repair。

   dispatch 前需要覆盖 required cursor。若 bounded catch-up 达到 required cursor，则继续 build RunInput；若 catch-up failure，则在预算内尝试 rebuild；若 rebuild 也 failure / budget exhausted / 未覆盖 required cursor，产生结构化 diagnostic 并按现有 pre-dispatch worker-start failure path 收口，不创建 recovery Attempt。

## Implementation Slices

### Slice 1：EventLog-backed pre-dispatch compact material source

Allowed files:

- `dayu/host/compact_material.py`
- `dayu/host/compact_material_source.py`，默认不新增；只有当 builder 代码规模或 import boundary 证据充分时才拆出
- `dayu/host/run_input.py`，仅可复用 / 小幅提取 existing helper，不改变 RunInputBuilder public shape
- `tests/host/test_compact_material.py`
- `tests/host/test_import_boundary.py`，仅当新增模块需要边界测试

Exact changes:

- 新增 `PreDispatchCompactMaterialView`，字段至少包含：
  - `material_blocks: tuple[RunInputMaterialBlock, ...]`
  - `previous_compacted_view: tuple[CompactMaterialBlock, ...]`
  - `current_input_text: str`
  - `source_boundary: CompactMaterialSourceBoundary`
  - `represented_evidence_refs: tuple[str, ...]`
  - `budget_fragments: tuple[BudgetTextFragment, ...]`
- `PreDispatchCompactMaterialView` 不把 `RunRow.input_event_id` / `RunRow.input_event_sequence` 复制成第二事实真源；current input ref 与 input cursor 的权威来源仍是 `RunRow`。若 `source_boundary` 为 diagnostic 记录 current input event sequence，builder 必须校验它与 `RunRow` 一致。
- `CompactMaterialSourceBoundary` 至少记录 `latest_compacted_event_id: str | None`、`latest_compacted_event_sequence: int | None`、`post_compact_delta_start_sequence: int`、`post_compact_delta_end_sequence: int`、`current_input_event_sequence: int`。
- 新增 `build_pre_dispatch_compact_material_view(...)`，输入为 transaction、EventLogStore、RunRow、current display text、policy caps。输出只来自 EventLog / payload / artifact truth，默认放在 `compact_material.py`。
- 从 latest accepted `CONTEXT_COMPACTED` 读取 accepted candidate，映射为 `previous_compacted_view` blocks。可复用 `ConversationCompactOutputVNext` / payload parser 或新增最小 typed parser；不得通过 memory snapshot 读取。
- 从 delta 起点到 `run.input_event_sequence` 之前读取 committed canonical facts，生成 post-compact delta material。delta 起点规则：
  - 有 latest accepted compact 时，`post_compact_delta_start_sequence = latest_compacted_event_sequence + 1`。
  - 无 latest accepted compact 时，`post_compact_delta_start_sequence` 为当前 session 内第一条 relevant committed canonical fact 的 event sequence；如果 current input 前没有 relevant fact，则等于 `run.input_event_sequence`。
  - `USER_INPUT_ACCEPTED` -> trace user turn block。
  - `RUN_SUCCEEDED` -> answer material block，复用现有 assistant final answer text helper；缺失 final answer continuity 时跳过并记录 diagnostic block 或 reason code。
  - `TOOL_RESULT_ACCEPTED` -> accepted evidence material，复用 `build_accepted_tool_evidence_material_blocks` 但增加 `after_event_sequence` / boundary 能力，避免读取 latest compact 之前的旧 evidence。
  - `CONTEXT_COMPACTED` 之外的 compact failed / request / diagnostic events 不进入 LLM-facing material。
- 当前 `USER_INPUT_ACCEPTED` 单独作为 current input anchor；不得同时出现在 delta trace material 中。
- evidence 去重只依赖 latest accepted compact event / artifact 中的 accepted evidence mapping。不得读取 Conversation Memory snapshot 中的 `evidence_backed_facts` 或其它 projection material 作为去重来源；projection lag 下 memory snapshot 的额外 material 不反向成为 compact input truth。
- 修改 `build_compact_material_pack(...)` 接口，新增 keyword-only 参数 `previous_compacted_view: tuple[CompactMaterialBlock, ...] | None = None`：
  - 当 `previous_compacted_view is not None` 时，直接使用该 explicit previous view，包括空 tuple 的首次 compact 场景，并跳过 `_previous_blocks_from_snapshot(...)`。
  - 当 `previous_compacted_view is None` 时，保留现有 `memory_snapshot` / `inline_delta_repair_view` 路径，供 ordinary RunInput 既有调用继续使用。
  - proactive / pre-dispatch compact 必须传入 `material_view.previous_compacted_view`；禁止构造 fake `ConversationMemorySnapshotVNext` 伪装 previous view。
  - 单元测试必须同时覆盖 explicit previous view 路径和既有 snapshot 路径。
- 保留 `RunInputMaterialBlock` / `CompactMaterialSection` / `CompactMaterialBlockKind`，避免新增第二套 material model。

Call path / data flow:

```text
dispatch proactive gate
  -> build_pre_dispatch_compact_material_view(transaction, event_log_store, run, display_text)
  -> material_view.material_blocks
  -> estimate_context_budget(material_view.budget_fragments)
  -> select_compact_segment(material_view.material_blocks)
  -> build_compact_material_pack(
       ...,
       previous_compacted_view=material_view.previous_compacted_view,
       current_input_ref=run.input_event_id,
       current_input_text=material_view.current_input_text,
     )
```

Invariants:

- Builder 不 import Engine / Service / UI / Fins。
- Builder 不读取 Conversation Memory snapshot。
- Builder 不写 EventLog、memory、projection checkpoint。
- Builder 输出的 `post_compact_delta_start_sequence` 必须大于 latest compact sequence；不存在 latest compact 时按本 slice 定义的 session first relevant canonical fact 起算，并用测试固定。
- Builder 输出不得包含 current input 的重复 raw block。
- Builder 对 payload / artifact source refs 缺失或 digest 不可校验 fail closed，抛 typed HostDurableError 或 compact material build error；不得 fallback 到 memory snapshot。

Tests:

- 首次 compact：无 previous compact，delta 包含 current input 前 canonical user / assistant / evidence blocks，current input 只在 anchor。
- 首次 compact：测试固定 `post_compact_delta_start_sequence` 等于 session 内第一条 relevant committed canonical fact；若 current input 前没有 relevant fact，则等于 `run.input_event_sequence` 且 delta 为空。
- 第二次 compact：有 latest accepted compact，previous view 来自 accepted compact candidate，delta 只包含 latest compact 后的新 facts，不包含 old raw turn / old tool result。
- memory snapshot lag / missing 不影响 builder 输出。
- accepted evidence refs 从 latest compact accepted mapping 排除，不从 memory snapshot 排除；测试中即使 memory snapshot 含额外 evidence facts，也不得影响 `represented_evidence_refs`。
- payload / artifact 损坏时 fail closed，错误不请求 Run recovery。

### Slice 2：Proactive Context Governance 使用同源 material view

Allowed files:

- `dayu/host/dispatch.py`
- `dayu/host/context_budget.py`，仅当需要 helper 把 material view 转 BudgetEstimateInput；不改变 public policy shape
- `dayu/host/engine_ingest.py`，仅限复用 shared previous-view/source helper 的最小适配，避免 reactive path 继续明显分叉
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_compact_material.py`

Exact changes:

- 在 `_run_context_governance_for_session` 读取 input event 后，先构造 `PreDispatchCompactMaterialView`，再估算预算。
- 删除或废弃 `_proactive_material_blocks` 与 `_proactive_represented_evidence_refs` 的 governance 拼接职责；若保留，必须降级为 source builder 内部 helper，且不读取 memory snapshot。
- `estimate_context_budget(...)` 的 `message_fragments` 使用 material view 的 budget fragments；fragment refs 使用业务可读 source refs，避免裸 cursor 作为 LLM-facing 文本。
- material view 到 `BudgetTextFragment` 的映射规则：
  - previous compacted view 按 compact material section / stable block id 分段，`fragment_ref` 使用 `previous:<business-section>:<stable-block-id>` 形态，`text` 使用已校验的业务可读 previous compact 文本。
  - post-compact delta 按 `RunInputMaterialBlock` 分段，`fragment_ref` 使用 `delta:<section>:<block_id>`；不得把 event sequence、payload ref、digest 作为 LLM-facing 文本。
  - current input anchor 单独一个 fragment，`fragment_ref` 使用 `current-input:<prompt-local-anchor>` 或等价业务可读 ref，`text` 使用 bounded current input anchor 文本。
  - 相邻 blocks 不为预算估算做跨 section 合并；如需为估算性能合并，只能合并同 section、同 source kind 且保留可追溯 stable ref 的 blocks。
- `_prepare_compact_before_dispatch` 接收已经冻结的 material view 和 estimate；不再自行拼 material。
- `select_compact_segment(...)` 和 `build_compact_material_pack(...)` 使用同一 material view。
- `CompactionRequest.recent_raw_turn_refs`、`older_raw_turn_refs`、`evidence_backed_fact_refs` 从 material view / selection 派生，不能只写 current input。
- material source failure 统一 fail closed：append structured governance diagnostic / `CONTEXT_COMPACTION_FAILED` 后 fail unstarted Run；不得进入 deterministic recent-window fallback，因为此时没有可信 material view 可供 fallback。
- deterministic recent-window fallback 只允许用于 compactor reject / failure / repair budget exhausted 之后，且前提是本次已经成功构造可信 material view；fallback 只使用 material view 中 post-compact bounded material，不提交 compact artifact。
- reactive compact path 的最小适配边界：本 WU 只允许让 reactive path 复用 shared previous-view/source helper，使 `build_compact_material_pack(...)` 在存在 latest accepted compact 时能接收 explicit `previous_compacted_view`，并消除继续传 `memory_snapshot=None` 导致 previous view 永远为空的 obvious divergence。不得在本 WU 内实现 reactive multi-pass、冻结 overflow ordinary material list 的大规模重写或 evidence-block 分段；如果 reactive path 需要这些改造才能通过，应停止并转后续 owner。

State transitions / error handling:

- material builder 失败发生在 Run 未启动前：append `CONTEXT_COMPACTION_FAILED` 或等价 governance failure diagnostic 后 fail unstarted Run；不得创建 Attempt，不得进入 `RECOVERING`。
- compact accepted 后仍按当前路径 append `CONTEXT_COMPACTED`，随后 bounded memory catch-up，再 start governed Attempt。
- compact failed fallback 预算通过时允许 start Attempt，但不得写 `CONTEXT_COMPACTED` 或 memory snapshot。

Tests:

- proactive budget estimate 包含 previous compacted view / post-compact delta / current anchor，而不是只有 current prompt。
- soft threshold 触发 compact 时，`CompactionRequest.material_pack.previous_compacted_view` 非空且来自 latest accepted compact。
- 第二次 proactive compact 不把 first compact 前旧 user / tool raw history 放入 trace/evidence material。
- material source failure 不进入 `RECOVERING`，不创建 Attempt。
- fallback path 不提交 `CONTEXT_COMPACTED`，仍有 failure diagnostic。
- reactive minimal adaptation test：存在 latest accepted compact 时，reactive compact request 的 material pack previous view 非空且来自 accepted compact；若需要 multi-pass 才能覆盖，记录 stop condition 而非扩大本 WU。

### Slice 3：Bounded memory projection catch-up / rebuild

Allowed files:

- `dayu/host/memory_repair.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `tests/host/test_memory_projection_repair.py`，可新增
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_logging.py`

Exact changes:

- 新增 internal `MemoryProjectionCatchupBudget`，第一版字段固定为：
  - `max_batches: int`
  - `max_scanned_events: int`
  - `purpose: MemoryProjectionRepairPurpose`，如 `BEST_EFFORT_AFTER_COMMIT`、`REQUIRED_BEFORE_DISPATCH`、`REBUILD_BEFORE_DISPATCH`
  - 不包含 `timeout_seconds`；本 WU 不引入 clock 注入或 wall-clock stop condition。
- 扩展 `ConversationMemoryProjectionRepairResult`：
  - `stop_reason: MemoryProjectionRepairStopReason`
  - `budget_exhausted: bool`
  - `target_reached: bool`
  - `max_event_sequence: int | None`
  - `max_batches: int | None`
  - `max_scanned_events: int | None`
- 将 `_run_memory_projection_until_idle(...)` 改为 `_run_memory_projection_bounded(...)`，循环条件同时检查：
  - failure -> stop_reason `failure`
  - events_scanned < batch_size -> `idle` / `target_reached`
  - finished_cursor >= max_event_sequence -> `target_reached`
  - batches_used >= max_batches 或 events_scanned >= max_scanned_events -> `budget_exhausted`
- `catch_up_conversation_memory_projection(...)` 接收可选 internal budget；无 budget 的调用方需要显式选择默认 budget，不保留无界 hot path。若为 close flush 需要追到 idle，应在 close-only helper 中显式传 `MemoryProjectionCatchupBudget.for_close_flush(...)`，不能复用 command path 默认。
- `rebuild_conversation_memory_projection(...)` 接收 required cursor 和 budget；dispatch rebuild 只需重建到 required cursor，不需要同步追到 EventLog idle。
- `ConversationMemoryProjectionCatchupPort.__init__` 新增 keyword-only `budget: MemoryProjectionCatchupBudget | None = None`，port 内部保存该 budget，并在 `catch_up_projection()` 调用 `catch_up_conversation_memory_projection(...)` 时传入；`budget is None` 只能用于 explicitly reviewed close-only / test-only 调用，command / admission path 不得留下无界默认。
- `open_host.py` 的 `_MemoryProjectionCatchupPort` 构造 `ConversationMemoryProjectionCatchupPort` 或直接调用 catch-up 时必须传入 after-commit best-effort budget；预算耗尽只记录 verbose / warning diagnostic，不抛出阻断 command path，除非 durable primitive 本身初始化失败。
- `_catch_up_memory_projection_before_worker(...)` 使用 required-before-dispatch budget。若未 target reached，返回 / 抛出 typed diagnostic error。
- `_build_run_input_with_lag_repair(...)` 中 lag rebuild 使用 rebuild-before-dispatch budget，并在 rebuild 未覆盖 required cursor 时抛 `MemoryProjectionRepairRequired` 或新的 `MemoryProjectionRepairBudgetExhausted`；外层 `_accept_local_worker(...)` 按 memory projection repair failure 收口，不触发 recovery。

Error handling / invariants:

- budget exhausted 不是 projection failure；不得写 projection failure row。
- projection consumer exception 仍按 `ProjectionRunner` 记录 projection failure row，result stop_reason 为 `failure`。
- dispatch required cursor 覆盖成功才允许 worker.accept。
- 超预算 / failure diagnostic 至少包含 run_id、attempt_id、execution_id、required_event_sequence、started_cursor、finished_cursor、events_scanned、batches_used、stop_reason、budget。
- 不新增 `RUN_RECOVERING` / recovery Attempt。

Tests:

- catch-up 在 `max_batches=1` 且未追完时返回 `budget_exhausted=True`，checkpoint 只推进已处理 row。
- catch-up 到 `max_event_sequence` 时返回 `target_reached=True`，即使 EventLog 后面还有更多事件也停止。
- after-commit port 调用不会无界追到 idle；预算耗尽不阻断 command path。
- `ConversationMemoryProjectionCatchupPort` 构造 budget 注入生效；`open_host.py` after-commit port 使用 best-effort budget，而不是调用无 budget catch-up。
- dispatch 前 required cursor 已覆盖时继续构造 RunInput。
- dispatch 前 catch-up budget exhausted 时不调用 worker.accept，不进入 recovery，diagnostic 可断言。
- rebuild budget exhausted 后仍需 repair 时按 memory projection repair failure 收口，不伪造成 worker startup timeout 根因。

### Slice 4：Accepted compact -> Conversation Memory -> ordinary RunInput regression

Allowed files:

- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_dispatch_scheduler.py`，仅当 public lifecycle / dispatch fixture 更适合表达链路时使用

Exact changes:

- 增加 regression，证明 accepted `CONTEXT_COMPACTED` 提交后 memory projection consumer 物化五类 memory sections，并与 projection checkpoint 同事务推进。
- 增加 ordinary RunInput regression，证明 dispatch 读取 memory snapshot 时可看到 accepted compact 物化出的 summary / facts / answer anchors / forward intents / reference continuity。
- 增加 negative regression，证明 failed compact fallback 不物化 memory snapshot、不生成 compact artifact、不污染 ordinary memory sections。
- Fixture 来源与断言链路：
  - 优先扩展 `tests/host/test_memory_projection.py` 现有 accepted compact fixture；若该 fixture 只覆盖 projection consumer apply，则补充同一 fixture 的 checkpoint 断言。
  - ordinary RunInput 断言复用 `tests/host/test_run_input_builder.py` 的 compact payload / memory snapshot helper，把 accepted compact artifact 先投影进 Conversation Memory，再由 RunInputBuilder 读取 snapshot。
  - 链路必须按 `accepted CONTEXT_COMPACTED -> projection checkpoint advanced in same transaction -> memory snapshot sections materialized -> ordinary RunInput includes those business sections` 断言，不能只断言 compact payload parser。
  - failed compact fallback negative fixture 可以复用 public compact smoke 或 dispatch scheduler 中的 compact failure fixture，但断言对象必须是 memory snapshot / compact artifact 未物化。
- Slice 4 是 regression safety net。若测试暴露 Slice 1-3 引入的问题，应回到对应 slice 的 allowed production files 修复；若暴露 pre-existing unrelated 问题，应记录为 residual risk 并回报总控，不在 Slice 4 擅自扩大 production scope。

Tests:

- 可复用 `tests/host/test_memory_projection.py` 现有 `test_accepted_compact_materializes_vnext_memory_sections`，补充 checkpoint / ordinary RunInput 联动断言。
- 可复用 `tests/host/test_run_input_builder.py` 中 compact payload helpers，补充 accepted compact 后 memory + compact artifact 的组合顺序断言。

## Validation Commands

实现后必须运行：

```bash
source .venv/bin/activate
python -m pytest tests/host/test_compact_material.py
python -m pytest tests/host/test_memory_projection.py
python -m pytest tests/host/test_run_input_builder.py
python -m pytest tests/host/test_open_host_runtime.py
python -m pytest tests/host/test_logging.py
python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"
python -m pytest tests/host/test_public_compact_smoke.py
pyright
```

当前仓库中 proactive governance / compact dispatch 测试入口是 `tests/host/test_dispatch_scheduler.py`，public compact lifecycle smoke 是 `tests/host/test_public_compact_smoke.py`。Implementation agent 不得使用不存在的 `tests/host/test_dispatch_context_governance.py` 作为验证入口。

Expected assertions:

- rolling compact：第二次 compact 的 material 不包含第一轮 compact 前旧 raw history。
- proactive budget：估算 fragments 与 compact material view 同源，不只包含当前 input。
- compact builder：memory snapshot missing / lag 不阻断 pre-dispatch compact material build。
- accepted compact projection：`CONTEXT_COMPACTED` 被 memory consumer 物化并推进 checkpoint。
- bounded catch-up：未追完时 structured result 为 budget exhausted，不写 recovery。
- dispatch：required cursor 覆盖才启动 worker；budget exhausted / rebuild failure 不调用 worker.accept。
- pyright：无新增或扩散类型错误。

## Docs Decision / README Trigger Decision

本 plan gate 只写 plan artifact，不更新 README。

后续 implementation 触发 `dayu/host/` 修改，必须检查 `dayu/host/README.md`。该 README 的约束是只写当前已实现的 Host 开发接口、公共契约、架构、稳定边界和关键机制，不写未来计划或 work unit 流水账。因此：

- 若 implementation 落地 EventLog-backed compact material truth、rolling compact 或 bounded memory catch-up 后，这些成为当前稳定开发者机制，应更新 `dayu/host/README.md` 的 Context Governance / Conversation Memory / Projection repair 相关说明。
- 若只做内部测试补强、没有稳定开发者可见语义变化，则可不改 README，但 final report 必须说明已检查 README 约束与不更新理由。

后续 implementation 修改 `tests/host` 时必须检查 `tests/README.md`；只有新增稳定测试入口、测试分类或运行约定时才更新。

本 WU 不计划修改 `dayu/README.md`，因为不改变 `UI -> Service -> Host -> Engine` 分层关系或装配边界。

## Risks / Open Questions / Residual Risks

- Blocking open question：无。当前 design / control / issue #86 足以生成 code-generation-ready plan；无需新增 public contract、durable schema 或状态机裁决。
- Scope risk：reactive compact 路径也存在 `memory_snapshot=None` 的 previous view 缺口。本 WU 以 pre-dispatch proactive 为主；若共享 builder 适配 reactive 需要大规模 multi-pass 重写，应停止并将 reactive deep hardening 转为后续 owner。
- Testing risk：dispatch proactive compact 可能缺少现成 focused fixture，需要新增最小 Host durable fixture。该风险属于 implementation 测试工作，不阻塞 plan。
- Diagnostic risk：现有 worker-startup failure closeout 可能把 memory projection budget exhausted 包装成 timeout。Implementation 应补充明确 error_code / diagnostic payload；若需要新增 HostEvent 或 durable diagnostic event type，应停止并回报总控。
- Performance risk：EventLog-backed builder 不能从 session 起点无界扫描。Implementation 必须用 latest compact boundary、current input cursor、现有 caps 和 short read transaction 限定读取范围。
- Compatibility risk：本项目默认按新设计处理，不保留旧 compact material 路径兼容；测试应跟着新边界迁移，不在生产代码堆兼容 wrapper。

## Why This Avoids Over-Design

- 不新增 public API、durable schema、HostEvent 或 Engine contract。
- 不重写 ProjectionRunner；只给 memory projection repair 调用方加 Host-owned bounded execution policy。
- 不把 Audit / Tool Trace / Outbox 拉入同一 WU。
- 不建立通用 material platform；只新增 pre-dispatch compact 所需的 EventLog-backed source builder，并复用现有 `RunInputMaterialBlock` / `build_compact_material_pack` / `select_compact_segment`。
- 不把 Context Governance 做成 material parser；它只消费 builder 输出做预算和裁决。
- 不用 Conversation Memory snapshot 修补 compact input truth；accepted compact 后的 memory materialization 仍由 projection 自己完成。

## Stop Conditions For Implementation

Implementation 必须停止并回报总控，不得擅自扩大方案，如果出现任一情况：

- 需要新增或修改 Host public API、`OpenHostOptions` public fields、config schema、durable schema、EventLog event type、HostEvent public shape 或 Run / Attempt 状态机。
- EventLog / payload / artifact truth 缺少构造 previous compacted view 或 post-compact delta 的必要 durable atom，且无法用当前 accepted compact payload / artifact refs 校验。
- 要求 reactive compact multi-pass 大规模重写才能完成 proactive builder 收敛。
- 需要把 Conversation Memory projection checkpoint 作为 compact input 前置条件才能通过测试。
- 需要让 Audit / Tool Trace / Outbox 进入 command-path blocking sink 才能解释本 WU。

## Completion Report Format

Implementation / later gate 返回总控时使用：

```text
artifact path:
plan status:
implemented slices:
changed files:
validation:
README decision:
blocking open questions:
residual risks:
```

本 plan gate 当前状态：

- plan status：code-generation-ready after AgentCodex plan fix
- key slices：EventLog-backed material source；proactive governance 同源 material；bounded memory catch-up / rebuild；accepted compact projection regression
- blocking open questions：none
- validation not run：本 gate 只产出 plan artifact，未修改生产代码，未运行 pytest / pyright
