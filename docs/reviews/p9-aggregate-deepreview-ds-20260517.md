# P9 Aggregate Deep Review — AgentDS

- **Reviewer**: AgentDS
- **Date**: 2026-05-17
- **Branch**: `feat/host-p9-conversation-memory`
- **Base**: `f27ce8a`
- **HEAD**: `1b19b35`
- **Scope**: P9全量 plan + implementation + docs + 历史 slice 裁决
- **Design truth**: `docs/host/design.md` §23 / §24 / §26
- **Control truth**: `docs/host/implementation-control.md` Phase 9
- **Plan truth**: `docs/host/phase9-conversation-memory-plan.md`

## Verdict

**PASS — no blocking findings.**

P9 在全部四个 slice 经 MiMo + DS 双路 review、controller adjudication 后，anti-hallucination 边界、层级隔离、Lag 治理、digest 确定性与 schema fresh-only 均守住设计真源。以下 non-blocking findings 指向可观测性、命名一致性与 working_assumptions 数据填充缺口，不构成回滚或重构条件。

---

## 1. 设计真源对齐审查

### 1.1 "财报分析工作台状态投影" 语义

**判断：守住。**

Conversation Memory 四个关键问题（分析谁、什么期间、按什么口径、哪些已确认）在代码中有明确映射：

| 设计问题 | 代码落点 | 状态 |
|---|---|---|
| 现在分析谁 | `PinnedStateView.confirmed_subjects` + `current_goal` | 已填（USER_INPUT_ACCEPTED → pinned_state） |
| 分析什么期间 | `PinnedStateView.user_constraints` | 已填（同上） |
| 哪些事实已由工具确认 | `VerifiedFactView` (只来自 TOOL_RESULT_ACCEPTED) | 已填，类型级强制 |
| 哪些仍是假设 | `WorkingAssumptionView` + `ConversationContinuityItem` (ASSUMPTION) | 见 finding N1 |
| 下一步需要验证什么 | `PinnedStateView.open_questions` | 已填 |

代码未变成聊天记录压缩器：raw turns 进入 `conversation_continuity`（语义为 continuity/ASSUMPTION），工具事实进入 `verified_facts`（语义为 TOOL_VERIFIED），分层清晰。

### 1.2 四类视图边界

| 视图 | 类型强制 | 数据来源 | 边界状态 |
|---|---|---|---|
| `PinnedStateView` | current_goal / confirmed_subjects / user_constraints / open_questions | USER_INPUT_ACCEPTED | 守住 |
| `VerifiedFactView` | claim_status=TOOL_VERIFIED, producer_kind=TOOL (硬编码 + `__post_init__` 强制) | TOOL_RESULT_ACCEPTED | 守住 |
| `WorkingAssumptionView` | claim_status=ASSUMPTION, producer_kind≠TOOL (硬编码 + `__post_init__` 强制) | **无事件类型填充** | 见 finding N1 |
| `ConversationContinuityView` | claim_status=ASSUMPTION, producer_kind≠TOOL (硬编码 + `__post_init__` 强制) | USER_INPUT_ACCEPTED / RUN_SUCCEEDED / EPISODE_SUMMARY_ACCEPTED | 守住 |

**关键安全机制：**`VerifiedFactView.__post_init__` (memory.py:364-369) 在构造时强制拒绝非 TOOL_VERIFIED / 非 TOOL provenance，这是类型级防线，不是文档约定。

### 1.3 verified facts 的 provenance / refs / digest

**判断：守住。**

`_verified_fact_from_projection_event` (memory.py:1158-1225) 完整保留：
- `producer_kind=TOOL`, `producer_name=tool_name`
- `event_id`, `event_sequence`, `run_id`, `attempt_id`, `execution_id`
- `tool_result_ref` (tool call requested event ref)
- `payload_ref`, `digest_ref`
- `source_refs` (来自 payload 的 opaque refs)
- `evidence_anchor` (可选)

不把 final_answer 升格为 fact：`RUN_SUCCEEDED` → `ConversationContinuityItem` (ASSISTANT_CONCLUSION, ASSUMPTION)，`VerifiedFactView` 构造时硬编码 `TOOL_VERIFIED`，不存在绕过路径。

