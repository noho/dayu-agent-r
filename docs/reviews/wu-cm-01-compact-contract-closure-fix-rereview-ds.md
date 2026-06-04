# WU-CM-01 Compact Contract Closure Fix Re-Review — AgentDS

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure re-review gate |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| previous review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-code-review-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-code-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-code-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md` |
| re-reviewer | AgentDS |
| date | 2026-06-04 |
| output file | `docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-ds.md` |

## Scope

- Mode: current changes (re-review of fix gate output only)
- Branch: phaseflow/wu-cm-01
- Base: HEAD (workspace changes post fix gate)
- Included scope: files modified by fix gate — `dayu/config/prompts/scenes/conversation_compaction_user.md`, `tests/host/test_llm_compaction.py`, `tests/host/test_dispatch_scheduler.py`, `docs/host/wu-cm-01-conversation-memory-plan.md`
- Excluded scope: production code outside fix gate scope; tests not affected by fix gate; README; other plan/control docs
- Review method: 沿 Controller adjudication 的 5 项裁决逐条验证，辅以全量 pytest + pyright 验证

## Controller Adjudication Compliance

### 1. Blocking: forward intent enum mismatch (DS Finding 1)

**裁决**: accepted-blocking。要求修正 prompt 枚举候选值 + 新增测试覆盖。

**验证**:

- `dayu/config/prompts/scenes/conversation_compaction_user.md:35` — `intent_type` 候选值已修正为 `"next_step_note|open_question|pending_clarification|pending_user_visible_task"`，四项全部匹配 `ForwardIntentTypeVNext` enum members（`compaction.py:131-134`）。
- `dayu/config/prompts/scenes/conversation_compaction_user.md:37` — `status` 候选值已修正为 `"open|blocked|superseded"`，三项全部匹配 `ForwardIntentStatusVNext` enum members（`compaction.py:140-142`）。
- 旧错误值 `user_constraint`、`working_assumption`、`resolved` 已从 prompt 中完全清除。
- `tests/host/test_llm_compaction.py:155-169` — 新增 `test_prompt_forward_intent_enum_values_match_parser_vnext`，通过 `_prompt_schema_pipe_values()` helper（`test_llm_compaction.py:302-318`）从 prompt template 中读取 pipe-separated 枚举候选值，逐项构造 `ForwardIntentTypeVNext` / `ForwardIntentStatusVNext`，并断言构造后数量不减少（即无 ValueError 抛出）。
- `_prompt_schema_pipe_values` 的解析逻辑：从 `conversation_compaction_user.md` 中按 `"field_name": "` 前缀定位行，提取 pipe-separated 值，过滤空字符串。对 `intent_type` 提取到 `("next_step_note", "open_question", "pending_clarification", "pending_user_visible_task")`，对 `status` 提取到 `("open", "blocked", "superseded")`。
- 测试通过（28 passed in `test_llm_compaction.py + test_compaction_contract.py`）。

**额外检查**: prompt 中另有 `evidence_kind`（line 20: `"tool_result|tool_source_text|accepted_evidence_material"`）和 `reason`（line 44: `"local_reference|ordinal_reference|ellipsis_recovery|recent_state"`）两个 pipe-separated 字段。经验证，`evidence_kind` 候选值全部匹配 `FactEvidenceKindVNext`（`compaction.py:123-125`），`reason` 候选值全部匹配 `ReferenceContinuityReasonVNext`（`compaction.py:148-151`），不存在同类 mismatch。这两个字段未被 `test_prompt_forward_intent_enum_values_match_parser_vnext` 覆盖，但 Controller 原始 finding 仅要求 forward intent enum 覆盖，当前测试范围符合裁决要求。

**结论**: 通过。

### 2. Blocking: test_dispatch_scheduler.py test regression (MiMo Finding 001)

**裁决**: accepted-blocking。要求 `pytest tests/host/test_dispatch_scheduler.py -q` 全文件通过。

**验证**:

- `tests/host/test_dispatch_scheduler.py:4280` — `expected_attempt_count = max_reactive_compactions_per_run + 1`（当 `max_reactive_compactions_per_run=2` 时为 3）。
- `tests/host/test_dispatch_scheduler.py:4293-4297` — 改为等待最终 `CONTEXT_COMPACTION_FAILED` event（`_wait_for_event_count`），而非原实现等待第一个 `CONTEXT_COMPACTED`。这确保测试读取的是终态而非中间竞态。
- `tests/host/test_dispatch_scheduler.py:4313-4331` — 断言终态：`run.status == RunStatus.FAILED`、`factory.created == expected_attempt_count`（3）、`actual_attempt_count == expected_attempt_count`（3）、2 个 `CONTEXT_COMPACTION_REQUESTED`、2 个 `CONTEXT_COMPACTED`、1 个 `CONTEXT_COMPACTION_FAILED`（reason=`reactive_compact_limit_reached`）、失败 payload 为 no-fallback diagnostic 形态、无 `RUN_LOST`。
- `pytest tests/host/test_dispatch_scheduler.py -q` → **60 passed**。
- `pytest tests/host/ -q` → **1143 passed, 2 skipped, 5 deselected**。

**attempt count 语义分析**:

- `max_reactive_compactions_per_run=2` 时，`expected_attempt_count=3` 的语义路径：第 1 次 reactive compaction 成功 → overflow 再次触发 → 第 2 次成功 → overflow 再次触发 → 第 3 次因 `reactive_compact_limit_reached` fail closed。共 3 次 attempt（2 成功 + 1 失败）。
- 原实现的 `expected_attempt_count=2` 是在等待第一个 `CONTEXT_COMPACTED` 时读取中间态的结果——此时后台 loop 可能尚未推进到 limit，也可能已创建下一次 attempt。这不是 production attempt accounting 的语义错误，而是测试读取中间态的竞态。
- 修复后测试等待终态 `CONTEXT_COMPACTION_FAILED`，读取的是稳定终态，attempt count 语义合理，不是掩盖 production bug。

**结论**: 通过。

### 3. Non-blocking: scope fallout recording (DS Finding 2)

**裁决**: accepted-non-blocking。要求在 fix artifact 或 plan 中补记 necessary dependency fallout。

**验证**:

- `docs/host/wu-cm-01-conversation-memory-plan.md:264-267` — 已补记 "necessary dependency fallout" 段落：
  - prompt files（`conversation_compaction.md` / `conversation_compaction_user.md`）仅限 vNext prompt schema、vNext material field name 与 parser enum member replacement。
  - `context_fallback.py` 仅限 fallback recent-window view 对 vNext material section / enum member 的类型对齐。
  - 明确不扩大到 config-service、scene assembly、runtime prompt loading、fallback behavior、memory durable/projection 语义。
- `docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md:69-80` — fix artifact 记录了 scope recording 的内容。
- `context_fallback.py` 的实际 diff（`git diff HEAD -- dayu/host/context_fallback.py`）确认只有 4 行 enum member 替换：`STABLE_INPUT` → `PREVIOUS_COMPACTED_VIEW`（line 556），`RAW_USER_TURN` / `RAW_ASSISTANT_TURN` → `USER_INPUT` / `ASSISTANT_FINAL_ANSWER`（lines 627-628）。未扩大范围。

**结论**: 通过。

### 4. Deferred: memory legacy projection parser path (DS Finding 3)

**裁决**: deferred-with-owner，owner 为后续 Slice C。本 fix 不要求删除。

**验证**:

- `dayu/host/memory.py:1494-1525` — `_validate_memory_projection_compacted_payload()` 仍保留 legacy/vNext 双路径分发逻辑。`_is_vnext_compacted_payload()` 检查 `accepted_candidate` 字段存在性；vNext path 调用 `_validate_memory_projection_vnext_compacted_payload()`，legacy path（lines 1509-1515）仍读取 `_PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE`、`_PAYLOAD_FIELD_PINNED_STATE_PATCH_CANDIDATE` 等旧字段。
- `git diff HEAD -- dayu/host/memory.py` 确认 fix gate 期间 `memory.py` 未被触碰（diff 仅包含 implementation gate 的旧 compact import 删除）。
- `MemoryEvidenceBackedFactKind`（`memory.py:136`）仍存在，是 memory-owned enum，未从 `dayu.host.compaction` 导入。
- 这些均符合 Controller 的 deferred-with-owner 裁决：legacy path 未删除，不属于 compact public contract，owner 为 Slice C。

**结论**: 通过（未误删）。

### 5. Rejected: MAX_VNEXT_* __all__ (MiMo Finding 002)

**裁决**: rejected-with-reason。当前这些常量仅由同包 parser 内部消费，保持较小 public surface。

**验证**:

