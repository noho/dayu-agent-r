# P10.5 Slice 6 Implementation Artifact

## 范围

本 Slice 只在 Host public-path smoke、测试支撑、Host/tests README 与既有 Host 测试契约迁移范围内实施；未修改 Engine、Service、配置入口、fresh schema、Run / Attempt / EventLog 状态机或新增 Service-facing public API。

## 修改文件

- 新增 `tests/host/public_smoke_support.py`，集中提供 Slice 6 public smoke 的 opener options、真实 provider case、精确 skip、watch terminal helper、deterministic worker / tool worker 支撑。
- 新增 `tests/host/test_public_open_host_multiturn_smoke.py`，覆盖 real-runner no-tool 两轮、双 watcher terminal 观察、queue client_request_id 幂等、per-run execution override freeze。
- 新增 `tests/host/test_public_tool_wiring_smoke.py`，覆盖 mock business tool wiring、accepted tool fact 到下一轮输入、`tool_names` 子集与空集合冻结。
- 新增 `tests/host/test_public_real_runner_matrix_smoke.py`，覆盖 mimo、deepseek、gemini、qwen 四个真实 runner public path。
- 新增 `tests/host/test_public_compact_smoke.py`，使用显式真实 LLM compactor adapter 覆盖 opener compact 后连续性。
- 扩展 `tests/host/test_public_cancel_smoke.py`、`tests/host/test_public_retry_replay.py`、`tests/host/test_public_steer.py`，收口 Slice 5 follow-up 的 cancel / close、retry / replay 幂等与 policy limit、steer WAITING 与 terminal race。
- 迁移旧 Host 测试到当前 P10.5 contract：`test_public_run_api.py`、`test_public_cancel_session_runs.py`、`test_active_cancel_dispatch.py`、`test_phase7_waiting_integration.py`、`test_admission_multiprocess.py`、`test_public_open_host_options.py`、`test_durable_schema.py`、`test_import_boundary.py`、`test_state_schema.py`。
- 窄修复 `dayu.host.engine_ingest`：空白 `FinalAnswerData.content` 不再写入 `RUN_SUCCEEDED`，而是按 `empty_final_answer` 收口为 `FAILED`，避免产生 public watch 无法投影的成功事实；新增 engine ingest 与 public watch 回归测试。
- 更新 `dayu/host/README.md` 与 `tests/README.md`，同步当前 public opener、low-level command handle、retry / replay、空 final answer 收口与 Slice 6 smoke 测试事实。
- P10.5 Slice 6 fix：`public_smoke_support.py` 抽出 provider 异常精确 skip helper，并扩展 503 / 429 / `RESOURCE_EXHAUSTED` / `QuotaFailure` / `RetryInfo` / overloaded / explicit unavailable 分类；`test_public_compact_smoke.py` 仅在真实 compactor adapter 抛出匹配 provider availability / quota / rate-limit 的 `RuntimeError` 时 skip，未匹配异常继续 hard fail。

## Coverage Table

| Signal / follow-up | 状态 | 证据 |
|---|---:|---|
| S1 real-runner no-tool two-turn public path | covered | `test_real_runner_no_tool_two_turn_public_path` 只通过 `open_host`、`submit_followup(queue)`、`watch_session_events` terminal final answer 断言，不读取 durable truth 作为 correctness assertion。 |
| S1 multi-client watch / queue idempotency | covered | `test_two_watchers_observe_same_terminal_event`、`test_concurrent_queue_uses_client_request_id_idempotency`。 |
| S1 per-run execution override freeze | covered | `test_submit_followup_field_level_execution_override_freezes_effective_config`。 |
| S2 mock-tool wiring smoke | covered | `test_mock_tool_fact_enters_memory_and_next_run_input`、`test_tool_names_subset_and_empty_freeze`；mock tool 只机械返回，未把 mock runner 计入 real-runner signal。 |
| S3 real-runner matrix | covered with one provider availability skip | mimo、deepseek、qwen 通过；gemini 因 provider quota / rate limit `RESOURCE_EXHAUSTED`、HTTP 429、`QuotaFailure`、`RetryInfo` 被精确 skip。skip reason 包含 `provider=gemini`、endpoint、`provider_quota_or_rate_limit=resource_exhausted` 与原始 provider message。503 / `UNAVAILABLE` / overloaded / transient server unavailable 仍只按明确 provider availability reason skip；API / schema / contract failure hard fail。 |
| S4 real compactor smoke | covered | `test_real_compactor_public_opener_compacts_and_preserves_continuity` 使用显式真实 LLM compactor adapter；未使用 `FakeContextCompactor` 计入 success signal。compactor provider secret / endpoint / network / temporary availability / quota / rate-limit 失败只按精确 marker skip，skip reason 包含 provider、endpoint、failure type 与原始错误消息；API / schema / public contract failure hard fail。 |
| S5 cancel / close boundary | covered | 新增 pre-dispatch watch cancel、active cancel public event、session-scoped cancel；既有 close/opener close/cancel distinct 测试继续由全量 Host suite 覆盖。 |
| Slice 5 follow-up: steer WAITING / terminal race | covered | `test_steer_waiting_run_creates_new_attempt_public_path`、`test_steer_terminal_race_rejects_non_active_target`。 |
| Slice 5 follow-up: retry / replay idempotency、retry policy limit、非目标状态 rejection | covered | `test_retry_run_replays_same_client_request_id_idempotently`、`test_replay_run_replays_same_client_request_id_idempotently`、`test_retry_run_policy_limit_rejects_second_retry`、`test_retry_and_replay_reject_non_target_source_status`。 |
| MiMo F1-F3 / DS N1-N7 public-path coverage follow-up | covered for Slice 6 owner | MIMO 与 DeepSeek 都进入 real-runner matrix 并通过；public smoke 不依赖 internal durable truth 或 mock runner。 |

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -rs`
  结果：`1 passed in 3.69s`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_public_cancel_smoke.py -q`
  结果：`11 passed in 21.46s`
