# Code Review — WU-TOOLS-01-F01-02-R1 Slice 2 Implementation

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-01-f01-02-r1`
- **Base**: checkpoint commit `2634f361`（Slice 2 实现起点）
- **Accepted Slice 1 commit**: `e10f2e99`（不纳入本次 review）
- **Output file**: `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-ds.md`
- **Included scope**: `dayu/fins/ingestion_runtime.py` prepare/activate 实现路径、`dayu/fins/ingestion/observation_handle.py` 新增 protocol 方法、`dayu/fins/ingestion/wait_adapter.py` activation adapter 与 registry builder、`dayu/fins/tools/download_tools.py` / `preprocess_tools.py` / `upload_tools.py` callable 调用方改为 prepare-only、`dayu/fins/README.md` 状态流与入口文档更新、`tests/fins/test_fins_ingestion_tools.py` 与 `tests/fins/test_fins_ingestion_runtime.py` 新增与修改测试
- **Excluded scope**: `docs/host/issues-implementation-control.md`（仅作为状态上下文，不作为 implementation finding 目标）；已 merge Slice 1 代码；Codex implementation artifact（作为另一路 reviewer output 忽略）
- **Parallel review coverage**: 无（单 reviewer 全链路覆盖）

## Findings

### 1. DS-未修复-低-`_observation_cancelled_result` 的取消消息 language mix 与 safe-message 未调用

- **入口/函数**: `_observation_cancelled_result(message)` -> `FinsResultSummary(error_message=message)`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:4986-5002`
- **输入场景**: `cancel_observation` 对 prepared-but-not-submitted observation 调用时。
- **实际分支**: `cancel_observation()` 设置 `record.message = "Observation was cancelled before activation."`（英文），然后 `record.result = _observation_cancelled_result(record.message)`，其中 `title=_DIRECT_CANCELLED_MESSAGE` 是中文 "操作已取消"。`_observation_cancelled_result` 直接把传入的 `message` 作为 `error_message`，不经过 `_safe_observation_message()`。
- **预期行为**: 现有代码中 `_observation_failure_result` 与 `_mark_observation_failed` 均通过 `_safe_observation_message` 做安全截断；此处也应一致。
- **实际行为**: `error_message` 未经过 `_safe_observation_message` 截断。当前 hardcoded message 为 45 字符且在 240 字符上限之内，且不包含 `_DISALLOWED_TOKEN_FRAGMENTS` 禁止片段，因此**当前不产生实际危害**。但若未来 message 来源变为动态拼接（如含 ticker、source 等），则会绕过安全截断检查。
- **直接证据**: `_observation_cancelled_result`（行 4986-5002）直接使用传入 `message` 作为 `error_message`，而 `_observation_failure_result`（行 4963-4981）虽然也未调 `_safe_observation_message`，但其调用方 `_mark_observation_failed`（行 5009-5039）在调用前已通过 `_safe_observation_message` 预处理。相比之下，`cancel_observation` 中设置 `record.message` 和调用 `_observation_cancelled_result(record.message)` 之间没有安全截断步骤。
- **影响**: 当前无害，但防御深度缺口。如果未来 `cancel_observation` 中的 message 变成动态构造，可能 leak 内部 token、path 或 job 语义。
- **建议改法和验证点**: 在 `_observation_cancelled_result` 内部对 `message` 调用 `_safe_observation_message`，或将 message 传入前的截断责任明确到调用方 docstring 中。同时验证 `FinsResultSummary.__post_init__` 不会因为 message 包含禁止片段而抛异常。
- **修复风险（低）**: 改动仅增加一个安全截断调用，不改变行为。
- **严重程度（低）**: 当前硬编码消息安全，但防御深度不一致。

### 2. DS-未修复-低-`build_fins_wait_activation_registry` 的 `tool_names` 参数仅做 validation side-effect