不把用户说法升格为 fact：`USER_INPUT_ACCEPTED` → `pinned_state` + `ConversationContinuityItem` (RAW_USER_TURN, ASSUMPTION)，不进 `verified_facts`。

### 1.4 RunInputBuilder 注入顺序

**判断：符合裁决。**

`RunInputBuilder.build()` (run_input.py:1208-1222) 全局顺序：
1. Scene system messages
2. Memory messages (stable layer → raw turns → episode summaries)
3. Compact artifact messages
4. Continuity (resume wait result) messages
5. Current user prompt (UserMessage)

Memory 内部顺序 (`_memory_messages`, run_input.py:1432-1465)：
1. Stable blocks (goals → subjects → verified_facts → questions/assumptions)
2. Raw turn messages
3. Episode summary block

这符合 design.md §23 顺序（system/scene → memory stable layer → current facts → guidance → tool schema）和 plan §7 的 memory 内部顺序。

**Budget 策略符合裁决：**
- `_limit_pinned_state`: 按 `max_pinned_items` 保留最后 N 条
- `_limit_verified_facts`: 按 `max_verified_facts` 保留最后 N 条
- `_limit_working_assumptions`: 按 `max_working_assumptions` 保留最后 N 条（当前无数据流入）
- `_limit_continuity_items`: 4-phase history pool 算法
  - Phase 1: recent_raw_turns_floor count-based floor
  - Phase 2: categorize remaining (primary + older_raw + episodes)
  - Phase 3: fill primary pool (older_raw + primary_pool_items, reverse sequence)
  - Phase 4: fill remaining with episodes (reverse sequence)
- Stable layer 在 run_input.py `_bounded_stable_memory_messages` 受 `stable_layer_size_units` 约束

Current prompt 单一来源：`USER_INPUT_ACCEPTED` 由 `CurrentRunFactProvider` 读取，memory provider 不替代。

Recent raw turns floor 是下限保底：`_limit_continuity_items` Phase 1 无条件保留 floor 数量的 raw turns。

### 1.5 projection lag / repair / catch-up

**判断：守住，不触发 Run recovery。**

Lag 检测 (`DurableMemorySnapshotProvider._load_memory_snapshot_tx`, run_input.py:654-711)：
- `required_event_sequence = attempt.started_event_sequence - 1` (run_input.py:1391-1402)
- `lag_events = required - cursor.checkpoint_event_sequence`
- lag_events < 0: `SNAPSHOT_AHEAD_OF_REQUIRED` → `MemoryProjectionRepairRequired`
- lag_events == 0: 直接使用
- 0 < lag_events <= max_lag_events_for_inline_delta: inline delta repair (不写 checkpoint)
- lag_events > threshold: `SNAPSHOT_LAG_OVER_THRESHOLD` → `MemoryProjectionRepairRequired`
- snapshot 缺失: `SNAPSHOT_MISSING` → `MemoryProjectionRepairRequired`
- snapshot 损坏: `SNAPSHOT_DAMAGED` → `MemoryProjectionRepairRequired`

`MemoryProjectionRepairRequired` 是结构化异常，不触发 Run 状态迁移，不把 Run 推入 `RECOVERING`。

After-commit catch-up (`ConversationMemoryProjectionCatchupPort`, memory_repair.py:55-100)：
- 复用 `ProjectionRunner` 从当前 checkpoint 追平
- best-effort: 失败仅 log，不影响 EventLog append / Run terminal
- 注入点: `resolve_wait` command 和 `DefaultHostToolFactAcceptPort` successful accept

不修改 EventLog / Run / Attempt / wait / dispatch truth。

### 1.6 Issue 39 预留

**判断：Host-neutral，无业务夹带。**

- `MemoryClaimStatus` 预留 `CANDIDATE` / `CONFLICTED` / `STALE` / `SUPERSEDED`，P9 不合成这些状态（`test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` 验证）
- `MemoryProducerKind.HOST_PROJECTION` 预留
- `HostNeutralRefKind` 含 `SOURCE` / `CHUNK` / `ENTITY` / `SUBJECT` / `TOPIC` / `EVIDENCE` / `PAYLOAD` / `EXTERNAL`，Host 不解释业务语义
- `OpaqueMemoryRef` 只保存 ref_id / digest / ref_kind
- 无长期 retrieval index、业务 signal ledger、public edit/reset/forget API

