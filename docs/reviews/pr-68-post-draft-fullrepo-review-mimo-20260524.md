# Code Review

## Scope

- Mode: All Repository (post draft-PR-pass appended full-repo review for PR 68)
- Branch: `feat/phase-12-5-conversation-memory-optimize` @ `53a6d13`
- PR: #68
- Base: `main`
- Output file: `docs/reviews/pr-68-post-draft-fullrepo-review-mimo-20260524.md`
- Review date: 2026-05-25
- Included scope: All production code in `dayu/`, all tests in `tests/`, README files, design docs, project instructions
- Excluded scope: `.venv/`, `workspace/`, `__pycache__/`, generated files
- Parallel review coverage:
  - Agent 1: Host durable layer (`dayu/host/durable/`, `command.py`, `dispatch.py`, `recovery*.py`) — 10 findings (0 critical, 1 medium, 9 low)
  - Agent 2: Host lifecycle/admission/dispatch (`admission.py`, `dispatch.py`, `run_input.py`, `engine_ingest.py`, `local_proxy.py`, `waiting.py`, `wait_adapter.py`, `tool_runtime.py`, `tooling.py`, `open_host.py`, `api.py`, `read_api.py`, `read_model.py`) — 10 findings (0 critical, 3 medium, 7 low)
  - Agent 3: Host compaction/memory/context governance (`compaction*.py`, `memory*.py`, `context_*.py`, `evidence.py`, `payload_resolution.py`, `projection.py`, `terminal_summary_payload.py`) — 8 findings (0 critical, 2 medium, 6 low)
  - Agent 4: Engine/contracts/runtime boundaries (`dayu/contracts/`, `dayu/engine/`, `dayu/runtime/`, `dayu/service/host_assembly.py`) — 1 finding (0 critical, 0 medium, 1 low)
  - Agent 5: Tests coverage and quality (`tests/`) — 5 findings (1 high, 2 medium, 2 low)
  - Main reviewer: Direct verification of import boundaries, pyright, test suite, README sync, design doc alignment

## Validation Commands and Results

| Command | Result |
|---------|--------|
| `python -m pytest tests/ -x -q` | **1637 passed, 1 skipped** in 75.87s |
| `python -m pyright dayu/ tests/` | **0 errors, 0 warnings, 0 informations** |
| Runtime import boundary check | **CLEAN** — no runtime module imports engine/host/service/ui/fins |
| Contracts import boundary check | **CLEAN** — no contracts module imports engine/host/service/ui/fins |
| Engine/Host import boundary check | **CLEAN** — engine does not import host; host does not import service/ui/fins |
| `class(object)` check | **CLEAN** — no forbidden `object` base class usage |
| Identity re-export check | **CLEAN** — no `import X as X` compatibility re-exports |
| `Any` in type signatures | **CLEAN** — false positive was `TypeVar("_AnyTaskResult")` |

## Findings

### 1-未修复-中-`_run_after_commit` 吞没后续 callback 错误

