# PR 190 F13 plan review Controller adjudication

## Metadata

- gate: `plan review fix`
- timestamp: `2026-08-06T14:25:33+08:00`
- plan: `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`
- reviewers:
  - AgentDS：`docs/reviews/plan-review-20260806-141818.md`
  - AgentMiMo：`docs/reviews/plan-review-20260806-142113.md`
- controller decision: `plan-fixed-awaiting-original-reviewers-rereview`
- implementation changes: 无

## Direct owner evidence used for adjudication

- `PromptLocalProvenanceEntry` 当前由 `dayu/host/compaction.py` 定义，`compact_material.py` 生产；旧 `accepted_evidence_id` 与新 tuple 若共存会形成两个读路径。
- request `canonical_evidence_refs` 是所有可选 evidence boundary 的 union；accepted refs 只来自最终 retained/new facts。合法 omit 使前者可为后者真超集。
- `ResolvedCompactorResponseIdentity` 是 public resolver 输出；analysis summary 当前从它机械投影。accepted provenance 必须先进入resolver typed view，不能只在analysis层重读raw terminal。
- fresh-schema规则禁止旧schema兼容reader/fallback；旧schema遇到新strict parser的正确行为是fail closed，不是静默丢历史facts。

## Findings resolution

### AgentDS

| finding | resolution | plan delta / reason |
|---|---|---|
| F1 retain-only被candidate empty check误拒 | `fixed` | 明确empty/low-information只看Host展开后的combined replacement；新增retain-only owner test。 |
| F2 Tool Trace字段owner不明确 | `fixed` | 新增`ResolvedCompactorEvidenceFact`，由public resolver拥有；response identity携带tuple，analysis summary exact pass-through。 |
| F3 S1过大 | `fixed-with-alternative` | 不拆成会产生不完整/双owner提交的sub-slice；同一未提交slice增加C1-C3 focused validation/review，最后整体review/commit。 |
| F4 PromptLocalProvenanceEntry owner不明 | `fixed` | 明确类型owner为`compaction.py`，producer为`compact_material.py`。 |
| F5 canonical refs多角色同名 | `fixed` | 增加从material entry到boundary再到per-fact/aggregate的确定公式与多source test。 |
| F6 reconnect路径未展开 | `fixed` | 明确strict payload -> accepted replacement -> Memory逐atom projection；RunInput aggregate不得反写fact。 |
| F7 boundary空refs行为未定 | `fixed` | previous/current evidence entry空refs均typed fail closed，不drop、不用event ref替代。 |
| F8 prompt缺combined cap例子 | `fixed` | 固定数值化retain+new cap例子要求。 |
| F9 request/output aggregate等式 | `rejected-with-reason` | request是可选集，output是已选集；omit时不相等。固定output exact逐fact union且为request boundary有序子集。 |

DS open questions：repair每次重走完整binding已补；旧schema reconnect严格fail closed且验证用新workspace已补；Tool Trace renderer明确为`tool_trace_analysis.py`。

### AgentMiMo

| finding | resolution | plan delta / reason |
|---|---|---|
| F01 S1过粗 | `fixed-with-alternative` | 同DS F3，增加C1-C3强制checkpoint，不制造可提交双schema中间态。 |
| F02 schema-4运营影响 | `fixed-with-correction` | 明确旧schema strict fail closed、数据保留、不承诺旧workspace升级；拒绝未确认的静默省略/fallback语义。 |
| F03 singular/tuple双真源 | `fixed` | `PromptLocalProvenanceEntry.canonical_evidence_refs` clean replacement旧singular字段；pack下游只有一个字段。 |
| F04 dataclass规格不精确 | `fixed` | 补frozen/slots、无default、字段级校验与governance binding职责。 |
| F05旧schema首次rolling refs来源 | `fixed-with-correction` | fresh v4只从v4 accepted replacement读取；schema-4不能构造boundary并strict fail closed，不静默fallback。 |
| F06同claim反向测试 | `fixed` | previous omit后，相同claim若有current evidence可作为新fact接受；retained+new exact duplicate按combined规则拒绝。 |
| F07 S0大纲 | `fixed` | S0补六项exact design edit list。 |

## Gate decision

- blocking unresolved findings: 0
- high unresolved findings: 0
- original reviewers re-review required: 是
- next entry point: 对修订后的同一plan执行两路独立re-review；re-review accepted前不得实现。

## Validation

- `git diff --check`: pass
- tests/pyright/CLI: 未运行；本gate只修改plan与review artifacts
