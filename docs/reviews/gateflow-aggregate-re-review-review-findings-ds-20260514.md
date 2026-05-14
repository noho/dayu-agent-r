# Gateflow Aggregate Deepreview Re-Review Artifact

- **gate**: aggregate deepreview re-review
- **reviewed target**: `fix/gateflow-review-findings` 分支对 `docs/reviews/code-review-20260514-2235.md` 中两个 controller-accepted finding 的修复
- **source review artifact**: `docs/reviews/code-review-20260514-2235.md`
- **fix artifact**: `docs/reviews/gateflow-aggregate-fix-review-findings-20260514.md`
- **re-review scope**: 仅复核 Finding 1 (closed handle guard) 和 Finding 2 (terminal RunSnapshot 一致性) 的修复是否真实生效，以及是否引入新 blocker
- **completion/stop status**: re-review pass completed；未修改生产代码、未 commit、未 push、未 PR、未 merge、未 closeout

## 最终 Finding 状态映射

| Finding | 状态 |
|---------|------|
| 1-中-admission-backed public facade 绕过 closed handle guard | **已修复** |
| 2-中-terminal RunSnapshot 在 command path 与 read path 中不一致 | **已修复** |

## Finding 1: closed handle guard — 已修复

### 逐函数验证

`dayu/host/command.py` 中四个 admission-backed public facade 入口均已添加 `host._raise_if_closed()` 调用：

| 函数 | 行号 | `_raise_if_closed()` 位置 | 是否在 admission 调用前 |
|------|------|---------------------------|------------------------|
| `start_run` | 296 | 第 296 行 | 是（admission 调用在第 297 行） |
| `submit_followup` | 321 | 第 321 行 | 是（admission 调用在第 334 行，且在 session_id 校验和 steer 检查之后但在 admission 之前） |
| `cancel_run` | 370 | 第 370 行 | 是（admission 调用在第 372 行） |
| `cancel_session_runs` | 411 | 第 411 行 | 是（admission 调用在第 412 行） |

`_raise_if_closed()` 的实现在 `dayu/host/command.py:179-191`，稳定抛出 `HostApiError(code=INVALID_STATE, retryable=False)`。

### 测试覆盖

`tests/host/test_command_handle.py:351` 的 `test_admission_backed_facades_fail_closed_before_public_branches` 覆盖以下场景：

1. `start_run` after close → `INVALID_STATE`, `retryable=False`
2. `submit_followup` with session_id mismatch after close → `INVALID_STATE`, `retryable=False`（验证 session_id 不匹配的 early return 分支也先经过 closed guard）
3. `submit_followup` with steer after close → `INVALID_STATE`, `retryable=False`（验证 steer unsupported 分支也先经过 closed guard）
4. `cancel_run` after close → `INVALID_STATE`, `retryable=False`
5. `cancel_session_runs` after close → `INVALID_STATE`, `retryable=False`
6. 断言 EventLog 与 idempotency record 数量在 close 后未增加

测试充分覆盖所有 admission-backed facade 及其内部分支（session mismatch、steer unsupported），且验证了零副作用写入。

## Finding 2: terminal RunSnapshot 一致性 — 已修复

### 共享转换真源

`dayu/host/durable/state.py:1818-1842` 的 `run_snapshot_from_row` 现在是 command path 与 read path 的**唯一** Run row → RunSnapshot 转换入口：

- 第 1835-1837 行调用 `_terminal_result_summary_from_status(run.status)` 统一处理终态/非终态映射
- `_terminal_result_summary_from_status`（第 1845-1861 行）对终态返回 `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)`，非终态返回 `None`

### Command path 使用点

| 调用点 | 文件:行号 |
|--------|----------|
| `start_run` 返回值 | `command.py:301` |
| `cancel_run` 返回值 | `command.py:390` |
| `submit_followup` cursor 读取 | `command.py:346` |

### Read path 使用点

| 调用点 | 文件:行号 |
|--------|----------|
| `_GetRunOperation.__call__` | `read_api.py:137` |

`read_api.py` 中原先的私有 helper `_run_snapshot_from_public_read_row` 已被完全移除，不存在重复转换逻辑。

