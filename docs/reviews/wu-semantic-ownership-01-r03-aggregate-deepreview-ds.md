# R03 Aggregate Deepreview — AgentDS

## Scope

- **Mode**: current changes（基于 accepted plan baseline `8c6ae966` 至当前 working tree 的完整 R03 组合行为）
- **Branch**: `phaseflow/host-issues-control`
- **Base ref**: `b1a0631f397967e7530b676a90ef7467d83a1817`（umbrella baseline）
- **Review range**: `8c6ae966..HEAD`（S1 `3e48f09e`、S2 `4b4696e5`、S3 `3f777753`） + 当前 unstaged F01-F03 fixes
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-ds.md`
- **Reviewed**: 2026-07-15 16:14 UTC+8
- **Truth sources**: `AGENTS.md`、`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`、`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`、accepted R03 plan `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`、Controller validation `docs/reviews/wu-semantic-ownership-01-r03-aggregate-controller-validation.md`
- **Included scope**: 75 files changed in `8c6ae966..HEAD`（含 16 production files, 9+ test files, smoke, docs）；重点走读 `dayu/host/tool_call_request.py`、`accepted_result_projection.py`、`payload_resolution.py`、`evidence.py`、`tool_trace.py`、`run_input.py`、`memory.py`、`durable/memory.py`、`compact_material.py`、`compact_pipeline.py`、`waiting.py`、`tool_runtime.py`、`_event_payload.py`、`durable/run_transition.py`、`dayu/runtime/__init__.py`
- **Uncommitted F01-F03 fixes**: `accepted_result_projection.py`（`_result_payload` cold descriptor resolution）、`compact_material.py`（`run_input_material_block` normalization bypass）、smoke/internal diagnostic `EventClass.CANONICAL_FACT` row selection + test fixtures
- **Excluded scope**: `dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/config/`（all audited no-diff per accepted plan §8）；`dayu/runtime/json_redaction.py`（deleted, source-scan verified）；docs/reviews 下 prior artifacts
- **Parallel review coverage**: 无。本路为独立单路 adversarial aggregate deepreview，与 AgentMiMo 并发执行，不共享 subagent 覆盖。

## 审查方法

1. 以 accepted plan §4 的 target contract 与 §6-11 的精确允许文件为真源基线。
2. 走读每条 canonical data flow（ordinary accept → TOOL_CALL_REQUESTED、awaiting accept → TOOL_CALL_REQUESTED + TOOL_AWAITING、wait resolution → TOOL_RESULT_ACCEPTED、shared projection → RunInput/Memory/Compact/Tool Trace）。
3. 对每条关键 `if` / `elif` / `match` / dispatch 展开入参 → 条件判断 → 下游调用 → 返回值/raise → 副作用。
4. 对每个 corruption/negative case（§4.5 matrix）逐条验证 fail-closed 行为。
5. 执行 adversarial failure pass 与 semantic ownership drift pass：检查 owner boundary、hot/cold integrity、canonical request/result typed selection、RunInput/Memory/Compact/LLM-ready Trace 同源、opaque provenance internal-only、LLM-facing 文本、安全保留项、deferred Issue 边界。
6. 核对 Controller validation 的 affected/full-suite/coverage/source scan 与真实 Doc/Web/Fins smoke 裁决。

## Findings

经完整 adversarial review，**未发现实质性问题**。

以下按审查维度逐项记录直接证据与结论：

### Correctness — 普通/awaiting 共享 request atom

**证据**：`dayu/host/tool_call_request.py` 定义唯一 `build_tool_call_requested_event_request` writer（line 150），接受 typed `AcceptedToolCallRequestAtomInput`（line 49）。Writer hard invariant（line 219-222）：
```python
arguments_json = _accepted_arguments_json(atom.accepted_arguments)
arguments_payload_digest = sha256_digest_json(arguments_json)
if arguments_payload_digest != atom.normalized_arguments_digest:
    raise HostPayloadReferenceError(...)
