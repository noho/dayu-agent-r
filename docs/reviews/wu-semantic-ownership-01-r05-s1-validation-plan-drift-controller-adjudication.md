# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Drift — Controller Adjudication

## 1. Gate 与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature、issue，也不是重新打开独立旧 sub-WU。
- 当前内部 remediation sub-WU / slice：`R05-S1`。
- accepted plan commit：`201eb7f5287fc8e73d05b442e84369e19928236a`。
- implementation transition HEAD：`f52b81f9f4abd37a65c35ea98955a416079e5d9e`。
- implementation evidence：`docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`。
- Controller verdict：`REQUIRES_SAME_R05_VALIDATION_PLAN_CORRECTION`。

R05-S1 产品语义 transaction 已落在 accepted owner / allowlist 内，focused owner matrix 为绿；但 accepted plan §8 把完整 `tests/host` collection 同时当作 R05 两个 owner 的覆盖率测量 session，并错误记录为稳定全绿。当前直接证据证明该 session 会触发一个与 R05 wait observation 无传播交集、且位于 scheduler close / terminal promotion owner 的真实竞态。该失败不得豁免为 inherited / flaky，也不得由 R05 越界修 scheduler；正确动作是修订同一 R05 的验证计划，使 coverage measurement 与无关 scheduler lifecycle owner 解耦，同时保留所有 R05 功能、逐文件覆盖率、静态检查和后续 aggregate gate。

## 2. 产品语义与 allowlist 复核

Controller 读取了当前七个 tracked implementation paths 的完整 diff，确认：

1. `dayu/host/wait_adapter.py` 的 poll observation timeout 改为既有 `_release_with_backoff(...)`，写 `ADAPTER_ERROR / wait_observation_timeout`，不构造 typed lost、不调用 resolver，Wait / Run 保持 `WAITING`。
2. cancelled abandon timeout 改为同一 release/backoff owner，写 `ABANDON_ERROR / wait_abandon_timeout`，durable status 保持 `CANCELLED`，不写 terminal `poll_abandoned_at`。
3. `dayu/host/durable/state.py` 删除 invalid timeout-only terminal primitive 与其唯一已登记 unused import；没有 schema、enum、migration 或兼容 surface。
4. `docs/host/design.md` 只纠正 accepted plan 允许的 timeout transient diagnostic / release / backoff / non-terminal 句子，并保留 provider explicit applied / unsupported / noop terminal transition。
5. 四个 owner 测试覆盖 timeout 后 late publication 无 authority、下一轮恢复、durable claimability、authoritative typed lost 与 explicit lifecycle terminal preservation。
6. 当前 tracked diff 精确为七个 S1 implementation/test/design 路径加一个 implementation artifact；`git diff --check` 通过。

计划修订期间不得修改上述产品、测试或设计 diff。七路径受保护 diff digest 为：

```text
sha256:3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2
```

## 3. R05-S1-VAL-PD-F01：accepted coverage gate 与独立 scheduler owner 耦合

### 3.1 失败六元组

```text
exact command:
  python -m pytest -q tests/host
    --ignore=tests/host/test_toolruntime_executor.py
    --cov=dayu.host.durable.state
    --cov=dayu.host.wait_adapter
    --cov-branch
    --cov-report=term-missing
    --cov-report=json:workspace/tmp/r05-s1-coverage.json
node:
  tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
error:
  HostApiError: Host execution is unavailable
first stable frame:
  dayu/host/_execution_health.py:258 in raise_if_scheduler_unavailable
normalized fingerprint:
  scheduler close 已提交私有 close gate 时，active worker clean EOF terminal closeout 同步 wake queue promotion，被 force health gate 拒绝
validation HEAD:
  f52b81f9f4abd37a65c35ea98955a416079e5d9e plus current uncommitted R05-S1 diff
```

AgentCodex 的 failing session 为 `1 failed, 1917 passed, 1 skipped, 5 deselected`；失败 session 中两个 owner 已分别达到 83% / 86%，但整个 gate 不是 green，不能冒充通过。

### 3.2 同源 root cause

Controller 读取了 `HostDispatchScheduler.close()`、worker clean-EOF closeout、`EngineEventIngestor._with_terminal_promotion_retry(...)`、scheduler wake health gate 与失败测试，并独立运行 `workspace/tmp/test_r05_scheduler_close_probe.py`，结果 `1 passed`。该探针用事件顺序确定性证明：

