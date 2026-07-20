# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift plan correction Controller validation

## 1. Verdict

`PASS / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。

本 validation 只接受既有 umbrella WU 内 R08 的 corrected plan 进入双路完整 plan review，不授权
implementation、测试、coverage、code review、aggregate deepreview、commit、push 或 PR。

## 2. Validated artifacts

| 项目 | Controller 复核值 |
|---|---|
| final plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| final plan SHA-256 | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` |
| AgentCodex artifact | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-codex.md` |
| AgentCodex artifact SHA-256 | `f71e1794327e7296e183e813c4a64e7cbbfbaaff69b801a2ca8f2638d0520354` |
| correction-before accepted plan commit | `261df95f54dbb8cece3919b898dc26ebe1582141` |
| correction-before plan SHA-256 | `115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401` |

Controller first pass caught two current-lineage wording defects before review：顶部 commit 仍指向较早
candidate-exhaustion plan，而 SHA 指向后一代 accepted plan；README 段落仍把已实施的 candidate 6
描述成未来 implementation。AgentCodex 在同一 task follow-up 中只修正这两处，并同步 final SHA；
复核后 commit/SHA 已同代，active continuation 时态正确。

## 3. Accepted finding closure

`R08-CR-PCF04` 已完整进入 plan：

1. Active prefix-six expected/result/checker 精确为
   `391/485 = 80.61855670% >= 80.00%`，checker 要求 `covered == 391` 与
   `statements == 485`。
2. Direct fresh JSON evidence 明确新增 executed lines `[344,346,348,442]`；前三行是
   material/other/CN FY 分类，第 442 行是 `form_type=None` 经 public owner normalization 的
   `return None`。
3. Candidate 6 import/test/三断言被声明为已存在且 immutable；不回退、不再次实现、不新增第七项。
4. Re-entry locks 已更新为 candidate 6 后的 cumulative diff 与 guards hash。
5. Fresh prefix-five `391 passed / 387/485<80` 及 JSON SHA 被保留为同一 implementation task 在
   mutation 前生成的 predecessor evidence；计划禁止回退 candidate 6 重跑该 proof。
6. Continuation 只 fresh erase 重跑同一八文件、零 deselect prefix-six，预期 `392 passed` 与
   exact `391/485>=80`；通过后从零完成原 §6.6/§6.7 全矩阵。
7. Numerator、denominator、threshold、hash、test、smoke、pyright、Ruff、scan 与 no-touch drift
   全部 fail closed。

旧 `390/485`、“candidate 6 尚不存在、先 prefix-five 再新增 candidate 6”等文本只出现在明确
superseded 的自检说明，不构成 active instruction。

## 4. Protected tree validation

| Lock | Controller 复核值 |
|---|---|
| cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| `read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged tree | empty |
| `git diff --check` | PASS |

本 gate authored delta 只有最终 plan 与 AgentCodex correction artifact；product、tests、README、control、
design、prior reviews、S1/S2 artifacts 均保持受保护状态。计划保留 Topic 8-9 no-code、安全机制、R07
no-touch、Issues 142/151/175/177/178、R09-R12 与统一 authorization 的边界。

## 5. Next gate

只授权 AgentMiMo 与 AgentDS 对完整 final plan `bbbaeee...1cdd` 做并发、独立、完整 plan review。
Reviewer 必须检查全部计划而非只看 patch，并独立匹配 current locks。Reviewer verdict 不独立授权
implementation；任何 accepted finding 必须由 AgentCodex 修复并完成双路 re-review。无 accepted finding
时，仍须 Controller adjudication、exact-scope accepted local plan commit 与单独 implementation
authorization 后才能继续。