```
inline/descriptor 选择只由 `transaction.payload_inline_threshold_bytes` 决定（line 227），awaiting 无特殊分支。payload key set（lines 261-290）对 ordinary 与 awaiting 完全相同。

**调用方验证**：
- `tool_runtime.py` ordinary accept 路径通过显式 `AcceptedToolCallRequestAtomInput` 映射 `ToolFactAcceptCandidate` 各字段，尤其 `tool_identity_digest` 原样传入（不在 builder 重算）。
- `waiting.py` awaiting accept 路径同样通过显式 atom 映射 `ToolAwaitingAcceptCandidate`，`semantic_query_text=None`。

**结论**：共享 writer contract 已正确实现。

### Correctness — TOOL_AWAITING payload contract

**证据**：`_event_payload.py::tool_awaiting_payload` 签名变更（line 22-40）：接受 `tool_call_requested_event_ref: Mapping[str, JsonValue]` 替代了旧的 `normalized_arguments_digest` 与 `accepted_arguments`。payload 字段（lines 67-83）不再包含任何 `arguments_*` 或 `accepted_arguments*` 字段。

**源扫描验证**：
```text
rg -n 'accepted_arguments_source_digest' dayu/ tests/
→ 仅 tests/ 中有 negative assertion（确认字段不存在），production 零命中。
```

**结论**：`TOOL_AWAITING` 已从 arguments/digest 副本变为 governance-only + request link。

### Correctness — wait-resolution source Attempt execution identity

**证据**：`durable/run_transition.py` 两处调用 `_waiting_tool_result_event_request` 均传入 `source_attempt=source_attempt`（lines 1791, 1951）。Writer 内部（line 3765-3766）：
```python
attempt_id=source_attempt.attempt_id,
execution_id=source_attempt.execution_id,
```
不再硬编码 `execution_id=None`。

`_invalid_waiting_resolution_precondition` 新增不变量（line 5363）：
```python
or wait_record.execution_id != source_attempt.execution_id
```
不一致时返回 `INVALID_STATE`，在任何 append/state mutation 前终止。

`accepted_result_projection.py::_request_row_matches_result`（line 503-520）保持 request/result `session/run/attempt/execution` strict equality，不恢复 `result.execution_id is None` 放行。

**结论**：wait-resolution durable transition 正确写入 suspended source Attempt 的 execution identity。

### Correctness — F01 fix（Compact accepted evidence block 保留 shared renderer exact text）

**证据**：`compact_material.py::run_input_material_block`（line 807-811）：
```python
material_text = (
    text
    if accepted_tool_evidence is not None
    else normalized_material_text(text)
)
```
当 `accepted_tool_evidence is not None` 时，跳过 `normalized_material_text`（折叠连续空白），保留唯一 shared renderer 的 exact text。

`_accepted_tool_evidence_delta_blocks`（line 2580）传入：
```python
text=render_accepted_tool_evidence_for_llm(projection.llm_material),
...
accepted_tool_evidence=projection.llm_material,
```
同一次 `render_accepted_tool_evidence_for_llm` 调用结果同时进入 `text` 和 `accepted_tool_evidence`。`RunInputMaterialBlock.__post_init__`（line 294-297）校验 `text == render_accepted_tool_evidence_for_llm(accepted_tool_evidence)`，确保证据块与 shared renderer 同源。

新测试 `test_pre_dispatch_evidence_preserves_shared_renderer_exact_whitespace`（`test_compact_material.py` line 575）注入含重复空白的 typed outcome，验证 `block.text == expected_text` 且 `normalized_material_text(expected_text) != expected_text`，覆盖 real Web result 的 whitespace-preserving 场景。

**结论**：F01 修复正确，evidence block 保留 shared renderer exact text。

### Correctness — F02 fix（shared accepted-result projection 区分 hot inline 与 cold descriptor）

**证据**：`accepted_result_projection.py::_result_payload`（line 289-311）新版逻辑：
```python
if fallback_payload.get(_FIELD_RAW_TOOL_OUTCOME) is not None:
    return fallback_payload, ()           # inline raw outcome
