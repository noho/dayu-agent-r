# PR 190 F13 S1 Allowed-test Scope Amendment

## Trigger

S1/C1开始前，Controller对将删除的v3 symbols做全仓直接引用扫描。accepted plan列出的S1 allowed tests遗漏6个现有Host test/helper；这些文件不是无关scope，而是直接导入将被fresh v4删除的类型或函数。若保持原列表，S1只能在allowed scope外修改，或在accepted checkpoint留下import/collection失败，或保留兼容alias；三者都违反已确认Goal与AGENTS owner约束。

实现Agent继续preflight还证明：C1若按时间截面停在步骤1-2也无法运行focused tests。`llm_compaction.py`运行时导入`compaction_operation.CompactorProposalRunInput`，后者与`context_governance.py`都直接导入大量将被步骤1删除的v3 symbols；contract/LLM tests也直接进入governance owner。只改C1四个文件会在test collection前失败。用alias、lazy import、临时双DTO或绕过production owner的test rewrite均不合法。

## Direct evidence

- `tests/host/memory_snapshot_factories.py`：`CompactForwardIntentStatusV3`。
- `tests/host/test_accepted_result_projection.py`：`CompactSourceKindV3`、`compact_output_caps_v3_from_memory_policy`。
- `tests/host/test_compaction_cancellation_scope.py`：`compact_output_caps_v3_from_memory_policy`。
- `tests/host/test_compaction_operation.py`：v3 repair/validation types与caps/feedback helpers。
- `tests/host/test_proactive_compaction_operation.py`：v3 caps helper。
- `tests/host/test_tool_trace_queries.py`：`COMPACT_OUTPUT_SCHEMA_V3`、`CompactCandidateV3`、`CompactSessionSummaryV3`及其fixture构造；S1必须先机械迁移已删除symbol与schema-5 fixture，S2再实现public Tool Trace逐fact projection与新断言。
- `utils/smoke_host_public_conversation_memory_scenarios.py`：14处v3 source/status/schema/candidate call site；该可执行Host smoke是S3诊断候选，删除symbol后不能留成import failure。
- `utils/smoke_host_public_r03_semantic_ownership.py`：4处v3 source/caps call site；虽无覆盖率要求，仍是可执行helper，不得靠缩窄scan掩盖broken import。

扫描命令：对`dayu`与`tests/host`执行v3 type/schema/function和`accepted_candidate` pattern的`rg -l`，再逐文件`rg -n`复核直接引用。生产allowed scope未发现新的遗漏；`dayu/host/README.md`按原计划留给S2。

## Amendment

1. 扩充S1 allowed tests/helpers为上述6个Host文件及两个直接依赖v3的可执行`utils/` smoke，并把S1 residue scan限定为全部Python production/test/helper contract；S2仍负责README与public Tool Trace新增语义，但不得以此保留已删除Python symbol或旧fixture。
2. 保持S1单一原子migration与步骤1-6的依赖顺序，但把C1-C3定义为完整、可收集的最终S1 worktree上的审查cluster，而不是要求不可导入中间态运行测试的时间截面。第一次focused test前允许完成全部必要production/test call-site迁移；随后按cluster分别验证与双路review。

## Goal and architecture impact

- Confirmed Goal、schema shape、semantic owner、implementation顺序与non-goals均不变。
- 不新增生产文件、兼容层、alias、migration、heuristic或consumer fallback。
- 扩充项全部是owner test/helper随fresh contract机械迁移，避免测试或仍可执行smoke倒逼生产保留v3，或在S3前静默损坏。
- cluster改为最终worktree审查视图，消除了中间双owner/alias诱因；S1仍只有一个accepted commit。
- 这是plan completeness修正，不是scope expansion到新业务能力。

## Gate state

两位原plan reviewer已逐项review与re-review，全部findings为FIXED/PASS、零STILL OPEN；Controller接受该amendment。S1实现Agent现在按完整atomic worktree推进，C1-C3在最终可收集worktree上分cluster验证。
