# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/wu-cm-01
- Base: main (committed: bf72d350)
- Output file: docs/reviews/wu-cm-01-compact-contract-closure-code-review-mimo.md
- Included scope: 26 unstaged workspace files (11 production `dayu/host/`, 2 config prompts, 2 README, 11 tests)
- Excluded scope: Service assembly, Runtime config schema, durable memory schema, UI, Fins
- Parallel review coverage: 6 subagents covered memory.py/run_input.py, compaction.py, compact_payload.py/compact_artifact.py, compaction_evidence.py/context_fallback.py, tests, scope compliance. 主 reviewer 复核证据链并裁决 severity。

## Findings

### 001-未修复-中-测试隔离回归导致 dispatch scheduler 全量运行失败

- **入口/函数**: `tests/host/test_dispatch_scheduler.py::test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:4310`
- **输入场景**: 全量运行 `pytest tests/host/test_dispatch_scheduler.py` 时，该 test 在前序 test 之后执行
- **实际分支**: `actual_attempt_count == 3`，期望 `expected_attempt_count == 2`
- **预期行为**: reactive overflow 循环在 `max_reactive_compactions_per_run=2` 限制下应产生恰好 2 次 attempt
- **实际行为**: 全量运行时产生 3 次 attempt，单独运行时通过
- **直接证据**: `git stash` 回到 committed state 后全量运行 60 tests 全部通过；恢复 workspace changes 后全量运行出现 1 failed。该 test 的 `expected_attempt_count = 2`（line 4277），断言 `actual_attempt_count == expected_attempt_count`（line 4310）。workspace changes 中 `test_dispatch_scheduler.py` 的唯一修改是将 `compact_request_vnext` 重命名为 `compact`（6 处），这改变了 FakeContextCompactor 子类的方法名。
- **影响**: 测试隔离回归。单独运行通过，全量运行失败。不直接影响 production correctness，但会阻塞 CI 全量回归。
- **建议改法和验证点**: 检查 `_RepeatedReactiveOverflowWorkerFactory` 或 `FakeContextCompactor.compact()` 的状态管理是否在 test 间泄漏。重点排查 `FakeContextCompactor` 是否有 module-level 或 class-level 可变状态被前序 test 修改。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-compaction.py __all__ 缺少 7 个 MAX_VNEXT_* 字符数/标签数常量

- **入口/函数**: `dayu/host/compaction.py` `__all__`
- **文件(行号)**: `dayu/host/compaction.py:2935`（`__all__` 定义处）
- **输入场景**: 下游模块需要引用 `MAX_VNEXT_SESSION_SUMMARY_CHARS`、`MAX_VNEXT_FACT_CLAIM_TEXT_CHARS` 等校验阈值
- **实际分支**: 7 个常量已定义（lines 40-58）但未出现在 `__all__` 中
- **预期行为**: 若这些常量属于 compact contract 的公共边界，应出现在 `__all__` 中
- **实际行为**: 只有 item-count 常量（`MAX_VNEXT_FACT_ITEMS` 等）被导出，char-limit 和 per-item-label 常量未导出
- **直接证据**: `MAX_VNEXT_SESSION_SUMMARY_CHARS`（line 40）、`MAX_VNEXT_FACT_CLAIM_TEXT_CHARS`（line 43）、`MAX_VNEXT_ANSWER_ANCHOR_TEXT_CHARS`（line 46）、`MAX_VNEXT_FORWARD_INTENT_TEXT_CHARS`（line 49）、`MAX_VNEXT_REFERENCE_CONTINUITY_TEXT_CHARS`（line 52）、`MAX_VNEXT_DIAGNOSTIC_TEXT_CHARS`（line 55）、`MAX_VNEXT_SOURCE_LABELS_PER_ITEM`（line 58）均不在 `__all__` 中。这些常量当前只被 `llm_compaction.py` 内部 parser 使用。
- **影响**: 低。这些常量是 Host 内部校验阈值，当前只被同包 `llm_compaction.py` 消费。若未来 quality checker 或 scene adapter 需要引用，需补充导出。
- **建议改法和验证点**: 在 `__all__` 中补充这 7 个常量名。或确认它们确实是 Host 内部实现细节，无需导出。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- `ConversationMemorySnapshot`、durable memory rows、memory projection、RunInputBuilder vNext prompt assembly、dispatch memory precondition、Service assembly 与 Runtime config loader 尚未迁移；owner 是后续 Slice C。Pre-Slice C 对 `memory.py` / `run_input.py` 的修改只关闭旧 compact public symbol owner，不关闭 memory contract。
- Memory projection 仍包含 memory-owned legacy fixture/parser path（`MemoryEvidenceBackedFactKind`、legacy field constants），用于现有 read-model 测试。该路径不从 `dayu.host.compaction` 导入，不作为 compact compatibility contract 导出，但后续 slice 应移除或迁移该 legacy shape。
- External `ContextCompactor` implementor 若存在，可能因 protocol 从旧 candidate 收敛到 vNext output 而需要同步迁移；当前 slice owner 已通过 package exports / tests / pyright 识别仓库内 implementor。
- 完整 Conversation Memory eval benchmark 仍 deferred-with-owner，owner 是 WU-CM-10 / GitHub Issue #80。

