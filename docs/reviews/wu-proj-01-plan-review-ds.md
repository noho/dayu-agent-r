# WU-PROJ-01 Plan Review — AgentDS

## 元数据

- **Review target**: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- **Work unit**: WU-PROJ-01
- **类型**: issue-backed bug fix / hardening
- **Review gate**: plan review (AgentDS lane)
- **日期**: 2026-06-11
- **设计真源**: `docs/host/design.md`; `docs/engine/design.md`
- **总控文档**: `docs/host/issues-implementation-control.md`
- **GitHub Issue**: #86
- **Review 产出**: `docs/reviews/wu-proj-01-plan-review-ds.md`

## Review Scope

本 review 对 WU-PROJ-01 plan 做严格 adversarial review，判断其是否 code-generation-ready。

**Reviewed plan sections**: Goal, Motivation, Success Signal, First-Principles Judgment, Design Alignment, Affected Files, Contract/Schema/State-Machine Changes, Implementation Decisions, Implementation Slices 1-4, Validation Commands, Risks, Stop Conditions.

**Reviewed code files** (逐行核对 plan 引用的代码位置):

| 文件 | 核对行号 | 核对结果 |
|---|---|---|
| `dayu/host/dispatch.py` | 968-982 | 确认：budget estimate 只用 `display_text`，不含 memory/compact/delta |
| `dayu/host/dispatch.py` | 1508-1534 | 确认：`_proactive_material_blocks` + `build_compact_material_pack(memory_snapshot=None)` |
| `dayu/host/dispatch.py` | 3636-3670 | 确认：`_proactive_material_blocks` 只返回 evidence + current input |
| `dayu/host/dispatch.py` | 3691-3721 | 确认：`_proactive_represented_evidence_refs` 读取 memory snapshot + compact event |
| `dayu/host/dispatch.py` | 2832-2859 | 确认：catch-up failure → rebuild 无总预算 |
| `dayu/host/dispatch.py` | 2699-2745 | 确认：lag repair rebuild 无总预算 |
| `dayu/host/compact_material.py` | 673-726 | 确认：`build_compact_material_pack` 从 `memory_snapshot` 推导 `previous_compacted_view` |
| `dayu/host/compact_material.py` | 1410-1487 | 确认：`_previous_blocks_from_snapshot` 读取 memory snapshot 构造 previous blocks |
| `dayu/host/run_input.py` | 1951-1989 | 确认：`build_material_blocks` 依赖 AttemptDispatchSnapshot + memory snapshot provider |
| `dayu/host/run_input.py` | 2412-2482 | 确认：ordinary RunInput 的 material block 形态可作为复用点 |
| `dayu/host/durable/memory.py` | 88-182 | 确认：projection consumer 消费 committed facts 包括 `CONTEXT_COMPACTED` |
| `dayu/host/memory_repair.py` | 33-55 | 确认：`ConversationMemoryProjectionRepairResult` 无 budget/stop_reason 字段 |
| `dayu/host/memory_repair.py` | 153-198 | 确认：`catch_up_conversation_memory_projection` 无总预算 |
| `dayu/host/memory_repair.py` | 201-259 | 确认：`_run_memory_projection_until_idle` 循环到 idle 或 failure，`batch_size` 只是单批上限 |
| `dayu/host/memory_repair.py` | 106-150 | 确认：`rebuild_conversation_memory_projection` 无总预算 |
| `dayu/host/projection.py` | 415-422, 587-606 | 确认：每 row 一个 write transaction，consumer apply + checkpoint advance 同事务 |
| `dayu/host/open_host.py` | 136-158 | 确认：after-commit catch-up 无界调用 `catch_up_conversation_memory_projection` |
| `dayu/host/engine_ingest.py` | 3575-3618 | 确认：reactive compact 也 `memory_snapshot=None` |
| `docs/host/design.md` | §23 RunInputBuilder, §24 Conversation Memory, §25 Context Governance | 确认：plan 与设计真源一致 |

