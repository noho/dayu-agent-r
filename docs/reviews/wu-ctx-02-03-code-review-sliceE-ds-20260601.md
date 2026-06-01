# WU-CTX-02 + WU-CTX-03 Code Review Slice E — AgentDS

## 审查范围

- **审查 Gate**: Slice E implementation review。
- **Base commit**: 13500ae (accepted Slice D)。
- **审查变更**:
  - `tests/host/test_dispatch_scheduler.py`: 新增 `_RepeatedReactiveOverflowWorkerFactory` / `_RepeatedReactiveOverflowWorker` / `_RepeatedReactiveOverflowHandle`；新增 `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit`；扩展 `_soft_compact_policy` 支持显式 `max_reactive_compactions_per_run`。
  - `tests/README.md`: 同步覆盖说明。
- **设计真源**: `docs/host/design.md` 第 25 节 Context Governance。
- **总控文档**: `docs/host/host-core-followup-implementation-control.md`。
- **Approved plan**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md` Slice E。
- **Implementation artifact**: `docs/reviews/wu-ctx-02-03-implementation-sliceE-codex-20260601.md`。

## 验证命令与结果

```bash
source .venv/bin/activate

# 全量 dispatch scheduler 测试
pytest tests/host/test_dispatch_scheduler.py -q
# => 57 passed in 1.02s

# reactive 相关测试子集
pytest tests/host/test_dispatch_scheduler.py -q -k "reactive"
# => 4 passed, 53 deselected in 0.36s

# proactive / compact 相关测试子集
pytest tests/host/test_dispatch_scheduler.py -q -k "proactive or compact"
# => 12 passed, 45 deselected in 0.43s

# 周边受影响的 context 测试
pytest tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py -q
# => 118 passed in 0.70s

# 类型检查
python -m pyright dayu/ tests/ utils/
# => 0 errors, 0 warnings, 0 informations
```

## Findings

### No blocking findings

以下按 severity 排序。

---

### F-1 (MEDIUM): `_soft_compact_policy` 扩展引入隐式默认值依赖

**文件**: `tests/host/test_dispatch_scheduler.py:4439-4458`

**描述**: `_soft_compact_policy` 新增参数 `max_reactive_compactions_per_run: int = 2`，该默认值与 `ContextBudgetPolicy` dataclass field default（`DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 2`）一致。现有调用方（`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 等 3 处）不传该参数，行为不变。

**风险评估**: 当前无实际风险——默认值 2 与 dataclass default 对齐，且现有测试均通过。但 `_soft_compact_policy` 的默认值现在与 `ContextBudgetPolicy` 的 dataclass default 存在**双重真源**：若未来 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 修改为 3，`_soft_compact_policy` 的默认值 2 将成为隐藏漂移。两个默认值应始终保持一致。

