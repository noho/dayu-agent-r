# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Fix Controller Validation

## Gate 与结论

- Gate：P3-C S1 code-review fix controller validation。
- Agent artifact：`docs/reviews/wu-semantic-ownership-01-p3-c-s1-fix-codex.md`。
- Controller 结论：PASS。
- Blocking questions：0。

## Findings 状态

- `P3-C-S1-CR-F01`：fixed pending independent re-review。
- `P3-C-S1-CR-F02`：fixed pending independent re-review。
- `P3-C-S1-CR-F03`：fixed pending independent re-review。

## Scope 审计

本 gate 修复仍落在 S1 owner boundary：

- persisted compact semantic parser owner：`dayu/host/compact_payload.py`。
- Memory diagnostic vocabulary owner：`dayu/host/memory.py` 与 durable DDL reason allowlist `dayu/host/durable/schema.py`。
- parser owner 回归测试：`tests/host/test_context_compact_events.py`。

Controller 未发现 S2/S3 contract 提前落地。`accepted_compact_business_texts()` 已删除，S2 后续必须与 `context_budget.estimate_post_compact_budget()` 原子实现。

## Controller 独立验证

- `source .venv/bin/activate && python -m pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q`
  - `259 passed in 1.32s`
- `source .venv/bin/activate && python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - `25 passed in 2.12s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`
- import smoke：
  - `dayu.host`
  - `dayu.host.compact_payload`
  - `dayu.host.memory`
  - `dayu.host.run_input`
  - `dayu.host.durable.schema`
  - result：`import smoke ok`
- `git diff --check`
  - pass。

## Coverage

命令：

```bash
source .venv/bin/activate && python -m pytest \
  tests/host/test_context_compact_events.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compact_material.py \
  --cov=dayu.host.compact_payload \
  --cov=dayu.host.context_events \
  --cov=dayu.host.memory \
  --cov=dayu.host.durable.memory \
  --cov=dayu.host.run_input \
  --cov=dayu.host.durable.schema \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

结果：

| 文件 | 覆盖率 |
|---|---:|
| `dayu/host/compact_payload.py` | 80% |
| `dayu/host/context_events.py` | 93% |
| `dayu/host/durable/memory.py` | 86% |
| `dayu/host/durable/schema.py` | 92% |
| `dayu/host/memory.py` | 92% |
| `dayu/host/run_input.py` | 88% |

总覆盖率 `89.07%`，`259 passed`，`--cov-fail-under=80` pass。

## Source scan

- `rg -n "EVIDENCE_BACKED_FACT_CANDIDATE_INVALID|evidence_backed_fact_candidate_invalid" dayu tests`
  - zero match。
- `rg -n "accepted_compact_business_texts" dayu tests`
  - zero match。

## Propagation audit

- Nested label/source-label duplicate 语义：
  - `CONTEXT_COMPACTED.accepted_candidate`
  - `compact_payload.parse_context_compacted_semantic_payload()`
  - `_required_unique_text_list(path="accepted_candidate.<section>[i].<field>")`
  - typed `ConversationCompactOutputVNext`
  - `MemoryProjectionEvent.compacted_semantics`
  - Conversation Memory / durable adapter / RunInput consumers。
- Dead diagnostic vocabulary：
  - invalid persisted compact fact candidate now fails at parser boundary。
  - no `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` producer remains。
  - durable DDL allowlist no longer contains `evidence_backed_fact_candidate_invalid`。
- Business text helper：
  - S1 does not expose traversal helper without production consumer。
  - S2 remains owner for budget integration and business text traversal.

## Next gate

Proceed to P3-C S1 independent code re-review by AgentMiMo and AgentDS.