**Reviewed design sections**:
- `docs/host/design.md` §23 RunInputBuilder (lines 2515-2750)
- `docs/host/design.md` §24 Conversation Memory (lines 2750-3099)
- `docs/host/design.md` §25 Context Governance (lines 3101-3286)
- `docs/engine/design.md` §15 Context Compaction (lines 485-504)

**Reviewed tests**:
- `tests/host/test_dispatch_scheduler.py` — 确认 proactive compact 测试在此文件，非 plan 所列 `test_dispatch_context_governance.py`
- `tests/host/test_public_compact_smoke.py` — 确认存在
- `tests/host/test_compact_material.py` — 确认存在
- `tests/host/test_memory_projection.py` — 确认存在
- `tests/host/test_run_input_builder.py` — 确认存在
- `tests/host/test_open_host_runtime.py` — 确认存在
- `tests/host/test_logging.py` — 确认存在

## Verdict

**needs-fix** — 2 medium findings 需在 plan 中修正后才能交给 implementation agent。无 blocking/严重 finding。所有 finding 均可通过 plan 文本修正解决，无需重新设计。

## Findings

### F1-未修复-中-Validation Commands 引用不存在的测试文件

- **位置**: Plan §Validation Commands, line 365
- **问题类型**: 不可直接实施
- **当前写法**: `python -m pytest tests/host/test_dispatch_context_governance.py`
- **反例/失败场景**: 该文件不存在。implementation agent 运行该命令会立即失败，无法确定应运行哪个测试文件。虽然 plan 在下方写了 fallback "若实际测试文件名不同，implementation agent 必须用 `rg` 定位"，但 validation commands 本身是错误的，会浪费 implementation agent 一轮排查。
- **为什么有问题**: 当前 proactive compact 相关测试在 `tests/host/test_dispatch_scheduler.py`（函数名 `test_pre_start_governance_*`、`test_proactive_compaction_*`、`test_compaction_*`），而非 plan 所列文件名。plan 的 validation 命令不可直接执行。
- **直接证据**:
  - `ls tests/host/test_dispatch_context_governance.py` → 文件不存在
  - `grep -n "def test_.*compact\|def test_.*proactive" tests/host/test_dispatch_scheduler.py` → 确认相关测试在该文件
  - 同时存在 `tests/host/test_public_compact_smoke.py` 也应纳入验证
- **影响**: 实施 Agent 浪费时间排查命令失败原因；若机械执行可能跳过关键测试
- **建议改法和验证点**: 将 Validation Commands 中的 `test_dispatch_context_governance.py` 替换为实际存在的测试文件：
  ```bash
  python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"
  ```
  或直接列出 `tests/host/test_dispatch_scheduler.py` 和 `tests/host/test_public_compact_smoke.py`。同时删除或修正 fallback 指令，避免 plan 自相矛盾。
- **修复风险**: 低 — 纯文本修正
- **严重程度**: 中

### F2-未修复-中-`build_compact_material_pack` 接口变更路径不明确

- **位置**: Plan §Slice 1 "Call path / data flow" (lines 223-230) 和 §Slice 2 "Exact changes" (lines 259-267)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 的 data flow 写 `build_compact_material_pack(..., previous source from material_view, current anchor)`（line 229），暗示 `build_compact_material_pack` 会接收来自新 material view 的 previous_compacted_view。但 Slice 1/2 的 exact changes 没有明确写出 `build_compact_material_pack` 的签名变更方案。
- **反例/失败场景**: 当前 `build_compact_material_pack` 签名（`compact_material.py:673-681`）通过 `memory_snapshot` 参数推导 `previous_compacted_view`（经由 `_effective_snapshot` → `_previous_blocks_from_snapshot`）。若 implementation agent 简单传入 `memory_snapshot=None`（当前 proactive 路径的做法），previous_compacted_view 为空，无法实现 rolling compact。若 implementation agent 自行决定接口变更方式，可能出现三种分歧方案：1) 新增 `previous_compacted_view` 参数；2) 构造假的 memory snapshot 只含 previous view 数据；3) 在调用前替换 `_previous_blocks_from_snapshot` 的输入源。三种方案的 review、测试、维护成本不同，且方案 2 会违反 plan 的核心目标"不依赖 memory snapshot"。
- **为什么有问题**: `build_compact_material_pack` 是 compact material 的构造入口，其接口变更直接影响 Slice 1 和 Slice 2 的可实施性。plan 必须明确该函数的变更方式，否则 implementation agent 需要自行裁决架构边界。
- **直接证据**:
  - `compact_material.py:673-681`: `build_compact_material_pack` 接受 `memory_snapshot: ConversationMemorySnapshotVNext | None`
  - `compact_material.py:700`: `snapshot = _effective_snapshot(memory_snapshot, inline_delta_repair_view)`
  - `compact_material.py:707`: `previous_blocks = _previous_blocks_from_snapshot(snapshot)`
  - Plan line 229: `build_compact_material_pack(..., previous source from material_view, current anchor)` — 暗示新参数但未明确
