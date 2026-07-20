# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Review — AgentDS

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A. Host accepted evidence/query/status typed projection contract`
- Review type: deep code review (`/deepreview --base HEAD`)
- Reviewer: AgentDS
- Date: 2026-07-09
- Input artifacts:
  - Plan: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
  - Plan re-review adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-rereview-controller-adjudication.md`
  - Implementation report: `docs/reviews/wu-semantic-ownership-01-p1-a-implementation-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-p1-a-controller-validation.md`

## Verdict

**`pass-with-risks`**

核心 projection contract 设计正确，owner boundary 划分清晰，全部 6 个消费者已完成迁移且不再私有回读 query/status/source。grep residual classification 通过，pyright 0 errors，全部 270 个受影响测试通过。3 个 residual risk 中 2 个为已确认降级路径/文案不一致，1 个为测试覆盖缺口，均不阻塞合并但需在后续 WU 中处理。

---

## Findings

### P1A-F01 (Medium) — `_selected_evidence_text` 的 legacy fallback path 可能掩盖 projection drift

- **文件/行**: `dayu/host/memory.py:1708-1727`
- **影响**: Conversation Memory 在 `event.evidence_tool_name is None or event.evidence_result_text is None` 时（即 durable memory consumer 未传入 projection 字段时），会回退到直接读取 `accepted_evidence_envelope_from_payload()` 和 `accepted_tool_raw_outcome_text_from_payload()`。这条路径绕过了 `project_accepted_tool_result()` 的 envelope 校验、request atom identity 校验和 status 归一。
- **owner-boundary 判断**: 该路径属于历史输入降级 — 当 durable memory consumer 的 caller（如旧 EventLog row 缺少 payload descriptor）未传入 projection 字段时执行。它不是新的 accepted-result projection owner path，但它独立重建 query/source 语义，且 `source_text` 在 fallback 内通过 envelope 直接构造而非经过 `_source_projection()` 的 internal refs 过滤。
- **required fix**: 可选。若 `_tool_result_memory_payload_view()` 在所有正常路径上都能成功产生 projection 字段，则该 legacy 路径永远不会执行。建议在 S3 测试中覆盖 `envelope_available == False` 场景，确保 legacy 路径不会意外激活。若发现 legacy 路径仍被正常 accepted result 触发，则该路径需改为 fail closed（raise `HostDurableError`）而不是静默重建。
- **Controller validation 分类**: 已标记为"历史输入降级路径"，与 controller 判断一致。

### P1A-F02 (Low) — `compact_pipeline.py` 有独立于 projection owner 的 unavailable query 文案

