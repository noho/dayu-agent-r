# P1-P7 Design / Code Divergence Review

## Scope

- Mode: design-code divergence review
- Reviewer: codex
- Branch: `fix/host-p1-p7-awaiting-production-wiring`
- Baseline design truth: `git show 1245aeefeeb182a2da833c8577d701a6a71b7065:docs/host/design.md`
- Reference control doc: `docs/host/implementation-control.md`
- Output file: `docs/reviews/p1-p7-design-code-divergence-review-from-1245base-codex-20260516.md`
- Included scope: `dayu/host`, Host-used `dayu/runtime`, Host-related tests, `docs/host` phase/control docs
- Excluded scope: Engine internals except import-boundary / Host call boundary evidence; full projection / audit / recovery implementation that is explicitly later-phase non-goal
- Parallel review coverage: 无

Verdict: **FAIL**

本轮发现 1 个 High、1 个 Medium。没有 Blocking。High 级问题是 baseline design 明确要求 `fetch_more` cursor / `scope_token` 进入 messages 或 EventLog 后必须可由 Host-governed durable descriptor 恢复，但当前实现和 Phase 6 plan 明确选择内存态 cursor，不满足 1245base 设计真源。

## Findings

### COD-001-未修复-High-`fetch_more` cursor 进入 EventLog 后只有内存真源，违反 baseline durable descriptor 要求

- **入口/函数**: `ToolRuntimeExecutor` 普通工具执行后应用 `TruncationManager.apply_truncation()`，LLM 随后用普通 `fetch_more` 工具补读。
- **文件(行号)**: `dayu/host/tool_runtime.py:1232`, `dayu/host/tool_runtime.py:1263`, `dayu/host/tool_runtime.py:1301`, `dayu/host/tool_runtime.py:1333`, `dayu/host/tool_runtime.py:1358`, `dayu/host/tool_runtime.py:1418`, `dayu/host/tool_runtime.py:3125`, `dayu/host/tool_runtime.py:3415`
- **输入场景**: 工具返回值被截断，LLM-facing result 含 `fetch_more.cursor` / `scope_token`；该工具 fact 通过 Host accept barrier 写入 EventLog；之后 Host/ToolRuntime 进程重启、Attempt LOST 后重建、resume/steer/replay 后模型继续使用该 cursor。
- **实际分支**: `TruncationManager` 在 `_store_cursor()` 中生成 cursor 与 scope token，只写入 `self._cursors` 内存 dict；`TOOL_RESULT_ACCEPTED` payload 的 `truncation` 只记录 `cursor_hint`，没有 durable descriptor、artifact ref、scope binding 或剩余内容 ref。
- **预期行为**: 1245base design §19 明确：`cursor` / `scope_token` 进入 messages 或 EventLog 后，必须可恢复到足以完成后续 `fetch_more` 校验与读取的 durable descriptor，不能只存在于远端 ToolRuntime 进程内存；跨 Host restart、Attempt `LOST`、resume、steer 或 replay 后必须依赖 Host attempt snapshot / Host-governed descriptor / artifact ref 恢复读取权限。基线证据：`docs/host/design.md@1245base` 行 1583-1587、1607-1612。
- **实际行为**: 当前实现的类 docstring 直接说明“不写 durable cursor 表，不承诺跨进程、跨 restart、跨 recovery 或 replay 可继续补读”（`dayu/host/tool_runtime.py:1232-1237`）；cursor 存储为 `self._cursors: dict[...]`（`1263`），`fetch_more()` 只从该 dict 读（`1358`），`_store_cursor()` 只写该 dict（`1418`）。EventLog payload 只保存 `_truncation_json()` 的 `cursor_hint`（`3125`, `3415-3430`）。
- **直接证据**: `ToolTruncationFact` 只有 `applied/strategy/original_digest/truncated_digest/cursor_hint`（`dayu/host/tool_runtime.py:271-285`），缺少 baseline 要求的 handle metadata、scope binding、artifact ref、digest、offset/path、expiry/access policy durable descriptor。
- **影响**: `fetch_more` 在同一内存态 Attempt 内可用，但 Host 已 durable accepted 的工具结果无法解释或恢复其补读能力。进程重启、remote ToolRuntime 丢失、resume/steer/replay 后，模型看见的 cursor 只能得到 `missing_cursor`，破坏 Host durable facts 可恢复、EventLog 可解释和工具事实审计链。Phase 6 plan 第 29、50、221 行把 durable cursor 明确列为 non-goal；这可以解释实现来源，但不能覆盖本 review 指定的 1245base design 真源。
- **建议改法和验证点**: 建议当前 fix。二选一：实现 Host-governed durable cursor descriptor / artifact ref，并在 Host accept 工具 fact 时持久化 descriptor；或在 durable descriptor 未落地前不要把可跨 EventLog/messages 使用的 `fetch_more` capability 暴露为生产能力。验证应增加“截断结果 accepted 后重建新的 ToolRuntime/Host handle，再用 EventLog/payload descriptor 恢复 fetch_more”的集成测试；测试不能只复用同一个 `ToolRuntimeHandle`。
- **修复风险（低/中/高）**: 中。需要修改 truncation fact schema / payload descriptor 或 artifact 存取边界，并补充恢复测试。
- **严重程度（低/中/高/严重）**: 高
- **是否建议当前 fix**: 是

