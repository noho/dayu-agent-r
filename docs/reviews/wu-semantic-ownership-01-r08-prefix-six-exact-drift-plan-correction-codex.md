# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift plan correction

## 1. Verdict

`READY_FOR_CONTROLLER_VALIDATION / NOT_IMPLEMENTATION`

本 artifact 只记录既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 R08 的 plan-only correction，
不是新 WU、sub-WU 或 slice，不授权 implementation、测试、coverage、pyright、Ruff、smoke、code review、
commit、push 或 PR。完成后停回 Controller。

## 2. 动机与 direct root evidence

Accepted finding `R08-CR-PCF04` 成立。Candidate 6 的三条 public-owner assertions 不只执行
material、other 与 CN `FY` 三条分类分支；`form_type=None` 在进入分类 owner 前还必经同一 public owner
normalization。Fresh prefix-five/prefix-six JSON 的 `executed_lines` 直接比较为：

```text
NEWLY_COVERED_LINES [344, 346, 348, 442]
344: return "material"
346: return "other"
348: return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]
442: return None
```

第 `442` 行是 `form_type=None` 经 `resolve_document_type_for_source` public owner normalization
产生的 `return None`，之后同一调用才进入 `other` 分类。因此 exact arithmetic 是：

```text
prefix-five: 387/485 = 79.79381443%
candidate 6: +4 covered statements
prefix-six:  391/485 = 80.61855670%
```

这不是 denominator、threshold、测试或产品语义失败；正确修复边界是纠正计划的 exact arithmetic、
direct evidence 与 re-entry sequence，而不是回退测试、增加第七项或修改 production。

## 3. 最终计划改动

1. 所有 active prefix-six expected/result/checker 已从 `390/485 = 80.41237113%` 更正为
   `391/485 = 80.61855670%`，denominator 保持 `485`；checker 精确要求 `covered == 391`。
2. 计划已记录 fresh JSON 新增执行行 `[344,346,348,442]` 及各自行的 owner 语义。
3. Candidate 6 已明确为现存、受保护的唯一 public-owner import/test与三条断言；仍是 first/shortest
   threshold-crossing prefix，不新增第七项、不回退或再次实现 candidate 6。
4. Re-entry locks 已更新为当前 stopped tree：cumulative diff 与 guards 使用 candidate 6 后的当前值，
   helper、actual owner、shared test、S1/S2 artifacts 与 staged-empty 继续精确锁定。
5. Prefix-five 保留为同一 implementation task 在 candidate 6 mutation 前、同一 locked tree、同一八文件、
   零 deselect 产生的 fresh predecessor proof；计划不再要求回退测试重跑 prefix-five。
6. Continuation 只 fresh erase 重跑同一八文件、零 deselect prefix-six，预期 `392 passed` 与
   exact `391/485 >= 80.00%`；JSON 可重写到
   `workspace/tmp/r08-prefix-six-proof-coverage.json`。精确通过后从零完成原 §6.6/§6.7 全矩阵。
7. Exact fail-closed 保留：任一 numerator、denominator、threshold、hash、test、smoke、pyright、Ruff、
   scan 或 no-touch drift 都停止回 Controller。
8. 所有会把 continuation 误导为“candidate 6 尚不存在、先重跑 prefix-five、再新增 candidate 6”的
   active re-entry/sequence 文本均已删除或明确标为 superseded historical evidence。
9. Production、shared/其它 tests、README、no-code/security 与 deferred Issue 边界保持不变；R09-R12、
   Issues 142/151/175/177/178、统一 authorization、Topic 8-9 code 仍不在本 gate。

Controller follow-up correction：顶部 current-lineage commit 已从不同代的 `65fd8d5c...` 更正为与
correction 前 plan SHA `115a6429...c401` 同代的 accepted-plan commit `261df95f...2141`；§6.8 已将
“后续 candidate 6 implementation”更正为“后续 prefix-six implementation continuation”，不再把已存在的
candidate 6 描述成未来 mutation。

## 4. Prefix-five predecessor 与 continuation contract

Fresh predecessor proof 固定为：

