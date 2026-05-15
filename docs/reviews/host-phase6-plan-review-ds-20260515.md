# Host Phase 6 Plan Review - 2026-05-15

- **reviewer**: AgentDS (role-scoped plan review)
- **reviewed target**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- **design source**: `docs/host/design.md`
- **control doc**: `docs/host/implementation-control.md`
- **controller adjudication**: `docs/reviews/host-phase6-design-discussion-controller-adjudication-20260515.md`
- **current gate**: Phase 6 handoff implementation-ready plan review
- **verdict**: BLOCKED — 4 blocking findings 必须修复后方可进入 implementation

## Findings

### DS-F1-未修复-BLOCKING-PolicySnapshot 与 no-tool 硬约束未拆解

- **Plan位置**: §5.1 P6-S1 允许修改 `dayu/host/run_input.py`；§6 P6-S1 exact changes 未提及 `PolicySnapshot` 与 `_validate_no_tool_snapshot` 约束放宽。
- **问题类型**: 实现前置条件缺失 — implementation agent 会在第一行代码就撞到硬约束。
- **直接证据**:
  - `dayu/host/run_input.py:171-172` — `PolicySnapshot.__post_init__` 无条件 `raise ValueError("AgentPolicy.allow_tool_calls must be False")`。
  - `dayu/host/run_input.py:964-980` — `_validate_no_tool_snapshot` 无条件 `raise HostDurableError("RunInputBuilder requires disable_tools=True")` 与 `requires allow_tool_calls=False`。
  - Plan §6 P6-S1 exact changes 只说 "Replace / extend no-op ToolSchemaSnapshotProvider and ToolExecutorProvider wiring"，但这两个验证函数会在工具启用 Attempt 的首个 build 调用中直接炸掉。
- **影响**: 工具启用的 `RunInputBuilder.build()` 无法执行；implementation agent 必须自行决定何时、如何放宽这两个约束，这属于 Host policy 决策，不应由 implementation agent 选择。
- **建议修复**:
  1. 在 P6-S1 exact changes 中显式列出：移除 `PolicySnapshot.__post_init__` 中的 `allow_tool_calls` 硬拒绝；改为由调用方（PolicySnapshotProvider）在构造期校验。
  2. 在 P6-S1 exact changes 中显式列出：将 `_validate_no_tool_snapshot` 改为条件校验——仅在 Attempt 为 replay / no-tool scope 时执行，或拆为两个函数 `_validate_tool_snapshot` / `_validate_no_tool_snapshot` 由调用路径选择。
  3. 在 P6-S1 tests 中增加：工具启用 `PolicySnapshot(allow_tool_calls=True)` 构造成功并通过 RunInputBuilder。

### DS-F2-未修复-BLOCKING-DefaultSceneParameterProvider 硬编码 tools=disabled

- **Plan位置**: §5.1 P6-S1 允许修改 `dayu/host/run_input.py`；§6 P6-S1 exact changes 未提及 `DefaultSceneParameterProvider`。
- **问题类型**: 实现遗漏 — system message 内容与工具启用状态矛盾。
- **直接证据**:
  - `dayu/host/run_input.py:587` — `DefaultSceneParameterProvider.build_scene_messages` 无条件输出 `"tools=disabled"`。
  - Plan §6 P6-S1 exact changes 未提及任何 system message 更新。
  - 设计文档 §18.1 明确 RunInputBuilder 为工具启用 Attempt 暴露 tool schemas；system message 中写 "tools=disabled" 与此矛盾。
- **影响**: 工具启用 Attempt 的 system message 会误导模型；实现 agent 需要自行决定是否修改及如何修改 `DefaultSceneParameterProvider`，这是设计决策。
- **建议修复**:
  1. 在 P6-S1 exact changes 中显式列出：`DefaultSceneParameterProvider` 的 system message 生成需根据 policy snapshot 或 tool schema snapshot 动态反映工具状态。
  2. 或在 P6-S1 exact changes 中显式列出：新增 `ToolEnabledSceneParameterProvider` 作为工具启用 Attempt 的 scene provider。
  3. 在 P6-S1 tests 中增加：工具启用场景的 system message 不包含 "tools=disabled"。

### DS-F3-未修复-BLOCKING-RunInputBuilder 工具启用/禁用决策机制缺失

