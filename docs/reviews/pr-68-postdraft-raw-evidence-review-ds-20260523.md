# PR 68 Post-Draft Raw Evidence Compaction Fix — Deep Review

**Date**: 2026-05-23
**Reviewer**: DS (deepreview)
**Scope**: current workspace diff (19 files, +540/-164)
**Gate**: Phase 12.5 PR 68 post-draft raw evidence compaction fix

---

## 1 Executive Summary

本轮 fix 响应 controller 裁决：`result_preview` 作为 evidence-backed fact extraction 的 primary input 会丢失长章节 evidence 内容（如"管理层讨论与分析"），必须删除该概念，改为 compactor 从 compact range raw tool result / raw transcript 读取原始内容，Host 仅负责将 `evidence_id` 标注到 raw 内容旁边。

**结论: PASS** — 所有 correctness blocker 已关闭。`result_preview` 完全删除，`_NeverCancelledToken` 无回归，Host layer 正确，evidence 链路完整闭合。发现 3 个中等严重度 finding，均为边界防御或覆盖缺口，建议在后续迭代中收口。

---

## 2 Mandatory Checks

### 2.1 `result_preview` 全量清理

| 搜索范围 | 命中 | 判定 |
|---|---|---|
| `dayu/host/` | 0 | PASS |
| `tests/host/` | 0 | PASS |
| `docs/host/design.md` | 0 | PASS |
| `dayu/host/README.md` | 0 | PASS |
| `tests/README.md` | 0 | PASS |
| `docs/host/implementation-control.md` | 4 (全部为历史过程记录) | PASS |

`AcceptedEvidenceResultRef.result_preview` 字段已删除；`MAX_ACCEPTED_EVIDENCE_RESULT_PREVIEW_CHARS` 已删除；`_accepted_tool_outcome_preview()` 已删除；`_TRUNCATED_PREVIEW_SUFFIX` 已删除；所有序列化/反序列化/校验辅助函数已删除。所有 `__all__` 导出列表已同步清理。

### 2.2 Cancellation Hardening 无回归

`_NeverCancelledToken` 在 `dayu/host/` 中零命中。`LLMContextCompactor.compact()` 签名保持 `(self, request, cancellation_token: CancellationToken)`，`CancellationToken` 被显式传入 `_agent_request()` → `AgentRunRequest.cancellation_token`。所有 compaction 测试使用 `StubCancellationToken()` 而非 `_NeverCancelledToken`。

### 2.3 Host Layer Correctness

`compaction_evidence.py` 不导入 `dayu.fins`、`dayu.engine`、`dayu.service`、`dayu.ui`。`CompactRawContextItem` 的 `content_kind` 使用 `CompactRawContextKind` 枚举（`USER_INPUT` / `ASSISTANT_CONCLUSION` / `ACCEPTED_TOOL_RESULT`）——全部是 Host-neutral 类型，不涉及 Fins locator/metric/chunk 语义。`AcceptedEvidenceEnvelope` 的 `source_refs` / `locator_refs` 保持 opaque，Host 不解析。

### 2.4 Evidence ID 生成权

`derive_accepted_evidence_id()` (`evidence.py:196-205`) 在 `TOOL_RESULT_ACCEPTED` accept barrier 处由 Host 生成：`evidence:{accepted_event_id}`。LLM compactor prompt schema（`llm_compaction.py:344`）中 `evidence_refs` 字段要求 LLM 引用已给出的 accepted evidence ref，不允许 LLM 自行生成 canonical evidence id。

---

## 3 Architecture Walkthrough

### 3.1 Raw Tool Outcome 写入链路

```
ToolRuntime._accept_tool_result()
  → _tool_fact_accept_candidate(outcome=...)
      raw_tool_outcome = _tool_outcome_json(outcome)    # 完整 ToolExecutionOutcome → canonical JSON
  → _append_tool_result_if_needed(candidate)
      → 非 REUSE: 写入 TOOL_RESULT_ACCEPTED
          payload["raw_tool_outcome"] = candidate.raw_tool_outcome   # 完整 JSON，无截断
          payload["accepted_evidence_envelope"] = {...evidence_id...}
      → REUSE: 不写 TOOL_RESULT_ACCEPTED (line 3473-3474)
```

