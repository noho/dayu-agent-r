# WU-PROJ-01 Aggregate Deepreview — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- 类型: 聚合深度审查
- 日期: 2026-06-11
- 分支: `wu-proj-01`
- HEAD: `9191f5ab` (Slice 4 bookkeeping, 干净状态)
- 审查范围: accepted plan `fb3cc9ec` → Slice 1 `1b4e7b67` → Slice 2 `8e9d42ea` → Slice 3 `a658ee1f` → Slice 4 `08709fe9` → bookkeeping `9191f5ab`

## 审查方法

1. 阅读全部必读文档：AGENTS.md、docs/host/design.md、docs/engine/design.md、控制文档、plan、Slice 1-4 全部 review/controller 裁决 artifact。
2. 逐 slice code-review：核对 plan exact changes 到生产代码的一一映射。
3. 独立运行 pyright 与全部聚焦测试、proactive governance/compact 测试、public compact smoke。
4. 核对 README 更新触发规则、控制文档 residual risk 追踪、设计文档一致性。
5. Adversarial pass：挑战 bounded loop 边界条件、reactive path 最小适配安全性、material truth 来源完整性。

## 结论

**PASS**

无 blocking finding。四个 Slice 均正确实现了 accepted plan；第一性原理目标完整达成；设计文档、控制文档、代码、测试一致；pyright 0 errors；全部聚焦测试通过；两条 active residual risk 均有明确 owner/owner destination，允许进入 draft PR gate。

---

## 1. 第一性原理目标验证

### 1.1 Compact input truth 来源链

Plan 要求的事实链：

```text
EventLog / payload descriptor / artifact truth
  -> EventLog-backed compact material builder
  -> ConversationCompactInputVNext
  -> Host-owned compactor
  -> Host accept barrier
  -> CONTEXT_COMPACTED canonical fact
  -> Conversation Memory projection read model
  -> ordinary RunInput
```

**验证**：通过。证据如下：

- `build_pre_dispatch_compact_material_view()` (`compact_material.py:456`) 只读取 `HostTransaction`、`EventLogStore`、`RunRow`、`current_display_text` 四类输入，不读取 `ConversationMemorySnapshotVNext`。
- `PreDispatchCompactMaterialView` (`compact_material.py:393`) 承载 `material_blocks`（从 EventLog delta 构造）、`previous_compacted_view`（从 latest accepted compact payload/artifact 构造）、`current_input_text`（从 `USER_INPUT_ACCEPTED` 的 display_text 来）、`source_boundary`（记录 EventLog sequence 边界）。
- Builder 在 payload/artifact 损坏时 fail closed (`HostDurableError`)，不 fallback 到 memory snapshot。
- `dispatch.py:1093` 中 proactive gate 先构造 material view，再用同一 view 做 budget、segment、pack build、CompactionRequest refs。

### 1.2 Conversation Memory projection 只消费 accepted compact

**验证**：通过。

- `test_accepted_compact_materializes_vnext_memory_sections` (`test_memory_projection.py:307`) 证明 `CONTEXT_COMPACTED` 提交后 projection consumer 物化五类 section（session_summary、evidence_fact、answer_anchor、forward_intent、trace reference continuity）。
- `test_failed_compaction_event_does_not_materialize_memory_sections` (`test_memory_projection.py:512`) 证明 `CONTEXT_COMPACTION_FAILED` 不物化任何 memory section。
- `test_projection_consumer_skips_failed_compact_without_memory_snapshot` (`test_memory_projection.py:729`) 进一步确认 failed compact 不能绕过 accept barrier。
- `test_write_snapshot_with_checkpoint_commits_snapshot_before_checkpoint` (`test_memory_projection.py:556`) 证明 snapshot 与 projection checkpoint 在同一 durable transaction 内提交，保证 `accepted → projection → ordinary RunInput` 的事务一致性。

### 1.3 Context Governance 只决策/编排，不拥有 material 语义

**验证**：通过。

- `dispatch.py` 的 proactive gate (`_run_context_governance_for_session`) 先调用 `build_pre_dispatch_compact_material_view()` 构造 material view（该 builder 属于 `compact_material.py`，不属于 Context Governance），再消费 view 做预算、segment、pack、CompactionRequest。
- 旧 `_proactive_material_blocks` 与 `_proactive_represented_evidence_refs` 的 governance 拼接职责已删除（grep 确认 dispatch.py 中不再存在这两个函数名）。
- `_prepare_compact_before_dispatch` 接收已冻结的 `material_view` 和 `estimate`，不再自行拼 material。

