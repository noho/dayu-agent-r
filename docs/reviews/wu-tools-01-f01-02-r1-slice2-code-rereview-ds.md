# Code Re-Review — WU-TOOLS-01-F01-02-R1 Slice 2

## Scope

- **Mode**: current changes re-review（Slice 2 implementation + code-review fix diff）
- **Branch**: `phase/wu-tools-01-f01-02-r1`
- **Base checkpoint**: `2634f361`
- **Output file**: `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-ds.md`
- **Input artifacts**:
  - implementation: `docs/reviews/wu-tools-01-f01-02-r1-slice2-implementation-codex.md`
  - code review (MiMo): `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-mimo.md`
  - code review (DS): `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-ds.md`
  - controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-controller-adjudication.md`
  - fix (Codex): `docs/reviews/wu-tools-01-f01-02-r1-slice2-fix-codex.md`
- **Re-review focus**:
  - S2-CR-F01: `_observation_cancelled_result` safe-message boundary
  - S2-CR-F02: `build_fins_wait_activation_registry` validation-only intent
  - Regression / scope creep / test weakening
  - pyright + Fins focused test 可信度
- **Included files**:
  - `dayu/fins/ingestion_runtime.py`（fix diff）
  - `dayu/fins/ingestion/wait_adapter.py`（fix diff）
  - `tests/fins/test_fins_ingestion_runtime.py`（fix diff）
  - `tests/fins/test_fins_ingestion_tools.py`（全量 implementation + fix diff）
  - `dayu/fins/tools/download_tools.py` / `preprocess_tools.py` / `upload_tools.py`（implementation diff）
  - `dayu/fins/ingestion/observation_handle.py`（implementation diff）
  - `dayu/fins/README.md`（implementation diff）
- **Excluded scope**: Slice 1 commit `e10f2e99`；`docs/host/` 治理文档；Codex implementation artifact（作为另一路 implementation output 读取但不 review）

## Findings

### 已修复确认：S2-CR-F01 — `_observation_cancelled_result` 已应用 `_safe_observation_message`

- **入口/函数**: `_observation_cancelled_result(message)` → `_safe_observation_message(message)`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:4999`
- **修复内容**: `_observation_cancelled_result` 现在在构造 `FinsResultSummary` 前对 `message` 调用 `_safe_observation_message(message)`（行 4999），安全截断结果写入 `error_message=safe_message`（行 5006）。

**验证项**:

| 验证条件 | 状态 | 证据 |
|---------|------|------|
| `_observation_cancelled_result` 内部调用 `_safe_observation_message` | ✅ | 行 4999: `safe_message = _safe_observation_message(message)` |
| 唯一调用路径为 `cancel_observation` pre-activation branch | ✅ | 行 2348: `record.result = _observation_cancelled_result(record.message)`，仅当 `not record.submitted` 时执行 |
| 当前取消 message 语义稳定（"Observation was cancelled before activation."） | ✅ | 行 2347 设置；测试行 2134 断言 `==` 该消息 |
| `_safe_observation_message` 对此硬编码消息不做改写 | ✅ | 消息仅 45 字符，无禁用片段，长度远低于 240 上限；`_safe_observation_message` 会原样返回 |
| 未新增 public/schema/兼容行为 | ✅ | `FinsResultSummary` shape 不变，`error_kind=CANCELLED` 不变，`title=_DIRECT_CANCELLED_MESSAGE` 不变 |
| 测试覆盖了取消 result 的 safe-message 稳定性 | ✅ | `test_cancel_prepared_observation_prevents_later_activation_submit` 行 2130-2134 断言 status/CANCELLED、error_kind/CANCELLED、error_message 稳定 |

**结论**: 修复正确、最小、无副作用。

### 已修复确认：S2-CR-F02 — `build_fins_wait_activation_registry` 已明确 validation-only 意图

- **入口/函数**: `build_fins_wait_activation_registry(tool_names=...)`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:241`
- **修复内容**: 在 `_deterministic_tool_names(tool_names)` 调用前增加注释（行 241）: `# activation 由单个 adapter key 分发，tool_names 只用于装配期校验。`

**验证项**:

| 验证条件 | 状态 | 证据 |
|---------|------|------|
| 注释明确 `tool_names` 仅用于 validation | ✅ | 行 241 |
| 仍然只有单 `FINS_INGESTION_WAIT_ADAPTER_KEY` activation registration | ✅ | 行 246-248: 仅一个 `WaitActivationAdapterRegistration` |
| 无 per-tool activation registration | ✅ | registry 只包含一个 registration tuple |
| Registry 行为未变 | ✅ | `_deterministic_tool_names` 返回值仍被丢弃；adapter 构造路径不变 |
| 测试覆盖 registry 单 key binding | ✅ | `test_fins_wait_activation_registry_binds_fins_adapter_key` 行 1485-1495 断言单 key 解析 |

**结论**: 修复正确、最小、无副作用。

### 回归检查：未发现测试改弱

