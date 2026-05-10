# Host P8 架构边界审查

## 审查范围

审查 [phase8-plan.md](./phase8-plan.md) 在 Dayu 分层架构 `UI -> Service -> Host -> Engine` 下的边界合规性。审查依据：

- [AGENTS.md](../../AGENTS.md) 架构硬约束
- [design.md](./design.md) Host 接口与架构边界真源
- [migration-plan.md](./migration-plan.md) 总控计划与残余风险
- 当前 `dayu/host/`、`dayu/engine/`、`dayu/runtime/` 实际代码状态

---

## 结论：有条件通过

P8 plan 在 7 个审查焦点上均保持正确的架构边界。以下 4 项条件必须在实施中逐 slice 验证，任一条件不满足即触发停止条件回修 plan。

| # | 条件 | 验证时机 |
| --- | --- | --- |
| C1 | AttemptSupervisor 拆分后 `_run_harness.py` 不新增 lease SQL、recovery scan、token 校验或 fencing error 策略 | P8-S3, P8-S4, P8-S5, P8-S6 每个 slice 后 |
| C2 | `ToolRuntimeOwnerScope` 不把 owner token 泄漏到 `dayu.contracts.tool_call.ToolExecutionContext`、RunEvent payload extra 或 public API | P8-S5 后 |
| C3 | multiprocessing 平台封装严格限定在 `tests/host/_multiprocess_platform.py` 或同等私有 helper，不进入 `dayu.runtime` 或 Host 生产 API | P8-S7 后 |
| C4 | `ObserverSink.process` async 升级后不引入 observer claim / lease，ProjectionCoordinator 仍从 EventLog 消费不消费 owner side channel | P8-S2 后 |

---

## F1: Engine 是否仍保持无状态执行原语

