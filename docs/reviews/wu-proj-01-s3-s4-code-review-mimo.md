# WU-PROJ-01 S3/S4 Residual Code Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Review scope: `WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1`
- Reviewer: AgentMiMo
- Date: 2026-06-11
- Changed files:
  - `tests/host/test_dispatch_scheduler.py`
  - `docs/host/issues-implementation-control.md`

## 审查结论

**PASS**

0 条 blocking findings，2 条非阻塞 findings。

## 审查逐项分析

### 1. S3 新测试是否覆盖 dispatch before-worker checkpoint-covered happy path

✅ 全部覆盖。

`test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input`（第 1987–2099 行）：

- **required cursor 已由 projection checkpoint 覆盖**：测试先用真实 `catch_up_conversation_memory_projection(...)` 将 conversation memory projection checkpoint 追到 `required_event_sequence`，然后断言 `prewarmed.target_reached is True`、`prewarmed.finished_cursor == required_event_sequence`、`checkpoint_before_dispatch == required_event_sequence`。这三条断言确认 dispatch 前 checkpoint 已覆盖 required cursor。
- **dispatch 内部 catch-up no-op / 不重复扫描**：通过 `_observed_catch_up` wrapper 观察 dispatch 内部真实 catch-up 返回值，断言 `started_cursor == finished_cursor == required_event_sequence`、`events_scanned == 0`、`target_reached is True`。这证明 checkpoint-covered 路径下 catch-up 是 no-op。
- **ordinary RunInput 构造**：断言 `factory.accepted_requests[0].disable_tools is True`（no-tool ordinary policy）和 `accepted_contents[-1] == "dispatch prompt"`（用户输入进入 request）。
- **worker accepted**：`len(factory.accepted_snapshots) == 1` 和 `len(factory.accepted_requests) == 1`。
- **未进入 RUN_FAILED / RUN_RECOVERING**：`_event_count(..., "RUN_FAILED") == 0`、`_event_count(..., "RUN_RECOVERING") == 0`、`_attempt_count_for_run(...) == 1`。
- **checkpoint 未被重复推进**：`checkpoint_after_dispatch == checkpoint_before_dispatch`。

与设计真源对齐：`docs/host/design.md` 第 3204 行要求"ordinary dispatch 前 snapshot cursor 不能覆盖 required cursor 时必须做 bounded catch-up / rebuild；这不是 Run crash recovery，不得把 Run 推入 RECOVERING"。本测试覆盖的是该规则的反面 happy path：checkpoint 已覆盖时不做额外扫描、不进入 fail-closed / recovery。

### 2. S3 测试是否过度 mock 或绕开真实路径

✅ 未过度 mock。

- **prewarm 使用真实函数**：`catch_up_conversation_memory_projection(...)` 直接调用真实 production 函数，使用真实 `open_host_durable_store` 和 `_seed_current_run` 构造 durable 状态。
- **dispatch 内部 observation seam**：`_observed_catch_up` wrapper 调用真实 `catch_up_conversation_memory_projection` 并记录返回值，不替换 catch-up 语义。这是标准 observation pattern，不是 mock。
- **monkeypatch 范围精确**：只替换 `host_dispatch.catch_up_conversation_memory_projection`（dispatch 模块内的引用），不影响其它模块对同一函数的调用。
- **未绕开 RunInputBuilder / scheduler 关键路径**：测试通过 `scheduler.wake_dispatch` + `scheduler.drain_once` 触发真实 dispatch 流程，worker factory 使用既有 `_FakeWorkerFactory` + `_CloseCountingHandle` 基础设施。
- **`_FakeWorkerFactory` / `_CloseCountingHandle`**：是该测试文件中已有的测试基础设施（第 1074、708 行），被多个既有测试复用。

### 3. S4 是否只稳定 flaky 测试且未降低断言强度

✅ 只改 timing fixture，断言强度不变。

`test_reactive_compact_failure_fallback_dispatch_uses_failed_view`（第 4988–5042 行）变更：

- **唯一变更**：`_open_scheduler(...)` 新增 `lane_default_timeout_seconds=1.0`（从默认 0.01 改为 1.0）。
- **断言保留**：fallback artifact / `CONTEXT_COMPACTION_FAILED` payload（`payload["fallback_action"] == "dispatch"`、`payload["fallback_policy_decision"] == "deterministic_recent_window"`）、第二次 dispatch request、Attempt 数量为 2、无 `CONTEXT_COMPACTED`、无 `RUN_LOST`、第二次 request 不包含 accepted compact artifact 文本、`second_contents[-1] == "dispatch prompt"`。全部保留，未降低。
- **动机对齐**：该测试验证 reactive compact failure fallback 语义，不验证 lane acquire timeout。使用默认 0.01s 会暴露给无关的宿主调度窗口。1.0s 足够隔离 timing 风险，且不改变测试语义。

