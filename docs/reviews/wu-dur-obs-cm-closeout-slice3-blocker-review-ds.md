# WU-DUR-P01 Slice 3 Blocker Review — AgentDS

## verdict

**blocker-accepted**

## evidence checked

| # | 声称 | 验证结果 | 直接证据 |
|---|---|---|---|
| 1 | `compaction_operation.py` 拥有 proposal loop 与 `attempt_number`，且不在 allowed files | **confirmed** | `run_compaction_operation()` L113-285：`attempt_number` 在 L139 初始化，L172 调用 `_compact_candidate()` 进入 compactor。`_compact_candidate()` L330-344 是 `compactor.compact(request, cancellation_token)` 的唯一调用方。 |
| 2 | `dispatch.py` 拥有 compact result EventLog 写入，且不在 allowed files | **confirmed** | `_execute_proactive_compaction()` L1150-1263：L1170 调 `run_compaction_operation()` 在事务外，L1182-1263 在新事务内写入 `CONTEXT_COMPACTED`（L1242）与 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`（L1206）。 |
| 3 | `llm_compaction.py` 无法自行产出 durable manifest | **confirmed** | `LLMContextCompactor.compact()` L197-235：接收 `CompactionRequest` + `CancellationToken`，返回 `ConversationCompactOutputVNext`。`_agent_request_vnext()` L313-353 构造 Engine request 时 `attempt_id=None`，`execution_id=None`，`run_id` 为 `context-compactor-vnext-*` 内部 id。compactor 无 durable transaction、payload store、artifact root 访问。 |
| 4 | `context_events.py` payload builder 当前不接受 proposal manifest ref | **confirmed** | `build_context_compacted_payload()` L249-304：参数列表中无 `accepted_proposal_manifest_ref`。`build_context_compaction_attempt_rejected_payload()` L514-579：有 `runner_attempt_summary_refs` 但数据源（`CompactionAttemptRejected`）在 `compaction_operation.py` 中，不在 allowed files。 |
| 5 | `compactor_input_projection` descriptor kind 在 schema.py 中不存在，且 schema.py 不在 allowed files | **confirmed** | `dayu/host/durable/schema.py` 全文 grep 0 matches。已有 `runner_call_input_manifest`（L225）和 `runner_call_input_manifest_schema_version`（L228），但无 `compactor_input_projection`。`design.md` L1449 明确要求此 descriptor kind。 |

## findings

### 1. blocker 真实且不可绕过

Slice 3 的生产级实现需要在 compactor proposal 调用前生成 durable manifest artifact，并在 accepted/rejected compact events 中引用。这要求一条完整的数据流：

```
llm_compaction.py  ──→  compaction_operation.py  ──→  dispatch.py
 (manifest 生产点)      (manifest 经 result types 传递)   (EventLog 写入)
```

三个节点分别在三个模块中，只有 `llm_compaction.py` 在 Slice 3 allowed files。数据必须流经全部三个节点才能成为 durable fact。具体来说：

- **manifest 生产点**必须知道 `attempt_number`、`compaction_operation_id`、实际 compactor 输入 messages、system/user template digest、compactor engine run id。这些信息在 `llm_compaction.py::compact()` 内部（rendered messages / run id）和 `compaction_operation.py` 循环中（attempt_number）分散持有。
- **manifest 传递**必须通过 `CompactionOperationResult`（L95-110）和 `CompactionAttemptRejected`（L73-91）两个 dataclass。它们定义在 `compaction_operation.py`，不在 allowed files。
- **manifest 消费**在 `dispatch.py`：`_append_compacted_event()` L1533-1629 调用 `build_context_compacted_payload()` 写入 `CONTEXT_COMPACTED`；`_append_compaction_attempt_rejected_event()` L1933-1980 写入 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`。两个写入点都不在 allowed files。

### 2. 被排除的替代路径

