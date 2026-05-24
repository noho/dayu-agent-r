# PR 68 P12.6 Draft Review — Independent Deep Review

## Scope

- **Mode**: PR review
- **PR**: [#68](https://github.com/noho/dayu-agent-r/pull/68) — "P12.5 conversation memory evidence-backed facts"
- **Base/Head**: `main` ← `feat/phase-12-5-conversation-memory-optimize`
- **Author**: noho (Leo Liu)
- **Output file**: `docs/reviews/pr-68-p12-6-draft-review-ds-20260524.md`
- **Review date**: 2026-05-25 01:35 CST
- **Included scope**: Full PR diff (37,524 additions / 1,930 deletions across 225 files); emphasis on P12.6 conversation memory redesign, evidence-backed facts, compaction material/label, memory projection, LLM compaction, RunInput builder, dispatch lag repair, engine ingest, durable schema, config, tests
- **Excluded scope**: Review artifacts in `docs/reviews/` (prior aggregate reviews, slice reviews, plan reviews); `docs/host/conversation-memory-compact-io-first-principles-discussion.md` (design discussion, not implementation)
- **Parallel review coverage**:
  - Subagent 1 (DS): `memory.py`, `evidence.py`, `compaction_evidence.py`, `compact_material.py`, `compaction.py`, `compaction_operation.py`, `durable/memory.py`, `durable/schema.py` — covered
  - Subagent 2 (DS): `llm_compaction.py`, `context_governance.py`, `context_events.py`, `compact_artifact.py`, `compact_payload.py`, `context_policy.py` — covered
  - Subagent 3 (DS): `run_input.py`, `dispatch.py`, `engine_ingest.py`, `tool_runtime.py`, `payload_resolution.py`, `api.py`, `open_host.py` — covered
  - Subagent 4 (DS): Tests alignment and design doc coverage — covered
  - Main reviewer: `evidence.py`, `compaction_evidence.py`, `tool_runtime.py:3470-3585`, `memory.py:1190-1310`, `dispatch.py:2340-2530`, `llm_compaction.py:186-276`, `run_input.py:1910-2077`, `config_loader.py:1450-1500`, `durable/schema.py:784-808` — directly walked
  - Not covered: `engine/runners/openai/` (SSE parser, tool_call_aggregator changes — low-risk Engine-side fixes); `contracts/cancellation.py` (minor cleanup); `dayu/__init__.py` (export change); `tests/engine/` (Engine-specific tests)

## Validation Commands

```bash
# 测试运行
source .venv/bin/activate && python -m pytest \
  tests/host/test_memory_projection.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_compact_artifact_store.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_toolruntime_executor.py \
  tests/host/test_compact_material.py \
  tests/service/test_host_assembly.py \
  tests/runtime/test_config_loader.py \
  -x -q
# Result: 328 passed in 5.04s

# 类型检查
source .venv/bin/activate && python -m pyright dayu/host/ dayu/engine/ dayu/service/ dayu/config/ dayu/runtime/ dayu/contracts/ --outputjson
# Result: Errors: 0, Warnings: 0

# 空白检查
git diff --check
# Result: PASS (no whitespace errors)
```

## Findings

### F1 — 严重 — Memory Diagnostic Reason 与 SQLite Schema CHECK Constraint 不一致

- **入口/函数**: `project_conversation_memory_event()` → `_replace_snapshot_diagnostics()` → `_insert_memory_diagnostic()`
- **文件(行号)**: `dayu/host/durable/schema.py:789-799` vs `dayu/host/memory.py:215-216`
- **输入场景**: 任一 memory projection 事件触发 evidence-backed fact 被 supersede（去重键冲突）或 minimum preserve item 被 stable fact / episode summary 覆盖时
- **实际分支**: `memory.py:1628` 创建 `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_SUPERSEDED` 的 diagnostic；`memory.py:2568` 创建 `MemoryDiagnosticReason.MINIMUM_PRESERVE_ITEM_COVERED` 的 diagnostic。两者经 `_replace_snapshot_diagnostics()` → `_insert_memory_diagnostic()` 写入 `host_memory_diagnostics` 表
- **预期行为**: Durable write 成功，diagnostic 被持久化
- **实际行为**: SQLite CHECK constraint（`schema.py:789-799`）只允许 8 个 reason 值，不包含 `'evidence_backed_fact_superseded'` 和 `'minimum_preserve_item_covered'`。INSERT 被 SQLite 拒绝，整个 durable transaction 失败
- **直接证据**:
  - `schema.py:789-799` CHECK 列表: `'evidence_backed_fact_candidate_invalid'`, `'inline_delta_repair_included'`, `'snapshot_missing'`, `'snapshot_damaged'`, `'unsupported_event_type'`, `'snapshot_lag_over_threshold'`, `'budget_limit_reached'`, `'empty_event_log_snapshot'`（共 8 个）
  - `memory.py:215-216` 枚举新增: `EVIDENCE_BACKED_FACT_SUPERSEDED = "evidence_backed_fact_superseded"`, `MINIMUM_PRESERVE_ITEM_COVERED = "minimum_preserve_item_covered"`
  - `memory.py:1628` 使用 `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_SUPERSEDED`
  - `memory.py:2568` 使用 `MemoryDiagnosticReason.MINIMUM_PRESERVE_ITEM_COVERED`
- **影响**: 触发去重 supersede 或 preserve-cover 场景时，memory snapshot 持久化崩溃。该事务失败会级联导致 projection catch-up 中断，进而阻塞 dispatch scheduler 对后续 Run 的 memory 渲染
- **建议改法和验证点**: 在 `schema.py:789-799` CHECK 约束中追加 `'evidence_backed_fact_superseded'` 和 `'minimum_preserve_item_covered'`；运行 `test_memory_projection.py` 中涉及 fact merge / preserve cover 的测试确认不再触发 durable error；新增测试直接验证这两个 reason 的 diagnostic 可成功写入
- **修复风险（低）**: 纯 schema 扩展，向下兼容
- **严重程度（严重）**: 运行时 durability 崩溃

### F2 — 中 — Evidence Trace 在 Compact Material Pack 二次构建路径中丢失 source_locator_refs 和 artifact_refs

- **入口/函数**: `build_compact_material_pack()` → `_provenance_from_evidence_blocks()`
- **文件(行号)**: `dayu/host/compact_material.py:125`（`RunInputMaterialBlock` 定义），`compact_material.py:1630-1631`
- **输入场景**: 从 `RunInputMaterialBlock` selected segments 构建 compact material pack（即二次/后续 compact 场景），且原始 evidence material 携带 `source_locator_refs` 或 `artifact_refs`
- **实际分支**: `_provenance_from_evidence_blocks()` 使用 `RunInputMaterialBlock` 作为 source。`RunInputMaterialBlock` 数据类（line 125）没有 `source_locator_refs` 和 `artifact_refs` 字段。函数在 line 1630-1631 硬编码 `artifact_refs=()` 和 `source_locator_refs=()`
- **预期行为**: Provenance entry 保留原始 evidence 的 locator refs（如文档页码、chunk id）和 artifact refs，确保可追溯
- **实际行为**: `PromptLocalProvenanceEntry` 的 `source_locator_refs` 和 `artifact_refs` 被设为空 tuple，证据溯源链中断
- **直接证据**:
  - `compact_material.py:345-346`: `InitialEvidenceMaterial` 有 `artifact_refs` 和 `source_locator_refs` 字段
  - `compact_material.py:1018-1019`: `build_initial_material_pack()` 正确传递这两个字段
  - `compact_material.py:125`: `RunInputMaterialBlock` 缺失这两个字段
  - `compact_material.py:1630-1631`: `_provenance_from_evidence_blocks()` 硬编码为空
- **影响**: 二次 compact 场景下，证据无法追溯到原始 locator（如财报页码、chunk id），违反 design.md "durable provenance" 要求
- **建议改法和验证点**: 在 `RunInputMaterialBlock` 中增加 `source_locator_refs` 和 `artifact_refs` 字段；在 `_run_input_material_block_from_initial()` 中传递；在 `_provenance_from_evidence_blocks()` 中从 `selected_blocks` 读取而非硬编码空值；新增测试验证二次 compact 后 provenance entry 保留 locator refs
- **修复风险（低）**: 数据类字段扩展，需同步更新所有 `RunInputMaterialBlock` 构造点
- **严重程度（中）**: 证据溯源能力降级

### F3 — 中 — Memory Stable Block 预算分配导致 evidence_backed_facts 被静默丢弃

- **入口/函数**: `_bounded_stable_memory_messages()`
- **文件(行号)**: `dayu/host/run_input.py:1904-1974`
- **输入场景**: Stable layer 预算紧张，`stable:subjects`（已确认主体列表）的 token 消耗接近 `stable_layer_size_units` 上限
- **实际分支**: `_memory_stable_blocks()` 排序为 goals → subjects → evidence_backed_facts → questions_assumptions。`_bounded_stable_memory_messages()` 按此顺序逐个填充预算。当 `stable:subjects` 包含大量已确认主体 opaque refs 时，其 message 消耗大部分预算，后续 `stable:evidence_backed_facts` 被 `budget_used + block_units <= policy.stable_layer_size_units` 拒绝（line 1959），产生 diagnostic "stable memory block skipped by stable layer budget"
- **预期行为**: Evidence-backed facts 是前序轮次已接受工具结果的提炼，对当前 Run 的事实推理至关重要，应享有最小保留保护
- **实际行为**: Evidence-backed facts 完全被丢弃，仅记录 diagnostic，LLM 上下文中失去所有 evidence-backed 事实上下文
- **直接证据**: `run_input.py:1959` 条件 `budget_used + block_units <= policy.stable_layer_size_units`，block 按固定顺序遍历，无最小保留策略
- **影响**: 预算压力下 LLM 失去前序轮次已接受工具证据的事实基础，可能导致幻觉回答
- **建议改法和验证点**: 在 `_bounded_stable_memory_messages()` 中加入 `evidence_backed_facts` block 的最小保留条数（至少 1 条）保护；或调整 block 优先级使 evidence-backed facts 优先于 subjects；新增测试验证预算压力下 evidence facts 不会被完全丢弃
- **修复风险（中）**: 策略调整涉及行为变更，需充分测试不同预算压力下的行为
- **严重程度（中）**: 上下文完整性退化

### F4 — 中 — Dispatch 滞后修复失败后 dispatch record 永久挂起

- **入口/函数**: `HostDispatchScheduler._start_worker()`
- **文件(行号)**: `dayu/host/dispatch.py:2241-2256`
- **输入场景**: `_catch_up_memory_projection_before_worker()` 和 `_build_run_input_with_lag_repair()` 均无法消除 `SNAPSHOT_LAG_OVER_THRESHOLD`（catch-up 有 failures，rebuild 后仍超过阈值）
- **实际分支**: `MemoryProjectionRepairRequired` 在 `_start_worker()` 被 catch（line 2241），当 `reason is SNAPSHOT_LAG_OVER_THRESHOLD` 时执行 `return "skipped"`（line 2256）。此时 `dispatch_record` 已被 `_mark_dispatching_after_recheck()` 更新为 `DISPATCHING`，Run 状态为 `RUNNING`，Attempt 状态为 `STARTING`
- **预期行为**: 超阈值时应做 terminal closeout（将 Run 标记为 FAILED），或回退 dispatch_record 状态，或安排自动重试
- **实际行为**: dispatch_record 保持 `DISPATCHING`，Run 保持 `RUNNING`，没有状态回滚或自动重试机制。仅靠外部 queue promotion wakeup 才有机会恢复，可能永久挂起
- **直接证据**: `dispatch.py:2105` `_mark_dispatching_after_recheck()` 先更新状态为 DISPATCHING；`dispatch.py:2241-2256` skip 时不回退；无超时终止逻辑
- **影响**: Run 永久阻塞，占用 Session active slot，需要 Host 重启或手动干预才能恢复
- **建议改法和验证点**: 在 skip 前执行 `_safe_closeout_worker_startup_timeout()` 做 terminal closeout；或实现 dispatch record 超时自终止；新增测试验证 lag repair 最终失败后 Run 被正确关闭
- **修复风险（中）**: 涉及状态机变更
- **严重程度（中）**: 资源泄漏和 Run 阻塞

### F5 — 中 — ToolRuntime Accept Barrier 未校验 payload_ref 存储完整性

- **入口/函数**: `_invalid_accept_context_reason()` → `DefaultHostToolFactAcceptPort.accept_tool_fact()`
- **文件(行号)**: `dayu/host/tool_runtime.py:3294-3328`；`dayu/host/payload_resolution.py:90-92`
- **输入场景**: 上游传入格式合法（ref 非空、digest 格式正确）但指向的 payload descriptor 已在 SQLite payloads 表中丢失
- **实际分支**: `HostPayloadRef.__post_init__` 仅校验 ref 非空和 digest 格式，不检查 durable store 存在性。Accept barrier 通过后写入 `TOOL_RESULT_ACCEPTED` event。后续 memory projection / compaction evidence 读取时，`event_payload_object_for_result_ref()` → `sqlite_payload_object()` → `read_payload_descriptor()` 返回 `None`，抛出 `HostDurableError`
- **预期行为**: Accept barrier 应尽早发现 payload 不可用，避免写入一个后续消费必失败的 event
- **实际行为**: 错误延迟到消费阶段，距 accept barrier 的时间/逻辑距离长，难以归因
- **直接证据**: `payload_resolution.py:90-92` `if descriptor is None: raise HostDurableError(...)`；`tool_runtime.py:3294-3328` 无 payload descriptor existence check
- **影响**: 延迟错误，问题定位困难；已写入的 TOOL_RESULT_ACCEPTED event 成为"坏引用"
- **建议改法和验证点**: 在 accept barrier 中增加 `tool_runtime.py` 对 `candidate.payload_ref` 指向 payload descriptor 的存在性校验；或至少记录 diagnostic 标记为 at-risk
- **修复风险（低）**: 增加一次 durable read
- **严重程度（中）**: 错误延迟发现

### F6 — 中 — LLM Compaction 超时与 CancellationToken 未协调

- **入口/函数**: `LLMContextCompactor.compact()` → `_run_agent_request()`
- **文件(行号)**: `dayu/host/llm_compaction.py:265-276`
- **输入场景**: `asyncio.wait_for` 超时触发，底层 `run_agent_and_wait` 仍在运行
- **实际分支**: `asyncio.wait_for` 超时抛出 `asyncio.TimeoutError`。`request` 内部的 `cancellation_token` 未被 signal。`TimeoutError` 不在 `LLMContextCompactor.compact()` 中被 catch，直接传播给调用方 `run_compaction_operation()`
- **预期行为**: 超时时 signal cancellation_token，让 Engine runner 有机会做清理后返回 cancelled outcome
- **实际行为**: `TimeoutError` 原始透传，engine runner task 被 asyncio cancel（非 token signal），`CancellationToken` 的状态与实际情况不一致
- **直接证据**: `llm_compaction.py:276` `asyncio.wait_for(run_agent_and_wait(request), timeout_seconds=timeout_seconds)` — token 未被 signal
- **影响**: 上层调用者若只 catch `LLMCompactionProposalError`，会漏接 `TimeoutError`；Engine runner 清理路径不完整
- **建议改法和验证点**: 在 `asyncio.wait_for` 超时捕获后 signal `cancellation_token`；或使用 `asyncio.wait_for` 的 cancel 语义并确保 Engine 正确处理 `CancelledError`
- **修复风险（低）**: 增加超时捕获和 token signal
- **严重程度（中）**: 取消信号协调缺失

### F7 — 低 — Compact Material Pack 中 Evidence Provenance 的 source_locator_refs 丢失

- **入口/函数**: `_provenance_from_evidence_blocks()`
- **文件(行号)**: `dayu/host/compact_material.py:1630-1631`
- **输入场景**: 同 F2
- **实际分支**: 同 F2
- **预期行为**: 同 F2
- **实际行为**: 同 F2
- **直接证据**: 同 F2
- **影响**: 同 F2，但影响范围较小（仅 evidence provenance entry 的 locator 元数据，不涉及 claim text 本身的溯源）
- **建议改法和验证点**: 同 F2
- **修复风险（低）**: 同 F2
- **严重程度（低）**: 与 F2 为同一代码路径的不同侧面，已在 F2 覆盖

### F8 — 低 — `_candidate_from_final_answer` 异常 catch 过于宽泛

- **入口/函数**: `_candidate_from_final_answer()`
- **文件(行号)**: `dayu/host/llm_compaction.py:435-438`
- **输入场景**: 内部数据结构（如 `request`）因代码 bug 抛出 `KeyError`、`TypeError` 或 `ValueError`
- **实际分支**: try/except 将三类异常一律诊断为 "proposal schema invalid"，抛出 `LLMCompactionProposalError`
- **预期行为**: proposal 解析失败与内部数据异常应有不同错误信号，以便区分 LLM 输出质量问题与代码缺陷
- **实际行为**: 内部 bug 被误归因于 LLM 输出格式问题
- **直接证据**: `llm_compaction.py:435` `except (KeyError, TypeError, ValueError)`
- **影响**: 可观测性下降，增加调试难度
- **建议改法和验证点**: 将 proposal 解析逻辑与数据访问逻辑分层，内层只 catch 真正的 JSON 解析/校验异常；或在 catch 块中区分数据内部异常和 proposal 格式异常
- **修复风险（低）**: 重构异常处理
- **严重程度（低）**: 仅影响调试体验

## Open Questions

1. **Subagent memory/evidence 指出 `memory.py` 模块文档声明为"层中立"但直接依赖 `compaction.py` 的具体类型**（`EvidenceBackedFactKind`、`MinimumPreserveReason`）：这些类型是否应下沉到公共契约（如 `dayu/contracts/`）？若 compaction 的 fact kind 语义确实属于 memory projection 的稳定边界，当前耦合可能合理但仍值得审视。**暂不构成 finding**，但需 controller 确认。

2. **`context_governance.py` 中 proactive/reactive 编排状态机是否完整？** subagent 2 指出 `context_policy.py` 定义了触发枚举，`context_events.py` 校验 REACTIVE 的必填字段，但 proactive compaction 的编排、次数限制、失败后 fallback 等逻辑分布在 `context_governance.py`、`dispatch.py`、`engine_ingest.py` 三个文件中，审查时发现所有关键路径都存在，但跨文件状态转换的完整性需要 controller 复核。**暂不构成 finding**。

3. **`_run_agent_request` 超时值来自 `runner_spec.default_timeout_seconds`**：compactor runner spec 的默认超时是否与 `agent_policy.tool_execution_timeout_seconds`（compactor scene 中配置）一致？场景配置的 `tool_execution_timeout_seconds` 是 per-tool-call 超时，而 `_run_agent_request` 的超时是整个 compactor run 的总超时。两者的关系需要确认。

## Residual Risk

| Risk | Owner | Notes |
|------|-------|-------|
| `stable:subjects` block 无 token 上限保护 | Host implementation | 已确认主体列表可无限膨胀，吃掉 stable layer 预算。需后续 phase 为 `confirmed_subjects` 增加数量或 token 上限 |
| Large-session memory projection rebuild 性能 | Host implementation | 大量 EventLog 事件时 rebuild 成本可能很高，当前 batch_size 机制缓解但未彻底解决 |
| In-flight compaction LLM 取消依赖 timeout + stale output checks | Host implementation | PR 已从 `_NeverCancelledToken` 迁移到真实 token 传播，但取消后 Engine runner 的清理路径依赖 asyncio task cancellation 和 Engine 内部处理，Host 侧缺乏显式的 post-cancel cleanup |
| `result_preview` 移除后的 LLM 证据抽取质量 | Host implementation | 已改为 raw evidence content 直传，需要后续在真实多轮场景中验证 LLM 抽取质量 |
| 测试缺口：bounded evidence-backed fact selection in RunInput builder 路径 | Host implementation | Subagent 4 识别但当前无 breaking behavior 证据 |
| 测试缺口：rejected tool facts 被排除在 memory projection 外 | Host implementation | Subagent 4 识别，当前测试通过 memory projection layer 不处理 TOOL_RESULT_ACCEPTED 事件来间接保证 |
| 测试缺口：source_refs / locator_refs 非空路径 | Host implementation | 所有测试中均为空 tuple，非空值路径未被测试覆盖 |

## Verdict

**PASS_WITH_FINDINGS**

**阻断项**: F1（严重 — schema CHECK constraint 与 enum 不一致）必须修复后才能 draft-PR-pass。

**建议修复项**: F2-F6（中 — 证据溯源丢失、stable block 预算分配、dispatch 挂起、accept barrier 校验缺失、超时/取消协调）应在 P12.6 内或下一个 phase 修复。

**非阻断**: F7-F8（低 — 可后续 polish）。

无架构分层违规、无跨层反向 import、无 Engine 泄漏到 Host contract、无 Fins 层泄漏。测试通过 328 例，pyright 零错误零警告。设计文档对齐良好。`max_verified_facts` → `max_evidence_backed_facts` 重命名全量清理且 config loader 的 `_require_exact_fields` 对旧 key fail-closed。CancellationToken 已从 `_NeverCancelledToken` 替身为真实 token 传播。Evidence envelope 的创建、序列化、反序列化路径完整且校验严格。
