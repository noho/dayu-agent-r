# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S5 Controller Validation

## 结论

`pass-for-code-review`。

Controller 独立复验接受 AgentCodex 的 S5 implementation handoff。当前变更停留在 S5 allowed production files、allowed tests/docs 内，未修改 S3 health state machine、S4 recovery cursor、wait adapter、public API、Service、CLI、Fins 或 Engine。

## Scope 复核

- Production：`dayu/host/command.py`、`dayu/host/dispatch.py`、`dayu/host/admission.py`。
- Tests：`tests/host/test_active_cancel_dispatch.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_admission_multiprocess.py`、`tests/host/test_open_host_runtime.py`。
- Docs：`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`。
- Required regression matrix also covered `tests/host/test_public_cancel_session_runs.py` and `tests/host/test_public_run_api.py` without modifications.

## 验证

```bash
source .venv/bin/activate
pytest tests/host/test_active_cancel_dispatch.py tests/host/test_dispatch_scheduler.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py tests/host/test_admission_multiprocess.py tests/host/test_open_host_runtime.py -q
```

结果：`165 passed in 7.10s`。

```bash
source .venv/bin/activate
python -m pyright dayu/host/command.py dayu/host/dispatch.py dayu/host/admission.py tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## Source Scan 分类

```bash
rg -n '_is_deferred_cancel_state|Queue\(maxsize=1\)|except asyncio\.QueueFull' dayu/host/command.py dayu/host/dispatch.py
```

结果：零命中，`rg` exit code 1，符合删除型 scan 预期。command 层 post-write deferred reader、bounded watchdog queue 与 QueueFull 吞 wake 均已移除。

```bash
rg -n 'asyncio\.Event|wake_active_cancel_watchdog|_CancelRunOperation' dayu/host/command.py dayu/host/dispatch.py
```

分类：`dayu/host/dispatch.py` 命中唯一 watchdog `asyncio.Event` owner 和 scheduler wake；`dayu/host/command.py` 命中 typed wake port 与 commit 后调用链。`_CancelRunOperation` 不在 command/dispatch 命中，因为真实 owner 位于 admission。

补充 owner scan：

```bash
rg -n '_CancelRunOperation|_CancelRunClassification|_CancelRunOperationResult|released_active_slot|wake_queue_promotion' dayu/host/admission.py
```

分类：transaction-local cancel classification 定义、operation 返回类型、service 映射、released active slot 与 promotion wake 触发点均在 admission owner 内。

## Residual / Review Focus

- periodic watchdog scan 保留为 restart/fallback reconcile，正确性不再依赖它补偿 bounded queue drop。
- Physical provider/tool hard stop remains non-goal; S5 only owns Host durable cancel governance.
- Multiprocess deferred fixture 使用缺 child dispatch row 的 defensive snapshot 覆盖分类，不是 production fallback/compat branch。
- Code review 需重点确认 command 层没有二次 durable read、错误码只来自 write transaction snapshot，以及 level Event 不会 busy-loop 或丢 tick 期间新事实。