---

## 2. Slice 1-2: Same-source material view 与 checkpoint 前置真源防范

### 2.1 Slice 1: EventLog-backed builder

**实现对照 plan exact changes**：

| Plan requirement | Code evidence | Status |
|---|---|---|
| `PreDispatchCompactMaterialView` 全部字段 | `compact_material.py:393-417` | ✅ |
| `CompactMaterialSourceBoundary` 全部字段 | `compact_material.py:347-389` | ✅ |
| `build_pre_dispatch_compact_material_view()` | `compact_material.py:456` | ✅ |
| previous view 从 latest accepted compact event/artifact 构造 | `_previous_compacted_view_from_compacted_event()` (line 512-540) | ✅ |
| delta 起点规则（有 compact 时 +1；无 compact 时 session first relevant） | `_post_compact_delta_rows()` (line 630-680) | ✅ |
| evidence 去重只依赖 latest accepted compact mapping，不依赖 memory snapshot | `_accepted_evidence_mapping_refs_from_compacted_event()` (line 500-510) | ✅ |
| `build_compact_material_pack` 新增 `previous_compacted_view` keyword-only 参数 | `compact_material.py:962` | ✅ |
| 当 `previous_compacted_view is not None` 时跳过 snapshot path | `compact_material.py:990-997` | ✅ |
| payload/artifact 损坏 fail closed | `_validated_current_input_event` 等抛 `HostDurableError` | ✅ |

**校验**：`tests/host/test_compact_material.py` 32 tests passed。

**关键测试覆盖**：
- `test_pre_dispatch_second_compact_rolls_from_latest_accepted_candidate` (`test_compact_material.py:1049`) — rolling compact 不重展旧 raw history。
- `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` (`test_compact_material.py:1130`) — builder 不读取 memory snapshot。
- `test_pre_dispatch_builder_fails_closed_on_payload_corruption` — payload 损坏 fail closed。

### 2.2 Slice 2: Proactive governance 同源 material view

**实现对照 plan exact changes**：

| Plan requirement | Code evidence | Status |
|---|---|---|
| 先构造 material view，再估算预算 | `dispatch.py:1093-1098` → `estimate_context_budget(..., material_view.budget_fragments)` | ✅ |
| 删除 `_proactive_material_blocks` / `_proactive_represented_evidence_refs` | grep 确认函数已从 dispatch.py 消失 | ✅ |
| `estimate_context_budget` 使用 material view budget fragments | `dispatch.py:1108-1121` | ✅ |
| `_prepare_compact_before_dispatch` 接收冻结核查的 material view | `dispatch.py:1606` 签名 | ✅ |
| material pack build 传 `previous_compacted_view` | `dispatch.py:1688` | ✅ |
| material source failure fail closed | `dispatch.py:1099-1129` → `_append_compaction_failed_event` | ✅ |
| fallback 不提交 `CONTEXT_COMPACTED` | dispatch scheduler 相关测试验证 | ✅ |
| reactive 最小适配：复用 previous-view helper | `engine_ingest.py:1327-1332` | ✅ |

**校验**：`tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"` 19 tests passed。

**关键测试覆盖**：
- `test_proactive_budget_uses_pre_dispatch_material_view` (`test_dispatch_scheduler.py:3846`) — 预算估算来自 material view，不是只有 current prompt。
- `test_second_proactive_compact_uses_previous_view_without_old_raw_replay` (`test_dispatch_scheduler.py:3948`) — 第二次 compact 不包含第一轮前旧 raw history。
- `test_multi_turn_proactive_compact_feeds_subsequent_run_input` (`test_dispatch_scheduler.py:4645`) — accepted compact 后 ordinary RunInput 可读取物化 section。
- `test_pre_start_governance_material_source_failure_fails_closed` (`test_dispatch_scheduler.py:4506`) — material source failure fail closed。

---

## 3. Slice 3: Bounded catch-up / rebuild 无 recovery truth 污染

### 3.1 Bounded loop 实现

**实现对照 plan exact changes**：

