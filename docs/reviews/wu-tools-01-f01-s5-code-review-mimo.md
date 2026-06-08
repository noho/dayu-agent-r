# WU-TOOLS-01-F01 Slice S5 Code Review

## Gate Metadata

- Gate: code review only.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S5 - Fins Wait Adapter And Service Assembly Wiring`.
- Branch: `host-wu-tools-01-f01`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s5-code-review-mimo.md`.
- Reviewer: mimo (claude code review agent).
- Scope guard: no commit, no code modification.

## 结论

**pass-with-findings**

S5 实现正确完成目标：Fins wait adapter 未修改 Host/Engine public contracts，poll adapter 状态映射符合计划，Service assembly 检测逻辑基于显式 provider config，workspace_root 校验 fail fast。发现 2 个中等 severity 测试覆盖缺口和 4 个低 severity 测试覆盖缺口，均为防御性覆盖缺失，不影响生产正确性。

## Findings

### F1 [medium] poll adapter 缺少 `running` 和 `cancelling` 状态的 poll_wait 测试覆盖

**文件:** `tests/fins/test_fins_ingestion_tools.py:426-454`

**证据:** `test_fins_wait_poll_adapter_maps_terminal_and_missing_jobs` 测试了 `SUCCEEDED`（L434）、`FAILED`（L435）、`CANCELLED`（L436）、`QUEUED`（L437）和 missing job（L443），但未测试 `RUNNING` 和 `CANCELLING` 状态。这两个状态在 `_ACTIVE_STATUSES`（`wait_adapter.py:64-70`）中被正确处理为 `WaitPollNotReady`，但缺少直接测试断言。

**影响:** 若后续代码重构误删 `_ACTIVE_STATUSES` 中的某个状态，当前测试不会捕获回归。

**建议:** 在 `test_fins_wait_poll_adapter_maps_terminal_and_missing_jobs` 中增加 `RUNNING` 和 `CANCELLING` 状态的 job poll 断言，确认返回 `WaitPollNotReady`。

### F2 [medium] service assembly 缺少 registry absent（无 Fins provider）的显式测试

**文件:** `tests/service/test_host_assembly.py`

**证据:** `test_tooling_options_binds_fins_wait_adapter_registry_for_enabled_awaiting_providers`（L549）只测试正向绑定路径。计划 S5 Expected assertions 明确要求："When registry is absent, existing Host governed failure behavior remains covered by current Host tests"。当前 `tests/service/test_host_assembly.py` 中无显式测试验证无 Fins awaiting provider 时 `_fins_wait_adapter_registry_from_provider_configs` 返回 `None`。

**影响:** Host governed failure 行为由 `tests/host/` 已有测试覆盖（`test_phase7_waiting_integration.py` 等），但 Service assembly 层缺少显式回归断言。

**建议:** 新增测试用空 provider_configs 或非 Fins provider_configs 调用 `_tooling_options_from_discovery`，断言 `wait_adapter_registry is None`。

### F3 [low] abandon_wait 遇到 ValueError 时静默返回，缺少测试覆盖

**文件:** `dayu/fins/ingestion/wait_adapter.py:136-142`，`tests/fins/test_fins_ingestion_tools.py`

**证据:** `abandon_wait` 在 `read_job` 抛出 `FileNotFoundError` 或 `ValueError` 时静默 `return`（L140-142）。`FileNotFoundError` 路径合理（job 已被清理），但 `ValueError`（corrupt evidence）静默忽略可能导致问题难以诊断。测试中无此路径覆盖。

**影响:** 生产中 corrupt job record 导致 `abandon_wait` 静默跳过，Host 已取消 wait 但 Fins 侧无日志。风险低，因为 Host 侧 wait 已被正确取消。

**建议:** 补充 `abandon_wait` 遇到 missing job（`external_job_ref=None`）和 corrupt job evidence 的测试。`ValueError` 路径可考虑记录 debug 日志。

### F4 [low] abandon_wait 缺少 `external_job_ref=None` 的测试覆盖

**文件:** `tests/fins/test_fins_ingestion_tools.py:457-475`

**证据:** `test_fins_wait_poll_adapter_abandon_marks_job_cancellation_requested` 使用有效 `external_job_ref`。`_wait_record` helper（L547）始终构造包含 `external_job_ref` 的 `WaitRecordRow`（L574）。`abandon_wait` 对 `external_job_ref=None` 的 early return（L137-138）未被测试。

**影响:** 代码正确性不受影响（early return 逻辑简单），但缺少防御性覆盖。

**建议:** 补充 `external_job_ref=None` 的 `abandon_wait` 测试，断言不抛异常且不修改 job。

### F5 [low] service assembly 缺少 workspace_root 非绝对路径和缺失的显式测试

**文件:** `tests/service/test_host_assembly.py`

**证据:** `_fins_workspace_root_from_provider_config`（`host_assembly.py:1141-1161`）对非绝对路径抛 `ValueError`（L1158-1160），对缺失/空值抛 `ValueError`（L1153-1155）。当前测试均使用 `.resolve(strict=False)` 生成绝对路径，未直接测试这两个失败路径。

**影响:** `wait_adapter.py:166-175` 的 `_require_absolute_workspace_root` 有独立测试覆盖（通过 `build_fins_wait_adapter_registry` 的 duplicate binding 测试间接验证），但 Service assembly 层的 `_fins_workspace_root_from_provider_config` 的独立失败路径未被覆盖。

