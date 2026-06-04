# WU-CM-01 Compact Contract Closure Fix Re-Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: phaseflow/wu-cm-01
- Base: main (committed: bf72d350)
- Output file: docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-mimo.md
- Design source: docs/host/design.md
- Controller adjudication: docs/reviews/wu-cm-01-compact-contract-closure-code-review-controller-adjudication.md
- Fix artifact: docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md
- Included scope: fix artifact 中声明的 5 个变更文件 + 验证所需全部 host tests / pyright

## 复审目标

只判断 fix 是否完整处理 Controller accepted findings。不修改 production code、tests、README、plan 或 control doc。

## Finding Adjudication 对照

### Controller accepted-blocking #1: forward intent enum mismatch

**裁决**: fixed。

**证据**:

1. `conversation_compaction_user.md:35` — `"intent_type": "next_step_note|open_question|pending_clarification|pending_user_visible_task"`。与 `ForwardIntentTypeVNext`（compaction.py:128-134）完全一致：`OPEN_QUESTION`、`PENDING_CLARIFICATION`、`PENDING_USER_VISIBLE_TASK`、`NEXT_STEP_NOTE`。
2. `conversation_compaction_user.md:37` — `"status": "open|blocked|superseded"`。与 `ForwardIntentStatusVNext`（compaction.py:137-142）完全一致：`OPEN`、`BLOCKED`、`SUPERSEDED`。
3. 新增测试 `test_prompt_forward_intent_enum_values_match_parser_vnext`（test_llm_compaction.py:155-169）通过 `_prompt_schema_pipe_values()` 从 prompt 模板读取 pipe-separated 枚举值，逐个构造 `ForwardIntentTypeVNext` / `ForwardIntentStatusVNext`，断言长度一致。该测试直接从 prompt 文件读取真实模板，不依赖硬编码值。
4. 验证结果：`pytest tests/host/test_llm_compaction.py -q` — 28 passed。

**注意**: 该测试是 consistency test（prompt 值能被 enum 接受），不验证 prompt 中缺少 enum 定义的某个值。但这符合 Controller 要求——"断言 prompt 中列出的 forward intent enum 值均能被 parser enum 接受"。若未来 enum 新增成员而 prompt 未同步，该测试不会捕获；但 enum 新增是 rare event，且 prompt 与 enum 同属同一 slice owner，风险可控。

### Controller accepted-blocking #2: dispatch scheduler test regression

**裁决**: fixed。

**证据**:

1. 原测试等待第一个 `CONTEXT_COMPACTED` 后读取 `actual_attempt_count`，存在竞态（中间态 2 vs 最终态 3）。
2. 修复后测试等待最终 `CONTEXT_COMPACTION_FAILED`（test_dispatch_scheduler.py:4293-4297），断言稳定终态。
3. `expected_attempt_count = max_reactive_compactions_per_run + 1`（line 4280）：`max_reactive_compactions_per_run=2` 时期望 3 次 attempt。语义：2 次成功 compact + 1 次 overflow fail closed。
4. 断言 `factory.created == expected_attempt_count`（line 4314）、`actual_attempt_count == expected_attempt_count`（line 4316）、`CONTEXT_COMPACTION_REQUESTED` 和 `CONTEXT_COMPACTED` 各 2 次（lines 4317-4322）、`CONTEXT_COMPACTION_FAILED` 1 次（line 4323）、`failure_reason == "reactive_compact_limit_reached"`（line 4324）、无 `RUN_LOST`（line 4331）。
5. 验证结果：`pytest tests/host/test_dispatch_scheduler.py -q` — 60 passed。全量 host tests — 1144 passed, 1 skipped, 5 deselected。

**attempt count 语义审查**: `expected_attempt_count = 3` 不是掩盖 bug。`max_reactive_compactions_per_run=2` 限制的是成功 compact 次数；第三次 attempt 是 overflow worker 在 budget limit 后触发的 fail-closed attempt，它产生 `CONTEXT_COMPACTION_FAILED` 而非 `CONTEXT_COMPACTED`。该语义在 `reactive_compact_limit_reached` failure reason 中明确表达。

### Controller accepted-non-blocking: scope fallout

**裁决**: fixed。

**证据**: `docs/host/wu-cm-01-conversation-memory-plan.md:264-267` 新增 `necessary dependency fallout` 段落，记录：
- `conversation_compaction.md` / `conversation_compaction_user.md` — 仅限 vNext prompt schema、vNext material field name 与 parser enum member replacement。
- `context_fallback.py` — 仅限 fallback recent-window view 对 vNext material section / enum member 的类型对齐。
- 明确不扩大到 config-service、scene assembly、runtime prompt loading、fallback behavior、memory durable/projection 语义。

### Controller deferred-with-owner: memory legacy path

**裁决**: 正确 deferred。

Fix artifact 明确记录 "未修复；Controller 裁决为 `deferred-with-owner`，owner 是后续 Slice C memory projection closure"。不在本 fix gate 删除。

### Controller rejected: MAX_VNEXT_* in __all__

**裁决**: 正确 rejected。

Fix artifact 明确记录 "Controller 已 rejected，保持内部实现细节"。不在本 fix gate 修改。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `test_prompt_forward_intent_enum_values_match_parser_vnext` 只验证 prompt 列出的值能被 enum 接受，不验证 enum 所有成员都在 prompt 中列出。若 enum 新增成员而 prompt 未同步，该测试不会捕获。风险可控：enum 与 prompt 同属同一 slice owner，且 prompt 是 LLM 产出的唯一 schema 示例。
- memory-owned legacy projection parser path 仍存在，owner 是后续 Slice C。已在 fix artifact 和本 artifact 中记录。

## 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q` | 28 passed |
| `pytest tests/host/test_dispatch_scheduler.py -q` | 60 passed |
| `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py -q` | 88 passed |
| `pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` | 99 passed |
| `pytest tests/host/test_package_exports.py tests/host/test_public_compact_smoke.py -q` | 15 passed, 1 skipped |
| `python -m pyright dayu/host/ tests/host/` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/host/ -q`（全量） | 1144 passed, 1 skipped, 5 deselected |

## Conclusion

**pass**

Controller accepted findings 已完整处理：
1. Prompt enum mismatch 已修复，新增 consistency test 覆盖。
2. Dispatch scheduler test regression 已修复，attempt count 语义合理（2 次成功 + 1 次 fail closed = 3）。
3. Scope fallout 已在 plan 中补记。
4. Deferred / rejected items 按 Controller 裁决正确处理。
5. 所有验证项（pytest + pyright）通过，包括全量 host tests 无失败。
