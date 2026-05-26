# Phase 12.5 Aggregate Re-review — 修复验证

## Scope

- **Mode**: Current changes re-review (修复后验证)
- **Branch**: `feat/phase-12-5-conversation-memory-optimize`
- **Base**: `main` (HEAD: `0dbcc5a`，上一次 aggregate review 基准)
- **Re-review scope**: 未提交修复 diff（17 files, +513 / -49 lines）
- **Review date**: 2026-05-23 02:37 UTC+8
- **Output file**: `docs/reviews/phase12-5-aggregate-rereview-ds-20260523.md`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Prior review artifact**: `docs/reviews/phase12-5-aggregate-deepreview-ds-20260522.md`（含 2 个严重 + 3 个高 + 5 个中）
- **Parallel review coverage**: 本次修复范围集中，未启用并行代理。主 reviewer 逐链路走读了全部 17 个变更文件。

---

## 修复验证 — 5 个 Blocker 逐项重审

### Blocker 1（严重）：LLM compactor 从未收到 evidence 信封内容 → **已修复，PASS**

**修复变更**:

| 文件 | 变更 | 行号 |
|---|---|---|
| `dayu/host/evidence.py` | `AcceptedEvidenceResultRef` 新增 `result_preview: str \| None` 字段；新增 `MAX_ACCEPTED_EVIDENCE_RESULT_PREVIEW_CHARS = 1200`；`_RESULT_REF_FIELDS` 扩展包含 `result_preview`；新增 `_require_optional_bounded_non_empty_text` 校验器；序列化/反序列化适配 | 54-61, 129-131, 149-153, 246-247, 302, 489-506 |
| `dayu/host/tool_runtime.py` | `ToolFactAcceptCandidate` 新增 `result_preview: str \| None` 字段；`_validate_common_candidate_fields` 新增 preview 长度校验；`_accepted_evidence_envelope()` 传入 `result_preview=candidate.result_preview`；新增 `_accepted_tool_outcome_preview()` 从 canonical JSON 派生有界预览（含 `...[truncated]` 后缀）；`_tool_fact_accept_candidate` 传入 `result_preview=_accepted_tool_outcome_preview(outcome)`；`_tool_fact_reuse_accept_candidate` 传入 `result_preview=None` | 389, 415, 3575-3577, 3939-3943, 4121-4137, 4785, 4874, 5022-5038 |
| `dayu/host/llm_compaction.py` | 新增 `AcceptedEvidenceEnvelope`/`OpaqueEvidenceRef` import；新增 `_accepted_evidence_envelope_lines()` 函数，格式化 evidence_id、tool_name、tool_call_id、query digests、result_ref 所有字段（含 `result_preview`）、source_refs、locator_refs；新增 `_opaque_refs_text()` 格式化 opaque ref 为可读文本；`_user_prompt()` 在 JSON schema 前调用 `_accepted_evidence_envelope_lines()` 注入 evidence 内容 | 60, 334, 338-388 |

**验证链路追踪**（逐行走读）：

1. `_tool_fact_accept_candidate()` 调用 `_accepted_tool_outcome_preview(outcome)` — `tool_runtime.py:4785`
2. `_accepted_tool_outcome_preview()` 将 outcome 序列化为 canonical JSON，截断至 1200 字符 — `tool_runtime.py:5022-5038`
3. `_accepted_evidence_envelope()` 将 preview 传入 `AcceptedEvidenceResultRef` — `tool_runtime.py:3575`
4. `_user_prompt()` 调用 `_accepted_evidence_envelope_lines(request.accepted_evidence_envelopes)` — `llm_compaction.py:334`
5. `_accepted_evidence_envelope_lines()` 展开每个 envelope 的全部字段 — `llm_compaction.py:338-388`
6. LLM prompt 中包含：evidence_id、tool_name、tool_call_id、query digests、payload_ref/digest、outcome_digest、**result_preview**（工具结果的实际内容预览，如 `"Revenue grew 12% year over year."`）、source_refs、locator_refs