---

## 2. Blocking Findings

**无。**

---

## 3. Non-blocking Findings

### N1. `WorkingAssumptionView` 已定义但无数据填充路径

- **严重度**: 低
- **证据**: 
  - `WorkingAssumptionView` 定义于 memory.py:371-417，有完整类型、校验、序列化、限制函数
  - `project_conversation_memory_event` (memory.py:999-1025) 四个 event type 分支均不写 `working_assumptions`
  - run_input.py:1623 渲染 `snapshot.working_assumptions`，但它始终为空 tuple
  - design.md §24 说 "working_assumptions 承载用户说法、assistant 推断、早期弱信号和待验证候选"
  - plan §4.2 说 "ASSUMPTION: 用户说法、assistant 推断、LLM patch candidate"
- **分析**: 当前用户说法和 assistant 推断进入了 `conversation_continuity` (RAW_USER_TURN / ASSISTANT_CONCLUSION / ASSUMPTION)，没有进入 `working_assumptions`。`WorkingAssumptionView` 与 `ConversationContinuityItem` 在 claim_status 上同为 ASSUMPTION，区别在于前者是"结构化假设"（含 subject_refs），后者是"对话连续性"（含 summary_text / payload_ref）。P9 主动产生的 claim status 只有 TOOL_VERIFIED 和 ASSUMPTION 两类，而 ASSUMPTION 当前全部进入 continuity view。
- **影响**: working_assumptions 渲染路径 (run_input.py:1623-1635) 始终产出空消息块。不影响正确性，但 `max_working_assumptions` policy 字段和 `_limit_working_assumptions` 成为死代码。
- **建议**: Phase 10 (proactive compaction) 或 issue 39 (长期记忆) 是 working_assumptions 的自然填充时机。P9 可考虑在代码注释中标注"Phase 10 接入点"，或在 plan/design 中明确 working_assumptions 的数据注入计划。

### N2. `MemoryIncludedReason` / `MemoryExcludedReason` 命名与 plan 不一致

- **严重度**: 低
- **证据**: 
  - Plan §4.8 列出 `PINNED_STATE_REQUIRED` / `VERIFIED_FACT_REQUIRED` / `WORKING_ASSUMPTION_REQUIRED` / `RECENT_RAW_TURN_FLOOR` / `HISTORY_POOL_BUDGET_AVAILABLE` / `INLINE_DELTA_REPAIR_INCLUDED`
  - 代码使用 `PINNED_STATE` / `TOOL_VERIFIED_FACT` / `WORKING_ASSUMPTION` / `RECENT_RAW_TURN` / `EPISODE_SUMMARY` / `EMPTY_SNAPSHOT`
  - Plan §4.8 列出 ~11 个 excluded reasons，代码只有 4 个: `BUDGET_LIMIT` / `MISSING_PROVENANCE` / `UNSUPPORTED_EVENT_TYPE` / `POLICY_EXCLUDED`
  - Plan 中详细的 excluded reasons (如 `OVER_STABLE_LAYER_LIMIT`, `OLDER_RAW_TURN_DEGRADED`, `EPISODE_SUMMARY_DEGRADED`, `MISSING_EVIDENCE_ANCHOR`) 被移入 `MemoryDiagnosticReason` 而非 `MemoryExcludedReason`
- **分析**: 此 divergence 在 S1 adjudication 已标记为 deferred（"rename before downstream consumers stabilize"）。当前无下游 consumer，暂不阻塞。
- **建议**: 若 Phase 10 / tool trace 需要消费这些 reasons，应在消费前统一命名。

### N3. 被 budget 丢弃的 items 不保留 excluded_reason

