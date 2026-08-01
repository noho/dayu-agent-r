# WU-CLI-INTERACTIVE-02 S5/F13 Utils Closure Amendment Final Adjudication

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：第三次 S5/F13 accepted-plan premise amendment / final dual re-review adjudication
- Base HEAD：`e7f578dc7bdfafb51a859be2db584300e08f81fb`
- Target plan：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- Proposal：`docs/reviews/wu-cli-interactive-02-s5-f13-utils-closure-plan-amendment-proposal-codex.md`
- Initial MiMo review：`docs/reviews/plan-review-20260802-000526.md`
- Initial AgentDS review：`docs/reviews/plan-review-20260802-000107.md`
- Controller review adjudication：`docs/reviews/gateflow-wu-cli-interactive-02-s5-utils-closure-amendment-review-adjudication-20260802.md`
- MiMo re-review：`docs/reviews/plan-review-20260802-002254.md`
- AgentDS re-review：`docs/reviews/plan-review-20260802-002027.md`
- Controller conclusion：`pass`
- Next gate：accepted amendment commit → resume S5 implementation

## 1. Controller evidence and arithmetic

Controller 亲自复核并冻结以下集合事实：

- tests+utils identity/typed-return closure：FA 37 calls / 21 files、OA 6 calls / 4 files、CR 7 files，三类 union 27；
- strict durable builder closure：accepted 8 calls / 6 files、rejected 7 calls / 4 files，两类 union 8；
- 两组 closure 的 overlap 精确为 `tests/host/test_compaction_operation.py` 与 `tests/host/test_dispatch_scheduler.py`；
- builder closure 相对 identity closure 的 set difference 为 6 files；其中 `tests/host/test_context_compact_events.py` 在第二 amendment 前已经属于 S5 allowed owner tests，其余 5 files 才是第二 amendment 新增 allowed-file delta；
- 完整 mechanical union 为 `27 + 8 - 2 = 33`。

因此“新增 allowed-file delta 5”与“builder-only set difference 6”是两个不同事实，均保留；任何以 `27 + 5` 计算完整 union 的写法均被拒绝。

## 2. Review and finding adjudication

| Artifact / item | Reviewer result | Controller decision |
|---|---|---|
| Initial MiMo finding 001 | `pass-with-findings` / total union 33≠32 | `accepted-medium-with-terminology-correction`；已修复。 |
| Initial AgentDS A5 / final pass | 误判 total union 32 | `rejected-set-arithmetic`；除该算术结论外，其 2-file/4-call、owner、identity source、cardinality、UNAVAILABLE、scope 与 validation 证据接受。 |
| MiMo re-review | `pass` | `accepted-pass`；独立复现 27/8/2/6/33、5-file allowed delta、完整验证脚本与零 active arithmetic residue。 |
| AgentDS re-review | `pass` | `accepted-pass`；独立纠正前次误判并复现同一集合、call-site 与 validation 证据，无 actionable finding。 |

Accepted arithmetic finding 已在 target plan 的 §9.1、§10.5、§13、§15 与 proposal 中关闭。最终两路 re-review 均无 material finding；无 unresolved、deferred 或未分类 finding。

## 3. Scope and ownership closure

- 第三 amendment 唯一新增 implementation boundary 是两个 utils 文件中的 4 个 required constructors：awaiting smoke `FinalAnswerData` 1 call，conversation-memory smoke `FinalAnswerData` 1 call 与 `EngineRunOutcomeFinalAnswer` 2 calls。
- Identity 只能从当前 synthetic invocation 的 `AgentRunRequest` run/attempt/execution 与 `runner_spec.provider/model` 构造，iteration/call cardinality 显式为 0/1，provider request id 使用 `UNAVAILABLE + None`。
- 两个 utils 只允许 file-local narrow typed helper、必要 import/常量与 required argument 迁移；不得改变 smoke 场景、输出、provider 配置、CLI oracle、artifact/EventLog 断言或异常语义。
- 当前 20-file S5 implementation dirty set 未被本 amendment/review loop 修改；保护 hash 保持 `d19605477fe3c284e5791f8c8bdfb8272bfaac8bbd1876d7d4518c7eff8beeb9`。
- 两个 utils 在本 gate 保持 clean；不得把 synthetic smoke identity 当作行为项 29/G06 的真实 provider evidence。

## 4. Validation and residual risk

- Plan/proposal whitespace 检查通过；active `32` / `27+5` total-union 残留为零。
- 五类 pattern 去重验证可执行并复现 identity 27、builder 8、overlap 2、builder-only 6、mechanical union 33。
- Amendment gate 按授权未运行 implementation pytest、pyright、coverage 或 smoke；获准恢复后的 S5 必须运行 full pyright、pre/post inventory、三条既有 utils smoke 与既有 S5 全部 validation。
- Utils 按项目规则不新增测试且不计覆盖率；该豁免不免除 pyright、inventory、smoke 与 code review。
- 未分类 residual risk：无。

## 5. Gate decision

第三次 S5/F13 utils closure plan amendment 通过。允许只 stage/commit target plan、proposal、initial reviews、Controller adjudication、dual re-reviews 与本 final adjudication；不得把当前 20-file implementation dirty set纳入 amendment commit。Commit 后从新的精确 HEAD 恢复 S5 implementation，先重跑 33-file pre-inventory；若任何 file/call/typed-return hit 不匹配，继续 fail closed，不得用 default、compatibility、scope drift 或下游推断绕过。
