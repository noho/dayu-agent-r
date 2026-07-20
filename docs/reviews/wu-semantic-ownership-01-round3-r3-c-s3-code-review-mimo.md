# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main` (未提交 working tree 变更)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s3-code-review-mimo.md`
- Included scope: R3-C S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue 的全部 production 变更、测试变更与 README 同步
- Excluded scope: S1/S2 production 与测试变更（已 accepted）；tool-security deferred items
- Parallel review coverage: 无

## 审查范围

### Production 文件

| 文件 | 变更类型 |
|------|----------|
| `dayu/host/wait_adapter.py` | 修改：新增 `WaitAdapterSnapshot`、`WaitAdapterSnapshotProjectionError`、`_adapter_snapshot_from_wait_record()`、`_validate_adapter_snapshot_resume_token()`；`WaitPollAdapter`/`WaitActivationAdapter` Protocol 改收 snapshot；poller 两处调用 adapter 前投影 snapshot |
| `dayu/service/fins_wait_adapter.py` | 新增：Service-owned Fins wait adapter，只消费 Host public snapshot/outcome contract |
| `dayu/service/host_assembly.py` | 修改：import 路径从 `dayu.fins.ingestion.wait_adapter` 切到 `dayu.service.fins_wait_adapter` |
| `dayu/fins/ingestion/wait_adapter.py` | 删除 |

### 测试文件

| 文件 | 变更类型 |
|------|----------|
| `tests/service/test_fins_wait_adapter.py` | 新增：14 个测试覆盖 registry/activation/poll/abandon/snapshot 边界 |
| `tests/service/test_import_boundary.py` | 修改：新增 `dayu.fins.direct_event_text` 到 Service allowed imports |
| `tests/service/test_host_assembly.py` | 修改：import 路径同步 |
| `tests/fins/test_fins_ingestion_runtime.py` | 修改：删除 `_observation_wait_record` helper 与 Host durable imports；迁移 `activation_submit_failure` 测试为直接观察 snapshot |
| `tests/fins/test_fins_ingestion_tools.py` | 修改：删除 Fins wait adapter registry/poll/abandon 测试（已迁到 Service） |
| `tests/host/test_wait_adapter_polling.py` | 修改：adapter fake 改收 `WaitAdapterSnapshot`；新增 `_SnapshotRecordingAdapter` 验证投影 |

### README 文件

| 文件 | 变更类型 |
|------|----------|
| `dayu/README.md` | 修改：wait-resume 说明增加 Service-owned adapter |
| `dayu/fins/README.md` | 修改：删除 Fins wait adapter 例外说明；记录 Service-owned adapter 边界 |
| `dayu/service/README.md` | 修改：新增 `fins_wait_adapter` 模块说明与 import 边界约束 |
| `dayu/host/README.md` | 修改：记录 Host poller 向 adapter 只投影 `WaitAdapterSnapshot` |
| `tests/README.md` | 修改：迁移 Fins wait adapter 测试说明到 Service；更新 Fins 测试范围 |

## Findings

未发现实质性问题。

### 逐项审查结论

#### 1. Host wait adapter 是否唯一拥有 durable WaitRecordRow 到 adapter-facing WaitAdapterSnapshot 的投影

**Pass。** `dayu/host/wait_adapter.py:2257-2290` 定义 `_adapter_snapshot_from_wait_record(record: WaitRecordRow) -> WaitAdapterSnapshot`，它是 Host 模块级私有函数，从 `WaitRecordRow` 校验 resume token 非空且不超长、用 Host-owned `parse_utc_timestamp()` 解析 `created_at` 为 UTC aware datetime，然后构造 frozen `WaitAdapterSnapshot(tool_name, resume_token, created_at)`。`WaitPollAdapter.poll_wait()` 和 `abandon_wait()` Protocol 签名已从 `(self, wait_record: WaitRecordRow)` 改为 `(self, snapshot: WaitAdapterSnapshot)`。poller 在 `poll_once()` 和 `_abandon_cancelled_wait()` 中调用 adapter 前都先投影；投影失败走 `ADAPTER_ERROR`/`ABANDON_ERROR` backoff，adapter 不被调用。Service adapter 不读取 `WaitRecordRow`。

#### 2. Service Fins adapter 是否只消费 Host public wait adapter snapshot/outcome contract

**Pass。** `dayu/service/fins_wait_adapter.py` import 列表确认：只从 `dayu.host.wait_adapter` 导入 snapshot、registry、poll result、lifecycle result 等 Protocol/公开类型；只从 `dayu.host.api` 导入 outcome 类型和 `WaitAdapterKey`。未 import `dayu.host.durable`、`WaitRecordRow`、`deadline_at`、`expires_at`、claim、state mutator 或 `ExternalJobRef`。

#### 3. dayu.fins production 是否完全没有 Host import

**Pass。** `rg -n '(^|\s)(from|import) dayu\.host' dayu/fins --glob '*.py'` 返回零匹配。`dayu/fins/ingestion/wait_adapter.py` 已删除（`test -e` 返回 `DELETED`）。`dayu/fins/__init__.py` 和 `dayu/fins/ingestion/__init__.py` 中无 wait_adapter re-export。

#### 4. Fins tests 是否不再固化 Service adapter 语义；Service tests 是否覆盖边界

