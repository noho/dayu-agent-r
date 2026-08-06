# PR 190 F13 S1 Scope Amendment Review 裁决

## Evidence

- MiMo：`docs/reviews/plan-review-20260806-f13-s1-scope-mimo.md`
- DeepSeek：`docs/reviews/plan-review-20260806-f13-s1-scope-ds.md`
- 被审plan diff：S1 allowed tests、Python residue scan、C1-C3 cluster执行时机

## Controller adjudication

| Finding | 裁决 | 处理 |
|---|---|---|
| C1步骤1-2会使operation/governance传递导入断裂 | ACCEPT / FIXED | C1-C3改为完整可收集S1 worktree上的domain review clusters；实现仍按1-6依赖顺序，不为中间态保留alias/双DTO。 |
| 6个Host test/helper遗漏 | ACCEPT / FIXED | 全部加入S1 allowed tests；它们只做fresh symbol/schema fixture机械迁移。 |
| `test_tool_trace_queries.py`证据描述不够精确 | ACCEPT / FIXED | amendment列出3个具体v3 symbols；S1机械存活、S2 public projection语义边界不变。 |
| S1/S2同文件重叠 | PASS | concern边界明确，不构成双owner。 |
| residue scan收窄后排除2个`utils/` smoke、完整pattern共18处v3引用 | ACCEPT / FIXED | 不接受仅记录broken helper为residual risk；两个脚本仍可执行且可能服务S3诊断，加入S1 helper scope，residue scan扩到`utils/**/*.py`。原review的15处计数未覆盖全部schema/candidate命中，Controller按完整residue pattern更正。 |
| dayu/tests其它遗漏扫描 | PASS | 非Host生产与非Host tests无会被删除的v3 contract引用；合法上游`derive_accepted_evidence_id`不属于material-pack字段。 |
| cluster会削弱checkpoint | REJECT WITH EVIDENCE | 两路review均确认在完整worktree运行focused tests反而消除collection假通过；checkpoint继续按cluster列出文件/符号、diff identity与双路结论。 |

## Gate status

所有accepted findings已更新到plan/amendment。等待原reviewers针对具体修复re-review；未复审前amendment不接受，S1生产实现保持暂停。
