# PR 54 Full-Repo Review Accepted Fix Artifact

## Gate

- Current gate: PR 54 full-repo review accepted-fix gate
- Worker: AgentCodex
- Source adjudication: `docs/reviews/repo-review-controller-adjudication-20260515.md`
- Source review artifacts:
  - `docs/reviews/repo-review-20260515-1338.md`
  - `docs/reviews/repo-review-20260515-1346.md`

## Summary

已完成 controller accepted-current A1-A10，未处理 rejected / deferred 项。

- A1 已修复：`dayu.runtime.lane` 的 shielded claim / release 路径在外层取消后等待 release task 收口；tracked token release 成功后同步更新 `token.released`、`_held_tokens` 并唤醒等待者；untracked best-effort release 失败时记录错误并重新抛出 `CancelledError`。
- A2 已修复：`HostDispatchScheduler._drain_loop` 不再在 empty / sleep 二次检查后提前退出，后台 drain loop 持续轮询直到 scheduler close。
- A3 已修复：`BatchToolExecutionRequest` 构造期拒绝重复 `tool_call_id`。
- A4 已修复：`is_retriable` 增加 `assert_never` 穷尽守卫，并覆盖 `CONTEXT_LENGTH_EXCEEDED` 不重试分支。
- A5 已修复：`ToolCancelledOutcome` 构造期拒绝空字符串 / 纯空白 `hint`。
- A6 已修复：`wait_for_or_cancel` docstring 明确说明会读取 `pending.result()` 并透传 pending 异常。
- A7 已修复：`_HostCancellationToken` 显式声明实现 `CancellationToken`。
- A8 已修复：新增 Host 内部 `_event_payload.py`，统一 `run_input.py` 与 `engine_ingest.py` 的 EventLog payload object / required text 读取逻辑。
- A9 已修复：新增 Host 内部 `_public_validation.py`，统一 `api.py` 与 `tooling.py` 的 public string validation helper。
- A10 已修复：`run_input.py` 删除 A8 后不再需要的 `json` / `cast` 死导入。

## Files Changed

Production:

- `dayu/runtime/lane.py`
- `dayu/runtime/cancellation.py`
- `dayu/contracts/tool_call.py`
- `dayu/contracts/tool_outcome.py`
- `dayu/engine/runners/openai/error_classifier.py`
- `dayu/host/dispatch.py`
- `dayu/host/api.py`
- `dayu/host/tooling.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/_event_payload.py`
- `dayu/host/_public_validation.py`

Tests / docs:

- `tests/runtime/test_lane.py`
- `tests/contracts/test_tool_call.py`
- `tests/contracts/test_tool_outcome_exhaustive.py`
- `tests/engine/runners/openai/test_http_error_classification.py`
- `tests/host/test_dispatch_scheduler.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/repo-review-fix-host-p5-full-repo-codex-20260515.md`

## Validation

Targeted affected tests:

```bash
source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/contracts/test_tool_call.py tests/contracts/test_tool_outcome_exhaustive.py tests/engine/runners/openai/test_http_error_classification.py tests/host/test_dispatch_scheduler.py tests/host/test_public_contracts.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py -q
```

Result: `126 passed in 1.00s`.

Required aggregate tests:

```bash
source .venv/bin/activate && pytest tests/host tests/runtime tests/contracts tests/engine -q
```

Result: `741 passed in 6.91s`.

Required type check:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Required whitespace check:

```bash
git diff --check
```

Result: passed with no output.

## Documentation Decision

- Updated `dayu/host/README.md` because Host dispatch scheduler behavior changed: drain loop now keeps polling until scheduler close to avoid empty / sleep wakeup loss.
- Updated `tests/README.md` because runtime lane and Host dispatch scheduler test coverage facts changed.
- Did not update `dayu/engine/README.md`: the Engine change is an internal exhaustive guard for an already documented error enum and does not change public Engine behavior.
- Did not update `dayu/README.md`: no layering, assembly, public runtime capability, or terminology boundary changed.

## Residual Risk

- A1 still treats release failure during cancellation as best-effort cleanup for untracked claims; leaked DB rows rely on existing TTL cleanup, matching controller adjudication.
- `_release_token` preserves memory / DB consistency after successful shielded release under a single outer cancellation. Repeated external cancellation while waiting for the release task is not separately modeled in tests.
- A2 changes the drain loop from opportunistic exit to persistent polling until close. This is intended by adjudication, but idle schedulers now keep one sleeping task alive until explicit `close()`.