`raw_tool_outcome` 是完整的 `ToolExecutionOutcome` 的 canonical JSON（`_tool_outcome_json(outcome)`），没有长度截断。这确保了 LLM compactor 能看到完整的工具结果内容，包括之前被 1200 字符 `result_preview` 截断的长章节。

### 3.2 Evidence 读取链路

```
collect_compaction_request_evidence_inputs(transaction, ..., start, end)
  → EventLog range 扫描 CANONICAL_FACT events
  → TOOL_RESULT_ACCEPTED:
       envelopes = _accepted_evidence_envelope_from_event(row)    # 读 envelope
       raw_context_items += _tool_result_raw_context_items(row, envelopes)
         → payload["raw_tool_outcome"] → canonical_json_dumps → CompactRawContextItem
         → accepted_evidence_refs = (envelope.evidence_id,)
         → 若 raw_tool_outcome 为 None → HostDurableError (fail-closed)
  → USER_INPUT_ACCEPTED:
       raw_context_items += _user_input_raw_context_items(row)
         → payload["display_text"] → CompactRawContextItem(content_kind=USER_INPUT)
  → RUN_SUCCEEDED:
       raw_context_items += _assistant_raw_context_items(row)
         → assistant_summary_from_payload(STRICT_NON_EMPTY)
  → CONTEXT_COMPACTED:
       evidence_backed_fact_refs += _evidence_backed_fact_refs_from_compacted_event(row)
```

### 3.3 LLM Prompt 渲染链路

`_user_prompt(request)`:
```
1. accepted_evidence_envelopes:         ← metadata only (evidence_id, tool_name, query, result ref without preview)
2. compact_raw_context:                 ← full raw content with evidence_id anchors
   - event_ref, content_kind
   - accepted_evidence_refs: evidence:X   ← evidence_id 直接标注在 content 之前
   - content: (indented full raw text)     ← 完整 raw 内容
3. Return strict JSON only. Required object schema:
```

### 3.4 FakeCompactor 适配

`FakeContextCompactor._fact_candidates()` 从 `request.compact_raw_context_items` 读取 raw 内容，为每个 `accepted_evidence_refs` 生成一个 fact candidate，`claim_text` 包含完整 `content_text`。

---

## 4 Findings

### F1 (中等严重度): `raw_tool_outcome` 缺少 aggregate prompt token budget guard

**位置**: `llm_compaction.py:403-426` `_compact_raw_context_lines()`

**描述**: `raw_tool_outcome` 现在存储完整 `ToolExecutionOutcome` 的 canonical JSON，没有长度上限。当 Session 内累积大量大型工具结果（如多份年报全文）时，`compact_raw_context` prompt section 可能超过模型 context window。设计文档和 implementation-control 已将此列为 residual risk（"raw evidence aggregate prompt budget"），不是本 fix 的 blocker，但在 production 场景中可能导致 LLM compaction 失败。

**建议**: 在 `_compact_raw_context_lines()` 或上游增加 aggregate content 的 token 估算与硬上限守卫。可与现有 `conservative estimator` 基础设施集成。

### F2 (中等严重度): `_compact_raw_context_lines` 的 evidence_id 标注距离可进一步收紧

**位置**: `llm_compaction.py:414-425` 与测试 `test_llm_compaction.py:1261-1293`

**描述**: 当前 prompt 格式中，`accepted_evidence_refs` 行与 `content:` 行之间没有空行，结构紧凑。测试 `test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id` 验证了 `raw_context_index < evidence_ref_index < raw_content_index` 的相对顺序。但如果一个 `CompactRawContextItem` 携带多个 `accepted_evidence_refs`，当前渲染方式将所有 refs 写在一行（`evidence:1, evidence:2`），LLM 需要自行推断哪个 evidence_id 对应 content 的哪部分。当前 V1 每个 TOOL_RESULT_ACCEPTED 只有一个 evidence_id，不存在此歧义。若未来支持 item-level evidence id，需要细化标注粒度。

