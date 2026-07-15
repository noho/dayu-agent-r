# WU-SEMANTIC-OWNERSHIP-01 R03 Aggregate Re-Review — AgentDS

## Scope

- **Mode**: current changes（complete R03 aggregate re-review，非新 WU）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `8c6ae966`（R03 accepted plan commit）
- **Review range**: `8c6ae966..HEAD`（S1 `3e48f09e`、S2 `4b4696e5`、S3 `3f777753`、aggregate transition `d6a1ef97`）+ current working tree F01-F03 unstaged fixes
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r03-aggregate-rereview-ds.md`
- **Reviewed**: 2026-07-15 16:47 UTC+8
- **Truth sources**: `AGENTS.md`、`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`、`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`、accepted R03 plan `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`
- **Controller artifacts**: `docs/reviews/wu-semantic-ownership-01-r03-aggregate-controller-validation.md`、`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-controller-adjudication.md`、`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-codex.md`、`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-controller-validation.md`
- **Included scope**: 75 files in accepted range + 5 aggregate artifacts = 80-path protected set；重点走读 working tree 8 个 unstaged modified files 与完整 S1-S3 + F01-F03 组合数据流
- **Excluded scope**: credential/raw config（明确禁止）、`dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/config/`（accepted plan §8 已审计 no-diff）

## 审查方法

1. 独立复算 80-path protected proof：ordered path SHA、content-record aggregate SHA、status/path-record aggregate SHA、full worktree status
2. 独立复核 F01-F03 四个 working tree fix 的正确性与闭合状态
3. 独立走读 canonical data flow：ordinary accept → TOOL_CALL_REQUESTED、awaiting accept → TOOL_CALL_REQUESTED + TOOL_AWAITING、wait resolution → TOOL_RESULT_ACCEPTED、shared projection → RunInput/Memory/Compact/Tool Trace
4. 独立执行 adversarial failure pass 与 semantic ownership drift pass
5. 独立源扫描：deleted symbols、opaque refs、unified tool authorization、Issue boundaries、LLM-facing 文本、安全保留项

## 80-Path Protected Proof 独立复算

### 复算方法

protected set = `git diff --name-only 8c6ae966..HEAD`（75 paths）+ 5 aggregate artifacts（aggregate-controller-validation、aggregate-deepreview-controller-adjudication、aggregate-deepreview-ds、aggregate-deepreview-mimo、aggregate-validation-fix-codex），按 `LC_ALL=C sort -u` 排序形成 80-path set。本 artifact 与 Controller validation artifact 不在创建前 protected set 中。

### 复算结果

| 检查项 | fix-codex 记录值 | 本路独立复算值 | 结论 |
|---|---:|---:|---|
| protected path count | `80` | `80` | `IDENTICAL / PASS` |
| ordered path SHA-256 | `75d464307db88470d1f8efcb9b302c9f18b3d3bc4396ca8bff5ae0ff4ee10e9a` | `75d464307db88470d1f8efcb9b302c9f18b3d3bc4396ca8bff5ae0ff4ee10e9a` | `IDENTICAL / PASS` |
| status/path-record aggregate SHA-256 | `8ee8baa8cd0e667ea08c106f904dd2bace5893cd3a8c51a130db8ba4680eeed5` | `8ee8baa8cd0e667ea08c106f904dd2bace5893cd3a8c51a130db8ba4680eeed5` | `IDENTICAL / PASS` |
| full status count (excluding 2 new artifacts) | `13` | `13` | `IDENTICAL / PASS` |
| full status SHA-256 (excluding 2 new artifacts) | `28db24213719dedede609d522455100396e776d4a10971a95a0ab3a0b9cf1850` | `28db24213719dedede609d522455100396e776d4a10971a95a0ab3a0b9cf1850` | `IDENTICAL / PASS` |
| staged path count | `0` | `0` | `IDENTICAL / PASS` |
| `git diff --check` | `PASS` | `PASS` | `IDENTICAL / PASS` |

### Post-proof 授权变更确认

fix-codex 创建后，仅存在以下 3 个 Controller 授权的 post-proof 变更：

1. **新增** `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-codex.md`（zero-change artifact，AgentCodex 唯一写入）
2. **新增** `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-controller-validation.md`（Controller validation artifact）
3. **修改** `docs/host/issues-implementation-control.md`（Controller 将 gate 从 "R03 aggregate validation" 更新为 "R03 aggregate deepreview re-review"）

80 个 protected path 的 ordered set、status/path aggregate、以及排除上述 3 项后的 full status count/SHA-256 均与 fix-codex 记录精确一致。**无 unauthorized protected target 漂移。**

## Findings

经完整独立 adversarial re-review，**未发现实质性问题**。

以下按审查维度逐项记录直接证据与独立验证结论：

### 1. F01 Fix 复核 — Compact accepted evidence block 保留 shared renderer exact text

**独立走读**：`dayu/host/compact_material.py:807-811`（working tree）：

```python
material_text = (
    text
    if accepted_tool_evidence is not None
    else normalized_material_text(text)
)
```

当 `accepted_tool_evidence is not None`（typed accepted evidence block）时跳过 `normalized_material_text`，保留 shared renderer exact text。`RunInputMaterialBlock.__post_init__` 校验 `block.text == render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)`，不允许 normalization 改写 renderer 输出。

**独立测试验证**：`test_pre_dispatch_evidence_preserves_shared_renderer_exact_whitespace`（`test_compact_material.py` line 1704+）构造含 `"first  result   keeps producer spacing"` 的 typed outcome，注入真实 `project_accepted_tool_result` → `render_accepted_tool_evidence_for_llm` pipeline，断言 `block.text == expected_text` 且 `normalized_material_text(expected_text) != expected_text`。

**结论**：F01 修复正确，状态 **CLOSED**。

### 2. F02 Fix 复核 — accepted-result projection 区分 hot inline 与 cold descriptor

**独立走读**：`dayu/host/accepted_result_projection.py:295-311`（working tree）：

```python
if fallback_payload.get(_FIELD_RAW_TOOL_OUTCOME) is not None:
    return fallback_payload, ()          # inline: raw outcome present
