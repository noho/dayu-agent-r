# Code Re-Review — WU-TOOLS-01-F01-02-R1 Slice 2

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `2634f361`（Slice 2 checkpoint commit）
- Re-review gate: code re-review after S2-CR-F01 / S2-CR-F02 fix
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-mimo.md`
- Included scope: Slice 2 implementation diff + code-review fix diff（`dayu/fins/ingestion_runtime.py`、`dayu/fins/ingestion/wait_adapter.py`、`tests/fins/test_fins_ingestion_runtime.py`）
- Excluded scope: `docs/host/issues-implementation-control.md`（仅作状态上下文）；已 merge Slice 1 代码；controller adjudication artifact、DS review artifact、Codex implementation/fix artifact（作为输入 artifact，不作为 re-review 目标）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## 验证结果

### S2-CR-F01 验证：`_observation_cancelled_result(...)` 已应用 `_safe_observation_message(...)`

- ✅ **修复已正确应用**。`_observation_cancelled_result`（`ingestion_runtime.py:4986-5007`）在第 4999 行调用 `safe_message = _safe_observation_message(message)`，将安全截断后的消息写入 `FinsResultSummary.error_message`。
- ✅ **调用链一致**。`cancel_observation`（行 2347-2348）设置 `record.message = "Observation was cancelled before activation."` 后调用 `_observation_cancelled_result(record.message)`；`_observation_cancelled_result` 内部对传入 message 执行 `_safe_observation_message`，确保与 `_mark_observation_failed`（行 5029）的防御深度一致。
- ✅ **当前取消消息语义稳定**。硬编码消息 `"Observation was cancelled before activation."`（45 字符）不含 `_DISALLOWED_TOKEN_FRAGMENTS` 禁止片段，经 `_safe_observation_message` 后原样返回，用户可见语义不变。
- ✅ **无新增 public/schema/兼容行为**。`_observation_cancelled_result` 是模块级私有函数，签名不变；`FinsResultSummary` 构造参数不变；`cancel_observation` 返回的 `FinsObservationSnapshot` shape 不变。
- ✅ **测试断言验证消息稳定**。`test_cancel_prepared_observation_prevents_later_activation_submit`（`test_fins_ingestion_runtime.py:2130-2134`）断言 `cancelled.result.error_message == "Observation was cancelled before activation."`，确认 safe-message 通过后消息未被替换。
- ✅ **工具端取消测试未被改弱**。`test_download/preprocess/upload_tool_cancelled_before_start_returns_cancelled_without_job` 仍使用 `_assert_cancelled_outcome_hides_host_term` 验证取消 outcome 不暴露 host 术语。

### S2-CR-F02 验证：`build_fins_wait_activation_registry(...)` validation-only 意图已明确

- ✅ **注释已添加**。`wait_adapter.py:241` 新增注释 `# activation 由单个 adapter key 分发，tool_names 只用于装配期校验。`，明确 `_deterministic_tool_names(tool_names)` 的返回值被丢弃的原因。
- ✅ **仍然只有单 `FINS_INGESTION_WAIT_ADAPTER_KEY` activation registration**。`build_fins_wait_activation_registry`（行 244-250）只构造一个 `WaitActivationAdapterRegistration(adapter_key=FINS_INGESTION_WAIT_ADAPTER_KEY, adapter=adapter)`，未引入 per-tool activation registration。
- ✅ **注册行为未变**。`_deterministic_tool_names` 仍做 fail-fast 校验（空名、不支持的工具名、重复名称），其排序返回值在 activation builder 中不被使用；`build_fins_wait_adapter_registry` 中同一函数的返回值仍被用于构造 per-tool bindings。
- ✅ **测试覆盖未变**。`test_fins_wait_activation_registry_binds_fins_adapter_key` 验证 registry 只包含 `FINS_INGESTION_WAIT_ADAPTER_KEY`。

### 测试与 pyright 验证

- ✅ `pytest tests/fins/test_fins_ingestion_runtime.py -q`：`68 passed`，与 fix artifact 报告一致。
- ✅ `pytest tests/fins/test_fins_ingestion_tools.py -q`：`51 passed`，与 fix artifact 报告一致。
- ✅ `pyright`：`0 errors, 0 warnings, 0 informations`。
- ✅ 测试数量未减少，无测试被删除或改弱。
- ✅ 无新增 scope creep：fix 只修改 `_observation_cancelled_result` 内部实现和一行注释，未扩展 public API、schema 或兼容行为。

### 辅助观察：`_observation_failure_result` 无内部 safe-message 调用

- `_observation_failure_result`（行 4963-4983）内部不调用 `_safe_observation_message`，但其唯一调用方 `_mark_observation_failed`（行 5029）在调用前已执行 `_safe_observation_message` 预处理。这与 `_observation_cancelled_result` 的模式不同（后者内部自行调用），但两条路径的最终效果一致：写入 `FinsResultSummary.error_message` 的值均经过安全截断。
- 当前 `_observation_cancelled_result` 有两个调用方：`cancel_observation`（行 2348）和 `_mark_observation_cancelled`（行 5082，若存在）。内部调用 `_safe_observation_message` 保护了所有调用方，是更防御性的设计。
- 此项不构成问题，仅作为一致性观察记录。

## Open Questions

无。

## Residual Risk

- **Slice 3 Service wiring 风险**（中）：`build_fins_wait_activation_registry` 已构造但未接入 Service/Host assembly。此项已在 plan 与实现文档中记录。
- **Poll/activation adapter 的 runtime 实例一致性**（中）：两个 builder 各自按 workspace root 构造 runtime，production 中需确保 process-local observation registry 装配一致。此项同属 Slice 3 assembly 风险。
- **`_observation_failure_result` 与 `_observation_cancelled_result` 的 safe-message 调用位置不对称**（低）：failure 路径由调用方预处理，cancelled 路径由函数内部处理。当前行为正确，但若未来新增 `_observation_failure_result` 调用方可能遗漏 safe-message。此项为防御深度观察，非当前 blocker。

## Conclusion

**Pass** — 无阻断问题。

S2-CR-F01 和 S2-CR-F02 的 fix 均为最小修复：
- F01：`_observation_cancelled_result` 内部新增 `_safe_observation_message` 调用，与 failure 路径防御深度一致，不改变用户可见语义。
- F02：新增一行中文注释明确 validation-only 意图，不改变注册行为。

测试全部通过（68 + 51 passed），pyright 无报错，无 scope creep、无过度设计、无测试被改弱。