**Pass。** `tests/fins/test_fins_ingestion_runtime.py` 删除了 `_observation_wait_record` helper 和所有 Host durable imports（`WaitRecordRow`、`WaitRecordStatus`、`WaitResumePolicy`、`ExternalJobRef`、`ResolveWaitFailedOutcome`、`WaitPollReady`）。原 `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter` 改为 `test_activation_submit_failure_terminalizes_prepared_observation`，直接观察 `FinsObservationSnapshot.status`，不经过 adapter 映射。

`tests/service/test_fins_wait_adapter.py` 新增 14 个测试覆盖：
- registry binding（3 工具绑定到同一 adapter key、duplicate fail-fast）
- activation registry 复用 shared runtime
- activation corrupt token fail-fast
- poll mapping（succeeded/failed/cancelled/pending/running/lost 六种状态）
- failed result 缺 message 时抛 ValueError
- corrupt/missing handle → lost
- transient unavailable → not ready
- old snapshot created_at 不强制 lost
- abandon cancel + cleanup / corrupt token no-op / missing no-op / LOST no-op / non-transient error no-op / transient re-raise

`tests/service/test_import_boundary.py` 新增 `dayu.fins.direct_event_text` 到 allowed imports，与 `fins_wait_adapter.py` 的 import 一致。

`tests/host/test_wait_adapter_polling.py` 的 `_SequenceAdapter` 已改为收 `WaitAdapterSnapshot`，并新增 `_SnapshotRecordingAdapter` 验证 Host 投影给 adapter 的 snapshot 字段。

#### 5. README 同步是否只说明已落地边界

**Pass。** 所有 README diff 只记录已落地的架构边界变化：Fins 不再有 Host import 例外、Service 拥有 wait glue、Host 只投影 minimal snapshot。`rg` 扫描确认新增 README 行中无 tool-security 承诺（无 security/allowlist/SSRF/TLS/redirect/symlink/byte-budget/authority 命中）。

#### 6. AGENTS.md 约束

**Pass。** 逐项确认：
- 中文 docstring：`fins_wait_adapter.py` 所有类、方法、模块级函数均有完整中文 docstring（参数、返回值、异常）。`WaitAdapterSnapshot` 和 `WaitAdapterSnapshotProjectionError` 的 docstring 也是中文。
- 无 `Any`/`object` 签名：所有类型签名明确，使用 `str`、`datetime`、`Path`、`Sequence[str]`、`FinsObservationRuntime` 等具体类型。
- 无 `getattr`/`hasattr` 逃避边界：`_handle_from_snapshot()` 用 `try/except ValueError` 而非 `getattr`。
- 无兼容 shim：旧 `dayu/fins/ingestion/wait_adapter.py` 删除，无 re-export/wrapper/lazy import。
- 无下游 fallback 修语义：`_poll_error_result()` 中移除了旧的 `_transient_pending_expired` 超时检查，transient unavailable 统一返回 `WaitPollNotReady`，由 Host poll owner 基于 durable boundary 决定终态。

### 行为变更确认

1. **transient unavailable 超时逻辑移除**：旧代码 `_TRANSIENT_PENDING_MAX_SECONDS = 300.0` 和 `_transient_pending_expired()` 已删除。transient unavailable 现在统一返回 `WaitPollNotReady`，不再由 adapter 从 `created_at` 年龄制造 lost。这是正确的语义收束——timeout 决策归 Host poll owner 的 durable boundary。`test_fins_wait_poll_adapter_old_snapshot_created_at_does_not_force_lost` 直接覆盖此行为。

2. **`_failure_message` 签名变更**：从 `_failure_message(snapshot, result)` 改为 `_failure_message(result)`，移除了未使用的 `snapshot` 参数。功能无变化。

3. **`direct_event_text` 模块新增**：`dayu/fins/direct_event_text.py` 提供 `wait_cancelled_hint()`、`wait_cancelled_message()`、`wait_failed_hint()` 等 Fins 文案投影。Service adapter 通过 `dayu.fins.direct_event_text` 导入这些函数，不在 Service 内硬编码 Fins 文案。

## Open Questions

无。

## Residual Risk

1. **S3 测试覆盖率**：`dayu/service/fins_wait_adapter.py` 是新增文件，当前 focused test matrix（132 passed）覆盖了主要行为路径。建议在 aggregate validation 时用 `pytest --cov dayu/service/fins_wait_adapter.py --cov-report=term-missing` 确认覆盖率 >= 80%。

2. **`_run_async_observation` 的 `asyncio.run()` 安全性**：当前实现用 `asyncio.run()` 在 sync adapter 内执行 async observation runtime 方法。这在 Host poller observation thread 内是安全的（thread 内无 running event loop），但如果未来 Service adapter 被从 async context 调用会抛 `RuntimeError`。当前所有 call site 均在 sync thread，非当前风险。

3. **旧 `test_fins_ingestion_tools.py` 删除的测试项**：原文件中的 Fins wait adapter registry binding / poll mapping / abandon lifecycle 测试已迁到 `tests/service/test_fins_wait_adapter.py`。`test_fins_ingestion_tools.py` 的 README 描述已相应缩减，但建议 aggregate validation 确认无测试覆盖缺口。
