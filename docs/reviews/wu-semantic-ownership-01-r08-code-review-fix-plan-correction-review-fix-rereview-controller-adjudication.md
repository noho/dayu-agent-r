# WU-SEMANTIC-OWNERSHIP-01 R08 Corrected-Plan Re-Review Controller Adjudication

## 1. Verdict

**PASS / CORRECTED PLAN ACCEPTED / READY FOR EXACT-SCOPE LOCAL PLAN COMMIT**

本 gate 仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R08 remediation continuation，不是新 WU、feature、issue 或独立 sub-WU。两路 reviewer 均对完整 final plan 执行 re-review，而不是只看 `R08-CR-PCPR-F01` delta。

## 2. Immutable evidence

| 证据 | Controller 独立值 |
|---|---|
| final corrected plan SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` |
| protected `dayu/fins + tests` binary diff SHA-256 | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` |
| AgentMiMo re-review artifact SHA-256 | `47e05b35e685a997bff62af3053fd485b6c25575e3bddc9631c3bd91f3d237dd` |
| AgentDS re-review artifact SHA-256 | `26279c847bb76b27bfe3d65fb14b1949c9020c7d263efa8cac57da763533f339` |
| staged paths before accepted commit | empty |
| `git diff --check` | PASS，无输出 |

AgentDS follow-up 只删除其 artifact 内不可稳定自证且非 gate 要求的 self-hash claim；verdict、findings、plan/protected hashes 与全部审查内容未变。

## 3. Re-review adjudication

### AgentMiMo

- verdict：`PASS / 0 material finding / 0 blocker`。
- 独立匹配 final plan、protected diff、shared test 与 guards correction-entry hashes。
- 确认 accepted finding closure、五候选可执行性、最短连续前缀/首次 80% stop、§6.6/§6.7、shared-file boundary、R07/Host/security/deferred no-drift。

**Controller 裁决：ACCEPTED，无 fix gate。**

### AgentDS

- verdict：`PASS / 0 MATERIAL FINDING / 0 BLOCKER`。
- 独立匹配相同 hashes 并逐项尊重此前 Controller adjudication。
- 没有重开已被事实证据驳回的 M1/L1-L3，没有提出新的 material finding。

**Controller 裁决：ACCEPTED，无 fix gate。**

## 4. Finding closure matrix

| finding / observation | 最终状态 | 直接证据 |
|---|---|---|
| `R08-CR-PCF01` plan/test authorization conflict | CLOSED IN FINAL PLAN | existing guards path 的五个 ordered owner families、whole-file 80%、first-pass stop、compat/private/omnibus 禁止均已写入并通过双路完整复审 |
| `R08-CR-PCPR-F01` section/table failure input chain | CLOSED | candidate 2/3 明确 fixture `KeyError` 输入、public runtime `FinsReadArgumentError` 投影、test 只观察 public failure；与 production 两处转换链一致 |
| DS M1 | REJECTED / NOT IMPLEMENTED | production owner `return sorted(doc_types)`；candidate 1 未被改成 repository-order workaround |
| DS L1 | REJECTED / ALREADY COVERED | 仍通过真实 metadata 驱动 form/taxonomy，无 private injection |
| DS L2 | REJECTED / ALREADY PRECISE | AST scan 仍比较 correction-entry 后“新增” imports，无额外白名单 |
| DS L3 | REJECTED / ALREADY CLOSED | ledger 逐步记录 statements/percent，任一 gate 失败 stop 回 Controller |
| re-review new findings | NONE | 两路均为 0 material finding |

## 5. Accepted plan boundaries

Final corrected plan 的 implementation authorization 仅允许：

1. 从 protected tree `7a7ebf...1d6d` 继续，只修改既有 allowlisted `tests/fins/test_read_runtime_semantic_ownership_guards.py`。
2. 按 candidate 1→5 顺序一次新增一个 exact test node；前四项走 public `FinsReadRuntime` seam，第五项仅在必要时使用唯一 module-helper exception。
3. 每次执行同一累计 coverage ledger；`read_runtime_helpers.py` 首次 whole-file exact-key `>=80.00%` 后立即停止新增；五项耗尽仍未过线则停止回 Controller。
4. 过线后从零完整执行 §6.6/§6.7，再建立新 immutable review lock，并由两路 reviewer 审完整 S1+S2+fix cumulative tree。

以下仍未授权：恢复/搬运四个 shared-file omnibus/compat nodes 或九 imports；修改其它 protected path；private/fake/compat/empty/skip/coverage bypass；实现 R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI 或其它 deferred scope；push/PR。

## 6. Exact accepted-plan commit scope

本 gate 的 accepted local plan commit 只允许下列尚未提交的 plan/review/control evidence：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/host/issues-implementation-control.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-codex.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-rereview-mimo.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-rereview-ds.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-rereview-controller-adjudication.md
```

不得把任何 `dayu/fins/**`、`tests/**`、README、S1/S2 implementation artifact 或其它 untracked path 带入该 commit。Commit 完成后才可更新总控中的 accepted plan commit hash，并派发 AgentCodex test-only continuation。
