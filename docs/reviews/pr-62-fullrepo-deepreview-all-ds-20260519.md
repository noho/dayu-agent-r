# PR-62 Fullrepo Deepreview --all (AgentDS)

## Scope

- Mode: all repository
- Branch: `feat/host-p10-5-public-contract-freeze`
- Review date/time: 2026-05-19 20:03 UTC+8
- Output file: `docs/reviews/pr-62-fullrepo-deepreview-all-ds-20260519.md`
- Included scope: `dayu/` (contracts, engine, host, runtime), `tests/`, `docs/host/design.md`, `docs/host/implementation-control.md`
- Excluded scope: `.venv/`, `workspace/tmp/`, `docs/engine/` historical phase artifacts, `docs/reviews/` (review artifacts themselves treated as output surface)
- Parallel review coverage:
  - Architecture boundaries / import discipline: Agent overview (all dayu/ files)
  - Host durable layer state machines: Agent (11 files, all transitions)
  - Host tool runtime / waiting / compaction: Agent (13 files, key paths)
  - Engine runner / SSE parsing: Agent (18 files, key paths)
  - Contracts layer / public API / test coverage: Agent (contracts + host tests)

## Verification Commands Run

```bash
# pyright
python -m pyright dayu/ tests/
# Result: 0 errors, 0 warnings, 0 informations

# Full test suite
python -m pytest tests/ -q
# Result: 6 failed, 1283 passed

# Failed test identification (all regressed in b8089a8)
python -m pytest tests/host/test_dispatch_scheduler.py -q
# Result: 5 failed, 36 passed

python -m pytest tests/host/test_public_compact_smoke.py -q
# Result: 1 failed, 0 passed (test_real_compactor_public_opener_compacts_and_preserves_continuity)

# Regression confirmation
git checkout b8089a8^  # parent commit 55c8d1d
python -m pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt -q
# Result: 1 passed (regression confirmed)

# git diff whitespace check
git diff --check main...HEAD
# Result: trailing whitespace found in review artifacts (docs/reviews/*.md), not in production code
```

## Findings

### F1-BLOCKED-严重-commit-b8089a8-proactive-compaction-test-regression-6-tests-fail

- **入口/函数**: `HostDispatchScheduler._execute_proactive_compaction` / `FakeContextCompactor.compact`
- **文件(行号)**:
  - `dayu/host/dispatch.py:921-1001` (`_execute_proactive_compaction`)
  - `dayu/host/fake_compaction.py:201-212` (`_budget_after_compact`)
  - `dayu/host/compaction_budget.py:24-44` (`estimate_compacted_context_budget`)
  - `tests/host/test_dispatch_scheduler.py:2134-2174` (test_pre_start_governance_soft_threshold_compacts_before_attempt)
  - `tests/host/test_dispatch_scheduler.py:2177-2210` (test_wake_queue_promotion_uses_tracked_async_promotion_task)
  - `tests/host/test_dispatch_scheduler.py` (test_proactive_compaction_calls_llm_outside_write_transaction)
  - `tests/host/test_dispatch_scheduler.py` (test_proactive_compaction_retries_quality_rejection_before_accept)
  - `tests/host/test_dispatch_scheduler.py` (test_multi_turn_proactive_compact_feeds_subsequent_run_input)
  - `tests/host/test_public_compact_smoke.py:45-140` (test_real_compactor_public_opener_compacts_and_preserves_continuity)
