# WU-TOOL-02 Plan Review Controller Adjudication

## 范围

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- Gate: plan review adjudication
- Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Reviews:
  - `docs/reviews/wu-tool-02-plan-review-mimo-20260602.md`
  - `docs/reviews/wu-tool-02-plan-review-ds-20260602.md`

## 总控结论

Plan 整体方向成立，但需要一次 plan fix 后再进入 plan re-review。核心原因是 DS Finding 01 指出 Slice 1 / Slice 2 在同一 `dayu/host/tool_runtime.py` 内存在中间态类型失败风险；这会破坏 gateflow 要求的每个 slice 可独立验证闭环。

基于 `docs/host/design.md` 的设计目标和第一性原理，ToolRuntime accept candidate 清理必须保持 Host accept barrier 与 EventLog 语义不变，同时让 implementation slice 可独立通过类型检查和 focused tests。让 implementation agent 在 Slice 1 遇到已知类型失败再自行重排，是把 planning 缺口后移；当前最佳实践是修正 plan。

## Finding 裁决

| 来源 | Finding | 裁决 | 理由 | Required plan fix |
|---|---|---|---|---|
| AgentDS | 01 Slice 1 与 Slice 2 的 `tool_runtime.py` 同文件修改存在顺序冲突 | accepted | 该 finding 有直接代码依据；组合根变更会让同文件 producer 构造立即类型失败，违反 slice 可独立验证要求。 | 重排或合并 slices。总控倾向：Slice 1 只新增子结构和局部 validation helper，不改变 `ToolFactAcceptCandidate` 顶层；Slice 2 再一次性迁移组合根、producer、accept barrier consumer 和 accept barrier tests，确保 slice 结束 pyright 通过。若 planning agent 选择合并 Slice 1/2，也必须保证新的 slice 有可 review 的闭环。 |
| AgentMiMo | 1 `ToolFactKind.LOST` 校验规则未显式声明 | accepted | 当前 `LOST` 无生产构造路径，但计划应明确保持 unsupported kind fail-fast，避免 implementation agent 误以为需要新增 LOST candidate 语义。 | 在 fact kind 规则或 stop condition 中补充 `ToolFactKind.LOST` 当前不在 `ToolFactAcceptCandidate` 支持范围，validation 继续 fail-fast；未来若需要 LOST candidate 必须另行设计。 |
| AgentMiMo | 2 `ToolAcceptResult` payload_ref/payload_digest 一致性约束措辞与当前代码不完全对齐 | accepted | WU-TOOL-02 不应借结构清理引入新 payload digest 校验语义；plan 必须描述当前行为而非未来增强。 | 调整措辞：`COMPLETED` 保持需要 `payload_digest`；`payload_ref` 存在时保持 descriptor 存在性校验，不新增 payload_ref 与 payload_digest 等值校验，除非已有代码已这样做。 |
| AgentDS | 02 `ToolAcceptDiagnostics` 单字段子结构可能过度分解 | deferred-to-implementation-discretion | 该项是结构品味风险，不是 plan blocker；plan 已允许命名和局部结构按实现微调。 | 在 plan 中保留职责边界要求即可，可补充 implementation agent 可在不破坏职责分组时把单字段 diagnostics 保留为组合根直接字段。 |
| AgentDS | 03 Slice 4 旧字段残留检测 rg 命令存在覆盖盲区 | accepted | grep 只能作为最佳努力；plan 应避免把它当成完整证明。 | 补充 pyright 是主要证明；rg 只是辅助；可增加更宽的字段名搜索并明确允许 EventLog payload 字符串、docstring 和子结构字段。 |
| AgentDS | 04 Validation 分解粒度未明确 | accepted | 子结构内部 invariant 与跨子结构 fact-kind invariant 的边界会影响实现质量和测试覆盖。 | 补充分解原则：子结构 `__post_init__` 只校验本结构内部 invariant；跨子结构约束在组合根 / fact-kind validator 中校验；错误消息和检查顺序可调整但语义不变。 |
| AgentDS | 05 Fact Kind 校验规则章节过细节 | accepted | plan 可保留语义约束，但应明确不是逐行实现模板，避免 implementation agent 被错误消息或检查顺序绑死。 | 补充该章节表达语义约束，implementation 可在保持语义不变时调整 validator 组织、错误消息和检查顺序。 |

## 下一步

进入 plan fix gate，派 planning agent 更新 `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`。Plan fix 完成后，重新派 AgentMiMo / AgentDS 做 plan re-review；re-review 通过后才能创建 accepted plan commit 并进入 implementation gate。
