# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Implementation — AgentCodex

## 1. Gate 状态

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`，本轮仅执行既有 `R05-S1 implementation`。
- accepted plan commit：`201eb7f5287fc8e73d05b442e84369e19928236a`。
- control transition / implementation HEAD：`f52b81f9f4abd37a65c35ea98955a416079e5d9e`。
- 当前结论：`STOPPED_FOR_CONTROLLER_VALIDATION`。
- R05 timeout semantic transaction 已实现并通过 focused owner matrix；但 required full Host coverage command 再次触发 scheduler health-gate node。独立顺序探针已把根因定位到 scheduler close gate 与 clean-EOF terminal promotion 的线性化冲突。正确修复 owner 超出 R05-S1 closed allowlist，因此按 accepted plan stop condition 停止，不把该失败豁免为 inherited / known flake。
- 未进入 R05-S2、aggregate acceptance、implementation review、deep review、commit、push 或 PR。

## 2. 第一性原理与 owner 判定

observation timeout 只证明本次同步观察没有在 Host 预算内取得可发布结果，不能证明外部 job 丢失、provider 已取消或 lifecycle 已终止。直接代码证据显示：

1. `dayu/host/_wait_observation.py` 已用同一锁下的 token identity、state 与 generation 管理发布权；timeout 先 invalidates token，迟到结果只增加 dropped count。该 owner 正确，保持 no diff。
2. `dayu/host/wait_adapter.py` 是 observation 解释、claim release 与 backoff policy owner；旧 poll timeout 在此被错误提升为 `ResolveWaitLostOutcome`，旧 abandon timeout 在此调用 timeout-only terminal marker。
3. `dayu/host/durable/state.py::release_wait_record_poll_claim(...)` 已同时承诺 `WAITING` / `CANCELLED` 的原子 claim release、next-observe、attempt 与 diagnostic；无需新增 primitive。`mark_wait_record_poll_abandon_timeout(...)` 只服务错误 terminal semantic，应在 storage owner boundary 完整删除。
4. authoritative typed lost 仍由 common `resolve_wait` pipeline 拥有；provider explicit applied / unsupported / noop lifecycle outcome 仍由 `mark_wait_record_poll_abandoned(...)` 写 terminal `poll_abandoned_at`。

## 3. Test-first red 证据

在 production 未修改时，仅修改四个指定测试文件并运行 accepted plan 的三个新节点：

```text
python -m pytest -q \
  tests/host/test_wait_observation_runner.py::test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve \
  tests/host/test_wait_observation_runner.py::test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal \
  tests/host/test_phase7_waiting_integration.py::test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run
