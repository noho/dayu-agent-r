# WU-TOOLS-CANCEL-01 Slice S2 Code Review — AgentDS

## Scope

- Mode: current changes (unstaged diff against HEAD on `phase/wu-tools-cancel-01`)
- Branch: `phase/wu-tools-cancel-01`
- Base: S1 accepted commit `eda4be1a`（只复核 S1 之后的未提交 diff）
- Output file: `docs/reviews/wu-tools-cancel-01-slice2-code-review-ds.md`
- Included scope:
  - `dayu/tools/web/web_tools.py` — timeout_budget propagation
  - `dayu/tools/web/web_playwright_backend.py` — Playwright fail-closed
  - `tests/tools/web/test_web_tools_provider.py` — budget + fail-closed tests
  - `docs/host/issues-implementation-control.md` — gate 状态更新
  - AgentCodex S2 report: `docs/reviews/wu-tools-cancel-01-slice2-implementation-codex.md`
- Excluded scope:
  - S1 committed code（`dayu/host/tool_runtime.py`, `dayu/host/dispatch.py`, `dayu/host/local_proxy.py`, `dayu/runtime/interruptible_process.py` 及相关 tests）— 已通过 S1 review/rereview
  - Doc/Fins production tool files — AgentCodex 未修改，不在此 slice diff 内
- Parallel review coverage: 无（单 reviewer 全量走读）

## Findings

### F01-未修复-严重-AgentCodex 正确识别 design stop condition，S2 不可标记为完成或 #87 closeout

- **入口/函数**: S2 per-tool-family migration assessment → production dispatch path
- **文件(行号)**:
  - `dayu/contracts/tool_declaration.py:87-107` — `ToolDefinition` 无 execution mode/capability 字段
  - `dayu/contracts/tool_call.py:111-137` — `BatchToolExecutionContext` 无 execution mode/capability 字段
  - `dayu/host/tool_runtime.py:1488-1509` — `DefaultToolExecutionCapsuleFactory.create_capsule()` 永远返回 `AsyncDirectToolExecutionCapsule`
  - `dayu/host/dispatch.py:3310-3313` — dispatch 中 `ToolExecutionMode` 仅用于 NO_TOOL_REPLAY / NO_TOOL_DISABLED，不用于选择 process/thread/async 执行模式
  - `dayu/tools/web/web_tools.py:1173-1174,1270-1271` — search/fetch 仍用 `asyncio.to_thread(...)` 包装同步业务调用
  - `dayu/tools/doc_tools.py:702-733` — Doc tools 仍用 `asyncio.to_thread(business_call, token)`（S1 后未变）
  - `dayu/fins/tools/fins_tools.py:770-778` — Fins tools 仍用 `asyncio.to_thread(business_call, cancellation_token)`（S1 后未变）
- **输入场景**: 任何需要将 Doc/Fins/Web sync 生产工具路径迁移到 `process_backed` 可中断执行的尝试
- **实际分支**: 当前生产路径上 capsule factory 永远创建 `AsyncDirectToolExecutionCapsule`；工具 callable 内部自行通过 `asyncio.to_thread(...)` 把同步阻塞调用丢进线程池。cancel 时只能取消 wrapper awaitable，底层同步 HTTP/文件 I/O 继续运行
- **预期行为**: 按 Plan Section 7.4.1，Doc/Fins/Web sync 生产路径需迁移到 `process_backed` 或 request-abort-capable `async_direct`；工具声明需通过 typed execution capability 表达执行模式
- **实际行为**: S1 capsule 基础设施（`ProcessBackedToolExecutionCapsule`、`ThreadBackedToolExecutionCapsule`、`ToolExecutionMode`）已存在于 `dayu/host/tool_runtime.py`，但生产 dispatch 路径无法根据工具类型选择正确的 capsule，因为 `ToolDefinition` 和 `BatchToolExecutionContext` 均无 execution mode 字段
- **直接证据**:
  1. `ToolDefinition` frozen dataclass 字段为 `name, schema, callable, truncate, display, tags`（`tool_declaration.py:102-107`），无 execution mode
  2. `DefaultToolExecutionCapsuleFactory.create_capsule()` 无条件返回 `AsyncDirectToolExecutionCapsule`（`tool_runtime.py:1505-1509`）
  3. dispatch.py 中 `ToolExecutionMode` 的唯一生产引用在 `_build_snapshot_tool_execution_mode()`，仅区分 `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED`（`dispatch.py:3310-3313`）
  4. Doc/Fins/Web 工具 callable 内部自行调用 `asyncio.to_thread(...)`，对 capsule 而言是不可见的实现细节
  5. 使 Doc/Fins/Web sync 路径成为 `process_backed` 需要在某处声明工具的 execution capability，但当前唯一可行的声明位置是 `ToolDefinition`（contracts 层）或 `BatchToolExecutionContext`（contracts 层），两者均为 `dayu.contracts` 公共契约