if envelope is None:
    return fallback_payload, ("accepted_evidence_envelope_missing",)
# cold descriptor resolution via envelope → result_ref
return event_payload_object_for_result_ref(...)
```

关键变更：不再使用已删除的 `resolved_payload_available` 布尔标志（该标志只证明 EventLog hot payload 已读取，不证明 cold result payload 已解析）。改为直接检查 `raw_tool_outcome` 字段存在性决定是否需要冷解析。

**独立源扫描**：`rg -rn 'resolved_payload_available' dayu/ tests/ --include='*.py'` → **零命中**。F02 的旧判断逻辑已彻底移除。

**独立测试验证**：
- `test_projection_resolves_hot_payload_cold_result_and_keeps_inline_direct`（`test_accepted_result_projection.py` line 821+）验证 hot/cold pair 与 inline result 在同一事务中正确区分
- `test_projection_hot_payload_cold_descriptor_corruption_fails_closed`（同文件 line 312+）覆盖四种冷 descriptor 损坏场景（`REF_MISMATCH`/`DIGEST_MISMATCH`/`REF_MISSING`/`DIGEST_MISSING`），每种断言 `projection.llm_material is None`
- `test_toolruntime_accept_barrier.py` 新增强断言（line 1061+）：verify large-payload descriptor 路径的 `projection.raw_outcome`、`projection.llm_material` 与 `result_text` 正确

**结论**：F02 修复正确，状态 **CLOSED**。

### 3. F03 Fix 复核 — smoke post-run 诊断使用 typed EventClass.CANONICAL_FACT

**独立走读**：`utils/smoke_host_public_r03_semantic_ownership.py` 新增两个辅助函数：

- `_canonical_fact_rows`（line 996+）：按 `EventClass.CANONICAL_FACT` 过滤 row，不按 event type 独立选择
- `_strict_accepted_request_atoms`（line 946+）：只对 canonical fact rows 调用 strict `tool_call_request_atoms` parser

原有 `_projection_observation_in_transaction` 中 awaiting_rows/result_rows 的收集也从裸 `event_type` 过滤改为 `_canonical_fact_rows(rows, event_type=...)`。

**独立测试验证**：`test_strict_diagnostic_collection_ignores_engine_previews`（`test_smoke_host_public_r03_semantic_ownership_assembly.py` line 271+）构造三组 PREVIEW/CANONICAL_FACT row pairs（request/awaiting/result），断言 strict rows 只包含 canonical fact，preview 不进入 atom/projection 校验。

**结论**：F03 修复正确，状态 **CLOSED**。

### 4. Shared request atom — ordinary/awaiting 同源验证

**独立走读**：`dayu/host/tool_call_request.py` 唯一 writer `build_tool_call_requested_event_request`（line 150）接受 typed `AcceptedToolCallRequestAtomInput`，写 `EventClass.CANONICAL_FACT`。Writer hard invariant（line 219-222）：

```python
arguments_json = _accepted_arguments_json(atom.accepted_arguments)
arguments_payload_digest = sha256_digest_json(arguments_json)
if arguments_payload_digest != atom.normalized_arguments_digest:
    raise HostPayloadReferenceError(...)
