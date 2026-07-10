# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 implementation artifact

## Gate 与状态

- Gate：P3-C S3 implementation
- Scope：Accepted evidence typed LLM material / renderer / typed mismatch closure
- 状态：PASS
- Artifact：`docs/reviews/wu-semantic-ownership-01-p3-c-s3-implementation-codex.md`

## Root cause / owner boundary

Root cause 成立：P1-A 已统一 accepted tool result 的 query/source/result/status 事实读取，但最终 LLM-facing evidence 文本仍分散在 Conversation Memory、compact pipeline 与 RunInput fallback/raw-tail 中；同时 producer event ref mismatch 仍通过字符串错误协议识别，durable memory、compact material、run input 仍存在重复 envelope 读取。

Owner boundary：

- 首次产生：ToolRuntime / wait-resolution accept barrier 写入 `TOOL_CALL_REQUESTED` request atom 与 `TOOL_RESULT_ACCEPTED` envelope/raw outcome。
- 校验 owner：`dayu.host.evidence` 校验 envelope 与 producer ref；`dayu.host.accepted_result_projection` 校验 accepted result identity、request atom、query/source/result/status。
- 持久化真源：EventLog `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED` 与 payload descriptor。
- LLM material projection owner：`AcceptedToolResultProjection.llm_material` 由 accepted-result projection 产生；无 durable 依赖的 `AcceptedToolEvidenceLLMMaterial` 与 `render_accepted_tool_evidence_for_llm()` 位于 `dayu.host.evidence` leaf contract，并由 `accepted_result_projection.py` 导出，避免 Host bootstrap cycle。
- 消费者：Conversation Memory、compact material、compact pipeline raw tail、RunInput fallback 只消费 typed material / renderer；Tool Trace 继续只消费 projection facts 并保留 trace-only caps。

## 改动摘要

Production：

- `dayu/host/evidence.py`
  - 新增 `AcceptedEvidenceProducerEventRefMismatchError(expected_event_ref, observed_event_ref)`。
  - producer mismatch 改为抛 typed exception，删除字符串控制流常量。
  - 新增 leaf contract `AcceptedToolEvidenceLLMMaterial` 与唯一四行 renderer。
- `dayu/host/accepted_result_projection.py`
  - `AcceptedToolResultProjection` 新增 `llm_material`、`tool_call_requested_event_ref`、`source_locator_refs`。
  - tool name / tool call id / resolution kind / tool fact kind 使用 strict optional payload text accessor：absent/null optional，存在但类型错误或空白 fail closed。
  - mismatch typed exception 包装为 `HostDurableError` cause chain。
- `dayu/host/memory.py`、`dayu/host/durable/memory.py`
  - `MemoryProjectionEvent` 以 `accepted_tool_evidence` 取代四个 loose evidence text fields。
  - `TOOL_RESULT_ACCEPTED` 总调用唯一 renderer；material 缺失时使用 owner fallback。
  - durable memory 不再二次打开 accepted evidence envelope。
- `dayu/host/compact_material.py`
  - `RunInputMaterialBlock` 原子迁移到完整 evidence contract：identity refs、payload/artifact/source locator refs、typed material。
  - evidence block `text` 必须等于 shared renderer；non-evidence block 禁止携带 evidence provenance。
  - EventLog-backed evidence block 只消费 `AcceptedToolResultProjection`，不再解析 envelope。
  - `CompactEvidenceBlock` / `EvidenceReadableItemVNext` 按 no-rename mapping 取 typed material 分量：result 分量只进入 `raw_result_text` / `response_text`。
- `dayu/host/compact_pipeline.py`、`dayu/host/run_input.py`
  - 删除私有 accepted evidence renderer；section routing 只加 consumer-owned prefix，正文来自唯一 renderer。
  - run input inline repair 不再二次打开 envelope。
- `dayu/host/README.md`
  - 更新 Host 当前实现事实：accepted evidence typed material、唯一 renderer、memory/run-input/compact 消费边界。

Tests：