- **严重度**: 低
- **证据**: `_limit_continuity_items` (memory.py:1442-1496) 中，超预算的 items 仅从 tuple 中移除，不设置 `excluded_reason`。只有一条 `BUDGET_LIMIT_REACHED` diagnostic 记录 first_dropped item。
- **影响**: 单个 budget diagnostic 足以解释"有 items 被丢弃"，但无法区分"哪个 item 因何具体原因被丢弃"（older raw turn vs episode summary vs primary pool item）。如果后续 tool trace 需要 per-item excluded reason，需要增强。
- **建议**: Phase 10 或 tool trace phase 评估是否需要 per-item excluded reason。

### N4. `current_goal` first-write-wins 语义未在 design 中显式定义

- **严重度**: 低
- **证据**: `_pinned_state_with_user_input` (memory.py:1358) 只在 `pinned_state.current_goal is None` 时设置。这意味着第一个 USER_INPUT_ACCEPTED 永久锁定 goal。
- **分析**: 对于买方财报分析场景，目标稳定是合理的（"分析 X 公司 2025 年报"不会中途变成"分析 Y 公司"）。但用户主动改变目标或 steer 时，此语义可能导致 goal 与实际工作不一致。
- **建议**: 后续 steer / 目标变更场景需要设计 goal 更新语义。当前 first-write-wins 可在 design.md §24 中显式记录。

### N5. 测试缺口 — preview / reasoning facts exclusion 无专项测试

- **严重度**: 低
- **证据**: plan §9 要求 "preview / reasoning / display-only facts 不进入 memory"。当前保护是结构性的：`ConversationMemoryProjectionConsumer.event_filter` 只接受 `EventClass.CANONICAL_FACT`，preview 事件不在 CANONICAL_FACT class 中。
- **分析**: 结构性保证有效，但 plan 要求显式测试覆盖。已在 S1-S4 adjudication 中讨论但未作为 blocking。
- **建议**: 新增 `test_preview_facts_not_projected_to_memory` 专项测试。

### N6. 测试缺口 — import boundary 无专项测试

- **严重度**: 低
- **证据**: plan §9 要求 "dayu.host.memory import boundary 不依赖 dayu.fins / dayu.service / dayu.ui / dayu.engine"。手动验证已确认 memory.py / durable/memory.py / memory_repair.py 均无这些 import。
- **分析**: 代码层已验证，但无自动化回归测试。若未来有人误加 import，不会被测试捕获。`tests/host/test_import_boundary.py` 或类似文件可覆盖。
- **建议**: 新增 import boundary lint test。

### N7. 无 `RAW_TOOL_RESULT` continuity kind

- **严重度**: 信息性
- **证据**: `ConversationContinuityKind` 包含 `RAW_USER_TURN` / `RAW_ASSISTANT_TURN` / `ASSISTANT_CONCLUSION` / `EPISODE_SUMMARY`，不含 `RAW_TOOL_RESULT`。
- **分析**: 工具结果通过 `VerifiedFactView` 进入 stable layer，不进入 continuity raw turns。这是有意设计——工具结果作为结构化事实比作为 raw turn 更有价值。但某些场景（如工具返回的是自然语言描述而非结构化数据）可能需要 raw tool result 参与连续性。plan 未明确要求 `RAW_TOOL_RESULT`。
- **建议**: 后续评估是否需要在 continuity 中保留工具 raw result 的连续性表述。

---

## 4. 层级边界审查

### 4.1 Import 依赖方向

| 模块 | 导入方向 |
|---|---|
| `dayu/host/memory.py` | dayu.contracts, dayu.host.durable.codec → OK |
| `dayu/host/durable/memory.py` | dayu.contracts, dayu.host.durable.*, dayu.host.memory, dayu.host.projection → OK |
| `dayu/host/memory_repair.py` | dayu.host.durable.errors, dayu.host.durable.memory, dayu.host.durable.transaction, dayu.host.memory, dayu.host.projection → OK |
| `dayu/host/run_input.py` | dayu.engine.* (message contracts, allowed by plan), dayu.host.* → OK |
| `dayu/host/projection.py` | dayu.contracts, dayu.host.durable.* → OK |

**无反向依赖。** Memory/durable memory/memory_repair 均不导入 dayu.engine / dayu.fins / dayu.service / dayu.ui。

### 4.2 Schema fresh-only

