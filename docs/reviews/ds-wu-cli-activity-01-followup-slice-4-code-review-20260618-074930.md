# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`（仅作为参照基线；本次只 review Slice 4 未提交改动）
- Output file: `docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`
- Design truth: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md` Slice 4
- Implementation report: `docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md`

### Included scope

- `dayu/host/memory_repair.py` — Conversation Memory repair 去预算化
- `dayu/host/open_host.py` — after-commit 热路径移除 memory catch-up port
- `dayu/host/dispatch.py` — compact accepted 热路径移除 memory catch-up；required repair 保留 target_reached
- `dayu/host/README.md` — 同步 opener 当前装配事实
- `tests/host/test_memory_repair.py` — 新增去预算化断言
- `tests/host/test_open_host_runtime.py` — 新增 after-commit port=None 断言
- `tests/host/test_dispatch_scheduler.py` — 新增 compact accepted 不调用 catch-up 断言
- `tests/host/test_logging.py` — 删除旧 budget 日志断言
- `docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md` — Codex 实现报告（只读，不 review）

### Excluded scope

- Slice 1–3 改动（ingest delta non-durable、filter-aware EventLog read、ProjectionRunner 语义）
- Slice 5（RunInputBuilder inline repair filter 共源化）
- 非 Slice 4 范围内的其他已提交/未修改文件
- `retry_repair_budget_exhausted` 字段（属于 Context Governance / compaction payload，不是 memory projection repair budget，Codex 报告已标记为 later work unit）

### Parallel review coverage

无。本次 review 由主 reviewer 逐文件走读。

## Findings

### 1-未修复-中-ConversationMemoryProjectionCatchupPort 违反设计计划命名约束和兼容性胶水禁令

- **入口/函数**: `ConversationMemoryProjectionCatchupPort.__init__` 与 `catch_up_projection`
- **文件(行号)**: `dayu/host/memory_repair.py:75-120`
- **输入场景**: 任何想在 admission/scheduler 中注入 memory catch-up 的调用方（当前仅测试使用）
- **实际分支**: 类定义存在且为公开类（无 `_` 前缀），`catch_up_projection()` 方法委托到 `catch_up_conversation_memory_projection()` 且不传 `max_event_sequence`，即无界追到 idle
- **预期行为**: 按设计计划 Slice 4（line 336-337）：
  > "`open_host._MemoryProjectionCatchupPort` 若保留，只能暴露 maintenance 语义，不得命名为 catch-up port；否则删除该 port。"

  且 line 179 明确选择"直接移除 after-commit / after-compact 的机会性 memory projection 动作"。因此该类要么被删除，要么重命名为 maintenance 语义（`_` 前缀私有类、方法名不含 "catch-up"、行为有界）
- **实际行为**: 类被从旧名 `_MemoryProjectionCatchupPort` 重命名为 `ConversationMemoryProjectionCatchupPort`，仍然是公开类，方法仍叫 `catch_up_projection()`，行为仍是无界追到 idle。生产热路径（open_host.py、dispatch.py）已不再实例化该类，但类本身作为兼容性胶水保留在模块中
- **直接证据**:
  - `dayu/host/memory_repair.py:75` — 类声明 `class ConversationMemoryProjectionCatchupPort:`（公开，无 `_` 前缀）
  - `dayu/host/memory_repair.py:108` — 方法名 `def catch_up_projection(self)`
  - `dayu/host/memory_repair.py:115-120` — 调用 `catch_up_conversation_memory_projection(...)` 不传 `max_event_sequence`，即无界追到 idle
  - `dayu/host/open_host.py:655` — `projection_catchup_port=None`，不注入该 port
  - `dayu/host/open_host.py:666` — `projection_catchup_port=None`，不注入该 port
  - `tests/host/test_memory_repair.py:614` — 测试直接实例化该 port
  - `tests/host/test_admission_queue.py:1018` — 测试注入该 port 到 admission service
  - `tests/host/test_resolve_wait_command.py:208` — 测试注入该 port 到 admission service
  - `tests/host/test_toolruntime_accept_barrier.py:656` — 测试注入该 port 到 tool accept port
  - CLAUDE.md "禁止兼容性代码"：禁止"兼容性 wrapper / facade：方法体仅透传到真源模块，不增加有效语义"
- **影响**: 当前无生产影响（热路径已断开），但存在维护风险——
  1. 类名和方法名暗示这是一个合法的"catch-up"入口，未来维护者可能误将其注入热路径
  2. 类作为公开 API 存在于模块中，但实际只被测试使用，属于 CLAUDE.md 禁止的兼容性胶水
  3. `catch_up_projection()` 的无界行为（不传 `max_event_sequence`）正是 Slice 4 明确要求从热路径移除的语义
- **建议改法和验证点**:
  - **方案 A（推荐）**: 删除 `ConversationMemoryProjectionCatchupPort` 类。修改四个测试文件中的引用，测试直接调用 `catch_up_conversation_memory_projection()` 或使用 `unittest.mock.Mock` 构造 `ProjectionCatchupPort` 替身
  - **方案 B**: 重命名为 `_ConversationMemoryProjectionMaintenancePort`（加 `_` 前缀），方法改为 `catch_up_projection_maintenance()`，并在 docstring 明确标注"仅测试/诊断用途，非 correctness catch-up 入口"。同时增加 `max_event_sequence` 参数或硬编码 page cap，确保不会被误用作无界 correctness catch-up
  - 验证点：`rg -n "ConversationMemoryProjectionCatchupPort\|CatchupPort" dayu/ tests/` 无匹配
- **修复风险（低）**: 仅影响测试文件，不涉及生产逻辑。四个测试文件的修改是机械替换
- **严重程度（中）**: 不阻塞 merge（热路径已断开），但违反设计计划显式约束和 CLAUDE.md 兼容性禁令

## Open Questions

- 无。

## Residual Risk

- **Slice 3 依赖**: `_run_memory_projection_until_stop` 的 idle 检测（line 283: `batch_result.events_scanned < batch_size`）依赖 `ProjectionRunner.run_once` 的 `events_scanned` 语义正确反映"已读取的总 EventLog row 数"（含非匹配行）。若 Slice 3 的 filter-aware `ProjectionRunner` 实现中 `events_scanned` 只计数匹配行，则此处的 idle 检测会提前误判。当前 Slice 4 测试使用 FakeProjectionRunner，该 fake 的 `scanned` 模拟"总读取行数"语义，因此 Slice 4 自身行为正确；风险在于 Slice 3 实现必须与此语义一致。建议在 Slice 3 closeout 时交叉验证该不变量
- **测试覆盖边界**: 当前 96 个测试全部通过，覆盖了 batch_size=1 多页追到 idle/target、rebuild 多页追到 target、failure 立即停止、真实 durable store page_size=1 追到 idle、required catch-up 跨超过旧 batch cap（17/33 批）、after-commit port=None 断言、compact accepted 不调用 catch-up 断言、dispatch required repair target_reached 断言、日志无 budget 字段断言。未覆盖的场景：`_run_memory_projection_until_stop` 在 `started_cursor is None` 且 while 循环零次迭代时的行为（line 286-287 的 fallback），该路径依赖 `runner.run_once` 至少执行一次，当前由 `_validate_batch_size` 保证非零 batch_size，行为正确但无显式测试覆盖该边界
- **`ConversationMemoryProjectionCatchupPort` 残留**: 见 Finding 1。该类的存在不阻塞功能正确性（热路径已断开），但它是设计计划显式要求移除的兼容性胶水。若选择保留至后续 WU 处理，必须在本 WU closeout 中明确记录为 deferred-with-owner