| 路径 | 为何不可行 | 违反的约束 |
|---|---|---|
| `llm_compaction.py` 原地写 durable manifest | 无 transaction runner、无 payload store、无 artifact root 访问 | 架构硬约束：durable write 必须通过 Host governance |
| 扩展 `ContextCompactor.compact()` 返回类型 | `ContextCompactor` 协议定义在 `compaction.py`，不在 allowed files | Slice 3 scope boundary |
| `dispatch.py` 自行重建 manifest | 缺少 compactor engine run id、实际 input messages digest、system/user template digest | 设计 contract：analyzer 不得 rerun material selection |
| global side channel / module-level dict | 非 durable、不可校验、非线程安全 | 编码硬约束：禁止胶水 seam；禁止 fake manifest |
| 用现有 descriptor kind（如 `runner_call_input_manifest`）替代 `compactor_input_projection` | 语义不同，`runner_call_input_manifest` 是 Host admitted/engine-continued runner call 的 manifest，compactor proposal 是 Host-owned internal call | 设计 contract：`design.md` L1449 要求独立 `compactor_input_projection` kind |

### 3. reslice 建议评审

blocker 建议的 reslice 需要增加的最小文件集：

| 文件 | 必要性 | 具体改动 |
|---|---|---|
| `dayu/host/compaction_operation.py` | **必须** | 在 `run_compaction_operation()` 中生成 proposal manifest ref；扩展 `CompactionOperationResult` / `CompactionAttemptRejected` 携带 manifest refs |
| `dayu/host/dispatch.py` | **必须** | `_execute_proactive_compaction()` 将 manifest refs 传入 `build_context_compacted_payload()` / `build_context_compaction_attempt_rejected_payload()` |
| `dayu/host/durable/schema.py` | **必须** | 新增 `compactor_input_projection` descriptor kind 常量 |
| `dayu/host/compaction.py` | **可能** | 如 `ContextCompactor` 协议需要返回 manifest 数据（extend return type 或 add method），则需要修改 |
| `dayu/host/context_events.py` | **已允许** | `build_context_compacted_payload()` 增加 `accepted_proposal_manifest_ref` 参数 |

该 reslice 覆盖了 manifest 生产、传递、持久化、消费的全链路，是 minimal viable expansion。不扩 `compaction_operation.py` 则数据无法从 compactor 传到 dispatch；不扩 `dispatch.py` 则 manifest ref 无法写入 EventLog；不扩 `schema.py` 则缺少 durable descriptor kind 真源。

**额外考虑**：`llm_compaction.py` 内部也需要改动以产出 manifest（需从 `_agent_request_vnext()` 中提取或暂存 compactor input / engine run id / system prompt digest / user template digest）。这一部分在 allowed files 内可完成，但数据要从 `llm_compaction.py` 传出到 `compaction_operation.py` 后才能真正 durable。当前 `compact()` 的返回值是 `ConversationCompactOutputVNext`，要么 return type 扩展（影响 `compaction.py`），要么 compactor 将 manifest metadata 暂存为实例属性，由 `compaction_operation.py` 在调用后读取。两种方式都需要 `compaction_operation.py` 配合。

### 4. 测试影响

扩张 allowed files 后，现有测试 `tests/host/test_compaction_operation.py`（已在 allowed files 列表）可复用以验证 manifest 数据流。`tests/host/test_llm_compaction.py`（已在 allowed files）可验证 manifest 生产的正确性。无新增测试文件需求。

## recommended next gate

1. **Accept blocker**。当前 allowed files 不足以完成 Slice 3 生产级实现。
2. **Expand allowed files** 至少包含 `compaction_operation.py`、`dispatch.py`、`durable/schema.py`，并评估是否需要 `compaction.py`（视 `ContextCompactor` 协议是否需要变更而定）。
3. **重新派发 Slice 3 implementation**，明确 manifest 数据的 interface contract：`CompactionOperationResult` 和 `CompactionAttemptRejected` 新增字段（如 `accepted_proposal_manifest_ref: str | None` 和 per-attempt `proposal_manifest_ref: str | None`），`build_context_compacted_payload()` 新增 `accepted_proposal_manifest_ref` 参数。
4. **无需重新 plan**：plan 附录已明确 `CompactorRunnerCallIdentity` shape、`compactor_input_projection` descriptor kind、data flow 和 invariant。current plan 仍然 valid，仅 allowed files 需要扩张。

## ready for controller adjudication

yes