**建议**: 将 `_soft_compact_policy` 的默认值改为 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`（从 `dayu.host.context_policy` 导入），消除双重真源。该改动属于当前 Slice 范围内的防御性改进，不作为 blocker。

---

### F-2 (INFO): 超时常量语义归类

**文件**: `tests/host/test_dispatch_scheduler.py:165`

**描述**: 新增 `_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS = 2.0`，用于 `asyncio.wait_for` 超时保护。该常量与 `_SOFT_CONTEXT_WINDOW_SIZE`、`_SOFT_HARD_THRESHOLD_TOKENS` 等 policy 参数常量放在同一区块，但语义不同——前者是测试同步超时，后者是 policy 参数。

**评估**: 不影响 correctness，仅影响可读性。常量命名已经表达语义区别，无需移动位置。

---

### F-3 (INFO): `create_worker` 中 `del snapshot` 模式延续

**文件**: `tests/host/test_dispatch_scheduler.py:1229`

**描述**: `_RepeatedReactiveOverflowWorkerFactory.create_worker` 使用 `del snapshot` discard 参数。该 snapshot 由 scheduler 在 `worker.accept(snapshot, request)` 中再次传入，factory 不需要转发。此模式与已有 `_ReactiveRecoveryWorkerFactory.create_worker` (line 1113) 一致。

**评估**: 无风险，与既有代码风格一致。

---

### F-4 (INFO): `_event_types_for_run` 硬编码 limit=200

**文件**: `tests/host/test_dispatch_scheduler.py:4804`

**描述**: `_event_types_for_run` 是已有 helper，本 Slice 未修改。其内部 `read_events_after(transaction, 0, limit=200)` 的 200 限制对本次测试足够（预计 event < 30），但若后续测试在同一 Session 内产生大量跨 Run 事件，可能截断。该问题是**既有代码的通用风险**，不属于本 Slice 引入。

**评估**: 不阻塞本 Slice；若未来扩展，可改为 `read_run_events` 类专用查询。

---

## 审查重点逐项检查

### 1. E2E 是否真实覆盖 scheduler / worker dispatch-loop

**通过。** 测试使用：
- `HostDispatchScheduler.open()` 真实 scheduler 启动路径
- `LocalEngineWorkerFactory` / `LocalEngineWorker` / `LocalWorkerHandle` 协议边界
- 真实 `EngineEvent` ingest mapping → reactive compact → recovery Attempt 创建 → 再 dispatch → 再 ingest
- `drain_once()` 触发 scheduler 真实 dispatch 循环
- `FakeContextCompactor` 提供 deterministic compact proposal

该路径覆盖了完整的 `dispatch → worker accept → EngineEvent → ingest mapping → reactive compact → CONTEXT_COMPACTION_REQUESTED → CONTEXT_COMPACTED → recovery Attempt → re-dispatch → ... → limit → CONTEXT_COMPACTION_FAILED → RUN_FAILED` 链，不是 ingest 单点单元测试。

### 2. 连续 reactive overflow 是否确定性同步

**通过。** 同步机制：
- `_accepted_condition` / `_closed_condition` 均为 `asyncio.Condition`，使用 `wait_for(predicate)` 而非 polling sleep
- `record_accept` / `record_closed` 在修改计数后调用 `notify_all()`
- `wait_for_accepted_count` / `wait_for_closed_count` 仅用 `asyncio.wait_for` 加 2s 超时作为防御，实际同步由 condition predicate 驱动
- handle close 发生在 scheduler 收口后：`events()` async generator 的 `yield` 为 await point，确保 scheduler 在 accept → events → ingest → close 之间多次 yield control 给 event loop

没有裸 sleep，不依赖不可控 race。

### 3. Attempt 数是否严格不超过 1 + max_reactive_compactions_per_run

**通过。** 断言：
```python
expected_attempt_count = 1 + policy.max_reactive_compactions_per_run  # = 3
assert factory.created == expected_attempt_count
assert len(factory.accepted_snapshots) == expected_attempt_count
assert actual_attempt_count == expected_attempt_count
assert actual_attempt_count <= expected_attempt_count  # 冗余防御
```

生产代码 `engine_ingest.py:1214` 在 `compact_count >= policy.max_reactive_compactions_per_run` 时直接 `_fail_reactive_recovery_without_request`，不创建新 recovery Attempt。上限语义正确。

### 4. Event 计数是否符合设计上限策略

**通过。** 对 `max_reactive_compactions_per_run=2`：

| Event Type | 断言值 | 设计依据 |
|---|---|---|
| `CONTEXT_COMPACTION_REQUESTED` | 2 | 前 2 次 overflow 各写一个；第 3 次 overflow 触发 limit，不写 request（`_fail_reactive_recovery_without_request` 路径） |
| `CONTEXT_COMPACTED` | 2 | 前 2 次 compact 成功，每次写一个 |
| `CONTEXT_COMPACTION_FAILED` | 1 | 第 3 次 overflow 触发 limit，`_fail_reactive_recovery_without_request` 写入 |
| `RUN_FAILED` | 1 | 最后 fail closed |
| `RUN_LOST` | 0 | 设计明确规定 reactive failure 不写 `RUN_LOST`（`design.md:2865`） |

### 5. Failed payload 验证

**通过。** 对最后一次 `CONTEXT_COMPACTION_FAILED`:
- `failure_reason == "reactive_compact_limit_reached"` — 匹配生产代码 `engine_ingest.py:1219`
- `attempt_count == 0` — `_fail_reactive_recovery_without_request` 固定传 0（`engine_ingest.py:1309`）
- `retry_repair_budget_exhausted is False` — 同上（`engine_ingest.py:1310`）
- `fallback_action == "not_applicable"` — `_append_reactive_compaction_failed_event` 默认值（`engine_ingest.py:1780`）
- fallback 字段全为 None（`fallback_policy_decision`、`fallback_input_window`、`fallback_input_digest`、`fallback_budget_result`）— 由 `assert_failed_payload_no_fallback` 断言（`_context_compaction_assertions.py:38-41`）

对 `RUN_FAILED`:
- `error_code == "reactive_compact_limit_reached"` — 透传自 `_fail_reactive_recovery_without_request`（`engine_ingest.py:1317`）
- `context_compaction_failed_event_id` 指向 `CONTEXT_COMPACTION_FAILED` event id — 确保 audit trail 可追溯

### 6. 无生产代码变更

**通过。** diff 仅涉及 `tests/host/test_dispatch_scheduler.py` 和 `tests/README.md`。无生产 seam、无新 public API、无 `dayu/` 路径变更。

### 7. README 更新合规

**通过。**
- `tests/README.md`: 已同步新增覆盖说明——`"连续 reactive overflow dispatch-loop 达到上限后 fail closed 且不写 RUN_LOST"`。符合 AGENTS.md 触发规则（`tests/` 修改 → `tests/README.md` 更新）。
- `dayu/host/README.md`: 未更新。验证后确认现有文档（line 274-276）已描述 reactive path 在 `max_reactive_compactions_per_run` 范围内继续 compact、超过上限 fail closed、不写 `RUN_LOST`、reactive compact failure 收口为 `FAILED`。无需重复。
- `dayu/config/README.md`: 未更新。验证后确认该文档不涉及 `max_reactive_compactions_per_run` 配置入口，且本 Slice 无配置变更。合理。

### 8. AGENTS 约束合规

**通过。**
- 中文 docstring: 所有新增类和方法均有完整中文 docstring，含参数、返回值、异常。
- 类型签名: 无 `Any`、`object`、无类型参数。
- 无魔法数字: `_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS` 为模块级常量；测试断言使用 `policy.max_reactive_compactions_per_run` 派生期望值，不硬编码。
- 无 overfitted fragile test: 测试通过 public dispatch / ingest 路径验证行为，不断言内部实现顺序或私有状态。
- pyright: 0 errors, 0 warnings, 0 informations。

## RR-CTX-PLAN-03 收口

RR-CTX-PLAN-03（连续 overflow E2E 稳定性）已由本 Slice 覆盖。验证通过：
- 确定性 fake worker / scheduler helper ✓
- 无裸 sleep 或 race ✓
- E2E 断言 Attempt 数、compact events 与 terminal 状态 ✓
- 连续 overflow 不无限循环 ✓

建议在 aggregate review 中标记该 RR 为 `closed`。

## 最终结论

**Accepted — No blocking findings.**

Slice E 实现符合设计真源与 approved plan。测试覆盖了真实 dispatch-loop 路径下的连续 reactive overflow → 上限收口 → fail closed 完整闭环，同步机制确定性强，事件计数与 payload 断言准确。无生产代码变更，无类型错误，README 更新合规。

仅有一条 MEDIUM 级别建议（F-1: `_soft_compact_policy` 默认值与 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 双重真源），可在后续 cleanup 中收敛，不作为当前 Slice blocker。
