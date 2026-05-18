# P10.5 Slice 5 Implementation Artifact

## 改动概览

- `dayu/host/admission.py`
  - 接入 public `submit_followup(steer)` admission：仅允许同 Session active `RUNNING` / `WAITING` Run，在同一 Run 内追加 steer 输入并创建新 Attempt / execution / dispatch record。
  - 接入 ordinary local `retry_run`：仅允许 `FAILED` 源 Run，源 Run immutable，创建关联新 Run，按 `(source_run_id, client_request_id)` 幂等，当前 ordinary retry policy 每个源 Run 只允许一个 retry。
  - 接入 `replay_run`：仅允许 `SUCCEEDED` 源 Run，创建关联新 Run，使用 repair instruction 作为新输入，并冻结 no-tool execution / tool set。
- `dayu/host/command.py`
  - 将 public command facade 从 stable unsupported 切换到 admission service，并保持 active cancel registry 传播。
- `dayu/host/durable/state.py`
  - 增加 `RunStartReason.STEER`、source relation 统计 / 写入 helper、steer active Run / running Attempt CAS helper。
- `dayu/host/dispatch.py`
  - replay 关联 Run 在 no-tool builder 路径使用 `ToolExecutionMode.NO_TOOL_REPLAY`，与 admission 侧 `AgentPolicy.allow_tool_calls=False`、空 tool set 同源。
- `tests/host/test_public_steer.py`
  - 覆盖 public steer active `RUNNING` Run 后复用同 Run、创建新 Attempt 并终态成功。
- `tests/host/test_public_retry_replay.py`
  - 覆盖 FAILED retry 关联新 Run、SUCCEEDED replay 关联 no-tool 新 Run。
- `tests/host/test_public_resolve_wait_resume.py`
  - 覆盖 `open_host` public `resolve_wait` 唤醒 scheduler 并通过新 Attempt resume。
- `tests/host/test_public_cancel_smoke.py`
  - 覆盖 accepted / queued / active public cancel path smoke。

## README 同步

- 已更新 `dayu/host/README.md`：同步 public steer / retry / replay 当前可用范围，保留 recovery-only retry、startup recovery、orphan proof、stuck cancel watchdog、purge unsupported 等 deferred 边界。
- 已更新 `tests/README.md`：同步新增 public run / wait / event API 覆盖面。

## 验证结果

已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_retry_replay.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_cancel_smoke.py -q
```

结果：`5 passed`

已通过：

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：`0 errors, 0 warnings, 0 informations`

## Scope 说明

- 未修改 `dayu/host/durable/run_transition.py`；该文件当前 diff 为空。
- 未实现 LOST / RECOVERING retry、startup recovery、positive orphan proof、stuck cancel watchdog。
- 未新增 `interrupt_*` public API。
- 未实现 callback HTTP endpoint / poller loop。

## 残余风险

- ordinary retry policy 当前是本地固定上限：每个源 Run 一个 retry；尚未接入可配置 policy provider。
- replay no-tool 防线由 admission 冻结 no-tool effective facts 与 dispatch 选择 replay no-tool mode 共同保证；更深层 runtime 防御仍依赖既有 no-tool scope defense。
- active worker 若不响应 cancel，仍沿用既有 active cancel 行为；stuck cancel watchdog 按 handoff deferred。