**裁决**: 证据链路完整闭合。LLM compactor 现可通过 prompt 中的 envelope 完整内容（特别是 `result_preview` 字段携带的工具结果预览文本）访问 accepted evidence 的实际内容，而非仅不透明 ID。`claim_text` 和 `evidence_kind` 的生成有 evidence 内容作为事实基础。与设计文档 §25 行 2670-2672 "evidence-backed fact candidates 基于 compact 输入中的 accepted evidence envelope 及其 bounded result_preview 生成" 对齐。

**残余风险**: `result_preview` 从 canonical JSON dumps 生成，是 Host-neutral 的 JSON 字符串。对于返回结构化数据（如表格、嵌套对象）的工具结果，JSON 预览可能不易被 LLM 直接解读。未来可考虑为 `result_preview` 增加工具提供方可控的摘要字段。当前 V1 已满足 "LLM 能看到 evidence 内容" 的最低要求。

---

### Blocker 2（严重）：Memory 投影滞后触发 Run→FAILED → **已修复，PASS**

**修复变更**:

| 文件 | 变更 | 行号 |
|---|---|---|
| `dayu/host/dispatch.py` | 新增 `MemoryRepairReason`/`rebuild_conversation_memory_projection` import；`_start_worker` 中 `MemoryProjectionRepairRequired` 异常处理拆分为两个分支：`SNAPSHOT_LAG_OVER_THRESHOLD` → log warning + release lane + return `"skipped"`（不走 terminal closeout）；其他 reason → 保持原有 `_safe_closeout_worker_startup_timeout` 路径 | 111-114, 2097-2110 |
| `dayu/host/dispatch.py` | 新增 `_build_run_input_with_lag_repair()` 方法：首次 build 若抛出 `SNAPSHOT_LAG_OVER_THRESHOLD`，调用 `rebuild_conversation_memory_projection` 后重试 build；非 lag repair 直接 raise | 2206-2262 |

**验证链路追踪**:

1. `_start_worker` 行 2097: `except MemoryProjectionRepairRequired as exc:`
2. 行 2098-2101: 检查 `exc.repair_request.reason is MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD`
3. 行 2102-2110: log warning → `await _safe_release_lane_token(token)` → `return "skipped"`
4. 不再进入 `_safe_closeout_worker_startup_timeout`（旧路径统一在此处关闭 Run→FAILED，行 2100 old）
5. `_build_run_input_with_lag_repair` 行 2238: `rebuild_conversation_memory_projection(...)` + 行 2256-2261: `retry_builder.build(snapshot)` — 重建后重试

**裁决**: 修复正确且完整。`SNAPSHOT_LAG_OVER_THRESHOLD` 不再触发 Run 终态迁移。dispatch 先在本方法内通过 `_build_run_input_with_lag_repair` 做 rebuild + retry；若 retry 后仍需 repair，在 `_start_worker` 外层 exception handler 中被安全跳过（`return "skipped"`），不关闭 Run。与设计文档 §24 行 2626 "memory projection lag 不得触发 Run 状态迁移，不得把 Run 推入 RECOVERING" 对齐。

**残余风险**: 连续多次 lag repair skip 可能导致 Run 长时间在 `ACCEPTED` 状态等待 scheduler 重新调度。当前 Run 不会 permanent fail，但用户体验上可能有延迟。需要后续 phase 增加 lag repair 的退避策略或报警。

---

### Blocker 3（高）：FakeContextCompactor 绕过 AcceptedEvidenceEnvelope → **已修复，PASS**

**修复变更**:

| 文件 | 变更 | 行号 |
|---|---|---|
| `tests/host/fake_compaction.py` | 新增 `AcceptedEvidenceEnvelope` import；`_fact_candidates()` 改为遍历 `request.accepted_evidence_envelopes`（替代 `request.accepted_evidence_refs`）；新增 `_fact_claim_from_envelope()` 函数从 envelope 的 `result_preview` 派生 claim_text；`evidence_refs` 改用 `envelope.evidence_id` | 25, 207-233 |

**验证**:

- 旧代码：`for index, evidence_ref in enumerate(request.accepted_evidence_refs)` + `claim_text=f"Accepted evidence retained: {evidence_ref}"` + `evidence_refs=(evidence_ref,)`
- 新代码：`for index, envelope in enumerate(request.accepted_evidence_envelopes)` + `claim_text=_fact_claim_from_envelope(envelope)` + `evidence_refs=(envelope.evidence_id,)`
- `_fact_claim_from_envelope()` 处理两种 case：`result_preview=None` → `"Accepted evidence has no preview: {evidence_id}"`；`result_preview=str` → `"Accepted evidence preview: {result_preview}"`
- `test_fact_candidates_can_reference_accepted_evidence_envelopes` 新增 claim_text 断言验证 preview 内容流入 candidate

**裁决**: FakeCompactor 现在消费完整的 `AcceptedEvidenceEnvelope` 对象。测试 double 与真实 LLM compactor 在证据消费接口上对齐。测试不再在"证据内容从未流经 compactor"的假象下通过。

**残余风险**: FakeCompactor 仍不模拟 LLM 语义理解（它直接回显 preview 作为 claim_text）。但这符合测试 double 的定位——验证契约和数据流，而非语义正确性。

---

### Blocker 4（高）：catch-up failure 静默忽略后误杀 Run → **已修复，PASS**

**修复变更**:

| 文件 | 变更 | 行号 |
|---|---|---|
| `dayu/host/dispatch.py` | `_catch_up_memory_projection_before_worker` 现在捕获 `catch_up_conversation_memory_projection` 返回值；若 `result.failures > 0`，log warning 并调用 `rebuild_conversation_memory_projection()` | 2358-2384 |

**验证链路追踪**:

1. 行 2358: `result = catch_up_conversation_memory_projection(...)` — 捕获返回值
2. 行 2368: `if result.failures == 0: return` — 正常路径快速返回
3. 行 2369-2376: log warning 含 run_id/attempt_id/execution_id/failures
4. 行 2377-2384: `rebuild_conversation_memory_projection(...)` — 全量重建

**裁决**: catch-up failure 不再被静默忽略。failure 时先 log 完整诊断信息，然后触发 rebuild 进行全量修复。配合 Blocker 2 的 `_build_run_input_with_lag_repair` retry，形成双层防御：catch-up fail → rebuild → lag repair检测 → skip（不关闭 Run）。

**残余风险**: `rebuild_conversation_memory_projection` 是全量重建，在大 session 中可能较耗时。当前无超时保护。rebuild 失败（如 durable store 损坏）会导致异常传播到 `_start_worker` 的 `MemoryProjectionRepairRequired` handler，按非 lag 原因走 terminal closeout。这个二段 fallback 行为是否正确取决于 rebuild 失败的具体原因——future phase 可能需要更细粒度的错误分类。

---

### Blocker 5（高）：EvidenceBackedFactView 缺少 claim_text 长度上限 → **已修复，PASS**

**修复变更**:

| 文件 | 变更 | 行号 |
|---|---|---|
| `dayu/host/memory.py` | 新增 `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS` import；`EvidenceBackedFactView.__post_init__` 新增 `if len(self.claim_text) > MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS: raise ValueError(...)` | 19, 423-424 |

**验证**:

- 长度校验插入在 `_require_non_empty` 之后、`evidence_kind` 类型检查之前
- 上限值 `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS = 2000` 与 `compaction.py` 中 `EvidenceBackedFactCandidate.__post_init__` 的校验一致
- 测试 `test_typed_contracts_reject_invalid_ids_cursor_and_evidence_fact` 新增 `pytest.raises(ValueError, match="claim_text")` 覆盖超长 claim_text 场景（2001 字符）

**裁决**: `EvidenceBackedFactView` 的 claim_text 现在有三层防线：(1) compaction proposal 阶段 `EvidenceBackedFactCandidate.__post_init__`；(2) context_events.py `_validate_fact_candidates`；(3) memory projection view 阶段 `EvidenceBackedFactView.__post_init__`。防御纵深完整。

**残余风险**: 无。

---

## 文档与设计同步

| 文件 | 变更 | 状态 |
|---|---|---|
| `docs/host/design.md` | §24 行 2556: accepted evidence envelope 描述增加 `result_preview`；§24 行 2624-2626: snapshot lag repair 改为先 rebuild/retry；§25 行 2670-2672: evidence-backed fact candidates 描述增加 `result_preview` | PASS |
| `dayu/host/README.md` | dispatch 前 rebuild/retry 语义更新；accepted evidence envelope result_preview 说明 | PASS |
| `tests/README.md` | P12.5 smoke 覆盖描述更新：bounded result preview、claim_text 长度防线、lag repair 不关闭 Run | PASS |

