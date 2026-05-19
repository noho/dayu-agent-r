# P10.5 Slice 3 Follow-up Re-Review Artifact

## Gate

P10.5 Slice 3 follow-up re-review。

## Review Target

controller adjudication accepted follow-up fix（F1: 测试 helper baseline 迁移、F2: fix artifact 更新）的实现是否正确完成且未引入新 blocker。

## Review Inputs

- Controller adjudication: `docs/reviews/phase10-5-slice3-rereview-controller-adjudication-20260518.md`
- Fix artifact: `docs/reviews/phase10-5-slice3-fix-codex-20260518.md`
- MiMo re-review: `docs/reviews/phase10-5-slice3-rereview-mimo-20260518.md`
- DS re-review: `docs/reviews/phase10-5-slice3-rereview-ds-20260518.md`
- 总控文档: `docs/host/implementation-control.md`

## Review Focus

### 1. test_admission_queue.py helper baseline 注入

**Verdict: CORRECT。**

**Evidence:**

1. `_service()` helper（line 1253-1277）新增 `ordinary_run_baseline=_ordinary_run_baseline()` 和 `tooling_options=None` 两个参数传递给 `create_host_admission_service`。

2. 新增 `_ordinary_run_baseline()` helper（line 1280-1311）构造完整的 `OrdinaryRunExecutionBaseline`，含 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`，字段值合理（`max_iterations=1`、`allow_tool_calls=False` 等）。

3. baseline 注入不改变原有 queue / promotion / cancel / closeout 断言语义：
   - 所有 24 个调用 `_service()` 的测试点（line 244, 277, 322, 361, 394, 456, 495, 537, 581, 605, 653, 714, 782, 820, 853, 884, 922, 979, 1024, 1066, 1106, 1145, 1213, 1235）通过同一 `_service()` helper 获得 baseline，签名未变。
   - `_followup_request()` 从旧 `input=HostInput(...)` 迁移到 Slice 3 新 `SubmitFollowupRequest` 字段（`system_prompt`、`user_prompt`、`tool_names`、`runner_spec`、`runner_options`、`agent_policy`），与 Slice 3 public contract 一致。
   - 断言内容（`RunStatus`、`AttemptStatus`、`DispatchRecordStatus`、event type 序列、idempotency 行为、promotion 行为、wakeup 行为）未改变。

4. `_followup_request()` 迁移（line 1536-1548）：旧 `input=HostInput(display_text=display_text, payload_ref=None, payload_digest=None)` 替换为 `system_prompt=None, user_prompt=display_text, tool_names=None, runner_spec=None, runner_options=None, agent_policy=None`。语义等价，与 Slice 3 `SubmitFollowupRequest` 公共契约一致。

### 2. test_projection_read_model.py baseline-aware test handle

**Verdict: CORRECT。**

**Evidence:**

1. `_host_with_ordinary_baseline()` helper（line 105-152）手工装配：
   - `open_host_durable_store(HostDurableStoreOptions(...))` — 显式打开 durable store
   - `create_host_admission_service(transaction_runner, ordinary_run_baseline=..., tooling_options=None)` — baseline-aware admission
   - `ActiveWorkerRegistry()` — 空 registry
   - `try/except` 保护：构造失败时 `durable_store.close()` 防止资源泄漏

2. 只用于正常 `submit_followup` read-model 测试：
   - `test_user_input_timeline_preserves_repeated_text_and_null_fallback`（line 773）— 调用 `submit_followup`
   - `test_cancelled_input_and_later_input_remain_separate_items`（line 855）— 调用 `submit_followup`
   - 其余 11 个测试继续使用 `create_host_command_handle(_options(tmp_path))`，不调用 `submit_followup`，无需 baseline。

3. durable resource 关闭：
   - `try/finally: host.close()` 在两个使用点（line 773/813, 855/883）正确关闭 handle。
   - `HostCommandHandle.close()` 关闭其持有的 `durable_store`。

4. 未改变生产 `create_host_command_handle` 或 public API：
   - `create_host_command_handle` 继续使用 `_options(tmp_path)`（不含 `local_execution`），不传入 baseline。
   - `_host_with_ordinary_baseline` 是测试内私有 helper，不暴露到生产代码。

5. `_followup_request()` 迁移（line 264-276）：同 test_admission_queue.py，从旧 `input=HostInput(...)` 迁移到 Slice 3 新字段。

### 3. 无 baseline misuse contract 覆盖

**Verdict: MAINTAINED。**

`tests/host/test_effective_execution_config.py::test_submit_followup_without_ordinary_baseline_fails_before_dispatch`（line 322-345）继续覆盖低层 `create_host_command_handle` 路径缺少 `ordinary_run_baseline` 时的 fail-early contract：
- `HostApiErrorCode.INVALID_STATE`
- `"ordinary Run baseline"` in message
- factory.requests == []（dispatch 前失败）

该测试未被修改。

### 4. 必跑验证

**Verdict: PASS。**

```text
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
→ 47 passed in 0.52s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations
```

47-test 集合全通过（test_admission_queue: 24, test_projection_read_model: 12, test_submit_followup_public_contract: 3, test_per_run_tool_selection: 4, test_effective_execution_config: 4）。pyright 零报错。

### 5. 新 correctness / stability / maintainability blocker

**Verdict: NONE。**

## Follow-up Fix Scope Verification

controller adjudication 允许范围：
- `tests/host/test_admission_queue.py` — **已修改**：`_service()` 注入 baseline，新增 `_ordinary_run_baseline()`，`_followup_request()` 迁移到 Slice 3 字段
- `tests/host/test_projection_read_model.py` — **已修改**：新增 `_host_with_ordinary_baseline()` 和 `_ordinary_run_baseline()`，两个 `submit_followup` 测试切换到 baseline-aware handle，`_followup_request()` 迁移到 Slice 3 字段
- `docs/reviews/phase10-5-slice3-fix-codex-20260518.md` — **已更新**：Follow-up Fix section 记录了 baseline 迁移和 misuse test 保留

禁止范围：
- 生产代码（`dayu/host/*`）— **未修改**（diff 确认生产代码变更均为原始 Slice 3 fix，非 follow-up fix）
- public API / payload shape / digest / ref / durable schema / state machine — **未改变**
- README — **未修改**（controller adjudication 禁止）

## Fix Artifact Verification

`docs/reviews/phase10-5-slice3-fix-codex-20260518.md` Follow-up Fix section（line 19-23）准确记录：
1. test_admission_queue.py `_service()` helper 已迁移到 ordinary baseline 边界
2. test_projection_read_model.py 新增 `_host_with_ordinary_baseline()` helper，未修改生产 `create_host_command_handle()`
3. 无 baseline fail-early test 保留

Residual Risk section（line 43-45）准确声明：
- 既有测试 helper 已迁移
- `OpenHostOptions` 不允许 baseline=None，public 路径无缺口
- 未做 schema migration / public API 扩展

## Positive Observations

1. **测试 helper 迁移精准**：只修改了调用 `submit_followup` 路径的测试 helper，不调用 `submit_followup` 的测试（如 `test_terminal_event_projects_run_result`、`test_repair_rebuilds_rows_after_deletion` 等）保持使用 `create_host_command_handle`，避免过度修改。

2. **durable resource 管理正确**：`_host_with_ordinary_baseline()` 使用 `try/except` 保护 `HostCommandHandle` 构造失败场景，`try/finally: host.close()` 在使用点正确关闭。

3. **baseline 隔离**：每个测试文件维护独立的 `_ordinary_run_baseline()` helper（admission 用 `"admission-baseline-model"`、projection 用 `"projection-baseline-model"`），避免跨文件 baseline 值耦合。

4. **`_followup_request()` 一致性迁移**：两个测试文件的 `_followup_request()` 均从旧 `input=HostInput(...)` 迁移到 Slice 3 新字段，与 `SubmitFollowupRequest` 公共契约一致。

## Verdict

**PASS**。Blocking count = 0。

### Summary

| 项目 | 状态 |
| --- | --- |
| F1: test_admission_queue.py baseline 注入 | 完成，24 个测试 helper 正确迁移 |
| F1: test_projection_read_model.py baseline-aware handle | 完成，2 个 submit_followup 测试正确迁移 |
| F2: fix artifact 更新 | 完成，Follow-up Fix section 记录完整 |
| 无 baseline misuse contract | 保持，dedicated fail-early test 未修改 |
| 47-test 集合 | 47 passed |
| pyright | 0 errors |
| 生产代码 | 未修改 |
| Public API / payload / schema / state machine | 未改变 |
| 新 Blocker | 0 |

### Non-blocking findings

无。

## Artifact Path

`docs/reviews/phase10-5-slice3-followup-rereview-mimo-20260518.md`
