# PR 190 F13 S1 Scope Amendment Accepted Checkpoint

## Decision

- Verdict：ACCEPTED
- Goal/schema/owner/non-goals：不变
- Production owner scope：不新增
- Mechanical scope：新增6个Host test/helper与2个仍可执行`utils/` smoke call sites
- Checkpoint model：C1-C3改为完整可收集S1 worktree上的domain review clusters；S1仍只有一个accepted implementation commit

## Direct reason

删除v3 domain symbols后，`compaction_operation`、`context_governance`、`llm_compaction`和focused tests形成直接传递导入断裂，步骤1-2不能成为可运行时间截面。保留alias、lazy import、双DTO或绕过真实owner的test seam均违反fresh schema。全仓扫描还发现原allowed list漏掉6个Host test/helper，另有2个可执行`utils/` smoke共18处v3引用；缩窄scan会留下broken helper并可能阻塞S3诊断。

## Review evidence

- MiMo initial：`docs/reviews/plan-review-20260806-f13-s1-scope-mimo.md`
- DeepSeek initial：`docs/reviews/plan-review-20260806-f13-s1-scope-ds.md`
- Controller adjudication：`docs/gateflow/pr-190-f13-s1-scope-review-adjudication-20260806.md`
- MiMo re-review：`docs/reviews/plan-review-20260806-f13-s1-scope-mimo-rereview.md`，7/7 FIXED/PASS
- DeepSeek re-review：`docs/reviews/plan-review-20260806-f13-s1-scope-ds-rereview.md`，独立确认7/7 FIXED/PASS

## Frozen execution boundary

- 实现按步骤1-6依赖顺序完成所有production/test/helper call-site迁移，第一次focused test前允许完成完整S1 worktree。
- C1只审domain/structure/prompt；C2只审material/governance/payload；C3只审consumers/call sites/residue。每个artifact列出文件、关键symbols、diff identity、命令与双路review。
- `dayu/**/*.py`、`tests/**/*.py`、`utils/**/*.py`最终不得残留v3 compact contract或material-pack singular provenance字段。
- S2继续拥有public Tool Trace新projection与README；S1在`test_tool_trace_queries.py`只做deleted-symbol/schema-5 fixture机械迁移。
