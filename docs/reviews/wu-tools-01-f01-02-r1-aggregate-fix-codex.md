# WU-TOOLS-01-F01-02-R1 Aggregate Deepreview Fix

## 修复范围

本次只处理 Controller 接受的 AGG-F01。未修改 `created_at` 相关逻辑，因为当前裁决明确不把它作为修复项。

## 问题判断

AGG-F01 动机成立。`build_fins_wait_activation_registry(...)` 原先通过 `workspace_root` 调用 `FinsIngestionWaitActivationAdapter.from_workspace_root(...)`，从而隐式创建新的 `FinsIngestionRuntime`。但 awaiting tool callable 准备的 observation 是 process-local runtime 状态；activation adapter 如果持有另一个 runtime 实例，就无法可靠激活 callable 刚准备的 observation。这个 builder 会误导独立装配调用方，且与生产 Service assembly 已经使用共享 runtime 的真实语义分叉。

## 代码改动

- `dayu/fins/ingestion/wait_adapter.py`
  - 删除 `FinsIngestionWaitActivationAdapter.from_workspace_root(...)`，避免 activation adapter 存在自建 runtime helper。
  - 将 `build_fins_wait_activation_registry(...)` 签名改为 `runtime: FinsObservationRuntime, tool_names: Sequence[str]`。
  - builder 只校验 `tool_names`，并用传入 runtime 构造 `FinsIngestionWaitActivationAdapter`。

- `dayu/service/host_assembly.py`
  - 生产 Service assembly 在确认存在共享 `FinsIngestionRuntime` 后，调用 `build_fins_wait_activation_registry(runtime=fins_awaiting_runtime, tool_names=...)`。
  - 删除不再需要的手写 `WaitActivationRegistry` registration 和死的重复名校验 helper。
  - 保留 fail-fast：有 Fins awaiting provider 时必须传入共享 runtime，且必须是 `FinsIngestionRuntime`。

- `tests/fins/test_fins_ingestion_tools.py`
  - 更新 activation registry builder 调用。
  - 新增断言证明 registry 解析出的 `FinsIngestionWaitActivationAdapter.runtime` 就是传入的 shared runtime。

- `tests/service/test_host_assembly.py`
  - 补强 Service wiring 断言，证明 activation adapter runtime、discovery shared runtime 与 awaiting callable runtime 是同一对象。

- `dayu/fins/README.md`
  - 将 builder 签名说明更新为 `build_fins_wait_activation_registry(runtime=..., tool_names=...)`。
  - 明确 awaiting observation 的 callable 与 activation adapter 必须共享同一个 `FinsIngestionRuntime` 实例，不能靠 `workspace_root` 重新发现 process-local observation。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q`
  - 结果：103 passed，3 个 edgar 依赖 deprecation warnings。
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_runtime.py -q`
  - 结果：108 passed，3 个 edgar 依赖 deprecation warnings。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

## 未覆盖风险

- 本次没有新增跨进程恢复能力。当前设计仍要求 prepared observation 与 activation adapter 在同一进程内共享同一个 `FinsIngestionRuntime`，这与 lightweight observation 的现有边界一致。
- 未处理 MiMo 02 `created_at` 观察项；Controller 已裁决其不参与当前 activation 查找语义。
