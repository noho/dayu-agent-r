# WU-CM-01 Slice B Code Review (DeepSeek)

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B implementation code review |
| design source | `docs/host/design.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| prior artifacts | `docs/reviews/wu-cm-01-slice-b-implementation-codex.md`、`docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md`、`docs/reviews/wu-cm-01-slice-b-plan-fix-followup-controller-adjudication.md` |
| reviewer | DeepSeek (via Claude Code) |
| review date | 2026-06-04 |
| claimed validation | 270 focused tests passed, pyright 0 errors |

## Verdict

**通过（有条件）**。Slice B implementation 整体正确地将 production compaction operation、event payload、fake compactor 和双路径（proactive dispatch / reactive engine_ingest）closeout 切换到 vNext candidate（`ConversationCompactOutputVNext` / `CompactQualityCheckResultVNext`），并同步迁移了受影响的测试。发现 0 个 blocking finding，2 个 non-blocking finding，2 个 observation。

---

## 逐项检查结果

### 1. production compaction operation/event/artifact 是否切换到 VNext

**结论：通过。**

- `compaction_operation.py:92-264` — `run_compaction_operation()` 完全使用 `_compact_vnext()` → `compactor.compact_request_vnext()`，返回 `CompactionOperationResult` 携带 `ConversationCompactOutputVNext | None` 与 `CompactQualityCheckResultVNext | None`。删除旧 `_merge_candidates`、`_merge_tuple_field_patch` 等 helper。
- `context_events.py:313-398` — `build_context_compacted_payload()` 签名接受 `ConversationCompactOutputVNext` 和 `CompactQualityCheckResultVNext`，不再接受 `CompactionCandidate` / `CompactQualityCheckResult`。`validate_context_compacted_payload()` 通过 `_reject_old_compacted_fields()` (L515-525) fail closed 拒绝 `episode_summary_candidate`、`pinned_state_patch_candidate`、`preservation_evidence`、`evidence_backed_fact_candidates`、`minimum_preserve_item_candidates`、`preserved_fact_refs`、`dropped_ranges`、`summarized_ranges`、`evidence_anchors_retained` 九个旧字段。
- `dispatch.py:1544-1640` — `_write_compacted_artifact_and_fact()` 签名接受 vNext 类型，使用 `compact_artifact_json_vnext()` 写 artifact，调用 `build_context_compacted_payload()` 传完整 vNext 字段。
- `engine_ingest.py:1713-1820` — `_append_reactive_compacted_event()` 签名接受 vNext 类型，逻辑与 dispatch 端对称。
- `compaction.py:2811-2834` — 新增 `ContextCompactorVNext` Protocol（`@runtime_checkable`），定义 `compact_request_vnext()` 方法签名。旧 `ContextCompactor` Protocol 仍保留供未迁移 consumer。
- `fake_compaction.py:80-116` — `FakeContextCompactor` 新增 `compact_vnext()` 和 `compact_request_vnext()` 方法，委托给 `FakeConversationCompactorVNext`。

### 2. proactive dispatch 与 reactive engine_ingest accepted closeout 是否写 vNext artifact 和 vNext CONTEXT_COMPACTED payload

**结论：通过。**

- proactive closeout（`dispatch.py:1544-1640`）：先通过 `LocalArtifactStore.write_artifact_bytes()` 写入 vNext artifact JSON（由 `compact_artifact_json_vnext()` 生成），再通过 `PayloadStore.write_payload_descriptor_for_artifact()` 写入 payload descriptor，最后通过 `build_context_compacted_payload()` 写出包含 `operation_id`、`accepted_attempt_number`、`accepted_candidate_digest`、`compact_artifact_ref`、`compact_artifact_digest`、`prompt_local_label_mapping_refs`、`source_boundary_refs`、`accepted_evidence_mapping_refs`、`quality_check_result`、`budget_after_compact`、`projection_signal` 的完整 CONTEXT_COMPACTED payload。
- reactive closeout（`engine_ingest.py:1713-1820`）：与 proactive 路径对称，使用同一套 `compact_artifact_json_vnext()` / `compact_artifact_payload_ref()` / `compact_artifact_descriptor_metadata_vnext()` helper，调用同一 `build_context_compacted_payload()` 签名。
- `_proactive_represented_evidence_refs()`（`dispatch.py:3645-3674`）已从调用 `preserved_canonical_evidence_refs()` 切换到 `accepted_evidence_mapping_refs()`（vNext helper）。

### 3. engine_ingest.py 修改是否仅限 reactive accepted closeout

**结论：通过（含一项 observation）。**

- `engine_ingest.py` 改动集中在：
  - Import 变更（L55-79, L90-98）：删除 `CompactArtifactStore`、`CompactArtifactWriteRequest` import，新增 `compact_payload` vNext helper import。
  - `_append_reactive_compacted_event()` 方法（L1713-1820）：完全重写为 vNext artifact/event closeout。
  - 调用点（L1676-1696）：传递 vNext 类型参数。
  - 模块级常量 `_NO_CONTEXT_BUDGET_POLICY_REF = "none"`（L244）：提取魔法字符串。
- **Observation O1**：L2330 的 `_NO_CONTEXT_BUDGET_POLICY_REF` 使用在非 closeout 路径（`_build_run_input_and_agent_request` 中）。该修改将原魔法字符串 `"none"` 替换为同名常量，不改变类型签名或实现逻辑，属于低风险命名一致性改进。严格按 plan 文字属于非 closeout 修改，但实际影响为零。

### 4. compact_payload.py 旧 preserved refs helper 是否仅暂留

**结论：通过。**

- `preserved_canonical_evidence_refs()`（L54-69）docstring 明确标注："该 helper 仅保留到 RunInputBuilder 所属 Slice D 切换前避免导入断裂；vNext operation / dispatch 不调用该函数"。
- `preserved_fact_refs_summary()`（L72-95）同标注。
- 当前唯一生产调用方：`dayu/host/run_input.py`（Slice D consumer），符合计划预期。
- `dispatch.py` 不再 import `preserved_canonical_evidence_refs`，改为 import `accepted_evidence_mapping_refs`。
- `engine_ingest.py` 不 import 旧 helper。

### 5. 是否无旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped payload

**结论：通过。**

- `context_events.py` 的 `_COMPACTED_OLD_FIELDS` 是拒绝列表（fail closed），不是兼容读取。
- 无 `hasattr` / `getattr` 在变更文件中使用。
- 无 lazy import（`importlib`）。
- 无 `extra` payload 字段注入。
- 所有变更文件使用 typed dataclass，无 `dict[str, Any]` 或 untyped payload。
- `dispatch.py` 和 `engine_ingest.py` 不再 import `compact_artifact` 模块（`CompactArtifactStore`、`CompactArtifactWriteRequest`）。
- `compact_artifact.py` 模块仍存在但已不被 operation/dispatch/engine_ingest 路径依赖；其清理属于后续 slice 或独立清理任务。

### 6. 测试覆盖

**结论：通过（含一项 observation）。**

- `tests/host/test_compaction_operation.py`：9 个 fake compactor 全部切换为继承 `FakeContextCompactor` 并实现 `compact_request_vnext()`。覆盖 proposal failure、quality reject、hard threshold reject、cancellation、multi-pass、vNext whole-candidate repair 等路径。质量校验 monkeypatch 改为 `check_conversation_compact_output_vnext`。
- `tests/host/test_context_compact_events.py`：`_candidate()` 返回 `ConversationCompactOutputVNext`（含 session summary、fact、answer anchor、forward intent、reference continuity、diagnostics）。`_quality_result()` 返回 `CompactQualityCheckResultVNext`。旧字段拒绝测试改为验证 vNext payload 拒绝。accepted/rejected quality result 测试使用 vNext 类型。
- `tests/host/test_dispatch_scheduler.py`：5 个 fake compactor 切换为 vNext。`test_multi_turn_proactive_compact_feeds_subsequent_run_input` 收窄为 closeout 断言（event_types 顺序、payload 字段存在性）。`test_reactive_overflow_recovers_and_dispatches_new_attempt` 改为断言 `CONTEXT_COMPACTED` event 写入。`test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 收窄为 closeout（不再断言后续 RunInputBuilder consumption）。`test_reactive_recovery_uses_fresh_duplicate_governance_attempt` 类似收窄。
- `tests/host/test_engine_ingest_mapping.py`：3 个 fake compactor 切换为 `FakeContextCompactor` + `compact_request_vnext()`。`test_context_compaction_requested_none_budget_uses_host_estimator_and_compactor` 新增断言：`operation_id`、`accepted_attempt_number`、`projection_signal`、`accepted_candidate.schema_version`、`preserved_fact_refs` 不存在、artifact descriptor media_type、artifact JSON schema_version、candidate digest 匹配。
- `tests/host/fake_compaction.py`：`FakeContextCompactor` 新增 `compact_vnext()` 和 `compact_request_vnext()`，使其满足 `ContextCompactorVNext` Protocol。
- **Observation O2**：`test_reactive_multi_pass_merges_only_candidate_preserved_refs`（重命名为保持原有名称但语义已不同）的新断言 `assert len(result.accepted_candidate.evidence_backed_facts) > 0` 较弱 — 它不再验证 "no preserved fact refs" 行为，因为 vNext candidate 没有 `preserved_evidence_backed_fact_refs` 字段。建议 Slice D/E 清理该测试名称或明确改为 vNext 语义断言。

