# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan Re-Review — AgentMiMo

## Artifact

- **Reviewer**: AgentMiMo (re-review after fix)
- **Plan under review**: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- **Fix report**: `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-fix-codex.md`
- **Prior reviews**:
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-ds.md`
- **Baseline**: commit `29003541`

---

## Accepted Findings Closure Check

### 1. ProcessBackedToolTarget 不再返回过宽 ToolExecutionOutcome — **CLOSED**

- Plan 第 107 行：`__call__() -> JsonValue`，已从 `-> ToolExecutionOutcome` 收窄。
- Plan 第 111-116 行 docstring 明确："合法形态仅为 `{"status": "completed", "value": JsonValue}` 或 `{"status": "failed", "error_type": str, "message": str}`。子进程不得返回 awaiting / cancelled 语义；等待、取消和超时只能由 Host / Engine 治理层产生。"
- Plan 第 282 行 process-backed entrypoint 规则："只允许表达 completed 或 failed。`awaiting`、`cancelled`、`host_cancelled`、approval、timeout 均不由子进程返回。"
- DS F01 与 MiMo F01 均已关闭。`JsonValue` 返回类型不再允许 `ToolAwaitingOutcome` 或 `ToolCancelledOutcome` 进入子进程合法返回集。

### 2. Factory 不再接完整 BatchToolExecutionContext — **CLOSED**

- Plan 第 76-94 行：新增 `ProcessBackedToolContext` frozen dataclass，只含 `run_id`、`session_id`、`iteration_id`、`timeout_seconds`、`correlation_id` 五个可序列化标量字段。
- Plan 第 122-134 行：`ProcessBackedToolTargetFactory.build_process_target(call, context: ProcessBackedToolContext)` 签名已替换。
- Plan 第 78-79 行 docstring："本类型由 Host 从 BatchToolExecutionContext 投影而来，只包含 multiprocessing spawn 可序列化的标量字段。"
- Plan 第 327 行 S2A2 验证："验证 `BatchToolExecutionContext -> ProcessBackedToolContext` 投影不携带 `cancellation_token`"。
- DS F02 已关闭。类型系统层面阻止了 factory 实现者捕获不可序列化字段。

### 3. dayu.runtime.interruptible_process JsonValue 层中立契约 — **CLOSED**

- Plan 第 56 行（原"允许扩展"措辞）已替换为："`dayu.runtime.interruptible_process` 必须保持当前层中立 `JsonValue` 契约；不得扩展为 `JsonValue | ToolExecutionOutcome`。工具语义只允许在 Host capsule 层解释：process target 返回 JSON 信封，Host capsule 将 `completed` / `failed` 信封映射为对应 tool outcome，并由父进程独占映射取消/超时。"
- Plan 第 387 行 stop condition："`dayu.runtime.interruptible_process` 必须改成返回 `ToolExecutionOutcome` 才能完成 S2A1 / S2A2：停止，回到 design gate；当前 plan 已选择 Host capsule JSON 信封映射方案。"
- Plan 第 198 行 Host capsule 变更草案：capsule 解析 JSON 信封并映射为 `ToolCompletedOutcome` / `ToolFailedOutcome`，未知或非 JSON 信封 fail closed。
- DS F03 + MiMo M01 + MiMo M02 均已关闭。原 plan 的内部矛盾（第 54-55 行 runtime 不应放工具语义 vs 第 56 行允许扩展）已消除。适配层问题因 `ProcessBackedToolTarget` 返回 `JsonValue`（与 S1 `InterruptibleProcessTarget` 同类型）而自然消解，无需额外 adapter。

### 4. S2A 拆分为 S2A1/S2A2 — **CLOSED**

- Plan 第 314-322 行：S2A1 定义为 "contract / declaration / digest"，覆盖 capability shape、ToolDefinition/decorator、ToolsDiscovery digest、直接构造站点迁移、JSON 信封/ProcessBackedToolContext/thread_backed guard/digest shape/pickle round-trip 测试。
- Plan 第 324-329 行：S2A2 定义为 "Host factory wiring"，覆盖 declaration-backed capsule factory、Engine import-boundary/projection 测试、BatchToolExecutionContext → ProcessBackedToolContext 投影验证。
- 每个 slice 有独立 stop condition。
- DS F04 已关闭。

### 5. 直接 ToolDefinition 构造站点补全 — **CLOSED**

- Plan 第 189 行："S2A1 implementation 必须用 `rg -n \"ToolDefinition\\(\" dayu tests` 扫描直接构造站点并逐个裁决。生产站点至少包含 `dayu/contracts/tool_declaration.py` decorator、`dayu/tools/doc_tools.py`、`dayu/fins/tools/download_tools.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/tools/preprocess_tools.py`、`dayu/host/tool_runtime.py` framework `fetch_more`；测试 helper 也必须随 contract 迁移。"
- Plan 第 228-230 行精确修改范围已列出 download/upload/preprocess。
- DS F07 已关闭。

