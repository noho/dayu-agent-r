# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Correction — AgentCodex

## 1. Gate 身份与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- 内部 remediation sub-WU / slice：既有 `R05-S1`；这不是新 WU、feature、issue，也不重新做 goal confirmation。
- accepted plan commit：`201eb7f5287fc8e73d05b442e84369e19928236a`。
- implementation transition / validation HEAD：`f52b81f9f4abd37a65c35ea98955a416079e5d9e` plus current uncommitted R05-S1 diff。
- Controller finding：`R05-S1-VAL-PD-F01`。
- 本 gate 结论：`READY_FOR_CONTROLLER_VALIDATION`。
- 本次只是 accepted plan 的同一 R05 validation correction；两 slices、产品 owner、产品 allowlist 与 semantic contract 均未改变。
- 未进入 R05-S1 剩余 validation、R05-S2、code review、commit、aggregate gate、Issue 175、scheduler 产品修复、push 或 PR。

严格 write allowlist 只有：

1. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`

## 2. 第一性原理与 semantic owner 判定

修订动机成立且是 blocking plan drift：accepted plan §8 把完整 `tests/host` collection 同时当作 R05 changed-owner coverage measurement 与完整 Host regression acceptance，并记录成稳定全绿；实际 session 触发了一个与 R05 wait observation 无 source / propagation 交集、但可由确定性事件顺序复现的 scheduler lifecycle 缺口。继续要求该无关 owner 在 R05 coverage session 内绿色，会迫使 R05 越界修改 scheduler；把失败直接豁免为 flake / inherited 又会伪造验证事实。

唯一正确 owner 分界是：

- R05 plan 的 validation section 拥有本 R05 changed-owner coverage measurement 的 collection scope、逐文件阈值、失败登记和 completion handoff，因此 correction 必须落在 plan owner boundary。
- `HostDispatchScheduler.close()` 与 terminal promotion wake coordination 拥有独立 scheduler close 线性化缺口；它不是 `WaitPoller` timeout transaction、测试 fixture、wait policy 或 coverage instrumentation 的语义。
- 当前 gate 不授权 scheduler 产品 owner 修改，也不授权创建外部 destination；因此只把 coverage measurement 与该独立 owner test 解耦，同时保留该缺口的完整证据与 residual owner boundary。

该方案没有引入新 profile、兼容分支或一般失败豁免：只在既有 coverage measurement 中增加一个经直接证据证明无 R05 传播交集的精确文件排除，仍要求全部 R05 功能矩阵、measurement 整体绿色、两个 changed owner 的逐文件阈值以及所有静态/scan/README gates。

## 3. 修订前后命令

### 修订前

```bash
python -m pytest -q tests/host \
  --ignore=tests/host/test_toolruntime_executor.py \
  --cov=dayu.host.durable.state \
  --cov=dayu.host.wait_adapter \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:workspace/tmp/r05-s1-coverage.json
python -m coverage report --include='dayu/host/durable/state.py' --fail-under=80
python -m coverage report --include='dayu/host/wait_adapter.py' --fail-under=80
```

### 修订后：R05 changed-owner coverage measurement

```bash
python -m pytest -q tests/host \
  --ignore=tests/host/test_toolruntime_executor.py \
  --ignore=tests/host/test_dispatch_scheduler.py \
  --cov=dayu.host.durable.state \
  --cov=dayu.host.wait_adapter \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:workspace/tmp/r05-s1-coverage.json
