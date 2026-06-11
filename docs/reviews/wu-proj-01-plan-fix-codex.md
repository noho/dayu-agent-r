# WU-PROJ-01 Plan Fix — AgentCodex

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: plan fix
- 日期: 2026-06-11
- Agent: AgentCodex
- Plan artifact: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- Controller adjudication: `docs/reviews/wu-proj-01-plan-review-controller-adjudication.md`
- Fix report artifact: `docs/reviews/wu-proj-01-plan-fix-codex.md`
- Gate constraint: 只修正 plan artifact 并新增本 fix report；不进入 implementation，不修改 production code / tests / design docs / control doc / GitHub issue，不 commit / push / PR。

## Fix Summary

plan 已按 controller adjudication 修正为 code-generation-ready。修正重点是把实现代理需要自行裁决的接口、边界、验证入口和失败语义收敛到 plan 中，避免 implementation 阶段走向 fake memory snapshot、无界 memory catch-up、错误测试入口或 reactive scope 扩张。

## Accepted Findings Fix Status

| # | Accepted finding | Fix status | 变更摘要 | 未覆盖风险 |
|---:|---|---|---|---|
| 1 | Validation Commands 引用不存在的 `tests/host/test_dispatch_context_governance.py` | fixed | Validation Commands 改为 `tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`，并加入 `tests/host/test_public_compact_smoke.py`；明确不得使用不存在的测试入口。 | 后续 implementation 可能仍需新增 focused fixture，但验证入口不再错误。 |
| 2 | `build_compact_material_pack` 接口变更路径不明确 | fixed | Slice 1 明确新增 keyword-only `previous_compacted_view: tuple[CompactMaterialBlock, ...] \| None = None`；`is not None` 时跳过 snapshot path，`None` 时保留 ordinary snapshot path；禁止 fake memory snapshot。 | 实际类型细节仍需 implementation 按现有 `CompactMaterialBlock` / `RunInputMaterialBlock` 约束落地并通过 pyright。 |
| 3 | evidence 去重源混合 memory snapshot 与 compact event | fixed | Slice 1 明确 evidence 去重只依赖 latest accepted compact event / artifact 的 accepted evidence mapping，不读取 Conversation Memory snapshot。 | 若 latest compact artifact 缺少 mapping，按 material source failure fail closed；不在本 gate 设计兼容读取。 |
| 4 | `ConversationMemoryProjectionCatchupPort` / `open_host.py` budget 注入路径不明确 | fixed | Implementation Decisions 与 Slice 3 明确 `ConversationMemoryProjectionCatchupPort.__init__` 接收 budget，`open_host.py` after-commit port 注入 best-effort budget，不保留 hot path 无界追平。 | close-only / test-only 无 budget 调用需要 implementation 明确 review，避免误进入 command path。 |
| 5 | `compact_material_source.py` 必要性未定 | fixed | Affected Files 与 Slice 1 改为默认在 `compact_material.py` 扩展；只有代码规模或 import boundary 证据充分时才新增 `compact_material_source.py`。 | 若实际实现拆文件，需要补 import boundary 测试。 |
| 6 | reactive compact path 最小适配边界不明确 | fixed | Slice 2 明确 reactive 只复用 shared previous-view/source helper，消除 latest compact 后 previous view 为空的 obvious divergence；multi-pass / overflow material freeze / evidence 分段必须停止并转后续 owner。 | reactive deep hardening 仍是 scope risk，保留在 residual risks。 |
| 7 | `MemoryProjectionCatchupBudget.timeout_seconds` 判断标准不明确 | fixed | Contract 与 Slice 3 明确第一版 budget 只含 `max_batches`、`max_scanned_events`、`purpose`，不加入 `timeout_seconds`。 | 单 row apply 时间不可控需后续 profiling 证明后另起设计。 |
| 8 | Slice 4 fixture 来源与断言链路不明确 | fixed | Slice 4 明确优先扩展 `test_memory_projection.py` accepted compact fixture，RunInput 断言复用 `test_run_input_builder.py` helpers，并固定 `accepted CONTEXT_COMPACTED -> checkpoint -> memory sections -> ordinary RunInput` 链路。 | 若现有 fixture 缺失，implementation 可新增最小 fixture；这属于测试工作量，不阻塞 plan。 |
| 9 | 首次 compact 无 latest compact 时 delta 起点 cursor 语义不明确 | fixed | Implementation Decisions 与 Slice 1 明确无 latest compact 时从 session 内第一条 relevant committed canonical fact 起算；若 current input 前无 relevant fact，则起点等于 current input sequence 且 delta 为空，并要求测试固定。 | “relevant committed canonical fact”的具体枚举需实现与 Slice 1 material rules 保持一致。 |
| 10 | material view 到 `BudgetTextFragment` 的映射规则缺失 | fixed | Slice 2 增加 previous compacted view、post-compact delta、current input anchor 到 `BudgetTextFragment` 的分段和 `fragment_ref` 规则。 | 预算估算仍用保守估算器，非 tokenizer 精确能力。 |
| 11 | material source failure fallback 行为不统一 | fixed | Slice 2 统一为 material source failure fail unstarted Run with structured diagnostic，不进入 deterministic recent-window fallback；fallback 只用于 compactor reject / failure 且已有可信 material view。 | fail closed 后的 user-facing error 文案由 implementation 现有 failure path 承载；不新增 HostEvent。 |
| 12 | 低风险 clarity：`PreDispatchCompactMaterialView` 与 `RunRow` 字段冗余、Slice 4 regression 归属 | fixed | Slice 1 移除 view 中 current input ref / cursor 第二真源，声明 `RunRow` 为权威来源；Slice 4 明确发现 Slice 1-3 regression 回到对应 slice allowed files 修复，pre-existing unrelated 问题记录 residual risk。 | `source_boundary` 仍可为 diagnostic 记录 current input sequence，但必须校验与 `RunRow` 一致。 |

## Validation

- 未运行 pytest。
- 未运行 pyright。
- 原因：本 gate 是 plan text fix，用户明确要求不运行 pytest / pyright。
- 已用文件读取与 `rg --files` 确认相关输入 artifact 与实际测试入口存在：`tests/host/test_dispatch_scheduler.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_compact_material.py`、`tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_open_host_runtime.py`、`tests/host/test_logging.py`、`tests/host/test_memory_repair.py`。

## Blocking Open Questions

无 blocking open questions。当前 plan 已把 controller accepted findings 收敛为可执行的 implementation 边界。

## Residual Risks

- Reactive compact deep hardening 仍可能需要后续 WU；本 plan 只允许最小 previous-view helper 适配。
- EventLog-backed builder 的 relevant canonical fact 枚举需要 implementation 严格跟随 Slice 1 material rules，避免无界扫描或遗漏必要 material。
- Existing fixtures 可能不足以覆盖完整 accepted compact -> projection -> ordinary RunInput 链路，implementation 可能需要新增最小测试 fixture。
- Diagnostic closeout 仍需 implementation 确保 budget exhausted 不被包装成 worker startup timeout 根因；若需要新增 HostEvent 或 durable schema，应按 stop condition 回报总控。