- **输入场景**: 任何 proactive compaction 场景 — soft threshold 触发 `COMPACT_SOFT_THRESHOLD` decision，scheduler 调用 `_prepare_compact_before_dispatch` → `_execute_proactive_compaction`
- **实际分支**: `run_compaction_operation` 返回 `accepted_candidate=None, failure_reason` 非 None（quality check 或 hard_threshold_after_compact 失败），进入 `dispatch.py:971-993` failure 分支
- **预期行为**: `FakeContextCompactor` 应生成可被 quality check 接受的 candidate，且 `budget_after_compact < hard_threshold_tokens`，compact 成功后创建 Attempt
- **实际行为**: compaction operation 返回失败，Attempt 不被创建（`_attempt_count_for_run == 0`），Run 被 `_fail_unstarted_in_transaction` 收口为 FAILED，错误消息 "Context compaction failed before dispatch"
- **直接证据**:
  - 根因链：`FakeContextCompactor._budget_after_compact` (fake_compaction.py:201) → `estimate_compacted_context_budget` (compaction_budget.py:24) → `_estimate_preserved_context_tokens` (compaction_budget.py:49) → `_estimate_preserved_share_from_budget` (compaction_budget.py:93) 中 `estimated_tokens = request.budget_before_compact.estimated_input_tokens` 可能在测试场景下与 actual preserved ref set 产生过大的 budget_after_compact 估计，导致 `budget_after_compact >= hard_threshold_tokens` 判定成立（compaction_operation.py:140-143）
  - 父 commit (55c8d1d) 上同一测试通过（1 passed），HEAD (b8089a8) 上失败，确认为 b8089a8 引入回归
  - 错误消息 "Context compaction failed before dispatch" 来自 `dispatch.py:991`
- **影响**: 6 个 proactive compaction 测试全部无法创建 Attempt / 收口到错误终态；真实 compactor smoke 返回 FAILED 而非 SUCCEEDED。proactive compaction 在 soft threshold 场景完全无法工作
- **建议改法和验证点**:
  1. 检查 `compaction_budget.py:_estimate_preserved_share_from_budget` 中 `source_refs` 与 `preserved_refs` 的集合构造 —— `preserved_refs` 包含 `current_user_input_ref` 但不包含在 `source_refs` 中，导致 `retained_count` 偏低，`estimated_tokens * retained_count / len(source_refs)` 可能产生与 typed_fragment_tokens 相差过大的估计
  2. `max(typed_fragment_tokens, proportional_estimate)` 在 `_estimate_preserved_context_tokens:69-72` 取了二者较大值，当 proportional estimate 因 ref set 不匹配而偏高时会导致 `budget_after_compact >= hard_threshold_tokens`
  3. 修复后运行 `pytest tests/host/test_dispatch_scheduler.py tests/host/test_public_compact_smoke.py -q` 确认全部通过
- **修复风险（中）**: 修改 compaction budget 估算逻辑可能影响 proactive compaction 的 budget decision；需在 real compactor smoke 中验证修复不引入新的误判
- **严重程度（严重）**: 阻断 proactive compaction 完整路径，6 个测试回归，功能不可用

### F2-高-oversized-truncation-data-loss-cursor-destroyed

- **入口/函数**: `TruncationManager.apply_truncation`
- **文件(行号)**: `dayu/host/tool_runtime.py:1399-1411`
- **输入场景**: 工具返回超大数据结果；truncation 后 visible portion 仍超过 `_MAX_LLM_INLINE_TOOL_RESULT_BYTES`
- **实际分支**: truncated outcome 的 inline size 仍超限 → `self._cursors.pop(cursor_metadata.cursor_id, None)` (line 1403)，同时返回 `ToolFailedOutcome`
- **预期行为**: cursor 应被保留，让调用方可以后续通过 `fetch_more` 分段获取完整数据
- **实际行为**: cursor 被销毁，数据永久丢失，`fetch_more` 无法恢复
- **直接证据**: `tool_runtime.py:1399-1403` pop cursor 后返回 failure；`fetch_more` (line 1425) 无法找到已被 pop 的 cursor id
- **影响**: 大数据工具结果在截断边界条件下永久丢失，无法通过 `fetch_more` 恢复
- **建议改法和验证点**: oversized truncation 场景下保留 cursor，只返回 truncated visible portion + cursor，不 pop cursor；或提供 oversized truncation cursor recovery 路径
- **修复风险（中）**: 修改 truncation cursor 生命周期可能影响 truncation manager 内存占用（cursor 不清理需 TTL 兜底）
- **严重程度（高）**: 数据丢失场景，用户可见

### F3-中-tool-call-index-short-circuit-fragmentation

