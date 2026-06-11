# WU-PROJ-01 Plan Re-Review — AgentMiMo

## 元数据

- review target：`docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`（plan fix 后版本）
- plan fix report：`docs/reviews/wu-proj-01-plan-fix-codex.md`
- controller adjudication：`docs/reviews/wu-proj-01-plan-review-controller-adjudication.md`
- 前次 MiMo review：`docs/reviews/plan-review-20260611-124757.md`
- 前次 DS review：`docs/reviews/wu-proj-01-plan-review-ds.md`
- reviewer：AgentMiMo (adversarial plan re-review)
- timestamp：2026-06-11
- review scope：controller accepted findings fix status、plan code-generation-readiness、residual blocker / under-design / over-design / scope drift / architecture boundary / testing gap

## Re-Review 方法

逐项检查 controller adjudication 接受的 12 条 findings 是否已在 plan fix 中收敛为可执行 implementation 边界；然后对修正后的 plan 做全量 code-generation-readiness 复核。

## Controller Accepted Findings Fix Status

### 1. Validation Commands 引用不存在的测试文件 — ✅ fixed

plan 已将 `tests/host/test_dispatch_context_governance.py` 替换为真实存在的 `tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"` 和 `tests/host/test_public_compact_smoke.py`。plan 末尾明确禁止使用不存在的测试入口。代码验证确认目标文件均存在，不存在的文件确认不存在。

### 2. `build_compact_material_pack` 接口变更路径不明确 — ✅ fixed

plan Slice 1 exact changes 明确新增 keyword-only `previous_compacted_view: tuple[CompactMaterialBlock, ...] | None = None`。语义固定为：
- `is not None` 时直接使用 explicit previous view，跳过 `_previous_blocks_from_snapshot`。
- `is None` 时保留现有 snapshot 路径，供 ordinary RunInput 既有调用继续使用。
- proactive / pre-dispatch 必须传入 `material_view.previous_compacted_view`。
- 禁止构造 fake `ConversationMemorySnapshotVNext`。

接口变更方向明确、向后兼容、不引入 fake snapshot，implementation agent 无需自行裁决。

### 3. evidence 去重源混合 memory snapshot 与 compact event — ✅ fixed

plan Slice 1 invariants 明确："evidence 去重只依赖 latest accepted compact event / artifact 中的 accepted evidence mapping。不得读取 Conversation Memory snapshot 中的 `evidence_backed_facts` 或其它 projection material 作为去重来源；projection lag 下 memory snapshot 的额外 material 不反向成为 compact input truth。"

与设计真源 §24.1 "compact material 的真源是 Host durable EventLog、payload descriptor 与 artifact"完全对齐。

### 4. `ConversationMemoryProjectionCatchupPort` / `open_host.py` budget 注入路径不明确 — ✅ fixed

plan Slice 3 exact changes 明确：
- `ConversationMemoryProjectionCatchupPort.__init__` 新增 keyword-only `budget: MemoryProjectionCatchupBudget | None = None`。
- port 内部保存 budget，在 `catch_up_projection()` 调用时传入。
- `budget is None` 只允许 explicitly reviewed close-only / test-only 调用。
- `open_host.py` 构造 port 时必须传入 after-commit best-effort budget。

注入路径从构造到调用全链路明确。

### 5. `compact_material_source.py` 必要性未定 — ✅ fixed

plan 改为默认在 `compact_material.py` 扩展。"只有当 builder 代码规模或 import boundary 证据充分时才拆出"。实现 agent 不再需要自行判断是否新建模块。

### 6. reactive compact path 最小适配边界不明确 — ✅ fixed

plan Slice 2 明确 reactive 最小适配边界："本 WU 只允许让 reactive path 复用 shared previous-view/source helper，使 `build_compact_material_pack(...)` 在存在 latest accepted compact 时能接收 explicit `previous_compacted_view`，并消除继续传 `memory_snapshot=None` 导致 previous view 永远为空的 obvious divergence。"

同时明确 stop condition："不得在本 WU 内实现 reactive multi-pass、冻结 overflow ordinary material list 的大规模重写或 evidence-block 分段；如果 reactive path 需要这些改造才能通过，应停止并转后续 owner。"

边界清晰，scope 受控。

### 7. `MemoryProjectionCatchupBudget.timeout_seconds` 判断标准不明确 — ✅ fixed

plan 明确："本 WU 不加入 `timeout_seconds`，避免引入 clock / async 测试面；若后续 production profiling 证明单 row apply 时间不可控，再另起设计。"

第一版 budget 只含 `max_batches`、`max_scanned_events`、`purpose`。implementation agent 不需要自行裁决。

### 8. Slice 4 fixture 来源与断言链路不明确 — ✅ fixed

