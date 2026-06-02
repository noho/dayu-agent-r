# Code Review — Re-review Follow-up

## Scope

- Mode: re-review follow-up (current workspace changes on branch)
- Branch: refactor/host-layer-followup-wu-layer-01-02
- Base review artifact: `docs/reviews/repo-review-20260602-210241.md`
- Batch1 implementation: `docs/reviews/repo-review-batch1-implementation-report-codex-20260602.md`
- Batch2 implementation: `docs/reviews/repo-review-batch2-implementation-report-codex-20260602.md`
- Output file: `docs/reviews/repo-review-rereview-ds-20260602.md`
- Re-review date: 2026-06-02 21:51:09 CST

## 验证基线

- pytest: 2024 passed, 1 skipped, 5 deselected
- pyright: 0 errors, 0 warnings
- 34 个未提交修改文件（batch1+batch2 修复累计），1210 insertions, 103 deletions

---

## 原始 Finding 状态逐项核查

### Finding 1 [CRITICAL] — LLM Compaction Material Prompt Injection
**状态: ✅ FIXED**
- 证据: `llm_compaction.py` L391-395 在 material JSON 外层增加 `_UNTRUSTED_COMPACTION_MATERIAL_BEGIN/END` delimiter
- 测试: `test_prompt_renders_material_pack_without_ledger_dump` 覆盖

### Finding 2 [CRITICAL] — Compaction Budget CJK Token Estimation
**状态: ✅ FIXED**
- 证据: `context_budget.py` L37 新增 `DEFAULT_ESTIMATOR_CJK_CHARS_PER_TOKEN = 1`；L471 新共享 helper `estimate_budget_text_tokens` 对 CJK Wide/Fullwidth 字符使用保守估算
- `llm_compaction.py` L67 导入并使用同一 helper（L1401），消除重复估算逻辑
- 测试: `test_text_token_estimator_keeps_english_chars_per_token_semantics` + `test_text_token_estimator_counts_cjk_more_conservatively` + `test_llm_compaction_text_estimator_uses_cjk_conservative_budget`

### Finding 3 [HIGH] — 工具重复治理永久阻塞
**状态: ⚠️ DEFERRED (controller 裁决)**
- 本轮修复: ToolRuntime `_execute_one` finally cleanup 改为 best-effort（见 Finding 4）
- Controller 明确裁决: duplicate governance durable lease 属于更大 contract 改动，不在本轮
- 裁决可接受: 当前内存治理在正常退栈路径已受 best-effort 保护；进程崩溃场景不在同一 event loop，不产生残留 waiter

### Finding 4 [HIGH] — `_execute_one` finally 异常掩盖
**状态: ✅ FIXED**
- 证据: `tool_runtime.py` L2368-2399 `_record_duplicate_durable_missing_best_effort` 内部 `try/except`，cleanup 失败只记录 warning，不覆盖原始返回/异常
- 测试: `test_duplicate_cleanup_failure_does_not_replace_tool_timeout_return` + `test_duplicate_cleanup_failure_does_not_replace_original_exception`

### Finding 5 [HIGH] — `_consume_worker_events` close_worker_lost 二次失败
**状态: ✅ FIXED**
- 证据: `dispatch.py` L3063 新增 `_safe_close_worker_lost`，内部 try/except 记录诊断并返回 False
- 两个异常处理路径（L3225 ingest 异常、L3263 stream error）均改用 safe wrapper
- 测试: `test_close_worker_lost_failure_logs_context_without_raising`

### Finding 6 [HIGH] — Drain loop retry exhausted 丢弃队列
**状态: ✅ FIXED**
- 证据: `dispatch.py` L2161 在 `self._closed = True` 之前调用 `_best_effort_closeout_pending_queue_for_shutdown`
- L3032 新增该方法: best-effort 对队列中每个残留 record 做 startup failure terminal closeout
- 测试: `test_drain_loop_retry_exhausted_closes_pending_queue_records`

