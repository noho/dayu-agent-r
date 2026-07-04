# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan Re-Review — AgentDS

## Artifact

- **Reviewer**: AgentDS (re-review)
- **Plan under re-review**: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- **Fix report**: `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-fix-codex.md`
- **Prior reviews**:
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-mimo.md`

## Re-Review Scope

只检查 accepted findings 是否在 fixed plan 中正确关闭。不重新做全量 plan review。

---

## Findings

### F01 — DS F01 / MiMo 交叉确认 — CLOSED ✓

**原问题**：`ProcessBackedToolTarget.__call__() -> ToolExecutionOutcome` 允许 `ToolAwaitingOutcome`，与 process-backed 语义冲突。

**Fix 证据**：
- Plan L107：`ProcessBackedToolTarget.__call__() -> JsonValue`
- Plan L111-114：JSON 信封合法形态仅为 `{"status": "completed", "value": JsonValue}` 或 `{"status": "failed", "error_type": str, "message": str}`，明确"子进程不得返回 awaiting / cancelled 语义；等待、取消和超时只能由 Host / Engine 治理层产生"

**判定**：类型已收窄到 `JsonValue`，不再允许子进程产出 `ToolAwaitingOutcome`、`ToolCancelledOutcome`。closed。

---

### F02 — DS F02 / MiMo 交叉确认 — CLOSED ✓

**原问题**：Process target factory 接收完整 `BatchToolExecutionContext`，无类型级 guard 防止捕获不可序列化 `CancellationToken`。

**Fix 证据**：
- Plan L76-93：新增 `ProcessBackedToolContext` frozen dataclass，仅包含 `run_id`、`session_id`、`iteration_id`、`timeout_seconds`、`correlation_id` 五个标量字段
- Plan L121-126：`build_process_target(call: ToolCallRequest, context: ProcessBackedToolContext) -> ProcessBackedToolTarget`
- Plan L129-130：docstring 明确"不包含 cancellation_token、lock、runtime、repository、session 或 Host internals"

**判定**：factory 签名已改为接收专用 `ProcessBackedToolContext`，类型系统可拦截对 `cancellation_token` 的误用。closed。

---

### F03 — DS F03 + MiMo M01/M02 — CLOSED ✓

**原问题**：`ProcessBackedToolTarget` 返回值类型与 S1 `InterruptibleProcessHandle` 的 `JsonValue` 契约不一致，且 plan 原 L56 "允许扩展"措辞与层中立定位矛盾，缺少适配层设计。

**Fix 证据**：
- Plan L56-57：明确"`dayu.runtime.interruptible_process` 必须保持当前层中立 `JsonValue` 契约；不得扩展为 `JsonValue | ToolExecutionOutcome`"
- Plan L57-58：明确 Host capsule 解析 JSON 信封并映射为 tool outcome，父进程独占映射 cancel / timeout
- Plan L197-198：`ProcessBackedToolExecutionCapsule` 继续使用 S1 `InterruptibleProcessTarget.__call__() -> JsonValue`，Host capsule 解析 JSON 信封
- 原"允许扩展"措辞已完全删除，替换为明确的方案选择（方案 C）

**判定**：选择方案 C，保持 runtime 层中立，Host capsule 负责 JSON 信封 → tool outcome 映射。M01 适配层问题因 `ProcessBackedToolTarget` 返回 `JsonValue` 而自然消失（与 `InterruptibleProcessTarget` 签名一致）。closed。

---

### F04 — DS F04 / MiMo 交叉引用 — CLOSED ✓

**原问题**：S2A slice 范围过大，contract + runtime + Host + test 四层联动。

**Fix 证据**：
- Plan L315-321：S2A1: contract / declaration / digest（仅 contracts + runtime 层）
- Plan L323-328：S2A2: Host factory wiring（依赖 S2A1，但可做 focused Host 层 review）
- 各有独立 stop condition

**判定**：S2A 已拆分为 S2A1/S2A2，fail-fast 由各自 stop condition 保证。closed。

---

### F05 — DS F05 / MiMo 交叉引用 — CLOSED ✓

**原问题**：Provider lock 语义在 process-backed 模式下未定义。

**Fix 证据**：
- Plan L283-284：明确"process-backed 路径默认绕过父进程 provider lock；子进程内重新创建 processor / runtime / session，依赖进程隔离而不是父进程共享 lock"
- Plan L284-285：stop condition："若某工具仍必须依赖父进程 provider lock 保护共享状态，说明它不满足当前 process-backed 入口条件，必须停止该 slice 并回到设计裁决"
- Plan L407：Residual Risks 已记录此取舍

**判定**：provider lock 语义已明确，process-backed 绕过 lock，子进程自行重建资源；不满足条件的工具 fail closed。closed。

---

### F06 — DS F06 — CLOSED ✓

**原问题**：`ThreadBackedToolExecutionCapability` 是空 dataclass，仅靠 review 防止生产误用，类型系统不参与。

**Fix 证据**：
- Plan L148-159：`ThreadBackedToolExecutionCapability` 新增字段 `production_safe_non_cooperative_cancel: Literal[False] = False`
- Plan L155-157：docstring 明确"让声明和测试能证明 thread_backed 不能作为非协作 blocking 生产 closeout 证据"
- Plan L389-390：stop condition 覆盖 thread_backed 误用

**判定**：类型系统已参与防御（`Literal[False]` 不可覆盖），配合 stop condition 和 residual risk 记录。closed。

---

### F07 — DS F07 / MiMo 交叉引用 — CLOSED ✓

**原问题**：直接构造 `ToolDefinition` 的站点未完全枚举（遗漏 `download_tools.py`、`upload_tools.py`、`preprocess_tools.py`）。

**Fix 证据**：
- Plan L189：明确要求 `rg -n "ToolDefinition\\(" dayu tests` 扫描全量构造站点并逐个裁决
- Plan L189-190：生产站点列表覆盖 decorator、doc_tools.py、download_tools.py、upload_tools.py、preprocess_tools.py、host/tool_runtime.py framework fetch_more
- Plan L228-230：修改范围已列入 download_tools.py、upload_tools.py、preprocess_tools.py

**判定**：直接构造站点已完全枚举，且有 rg 扫描作为实现验证手段。closed。

---

### F08 — DS F08 / MiMo 交叉引用 — CLOSED ✓

**原问题**：Fins process target 子进程内重建 `DefaultFinsRuntime` 的可行性未充分验证。

**Fix 证据**：
- Plan L296-297：新增 focused pre-check："在 spawned child 中用真实临时 workspace 调用 `DefaultFinsRuntime.create(workspace_root)` 并执行一条只读查询，验证不依赖父进程 singleton、不可序列化 repository 或写入型缓存"
- Plan L392-393：stop condition："Fins read 子进程无法通过 `DefaultFinsRuntime.create(workspace_root)` spawned-child pre-check，或需要绕过 `dayu.fins.storage` / 跨进程序列化 repository/runtime：停止"
- Plan L403-404：Residual Risks 记录

**判定**：可行性验证已作为前置 pre-check 写入 S2C 和 stop condition。closed。

---

### F09 — DS F09 — CLOSED ✓

**原问题**：`_tool_definition_json_value` digest 新增 capability 字段的具体 JSON shape 未定义。

**Fix 证据**：
- Plan L185-188：digest 中 execution 字段的稳定 JSON shape 固定为：
  - `async_direct`: `{"mode": "async_direct", "request_abort_capable": true | false}`
  - `thread_backed`: `{"mode": "thread_backed", "production_safe_non_cooperative_cancel": false}`
  - `process_backed`: `{"mode": "process_backed"}`

**判定**：三种 capability 的 digest JSON shape 已精确定义。closed。

---

### F10 — DS F10 — CLOSED ✓

**原问题**：Web `async_direct` 替代路径的 `request_abort_capable` 验证标准不够具体。

**Fix 证据**：
- Plan L306-308：可接受验证标准具体化为"fake / instrumented async client 的 `aclose()` 或 response close 被调用、stream 被退出、无 unclosed-resource warning，并证明 cancelled task 不再持有连接池资源"
- Plan L393-394：stop condition 已覆盖

**判定**：验证标准已具体化到可操作的检查项（aclose 调用、stream 退出、无 resource warning、连接池释放）。closed。

---

### F11 — DS F11 — CLOSED ✓

**原问题**：Plan 原 L56 "允许扩展"措辞与推荐方案混淆。

**Fix 证据**：
- Plan L56-57：原"允许扩展"已完全删除，替换为"必须保持当前层中立 `JsonValue` 契约；不得扩展为 `JsonValue | ToolExecutionOutcome`"
- 全文不再包含"允许扩展 `interruptible_process`"等模棱两可的表述

**判定**：措辞已从"允许"收敛为明确禁止扩展，方案选择已固定为方案 C。closed。

---

### M03 — MiMo — CLOSED ✓

**原问题**：`ToolCancelledOutcome.reason="timeout"` 在 process-backed 语义下的归属未明确。

**Fix 证据**：
- Plan L282："timeout 归属完全在父进程 capsule，子进程内部不得再引入第二套 timeout outcome"
- Plan L113-114：子进程只允许 completed / failed 信封

**判定**：timeout 归属已明确为父进程独占，子进程不自报 timeout。closed。

---

### Pickle round-trip — DS + MiMo 交叉引用 — CLOSED ✓

**原问题**：S2A 缺少 pickle round-trip 验证。

**Fix 证据**：
- Plan L320：S2A1 包含"pickle round-trip 测试"
- Plan L387：stop condition："`ProcessBackedToolTarget`、`ProcessBackedToolContext` 或 JSON 信封不能通过 multiprocessing pickle round-trip：停止"
- Plan L356（验证矩阵）已列入

**判定**：pickle round-trip 作为测试项和 stop condition 写入 plan。closed。

---

## Verdict

**PASS**

全部 accepted findings（DS F01-F11、MiMo M01-M03、pickle round-trip 交叉引用项）已在 fixed plan 中正确关闭：

| Finding | 状态 |
|---------|------|
| DS F01 — ProcessBackedToolTarget 返回过宽 | CLOSED ✓ |
| DS F02 — BatchToolExecutionContext 无可序列化 guard | CLOSED ✓ |
| DS F03 — JsonValue 契约冲突 | CLOSED ✓ |
| DS F04 — S2A 范围过大 | CLOSED ✓ |
| DS F05 — Provider lock 语义缺失 | CLOSED ✓ |
| DS F06 — thread_backed guard 仅靠 review | CLOSED ✓ |
| DS F07 — 直接构造站点未枚举 | CLOSED ✓ |
| DS F08 — Fins 子进程可行性未验证 | CLOSED ✓ |
| DS F09 — Digest JSON shape 未定义 | CLOSED ✓ |
| DS F10 — Web async close 验证标准不具体 | CLOSED ✓ |
| DS F11 — "允许扩展"措辞混淆 | CLOSED ✓ |
| MiMo M01 — 适配层设计缺失 | CLOSED ✓ (因方案 C 自然消解) |
| MiMo M02 — L56 内部矛盾 | CLOSED ✓ |
| MiMo M03 — timeout 归属未明确 | CLOSED ✓ |
| Pickle round-trip 交叉引用 | CLOSED ✓ |

无新增 finding。plan 可以进入下一 gate。
