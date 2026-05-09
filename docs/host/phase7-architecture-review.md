# Host P7 架构边界 Review

**审查对象**：`migration/host-p7-tool-trace-projection` 分支未提交 P7 实现
**审查日期**：2026-05-08
**审查依据**：`docs/host/phase7-plan.md`、`docs/host/phase7-implementation-plan.md`、`docs/host/design.md`、`docs/engine/design.md`

---

## 结论：有条件通过

P7 实现整体遵守 Host/Engine 架构边界，Engine 不拥有 trace、ToolRuntime 只产出 canonical facts、trace 由 Host observer 从 durable EventLog 派生。发现 1 个 HIGH 级别问题（raw payload 内联导致 EventLog 冷数据膨胀，与 design.md 同事务边界意图存在张力）和 3 个 MEDIUM 级别问题。无阻断性架构违规。

---

## Finding 1 — RAW PAYLOAD 内联导致 EventLog 承担过大冷数据职责

**严重性**：HIGH `[已记录-说明]`

> 文档对齐：`docs/host/design.md` §9.4 已显式记录"raw payload 内联在 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact data，事务边界收敛到单条 `append_in_transaction`"，并把"中期评估冷数据外迁"作为 `docs/host/migration-plan.md` §4.3 残留风险条目登记。当前本地诊断场景下短期可接受。
**位置**：[contracts.py:520-559](dayu/host/contracts.py#L520-L559)、[_run_input_context_fact.py:113-120](dayu/host/_run_input_context_fact.py#L113-L120)、[_run_harness.py:1365-1376](dayu/host/_run_harness.py#L1365-L1376)

**证据**：

design.md §9.4 (L790-793) 明确要求：

> `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 的冷层 raw payload 与 EventLog fact 必须作为同一个 durable unit of work 提交。Host 应先在同一事务中写入完整 model input / tool schemas raw payload，再 append fact 引用这些 raw refs；任一写入失败时 transaction 回滚，Engine attempt 不启动。禁止留下"fact 已落库但 raw ref 缺失"的可见状态。

phase7-implementation-plan.md (L28, L143) 做了决策偏移：

> fact payload 内联完整 model_input_messages JSON 与 tool_schemas JSON（EventLog row 是 TEXT 列，无大小硬上限；plan §13 已允许 cold layer 大体积）。observer 阶段从 EventLog 读出 fact 后再拆文件。**不新增 raw_payloads 表。**
>
> 没有 raw_payload 同事务写入步骤了（raw payload 内联在 fact 自身），事务边界自然收敛到单条 `append_in_transaction`。

实现中 `RunInputContextSnapshotBuiltData` 包含 `raw_input_messages_json: str` 和 `raw_tool_schemas_json: str`，完整 model input messages 和 tool schemas JSON 直接写入 EventLog `data` TEXT 列。

**分析**：

1. **同事务语义被正确满足**：raw payload 内联在 fact payload 中，`append_in_transaction` 单次写入即完成，不存在"fact 已落库但 raw ref 缺失"的风险。事务边界比 design.md 原始设想（先写 raw blob 再 append fact ref）更简洁。

2. **但 EventLog 承担了冷数据职责**：每个 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 可能携带数十 KB 到数百 KB 的 raw JSON（取决于 tool schemas 数量和 model input 长度）。这些数据进入 `run_events` 表后：
   - 增大 EventLog 存储体积，影响 `ProjectionCoordinator.drain()` 的读取效率（drain 需要反序列化整行 data）。
   - EventLog 的 retention/compaction 策略（design.md §9.3 提到的未来能力）需要同时处理这些大体积行。
   - 长期运行后 EventLog 变成冷热混合存储，违背 P6 设计中 EventLog 只存 canonical facts 的初衷。

3. **phase7-plan.md (L76) 预期的是不同架构**：

   > JSONL 可以作为 smoke / 本地诊断 sink 的实现素材，但 durable Host schema 才是 NEW projection 真源。

   但实现选择了 JSONL 作为唯一 trace 真源、零 SQLite 新表，这与 plan 的预期（durable Host schema 才是真源）有本质差异。

**建议**：

- 短期可接受：当前本地诊断场景下，EventLog 内联 raw payload 的方案简洁且正确。`run_events` 表 TEXT 列无硬限制，SQLite 单文件数据库的 IO 特性也使得大行不会造成严重性能问题。
- 中期应评估：当 Run 数量增长或 tool schemas 复杂度增加时，应考虑将 raw payload 拆到独立表或文件，fact 只保留引用。这需要同步评估 `ProjectionCoordinator.drain()` 的内存占用。
- 文档应同步：phase7-implementation-plan.md 已记录此决策偏移，但 design.md §9.4 的表述仍暗示"先写 raw payload 再 append fact ref"的原始方案，建议在 design.md 中标注当前实际实现方式。

---

## Finding 2 — JSONL 与 Projection Checkpoint 非原子是可接受的 Best-Effort 取舍

**严重性**：LOW（确认为可接受）
**位置**：[_tool_trace_projection.py:142-197](dayu/host/_tool_trace_projection.py#L142-L197)、[phase7-implementation-plan.md L30-31, L164](docs/host/phase7-implementation-plan.md)

**证据**：

phase7-implementation-plan.md (L30) 明确记录：

> Trace 存储：单一来源 = JSONL 文件。Sink 在 `observer.process` 中实时 append 一行 + flush + fsync（每行 fsync）；checkpoint 推进与文件系统写不在同一原子单元，crash 窗口产生的孤儿副本由 JSONL 行内 `idempotency_key` 字段去重。

phase7-plan.md (L96)：

> observer 默认 best-effort，失败只更新 projection checkpoint 状态，不改变 Run terminal。

design.md (L822-824)：

> `ToolTraceObserver` 是当前唯一 sink 同步阻塞 terminal drain 的 observer：sink 每行 `flush + fsync`、raw payload `tmp + os.replace` 原子落地，但写入完全在文件系统，**不动 SQLite**，不阻塞 Engine 事件产生；`tx` 参数仅为满足 `ObserverSink` 协议而保留。

**分析**：

crash 窗口语义明确：JSONL 行 fsync 完成 → `advance_success` 未提交 → crash → replay 重放 → 同 `idempotency_key` 行再次 append → JSONL 出现孤儿副本。窗口大小 = 单 batch 内已 append 的行数。

这是 **at-least-once** 投影语义，不是 exactly-once。实现通过 JSONL 行内 `idempotency_key` 字段让 analyzer 去重消化，不依赖 SQLite 唯一约束。

`ToolTraceObserver.process()` 中 `_ = tx` 明确表明 observer 不使用 SQLite 事务，只走文件系统。这与 `ObserverSink` 协议一致（tx 参数保留但不使用）。

**结论**：at-least-once + `idempotency_key` 去重是可接受的 best-effort 取舍，符合 plan 和 design 的预期。无架构违规。

---

## Finding 3 — Engine 不拥有 trace、不恢复 recorder/store、不 import Host trace

**严重性**：PASS
**位置**：全量 `dayu/engine/` 目录

**证据**：

phase7-plan.md §2 非目标 (L28-29)：

> 不恢复 Engine 私有 recorder / store，不新增 `dayu.engine.tool_trace`，不让 Engine import Host trace schema。

实现中 P7 新增和修改的文件全部位于 `dayu/host/` 目录：

- `dayu/host/_run_input_context_fact.py` — Host-owned fact builder
- `dayu/host/_tool_trace_jsonl_sink.py` — Host trace sink
- `dayu/host/_tool_trace_projection.py` — Host trace observer
- `dayu/host/contracts.py` — 新增 `RunInputContextSnapshotBuiltData`
- `dayu/host/_run_event_serializer.py` — 注册新类型 serializer
- `dayu/host/_run_harness.py` — 调用 fact builder
- `dayu/host/_durable_harness.py` — 装配 observer
- `dayu/host/_durable_event_store.py` — `append_in_transaction` thin wrapper

`dayu/engine/` 目录无任何修改。`_tool_trace_projection.py` import 了 `dayu.engine` 的数据类型（`FinalAnswerData`、`ProviderProtocolErrorData` 等），但这些是 Engine 产出的公开数据类型，不是 trace recorder 或 store。

**结论**：Engine 不拥有 trace、不恢复 recorder/store、不 import Host trace。PASS。

---

## Finding 4 — ToolRuntime 只产出 Canonical Facts，不直接写 Trace

**严重性**：PASS
**位置**：[_tool_trace_projection.py:162-197](dayu/host/_tool_trace_projection.py#L162-L197)

**证据**：

phase7-plan.md §5 (L95-96)：

> ToolRuntime 只产生工具运行事实，例如 truncation、cursor issued、fetch_more requested/completed/failed；它不是 trace writer。

实现中 `ToolTraceObserver.process()` 消费的 `RunEventType` 包括 `TOOL_RESULT_TRUNCATED`、`TOOL_FETCH_MORE_COMPLETED`、`TOOL_CURSOR_DENIED`、`TOOL_CURSOR_EXPIRED`，这些全部是 ToolRuntime 产出的 canonical RunEvent facts，通过 EventLog → ProjectionCoordinator → observer 链路到达。

ToolRuntime 本身（`dayu/host/_tool_runtime.py`）不 import 任何 trace 模块。`_tool_trace_projection.py` 从 `dayu.host.contracts` 读取 ToolRuntime 产出的 data 类型，不直接调用 ToolRuntime。

**结论**：ToolRuntime 只产出 canonical facts，不直接写 trace。PASS。

---

## Finding 5 — Tool Trace 确实由 Host Observer 从 Durable EventLog 派生

**严重性**：PASS
**位置**：[_tool_trace_projection.py:116-197](dayu/host/_tool_trace_projection.py#L116-L197)

**证据**：

`ToolTraceObserver` 实现 `ObserverSink` 协议，由 `ProjectionCoordinator` 驱动。`process()` 方法接收 `tuple[ProjectionEventEnvelope, ...]`，每个 envelope 包含一个 `RunEvent`（已从 durable EventLog 读出）。

派发规则：
- `TOOL_CALL_REQUESTED` + `TOOL_RESULT_ACCEPTED` → `ToolCallRecord`
- `RUNNER_USAGE_RECORDED` → `IterationUsageRecord`
- `FINAL_ANSWER` → `FinalResponseRecord`
- `PROVIDER_PROTOCOL_ERROR` → `ProviderProtocolErrorRecord`
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` → `IterationContextSnapshotRecord` + raw payload files

observer 不读取 `LocalRunHarness.last_run_input_build_trace_by_run`（进程内 LRU），不读取 Engine 私有对象，不从日志文本或 metadata 取数。所有数据来源均为 EventLog canonical facts。

**结论**：trace 确实由 Host observer 从 durable EventLog 派生。PASS。

---

## Finding 6 — JSONL 文件系统作为 Trace 真源：与 Plan 预期的偏差

**严重性**：MEDIUM `[已修复]`

> 修复说明：`docs/host/phase7-plan.md` §9 已标注 SQLite 表方案被 JSONL 真源方案取代；`docs/host/design.md` §9.4 已记录 JSONL 是 trace 真源、不在 SQLite 引入 `host_tool_trace_*` 表；`docs/host/migration-plan.md` §4.3 已登记 JSONL+checkpoint 非原子的 best-effort 取舍。
**位置**：[phase7-plan.md L76](docs/host/phase7-plan.md)、[phase7-implementation-plan.md L27](docs/host/phase7-implementation-plan.md)

**证据**：

phase7-plan.md (L76)：

> JSONL 可以作为 smoke / 本地诊断 sink 的实现素材，但 durable Host schema 才是 NEW projection 真源。

phase7-plan.md §9 (L273-296) 建议新增两张 SQLite 表：`host_tool_trace_records` 和 `host_tool_trace_raw_payloads`。

phase7-implementation-plan.md (L27) 做了明确决策偏移：

> 新增 SQLite 表：**0 张**。tool trace 完全走文件系统。

design.md (L818) 已更新为：

> JSONL 文件是 trace 的真源；P7 不在 SQLite 引入任何 `host_tool_trace_*` 表。

**分析**：

实现选择了 JSONL 作为唯一 trace 真源，零 SQLite 新表。这是一个合理的技术决策：

- JSONL 文件系统写入简单、无 schema migration 负担。
- 行内 `idempotency_key` 支持 analyzer 去重。
- `os.replace` 原子写入保证 raw payload 文件完整性。

但与 phase7-plan.md 的原始预期（durable Host schema 才是真源）有本质差异。plan §9 建议的 `host_tool_trace_records` 表提供了 SQLite 索引、事务性 checkpoint 推进、跨进程并发安全等能力，JSONL 方案不具备这些。

**结论**：design.md 已更新为"JSONL 文件是 trace 的真源"，implementation plan 记录了决策偏移。当前本地诊断场景下 JSONL 方案可接受。但如果未来需要多进程并发读写 trace、或需要事务性 checkpoint 推进，应重新评估是否引入 SQLite 表。

---

## Finding 7 — LocalRunHarness 膨胀趋势

**严重性**：MEDIUM（非 P7 引入，但 P7 加剧）`[已记录-说明]`

> 文档对齐：`docs/host/migration-plan.md` §4.3 已登记 "LocalRunHarness God Object 基线风险"，明确该项不属于 P7 阻断项，留待 P8/P9 拆分。
**位置**：[_run_harness.py:292-354](dayu/host/_run_harness.py#L292-L354)

**证据**：

`LocalRunHarness` 当前状态：
- 文件总行数：1772 行
- 方法数：43 个
- 字段数：16 个（含 P7 新增的 `tool_trace_context_fact_enabled` 和 `run_input_context_fact_builder`）

phase7-plan.md §5 (L98)：

> `LocalRunHarness` 只做装配和 terminal 后 `coordinator.drain()`，不能继续膨胀为 trace builder / schema owner。

**分析**：

P7 新增内容控制较好：
- 2 个字段：`tool_trace_context_fact_enabled: bool`、`run_input_context_fact_builder: RunInputContextFactBuilder | None`
- 1 个方法：`_append_run_input_context_snapshot_fact`（69 行，职责清晰）
- 2 个模块级辅助函数：`_iteration_id_for_attempt`、`_synthesize_compact_trace`

fact builder 逻辑被正确抽取到独立模块 `_run_input_context_fact.py`（`RunInputContextFactBuilder` dataclass），harness 只负责调用 builder 和 `append_in_transaction`。harness 不持有 LRU、不直接构造 trace record。

但 `LocalRunHarness` 已承载 16 个字段和 43 个方法，横跨 Run 生命周期管理、Engine 事件翻译、context compact、memory projection、attempt state 持久化、P7 fact append 等多个职责。P7 的增量虽然克制，但基线已接近 God Object 阈值。

**建议**：后续 phase（P8/P9）应评估将 `LocalRunHarness` 拆分为更小的组件（例如 `AttemptManager`、`ContextCompactHandler`、`RunInputContextFactAppender`），但不属于 P7 阻断项。

---

## Finding 8 — P7 未越界到 P8/P9/P10/P15 能力

**严重性**：PASS
**位置**：全量 P7 实现

**证据**：

phase7-plan.md §2 非目标明确列出：

| 非目标项 | 实现是否越界 |
| --- | --- |
| P8 attempt lease / recovery / fencing | 否 — P7 不引入 attempt lease 或 fencing |
| P9 Session / Run lifecycle / public interface | 否 — P7 不改变 Host public interface |
| P10 ToolRegistry 权限治理 | 否 — P7 不扩大 ToolRegistry |
| P15 audit hard-gate | 否 — P7 observer 是 `required=False`，不阻塞 Run terminal |
| async observer drain | 否 — P7 observer 同步阻塞 terminal drain，不引入异步后台 drain（属 P9 范畴） |
| web/business tools 迁移 | 否 — P7 只做 trace projection |
| OLD trace 兼容迁移 | 否 — `tool_trace_v2_host` 完全自有 schema |

**结论**：P7 实现严格控制在 Tool Trace Projection / Sink 范围内，未越界。PASS。

---

## Finding 9 — EngineEvent → RunEvent 翻译层无架构问题

**严重性**：PASS
**位置**：[_tool_trace_projection.py:37-73](dayu/host/_tool_trace_projection.py#L37-L73)

**证据**：

`ToolTraceObserver` 从 `dayu.engine` import 的类型包括：
- `FinalAnswerData`、`ProviderProtocolErrorData`、`RunnerUsageData`、`ToolCallRequestedData`、`ToolResultAcceptedData` — 这些是 Engine 产出的公开数据类型

从 `dayu.host.contracts` import 的类型包括：
- `RunEvent`、`RunEventKind`、`RunEventSource`、`RunEventType` — Host canonical facts
- `RunInputContextSnapshotBuiltData`、`ToolCursorDeniedData` 等 — Host-owned data

import 边界清晰：observer 消费 Engine 产出的公开数据类型（作为 EventLog canonical facts 的 payload），不 import Engine 内部实现。

**结论**：import 边界符合架构约束。PASS。

---

## 总结

| Finding | 严重性 | 结论 |
| --- | --- | --- |
| F1: RAW PAYLOAD 内联导致 EventLog 冷数据膨胀 | HIGH `[已记录-说明]` | 同事务语义正确，但 EventLog 承担了过大冷数据职责；短期可接受，中期应评估拆分（已登记 migration-plan §4.3） |
| F2: JSONL 与 Checkpoint 非原子 | LOW | at-least-once + idempotency_key 去重是可接受的 best-effort 取舍 |
| F3: Engine 不拥有 trace | PASS | Engine 目录无修改，不 import Host trace |
| F4: ToolRuntime 只产出 canonical facts | PASS | ToolRuntime 不直接写 trace |
| F5: trace 由 Host observer 从 EventLog 派生 | PASS | observer 消费 durable EventLog canonical facts |
| F6: JSONL 作为 trace 真源与 plan 偏差 | MEDIUM `[已修复]` | design.md / phase7-plan.md / migration-plan.md 已对齐 |
| F7: LocalRunHarness 膨胀趋势 | MEDIUM `[已记录-说明]` | P7 增量克制，God Object 基线已登记 migration-plan §4.3 |
| F8: P7 未越界 | PASS | 严格控制在 Tool Trace Projection / Sink 范围内 |
| F9: import 边界 | PASS | observer 消费 Engine 公开数据类型，不 import Engine 内部 |

**最终判定：有条件通过**

条件：建议在 merge 前或紧随其后的 PR 中：
1. 在 design.md §9.4 标注当前实际实现方式（raw payload 内联在 fact payload，非先写 raw blob 再 append fact ref）。
2. 在 phase7-plan.md §9 标注 SQLite 表方案已被 JSONL 方案替代。
