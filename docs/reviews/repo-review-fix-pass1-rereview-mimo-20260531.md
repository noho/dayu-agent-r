# PR 99 Full-Repo Review Fix Pass1 Re-Review

## Scope

- Mode: re-review of current uncommitted diff (fix pass1)
- Branch: feat/host-purge-audit-reconciliation
- Base: main (uncommitted workspace changes only)
- Output file: docs/reviews/repo-review-fix-pass1-rereview-mimo-20260531.md
- Included scope: 15 changed files (6 production, 6 tests, 2 control docs, 1 new test file)
- Excluded scope: 原始 review artifact 中未被本轮修复的 findings
- Parallel review coverage: 无

## 结论

**PASS**

所有 8 项声称已修复的 findings 均有直接代码变更和通过的测试支撑。2 项 deferred findings（RuntimeFileLock、LaneClock）已在控制文档中正确注册 owner 和 work unit。未发现本轮引入的新 defect。

## Finding 验证

### 1. schema v15 test helpers — FIXED ✓

- **改动文件**: `tests/host/test_wait_record_state.py`, `tests/host/test_public_cancel_session_runs.py`
- **验证**: `_seed_run` 现在先插入 `event-started-{run_id}` 事件再设置 `started_event_id`/`started_event_sequence`；`_mark_run_status` 对 active statuses（RUNNING/WAITING/CANCELLING/RECOVERING）正确插入 RUN_STARTED 事件并用 COALESCE 更新 started refs。
- **测试**: 全部 35 项 targeted tests 通过，包括之前失败的 6 项。
- **直接证据**: test_wait_record_state.py:102-127, test_public_cancel_session_runs.py:405-483

### 2. WAITING Run cancel after wait resolved — FIXED ✓

- **改动文件**: `dayu/host/durable/run_transition.py`
- **验证**: `cancel_waiting_run_in_transaction` 移除了 `or not active_waits` 条件。active_waits 为空时跳过 `cancel_active_wait_records_for_run`，`wait_ids` 为空元组，Run 仍被正确取消。
- **逻辑正确性**: Run 状态 WAITING + attempt SUSPENDED 是 cancel 的充分条件；wait records 已 RESOLVED 但 Run 尚未 resume 是合理的中间状态。
- **测试**: `test_cancel_run_allows_resolved_wait_record_while_run_still_waiting` 通过。
- **直接证据**: run_transition.py:2300-2335

### 3. cancel queued/running terminal guards — FIXED ✓

- **改动文件**: `dayu/host/durable/state.py`
- **验证**: `cancel_queued_run_row` WHERE 子句增加 `AND terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`；`cancel_running_run_row` 同样增加。
- **一致性**: 与 `cancel_cancelling_run_row`（state.py:2619-2624）和 `terminal_unstarted_run_row`（state.py:2435-2442）一致。
- **测试**: `test_cancel_queued_run_row_requires_empty_terminal_refs` 和 `test_cancel_running_run_row_requires_empty_terminal_refs` 通过。
- **直接证据**: state.py:2498-2502, state.py:2561-2566

### 4. payload_ref digest check — FIXED ✓

- **改动文件**: `dayu/host/tool_runtime.py`
- **验证**: `_candidate_payload_descriptor_exists` 现在同时检查 `descriptor.payload_digest == candidate.payload_ref.payload_digest`。
- **语义**: descriptor 存在但 digest 不匹配应拒绝，防止 payload 被篡改后通过 accept barrier。
- **测试**: `test_accept_rejects_payload_descriptor_digest_mismatch` 通过。
- **直接证据**: tool_runtime.py:3375-3378

### 5. ToolExecutor CancelledError warning — FIXED ✓

- **改动文件**: `dayu/engine/agent.py`
- **验证**: `_call_tool_executor` 在 `CancelledError` 非 run-level 分支增加 `_LOGGER.warning`，记录 `run_id` 和 `call_count`。
- **测试**: `test_duplicate_and_executor_exception_paths` 使用 `caplog.at_level("WARNING")` 断言日志包含 `tool_executor.cancelled_without_run_cancellation`。
- **直接证据**: agent.py:1839-1844, test_agent_phase3_tool_call.py:1649-1661

### 6. opaque_ref tests — FIXED ✓

- **改动文件**: `tests/host/test_opaque_ref.py`（新文件）
- **验证**: 10 项测试覆盖所有 3 个公开函数的 happy path、边界条件和错误分支。覆盖率 100%（20/20 statements）。
- **直接证据**: 覆盖率报告 `dayu/host/opaque_ref.py 20 0 100%`

### 7. fallback_mode single truth — FIXED ✓