- **Plan位置**: §6 P6-S1 exact changes；§6 P6-S3 exact changes。
- **问题类型**: 架构决策缺口 — implementation agent 无法从 plan 中得知 RunInputBuilder 如何区分 tool-enabled vs no-tool Attempt。
- **直接证据**:
  - `dayu/host/run_input.py:716-739` — `create_no_tool_run_input_builder` 硬编码 `NoopToolSchemaSnapshotProvider` 与 `NoToolExecutorProvider`；没有对应的 `create_tool_enabled_run_input_builder` 工厂。
  - `dayu/host/api.py:240-260` — `AttemptDispatchSnapshot` 不携带 `start_reason`、`is_replay`、`tool_enabled` 或任何可用于区分工具启用/禁用的显式字段。
  - 设计文档 §18.1 要求 "Replay 即使存在 effective ToolBundle，也不向模型暴露 tool schemas"；implementation control §6 关键设计问题要求 "必须确认 replay no-tool 防线如何从 RunInputBuilder 与 ToolRuntime 双层执行"。
  - Plan §6 P6-S1 只说 "Replace / extend ... so tool-enabled Attempts can receive a ToolRuntimeHandle"，未指定决策机制。
  - Plan §6 P6-S3 只说 "replay/no-tool scope rejects model tool call"（defense-in-depth），但 RunInputBuilder 层的主防线决策机制未定义。
- **影响**: implementation agent 必须自行设计 Attempt 级别的工具启用判定机制（是否依赖 `start_reason`、是否在 `AttemptDispatchSnapshot` 加字段、是否在 dispatch 路径注入策略），这突破了 Host 分层设计边界。
- **建议修复**:
  1. 在 P6-S1 exact changes 中显式指定：RunInputBuilder 通过什么机制区分 tool-enabled vs replay/no-tool Attempt。
  2. 建议方案（二选一）：(a) `AttemptDispatchSnapshot` 增加 `start_reason: RunStartReason` 字段，RunInputBuilder 据此选择 provider 集合；(b) 在 dispatch path 中根据 `start_reason` 调用不同的 RunInputBuilder 工厂函数。
  3. 同步更新 §3.9 replay guard 描述，明确双层防线的第一层（RunInputBuilder 不暴露 schema）的触发条件。

### DS-F4-未修复-BLOCKING-engine_ingest.py 工具事件映射变更未细化

- **Plan位置**: §5.1 P6-S2 允许修改 `dayu/host/engine_ingest.py`；§6 P6-S2 exact changes "Ensure EngineEvent ingest cannot create duplicate tool canonical facts; late Engine tool events are diagnostic / preview only if current code sees them."
- **问题类型**: 实现范围不明确 — 当前 engine_ingest.py 已映射多种工具 EngineEvent，变更范围未量化。
- **直接证据**:
  - `dayu/host/engine_ingest.py:1683-1757` — 已映射 `TOOL_CALL_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE` 等多种 Engine 工具事件。
  - `dayu/host/engine_ingest.py:1751-1754` — `TOOL_RESULT_ACCEPTED` 当前 event mapping 未明确使用 `EventClass.PREVIEW` 还是 `EventClass.CANONICAL_FACT`（需要读完整映射函数确认）。
  - 设计文档 §18.2 硬约束："EngineEvent ingest 不能替代 ToolRuntime accept path 写工具 canonical facts"。
  - Plan §6 P6-S2 exact changes 只说 "late Engine tool events are diagnostic / preview only"，但未列举哪些现有映射的 event class 需要从 canonical 改为 preview/diagnostic。
- **影响**: implementation agent 可能保留现有工具事件映射不变，导致 EngineEvent ingest 与 ToolRuntime accept path 双重写入 canonical tool facts，违反设计硬约束。
- **建议修复**:
  1. 在 P6-S2 exact changes 中显式列出：`TOOL_RESULT_ACCEPTED` EngineEvent 映射必须改为 `EventClass.PREVIEW` 或 `EventClass.DIAGNOSTIC`（如当前已是 preview 则确认不冲突）。
  2. 在 P6-S2 exact changes 中显式列出：`TOOL_CALL_REQUESTED` EngineEvent 与 ToolRuntime 的 `TOOL_CALL_REQUESTED` canonical fact 关系——Engine 事件是 preview，ToolRuntime accept path 才是 canonical。
  3. 在 P6-S2 tests 中增加：验证 EngineEvent `TOOL_RESULT_ACCEPTED` 不产生 canonical fact，且 ToolRuntime accept path 的 `TOOL_RESULT_ACCEPTED` 是唯一 canonical 真源。

### DS-F5-未修复-HIGH-测试文件迁移范围未量化

- **Plan位置**: §5.2 P6-S3 test files — `tests/host/test_phase5_local_execution_integration.py`。
- **问题类型**: 测试迁移风险 — 修改范围模糊可能导致破坏 Phase 5 已验证行为或引入兼容性 hack。
- **直接证据**:
  - Plan §6 P6-S3 tests 描述："`tests/host/test_phase5_local_execution_integration.py` only to migrate no-tool assertions to tool-enabled cases without preserving compatibility hacks"。
  - 当前 `test_phase5_local_execution_integration.py` 的内容和断言数量未知，implementation agent 无法从 plan 知道哪些断言需要改、哪些需要保留。