| 项目 | 结果 |
|---|---|
| tests | 同一八文件、零 deselect，`391 passed` |
| exact coverage | `387/485 = 79.79381443% < 80.00%` |
| JSON | `workspace/tmp/r08-prefix-five-proof-coverage.json` |
| JSON SHA-256 | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` |
| 时序 | 同一 implementation task、candidate 6 mutation 前、同一 locked tree |

Continuation 不重跑 prefix-five。Candidate 6 保持现状后，fresh prefix-six 必须得到 `392 passed`、
`391/485 = 80.61855670% >= 80.00%`，且同一八文件命令不得包含 `--deselect`。精确通过后从零执行原
§6.6/§6.7 focused、aggregate、full Fins、三段 forced-truncation、AAPL/HTML/no-statement smokes、
15-file exact-key coverage、full pyright、changed-file Ruff 与全部 scans/no-touch checks。

## 5. Plan SHA-256

| 项目 | SHA-256 |
|---|---|
| correction 前 plan | `115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401` |
| final plan | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` |

Final plan 路径：
`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`。

## 6. Current locks

| 锁 | 当前值 |
|---|---|
| HEAD | `e9c68cdc1d6079374149df2b8d0ff0ca3b63a02e` |
| cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| `read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards after candidate 6 | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged tree | empty |

以上 locks 在本 gate 前后均匹配。Candidate 6、helper deletion、actual owner、shared/其它 tests、
production、README 与 S1/S2 artifacts 均未被本 turn 修改。

## 7. Scope、no-touch 与 status

本 turn authored paths 精确为：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-codex.md
```

完整 final `git status --short --untracked-files=all` 预期并已核对为：

```text
 M dayu/fins/README.md
 M dayu/fins/domain/financial_result_contract.py
 M dayu/fins/domain/xbrl_result_contract.py
 M dayu/fins/pipelines/sec_fiscal_fields.py
 M dayu/fins/processors/bs_report_form_common.py
 M dayu/fins/processors/bs_six_k_processor.py
 M dayu/fins/processors/financial_base.py
 M dayu/fins/processors/html_financial_statement_common.py
 M dayu/fins/processors/report_form_financial_statement_common.py
 M dayu/fins/processors/sec_processor.py
 M dayu/fins/processors/sec_xbrl_query.py
 M dayu/fins/processors/six_k_form_common.py
 M dayu/fins/tools/fins_tools.py
 M dayu/fins/tools/read_runtime.py
 M dayu/fins/tools/read_runtime_helpers.py
 M dayu/fins/tools/result_types.py
 M docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
 M tests/README.md
 M tests/fins/test_financial_read_contracts.py
 M tests/fins/test_fins_read_runtime.py
 M tests/fins/test_fins_storage_provider.py
 M tests/fins/test_processor_read_consistency.py
 M tests/fins/test_read_runtime_semantic_ownership_guards.py
 M tests/fins/test_sec_pipeline_download.py
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
```

除本 turn 两条 authored docs 外，其余均为 pre-existing protected stopped-tree 状态。`dayu/fins`、
`tests`、README、control、design、prior reviews、Controller adjudication 与 S1/S2 artifacts 无本 turn delta。

## 8. 文档验证与未运行项

| 检查 | 结果 |
|---|---|
| `git rev-parse HEAD` | `e9c68cdc1d6079374149df2b8d0ff0ca3b63a02e` |
| `git diff --cached --name-only` | empty |
| protected binary diff before/after | 均为 `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| current content locks | 全部精确匹配 §6 |
| `git diff --check` | PASS |
| 两条 authored docs whitespace check | PASS |
| scope/no-touch check | PASS |

按 plan-only gate 明确未运行 implementation、pytest、coverage、pyright、Ruff 或任何 smoke；未 stage、
commit、push 或创建 PR。README trigger 结论为 no-update：本 correction 只修计划 arithmetic、证据与
continuation sequence，不改变用户可见 contract、测试职责、CLI 工作流或分层关系。

Stop status：`READY_FOR_CONTROLLER_VALIDATION / NOT_IMPLEMENTATION`，停回 Controller。
