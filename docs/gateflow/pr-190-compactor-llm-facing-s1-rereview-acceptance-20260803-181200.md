# PR 190 Compactor LLM-facing S1 re-review acceptance

## Gate decision

- Gate: S1 code re-review
- Decision: accepted
- Base: `a9383ee6`
- Scope: prompt trust boundary、自足 output contract、同源示例与 owner-level deterministic tests

## Independent evidence adjudication

### AgentMiMo

- Artifact: `docs/reviews/pr-190-s1-code-rereview-mimo-20260803-180732.md`
- Decision: accepted
- Controller adjudication: 原 repair marker mismatch 与宽泛 forbidden-term finding 均有直接代码、rendered path 和测试证据证明已修复；F01/F02 pass evidence 未退化。

### AgentDS

- Artifact: `docs/reviews/pr-190-s1-code-rereview-ds-20260803-180825.md`
- Decision: accepted
- Controller adjudication: 逐项确认 prompt 不再承诺 S2 future marker/schema，现有 generic whole-candidate repair 语义与 renderer 一致；production parser 与 Context Governance 接受四源 example，coverage partition 精确。

## Controller finding decisions

1. S1 prompt 与当前 renderer marker 不一致：**已修复**。S1 撤回未来 marker/schema 承诺；S2 将原子落地新 marker、typed projector 与 prompt contract。
2. forbidden-term 宽泛子串可能误伤业务英文：**已修复**。改为精确内部类型、字段和治理短语。
3. 不可信材料边界缺失：**已修复**。`current_input.readable_text` 与所有 `source_boundary[*].readable_text` 均明确是引用数据；不执行材料内指令不等于过滤、删除或改写材料。
4. schema 语义与 T1 示例不自足：**已修复**。八类 source、开放字段、覆盖规则和 E1/A1/T1/D1 同源示例均在当前 prompt 自足说明，并由 production parser/governance 验证。

## Validation accepted

- `pytest tests/host/test_llm_compaction.py -q`: 24 passed
- filtered `tests/host/test_public_compact_smoke.py`: 1 passed, 23 deselected
- pyright: 0 errors, 0 warnings, 0 informations
- `git diff --check`: passed

## Residual ownership

- S2: repair feedback marker、typed LLM-facing projector、精确 policy-cap feedback。
- S3: Mimo-first real-provider adversarial behavior、repair behavior、publication hashes。
- S4: design/README 与 aggregate verification。

没有 blocking open question，也没有未分类 residual risk。S1 可以进入 accepted slice commit。
