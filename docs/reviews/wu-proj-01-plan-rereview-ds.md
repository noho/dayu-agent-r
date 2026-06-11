# WU-PROJ-01 Plan Re-Review — AgentDS

## 元数据

- **Review target**: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md` (post AgentCodex plan fix)
- **Work unit**: WU-PROJ-01
- **类型**: issue-backed bug fix / hardening
- **Review gate**: plan re-review (AgentDS lane)
- **日期**: 2026-06-11
- **设计真源**: `docs/host/design.md`; `docs/engine/design.md`
- **总控文档**: `docs/host/issues-implementation-control.md`
- **GitHub Issue**: #86
- **Plan fix report**: `docs/reviews/wu-proj-01-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-proj-01-plan-review-controller-adjudication.md`
- **Previous DS review**: `docs/reviews/wu-proj-01-plan-review-ds.md`
- **Re-review 产出**: `docs/reviews/wu-proj-01-plan-rereview-ds.md`

## Review Scope

本 re-review 对 AgentCodex plan fix 后的 WU-PROJ-01 plan 做严格 adversarial re-review，逐条验证 controller accepted findings 是否已正确修复，并判断修正后的 plan 是否 code-generation-ready。

**Reviewed**: 修正后的 plan 全量；plan fix report 中 12 条 accepted finding 的 fix status；相关代码文件中的函数签名、类型名、测试文件存在性。

**Verified code references** (逐项核对):

| 核对项 | 结果 |
|---|---|
| `tests/host/test_dispatch_context_governance.py` 不存在 | ✅ 确认不存在；修正后 plan 不再引用 |
| `tests/host/test_dispatch_scheduler.py` 存在且含 14 个 governance/compact/proactive 测试 | ✅ 确认 |
| `tests/host/test_public_compact_smoke.py` 存在 | ✅ 确认 |
| `tests/host/test_compact_material.py` 存在 | ✅ 确认 |
| `tests/host/test_memory_projection.py` 存在，含 `test_accepted_compact_materializes_vnext_memory_sections` | ✅ 确认 |
| `tests/host/test_run_input_builder.py` 存在 | ✅ 确认 |
| `tests/host/test_open_host_runtime.py` 存在 | ✅ 确认 |
| `tests/host/test_logging.py` 存在 | ✅ 确认 |
| `tests/host/test_memory_repair.py` 存在 | ✅ 确认 |
| `dayu/host/compact_material.py:673` `build_compact_material_pack` | ✅ 确认 |
| `dayu/host/compact_material.py:1410` `_previous_blocks_from_snapshot` | ✅ 确认 |
| `dayu/host/compact_material.py:1325` `_effective_snapshot` | ✅ 确认 |
| `dayu/host/memory_repair.py:33` `ConversationMemoryProjectionRepairResult` | ✅ 确认 |
| `dayu/host/memory_repair.py:58` `ConversationMemoryProjectionCatchupPort` | ✅ 确认 |
| `dayu/host/memory_repair.py:153` `catch_up_conversation_memory_projection` | ✅ 确认 |
| `dayu/host/memory_repair.py:201` `_run_memory_projection_until_idle` | ✅ 确认 |
| `dayu/host/memory_repair.py:106` `rebuild_conversation_memory_projection` | ✅ 确认 |
| `dayu/host/open_host.py:137` `_MemoryProjectionCatchupPort` | ✅ 确认 |
| `dayu/host/dispatch.py:968-982` budget estimate 只用 `display_text` | ✅ 确认 |
| `dayu/host/dispatch.py:1508-1534` `_prepare_compact_before_dispatch` | ✅ 确认 |
| `dayu/host/dispatch.py:3636` `_proactive_material_blocks` | ✅ 确认 |
| `dayu/host/dispatch.py:3691` `_proactive_represented_evidence_refs` | ✅ 确认 |
| `dayu/host/dispatch.py:2832` `_catch_up_memory_projection_before_worker` | ✅ 确认 |
| `dayu/host/dispatch.py:2699` `_build_run_input_with_lag_repair` | ✅ 确认 |
| `dayu/host/context_budget.py:63` `BudgetTextFragment` | ✅ 确认 |
| `dayu/host/run_input.py:58` `RunInputMaterialBlock` | ✅ 确认 |
| `dayu/host/run_input.py:66-67` `CompactMaterialBlockKind` / `CompactMaterialSection` | ✅ 确认 |

## Verdict

**pass** — 12 条 controller accepted findings 均已正确修复。0 条未修复、0 条部分修复。修正后的 plan 为 code-generation-ready。

1 条 low-severity new finding (NF1)：Validation Commands 缺少 `test_memory_repair.py`，不影响 code-generation-readiness，implementation agent 可自行补齐。

## Accepted Findings Fix Status

逐条验证 controller adjudication 中 12 条 accepted findings 的修复状态。

### F1 (DS) — Validation Commands 引用不存在的测试文件 ✅ fixed

- **Controller 要求**: 改为实际存在的 `test_dispatch_scheduler.py -k "governance or compact or proactive"`，并纳入 `test_public_compact_smoke.py`
- **Plan 修正**: Validation Commands 改为 7 个真实存在的测试入口，第 6 条使用 `tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`，第 7 条纳入 `tests/host/test_public_compact_smoke.py`。新增明确声明（line 403）："Implementation agent 不得使用不存在的 `tests/host/test_dispatch_context_governance.py` 作为验证入口。"
- **验证**: 所有 7 个测试文件均确认存在于文件系统；`test_dispatch_context_governance.py` 确认不存在；`test_dispatch_scheduler.py` 确认包含 14 个 governance/compact/proactive 相关测试函数。
- **状态**: fixed

### F2 (DS) — `build_compact_material_pack` 接口变更路径不明确 ✅ fixed

- **Controller 要求**: 明确写出签名变更方案，禁止 implementation agent 自行选择伪造 memory snapshot
- **Plan 修正**: Slice 1 exact changes（lines 222-226）明确新增 keyword-only `previous_compacted_view: tuple[CompactMaterialBlock, ...] | None = None`；`is not None` 时跳过 `_previous_blocks_from_snapshot(...)` 路径；`None` 时保留既有 snapshot 路径供 ordinary RunInput 继续使用；proactive/pre-dispatch compact 必须传入 `material_view.previous_compacted_view`；禁止构造 fake `ConversationMemorySnapshotVNext`（line 225）；单元测试必须同时覆盖两条路径（line 226）。
- **验证**: 接口变更方向明确、无歧义，implementation agent 无需自行裁决。`_previous_blocks_from_snapshot` 确认存在于 `compact_material.py:1410`，`_effective_snapshot` 确认存在于 `compact_material.py:1325`。
- **状态**: fixed

### F3 (DS) — `PreDispatchCompactMaterialView` 字段与 `RunRow` 信息冗余 ✅ fixed

- **Controller 要求**: 减少或解释冗余字段的真源优先级
- **Plan 修正**: Slice 1（line 209）声明 "`PreDispatchCompactMaterialView` 不把 `RunRow.input_event_id` / `RunRow.input_event_sequence` 复制成第二事实真源；current input ref 与 input cursor 的权威来源仍是 `RunRow`"。view 字段列表（lines 202-208）不再包含冗余的 `current_input_ref` / `input_cursor`，只保留 `current_input_text`（可能经 builder normalize/截断处理）和 `source_boundary`（diagnostic 用途，需校验与 `RunRow` 一致）。
- **验证**: 字段冗余已消除，真源优先级已明确。
- **状态**: fixed

### F4 (DS) — Slice 4 缺少 production regression 处置流程 ✅ fixed

- **Controller 要求**: 说明 Slice 4 发现 regression 的处置流程
- **Plan 修正**: Slice 4（line 380）明确："若测试暴露 Slice 1-3 引入的问题，应回到对应 slice 的 allowed production files 修复；若暴露 pre-existing unrelated 问题，应记录为 residual risk 并回报总控，不在 Slice 4 擅自扩大 production scope。"
- **验证**: 处置流程清晰，两条分支（Slice 1-3 regression vs pre-existing）均有明确动作。
- **状态**: fixed

### M1 (MiMo) — evidence 去重源混合 memory snapshot 与 compact event ✅ fixed

- **Controller 要求**: 明确 compact material builder 的 evidence 去重只依赖 latest accepted compact event/artifact mapping，不读取 Conversation Memory snapshot
- **Plan 修正**: Slice 1（line 221）明确："evidence 去重只依赖 latest accepted compact event / artifact 中的 accepted evidence mapping。不得读取 Conversation Memory snapshot 中的 `evidence_backed_facts` 或其它 projection material 作为去重来源；projection lag 下 memory snapshot 的额外 material 不反向成为 compact input truth。" 测试要求（line 260）："即使 memory snapshot 含额外 evidence facts，也不得影响 `represented_evidence_refs`。"
- **验证**: 去重策略已收敛为单一真源（compact event/artifact），不再混合 memory snapshot。
- **状态**: fixed

### M2 (MiMo) — Slice 3 budget 接口缺少 `ConversationMemoryProjectionCatchupPort` 改造路径 ✅ fixed

- **Controller 要求**: 明确 budget 注入路径：port 构造或调用接收 internal budget，after-commit port 使用 best-effort budget
- **Plan 修正**: Implementation Decisions 7（lines 181-182）和 Slice 3 exact changes（lines 338-340）明确：
  - `ConversationMemoryProjectionCatchupPort.__init__` 新增 keyword-only `budget: MemoryProjectionCatchupBudget | None = None`
  - port 内部保存该 budget，`catch_up_projection()` 调用时传入
  - `budget is None` 只能用于 explicitly reviewed close-only / test-only 调用
  - `open_host.py` 的 `_MemoryProjectionCatchupPort` 必须传入 after-commit best-effort budget
  - 预算耗尽只记录 diagnostic，不阻断 command path
- **验证**: budget 注入路径完整闭环，从 port 构造 → 内部保存 → catch_up 调用 → after-commit 注入 → 超预算处理，各环节均有明确指令。
- **状态**: fixed

### M3 (MiMo) — 新增 `compact_material_source.py` 必要性未定 ✅ fixed

- **Controller 要求**: 默认收敛为 `compact_material.py` 内扩展，只有证据充分时才新增模块
- **Plan 修正**: Affected Files（lines 115-117）和 Slice 1（lines 194-196）均改为："默认不新增；只有当 implementation 证据显示 `compact_material.py` 会明显膨胀或出现 import boundary 风险时才新增 Host 内部模块"
- **验证**: 默认方案已收敛，新增模块有明确触发条件。
- **状态**: fixed

### M4 (MiMo) — reactive compact path 适配范围不明确 ✅ fixed

- **Controller 要求**: 定义最小适配边界，避免 scope 扩张
- **Plan 修正**: Slice 2 exact changes（lines 289）明确定义最小适配边界：
  - 只复用 shared previous-view/source helper
  - 使 `build_compact_material_pack(...)` 在存在 latest accepted compact 时能接收 explicit `previous_compacted_view`
  - 消除继续传 `memory_snapshot=None` 导致 previous view 永远为空的 obvious divergence
  - 不得实现 reactive multi-pass、overflow ordinary material list 大规模重写或 evidence-block 分段
  - 若需要这些改造才能通过，应停止并转后续 owner
- **验证**: 最小适配边界清晰，stop condition 明确。
- **状态**: fixed

### M5 (MiMo) — `MemoryProjectionCatchupBudget.timeout_seconds` 判断标准不明确 ✅ fixed

- **Controller 要求**: 明确第一版不加入 `timeout_seconds`，只用 `max_batches` + `max_scanned_events`
- **Plan 修正**: Contract 章节（lines 149-150）和 Slice 3（line 323）均明确：
  - 第一版 budget 字段固定为 `max_batches: int`、`max_scanned_events: int`、`purpose: MemoryProjectionRepairPurpose`
  - "不包含 `timeout_seconds`；本 WU 不引入 clock 注入或 wall-clock stop condition。"
  - "若后续 production profiling 证明单 row apply 时间不可控，再另起设计。"
- **验证**: timeout_seconds 已从第一版明确排除，后续引入有明确触发条件。
- **状态**: fixed

### M6 (MiMo) — Slice 4 regression 测试缺少 fixture 来源说明 ✅ fixed

- **Controller 要求**: 说明扩展现有 fixture 还是新增 fixture，明确断言链路
- **Plan 修正**: Slice 4 exact changes（lines 376-379）明确：
  - 优先扩展 `tests/host/test_memory_projection.py` 现有 accepted compact fixture
  - ordinary RunInput 断言复用 `tests/host/test_run_input_builder.py` 的 compact payload / memory snapshot helper
  - 固定断言链路：`accepted CONTEXT_COMPACTED -> projection checkpoint advanced in same transaction -> memory snapshot sections materialized -> ordinary RunInput includes those business sections`
  - failed compact fallback negative fixture 复用 public compact smoke 或 dispatch scheduler 的 compact failure fixture
- **验证**: fixture 来源、断言链路、negative case fixture 来源均已明确。现有 `test_accepted_compact_materializes_vnext_memory_sections` 确认存在于 `test_memory_projection.py:291`。
- **状态**: fixed

### M7 (MiMo) — 首次 compact 无 latest compact 时 delta 起点 cursor 语义不明确 ✅ fixed

- **Controller 要求**: 定义无 latest compact 时的 delta 起点，并用测试固定
- **Plan 修正**: Implementation Decision 4（lines 169-170）和 Slice 1 exact changes（lines 214-216）明确：
  - 无 latest accepted compact 时，`post_compact_delta_start_sequence` 为当前 session 内第一条 relevant committed canonical fact 的 event sequence
  - 如果 current input 前没有 relevant fact，则起点等于 `run.input_event_sequence` 且 delta 为空
  - Slice 1 tests（line 257）：测试固定该起点语义
- **验证**: 首次 compact delta 起点语义完整，边界情况（无 relevant fact）已覆盖。
- **状态**: fixed

### Additional 1 (Controller) — Budget fragments 映射规则 ✅ fixed

- **Controller 要求**: 说明 material view 如何映射为 `BudgetTextFragment`
- **Plan 修正**: Slice 2 exact changes（lines 279-283）明确三类映射规则：
  - previous compacted view → `fragment_ref` 使用 `previous:<business-section>:<stable-block-id>`，`text` 使用已校验的业务可读 previous compact 文本
  - post-compact delta → `fragment_ref` 使用 `delta:<section>:<block_id>`；不得把 event sequence、payload ref、digest 作为 LLM-facing 文本
  - current input anchor → `fragment_ref` 使用 `current-input:<prompt-local-anchor>` 或等价业务可读 ref
  - 相邻 blocks 不为预算估算做跨 section 合并；如需合并，只能合并同 section、同 source kind 且保留可追溯 stable ref 的 blocks
- **验证**: 映射规则自足，fragment_ref 均为业务可读形态，不暴露内部治理标识。
- **状态**: fixed

### Additional 2 (Controller) — Material source failure 后是否 fallback ✅ fixed

- **Controller 要求**: 统一为 fail unstarted Run with structured diagnostic，不进入 deterministic recent-window fallback
- **Plan 修正**: Slice 2 exact changes（lines 287-288）明确：
  - "material source failure 统一 fail closed：append structured governance diagnostic / `CONTEXT_COMPACTION_FAILED` 后 fail unstarted Run；不得进入 deterministic recent-window fallback，因为此时没有可信 material view 可供 fallback。"
  - fallback 只允许用于 compactor reject / failure / repair budget exhausted 之后，且前提是本次已经成功构造可信 material view（line 288）
- **验证**: fail-closed 与 fallback 的边界统一、无歧义。
- **状态**: fixed

## New Findings

### NF1-新-低-Validation Commands 缺少 `test_memory_repair.py`

- **位置**: Plan §Validation Commands (lines 391-400)
- **问题类型**: 验证入口不完整
- **当前写法**: Validation Commands 列出 7 个测试文件，但不包含 `tests/host/test_memory_repair.py`。Slice 3 的 allowed test files 包含 `tests/host/test_memory_repair.py`（existing）和 `tests/host/test_memory_projection_repair.py`（可新增），但两个文件均未出现在 Validation Commands 中。
- **反例/失败场景**: implementation agent 完成 Slice 3 后运行 Validation Commands，可能遗漏 `memory_repair.py` 相关测试。若新 bounded catch-up/rebuild 测试放在 `test_memory_repair.py` 或 `test_memory_projection_repair.py`，不会被验证命令覆盖。
- **为什么有问题**: Slice 3 修改 `dayu/host/memory_repair.py`，对应的测试验证必须纳入 Validation Commands。当前遗漏可能导致 bounded catch-up/rebuild 的测试未被运行。
- **直接证据**: Plan Slice 3 allowed files 列出 `tests/host/test_memory_projection_repair.py`（可新增）和 `tests/host/test_memory_repair.py`；Validation Commands 未包含其中任一。
- **影响**: 低 — implementation agent 完成 Slice 3 后自然会运行对应测试；但 plan 的 Validation Commands 作为最终验证入口应保持完整。
- **建议改法和验证点**: 在 Validation Commands 中加入 `python -m pytest tests/host/test_memory_repair.py`（若新增 `test_memory_projection_repair.py`，则同时加入该文件）。
- **修复风险**: 低
- **严重程度**: 低

## Architecture Boundary Re-review

修正后的 plan 在所有关键架构边界上保持正确方向：

| Boundary | 状态 | 证据 |
|---|---|---|
| Host ↔ Engine | ✅ 不涉及 | 无 Engine contract 变更 |
| Context Governance ↔ Conversation Memory | ✅ 方向正确 | compact material truth EventLog-backed；memory 消费 compact event 做物化 |
| compact material builder ↔ memory snapshot | ✅ 完全解耦 | builder 不读取 memory snapshot（line 248 invariant） |
| Context Governance ↔ RunInputBuilder | ✅ 边界清晰 | pre-dispatch compact material（EventLog-backed）vs ordinary RunInput（memory-backed） |
| dayu.host ↔ dayu.runtime | ✅ 不穿透 | 无 runtime 层新依赖 |
| durable schema / EventLog / HostEvent | ✅ 不变更 | 无 schema 变更 |
| ProjectionRunner ownership | ✅ 正确 | 不重写 ProjectionRunner，只给调用方加 bounded budget |
| reactive path ↔ pre-dispatch path | ✅ 最小收敛 | reactive 只复用 shared previous-view helper |

## Overdesign / Underdesign Re-check

| 检查项 | 状态 | 说明 |
|---|---|---|
| 无新 public API | ✅ | 所有新增类型为 Host internal |
| 无新 durable schema | ✅ | 不修改 EventLog event type |
| 无新状态机状态 | ✅ | 不引入 RECOVERING |
| budget timeout_seconds 已排除 | ✅ | 第一版只用 max_batches + max_scanned_events |
| 复用现有类型 | ✅ | RunInputMaterialBlock / CompactMaterialSection / CompactMaterialBlockKind |
| compact_material_source.py 默认不新增 | ✅ | 有明确触发条件才新增 |
| reactive path 不重写 | ✅ | 最小 shared helper 适配，有 stop condition |
| 无 conversation memory snapshot 作为 compact input 前置条件 | ✅ | 明确禁止（line 166, line 225） |
| 无 fake memory snapshot | ✅ | 明确禁止（line 225） |

## Blocking Open Questions

无 blocking open questions。原 DS review 的 non-blocking clarification questions 已被 plan fix 覆盖：

1. BudgetTextFragment 映射规则 → 已在 Slice 2 补充（lines 279-283）
2. Material source failure 后是否 fallback → 已统一为 fail unstarted Run（lines 287-288）

## Residual Risks (re-confirmed)

| Risk | 分类 | 状态 |
|---|---|---|
| Reactive compact deep hardening | Scope risk | 仍保留；plan 已设 stop condition |
| EventLog-backed builder relevant canonical fact 枚举 | Implementation risk | Implementation agent 需严格跟随 Slice 1 material rules |
| Existing fixtures 可能不足以覆盖完整链路 | Testing risk | Implementation agent 可新增最小 fixture |
| Diagnostic closeout 可能包装 budget exhausted 为 timeout | Diagnostic risk | Plan 已设 stop condition |
| EventLog-backed builder 无界扫描 | Performance risk | Plan 已明确 bounded read 要求 |

## Conclusion

AgentCodex plan fix 已将 controller adjudication 中 12 条 accepted findings 全部正确修复。修正后的 plan：

- Validation Commands 全部引用真实存在的测试入口
- `build_compact_material_pack` 接口变更路径明确，禁止 fake memory snapshot
- evidence 去重只依赖 compact event/artifact truth，不再读取 Conversation Memory snapshot
- memory catch-up budget 注入路径完整闭环：port → open_host.py → after-commit best-effort
- compact material source 默认在 `compact_material.py` 扩展
- reactive path 最小适配边界明确，有 stop condition
- `timeout_seconds` 已从第一版排除
- Slice 4 fixture 来源与断言链路明确
- 首次 compact cursor 语义完整
- BudgetTextFragment 映射规则自足
- material source failure fail-closed 统一
- 字段冗余已消除，regression 处置流程已补充

1 条 low-severity new finding（NF1：Validation Commands 缺少 `test_memory_repair.py`）不影响 code-generation-readiness，implementation agent 可自行补齐。

**Plan is code-generation-ready.**

---

## Completion Report

- **artifact path**: `docs/reviews/wu-proj-01-plan-rereview-ds.md`
- **verdict**: pass
- **fixed findings status**: 12/12 controller accepted findings fixed；0 条未修复；0 条部分修复
- **new findings**: 1 条 low-severity（NF1：Validation Commands 缺少 `test_memory_repair.py`）
- **blocking open questions**: none
- **residual risks**: 5 条（均为已知风险，plan 已设 stop condition 或明确 owner）
