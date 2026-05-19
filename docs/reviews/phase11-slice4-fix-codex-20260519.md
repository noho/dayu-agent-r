# Phase 11 Slice 4 Fix Codex - 2026-05-19

## 动机判断

- S4-F1 成立：`cancel_session_runs` 的 unsupported diagnostic 已支持 `RECOVERING`，但错误信息仍未列出该状态，属于 public-facing contract 文案滞后。
- S4-F2 成立：`_cancel_recovering` 返回 `released_active_slot=True` 的语义是释放 session active slot 与 queue promotion eligibility，不是 active worker cancel；局部注释可以降低后续维护误判。
- S4-F3 成立：既有测试覆盖了 RECOVERING cancel facts 与 session-scope cancel，但缺少同一 `client_request_id` 在 RECOVERING `cancel_run` 上的幂等重放窄验证。

## 改动

- `dayu/host/admission.py`
  - 仅更新 `cancel_session_runs` unsupported error message，加入当前支持的 `RECOVERING`，未改变 supported target 判定逻辑。
  - 在 `_cancel_recovering` 的 `released_active_slot=True` 旁补充极窄中文注释，明确它不是 active worker cancel。
- `tests/host/test_public_cancel_session_runs.py`
  - 新增 `test_cancel_run_recovering_replay_is_idempotent_per_run_id`。
  - 覆盖同一 RECOVERING run 重放同一 `client_request_id` 不追加第二组 `CANCEL_REQUESTED` / `RUN_CANCELLED`。
  - 覆盖同一 `client_request_id` 用于另一个 RECOVERING run 时仍落到该 run，证明幂等 scope 未从 `run_id` 漂移。

## README 检查

- 已检查 `dayu/host/README.md`，其中 `cancel_run`、`cancel_session_runs` 与 `RECOVERING` 描述已经覆盖当前语义。
- 本次 bounded fix 不改变接口、命令、配置入口或稳定架构表述，因此无需修改 README。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py::test_cancel_run_recovering_replay_is_idempotent_per_run_id -q`
  - 结果：`1 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q`
  - 结果：`20 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## 风险与未覆盖项

- 本 fix 未重开 RECOVERING 创建路径，也未新增端到端 recovery setup；裁决已明确该方向为 current-slice no-action。
- 本 fix 未修改 supported target 判定、状态机、WorkerProxy 传播或 queue promotion 行为。

FIX_COMPLETE