- **影响**: implementation agent 可能过度修改破坏 Phase 5 已验证的 no-tool 路径，或保守不改导致 P6-S3 集成测试覆盖不足。
- **建议修复**:
  1. 在 P6-S3 exact changes 中更具体描述：哪些 test case 需要从 no-tool 迁移为 tool-enabled，哪些 no-tool case 保留为 replay 路径测试。
  2. 或者将 Phase 5 测试完全保留不变，新增独立的 tool-enabled integration test（已在 `test_phase6_toolruntime_integration.py` 覆盖），明确 `test_phase5_local_execution_integration.py` 不做修改。

### DS-F6-未修复-HIGH-TruncationManager 与 business ToolTruncateSpec 的 wiring 未指定

- **Plan位置**: §3.6 TruncationManager / fetch_more；§6 P6-S4 exact changes。
- **问题类型**: 数据流缺口 — TruncationManager 如何获取业务工具的 `ToolTruncateSpec` 未在 plan contract 中体现。
- **直接证据**:
  - 设计文档 §19 明确 "Host / ToolRuntime keeps ToolTruncateSpec" 且从 `ToolDefinition.truncate` 派生。
  - `dayu/contracts/tool_declaration.py:159-163` — `ToolBundle.truncate_specs()` 已提供 `Mapping[str, ToolTruncateSpec]`。
  - `dayu/contracts/tool_schema.py:84-107` — `ToolTruncateSpec` 包含 `enabled`、`strategy`、`limits`、`target_field`、`field_path`、`ttl_seconds`。
  - Plan §3.3 `EffectiveToolBundle` 包含 `truncate_specs_by_name: Mapping[str, ToolTruncateSpec]`。
  - 但 §3.6 `TruncationPort` 输入包含 `ToolTruncateSpec | None` 单值而非从 bundle 按 tool name 查询；§6 P6-S4 exact changes 未说明 `TruncationManager` 如何从 `EffectiveToolBundle.truncate_specs_by_name` 初始化。
- **影响**: implementation agent 可能遗漏将 business `ToolTruncateSpec` 从 `EffectiveToolBundle` 注入到 `TruncationManager` 的 wiring，导致截断策略对业务工具不生效。
- **建议修复**:
  1. 在 §3.6 `TruncationManager` 类型定义中增加构造参数：接收 `truncate_specs_by_name: Mapping[str, ToolTruncateSpec]`。
  2. 在 P6-S4 exact changes 中显式列出：`TruncationManager` 从 `EffectiveToolBundle.truncate_specs_by_name` 初始化。

### DS-F7-未修复-MEDIUM-P6-S3 执行流步骤3隐含依赖 P6-S5 的 duplicate pass-through

- **Plan位置**: §3.4 步骤3；§6 P6-S3 non-goals。
- **问题类型**: 跨 slice 隐含依赖 — P6-S3 执行流中提到 "先执行 policy / duplicate governance"，但 duplicate governance 完整实现在 P6-S5。
- **直接证据**:
  - Plan §3.4 步骤3: "先执行 policy / duplicate governance；若决策为 governed rejection、reuse、hint、require_justification 或 hard_stop..."
  - Plan §6 P6-S3 non-goals: "no duplicate governance beyond pass-through allow"。
  - P6-S3 的 pass-through `allow` 需要在 `DuplicateGovernancePort` 存在的前提下才能调用，但该 port 的完整实现在 P6-S5。
- **影响**: implementation agent 在 P6-S3 需要提供一个 stub `DuplicateGovernancePort` 返回 `allow`，在 P6-S5 替换为完整实现。plan 未明确这个 stub 的存在和替换方式。
- **建议修复**:
  1. 在 P6-S3 exact changes 中显式列出：提供 `PassThroughDuplicateGovernance` stub，始终返回 `allow`。
  2. 或在 §3.2 ToolRuntime ports 中增加说明：P6-S3 可先注入 always-allow stub，P6-S5 替换为完整 matrix。

### DS-F8-未修复-MEDIUM-ToolFactAcceptCandidate 字段构造时机与校验规则未指定

- **Plan位置**: §3.5 Host Accept Candidate 字段列表。
- **问题类型**: 实现细节缺失 — 18 个字段的 dataclass 缺少必填/可选语义和构造期校验规则。
- **直接证据**:
  - Plan §3.5 列出 18 个 `ToolFactAcceptCandidate` 字段，其中 `payload_ref: HostPayloadRef | None`、`tool_idempotency_key: str | None`、`duplicate_key: str | None`、`duplicate_decision: DuplicateDecisionKind | None` 等可为 None。
  - 未指定哪些字段在何种 tool fact kind 下为必填（如 `completed` 必须有 `payload_ref`，`governed_error` 可能不需要）。
  - 未指定 `accept_idempotency_key` 与 `semantic_input_digest` 的派生规则如何通过 `__post_init__` 校验。
