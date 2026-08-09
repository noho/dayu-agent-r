# WU-CLI-INTERACTIVE-02 S5/F13 Durable Builder Amendment Final Adjudication

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：第二次 S5/F13 accepted-plan premise amendment / final dual re-review adjudication
- Base HEAD：`ec9342ed9e5584123618f6b5c5eba8e93e2aed94`
- Target plan：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- Proposal：`docs/reviews/wu-cli-interactive-02-s5-f13-durable-builder-plan-amendment-proposal-codex.md`
- Controller review adjudication：`docs/reviews/gateflow-wu-cli-interactive-02-s5-durable-builder-amendment-review-adjudication-20260801.md`
- Final MiMo re-review：`docs/reviews/plan-review-20260801-231111.md`
- Final AgentDS re-review：`docs/reviews/plan-review-20260801-231120.md`
- Controller conclusion：`pass`
- Next gate：accepted amendment commit → S5/F13 implementation

## 1. Direct evidence verified by Controller

Controller 亲自复核并接受以下直接证据：

- `build_context_compacted_payload(...)`：8 test calls / 6 files；
- `build_context_compaction_attempt_rejected_payload(...)`：7 test calls / 4 files；
- 两类 union：8 files / 15 calls，其中 3 files 已在既有 S5 boundary，新增 allowed-file delta 精确为 5 files；
- 第一 amendment 的 `FinalAnswerData(...)`、`EngineRunOutcomeFinalAnswer(...)`、`ContextCompactor` typed-return closure 仍为 25 个去重文件；它与 5-file delta 无重叠，总机械 closure 为 30 个去重 test/test-support files；
- 两个 production builder 仍处于 implementation 前状态，尚未包含 `successful_response_identity`；amendment 正确要求先收紧 `dayu.host.context_events` owner signature，再迁移完整 8 files / 15 calls；
- 5 个新增 test files 的现有 helper/call site 均至少拥有 `operation_id`，部分另有 attempt number、run id 或 ordinal，足以构造 deterministic、非敏感、event-unique 的 file-local typed identity，不需要虚构 `case_label` / `attempt_label` 等不存在的维度；
- `test_proactive_compaction_operation.py::_rejected_payload()` 的三个调用均产生 `quality_check_rejected` event，因此三者 identity 都按 post-success event semantic 使用 mapping。

## 2. Final dual re-review adjudication

| Review artifact | Reviewer verdict | Controller decision | Reason |
|---|---|---|---|
| `plan-review-20260801-231111.md` | `pass` | `accepted-pass` | MiMo 独立复现 inventory，逐文件验证 5-file call-site context，并确认 accepted clarification 已在 plan §9.1/§10.5/§13 和 proposal 闭合；无 actionable finding。 |
| `plan-review-20260801-231120.md` | `pass` | `accepted-pass` | AgentDS 独立复现两组 inventory、owner/sequencing/反例与 validation closure；确认无第三份 30-file 清单和新抽象；无 material finding。 |

AgentDS 对 `proposal_failed` fixture 的观察不升级为 finding。冻结计划 §9.3 已规定：identity 的 mapping/null 取决于对应 attempt 是否实际取得 successful Engine final，而不是只看 `failure_category` 字符串；`LLMCompactionProposalError` 在 LENGTH、parse/schema 等成功 final 后失败路径携带同源 identity，transport/timeout/cancel/Engine failed no-final 才为 `None`。因此 implementation 能从 typed proposal result/error 同源决定 identity，不需要新增 enum、兼容分支或 consumer 推断。

## 3. Accepted-finding closure

- Initial review 的 owner-first 8-file/15-call closure、mapping/null 语义与 file-local fixture owner findings 已修复；
- first re-review 的 residual-risk 分类、proactive 三场景 mapping 与 fixture data-flow findings 已修复；
- preceding final dual re-review 的过度写死 label 参数 finding 已修复为使用 call site 实际已有的显式唯一上下文；
- MiMo 提议复制第三份 30-file 清单与一般“依赖实施纪律”的意见经 Controller 拒绝，现有 inventory/validation 与 code-review gates 已覆盖，避免增加文档漂移和无关抽象；
- 最终两路独立 re-review 未产生新的 actionable finding。

Finding 最终状态：全部 accepted findings 已在 plan/proposal 层关闭；无 unresolved、deferred 或未分类 finding。

## 4. Scope, validation and residual risk

- 本 amendment 只修改目标 plan、proposal、review/adjudication artifacts；没有修改 production、tests、README、design、oracle 或 scenario 文件。
- F13 semantic owner、required schema、Engine → Host typed identity flow、5-file allowed delta、30-file closure、mapping/null 分类与 G06/行为项 29 的真实 provider evidence 边界均未改变。
- 文档 whitespace 检查通过；reviewer 与 Controller 的只读 inventory 一致。
- pytest、pyright、coverage、secret scan 与真实 provider smoke 尚未运行，这是 plan gate 的预期状态，已由后续 approved S5/S6 validation gate 明确承接，不是未分类风险。
- 未分类 residual risk：无。

## 5. Gate decision

第二次 S5/F13 durable-builder plan amendment 通过。允许把本 gate 的 plan、proposal、两轮 review chain、Controller adjudication 与本 final adjudication 创建为 accepted amendment commit；commit 后工作树必须干净，随后从该精确 HEAD 恢复 S5/F13 implementation。S5 必须按 amended plan fail closed：先重跑两组 pre-inventory，若出现未允许的新文件 hit 或 closure 不一致，停止 implementation 并退回 Controller，不得用 default、compatibility、manifest/config inference 或范围外修改绕过。