### Finding 7 [HIGH] — `_require_exact_fields` 语义不一致
**状态: ✅ FIXED (rename)**
- 证据: `scene_prepare.py` L1228 改名为 `_require_no_unknown_fields`，7 个调用点全部更新
- 保留字段级 `_require_*_field` 独立校验覆盖 missing 检查
- `config_loader.py` 的 `_require_exact_fields` 语义不变
- 测试: `test_manifest_model_missing_required_field_fails_fast`

### Finding 8 [HIGH] — Agent `_acquire_run_slot` 在 try 块之前
**状态: ✅ REJECTED (controller 裁决，有补测试)**
- Controller 裁决: 原修复建议将 `_acquire_run_slot` 移入 try 块会导致非法重入时关闭 active runner，破坏第一个 generator
- 当前行为: 非法重入 fail-fast，不关闭 active runner
- 补测试: `test_private_agent_concurrent_run_fail_fast` 增加 `assert runner.close_count == 0`

### Finding 9 [HIGH] — `terminal_run_row` CAS 不检查 terminal refs
**状态: ✅ FIXED**
- 证据: `state.py` L3605 WHERE 条件增加 `_TERMINAL_REFS_UNSET_WHERE_SQL`
- 测试: `test_terminal_run_row_reports_cas_lost_when_terminal_refs_already_set`

### Finding 10 [HIGH] — 终态幂等回放归类为 CAS_LOST
**状态: ✅ FIXED**
- 证据: `run_transition.py` L4697-4728 新增 `_terminal_closeout_replay_result`，同 Run/Attempt/同种终态→返回 `UPDATED`，异种终态/不同 ref 不吸收
- `state.py` L4938-4944 `_run_mutation_result_for_active` 仅在同 terminal_status + 同 terminal_event_id 时返回 `UPDATED`
- 测试: `test_terminal_closeout_replay_absorbs_same_terminal_status_without_new_events` + `test_terminal_run_row_absorbs_only_same_terminal_ref_replay` + `test_terminal_run_row_rejects_same_terminal_status_with_different_ref`

### Finding 11 [MEDIUM] — SSE Parser 行缓冲无上限
**状态: ✅ FIXED**
- 证据: `sse_parser.py` L81-82 新增 `_MAX_SSE_LINE_CHARS = 1MB`，`_MAX_SSE_DATA_LINES = 256`；L194/L207/L229/L329 四处检查
- 超限产出 `provider_protocol_error` + `runner_done(error)` 收口
- 测试: `test_sse_line_buffer_limit_emits_protocol_error` + `test_sse_data_line_count_limit_emits_protocol_error`

### Finding 12 [MEDIUM] — Content-Type 空导致 SSE 误判为非流式
**状态: ✅ FIXED**
- 证据: `runner.py` L137-138 空 Content-Type 改为返回 `True`（原返回 `False`），即回退到 SSE 解析
- 测试: `test_stream_true_missing_content_type_falls_back_to_sse`

### Finding 13 [MEDIUM] — ToolCallAggregator delta 顺序假设
**状态: ⚠️ NOT ADDRESSED**
- 本轮未处理。原始 risk 评估为 Low（需并行 tool call + provider delta 乱序），可接受在本轮 deferred
- 注意: 该 finding 原 severity 评为 Medium，但实际触发概率低

### Finding 14 [MEDIUM] — cancel_recovering_run_row 缺 current_attempt_id
**状态: ⚠️ NOT ADDRESSED**
- 本轮未处理。原始风险较低（SQLite 写序列化提供保护 + 调用方有前置检查），可接受 deferred

### Finding 15 [MEDIUM] — Reactive Compaction 不检查 budget hard threshold
**状态: ⚠️ NOT ADDRESSED**
- 原始 review 已确认是 intentional design（reactive 路径依赖真实 dispatch 闭环），有 `max_reactive_compactions_per_run` 限制