- `dayu/host/compaction.py:2935-2994` — `__all__` 包含 5 个 `MAX_VNEXT_*_ITEMS` item-count 常量，但不包含 7 个 `MAX_VNEXT_*_CHARS` / `MAX_VNEXT_*_LABELS_PER_ITEM` char/label limit 常量。
- 7 个 char/label 常量（`compaction.py:40-58`）仍为模块级定义，仅由同包 `llm_compaction.py` parser 内部消费，未扩大为 public contract。

**结论**: 通过（未误加）。

## Validation

以下验证均在 `source .venv/bin/activate` 后运行，结果与 fix artifact 声明一致：

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q` | 28 passed |
| `pytest tests/host/test_dispatch_scheduler.py -q` | 60 passed |
| `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py -q` | 88 passed |
| `pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` | 99 passed |
| `pytest tests/host/test_package_exports.py tests/host/test_public_compact_smoke.py -q` | 15 passed, 1 skipped |
| `pytest tests/host/ -q` | 1143 passed, 2 skipped, 5 deselected |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Findings

### 1-未修复-低-prompt 中 evidence_kind / reason 枚举值未被自动化测试覆盖

- **入口/函数**: `test_prompt_forward_intent_enum_values_match_parser_vnext` → `_prompt_schema_pipe_values`
- **文件(行号)**: `tests/host/test_llm_compaction.py:155-169`
- **输入场景**: 未来有人修改 prompt 中 `evidence_kind` 或 `reason` 的 pipe-separated 候选值为 parser 不接受的枚举值
- **实际分支**: 当前测试只覆盖 `intent_type` 和 `status` 两个 forward_intent 字段，未覆盖 prompt 中同样使用 pipe-separated 枚举值的 `evidence_kind`（line 20）和 `reason`（line 44）
- **预期行为**: prompt 中所有 pipe-separated 枚举候选值都有自动化测试保护
- **实际行为**: `evidence_kind` 映射到 `FactEvidenceKindVNext`，`reason` 映射到 `ReferenceContinuityReasonVNext`，当前值均正确（已人工验证），但无自动化保护
- **直接证据**: `test_llm_compaction.py:158-159` 只调用 `_prompt_schema_pipe_values("intent_type")` 和 `_prompt_schema_pipe_values("status")`；`conversation_compaction_user.md:20` 含 `"evidence_kind": "tool_result|tool_source_text|accepted_evidence_material"`、line 44 含 `"reason": "local_reference|ordinal_reference|ellipsis_recovery|recent_state"`
- **影响**: 低。Controller 原始 finding 仅要求 forward_intent 覆盖，当前实现符合裁决要求。`evidence_kind` 和 `reason` 的枚举值已经过人工验证正确。若未来 prompt 修改引入不一致，需依赖 review 或运行时 fail closed 发现。
- **建议改法和验证点**: 可扩展 `test_prompt_forward_intent_enum_values_match_parser_vnext` 或新增 companion test，对 `evidence_kind` 和 `reason` 做同样的一致性断言。非本 gate blocking。
- **修复风险（低）**: 纯测试扩展，不涉及 production code。
- **严重程度（低）**: non-blocking，当前值已验证正确，Controller 裁决范围已覆盖。

## Open Questions

- 无。

## Residual Risk

- prompt 中 `evidence_kind` 和 `reason` 枚举值与 parser enum 的一致性无自动化保护（见 Finding 1）。当前值正确，风险低。
- Deferred Slice C memory legacy path（`memory.py:1509-1515`）仍未迁移；owner 为 Slice C。
- 本 re-review 未重新检查 fix gate 范围外的 production code、README 或 plan doc 的其他部分；这些已在 DS/MiMo 初轮 review 中覆盖。

## Conclusion

**pass**

Controller 5 项裁决逐一验证通过：

1. forward intent enum mismatch — prompt 已修正，测试已覆盖。
2. test_dispatch_scheduler.py test regression — 全文件 60 passed，attempt count 语义正确（终态读取）。
3. scope fallout recording — plan 已补记 necessary dependency fallout，范围限定正确。
4. memory legacy path — 未误删，deferred to Slice C。
5. MAX_VNEXT_* __all__ — 未误加，保持内部实现细节。

全量 pytest（1143 passed）+ pyright（0 errors）通过。

一项 non-blocking 低严重度 finding：`evidence_kind` / `reason` 枚举值未被自动化测试覆盖，但当前值已验证正确，Controller 裁决未要求覆盖这两个字段。