### 6. 细节项进入 plan — **CLOSED**

| 细节项 | Plan 位置 | 状态 |
|---|---|---|
| provider lock | 第 284 行："process-backed 路径默认绕过父进程 provider lock；子进程内重新创建 processor / runtime / session，依赖进程隔离而不是父进程共享 lock。" + 第 391 行 stop condition | CLOSED |
| thread_backed guard | 第 157-159 行：`production_safe_non_cooperative_cancel: Literal[False] = False`，frozen 永远 False 的显式 guard 字段。第 344 行 residual risk 与第 390 行 stop condition 配合 | CLOSED |
| Fins pre-check | 第 297 行："S2C 开始前必须先做 focused pre-check：在 spawned child 中用真实临时 workspace 调用 `DefaultFinsRuntime.create(workspace_root)` 并执行一条只读查询，验证不依赖父进程 singleton、不可序列化 repository 或写入型缓存。" + 第 393 行 stop condition | CLOSED |
| digest JSON shape | 第 186-188 行：三种 mode 的稳定 JSON shape 已定义（`async_direct`/`thread_backed`/`process_backed`） | CLOSED |
| Web async close | 第 307 行："可接受验证至少包括 fake / instrumented async client 的 `aclose()` 或 response close 被调用、stream 被退出、无 unclosed-resource warning，并证明 cancelled task 不再持有连接池资源。" + 第 394 行 stop condition | CLOSED |
| timeout 归属 | 第 283 行："子进程内部不得再引入第二套 timeout outcome。" + 第 390 行："子进程 target 试图返回 awaiting / cancelled / timeout / host_cancelled 语义：停止" | CLOSED |
| pickle round-trip | 第 321 行 S2A1："增加 JSON 信封 shape、`ProcessBackedToolContext`、thread_backed guard、digest shape 和 pickle round-trip 测试。" + 第 388 行 stop condition | CLOSED |

DS F05/F06/F08/F09/F10/F11 + MiMo M03 均已关闭。

---

## Fix Quality Assessment

fix 不只做了机械文本替换，而是在三个层面修正了 plan 的设计张力：

1. **类型契约收窄**：`ProcessBackedToolTarget.__call__() -> JsonValue` 消除了 F01/F03 的根源——不需要定义 `ProcessBackedToolResult` 别联合，也不需要 adapter 层。子进程返回 JSON 信封与 S1 `InterruptibleProcessTarget` 同类型，Host capsule 自然复用现有信封解析逻辑。

2. **Context 投影**：`ProcessBackedToolContext` frozen dataclass 用类型系统替代了文档约束，符合编码硬约束"显式参数必须有 typed field"。Host 投影步骤写入 S2A2 验证矩阵，不是只靠 docstring 提示。

3. **slice 拆分 + stop condition 写入 plan 本体**：S2A1/S2A2 各自有独立 stop condition，S2A1 失败不阻塞 Doc/Fins/Web 的纯业务逻辑重构准备。provider lock、thread_backed guard、Fins pre-check、Web async close 等实现期决策被提前写入 plan，减少 S2 实现者面临的未预期设计决策数量。

---

## Verdict

**PASS**

所有 accepted findings 已在 plan 中关闭。fix 消除了原 plan 的三处类型不自洽（DS F01/F02/F03）、内部矛盾（MiMo M01/M02）和实现期歧义（DS F04/F05-F11 + MiMo M03），未引入新的设计张力。plan 可进入 implementation gate。