**影响**: 当前无实际影响（单 evidence_id per item），但架构设计上对多 evidence 场景预留不足。

### F3 (中等严重度): 缺少 `raw_tool_outcome` 缺失场景的 fail-closed 行为测试

**位置**: `compaction_evidence.py:166-168` 与 `tests/host/test_compaction_operation.py`

**描述**: `_tool_result_raw_context_items()` 在 `raw_tool_outcome is None` 时抛出 `HostDurableError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")`，这是正确的 fail-closed 行为。但没有任何测试覆盖该异常路径。当前生产路径中，非 REUSE 的 `_append_tool_result_if_needed` 始终写入 `candidate.raw_tool_outcome`（已由 `_require_raw_tool_outcome()` 保证非 None），所以该异常仅在 durable store 数据损坏或 schema 迁移不兼容时触发。

**建议**: 添加测试用例直接构造 `raw_tool_outcome` 缺失的 EventLog row，验证 `_tool_result_raw_context_items` 抛出 `HostDurableError`。

### F4 (低严重度): `USER_INPUT_ACCEPTED` / `RUN_SUCCEEDED` raw context 收集的 EventLog 覆盖不完整

**位置**: `tests/host/test_compaction_operation.py:262-362`

**描述**: `test_compaction_request_evidence_inputs_are_bounded_for_proactive_and_reactive` 中 EventLog setup 包含 `USER_INPUT_ACCEPTED` event（通过 `_ensure_session_row` 或类似 setup），但未显式包含 `RUN_SUCCEEDED` event。`_assistant_raw_context_items()` 的读取路径没有直接的单元级覆盖。

**建议**: 在现有 range-bounded test 或新测试中显式包含 `RUN_SUCCEEDED` event，验证 `assistant_summary_from_payload(STRICT_NON_EMPTY)` 的路径。

### F5 (低严重度): `compact_raw_context_items` 顺序依赖 EventLog 遍历顺序，未显式排序

**位置**: `compaction_evidence.py:89-109`

**描述**: `raw_context_items` 按 EventLog 遍历的先后顺序追加，最终顺序依赖于 `event_log_store.read_events_after()` 返回的 event_sequence 升序。当前实现依赖该隐式保证，但未在代码中显式排序。如果 EventLogStore 实现变更（如并行读取），顺序可能错乱。

**建议**: 在返回前对 `raw_context_items` 按 `event_ref`（即 `row.event_id` 或 `row.event_sequence`）显式排序，或在 docstring 中明确声明排序契约。

---

## 5 Test Coverage Assessment

### 5.1 长 Raw Evidence 存活证明

`test_llm_context_compactor_prompt_keeps_long_raw_evidence_content` (`test_llm_compaction.py:1234-1258`):
- 构造 1300+ 字符的 raw content（超过旧 `result_preview` 1200 字符上限）
- 验证尾部标记出现在 prompt 中
- **结论**: PASS — 证明长 evidence 内容不再被截断

### 5.2 Evidence ID 标注位置证明

`test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id` (`test_llm_compaction.py:1262-1293`):
- 验证 `raw_context_index < evidence_ref_index < raw_content_index` 的顺序关系
- evidence_id 出现在 raw content 之前，LLM 可关联
- **结论**: PASS

### 5.3 Raw Context 传递与契约覆盖

