# WU-PROJ-01 Plan Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: plan review controller adjudication
- 日期: 2026-06-11
- Plan artifact: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- AgentMiMo review artifact: `docs/reviews/plan-review-20260611-124757.md`
- AgentDS review artifact: `docs/reviews/wu-proj-01-plan-review-ds.md`
- Controller verdict: plan fix required

## 总体裁决

两路 review 均确认 WU-PROJ-01 的动机成立、架构方向正确、scope 边界基本清楚，且无需新增 public API、durable schema、EventLog event type、HostEvent 或 Run / Attempt 状态机。

但 AgentDS 给出 `needs-fix`，且 AgentMiMo 的中等 finding 指向 plan 中会影响 implementation agent 裁决的模糊点。因此当前 plan 不进入 implementation gate，下一步进入 AgentCodex plan fix gate。

## AgentDS Findings

| Finding | 裁决 | 说明 |
|---|---|---|
| F1 Validation Commands 引用不存在的测试文件 | accepted | 当前 plan 中 `tests/host/test_dispatch_context_governance.py` 不存在，必须改为实际存在的 dispatch compact / proactive governance 测试入口，例如 `tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`，并纳入 `tests/host/test_public_compact_smoke.py`。 |
| F2 `build_compact_material_pack` 接口变更路径不明确 | accepted | 这是 code-generation-ready blocker。Plan 必须明确 `build_compact_material_pack` 如何接收 EventLog-backed previous compacted view，禁止 implementation agent 自行选择伪造 memory snapshot 或其它绕路。建议方案是新增明确的 keyword-only previous material 参数，同时保留 snapshot path 供 ordinary RunInput 既有调用继续使用。 |
| F3 `PreDispatchCompactMaterialView` 字段与 `RunRow` 信息冗余 | accepted | 非 blocker，但 plan 应减少或解释冗余字段的真源优先级，避免同一事实在 view 与 `RunRow` 之间形成维护歧义。 |
| F4 Slice 4 缺少 production regression 处置流程 | accepted | Plan fix 应说明 Slice 4 如果暴露 Slice 1-3 引入的 regression，应回到对应 slice allowed files 修复；若暴露 pre-existing unrelated 问题，应记录为 residual risk 并回报总控。 |
| F5 类型名引用 | rejected-with-reason | DS 已自行降级为 informational，并确认 `_MemoryProjectionCatchupPort` 在 `open_host.py` 中存在，非实际 finding。 |

## AgentMiMo Findings

| Finding | 裁决 | 说明 |
|---|---|---|
| M1 `_proactive_represented_evidence_refs` 去重源混合 memory snapshot 与 compact event | accepted | Plan fix 必须明确 compact material builder 的 evidence 去重只依赖 latest accepted compact event / artifact mapping，不读取 Conversation Memory snapshot。Projection lag 下 memory snapshot 中的 material 不得反向成为 compact input truth。 |
| M2 Slice 3 budget 接口缺少 `ConversationMemoryProjectionCatchupPort` 改造路径 | accepted | Plan fix 必须明确 budget 注入路径：`ConversationMemoryProjectionCatchupPort` 构造或调用接收 internal budget，`open_host.py` 的 after-commit port 使用 best-effort budget，不保留 hot path 无界追平。 |
| M3 新增 `compact_material_source.py` 必要性未定 | accepted | Plan fix 应把默认方案收敛为在 `compact_material.py` 内扩展，只有当 implementation 证据显示代码规模或 import boundary 明显需要独立模块时才新增 `compact_material_source.py`。 |
| M4 Reactive compact path 的 `memory_snapshot=None` 适配范围不明确 | accepted | Plan fix 必须定义最小适配边界：本 WU 只复用 shared previous-view/source helper 消除 obvious divergence；若 reactive path 需要 multi-pass 或大规模重写，必须停止并转后续 owner。 |
| M5 `MemoryProjectionCatchupBudget.timeout_seconds` 判断标准不明确 | accepted | Plan fix 应明确第一版不加入 `timeout_seconds`，先以 `max_batches` 与 `max_scanned_events` 实现 bounded 行为；若后续 profiling 证明单行处理耗时不可控，再另行设计 clock / timeout。 |
| M6 Slice 4 regression 测试缺少 fixture 来源说明 | accepted | Plan fix 应说明是扩展现有 fixture 还是新增 fixture，并明确 accepted compact -> projection checkpoint -> ordinary RunInput 的断言链路。 |
| M7 首次 compact 的 session 起点 cursor 语义不明确 | accepted | Plan fix 必须定义无 latest compact 时的 delta 起点，例如 session 内首个 relevant committed canonical fact 的 event sequence，并用测试固定。 |

## 额外 Clarifications

| 项目 | 裁决 | 说明 |
|---|---|---|
| Budget fragments 映射规则 | accepted | Plan fix 应说明 material view 如何映射为 `BudgetTextFragment`，至少按 previous compacted view、post-compact delta、current input anchor 的 stable section/source ref 分段。 |
| Material source failure 后是否 fallback | accepted | Plan fix 应统一为 fail unstarted Run with structured diagnostic，不进入 deterministic recent-window fallback；fallback 只能用于 compactor reject/failure 后仍有可信 material view 的场景。 |

## 下一步

- 当前 gate 进入 plan fix。
- 负责 Agent: AgentCodex。
- Expected fix artifact: `docs/reviews/wu-proj-01-plan-fix-codex.md`。
- Plan fix 只允许修改 plan artifact；如需同步总控状态，可由 controller 后续更新。
- Plan fix 不得 implementation、review、commit、push、PR 或修改 production code。
