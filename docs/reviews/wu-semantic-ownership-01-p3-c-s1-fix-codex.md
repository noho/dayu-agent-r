# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Code Review Fix

## Gate 与结论

- Gate：P3-C S1 code-review fix。
- 修复范围：仅修 controller adjudication accepted 的 `P3-C-S1-CR-F01`、`P3-C-S1-CR-F02`、`P3-C-S1-CR-F03`。
- 结论：PASS。
- Blocking questions：0。
- 未执行：commit、push、PR、controller artifact 修改、S2/S3 实现。

## Root cause

### P3-C-S1-CR-F01

`compact_payload.parse_context_compacted_semantic_payload()` 已是 persisted accepted compact candidate 的 parser owner，但 nested label list 的唯一性仍依赖 typed candidate constructor。constructor 只知道自身字段语义，不知道 persisted JSON 的完整位置，因此 duplicate label 失败会丢失 `accepted_candidate.<section>[i].<labels>[j]` 这类 indexed path。

根因不是 fact 特例，而是 parser owner 缺少一个 path-aware、non-empty、unique text list helper。需要唯一性的 persisted candidate label/source-label 字段包括：

- `session_summary.source_labels`
- `evidence_backed_facts[*].evidence_labels`
- `evidence_backed_facts[*].source_labels`
- `answer_anchors[*].answer_source_labels`
- `forward_intents[*].source_labels`
- `reference_continuity_items[*].source_labels`
- `diagnostics[*].source_labels`

其中 `evidence_backed_facts[*].source_labels` 与 `diagnostics[*].source_labels` 按 typed contract 允许空 list，但 list 内元素仍必须是非空文本且不得重复；其它 source-label/evidence-label list 必须非空且唯一。

### P3-C-S1-CR-F02

invalid compact fact candidate 已经移动到 persisted parser boundary fail closed。`MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 不再有 producer，durable diagnostics DDL 的 reason allowlist 仍保留同一死治理词汇。

### P3-C-S1-CR-F03

`accepted_compact_business_texts()` 是 S2 budget integration 才需要的 traversal helper，S1 没有 production consumer。S1 保留它会形成 contract-only half product，并诱导提前落地 S2 budget 行为。

## Owner boundary

- 首次产生：`ConversationCompactOutputVNext` 经 Host accept barrier 写入 `CONTEXT_COMPACTED.accepted_candidate`。
- 校验 owner：`dayu.host.compact_payload.parse_context_compacted_semantic_payload()`。
- 持久化真源：canonical `CONTEXT_COMPACTED` EventLog payload 与 `accepted_candidate_digest`。
- 投影 owner：`ContextCompactedSemanticPayload.accepted_candidate`。
- 消费者：Conversation Memory、durable memory adapter、RunInput inline repair adapter。

本次修复落在 parser owner 与 durable diagnostic contract。未在 Memory、RunInput、测试夹具或展示层添加下游特例。

## 改动摘要

- `dayu/host/compact_payload.py`
  - 删除无 production consumer 的 `accepted_compact_business_texts()`。
  - 新增 `_required_unique_text_list(..., path=..., allow_empty=...)`，复用 `_required_text_list(..., path=...)` 后按 typed contract 做非空与唯一性检查。
  - 所有 persisted candidate nested label/source-label list 改走 path-aware unique helper。
  - list/object item 错误路径改为从 `accepted_candidate` 根开始，保留 indexed JSON path。
- `dayu/host/memory.py`
  - 删除 `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`。
- `dayu/host/durable/schema.py`
  - 删除 host memory diagnostics DDL allowlist 中的 `evidence_backed_fact_candidate_invalid`。
- `tests/host/test_context_compact_events.py`
  - 删除 S1-only `accepted_compact_business_texts()` 断言。
  - 新增 summary empty `source_labels` parser-owner path 回归。
  - 新增 fact `evidence_labels` / `source_labels` duplicate indexed path 回归。
  - 新增 `forward_intents[*].source_labels` duplicate indexed path 回归，证明修复不是 fact 特例。

## 测试命令和结果

- `source .venv/bin/activate && python -m pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q`
  - `259 passed in 1.38s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - `25 passed in 2.21s`
- import smoke：
  - `dayu.host`
  - `dayu.host.compact_payload`
  - `dayu.host.memory`
  - `dayu.host.run_input`
  - `dayu.host.durable.schema`
  - 结果：`import smoke ok`
- `git diff --check`
  - 通过。

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

