# PR 190 Compactor 输出业务语义 plan-review acceptance

## Gate metadata

- Gate：`plan review / fix / re-review acceptance`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Branch：`codex/interactive-oracle`
- Reviewed plan：`docs/gateflow/pr-190-compactor-output-business-semantics-plan-20260803.md`
- Decision：`pass`
- Completion status：`plan-review-pass`
- Current gate after this artifact：`accepted plan commit`
- Next entry point：创建 accepted plan commit；checkpoint 完成后自动进入单一 implementation slice，并在无 Gateflow stop condition 时继续推进
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-plan-review-acceptance-20260803-215810.md`

## Scope

本 acceptance 只收口当前 work unit 的 plan review / fix / re-review loop，记录全部 review evidence、controller 裁决、冻结 contract 与 accepted-plan checkpoint 边界。它不修改 plan、生产代码、测试、README、design、manifest、hash、frozen oracle/scenario 或任何 review artifact，也不执行 stage、commit 或 push。

## Review artifacts

以下 review artifacts 已全部读取并纳入本 gate decision：

| Artifact | Role / result | SHA-256 |
|---|---|---|
| `docs/reviews/pr-190-review-20260803-203709.md` | PR follow-up code review；识别当前 Compactor 输出字段/drop reason 的 residual LLM-facing finding | `e7add55e6c95c783ca8d92c8f8d15b223836851e70cfd73a902f15207d0d9841` |
| `docs/reviews/plan-review-20260803-212134.md` | 初始 plan review；指出并冻结 `session_summary:null`、previous evidence support 与 `policy_limit` cap 可见来源纠正 | `1d592ae41f6ed42b8b0c2e30fe37ebfa96751347859d2b0bf8ddb07aad46ae02` |
| `docs/reviews/plan-review-20260803-214309.md` | AgentMiMo plan review；无 material finding，结论 `pass` | `3211dcb0d3752720f55bacac8f144518229eef4d237077fd4363ccadb410442e` |
| `docs/reviews/plan-review-20260803-214733.md` | AgentDS adversarial plan review；提出 F01/F02，交由 controller 裁决 | `42d5970a2dbb54fb3d2090c9e66f16dd2988623bd8da6155308af220b03a3ab9` |
| `docs/reviews/plan-review-20260803-215317.md` | plan-review-fix 后第一路 re-review；无 material finding，结论 `pass` | `b713b45476a31d1bb986b7ca9678a0c0ba61ef4fc839a2a55cbe8a9a502918b6` |
| `docs/reviews/plan-review-20260803-215546.md` | plan-review-fix 后第二路独立 re-review；无 material finding，结论 `pass` | `bf7f15e0e98ec371324cfc1832745a1ffaceaf5d798e30e64b31dfd54bd4ddbe` |

Reviewed plan 的当前 SHA-256 为 `23b8951e787cecbee520490988a7e69c229c7426249ac9796379e917bf11510a`。

## Controller adjudication and finding status

- AgentMiMo：无 finding；plan review pass。
- AgentDS F01（`forward_intents.status` / `reference_continuity.reason` 的 LLM-facing 业务语义仍不完整）：`deferred-with-owner`。Owner 为后续独立 LLM-facing schema work unit；当前 work unit 不扩 scope，也不在下游加 fallback 或兼容解释。
- AgentDS F02（hash 更新步骤需额外 encoding 流程）：`rejected-with-reason`。`sha256sum` 与 publication test 都读取最终 raw bytes；任何保存后的 byte drift 都会被 exact digest assertion fail closed，无需新增脚本、encoding 规则或流程。
- Controller 指出的 Gateflow 元数据错误已修正：plan 不再声称只停在 plan gate；re-review 通过后进入 accepted plan commit，随后按 Gateflow 自动推进。Accepted checkpoint 只处理本 gate intended artifacts，implementation slice 在 code review 接受前不 stage/commit/push。
- 两路 re-review 均确认上述裁决记录、Gateflow 自动推进/checkpoint 权限、冻结业务语义与 scope 无漂移，结论均为 `pass`。

不存在 `accepted` 后仍未修复的 finding，不存在 `needs-more-evidence` finding。唯一 deferred finding 已有明确 later-work-unit owner；rejected finding 已记录直接理由。

## Frozen semantics

Implementation 必须严格执行 reviewed plan 中已接受的 LLM-facing 业务语义，不得在实现时重新设计或弱化：

- `session_summary`：说明整体任务背景、进展、状态与约束；`text` 只概括 cited source；`source_labels` 是直接来源标签。
- `session_summary: null`：本次完整 replacement 不包含 summary；candidate 被接受后当前摘要变为空，包括清除既有摘要，不影响同一 candidate 中其它四类业务语义项。
- `evidence_facts.claim`：必须由 `support_labels` 对应的 accepted `evidence_material` 或 `previous_evidence_fact` 直接支持。
- `evidence_facts.context_labels`：只补充背景、限定或既有回答上下文，不能直接支持 claim，也不能弥补 support 不足。
- `answer_anchors`：只整理既有回答、判断或结论；`title` 标识主题，`detail` 保留结论及必要边界/不确定性，`source_labels` 只引用 `answer_material` 或 `previous_answer_anchor`。
- `superseded`：旧 source 已被更新、更完整或更权威的内容替代，继续保留会过时、冲突或误导。
- `redundant`：source 仍有效，但必要信息已完整表达，丢弃不损失独立业务信息；不能用于掩盖冲突或遗漏。
- `out_of_scope`：source 与当前输入、会话任务及可预见后续无关；不能因难分类、冲突或依据不足而使用。
- `policy_limit`：source 仍相关且原本应保留，但当前 repair feedback 明示具体 cap，并且为让完整 replacement 落入该 cap 必须舍弃；首次请求、无 repair feedback 或无具体 cap 时禁止猜测或使用，也不得用于隐藏冲突、无依据内容或分类困难。

四种 drop reason 是对 source 实际业务关系的互斥解释，不实现脆弱的固定优先级状态机。

## Frozen owner and contract boundary

- 唯一 LLM-facing 语义 owner：`dayu/config/prompts/scenes/conversation_compaction_user.md`。
- `dayu/host/compaction.py` 的 typed shape、enum 与 strict parser 不变。
- `dayu/host/context_governance.py` 的 accept/reject barrier、coverage、policy cap 与 repair feedback 生成不变。
- `dayu/host/memory.py` 的 accepted candidate 完整 replacement 投影不变。
- `docs/cli_init_workspace_manifest_v1.json` 与 `FROZEN_MANIFEST_SHA256` 只承载最终 prompt bytes 的派生 publication truth，不拥有业务语义。
- 不新增 public interface、schema 字段、enum、状态机、semantic verifier、fallback、loose parsing、默认值或兼容分支。

## Frozen implementation scope

当前 work unit 只有一个 implementation slice。允许的实现文件严格为：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_public_compact_smoke.py`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
- 后续 implementation/review gate 按 Gateflow 新建的 durable artifacts