```

inline/descriptor 选择只由 `transaction.payload_inline_threshold_bytes` 决定，awaiting 无特殊分支。payload key set 对 ordinary/awaiting 完全相同。

**调用方验证**：
- `tool_runtime.py` ordinary accept 通过显式 `AcceptedToolCallRequestAtomInput` 映射 `ToolFactAcceptCandidate`
- `waiting.py` awaiting accept 同样通过显式 atom 映射 `ToolAwaitingAcceptCandidate`，`semantic_query_text=None`

**结论**：共享 writer contract 正确实现，ordinary/awaiting 同源。

### 5. TOOL_AWAITING payload — governance-only + request link

**独立走读**：`dayu/host/_event_payload.py:22-80`（`tool_awaiting_payload`）签名与 payload 字段均无 `arguments_*`、`accepted_arguments*` 或 `normalized_arguments_digest`。payload 只含 identity/awaiting metadata + `tool_call_requested_event_ref={event_id, event_sequence}` 显式链接 canonical request atom。

**独立源扫描**：`rg -n 'accepted_arguments_source_digest' dayu/ tests/` → production 零命中；仅 tests 中有 negative assertion（确认字段不存在）。

**结论**：`TOOL_AWAITING` 已从 arguments/digest 副本变为 governance-only + request link。

### 6. Wait-resolution execution identity

**独立走读**：`dayu/host/durable/run_transition.py` 两处调用 `_waiting_tool_result_event_request` 均传入 `source_attempt=source_attempt`。Writer 写入 `attempt_id=source_attempt.attempt_id`、`execution_id=source_attempt.execution_id`。`_invalid_waiting_resolution_precondition` 新增不变量 `wait_record.execution_id == source_attempt.execution_id`，不一致返回 `INVALID_STATE` 且在任何 state mutation 前终止。

**结论**：wait-resolution durable transition 正确写入 suspended source Attempt 的 execution identity。

### 7. 四消费者同源与 fail-closed 验证

| 消费者 | evidence 来源 | material 缺失处理 | 位置 |
|---|---|---|---|
| Durable Memory | `project_accepted_tool_result` → `projection.llm_material` | `HostDurableError` | `durable/memory.py:426-429` |
| Memory | `render_accepted_tool_evidence_for_llm(material)` via `_selected_evidence_text` | `HostDurableError` | `memory.py:1704-1706` |
| Compact | `render_accepted_tool_evidence_for_llm(projection.llm_material)` | `HostDurableError` | `compact_material.py:2570` |
| Tool Trace | `project_accepted_tool_result` → `_tool_result_summary_from_projection` | `HostDurableError` | `tool_trace.py:1111` |
| RunInput | `render_accepted_tool_evidence_for_llm(material)` | `HostDurableError` | `run_input.py:3146` |

所有消费者从同一 shared `AcceptedToolEvidenceLLMMaterial` 通过唯一 renderer `render_accepted_tool_evidence_for_llm` 生成 LLM-facing 文本。缺 material 时全部 fail closed（抛 `HostDurableError`），不走 skip/fallback/limited signal。

**结论**：四消费者同源、fail-closed propagation 正确闭合。

### 8. Opaque provenance internal-only

**独立源扫描**：

- `OpaqueEvidenceRef` 在 `accepted_result_projection.py`、`run_input.py`、`memory.py`、`compact_material.py`、`tool_trace.py` 五个 shared/LLM path 中 **零命中**
- `compact_material.py` 所有 5 处 `source_locator_refs` 均为空 tuple `()`
- `_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text` 在 active production/test 中 **零命中**

**结论**：opaque refs 已严格限制在 internal provenance/audit owner（`dayu/host/evidence.py`），不进入 LLM-facing source。

### 9. LLM-facing 文本

**独立验证**：
- `render_accepted_tool_evidence_for_llm` 四行渲染保留中文业务标签
- `_source_projection` 只从 completed+ok outcome 的 citation 提取 producer-owned 业务来源
- 缺 citation 时使用唯一业务中性文案 `"该工具结果未提供业务来源。"`
- 旧 safe/fallback 文案（`"工具证据不可用；缺少可安全展示"` 等）在 active production/test 中 **零命中**
- `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 包含 16 个内部治理标识，禁止进入 LLM-facing system content

