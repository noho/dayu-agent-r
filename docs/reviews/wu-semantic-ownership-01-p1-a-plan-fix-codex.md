# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Fix — AgentCodex

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: plan fix
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-review-controller-adjudication.md`
- Fix date: 2026-07-09

## Scope

本次只修 plan artifact，并新增本 plan-fix artifact。未修改生产代码，未修改 tests，未修改 controller adjudication，未提交，未 push。

第一性原理判断：controller accepted findings 成立。现有 plan 的总体 owner boundary 正确，但 Tool Trace display rendering、Read API event class、source note producer、limited-signal 文案 owner、status mapping、initial material 边界和 validation grep 仍不够 code-generation-ready。修复应落在 plan contract / migration checklist / validation，而不是提前实现生产代码。

## Fix Status

### P1A-PLAN-F01：Tool Trace request summary 替代策略

- 状态：已修复。
- 修改位置：
  - `docs/host/wu-semantic-ownership-01-p1-a-plan.md` Section 4：明确选择窄方案，projection helper 拥有 query/status/source/result truth；Tool Trace 只保留 display-only 参数有界渲染、脱敏和展示格式 helper。
  - Section 6 S2：明确 Tool Trace 不再直接回读 request atom 决定 query/status/source，也不保留 `_tool_result_status()` payload fallback chain。
  - Section 8：更新 checklist，区分 projection truth 与 trace 参数摘要。
  - Section 12：补 propagation audit，确认 Tool Trace 参数摘要只是 display-only。
- 未决风险：Tool Trace 参数摘要仍可能需要展示 request 参数；implementation 必须确保该参数视图来自 projection helper 已校验的 display-only 输入，而不是消费者重新拥有 query/status/source 语义。

### P1A-PLAN-F02：Read API PREVIEW vs CANONICAL_FACT 边界

- 状态：已修复。
- 修改位置：
  - Section 4：明确 Read API 迁移到 canonical `TOOL_RESULT_ACCEPTED` projection helper，并要求 `_activity_from_row()` 新增 CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 显式分发；PREVIEW path 和 canonical path 不互相 fallback。
  - Section 4：补 `AcceptedToolResultStatus` 到 `HostActivityStatus` 映射。
  - Section 6 S2：明确 Read API canonical 分发和 PREVIEW path 边界。
  - Section 8 / Section 12：补 checklist 和 propagation audit。
- 未决风险：implementation 若发现 Read API 当前 activity feed 不读取 CANONICAL_FACT row，需要先调整分发边界；不能退回到 PREVIEW `outcome_kind` 冒充 canonical accepted result projection。

### P1A-PLAN-F03：`_readable_source_text_from_refs()` 处理方式

- 状态：已修复。
- 修改位置：
  - Section 6 S1：明确 accepted-result source readable 生产逻辑迁移到 projection helper；`compact_material._readable_source_text_from_refs()` 对 accepted result 的使用必须被 helper 输出替代。
  - Section 6 S2：明确 CompactMaterial accepted evidence block 不再用 `_readable_source_text_from_refs()` 生产 `source_note`。
  - Section 8：补 CompactMaterial checklist。
  - Section 9：validation grep 增加 `_readable_source_text_from_refs` 和 `source_note`。
- 未决风险：`_readable_source_text_from_refs()` 可在 non-accepted initial material 边界保留；re-review 需确认 plan 对允许命中和禁止命中的区分足够清楚。

### P1A-PLAN-F04：Conversation Memory unavailable-query fallback owner

- 状态：已修复。
- 修改位置：
  - Section 4：明确 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 的 owner 迁移到 `accepted_result_projection.py`，作为 query typed limited-signal 的唯一定义。
  - Section 4 / Section 6 S2：明确 Conversation Memory 只消费 projection `query_text` / `query_state`，不得根据缺失字段自行决定 fallback 条件。
  - Section 8：补 Conversation Memory checklist。
- 未决风险：若 implementation 发现旧模块仍需导入该常量，只能从 projection owner 导入，不能保留多个同名真源。

### P1A-PLAN-F05：`AcceptedToolResultStatus` 映射规则与 `_tool_result_status()`

- 状态：已修复。
- 修改位置：
  - Section 4：补 durable signal 到 `AcceptedToolResultStatus` 的映射表，覆盖 `completed`、`failed`、`cancelled`、`governed_error`、`lost`、`unknown`。
  - Section 4：补 status 字段优先级：canonical accepted fields 优先，raw outcome 仅作为同一 helper 内的降级依据。
  - Section 4 / Section 6 S2：明确 `_tool_result_status()` 删除，或只保留为 projection status 的 Tool Trace 展示格式 adapter；不得继续读取 payload 字段推断 status。
  - Section 6 S1 / S3：补 status mapping 测试要求。
- 未决风险：`governed_error` 的具体 durable 字段名需由 implementation 基于现有 payload contract 落实；如果现有 payload 没有明确 governance signal，应在 S1 测试前停止并重新裁决，而不是臆造字段。

### P1A-PLAN-F06：`InitialEvidenceMaterial` / `_evidence_blocks()` 边界

- 状态：已修复。
- 修改位置：
  - Section 5：明确 `InitialEvidenceMaterial` / `_evidence_blocks()` 不是 accepted-result projection owner，本轮不把它们改造成 EventLog accepted result 读取路径。
  - Section 5 / Section 8：说明若测试用 accepted tool result 构造 initial material，输入必须先经 projection helper 派生，不能在 fixture 内手写 accepted query/source 语义。
  - Section 6 S3：补 initial material grep / fixture 审计要求。
- 未决风险：initial material 仍可承载调用方提供的 readable evidence；这不是 P1-A accepted-result projection drift，后续若发现它生产业务事实，再单独立 WU 处理。

### P1A-PLAN-F07：validation scans

- 状态：已修复。
- 修改位置：
  - Section 9：validation grep 增加 `_readable_source_text_from_refs`、`source_note`、`tool_call_request_atoms`。
  - Section 9：明确 helper 内部允许命中 `tool_call_request_atoms`，消费者禁止 request atom back-query；允许 non-accepted initial material 边界命中 source helper，禁止 accepted-result source note producer。
- 未决风险：grep 是结构性验证，不能替代 focused tests；implementation 仍必须用 cross-consumer equivalence tests 证明同一 accepted result 在 Trace / Memory / RunInput / CompactMaterial 中语义一致。

## Residual Risks

- Plan 仍选择不改变 durable schema；如果 implementation 发现必须新增 payload 字段或 version，应触发 plan 的 stop condition，先更新 design truth。
- Source refs 当前生产路径多数为空；P1-A 只能关闭 no-leak 和 projection ownership，不能承诺业务 source 丰富度。
- Tool Trace result details 和参数摘要仍有 display-level bounded rendering；这类截断不得反向改变 projection truth。

## Validation

- 已执行：`git diff --check`
- 结果：通过。
