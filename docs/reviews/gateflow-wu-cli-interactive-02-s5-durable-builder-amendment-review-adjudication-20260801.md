# WU-CLI-INTERACTIVE-02 S5/F13 Durable Builder Amendment Review Adjudication

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：第二次 S5 accepted-plan premise amendment / review adjudication
- Base HEAD：`ec9342ed9e5584123618f6b5c5eba8e93e2aed94`
- Proposal：`docs/reviews/wu-cli-interactive-02-s5-f13-durable-builder-plan-amendment-proposal-codex.md`
- MiMo review：`docs/reviews/plan-review-20260801-221922.md`
- AgentDS review：`docs/reviews/planreview-20260801-222140.md`
- Controller conclusion：`accepted findings require plan fix and dual re-review`
- Next gate：AgentCodex plan fix → MiMo/DS simultaneous independent re-review

## 1. Controller direct evidence

Controller 亲自复核两个 strict builder 的 test call inventory：

- `build_context_compacted_payload(...)`：8 calls / 6 files；
- `build_context_compaction_attempt_rejected_payload(...)`：7 calls / 4 files；
- union：8 files；
- 原 S5 boundary 已允许 3 files，新增 allowed-file delta 精确为 5 files；
- 第一 amendment 的 25-file closure 与这 5 files 无重叠，总枚举 union 为 30 files。

两个 production builder 当前尚未接收 `successful_response_identity`，因为 S5 implementation 尚未执行。F13 实现必须先在 `dayu/host/context_events.py` owner 中把该参数设为 required，再机械迁移全部 8 files / 15 calls；5 files 只表示新放行的文件，不表示完整迁移范围。

## 2. Semantic adjudication

Durable event fixture 是否需要 identity，必须由该 event 自身的业务语义决定，而不是由测试是否真的运行 Engine 决定：

- `CONTEXT_COMPACTED` 表示成功 compact，`successful_response_identity` 必须是 mapping；
- rejected attempt 若 failure category 表示成功 response 后的 parse/schema/semantic/quality/budget rejection，必须是 mapping；
- transport/timeout/cancel/Engine failed 等未得到 successful final 的 rejected attempt 才是 `null`；
- `tests/host/test_proactive_compaction_operation.py::_rejected_payload()` 当前使用 `failure_category="quality_check_rejected"`，因此即使其外层测试关注 orphan/incomplete/exhausted projection，该 rejected event fixture 仍必须提供 mapping，不能填 `null`。

当 contract/projection/material/run-input 测试本身不运行真实 Engine 时，正确做法是在该 file-local fixture owner 中构造 deterministic、非敏感、typed `SuccessfulRunnerResponseIdentity`，并与同一 payload 的 run/operation/attempt/manifest sibling fields 保持一致。它只是 strict event contract fixture，不是 provider continuity evidence；不得使用全局万能 identity、相邻事件 identity、manifest/config 反推或 loose dict patch。

## 3. Finding adjudication

| Review item | Decision | Required action / reason |
|---|---|---|
| MiMo-001 | `accepted-medium-clarification` | Plan/proposal 必须明确 production builder required signature 先由 `context_events.py` owner 扩展，随后全部 8 files / 15 calls 机械迁移；5-file delta 只表示 allowed-file delta。 |
| MiMo-002 | `accepted-concern / rejected-null-conclusion` | 接受逐 failure category 冻结 mapping/null 的要求；拒绝“proactive 三场景均填 null”，因为其 event category 是 `quality_check_rejected`，语义上已有 successful response，应填安全 typed mapping。 |
| DS finding 2 | `accepted-medium-with-owner-correction` | 接受缺少 runtime identity fixture 需在 plan 前置收敛；按 event semantic 允许 file-local deterministic typed identity。Accepted compact 与 post-success rejection 不得因测试未跑 Engine 而写 null。 |
| DS finding 1 | `rejected-historical-trace` | §16 的 `planned-new` 是 accepted original plan gate 当时的 path-inventory validation trace，不是当前工作树声明；改写会破坏 durable history，且不会影响本 amendment 已明确“文件当前存在”。 |

## 4. Scope and residual risk