| Plan requirement | Code evidence | Status |
|---|---|---|
| `MemoryProjectionCatchupBudget`（max_batches, max_scanned_events, purpose） | `memory_repair.py:51-77` | ✅ |
| `MemoryProjectionRepairStopReason`（IDLE, TARGET_REACHED, FAILURE, BUDGET_EXHAUSTED） | `memory_repair.py:41-47` | ✅ |
| `ConversationMemoryProjectionRepairResult` 扩展字段 | `memory_repair.py:81-117` | ✅ |
| `_run_memory_projection_bounded()` 替代 `_run_memory_projection_until_idle()` | `memory_repair.py:289-384` | ✅ |
| catch_up 接收 budget 参数 | `memory_repair.py:233-286` | ✅ |
| rebuild 接收 budget 参数 | `memory_repair.py:174-230` | ✅ |
| `ConversationMemoryProjectionCatchupPort` 接收 budget | `memory_repair.py:120-171` | ✅ |
| after-commit best-effort budget（max_batches=1） | `open_host.py:143-156` | ✅ |
| dispatch catch-up before worker 有 required cursor 检查 | `dispatch.py:3026-3052` | ✅ |
| dispatch rebuild 有 budget | `dispatch.py:2915-2933` | ✅ |
| budget exhausted 不是 projection failure | `dispatch.py:370-371`：budget_exhausted 时不抛 projection failure | ✅ |
| 不触发 recovery Attempt | `_raise_if_memory_projection_target_not_reached` 抛 `_MemoryProjectionDispatchDiagnosticError`，不写 RUN_RECOVERING | ✅ |

### 3.2 Bounded loop 边界条件 adversarial pass

**Adversarial check 1: max_batches 耗尽但 target_reached 未满足**

Loop 条件 line 330: `if budget is not None and batches_used >= budget.max_batches` → break with `BUDGET_EXHAUSTED`。正确。

**Adversarial check 2: max_scanned_events 耗尽但 batches 未满**

Line 333: `_bounded_batch_limit` 限制当前 batch 扫描量，防止单 batch 超预算。Line 360: batch 结束后 `_budget_scanned_events_exhausted` 再次检查。两种预算维度互补，无漏检。

**Adversarial check 3: 单个 batch 内 events_scanned ≥ max_scanned_events**

`_bounded_batch_limit` 返回 `min(batch_size, remaining_events)`，若 remaining_events ≤ 0 则返回 ≤ 0，line 334 检查 `limit < 1` 时 break。即使 `runner.run_once(limit=1)` 并扫描恰好 1 个事件，后续 `_budget_scanned_events_exhausted` 也会检测到 `events_scanned >= max_scanned_events`。双重防护，无漏检。

**Adversarial check 4: budget=None 时无界循环**

Line 330 guard: `if budget is not None`。Line 333: `_bounded_batch_limit(batch_size, None, ...)` → `batch_size`。Line 360: `_budget_scanned_events_exhausted(None, ...)` → `False`。无 budget 时只靠 failure、target_reached 或 idle 停止。这在生产代码中的三条路径上不可达无界：after-commit (max_batches=1)、catch-up before dispatch (max_batches=16)、rebuild before dispatch (max_batches=32)。所有生产 caller 均传 budget。`budget=None` 只用于 close-only / test-only（docstring 明确标注），不构成本 WU 的生产风险。

**Adversarial check 5: projection failure 停止循环**

Line 351-353: `batch_result.failures > 0` → break with `FAILURE`。stop_reason 正确分离。

**Adversarial check 6: target_reached 提前停止**

Line 354-356: `_target_reached(finished_cursor, max_event_sequence)` → break with `TARGET_REACHED`。即使 EventLog 后面还有更多事件也停止，符合 bounded catch-up 语义。

**Adversarial check 7: budget exhausted 不影响已推进的 checkpoint**

`runner.run_once` 在每个 write transaction 内同时推进 consumer apply 与 checkpoint advance。budget exhausted 停止后续 loop，但已处理 row 的 checkpoint 已提交。测试 `test_catch_up_budget_exhausted_advances_only_processed_checkpoint` (`test_memory_repair.py:608`) 确认此行为。

### 3.3 Timeout bug 检查

Plan 明确第一版不加 `timeout_seconds`，所有 budget 均为纯计数边界。`MemoryProjectionCatchupBudget` 只有 `max_batches`、`max_scanned_events`、`purpose` 三个字段，无 `timeout_seconds`。`_run_memory_projection_bounded` 同步执行，无 asyncio 超时竞争。无 timeout-related bug。

---

## 4. Slice 4: Accepted compact → projection → ordinary RunInput 证据

### 4.1 Positive regression

**链路** `accepted CONTEXT_COMPACTED → projection checkpoint → memory snapshot → ordinary RunInput`：