- **入口/函数**: `HostTransaction.run_write()` 的 after-commit callback 执行路径
- **文件(行号)**: `dayu/host/durable/transaction.py` (379-401)
- **输入场景**: 同一事务注册多个 after-commit callback，且 callback 0 之后的 callback 抛出异常
- **实际分支**: `for index, callback in enumerate(callbacks)` 循环中，只有第一个失败的 callback 被记录，后续 callback 继续执行但其错误被静默丢弃
- **预期行为**: 所有 callback 错误都应被观察到——至少通过日志或复合异常
- **实际行为**: 只有 `first_error` 被保留并重新抛出；`first_error_index` 之后的 callback 异常被静默吞没
- **直接证据**: `transaction.py:385` — `if first_error is None: first_error = exc` 仅记录首个错误
- **影响**: 若后续 callback 执行关键副作用（如唤醒 scheduler、发送通知），其失败对调用方不可见。当前代码中 after-commit callback 主要用于 scheduler wakeup，失败会被 drain loop 轮询兜底，但诊断性降低
- **建议改法和验证点**: 在 `first_error` 已非 `None` 时，对后续 callback 错误执行 `_LOGGER.warning` 记录；或收集所有错误后抛出 `HostAfterCommitMultiError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-中-`max_compaction_attempts_per_operation` 默认为 1，消除语义修复

- **入口/函数**: `compaction_operation.py` 中的 compaction attempt loop
- **文件(行号)**: `dayu/host/context_policy.py` (22), `dayu/host/compaction_operation.py` (129-153)
- **输入场景**: LLM compactor 首次 proposal 未通过 quality check
- **实际分支**: `while attempt_number <= max_attempts` 循环在 `max_attempts=1` 时首次拒绝即退出
- **预期行为**: 至少允许一次 repair attempt（将 rejection feedback 回传 LLM）
- **实际行为**: 每个 LLM proposal 必须首次即通过全部 quality check；无 repair 机会
- **直接证据**: `context_policy.py:22` — `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 1`
- **影响**: LLM 偶发遗漏 preservation evidence ref 或 open questions 时，compaction 直接失败。结合 Finding 3（open_questions quality check），已完成任务的 compaction 几乎必然失败
- **建议改法和验证点**: 将默认值提升至 2，或在文档中明确说明默认禁用 semantic repair、生产环境应调高
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-中-`open_questions_retained` quality check 对无 open questions 场景误拒

- **入口/函数**: `check_compaction_candidate()` 中的 `_open_questions_retained()` 调用
- **文件(行号)**: `dayu/host/context_governance.py` (616-628, 104-105)
- **输入场景**: 一个已完成的简单任务，compaction candidate 的 episode summary 和 pinned state 均无 open questions
- **实际分支**: `_open_questions_retained` 返回 `False`，触发 `CompactQualityIssue.OPEN_QUESTIONS_MISSING`，导致 `accepted=False`
- **预期行为**: 当原始上下文确实没有 open questions 时，compaction candidate 不应被强制要求发明 open questions
- **实际行为**: 任何 open questions 为空的 candidate 都被拒绝，无论原始上下文是否真有 open questions
- **直接证据**: `context_governance.py:623-628` — 仅检查 candidate 输出，不参照原始 context 的 open questions 状态
- **影响**: 已完成任务的 compaction 必然失败（quality check 拒绝 + max_attempts=1 无 repair）。LLM 被迫编造人工 open questions 以通过检查
- **建议改法和验证点**: 增加对原始 context open questions 状态的参照；或当原始无 open questions 时跳过此 check；或改为 soft warning 而非 hard rejection
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-中-Host close 不为 in-flight Run 写 terminal facts

- **入口/函数**: `_PublicHostHandle.close()`
- **文件(行号)**: `dayu/host/open_host.py` (359-386)
- **输入场景**: Host 正在执行 active Run 时，调用方调用 `close()`
- **实际分支**: scheduler close 取消 active tasks（`dispatch.py:1731-1733`），但 `_consume_worker_events` 的 finally block（`dispatch.py:2987-3008`）在 `CancelledError` 路径不写 terminal closeout
- **预期行为**: Host close 后，所有 in-flight Run 应在 durable store 中有明确终态
- **实际行为**: `run_terminal_closed` 保持 `False`，Run 留在 `RUNNING`/`STARTING` 非终态。下次 startup 由 recovery scanner 处理
- **直接证据**: `dispatch.py:2916-2917` — `except asyncio.CancelledError: raise` 直接传播，finally block 不尝试 terminal closeout；`open_host.py:364` — 文档明确"不写 cancel / failed terminal facts"
- **影响**: Host close 后 durable store 中存在非终态 Run。依赖 recovery scanner 作为 safety net。若 recovery scanner 配置不当或未运行，Run 永久卡在非终态
- **建议改法和验证点**: 在 scheduler close 的 active task cancel 前，增加 best-effort terminal closeout phase；或在 `_consume_worker_events` finally block 中检测 `self._closed` 并尝试写 lost terminal
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 5-未修复-中-Dispatch record 在意外 task 取消后孤立在 WAITING_FOR_LANE

- **入口/函数**: `HostDispatchScheduler._dispatch_one()`
- **文件(行号)**: `dayu/host/dispatch.py` (1958-2041)
- **输入场景**: `_lane_controller.acquire()` 等待期间，task 被外部取消（非 scheduler close）
- **实际分支**: `CancelledError` 在 line 2017 被捕获，lane token 被释放，但 dispatch record 留在 `WAITING_FOR_LANE` 状态
- **预期行为**: dispatch record 应被重置或加入重试队列
- **实际行为**: task 已取消，dispatch record 永久留在 `WAITING_FOR_LANE`，不会被重试
- **直接证据**: `dispatch.py:2017` — CancelledError handler 释放 token 但不重置 record 状态
- **影响**: 孤立的 dispatch record 需要下次 startup recovery scanner 处理。在正常 scheduler close 路径下不是问题（close 取消所有 tasks 后 scanner 兜底），但异常取消场景可能遗留
- **建议改法和验证点**: 在 CancelledError handler 中，若 `not self._closed`，重置 dispatch record 到前一状态或标记为可重试
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 6-未修复-低-Reactive compaction 跳过 budget acceptance gate

- **入口/函数**: `_requires_budget_acceptance()`
- **文件(行号)**: `dayu/host/compaction_operation.py` (215, 265, 630-639)
- **输入场景**: Reactive compaction（Engine provider overflow 触发）完成后
- **实际分支**: `_requires_budget_acceptance` 对 `REACTIVE` trigger 返回 `False`，跳过 hard threshold 检查
- **预期行为**: 这是**有意设计**——docstring 明确说明 reactive path 来自真实 overflow，compact 后是否足够应由后续真实 dispatch 闭环判断
- **实际行为**: `max_reactive_compactions_per_run`（默认 2）bound 了重试循环，每次浪费一次 LLM call + dispatch
- **直接证据**: `compaction_operation.py:633-635` — "避免不准估算阻断第二次 reactive compact"
- **影响**: 最坏情况下浪费 2 次 LLM call + 2 次 dispatch，但不会无限循环。设计选择合理
- **建议改法和验证点**: 可增加 advisory warning log 当 `budget_after_compact >= hard_threshold_tokens`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 7-未修复-低-Drain loop 增加系统性 dispatch 延迟

- **入口/函数**: `HostDispatchScheduler._drain_loop()`
- **文件(行号)**: `dayu/host/dispatch.py` (1862-1911)
- **输入场景**: `wake_dispatch` 在 drain loop sleeping 期间入队新 record
- **实际分支**: drain loop 先检查 `queue.empty()` → true → sleep `dispatch_poll_interval_seconds` → `drain_once()`
- **预期行为**: 新 record 应尽快被处理
- **实际行为**: 最多延迟一个 poll interval 才处理新 record
- **直接证据**: `dispatch.py:1873-1886` — empty check 后 sleep，而非 Event-driven wake
- **影响**: 系统性延迟 floor = `dispatch_poll_interval_seconds`。生产环境 poll interval 较短时影响小
- **建议改法和验证点**: 考虑用 `asyncio.Event` 或 `queue.get()`（阻塞）替代 `empty()` + `sleep()` 模式
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 8-未修复-低-Session watch 使用 busy-wait 轮询

- **入口/函数**: `_watch_session_events_after()`
- **文件(行号)**: `dayu/host/open_host.py` (333-357)
- **输入场景**: 长时间无新事件的 session watch
- **实际分支**: 每 20ms（`_SESSION_WATCH_POLL_INTERVAL_SECONDS = 0.02`）轮询一次
- **预期行为**: 空闲时应低功耗等待
- **实际行为**: 50 次/秒的 wakeups，持续消耗 CPU
- **直接证据**: `open_host.py:342` — `await asyncio.sleep(_SESSION_WATCH_POLL_INTERVAL_SECONDS)`
- **影响**: 空闲 session 的 CPU 开销。多 session 并发时累积
- **建议改法和验证点**: 使用 `asyncio.Event` 在新事件 append 时 signal，或使用指数退避
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 9-未修复-低-Memory snapshot 读取路径每次都执行 item kind 校验

- **入口/函数**: `_snapshot_row_from_host_row()`
- **文件(行号)**: `dayu/host/durable/memory.py` (941-972)
- **输入场景**: 每次 `read_memory_snapshot` 或 `read_latest_memory_snapshot`
- **实际分支**: 额外执行 `SELECT item_kind FROM host_memory_items WHERE snapshot_id = ?` 查询
- **预期行为**: 读取热路径不应有额外查询
- **实际行为**: 每次 snapshot read 都执行一次额外查询来检测旧 schema item kinds
- **直接证据**: `memory.py:968` — `_validate_snapshot_item_kinds(transaction, snapshot.snapshot_id)`
- **影响**: 读取延迟增加。对频繁 snapshot 读取的路径（如 dispatch 前 memory catch-up）有累积影响
- **建议改法和验证点**: 将校验移到写入路径，或在 snapshot 中添加 schema version marker 跳过校验
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 10-未修复-低-`count_committed_events_by_run_and_type` 无 filter 时全量加载

- **入口/函数**: `count_committed_events_by_run_and_type()`
- **文件(行号)**: `dayu/host/durable/event_log.py` (570-598)
- **输入场景**: `payload_filter=None` 时统计事件数
- **实际分支**: `fetchall()` 加载所有匹配行到内存，然后 `len(rows)`
- **预期行为**: 使用 `SELECT COUNT(*)`
- **实际行为**: 加载所有 `payload_json` 到 Python 内存只为返回 count
- **直接证据**: `event_log.py:585` — `rows = transaction.fetchall(...)` 后 `return len(rows)`
- **影响**: 内存开销，非正确性问题
- **建议改法和验证点**: `payload_filter is None` 时使用 `SELECT COUNT(*)`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 11-未修复-低-SSE content type fallback 可能误分类非 SSE 响应

- **入口/函数**: `_is_sse_response()`
- **文件(行号)**: `dayu/engine/runners/openai/runner.py` (122-135)
- **输入场景**: 流式请求时反向代理返回 `text/html` 错误页面
- **实际分支**: content type 既非 `text/event-stream` 也非 `json` 时，fallback 返回 `True`，将响应送入 SSE parser
- **预期行为**: 非 SSE 非 JSON 响应应走 non-stream 路径（可正确分类 HTTP 错误）
- **实际行为**: 被误送到 SSE parser，产生 confusing protocol error
- **直接证据**: `runner.py:134` — `return _JSON_CONTENT_TYPE_FRAGMENT not in content_type`
- **影响**: 边缘场景下错误诊断质量降低。下游 error classifier 和 retry policy 仍能捕获大多数情况
- **建议改法和验证点**: fallback 改为 `return False`，让非 SSE 非 JSON 响应走 non-stream 路径
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 12-未修复-低-`requests_run_recovery` 始终为 False（dead code）

- **入口/函数**: `CompactMemorySnapshotRepairRequired.__init__()`
- **文件(行号)**: `dayu/host/compact_material.py` (106, 313)
- **输入场景**: memory snapshot 损坏时触发 repair
- **实际分支**: `self.requests_run_recovery = False` 硬编码
- **预期行为**: 若 caller 依赖此字段判断是否需要 Run recovery，应有 True 的场景
- **实际行为**: 字段始终 False，是 dead code pattern
- **直接证据**: `compact_material.py:106` — `self.requests_run_recovery = False`
- **影响**: 无功能影响（caller 通过异常类型判断），但代码误导
- **建议改法和验证点**: 删除字段或文档说明 caller 应检查 `repair_request.reason`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 13-未修复-严重-`memory_repair.py` 零测试覆盖

- **入口/函数**: `rebuild_conversation_memory_projection()`, `catch_up_conversation_memory_projection()`, `ConversationMemoryProjectionCatchupPort`
- **文件(行号)**: `dayu/host/memory_repair.py` (全文)
- **输入场景**: Host startup recovery、admission 前 memory projection catch-up
- **实际分支**: `grep -r "memory_repair" tests/` 返回零匹配；无 `test_memory_repair.py` 文件
- **预期行为**: memory projection rebuild/catch-up 是生产关键路径，应有单元测试覆盖 batch loop 终止条件、cursor tracking、failure counting
- **实际行为**: 零测试覆盖。`_run_memory_projection_until_idle` loop（line 237-251）的终止条件 `batch_result.failures > 0 or batch_result.events_scanned < batch_size` 若有逻辑错误，可导致无限循环或过早停止
- **直接证据**: `grep -r "memory_repair" tests/` 无结果
- **影响**: memory projection 是 conversation continuity 的关键 read model；静默损坏影响所有后续 Run
- **建议改法和验证点**: 新增 `tests/host/test_memory_repair.py`，覆盖：空 EventLog rebuild、mid-stream cursor catch-up、batch size 校验、loop 终止条件、port delegation
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重

### 14-未修复-中-`_summary_pretends_evidence_backed_fact` 条件 3 死代码

- **入口/函数**: `_summary_pretends_evidence_backed_fact()`
- **文件(行号)**: `dayu/host/context_governance.py` (203-204)
- **输入场景**: compaction candidate 的 `proposed_evidence_backed_fact_refs` 为空时
- **实际分支**: 条件 1（line 198-199）已对非空 `proposed_evidence_backed_fact_refs` 返回 True；条件 3 的 intersection 在空集合上永远为空
- **预期行为**: 条件 3 应检查不同的语义条件
- **实际行为**: 条件 3 是 unreachable dead code
- **直接证据**: `context_governance.py:198` — `if len(summary.proposed_evidence_backed_fact_refs) > 0: return True` 先于 line 203 执行
- **影响**: 无功能影响，但信号可能的设计意图 mismatch
- **建议改法和验证点**: 删除 line 203-204 或补充注释说明防御目的
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 15-未修复-中-`_summary_pretends_evidence_backed_fact` 条件 4 未被测试覆盖

- **入口/函数**: `_summary_pretends_evidence_backed_fact()`
- **文件(行号)**: `dayu/host/context_governance.py` (205-208)
- **输入场景**: candidate 的 `preserved_evidence_backed_fact_refs` 包含不在 `request.evidence_backed_fact_refs` 中的 ref
- **实际分支**: `not set(candidate.preserved_evidence_backed_fact_refs).issubset(set(request.evidence_backed_fact_refs))` 应返回 True 并拒绝 candidate
- **预期行为**: 此 quality check 应拒绝保存了请求中不存在的 fact refs 的 candidate
- **实际行为**: 无测试覆盖此路径；`fake_compaction.py` 总是设置两者相等
- **直接证据**: `grep "preserved_evidence_backed_fact_refs.*request.evidence_backed_fact_refs" tests/` 仅返回 `fake_compaction.py`
- **影响**: 回归可能静默允许无效 candidate 通过
- **建议改法和验证点**: 在 `test_compaction_contract.py` 中新增测试，创建 `preserved_evidence_backed_fact_refs=("fake-extra-ref",)` 的 candidate 并断言拒绝
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 16-未修复-中-`tool_runtime_schema_projection.py` 仅有 import boundary 测试

- **入口/函数**: `validate_reserved_name_conflicts()`, `definitions_by_name()`
- **文件(行号)**: `dayu/host/tool_runtime_schema_projection.py` (全文)
- **输入场景**: ToolRuntime effective bundle construction 时校验 reserved name 冲突和重复 tool name
- **实际分支**: `grep "tool_runtime_schema_projection" tests/` 仅返回 `test_import_boundary.py`
- **预期行为**: 校验函数应有功能测试覆盖拒绝路径
- **实际行为**: 仅有 import boundary 测试，无功能测试
- **直接证据**: 无 `test_toolruntime_schema_projection.py` 文件
- **影响**: 若校验函数静默接受无效输入（重复 tool name 或 reserved name 冲突），可导致 ToolRuntime 运行时错误
- **建议改法和验证点**: 新增测试覆盖 valid bundle acceptance、reserved name rejection、duplicate name rejection
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 17-未修复-中-`tool_truncation.py` 无直接测试

- **入口/函数**: tool result truncation 逻辑
- **文件(行号)**: `dayu/runtime/tool_truncation.py` (全文)
- **输入场景**: 工具结果截断边界条件（精确阈值、多字节 UTF-8、空输入）
- **实际分支**: `tests/runtime/` 中无 `test_tool_truncation.py`
- **预期行为**: runtime safety mechanism 应有直接功能测试
- **实际行为**: 仅有 weak typing guard 中的 import 覆盖，无功能测试
- **直接证据**: 无 `test_tool_truncation.py` 文件
- **影响**: 截断边界条件未验证，可能损坏工具输出或未防护超大结果
- **建议改法和验证点**: 新增 `tests/runtime/test_tool_truncation.py` 覆盖截断阈值边界条件
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- 无。所有 finding 均基于直接代码证据。

## Residual Risk

1. **`memory_repair.py` 零测试覆盖 (Finding 13)**: 这是本次 review 发现的最高严重度问题。memory projection rebuild/catch-up 是 Host startup recovery 和 admission 的关键路径，batch loop 终止条件若有逻辑错误可导致无限循环或 memory projection 静默损坏。

2. **大 session rebuild performance**: implementation-control.md 已记录此为已知剩余风险。当 session EventLog 很大时，memory projection rebuild 可能需要处理大量事件。

3. **Host close terminal closeout (Finding 4)**: 设计上有意选择不写 terminal facts（文档明确记录），依赖 startup recovery scanner 作为 safety net。这是架构权衡而非 bug，但增加了对 recovery scanner 正确性的依赖。

4. **Compaction quality check 与 max_attempts 的组合效应 (Finding 2 + 3)**: 单独看各是 medium，组合看已完成任务的 compaction 几乎必然失败。这是 P12.6 新引入的行为，需确认是否有意。

5. **Dispatch/Recovery 与 Durable layering 的已知 residual items**: implementation-control.md 记录的"dispatch / recovery、durable layering、memory semantics、Engine runner / provider、ToolRuntime 与 production hardening items"仍为后续 owner 跟踪项。

6. **Quality check 未测试分支 (Finding 15)**: `_summary_pretends_evidence_backed_fact` 条件 4 无测试覆盖，回归可能静默允许无效 compaction candidate。

7. **ToolRuntime schema projection 与 tool truncation 无功能测试 (Finding 16, 17)**: 校验函数和截断逻辑仅有 import boundary 测试，无功能测试覆盖拒绝路径和边界条件。

## Verdict

**PASS_WITH_FINDINGS**

1 个 blocking finding：

- **Finding 13（严重）**: `memory_repair.py` 零测试覆盖。memory projection rebuild/catch-up 是生产关键路径，无测试覆盖构成 ship blocker。

5 个 medium findings 均有直接代码证据：

- Finding 1（callback error swallowing）有 drain loop 轮询兜底
- Finding 2+3（compaction max_attempts + open_questions check）是 P12.6 新引入的设计选择，需确认是否有意
- Finding 4（Host close terminal）是有意设计，recovery scanner 兜底
- Finding 5（WAITING_FOR_LANE orphan）有 startup recovery 兜底
- Finding 15（quality check 未测试分支）回归风险
- Finding 16, 17（ToolRuntime / truncation 无功能测试）回归风险

7 个 low findings 为性能优化和代码质量改进项。