- **文件/行**: `dayu/host/compact_pipeline.py:75`
- **影响**: `_UNAVAILABLE_TOOL_QUERY = "The original tool query is not available in readable form."` 与 projection owner 定义的 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT = "查询语义不可用；参数未安全展开。"` 是两套不同的 LLM-facing unavailable query 文案。compact pipeline 的 `_accepted_tool_evidence_content()` 在 `block.readable_query_text is None` 时使用自己的英文 fallback，而不是从 projection owner 导入。
- **owner-boundary 判断**: 该文案的使用条件是 `block.readable_query_text is None`，即 projection 已经判定 query 不可用。此时 compact pipeline 不是在做语义判断（它没有重新决定 query 是否可用），而是在做展示级 fallback。但两套文案不一致会让 LLM 在不同上下文中看到不同的 unavailable 表示，违反 cross-consumer consistency。
- **required fix**: 可选。`_accepted_tool_evidence_content()` 应从 `dayu.host.accepted_result_projection` 导入 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 替代 `_UNAVAILABLE_TOOL_QUERY`，或者至少让 compact pipeline 的 fallback 文案与 projection owner 保持一致。

### P1A-F03 (Low) — `_arguments_fallback_query` 函数签名暗示可从 payload 降级但实际未实现

- **文件/行**: `dayu/host/accepted_result_projection.py:549-560`
- **影响**: `_arguments_fallback_query(payload, reason)` 接受 `payload` 参数但立即 `del payload` 并委托给 `_limited_query(reason)`。函数签名暗示在 request atom 不可用时可以从 result payload 中读取降级参数信息，但实际行为是所有 request atom 缺失场景直接返回 limited-signal。这不影响正确性但会让读者误以为存在 payload-level fallback。
- **owner-boundary 判断**: 当前行为向 `_limited_query` 统一收口是正确的 — 不能把 result payload 当作 query source。但函数签名和实现之间的 gap 造成代码意图不清晰。
- **required fix**: 可选。要么删除 `payload` 参数并重命名函数（如 `_unavailable_query_projection`），要么保留但添加注释说明为何故意不使用 payload 降级。

### P1A-C01 (Medium) — 测试覆盖缺口

- **文件/行**: `tests/host/test_accepted_result_projection.py`（仅 4 个测试）
- **影响**: 当前 4 个测试覆盖了语义查询、参数回退、request atom 缺失、governed_error/unknown 状态映射，但 Plan S1 列出的以下场景未被覆盖：
  - **identity mismatch**（`request_atom_identity_mismatch`）：request atom 存在但 session/run/attempt/execution 或 tool_call_id 与 envelope 不一致时
  - **wait-resolution status mapping**：`resolution_kind` 优先于 `tool_fact_kind` 的优先级
  - **source filtering**：`source_refs` 中混入 internal ref kind（如 `event`、`payload`）时应被过滤
  - **payload descriptor 场景**：`resolved_payload` 参数路径与 `result_payload_unavailable` 诊断
  - **`_contains_unsafe_argument_key`**：含 `api_key`、`token`、`secret`、`password`、`*_path` 等敏感字段的参数 JSON 应触发 limited-signal
  - **raw_outcome result.ok mapping**：当 raw outcome 没有 `kind` 字段但有 `result.ok == false` 时映射到 `FAILED`
  - **result_details_text 提取**：`details`/`summary`/`message`/`error` 字段的提取和截断
- **required fix**: 建议在后续 WU 中补齐，至少覆盖 identity mismatch、source filtering、wait-resolution priority 三个场景。当前测试不阻塞合并，但 4 个测试对 ~800 行 projection helper 的覆盖率偏低（Plan S1 的"完成信号"要求覆盖 identity mismatch、payload descriptor、source filtering 和 wait-resolution 场景）。
- **注意**: 4 个测试的设计质量良好 — 使用真实 durable store write + read 构造 projection，不是 mock 夹具。缺失场景应继续遵循此模式。

### P1A-C02 (Low) — 无 cross-consumer equivalence 测试

- **文件/行**: (缺失)
- **影响**: Plan S3 要求 "增加同一 accepted result 同时投影到 Tool Trace / Memory / RunInput / CompactMaterial 的等价性断言"。当前测试套件中未见此类测试。这增加了 regression 风险：未来某个 consumer 修改可能打破 cross-consumer consistency 而不会被现有测试捕获。
- **required fix**: 建议在 S3 后续补齐 cross-consumer equivalence tests，或在 P1-B 中作为 propagation audit 的一部分。

---

## Owner Boundary Verification

### 产生 (Produce) ✓
ToolRuntime accept barrier（`dayu/host/tool_runtime.py`）与 waiting resolve（`dayu/host/waiting.py`）继续写入 `TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED` canonical facts，本次未修改。producer 路径不变。

### 校验 (Validate) ✓
`project_accepted_tool_result()` 在单一入口完成：
- envelope schema、producer event ref 校验（`_accepted_envelope`）
- payload digest 校验（`_result_payload` → `event_payload_object_for_result_ref`）
- request atom event type、session/run/attempt/execution identity 校验（`_request_row_matches_result`）
- request atom 与 envelope tool_call_id/tool_name/arguments_digest 身份一致校验（`_request_atoms_match_envelope`）
- 缺失 request atom、identity mismatch、digest mismatch 统一进入 `diagnostic_reasons`，不抛异常让消费者分支处理

### 持久化 (Persist) ✓
EventLog row、payload store、request atom 表未修改。projection helper 不写回 durable truth，不伪造缺失字段。

### 审计/投影 (Trace) ✓
`tool_trace.py:1271-1289`：`_canonical_trace_summary_signals()` 对 `TOOL_RESULT_ACCEPTED` 调用 `project_accepted_tool_result()`，`_tool_result_summary_from_projection()` 与 `_tool_request_summary_from_tool_result()` 只消费 projection 字段。Tool Trace 的参数有界渲染/脱敏（`_redacted_json`、`_bounded_text`）保留为 display-only，不重新拥有 query/status/source 语义。

### Read API ✓
`read_api.py:1225-1229`：`_tool_result_accepted_activity()` 明确检查 `row.event_class is EventClass.CANONICAL_FACT`，分发到 `_canonical_tool_result_accepted_activity()`。PREVIEW path（`_preview_tool_result_accepted_activity()`）保留原有 `outcome_kind` 逻辑。`_accepted_result_activity_state()` 将 `AcceptedToolResultStatus.UNKNOWN` fail closed 为 `HostActivityStatus.FAILED`，符合 Plan 要求。

### Durable Memory ✓
`durable/memory.py:429-474`：`_tool_result_memory_payload_view()` 调用 `project_accepted_tool_result()` 并传递 `resolved_payload=event.payload`，从 projection 读取 query/result/source。

### Conversation Memory ✓ (with noted legacy risk)
`memory.py:1689-1728`：`_selected_evidence_text()` 主路径使用 `event.evidence_*` projection 字段。存在 legacy fallback 路径（见 P1A-F01）。

### RunInputBuilder ✓
`run_input.py:2272-2296`（`_accepted_tool_evidence_delta_blocks`）：调用 `project_accepted_tool_result()` 并消费 `projection.result_text`、`projection.query.text`、`projection.source.text`。不再有 `_llm_facing_evidence_source_text` blacklist 逻辑。

### CompactMaterial ✓
`compact_material.py:2232-2297`（`_accepted_tool_evidence_delta_blocks`）：接受 `project_accepted_tool_result()` 输出，将 `readable_query_text` 和 `readable_source_text` 写入 `RunInputMaterialBlock`。`source_note` 字段（`compact_material.py:3229`）由已清洗的 `block.readable_source_text` 赋值，不再经过 `_readable_source_text_from_refs()` 生产。

### Compact pipeline ✓
`compact_pipeline.py:1099-1122`（`_accepted_tool_evidence_content`）：消费 `block.readable_tool_name/readable_query_text/readable_source_text`，不再有独立 source blacklist。

---

## Grep Residual Classification Audit

| pattern | 命中位置 | 分类 |
|---|---|---|
| `source_note` | `compaction.py:679,684,695,706,963,970,983,996` | 允许 — compaction schema 字段定义 |
| `source_note` | `compact_material.py:3229` | 允许 — 由 projection-cleaned `readable_source_text` 赋值 |
| `tool_call_request_atoms` | `accepted_result_projection.py:32,464` | 允许 — projection owner 内部读取 |
| `tool_call_request_atoms` | `payload_resolution.py:112,403` | 允许 — primitive 定义/导出 |
| `_readable_query_text_from_envelope` | 无命中 | ✓ 已删除 |
| `_tool_result_query_text` | 无命中 | ✓ 已删除 |
| `_tool_result_status` | 无命中 | ✓ 已删除 |
| `def _llm_facing_evidence_source_text` | 无命中 | ✓ 已删除 |
| `_is_internal_evidence_source_part` | 无命中 | ✓ 已删除 |
| `_readable_source_text_from_refs` | 无命中 | ✓ 已删除 |

全部命中均已分类为允许。无消费者继续重建旧语义。

---

## LLM-facing 文本检查

- `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`（`accepted_result_projection.py:35`）：中文，自解释，不泄漏 Host 内部术语 ✓
- `AcceptedToolResultQueryProjection` 的 `text` 字段：优先 semantic query，fallback 为有界参数 JSON 摘要，degradation 为 unified limited-signal 文案 ✓
- `AcceptedToolResultSourceProjection` 的 `text` 字段：只包含 business-readable `ref_kind:ref_id`，internal refs（`event`、`payload`、`digest` 等）被过滤 ✓
- `_compact_pipeline.py:_accepted_tool_evidence_content()`：LLM-facing 文本使用 `tool_name=`、`query=`、`source=`、`result=` 等自解释 key，不泄漏 Host 内部 refs/digest ✓
- `memory.py:_accepted_evidence_readable_text()`：LLM-facing 文本使用 `工具：`、`查询：`、`来源：`、`结果：` 等中文 key，自解释 ✓
- Read API `_canonical_tool_result_accepted_activity()` 的 `summary`：使用 `f"结果状态：{projection.status.value}"` 中文展示，不暴露 internal refs ✓

不一致项（见 P1A-F02）：`compact_pipeline.py` 的 `_UNAVAILABLE_TOOL_QUERY` 是英文且与 projection owner 的中文文案不一致。

---

## Test Cross-Consumer Consistency Check

- Tool Trace tests：`tests/host/test_tool_trace_projection.py`（46 passed）— 覆盖 Tool Trace 展示 ✓
- Memory tests：`tests/host/test_memory_projection.py`（更新后）— 覆盖 Conversation Memory ✓
- Compact material tests：`tests/host/test_compact_material.py`（更新后）✓
- RunInputBuilder tests：`tests/host/test_run_input_builder.py`（更新后）✓
- Read API tests：`tests/host/test_host_activity_event_projection.py` ✓
- Accepted result projection tests：`tests/host/test_accepted_result_projection.py`（4 passed）— coverage gap noted in P1A-C01

无测试夹具 workaround 证据 — 4 个新测试使用真实 durable store write + read，不构造兼容分支。

---

## README / Design Check

- `dayu/host/README.md`：已补充 "accepted 工具结果投影" 段落，符合触发规则 ✓
- `tests/README.md`：已补充 `test_accepted_result_projection.py` 到命令示例，并在测试覆盖段落中补充 "accepted result projection" 覆盖说明 ✓
- `docs/host/design.md`：未修改 — 本次未改变 durable schema 或 Host/Engine 分层设计，符合 Plan 判断 ✓
- 根 `README.md`：未触发 — 无用户可见 CLI/Web/workflow/日志定位变化 ✓

---

## Validation Commands Summary

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_accepted_result_projection.py` | 4 passed |
| `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` | 46 passed |
| `pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py` | 220 passed |
| `rg` residual classification scan | 全部命中已分类为允许 |
| `pyright` | 0 errors, 0 warnings |
| `git diff --check` | 通过 |