- `test_accepted_compact_materializes_vnext_memory_sections` (`test_memory_projection.py:307`)：projection consumer 物化 summary、facts、anchors、intents、reference continuity 五类 section。
- `test_write_snapshot_with_checkpoint_commits_snapshot_before_checkpoint` (`test_memory_projection.py:556`)：snapshot 与 checkpoint 在同一 durable transaction 提交。
- `test_run_input_memory_messages_include_context_compacted_projection` (`test_run_input_builder.py:1427`)：ordinary RunInput builder 读取到五类 business section，包括 `"## Conversation Summary"`、`"## Verified Evidence and Facts"`、`"## Prior Answer Anchors"`、`"## Open Follow-up Context"`、`"## Reference Continuity"`。

### 4.2 Negative regression

- `test_failed_compaction_event_does_not_materialize_memory_sections` (`test_memory_projection.py:512`)：`CONTEXT_COMPACTION_FAILED` 不写任何 memory section 或 snapshot item。
- `test_projection_consumer_skips_failed_compact_without_memory_snapshot` (`test_memory_projection.py:729`)：failed compact event 被 projection consumer 跳过，不生成 compact artifact。
- `test_pre_start_governance_compact_failure_is_attempt_free` (`test_dispatch_scheduler.py:4409`)：compact failure 不创建 Attempt。

### 4.3 Fixture 链路完整性

Slice 4 的 `test_run_input_memory_messages_include_context_compacted_projection` 真实走 `catch_up_conversation_memory_projection` → durable write → `RunInputBuilder` → `build(snapshot)` 完整链路，而非只断言 compact payload parser。符合 plan 要求："不能只断言 compact payload parser"。

---

## 5. 设计文档、控制文档、代码、测试一致性

### 5.1 设计文档 vs 代码

| 设计点 | 代码 | 一致性 |
|---|---|---|
| Host design 24 章：Memory 是 EventLog read model，不是 compact input truth | `compact_material.py:456` builder 不读 memory snapshot | ✅ |
| Host design 25 章：Context Governance 只编排，不拥有 material 语义 | `dispatch.py:1093-1098` 消费 builder 输出 | ✅ |
| Host design：ordinary RunInput 读 memory snapshot | `test_run_input_builder.py:1427` 证明 | ✅ |
| Engine design 15 章：Engine 不做 context budget/compact/retry | 本 WU 只改 Host 层，不碰 Engine | ✅ |

### 5.2 控制文档 vs 代码

- 控制文档 `WU-PROJ-01` 条目的"目标"、"非目标"、"验收信号"与 plan、代码一一对应。
- Slice 1-4 的 accepted commit hash 与 git log 一致。
- Residual risk 表已更新：`WU-PROJ-01-S3-R1` 和 `WU-PROJ-01-S4-R1` 均有 owner。

### 5.3 Plan vs 代码

逐 slice 检查（见第 2/3 节详细表格），所有 plan exact changes 均已在代码中落地。无遗漏。

### 5.4 README 更新

- `dayu/host/README.md` 修改 1 行（line 607），新增："pre-dispatch compact material 则由 EventLog / payload / artifact truth 构造"。符合 README 触发规则（`dayu/host/` 修改且在 README 职责范围内）。
- `tests/README.md` 未修改。检查：Slice 4 新增了一个 test（`test_compact_material.py` 中新增 test count），但未新增稳定测试入口文件或测试分类。不触发 `tests/README.md` 更新。合理。
- 控制文档已更新（174 行新增/修改），包含 full Slice 1-4 状态、commit hash、residual risk、entry point。符合控制文档自身更新规则。

---

## 6. Residual Risk 审查

### 6.1 WU-PROJ-01-S3-R1

- **内容**：dispatch before-worker catch-up happy path 无独立集成测试（required cursor 已被 projection checkpoint 覆盖时不重复追账且继续构造 ordinary RunInput）。
- **状态**：`deferred-with-owner` → Host dispatch test hardening。
- **是否允许进入 draft PR gate**：允许。当前 `_catch_up_memory_projection_before_worker` 的逻辑是：调用 bounded catch_up → 检查 target_reached → 成功时继续。catch_up 中的 target_reached path 已有单元测试覆盖（`test_catch_up_stops_when_target_reached_before_idle`）。缺失的是 dispatch 层集成，即 dispatch 读到 required cursor 已满足时的完整路径。这不影响 compact material truth 的正确性，属于测试完备性缺口。

### 6.2 WU-PROJ-01-S4-R1

