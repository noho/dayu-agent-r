# PR 190 F14 plan re-review acceptance

## Metadata

- gate: `plan re-review`
- plan: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`
- prior adjudication: `docs/gateflow/pr-190-f14-plan-review-adjudication-20260806-224800.md`
- AgentMiMo re-review: `docs/reviews/pr-190-f14-plan-rereview-mimo-20260806.md`
- AgentDS re-review: `docs/reviews/pr-190-f14-plan-rereview-ds-20260806.md`
- Controller decision: `accepted`
- implementation changes: none

## Re-review evidence

- 两位原reviewer均确认原findings已解决，结论均为`accepted`。
- metadata-first proof只用user anchor exact accepted ref跳过已消费group；evidence id继续在suffix typed projector中解析，不与EventLog id混用。
- production EventLog-backed raw projector不设置任意位置的explicit protected flag；recent floor按各group最新canonical位置保护最新N组，因此protected groups为suffix。
- selector对剩余eligible atomic units做strict prefix selection；cumulative consumed groups因此只能形成canonical prefix。
- suffix再复用`_atomic_material_units`执行block/unit all-or-none与prefix check，任何partial coverage fail closed。
- accepted chain每条payload只strict解析一次；latest replacement/evidence aggregate与cumulative consumption从同一typed entries投影。

## Controller adversarial conclusion

MiMo re-review一度提出“较老R3 protected、较新R4 selected”反例；该反例与recent-floor owner实现矛盾：如果R3属于最新N组，任何更近R4也必在最新N组，不能eligible。原reviewer依据直接代码证据纠正并覆盖了review artifact。Controller确认没有遗留correctness gap。

不采用按terminal位置、recent cap或window大小估算frontier的性能捷径；它们不是coverage truth。accepted chain strict parse成本作为不引入第二cursor的必要代价保留，raw payload解析通过metadata prefix proof有界收窄。

## Gate decision

- unresolved blocking/high/medium findings: 0
- schema/public contract expansion: none
- correct owner: Host `dayu.host.compact_material`
- plan status: accepted
- next entry point: commit accepted plan artifacts，随后把单一S1 slice交给AgentCodex实现。