- Fix 只修改目标 plan 与第二 amendment proposal，不新增 production/test allowed files。
- 5-file delta、30-file total、Engine/Host owner、F13 required schema、no compatibility 与 G06/行为项 29 外部证据边界均不变。
- Implementation pytest/pyright/coverage 仍未运行，由修订获批后的 S5 gate 执行。
- 未分类 residual risk：无；accepted clarity findings 修复后必须双路 re-review。

## 5. Gate decision

当前不得恢复 S5 implementation。AgentCodex 完成上述 owner/15-call/mapping-null/file-local fixture 规则修订后，MiMo 与 AgentDS 必须同时独立 re-review；两路通过、controller 最终复核并创建第二 accepted plan-amendment commit 后，才恢复 S5。

## 6. First re-review finding adjudication

MiMo 与 AgentDS 完成 accepted-finding fix 后的第一轮双路 re-review，核心结论均为通过；Controller 对附带低风险 finding 裁决如下：

| Review item | Decision | Required action |
|---|---|---|
| MiMo re-review finding 001 | `accepted-low` | Proposal §6 中已由当前 amendment 冻结规则关闭的风险分类改为 `fixed in current amendment`，避免误称仍待后续 slice 决策。 |
| MiMo re-review finding 002 | `accepted-low` | 明确 proactive projection 中 orphan、incomplete、exhausted 三个调用都构造同一 `failure_category="quality_check_rejected"` event，按 event semantic 均提供 mapping。 |
| AgentDS re-review finding 001 | `accepted-low-with-strategy` | 对无 run context 的测试 helper，禁止内部默认值、硬编码共享 singleton 或跨文件万能 helper。每个文件可定义 private typed fixture factory，由 caller 传入显式 case/operation/attempt label 并生成该 event 唯一 identity，再以 required 参数传给 payload helper。已有 manifest/compactor engine run 的场景必须显式传入对应 run id，不能从 manifest 反推。 |

该策略仍是 test fixture mechanical migration：不改变业务场景/断言，不新增 production owner，不把 test identity 伪装成 provider evidence。上述三项修复后再次执行 MiMo/AgentDS simultaneous independent re-review；两路 clean pass 前不得提交 amendment 或恢复 S5。

## 7. Final dual re-review finding adjudication

第二轮修复后的 MiMo 与 AgentDS 独立 re-review 均确认 amendment 的 inventory、owner-first 顺序、mapping/null 语义和禁止 compatibility/inference 的边界成立。Controller 对附带低风险意见裁决如下：

| Review item | Decision | Required action / reason |
|---|---|---|
| MiMo final finding 001 | `rejected-duplicate-inventory` | Plan §9.1 已完整列出第一 amendment 的 25-file closure，本次 builder inventory 又完整列出 8 files 并明确 3 个既有文件与 5-file delta；§10.5 还要求重跑去重 inventory。再复制第三份 30-file 清单会增加文档漂移源，不提升可执行性。 |
| MiMo final finding 002 | `rejected-already-covered` | File-local factory 的 event uniqueness、sibling consistency、required argument、无 default/共享 singleton/反推均已由 §9.1、§10.5、§13 的 focused assertions 和后续 code review gate 约束；一般“依赖实施纪律”不是尚缺的 plan action。 |
| AgentDS final finding 001 | `accepted-low-clarification` | 当前文字把输入名写死为 `case_label`、`operation_label`、`attempt_label`，但部分 helper 只有 `operation_id`。修订为：caller 使用当前 helper/call site 实际已有的显式、非敏感、足以区分 event 的上下文（例如 case label、`operation_id`、attempt/run id 或显式 ordinal）；不要求虚构不存在的维度，仍须生成 event-unique identity 并保持 sibling 语义一致。 |

本次 accepted finding 仅修正 plan/proposal 的可实施性措辞，不改变 test allowed-file boundary、生产 contract、identity 语义、mapping/null 分类或验证要求。AgentCodex 修复后仍须由 MiMo 与 AgentDS 同时独立 re-review；两路均无新增 actionable finding 后，Controller 才可创建 accepted amendment commit 并恢复 S5 implementation。
