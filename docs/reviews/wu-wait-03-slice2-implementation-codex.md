# WU-WAIT-03 Slice 2 Implementation

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: implementation
- Slice: Slice 2 - Fins Adapter/Runtime Mapping And Provider-focused Tests
- Accepted plan: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Accepted Slice 1 commit: `4e661cee`
- Artifact path: `docs/reviews/wu-wait-03-slice2-implementation-codex.md`

本 slice 只实施 Fins process-local observation cleanup 到 Host external job lifecycle result contract 的映射，并补充 Fins provider-focused tests。未进入 code review、commit、push、PR 或后续 gate。

## Changed Files

- `dayu/fins/ingestion/wait_adapter.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `docs/reviews/wu-wait-03-slice2-implementation-codex.md`

未修改 `docs/host/issues-implementation-control.md`；该文件的既有脏改属于 controller bookkeeping。

## Exact Behavior Changes

- `FinsIngestionWaitPollAdapter.abandon_wait(...)` 现在返回 `WaitExternalJobLifecycleResult`。
- 有效 observation handle：
  - 先调用 `cancel_observation(handle)`；
  - 若取消后不是 `LOST`，再调用 `abandon_observation(handle)`；
  - 返回 `WaitExternalJobLifecycleApplied(action=ABANDON, message=...)`。
- corrupt / unparsable token：
  - 不调用 runtime；
  - 返回 `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`。
- observation missing 或 runtime 返回 `LOST`：
  - 返回 `WaitExternalJobLifecycleNoop(reason="observation_missing")`；
  - 不继续调用 `abandon_observation(...)`。
- 非 transient observation error：
  - `PERMANENT_NOT_FOUND` 映射为 `observation_missing`；
  - 其它稳定错误分类映射为 `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind_value>")`。
- `TRANSIENT_UNAVAILABLE` 保持 re-raise，交给 Host poller 写 `ABANDON_ERROR` 并按既有 backoff 重试。
- lifecycle result message 不包含 Host wait id、adapter key、tool call id 或 observation handle id。

## Tests And Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q
```

结果：`125 passed, 3 warnings in 4.65s`。warnings 为现有 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q
```

结果：`35 passed in 0.75s`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 提示有新版本可用。

```bash
git diff --check
```

结果：通过，无输出。

## Test Coverage Added Or Updated

- 更新 `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation`，断言 returned lifecycle result 为 `ABANDON` applied，并保留 cancel + abandon 调用断言。
- 更新 corrupt token test，断言 `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")` 且不调用 runtime。
- 新增 missing observation test，断言 `WaitExternalJobLifecycleNoop(reason="observation_missing")`。
- 新增 runtime returns `LOST` test，断言 `WaitExternalJobLifecycleNoop(reason="observation_missing")`。
- 新增 non-transient observation error test，断言 `WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`。
- 新增 `TRANSIENT_UNAVAILABLE` re-raise test；Host retry/backoff 语义由 Host focused tests 保持覆盖。
- 新增 prepared observation cancel + abandon before activation runtime test，证明后续 activation 不提交 executor 且本地 handle 已释放。
- 新增 submitted observation abandon runtime test，证明 abandon 会触发 cooperative cancellation check、释放本地 handle，并保留已写入 Fins storage 的源文档 artifact。

## Docs Decision

- 已按触发规则读取 `dayu/fins/README.md` 的 Agent 更新约束。
- 已按触发规则读取 `tests/README.md` 的 Agent 更新约束。
- 本 slice 不更新 README：
  - Fins README 已记录 Fins wait adapter 是 Host wait integration、只映射 observation snapshot / cleanup、不写 Host durable truth；本次是既有边界内的 Host lifecycle result mapping，不改变 Fins package 的稳定对外入口或架构边界。
  - tests README 只记录测试分层、运行方式与维护约定；本次只在既有 Fins ingestion runtime/tools 测试文件中补覆盖，不新增测试层级或维护约定。

## Deferred Findings Closed

- Closed: `docs/reviews/wu-wait-03-slice1-code-review-controller-adjudication.md` 中 `FinsIngestionWaitPollAdapter.abandon_wait` return type `deferred-with-owner`。
- Closure evidence: Fins adapter method signature 已改为返回 `WaitExternalJobLifecycleResult`，并由 Fins focused tests 与 pyright 验证。

## Residual Risks And Owners

- Fixed in current slice: Fins adapter corrupt token、missing/LOST、non-transient error、transient retry 与 valid handle applied result mapping。
- Fixed in current slice: Fins prepared/submitted observation abandon 的 process-local best-effort cancellation 与 handle release 行为测试覆盖。
- Covered by existing Host tests: `TRANSIENT_UNAVAILABLE` re-raise 后 Host poller `ABANDON_ERROR` backoff / retry 语义。
- No unclassified residual risk for this slice.

## Completion Status

Implementation slice complete. Per user instruction, stop after implementation slice gate; do not enter code review or later gate.