总结果：`259 passed`，总覆盖率 `89.07%`，`--cov-fail-under=80` 通过。

## Source scan

- Dead enum scan：
  - 命令：`rg -n "EVIDENCE_BACKED_FACT_CANDIDATE_INVALID|evidence_backed_fact_candidate_invalid" dayu tests || true`
  - 结果：零匹配。
- Contract-only helper scan：
  - 命令：`rg -n "accepted_compact_business_texts" dayu tests || true`
  - 结果：零匹配。
- S2/S3 新 contract 提前落地 scan：
  - 命令：`rg -n "estimate_post_compact_budget|AcceptedToolEvidenceLLMMaterial|render_accepted_tool_evidence_for_llm|accepted_compact_business_texts" dayu tests || true`
  - 结果：零匹配。

说明：`compact_material.py` 中既有 `_previous_compacted_*_vnext` 与 `run_input.py` 中既有 `_compact_material_source_ref` 仍是 S2 residual，不是本 fix 新增；本 gate 未实现 S2/S3 新 contract。

## README decision

触发规则：本次修改 `dayu/host/`。

已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。README 已说明 persisted accepted compact candidate 由唯一 strict typed read boundary 恢复，非法 shape、digest 或 enum fail closed。此次只是：

- 补 parser diagnostic path 精度；
- 删除 dead diagnostic reason；
- 删除无 consumer helper。

这些不改变 Host 稳定开发接口、公共契约或架构说明，因此不修改 README。

`tests/README.md` 未触发实质更新：只增加同一测试文件内的 parser regression case，未新增测试层级、公共测试工具或常用命令职责。

## Propagation audit

### Persisted candidate label/source-label path

```text
CONTEXT_COMPACTED.accepted_candidate
  -> compact_payload.parse_context_compacted_semantic_payload()
     -> _required_unique_text_list(path="accepted_candidate.<section>[i].<label_field>")
        -> typed ConversationCompactOutputVNext constructor
        -> ContextCompactedSemanticPayload.accepted_candidate
           -> MemoryProjectionEvent.compacted_semantics
           -> Conversation Memory projection / snapshot / RunInput memory renderer
```

一致性结论：

- nested label/source-label duplicate 在 parser owner fail closed。
- optional fact/diagnostic source-label list 仍允许空 list；非 optional label list 在 parser owner 拒绝空 list。
- 错误路径保留完整 indexed JSON path，例如：
  - `accepted_candidate.evidence_backed_facts[0].evidence_labels[1]`
  - `accepted_candidate.evidence_backed_facts[0].source_labels[1]`
  - `accepted_candidate.forward_intents[0].source_labels[1]`
- 下游消费者只接收 typed candidate，不新增特例分支。

### Memory diagnostic reason

```text
invalid persisted compact fact candidate
  -> compact_payload parser ValueError
  -> projection boundary failure handling
  -> 不再生成 MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
```

一致性结论：

- dead enum member 已删除。
- durable schema reason allowlist 已同步删除同一值。
- source scan 对 production/test 均零匹配。

### S2 business text helper

```text
S1 persisted semantic parser
  -> typed candidate
  -> S2 才会与 context_budget.estimate_post_compact_budget() 原子实现 business text traversal
```

一致性结论：

- S1 不保留无 consumer traversal helper。
- 未添加假 consumer。
- 未复制 traversal 到其它 S1 consumer。

## Git diff scope check

本轮实际编辑文件：

- `dayu/host/compact_payload.py`
- `dayu/host/memory.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_context_compact_events.py`
- `docs/reviews/wu-semantic-ownership-01-p3-c-s1-fix-codex.md`

工作区仍显示进入本轮前已经存在的 S1 implementation 修改和未跟踪 review/cli-ci 文件，包括 `docs/cli_ci*` 与 `docs/reviews/code-review-20260710-*`。本轮未编辑这些禁触文件，也未修改 controller adjudication 文档。

## Remaining risk

- `covered by later approved slice`：S2 previous compacted view、ordinary duplicate compact renderer、post-compact budget helper 与 `context_budget.estimate_post_compact_budget()` 原子实现。
- `covered by later approved slice`：S3 accepted evidence typed material、唯一 LLM renderer 与 typed mismatch exception。
- `fixed in current slice`：nested candidate label duplicate 错误路径不精确。
- `fixed in current slice`：dead memory diagnostic reason。
- `fixed in current slice`：S1 contract-only `accepted_compact_business_texts()`。
- 未分类 residual risk：0。