**建议:** 补充 workspace_root 为相对路径和缺失值的 `_fins_wait_adapter_registry_from_provider_configs` 测试。

### F6 [low] poll_adapter unreachable else 分支

**文件:** `dayu/fins/ingestion/wait_adapter.py:125`

**证据:** `poll_wait` 方法的最后一个 `return WaitPollLost(_lost_outcome())`（L125）在当前 `FinsIngestionJobStatus` 枚举（6 个值）下不可达：`_ACTIVE_STATUSES` 覆盖 3 个，`SUCCEEDED`/`FAILED`/`CANCELLED` 各有独立分支。

**影响:** 防御性代码，无生产影响。若未来新增 job 状态而未更新 adapter，此分支会静默返回 lost 而非 fail fast。

**建议:** 可保持现状作为防御；若追求严格穷尽匹配，可改为 `assert_never` 或显式 `raise`。

## 正面发现

### 合约完整性

- `git diff main...HEAD` 确认 7 个 Host/Engine public contract 文件（`tool_await.py`、`tool_outcome.py`、`host/api.py`、`durable/state.py`、`wait_adapter.py`、`tooling.py`、`tools_discovery.py`）零修改。
- `ToolAwaitSpec`、`ToolAwaitingOutcome`、`ResolveWaitRequest`、`WaitRecord` schema、`ToolsDiscoveryProviderOutput` shape 均未变更。

### Poll adapter 状态映射

- `wait_adapter.py:101-125` 正确映射：
  - `queued`/`running`/`cancelling` → `WaitPollNotReady`（通过 `_ACTIVE_STATUSES` frozenset）
  - `succeeded` → `WaitPollReady(ResolveWaitCompletedOutcome)`
  - `failed` → `WaitPollReady(ResolveWaitFailedOutcome)`
  - `cancelled` → `WaitPollReady(ResolveWaitCancelledOutcome)`
  - missing/corrupt evidence → `WaitPollLost(ResolveWaitLostOutcome)`
- `abandon_wait`（L127-142）只调用 `runtime.request_cancel(job_id)`，不删除业务数据或 Host wait record。

### Service assembly 检测逻辑

- `host_assembly.py:89-106` 使用显式 provider config 的 `provider_id`、`import_path`、`source_id` 匹配 Fins awaiting providers。
- 不依赖 diagnostics 或 discovery output。
- `_fins_awaiting_tool_name_from_provider_config`（L1116-1138）使用 OR 逻辑匹配三元组，custom import_path 生效。

### workspace_root 校验

- `_fins_workspace_root_from_provider_config`（L1141-1161）校验非空字符串、绝对路径。
- `_single_fins_workspace_root`（L1164-1182）校验多个 Fins provider 使用同一 workspace。
- 校验在 `open_host` 前 fail fast。

### WaitAdapterRegistry binding

- `_deterministic_tool_names`（`wait_adapter.py:178-198`）校验非空、去重、按字典序排序。
- `build_fins_wait_adapter_registry`（L145-163）fail fast on duplicate。
- 工具名使用 S4 稳定名称 `DOWNLOAD_TOOL_NAME` 和 `PREPROCESS_TOOL_NAME`。

### Service → Fins 依赖边界

- `tests/service/test_import_boundary.py` allowlist 只允许 `dayu.fins.ingestion`，禁止 `dayu.fins` 其它子包。
- `dayu.runtime` 未新增 Fins import。
- `host_assembly.py` 的 Fins import 限制在 `dayu.fins.ingestion`（L22-26）。

### README 同步

- `dayu/fins/README.md`：新增 ingestion wait adapter 边界、poll 状态映射与 abandon 行为说明。
- `dayu/README.md`：新增 Service composition root 为 Fins awaiting provider 装配 wait adapter registry 说明。
- `tests/README.md`：新增 Service Fins awaiting assembly 测试覆盖说明。
- 未更新根 `README.md`（无用户手册变更）和 `dayu/host/README.md`/`dayu/engine/README.md`（无 Host/Engine 变更）。符合 AGENTS.md 触发规则。

## 验证命令结果

```bash
# S5 核心测试
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py -q
# 结果: 49 passed, 3 warnings

# Service 全量测试
source .venv/bin/activate && pytest tests/service -q
# 结果: 34 passed, 3 warnings

# 类型检查
source .venv/bin/activate && pyright
# 结果: 0 errors, 0 warnings, 0 informations
```

## Open Questions / Residual Risk

1. **assigned to later work unit**: Service assembly 只构造 `HostToolingOptions.wait_adapter_registry`，未提供生产 poller loop 的自动启动 / backoff / fencing / retry wiring。属于既有 WAIT hardening owner。
2. **assigned to later work unit**: 默认 `tool_discovery.json` closeout 和 packaged config 启用策略属 S6 non-goal。
3. **assigned to later work unit**: 无真实 SEC / CN / HK 网络下载 adapter。Fins ingestion runtime 对 unsupported source 写入明确 failed 终态。
4. **observation**: `_fins_awaiting_tool_name_from_provider_config` 的 OR 逻辑允许仅 `source_id` 匹配即可识别为 Fins provider。若第三方 provider 恰好使用相同 `source_id`，会被误识别。当前 `source_id` 值足够具体（`dayu.fins.tools.download_provider`），风险极低。