- **入口/函数**: `build_fins_wait_activation_registry(tool_names=...)`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:226-250`
- **输入场景**: 装配时传入三个 Fins 工具名。
- **实际分支**: `_deterministic_tool_names(tool_names)` 校验并排序后，返回值被丢弃。activation registry 始终只注册一个 `WaitActivationAdapterRegistration`，使用固定 `FINS_INGESTION_WAIT_ADAPTER_KEY`，不按 tool 区分。
- **预期行为**: 函数签名暗示 `tool_names` 会影响 registry 构造行为；实际上仅做 fail-fast 校验。与 `build_fins_wait_adapter_registry` 的不对称（后者按 tool_name 逐条构造 binding）可能让后续维护者误以为 activation registry 也需要逐 tool 注册。
- **实际行为**: 丢弃校验结果，single-key registration。对于 Host 当前的单 key dispatch activation 机制是正确的，但代码意图不如直接接收 `tool_names` 做 validation 再明确丢弃清晰。
- **直接证据**: `_deterministic_tool_names(tool_names)` 返回值未被赋值（行 241），下一行直接构造 adapter。
- **影响**: 维护者可能误以为需要为每个 tool 构造独立 activation registration，在 Slice 3 Service wiring 中做多余工作。
- **建议改法和验证点**: 将 `_deterministic_tool_names(tool_names)` 改为不返回值的 `_validate_tool_names(tool_names)`，或在行 241 加注释说明 "validation only; single adapter key covers all Fins tools"。
- **修复风险（低）**: 纯重构，不改变行为。
- **严重程度（低）**: 代码可读性/维护性问题，无功能影响。

## 重点 Review 结论（无 finding 项，确认通过）

以下各项经逐行走读确认**无问题**：

### download / preprocess / upload callable prepare-only

- 三个 tool callable（`FinsDownloadToolCallable.__call__`、`FinsPreprocessToolCallable.__call__`、`FinsUploadToolCallable.__call__`）均改为调用 `runtime.prepare_observed_*` 而非 `runtime.start_observed_*`。
- `_prepare_observed_stream` 只登记 process-local observation record，不提交 executor（行 2474-2476）。executor submit 已从该方法移除（对比 Slice 1 的 `_start_observed_stream` 会在同方法内 submit）。
- `ToolAwaitingOutcome` shape 未变：resume token 仍是 `handle.handle_id`（opaque UUID 十六进制），`await_spec.await_kind` 仍是 `ToolAwaitKind.EXTERNAL_JOB`。
- 测试 `test_awaiting_tool_callables_prepare_without_executor_submit` 用 `_NoOpExecutor` 验证三个 callable 返回 `ToolAwaitingOutcome` 且 `executor.submitted_job_ids == ()`。

### activate_observation 幂等性

- `activate_observation` 在 `_observation_lock` 内检查三个条件（行 2392-2397）：`record.submitted`、`record.cancellation_state.is_cancelled()`、`record.status in _TERMINAL_OBSERVATION_STATUSES`。
- `record.submitted = True` 在 lock 内设置，在 `executor.submit` 调用之前。重复 `activate_observation` 看到 `submitted=True` 直接返回（行 2397）。
- `_TERMINAL_OBSERVATION_STATUSES` 包含 `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 四个终态。`cancel_observation` 也使用同一集合判断是否跳过状态修改（行 2341），确保 terminal 状态为 absorbing。
- 测试 `test_activate_observation_is_idempotent_for_same_handle` 验证两次 activation 只产生一次 executor submit。

### cancel/activate 锁协调

- `cancel_observation`（行 2337）与 `activate_observation`（行 2387）均通过 `with self._observation_lock` 获取同一把 `threading.Lock`。
- `cancel_observation` 的锁内逻辑（行 2341-2349）：若 `submitted=False` 且非终态，设置 `status=CANCELLED` 并构造 `result`；若 `submitted=True` 且非终态，只设置 message 不改变 status（让 producer 自己收口）。
- cancel-before-activate：cancel 先获取锁，设置 CANCELLED；activate 后获取锁，发现 `record.cancellation_state.is_cancelled()` 为 True 且 `record.status in _TERMINAL_OBSERVATION_STATUSES`，return early，不 submit。
- 测试 `test_cancel_prepared_observation_prevents_later_activation_submit` 验证：cancel 后 activate 不 submit，且 poll 返回 `CANCELLED`。
- 测试 `test_cancel_and_activate_share_observation_lock_without_timing_sleep` 用 `_HookedObservationLock` 替换 runtime 的 `_observation_lock`，双线程验证 cancel 持有锁时 activate 必须等待，且最终 `executor.operations == []`。这**确实证明了同一把锁在协调**，不是依赖 timing/sleep 的脆弱测试。

### activation submit failure 与 unexpected exception 收口