- 更新既有 host tests 到 typed material contract。
- 新增/强化断言：mismatch typed exception 与 cause chain、malformed optional payload fail closed、material missing fallback、memory/compact/run-input 文本一致、component no-rename exact mapping、Tool Trace unchanged-consumer regression。

## Validation

Required affected matrix：

```text
449 passed, 1 skipped
```

命令：

```bash
source .venv/bin/activate
python -m pytest tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_memory_projection.py tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py -q
```

Type / import / weak typing：

```text
python -m pyright dayu/ tests/ utils/ -> 0 errors
python -c 'import dayu.host; import dayu.host.memory; import dayu.host.compact_material; import dayu.host.run_input' -> pass
python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q -> 25 passed
```

Coverage per touched production file：

```text
dayu/host/evidence.py                    92%
dayu/host/accepted_result_projection.py  94%
dayu/host/memory.py                      92%
dayu/host/durable/memory.py              85%
dayu/host/compact_material.py            86%
dayu/host/compact_pipeline.py            94%
dayu/host/run_input.py                   88%
```

## Source scans

通过：

- no `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH`
- no `str(exc).*ACCEPTED_EVIDENCE`
- no `accepted_evidence_envelope_from_payload` in `compact_material.py`, `durable/memory.py`, `run_input.py`
- no `def _accepted_tool_evidence_content`
- no `def _accepted_evidence_readable_text`
- no compact candidate/string round-trip dead helpers from plan section 9
- `CompactPipelineCompactArtifactView` only exposes `compact_artifact_ref` / `compact_artifact_digest`
- `git diff -- dayu/host/tool_trace.py` empty
- `git diff --check` pass

## README decision

- `dayu/host/README.md` updated because `dayu/host/` implementation changed stable owner contract for accepted evidence material/rendering.
- `tests/README.md` not updated: only existing host tests were expanded; no new test tier, command family, or maintenance rule changed.
- Root README / `dayu/README.md` not updated: no user-facing install/CLI/workflow or layer boundary change.

## Propagation audit

Accepted evidence propagation now follows one path:

```text
ToolRuntime / wait-resolution accept barrier
  -> TOOL_CALL_REQUESTED request atom
  -> TOOL_RESULT_ACCEPTED envelope + raw outcome + refs/digests
  -> evidence.py envelope codec / typed mismatch exception
  -> accepted_result_projection identity/query/source/result validation
  -> AcceptedToolEvidenceLLMMaterial
     -> durable MemoryProjectionEvent.accepted_tool_evidence
        -> Conversation Memory renderer output
     -> EventLog-backed compact material RunInputMaterialBlock.accepted_tool_evidence
        -> CompactEvidenceBlock component fields
        -> EvidenceReadableItemVNext response_text = material.result_text
     -> ordinary protected raw tail / fallback RunInput
        -> shared renderer output
  -> Tool Trace consumes same projection facts, then applies trace-only display caps
```

Consistency assertions:

- 同一 durable accepted result 在 memory、ordinary protected tail、fallback RunInput 使用同一个 renderer 正文。
- `RunInputMaterialBlock.text` 是完整四字段 renderer；`CompactEvidenceBlock.raw_result_text` 与 `EvidenceReadableItemVNext.response_text` 只等于 `material.result_text`。
- query/source unavailable 与 material missing fallback 均由 owner 常量/renderer 给出，不含 internal id/ref/digest/wait/poll/runtime 术语。
- producer mismatch fail closed，并保留 typed cause chain。
- Tool Trace production diff 为空，trace caps/status owner 未改变。

## Remaining risks

- fixed in S3：evidence renderer/fallback drift、string exception protocol、accepted-result lenient optional payload text、durable memory/compact/run input envelope 二次解析。
- assigned to P3-E：accepted tool status fallback/raw outcome reconstruction。
- assigned to P3-J：全局 EventLog schema/taxonomy/DDL closed-set。
- residual implementation note：typed material/renderer 的无 durable 依赖 value contract 放在 `evidence.py` leaf，以解决直接 import projection type 导致的 Host bootstrap cycle；`accepted_result_projection.py` 仍负责产出并导出该 material。