python -m coverage report --include='dayu/host/durable/state.py' --fail-under=80
python -m coverage report --include='dayu/host/wait_adapter.py' --fail-under=80
```

命令只增加 `tests/host/test_dispatch_scheduler.py` 排除，并保留原 `tests/host/test_toolruntime_executor.py` 排除。计划明确禁止其它 ignore、deselect、xfail、retry 或 failure exemption。

## 4. Root-cause disposition

### 4.1 完整失败六元组

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

失败 session：`1 failed, 1917 passed, 1 skipped, 5 deselected`；其中 `dayu/host/durable/state.py=83%`、`dayu/host/wait_adapter.py=86%`，但 session 整体不是绿色，不能冒充通过。

### 4.2 确定性 probe 与同源 root cause

Controller 独立运行 `workspace/tmp/test_r05_scheduler_close_probe.py`，结果 `1 passed`。该 probe 以事件顺序证明：

1. scheduler `close()` 先提交 `self._closed = True`；
2. close 取消并等待 promotion task 时让出 event loop；
3. 已 active worker 此时以 clean EOF 完成并提交 terminal closeout；
4. terminal closeout 同步调用 queue-promotion wake；
5. scheduler 私有 close gate 以 `force=True` 拒绝 wake，异常从 active task 传播回 `close()`。

因此 root cause 是 Host scheduler close / terminal promotion coordination 的线性化缺口。`tests/host/test_dispatch_scheduler.py` 对 `wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord` 及 R05 两个删除/复用 primitive 的 source scan 为零；`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 和该测试文件相对 R05 plan base 均无本 slice diff。

完整 disposition：这不是 flake、不是 inherited pass、不是已修复问题，也不是 R05 timeout semantic transaction 的失败。修复需要进入 scheduler / terminal-promotion 产品 owner，超出 R05-S1 closed allowlist；当前不修、不创建 issue、不归入 Issue 175，后续 destination 只能由 Controller / 用户另行裁决。

## 5. Controller 候选 session 证据

Controller 在当前 R05-S1 diff 上独立运行修订后的候选 measurement，结果：

- `1830 passed, 2 skipped, 5 deselected in 53.15s`；
- `dayu/host/durable/state.py=83%`；
- `dayu/host/wait_adapter.py=86%`；
- 两个逐文件 `coverage report --fail-under=80` 均通过。

这项证据只证明修订命令可执行且没有削弱逐文件阈值，不提前接受 S1。plan correction 通过 Controller validation、双路完整 review、必要 fix / re-review 与 Controller adjudication 后，R05-S1 才能恢复尚未运行的 functional、coverage、pyright、Ruff、scan 和 README-decision gates。

## 6. Plan correction 内容

- §7.1 的 test-first、durable preservation、focused owner nodes 与 Host focused files 原样保留；§7.2、§7.3 及 aggregate functional matrix 也未修改。
- §8 将 session 精确命名为 `R05 changed-owner coverage measurement`，明确它不是完整 Host regression acceptance；只增加 scheduler test file 排除，继续要求 session 整体绿色和两个实际 changed production files 各自 `--fail-under=80`。
- §12 用 Controller artifact 的完整失败六元组、失败结果、确定性 probe、同源 root cause、source/propagation 证据与候选 session 结果替换“required gate 当前无失败”的失真记录。
- §13 将修订后 measurement 整体绿色、逐文件阈值与禁止第三个排除/失败豁免写入 stop conditions；任何 scheduler 产品修复需求必须停回 Controller。
- §14 明确本 correction 的 review/completion handoff、受保护 digest 与下一步只回 Controller validation；原 accepted-plan review 要点继续保留。
- §15 把 scheduler close / terminal promotion coordination 记录为非 R05 产品 residual owner boundary，当前不修、不创建 issue、不归 Issue 175。

## 7. 受保护实现 digest 与精确路径

digest 复核命令：

```bash
git diff --binary -- \
  dayu/host/durable/state.py \
  dayu/host/wait_adapter.py \
  docs/host/design.md \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_record_state.py \
  | shasum -a 256
```

修订前 digest：`3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。

修订后 digest：`3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。

受保护七路径精确为：

1. `dayu/host/durable/state.py`
2. `dayu/host/wait_adapter.py`
3. `docs/host/design.md`
4. `tests/host/test_phase7_waiting_integration.py`
5. `tests/host/test_wait_adapter_polling.py`
6. `tests/host/test_wait_observation_runner.py`
7. `tests/host/test_wait_record_state.py`