- **影响**: Doc/Fins/Web sync 三个生产工具族在当前架构下无法实现 production-grade non-cooperative cancel。取消后底层同步 I/O 可能继续运行并产生外部副作用。issue #87 不可关闭
- **建议改法和验证点**:
  1. 确认本 slice 不标记为完成
  2. 返回 design gate，在 `ToolDefinition` 或等价 typed 声明中增加 execution capability 字段，明确表达工具执行模式
  3. 更新 `docs/host/design.md` / `docs/engine/design.md` 记录该 contract 变更
  4. 更新 capsule factory 根据工具声明的 execution mode 选择正确 capsule
  5. 逐工具族迁移到 `process_backed` 或 request-abort-capable `async_direct`
- **修复风险（中）**: contracts 变更需要同步更新所有现有 `ToolDefinition` 构造点、provider 装配、tests fixture；但已有 S1 typed enum 和 capsule 实现可复用
- **严重程度（严重）**: 命中 Plan Section 7.4.1 全局 stop condition；S2 不可标记完成；#87 不可 closeout

### F02-未修复-中-Web search/fetch timeout_budget 传递正确但仍是 cooperative-only，不构成 production-grade interrupt

- **入口/函数**: `_call_search_web` / `_call_fetch_web_page` → `asyncio.to_thread(...)` → 同步 business
- **文件(行号)**:
  - `dayu/tools/web/web_tools.py:1173-1174` — `asyncio.to_thread(_search_web_business, ..., timeout_budget=context.timeout_seconds, ...)`
  - `dayu/tools/web/web_tools.py:1270-1271` — `asyncio.to_thread(_fetch_web_page_business, ..., timeout_budget=context.timeout_seconds, ...)`
- **输入场景**: Host 取消后，`asyncio.to_thread` wrapper awaitable 被取消，但底层 `requests.Session.get()` 阻塞在 socket read 上
- **实际分支**: capsule（`AsyncDirectToolExecutionCapsule`）cancel → `asyncio.to_thread` task cancelled → 底层 thread 中的 `requests` 调用无法被中断，继续阻塞直到 socket timeout 或 OS-level socket close
- **预期行为**: Plan Section 7.2/7.3 要求 `requests / synchronous HTTP path` 必须迁移到 `process_backed` capsule 或在 adapter 内提供可验证的 socket/session abort hook；仅关闭 thread wrapper 不满足生产级取消
- **实际行为**: `timeout_budget` 传递改善了 HTTP 请求的 deadline 感知（请求会在 deadline 前超时），但 cancel 仍只能取消 wrapper awaitable，不能物理中断正在进行的 socket read。这是 cooperative-only 行为
- **直接证据**: `web_tools.py:1173` 的 `asyncio.to_thread(...)` 调用不提供 socket/session abort hook；`_search_web_business` / `_fetch_web_page_business` 内部使用共享 `requests.Session`，未被任何 interrupt adapter 包裹
- **影响**: 取消后底层 HTTP 请求可能继续占用 socket 和 thread pool 资源；如果请求在 deadline 内完成，late result 需靠 accept/ingest barrier 拒绝（barrier 存在，但资源未被释放）
- **建议改法和验证点**: 此问题是 F01 的衍生问题，随 F01 的 contract 修复一并解决。当前 `timeout_budget` 传递本身是正确的局部改进
- **修复风险（低）**: 当前改动不引入回归；timeout_budget 传递是纯增量安全改动
- **严重程度（中）**: 改动本身安全，但不可声称 production-grade；需在 review artifact 和 control doc 中明确标注为 partial/cooperative-only