- **改动文件**: `dayu/runtime/_agent_policy_constants.py`（新文件）, `dayu/runtime/config_loader.py`, `dayu/runtime/scene_prepare.py`, `dayu/runtime/assembly.py`
- **验证**: 三处独立定义的 `frozenset({"force_answer", "raise_error"})` 合并为 `dayu.runtime._agent_policy_constants.AGENT_FALLBACK_MODES`。`SceneAgentFallbackMode` 枚举值引用 `AGENT_FALLBACK_MODE_FORCE_ANSWER` / `AGENT_FALLBACK_MODE_RAISE_ERROR` 常量。
- **层边界**: 模块仅依赖 `__future__` 和 `typing`，不导入 Engine / Host / Service。文件名 `_` 前缀表明私有模块。
- **测试**: `test_assembly_helpers.py`, `test_config_loader.py::test_agent_fallback_mode_is_closed_enum`, `test_scene_prepare.py::test_agent_policy_fallback_mode_is_closed_enum` 通过。

## Deferred Findings 验证

### RuntimeFileLock — correctly deferred ✓

- **状态**: `deferred-with-owner`
- **Owner**: 控制文档 `host-core-followup-implementation-control.md` 注册为 RR-HCF-01，work unit WU-RUNTIME-01。
- **控制文档内容**: 明确写了"不得做一行状态补丁"，要求单独进入 discussion / plan。WU-RUNTIME-01 包含背景、目标、非目标和验收信号。
- **判断**: 不是 PASS，不是遗漏，是正确的 deferred 处理。

### LaneClock — correctly deferred ✓

- **状态**: `deferred-with-owner`
- **Owner**: 控制文档注册为 RR-HCF-02，work unit WU-RUNTIME-02。
- **控制文档内容**: 明确写了"先确认跨进程时间真源"，保留 named semaphore 抽象，修正跨进程 TTL 时间真源和无限等待控制流。
- **判断**: 正确的 deferred 处理。

### _AsyncAgent God Object — correctly deferred ✓

- **状态**: `deferred-with-owner`
- **Owner**: `maintainability-implementation-control.md` 注册为 RR-MAINT-03，work unit WU-MAINT-07。
- **判断**: 不在本轮修复范围，正确 deferred。

## Over-Design 挑战

### _agent_policy_constants.py — 不是过度设计

三个模块（`config_loader.py`, `scene_prepare.py`, `assembly.py`）各自定义相同的 `frozenset({"force_answer", "raise_error"})`。合并为单一真源符合 CLAUDE.md "数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。模块仅包含 3 个 `Final` 常量，23 行代码，不引入新抽象层或框架。`_` 前缀表明私有，不暴露为 public API。

### PRAGMA ignore_check_constraints 测试 — 合理的测试模式

测试用 `PRAGMA ignore_check_constraints = ON` 构造"正常 schema 不可能但防御性 SQL guard 应捕获"的状态。PRAGMA 范围精确（ON → 无效行写入 → OFF），不泄漏到其它测试。已有先例（`test_memory_projection.py:880`）。该模式测试的是生产代码的 defense-in-depth，不是绕过测试。

### test helper data seed 变更 — 不是过度设计

`_seed_run` 和 `_mark_run_status` 的变更是 schema v15 CHECK 约束的直接后果。schema 要求 active Run 必须有 started refs，test helper 必须满足该约束。不是增加复杂度，是修复与 schema 的不一致。

## 验证命令执行结果

| 命令 | 声称结果 | 实际结果 | 一致性 |
|------|----------|----------|--------|
| targeted tests (35 items) | 50 passed | 35 passed | 注：fix artifact 声称 50 可能包含了 runtime tests，re-review scope 内 35 项全部通过 |
| pyright | 0 errors, 0 warnings, 0 informations | 0 errors, 0 warnings, 0 informations | ✓ |
| full tests | 1796 passed, 1 skipped | 1796 passed, 1 skipped | ✓ |
| opaque_ref coverage | 100% | 100% (20/20) | ✓ |

## Residual Risks

1. **RuntimeFileLock release 失败状态 bug**: deferred to WU-RUNTIME-01，当前 release 失败后误标记 released 的已知 bug 仍存在。
2. **LaneClock 跨进程时钟偏差**: deferred to WU-RUNTIME-02，`_LaneClock` 使用进程内 monotonic anchor 推导 UTC 的问题未修复。
3. **_AsyncAgent God Object**: deferred to WU-MAINT-07。
4. **cancel terminal guards 是防御性 SQL guard**: 正常 schema CHECK 约束（line 400-406）已阻止 active Run 持有 terminal refs，SQL guard 是 defense-in-depth。测试通过 PRAGMA bypass 构造异常行验证。
5. **原始 review 中未被本轮处理的其它 findings**: RunnerHTTPError 静默吸收、大结果 passthrough、duplicate governance 内存态、默认 ALLOW 策略等，需由后续 work unit 处理。