1. scheduler `close()` 先提交 `self._closed = True`；
2. close 在取消并等待 promotion task 时让出 event loop；
3. 已 active 的 worker 此时以 clean EOF 完成，Host 提交 terminal closeout；
4. terminal closeout 同步调用 queue-promotion wake；
5. scheduler 私有 close gate 以 `force=True` 拒绝 wake，异常从 active task 传播回 `close()`。

因此这是 scheduler close 与 terminal promotion 的线性化/协调缺口，不是 R05 timeout transaction、测试 fixture、wait policy 或 coverage instrumentation 的错误。`tests/host/test_dispatch_scheduler.py` 对 `wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord` 及 R05 两个删除/复用 primitive 的 source scan 为零；`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、该测试文件相对 R05 plan base 均无本 slice diff。

修复它需要进入 `dayu/host/dispatch.py` / `dayu/host/engine_ingest.py` 或相应 scheduler owner tests，超出 R05-S1 closed allowlist，且与用户要求“不修改 accepted findings 无关既有代码”直接冲突。本 gate 不授权该修复，不创建新 issue，也不把它误归 Issue 175。

## 4. 计划修订的唯一允许内容

AgentCodex 必须在保留当前 S1 产品 diff 的前提下，修订既有 R05 plan 的 validation sections；这不是新 plan / 新 WU，也不改变两 slice、产品 owner、产品 allowlist 或 semantic contract。

修订必须同时满足：

1. 把 §8 的 S1 session 明确命名为“R05 changed-owner coverage measurement”，不是完整 Host regression acceptance。
2. 该 coverage session 只额外排除 `tests/host/test_dispatch_scheduler.py`；保留原先对 `tests/host/test_toolruntime_executor.py` 的排除。不得新增其它 ignore、deselect、xfail、retry 或 failure exemption。
3. 保留 §7.1 exact owner / focused / aggregate functional matrices；任何 R05 功能节点不得因 coverage session 修订而删除、放宽或改为只看 coverage。
4. 保留两个实际 changed production files 的逐文件 `--fail-under=80`；不得用 aggregate coverage 替代。
5. 在 baseline registry 中用本 artifact 的完整六元组和确定性 probe 更新原“root-cause-undetermined / required gate 全绿”记录，不得称为 flake、inherited pass 或已修复。
6. stop conditions 继续要求：修订后的 owner coverage session 必须整体绿色、两个文件各自 >=80%、pyright 零错误、changed-file Ruff 为零、full Ruff residual 可解释、allowlist/source/security scans 通过。
7. root cause 作为非 R05 产品 residual 明确记录 owner boundary 为 Host scheduler close / terminal promotion coordination；当前 umbrella 不实现它，也不擅自创建外部 destination。
8. 计划修订 artifact 必须记录当前受保护七路径 digest；修订期间不得改产品、测试、设计、既有 implementation artifact 或 control doc。

## 5. Controller 独立可行性证据

Controller 在当前 S1 diff 上运行候选 owner coverage session：

```text
python -m pytest -q tests/host
  --ignore=tests/host/test_toolruntime_executor.py
  --ignore=tests/host/test_dispatch_scheduler.py
  --cov=dayu.host.durable.state
  --cov=dayu.host.wait_adapter
  --cov-branch
  --cov-report=term-missing
  --cov-report=json:workspace/tmp/r05-s1-coverage-candidate-controller.json
```

结果：`1830 passed, 2 skipped, 5 deselected in 53.15s`；`dayu/host/durable/state.py=83%`，`dayu/host/wait_adapter.py=86%`。随后两个逐文件 `coverage report --fail-under=80` 均通过。

这项证据只证明修订后的 coverage measurement 可执行且不削弱逐文件阈值，不提前接受 S1。S1 仍须在计划修订通过双路完整 review 后恢复 Controller validation，完成所有尚未运行的 functional、coverage、pyright、Ruff、scan 和 README-decision gates。

## 6. 下一 gate

下一 gate 是同一 R05 内的 `R05-S1 validation plan correction`：

```text
AgentCodex 修订计划与产出 correction artifact
  -> Controller validation
  -> AgentMiMo / AgentDS 并发完整 plan-correction review
  -> AgentCodex fix 全部 accepted findings
  -> 并发完整 re-review
  -> Controller adjudication
  -> exact-scope accepted plan-correction commit
  -> 恢复 R05-S1 validation
```

R05-S2、scheduler 产品修复、code review、accepted product commit、aggregate gate、Issue 175、callback transport、统一 authorization 与 R06-R12 仍未授权。