- `HOST_SCHEMA_VERSION = 6` (从 Phase 8 的 5 递增)
- `MEMORY_PROJECTION_TABLES` 为新增 table 集合（snapshots / items / diagnostics）
- 无旧库兼容读取、migration 或 compat table
- `test_fresh_db_creates_foundation_phase8_and_memory_tables` 验证 fresh bootstrap

### 4.3 架构层级

- Memory 是 EventLog read model，不是 governance truth → 符合 design.md §24
- Memory 不写 EventLog，不修改 Run / Attempt / wait / dispatch → 符合 plan §1
- RunInputBuilder 通过 typed provider protocol 消费 memory → 符合 plan §7
- Repair path 不触发 RECOVERING → 符合 plan §4.9

---

## 5. 类型纪律审查

### 5.1 memory.py (2799 行)

- 0 处 `Any`
- 0 处 `object`
- 0 处 `# type: ignore`
- 所有 public/internal dataclass 使用 `frozen=True, slots=True`
- 所有 enum 使用 `StrEnum`
- Protocol 定义清晰 (ProjectionConsumer, MemorySnapshotProvider)
- TypeAlias 用于语义化 type alias (MemoryPolicyDigest, MemoryDigestRef, HostEventRef, HostPayloadRef)

### 5.2 durable/memory.py (901 行)

- 0 处 `Any`
- 0 处 `object`
- 0 处 `# type: ignore`
- 1 处 `cast(...)` (line 13, `from typing import cast`)，用于 SQLite row 到 typed row 的转换

### 5.3 memory_repair.py (243 行)

- 全部 typed dataclass
- 0 处弱类型

### 5.4 run_input.py

- Memory 相关新增代码均为强类型
- No `Any` / `object` 用于 memory provider 边界

**结论：类型纪律符合项目 AGENTS 约束。**

---

## 6. 测试覆盖审查

### 6.1 反幻觉矩阵覆盖 (plan §9, 15 条)

| # | 要求 | 测试覆盖 | 文件:行号 |
|---|------|---------|----------|
| 1 | final_answer 不进 verified_facts | PASS | test_memory_projection.py:924 |
| 2 | RUN_SUCCEEDED → ContinuityItem, ASSISTANT, ASSUMPTION | PASS | test_memory_projection.py:924, 1213 |
| 3 | 用户输入不进 verified_facts | PASS | test_memory_projection.py:950 |
| 4 | TOOL_RESULT_ACCEPTED → verified_facts + refs | PASS | test_memory_projection.py:980 |
| 5 | P9 不合成 CONFLICTED/STALE/SUPERSEDED | PASS | test_memory_projection.py:883 |
| 6 | episode summary 不替代 evidence anchor | PASS | test_memory_projection.py:1124 |
| 7 | snapshot rebuild 后 provenance 不丢 | PASS | test_memory_projection.py:1335 |
| 8 | projection lag 不改变 Run 状态 | PASS | test_run_input_builder.py:630, 654, 727 |
| 9 | 同 EventLog + policy → 稳定 digest | PASS | test_memory_projection.py:817, 1335; test_run_input_builder.py:194, 800 |
| 10 | recent raw turns floor 保连续性 | PASS | test_memory_projection.py:1157, 1213, 1269 |
| 11 | SessionContinuityProvider 不注入未预算 raw turns | PASS | test_run_input_builder.py:222 |
| 12 | preview/display-only facts 不进 memory | GAP (结构性保证) | 见 N5 |
| 13 | projection checkpoint 不是 memory truth | PASS | test_memory_projection.py:650; test_run_input_builder.py:654, 762 |
| 14 | schema/contracts 无业务字段 | PASS | test_memory_projection.py:735, 755 |
| 15 | import boundary 不依赖 fins/service/ui/engine | GAP (手动验证) | 见 N6 |

13/15 有直接测试覆盖，2 个 GAP 均为低严重度。

### 6.2 测试数量汇总

| 文件 | 行数 | 测试函数 | Memory 相关 |
|---|---|---|---|
| test_memory_projection.py | 1645 | 26 | 26 |
| test_run_input_builder.py | 2336 | 23 | 13 |
| test_durable_schema.py | 713 | 12 | 3 |
| **合计** | **4694** | **61** | **42** |