逐项复核结果：

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `_assert_failed_outcome_hides_internal_terms` 移除 | ✅ 合理 | prepare 阶段不再产生 `ToolFailedOutcome`（工具改为 prepare-only，返回 `ToolAwaitingOutcome`）；该 helper 与 `_FORBIDDEN_LLM_ERROR_FRAGMENTS` 常量不再有调用方 |
| `_assert_cancelled_outcome_hides_host_term` 保留 | ✅ 保留 | 取消 outcome 路径仍存在（`ToolCancelledOutcome`），保留正确 |
| 旧 failure path 测试从 `ToolFailedOutcome` 改为 `ToolAwaitingOutcome` | ✅ 语义正确 | `test_download_tool_os_error_executor_is_not_used_during_prepare` 等测试验证 prepare 阶段不触发 executor 错误 — 这是正确的语义变更，因为 prepare 不再 submit executor |
| Activation 端已有独立 failure coverage | ✅ 已覆盖 | `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter`、`test_unexpected_activation_exception_terminalizes_prepared_observation` |
| 参数错误测试仍断言 `ToolFailedOutcome` | ✅ 未改弱 | `test_tool_argument_error_returns_failed_outcome_before_observation_start` 仍断言 `ToolFailedOutcome` 和 `error == "invalid_argument"` |
| 取消 outcome 测试保留 | ✅ 未改弱 | `test_download_tool_cancel_before_prepare_returns_cancelled_outcome` 等仍存在且断言 `ToolCancelledOutcome` |
| 新增 focused assertion（S2-CR-F01） | ✅ 增强 | `test_cancel_prepared_observation_prevents_later_activation_submit` 增加了 `error_message` 稳定性和 `error_kind` 断言 |

**结论**: 测试覆盖增强，无改弱。

### 回归检查：`_observation_failure_result` 的 safe-message 边界未退化

`_observation_failure_result`（行 4963-4983）自身不调用 `_safe_observation_message`，但这是已有设计——其唯一调用方 `_drain_observation_queue`（行 2548）在传入前已通过 `_safe_observation_message(item.message)`（行 2553/2558）做了安全截断。本次 fix 未修改 `_observation_failure_result` 或 `_drain_observation_queue`，该路径的防御深度未退化。

### 回归检查：`_mark_observation_failed` 的 safe-message 边界未退化

`_mark_observation_failed`（行 5010-5039）本身调用 `_safe_observation_message`（行 5029），本次 fix 未修改此函数，行为不变。

### 回归检查：无 scope creep 或过度设计

- 修复变更仅涉及 `dayu/fins/ingestion_runtime.py` 的 `_observation_cancelled_result` 函数体（1 行新增 `safe_message = ...`）和 `dayu/fins/ingestion/wait_adapter.py` 的 `build_fins_wait_activation_registry` 函数体（1 行注释）。
- 未新增 durable prepared status、lifecycle supervisor、public await contract。
- 未引入 per-tool activation registration。
- 未修改 `FinsObservationRuntime` protocol 或 Host/Engine contract。
- `FinsIngestionWaitActivationAdapter` 的边界行为不变。

### pyright 与测试可信度

| 验证项 | 结果 | 备注 |
|--------|------|------|
| pyright | `0 errors, 0 warnings, 0 informations` | `v1.1.409`，有新版本 `v1.1.410` 可用 |
| `test_fins_ingestion_runtime.py` | `68 passed` | 3 条 upstream `edgar` deprecation warning（预存） |
| `test_fins_ingestion_tools.py` | `51 passed` | 3 条 upstream `edgar` deprecation warning（预存） |
| 总计 | `119 passed` | — |

pyright 和测试结果可信，无新增错误或警告。

## Open Questions

无。

## Residual Risk

| Risk | 严重度 | 说明 |
|------|--------|------|
| `_observation_failure_result` 的防御深度与 `_observation_cancelled_result` 不对称 | 低 | `_observation_failure_result`（行 4982）自身不调用 `_safe_observation_message`，依赖调用方 `_drain_observation_queue` 做截断。当前唯一调用路径已正确截断，但防御责任分散在两个函数间。不建议在本次 fix 中修改——这不属于 S2-CR-F01/F02 scope，且修改会影响现有 `_drain_observation_queue` 的 message 设置逻辑（行 2553/2558 设置已截断消息 → 行 2548 传入 `_observation_failure_result`）。未来若有人新增 `_observation_failure_result` 调用方，需确保 message 已截断。 |
| Slice 3 Service wiring runtime 一致性 | 中 | 与 pre-fix 状态相同：`build_fins_wait_adapter_registry` 和 `build_fins_wait_activation_registry` 各自构造 runtime，production assembly 需确保同一 process-local 实例。 |
| Process-local prepared observation TTL | 低 | 与 pre-fix 状态相同：无过期机制。 |

## Conclusion

**Pass** — 无阻断问题。

S2-CR-F01 与 S2-CR-F02 均已正确、最小修复：

- `_observation_cancelled_result` 现在通过 `_safe_observation_message` 做安全截断，与 `_mark_observation_failed` 的防御深度一致；当前硬编码取消消息语义稳定。
- `build_fins_wait_activation_registry` 的注释明确了 `tool_names` 仅用于装配期校验，不改变 registry 单 key 行为。
- 未引入 scope creep、过度设计或测试改弱。
- pyright 0 错误，119 测试全部通过。

建议 Slice 2 进入 accept commit gate。