- **影响**: implementation agent 可能构造不完整的 candidate 并通过 accept path，导致 EventLog 中出现语义不完整的 tool fact。
- **建议修复**:
  1. 在 §3.5 增加 candidate 构造规则表：按 `ToolFactKind` 列出哪些字段必填。
  2. 在 candidate dataclass 定义中增加 `__post_init__` 校验描述。

### DS-F9-未修复-LOW-批内 partial accept failure 测试覆盖缺失

- **Plan位置**: §7 Testing Matrix — Integration 部分。
- **问题类型**: 测试覆盖缺口 — 批内一个 call accept 失败但不影响其他已 accepted call 的路径未覆盖。
- **直接证据**:
  - Plan §3.4 步骤9: "批内一个 call 的 accept failure 不得让其它已 accepted call 的事实回滚"。
  - Plan §7 Integration tests 未包含 "batch with mixed accept outcomes" 测试用例。
- **影响**: 批内 partial failure 的正确性仅靠实现约束保证，没有测试证明。
- **建议修复**: 在 §7 Integration tests 中增加一条：batch 内部分 call accept 被拒绝时，已 accepted call 的 outcome 仍返回给 Engine。

### DS-F10-未修复-LOW-duplicate key 是否包含 index_in_iteration 未明确

- **Plan位置**: §3.7 Duplicate Governance — 判定信号。
- **问题类型**: 语义歧义 — `index_in_iteration` 是否参与 duplicate key 计算。
- **直接证据**:
  - `dayu/contracts/tool_call.py:65` — `ToolCallRequest.index_in_iteration` 是 LLM 输出顺序序号。
  - Plan §3.7 判定信号包括 "tool name / version / schema digest"、"normalized arguments digest"、"optional semantic key"、"accepted result digest"。
  - 未提及 `index_in_iteration` 是否参与 key 计算。同一 iteration 内重复 tool call（相同 name + args）若 index 不同，判定 `reuse` 还是 `allow`？决定权在 implementation agent。
- **影响**: 同一 iteration 内模型对同一工具同一参数发出两个调用时，duplicate governance 行为不确定。
- **建议修复**: 在 §3.7 增加明确说明：`index_in_iteration` 不参与 duplicate key 计算（或反之），并给出一致性理由。

## Conclusion

- **verdict**: BLOCKED
- **finding count**: 10
- **blocking count**: 4 (DS-F1, DS-F2, DS-F3, DS-F4)
- **high count**: 2 (DS-F5, DS-F6)
- **medium count**: 2 (DS-F7, DS-F8)
- **low count**: 2 (DS-F9, DS-F10)

### Open Questions

1. 当前 `EventLog` 是否有 event_type 闭合集合校验？若有，`TOOL_CALL_REQUESTED` / `TOOL_CALL_GOVERNED` / `TOOL_RESULT_ACCEPTED` 需要注册到 schema。——plan §10 将此列为 working assumption，应在 implementation 启动前确认。
2. `HostToolingOptions.framework_tool_policy.enabled_framework_tools` 的默认值当前为 `frozenset()`（不启用 fetch_more）。Plan §10 说"默认构造可以保持禁用，除非 Host command policy 开启 truncation"。实现时需确认默认构造是否满足 integration test 需求，还是 test 显式开启。

### Remaining Test/Risk Gaps (PASS 条件下的 residual)

- 即使所有 BLOCKING 修复后，以下 risk 仍需 implementation agent 关注：
  - `PolicySnapshot` 拆分为 tool-enabled / no-tool 两种变体后，需要确保 replay path 仍走 no-tool 变体，且 Attempt 级别的 start_reason 准确传递。
  - `create_no_tool_run_input_builder` 与新增的 `create_tool_enabled_run_input_builder`（或等效构造路径）之间的代码复用度——避免两个 builder factory 互相复制造成 drift。
  - `ToolAcceptRetryPolicy` 的 backoff 若不够保守，可能在 durable store 短暂不可用时让整个 batch 返回 governed error；需要 integration 级别的 transient failure 测试（可延后到 Phase 11）。

### Verification

```bash
cd /Users/leo/workspace/dayu-agent-r && git diff --check docs/reviews/host-phase6-plan-review-ds-20260515.md
```

- **artifact path**: `docs/reviews/host-phase6-plan-review-ds-20260515.md`
- **verdict**: BLOCKED
- **finding count**: 10
- **blocking count**: 4