---

## 测试覆盖验证

| 新增/修改测试 | 文件 | 覆盖场景 |
|---|---|---|
| `test_llm_context_compactor_prompt_contains_accepted_evidence_preview` | `test_llm_compaction.py` | LLM prompt 包含 evidence envelope 完整字段和 result_preview 内容 |
| `test_fact_candidates_can_reference_accepted_evidence_envelopes` (扩展) | `test_compaction_contract.py` | FakeCompactor claim_text 来自 envelope preview |
| `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run` | `test_dispatch_scheduler.py` | SNAPSHOT_LAG_OVER_THRESHOLD 触发 rebuild retry，不关闭 Run→FAILED |
| `test_typed_contracts_reject_invalid_ids_cursor_and_evidence_fact` (扩展) | `test_memory_projection.py` | EvidenceBackedFactView 超长 claim_text 抛出 ValueError |
| `test_tool_result_accepted_payload_carries_accepted_evidence_envelope` (扩展) | `test_toolruntime_accept_barrier.py` | envelope.result_ref.result_preview 与 candidate 一致 |
| `test_oversized_tool_result_returns_completed_outcome_without_default_governor` (扩展) | `test_toolruntime_executor.py` | result_preview 长度不超过 MAX_ACCEPTED_EVIDENCE_RESULT_PREVIEW_CHARS |

---

## 确认合规项（无退化）

| 检查项 | 修复前状态 | 修复后状态 |
|---|---|---|
| LLM compactor 收到 evidence 内容 | FAIL（仅 opaque refs） | PASS（完整 envelope + result_preview） |
| Memory projection lag 不关闭 Run | FAIL（统一走 terminal closeout） | PASS（lag → skip，非 lag → closeout） |
| FakeCompactor 消费 envelope 内容 | FAIL（仅消费 refs） | PASS（消费全量 envelope） |
| catch-up failure 检测 | FAIL（静默忽略） | PASS（log + rebuild） |
| claim_text 长度防线 | FAIL（仅 proposal 阶段校验） | PASS（view 层也有校验） |
| 分层架构 | PASS（无变化） | PASS |
| 旧 contract fail-closed | PASS（无变化） | PASS |
| Config schema | PASS（无变化） | PASS |
| ToolRuntime accept barrier | PASS（新增 preview 字段） | PASS |
| RunInputBuilder 渲染 | PASS（无变化） | PASS |

---

## Findings

### 1-中-rebuild 后 `_build_run_input_with_lag_repair` 复用原 snapshot 对象，不刷新 stale 内存引用

- **入口/函数**: `_build_run_input_with_lag_repair`
- **文件(行号)**: `dayu/host/dispatch.py` 行 2256-2261
- **输入场景**: rebuild 完成后，retry_builder 使用同一个 `snapshot` 对象调用 `build()`。
- **实际分支**: `retry_builder = self._run_input_builder_for_dispatch(snapshot=snapshot, ...)` + `retry_builder.build(snapshot)`
- **预期行为**: rebuild 已将 durable store 中的 memory snapshot 更新到最新。`builder.build(snapshot)` 会从 durable store 重新读取 memory snapshot，应获取到最新数据。
- **实际行为**: `snapshot` 对象本身未被修改（它是 frozen/immutable 或至少在此路径中不被 rebuild 修改）。新 builder 在 `build()` 中会调用 `DurableMemorySnapshotProvider._load_memory_snapshot_tx()` 重新从 durable store 读取，因此可以获取最新数据。逻辑正确，但 `snapshot` 变量在 rebuild 后仍指向旧对象，代码可读性上可能让读者误以为 "旧 snapshot 被用于构建请求"。
- **直接证据**: `dispatch.py` 行 2256-2261，`snapshot` 作为参数传入但 rebuild 后未被重新获取。
- **影响**: 无功能影响（`build()` 会从 durable store 重新读取），仅代码可读性。
- **建议改法和验证点**: 考虑在 rebuild 后重新获取 Attempt dispatch snapshot 或在注释中说明 "build() 会从 durable store 重新读取 memory"。
- **修复风险**: 低
- **严重程度**: 低（无功能影响，可读性优化建议）

