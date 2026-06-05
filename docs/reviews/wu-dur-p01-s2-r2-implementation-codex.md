# WU-DUR-P01-S2-R2 Implementation Report

## 结论

已按 `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md` 完成实现。Host 现在通过追加式 `RUNNER_CALL_INPUT_ITERATION_LINKED` 把 ordinary prepared runner-call manifest 与 Engine `ITERATION_STARTED` observation 显式关联；不再依赖 `payload_iteration_id is None and iteration_index == 0` 的间接猜测。

## Slice 0 设计同步

- `docs/host/design.md` 增加 `RUNNER_CALL_INPUT_ITERATION_LINKED` canonical event contract。
- `ENGINE_EVENT_REJECTED` 纳入 design sync 范围，明确其只表达 ingest fail-closed diagnostic 与 worker stream stop signal，不驱动 Run / Attempt 状态。
- 明确 `RUNNER_CALL_INPUT_ASSEMBLED.validation_status="complete"` 只表示 prepared manifest 完整；`RUNNER_CALL_INPUT_ITERATION_LINKED.validation_status="complete"` 才表示 Engine-linked complete。
- 明确 missing、ambiguous、mismatch、link conflict 的 reason 语义、使用边界与 fail-closed 行为。

## Slice 1 Host Engine Ingest

- `dayu/host/engine_ingest.py` 新增当前 attempt / execution 范围内的 link resolution。
- ordinary manifest candidate 只接受 `validation_status=complete`、`iteration_id is None`、`iteration_index is None`、`compactor_identity is None` 且 kind 属于 `initial_user_dispatch` / `followup_user_dispatch` / `post_compaction_dispatch`。
- 已 linked manifest 通过 accepted link anti-join 排除，不再按 manifest 总计数推断 continuation。
- missing、ambiguous、mismatch、link conflict 均写入 `ENGINE_EVENT_REJECTED(..., stop_worker_stream=true)` 并 fail closed。
- mismatch 场景在同一 Host transaction 内追加 mismatch link 与 rejected diagnostic，不追加 accepted `ITERATION_STARTED` preview。
- 既有 link 的 `validation_status` 不是 `complete` 时，即使 Engine observation 字段与 link 一致，重放也继续返回 `ENGINE_EVENT_REJECTED(reason="runner_call_manifest_mismatch", stop_worker_stream=true)`，不得追加 accepted `ITERATION_STARTED` preview。
- accepted link 场景在同一 Host transaction 内追加 link 与 preview，preview payload 接收 link resolution result。
- continuation reset `iteration_index == 0` 只有在当前 attempt / execution 已有 `validation_status=complete` 的 accepted link 或 accepted `ITERATION_STARTED` preview 且无 unlinked prepared ordinary manifest 时，才写 limited-signal manifest，并标记为 `tool_result_continuation`。
- mismatch link 与 `ENGINE_EVENT_REJECTED` 都不能 seed continuation prior observation；mismatch 后的新 iteration 仍按 missing prepared manifest fail closed。
- 未让 Engine 携带 Host manifest id，未回写旧 manifest body / payload / digest。
- 删除旧 `_find_runner_call_manifest_event` / `_runner_call_manifest_matches_iteration` matching 路径。

## Slice 2 测试

`tests/host/test_engine_ingest_mapping.py` 增加覆盖：

- prepared manifest 正常 link，并把 link refs 投影到 preview validation。
- message count mismatch 与 role digest mismatch 均 fail closed；同一 rejected candidate 重放仍 rejected，link / rejected event 保持幂等，不追加 `ITERATION_STARTED` preview。
- mismatch link 不会 seed continuation；mismatch rejected 后的新 iteration 若没有 unlinked prepared manifest，仍返回 `missing_runner_call_manifest`，不写 limited-signal manifest 或 preview。
- 首个 iteration 缺少 prepared manifest fail closed。
- rejected event 不会 seed continuation prior observation。
- ambiguous prepared manifest fail closed。
- existing link conflict fail closed。
- ordinary dispatch kind 闭集覆盖 initial / followup / post-compaction。
- compactor manifest 不会被 ordinary Engine iteration 误收。
- continuation reset `iteration_index == 0` 只在 accepted prior observation 后写 limited-signal manifest。

## Slice 3 README / Control Doc

- `dayu/host/README.md` 同步 prepared complete 与 Engine linked complete 的区别，以及 link / fail-closed 行为。
- `tests/README.md` 同步新增测试覆盖范围。
- `docs/host/issues-implementation-control.md` 将 `WU-DUR-P01-S2-R2` residual risk 标记为 closed，并指向本报告。

## 验证

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -k "iteration_started or runner_call_manifest"
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_public_tool_wiring_smoke.py -k "runner_call or tool_wiring or system"
source .venv/bin/activate && pyright
rg "_runner_call_manifest_matches_iteration|payload_iteration_id is None and iteration_index == 0" dayu/host/engine_ingest.py
git diff --check
```

最新结果：

- Engine ingest focused tests：12 passed。
- RunInputBuilder / Tool Trace / public tool wiring selected tests：10 passed。
- pyright：0 errors。
- static fallback `rg`：无匹配。
- `git diff --check`：通过。

2026-06-05 follow-up bugfix 后重跑：

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -k "iteration_started or runner_call_manifest"
source .venv/bin/activate && pyright
rg "_runner_call_manifest_matches_iteration|payload_iteration_id is None and iteration_index == 0" dayu/host/engine_ingest.py
git diff --check
```

结果：

- Engine ingest focused tests：12 passed。
- pyright：0 errors。
- static fallback `rg`：无匹配。
- `git diff --check`：通过。

2026-06-05 follow-up prior-observation bugfix 后重跑：

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -k "iteration_started or runner_call_manifest"
source .venv/bin/activate && pyright
rg "_runner_call_manifest_matches_iteration|payload_iteration_id is None and iteration_index == 0" dayu/host/engine_ingest.py
git diff --check
```

结果：

- Engine ingest focused tests：13 passed。
- pyright：0 errors。
- static fallback `rg`：无匹配。
- `git diff --check`：通过。

## 剩余风险

- Tool Trace 当前仍只强制投影 prepared manifest reconstruction signal；link event 是 durable truth，但最小实现不要求 Tool Trace 投影 link event。
- 本次未修改 Engine contract，Engine 仍只提供 `ITERATION_STARTED` observation；Host manifest id 保持 Host-only。
