# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S3 Controller Validation

## 结论

`pass-for-code-review`。

Controller 独立复验接受 AgentCodex 的 S3 implementation handoff。当前变更仍停留在 S3 allowed production files、allowed tests/docs 与一个 controller 授权的直接受影响测试扩展内：`tests/host/test_public_contracts.py` 仅同步新增 public `HostApiErrorCode.UNAVAILABLE` 枚举断言，没有生产兼容 shim。

## Scope 复核

- Production 变更在 `dayu/host/_execution_health.py`、`dayu/host/api.py`、`dayu/host/open_host.py`、`dayu/host/admission.py`、`dayu/host/dispatch.py`、`dayu/host/__init__.py` 内。
- S2 actor、Service、CLI 未修改。
- Docs/README 变更在 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md` 内，符合触发规则。
- `tests/host/test_public_contracts.py` 是 controller 复验发现的直接受影响 public enum contract 测试，已作为 narrow scope extension 接受。

## 验证

```bash
source .venv/bin/activate
pytest tests/host/test_scheduler_health.py tests/host/test_open_host_runtime.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_submit_followup_public_contract.py tests/host/test_public_retry_replay.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_admission_multiprocess.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
```

结果：`212 passed in 8.30s`。

```bash
source .venv/bin/activate
pytest tests/host/test_public_contracts.py -q
```

结果：`45 passed in 0.32s`。

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## Source Scan 分类

```bash
rg -n "HostExecutionHealthGate|STARTING|READY|UNAVAILABLE|CLOSING|CLOSED|report_fatal" dayu/host/_execution_health.py dayu/host/open_host.py dayu/host/dispatch.py
```

分类：`HostExecutionHealthGate`、state、transition 与 public unavailable detail 由 `dayu/host/_execution_health.py` 拥有；`open_host.py` 负责 assembly、READY handoff 与 close sequencing；`dispatch.py` 只消费 shared gate 并将 critical fatal 报告到唯一 `report_fatal()`。

```bash
rg -n "idempotent_replay|wake_dispatch|wake_queue_promotion|HostTransactionRetryExhaustedError" dayu/host/admission.py dayu/host/command.py dayu/host/dispatch.py
```

分类：S3 new-work admission replay wake 由 `dayu/host/admission.py` 从 durable Run/Attempt/dispatch snapshot 派生；`dispatch.py` 的 retry exhaustion 分支进入 warning + poll interval backoff，不再 self-close；`command.py` 中的 `not idempotent_replay` 命中属于 wait/callback resume command path，不是 S3 new-work admission wake owner。

```bash
rg -n "if .*_closed.*return|Queue\(maxsize=1\)" dayu/host/dispatch.py dayu/host/open_host.py
```

分类：唯一命中为 `dayu/host/dispatch.py` active-cancel watchdog `asyncio.Queue(maxsize=1)`，按 S3 plan 明确留给 S5 level-triggered watchdog owner；未发现 closed scheduler wake 静默 return。

## Residual / Review Focus

- S5-owned active-cancel watchdog `Queue(maxsize=1)` 未提前修复，符合 S3 non-goal。
- wait/callback resume replay wake suppression 未在 S3 扩张处理，需在对应 wait owner slice 或后续 review 中裁决。
- Code review 需重点检查 deterministic race tests 是否只控制时序而没有替代 durable truth，以及 admission lease 是否覆盖 actor future、commit after-callback 与 wake completion。
