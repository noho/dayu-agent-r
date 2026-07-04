# WU-TOOLS-CANCEL-01 Plan Review — AgentDS

## Metadata

- **Reviewer**: AgentDS
- **Reviewed artifact**: `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- **Work unit**: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- **Gate**: plan review
- **Timestamp**: 2026-07-04T18:19:16+08:00
- **Review target scope**: plan readiness for implementation gate
- **Design sources consulted**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source consulted**: `docs/host/issues-implementation-control.md`
- **Code evidence consulted**:
  - `dayu/host/dispatch.py` (lines 685-715, 3730-3923, 4589-4600)
  - `dayu/host/local_proxy.py` (lines 125-244)
  - `dayu/host/tool_runtime.py` (lines 2590-2630, 3490-3544)
  - `dayu/tools/web/web_playwright_backend.py` (lines 418-551)
  - `dayu/tools/web/web_http_session.py` (session/requests usage)
  - `dayu/tools/doc_tools.py`, `dayu/fins/tools/fins_tools.py`, `dayu/tools/web/web_tools.py` (`asyncio.to_thread` sites)

---

## Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| A1 | Root cause is ToolRuntime/worker execution boundary lacking interruptible capsule | **Confirmed** | `_dispatch_tool_call_with_bounds` uses `await_or_cancel` on the awaitable task but cannot stop synchronous I/O in `asyncio.to_thread`; `on_cancel` is a no-op (`del reason`); active worker cleanup only runs in finally after stream ends |
| A2 | Existing accept barrier / late rejection is sufficient for stale quarantine | **Confirmed** | `_invalid_accept_context_reason` checks `RunStatus.RUNNING`, `AttemptStatus.RUNNING`, `STALE_EXECUTION`; Engine ingest has late terminal rejection at lines 3283-3308 |
| A3 | No durable schema / EventLog / Engine contract changes needed | **Confirmed** | Capsule is runtime-only; cancel terminal truth already handled by WU-LIFE-03 watchdog |
| A4 | Plan does not introduce second cancel timeout | **Confirmed** | Section 2 and 6 explicitly forbid it; all deadlines derived from `tool_execution_timeout_seconds` |
| A5 | Plan does not hardcode provider-specific kill API in Host core | **Confirmed** | Capsule provides typed generic boundary; adapter implements provider-specific abort |
| A6 | Completed WU are consumed, not redone | **Confirmed** | WU-LIFE-03 terminal truth, WU-LIFE-04 deadline governance, WU-WAIT-03 external job lifecycle all correctly referenced as prerequisites |
| A7 | 3-slice structure forms semantic closures | **Partially confirmed** | S1 (capsule + cleanup) and S3 (smoke + docs) are well-scoped; S2 (tool migration) depends on S1 capsule contract stability — risk not explicitly acknowledged |

---

## Findings

### F1 — Blocking — `on_cancel` → worker stream interruption mechanism unspecified

- **位置**: Section 7.7 "Lane token / active worker cleanup" (line 257), Section 8 Slice S1 "Exact allowed changes" (line 307)
- **问题类型**: 不可直接实施
- **当前写法**: "default local worker `on_cancel(...)` 必须触发 worker event stream interruption / close，使 `_consume_worker_events(...)` 进入 finally。"
- **反例/失败场景**:
  当前 `LocalWorkerHandle.on_cancel` 实现为 `del reason`（空操作）。`_DefaultLocalWorkerEventStream` 持有 `_active_anext` task 和底层 `_events` async generator。`on_cancel` 可以通过以下至少三种互不兼容的方式触发 stream interruption：
  a. 取消 `_active_anext` task（会抛出 `CancelledError`）
  b. 调用 `_DefaultLocalWorkerEventStream.close()`（取消 task + `aclose()` generator）
  c. 设置一个 `_closed` flag 让 `__anext__` 返回 `StopAsyncIteration`

  三种方式对 `_consume_worker_events` 中 `anext(events)` 的异常传播路径不同：
  - `CancelledError` 在 line 3829 被 `raise` 重新抛出（在 `finally` 之前）
  - `StopAsyncIteration` 进入 line 3797 的 `except StopAsyncIteration` 分支
  - `RuntimeError`（并发读取）在 line 3831 的 `except Exception` 分支进入 `_safe_close_worker_lost`

  plan 没有裁决选择哪一种、为什么，也没有规定 `CancelledError` 重新抛出后对调用方的影响。
- **为什么有问题**: 这是 Slice 1 的**核心机制**——worker cleanup 和 lane token release 依赖 stream interruption 进入 finally。如果 implementation agent 选错机制，可能导致 lane token 无法释放、`CancelledError` 污染调用栈、或 worker stream close 行为不一致。
- **直接证据**: `dayu/host/local_proxy.py:136-146`（空 `on_cancel`），`dayu/host/dispatch.py:3794-3828`（`anext(events)` 循环的三种异常路径），`dayu/host/dispatch.py:3904-3911`（finally 中 lane release）
- **影响**: 实施 Agent 需要在三种互不兼容的 interruption 机制中自行裁决；裁决错误会导致 lane token 泄漏或 worker close 异常传播错误
- **建议改法和验证点**:
  1. Plan 必须明确 `on_cancel` 调用 `_DefaultLocalWorkerEventStream.close()` 作为默认实现（该路径已有完整的 task cancel + generator aclose + 幂等 close lock）
  2. 必须说明 `CancelledError` 在 `_consume_worker_events` line 3829 re-raise 后由哪个调用方 suppress
  3. 或者，如果选择 cancel `_active_anext` task 方式，必须说明 `CancelledError` 传播路径和 suppress 位置
  4. 验证点：focused test 注入 cancel 后，assert finally 中的 `_safe_release_lane_token` 在 bounded time 内被调用
- **修复风险**: 低。只需在 plan 中明确 interruption 机制选择及理由，当前 `_DefaultLocalWorkerEventStream.close()` 实现已提供完整的 task cancel + aclose + 幂等语义。
- **严重程度**: 高

---

### F2 — Blocking — Process-backed capsule feasibility not assessed per tool path

- **位置**: Section 4.3 "生产工具存在 blocking I/O 形态" (line 89-96), Section 7.4 "Subprocess / process group / sandbox termination" (line 228-235), Risk R1 (line 561-564)
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: "生产级路径优先使用 process-backed capsule"；Risk R1 承认 "部分现有 tool callable 或 provider closure 可能不可 picklable"，但将其完全推迟到 "S1 implementation" 裁决，fallback 为 "转为 dedicated follow-up issue，不允许把不可抢占路径标为 production-grade"。
- **反例/失败场景**:
  1. `dayu/tools/web/web_http_session.py` 使用全局共享的 `requests.Session` 实例（`_WEB_SESSION`）——该对象不可 picklable，且全局共享使其不能简单地"迁移到 process capsule"
  2. `dayu/tools/doc_tools.py:733` 的 `asyncio.to_thread(business_call, token)` 中 `business_call` 是一个 `functools.partial` 或 closure——是否可 picklable 取决于具体绑定的参数
  3. `dayu/fins/tools/fins_tools.py:777` 同理

  如果 S1 实现发现 doc/fins/web 三条路径都不可 picklable，而 plan 唯一的 fallback 是"标记为不可抢占"——那 WU-TOOLS-CANCEL-01 就不能关闭 #87（因为主要生产工具仍不可抢占），这与 work unit 目标冲突。
- **为什么有问题**: Plan 将核心可行性问题推迟到 S1 implementation，但 S2（生产工具迁移）依赖 S1 的可行性结论。如果 S1 证明 process-backed capsule 对多数生产路径不可行，plan 没有备选方案。这违反了 "plan 必须 code-generation-ready" 的要求——implementation agent 在 S1 可能发现整个 work unit 的核心前提不成立。
- **直接证据**: `dayu/tools/web/web_http_session.py:24-25`（全局 `requests.Session`），`dayu/tools/doc_tools.py:733`（`asyncio.to_thread(business_call, token)`），`dayu/tools/web/web_playwright_backend.py:480-551`（已有 process-backed 模式但使用 `multiprocessing.Process` 而非通用 capsule）
- **影响**: S1 implementation agent 可能发现无法实现 process-backed capsule 对同步 HTTP 路径的迁移，导致整个 S2 无法推进，work unit 目标不成立
- **建议改法和验证点**:
  1. Plan 必须在 S1 前对三条主要生产工具路径做 picklability / process-migration 可行性快速评估（可以在 plan 中附一个检查清单，不需要完整代码）
  2. 为 `requests.Session` 路径明确 fallback：是迁移到 `httpx.AsyncClient`（已有 SEC downloader 先例），还是保留 thread path + socket close interrupt handle
  3. 如果所有路径都无法迁移到 process-backed，plan 必须提供备选 interrupt 策略（如 adapter-level socket close），并说明为何备选策略可达 production-grade
  4. S1 stop condition 应补充：如果超过 N 条生产路径无法迁移，整个 work unit 应回到 design gate，而非仅标记为 "dedicated follow-up issue"
- **修复风险**: 中。需要在 plan 中增加工具路径可行性分析，但不需要完整实现。
- **严重程度**: 高

---

### F3 — Non-blocking — Bounded close timeout value and configuration unspecified

- **位置**: Section 7.7 "Lane token / active worker cleanup" (line 259), Section 8 Slice S1 "Exact allowed changes" (line 308)
- **问题类型**: 不可直接实施
- **当前写法**: "若 worker stream close 本身卡住，必须 bounded close 并记录 diagnostic；不得无限期阻塞 lane token release。"（line 259）；"Add bounded close behavior for worker stream cleanup; log diagnostic on close timeout."（line 308）
- **反例/失败场景**: implementation agent 需要选择 bounded close 的超时值。如果选择与 `tool_execution_timeout_seconds` 相同的值，可能在工具执行 timeout 之上再叠加等待；如果选择太短，可能过早放弃正常 close 的 worker。plan 没有给出超时值的选取原则或与现有 deadline 的关系。
- **为什么有问题**: bounded close timeout 是一个新的 time budget，虽然 plan 正确地说它不是"第二套 cancel timeout"（它用于 cleanup 而非 cancel），但它仍然是一个新的等待预算。如果取值不当，可能在实际效果上延长用户等待时间。plan 应说明取值原则（例如：固定 small grace period like 2-5 秒，或 derived from remaining tool deadline）以避免 implementation agent 选择不当。
- **直接证据**: plan line 259 "必须 bounded close"，line 308 "log diagnostic on close timeout"——均未指定 timeout 值或取值原则
- **影响**: implementation agent 可能选择过长的 bounded close timeout，使用户在 cancel 后仍需等待，削弱 interrupt 体感
- **建议改法和验证点**: Plan 应明确 bounded close timeout 的取值原则（建议：固定短 grace period 如 3 秒，独立于 tool_execution_timeout_seconds，并说明为什么这个值不会实质性延长用户等待）。验证点：cancel 后 lane token release 的 wall-clock 时间应 ≤ tool_execution_timeout_seconds + bounded_close_grace。
- **修复风险**: 低。只需在 plan 中补充取值原则。
- **严重程度**: 中

---

### F4 — Non-blocking — Slice 3 new-input-progress test fixture unspecified

- **位置**: Section 8 Slice S3 "Expected assertions" (line 497-500), Section 9 "Expected assertion categories" (line 534-540)
- **问题类型**: 测试缺口
- **当前写法**: "Run B 同 Session 后续输入能获得 dispatch lane 并产生 terminal"（line 266）；"public Esc/cancel smoke：Esc 触发 cancel，用户可继续输入，新 Run 可推进"（line 535）
- **反例/失败场景**: 要证明 Run B 能推进，必须先让 Run A 的 worker 在 cancel 时处于**真正阻塞**状态（而非 cooperative async 工具在下一个 token check 就返回）。如果测试使用 cooperative fixture，cancel 后 worker 立即返回，stream 自然结束，finally 自然执行——这不证明 interrupt capsule 和 worker cleanup 机制对 non-cooperative blocking 有效。plan 的 Slice 3 没有说明如何构建 non-cooperative blocking fixture 用于 public smoke。
- **为什么有问题**: Slice 3 的 public smoke 如果只使用 cooperative tools，会通过但无法证明 WU-TOOLS-CANCEL-01 的核心价值——对 non-cooperative blocking I/O 的 interrupt。这造成验证矩阵的盲区：Slice 1 用 fixture 证明了 interrupt 机制，Slice 3 的 public smoke 却可能在 cooperative 路径上"虚假通过"。
- **直接证据**: plan line 534-540 的 assertion categories 包含 "non-cooperative blocking fixture" 但将其放在 Slice 1 的 focused tests（line 347），而 Slice 3 的 public smoke assertions（line 497-500）没有提及 non-cooperative blocking fixture
- **影响**: public smoke 可能遗漏 non-cooperative blocking + cancel → new input progress 的关键用户场景
- **建议改法和验证点**: Slice 3 必须包含至少一个 public smoke case：使用 non-cooperative blocking fixture tool，Esc cancel 后同 Session 新 Run 能推进。如果 public CLI smoke 在非 TTY CI 中无法真实按 Esc，至少 Host public lifecycle smoke 应覆盖此场景。
- **修复风险**: 低。只需在 Slice 3 验证矩阵中增加一行 non-cooperative blocking + new input progress 的要求。
- **严重程度**: 中

---

### F5 — Non-blocking — `dayu.contracts` modification scope ambiguity

- **位置**: Section 5 "Affected Files / Modules Estimate" Runtime / contracts (line 133-134)
- **问题类型**: 架构边界
- **当前写法**: "可能新增 `dayu.contracts` 中的 typed declaration 字段，表达 tool execution mode / interrupt capability。只有当 Host 需要从 ToolDefinition 读取 provider 声明时才新增；不得使用 `extra payload` 或 magic tag。"
- **反例/失败场景**: `dayu.contracts` 是 Engine、Host、Tools 共享的公共契约层。新增 typed declaration 字段是跨层契约变更。plan 的"可能"措辞意味着 implementation agent 需要自行判断是否需要，但 agent 可能：
  1. 在不需要时添加字段（过度设计）
  2. 在需要时不添加字段（使用 magic tag 变通）
  3. 添加字段但未同步更新 Engine design doc（因为 plan 说"默认不修改 Engine public contract"）
- **为什么有问题**: `dayu.contracts` 修改是 public contract change，应有明确的判定标准，不能留给 implementation agent "可能需要也可能不需要"。如果不需要，应明确说明为什么 ToolDefinition 不需要新字段（例如：capsule 是 ToolRuntime internal，tool declaration 不变）。如果需要，应明确新字段的语义和范围。
- **直接证据**: plan line 133-134 使用"可能"措辞；Section 3 "Engine design alignment" line 62-68 说"当前 plan 判定不需要"扩展 Engine public contract，但没有对 `dayu.contracts` 做同等判定
- **影响**: implementation agent 可能在公共契约层引入不必要的字段，或遗漏必要的声明
- **建议改法和验证点**: Plan 应在 Section 6 "Contract / Schema / State-machine / Public Interface Changes" 中明确裁决 `dayu.contracts` 是否需要新增字段。当前证据显示：capsule 是 ToolRuntime internal contract，tool declaration 不变——建议明确写"不新增 `dayu.contracts` 字段"，除非 S1 implementation 发现 tool provider 必须在声明中表达 interrupt capability。
- **修复风险**: 低。只需在 Section 6 中增加一行明确裁决。
- **严重程度**: 低

---

### F6 — Non-blocking — Cooperative async path regression risk not addressed in validation matrix

- **位置**: Section 8 Slice S1 "Exact allowed changes" (line 306), Section 9 "Implementation Validation Matrix" (line 512-523)
- **问题类型**: 测试缺口
- **当前写法**: "Keep default cooperative async callable path for pure async tools."（line 306）
- **反例/失败场景**: 引入 capsule 后，`_dispatch_tool_call_with_bounds` 需要区分 "capsule path" 和 "cooperative async path"。如果 capsule integration 改变了现有 cooperative async callable 的执行路径（例如包装了额外的 await/race），可能导致：
  1. 现有纯 async 工具的性能退化
  2. 取消行为变化（原来 token check 在 callable 内部，现在 capsule 在外部也 check）
  3. 异常传播路径变化
  plan 的验证矩阵（Section 9）没有包含 "existing cooperative async tools continue to work correctly" 的回归测试类别。
- **为什么有问题**: 项目中有大量纯 async 工具（不经过 `asyncio.to_thread`）。如果 capsule 集成不当改变了它们的行为，现有测试可能捕获不到（因为现有测试假设当前的 `_dispatch_tool_call_with_bounds` 行为）。
- **直接证据**: plan line 306，验证矩阵 line 512-540 未提及 cooperative async path regression
- **影响**: 引入 capsule 后可能导致现有纯 async 工具行为回归，测试不覆盖
- **建议改法和验证点**: S1 validation matrix 应增加：现有 cooperative async tools 在 capsule 集成后行为不变（相同 input → 相同 output，相同 cancel → 相同 cancelled outcome）。由于 S1 只改 ToolRuntime/dispatch/local_proxy，不涉及具体工具文件，该验证可通过 existing `test_toolruntime_executor.py` 覆盖。
- **修复风险**: 低。不需要新增测试文件，只需在 validation matrix 中增加该验证类别。
- **严重程度**: 低

---

## Special Lens Review

### Architecture Boundary Review

**Verdict: Pass.** Plan correctly preserves:
- Host → Engine dependency direction (no reverse dependency)
- Engine contract unchanged (`BatchToolExecutionContext` fields preserved)
- ToolRuntime owns execution governance, Engine only does bounded handshake
- No provider-specific code in Host core (capsule is typed generic boundary)
- `dayu.runtime` helper constraint (no Host/Engine/Service/UI/Fins imports)

One note: the plan's "可能新增 `dayu.contracts` 字段" (F5) is the only architectural boundary ambiguity.

### Best-Practice Review

**Verdict: Pass with note.** Plan correctly:
- Prioritizes existing accept barrier / late rejection over "kill guarantees correctness"
- Escalates cooperative cancel → terminate → kill with bounded grace
- Distinguishes runtime diagnostic from business fact
- Does not use kill success as correctness precondition

Note: The bounded close timeout (F3) should follow the existing project pattern of explicit typed configuration rather than a magic number, consistent with how `tool_execution_timeout_seconds` is explicitly configured in `AgentPolicy`.

### Optimal-Solution Review

**Verdict: Pass.** The capsule abstraction is the right level:
- Does NOT build a generic sandbox platform (correctly scoped to current need)
- Does NOT add durable schema (correctly uses existing accept/ingest barriers)
- Does NOT add a second timeout (correctly derives from existing deadline)
- The 3-slice split (boundary → migration → smoke) is more efficient than a per-module split

Alternative considered: making every tool async-native (replacing `requests` with `httpx`, removing `asyncio.to_thread`). This would be a larger refactor with higher risk. The plan's approach of wrapping existing execution in an interruptible capsule is more surgical and has lower regression risk.

### Overengineering Review

**Verdict: Pass.** Plan explicitly avoids:
- New durable schema / EventLog event types
- Second cancel timeout
- Generic sandbox platform
- Provider capability registry
- Universal tool execution mode DSL

Section 13 "Why This Is Not Over-designed" is self-aware and accurate.

### Overcoupling Review

**Verdict: Pass.** Plan correctly separates:
- Capsule execution ownership (ToolRuntime) from cancel terminal truth (Host watchdog)
- Interrupt mechanism (runtime) from stale quarantine (accept barrier + ingest)
- Provider-specific abort (adapter) from generic interrupt boundary (capsule)

No cross-layer coupling found.

---

## Slice Review

### Slice S1: Interrupt capsule + local worker cleanup

- **语义闭环**: ✅ — 建立了 capsule 边界 + worker cleanup 闭环，可用 test fixture 独立验证
- **依赖顺序**: ✅ — 无前置 slice 依赖，是 S2/S3 的基础
- **失败/回滚风险**: ⚠️ — 如果 process-backed capsule 对多数生产路径不可行（F2），S1 虽能通过 fixture 验证但无法支撑 S2
- **验证矩阵**: ⚠️ — 缺少 cooperative async path regression（F6）
- **Allowed files**: ✅ — 范围合理，集中在 Host + runtime
- **Stop conditions**: ✅ — 有明确的 durable schema / public contract 触发停止条件

### Slice S2: Production tool/provider migration

- **语义闭环**: ✅ — 三条生产工具路径各自形成可验证的迁移闭环
- **依赖顺序**: ⚠️ — 强依赖 S1 capsule contract 稳定性（S1 的 capsule 接口变更会导致 S2 重做），plan 未明确此依赖风险
- **失败/回滚风险**: ⚠️ — 如果 doc/fins/web 中某条路径无法迁移（F2 的延续），该工具可能被标记为 "非 production-grade"，影响 #87 closeout
- **验证矩阵**: ✅ — 每条工具路径都有对应的 test file，覆盖 blocking fixture cancel 和 cancelled outcome
- **Allowed files**: ✅ — 范围合理，集中在 tools + fins + web
- **Stop conditions**: ✅ — "若 production tool 无法 interruptible 且不改架构，转为 dedicated issue"

### Slice S3: Public Esc/cancel smoke + stale quarantine + docs

- **语义闭环**: ✅ — 覆盖 public UX, stale quarantine, docs sync 三个收口
- **依赖顺序**: ✅ — 依赖 S1/S2 完成
- **失败/回滚风险**: ⚠️ — public smoke 的 non-cooperative blocking fixture 未明确（F4）
- **验证矩阵**: ⚠️ — 缺少 non-cooperative blocking + new input progress 的 public smoke case（F4）
- **Allowed files**: ✅ — 范围合理，集中在 tests + docs
- **Stop conditions**: ✅ — "若 public smoke 显示 Host 仍等待旧 worker lane，返回 S1"

### Slice Count Assessment

3 slices 符合控制文档 Slice 切分原则：
- 中型跨 ToolRuntime / dispatch / tools / tests work，3 slices 在 budget 内（中型上限 3-5）
- 每个 slice 都是可验证行为闭环
- 不是按模块机械拆分：S1 横跨 ToolRuntime + dispatch + local_proxy，S2 横跨 doc + fins + web
- 如果按"Host / Engine / tools / tests"机械拆分会是 4+ slices，当前按语义闭环拆分的 3-slice 结构更优

---

## Review Focus Checklist

| # | Focus Area | Verdict | Notes |
|---|---|---|---|
| 1 | 消费已完成 WU | ✅ Pass | 正确引用 WU-LIFE-03/04, WU-WAIT-03 作为前置，不重做 |
| 2 | 抓住 root cause | ✅ Pass | 正确识别 ToolRuntime/worker execution boundary 缺少 interruptible capsule |
| 3 | 支撑 Esc 后新输入推进 | ⚠️ F4 | 验证矩阵缺少 non-cooperative blocking + new input progress public smoke |
| 4 | lane token / active worker cleanup 一等验收 | ✅ Pass | Section 7.7 + S1 invariants 包含；F1 指出 on_cancel 机制待明确 |
| 5 | Stale quarantine 依赖 accept/ingest barrier | ✅ Pass | 正确依赖现有 barrier，不依赖 kill 一定成功 |
| 6 | 不新增第二套 cancel timeout | ✅ Pass | 明确禁止，所有 deadline 来自 tool_execution_timeout_seconds |
| 7 | 不硬编码 provider kill API | ✅ Pass | Capsule 提供 typed generic boundary |
| 8 | Durable schema/EventLog/Engine contract 更新 | ✅ Pass | 正确判定不需要；accept barrier 和 ingest 已覆盖 |
| 9 | 3 slices 符合切分原则 | ✅ Pass | 语义闭环，非机械拆分 |
| 10 | Tests/validation 覆盖 | ⚠️ F4, F6 | Non-cooperative blocking public smoke 和 cooperative path regression 待补 |

---

## Open Questions

无 blocking open question。所有 open question 已列为 findings 或 residual risks。

---

## Residual Risks / Uncovered Areas

| ID | Risk | Suggested Tracking |
|---|---|---|
| R1 | 部分 tool callable 不可 picklable，无法进入 process-backed capsule | 已在 plan Risk R1 中，owner S1 implementation |
| R2 | `asyncio.to_thread` 取消后底层线程继续运行 | 已在 plan Risk R2 中，owner S2 implementation |
| R3 | Worker stream close 释放 lane 与 run_cancelled 之间的 race | 已在 plan Risk R3 中，owner S1 tests |
| R4 | Hard kill diagnostic 进入 LLM-facing tool result | 已在 plan Risk R4 中，owner S1/S2 implementation |
| R5 | Public smoke 在非 TTY CI 中无法真实按 Esc | 已在 plan Risk R5 中，owner S3 tests |
| RR-DS-01 | `requests.Session` 全局共享实例不可 picklable，无法进入 process-backed capsule | 建议在 S2 plan 或 #87 closeout 中追踪 |
| RR-DS-02 | Bounded close timeout 取值未定，可能影响 interrupt 体感 | 建议在 S1 implementation 前裁决 |

---

## Verdict

**Verdict: pass-with-findings**

- **Blocking findings**: 2 (F1, F2)
- **Non-blocking notes**: 4 (F3, F4, F5, F6)
- **F1** (`on_cancel` mechanism unspecified) 和 **F2** (process-backed capsule feasibility not assessed) 必须在 accepted plan commit 前修复。它们不影响 plan 的整体方向正确性，但如果不明确，implementation agent 可能在 Slice 1 做出错误的设计裁决。
- **F3-F6** 建议在 plan fix 中一并处理，但不阻塞 accepted plan commit。

### What the plan gets right

1. Root cause 定位准确：问题不在按键入口或 Host terminal truth，而在 ToolRuntime 缺少对 blocking I/O 的 interrupt 能力
2. Architecture boundary 正确：不修改 Engine contract，不新增 durable schema，不硬编码 provider kill API
3. 消费已完成 WU 而非重做：正确依赖 WU-LIFE-03/04 和 WU-WAIT-03
4. Stale quarantine 依赖 accept/ingest barrier 而非 kill 成功——这是正确的 correctness 基础
5. 3-slice 结构合理：语义闭环、非机械拆分、有明确的 stop conditions
6. 不做过度设计：Section 13 自我约束准确

---

## Artifact Path

`docs/reviews/wu-tools-cancel-01-plan-review-ds.md`
