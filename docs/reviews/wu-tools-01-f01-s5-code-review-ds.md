# WU-TOOLS-01-F01 Slice S5 Code Review — DeepReview

## Gate Metadata

- Gate: code review only.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S5 - Fins Wait Adapter And Service Assembly Wiring`.
- Branch: `host-wu-tools-01-f01`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s5-code-review-ds.md`.
- Scope guard: no commit, no push, no code modification.

## 结论: PASS

所有 S5 目标均已实现，Host/Engine public contract 未修改，测试与 pyright 全通过，README 同步适当。未发现 correctness / architecture / stability / missing tests 层面的 blocking 问题。

---

## 验证命令结果

### 1. S5 核心测试

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py
```

结果: `49 passed, 3 warnings`。warnings 来自第三方 `edgar` deprecation，非本 slice 引入。

### 2. Service 全量测试

```bash
source .venv/bin/activate && pytest tests/service -q
```

结果: `34 passed, 3 warnings`。

### 3. pyright 类型检查

```bash
source .venv/bin/activate && pyright
```

结果: `0 errors, 0 warnings, 0 informations`。

### 4. Host/Engine 合约 diff 验证

```bash
git diff HEAD -- dayu/host/api.py dayu/host/wait_adapter.py dayu/host/tooling.py dayu/host/durable/state.py dayu/contracts/tool_await.py dayu/contracts/tool_outcome.py dayu/runtime/tools_discovery.py dayu/runtime/config_loader.py
```

结果: 无输出，确认 S5 未修改任何 Host/Engine public contract 文件。

---

## 逐项审查

### 1. Host/Engine public contracts 是否未变

**结论: 通过，未修改。**

直接证据:

- `git diff` 对 `dayu/host/api.py`、`dayu/host/wait_adapter.py`、`dayu/host/tooling.py`、`dayu/host/durable/state.py`、`dayu/contracts/tool_await.py`、`dayu/contracts/tool_outcome.py`、`dayu/runtime/tools_discovery.py`、`dayu/runtime/config_loader.py` 均无输出。
- `ToolAwaitSpec` (`dayu/contracts/tool_await.py:34`): fields unchanged — `await_kind`, `deadline`, `resume_token`。
- `ToolAwaitingOutcome` (`dayu/contracts/tool_outcome.py:82`): fields unchanged — `await_spec`, `snapshot`。
- `ResolveWaitRequest` (`dayu/host/api.py:2107`): fields unchanged — `context`, `idempotency_key`, `outcome`, `source`, `observed_at`。
- `WaitRecordRow` (`dayu/host/durable/state.py:395`): 27 fields, all unchanged。
- `ToolsDiscoveryProviderSpec` (`dayu/runtime/tools_discovery.py:89`): fields unchanged — `spec_id`, `location`, `enabled`, `allow_empty`, `config`。
- `ToolsDiscoveryProviderOutput` (`dayu/runtime/tools_discovery.py:119`): fields unchanged — `provider_id`, `version_ref`, `source_refs`, `definitions`。
- `HostToolingOptions` (`dayu/host/tooling.py:71`): fields unchanged — `business_tool_bundle`, `source_refs`, `framework_tool_policy`, `wait_adapter_registry`, `duplicate_governance_policy`。`wait_adapter_registry` 字段 S5 之前即存在，S5 仅将之前永远为 `None` 的值改为非空，字段类型 `WaitAdapterRegistry | None` 未变。

### 2. Fins poll adapter mapping 是否符合计划

**结论: 通过，完全符合 S5 计划规则。**

`dayu/fins/ingestion/wait_adapter.py` 中的映射:

- `poll_wait()` (line 101):
  - queued/running/cancelling → `WaitPollNotReady` (lines 117-118)
  - succeeded → `WaitPollReady(ResolveWaitCompletedOutcome)` (lines 119-120)
  - failed → `WaitPollReady(ResolveWaitFailedOutcome)` (lines 121-122)
  - cancelled → `WaitPollReady(ResolveWaitCancelledOutcome)` (lines 123-124)
  - missing job_id → `WaitPollLost` (lines 111-112)
  - FileNotFoundError/ValueError from `read_job` → `WaitPollLost` (lines 115-116)
  - 其他 unknown state → `WaitPollLost` (line 125)
- `abandon_wait()` (line 127): 只调用 `self.runtime.request_cancel(job_id)` (line 140)，不删除 source docs，不修改 Host wait records。job_id 为 None 或 job 不存在时静默返回 (lines 137-138, 141-142)。
- `_completed_outcome()` (line 231): 从 job record 投影 ticket、operation、status、result 等业务字段，不暴露 Host internal refs。
- `_failed_outcome()` (line 258): 从 failure_summary 提取 message 或 error，兜底为通用错误文本。
- `_lost_outcome()` (line 304): 返回稳定 reason_code `"fins_ingestion_job_lost"` 和 message。

### 3. Service assembly 检测是否只用显式 config

**结论: 通过，严格基于 provider config 显式字段，不依赖 diagnostics。**

`dayu/service/host_assembly.py` 的检测路径:

1. `_tooling_options_from_discovery()` (line 1050): 调用 `_fins_wait_adapter_registry_from_provider_configs(provider_configs)`，参数仅为 `provider_configs`（来自 `RuntimeConfig.tool_discovery.providers`）。
2. `_fins_awaiting_tool_name_from_provider_config()` (line 1116): 只检查三个显式配置字段:
   - `provider_config.provider_id` in `{financial-download-tools, financial-preprocess-tools}` (lines 89-98)
   - `provider_config.import_path` in `{dayu.fins.tools.download_provider:discover_tools, dayu.fins.tools.preprocess_provider:discover_tools}` (lines 95-100)
   - `provider_config.source_id` in `{dayu.fins.tools.download_provider, dayu.fins.tools.preprocess_provider}` (lines 101-106)
3. `_fins_workspace_root_from_provider_config()` (line 1141): 只读 `provider_config.config[_FINS_WORKSPACE_ROOT_CONFIG_FIELD]` (line 1151)。
4. 未使用 `provider_reports`（diagnostic strings）、`ToolsDiscoveryProviderOutput` shape 或 discovery output 内部字段。

### 4. workspace_root 校验是否 fail fast

**结论: 通过，多层 fail fast，均为绝对路径校验。**

- `_fins_workspace_root_from_provider_config()` (lines 1151-1161): 先校验 config 中 value 是非空字符串，再校验 `workspace_root.is_absolute()`，再 `resolve(strict=False)`。
- `build_fins_wait_adapter_registry()` 内 `_require_absolute_workspace_root()` (line 166-175): 再次校验绝对路径。
- `_single_fins_workspace_root()` (line 1164-1182): 校验所有启用的 Fins awaiting providers 的 workspace root 一致。不一致时抛出 `ValueError("Fins awaiting providers must use the same absolute workspace_root")`。
- 全部校验在 `_tooling_options_from_discovery()` 内完成，发生在 `_compose_options()` 调用 `open_host` 之前。

### 5. Service → Fins import boundary

**结论: 通过，边界合理。**

- `dayu/service/host_assembly.py` 的 Fins 导入仅限 `dayu.fins.ingestion` (line 22-26):
  ```python
  from dayu.fins.ingestion import (
      FINS_DOWNLOAD_AWAITING_TOOL_NAME,
      FINS_PREPROCESS_AWAITING_TOOL_NAME,
      build_fins_wait_adapter_registry,
  )
  ```
- `tests/service/test_import_boundary.py` 的 allowlist:
  - 禁止 `"dayu.fins"` 前缀 (line 12-14)，除 `"dayu.fins.ingestion"` 之外 (line 16)
  - AST 扫描覆盖 `dayu/service/` 下所有 `.py` 文件 (line 31-39)
  - 禁止 `dayu.config`、`dayu.ui` (line 10-11)，不允许 service 导入配置或 UI

allowlist 适当：只允许 composition-root assembly 通过 `dayu.fins.ingestion` (公共 wait adapter factory) 来装配 Fins wait adapter registry；不允许 service 导入 `dayu.fins.storage`、`dayu.fins.service_runtime`、`dayu.fins.tools.*` 等内部模块。

### 6. WaitAdapterRegistry binding 是否 deterministic

**结论: 通过。**

- `build_fins_wait_adapter_registry()` (line 145):
  - `_deterministic_tool_names()` (line 178): 先按遍历顺序去重（fail fast on duplicate），再 `tuple(sorted(ordered))` 字典序排序
  - `_binding_for_tool_name()` (line 201): 每个 tool_name 产生一个 `WaitAdapterBinding`，所有 binding 使用相同的 `ToolAwaitKind.EXTERNAL_JOB`、`WaitResumePolicy.POLL`、`WaitExternalJobRefSource.RESUME_TOKEN` 和 adapter_key `poll:fins-ingestion`
  - `WaitAdapterRegistry.__init__` (`dayu/host/wait_adapter.py:233`): Host 端再做一次 duplicate key fail fast
- 工具名均为 S4 稳定名称: `start_fins_download` (`dayu/fins/tools/download_tools.py:31`), `start_fins_preprocess` (`dayu/fins/tools/preprocess_tools.py:30`)

### 7. 测试覆盖

**结论: 通过，覆盖计划要求的全部场景。**

`tests/fins/test_fins_ingestion_tools.py`:
- `test_fins_wait_adapter_registry_binds_download_and_preprocess_tools` (line 385): registry 绑定 S4 工具名
- `test_fins_wait_adapter_registry_duplicate_binding_fails` (line 411): 重复 binding fail fast
- `test_fins_wait_poll_adapter_maps_terminal_and_missing_jobs` (line 426): succeeded/failed/cancelled → WaitPollReady, queued → WaitPollNotReady, missing → WaitPollLost
- `test_fins_wait_poll_adapter_abandon_marks_job_cancellation_requested` (line 457): abandon_wait 标记 cancellation_requested

`tests/service/test_host_assembly.py`:
- `test_tooling_options_binds_fins_wait_adapter_registry_for_enabled_awaiting_providers` (line 549): registry 非空，binding 按 provider_id/import_path/source_id 正确匹配
- `test_fins_awaiting_provider_workspace_root_mismatch_fails_before_open_host` (line 596): workspace mismatch fail fast
- `test_fins_awaiting_provider_duplicate_binding_fails_before_open_host` (line 628): duplicate binding fail fast

Registry absent behavior: 既有 Host tests (`tests/host/test_phase7_waiting_integration.py`) 覆盖 `wait_adapter_registry=None` 时 ToolRuntime 返回 governed failure `awaiting_adapter_not_configured`。

`tests/host/test_public_resolve_wait_resume.py`: Host resolve_wait 公共路径不变。

Corrupt evidence: `poll_wait()` 的 `except (FileNotFoundError, ValueError)` 分支 (line 115) 将 corrupt/stale job evidence 映射为 `WaitPollLost`。`ValueError` 覆盖 corrupt JSON 解析失败的场景，但无显式测试用例。

### 8. README 同步

**结论: 通过，符合 AGENTS.md 职责边界。**

- `dayu/fins/README.md` (line 14): 新增 `dayu.fins.ingestion.wait_adapter` 边界说明、poll 状态映射和 abandon 行为
- `dayu/README.md` (line 71): 新增 Service composition root 为 Fins awaiting provider 装配 wait adapter registry 的稳定边界说明
- `tests/README.md` (line 111): 新增 Service Fins awaiting assembly 测试覆盖说明和 import boundary 收敛文案
- 未更新根 `README.md`：正确，S5 无 CLI 命令或用户手册层面变化
- 未更新 `dayu/host/README.md` / `dayu/engine/README.md`：正确，S5 未修改 Host/Engine public contract

---

## Findings

### Finding 1 — Corrupt evidence 缺少显式测试 (severity: low)

- 文件: `tests/fins/test_fins_ingestion_tools.py`
- `test_fins_wait_poll_adapter_maps_terminal_and_missing_jobs` (line 426) 覆盖了 queued/succeeded/failed/cancelled/missing 五种状态，但未覆盖 **corrupt job evidence**（例如 job JSON 文件存在但内容非法导致 `read_job` 抛出 `ValueError`）。
- `poll_wait()` 的 `except (FileNotFoundError, ValueError)` 分支 (line 115) 在代码层面已正确处理，但没有独立测试断言 corrupt evidence → `WaitPollLost`。
- 影响: 低。代码 handler 覆盖了该路径，已在生产代码层面防住。缺少显式测试不影响正确性，但降低了 coverage visibility。
- 建议: 后续 slice 加一个 corrupt record fixture（写入格式错误的 JSON 文件后调用 `poll_wait`）覆盖该分支。

### Finding 2 — Provider 检测使用 OR 逻辑可能过度匹配 (severity: low)

- 文件: `dayu/service/host_assembly.py`, `_fins_awaiting_tool_name_from_provider_config()` (line 1116)
- 该函数通过 `provider_id in _SET` OR `import_path in _SET` OR `source_id in _SET` 判定是否 Fins awaiting provider。`source_id` 是通用配置字段（非 Fins 专用），若有人故意或误配置 `source_id` 为 `"dayu.fins.tools.download_provider"` 但实际不是 Fins download provider，会被误识别。
- 影响: 极低。普通 workspace overlay 不会误配 source_id；如有意构造恶意配置也能通过其他校验 fail。
- 建议: 当前设计足够，可考虑后续将 detection 收敛为 provider_id 为主标识、import_path/source_id 为辅助确认。

### Finding 3 — import boundary allowlist 中排除 `dayu.fins` 但允许子包 `dayu.fins.ingestion` (severity: informational)

- 文件: `tests/service/test_import_boundary.py` (lines 10-17)
- 当前设计: `SERVICE_FORBIDDEN_PREFIXES = ("dayu.config", "dayu.ui", "dayu.fins")` 但 `SERVICE_ALLOWED_IMPORTS = ("dayu.fins.ingestion",)`。
- 该 allowlist 模式在 `_matches_prefix` 中正确实现（line 62-70）: 先匹配 allowlist 中的精确模块名，再匹配 forbidden prefixes。
- 评估: 边界合理。`dayu.fins.ingestion` 是公共 wait adapter factory 的稳定入口，不暴露 `dayu.fins.storage`、`dayu.fins.service_runtime` 等内部模块。若后续 Fins 新增公共 assembly boundary 子包，需同步更新 allowlist。

---

## Open Questions / Residual Risk

| 分类 | 内容 |
|------|------|
| Assigned to later work unit | Service assembly 只构造 `HostToolingOptions.wait_adapter_registry`，没有为生产 poller loop 提供自动启动 / backoff / fencing / retry wiring；属于既有 WAIT hardening owner，不在 S5 范围。 |
| Assigned to later work unit | 默认 `tool_discovery.json` closeout 和 packaged config 启用策略仍属 S6 non-goal。 |
| Assigned to later work unit | 当前没有真实 SEC/CN/HK 网络下载 adapter；Fins ingestion runtime 对 unsupported source 写入 failed terminal，真实 adapter breadth 不属于 S5。 |
| Residual risk | `dayu.fins.ingestion.wait_adapter` 中 `from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME` 和 `from dayu.fins.tools.preprocess_tools import PREPROCESS_TOOL_NAME` 使 wait adapter 模块依赖具体 tool 模块。这是合理的设计耦合（S4 稳定工具名需要稳定引用源），但若未来工具名变更需同步更新 `FINS_SUPPORTED_AWAITING_TOOL_NAMES`。 |
| Residual risk | Corrupt job evidence 的 `ValueError` 捕获路径与 `poll_wait()` 自身的参数校验 `ValueError` 在同一个 except 分支，无法区分 corrupt evidence vs. internal invariant error。当前实现安全（两者都映射到 lost），但缺少 diagnostic 区分日志。 |