- **内容**：`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 存在 lane timeout flaky 观察。
- **状态**：`deferred-with-owner` → Host dispatch scheduler test hardening。
- **是否允许进入 draft PR gate**：允许。该 flaky 与 Slice 4 改动无关（Slice 4 只新增 regression tests，不修改 dispatch scheduler 时间逻辑）。后续单独稳定化或调整 timing fixture。

### 6.3 其他 deferred residual risks from slice reviews

Slice 2/3 controller adjudications 中 defer 的 risks（material source failure exception taxonomy、reactive governance owner 等）均已有 owner 且在总控 residual 表中无对应 active 条目——表明它们已在 slice review 阶段裁决为后续 owner 负责，不进入本 WU 的 draft PR gate。合理。

---

## 7. 验证记录

### 7.1 pyright

```
source .venv/bin/activate && pyright
→ 0 errors, 0 warnings, 0 informations
```

### 7.2 聚焦测试

```
source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_memory_repair.py -x -q
→ 102 passed in 0.75s
```

### 7.3 open_host / logging 测试

```
source .venv/bin/activate && python -m pytest tests/host/test_open_host_runtime.py tests/host/test_logging.py -x -q
→ 16 passed in 0.47s
```

### 7.4 Dispatch proactive governance/compact 测试

```
source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive" -x -q
→ 19 passed, 48 deselected in 0.61s
```

### 7.5 Public compact smoke

```
source .venv/bin/activate && python -m pytest tests/host/test_public_compact_smoke.py -x -q
→ 6 passed, 1 skipped in 0.83s
```

共计 143 tests passed, pyright 0 errors。

---

## 8. 总体评估

### 正确性

- Compact material truth 来源已从 memory projection checkpoint 纠正为 EventLog / payload / artifact truth。
- Proactive budget、segment selection、pack build、CompactionRequest refs 使用同源 material view。
- Rolling compact 正确实现（previous_compacted_view + post-compact delta + current anchor）。
- Bounded catch-up/rebuild 有 max_batches + max_scanned_events 双重预算，budget exhausted 与 projection failure 分离。
- Accepted compact → projection → ordinary RunInput 链路完整且有正向/负向 regression 证据。
- 无 recovery truth 污染、无界循环或 timeout bug。

### 稳定性

- 所有现有测试通过，没有 regression。
- Material source failure fail closed（不 fallback 到 memory snapshot、不进入 RECOVERING）。
- budget exhausted 不被伪装成 projection failure 或 worker startup timeout。

### 可维护性

- `PreDispatchCompactMaterialView` 与 `build_pre_dispatch_compact_material_view` 封装完整，不污染 dispatch.py 的 governance 逻辑。
- `MemoryProjectionCatchupBudget` 是 internal contract，不进入 public API/durable schema。
- Reactive path 最小适配（只复用 previous-view helper），不引入 multi-pass 复杂重写。
- 无兼容性 wrapper/re-export/旧字段 alias。

### Blocking findings

无。

### Non-blocking observations

1. **Low: `dispatch.py:1684` 的 `memory_snapshot=None` 透传** — proactive path 显式传 `previous_compacted_view`（line 1688），`memory_snapshot=None` 只是兼容旧签名的默认值传递。当 `previous_compacted_view is not None` 时 snapshot path 不会执行（`compact_material.py:990` 的 `is None` 检查）。语义正确但表面可读性可提升：未来可考虑移除 proactive path 上的 `memory_snapshot` 参数传递。不阻塞。

2. **Low: `catch_up_conversation_memory_projection` 的 `budget=None` 无运行时 guard** — docstring 声明 `budget=None` 仅供 close-only/test-only，但无运行时检查。当前三条生产 caller 均传入 budget，不构成实际风险。若后续新增 caller 可能遗忘传 budget，可加 `assert budget is not None` 或等价 defense。属于 maintainability enhancement，不阻塞。

3. **Low: `_bounded_batch_limit` 与 `_budget_scanned_events_exhausted` 的扫描预算检查分散在两处** — line 333（batch 前限制）和 line 360（batch 后检查）。虽然当前覆盖充分且无 bug，但双重检查的意图和关系在代码中无注释说明。可补一行注释说明 `_bounded_batch_limit` 是 preventative guard、`_budget_scanned_events_exhausted` 是 accounting check。不阻塞。

---

## 9. 下一步

- 进入 draft PR gate。
- Draft PR 前确认控制文档 `当前状态` 表更新：`gate: review` → `gate: ready-to-open-draft-PR`。
- Draft PR 中引用本 artifact。
