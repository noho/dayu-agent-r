# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Controller Validation

## Gate 与结论

- Gate：P3-C S3 implementation controller validation。
- Agent artifact：`docs/reviews/wu-semantic-ownership-01-p3-c-s3-implementation-codex.md`。
- Controller 结论：PASS，ready for code review。
- Blocking questions：0。

## Scope 审计

S3 实际修改落在 accepted plan 的 allowed production/test/docs 范围：

- Production：`evidence.py`、`accepted_result_projection.py`、`memory.py`、`durable/memory.py`、`compact_material.py`、`compact_pipeline.py`、`run_input.py`。
- Tests/docs：`test_accepted_result_projection.py`、`test_memory_projection.py`、`test_compact_material.py`、`test_compact_pipeline.py`、`test_run_input_builder.py`、`dayu/host/README.md`。

`dayu/host/tool_trace.py` diff is empty. `tests/README.md` was not changed because S3 only expanded existing Host test coverage and did not add a new test tier, command family, or maintenance rule.

## Controller 独立验证

- `source .venv/bin/activate && python -m pytest tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_memory_projection.py tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py -q`
  - `449 passed, 1 skipped in 2.50s`
- `source .venv/bin/activate && python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - `25 passed in 2.16s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`
- import smoke：
  - `dayu.host`
  - `dayu.host.memory`
  - `dayu.host.compact_material`
  - `dayu.host.run_input`
  - result：`import smoke ok`
- `git diff --check`
  - pass。
- `git diff -- dayu/host/tool_trace.py`
  - empty。

## Coverage

命令：

```bash
source .venv/bin/activate && python -m pytest \
  tests/host/test_context_compact_events.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_context_budget.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compact_material.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_memory_projection.py \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_public_compact_smoke.py \
  --cov=dayu.host.evidence \
  --cov=dayu.host.accepted_result_projection \
  --cov=dayu.host.memory \
  --cov=dayu.host.durable.memory \
  --cov=dayu.host.compact_material \
  --cov=dayu.host.compact_pipeline \
  --cov=dayu.host.run_input \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

结果：

| 文件 | 覆盖率 |
|---|---:|
| `dayu/host/evidence.py` | 92% |
| `dayu/host/accepted_result_projection.py` | 94% |
| `dayu/host/memory.py` | 92% |
| `dayu/host/durable/memory.py` | 85% |
| `dayu/host/compact_material.py` | 86% |
| `dayu/host/compact_pipeline.py` | 94% |
| `dayu/host/run_input.py` | 88% |

总覆盖率 `89.38%`，`449 passed, 1 skipped`，`--cov-fail-under=80` pass。

## Source scans

Hard scans passed:

- `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` zero match.
- `str(exc).*ACCEPTED_EVIDENCE` zero match.
- `accepted_evidence_envelope_from_payload` zero match in `compact_material.py`, `durable/memory.py`, and `run_input.py`.
- `def _accepted_tool_evidence_content` zero match.
- `def _accepted_evidence_readable_text` zero match.
- `git diff -- dayu/host/tool_trace.py` empty.

Renderer/type distribution:

- `AcceptedToolEvidenceLLMMaterial`, `render_accepted_tool_evidence_for_llm(...)`, and `AcceptedEvidenceProducerEventRefMismatchError` are defined in `evidence.py`, a Host leaf contract without durable/projection imports.
- `accepted_result_projection.py` produces `AcceptedToolResultProjection.llm_material` and re-exports the material/renderer for the existing projection owner API.
- memory, compact material, compact pipeline, and run input consume the typed material/renderer rather than formatting their own evidence body.

Controller accepts the leaf placement as the correct import-cycle resolution: it keeps the value/renderer contract below durable projection code and preserves `accepted_result_projection` as producer owner.

## README decision

- `dayu/host/README.md` update is in scope: it records typed accepted evidence material, the unique four-line renderer, RunInputBuilder evidence routing, and Conversation Memory evidence projection boundaries.
- `tests/README.md` not changed: S3 expanded existing Host tests only.
- Root README and `dayu/README.md` not triggered.

## Propagation audit

```text
TOOL_CALL_REQUESTED + TOOL_RESULT_ACCEPTED
  -> evidence envelope codec
  -> AcceptedEvidenceProducerEventRefMismatchError on producer mismatch
  -> accepted_result_projection validates request/query/source/result
  -> AcceptedToolEvidenceLLMMaterial
     -> MemoryProjectionEvent.accepted_tool_evidence
        -> Conversation Memory renderer text
     -> RunInputMaterialBlock.accepted_tool_evidence
        -> CompactEvidenceBlock component fields
        -> EvidenceReadableItemVNext.response_text = material.result_text
     -> compact pipeline / ordinary protected raw tail / fallback RunInput renderer text
  -> Tool Trace consumes projection facts and keeps trace-local caps
```

Consistency conclusion:

- memory, compact material, compact pipeline, and run input now share one evidence renderer body.
- mismatch is typed and fail-closed with cause chain.
- compact material, durable memory, and run input no longer parse the evidence envelope directly.
- normal LLM-facing evidence text contains business-readable tool/query/source/result text and does not expose internal refs/digests/governance terms as evidence content.

## Remaining risks

- P3-E remains owner for accepted tool status fallback/raw outcome reconstruction.
- P3-J remains owner for global EventLog schema/taxonomy/DDL closed-set.
- S3 code review by AgentMiMo and AgentDS is still required before accepted slice commit.