if envelope is None:
    return fallback_payload, ("accepted_evidence_envelope_missing",)
# cold resolution via envelope → descriptor
try:
    return (event_payload_object_for_result_ref(...), ())
except HostDurableError:
    return (None, (_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE,))
```

关键变更：不再使用 `resolved_payload_available`（"EventLog hot payload 已读取"）作为"result 已解析"的代理信号。直接检查 `raw_tool_outcome` 字段存在性决定是否需要冷解析。

新测试 `test_projection_resolves_hot_payload_cold_result_and_keeps_inline_direct`（`test_accepted_result_projection.py` line 149）在同事务写入 hot/cold pair 与 inline result，验证 descriptor 路径正确解析冷 result 且 inline 路径不被误跟随。

新测试 `test_projection_hot_payload_cold_descriptor_corruption_fails_closed`（同文件 line 312）覆盖四种冷 descriptor 损坏场景（ref_mismatch/digest_mismatch/ref_missing/digest_missing），每种均断言 `projection.llm_material is None`、`result_text is None`、`status is LOST`。

**结论**：F02 修复正确，cold descriptor resolution 区分 hot inline 与 cold ref。

### Correctness — F03 fix（smoke post-run 诊断使用 typed EventClass.CANONICAL_FACT）

**证据**：`utils/smoke_host_public_r03_semantic_ownership.py` 新增 `_canonical_fact_rows`（line 1206）与 `_strict_accepted_request_atoms`（line 1179），按 `EventClass.CANONICAL_FACT` 选择 row：
```python
return tuple(
    row for row in rows
    if row.event_class is EventClass.CANONICAL_FACT
    and row.event_type == event_type
)
```
Engine `preview` 行与 Host `canonical_fact` 行可共享同一 `event_type`；只有 `EventClass.CANONICAL_FACT` 承诺 strict Host semantic contract。

新 assembly test `test_strict_diagnostic_collection_ignores_engine_previews`（`test_smoke_host_public_r03_semantic_ownership_assembly.py` line 271）构造三组 preview/canonical pairs（request/awaiting/result），断言 strict rows 只包含 canonical fact，preview 不进入 atom/projection 校验。

**结论**：F03 修复正确，typed `EventClass` 语义正确用于 row selection。

### Semantic ownership — opaque provenance internal-only

**证据**：
- `accepted_result_projection.py`：`AcceptedToolResultProjection` 无 `source_locator_refs` 字段；`_source_projection` 只消费 `raw_outcome` 中的 `citation` object，不读取 opaque refs。
- `compact_material.py`：所有 `PromptLocalProvenanceEntry` 构造中 `source_locator_refs=()`（lines 1516, 1542, 1573, 2792, 2830）—— opaque refs 不进入 LLM-facing provenance。
- `run_input.py`：无 `source_locator_refs` 或 `OpaqueEvidenceRef` 引用。
- `memory.py`：无 `source_locator_refs` 或 `OpaqueEvidenceRef` 引用。

**源扫描验证**：
```text
rg -n '_INTERNAL_SOURCE_REF_KINDS|_readable_ref_text|OpaqueEvidenceRef' \
  dayu/host/accepted_result_projection.py dayu/host/run_input.py \
  dayu/host/memory.py dayu/host/compact_material.py dayu/host/tool_trace.py
