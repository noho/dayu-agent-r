# WU-STRESS-01 PR Focused Re-Review — AgentDS

## Gate

- **Gate**: focused re-review (PR-LOW-01 fix verification)
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Review role**: AgentDS focused re-review specialist
- **Review target**: AgentCodex fix for PR-LOW-01 (`StressWorkerBehavior.CLEAN_EOF` 缺少直接 stress 覆盖)
- **Fix artifact**: `docs/reviews/wu-stress-01-fix-pr-codex-20260601.md`
- **Prior PR review**: `docs/reviews/wu-stress-01-pr-review-ds-20260601.md`
- **Output file**: `docs/reviews/wu-stress-01-pr-rereview-ds-20260601.md`
- **Review date**: 2026-06-01

## Scope

- **Included**: `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py` 的 uncommitted diff。
- **Excluded**: 全 PR deepreview、已有 review artifact、生产代码、README、控制文档。

## Conclusion: PASS

PR-LOW-01 已正确关闭。`CLEAN_EOF` 行为在 Slice 4 scheduler/liveness long-run stress 中获得直接覆盖，新增 `clean_eof_failed_closeout_ok` 断言同时验证 public snapshot 终态（`FAILED`）和 durable reason（`stream_ended_without_terminal`）。fix 未引入新的 correctness、flake、typing、docstring、README 或分层问题。

## Finding Closure Verification

### PR-LOW-01: `StressWorkerBehavior.CLEAN_EOF` 缺少直接 stress 覆盖 → CLOSED

- **Fix artifact 声明**: 在 Slice 4 的 mixed flow 中新增一个 `CLEAN_EOF` scripted run，增加 `run_failed_reason_for_run()` helper 和 `clean_eof_failed_closeout_ok` 诊断。
- **验证证据**:

  1. **Worker 行为正确**: `DeterministicStressWorkerHandle.events()` (`stress_support.py:302-303`) 对 `CLEAN_EOF` 分支直接 `return`，不产出任何 EngineEvent。Host scheduler 将检测到 stream clean EOF 并执行 `RUN_FAILED` closeout，reason 为 `stream_ended_without_terminal`。docstring 已同步更新 ("``CLEAN_EOF`` 行为不产出事件，由 Host scheduler 显式 closeout")。

  2. **Helper 诊断正确**: `run_failed_reason_for_run()` (`stress_support.py:1367-1410`) 通过参数化 SQL 查询 `json_extract(reason_json, '$.reason')`，读取目标 Run 最近一条 `RUN_FAILED` 的 reason。返回值类型为 `str | None`，完整处理 None row / None reason / 非文本 reason 三类边界。

  3. **诊断字段与 predicate 正确**: `Slice4SchedulerLivenessDiagnostics` 新增 `clean_eof_run_id: str` 和 `clean_eof_failed_reason: str | None` 两个字段（`test_host_production_stress.py:670-671`）。`clean_eof_failed_closeout_ok` property (`:759-772`) 同时检查：
     - public snapshot 中存在该 `run_id` 且 `status is RunStatus.FAILED`
     - durable `RUN_FAILED` reason 等于 `_CLEAN_EOF_FAILED_REASON = "stream_ended_without_terminal"`

  4. **failure_boundary 集成正确**: `failure_boundary` property (`:795`) 新增 `if not self.clean_eof_failed_closeout_ok: return "scheduler_close"`，位于 `stream_exception_closeout_ok` 检查之后、`terminal_dedupe_ok` 检查之前，优先级合理。

  5. **测试体覆盖正确**: Slice 4 测试体 (`:1552-1559`) 新增一个 `CLEAN_EOF` scripted run 提交到 `sessions[3]`，`run_id` 加入 `run_ids` 列表，随后 `wait_all_runs_terminal` 统一等待。测试断言 (`:1627`) 新增 `assert diagnostics.clean_eof_failed_closeout_ok, summary_json`。

- **状态**: **CLOSED**。plan 要求的 clean EOF scheduler failed closeout 在 production stress level 获得直接哨兵覆盖。

## Cross-Cutting Checks

### No new correctness / flake risk

- `CLEAN_EOF` 行为是纯确定性——worker events() 直接 `return`，不涉及时序、竞态或外部依赖。
- Host scheduler 对 clean EOF 的 closeout 行为是既有的生产语义（stream ended without terminal → `RUN_FAILED` closeout），fix 未修改 scheduler 行为。

### No new typing issues

- `run_failed_reason_for_run(): str | None` 返回值类型完整，处理 None row / None reason / 非 str 三类边界。
- 新增 dataclass 字段 `clean_eof_run_id: str` 和 `clean_eof_failed_reason: str | None` 类型完整。
- 无 `Any`、`object`、裸容器注解。

### No new docstring issues

- `events()` docstring 更新为描述 `CLEAN_EOF` 语义。
- `run_failed_reason_for_run()` 有完整中文 docstring（参数、返回值、异常）。
- `Slice4SchedulerLivenessDiagnostics` class docstring 新增两个字段说明。
- `clean_eof_failed_closeout_ok` property 有中文 docstring。

### No SQL injection

- `run_failed_reason_for_run()` 使用 `?` 占位符 + tuple 参数化: `(_EVENT_REASON_JSON_PATH, run_id, _EVENT_TYPE_RUN_FAILED)`，无注入风险。

### No README / layering / production code

- 修改仅限 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py`。
- 未修改生产代码、README、控制文档或已有 review artifact。
- `stress_support.py` 未增加新 import，未导入 Host 内部实现。

### Controller validation alignment

- `1 passed` (Slice 4 targeted stress)、`5 passed` (full stress suite)、`pyright 0 errors`——与代码证据一致。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无新增 residual risk。clean EOF 覆盖仍限定在 stress marker 下，符合 WU-STRESS-01 的默认排除策略。

## Review Artifact Path

`docs/reviews/wu-stress-01-pr-rereview-ds-20260601.md`
