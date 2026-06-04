# WU-CM-01 Compact Contract Closure Code Review — AgentDS

## Scope

- Mode: current changes
- Branch: phaseflow/wu-cm-01
- Base: HEAD (current workspace changes)
- Output file: docs/reviews/wu-cm-01-compact-contract-closure-code-review-ds.md
- Design source: docs/host/design.md
- Plan source: docs/host/wu-cm-01-conversation-memory-plan.md (Pre-Slice C)
- Implementation artifact: docs/reviews/wu-cm-01-compact-contract-closure-implementation-retry-codex.md
- Accepted plan commits: ff6c225a, bf72d350
- Included scope: all modified files (26 files, staged and unstaged changes relative to HEAD)

## Findings

### 1-未修复-高-LLM prompt 中 forward intent type/status 枚举值与 parser 不一致

- **入口/函数**: `LLMContextCompactor.compact()` → `parse_conversation_compact_output_vnext()` → `_forward_intent_candidates_vnext()`
- **文件(行号)**: `dayu/config/prompts/scenes/conversation_compaction_user.md:35-38` 与 `dayu/host/compaction.py:128-152`
- **输入场景**: LLM 根据 user prompt 模板中的 schema 示例产出 `forward_intents` 条目
- **实际分支**: parser 在 `llm_compaction.py:557` 执行 `ForwardIntentTypeVNext(_required_string(data, "intent_type"))` 和 `ForwardIntentStatusVNext(_required_string(data, "status"))`
- **预期行为**: prompt 中给出的枚举候选值与 parser 的 `ForwardIntentTypeVNext` / `ForwardIntentStatusVNext` 完全一致
- **实际行为**:
  - Prompt 第 35 行：`"intent_type": "next_step_note|open_question|user_constraint|working_assumption"` — 包含 `user_constraint` 和 `working_assumption`
  - Prompt 第 37 行：`"status": "open|resolved"` — 包含 `resolved`
  - `ForwardIntentTypeVNext` 实际枚举值（compaction.py:128-136）：`open_question`、`pending_clarification`、`pending_user_visible_task`、`next_step_note` — **不含** `user_constraint` 或 `working_assumption`
  - `ForwardIntentStatusVNext` 实际枚举值（compaction.py:137-142）：`open`、`blocked`、`superseded` — **不含** `resolved`