→ 零命中。
```

`OpaqueEvidenceRef` 只留在 `dayu/host/evidence.py`（internal envelope/audit owner）与 `dayu/host/durable/`（codec owner），不进入共享 LLM material 或四个消费者的渲染路径。

**结论**：opaque refs 已严格限制在 internal provenance/audit owner，不进入 LLM-facing source。

### Four-consumer fail-closed on missing material

**证据**：
- `durable/memory.py` line 426：`if projection.llm_material is None: raise HostDurableError(...)`
- `memory.py::_selected_evidence_text` line 1699：`if material is None: raise HostDurableError(...)`
- `compact_material.py::_accepted_tool_evidence_delta_blocks` line 2570：`if projection.llm_material is None: raise HostDurableError(...)`
- `compact_material.py::_pack_evidence_blocks` line 2751：`if block.accepted_tool_evidence is None: raise HostDurableError(...)`
- `tool_trace.py` line 1111：`if projection.llm_material is None: raise HostDurableError(...)`
- `run_input.py` line 3144：`if accepted_tool_projection.llm_material is None: raise HostDurableError(...)`
- `run_input.py::_fallback_message_from_material_block` line 2925：`if block.accepted_tool_evidence is None: raise HostDurableError(...)`

全部四个消费者（Memory、Compact、Tool Trace、RunInput）对 canonical accepted result 缺 typed LLM material 的状态 fail closed，不走 fallback/limited signal/skip。

**结论**：四消费者 fail-closed propagation 已正确闭合。

### LLM-facing 文本

**验证项**：
- `fetch_more` schema 的 `description`、`cursor`/`scope_token`/`limit` 参数说明已补全（S2 owner 修正）。
- `fetch_web_page.url` 参数说明已补全（S2 owner 修正）。
- Fins 九个 read tool 的 `ticker`/`document_id` 共用说明已补全（S2 owner 修正）。
- `evidence.py::ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` = `"该工具结果未提供业务来源。"` —— 业务中性，不声称 Host 做过安全判断。
- `render_accepted_tool_evidence_for_llm` 四行渲染保留中文业务标签（"工具名称："/"查询语义："/"业务来源："/"工具结果："）。
- `_query_projection` 缺失 semantic query 时序列化 canonical args：`f"参数：{canonical_json_dumps(atoms.arguments_json)}"` —— 业务可读，不暴露内部 ref/digest。
- Tool Trace `business_source_text`/`business_source_state` 从 shared projection 映射（lines 1303-1304），state 复用 `AcceptedToolResultSourceState.available|unavailable`。

**结论**：LLM-facing 文本符合 AGENTS.md 约束，无内部治理标识伪装为业务事实。

### 安全保留项与 deferred Issue 边界

**验证项**：
- 无统一 tool authorization 框架：`waiting.py::authorization_claims=()`（line 1446）是既有空 claims，不是新授权框架。
- 无 Issue #177（Doc output continuation wiring）。
- 无 Issue #178（storage-state lifecycle）。
- 无 Issue #142（workspace migration）。
- 无 Issue #151（write/assets）。
- 无 Issue #175（Fins Docling process isolation）。
- DNS/peer、path containment、symlink、resource budget、atomic/process fencing 均未修改。

**结论**：deferred Issue 边界完整保留，未引入统一 tool authorization。

### 静态质量

**验证项**：
- 关键生产文件零 `hasattr`/`getattr` 使用。
- 已删除符号源扫描：`llm_safe_replay_arguments`、`arguments_summary_unsafe`、`redact_sensitive_json_fields`、`json_redaction`、`_SENSITIVE_KEY_FRAGMENTS`、`accepted_arguments_source_digest`（production 零命中；tests 仅有 negative assertion）。
- `dayu/runtime/json_redaction.py` 全模块已删除；`dayu/runtime/__init__.py` 只更新 docstring。
- 无兼容性 re-export、wrapper、facade 或 legacy fixture。

**结论**：代码质量符合 AGENTS.md 编码硬约束。

### Controller validation 核对

- affected matrix：933 passed, 2 skipped, 3 warnings（edgar 弃用提示）—— 与本路独立代码审查一致。
- pyright：0 errors, 0 warnings, 0 informations —— 与本路扫描一致。
- 全量六域：4235 passed, 3 skipped, 5 deselected, 2 failed —— 已确认两个失败为隔离 green 的既有 logging-state 污染，不在 R03 changed owner 范围。
- 单文件覆盖率全部 ≥ 80%（最低 `fins_tools.py` 80%，最高 `_event_payload.py` 98%）—— 与 Controller 报告一致。
- 真实 public smoke：六轮 ROUND_PASS + requests=5 accepted_results=5 explicit_citations=1 —— 与 Controller 独立验证一致。
- sentinel closure tests：`test_opaque_provenance_round_trips_but_stays_out_of_projection`、`test_same_accepted_result_has_equivalent_consumer_projection`、`test_run_input_messages_use_explicit_citation_and_hide_opaque_refs` 全部通过。

**结论**：Controller validation 证据与本路独立代码审查一致，无矛盾。

### 残余观察（非 R03 finding）

以下为沿代码路径走读发现的 minor observations，不构成 correctness/owner/safety defect，仅记录供后续参考：

1. **`compact_material.py:2571` 错误消息语义不完全精确**：
   - 代码：`if projection.llm_material is None: raise HostDurableError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")`
   - `llm_material` 为 `None` 可能是 `tool_name is None` 或 `result_text is None` 两种情况；消息只说 `raw_tool_outcome is missing` 不完全覆盖 `tool_name` 缺失场景。当前 `tool_name` 从 envelope 读取（有 envelope 时必存在），因此实际上只可能是 `result_text` 缺失，消息语义对当前路径成立。属于 minor diagnostic text precision，不构成 correctness defect。
   - **分类**：非 R03 baseline observation（不进入 finding）。