- **影响**: 实施 Agent 需要自行裁决 `build_compact_material_pack` 的接口变更；若选择不当，后续 review 可能推翻已实施代码
- **建议改法和验证点**: 在 plan Slice 1 exact changes 中明确写出 `build_compact_material_pack` 的变更方案。建议方案：新增 keyword-only `previous_compacted_view: tuple[CompactMaterialBlock, ...] = ()` 参数；当该参数非空时，跳过 `_previous_blocks_from_snapshot` 路径；否则回退到现有 snapshot 路径（供 ordinary RunInput builder 继续使用）。同时在 Slice 1 allowed files 中明确 `compact_material.py` 的修改范围包含此接口变更。验证点：`build_compact_material_pack` 的单元测试需同时覆盖新参数路径和旧 snapshot 路径。
- **修复风险**: 低 — 明确接口变更方向，不改变 plan 整体架构
- **严重程度**: 中

### F3-未修复-低-`PreDispatchCompactMaterialView` 字段与 RunRow 存在信息冗余

- **位置**: Plan §Slice 1 "Exact changes", `PreDispatchCompactMaterialView` 字段定义 (lines 200-210)
- **问题类型**: 过度设计
- **当前写法**: `PreDispatchCompactMaterialView` 同时包含 `current_input_ref: str`、`current_input_text: str` 和 `input_cursor: int`
- **反例/失败场景**: 这三个字段都可以从 builder 的输入参数 `RunRow` 直接读取（`run.input_event_id`、`display_text`、`run.input_event_sequence`）。material view 的消费者（Context Governance）已经在调用 builder 时持有 `run` 和 `display_text`。将这些字段同时放在 material view 和 RunRow 中，造成同一事实的两个真源，后续维护者可能困惑应以哪个为准。
- **为什么有问题**: plan 的 Implementation Decision 2 说 "Context Governance 只消费 material view"，暗示 material view 应该是自足的。但 material view 的消费者 `_run_context_governance_for_session` 本身就持有 `run` 和 `display_text`。`current_input_ref` 和 `input_cursor` 从 RunRow 读取是零成本、零歧义的，不需要在 material view 中复制。
- **直接证据**:
  - `dispatch.py:968`: `display_text = _display_text_from_input_event(transaction, input_event)` — governance 函数已经持有 display_text
  - `dispatch.py:1508-1519`: `_prepare_compact_before_dispatch` 接收 `run` 和 `display_text` 作为参数
  - Plan line 202-204: material view 的 `current_input_ref`、`current_input_text`、`input_cursor` 与 RunRow 字段重叠
- **影响**: 低 — 不导致功能错误，但增加维护歧义
- **建议改法和验证点**: 建议保留 `current_input_text`（因为 builder 可能对其做 normalize/截断处理，与原始 display_text 不同），但移除 `current_input_ref` 和 `input_cursor`（直接从 RunRow 读取）。或者为这三个字段添加明确注释说明它们与 RunRow 的关系以及哪个是优先真源。
- **修复风险**: 低
- **严重程度**: 低

### F4-未修复-低-Slice 4 缺少 production code 修改入口的说明