## Correctness 证据摘要

| 审查维度 | 结论 | 证据 |
|---|---|---|
| production compact contract 收敛为 ConversationCompactOutputVNext | 通过 | `ContextCompactor.compact()` 返回 `ConversationCompactOutputVNext`（compaction.py:2069-2073）；`__all__` 无旧 candidate 类型 |
| LLM parser 只接受 vNext schema | 通过 | `parse_conversation_compact_output_vnext()` 要求 `schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`（llm_compaction.py:443-454）；旧 schema 输入 fail closed（test_llm_compaction.py:151） |
| quality checker 只接受 vNext | 通过 | `check_conversation_compact_output_vnext()` 按 vNext source section 校验 label（context_governance.py:26-102） |
| operation closeout 使用 vNext | 通过 | `CompactionOperationResult` 使用 `ConversationCompactOutputVNext` 和 `CompactQualityCheckResultVNext`（compaction_operation.py:84-85） |
| event payload 使用 vNext | 通过 | `compact_payload.py` 提供 `compact_artifact_json_vnext()` / `compact_artifact_descriptor_metadata_vnext()`，旧 `preserved_canonical_evidence_refs()` / `preserved_fact_refs_summary()` 已删除 |
| artifact writer 使用 vNext | 通过 | `CompactArtifactWriteRequest` 接受 `ConversationCompactOutputVNext` 和 `CompactQualityCheckResultVNext`（compact_artifact.py:46-47） |
| compaction_evidence 从 vNext payload 派生 | 通过 | `_evidence_backed_fact_refs_from_compacted_event` 读取 `payload["accepted_candidate"]["evidence_backed_facts"]`（compaction_evidence.py:313-342） |
| memory.py 断开旧 compact 依赖 | 通过 | memory.py 零 imports from `dayu.host.compaction` |
| run_input.py 使用 vNext material enums | 通过 | 只引用 vNext `CompactMaterialBlockKind` / `CompactMaterialSection` members |
| 无旧 CompactionCandidate / CompactQualityCheckResult 残留 | 通过 | rg 旧类型名零匹配（除 tests 中的负面断言字符串） |
| 无旧 material fields 残留 | 通过 | `CompactMaterialPack` 字段为 `previous_compacted_view` / `trace_material` / `evidence_material` / `answer_material`；`to_json()` / `llm_json()` 不输出 `stable_input` / `history_input` / `evidence_input` |
| 无 compact_request_vnext / compact_vnext 双 public method | 通过 | `ContextCompactor` 只有单一 `compact()` 方法 |
| EvidenceBackedFactCandidate 处置 | 通过 | 旧 `EvidenceBackedFactCandidate` 已删除；vNext 使用 `EvidenceBackedFactCandidateVNext`；memory projection 使用 memory-owned `EvidenceBackedFactView` |
| prompt 同步到 vNext schema | 通过 | `conversation_compaction.md` 和 `conversation_compaction_user.md` 使用 vNext JSON example 和 source label rules |
| scope 合规 | 通过 | 26 个变更文件全部在 Pre-Slice C allowed files 集合内 |
| type discipline | 通过 | 无 `Any` / `object` / 无类型签名 / `hasattr` / `getattr` 逃逸 / lazy import / extra payload |
| layering | 通过 | 未触碰 Service assembly / Runtime config schema / durable memory schema / UI / Fins |
| README 同步 | 通过 | `dayu/host/README.md` 和 `tests/README.md` 只更新与当前代码不一致的部分，职责正确且不过度 |

## Tests / Pyright 验证

- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py -q`: **191 passed, 1 skipped**
- `source .venv/bin/activate && python -m pyright dayu/host/compaction.py dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/compact_artifact.py dayu/host/compact_payload.py dayu/host/compact_material.py dayu/host/compaction_operation.py dayu/host/compaction_evidence.py dayu/host/context_fallback.py dayu/host/memory.py dayu/host/run_input.py`: **0 errors, 0 warnings, 0 informations**
- `source .venv/bin/activate && pytest tests/host/ -q`: **1140 passed, 2 failed, 2 skipped**。2 个失败为 `test_dispatch_scheduler.py` 中的测试隔离回归（Finding 001），不涉及 production code correctness。

## 结论

**pass-with-findings**

Production compact contract 已正确收敛为 vNext：LLM parser、quality checker、operation closeout、event payload、artifact writer、memory/run_input dependency severance 均语义正确。旧 CompactionCandidate / CompactQualityCheckResult / compact_request_vnext / compact_vnext / old material fields 的 public contract、alias、wrapper、re-export 均已清除。prompt 同步到 vNext schema。scope 合规、type discipline 合格、layering 正确、README 同步恰当。

2 个 findings 均为 non-blocking：
1. 测试隔离回归（中）：`test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 全量运行时 attempt count 偏差，需排查 FakeContextCompactor 状态泄漏。
2. `__all__` 缺少 7 个 char-limit 常量（低）：当前只被同包内部消费，非 blocking。