plan Slice 4 明确：
- 优先扩展 `tests/host/test_memory_projection.py` 现有 accepted compact fixture。
- ordinary RunInput 断言复用 `tests/host/test_run_input_builder.py` 的 compact payload / memory snapshot helper。
- 链路固定为 `accepted CONTEXT_COMPACTED -> projection checkpoint advanced in same transaction -> memory snapshot sections materialized -> ordinary RunInput includes those business sections`。
- regression 回到对应 slice allowed production files 修复；pre-existing 问题记录 residual risk。

### 9. 首次 compact 无 latest compact 时 delta 起点 cursor 语义不明确 — ✅ fixed

plan Implementation Decision 4 和 Slice 1 均明确："首次 compact 没有 latest accepted compact 时，delta 起点是当前 session 内第一条 relevant committed canonical fact 的 event sequence；如果 current input 前没有 relevant fact，则起点等于当前 `USER_INPUT_ACCEPTED` 的 event sequence，且 delta 为空。"

测试要求："首次 compact：测试固定 `post_compact_delta_start_sequence` 等于 session 内第一条 relevant committed canonical fact；若 current input 前没有 relevant fact，则等于 `run.input_event_sequence` 且 delta 为空。"

### 10. material view 到 `BudgetTextFragment` 的映射规则缺失 — ✅ fixed

plan Slice 2 明确三种映射规则：
- previous compacted view：`previous:<business-section>:<stable-block-id>`，text 为已校验业务可读 previous compact 文本。
- post-compact delta：`delta:<section>:<block_id>`，不得把 event sequence、payload ref、digest 作为 LLM-facing 文本。
- current input anchor：`current-input:<prompt-local-anchor>`，text 为 bounded current input anchor 文本。

与设计真源 §23 "ordinary RunInput 的 LLM-facing material 不得暴露内部治理标识"完全对齐。

### 11. material source failure fallback 行为不统一 — ✅ fixed

plan Slice 2 统一为："material source failure 统一 fail closed：append structured governance diagnostic / `CONTEXT_COMPACTION_FAILED` 后 fail unstarted Run；不得进入 deterministic recent-window fallback，因为此时没有可信 material view 可供 fallback。"

deterministic recent-window fallback 仅限 "compactor reject / failure / repair budget exhausted 之后，且前提是本次已经成功构造可信 material view"。

### 12. 低风险 clarity：`PreDispatchCompactMaterialView` 字段冗余与 Slice 4 regression 归属 — ✅ fixed

- Slice 1 明确移除 view 中 `current_input_ref` / `input_cursor` 第二真源，声明 `RunRow` 为权威来源。`source_boundary` 可为 diagnostic 记录 current input event sequence，但必须校验与 `RunRow` 一致。
- Slice 4 明确："若测试暴露 Slice 1-3 引入的问题，应回到对应 slice 的 allowed production files 修复；若暴露 pre-existing unrelated 问题，应记录为 residual risk 并回报总控。"

## 全量 Code-Generation-Readiness 复核

### 必检项逐项判定

| 检查项 | 结果 | 说明 |
|---|---|---|
| validation commands 是否改为真实存在的测试入口 | ✅ | 全部 8 条命令指向已存在文件；明确禁止使用不存在的入口 |
| `build_compact_material_pack` 接口路径是否明确且不要求 fake memory snapshot | ✅ | keyword-only `previous_compacted_view`；`is not None` 走 explicit 路径；禁止 fake snapshot |
| evidence 去重是否不再依赖 Conversation Memory snapshot | ✅ | 只依赖 latest accepted compact event / artifact 的 accepted evidence mapping |
| memory catch-up budget 注入路径是否明确且无 hot path 无界追平 | ✅ | port 构造注入 budget；after-commit 使用 best-effort budget；`budget is None` 只允许 close-only / test-only |
| compact material source 默认模块位置 | ✅ | 默认 `compact_material.py`，仅在代码规模 / import boundary 证据充分时拆分 |
| reactive 最小适配 | ✅ | 只复用 shared previous-view/source helper；multi-pass / overflow / evidence 分段转后续 owner |
| 无 `timeout_seconds` | ✅ | 第一版 budget 固定为 `max_batches` + `max_scanned_events` + `purpose` |
| Slice 4 fixture 来源 | ✅ | 优先扩展现有 fixture；回归链路明确为 `CONTEXT_COMPACTED -> projection -> RunInput` |
| 首次 compact cursor | ✅ | session 内第一条 relevant committed canonical fact 或 `run.input_event_sequence` |
| BudgetTextFragment 映射 | ✅ | 三种 fragment_ref 规则明确且与设计真源 LLM-facing boundary 对齐 |
| material source failure fail-closed | ✅ | fail unstarted Run with structured diagnostic；fallback 仅限已有可信 material view |
| 字段冗余 | ✅ | 移除 view 中 `current_input_ref` / `input_cursor`；`RunRow` 为权威来源 |
| regression 归属 | ✅ | Slice 1-3 regression 回对应 slice 修复；pre-existing 记录 residual risk |

