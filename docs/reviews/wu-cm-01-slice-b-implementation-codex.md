# WU-CM-01 Slice B Implementation Blocker

日期：2026-06-04

## 结论

Slice B 的动机成立：production compaction operation 与 proactive dispatch compacted 事件仍存在旧 `CompactionCandidate` / 旧 compacted payload 闭环，和已接受的 vNext candidate 设计不一致。已完成的修改把 operation、vNext compactor 调用、accepted/rejected/failed operation 测试、context compacted payload validator/helper、fake compactor、proactive dispatch compacted artifact/event 写入切到 vNext candidate。

当前不能继续完成整条 reactive recovery 闭环，因为 remaining reactive failures 的 accepted `CONTEXT_COMPACTED` 写入代码实际位于 `dayu/host/engine_ingest.py`，该文件不在 accepted Slice B allowed files 中。继续修复会违反本轮 allowed list。建议 controller 回到 plan fix/reslice，或明确扩大 Slice B allowed files，把 `dayu/host/engine_ingest.py` 纳入本 slice。

## 已完成/已修改范围

已修改文件均在用户给定 Slice B allowed files 范围内：

- `dayu/host/compaction.py`
  - 增加 vNext request-level compactor protocol：operation 可用 `CompactionRequest` 直接调用 vNext compact。
- `dayu/host/llm_compaction.py`
  - 增加 `compact_request_vnext`，从 `CompactionRequest.material_pack` 派生 `ConversationCompactInputVNext` 后调用现有 vNext compaction。
- `dayu/host/compaction_operation.py`
  - operation accepted candidate / quality result 切到 vNext 类型。
  - 删除 operation path 内旧 candidate merge、pinned patch merge、minimum preserve merge 逻辑。
  - 多 pass 不再做旧字段 patch merge；accepted candidate 为最后一次通过质量检查的完整 vNext candidate。
- `dayu/host/context_events.py`
  - `CONTEXT_COMPACTED` payload builder / validator 切到 vNext accepted candidate 与 vNext quality result。
  - compacted payload 拒绝旧字段作为事件兼容入口。
- `dayu/host/compact_payload.py`
  - compact payload helper 切到 vNext accepted evidence mapping 读取。
- `dayu/host/dispatch.py`
  - proactive compaction accepted event/artifact 写入切到 vNext compact artifact JSON 与 vNext payload。
  - proactive represented evidence refs 改为从 vNext accepted evidence mapping 推导。
- `tests/host/fake_compaction.py`
  - fake compactor 增加 vNext request-level 调用路径。
- `tests/host/test_compaction_operation.py`
  - operation tests 切到 vNext candidate / vNext quality check / vNext multi-pass 行为。
- `tests/host/test_context_compact_events.py`
  - compacted event tests 切到 vNext payload contract。
- `tests/host/test_dispatch_scheduler.py`
  - proactive dispatch fake compactor 与部分断言切到 vNext。

未修改任何未授权模块；特别是未修改 `dayu/host/engine_ingest.py`。当前 `git diff --name-only` 只包含上述 10 个 allowed 文件，外加本 blocker artifact。

## 已通过验证

已运行并通过：

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py -q`
  - 结果：`41 passed`
- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py -q`
  - 结果：`33 passed`
- `python -m py_compile dayu/host/compaction_operation.py dayu/host/context_events.py dayu/host/compact_payload.py dayu/host/dispatch.py tests/host/fake_compaction.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py`
  - 结果：通过

未运行最终全量指定 pytest/pyright 收口，因为 Slice B 当前存在明确 allowed-files blocker，继续扩大修复会越界。

## 当前失败测试

最近一次 `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q` 仍有 4 个失败：

- `tests/host/test_dispatch_scheduler.py::test_multi_turn_proactive_compact_feeds_subsequent_run_input`
- `tests/host/test_dispatch_scheduler.py::test_reactive_overflow_recovers_and_dispatches_new_attempt`
- `tests/host/test_dispatch_scheduler.py::test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit`
- `tests/host/test_dispatch_scheduler.py::test_reactive_recovery_uses_fresh_duplicate_governance_attempt`

第一项是后续 RunInput/projection 消费 vNext compacted event 的问题，属于 Slice C/D 明确禁止范围：memory projection / RunInputBuilder 仍按旧 compacted payload 字段读取，测试继续要求 compacted 后的 subsequent run input 能被投影消费。该失败不应在 Slice B 内通过修改 memory durable/projection 或 RunInputBuilder 解决。

后三项是 reactive compaction accepted closeout 问题，root cause 在 `engine_ingest.py`。

## Root Cause 直接证据

### Reactive accepted closeout 仍在 `engine_ingest.py`

直接代码证据：

- `dayu/host/engine_ingest.py:58` 仍导入旧 artifact 写入入口：
  - `CompactArtifactStore`
  - `CompactArtifactWriteRequest`
- `dayu/host/engine_ingest.py:66-75` 仍导入旧 compaction 类型：
  - `CompactQualityCheckResult`
  - `CompactionCandidate`
  - `ContextCompactor`
