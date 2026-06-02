# WU-TOOL-02 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- Gate: aggregate deepreview
- Review artifacts:
  - `docs/reviews/wu-tool-02-aggregate-deepreview-mimo-20260602.md`
  - `docs/reviews/wu-tool-02-aggregate-deepreview-ds-20260602.md`
- Handoff: `docs/reviews/wu-tool-02-aggregate-deepreview-handoff-20260602.md`
- Approved plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

## Controller Summary

Aggregate deepreview pass。AgentMiMo 与 AgentDS 均给出 `pass-with-nonblocking-notes`，无 blocking finding。两份 review 均确认：

- `ToolFactAcceptCandidate` 已收敛为 Host 内部 typed composition root，未保留旧字段 property facade、wrapper 或 re-export。
- producer -> candidate validation -> accept barrier -> EventLog payload -> ack -> projection consumers 全链路读取新子结构。
- EventLog event type、payload key、event id 派生、accepted evidence envelope、idempotency scope、duplicate governance、reuse、wait、retry、replay、resume、memory、compaction、tool trace 语义保持不变。
- 受影响 Host tests 206 passed，全量 pyright 0 errors；projection consumer tests 121 passed。
- AGENTS.md 的分层边界、类型签名、中文 docstring、README 触发规则和禁止兼容 wrapper 约束未被违反。

## Finding Adjudication

### MiMo Finding 01: ALLOW duplicate governance validation 更严格

- Reviewer severity: Low
- Controller decision: rejected as defect；accepted as nonblocking note only。
- 直接证据：旧实现 `main:dayu/host/tool_runtime.py` 的 `_validate_duplicate_fields` 只在 `candidate.duplicate_decision is None` 时直接返回；一旦 `duplicate_decision` 存在，包括 `DuplicateDecisionKind.ALLOW`，旧实现同样要求 `duplicate_scope` 与 `duplicate_decision_message` 非空。当前实现中 `ToolAcceptDuplicateGovernance` 表示“存在 duplicate governance 记录”，而 `governance.duplicate is None` 表示完全无 duplicate governance 记录。因此 current validator 没有相对旧 ALLOW decision 引入更严格运行时语义。
- 裁决依据：基于 approved plan 的目标，duplicate governance 子结构应表达已有治理记录；保持 scope/message 必填是当前 phase 的最佳实践，避免 ALLOW duplicate record 退化成缺少审计语义的半记录。无需修复。

### MiMo Finding 02 / DS Finding 2: `_tool_result_payload` 中 `else None` 缩进

- Reviewer severity: Low / non-blocking
- Controller decision: rejected as blocking；accepted as style note。
- 裁决依据：该缩进不改变 Python 语义，pyright 与 206 affected tests 均通过。AGENTS.md 禁止低价值 cleanup 稀释 review；当前 gate 不为非行为问题开启 fix loop。无需修复。

### MiMo Finding 03: `ToolFactKind.LOST` fail-fast 无显式测试

- Reviewer severity: Low
- Controller decision: deferred-with-owner to future ToolRuntime fact-kind expansion if needed。
- 裁决依据：approved plan 明确 `LOST` 不在 `ToolFactAcceptCandidate` 支持范围内，当前代码 fail-fast；main 分支也无该路径显式测试，属于 pre-existing coverage gap，不是本 work unit 引入的 correctness regression。若未来要让 ToolRuntime accept candidate 表达 lost tool fact，应另行进入设计与 implementation work unit。

### DS Finding 3: duplicate decision message 双重校验可读性

- Reviewer severity: non-blocking
- Controller decision: rejected as defect；accepted as readability note。
- 裁决依据：`_require_optional_non_empty_text` 负责拦截空字符串，后续 `is None` 负责拦截缺失，语义与旧实现等价。无需在当前 gate 修改。

### DS Finding 4: ALLOW decision 要求 scope/message 非空

- Reviewer severity: non-blocking
- Controller decision: accepted as correct current behavior。
- 裁决依据：与旧 validator 一致；也符合当前 duplicate governance record 必须可审计的设计目标。无需修复。

### DS Residual Notes: 子结构直接单元测试、`raw_tool_outcome is None`、diagnostics wrong-type、测试 helper 重复

- Reviewer severity: non-blocking / residual
- Controller decision: no current action。
- 裁决依据：当前行为由组合根路径、focused tests 和 pyright 共同覆盖；helper 重复为 pre-existing test organization issue。基于最小化满足 WU-TOOL-02 目标，不把当前结构清理扩大成测试工具重构或更细类型建模。

## Final Decision

Aggregate deepreview pass。无 accepted blocking finding，无需 fix / re-review。下一步按用户补充要求，进入 ready-to-open-draft-PR 前的额外 AgentMiMo + AgentDS 并行全仓 review gate。