### F03-已修复-低-Docstring 更新准确反映 timeout_budget 语义变化

- **入口/函数**: `_search_web_business` / `_fetch_web_page_business` docstring
- **文件(行号)**:
  - `dayu/tools/web/web_tools.py:1326` — `:param timeout_budget: 单次工具调用预算，用于约束下游 HTTP 请求预算。`
  - `dayu/tools/web/web_tools.py:1510` — 同上
- **输入场景**: 开发者阅读这些函数的 docstring
- **实际分支**: N/A（文档）
- **预期行为**: docstring 应准确描述当前行为
- **实际行为**: docstring 已从 `当前保持旧行为传 None` 更新为 `用于约束下游 HTTP 请求预算`，准确反映当前实现
- **直接证据**: diff 中 `web_tools.py:1326,1510` 的 docstring 变更
- **影响**: 无功能影响，纯文档准确性
- **建议改法和验证点**: 无需修改
- **修复风险（无）**: 纯文档变更
- **严重程度（低）**: 文档改进，非 defect

### F04-未修复-低-Playwright fail-closed 在 unpicklable 场景下丢弃了旧路径的 Warning 日志语义

- **入口/函数**: `_fetch_and_convert_with_playwright` unpicklable 分支
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1104-1111`
- **输入场景**: `playwright_sync_worker` 不可 pickle，且 `playwright_channel` 非空（即 Playwright 已安装但 worker 刚好不可序列化）
- **实际分支**: `_is_picklable_worker` 返回 `False` → 记录 Warning → 返回 `{"ok": False, "availability": "unprocessable", "reason": "playwright_worker_not_picklable"}`
- **预期行为**: 旧代码在 unpicklable 时会走到同进程 fallback，fallback 内部会检查 `_PLAYWRIGHT_INSTALLED` 并可能返回 `playwright_not_installed`。新代码直接返回 `playwright_worker_not_picklable`，调用方 `_try_playwright_fallback` 会将 `reason` 写入 LLM-facing hint
- **实际行为**: `playwright_worker_not_picklable` 作为 `reason` 进入 `_build_fetch_fallback_message`（`web_tools.py` 中），最终出现在 LLM-facing hint 文本中。该 reason 值不暴露内部治理标识（无 digest/ref/id），是安全的
- **直接证据**: `web_playwright_backend.py:1108-1110` 的返回值；`web_tools.py` 中 `_try_playwright_fallback` 对 `availability="unprocessable"` 的处理使用 `reason` 构造 hint
- **影响**: LLM-facing hint 中会出现 `playwright_worker_not_picklable` 字样，但这是业务可读的失败原因，不违反 LLM-facing 文本约束
- **建议改法和验证点**: 如果未来需要对 LLM 隐藏 `playwright_worker_not_picklable`，可以在 `_try_playwright_fallback` 中将该 reason 映射为更通用的用户提示。当前可接受
- **修复风险（低）**: 仅影响 hint 文案
- **严重程度（低）**: LLM-facing 文本合规，但可作为后续改进项

## Open Questions

1. **Design gate 后的 contract 方案选择**：execution capability 应放在 `ToolDefinition`（工具声明时确定）还是由 `ToolRuntimeBuildRequest.execution_capsule_factory` 根据 tool name/config 动态选择？前者符合 typed declaration 原则但需要 contracts 变更；后者避免 contracts 变更但接近 "tool-name branch"。Design gate 需裁决。

2. **Doc/Fins process-backed 迁移的 picklability 风险**：AgentCodex 报告指出 Doc tools 的 `business_call` 可能是 closure/partial，Fins tools 的 `FinsReadRuntime` 不可 picklable。这些风险在 Plan Section 7.4.1 已有记录，但 design gate 需要给出具体的重构方案（模块级 entrypoint、子进程内重建 runtime 等）。

3. **S2 的两个 Web 改动是否应作为独立 accepted slice commit？**：`timeout_budget` 传递和 Playwright fail-closed 是两个正确、安全、独立的改进。它们可以被 accepted 为 S2 partial commit，不阻塞 S2 返回 design gate。需要 controller 裁决。

## Residual Risk

1. **Web sync HTTP 路径仍是 cooperative-only**：`asyncio.to_thread(...)` + `requests` 的组合在 cancel 时无法中断底层 socket read。Web search/fetch 的生产级 interrupt 依赖 F01 的 contract 修复。

2. **Doc/Fins 工具的 `asyncio.to_thread(...)` 路径未在此 slice 中触及**：这些路径仍完全依赖 cooperative token + `asyncio.to_thread` task cancel，不提供 production-grade non-cooperative interrupt。AgentCodex 已正确分类为 design-stop，但风险存在于当前生产代码中。

3. **LLM-facing `playwright_worker_not_picklable` 暴露**：当前 hint 文案中包含此 reason，LLM 可能据此做出非预期的工具选择决策。风险低，但值得在后续 slice 中审视 hint 映射。

## Verdict

**PASS_TO_DESIGN_GATE**

### 裁决理由

1. **AgentCodex 的 design stop 判断成立**：Doc、Fins read、Web sync HTTP 三个生产工具族在当前 `ToolDefinition` / `BatchToolExecutionContext` 契约下无法表达 typed execution capability。S1 的 `ProcessBackedToolExecutionCapsule` 存在但无法被生产 dispatch 选中，因为没有任何 typed 声明机制告诉 capsule factory 哪个工具应使用哪种执行模式。这直接命中 Plan Section 7.4.1 全局 stop condition。

2. **Web 两个改动安全且正确**：
   - `timeout_budget=context.timeout_seconds` 传递是正确的局部改进，使 HTTP 请求感知工具 deadline
   - Playwright fail-closed 移除了不安全的同进程 fallback，符合 Plan Section 7.4.1 对 Playwright 的要求
   - 两项改动均通过测试、pyright、git diff --check
   - 不违反 AGENTS.md / LLM-facing / 分层约束

3. **S2 不可标记完成**：Plan 要求的 "production tool families that currently use `asyncio.to_thread(...)` or Playwright process execution are covered by interrupt boundary tests" 未达成。三个工具族中有两个（Doc、Fins）零改动，一个（Web sync HTTP）仅做了 cooperative deadline 改进。

4. **#87 不可 closeout**：Plan Section 7.4.1 全局 stop condition 明确禁止在关键生产路径不能 process-backed / abort-capable 且修复需要 contracts 变更时标记 #87 closeout。

### 建议下一步

1. Controller 裁决是否将 Web 两个改动作为 S2 partial accepted slice commit（两个改动独立安全）
2. 进入 design gate：在 `dayu.contracts` 中为 `ToolDefinition` 增加 typed execution capability 字段
3. 同步更新 `docs/host/design.md` / `docs/engine/design.md` 记录 contract 变更
4. 更新 `DefaultToolExecutionCapsuleFactory` 根据 tool execution capability 选择正确 capsule
5. 逐工具族迁移到 `process_backed` 或 request-abort-capable `async_direct`
6. Design gate 完成后重启 S2 implementation