- `source .venv/bin/activate && pytest tests/host/test_public_real_runner_matrix_smoke.py -q -rs`
  结果：`3 passed, 1 skipped in 30.18s`；skipped provider 为 `gemini`，原因是 endpoint 返回 HTTP 429 / `RESOURCE_EXHAUSTED` / `QuotaFailure` / `RetryInfo`，skip reason 包含 `provider=gemini`、endpoint、`provider_quota_or_rate_limit=resource_exhausted` 与原始 provider payload。
- `source .venv/bin/activate && pytest tests/host -q`
  结果：`695 passed, 1 skipped in 40.97s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  结果：`0 errors, 0 warnings, 0 informations`

Controller 复跑曾观察到真实 runner 返回空 final answer：payload 为 `{"content": "", "degraded": true, "filtered": false, "finish_reason": "length"}`，旧 Host ingest 会写入 `RUN_SUCCEEDED`，但 public `watch_session_events` 读取 `RUN_SUCCEEDED` 时要求 final answer `content` 是非空文本，导致 `HostDurableError` 转为 `HostApiError`。本 follow-up 的 root cause fix 是在 Engine ingest terminal plan 边界拒绝空白 final answer 成功收口，改写为 `RUN_FAILED(error_code=empty_final_answer)`，使 public watch 返回 typed failed terminal event 而不是崩溃。

Controller 复跑也曾观察到 Gemini 第二轮 provider 503：`UNAVAILABLE` / `The model is overloaded. Please try again later.`。真实 provider terminal failure 的 skip marker 只接受明确 provider availability reason：network unavailable、503、`UNAVAILABLE`、overloaded、transient server unavailable、try-again-later，以及 HTTP 429 / `RESOURCE_EXHAUSTED` / provider `QuotaFailure` / `RetryInfo`。非临时 API / schema / contract failure 仍 hard fail。

补充验证：`test_public_steer.py`、`test_public_retry_replay.py`、`test_public_resolve_wait_resume.py` 的 follow-up 覆盖也已被全量 `tests/host -q` 覆盖。

## Residual Risk / Owner

- 本次本地 real-runner matrix 有一个 Gemini provider quota / rate-limit skip：HTTP 429 / `RESOURCE_EXHAUSTED` / quota failure / retry delay。mimo、deepseek、qwen 真实 provider public path 已通过；Gemini coverage residual 归环境 provider quota，非 Host public contract residual。外部复跑若真实 compactor 或 runner 命中 503 overloaded / explicit unavailable / 429 quota / rate-limit，会记录精确 provider availability 或 quota / rate-limit skip；API / schema / contract failure 不会被 skip。
- 复验期间曾观察到一次 DeepSeek compactor 返回空摘要并 hard fail；后续重跑通过。该类空摘要不属于本 fix 允许的 provider availability / quota / rate-limit skip 范围，仍按 API / contract failure 处理。
- `RECOVERING` cancel、recovery takeover、远端 worker wait 恢复仍属于 Phase 11 owner；本 Slice 只验证当前 public path 支持的 accepted / queued / pre-dispatch / active worker / WAITING 子集。
- 多进程 admission 旧测试已迁移到当前 accepted pre-start contract；FIFO promotion 仍验证 durable promotion 顺序，但不把旧低层 closeout 返回对象里的即时 promotion timing 当作 public-path success signal。