### 6.3 测试质量观察

- Schema constraint rejection tests 覆盖 memory tables (test_durable_schema.py:562)
- Digest 确定性测试覆盖 non-deterministic field exclusion (test_memory_projection.py:817)
- Typed contract rejection tests 覆盖非法 id/cursor/claim_status/provenance (test_memory_projection.py:666)
- Host-neutral ref kind 拒绝业务字段 (test_memory_projection.py:735)
- History pool 降级顺序测试覆盖 floor > primary > episodes (test_memory_projection.py:1157, 1213, 1269)

---

## 7. 文档审查

### 7.1 dayu/host/README.md

- 新增 "Conversation Memory Contracts" 段落 (README.md:111-121)
- 描述四类视图、claim status、ref 中立性、digest 排除字段
- 说明 `TOOL_RESULT_ACCEPTED` 是唯一投影为 VerifiedFact 的 event type
- 说明 `RUN_SUCCEEDED` / `USER_INPUT_ACCEPTED` 不进 verified facts
- **符合 README 职责**（当前工作方式，不写未来设计）

### 7.2 tests/README.md

- 仅更新测试文件列表，新增 test_memory_projection.py 等
- **符合 README 职责**

### 7.3 docs/host/implementation-control.md

- Phase 9 slice 状态已更新为 accepted
- 包含 residual risks 与 owner 追踪
- **符合总控文档职责**

### 7.4 未更新文档

- 根目录 README.md：未更新（正确—public CLI 未变化）
- dayu/README.md：未更新（正确—分层关系未变化）
- dayu/engine/README.md：未更新（正确—Engine 未修改）

---

## 8. Residual Risks

| Risk | Severity | Owner | Notes |
|---|---|---|---|
| working_assumptions 无数据填充 | Low | Phase 10 / issue 39 | 基础设施完整，数据源待后续 phase |
| included/excluded reason 命名不一致 | Low | 后续 tool trace phase | 已在 S1 adjudication deferred |
| per-item excluded_reason 缺失 | Low | 后续 tool trace phase | 当前仅 aggregate budget diagnostic |
| current_goal first-write-wins 语义未文档化 | Low | P9 hardening | 建议 design.md 显式记录 |
| preview facts exclusion 无专项测试 | Low | 后续 hardening | 结构性保证有效 |
| import boundary 无自动回归 | Low | 后续 hardening | 建议 lint test |
| production composition root 未注入 concrete memory catch-up | Medium | 后续 Host / Service wiring | S4 adjudication 已记录 |
| after-commit catch-up 是 synchronous best-effort | Low | Phase 13 / Phase 15 | 性能和 batch 化归后续 phase |
| `resolve_wait` late rejection 冗余 catch-up | Low | Host hardening cleanup | S4 adjudication 已记录 |

---

## 9. Verification

审查过程中验证了以下内容：

- `git diff f27ce8a..HEAD --stat`: 48 files, +12566/-53
- 手动验证 import boundary: memory.py / durable/memory.py / memory_repair.py 均无 engine/fins/service/ui 导入
- 手动验证类型纪律: 0 处 Any/object/type-ignore 在 memory module
- 手动验证 schema fresh-only: HOST_SCHEMA_VERSION = 6, 无旧库兼容
- 手动验证 4 类视图边界: 类型级 post_init 强制
- 历史 slice 裁决追踪: S1-S4 均 PASS，blocking findings 已闭环
- 现有测试通过确认: 基于 S4 adjudication "pytest ... 0 failures"

---

## 10. Conclusion

P9 Conversation Memory 在架构上守住了"财报分析工作台状态投影"而不是聊天记录压缩器的定位。四个视图的类型级强制边界（`__post_init__` 硬编码 claim_status + producer_kind）是比文档约定更可靠的 anti-hallucination 防线。Lag 检测不触发 Run recovery，digest 计算排除非确定性字段，schema 按全新库起库。已知 non-blocking findings 均有明确 owner（Phase 10 / issue 39 / tool trace phase / hardening），不阻塞 P9 合并。