### COD-002-未修复-Medium-`resolve_wait` 幂等 digest 包含 `observed_at`，同一 outcome 的真实重试会被误判冲突

- **入口/函数**: `resolve_wait(host, wait_id, request)` -> `DefaultHostResolveWaitService._resolve_in_transaction()` -> `_wait_resolution_digest()`
- **文件(行号)**: `dayu/host/waiting.py:619`, `dayu/host/waiting.py:682`, `dayu/host/waiting.py:685`, `dayu/host/waiting.py:1085`, `dayu/host/waiting.py:1093`; test gap at `tests/host/test_resolve_wait_command.py:124`
- **输入场景**: poller / callback / manual caller 已用 `(wait_id, idempotency_key)` 成功提交一次 completed outcome；网络或调用方超时后以同一 idempotency key、同一工具结果重试，但重新生成 `ResolveWaitRequest.observed_at`。
- **实际分支**: `_wait_resolution_digest()` 把 `observed_at.isoformat()` 纳入 semantic digest；第二次请求命中同一 `(wait_id, idempotency_key)` idempotency record 后，`existing.semantic_input_digest != resolution_digest`，抛 `IDEMPOTENCY_CONFLICT`。
- **预期行为**: 1245base design §20 固定 `resolve_wait` 幂等范围是 `(wait_id, idempotency_key)`，并要求“同一幂等键 + 同一 outcome 重试”返回既有 RunSnapshot / Attempt refs，不追加第二份 canonical fact，不创建第二个 Attempt；同一 key + 不同 outcome 才返回 conflict。基线证据：`docs/host/design.md@1245base` 行 1704-1707。
- **实际行为**: 同一 outcome 但不同 `observed_at` 被视为不同 semantic digest。`ResolveWaitRequest` 本身把 `observed_at` 建模为结果观测时间（`dayu/host/api.py:1533-1550`），但 baseline 幂等冲突条件绑定的是 outcome 差异，不是 retry 时间戳差异。
- **直接证据**: `_wait_resolution_digest()` 输入包含 `"observed_at": request.observed_at.isoformat()`（`dayu/host/waiting.py:1093-1099`）；已有 idempotency 记录时直接比较 digest，不做“同 outcome 新 observed_at”的重放判定（`dayu/host/waiting.py:682-692`）。现有重放测试复用同一个 request 对象（`tests/host/test_resolve_wait_command.py:132-137`），没有覆盖同 key、同 outcome、不同 `observed_at`。
- **影响**: benign duplicate delivery 或 retry 可能变成用户可见 `IDEMPOTENCY_CONFLICT`。这不改写 durable truth，但会削弱 poll/callback/manual 入口的幂等语义，让调用方无法稳定重试同一结果。
- **建议改法和验证点**: 建议当前 fix。将 conflict digest 限定为 wait id、idempotency key、source 和 typed outcome 事实；`observed_at` 应作为首次成功提交的事件 payload / audit 字段保留，不应让同一结果重试冲突。新增测试：同一 key + 同一 outcome + 不同 observed_at 返回既有 snapshot 且不追加事件；同一 key + 不同 outcome 仍 conflict。
- **修复风险（低/中/高）**: 低到中。需要明确 digest ownership，并确保 EventLog payload 仍保留首次 observed_at。
- **严重程度（低/中/高/严重）**: 中
- **是否建议当前 fix**: 是