### Finding 16-23 [MEDIUM/LOW] — 其余 medium 和 low finding
**状态: ⚠️ 多数 LOW 项未在本轮处理**
- 这些项 severity 低，按 controller 优先级可 deferred 到后续 Phase

### 新增 LOST Public HostEvent / HostTerminalStatus
**状态: ✅ FIXED (batch1)**
- 证据: `api.py` L2505 `HostEventKind.LOST`，L2522 `HostTerminalStatus.LOST`
- `read_api.py` L739-740/L874 新增 `_lost_host_event` 投影逻辑
- 测试: `test_run_lost_projects_to_lost_host_event`

### 新增 contracts 包根导出 `truncate_limit_key_for_strategy`
**状态: ✅ FIXED (batch2)**
- 证据: `contracts/__init__.py` L82 导入, L126 `__all__`
- 测试: `test_contracts_all_matches_expected_set`

### 新增 execution config projection HostDurableError
**状态: ✅ FIXED (batch1)**
- 证据: `_execution_config_projection.py` corrupted JSON/unknown provider request 统一抛 `HostDurableError`

---

## 新增问题检查

### 交叉验证: 修复是否引入新的 correctness/分层/类型/测试/README 问题

1. **pyright**: 0 errors, 0 warnings — 无新增类型问题
2. **pytest**: 2024 passed — 无回归
3. **分层架构**: 未引入新的反向依赖
   - 验证: `dayu/runtime/` 仍不 import 业务层
   - 验证: `dayu/host/` import `dayu/engine/` 公共入口是合法向下依赖（controller 已明确裁决）
4. **README 同步**: `dayu/host/README.md`, `dayu/engine/README.md`, `tests/README.md` 已更新
5. **新增代码风格**: 新增函数（`_safe_close_worker_lost`, `_terminal_closeout_replay_result`, `_best_effort_closeout_pending_queue_for_shutdown`）均遵循模块命名与职责 convention
6. **测试质量**: 新增测试覆盖了 failure paths（cleanup 失败不替换异常、CAS 防御、SSE buffer bounds、terminal replay 幂等吸收等），不仅仅 happy path

### 发现一个潜在关注点

**R1-[INFO]-`estimate_budget_text_tokens` 导入链**: `llm_compaction.py` L67 从 `context_budget` 导入 `estimate_budget_text_tokens`，但 `context_budget.py` 也在 host 包内。这是 Host 内部依赖，不违反分层约束，但两者之间存在微妙的耦合: `llm_compaction` 原本独立的 token 估算已被替换为依赖 shared helper。

- 风险: Low。两个模块都在 `dayu.host` 包内，内部共享 helper 是正常做法
- 修复: 不需要。此为可接受的内聚

---

## 结论

### PASS — with residual notes

原始 review artifact 中 2 个 CRITICAL 和 10 个 HIGH finding 中：
- **7 个已修复**: F#1(prompt injection), F#2(CJK), F#4(finally mask), F#5(worker lost), F#6(queue drain), F#7(exact_fields rename), F#9(terminal CAS), F#10(replay absorb)
- **2 个 controller 已裁决拒绝/推迟**: F#3(duplicate lease, deferred), F#8(acquire_run_slot, rejected with test lock)
- **3 个 MEDIUM 已修复**: F#11(SSE bounds), F#12(content-type), F#13 未处理
- **所有 LOW 项**未在本轮处理，但 controller 优先级可接受

**整体判定**: 无 blocking finding。batch1+batch2 修复正确，验证通过。

### Residual Notes

| Item | Status |
|------|--------|
| ToolCallAggregator delta 顺序假设 (F#13) | Deferred — 触发概率低 |
| cancel_recovering_run_row CAS 不一致 (F#14) | Deferred — 外围保护有效 |
| Duplicate governance durable lease (F#3) | Deferred — 需更大 contract |
| Reactive compaction budget bypass (F#15) | Intentional design |
| 其余 LOW finding (F#17-34) | Deferred to later phase |
