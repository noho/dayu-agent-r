# PR 190 Compactor LLM-facing S2 review acceptance

## Gate decision

- Gate: S2 code review
- Decision: accepted without fix cycle
- Base: `64aade07`
- Scope: Context Governance 精确 reject fact、typed repair projector、repair prompt contract 与 owner-level tests

## Independent review artifacts

- AgentMiMo: `docs/reviews/pr-190-s2-code-review-mimo-20260803-182716.md`
- AgentDS: `docs/reviews/pr-190-s2-code-review-ds-20260803-182338.md`

## Controller adjudication

总控逐项检查两份 review 的 direct evidence 后作出以下裁决；结论不以“两路一致”替代证据：

1. **Reject truth ownership — accepted**：actual/cap/measurement/action 均由 `context_governance.py::_collect_policy_issues/_section_caps` 在真实拒绝判断点、基于同一 candidate、policy 与 estimator 产生；renderer/projector 不读取 policy 或重算数值。
2. **Typed projection — accepted**：`_repair_feedback_prompt_json_vnext` 只接受 `CompactRepairFeedbackV2`，拒绝 raw mapping，直接读取 typed fields，且不调用 internal `to_json()`。
3. **Internal/LLM boundary — accepted**：durable serialization 继续保留 attempt/count；LLM block exact 顶层为 `required_action/issues`，issue exact fields 为 `code/json_path/message/source_labels`，不含内部治理字段或类型名。
4. **Repair lifecycle — accepted**：first attempt 无独占 repair marker 行；repair attempt 恰有一对新 marker；旧 `PREVIOUS_VALIDATION_REPORT_JSON` 已从 production path 与 prompt contract 删除。
5. **LLM-facing self-containment — accepted**：两份 prompt 自足说明字段名、类型、必填性、语义边界、whole-candidate 动作和最小 JSON 示例；feedback 不是业务材料，source label 只用于定位问题。
6. **Nine-issue matrix — accepted**：owner-level test 真实触发 `1 + 4 * 2 = 9` 条 cap issues，逐项校验精确消息，feedback/projector 均无截断。
7. **Architecture — accepted**：strict parser、accept barrier、state machine、outcome owner 未漂移；没有 compat shim、loose parsing、下游补偿或 God helper。
8. **Validation/docs boundary — accepted**：48 focused tests、71 extended tests、1 deterministic public prompt test 通过；pyright 0；diff check 通过。README/design 由 approved S4 原子更新。

AgentDS 的两个补充观察均不构成 finding：自由字符串 measurement 已由全部 production 调用点与 owner-level matrix 覆盖；repair 示例 label 明确是 schema 示例引用，不作为业务事实或真实请求 label。

## Residual ownership

- S3: real-provider 对注入边界与 repair contract 的行为证据；prompt publication hashes。
- S4: Host/config/tests README 与 Host design；aggregate deterministic verification。

没有 blocking/non-blocking finding，没有 blocking open question，也没有未分类 residual risk。S2 可以进入 accepted slice commit。