- **直接证据**:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md:35`：`"intent_type": "next_step_note|open_question|user_constraint|working_assumption"`
  - `dayu/config/prompts/scenes/conversation_compaction_user.md:37`：`"status": "open|resolved"`
  - `dayu/host/compaction.py:128-136`：`class ForwardIntentTypeVNext(StrEnum): OPEN_QUESTION = "open_question"; PENDING_CLARIFICATION = "pending_clarification"; PENDING_USER_VISIBLE_TASK = "pending_user_visible_task"; NEXT_STEP_NOTE = "next_step_note"`
  - `dayu/host/compaction.py:137-142`：`class ForwardIntentStatusVNext(StrEnum): OPEN = "open"; BLOCKED = "blocked"; SUPERSEDED = "superseded"`
  - `dayu/host/llm_compaction.py:557`：`ForwardIntentTypeVNext(_required_string(data, "intent_type"))` — StrEnum 构造对未知字符串会抛出 ValueError
- **影响**: LLM 若按 prompt 示例输出 `"intent_type": "user_constraint"` 或 `"status": "resolved"`，`ForwardIntentTypeVNext()` / `ForwardIntentStatusVNext()` 构造将抛出 `ValueError`，被 `llm_compaction.py:420` 的 `except (KeyError, TypeError, ValueError)` 捕获，整个 proposal fail closed。由于 operation 采用 whole-candidate repair（compaction_operation.py:146），单字段枚举非法即导致整体 proposal 被拒绝，浪费一次 repair attempt 预算。
- **建议改法和验证点**:
  1. 修正 prompt 中的 `intent_type` 候选值为 `next_step_note|open_question|pending_clarification|pending_user_visible_task`
  2. 修正 prompt 中的 `status` 候选值为 `open|blocked|superseded`
  3. 验证方法：在 `test_llm_compaction.py` 或 `test_compaction_contract.py` 中新增测试，断言 LLM prompt 模板中出现的所有枚举候选值都能通过 parser 的 StrEnum 构造
- **修复风险（低）**: 纯文本替换，不涉及 parser、schema 或 contract 变更
- **严重程度（高）**: 运行时可能导致所有 forward intent candidate 被 rejection，影响 compaction 成功率

### 2-未修复-中-Pre-Slice C 范围外文件被修改

- **入口/函数**: Pre-Slice C allowed files 边界
- **文件(行号)**:
  - `dayu/config/prompts/scenes/conversation_compaction.md` — 不在 Pre-Slice C allowed files 中
  - `dayu/config/prompts/scenes/conversation_compaction_user.md` — 不在 Pre-Slice C allowed files 中
  - `dayu/host/context_fallback.py` — 不在 Pre-Slice C allowed files 中（仅列在 Slice B 和 Slice C）
- **输入场景**: 删除旧 `CompactMaterialBlockKind` enum members（PINNED_STATE、WORKING_ASSUMPTION、RAW_USER_TURN、RAW_ASSISTANT_TURN、EPISODE_SUMMARY 等）与旧 `CompactMaterialSection` members（STABLE_INPUT、HISTORY_INPUT、EVIDENCE_INPUT）后，下游文件必须同步迁移
- **实际分支**: 这些文件因旧 enum member 删除而需要同步更新引用
- **预期行为**: Pre-Slice C 只修改 allowed files 列表中的文件；若下游文件因旧 symbol 删除而无法编译，应由 Slice B 或 Slice C 在自己的范围内解决
- **实际行为**:
  - `context_fallback.py:556` — `CompactMaterialSection.STABLE_INPUT` → `CompactMaterialSection.PREVIOUS_COMPACTED_VIEW`
  - `context_fallback.py:627-628` — `CompactMaterialBlockKind.RAW_USER_TURN/RAW_ASSISTANT_TURN` → `CompactMaterialBlockKind.USER_INPUT/ASSISTANT_FINAL_ANSWER`
  - `conversation_compaction.md:10-14` — 更新 label 引用规则为 vNext section
  - `conversation_compaction_user.md:5-60` — 更新输出 schema 示例为 vNext
- **直接证据**: Pre-Slice C plan 章节的 allowed files/modules 列表不包含这三个文件；git diff 显示这些文件有实际修改
- **影响**: prompt 文件本身是必要的——旧 prompt 会让 LLM 产出旧格式 candidate，与 vNext parser 不兼容。context_fallback.py 的修改量极小（4 行，纯 enum member 替换），且修改本身语义正确。这些修改对 Pre-Slice C 目标的达成是必要的，但超出了 plan 声明的文件边界
- **建议改法和验证点**: 在 implementation report 中明确记录 scope drift，或确认 plan 接受这些文件为 Pre-Slice C 的必要依赖 fallout。不影响 correctness
- **修复风险（低）**: 无需回退代码，只需记录 scope drift
- **严重程度（中）**: 不影响功能正确性，但 plan-to-implementation 一致性有缺口

### 3-未修复-低-memory.py 保留 memory-owned legacy projection parser path

- **入口/函数**: `_validate_compacted_payload_for_memory_projection()` → `_validate_memory_projection_compacted_payload()` → legacy branch
- **文件(行号)**: `dayu/host/memory.py:1491-1700`（新增 `_validate_memory_projection_compacted_payload` 及相关私有函数）；`dayu/host/memory.py:107-121`（新增 `MemoryEvidenceBackedFactKind`、`MemoryContinuityPreserveReason`）
- **输入场景**: memory projection 消费 `CONTEXT_COMPACTED` event payload
- **实际分支**: `_is_vnext_compacted_payload()` 在 `accepted_candidate` 存在时走 vNext path，否则走 legacy path（仍从旧 `episode_summary_candidate`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates` 读取）
- **预期行为**: memory projection 只消费 vNext compact payload
- **实际行为**: legacy branch 仍存在，作为 memory-owned fallback。Codex report 第 62 行正确描述为 "memory-owned legacy fixture/parser path"，并注明 "not exported as compact public contract"
- **直接证据**: `memory.py:1506-1512` — legacy path 读取 `_PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE`、`_PAYLOAD_FIELD_PINNED_STATE_PATCH_CANDIDATE`、旧 `_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES`（即 `"evidence_backed_fact_candidates"`）。`MemoryEvidenceBackedFactKind` 是 memory 模块自有 enum，不从 `dayu.host.compaction` 导入
- **影响**: legacy path 是 memory projection 的内部实现细节，不为 compact contract 提供兼容性。但存在一个微妙的语义问题：`_validate_compacted_payload_for_memory_projection()` 的 fact-validation 分支在 vNext path 下使用 `_validate_memory_projection_vnext_compacted_payload()`，其中 fact 校验逻辑与旧 path 不同——旧 path 对 fact-candidate-only invalid 做降级处理（剥掉 facts 后用 patched payload 重校验），vNext path 的实现需要在 `_validate_memory_projection_vnext_compacted_payload()` 中对应处理
- **建议改法和验证点**: 在 Slice C（memory projection closure）中确认 vNext path 的 fact-validation 降级逻辑与 legacy path 语义等价，或明确声明 vNext 不支持 legacy 的 fact-candidate-only invalid 降级
- **修复风险（中）**: 涉及 memory projection 的 fact validation 语义，需在 Slice C 中作为明确验证项
- **严重程度（低）**: non-blocking；不影响 compact contract closure；属于 Pre-Slice C 范围外的 residual risk，owner 是 Slice C