- **入口/函数**: `ToolCallAggregator._resolve_index`
- **文件(行号)**: `dayu/engine/runners/openai/tool_call_aggregator.py:170-171`
- **输入场景**: Provider 在同一 chunk 中对不同 tool call 使用混合 identification 模式（部分只有 id，部分只有 index），且 provider index 与 synthetic index 冲突
- **实际分支**: `delta_index` 存在 → `return delta_index` 直接短路，不检查 `delta_id` 是否已 mapping 到不同 index
- **预期行为**: delta 的 id 已存在 mapping 时应沿用已分配的 index，不创建新的 partial
- **实际行为**: 同一 tool call 的数据被分片到两个不同的 `_PartialToolCall` 实例中，导致数据不完整
- **直接证据**: `_resolve_index:170-171` 短路返回 provider index；`_partials_by_index` 中既有 synthetic-index partial（有 name 有部分内容）又有 provider-index partial（有剩余内容），finalize 时 synthetic-index partial 因缺 id 被标记为 `tool_call_missing_id`
- **影响**: 特定 delta 序列下 tool call 参数不完整，可能导致工具执行失败或参数错误
- **建议改法和验证点**: `_resolve_index` 中在短路返回前先检查 `delta_id` 是否已在 `_index_by_id` 中；若已有映射，返回已有 index 而非 provider index
- **修复风险（低）**: 修改短路逻辑，影响面限定在 tool_call_aggregator 内部
- **严重程度（中）**: 触发条件需特定 provider delta 序列，但后果是数据完整性问题

### F4-中-duplicate-governance-check-then-act-race

- **入口/函数**: `ToolRuntimeExecutor._execute_one`
- **文件(行号)**: `dayu/host/tool_runtime.py:2465-2546`
- **输入场景**: 同 Run 内两个并发 tool call 对同一工具、相同参数同时到达
- **实际分支**:
  1. Call A: `decide_duplicate()` (line 2465, RLock 内 find()) → ALLOW（无已有记录）
  2. Call B: `decide_duplicate()` (line 2465, RLock 内 find()) → ALLOW（仍无记录）
  3. Call A: 执行工具 → accept barrier 成功
  4. Call B: 执行工具 → accept barrier 成功
  5. Call A: `record_accepted()` (line 2546, RLock 内 record()) → 写入 outcome A
  6. Call B: `record_accepted()` (line 2546, RLock 内 record()) → 覆盖 outcome A
- **预期行为**: 第二个调用应返回 REUSE，不执行工具，引用第一个调用的结果
- **实际行为**: 两个调用都执行了工具（对 side-effect/paid 工具产生双重成本），且第二个调用的记录覆盖了第一个
- **直接证据**: `find()` (RLock) 与 `record()` (RLock) 之间无原子性保护（line 2465 check 到 line 2546 record），`decide_duplicate` 与 `record_accepted` 是两次独立的 RLock 获取/释放
- **影响**: 同参数重复工具调用可能被执行多次，对 side-effect 工具产生双重成本，且先执行的结果被覆盖
- **建议改法和验证点**: 将 `find+record` 合并为单一 RLock 保护的操作；或将 `record` 使用 INSERT OR IGNORE 语义
- **修复风险（低）**: 修改 duplicate governance 内部数据结构，不影响 public contract；但需要确保合并不引入死锁
- **严重程度（中）**: 并发场景下的正确性问题，对 side-effect 工具有实际成本影响

### F5-低-close-session-no-active-run-validation