- **位置**: Plan §Slice 4 (lines 335-352)
- **问题类型**: 切片过粗
- **当前写法**: Slice 4 allowed files 只有测试文件。plan 描述为 "增加 regression 测试"。
- **反例/失败场景**: 如果 Slice 1-3 的实现正确，Slice 4 的回归测试应该直接通过。如果 Slice 1-3 的实现引入了预期外的 regression，Slice 4 会发现。但 Slice 4 没有 allowed production files — 如果 regression 测试发现需要修 production code，implementation agent 需要自行判断是否属于 Slice 1-3 的 scope 还是新问题。plan 应明确 Slice 4 发现的 regression 如何处理。
- **为什么有问题**: Slice 4 的定位不够清晰。它既是 regression safety net，又可能发现需要 production 修复的问题。当前 plan 没有定义 Slice 4 failure 的处置流程。
- **直接证据**: Plan lines 335-338: Slice 4 allowed files 只有测试文件
- **影响**: 低 — implementation agent 遇到 regression 时可能困惑应修哪个 slice 还是停止
- **建议改法和验证点**: 在 Slice 4 描述中增加一句：若回归测试发现 Slice 1-3 实现导致的 regression，应在对应 slice 的 allowed files 范围内修复；若发现 pre-existing 问题（与 Slice 1-3 无关），应记录为 residual risk 并回报总控。
- **修复风险**: 低
- **严重程度**: 低

### F5-未修复-低-Plan 中 `_MemoryProjectionCatchupPort` 命名与实际类型不一致

- **位置**: Plan §Slice 3, line 314
- **问题类型**: 不可直接实施
- **当前写法**: `_MemoryProjectionCatchupPort.catch_up_projection()`
- **反例/失败场景**: 实际类型名为 `ConversationMemoryProjectionCatchupPort`（`memory_repair.py:58`），而非 `_MemoryProjectionCatchupPort`。implementation agent 在代码库中搜索 `_MemoryProjectionCatchupPort` 会找不到。虽然这是明显的 typo-level 问题，但 plan 应使用实际类型名避免混淆。
- **为什么有问题**: plan 应准确引用已有代码中的类型名，减少 implementation agent 的查找成本。
- **直接证据**:
  - `memory_repair.py:58`: `class ConversationMemoryProjectionCatchupPort:`
  - `open_host.py:137`: `class _MemoryProjectionCatchupPort(ProjectionCatchupPort):` — 注意这里有一个不同的 `_MemoryProjectionCatchupPort` 在 `open_host.py`
  - 实际上 plan line 314 引用的是 `open_host.py` 中的 `_MemoryProjectionCatchupPort`，该名称存在但带下划线前缀。plan 的引用是正确的（`_MemoryProjectionCatchupPort` 在 `open_host.py:137`），但代码中同时存在两个相似名字的类型（`ConversationMemoryProjectionCatchupPort` 在 `memory_repair.py:58` 和 `_MemoryProjectionCatchupPort` 在 `open_host.py:137`）。plan line 314 引用的是后者，这是正确的。此 finding 降级为 informational。
- **影响**: 无 — plan 引用正确
- **建议改法和验证点**: 无需修改。此条为 informational note，不进入 fix。
- **修复风险**: N/A
- **严重程度**: N/A（informational，不进入 finding count）

## Architecture Boundary Review

逐 boundary 检查结果：

| Boundary | 状态 | 证据 |
|---|---|---|
| Host ↔ Engine | ✅ 不涉及 | Plan 明确不修改 Engine public contract、不改变 Engine 行为 |
| Context Governance ↔ Conversation Memory | ✅ 方向正确 | Plan 把 compact material truth 从 memory snapshot → EventLog；memory 仍消费 compact event 做物化 |
| Context Governance ↔ RunInputBuilder | ✅ 边界清晰 | Plan 区分 pre-dispatch compact material（EventLog-backed）和 ordinary RunInput（memory-backed） |
| dayu.host ↔ dayu.runtime | ✅ 不穿透 | Plan 不引入 runtime 层新依赖 |
| dayu.host ↔ dayu.service/ui/fins | ✅ 不穿透 | Plan 不修改上层 |
| durable schema / EventLog / HostEvent | ✅ 不变更 | Plan 明确无 schema 变更 |
| ProjectionRunner ownership | ✅ 正确 | Plan 不重写 ProjectionRunner，只给调用方加 bounded budget |