## Open Questions

- 无。

## Residual Risk

### Compact contract closure 已验证通过

- 旧 `CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PreservationEvidence`、`PinnedPatchOperation` 与旧 `CompactQualityCheckResult`（非 VNext）在 `dayu/host/` 全量 production closeout files 中无 class definition、无 public export、无 production reference（grep 结果为空）。
- `compact_request_vnext`/`compact_vnext` 双 public method 未形成；`ContextCompactor` protocol 仅保留单一 `compact()` vNext method；`LLMContextCompactor.compact()` 是唯一 production implementor。
- 旧 `stable_input`/`history_input`/`evidence_input` material field 在 production closeout files 中无 alias、wrapper 或 re-export（grep 结果仅命中 `compaction_evidence.py` 的函数名 `collect_selected_compaction_request_evidence_inputs`，不是字段引用）。
- `CompactMaterialPack` JSON/LLM JSON 不再输出 `stable_input`、`history_input`、`evidence_input`；`to_json()`/`llm_json()` 使用 vNext 字段 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`。
- `LLMContextCompactor.compact()` production parser 只返回 `ConversationCompactOutputVNext`；旧 schema 输入 fail closed。
- `check_conversation_compact_output_vnext()` 按 vNext section allowlist 校验 label；section allowlist 规则（compaction.py:154-192）与 design 24.3 一致。
- `EvidenceBackedFactCandidate`（旧）已删除，不做 alias、wrapper 或 re-export。vNext 只使用 `EvidenceBackedFactCandidateVNext`。
- `memory.py` 与 `run_input.py` 不再从 `dayu.host.compaction` 导入旧 compact candidate/type symbols。保留的 old-field 引用均为本模块私有常量或 memory-owned typed shape。
- `context_events.py` 中旧 compact field 常量均为私有（`_FIELD_*` 前缀），仅用于 `_COMPACTED_OLD_FIELDS` denylist fail-closed 机制，不作为 public event contract 导出。

### Tests and pyright

- Pre-Slice C 要求的核心测试全部通过：`test_compaction_contract.py`、`test_llm_compaction.py`、`test_compaction_operation.py`、`test_compact_material.py`、`test_compact_artifact_store.py` — 87 passed
- memory/run_input dependency severance 测试全部通过：`test_memory_projection.py`、`test_run_input_builder.py` — 99 passed
- pyright 全量通过：0 errors, 0 warnings, 0 informations
- 当前未运行 conditional 测试（`test_package_exports.py`、`test_public_compact_smoke.py`、`test_public_open_host_options.py`、`test_open_host_runtime.py`），但 Codex report 声明这些测试也通过（15 passed, 1 skipped）

### 未覆盖/未检查区域

- ForwardIntentTypeVNext/ForwardIntentStatusVNext 枚举值与 prompt 模板的一致性无自动化测试保护（Finding 1）
- `memory.py` 的 vNext compacted payload validation path（`_validate_memory_projection_vnext_compacted_payload`）在 fact-candidate-only invalid 场景下的降级行为与 legacy path 的对齐情况未单独检查
- `dayu/host/open_host.py` 与 `dayu/host/api.py` 的 compactor construction/typed option 对齐变更未逐行审查（Codex report 声称仅限类型对齐）

## Conclusion

**pass-with-findings**

Finding 1（高严重度）是 correctness issue：prompt-to-parser 的 `ForwardIntentTypeVNext`/`ForwardIntentStatusVNext` 枚举值不一致会导致 LLM 产出合法 prompt 值但被 parser reject，应在 merge 前修复。

Finding 2（中严重度）是 scope 记录问题，不影响 correctness。

Finding 3（低严重度）是 non-blocking residual risk，明确 owner 为 Slice C。
