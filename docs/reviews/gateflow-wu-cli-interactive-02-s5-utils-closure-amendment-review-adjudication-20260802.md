# WU-CLI-INTERACTIVE-02 S5/F13 Utils Closure Amendment Review Adjudication

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：第三次 S5/F13 accepted-plan premise amendment / initial review adjudication
- Base HEAD：`e7f578dc7bdfafb51a859be2db584300e08f81fb`
- Proposal：`docs/reviews/wu-cli-interactive-02-s5-f13-utils-closure-plan-amendment-proposal-codex.md`
- MiMo review：`docs/reviews/plan-review-20260802-000526.md`
- AgentDS review：`docs/reviews/plan-review-20260802-000107.md`
- Controller conclusion：`accepted arithmetic finding requires plan fix and dual re-review`
- Next gate：AgentCodex plan fix → MiMo/AgentDS simultaneous independent re-review

## 1. Controller direct evidence

Controller 亲自复核 accepted HEAD 与当前未修改的两个 utils：

- `utils/smoke_host_public_awaiting_entrypoint.py`：`FinalAnswerData(...)` 1 call；
- `utils/smoke_host_public_conversation_memory_scenarios.py`：`FinalAnswerData(...)` 1 call、`EngineRunOutcomeFinalAnswer(...)` 2 calls；
- utils 中没有 `ContextCompactor` typed-return hit；
- tests+utils identity/typed-return closure：FA 37 calls / 21 files、OA 6 calls / 4 files、CR 7 files、union 27；
- strict durable builder closure：accepted 8 calls / 6 files、rejected 7 calls / 4 files、union 8；
- 27-file identity closure 与 8-file builder closure 的交集精确为 2 files：`tests/host/test_compaction_operation.py` 与 `tests/host/test_dispatch_scheduler.py`；
- `tests/host/test_context_compact_events.py` 虽然在第二 amendment 前已经属于 S5 allowed owner tests，但它没有 FA/OA/CR hit，因此不在 27-file identity closure 中。

Controller 对五类 mechanical pattern 做单次去重搜索，结果为 33 files。正确集合运算是
`27 + 8 - 2 = 33`，不是 `27 + 5 = 32`。

## 2. Finding adjudication

| Review item | Decision | Required action / reason |
|---|---|---|
| MiMo finding 001 | `accepted-medium-with-terminology-correction` | 接受 total union 算术错误；目标 plan/proposal 的 active implementation/validation/checklist/residual-risk wording 必须把总 union 改为 33，并明确 27/8/intersection 2。保留“5-file allowed-file delta”这一正确边界术语；不得把它改称 6-file allowed delta。相对 27-file identity closure 的 builder-only set difference 是 6 files，其中 `test_context_compact_events.py` 已获 S5 owner-test 授权，另外 5 files 才是第二 amendment 新增 allowed-file delta。 |
| AgentDS A5 / final pass | `rejected-set-arithmetic` | Review 把“新增 allowed-file delta 5”误当成“builder closure 相对 identity closure 的完整差集”。它没有验证实际交集，故 `27 + 5 = 32` 结论不成立。其它关于 2-file/4-call、owner、identity source、cardinality、UNAVAILABLE、scope 与 validation 的直接证据接受。 |

## 3. Required plan/proposal fix

AgentCodex 只修改目标 plan 与本次 proposal：

1. 所有 active total-union completion signal 从 32 改为 33，公式统一为 `27 identity/typed-return + 8 builder - 2 overlap = 33`。
2. 同时保留并区分三种集合事实：第二 amendment 新增 allowed-file delta 为 5；builder closure 相对 27-file identity closure 的 set difference 为 6；完整 mechanical union 为 33。
3. 显式列出 2-file overlap 与额外 builder-only `test_context_compact_events.py`，防止 implementation/post-inventory 再次误判。
4. §10.5 的 pre/post inventory 要求必须用完整五类 pattern 去重验证 33，而不能只把两个 delta 数字相加。
5. §15 追加本轮 accepted finding/fix trace；历史 review artifacts 保持不变，不把 AgentDS 的错误 pass 结论当作 acceptance。

Fix 不改变两个 utils 的 exact 2-file/4-call allowed delta、identity 字段来源、smoke 行为、production/test allowed files、builder 5-file allowed delta或 F13 业务语义。

## 4. Scope and residual risk

- 当前 20-file implementation dirty set 继续由既有 S5 implementation owner 持有；本 gate 不修改、revert、stage 或格式化它们。
- 本 fix 只允许修改目标 plan 与 utils-closure proposal；不得修改两个 utils 或其它代码。
- Amendment review 阶段不运行 implementation pytest/pyright/coverage/smoke；后续获准 implementation 承接。
- 未分类 residual risk：无；accepted arithmetic finding 修复后必须双路独立 re-review。

## 5. Gate decision

当前不得恢复 S5 implementation，也不得创建第三次 accepted amendment commit。AgentCodex 完成 33-file union 与集合术语修订后，MiMo 与 AgentDS 必须同时独立 re-review；两路无新增 actionable finding、Controller 最终复核并创建 accepted amendment commit 后，才恢复 implementation。
