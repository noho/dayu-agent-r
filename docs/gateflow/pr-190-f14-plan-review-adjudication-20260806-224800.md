# PR 190 F14 plan review Controller adjudication

## Metadata

- gate: `plan review fix`
- timestamp: `2026-08-06T22:48:00+08:00`
- plan: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`
- reviewers:
  - AgentController: `docs/reviews/plan-review-20260806-223954.md`
  - AgentMiMo: `docs/reviews/pr-190-f14-plan-review-mimo-20260806.md`
  - AgentDS: `docs/reviews/pr-190-f14-plan-review-ds-20260806.md`
- decision: `plan-revised-awaiting-original-reviewers-rereview`
- implementation changes: none

## Direct owner evidence

- user/answer block的consumable ref是EventLog event id；tool evidence block的consumable ref是accepted evidence id。
- existing selector先从typed blocks构造`_AtomicMaterialUnit`，对完整`turn_group_id=run_id` unit做排除与strict prefix selection。
- strict accepted `compacted_source_refs`已经包含represented+omitted exact coverage，且排除current input。
- rejected event type是`CONTEXT_COMPACTION_ATTEMPT_REJECTED`，不是一个待“推翻”的`CONTEXT_COMPACTED`。
- all accepted terminal union不依赖previous compact ref传递推断；每条terminal直接贡献当轮coverage。

## Findings adjudication

| source / finding | resolution | plan delta / reason |
| --- | --- | --- |
| Controller F01、MiMo 01：atomic group proof未冻结 | fixed | 冻结metadata-first user anchor proof，再对保守suffix复用`_atomic_material_units`做block/unit all-or-none与prefix validation。 |
| Controller F02：chain referential integrity | fixed | 每个current input ref校验same-session canonical user/sequence；命中compact event的refs校验back-reference，禁止prefix猜测。 |
| Controller F03、MiMo 02、DS F1：全历史payload扫描矛盾 | fixed | raw侧只读全量metadata；已消费prefix不resolve payload；accepted terminals仍全量strict parse，因为不允许第二persisted cursor。 |
| DS F1建议按recent-window size或terminal附近估算 | rejected | recent policy不是coverage truth；任何cap/terminal估算都会重新引入F14同类gap。 |
| Controller F04：latest payload重复解析 | fixed | 新私有typed chain entry；latest replacement/evidence aggregate直接从最后entry投影。 |
| Controller F05：fake source refs | fixed | coverage-sensitive fixture必须显式写真实current/source/evidence refs；synthetic refs只服务shape tests。 |
| Controller F06、DS F2：函数级职责不清 | fixed | 明确四个helper/签名职责、metadata扫描起点与material frontier字段语义。 |
| DS F3：existing evidence early-filter双owner | fixed | 删除`represented_evidence_refs` early skip参数；suffix投影后由唯一cumulative atomic proof分类，避免隐藏partial corruption。 |
| DS F4：无continuity answer | fixed | atomic proof只消费projector实际产生的eligible blocks，不为无block row虚构ref。 |
| MiMo 03：heterogeneous refs | fixed | 明确tool projector先产生evidence id，再以block canonical refs比较；测试使用opaque不等id。 |
| MiMo 04：repair event语义 | fixed-with-correction | 明确rejected有独立event type；repair accepted最终只有一个normal accepted terminal。 |
| MiMo 05：previous ref累积 | fixed-with-correction | union读取每条accepted terminal直接coverage；previous event ref只作rolling provenance，不承担transitive coverage。 |
| MiMo 06：regression proof | fixed | fixture断言protected seq早于terminal、material frontier等于最早protected block；不新增旧算法helper。 |
| MiMo 07：CLI人工标准 | fixed | 拆分mechanical boundary/ref检查与自然语言人工记录，provider差异不归咎frontier。 |

## Revised exact flow

```text
strict accepted terminals -> cumulative compacted_source_refs
relevant raw EventLog metadata -> user-anchor consumed prefix proof
conservative suffix payload projection -> existing atomic units
block/unit all-or-none + consumed-prefix validation -> raw material frontier
```

任一proof缺失只允许保守读取或fail closed，不允许向前跳；因此性能优化不会改变correctness。

## Gate decision

- unresolved blocking/high findings: 0 after revision
- original reviewer re-review required: yes
- next entry point: AgentMiMo、AgentDS与Controller对revision 1做窄re-review；accepted前不实现。