| 测试 | 文件 | 覆盖 |
|---|---|---|
| `test_compaction_request_evidence_inputs_are_bounded_for_proactive_and_reactive` | `test_compaction_operation.py` | raw context 与 envelope 关联、evidence_id、USER_INPUT 收集 |
| `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids` | `test_compaction_operation.py` | envelope dedup + raw context |
| `test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch` | `test_compaction_operation.py` | producer_event_ref 校验 |
| `test_fact_candidates_can_reference_accepted_evidence_envelopes` | `test_compaction_contract.py` | FakeCompactor 使用 raw context 生成 fact |
| `test_llm_context_compactor_prompt_contains_raw_evidence_content` | `test_llm_compaction.py` | prompt 包含 raw content + evidence_id 交叉引用 |
| `test_tool_result_accepted_payload_carries_accepted_evidence_envelope` | `test_toolruntime_accept_barrier.py` | payload 中 raw_tool_outcome 校验 |
| `test_oversized_tool_result_returns_completed_outcome_without_default_governor` | `test_toolruntime_executor.py` | raw_tool_outcome 包含完整 oversized value |
| `test_compact_artifact_snapshot_includes_compact_raw_context_items` (implicit) | `test_compact_artifact_store.py` | artifact snapshot JSON 包含 compact_raw_context_items |

---

## 6 Project Instruction Compliance

- [PASS] 禁止兼容性代码：无 `result_preview` 兼容性 wrapper/reexport/fallback。
- [PASS] 禁止 `hasattr`/`getattr` 滥用：未新增。
- [PASS] 禁止魔法数字/字符串：`CompactRawContextKind` 使用 StrEnum。
- [PASS] 禁止 God object/function：`CompactRawContextItem` 职责单一。
- [PASS] 模块级私有辅助函数：`_tool_result_raw_context_items`、`_user_input_raw_context_items`、`_assistant_raw_context_items` 均为模块级。
- [PASS] Docstring 完整性：所有新增函数/类有完整中文 docstring。
- [PASS] 类型标注：所有新增函数/类有完整类型标注，无 `Any`/`object`。
- [PASS] 测试更新：所有受影响测试已同步更新，旧的 `result_preview` 断言已替换为 `raw_tool_outcome` 断言。

---

## 7 Architecture Compliance

- [PASS] Host 不理解 Fins 语义：`CompactRawContextItem` / `CompactRawContextKind` 均为 Host-neutral。
- [PASS] 分层正确：`compaction_evidence.py` 只依赖 `dayu.host` 内部模块与 `dayu.contracts.json_value`。
- [PASS] 无反向依赖：`dayu.host.compaction_evidence` 不被 `dayu.engine` / `dayu.fins` 反向依赖。
- [PASS] 无胶水 seam：`canonical_json_dumps` import 有充分理由（将 raw outcome 序列化为 prompt-able 文本）。
- [PASS] REUSE 工具不写入 TOOL_RESULT_ACCEPTED：`_append_tool_result_if_needed` line 3473-3474 early return。

---

## 8 Findings Summary

| # | 严重度 | 类别 | 文件:行 | 简述 |
|---|---|---|---|---|
| F1 | 中等 | 稳定性 | `llm_compaction.py:403-426` | raw context 缺少 aggregate token budget guard |
| F2 | 中等 | 可维护性 | `llm_compaction.py:414-425` | 多 evidence_id per item 标注粒度不足 |
| F3 | 中等 | 测试覆盖 | `compaction_evidence.py:166-168` | raw_tool_outcome 缺失 fail-closed 路径无测试 |
| F4 | 低 | 测试覆盖 | `test_compaction_operation.py` | RUN_SUCCEEDED raw context 收集无显式覆盖 |
| F5 | 低 | 可维护性 | `compaction_evidence.py:89-109` | raw_context_items 顺序依赖隐式 EventLog 排序 |

---

## 9 Final Report

**结果: PASS**

`result_preview` 概念已从所有 active 生产代码、测试、设计文档和 README 中完全删除。`AcceptedEvidenceEnvelope` 现在是 provenance anchor，不承载 lossy 内容预览。`CompactRawContextItem` 携带完整 raw 内容，`evidence_id` 由 Host 在 accept barrier 生成并标注到 raw 内容旁边。LLM compactor 通过 `compact_raw_context` prompt section 获取完整 evidence 内容。`_NeverCancelledToken` 无回归。

F1（aggregate token budget guard）是已知 residual risk，已在 `implementation-control.md` 中记录。F2/F3/F4/F5 为非阻塞 finding，不影响本轮 gate 通过。

**Output**: `docs/reviews/pr-68-postdraft-raw-evidence-review-ds-20260523.md`
