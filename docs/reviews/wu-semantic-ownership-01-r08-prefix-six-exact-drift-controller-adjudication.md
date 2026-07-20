# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact drift Controller adjudication

## 1. Gate 与结论

本轮仍是既有 umbrella WU 内 R08 coverage-statement drift implementation continuation，不是新 WU、
新 sub-WU 或新 slice。AgentCodex 在全部 re-entry/source-AST locks 与 fresh prefix-five proof 通过后，
只实施了已授权的 candidate 6 public-owner test；prefix-six 测试全部通过且 whole-file coverage 已超过
`80.00%`，但 exact numerator 实测为 `391/485`，不等于 accepted plan 的 `390/485`，因此正确
fail closed，未继续完整 acceptance validation。

**Decision：ACCEPTED NEW PLAN FINDING `R08-CR-PCF04`。**

保留语义正确且严格在授权范围内的 candidate 6 import/test。回到同一 R08 的 plan-only correction，
只纠正 prefix-six exact arithmetic、direct executed-line evidence 与 stopped-tree re-entry locks；不得回退
candidate 6、降低阈值、补第七个测试或修改 production/README/其它 tests。

## 2. Protected stopped tree

| 项目 | Controller 复核值 |
|---|---|
| AgentCodex stopped artifact | `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-implementation-codex.md` |
| stopped artifact SHA-256 | `35a9669edf8e6e3ce5b38cb69ee831df52ba972c320155896061c51713bbfba8` |
| cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| `read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b`，no-touch |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657`，no-touch |
| guards after candidate 6 | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，no-touch |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748`，no-touch |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`，no-touch |
| staged tree | empty |
| `git diff --check` | PASS |

Fresh prefix-five JSON：
`workspace/tmp/r08-prefix-five-proof-coverage.json`，SHA-256
`43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb`。

Fresh prefix-six JSON：
`workspace/tmp/r08-prefix-six-proof-coverage.json`，SHA-256
`b4c103423956543069ef89434cb7190d3e32b2847cff9f6320dc0a6c6f7b4dee`。

## 3. Root cause

Accepted plan 正确识别了 candidate 6 的三条业务分类分支，却漏算同一 public-owner 调用在进入
`_resolve_document_type` 前必经的 normalization 分支。Candidate 6 的
`form_type=None` 调用按唯一生产路径执行：

```text
resolve_document_type_for_source
  -> _normalize_form_type_for_matching(None)
  -> if normalized is None: return None
  -> _resolve_document_type(...)
  -> return "other"
```

两个 fresh JSON 的 `executed_lines` 同源比较直接证明 prefix-six 相对 prefix-five 新增覆盖行是：

```text
[344, 346, 348, 442]
344: return "material"
346: return "other"
348: return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]
442: return None
```

因此机械结果是：

```text
prefix-five: 387/485 = 79.79381443%
candidate 6: +4 covered statements
prefix-six:  391/485 = 80.61855670%
```

这不是测试、denominator、threshold 或产品语义失败，也不是新增非业务 coverage padding。第 442 行是
缺失 form type 输入所必需的 production normalization 语义，与同一断言的 `other` 业务结果不可分割。

## 4. Accepted finding `R08-CR-PCF04`

最终计划必须只作以下纠正：

1. 将所有 prefix-six 预期从 `390/485 = 80.41237113%` 改为 fresh evidence 已证明的
   `391/485 = 80.61855670%`；prefix-five 仍为 `387/485 = 79.79381443%`。
2. 显式记录 candidate 6 覆盖 `344/346/348/442` 四条 statements，并说明第 442 行来自
   `form_type=None` 的 public-owner normalization 路径。
3. 保留 candidate 6 的唯一 import/test 与三条 owner-level assertions；它仍是 first/shortest
   threshold-crossing prefix，不新增第七项。
4. 实现重入必须匹配当前 cumulative diff `e40de2a0...33f`、guards
   `cc4c5267...9274` 以及其余 no-touch locks；candidate 6 已存在，不得再次实现或回退。
5. Prefix-five fresh proof 已由本 implementation task 在 candidate 6 mutation 前、同一 locked tree、
   同一八文件零 deselect 命令中完成。纠正后 implementation continuation 保留该 fresh predecessor
   JSON/result 为进入证据，不要求为了重跑 prefix-five 而回退正确测试。
6. Continuation 必须 fresh erase 并以同一八文件零 deselect 命令重新运行 prefix-six，精确得到
   `391/485 = 80.61855670% >= 80.00%`；随后从零完成原 §6.6/§6.7 全部 acceptance validation。
7. 任一 numerator、denominator、threshold、hash、test、smoke、pyright、Ruff、scan 或 no-touch drift
   仍 fail closed 回 Controller。

## 5. Rejected alternatives

| Alternative | Decision |
|---|---|
| 回退 candidate 6 只为重跑 prefix-five | REJECTED：会破坏已证明的正确 owner contract test；predecessor fresh JSON 已在 mutation 前产生 |
| 修改断言以避免覆盖第 442 行 | REJECTED：会伪造业务输入并切断 missing-form normalization 真路径 |
| 把 checker 放宽成只判断 `>=80%` | REJECTED：继续保留 exact fail-closed source/test/environment drift proof |
| 降低 whole-file threshold | REJECTED：违反 AGENTS.md 与 accepted R08 gate |
| 新增第七个测试或 coverage padding | REJECTED：candidate 6 已是 first/shortest threshold-crossing prefix |
| 修改 production、shared/其它 tests 或 README | REJECTED：没有新的语义 owner finding，超出本 correction allowlist |
| 恢复旧 shared compatibility/omnibus tests | REJECTED：会重开已关闭 `R08-CR-CF01` |

## 6. Gate 与 next entry

AgentCodex 只允许 plan-only correction：修改唯一最终计划，并新增新的 plan-correction artifact；当前
product/test/README/S1/S2 tree 保持 immutable。Controller validation 后必须再次双路完整 plan review；
任何 accepted finding 仍须 plan fix/re-review。新的 accepted local plan commit 与单独 implementation
authorization 完成前，不得运行 implementation continuation、完整 acceptance、code review、aggregate
deepreview 或提交产品代码。