```

结果：`3 failed in 0.47s`，全部失败在预期 owner semantic assertion，无 fixture/setup 失败：

- poll owner node：旧实现 `WaitPollOnceResult.lost == 1`，新 contract 断言要求 `lost == 0`。
- abandon owner node：旧实现把固定时钟写入 `poll_abandoned_at`，新 contract 断言要求 `poll_abandoned_at is None`。
- Phase 7 integration node：同一旧 poll timeout 路径返回 `lost == 1`，新 contract 断言要求保持 WAITING。

完整输出：`workspace/tmp/r05-s1-red.txt`。

合法 durable owner preservation 在 production 修改前即为绿：

```text
tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due
tests/host/test_wait_record_state.py::test_poll_abandon_success_marks_row_and_clears_claim
```

结果：`4 passed in 0.33s`（第二节点含三个 explicit lifecycle 参数）。这证明正确路径是复用既有 release primitive，而不是新增 timeout primitive。

## 4. 实现改动

### `dayu/host/wait_adapter.py`

- poll `WaitObservationTimedOut` 不再构造 `WaitPollLost(ResolveWaitLostOutcome(...))`，也不调用 resolver；改为既有 `_release_with_backoff(...)`，写 `ADAPTER_ERROR / wait_observation_timeout`，Wait 与 Run 保持 WAITING。
- cancelled abandon `WaitObservationTimedOut` 不再调用 timeout-only terminal operation；改为同一 `_release_with_backoff(...)`，写 `ABANDON_ERROR / wait_abandon_timeout`，保持 CANCELLED 且不写 `poll_abandoned_at`。
- 删除 invalid durable primitive import、`_MarkWaitRecordAbandonTimeoutOperation` wrapper 与旧调用。
- 保留 authoritative `WaitPollLost`、Ready/NotReady、explicit lifecycle terminal、token fence、capacity、claim CAS、close gate 与 backoff 唯一真源。

### `dayu/host/durable/state.py`

- 完整删除 `mark_wait_record_poll_abandon_timeout(...)`，未保留 deprecated、compat、re-export 或 dead surface。
- 删除 accepted plan 已登记的 unused `TERMINAL_RUN_STATUS_VALUES` import。
- 保留 `release_wait_record_poll_claim(...)` 与 `mark_wait_record_poll_abandoned(...)`；schema、row、enum、codec、migration 均未修改。

### `docs/host/design.md`

- 只改写 accepted plan 指定的 cancelled abandon timeout 句：timeout 是 poll-local transient diagnostic，释放 claim 并按 policy backoff，保持 CANCELLED，不写 terminal `poll_abandoned_at`；只有 provider explicit applied / unsupported / noop 才写 terminal marker，且不调用 wait resolve。
- 未扩写 policy、schema 或 future terminal evidence contract。

### Tests

- runner owner tests覆盖 poll timeout release/backoff、late Ready drop、下一轮 Ready resolve，以及 abandon timeout release/backoff、late Applied drop、下一轮 explicit terminal。
- durable owner test覆盖 CANCELLED release 后到期可再次 claim，并保留 parameterized explicit terminal marker。
- Phase 7 owner integration覆盖真实 awaiting durable record 在 timeout 后继续 WAITING、下一轮 Ready 恢复。
- authoritative lost test增加 common resolver idempotency key 与 durable terminal 同源断言。

## 5. Green 与 focused validation

| 门禁 | 结果 |
|---|---|
| 三个 test-first nodes + 两个 durable preservation nodes | `7 passed in 0.41s` |
| accepted plan focused owner/branch matrix | `19 passed in 0.55s` |
| 四个指定 Host test files | `69 passed in 0.91s` |
| 六个 changed Python files Ruff | `All checks passed` |
| 四个 test files targeted pyright（production 修改前的 test-first 静态检查） | `0 errors, 0 warnings, 0 informations` |
| invalid timeout-only symbol guard | PASS，production/tests 零定义、零调用 |
| `git diff --check` | PASS |

Focused matrix 已同时覆盖：low-level token invalidation、shared close deadline、Ready、NotReady、authoritative typed lost、adapter snapshot error release、explicit applied terminal、abandon retry、active/expired claim、invalid deadline 与 durable explicit lifecycle terminal。

## 6. Required full Host coverage gate：失败并触发 stop

执行 accepted plan 原命令：

```text
python -m pytest -q tests/host \
  --ignore=tests/host/test_toolruntime_executor.py \
  --cov=dayu.host.durable.state \
  --cov=dayu.host.wait_adapter \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:workspace/tmp/r05-s1-coverage.json
```

结果：`1 failed, 1917 passed, 1 skipped, 5 deselected in 53.47s`。

失败六元组：

```text
exact command:
  上述完整 Host coverage command
node:
  tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
error:
  HostApiError: Host execution is unavailable
first stable frame:
  dayu/host/_execution_health.py:258 in raise_if_scheduler_unavailable
normalized fingerprint:
  scheduler close期间 clean EOF terminal closeout 同步 wake queue promotion，close gate 强制拒绝 wake
baseline SHA:
  5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

该失败不能继承或豁免。失败 session 已生成覆盖数据，但 gate 整体不是 green：

- `dayu/host/durable/state.py`：83%。
- `dayu/host/wait_adapter.py`：86%。
- 输出：`workspace/tmp/r05-s1-host-coverage.txt`、`workspace/tmp/r05-s1-coverage.json`。

### 独立 root-cause 定位

隔离原节点连续运行 20 次均通过；这只排除了稳定的单节点 semantic failure，不能作为豁免。随后在 `workspace/tmp/test_r05_scheduler_close_probe.py` 构造确定性顺序：active worker 先阻塞，在 `close()` 已置 close gate、正在等待 promotion task cancellation 时释放为 clean EOF，并等待 active task完成。探针预期 `HostApiError`，结果 `1 passed`，直接复现以下同源顺序：