## Rejected / Deferred Observations

- **Rejected: EngineEvent `tool_awaiting` / `run_suspended` 未成为 waiting owner。** 当前 `engine_ingest` 将这类事件作为 diagnostic / confirmation，等待 canonical owner 是 ToolRuntime Host accept path；这符合 baseline §13.4、§20。未作为偏离报告。
- **Rejected: P7 awaiting production wiring 已接入真实 scheduler。** `HostDispatchScheduler` 在 tool-enabled dispatch 构造 `ToolRuntimeBuildRequest` 时注入 `DefaultHostToolFactAcceptPort`、`DefaultHostToolAwaitingAcceptPort` 与 `wait_adapter_registry`（`dayu/host/dispatch.py:710-740`），并有 scheduler-level integration coverage（`tests/host/test_phase7_waiting_integration.py:690-695`）。不重复报告此前已修复的 production wiring finding。
- **Rejected: `cancel_run` / `cancel_session_runs` 的 WAITING cancel 已有生产路径。** 虽然 `dayu/host/command.py:368-423` docstring 仍称 WAITING 由 Phase 7 负责，但 admission 实际在 `RunStatus.WAITING` 分支调用 `_cancel_waiting()`（`dayu/host/admission.py:968-973`），并有 `tests/host/test_wait_cancel_late_result.py:37-92` 覆盖。该 docstring stale 属 Low 文档清理，不构成本轮设计偏离 finding。
- **Deferred: audit / projection / full recovery scan。** 1245base 设计覆盖这些终态能力，但 P1-P7 control/phase docs明确未实现完整 audit projection、outbox/projection 和 orphan recovery scan；本轮只记录 residual risk，不作为当前 P1-P7 必须完成的偏离。

## Residual Risks

- 当前 review 未完整逐行覆盖全部 70k+ Host 新增代码；重点抽查了 public API、dispatch scheduler、ToolRuntime/truncation/fetch_more、waiting/resolve_wait、cancel waiting、EventLog accept path、runtime/import boundary 与相关 tests。
- Phase 6 plan 与 1245base design 在 durable cursor 语义上存在明确冲突；若 controller 认为 plan 后续裁决可覆盖 1245base，则需要先更新 review 的设计真源口径，否则应按 COD-001 修复。
- `resolve_wait` 的 callback authentication / replay defense 是 Phase 7 non-goal；产品化 callback endpoint 前仍需单独 review。

## Validation

- `pwd && git branch --show-current && git status --short && mkdir -p docs/reviews && date +%Y%m%d-%H%M`：通过；branch 为 `fix/host-p1-p7-awaiting-production-wiring`，timestamp `20260516-1454`，工作树进入 review 前无 dirty 输出。
- `git show 1245aeefeeb182a2da833c8577d701a6a71b7065:docs/host/design.md`：已读取 baseline design truth。
- `rg --files dayu/host dayu/runtime tests docs/host docs/reviews`：已建立 Host/runtime/test/doc review map。
- `rg -n "dayu\\.(engine|service|ui|fins|host)" dayu/runtime dayu/host`：未发现 `dayu.runtime` 反向 import Host/Engine/Service/UI/Fins；Host 只沿 Host -> Engine 方向调用 Engine contracts / LocalProxy。
- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_phase6_toolruntime_integration.py -q`：20 passed。
- `source .venv/bin/activate && pyright`：0 errors, 0 warnings, 0 informations。
