# Host Phase 6 Plan Review Controller Adjudication - 2026-05-15

## 结论

Controller 裁决：Phase 6 plan review gate **未通过**，进入 plan fix gate。

AgentMiMo verdict 为 PASS with findings，blocking count 为 0。AgentDS verdict 为 BLOCKED，blocking count 为 4。Controller
接受 DS-F1 至 DS-F4 为 blocking findings：当前 plan 目标态正确，但未充分覆盖 Phase 5 no-tool 硬编码到 Phase 6
tool-enabled 路径的拆解，因此 implementation agent 会被迫自行选择工具启用机制与 EngineEvent 工具事件降级方式。

## Accepted Blocking Findings

### DS-F1 accepted - PolicySnapshot 与 no-tool 硬约束未拆解

裁决：接受，blocking。

理由：`PolicySnapshot.__post_init__` 和 `_validate_no_tool_snapshot` 当前明确拒绝 tool-enabled RunInputBuilder。Plan 若不指明拆解方式，P6-S1 无法实施。

Plan fix 要求：
- 明确 `PolicySnapshot` 只校验 policy ref，不再无条件拒绝 `allow_tool_calls=True`。
- 明确 no-tool 校验只在 replay / no-tool scope 执行；tool-enabled scope 使用独立校验。
- 增加 tool-enabled policy snapshot / RunInputBuilder 测试。

### DS-F2 accepted - DefaultSceneParameterProvider 硬编码 tools=disabled

裁决：接受，blocking。

理由：tool-enabled Attempt 若仍在 system message 写 `tools=disabled`，会直接误导模型，且与 P6 目标相冲突。

Plan fix 要求：
- 明确 scene provider 依据 tool snapshot / policy snapshot 输出工具状态。
- 增加工具启用场景不包含 `tools=disabled` 的测试；no-tool / replay 场景仍应表达 no-tool。

### DS-F3 accepted - RunInputBuilder 工具启用 / 禁用决策机制缺失

裁决：接受，blocking。

理由：设计要求 replay no-tool 主防线在 RunInputBuilder。Plan 必须说明 dispatch / builder 如何选择 tool-enabled 与 no-tool provider，而不是让 implementation agent 自行推断。

Plan fix 要求：
- 固定 P6 第一版机制：在 Host dispatch / RunInputBuilder construction 边界显式传入 `ToolExecutionMode` 或等价 typed enum。
- `ToolExecutionMode.TOOL_ENABLED` 用于普通 initial / queue promotion / resume 等允许工具的 Attempt；`ToolExecutionMode.NO_TOOL_REPLAY` 用于 replay；需要 no-tool fake path 时用 `ToolExecutionMode.NO_TOOL_DISABLED`。
- 若需要把该模式加入 `AttemptDispatchSnapshot`，必须明确这是 Host public/internal typed contract change，并补测试。

### DS-F4 accepted - EngineEvent 工具事件映射变更未细化

裁决：接受，blocking。

理由：当前 `engine_ingest.py` 已把工具类 EngineEvent 作为 preview 识别，但 plan 未明确 P6 要保持 / 强化该映射，容易让 implementation agent 误把 EngineEvent 工具事实升级为 canonical。

Plan fix 要求：
- 明确 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE` 等 EngineEvent 工具事件必须保持 preview / diagnostic，不成为 canonical tool fact。
- ToolRuntime accept path 是唯一 canonical owner。
- 增加 EngineEvent 工具事件不追加 canonical tool fact 的测试。

## Accepted Non-blocking Findings For Plan Fix

- MIMO-F1 / DS open question 1 accepted：EventLog `append_event` 当前不做 global event_type closed set 验证；plan 应写明 P6 新增 `TOOL_*` event type 通常无需 schema version bump，除非实现中另有 payload validator 需要注册。
- MIMO-F2 / DS-F9 accepted：补充 batch partial accept failure 测试。
- MIMO-F3 accepted：明确 `ToolAwaitingOutcome` 在 P6 映射为 `ToolFailedOutcome` + `governed_error` policy decision；`unsupported_awaiting` 只可作为 policy reason，不进入 canonical `ToolFactKind`。
- DS-F5 accepted：收窄测试迁移范围，优先新增 Phase 6 integration tests，不改或少改 Phase 5 no-tool tests。
- DS-F6 accepted：明确 `TruncationManager` 从 `EffectiveToolBundle.truncate_specs_by_name` 获得业务 `ToolTruncateSpec`。
- DS-F7 accepted：明确 P6-S3 使用 `PassThroughDuplicateGovernance` always-allow stub，P6-S5 替换完整 matrix。
- DS-F8 accepted：补 candidate 按 `ToolFactKind` 的必填字段与 `__post_init__` 校验要求。
- DS-F10 accepted：明确 duplicate key 不包含 `index_in_iteration`；同 iteration 相同工具和相同 normalized args 仍进入 duplicate governance，由 policy 决定 allow / reuse / hint。

## Rejected Or No-fix Findings

- MIMO-F4 rejected as no-fix：计划从 4 个建议 slice 细化为 6 个 slice 是合理分解，不需要修复；可在 plan fix 中补一句偏离理由。

## Plan Fix Gate

下一步派发 plan fix，仅允许修改：

- `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`

不得修改设计真源、总控文档、代码、测试或 README。Plan fix 完成后进入 MiMo / DS plan re-review。