**结论**：LLM-facing 文本符合 AGENTS.md 约束，无内部治理标识伪装为业务事实。

### 10. 安全保留项与 deferred Issue 边界

**独立源扫描验证**：

| 检查项 | 扫描范围 | 结果 |
|---|---|---|
| 统一 tool authorization | `dayu/ tests/ --include='*.py'` | 零命中 |
| `llm_safe_replay_arguments` / `arguments_summary_unsafe` / `safe_arguments` | `dayu/ tests/ --include='*.py'` | 零命中 |
| `redact_sensitive_json_fields` / `json_redaction` / `JSON_REDACTION_MARKER` | `dayu/ tests/ --include='*.py'` | 零命中 |
| `resolved_payload_available` | `dayu/ tests/ --include='*.py'` | 零命中 |
| Issue 142 / 151 / 175 / 177 / 178 | `dayu/ --include='*.py'` | 零命中 |
| `dayu/runtime/json_redaction.py` | protected content record | `ABSENT` |
| `_INTERNAL_SOURCE_REF_KINDS` / `_readable_ref_text` | `dayu/ tests/ --include='*.py'` | 零命中 |
| DNS/peer、path containment、symlink、resource budget、atomic/process fencing | R03 changed files | 未修改 |

**结论**：安全机制保持，deferred Issue 边界完整，未引入统一 tool authorization。

### 11. 静态质量

- 关键生产文件零 `hasattr`/`getattr` 使用
- 无兼容性 re-export、wrapper、facade 或 legacy fixture
- `accepted_arguments_source_digest` 在 production 中零命中（仅 tests 有 negative assertion）
- 代码质量符合 AGENTS.md 编码硬约束

### 12. Controller validation 独立复核

本路独立复核确认：
- 80-path protected proof 与 Controller 独立复算一致
- `git diff --check` 通过
- 已删除符号源扫描与本路独立扫描一致
- F01-F03 全部保持 CLOSED
- 初轮 aggregate deepreview 的四项 reviewer observation 仍然为 `NO_CURRENT_DEFECT` / `HYPOTHETICAL_ONLY` / `STYLE_OBSERVATION` / `OWNER-CORRECT`，无新证据推翻 Controller 裁决

## Open Questions

无。

## Residual Risk

- 全量六域的两个 logging-order failure（`test_sec_request_debug_logs_success_response`、`test_configure_does_not_touch_root_by_default`）已确认为既有 Web smoke 全局 logging-state 污染，不在 R03 changed owner 范围内。Controller 已明确记录此 observation 且不接受为 R03 finding。建议后续 WU 由 Web smoke owner 修复。
- macOS coverage 预载入对 Web/Fins spawn pickling 的影响继续归 validation harness/environment owner。真实子进程用例已有无 instrumentation 的通过证据。
- 本 re-review 未覆盖 `dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/config/` 内部实现细节（均在 accepted plan §8 审计为 compliant/no-diff）。若后续 WU 修改这些层，需独立 deepreview。
- R03 尚未完成 accepted local commit；R04 与 umbrella WU final closeout 仍未授权。

## Final Verdict

| 指标 | 值 |
|---|---|
| **总体 verdict** | **PASS** |
| **Accepted findings** | **0** |
| **Blocking open questions** | **0** |
| **F01-F03 状态** | **全部 CLOSED** |
| **80-path protected proof** | **独立复算通过** |
| **Unauthorized drift** | **无** |
| **Controller-authorized post-proof changes** | **3（zero-change artifact、Controller validation、issues-implementation-control.md gate diff）** |
| **四消费者同源** | **验证通过** |
| **Opaque refs internal-only** | **验证通过** |
| **LLM-facing 文本** | **符合 AGENTS.md 约束** |
| **安全保留项** | **保持** |
| **Deferred Issue 边界** | **完整** |
| **统一 tool authorization** | **未引入** |

本路 AgentDS 完整 R03 aggregate re-review 对 `8c6ae966..HEAD` 的 S1-S3 accepted commits + 当前 working tree F01-F03 fixes 返回 **PASS / ZERO ACCEPTED FINDING / ZERO BLOCKING QUESTION**。

所有 observation/residual risk 均有明确 owner 与最终状态；无 accepted finding 留给后续优化。

R03 accepted local commit 授权等待 Controller 最终裁决。