- `dayu/host/engine_ingest.py:1666-1673` reactive recovery accepted 分支调用 `_append_reactive_compacted_event(...)`，并把 `operation_result.accepted_candidate` 传给 `candidate=`。
- `dayu/host/engine_ingest.py:1696-1705` `_append_reactive_compacted_event` 的签名仍要求：
  - `candidate: CompactionCandidate`
  - `quality: CompactQualityCheckResult`
- `dayu/host/engine_ingest.py:1719-1738` 仍通过 `CompactArtifactStore(...).write_compact_artifact(CompactArtifactWriteRequest(...))` 写旧 compact artifact。
- `dayu/host/engine_ingest.py:1761-1766` 仍用旧形态调用 `build_context_compacted_payload(...)`，只传 `compact_artifact_ref`、`compact_artifact_digest`、`accepted_candidate`、`quality_check_result`。

这些证据说明 reactive accepted `CONTEXT_COMPACTED` closure 的生产路径不是 `dispatch.py`，而是 `engine_ingest.py`。Slice B allowed files 只允许修改 `dispatch.py` 的 proactive/reactive compaction 编排，不包含 `engine_ingest.py`，因此无法在不越界的情况下完成 reactive accepted vNext event closure。

### 旧 artifact store 与 vNext candidate 类型冲突

直接代码证据：

- `dayu/host/compact_artifact.py:40-56` 的 `CompactArtifactWriteRequest.accepted_candidate` 类型仍是 `CompactionCandidate`。
- `dayu/host/compact_artifact.py:71-75` 在 `__post_init__` 中强校验 `accepted_candidate` 必须是 `CompactionCandidate`。

当前 operation 已按 Slice B 切到 `ConversationCompactOutputVNext`，因此 reactive accepted 分支把 vNext candidate 交给 `CompactArtifactWriteRequest` 时会触发类型错误。最近失败输出中的关键错误为：

- `TypeError: CompactArtifactWriteRequest.accepted_candidate must be CompactionCandidate`

这不是测试夹具问题，而是 production reactive accepted closeout 仍使用旧 artifact writer 的直接结果。

### Proactive subsequent run input failure 属于 Slice C/D

最近失败输出中的关键错误为：

- `ValueError: evidence_backed_fact_candidates is required`

该错误来自 compacted 后的后续 run input/projection 消费路径仍按旧 payload 字段读取。用户明确要求本轮不要切 memory durable/projection、不要切 RunInputBuilder、不要做旧库兼容读取、不要保留旧字段作为事件兼容入口。因此该测试若继续断言 subsequent run input 已能消费 vNext compacted event，应由 Slice C/D 或 test reslice 处理，而不是在 Slice B 生产代码中添加兼容字段。

## 为什么不能在当前 allowed list 内修复 reactive failures

remaining reactive failures 的必要修改点包括：

- `dayu/host/engine_ingest.py` 中 reactive accepted `CONTEXT_COMPACTED` event/artifact 写入；
- reactive accepted payload 参数从旧 compacted payload builder 参数切换到 vNext compacted payload builder 参数；
- reactive accepted artifact JSON/descriptor metadata 与 digest/ref 生成切换到 vNext candidate；
- reactive accepted type annotations 从 `CompactionCandidate` / `CompactQualityCheckResult` 切换到 `ConversationCompactOutputVNext` / `CompactQualityCheckResultVNext`。

这些修改都落在 `engine_ingest.py`。该文件不在 accepted Slice B allowed files 中；同时用户明确要求“不要修改 engine_ingest.py 或任何未在 Slice B allowed files 中列出的模块”。因此必须停止实现，写 blocker artifact。

## 未授权文件修改核对

截至本 artifact 写入前，未修改未授权文件。

当前已修改文件清单：

- `dayu/host/compact_payload.py`
- `dayu/host/compaction.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/llm_compaction.py`
- `tests/host/fake_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-cm-01-slice-b-implementation-codex.md`

## README 决策

未更新 README。原因是当前 Slice B 未通过完整测试与 pyright 收口，且存在 accepted plan allowed-files blocker；此时同步 README 会把未完成状态写入稳定文档，违反 README 只记录当前稳定接口/机制的职责。

## 建议

建议 controller 采取其一：

1. 回到 plan fix/reslice：把 reactive accepted closeout 明确拆到包含 `engine_ingest.py` 的 slice，并把 proactive subsequent RunInput/projection 消费保留到 Slice C/D。
2. 明确扩大 Slice B allowed files：至少加入 `dayu/host/engine_ingest.py`，允许把 reactive accepted compacted event/artifact closure 同步切到 vNext。

不建议在 `context_events.py` 或 `compact_payload.py` 保留旧字段兼容入口来绕过失败；这会违反本 work unit 对 vNext event closure 的目标，也会与用户明确的“不做旧库兼容读取/不保留旧字段作为事件兼容入口”冲突。

## Residual Risks

- 当前 workspace 中已有 Slice B allowed files 改动尚未完成最终全量验证。
- `test_dispatch_scheduler.py` 的 proactive subsequent run input 断言仍覆盖 Slice C/D 行为，需要 reslice 或调整测试边界。
- reactive accepted closeout 未切 vNext，直到 `engine_ingest.py` 被纳入允许范围前，相关测试不能完成。
- `compact_payload.py` 为避免未迁移 Slice D import 断裂，仍需在后续 Slice C/D 中统一清理旧读取 helper 的剩余导入关系。