**结论：通过。** P8 plan 不要求 Engine 理解 owner token、lease、fencing 或 recovery。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 1.1 | [phase8-plan.md §5](phase8-plan.md#L84-L85) | "Host 是 attempt ownership 真源；Engine 不理解 owner token、lease、fencing，也不反向依赖 Host storage" |
| 1.2 | [phase8-plan.md §7.3](phase8-plan.md#L458-L459) | "P8 不修改 `dayu.contracts.tool_call.ToolExecutionContext`，避免把 Host owner token 泄漏到 Engine / contracts 层" |
| 1.3 | [phase8-plan.md §13](phase8-plan.md#L617-L618) | 不应修改 "`dayu/engine/**`：不新增 owner / lease / trace / recovery 语义" |
| 1.4 | [phase8-plan.md §21](phase8-plan.md#L929) | 停止条件："必须修改 Engine 才能表达 owner token / lease" |
| 1.5 | [design.md §3.2](design.md#L47-L54) | "Host 和 Engine 都是业务无关层，不懂财报业务" |
| 1.6 | [design.md §10](design.md#L891-L951) | EngineWorker 是 Host capability，Engine 只消费 `ToolExecutor` protocol，不持有 ToolRegistry |

**当前代码基线确认：** Engine (`dayu/engine/`) 不 import Host storage、RunEventStore 或任何 Host 治理状态。P8 新增的 `AttemptOwnerContext`、`AttemptScopedRunEventAppender`、`AttemptLeaseStore` 全部限定在 `dayu/host/` 内部，Engine 不可见。

**审查判断：** P8 plan 的 ToolRuntime owner context 注入路径（§7.3）通过 `ToolRuntimeOwnerScope` 在 Host 内部传递 append port，Engine 仍只看到普通 `ToolExecutor` protocol。没有 Engine 需要知道 owner token 的场景。

---

## F2: Host 是否是 attempt owner/fencing/recovery 真源

**结论：通过。** P8 plan 把 attempt ownership 全部收敛到 Host internal 新模块。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 2.1 | [phase8-plan.md §5](phase8-plan.md#L84) | "Host 是 attempt ownership 真源" |
| 2.2 | [phase8-plan.md §6.1](phase8-plan.md#L97-L193) | `AttemptOwnerToken`、`AttemptOwnerContext`、`AttemptLeaseDecision`、`AttemptFencingReason`、`AttemptRecoveryAction` 等全部类型定义在 Host internal 新文件 `_attempt_lease.py` |
| 2.3 | [phase8-plan.md §6.2](phase8-plan.md#L205-L246) | Schema 扩展只在 `host_attempts` 表（Host owned），字段包括 `owner_id`、`owner_token_hash`、`lease_generation`、`lease_expires_at`、`recovered_from_attempt_id` |
| 2.4 | [phase8-plan.md §6.4](phase8-plan.md#L292-L389) | `AttemptLeaseStore` + `AttemptSupervisor` 全部在 `dayu/host/` 内部 |
| 2.5 | [phase8-plan.md §13](phase8-plan.md#L591-L593) | 新增文件 `dayu/host/_attempt_lease.py`、`dayu/host/_attempt_supervisor.py` |
| 2.6 | [phase8-plan.md §19](phase8-plan.md#L899) | 不可接受："用进程内 dict / lock 作为 owner 真源" |

**当前代码基线确认（[`dayu/host/_run_state_store.py:7`](../../dayu/host/_run_state_store.py#L7)）：**

> "P6 不实现 admission、owner lease、fencing、orphan recovery。"

`AttemptStateStore.update_state` 当前只按 `attempt_id` 更新（[`_run_state_store.py:1-40`](../../dayu/host/_run_state_store.py#L1-L40)），无 owner CAS。`host_attempts` schema 无 owner token/lease 字段（[`_durable_event_store.py:1-40`](../../dayu/host/_durable_event_store.py#L1-L40)）。P8 plan 的 CAS 规则（§6.4 acquire/renew/verify/terminal close/mark recovering）填补了这一空白。

**审查判断：** P8 plan 将 owner token 的生成、digest 存储、lease TTL、CAS acquire/renew/verify、fencing 拒绝、recovery 扫描全部作为 Host internal 能力落地。明文 token 仅存在于 `AttemptOwnerContext`，存储只保存 hash，日志只输出 masked token。满足 Host 是 attempt ownership 真源的架构要求。

---

## F3: dayu.runtime 是否只承载层中立能力

**结论：通过。** P8 plan 明确不把 attempt ownership、lease 或多进程管理放入 `dayu.runtime`。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 3.1 | [phase8-plan.md §5](phase8-plan.md#L89-L90) | "P8 不把测试用 process launcher 做成 Host 生产能力" |
| 3.2 | [phase8-plan.md §13](phase8-plan.md#L620-L621) | 不应修改 "`dayu/runtime/**`：P8 不实现 lane，不把 Host ownership 放入 runtime" |
| 3.3 | [phase8-plan.md §5](phase8-plan.md#L90) | "若后续发现某个 helper 属于层中立运行时能力... 再单独评估是否进入 `dayu.runtime`" |
| 3.4 | [design.md §3.4](design.md#L64-L82) | lane 是层中立能力，适合放在 `dayu.runtime`；但 P8 不实现 lane |
| 3.5 | [AGENTS.md](../../AGENTS.md) 架构硬约束 | "`dayu.runtime` 只能承载层中立、运行期通用、可被多层复用的基础能力；不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`" |

**当前代码基线确认（[`dayu/runtime/__init__.py`](../../dayu/runtime/__init__.py)）：**

- 包 docstring 明确硬约束：不 import engine/host/service/ui/fins
- 当前仅有 `cancellation.py`、`log.py`、`log_levels.py`——三者均为层中立通用能力

**审查判断：** P8 plan 新增的 `UtcClock` protocol（§6.4）是 Host internal 可注入时间抽象，不放入 `dayu.runtime`。multiprocessing 测试平台封装限定在 `tests/host/_multiprocess_platform.py`。plan 正确地把 "是否进入 runtime" 的决策推迟到有明确层中立需求证据时再评估（条件 C3），不提前把测试 helper 提升为 runtime 公共 API。

---

## F4: ToolRuntime facts fencing 是否属于 Host 内部 append port

**结论：通过。** P8 plan 通过 `AttemptScopedRunEventAppender` + `ToolRuntimeOwnerScope` 在 Host 内部实现 fencing，不修改 contracts 层。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 4.1 | [phase8-plan.md §7.2](phase8-plan.md#L421-L455) | `AttemptScopedRunEventAppender` 定义在 Host internal，每次 append 在同一 `BEGIN IMMEDIATE` 事务内执行 `lease_store.verify_owner(...)` |
| 4.2 | [phase8-plan.md §7.3](phase8-plan.md#L458-L466) | "不修改 `dayu.contracts.tool_call.ToolExecutionContext`"，通过 `ToolRuntimeEventAppender` 协议 + `ToolRuntimeOwnerScope` 注入 |
| 4.3 | [phase8-plan.md §7.3 覆盖表](phase8-plan.md#L469-L477) | 7 种 ToolRuntime fact 的 call site → owner 来源映射表 |
| 4.4 | [phase8-plan.md §19](phase8-plan.md#L900) | 不可接受："owner token 放进 EventLog data 的 extra payload、ToolExecutionContext、public stream 或普通日志" |
| 4.5 | [phase8-plan.md §21](phase8-plan.md#L930-L931) | 停止条件："需要把 owner token 放入 `dayu.contracts`、RunEvent payload extra 或 public API" |

**当前代码基线确认（[`dayu/host/_tool_runtime.py`](../../dayu/host/_tool_runtime.py#L1049-L1315)）：**

> 当前 `InMemoryToolRuntime` 的 `_append_tool_result_truncated`、`_append_cursor_issued`、`_append_fetch_requested`、`_append_fetch_completed`、`_fetch_failure`、`_append_cursor_expired`、`_append_cursor_denied` 全部直接调用 `self.event_store.append(...)`，无 owner fencing。

**审查判断：** P8 plan 的 fencing 注入路径（条件 C2）正确地把 fencing check 放在 Host internal append port 内（`AttemptScopedRunEventAppender`），ToolRuntime 通过 `ToolRuntimeOwnerScope` 获取当前 attempt 的 scoped appender。非 durable 路径仍使用 `PlainRunEventAppender`，保持向后兼容。framework `fetch_more` 使用当前 attempt owner 而非原始 cursor owner（§7.3），避免旧 owner 绕过 fencing。

---

## F5: async ObserverSink 是否只是协议升级（非 observer claim/lease）

**结论：通过。** P8 plan 明确只升级调用协议为 async，不引入 observer claim/lease/ownership。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 5.1 | [phase8-plan.md §11](phase8-plan.md#L536-L538) | "P8 固定升级 `ObserverSink.process` 为 async 协议，但不实现 observer claim / lease，不升级 observer ownership" |
| 5.2 | [phase8-plan.md §11](phase8-plan.md#L561-L565) | "P8 不实现跨进程 observer claim / lease，不实现后台 observer worker，不改变 projection checkpoint schema" |
| 5.3 | [phase8-plan.md §11](phase8-plan.md#L564) | "attempt ownership 与 observer ownership 仍是两个状态机" |
| 5.4 | [phase8-plan.md §19](phase8-plan.md#L907-L908) | 不可接受："P8 引入 observer claim / lease" |
| 5.5 | [phase8-plan.md §2](phase8-plan.md#L40-L41) | 非目标："不做 observer claim / lease，不把 ProjectionCoordinator 升级为后台消费者 ownership 模型" |

**当前代码基线确认（[`dayu/host/_event_observer.py:75-105`](../../dayu/host/_event_observer.py#L75-L105)）：**

> `ObserverSink.process` 是同步协议（`def process(self, *, tx, batch) -> None`），P6 `MemoryProjectionObserver._run_async` 通过 thread + event loop 桥接 async store。P7 `ToolTraceObserver.process` 是同步但内部执行文件 IO。

**审查判断：** P8 plan 将 `process` 升级为 `async def process(...)`（§11），这是纯协议升级：消除 P6 的 `_run_async` thread bridge，让 observer 可以直接 `await` async store/sink。Plan 明确声明的边界——不实现 observer claim/lease、不实现后台 observer worker、不改变 checkpoint schema、observer 仍从 EventLog 消费而不从 owner side channel——与 attempt ownership 状态机完全隔离。条件 C4 在 P8-S2 实施后验证。

---

## F6: 多平台 helper 是否只在 tests/utils 范围

**结论：通过。** P8 plan 把 multiprocessing 平台封装严格限定在测试/smoke 范围。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 6.1 | [phase8-plan.md §1](phase8-plan.md#L18) | "该封装先定位为测试 / smoke helper，不提升为 Host 生产 launcher" |
| 6.2 | [phase8-plan.md §5](phase8-plan.md#L89-L90) | "P8 只在 `tests/host` / `utils` 范围封装 multiprocessing 测试和 smoke 的平台差异" |
| 6.3 | [phase8-plan.md §13](phase8-plan.md#L599-L600) | 新增 `tests/host/_multiprocess_platform.py` 或同等私有测试 helper |
| 6.4 | [phase8-plan.md §19](phase8-plan.md#L907) | 不可接受：把测试用 process launcher 做成 Host 生产能力 |
| 6.5 | [phase8-plan.md §2](phase8-plan.md#L38) | 非目标："不把 lane / runtime dependency 实现为 Host 私有业务层" |

**审查判断：** P8 plan 封装的范围明确：start method、join timeout、进程终止、文件 SQLite path、跨进程结果收集。这些封装定位为测试 helper（`tests/host/_multiprocess_platform.py`），与 Host 生产 API 严格隔离。条件 C3 确保实施不越界。

---

## F7: LocalRunHarness 是否继续恶化为 God Object，AttemptSupervisor 拆分是否足够

**结论：通过（有残余风险）。** P8 plan 通过 `AttemptSupervisor` 拆分出 lease/renew/recovery 职责，但承认 `LocalRunHarness` 仍偏大，完整拆分留到 P9。

**证据：**

| # | 来源 | 内容 |
| --- | --- | --- |
| 7.1 | [phase8-plan.md §5](phase8-plan.md#L68-L80) | 新增 AttemptSupervisor 拆分架构图，AttemptSupervisor 承载 acquire/renew/fence/terminal close/recovery |
| 7.2 | [phase8-plan.md §5](phase8-plan.md#L87-L88) | "`LocalRunHarness` 只能编排 attempt supervisor、event append 与 projection drain，不承载 lease SQL、recovery scan、token 校验或 fencing error 策略" |
| 7.3 | [phase8-plan.md §20](phase8-plan.md#L918-L919) | 残余风险："`LocalRunHarness` 仍偏大；P8 必须抽出 AttemptSupervisor，但完整 RunSupervisor 拆分留到 P9" |
| 7.4 | [phase8-plan.md §19](phase8-plan.md#L905-L908) | 不可接受："在 `_run_harness.py` 堆 lease SQL、recovery scan、observer claim" |
| 7.5 | [migration-plan.md §4.3](migration-plan.md#L397-L402) | P7 残余风险："`LocalRunHarness` 已承载 16 字段 / 43 方法... 基线已接近 God Object 阈值" |

**当前代码基线确认（[`dayu/host/_run_harness.py`](../../dayu/host/_run_harness.py#L1-L99)）：**

> P7 的 `LocalRunHarness` 横跨 Run 生命周期管理、Engine 事件翻译、context compact、memory projection、attempt state 持久化、P7 fact append 等职责。

**P8 plan 拆分的职责：**

| 职责 | P7 位置 | P8 目标位置 |
| --- | --- | --- |
| attempt lease acquire/renew/close | 不存在 | `_attempt_supervisor.py` → `AttemptSupervisor` |
| lease SQL / CAS | 不存在 | `_attempt_lease.py` → `AttemptLeaseStore` |
| owner token 生成/校验 | 不存在 | `_attempt_lease.py` |
| recovery scan / reconcile | 不存在 | `_attempt_supervisor.py` → `AttemptSupervisor` |
| attempt-scoped event append | 散落在 `_run_harness.py` | `_attempt_supervisor.py` → `AttemptScopedRunEventAppender` |
| ToolRuntime facts fencing | 无 fencing | `_tool_runtime.py` → `ToolRuntimeOwnerScope` |

**审查判断：** P8 plan 的 AttemptSupervisor 拆分方向正确——把 lease SQL、CAS、recovery scan、token 校验等全新职责放到独立模块，`LocalRunHarness` 通过薄委托接入（条件 C1）。但 plan 诚实地承认（§20）`LocalRunHarness` 仍偏大，因为 context compact、memory projection trigger、Engine event translation 等职责仍在 harness 上。完整 `RunSupervisor` 拆分留给 P9，与 P9 的 Session/Run lifecycle governance 一起做。这在架构上是合理的优先级安排：P8 先解决多进程安全的 owner 真源问题，P9 再以 owner 真源为基础做完整治理拆分。

---

## 审查不变量检查

以下不变量来自 [migration-plan.md §10](migration-plan.md#L583-L602)，逐项对照 P8 plan 检查：

| # | 不变量 | P8 plan 状态 |
| --- | --- | --- |
| I1 | 没有 Engine -> Host / Service / UI 反向依赖 | 通过。§13 明确不修改 `dayu/engine/**`，§21 把"必须修改 Engine"作为停止条件 |
| I2 | 没有 Host / Engine 内嵌业务知识 | 通过。§2 明确不迁移业务工具，不让 Host/Engine 理解 fins/doc/web 业务语义 |
| I3 | 财报文档访问仍只能通过 `dayu.fins.storage` | 通过。§2 "财报文档存取仍只能由业务工具通过 `dayu.fins.storage` 保证" |
| I4 | 没有旧接口兼容 wrapper / facade / re-export | 通过。§2 "不做旧库兼容读取或兼容测试" |
| I5 | 没有 `Any`、`object`、无类型参数扩散 | 通过。§6.1 全部类型为 frozen dataclass/slots + StrEnum，§21 把"typed contract 无法避免 Any/object"作为停止条件 |
| I6 | P8 有对应 smoke | 通过。§15 定义 `utils/smoke_host_p8_attempt_lease.py`，6 个场景覆盖 acquire/renew/fence/recovery/terminal/observer |

---

## 残余风险评估

| # | 风险 | 严重性 | 缓解 |
| --- | --- | --- | --- |
| R1 | `LocalRunHarness` P8 后仍偏大（16+ 字段保持），P9 拆分可能因 P8 新增 harness→supervisor 薄委托而产生额外重排成本 | 中 | §20 已登记，P9 plan 必须包含完整 RunSupervisor 拆分 |
| R2 | SQLite time / Python time 混用导致 lease expiry flaky | 中 | §20 通过可注入 `UtcClock` + 集中常量降低风险 |
| R3 | ObserverSink async 升级可能触发 P6/P7 projection tests 大面积修改 | 中 | §11 明确迁移范围，P8-S2 独立 slice 先处理 |
| R4 | `AttemptScopedRunEventAppender` 抽象可能与 P9 admission 的 append port 产生接口摩擦 | 低 | 两者都是 Host internal，P9 可以调整；§6.4 API 设计已考虑扩展性 |
| R5 | P8 恢复 scan 不推进 projection checkpoint（§10），若 stale attempt 的 EventLog 有新事件未被 observer drain，新 recovery attempt 的 observer 可以补齐 | 低 | observer 从 EventLog global position 消费，不依赖 attempt 边界 |

---

## 审查记录

- 审查类型：架构边界 plan review
- 审查日期：2026-05-09
- 审查依据：`AGENTS.md`、`docs/host/design.md`、`docs/host/migration-plan.md`、当前代码基线
- 审查结论：**有条件通过**（4 项条件见上文）
- 下一步：条件 C1-C4 的验证责任由 P8 各 slice 的实施 Agent 与 code review Agent 共同承担；任一条件不满足必须触发 §21 停止条件