### 测试覆盖

1. `tests/host/test_public_run_api.py:311` `test_get_run_returns_durable_status_attempt_and_cursor`：
   - 第 344 行断言 `cancel_run` 返回 snapshot 的 `terminal_result_summary is not None`
   - 第 345-347 行断言 status-only 字段
   - 第 350-354 行断言 `cancelled_read.terminal_result_summary == cancelled.terminal_result_summary`
   - 覆盖 command path cancel 与 read path get_run 的 terminal summary 一致性

2. `tests/host/test_public_run_api.py:366` `test_start_run_idempotent_replay_returns_latest_snapshot_without_events`：
   - 第 382-384 行断言 cancelled snapshot 有 terminal summary
   - 第 386-388 行断言 replay snapshot 的 `terminal_result_summary == cancelled.terminal_result_summary`
   - 第 389-390 行断言无新增 EventLog 或 idempotency record
   - 覆盖 start_run 幂等重放已终态 Run 时的 terminal summary 一致性与无副作用

## README 验证

`dayu/host/README.md` 第 46 行已更新为：

> 所有从 durable Run row 构造的 public `RunSnapshot` 都使用同一映射：非终态 Run 的 `terminal_result_summary` 为 `None`；终态 Run 当前返回 status-only `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)`

该描述准确反映当前 `run_snapshot_from_row` 的实际行为，属于 `dayu/host/README.md` 的 Public Run Command Path 职责范围，未越界到其他 README 职责。

## 类型/docstring/项目指令回归检查

- pyright 对 `dayu/host/command.py`、`dayu/host/read_api.py`、`dayu/host/durable/state.py`、`tests/host/test_command_handle.py`、`tests/host/test_public_run_api.py` 报告 **0 errors, 0 warnings, 0 informations**
- 所有新增/修改函数的 docstring 均为中文，参数、返回值、异常说明完整
- 未发现 `object`、`Any`、无类型参数、无类型返回值
- 未发现魔法数字或魔法字符串
- 未发现层间反向依赖（`test_host_import_boundary_still_excludes_upper_layers` 也通过）
- 未发现 God object/function/dataclass 扩散
- 未发现兼容性 re-export 或 wrapper

## 验证命令

以下命令均已执行并通过：

```bash
source .venv/bin/activate && python -m pytest tests/host/test_command_handle.py tests/host/test_public_run_api.py -v
# 结果: 16 passed

source .venv/bin/activate && python -m pyright dayu/host/command.py dayu/host/read_api.py dayu/host/durable/state.py tests/host/test_command_handle.py tests/host/test_public_run_api.py
# 结果: 0 errors, 0 warnings, 0 informations
```

## 新发现/blocker

无。

## Open Questions / Residual Risk

- **Residual risk**: 低。
- **理由**: 修复限定在 public facade lifecycle guard 与 `RunSnapshot` row conversion 单一语义真源，未扩大到 Engine、admission state machine 或 schema。测试覆盖 closed handle 错误优先级、零写入、command/read terminal summary 一致性和幂等重放无新增事实。所有受影响测试通过，pyright 零报错。
- **未覆盖项**: 未对 `submit_followup` 在 admission service 中 closed handle 后 SQLite connection 状态做直接集成验证——但已通过 `_raise_if_closed()` 在所有 admission-backed 路径中先于 admission 调用执行，确保 SQLite connection 不会被触及。未对 `retry_run`、`replay_run`、`resolve_wait`、`purge_session` 做 closed guard 验证——这些 deferred facade 不接触 admission service 或 durable store，当前直接返回 `UNSUPPORTED_OPERATION`，不属于本次 finding 修复范围。
- **Owner / Destination**: 已回写 `docs/host/implementation-control.md` 追踪区；当前 Gateflow work-unit controller 持有到 PR 创建前。该项不是 accepted finding，不进入后续 fix slice，也不需要新 issue。若后续需求要求所有 deferred facade 在 closed handle 后也优先返回 lifecycle error，应作为新的 public API contract change 进入独立 Gateflow work-unit，由 Host public API owner 承接。