1. `dayu/host/dispatch.py:2565` 先设置 `self._closed = True`。
2. `dayu/host/dispatch.py:2582-2585` 在取消并等待 promotion task 时让出 event loop；active worker 可在 active-task cancel 前完成。
3. `dayu/host/dispatch.py:3938-3975` 观察 clean EOF 并调用 `ingestor.close_clean_eof(...)`。
4. terminal closeout commit 后，`dayu/host/engine_ingest.py:2774-2778` 同步调用 `wake_queue_promotion(session_id)`。
5. `dayu/host/dispatch.py:2705-2709` 因 `_closed` 已为真而以 `force=True` 拒绝该 wake；异常最终从 `close()` 等待 active task传播。

因此 root cause 是 scheduler close gate 与 terminal promotion wake 的线性化/协调边界缺少一种合法 close-time terminal-promotion 处理，不是 R05 wait timeout transaction、测试顺序污染或可继承的旧失败。修复需要修改 `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 或相应 scheduler owner test；这些路径均不在 R05-S1 closed allowlist。按 stop condition 不在本 slice 加下游 catch、fallback、特例或 test-only 等待。

## 7. Ruff registry

implementation 前 machine-readable baseline：`workspace/tmp/r05-s1-ruff-baseline.json`，全量 `167` 条，baseline SHA 固定为 `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。本 S1 touched-file 两条登记为：

```text
(python -m ruff check dayu tests utils,
 dayu/host/durable/state.py,
 F401,
 dayu/host/durable/state.py:40:5,
 TERMINAL_RUN_STATUS_VALUES imported but unused,
 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1)

(python -m ruff check dayu tests utils,
 tests/host/test_phase7_waiting_integration.py,
 F401,
 tests/host/test_phase7_waiting_integration.py:8:22,
 datetime.UTC imported but unused,
 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1)
```

两条均已删除，六个 changed Python files Ruff 已全绿。由于 required full Host gate触发 stop，未继续执行最终 full Ruff residual `165` 的逐六元组核对；不得把预期数写成已验证结果。

## 8. 未完成门禁与 allowlist 状态

按 stop condition，以下命令未继续执行：

- 两个逐文件 `coverage report --fail-under=80`（失败 coverage session 的 term report 已显示 83% / 86%，但未冒充独立门禁结果）。
- full `python -m pyright dayu/ tests/ utils/`。
- final full Ruff residual 165 与逐六元组 diff。
- schema/no-diff、Engine/no-diff、R04 propagation/security scan 的完整 accepted-plan 命令组。
- S1 aggregate acceptance 与任何 S2 命令。

当前 working-tree tracked diff 精确为七个授权 implementation/test/design 路径，加本 artifact 后为八个授权路径。`_wait_observation.py`、`waiting.py`、`durable/schema.py`、Engine、Service、config、README、control、accepted plan 与其它既有 artifacts 均未修改。基于 transition HEAD 的 `git status --short` 无 allowlist 外 tracked path；`git diff --check` 通过。

README 决策：按 accepted plan，S1 不修改 README；最终 Host/tests README acceptance 仍属于未授权的 R05-S2。

## 9. 安全保留、deferred scope 与残余风险

已由 focused matrix 或 source guard保留：

- late publication token/generation fence；
- outstanding capacity 与 shared close deadline；
- claim token CAS、release/backoff 唯一真源与 next-due claimability；
- authoritative typed lost 仍经 common resolver terminalize；
- explicit applied/unsupported/noop lifecycle 仍写 terminal abandon marker且不调用 wait resolve；
- invalid timeout-only symbol在 production/tests 为零。

未进入且未实现：Issue 175、process-backed containment、callback transport、统一 authorization/permission、future lost evidence policy、future cancelled-abandon terminal evidence、R06+、R05-S2。

R05 自身残余风险保持 accepted plan 原裁决：若 CANCELLED wait 的 abandon observation 长期 timeout 且 provider 永不返回 explicit lifecycle terminal outcome，record 会按 capped backoff 长期重试；R05 的 claim CAS、finite timeout、capacity cap、late-result fence 与 backoff cap 只限制资源，不创造 terminal evidence。

新增 blocking risk：scheduler close/terminal promotion 竞态会使 required Host gate非确定性失败，并可由确定性顺序探针复现。其 owner 超出本 S1 scope，必须由 Controller 决定独立修复/前置 transition 后，才能恢复本 S1 剩余门禁。

## 10. Controller handoff

请 Controller 裁决 scheduler close/terminal promotion root cause 的独立 owner 与修复 gate，或提供已修复的 accepted base/transition。当前 R05 semantic diff 保留供 Controller validation，但 R05-S1 不声明 accepted/completed，不进入 S2，不 commit/push。