### 7. README 更新

**结论：通过。**

- `dayu/host/README.md` Context Compaction 段落：删除旧 pinned patch / minimum preserve / stable layer 描述；更新为 vNext candidate output（session summary、evidence-backed facts、answer anchors、forward intents、reference continuity items、diagnostics）、vNext artifact closeout、vNext CONTEXT_COMPACTED payload 字段。
- `tests/README.md`：
  - `test_compaction_operation.py` 覆盖描述更新：删除 "CLEAR 后 REPLACE tuple patch evidence refs 隔离"，改为 vNext operation 描述。
  - `test_dispatch_scheduler.py` 覆盖描述更新：删除 "multi-turn proactive compact 到后续 memory 注入链路"，改为 "proactive compact vNext artifact / `CONTEXT_COMPACTED` closeout"；删除 "reactive Engine overflow recovery 到新 Attempt"，改为 "reactive Engine overflow accepted closeout 到 recovery Attempt"。
  - 删除 P12.6 中 "minimum preserve 和 summary 不建 fact" 等旧语义表述，替换为 vNext operation 覆盖描述。
- 未命中根目录 `README.md`、`dayu/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md` 职责触发条件。

---

## Findings

### Non-blocking Findings

**N1** — `engine_ingest.py` L2330 非 closeout 路径引用 `_NO_CONTEXT_BUDGET_POLICY_REF`。