### 架构边界检查

| Boundary | 状态 | 证据 |
|---|---|---|
| Host ↔ Engine | ✅ 不涉及 | plan 不修改 Engine public contract 或 Engine runtime 行为 |
| Context Governance ↔ Conversation Memory | ✅ 方向正确 | compact material truth 从 EventLog 构造；memory 消费 compact event 做物化 |
| Context Governance ↔ RunInputBuilder | ✅ 边界清晰 | pre-dispatch compact material（EventLog-backed）≠ ordinary RunInput（memory-backed） |
| dayu.host ↔ dayu.runtime | ✅ 不穿透 | 不引入 runtime 层新依赖 |
| dayu.host ↔ dayu.service/ui/fins | ✅ 不穿透 | 不修改上层 |
| durable schema / EventLog / HostEvent | ✅ 不变更 | 明确无 schema 变更 |
| ProjectionRunner ownership | ✅ 正确 | 不重写 ProjectionRunner，只给调用方加 bounded budget |

### Over-Design / Under-Design / Scope Drift 检查

| 检查项 | 状态 | 说明 |
|---|---|---|
| 无新 public API | ✅ | 新增类型均为 Host internal |
| 无新 durable schema | ✅ | 不修改 EventLog event type |
| 无新状态机状态 | ✅ | 不引入 `RECOVERING` / `LOST` |
| 无通用 material platform | ✅ | 只新增 pre-dispatch compact 所需的 builder |
| 复用现有类型 | ✅ | 复用 `RunInputMaterialBlock` / `CompactMaterialSection` / `CompactMaterialBlockKind` |
| scope boundary 清晰 | ✅ | 4 个 slice 沿依赖边界切分，stop conditions 覆盖关键停止条件 |
| 无 scope drift | ✅ | reactive path 有明确最小适配边界和 stop condition |

## Residual Risks

| ID | 风险 | 分类 | 建议追踪 |
|---|---|---|---|
| WU-PROJ-01-RR1 | Reactive compact path 的 previous view 适配可能超预期 | scope risk | implementation Slice 2 完成后评估；若需要大规模 reactive 改造，按 plan stop condition 转后续 owner |
| WU-PROJ-01-RR2 | EventLog-backed builder 首次 compact 时可能需要扫描大量历史 | performance risk | implementation 必须用 latest compact boundary 和 current input cursor 限定读取范围 |
| WU-PROJ-01-RR3 | 现有 dispatch proactive compact 测试可能缺少 focused fixture | testing risk | implementation 新增最小 Host durable fixture |
| WU-PROJ-01-RR4 | `for_close_flush()` 工厂方法需要 implementation review 确保不误入 command path | implementation risk | Slice 3 明确 `budget is None` 只允许 close-only / test-only |

## Verdict

**pass**

controller adjudication 接受的 12 条 findings 全部标记为 fixed，修正内容与 plan artifact 一致，修正方向正确，收敛为可执行 implementation 边界。修正后的 plan 全量 code-generation-readiness 复核通过：无 blocker、无 under-design、无 over-design、无 scope drift、无架构边界违反、无测试缺口。

关键判断：

1. **12 条 accepted findings 全部 fixed**：每条 fix 都收敛为 plan 中的具体 invariant、exact change 或 test requirement，implementation agent 不需要自行裁决设计决策。
2. **validation commands 全部指向已存在文件**：8 条验证命令均可直接执行。
3. **`build_compact_material_pack` 接口变更方向明确**：keyword-only `previous_compacted_view` 向后兼容，禁止 fake snapshot。
4. **evidence 去重真源唯一**：只依赖 latest accepted compact event / artifact，不读取 Conversation Memory snapshot。
5. **budget 注入路径全链路明确**：从 port 构造到 after-commit 调用到 dispatch 前 catch-up，每层都有明确 budget 策略。
6. **reactive 最小适配有明确边界和 stop condition**：不会导致 scope drift。
7. **4 个 slice 沿依赖边界切分**：每个 slice 有明确 allowed files、invariants、exact changes 和 tests。

## Completion Report

- **artifact path**: `docs/reviews/wu-proj-01-plan-rereview-mimo.md`
- **verdict**: pass
- **fixed findings status**: 12/12 accepted findings confirmed fixed
- **new findings**: 0
- **blocking open questions**: none
- **residual risks**: 4（均有 owner / destination，不阻塞 implementation gate）
