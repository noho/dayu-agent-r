# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan Review — AgentMiMo

## Artifact

- **Reviewer**: AgentMiMo (adversarial plan review)
- **Plan under review**: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- **Cross-reference**: `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-ds.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- **Code references**: `dayu/runtime/interruptible_process.py`, `dayu/contracts/tool_outcome.py`, `dayu/contracts/tool_call.py`, `dayu/contracts/cancellation.py`
- **Current baseline**: commit `29003541`

---

## DS F01/F02/F03 交叉判定

### DS F01 — `ProcessBackedToolTarget` 返回 `ToolExecutionOutcome` 允许 `ToolAwaitingOutcome` — **成立**

**判定：成立，且 DS 的分析比 plan 更精确。**

直接证据链：

- `dayu/contracts/tool_outcome.py:137-141`：`ToolExecutionOutcome` 是 `ToolCompletedOutcome | ToolFailedOutcome | ToolAwaitingOutcome | ToolCancelledOutcome` 四元联合。
- `docs/engine/design.md` Section 12：`ToolAwaitingOutcome` 的语义是"工具进入长事务等待"，Engine 收到后产出 `run_suspended` 并结束本次 run。子进程无法表达"我进入等待，请宿主稍后恢复我"——子进程没有 Host wait_adapter_registry / wait_activation_registry 的接入点。
- `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md` Section 7.4：`process_backed` 的定位是"非协作 blocking I/O 可隔离子进程执行"，子进程应返回 completed / failed 或被父进程 kill。

plan 的 `-> ToolExecutionOutcome` 签名在类型层面允许了四种 outcome，但子进程在语义上只能合法返回两种（completed / failed）。`ToolAwaitingOutcome` 携带 `ToolAwaitSpec`，其消费者是 Engine 的 suspend/resume 协议；子进程产出它会导致父进程 capsule 面对一个无意义的 awaiting 结果。

`ToolCancelledOutcome` 的情况更微妙：reason="host_cancelled" 不应由子进程产出（子进程不知道 Host 是否取消了 Run），reason="approval_denied" 也不应由子进程产出（审批在 Host 层）。但 reason="timeout" 理论上可由子进程内部超时触发——不过 plan 明确说"父进程 cancel / timeout 后 terminate / kill process"，意味着超时治理在父进程，子进程不需要自报 timeout。因此 `ToolCancelledOutcome` 同样不应出现在 process target 的合法返回中。

DS 的建议改法（定义 `ProcessBackedToolResult = ToolCompletedOutcome | ToolFailedOutcome`）是正确的方向。但需注意：`ToolCompletedOutcome` 包含 `ToolResultSuccess`，`ToolFailedOutcome` 包含 `ToolResultFailure`，两者都是 frozen dataclass——它们能否被 multiprocessing pickle？需要在 S2A 中验证。

### DS F02 — `BatchToolExecutionContext` 含不可序列化 `CancellationToken` — **成立**

**判定：成立，但影响评估需修正。**

直接证据：

- `dayu/contracts/tool_call.py:110-137`：`BatchToolExecutionContext` 包含 `cancellation_token: CancellationToken`。
- `dayu/contracts/cancellation.py:20-48`：`CancellationToken` 是 `Protocol`（`@runtime_checkable`），定义了 `is_cancelled()` / `cancel_reason()` / `requested_at()` 三个方法。Protocol 对象本身不可 pickle。
- plan 第 107 行 docstring："实现只能读取可序列化字段，例如 session_id、run_id、iteration_id、timeout_seconds 与 arguments"——这是文档约束，不是类型约束。

DS 的核心论点成立：factory 实现者可能在 `build_process_target` 内读取 `context.cancellation_token` 并闭包捕获到 target 中，导致 multiprocessing spawn pickling 在运行时失败。

但影响评估需修正：plan 的 docstring 已经明确列出了可读取字段（`session_id`、`run_id`、`iteration_id`、`timeout_seconds`、`arguments`），没有列出 `cancellation_token`。这意味着 plan 的意图是正确的，只是类型系统没有强制执行。DS 建议定义 `ProcessBackedToolContext` dataclass 是更安全的做法，但 plan 的 docstring 至少为 code review 提供了检查依据。

建议：采用 DS 的 F02 建议——定义专用 `ProcessBackedToolContext` dataclass，只包含可序列化字段，在 Host ToolRuntime 中从 `BatchToolExecutionContext` 投影后再调用 factory。这符合编码硬约束"显式参数必须有 typed field"。

### DS F03 — `ProcessBackedToolTarget` 与 S1 `InterruptibleProcessHandle` 的 `JsonValue` 契约冲突 — **成立，且 plan 自身存在内部矛盾**

**判定：成立。plan 第 56 行的"允许扩展"建议与 F03 推荐方案直接矛盾。**

直接证据：

- `dayu/runtime/interruptible_process.py:22-35`：`InterruptibleProcessTarget.__call__() -> JsonValue`。
- `dayu/runtime/interruptible_process.py:46`：`InterruptibleProcessCompleted.value: JsonValue`。
- plan 第 86-91 行：`ProcessBackedToolTarget.__call__() -> ToolExecutionOutcome`。
- plan 第 56 行："若 process target 需要返回 `ToolExecutionOutcome` 而不是裸 `JsonValue`，允许扩展 `dayu.runtime.interruptible_process` 的返回联合到 `JsonValue | ToolExecutionOutcome`"。

这里 plan 有一个内部矛盾：

- plan 第 54-55 行说 `dayu.runtime` "不应放"工具执行语义。
- plan 第 56 行又说"允许扩展 `interruptible_process` 的返回联合到 `JsonValue | ToolExecutionOutcome`"。

`ToolExecutionOutcome` 是 `dayu.contracts` 中的工具执行语义类型。把它放入 `dayu.runtime.interruptible_process` 的返回类型中，会让层中立的 process helper 携带工具语义，违反 plan 自身对 runtime 的定位。

DS 推荐方案 (C)：`ProcessBackedToolTarget.__call__() -> JsonValue`，让 capsule 负责映射。这是正确的。但需补充：如果子进程需要返回结构化失败（带 error / message / hint），可以在 `JsonValue` 中使用 JSON 信封约定（如 `{"__tool_error__": true, "error": "...", "message": "..."}`），由 capsule 解析。这比修改 `interruptible_process` 的类型更轻量。

关键问题：plan 需要在 S2A 前明确选择方案 (A)、(B) 还是 (C)。当前 plan 没有明确选择，只是说"允许扩展"，这会导致 S2A 实现者面临未预期的设计决策。

---

## DS 遗漏的 Material Findings

### M01 — 中 — 缺少 ProcessBackedToolTarget → InterruptibleProcessTarget 适配层设计

- **Plan 章节**: Contract / API Shape 草案；Host ToolRuntime 变更草案
- **直接证据**:
  - `dayu/runtime/interruptible_process.py:22-35`：S1 capsule 接收 `InterruptibleProcessTarget`（runtime 层 Protocol）
  - plan 第 86-91 行：plan 定义 `ProcessBackedToolTarget`（contracts 层 Protocol）
  - plan 第 161 行："`process_backed`：调用 `target_factory.build_process_target(call, context)`，创建 `ProcessBackedToolExecutionCapsule`"
  - `dayu/host/tool_runtime.py:1615-1620`：S1 `ProcessBackedToolExecutionCapsule.__init__(target: InterruptibleProcessTarget)` 接收的是 runtime 层 target
- **分析**: plan 引入了 contracts 层的 `ProcessBackedToolTarget`，但没有说明 Host capsule 如何使用它。当前 S1 capsule 接收 `InterruptibleProcessTarget`（返回 `JsonValue`），而 plan 的 `ProcessBackedToolTarget` 返回 `ToolExecutionOutcome`。Host capsule 需要一个适配层：
  - (a) 创建一个新的 capsule 类直接接收 `ProcessBackedToolTarget`，内部绕过 `InterruptibleProcessTarget`
  - (b) 创建一个 adapter 把 `ProcessBackedToolTarget` 包装为 `InterruptibleProcessTarget`（需要解决返回类型不匹配）
  - (c) 修改 `InterruptibleProcessTarget` 支持 `ToolExecutionOutcome`（DS F03 已拒绝）

  plan 没有明确选择，也没有给出 adapter 设计。这是 S2A 的阻塞项。
- **影响**: S2A 实现者需要在实现中做 ad-hoc 选择，增加返工风险。如果选择 (a)，可能需要重写 capsule；如果选择 (b)，需要处理返回类型映射；如果选择 (c)，违反 runtime 层中立性。
- **建议改法**: 在 plan 的 Host ToolRuntime 变更草案中明确 adapter 设计。推荐方案 (b)：在 Host capsule 层创建 adapter，把 `ProcessBackedToolTarget` 包装为 `InterruptibleProcessTarget`，adapter 内部把 `ToolExecutionOutcome` 序列化为 JSON 信封，再由 capsule 解析回 `ToolExecutionOutcome`。或者更简单地——如果采用 DS F03 建议让 `ProcessBackedToolTarget` 返回 `JsonValue`，adapter 就不需要了。

### M02 — 中 — plan 第 56 行"允许扩展 interruptible_process 返回联合"与 DS F03 推荐直接矛盾，plan 未取舍

- **Plan 章节**: 方案选择 → `dayu.runtime` 取舍
- **直接证据**:
  - plan 第 56 行："若 process target 需要返回 `ToolExecutionOutcome` 而不是裸 `JsonValue`，允许扩展 `dayu.runtime.interruptible_process` 的返回联合到 `JsonValue | ToolExecutionOutcome`"
  - DS F03 推荐方案 (C)：保持 `InterruptibleProcessTarget.__call__() -> JsonValue`，在 capsule 层做映射
  - `docs/host/design.md` Section 3：`dayu.runtime` "只能承载层中立基础能力，不能承载业务语义"
- **分析**: plan 的"允许扩展"措辞是一种回避——它没有明确推荐，也没有分析取舍。但 DS F03 的分析是正确的：`ToolExecutionOutcome` 是工具执行语义，放入 `interruptible_process` 会让层中立的 runtime helper 携带工具语义。plan 需要明确选择：要么接受 runtime 层中立性退化（方案 B），要么保持层中立性并在 Host capsule 层做映射（方案 C）。
- **影响**: 如果 plan 不明确选择，S2A 实现者可能直接修改 `InterruptibleProcessCompleted.value` 的类型，导致后续非工具场景的 interruptible process 消费者也需要理解 `ToolExecutionOutcome` 分支。
- **建议改法**: 在 plan 中明确选择 DS F03 推荐的方案 (C)：保持 `interruptible_process` 返回 `JsonValue`，在 Host capsule 层做映射。删除 plan 第 56 行的"允许扩展"措辞，替换为明确的取舍说明。

### M03 — 低 — `ToolCancelledOutcome.reason="timeout"` 在 process-backed 语义下的归属未明确

- **Plan 章节**: Process-backed Entrypoint 形状
- **直接证据**:
  - `dayu/contracts/tool_outcome.py:48`：`TOOL_CANCELLED_REASON_TIMEOUT = "timeout"`
  - plan 第 241 行："父进程 cancel / timeout 后 terminate / kill process，并返回 Host governed cancelled / timeout outcome"
  - plan 第 242 行："late child result 不得进入 accept barrier"
- **分析**: plan 说"父进程 cancel / timeout 后 terminate / kill process"，但没有明确父进程返回的 timeout outcome 是 `ToolCancelledOutcome(reason="timeout")` 还是 `ToolFailedOutcome`。如果父进程返回 `ToolCancelledOutcome(reason="timeout")`，这是合理的（工具被超时取消）。但如果子进程内部也想报 timeout（如子进程内部有独立的超时逻辑），就会与父进程的 timeout 治理冲突。plan 应明确：子进程不自报 timeout，timeout 治理完全在父进程。
- **影响**: 低。实现者通常会正确处理，但 plan 明确说明可以避免歧义。
- **建议改法**: 在 plan 的 Process-backed Entrypoint 形状中增加一条："子进程不自报 timeout 或 host_cancelled；timeout 和取消治理完全由父进程 capsule 负责。"

---

## 逐维度 Review 结论

### 1. `ToolDefinition.execution` 放在 `dayu.contracts` 是否是最小正确契约？

**结论：方向正确，但 ProcessBackedToolTarget/Factory Protocol 有三处类型不自洽（DS F01, F02, F03），且缺少适配层设计（M01）。**

- execution capability 放在 contracts 层是正确的：tool provider → ToolsDiscovery → Host ToolRuntime 三者都需要消费它，contracts 是唯一共享依赖。
- `ProcessBackedToolTarget` 和 `ProcessBackedToolTargetFactory` 的签名需要修正：返回类型应收窄（F01），context 类型应专用化（F02），与 S1 的类型关系应明确（F03, M01）。
- 新增类型数量（1 enum + 2 Protocol + 3 dataclass）合理，不构成 contract 膨胀。

### 2. 分层边界是否清楚？

**结论：大体清楚，但 `interruptible_process` 返回类型扩展存在层中立性退化风险（M02），provider lock 语义缺失（DS F05）。**

- contracts / runtime / Host / tools / Fins / Engine 边界在 plan 中有明确声明。
- `dayu.runtime.interruptible_process` 的返回类型扩展（plan 第 56 行）与 runtime 层中立性定位矛盾（M02）。
- Engine 边界保持正确：plan 明确 Engine 不消费 capability。
- provider lock 在 process-backed 模式下的语义未定义（DS F05）。

### 3. ProcessBackedToolTarget/Factory 草案是否自洽？

**结论：类型、pickling、context 使用、Outcome 返回存在三处不自洽（DS F01, F02, F03），且缺少适配层设计（M01）。**

- 类型不自洽：`-> ToolExecutionOutcome` 允许 `ToolAwaitingOutcome`（F01）
- Pickling / context 不自洽：`BatchToolExecutionContext` 包含不可序列化的 `CancellationToken`（F02）
- Outcome 返回不自洽：与 S1 `InterruptibleProcessHandle` 的 `JsonValue` 契约不一致（F03）
- 适配层缺失：plan 引入 contracts 层 target 但未说明 Host capsule 如何消费它（M01）

### 4. ToolBundle digest / ToolsDiscovery / direct ToolDefinition construction 是否有遗漏？

**结论：digest shape 未指定（DS F09），直接构造站点未完全枚举（DS F07）。**

- Digest 变更方向正确，但 JSON shape 需要在 plan 中给出示例。
- 直接构造 `ToolDefinition(...)` 的站点有遗漏：`download_tools.py`、`upload_tools.py`、`preprocess_tools.py` 未列入修改范围。

### 5. Doc/Fins/Web process-backed slices 是否足够具体、可测试，是否保留 Fins storage 边界？

**结论：Doc 和 Web 足够具体；Fins 有可行性未验证项（DS F08）；storage 边界明确保留；provider lock 语义缺失（DS F05）。**

- Doc slice：input shape 具体，测试边界覆盖完整。
- Fins slice：storage 边界正确保留，但 `DefaultFinsRuntime.create` 子进程可行性未验证。
- Web slice：两种策略都有测试约束。
- 共性问题：provider lock 在 process-backed 模式下未讨论。

### 6. Implementation sequencing 风险

**结论：S2A 范围过大（DS F04）是主要风险；适配层设计缺失（M01）增加 S2A 返工风险。**

- S2A 同时改 contracts + runtime + Host + tests，且包含未明确的适配层设计。
- 建议按 DS F04 拆分 S2A，或至少在 plan 中明确 S2A 的 fail-fast 策略。

### 7. Tests / README / design 验证矩阵是否足够？

**结论：基本足够，但 process target pickle 验证、ToolExecutionOutcome dataclass pickle 验证和 Fins 子进程可行性验证缺失。**

- 缺失：S2A 应有 `ProcessBackedToolTarget` 的 pickle round-trip 测试。
- 缺失：S2A 应有 `ToolCompletedOutcome` / `ToolFailedOutcome` 的 pickle round-trip 验证（process target 返回这些类型时需要序列化）。
- 缺失：S2C 应有 `DefaultFinsRuntime.create` 子进程可行性验证。

---

## Verdict

**NEEDS_PLAN_FIX**

Plan 的核心方向（在 `dayu.contracts` 增加 typed execution capability、Host 从 `ToolDefinition.execution` 选择 capsule、Engine 不消费 capability）是正确的，且被 S2 review 的直接证据充分支持。

但 plan 在 process-backed 的类型契约设计上有三处不自洽（DS F01, F02, F03），加上适配层设计缺失（M01）和 `interruptible_process` 返回类型扩展的内部矛盾（M02），不修复会导致 S2A 实现中遇到未预期的设计决策，增加返工风险。

**建议修复优先级**：

1. **必须在 plan accept 前修复**：
   - DS F01：收窄 `ProcessBackedToolTarget` 返回类型为 `ToolCompletedOutcome | ToolFailedOutcome`
   - DS F02：定义 `ProcessBackedToolContext` dataclass 替代直接传入 `BatchToolExecutionContext`
   - DS F03 + M01 + M02：明确选择方案 (C)（`ProcessBackedToolTarget` 返回 `JsonValue`，capsule 层做映射），或方案 (A)（Host capsule 直接接收 `ProcessBackedToolTarget`，绕过 `InterruptibleProcessTarget`）；删除 plan 第 56 行的"允许扩展"措辞
2. **建议在 plan accept 前修复**：
   - DS F04：S2A 拆分或明确 fail-fast 策略
   - DS F07：补全直接构造站点
3. **可在 S2 实现中验证后修复**：DS F05（provider lock）、DS F06（thread_backed guard）、DS F08（Fins 可行性）、DS F09（digest shape）、DS F10（Web 验证标准）、DS F11（runtime 扩展策略）、M03（timeout 归属）

修复后 plan 可以 `PASS`，不需要 `REDESIGN`。
