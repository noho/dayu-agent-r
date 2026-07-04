# WU-WAIT-03 Slice 2 Fix

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: Slice 2 code-review fix
- Slice: Fins Adapter/Runtime Mapping And Provider-focused Tests
- Accepted plan: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Controller adjudication: `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md`
- Artifact path: `docs/reviews/wu-wait-03-slice2-fix-codex.md`

本 fix 只处理 controller accepted finding：为 Fins adapter 的 `cancel_observation(...)` 非临时错误路径补 focused regression test。未修改生产代码，未提交、未 push、未创建 PR、未关闭 issue。

## First-principles Judgment

动机成立。Accepted plan 明确要求 "Non-transient observation error during cancel or abandon" 映射为 `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`。Slice 2 既有测试已覆盖 abandon-side 非临时错误，但缺少 cancel-side 直接回归保护。

生产实现已由 code review 和 controller adjudication 裁决为正确；本轮没有直接失败证据证明生产代码错误。因此最佳修复是只补测试，不改 `dayu/fins/ingestion/wait_adapter.py`。

## Changed Files

- `tests/fins/test_fins_ingestion_tools.py`
- `docs/reviews/wu-wait-03-slice2-fix-codex.md`

未修改生产代码。工作区中 `dayu/fins/ingestion/wait_adapter.py`、`tests/fins/test_fins_ingestion_runtime.py`、`docs/host/issues-implementation-control.md` 及 Slice 2 review artifacts 已存在脏改，本 fix 未改动这些非本轮允许范围文件。

## Fix Details

新增测试 `test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop`：

- 使用 `_FakeObservationRuntime(cancel_errors={handle_id: FinsObservationPollError(FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE, ...)})`；
- 调用 `FinsIngestionWaitPollAdapter.abandon_wait(...)`；
- 断言返回 `WaitExternalJobLifecycleNoop`；
- 断言 `reason == "observation_error:permanent_corrupt_handle"`；
- 断言 `runtime.cancelled_handles == (handle.handle_id,)`；
- 断言 `runtime.abandoned_handles == ()`。

该测试证明 cancel 阶段发生稳定 observation 错误时，adapter 记录已尝试 cancel，但不会继续调用 abandon cleanup。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q
```

结果：`56 passed, 3 warnings in 1.59s`。warnings 为既有 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q
```

结果：`126 passed, 3 warnings in 3.79s`。warnings 为既有 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q
```

结果：`35 passed in 0.76s`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 提示有新版本可用：`v1.1.409 -> v1.1.411`。

```bash
git diff --check
```

结果：通过，无输出。

## README Decision

- 已读取 `tests/README.md` 的 Agent 更新约束。
- 本 fix 修改 `tests/fins/test_fins_ingestion_tools.py`，但只是既有 Fins ingestion tools 测试文件内的 focused regression test，不新增测试层级、运行方式、fixture 维护约定或测试目录职责。
- 因此不更新 `tests/README.md`。
- 本 fix 未修改 `dayu/fins/` 生产代码，因此不触发 `dayu/fins/README.md` 更新。

## Finding Status

| Finding | Decision | Fix status | Evidence |
|---|---|---|---|
| `cancel_observation(...)` 非临时错误路径缺少直接测试覆盖 | accepted | 已修复 | 新增 cancel-side `PERMANENT_CORRUPT_HANDLE` regression test，并通过 Fins / Host focused tests、pyright 和 `git diff --check`。 |

## Residual Risks

- fixed in current slice: cancel-side 非临时 observation error regression coverage 已补齐。
- existing accepted tradeoff: provider lifecycle cleanup 仍是 best-effort；cancel 成功但 abandon cleanup 失败时，Host cancellation correctness 不依赖 provider cleanup 完成。该风险已在 controller adjudication 中分类为 informational。
- existing deployment risk: poller-disabled 部署不会执行 external lifecycle adapter actions，仍依赖 durable Host cancellation truth。该风险已在 controller adjudication 中分类为 residual risk，不由本 focused test fix 改变。

无新增 unclassified residual risk。

## Completion Status

Slice 2 code-review fix gate complete for the accepted test coverage finding. Per user instruction, stop here: no commit, no push, no PR, no issue close, and no transition to later gate.