- `activate_observation` 的 `except Exception` 处理（行 2405-2414）：重新获取 `_observation_lock`，查找 `failed_record`，如果存在则调用 `_mark_observation_failed` 设置 `FAILED` 终态，然后 re-raise。
- `_mark_observation_failed` 使用 `_safe_observation_message` 截断消息（行 5031），不泄漏 raw provider/path/job/cursor/Host id。
- 若 `failed_record` 为 None（被 `abandon_observation` 在 submit 失败窗口内删除），不标记，异常仍 propagate。合理——abandon 意味着调用方主动放弃。
- 测试 `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter` 验证 `_FailingSubmitExecutor` 的 OSError 被 raise 后，现有 `FinsIngestionWaitPollAdapter.poll_wait` 返回 `WaitPollReady(ResolveWaitFailedOutcome)`。
- 测试 `test_unexpected_activation_exception_terminalizes_prepared_observation` 验证 `ValueError` 被 raise 后，`poll_observation` 返回 `status=FAILED` 且 `result.error_message="Observation activation failed."`。

### LLM-facing output 安全

- 所有 observation snapshot message 均经过 `_safe_observation_message` 或为 hardcoded 常量（如 `"Observation activation failed."`、`"Observation was cancelled before activation."`）。
- `_safe_observation_message` 通过 `_DISALLOWED_TOKEN_FRAGMENTS` 禁止 `job`、`sequence`、`cursor`、`resume`、`token`、`tool_call`、`storage`、`.dayu`、`/`、`\` 等片段；长度限制 240 字符（`_MESSAGE_MAX_CHARS`）。
- resume token 始终是 `finsjob_` 前缀的 UUID hex 格式，不包含 path/cursor/job id。
- `FinsResultSummary` title 使用中文常量（`"操作已取消"`、`"操作失败"`），不暴露实现细节。
- 确认：`_DISALLOWED_TOKEN_FRAGMENTS` 的禁止片段覆盖了 Host id（`host` 不在禁止列表中，但这是故意的——"host" 是合理的英文词汇，不应被禁止；Fins 层面不暴露 Host identifier）。

### FinsIngestionWaitActivationAdapter 边界

- `activate_accepted_wait` 只做两件事：`parse_observation_handle_id_token(request.await_spec.resume_token)` 解析 token + `self.runtime.activate_observation(handle)` 调用 runtime。
- token 解析经过 `_validate_handle_id`，包含正则匹配 `_HANDLE_ID_PATTERN` 与禁止片段检查。corrupt token（如旧 `finsjob_` 前缀、含 `/` 等）触发 `ValueError` 并 propagate 到 Host。
- 测试 `test_fins_wait_activation_adapter_activates_existing_resume_token` 用 `_FakeObservationRuntime` 验证 adapter 只调用 `activate_observation(handle_id)`。
- 测试 `test_fins_wait_activation_adapter_rejects_corrupt_resume_token` 验证 corrupt token 抛 `ValueError` 且 `runtime.activated_handles == ()`。

### 无 Engine/Host/Service scope creep

- 所有变更严格限定在 `dayu/fins/` 内。
- `FinsObservationRuntime` protocol 新增方法（prepare/activate），不改动 Host/Engine contract。
- `build_fins_wait_activation_registry` 构造 `WaitActivationRegistry`（Host-facing 类型），但不做 Host assembly / wiring — 留待 Slice 3。
- 未引入 durable prepared status、lifecycle supervisor 或 public await contract。

### README 更新

- `dayu/fins/README.md` 变更：新增 prepare/activate 入口说明、更新状态流图、补充 activation submit failure 行为说明。均为事实同步，无文档职责扩张。
- 未触及其他 README。

### 测试覆盖

- **prepare-only**: `test_prepare_observed_operations_do_not_submit_until_activation`（3 个 operation 类型全覆盖）
- **activation 幂等**: `test_activate_observation_is_idempotent_for_same_handle`
- **cancel-before-activate**: `test_cancel_prepared_observation_prevents_later_activation_submit`
- **锁协调**: `test_cancel_and_activate_share_observation_lock_without_timing_sleep`（证明 cancel/activate 用同一把锁）
- **submit failure**: `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter`
- **unexpected exception**: `test_unexpected_activation_exception_terminalizes_prepared_observation`
- **callable prepare-only**: `test_awaiting_tool_callables_prepare_without_executor_submit`
- **activation adapter**: `test_fins_wait_activation_adapter_activates_existing_resume_token`、`test_fins_wait_activation_adapter_rejects_corrupt_resume_token`
- **activation registry**: `test_fins_wait_activation_registry_binds_fins_adapter_key`
- 旧 failure path 测试已更新命名（如 `test_download_tool_os_error_executor_is_not_used_during_prepare`），继续验证 prepare 阶段错误返回失败 outcome。

**未发现测试被改弱的情况**。旧测试的 assertion 强度保持不变。旧 failure path（如 `_RuntimeErrorExecutor` / `_OSErrorExecutor`）在工具测试中仍然存在，只是测试名从 "start" 改为 "prepare"，验证的错误路径（参数错误、OS error、unexpected error）一致。

### 未引入过度设计

- 无 durable prepared status、无 lifecycle supervisor、无 public await contract。
- `FinsObservationRuntime` protocol 的 prepare/activate 方法为最小语义：prepare 注册、activate 提交。
- `_FinsObservedOperationRecord.submitted` 为简单 bool flag，不引入状态机层级。

## Open Questions

1. **`cancel_observation` async vs `activate_observation` sync 的不对称**：`cancel_observation` 是 `async` 方法而 `activate_observation` 是 sync 方法。两者都通过 `asyncio.run()` 在 adapter 中被调用。当前行为正确，但若未来有代码在 asyncio event loop 内直接 await `cancel_observation` 的同时其他线程调用 `activate_observation`，`threading.Lock` 仍能正确协调，但 await 点 inside lock 的缺失也确保了不会在持锁时 yield event loop。目前不需要修改，但值得在未来 Host 接入时做一次 concurrent access stress test。

2. **`abandon_observation` 与 running producer 的交互**：`abandon_observation` pops 记录并调用 `record.cancellation_state.request_cancel()`。如果 producer 已提交到 executor 且正在运行，其 cancellation checker 会在下一个检查点看到取消请求并终止。但队列中已投递但尚未被 `_drain_observation_queue` 消费的事件会随 record 一起丢失。这对于 abandoned observation 是预期行为（调用方已放弃），但值得确认是否需要在 abandon 时 flush 队列以避免内存泄漏的信号量/队列资源。

## Residual Risk

| Risk | 严重度 | 说明 |
|------|--------|------|
| Service wiring 未接入 | 中 | `build_fins_wait_activation_registry` 已构造但未接入 Service/Host assembly。若 Slice 3 中发现 Host activation 机制与 Fins adapter 的 key dispatch 不兼容，可能需要调整 adapter 注册方式。此项已在 plan 与 Codex artifact 中记录。 |
| Poll/activation adapter 的 runtime 一致性 | 中 | `build_fins_wait_adapter_registry` 与 `build_fins_wait_activation_registry` 各自通过 `DefaultFinsRuntime.create(workspace_root)` 构造 runtime。若 Host 装配时两次调用产生的 runtime 不是同一 process-local 实例，activation adapter 的 `activate_observation` 将找不到 poll adapter 注册的 observation record。此项同属 Slice 3 assembly 风险。 |
| process-local observation 没有 TTL | 低 | prepared-but-never-activated observation 在 `_observations` dict 中无过期机制。若 Host accepted-wait 后 activation 永远不到达，record 在进程生命周期内泄漏。当前基于 Host governance 的 WaitRecord deadline/expiry 机制应能确保 activation 或 abandon 终将发生；若 Host 侧机制有 bug，则存在泄漏可能。 |
| `cancel_observation` pre-submit cancel message 与 `_safe_observation_message` 的防御深度缺口 | 低 | 见 Finding 1。 |
| 无 multi-thread concurrent activation 测试 | 低 | 测试覆盖了 cancel vs activate 的双线程锁协调，但未覆盖两个线程同时 activate 同一 handle 的场景。幂等性由 lock + `submitted` flag 保证，且 unit test 覆盖了 sequential double-activate。 |
| 无 executor thread running 中途 activate 测试 | 低 | 无测试覆盖 producer 已在 executor 中运行时再次调用 `activate_observation` 的场景（幂等检查在 `submitted=True` 时返回）。lock 内逻辑是明确的，但缺少 explicit regression test。 |

## Conclusion

**Pass** — 无阻断问题。

Slice 2 implementation 正确实现了 Fins prepare/activate two-phase runtime：
- 工具 callable 为 prepare-only，不提交 executor；
- `activate_observation` 幂等，通过 `_observation_lock` 与 `cancel_observation` 协调；
- activation submit failure 与 unexpected exception 将 observation terminal 化为 FAILED，可由现有 wait adapter 观察；
- `FinsIngestionWaitActivationAdapter` 边界清晰，只解析 resume token 并委托 runtime；
- 无 scope creep，Service wiring 合理保留到 Slice 3；
- README 更新必要且最小；
- 测试覆盖 Slice 2 预期断言，未发现被改弱或删除覆盖的情况。

两个 low-severity finding 为防御深度与代码可读性建议，不构成 merge blocker。Residual risks 中 Service wiring 与 runtime 实例一致性属于 Slice 3 已知风险，建议在 Slice 3 实现时做针对性验证。
