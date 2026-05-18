# P10.5 Slice 6 Fix Artifact

## Fix Scope

本次 fix 响应 Controller CF1 / AgentDS H1，仅修正 real compactor smoke 的 provider 环境失败处理。

真实 compactor provider 在 `_RealLLMContextCompactor._run_llm_summary` / `run_agent_and_wait` 路径中返回明确 transient unavailable / quota / rate-limit 时，测试现在按 P10.5 plan 允许的 provider availability 条件精确 skip。覆盖的环境失败包括 503、429、`RESOURCE_EXHAUSTED`、`QuotaFailure`、`RetryInfo`、overloaded、transient unavailable 与 explicit unavailable。

本 fix 不 broad skip；API、schema、public contract failure 继续 hard fail。`FakeContextCompactor` 或 mock compactor 不计入 real compactor success signal。

## 修改文件

- `tests/host/public_smoke_support.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/README.md`
- `docs/reviews/phase10-5-slice6-implementation-codex-20260518.md`

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -rs`
  结果：`1 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_public_cancel_smoke.py -q`
  结果：`11 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_real_runner_matrix_smoke.py -q -rs`
  结果：`3 passed, 1 skipped`；skipped provider 为 Gemini，原因为 provider quota / rate-limit。
- `source .venv/bin/activate && pytest tests/host -q`
  结果：`695 passed, 1 skipped`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  结果：`0 errors, 0 warnings, 0 informations`
- Controller 复跑同一验证通过，并确认 `git diff --check` clean。

## Residual Risk

- Gemini quota / rate-limit skip 属于环境 provider residual，不是 Host public contract residual。
- 复验期间观察到一次 DeepSeek compactor 空摘要；该情况仍 hard fail，符合本 fix 不 broad skip、只跳过 provider availability / quota / rate-limit 的边界。
