# PR-62 fullrepo review controller adjudication

## 输入

- `docs/reviews/repo-review-20260519-182223.md`
- `docs/reviews/repo-review-20260519-182226.md`
- `docs/host/design.md`

## 已修复

### repo-review-20260519-182226

- Finding 1 / 4 / 12：成立。`dayu/host/llm_compaction.py` 原先只按 summary 文本估算 `budget_after_compact`，且使用 4 chars/token。已新增 `dayu/host/compaction_budget.py`，统一使用 `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN`，并按 summary + 当前输入 + recent refs + tool fact refs + verified refs + 已有 summary refs + system prompt 与 compact 前预算保留占比估算；不再用 hard threshold 反向截断估算值。`FakeContextCompactor` 已复用同一 helper。
- Finding 3：部分成立。当前 `EngineEventType` 是封闭 enum，真正“未来未知 enum 成员”在同一进程内不可直接构造；但 type/data 不匹配的 unsupported 分支真实可达。已将 unsupported 分支改为 `stop_worker_stream=True` fail closed，并补测试。
- Finding 5：成立。`_close_runner_once` 普通异常路径未置 `_closed`。已改为 finally 置位，保证一次 close 尝试后不重复 close 同一 Runner。
- Finding 6：成立。`require_optional_non_empty_text` 对非文本值会触发 `AttributeError`。已增加 `isinstance` 守卫并补测试。
- Finding 8：成立。`ToolAwaitSnapshot` 缺少空 `snapshot_id` 校验。已补 `__post_init__` 与测试。
- Finding 9：成立且低风险。已将 `ALLOWED_TOOL_CANCELLED_REASONS` 标注为 `frozenset[ToolCancelledReason]`。
- Finding 14：验证时仍失败。已按设计允许 `llm_compaction.py` 依赖 Engine public entry / contracts，更新 import boundary 测试。
- Finding 15：验证时仍失败。root cause 是 active cancel 已提交并传播到 worker 后，worker stream clean EOF 先于 Engine `run_cancelled` 事件到达，Host 走 clean EOF lost closeout。已在非 scheduler close 场景下把 cancel 后 clean EOF 合成为明确 `run_cancelled` ingest。
- Finding 16：验证时仍失败。生产 event id 已稳定为 `event-tool-result-accepted-...`，测试仍断言旧 `event-engine-` 前缀。已更新测试断言。

### repo-review-20260519-182223

- Finding 1：成立。`_accept_awaiting_with_retry` timeout 未发 diagnostic ref，且 follow-up re-review 确认 `_awaiting_accept_failure_outcome` 会在转最终失败 outcome 时丢弃已有 refs。已让 timeout path 发射诊断，把诊断 ref id 放入 `ToolAwaitingAcceptTimedOut.diagnostic_refs`，并在最终 `ToolFailedOutcome.result.hint` 中保留该 ref。
- Finding 2：成立。duplicate governance 条件重复。已合并为单次条件判断，同时保留 `duplicate_governed` 语义。
- Finding 3：成立。resolve wait 幂等记录写入隐含假设 `started_event_id` 非空。已抽出 `_resolve_created_event_ref`，resume / terminal 路径缺失对应 event ref 时以 `INTERNAL_ERROR` fail closed。
- Finding 4：成立。已在 `TruncationManager` docstring 和 Host README 说明 cursor 为 run-scoped、短生命周期、single-use。

## Deferred

- repo-review-20260519-182226 Finding 2：`ToolFactAcceptCandidate` God dataclass。风险是维护性和字段聚合复杂度，不是当前运行时 correctness blocker。拆分会牵动 accept candidate 构造、验证、测试矩阵，适合作为后续独立结构重构切片，PR-62 accepted-fix 不半拆。
- repo-review-20260519-182226 Finding 7：compact 失败最终降级路径。当前 operation 会返回明确 failure reason，dispatch/proactive 路径已有失败事件与 fail-unstarted 收口；reactive/proactive 策略仍值得单独做端到端 failure matrix。本轮不扩大 context governance 编排范围。
- repo-review-20260519-182226 Finding 10：`LaneController.close()` / `acquire()` 竞态。属于 `dayu.runtime` 并发 primitive，不在 PR-62 Host accepted-fix 主路径；有 TTL 兜底，后续应以 runtime lane 独立并发测试切片处理。
- repo-review-20260519-182226 Finding 11：`_execute_batch` 捕获 executor 普通异常缺日志。当前行为会转为工具失败 outcome，不影响 Host 终态一致性；后续可做 Engine observability 小切片。
- repo-review-20260519-182226 Finding 13：`dayu.runtime.log` import 副作用。低风险全局 logging 命名注册，且非 Host/Engine correctness blocker，延后到 runtime 日志清理切片。
- repo-review-20260519-182223 Finding 5：durable bootstrap DDL 原子性。`IF NOT EXISTS` 与 schema version 已具备恢复能力；改事务边界需覆盖 bootstrap / fresh DB 测试，延后到 durable bootstrap 切片。
- repo-review-20260519-182223 Finding 6：after-commit callback 多错误诊断聚合。属于 observability 改善，不影响 committed durable truth，延后。
- repo-review-20260519-182223 Finding 7：service/ui 测试缺失。当前仓库未实现 service/ui Python 层，finding 对当前代码不可执行。
- repo-review-20260519-182223 Finding 8：Host crash recovery 端到端测试。是真实测试缺口，但需要多进程/强杀式测试设计，超出 accepted-fix 范围。
- repo-review-20260519-182223 Finding 9：敏感异常 marker 精度。当前偏保守 redaction 只会过度脱敏，非 correctness blocker。
- repo-review-20260519-182223 Finding 10：open_host fallback 8192/1024 常量。已有内部 fallback 说明；生产应显式传入 policy，后续配置治理切片处理。
- repo-review-20260519-182223 Finding 11：session watch 20ms 轮询。性能优化项，当前无 correctness 回归证据。
- repo-review-20260519-182223 Finding 12：import boundary 测试 helper 重复。测试维护性重构，非 PR-62 blocker。

## 验证结果

- `pytest -q tests/host/test_import_boundary.py::test_host_engine_imports_stay_on_allowed_boundary_modules tests/host/test_public_cancel_smoke.py::test_active_cancel_emits_public_cancel_event tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_fact_enters_memory_and_next_run_input`：修改前 3 failed，确认 Findings 14/15/16 非 stale。
- `pytest -q tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_durable_validation.py tests/contracts/test_tool_outcome_exhaustive.py tests/host/test_toolruntime_executor.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_engine_ingest_mapping.py tests/engine/test_agent_phase2.py tests/host/test_public_cancel_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_import_boundary.py`：160 passed。
- `pyright dayu/contracts/tool_await.py dayu/contracts/tool_outcome.py dayu/engine/agent.py dayu/host/compaction_budget.py dayu/host/dispatch.py dayu/host/durable/_validation.py dayu/host/engine_ingest.py dayu/host/fake_compaction.py dayu/host/llm_compaction.py dayu/host/tool_runtime.py dayu/host/waiting.py tests/contracts/test_tool_outcome_exhaustive.py tests/engine/test_agent_phase2.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_durable_validation.py tests/host/test_engine_ingest_mapping.py tests/host/test_import_boundary.py tests/host/test_llm_compaction.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_resolve_wait_command.py tests/host/test_toolruntime_executor.py`：0 errors, 0 warnings。
- `git diff --check`：通过。