- 证据：`_NO_CONTEXT_BUDGET_POLICY_REF = "none"` 常量同时用于 reactive closeout（L1746）和 `_build_run_input_and_agent_request` 方法（L2330）。该常量提取是 plan fix 期间引入的，本质上是将两处相同的 `"none"` 魔法字符串替换为命名常量。L2330 在非 closeout 函数中，严格按 plan 文字属于非 closeout 修改。
- 严重性：低。不改变类型签名、实现逻辑或行为。
- 建议：可接受现状。若未来 slice 重构该区域时可统一常量命名。

**N2** — `test_reactive_multi_pass_merges_only_candidate_preserved_refs` 测试名称与断言不匹配。

- 证据：测试名称仍暗示 "merges only candidate preserved refs"，但 vNext candidate 没有 `preserved_evidence_backed_fact_refs` 字段。新断言 `assert len(result.accepted_candidate.evidence_backed_facts) > 0` 只验证 candidate 有 fact 输出，不再验证 "no preserved fact refs" 语义。
- 严重性：低。测试仍通过且覆盖了 vNext 路径的 happy path。但测试名称可能在后续维护中引起混淆。
- 建议：Slice D/E 重命名该测试或恢复更有针对性的 vNext 语义断言。

### Observations

**O1** — 见上文第 3 节，与 N1 相同。

**O2** — 见上文第 6 节，与 N2 相同。

---

## Residual Risks

1. **vNext CONTEXT_COMPACTED 已提交后，memory durable / projection 尚未消费。**
   - Owner：WU-CM-01 Slice C。
   - 当前状态：`CONTEXT_COMPACTED` payload 携带完整 vNext 字段（`accepted_candidate`、`quality_check_result`、`projection_signal` 等），但 `memory.py` / `durable/memory.py` 仍使用旧 snapshot shape。这是预期的 Slice B exit 状态。

2. **ordinary RunInputBuilder 对 vNext compacted view 的后续消费尚未迁移。**
   - Owner：WU-CM-01 Slice D。
   - 当前状态：`run_input.py` 仍通过 `preserved_canonical_evidence_refs()` 和 `preserved_fact_refs_summary()` 读取 compact payload。测试已收窄为 closeout 断言。

3. **`compact_artifact.py` 模块（`CompactArtifactStore`、`CompactArtifactWriteRequest`）仍存在但已不被 operation/dispatch/engine_ingest 引用。**
   - Owner：后续清理（非 WU-CM-01 直接 scope，可在任一后续 slice 删除未使用 import 时一并清理）。
   - 当前状态：模块未被 import，无运行时影响。

4. **完整 Conversation Memory eval benchmark、User Profile Memory、deep historical recall 等仍 deferred。**
   - Owner：WU-CM-10（#80）、WU-CM-11（#115）、GitHub Issue #39。

---

## 验证状态

以下为 Codex implementation report 声称的验证命令，本次 review 未独立运行：

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py \
  tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py \
  tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py \
  tests/host/test_engine_ingest_mapping.py -q
# claimed: 270 passed in 1.89s

python -m pyright dayu/ tests/ utils/
# claimed: 0 errors, 0 warnings, 0 informations
```

**建议**：在 commit 前独立运行上述命令确认。

---

## 总结

Slice B implementation 实现了 plan 规定的全部目标：

- production compaction operation、event payload、proactive dispatch closeout 和 reactive engine_ingest closeout 全部切换到 `ConversationCompactOutputVNext` / `CompactQualityCheckResultVNext`。
- vNext CONTEXT_COMPACTED payload 包含完整治理字段（operation id、attempt number、candidate digest、artifact ref/digest、label mapping refs、source boundary refs、accepted evidence mapping refs、quality result、budget after compact、projection signal）。
- 旧 payload compatibility fields 被 fail-closed 拒绝，无 projection shim、old candidate adapter、lazy import、extra payload 或 untyped payload。
- `engine_ingest.py` 修改仅限 reactive closeout（含一项低风险常量提取）。
- 旧 preserved refs helper 仅保留给 Slice D consumer（`run_input.py`），operation/dispatch/engine_ingest 已不依赖。
- 测试覆盖 operation/event/proactive/reactive closeout，测试 fake compactor 全部迁移到 vNext。
- README 更新符合职责。