2. **`run_input.py:3481` 与 `project_accepted_tool_result` 内部 payload 重读**：
   - `_payload_object(tool_result_event)` 只解析 inline `payload_json`，不跟随 `payload_ref` descriptor；若未来 wait-resolution result 使用 cold descriptor（当前不触发），line 3481 会得到不完整 payload，而 line 3482 `project_accepted_tool_result` 内部 `event_payload_object` 会正确解析。两条路径不存在数据不一致的实际 risk（wait-resolution result 始终 inline），但调用方与 projection 内部分别使用不同 payload reader 是微小的技术债。
   - **分类**：非 R03 baseline observation（不进入 finding）。

## Open Questions

无。

## Residual Risk

- 全量六域的两个 logging-order failure（`test_sec_request_debug_logs_success_response`、`test_configure_does_not_touch_root_by_default`）已确认为既有 Web smoke 全局 logging-state 污染，不在 R03 changed owner 范围内。Controller 已记录此 observation 且明确不接受为 R03 finding。建议在后续 WU 中由 Web smoke owner 修复全局状态污染。
- macOS coverage run 对 Web/Fins 各排除了 6 个真实子进程用例（因 NumPy/Pandas `spawn` pickling identity 问题）；这些用例在无 instrumentation 的完整文件测试中分别通过（Web `194 passed, 1 skipped`，Fins `65 passed`）。对 R03 aggregate 的正确性不构成 residual risk，但若未来修改涉及子进程边界的行为，需要额外验证。
- 本 deepreview 未覆盖 `dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/config/` 的内部实现细节（均已在 accepted plan §8 中审计为 compliant/no-diff）。若后续 WU 修改这些层，需要独立 deepreview。

## Final Verdict

- **总体结论**：**PASS**
- **Accepted findings**：0
- **Blocking open questions**：0
- **Minor observations**：2（`compact_material.py:2571` 诊断消息精度、`run_input.py:3481` payload reader 技术债）。两条均非 accepted finding，不构成 correctness/owner/safety defect，不要求当前 R03 fix，不阻塞 R03 accepted local commit。
- **R03 completion gate**：本路 AgentDS aggregate deepreview 对完整 R03 组合行为（S1/S2/S3 accepted commits + F01-F03 working-tree fixes）返回 PASS / ZERO MATERIAL FINDINGS。R03 accepted local commit 与下一 gate 授权等待 Controller 裁决。
