# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S6 Controller Validation

## 结论

`pass-for-code-review`。

Controller 独立复验接受 AgentCodex 的 S6 implementation handoff。当前变更停留在 S6 allowed production files、allowed tests/docs 内；`dayu/fins/` diff 为空，未修改 Service、CLI、Engine、S3 health、S4 recovery 或 S7/S8 scope。

## 验证

```bash
source .venv/bin/activate
pytest tests/host/test_wait_expiry_closeout.py tests/host/test_wait_observation_runner.py tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_open_host_options.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py -q
```

结果：`137 passed in 2.65s`。

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --name-only -- dayu/fins/
git diff --check
```

结果：Fins diff 空；`git diff --check` 通过。

## Source Scan 分类

- `thread.join()` / optional close timeout / unbounded feeder join scan：零命中，符合 S6 预期。
- `_release_expired_or_invalid_boundary|WAIT_EXPIRED`：旧 release helper 无命中；`WAIT_EXPIRED` 只在 `dayu/host/waiting.py` late-rejection reason 与 expiry owner 中命中。
- `ExpireWaitInput|_expire_wait_in_transaction|ResolveWaitFailedOutcome|fail_run_from_waiting_in_transaction`：poll/direct/callback 路径均进入 `waiting.py` common expiry owner，并复用 existing failed wait transition helper。
- `max_outstanding_adapter_calls|ACTIVE|INVALIDATED|FINISHED|publish`：observation cap/token/publish gate 的唯一 owner 在 `dayu/host/_wait_observation.py`，`wait_adapter.py` 仅注入 policy 与消费 runner。

## Review Focus

- Code review 需重点确认 FAILED deadline-expiry 与 LOST observation-timeout 没有混用。
- late result 必须发生在 expiry commit/projection/promotion 后，不能出现 caller 被拒绝但 durable 仍 WAITING。
- Observation thread 不得持 durable authority；late publish 必须被 token invalidation 拒绝。
- Shared close deadline 必须有界，且 CLOSING/STOPPED 反映 poller 与 tracked threads 的真实状态。