**结论**: Plan 在所有关键架构边界上保持正确方向，不引入跨层穿透或反向依赖。

## Best-Practice Review

| 检查项 | 状态 | 说明 |
|---|---|---|
| 测试先行 | ✅ | 每个 slice 有明确测试要求，包括 positive/negative/regression |
| 可独立验证的 slices | ✅ | 4 个 slices 均可独立跑 pytest 验证 |
| 错误处理 fail-closed | ✅ | 多处明确 fail closed 语义（material build failure、budget exhausted、fallback diagnostic） |
| 不静默失败 | ✅ | 要求 structured diagnostic、stop_reason、budget exhausted 标记 |
| 禁止兼容 wrapper | ✅ | Plan 明确"不保留旧 compact material 路径兼容" |
| 类型安全 | ✅ | 新增 typed dataclass/enum，禁止 Any/object |

## Overengineering Review

| 检查项 | 状态 | 说明 |
|---|---|---|
| 无新 public API | ✅ | 所有新增类型为 Host internal |
| 无新 durable schema | ✅ | 不修改 EventLog event type |
| 无新状态机状态 | ✅ | 不引入 RECOVERING / LOST |
| 无通用 material platform | ✅ | 只新增 pre-dispatch compact 所需的 builder |
| budget timeout_seconds 延迟裁决 | ✅ | Plan 写明"若需要 async/clock 注入则停止评估是否过度设计" |
| 复用现有类型 | ✅ | 复用 RunInputMaterialBlock / CompactMaterialSection / CompactMaterialBlockKind |

## Overcoupling Review

| 检查项 | 状态 | 说明 |
|---|---|---|
| Builder 不 import Engine/Service/UI/Fins | ✅ | Plan invariants 明确列出 |
| Builder 不读 memory snapshot | ✅ | Plan invariants 明确列出 |
| Builder 不写 EventLog/memory/checkpoint | ✅ | Plan invariants 明确列出 |
| Context Governance 只消费 material view | ✅ | Implementation Decision 2 |
| reactive path 不重写 | ✅ | Plan 只做最小共享 builder 适配 |

## Optimal-Solution Review

Plan 的方案选择合理：
- 不重写 ProjectionRunner（用现有基础设施 + bounded budget wrapper）
- 不建立通用 material platform（只加一个 builder）
- 不把 reactive path 拉入主 scope（最小共享适配）
- 复用现有 `RunInputMaterialBlock` / `CompactMaterialSection` / `CompactMaterialBlockKind`

没有发现更简单、更安全、更可维护的替代方案。plan 的 scope discipline 值得肯定。

## Findings Summary

| 编号 | 严重程度 | 问题类型 | 简述 |
|---|---|---|---|
| F1 | 中 | 不可直接实施 | Validation Commands 引用不存在的测试文件 `test_dispatch_context_governance.py` |
| F2 | 中 | 契约缺失 | `build_compact_material_pack` 接口变更路径不明确 |
| F3 | 低 | 过度设计 | `PreDispatchCompactMaterialView` 与 `RunRow` 存在字段冗余 |
| F4 | 低 | 切片过粗 | Slice 4 缺少 production regression 处置流程说明 |
| (F5) | N/A | informational | 类型名引用已验证为正确，不进入 finding |

## Open Questions

无 blocking open questions。Plan 自身声明无 blocking open question，review 未发现新的 blocking question。

以下为 non-blocking clarification questions（不阻塞 plan 进入 implementation）：

