# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Gate 交付说明

## 范围

本次只执行 P1-A plan gate：读取设计真源和当前代码，确认 root cause，产出 code-generation-ready plan。未修改生产代码，未修改测试，未提交，未 push。既有 `docs/host/issues-implementation-control.md` 本地修改未触碰。

## 扫描命令

```bash
git branch --show-current
git status --short
rg -n "AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery|accepted_evidence|accepted evidence|_readable_query_text_from_envelope|_tool_result_query_text|_llm_facing_evidence_source_text|_tool_result_status|source_note|resolution_kind|tool_fact_kind|raw_tool_outcome" dayu/host tests/host
rg -n "accepted evidence|TOOL_RESULT_ACCEPTED|Tool Trace|RunInputBuilder|Conversation Memory|CompactMaterial|accepted_evidence_envelope|source_note|semantic_query_text" docs/host/design.md
rg -n "trace_summary_json|result_details|tool_result|TOOL_RESULT_ACCEPTED|_tool_result_status|tool_fact_kind|resolution_kind|raw_tool_outcome|accepted_evidence_envelope|tool_request" dayu/host
rg -n "_tool_result_status|_tool_result_query_text|_readable_query_text_from_envelope|_llm_facing_evidence_source_text|_tool_request_summary_from_tool_result|_tool_result_accepted_activity" tests/host dayu/host
```

## 直接证据摘要

- `dayu/host/evidence.py` 已有 `AcceptedEvidenceEnvelope` 和 codec；旧 finding 中“完全没有 envelope”的部分已过期。
- `dayu/host/tool_runtime.py` 已同事务写入普通 `TOOL_CALL_REQUESTED` request atom、`TOOL_RESULT_ACCEPTED` envelope 和 `raw_tool_outcome`。
- `dayu/host/waiting.py` 已让 wait-resolution `TOOL_RESULT_ACCEPTED` 携带 envelope 和 raw outcome。
- `dayu/host/compact_material.py` 仍有 `_readable_query_text_from_envelope()`，会在无 semantic query 时回退到参数 JSON。
- `dayu/host/durable/memory.py` 仍有 `_tool_result_query_text()`，同类情况下返回 unavailable，和 CompactMaterial 不一致。
- `dayu/host/tool_trace.py` 仍有 `_tool_request_summary_from_tool_result()` 与 `_tool_result_status()`，独立回读 request atom 并按 `resolution_kind -> tool_fact_kind -> raw outcome` 推断 status。
- `dayu/host/read_api.py` 的 `_tool_result_accepted_activity()` 只读取 `outcome_kind`，和 canonical accepted payload 的 `tool_fact_kind` / wait-resolution 的 `resolution_kind` 不是同一 projection source。
- `dayu/host/run_input.py` 与 `dayu/host/compact_pipeline.py` 各自保留 `_llm_facing_evidence_source_text()` blacklist source filter；`dayu/host/compact_material.py` 先把 opaque refs 拼成 `ref_kind:ref_id`。

## 计划路径

主计划 artifact：

- `docs/host/wu-semantic-ownership-01-p1-a-plan.md`

选定方案：

- 新增 sibling Host projection contract/helper，而不是扩展 `AcceptedEvidenceEnvelope` 本体。
- 下游消费者迁移到同一个 accepted-result projection helper。

## 未决风险

- source refs 当前生产路径多数为空；本轮可关闭 source 泄漏和 projection 真源问题，但业务 source 丰富度可能需要后续 producer WU。
- 如果 implementation 发现必须新增 EventLog payload 字段或 schema version，必须先更新 `docs/host/design.md` 并按全新 schema 起库策略处理。
- Tool Trace result details 的 bounded rendering 属于展示策略，不能反向改变 projection truth。

## 完成状态

P1-A plan artifact 已产出；本 gate 未做实现、测试修改、提交或 push。

