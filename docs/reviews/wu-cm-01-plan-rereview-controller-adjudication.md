# WU-CM-01 Plan Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | plan re-review adjudication |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-plan-rereview-mimo.md`; `docs/reviews/wu-cm-01-plan-rereview-ds.md` |
| fix artifact | `docs/reviews/wu-cm-01-plan-fix-codex.md` |

## Verdict

Plan re-review gate 通过。AgentMiMo 与 AgentDS 均裁决 `pass`，PF-01 到 PF-06 均为 fixed，0 条 blocking finding，0 条 blocking open question。

## Re-Review Finding Adjudication

| ID | 来源 | 裁决 | 理由 | 后续处理 |
|---|---|---|---|---|
| RR-NF-01 | AgentMiMo NR-01 | rejected-with-reason | `tests/host/test_context_budget.py` 出现在测试矩阵不意味着 `dayu/host/context_budget.py` 必须进入 allowed modification list；当前 plan 已要求若 implementation 发现 allowed files 不足或 contract 需要调整，停止并回到 plan / design 修正。 | 不改 plan；implementation gate 若直接证据证明需要改 `context_budget.py`，由 Controller 扩展 allowed files。 |
| RR-NF-02 | AgentDS NF-01 | rejected-with-reason | Plan 已声明 vNext compact output candidate schema 以 `docs/host/design.md` 24.3 为唯一真源；若 `EvidenceBackedFactCandidate.source_labels` 存在歧义，implementation 应按 design 24.3 的 evidence material label 约束收敛，不需要再修 plan。 | 作为 implementation review 关注点。 |
| RR-NF-03 | AgentDS NF-02 | rejected-with-reason | `ForwardIntentCandidate` 不自动触发工具是 Host 编排 / RunInputBuilder 边界，不是 accept barrier 的可机械校验项；plan 的分层边界已足够防止将其误实现为工具触发。 | 作为 implementation review 关注点。 |

## Residual Risks

以下 residual risks 均已有 owner / destination，不阻塞进入 accepted plan commit：

- 完整 Conversation Memory eval benchmark：WU-CM-10 / GitHub Issue 80。
- Cross-session User Profile Memory：WU-CM-11 / GitHub Issue 115。
- Deep historical recall / semantic search：GitHub Issue 39。
- Provider-specific tokenizer adapter：WU-CTX-01 / GitHub Issue 20。
- Fins fact grounding integration：Fins integration work unit。
- Schema old DB upgrade：explicit non-goal；全新 schema 起库。
- Slice 1-4 中间不可编译状态的跨 slice 类型一致性：implementation gate + Slice 5 pyright + code review gate。
- 禁止通过 compatibility wrapper 维持表面可编译：implementation gate + review gate。

## Next Gate

进入 `accepted plan commit`。提交范围应只包含 WU-CM-01 plan / plan review / plan fix / re-review / controller adjudication artifacts，以及控制文档中的 gate bookkeeping。