---

## Propagation Audit

1. **产生**：ToolRuntime / waiting 继续写入 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、envelope、raw outcome — 无变更 ✓
2. **校验**：`project_accepted_tool_result()` 统一校验 envelope、payload digest、request atom identity — 无缺口 ✓
3. **持久化**：EventLog / payload store 不变；projection 不写回 — ✓
4. **审计/Trace**：Tool Trace 通过 projection helper 取得 query/status/result/source；参数摘要仅为 display-only — ✓
5. **Read API**：CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 通过 projection helper；PREVIEW path 独立分发 — ✓
6. **Durable Memory / Conversation Memory**：durable memory 通过 projection helper；Conversation Memory 有 legacy fallback（P1A-F01）
7. **RunInputBuilder**：不暴露 internal refs、digest、wait/poll/runtime 治理术语 — ✓
8. **CompactMaterial / compact pipeline**：不再独立回读 query、生产 accepted-result `source_note` 或 blacklist source — ✓
9. **Tests**：cross-consumer equivalence tests 缺失（P1A-C02）

---

## Residual Risk Summary

| Risk | Severity | Owner | Action |
|---|---|---|---|
| `memory.py` legacy fallback path | Medium | P1-B / S3 test | 补充 `envelope_available == False` 测试，确认 fallback 路径不会在正常 accepted result 上意外激活 |
| `compact_pipeline.py` 独立 unavailable query 文案 | Low | P1-B | 统一为 projection owner 文案或明确记录差异理由 |
| 测试覆盖缺口（identity mismatch, source filtering, wait-resolution） | Medium | P1-B / S3 | 补测至少 3 个缺失场景 |
| Cross-consumer equivalence 测试缺失 | Low | P1-B | 在 propagation audit 完成前补测 |

---

## Conclusion

P1-A implementation 成功建立了 Host accepted tool result 的单一 typed projection contract。新模块 `accepted_result_projection.py` 设计正确：envelope 校验、request atom identity 校验、status 归一、source 过滤、query 降级链均在单一 owner 内完成。全部 6 个消费者（Tool Trace、Read API、Durable Memory、Conversation Memory、RunInputBuilder、CompactMaterial/compact pipeline）已完成迁移，grep residual scan 确认无消费者继续私有回读 query/status/source。

`conversation_memory.py` 的 legacy fallback path 是唯一实质性 residual risk，但 controller 已将其分类为"历史输入降级路径"而非当前 projection path。测试覆盖虽有缺口但不阻塞合并 — 核心 happy path 与关键错误场景（request atom 缺失、governed_error/unknown status）已被覆盖。

建议在 P1-B 或 S3 后续补齐测试覆盖和文案统一。