1. `PreDispatchCompactMaterialView.budget_fragments` 的构造逻辑：plan 说 "budget fragments 使用 material view"，但 `BudgetTextFragment` 当前只有 `fragment_ref` 和 `text` 两个字段。material view 中的 previous_compacted_view / post-compact delta / current anchor 如何映射为 `BudgetTextFragment` 列表？建议在 Slice 2 exact changes 中补充映射规则（至少说明是否按 material section 分段、是否合并相邻同 section blocks）。
2. 当 EventLog 中 latest accepted `CONTEXT_COMPACTED` 存在但对应的 compact artifact 文件缺失/digest 不匹配时，plan 说 "fail closed"。fail closed 后是 fallback 到 deterministic recent-window 还是直接 fail unstarted Run？当前 plan 两处说法略有差异（Slice 1 tests 说 "错误不请求 Run recovery"，Slice 2 state transitions 说 "fail unstarted Run"）。建议统一为：material source failure → fail unstarted Run with structured diagnostic，不进入 fallback（因为 fallback 也需要 material view）。

## Residual Risks Classification

| Risk | 分类 | Owner | 说明 |
|---|---|---|---|
| reactive path 共享 builder 可能触发 multi-pass 重写 | Scope risk | 后续 WU（plan 已明确此边界） | Plan 已设 stop condition：若需要大规模 multi-pass 重写则停止 |
| dispatch proactive compact fixture 缺失 | Testing risk | Implementation agent | 属于 implementation 测试工作，不阻塞 plan |
| worker-startup failure 可能把 budget exhausted 包装成 timeout | Diagnostic risk | Implementation agent（plan 明确要求补充 error_code） | Plan 已设 stop condition：若需新增 HostEvent 则停止 |
| EventLog-backed builder 无界扫描风险 | Performance risk | Implementation agent（plan 要求 bounded read） | Plan 已明确：用 latest compact boundary + current input cursor + caps 限定范围 |

## Tests / Validation Expectations

Implementation 后必须验证：

1. **Rolling compact**: 第二次 compact 的 material 不包含第一轮 compact 前旧 raw history（Slice 1 tests）
2. **Proactive budget**: 估算 fragments 与 compact material view 同源（Slice 2 tests）
3. **Material source independence**: memory snapshot missing/lag 不阻断 pre-dispatch compact material build（Slice 1 tests）
4. **Accepted compact projection**: `CONTEXT_COMPACTED` 被 memory consumer 物化并推进 checkpoint（Slice 4 tests）
5. **Bounded catch-up**: 未追完时 structured result 为 budget exhausted，不写 recovery（Slice 3 tests）
6. **Dispatch guard**: required cursor 覆盖才启动 worker；budget exhausted 不调用 worker.accept（Slice 3 tests）
7. **pyright**: 无新增或扩散类型错误

修正后的 validation commands（基于 F1 finding）：
```bash
source .venv/bin/activate
python -m pytest tests/host/test_compact_material.py
python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"
python -m pytest tests/host/test_public_compact_smoke.py
python -m pytest tests/host/test_memory_projection.py
python -m pytest tests/host/test_run_input_builder.py
python -m pytest tests/host/test_open_host_runtime.py
python -m pytest tests/host/test_logging.py
pyright
```

## Final Conclusion

**Verdict: needs-fix**

Plan 整体质量高：动机第一性原理正确、代码证据充分（14 处直接代码引用均验证通过）、设计真源对齐完整、架构边界清晰、4 个 slices 切分合理、anti-overengineering discipline 值得肯定。

2 个 medium findings 阻止直接进入 implementation：
- **F1**: validation commands 引用不存在的文件，浪费 implementation agent 时间
- **F2**: `build_compact_material_pack` 接口变更路径不明确，implementation agent 需自行裁决关键接口

2 个 low findings 建议修正但不阻塞：
- **F3**: 字段冗余
- **F4**: Slice 4 regression 处置流程不完整

所有 findings 均可通过 plan 文本修正解决，无需重新设计或新增架构裁决。修正后 plan 应为 code-generation-ready。

**Plan is NOT yet code-generation-ready** — 修正 F1 和 F2 后即可。

---

## Completion Report

- **artifact path**: `docs/reviews/wu-proj-01-plan-review-ds.md`
- **verdict**: needs-fix
- **finding count by severity**: 中 2，低 2
- **blocking open questions**: none
