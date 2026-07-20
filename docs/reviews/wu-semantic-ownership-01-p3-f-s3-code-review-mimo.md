# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S3

## Scope

- Mode: current changes (unstaged workspace diff since `3b2779e4`)
- Branch: `phaseflow/host-issues-control`
- Base: `3b2779e4` (S2 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s3-code-review-mimo.md`
- Included scope: 4 files (+83/-21) — S3 Fins wait adapter deadline/expiry consumption
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`, `docs/host/issues-implementation-control.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项检查：

### `_TRANSIENT_PENDING_MAX_SECONDS` 和 `_transient_pending_expired` 已移除

`_TRANSIENT_PENDING_MAX_SECONDS: Final[float] = 300.0` 已从 `wait_adapter.py:103` 删除。`_transient_pending_expired(...)` 已被 `_wait_boundary_lost(...)` 替换。source scan `rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests` 返回零匹配（exit code 1）。

### `_wait_boundary_lost(...)` 边界优先级正确

函数实现（`wait_adapter.py:609-629`）：

1. 先读 `wait_record.deadline_at`；非空时用作边界文本。
2. `deadline_at` 为空时退到 `wait_record.expires_at`。
3. 两者都为空 → `return False`（not ready）。
4. 边界文本存在但 `parse_utc_timestamp` 抛 `ValueError` → `return True`（fail closed to lost）。
5. 边界解析成功 → `datetime.now(timezone.utc) > boundary` 判断是否过期。

这与 `dayu/host/wait_callback.py:_stale_status_or_none` 的 precedence 一致：deadline first, expires second。`parse_utc_timestamp` 来自 `dayu.host.durable.codec`，是 Host 拥有的 timestamp 解析真源。

### 无边界时保持 not ready

`boundary_text is None` 时返回 `False`，对应 `_poll_error_result` 中 `WaitPollNotReady()`。这正确反映了：Fins adapter 不拥有 terminal timeout；Host poller cadence、claim TTL、cancel/close lifecycle 负责治理无边界 wait。

### 旧 `created_at` 年龄不再影响 lost 判断

`_wait_boundary_lost` 不读取 `wait_record.created_at`。`_timestamp_or_now` 仍在 `wait_adapter.py:366` 用于 observation handle 时间戳（不同用途），不影响 transient timeout 语义。

### Fail closed on invalid boundary

`parse_utc_timestamp` 抛 `ValueError` 时返回 `True` → `WaitPollLost`。测试覆盖了 `deadline_at="invalid-deadline"` 和 `expires_at="invalid-expires"` 两种场景。

### 无 LLM-facing 泄漏

`_lost_outcome()` 使用稳定常量 `_ERROR_FINS_OBSERVATION_LOST` 和 `_MESSAGE_FINS_OBSERVATION_LOST`，不暴露 wait id、deadline、expiry timestamp 或 Host governance 措辞。`_poll_error_result` 对 `TRANSIENT_UNAVAILABLE` 返回 `WaitPollLost(_lost_outcome())` 或 `WaitPollNotReady()`，均为类型化 Host poll result，不携带内部边界细节。

### 测试矩阵覆盖

`test_fins_wait_poll_adapter_transient_unavailable_uses_host_wait_boundaries` 覆盖六个场景：

| 场景 | 断言 |
|---|---|
| future `deadline_at` + past `expires_at` | `WaitPollNotReady`（deadline 优先） |
| past `deadline_at` + future `expires_at` | `WaitPollLost`（deadline 优先） |
| no deadline + past `expires_at` | `WaitPollLost` |
| invalid `deadline_at` + future `expires_at` | `WaitPollLost`（fail closed） |
| no deadline + invalid `expires_at` | `WaitPollLost`（fail closed） |
| no boundary + old `created_at` | `WaitPollNotReady`（旧 created_at 不影响） |

`_wait_record` builder 支持显式 `deadline_at` / `expires_at` 参数。`_boundary_from_now` helper 使用 Host codec `format_utc_timestamp` 构造边界文本。

### README 更新

`dayu/fins/README.md` 更新了两处：wait adapter contract 描述从"有界窗口"改为 Host boundary ownership；wait adapter 与 Host resume 章节增加 deadline/expiry durable truth 属于 Host 的说明。内容在 `dayu/fins/` Agent update constraints 范围内。

## Owner Boundary 评估

| 检查项 | 状态 | 证据 |
|---|---|---|
| Host wait record 拥有 deadline/expiry truth | ✅ | `_wait_boundary_lost` 只读 `WaitRecordRow` 字段 |
| Fins adapter 不自行制造 terminal timeout | ✅ | 无 `created_at` 年龄计算；无边界 → not ready |
| Boundary precedence: deadline first, expires second | ✅ | `wait_adapter.py:618-622` |
| Invalid boundary fail closed to lost | ✅ | `except ValueError: return True` |
| 无 LLM-facing 泄漏 | ✅ | `_lost_outcome()` 使用稳定常量 |
| 旧路径完全移除 | ✅ | rg 零匹配 |
| Host wait resolution 仍是 terminal governance owner | ✅ | adapter 只返回 typed poll result |

## Validation

- `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`: **132 passed, 3 warnings**
- `rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests`: **零匹配**
- `pyright dayu/fins/ingestion/wait_adapter.py`: **0 errors**
- `git diff --check`: passed

## Residual Risk

- **无边界的 transient unavailable 可能长期 not ready**: 这是有意边界选择。Fins adapter 不拥有 terminal timeout；实际轮询节奏由 Host `WaitPollerRuntimePolicy` 控制，cancel/close lifecycle 由 Host 治理。
- **`expires_at` 当前 Host creation path 写 `None`**: 实现已按 contract 支持该字段，供未来 Host-owned expiry truth 消费。
- **Coverage 未测量**: pytest-cov 本地 numpy/pandas import 问题仍存在。

## Verdict

**PASS** — S3 实现正确执行了 plan 中的 Fins wait adapter deadline/expiry consumption。旧 adapter-owned timeout 完全移除，Host boundary precedence 与 `wait_callback.py` 一致，fail closed 行为正确，无 LLM-facing 泄漏。未发现 material defects。
