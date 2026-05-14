# Gateflow Aggregate Deepreview Fix Artifact

- **gate**: aggregate deepreview fix
- **work-unit**: 修复 `docs/reviews/code-review-20260514-2235.md` 中 controller-accepted 的两个中风险 finding
- **source review artifact**: `docs/reviews/code-review-20260514-2235.md`
- **accepted finding ids**: 1, 2
- **completion/stop status**: fix pass completed；未 commit、未 push、未创建 PR、未 closeout

## Per-Finding Status

### 1-已修复-[中]-admission-backed public facade 绕过 closed handle guard

- **修复状态**: 已修复。
- **修复内容**: `start_run`、`submit_followup`、`cancel_run`、`cancel_session_runs` 在读取 `host._admission_service` 前统一调用 `HostCommandHandle._raise_if_closed()`。
- **验证点**: 新增关闭 handle 后 public facade 回归测试，覆盖 `start_run`、`submit_followup` 的 session id mismatch 与 steer unsupported 分支、`cancel_run`、`cancel_session_runs`，均断言 `HostApiErrorCode.INVALID_STATE`、`retryable=False`，并断言 EventLog 与 idempotency record 未增加。

### 2-已修复-[中]-terminal RunSnapshot 在 command path 与 read path 中不一致

- **修复状态**: 已修复。
- **修复内容**: 将 public `RunSnapshot` 的 durable row 映射收敛到 `dayu.host.durable.state.run_snapshot_from_row`；终态 Run 返回 status-only `TerminalResultSummary`，非终态保持 `None`。`read_api.get_run` 移除私有重复 helper，改为复用同一转换真源；command path 继续通过同一 helper 返回 snapshot。
- **验证点**: 更新 public Run API 测试，断言 `cancel_run` 返回的终态 snapshot 与后续 `get_run` 的 `terminal_result_summary` 一致；断言 `start_run` 幂等重放已终态 Run 时返回 status-only `terminal_result_summary`，且不追加 EventLog 或 idempotency record。

## Changed Files

- `dayu/host/command.py`
- `dayu/host/read_api.py`
- `dayu/host/durable/state.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_public_run_api.py`
- `dayu/host/README.md`
- `docs/reviews/gateflow-aggregate-fix-review-findings-20260514.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_run_api.py`
  - Result: passed, 16 tests passed.
- `source .venv/bin/activate && pyright dayu/host tests/host`
  - Result: passed, 0 errors, 0 warnings, 0 informations.

## Docs Decision

- 已更新 `dayu/host/README.md` 的 Public Run Command Path，说明所有从 durable Run row 构造的 public `RunSnapshot` 使用同一终态摘要映射。

## New Risks / Open Questions

- **Open questions**: 无。
- **New risks**: 未发现新增架构或契约风险。

## Residual Risk Classification

- **Residual risk**: 低。
- **分类理由**: fix 限定在 public facade lifecycle guard 与 `RunSnapshot` row conversion 单一语义真源；未扩大到 Engine、OpenAI runner、admission state machine 或 schema。验证覆盖了 handoff 要求的关闭后错误优先级、无写入、command/read terminal summary 一致性和幂等重放无新增事实。