### 2-低-`_catch_up_memory_projection_before_worker` rebuild 后与 `_build_run_input_with_lag_repair` rebuild 可能双重重建

- **入口/函数**: `_catch_up_memory_projection_before_worker` + `_build_run_input_with_lag_repair`
- **文件(行号)**: `dayu/host/dispatch.py` 行 2377-2384, 2238-2250
- **输入场景**: catch-up 失败触发第一次 rebuild。此后 `_build_run_input_with_lag_repair` 中首次 `builder.build(snapshot)` 可能因 lag 仍未消失（rebuild 不完整、事务隔离等）再次抛 `SNAPSHOT_LAG_OVER_THRESHOLD`，触发第二次 rebuild。
- **实际分支**: 两次 rebuild 均由 `rebuild_conversation_memory_projection` 执行，第二次大概率是 no-op（projection 已重建到最新）。
- **预期行为**: 第一次 rebuild 应使 lag 消失，第二次 builder.build 直接成功。
- **实际行为**: 在事务隔离和 projection runner 异步执行正常情况下，第一次 rebuild 应足够。双重重建概率极低但路径存在。
- **直接证据**: `dispatch.py` 行 2368（catch-up 失败触发 rebuild）、行 2238（build 失败触发 rebuild）。
- **影响**: 极端情况下浪费一次 projection rebuild。不影响正确性。
- **建议改法和验证点**: 可在 `_catch_up_memory_projection_before_worker` rebuild 后设置标记，`_build_run_input_with_lag_repair` 检测到已 rebuild 时直接 raise（不再重复 rebuild，交给外层 skip）。
- **修复风险**: 低
- **严重程度**: 低（性能优化，非功能缺陷）

---

## Open Questions

- 无。

---

## Residual Risk

| 风险 | 严重程度 | Owner |
|---|---|---|
| `result_preview` 为 canonical JSON 格式，结构化工具结果（表格/嵌套对象）可能不易被 LLM 解读 | 低 | Phase 12.5 / future — 可增加工具提供方可控摘要字段 |
| 连续 lag repair skip 后 Run 可能长时间停留在 `ACCEPTED` 状态 | 低 | Phase 12.5 / future — 需退避策略或报警 |
| `rebuild_conversation_memory_projection` 对大 session 无超时保护 | 低 | Phase 12.5 / future performance hardening |
| `result_preview` 截断可能切割多字节字符（canonical JSON dumps 为 ASCII-safe，实际无此风险） | 无 | — |
| `_accepted_evidence_envelope_lines` 中 digest 值为不透明 SHA256 哈希，LLM 无法做语义关联 | 无（设计如此，digest 服务 Host 可追溯性而非 LLM 语义） | — |

---

## Verdict

**PASS — ready-to-open-draft-PR.**

全部 5 个前次审查 blocker 均已正确修复，直接证据链路闭合：

1. **Blocker 1（严重）**: LLM compactor 现在通过 `_accepted_evidence_envelope_lines()` 在 prompt 中接收完整 evidence envelope 内容（含 `result_preview` 工具结果预览）。证据提取有事实基础，不再只依赖不透明 ID。
2. **Blocker 2（严重）**: `SNAPSHOT_LAG_OVER_THRESHOLD` 被显式区分，不再触发 Run→FAILED。dispatch 先通过 `_build_run_input_with_lag_repair` 做 rebuild+retry，失败后返回 `"skipped"` 而非 terminal closeout。
3. **Blocker 3（高）**: FakeCompactor 现在消费 `accepted_evidence_envelopes` 全量对象，测试 double 与真实 compactor 在证据消费接口上对齐。
4. **Blocker 4（高）**: catch-up failure 被显式检测，触发 rebuild 而非静默忽略。
5. **Blocker 5（高）**: `EvidenceBackedFactView` claim_text 长度校验已添加到三层防线的最内层。

新增测试覆盖所有关键修复路径，文档（design.md、host/README.md、tests/README.md）已同步更新。无新引入的严重或高严重程度问题。
