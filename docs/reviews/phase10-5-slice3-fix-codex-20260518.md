# P10.5 Slice 3 Fix - AgentCodex

## Scope

- 当前 gate：P10.5 Slice 3 fix。
- 分支：`feat/host-p10-5-public-contract-freeze`。
- 本次只处理 controller adjudication accepted for fix 的 F1、F2、F3。

## Changes

1. 新增 `dayu/host/_execution_config_projection.py`，集中维护 Host 内部 RunnerSpec、RunnerCallOptions、AgentPolicy 与 provider request 的 JSON 投影、反投影和 effective execution config digest/ref 生成。
2. 调整 `dayu/host/admission.py`、`dayu/host/command.py`、`dayu/host/dispatch.py`，统一复用内部 helper；未改变 `USER_INPUT_ACCEPTED` payload shape、policy digest/ref 语义、durable schema、public API 或 dispatch state machine。
3. 在 `tests/host/test_effective_execution_config.py` 增加 focused 覆盖：
   - `SubmitFollowupRequest.agent_policy` override 会冻结到 `USER_INPUT_ACCEPTED.effective_execution_config.config.agent_policy`；
   - dispatch `AttemptDispatchSnapshot.policy_snapshot_ref` 使用同一冻结 `policy_snapshot_ref`；
   - 低层 `create_host_command_handle` 缺少 opener ordinary baseline 时，`submit_followup` 以 `HostApiErrorCode.INVALID_STATE` 早失败。
4. 补齐新增 helper 与 Slice 3 fix 新增/修改函数 docstring 的 `:raises` 说明，区分无主动抛出、JSON shape validation、enum/dataclass validation 与未知 provider extension 分支。

## Follow-up Fix

1. `tests/host/test_admission_queue.py` 的 `_service()` helper 已迁移到新的 ordinary baseline 边界：构造 `HostAdmissionService` 时显式传入 `OrdinaryRunExecutionBaseline`，并保留无业务工具的 `tooling_options=None` 语义。
2. `tests/host/test_projection_read_model.py` 为正常 `submit_followup` 路径新增 `_host_with_ordinary_baseline()` helper，手工装配 durable store、baseline-aware admission service 与 `ActiveWorkerRegistry`；未修改生产 `create_host_command_handle()` 的无 baseline misuse 行为。
3. `tests/host/test_effective_execution_config.py::test_submit_followup_without_ordinary_baseline_fails_before_dispatch` 保留，继续覆盖无 ordinary baseline 的 fail-early contract。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q`
  - 结果：`11 passed in 0.31s`
- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py -q --tb=short`
  - 结果：`36 passed in 0.47s`
- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_projection_read_model.py tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q`
  - 结果：`47 passed in 0.53s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`

## README Check

- 本次修改为 Host 内部 helper 抽取与 focused test 补充，不改变 Host 对外接口、架构边界、命令入口或测试运行约定。
- 按 README 职责检查后，无需更新 `dayu/host/README.md` 或 `tests/README.md`。

## Residual Risk

- 既有 admission queue / projection read-model 正常 follow-up 测试 helper 已迁移到 ordinary baseline 边界；无 baseline misuse 仍由 dedicated fail-early 测试覆盖。
- `OpenHostOptions` 构造期不允许 baseline 为 `None`，因此 public opener 路径不存在同类运行期缺口。
- 未做 schema migration、public API 扩展、Engine/Service/UI/Fins 修改。
