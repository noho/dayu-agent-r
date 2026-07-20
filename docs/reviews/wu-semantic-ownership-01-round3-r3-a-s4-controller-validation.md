# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S4 Controller Validation

## 结论

`pass-for-code-review`。

Controller 独立复验接受 AgentCodex 的 S4 implementation handoff。当前变更停留在 S4 allowed production files、allowed tests/docs 内，未修改 S3 health lease、watchdog、cancel command、public API、Service、CLI、Fins 或 Engine。

## Scope 复核

- Production：`dayu/host/recovery.py`、`dayu/host/open_host.py`、`dayu/host/durable/state.py`。
- Tests：`tests/host/test_recovery_scan.py`、`tests/host/test_open_host_runtime.py`。
- Docs：`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`。
- `tests/host/test_recovery_dispatch.py`、`tests/host/test_recovery_multiprocess.py`、`tests/host/test_admission_multiprocess.py` 作为 required regression matrix 参与验证，未修改。

## 验证

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_multiprocess.py tests/host/test_open_host_runtime.py tests/host/test_admission_multiprocess.py -q
```

结果：`60 passed in 6.72s`。

```bash
source .venv/bin/activate
python -m pyright dayu/host/recovery.py dayu/host/open_host.py dayu/host/durable/state.py tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## Source Scan 分类

```bash
rg -n 'read_non_terminal_runs\(|OFFSET|fetchall\(' dayu/host/recovery.py dayu/host/durable/state.py
```

分类：

- `dayu/host/recovery.py` 无命中，startup recovery call graph 不再调用全量 `read_non_terminal_runs()`，也不使用 `OFFSET` 或直接 `fetchall()`。
- `dayu/host/durable/state.py:1927` 是 legacy full reader 定义，S4 recovery 不引用；删除它超出当前 slice。
- `dayu/host/durable/state.py:2075` 是 S4 keyset page reader 的唯一新增 `fetchall()`，SQL 明确带 `LIMIT ?`，参数来自 typed `batch_size`。
- 其它 `fetchall()` 命中是既有非 S4 readers，不在 startup recovery call graph。

```bash
rg -n 'accepted_event_sequence|upper_watermark|cursor|batch_size|policy_now' dayu/host/recovery.py dayu/host/durable/state.py
```

分类：`NonTerminalRunKeysetCursor` 与 `read_non_terminal_run_upper_watermark()` / `read_non_terminal_runs_keyset_page()` 是 durable keyset/watermark reader owner；`StartupRecoveryScanner` 拥有 default `batch_size`、fixed `policy_now`、batch operation、committed cursor 推进与 commit-after-wake orchestration。未发现 projection/read model 或 opener 下游补偿成为 recovery truth owner。

## Residual / Review Focus

- legacy `read_non_terminal_runs()` 仍存在但不在 S4 recovery call graph，code review 需确认没有 indirect call path。
- S4 通过 actor-thread `_StartupRecoveryActorOperation` 执行 recovery；review 需重点确认 READY handoff 只发生在全部 batches 和 wakes 成功后，失败路径不会 READY。
- 一个 batch commit 后多个 wake callback 之间不是跨 callback 原子事务；当前裁决为非 stop condition，因为 durable pending truth 允许下一 healthy opener 幂等重放。review 可继续检查是否存在 rollback batch wake。