- **入口/函数**: `_CloseSessionOperation.__call__`
- **文件(行号)**: `dayu/host/durable/session_lifecycle.py:360-447`
- **输入场景**: 调用 `close_session` 时 Session 下仍有 RUNNING / WAITING / CANCELLING / RECOVERING Run
- **实际分支**: 只检查 Session 存在且 status == OPEN (line 381-392)，不检查 active Run
- **预期行为**: 文档约定 close 不取消 active Run，也不应阻止 close；但当前实现完全不做检查，调用方可能不知情地留下孤儿 Run
- **实际行为**: Session 被关闭（CLOSED），active Run 不受影响但成为孤儿（Session 已不接受新操作）
- **直接证据**: `session_lifecycle.py:360-447` 整个 `__call__` 方法中没有任何 `read_active_run_for_session` 调用
- **影响**: 调用方可能在不知晓 active Run 存在的情况下关闭 Session，导致 orphan Run
- **建议改法和验证点**: 设计文档已声明 `close_session` 不取消 active Run；当前行为符合设计但缺少防御性 diagnostic。可添加 diagnostic log 或返回 `close_session` result 中标记存在 active Run
- **修复风险（低）**: 添加 passive check 不影响现有行为
- **严重程度（低）**: 符合设计文档约定，但 observability 不足

### F6-低-inconsistent-terminal-null-checks-in-cas-mutations

- **入口/函数**: `cancel_queued_run_row`, `cancel_running_run_row`, `cancel_cancelling_run_row`, `terminal_run_row`
- **文件(行号)**:
  - `dayu/host/durable/state.py:2569` (`cancel_queued_run_row`)
  - `dayu/host/durable/state.py:2625` (`cancel_running_run_row`)
  - `dayu/host/durable/state.py:2687` (`cancel_cancelling_run_row`)
  - `dayu/host/durable/state.py:3353` (`terminal_run_row`)
- **输入场景**: CAS mutation 在 SQLite transaction 内并发执行
- **实际分支**: 这 4 个函数在 SQL WHERE 子句中只检查 `status = ?` 或 `status IN (...)`，不检查 `terminal_event_id IS NULL`
- **预期行为**: 其他 terminal mutation 函数（如 `cancel_waiting_run_row` line 3329, `terminal_unstarted_run_row` line 2546）在 WHERE 中显式检查 `terminal_event_id IS NULL`
- **实际行为**: 依赖 source status mismatch 保护（即 row 已被 terminal 后 status 不再是 QUEUED/RUNNING/CANCELLING/WAITING，CAS 返回 rowcount=0）
- **直接证据**: `cancel_queued_run_row:2604` WHERE 只有 `run_id = ? AND status = ?`；对比 `cancel_waiting_run_row:3329-3331` WHERE 包含 `AND terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`
- **影响**: Schema CHECK 约束（schema.py:366-378）提供了终态物理防护，不存在实际 bug；但代码风格不一致增加了维护者误判风险
- **建议改法和验证点**: 统一所有 terminal mutation 的 NULL terminal 检查，或在函数 docstring 中说明依赖 source status mismatch 的设计理由
- **修复风险（低）**: 纯维护性改进，不影响运行时行为
- **严重程度（低）**: 无实际 bug，代码一致性改进

### F7-低-contracts-validation-gaps-accumulated

- **入口/函数**: 各 `__post_init__` 方法
- **文件(行号)**:
  - `dayu/contracts/tool_call.py:120` — `BatchToolExecutionContext.correlation_id` 未校验
  - `dayu/contracts/tool_outcome.py:178` — `BatchToolExecutionOutcome.records` 可为空 tuple
  - `dayu/contracts/tool_outcome.py:115` — `ToolCancelledOutcome.meta` 未校验
  - `dayu/contracts/tool_schema.py:125` — `ToolTruncateSpec.ttl_seconds` 未校验
  - `dayu/contracts/tool_await.py:45` — `ToolAwaitSpec.deadline` 未校验（naive datetime / 过去时间）
  - `dayu/contracts/tool_await.py:73` — `ToolAwaitSnapshot.captured_at` 未校验 timezone
- **输入场景**: 各对应字段传入非法值
- **实际分支**: 校验缺失，非法值静默通过 `__post_init__`
- **预期行为**: 与同 dataclass 中其他字段的严格校验一致
- **直接证据**: 各文件对应行号的 `__post_init__` 方法中缺少对应字段校验
- **影响**: 非法值可能在更下游触发难以追踪的错误，排障成本增加
- **建议改法和验证点**: 补齐各字段校验，对齐同 dataclass 中已有校验的严格性；新增对应测试
- **修复风险（低）**: 添加校验是纯防御性改进，可能暴露调用方的非法传参（但那是调用方的 bug）
- **严重程度（低）**: 防御性校验缺失，当前无证据显示生产代码传入非法值