### 4. 是否误改 production code / 引入 sleep / flaky / 硬编码不合理值

✅ 无问题。

- **未修改 production code**：所有变更仅在 `tests/host/test_dispatch_scheduler.py` 和 `docs/host/issues-implementation-control.md`。
- **未引入 sleep**：新测试和 S4 变更均未使用 `asyncio.sleep` 或 `time.sleep`。
- **未引入 flaky 风险**：S3 测试的 `lane_default_timeout_seconds=1.0` 和 S4 的相同修改均是确定性 timing fixture，不是 polling 或 retry。
- **硬编码值合理**：`batch_size=32`（与生产默认值对齐）、`lane_default_timeout_seconds=1.0`（测试专用，足够宽裕）、`lane_claim_ttl_seconds=1.0`（由 `_open_scheduler` 默认值决定，非新增）。

### 5. 测试 helper 和 imports 是否符合 AGENTS.md

✅ 符合。

- **`_read_memory_checkpoint_sequence`**（第 6130–6153 行）：
  - 完整类型签名：`transaction_runner: HostTransactionRunner -> int`。
  - 完整中文 docstring，含参数、返回值、异常。
  - 内部嵌套 `_operation` 函数遵循既有模式（`_event_count`、`_attempt_count_for_run` 等同样使用嵌套 closure 传给 `transaction_runner.run_read`），属于 API 约束下的必要嵌套。
  - 使用 public durable projection read primitive `read_projection_checkpoint`。
  - 无 `Any`、`object` 或无类型参数。

- **`_observed_catch_up` wrapper**（第 2018–2047 行）：
  - 完整类型签名，与 production `catch_up_conversation_memory_projection` 参数完全对齐。
  - 完整中文 docstring。
  - 无 `Any`、`object`。

- **新增 imports**（第 16、115–119、145 行）：
  - `import dayu.host.dispatch as host_dispatch`：用于 monkeypatch，与既有 `from dayu.host.dispatch import ...` 共存合理。
  - `MemoryProjectionPolicy`、`ConversationMemoryProjectionRepairResult`、`MemoryProjectionCatchupBudget`、`catch_up_conversation_memory_projection`、`read_projection_checkpoint`：均为 production 公共 API，非内部实现。
  - 无兼容 wrapper / facade / re-export。

- **测试 docstring**：新增测试和 helper 均有完整中文 docstring，符合 AGENTS.md 要求。

### 6. README 判断是否合理

✅ 合理。

Implementation artifact 报告"本次仅在既有测试文件内补充 dispatch scheduler 行为覆盖并调整单个测试的 lane timeout fixture，不新增测试层级、运行方式、公共测试约定或维护入口"，判断无需更新 `tests/README.md`。符合 AGENTS.md 触发规则。

## 非阻塞 Findings

### NF-1: `_read_memory_checkpoint_sequence` helper 命名可与既有 pattern 更一致

既有 helper `_event_count` 和 `_attempt_count_for_run` 使用简短动词 + 名词命名。新增 `_read_memory_checkpoint_sequence` 使用 `read_` 前缀，与 `read_projection_checkpoint` production 函数对齐但与测试 helper 命名风格略有差异。这不影响正确性或可读性，仅是风格一致性提示。

**严重度**：informational。不阻塞。

### NF-2: S3 测试 `lane_default_timeout_seconds=1.0` 与 S4 改动动机不同但值相同

S3 测试设置 `lane_default_timeout_seconds=1.0` 不是为了修复 flaky（S3 是新测试），而是为了与 S4 保持一致的测试专用 timeout。这合理，但如果未来有人 grep `lane_default_timeout_seconds` 寻找 flaky 修复记录，可能会误将 S3 测试也当作 flaky 修复。不影响正确性。

**严重度**：informational。不阻塞。

## 验证确认

Controller 已复验：
- `python -m pytest tests/host/test_dispatch_scheduler.py` → 68 passed
- `pyright` → 0 errors
- `git diff --check` → passed

## 最终裁决

**PASS**。S3-R1 和 S4-R1 实现正确覆盖了 controller adjudication 要求的所有验收点，未修改 production code，未降低既有断言强度，符合 AGENTS.md 约束。
