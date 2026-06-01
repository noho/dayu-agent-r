# WU-STRESS-01 PR Re-Review — AgentMiMo

## Gate

- **Gate**: draft PR focused re-review (WU-STRESS-01)
- **Source finding**: PR-LOW-01, `StressWorkerBehavior.CLEAN_EOF` 缺少直接 stress 覆盖
- **Fix artifact**: `docs/reviews/wu-stress-01-fix-pr-codex-20260601.md`
- **Review date**: 2026-06-01
- **Reviewer**: AgentMiMo
- **Scope**: 只审查 fix diff，不重新扩大到全 PR deepreview

## Re-Review Pass/Fail

**PASS**

Fix 正确关闭 PR-LOW-01 finding，未引入新的 correctness、flake、typing、docstring、README 或分层问题。

## Finding Closure Verification

### PR-LOW-01: `StressWorkerBehavior.CLEAN_EOF` 缺少直接 stress 覆盖 — CLOSED

**Fix 内容**:

1. `stress_support.py:302-303`: 为 `DeterministicStressWorkerHandle.events()` 增加显式 `CLEAN_EOF` 分支，语义为 clean return（空 generator），由 Host scheduler timeout closeout 处理。
2. `test_host_production_stress.py:1552-1559`: 在 Slice 4 scheduler/liveness mixed flow 中新增一个 `CLEAN_EOF` scripted run。
3. `stress_support.py:1367-1409`: 新增 `run_failed_reason_for_run()` helper，从 EventLog canonical fact 读取 `RUN_FAILED` reason。
4. `test_host_production_stress.py:756-773`: 在 `Slice4SchedulerLivenessDiagnostics` 中新增 `clean_eof_failed_closeout_ok` property，断言 clean EOF Run 的 public snapshot 为 `FAILED` 且 durable reason 为 `stream_ended_without_terminal`。
5. `test_host_production_stress.py:795-796`: 将 `clean_eof_failed_closeout_ok` 纳入 `failure_boundary` predicate chain。
6. `test_host_production_stress.py:1627`: 新增显式断言 `assert diagnostics.clean_eof_failed_closeout_ok`。

**验证**: Fix 覆盖了 plan Decision 5 要求的 clean EOF 脚本行为和 scheduler failed closeout 路径。`CLEAN_EOF` 枚举成员不再是死代码。

## Correctness 验证

### 1. Production constant 对齐

Test 常量 `_CLEAN_EOF_FAILED_REASON = "stream_ended_without_terminal"`（`test_host_production_stress.py:111`）精确匹配生产常量 `_REASON_STREAM_ENDED_WITHOUT_TERMINAL = "stream_ended_without_terminal"`（`dayu/host/engine_ingest.py:203`）。该常量在已有测试 `test_phase5_local_execution_integration.py:721` 和 `test_dispatch_scheduler.py:2154` 中已验证。

### 2. `events()` 方法语义

`CLEAN_EOF` 分支（`stress_support.py:302-303`）直接 `return`，产出空 async generator。这与 Host 生产代码 `dispatch.py:2783-2794` 中 clean EOF 触发 `close_clean_eof()` 的路径一致。最终 fallback `return`（line 304）仍保留作为防御性收口。

### 3. `run_failed_reason_for_run()` 类型与安全

- 参数类型: `root_path: pathlib.Path`, `run_id: str` -> `str | None`
- SQL 使用 `?` 参数化，无注入风险
- `json_extract(reason_json, ?)` 路径由模块级常量 `_EVENT_REASON_JSON_PATH = "$.reason"` 控制
- 返回值: 无匹配 row 时 `None`，reason 为 SQL NULL 时 `None`，非 str 时 `TypeError`
- Docstring 完整中文，声明参数、返回值、异常和 diagnostic 边界

### 4. `Slice4SchedulerLivenessDiagnostics` 扩展

- 新增字段 `clean_eof_run_id: str` 和 `clean_eof_failed_reason: str | None`（frozen dataclass，类型安全）
- `clean_eof_failed_closeout_ok` property 同时检查 public snapshot `FAILED` status 和 durable reason 匹配
- Docstring 完整中文

### 5. `failure_boundary` predicate 链顺序

`clean_eof_failed_closeout_ok` 检查位于 `stream_exception_closeout_ok` 之后、`terminal_dedupe_ok` 之前。语义正确：先验证 stream exception lost closeout，再验证 clean EOF failed closeout，最后验证 terminal 去重。失败时返回 `"scheduler_close"`，合理（scheduler 层面的 closeout 失败）。

### 6. Test 流程

- `clean_eof_run_id` 通过 `_submit_scripted_followup` 提交，behavior 队列入 `CLEAN_EOF`
- Worker accept 后 `events()` 立即 return（空 generator）
- Host scheduler 检测 stream 结束无 terminal，触发 `close_clean_eof()`，写 `RUN_FAILED` + reason
- `wait_all_runs_terminal` 等待 clean EOF run 进入 `FAILED` terminal
- `run_failed_reason_for_run` 读取 durable reason
- `clean_eof_failed_closeout_ok` 断言 public snapshot + durable reason 双重验证

### 7. 未引入的问题

- **Flake**: clean EOF closeout 由 Host scheduler timeout 机制驱动，确定性行为，无竞态
- **Typing**: pyright 0 errors（controller 验证）
- **Docstring**: 新增函数和 property 均有完整中文 docstring
- **README**: 未更新（正确 — 只补 stress 内部覆盖，未改变测试分层、运行命令或 marker 策略）
- **分层**: `run_failed_reason_for_run` 只读 EventLog canonical fact，不暴露 scheduler internals
- **Magic string**: `_CLEAN_EOF_FAILED_REASON` 和 `_EVENT_REASON_JSON_PATH` 均为模块级命名常量

## Controller 验证证据一致性

- `pytest -o addopts= -m stress tests/host/test_host_production_stress.py::test_scheduler_liveness_long_run_mixed_flow_stress -q`: 1 passed — clean EOF run 在 Slice 4 中正确收口
- `pytest -o addopts= -m stress tests/host/test_host_production_stress.py -q`: 5 passed — 全 suite 通过，fix 未破坏其它 slice
- `python -m pyright dayu/ tests/ utils/`: 0 errors — 类型安全

## Residual Risk

无新增 residual risk。`CLEAN_EOF` 覆盖仍限定在 stress marker 下，符合 WU-STRESS-01 默认排除策略。

## Final Decision

**PASS**。Fix 正确关闭 PR-LOW-01，可接受进入 PR。