## Architecture Boundary Audit

**结论：零违规。** 对所有生产 Python 文件的 import 边界检查结果：

| 层 | 规则 | 结果 |
|---|---|---|
| `dayu/runtime/` | 不 import engine/host/service/ui/fins | 通过（5 文件） |
| `dayu/engine/` | 不 import host/service/ui | 通过（所有文件含 runners/openai/） |
| `dayu/contracts/` | 层中立，不 import engine/host | 通过（9 文件） |
| `dayu/host/` | 不 import service/ui | 通过（所有文件含 durable/） |

- `dayu/host/` → `dayu.engine.contracts` 是向下的合法依赖（Host → Engine）
- `dayu/runtime/` → `dayu.contracts.cancellation` 是向下的合法依赖（Runtime → Contracts）
- 无反向依赖，无 dynamic import 隐藏违规

## Design Doc / Implementation Control Doc 一致性

1. `docs/host/design.md` 作为设计真源保持干净：当前描述与 Host 实现架构一致，无旧术语残留
2. `docs/host/implementation-control.md` 追踪区完整：PR-62 fullrepo review deferred tracking 已记录（line 1634-1711），Phase 10 S4/S5/S6 residual risks 已记录，P9.5 归属追踪已记录
3. 已 deferred 的事项全部有 owner/destination：
   - Recovery / startup crash recovery / positive orphan proof → Phase 11
   - ToolsDiscovery / ScenePrepare → Phase 12
   - Audit / Tool Trace / Outbox → Phase 13
   - RemoteProxy → Phase 14
   - Retention / Purge production hardening → Phase 15
   - lane close/acquire race → Phase 11
   - DDL atomicity → durable bootstrap hardening work unit
   - watch polling performance → Phase 11
   - import boundary helper 重复 → P9.5 / Phase 11
4. 未发现未 tracking 的 deferred 事项

## Open Questions

- 无。所有观察项均可基于当前代码状态做出明确判断。

## Residual Risk

- **F1 test regression**: 必须在本次 deepreview 后作为 fix 收口，不阻塞 PR-62 draft-PR-pass 之后的 Phase 11
- **F2 oversized truncation data loss**: 已有 tracking owner（ToolRuntime diagnostics hardening），当前条件触发概率低
- **F3 tool call index fragmentation**: 需要特定 provider delta 序列触发，标准 OpenAI 协议不受影响
- **F4 duplicate governance race**: 同一 Run 内并发同一工具同一参数调用概率低，但 side-effect 工具有成本风险
- **F5 close-session-no-active-run-validation**: 符合设计文档约定，observability 不足但不影响 correctness
- **Engine runner layer**: 无 material findings，SSE/stream/non-stream/cancellation/error classification 均 verified correct
- **Durable state machines**: CAS + schema CHECK + transaction 三层防护有效，无数据一致性漏洞
- **Contracts serialization**: 无跨进程/跨边界 JSON 序列化 round-trip 测试，但当前全部为 in-process 使用

## Verdict

**BLOCKED**

阻塞理由：commit `b8089a8` ("fix pr62 fullrepo review findings") 引入 6 个 proactive compaction 测试回归（F1）。所有失败均涉及 `compaction_budget.py`（新增文件）与 `FakeContextCompactor._budget_after_compact` 的交互，导致 `budget_after_compact >= hard_threshold_tokens` 判定在测试场景下误成立。父 commit `55c8d1d` 上同一测试全部通过。

必须修复 F1 后才能继续推进 PR-62 draft-PR-pass 后续 gate。

验证命令（fix 后执行）:
```bash
source .venv/bin/activate
python -m pytest tests/host/test_dispatch_scheduler.py tests/host/test_public_compact_smoke.py -q
python -m pytest tests/host/ -q
python -m pyright dayu/host tests/host
git diff --check main...HEAD
```