明确不修改：Host typed contract、Context Governance、Memory projection、system prompt、scene manifest、execution profile、README、design、现有 review artifacts、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 与 `docs/cli_ci.md`。Readiness refresh、real-provider conformance，以及 `forward_intents.status` / `reference_continuity.reason` 语义补充均属于后续独立 work unit。

## Accepted plan gate intended files

Accepted plan commit checkpoint 只允许 stage/commit/push 以下 intended files，不得包含 implementation 文件或其它 dirty files：

- `docs/gateflow/pr-190-compactor-output-business-semantics-plan-20260803.md`
- `docs/gateflow/pr-190-compactor-output-business-semantics-plan-review-acceptance-20260803-215810.md`
- `docs/reviews/pr-190-review-20260803-203709.md`
- `docs/reviews/plan-review-20260803-212134.md`
- `docs/reviews/plan-review-20260803-214309.md`
- `docs/reviews/plan-review-20260803-214733.md`
- `docs/reviews/plan-review-20260803-215317.md`
- `docs/reviews/plan-review-20260803-215546.md`

Checkpoint 前必须重新检查 branch 与 `git status --short`，逐项 stage 上述显式路径并核对 staged diff。该 checkpoint 的 commit message 应为：

```text
gateflow: accept plan for compactor output business semantics
```

## Validation and docs decision

- 两份 re-review artifact 均明确为 `pass`，没有 material finding 或 blocking open question。
- 所有 review artifact 与 reviewed plan 的 SHA-256 已在创建本 artifact 前从实际 raw bytes 计算并记录。
- 本次 acceptance 只新增 Markdown gate artifact，不改代码、测试或 LLM-facing 文本，因此不运行 pytest/pyright，也不触发 README/design 更新。
- `git status --short` 用于确认现有 dirty set；本 gate 未 stage、commit 或 push。
- 创建后必须确认只有本 acceptance artifact 是本次新增文件，且原 review artifacts 内容未被修改。

## Residual risks and uncovered areas

- `assigned to later work unit`：`forward_intents.status` 与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。
- `assigned to later work unit`：真实 provider 对字段分类、drop reason 与 repair cap 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head readiness refresh；owner 为独立 readiness refresh work unit。
- AgentDS F02 已 `rejected-with-reason`，不是 residual risk。

所有 residual risk 均已分类并有 owner；无未分类 residual risk，无 blocking open question。

## Acceptance decision

`pass`

Plan artifact、全部 review artifacts、controller finding 裁决、两路 re-review pass、冻结语义、owner、scope、tests/hash/docs decision 与 residual-risk ownership 均完整。Plan review loop 已关闭，下一未完成 gate 是 `accepted plan commit`；该 checkpoint 完成后自动进入 approved single implementation slice。