本 correction 精确 changed paths 只有：

1. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`

既有 implementation artifact、Controller artifact、control doc、产品、测试与设计 diff 均未修改。

## 8. Validation 与 README decision

- protected seven-path digest：PASS，修订前后均为 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。
- correction write allowlist：PASS，只有计划与本 artifact。
- §7 functional matrix preservation：PASS，plan diff 无 §7 hunk。
- §8 exclusion contract：PASS，修订后的 measurement 精确包含两个 `--ignore`，没有新增其它 failure exemption。
- `git diff --check`：PASS。
- 新 artifact 另以 `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md` 检查：无 whitespace error 输出；exit 1 仅表示 `/dev/null` 与新文件存在预期内容差异。
- pytest / coverage / pyright / Ruff：本 gate 未重跑；这是 doc-only validation-plan correction，任务明确下一步只回 Controller validation，不能把 Controller 候选证据冒充 AgentCodex 对 S1 的 acceptance。所有这些 gate 均在 plan 中保持强制且未放宽。
- README decision：不更新。当前只修订 `docs/host/` 下的实施计划与 `docs/reviews/` artifact，没有用户入口、产品行为、分层、装配或 README 职责范围变化。

## 9. Residual risks、完成状态与 handoff

- R05 原 residual 不变：若 cancelled wait 的 abandon observation 长期 timeout 且 provider 永不返回 explicit lifecycle terminal outcome，record 仍可能按 capped backoff 长期重试；R05 不创造 terminal evidence。
- 新登记的非 R05 产品 residual：Host scheduler close / terminal promotion coordination 线性化缺口。当前只在 coverage measurement collection 中与其解耦；没有产品修复、failure waiver、外部 issue 或 Issue 175 归属。
- correction artifact 与 plan 均保留完整 root-cause evidence，后续不得把该 residual 重写成 flake、inherited pass 或已修复。
- 当前 gate 状态：`READY_FOR_CONTROLLER_VALIDATION`。
- 唯一下一步：Controller validation；通过后才可按 Controller 顺序进入 AgentMiMo / AgentDS 并发完整 plan-correction review。AgentCodex 在此停止等待 Controller。

## 10. Controller follow-up closure

Controller validation follow-up 指出计划中三处历史 gate 文本仍冒充当前 gate。直接读取确认 finding 成立，本次在原 correction write allowlist 内完成以下精确修复：

1. §0 把 `R05 remediation second plan fix`、`WAITING_FOR_CONTROLLER_VALIDATION_AFTER_SECOND_PLAN_FIX` 与旧 second-plan-fix owner / allowlist 叙述改为：同一 R05-S1 validation plan correction 已完成，当前等待 Controller validation；接受后只进入 AgentMiMo / AgentDS 双路完整 plan-correction review。
2. §14 删除“本轮 second plan-fix + 旧 `wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md`”当前态，改为本 correction artifact 已完成并等待 Controller validation；后续 review 覆盖完整修订后的 validation / gate-state contract。
3. §15 末尾把“Controller 对 second plan-fix validation”改为 Controller validation 当前 R05-S1 validation plan correction；接受后只进入双路完整 plan-correction review。

历史 `R05-PF-01` 至 `R05-PF-04` 与 `R05-PRR-F01` 已关闭事实全部保留，但不再作为当前 gate。两 slices、产品 owner、产品 allowlist、semantic contract、coverage / static / scan gates 与 residual disposition 均未改变。

follow-up 仍只修改：

1. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`

受保护七路径 digest 在 follow-up 前后均为 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`；`git diff --check` 通过。当前状态继续为 `READY_FOR_CONTROLLER_VALIDATION`，唯一下一步是 Controller validation，AgentCodex 在此停止。
