# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Correction — Controller Validation

## 1. Gate 与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- 当前内部 remediation sub-WU / slice：既有 `R05-S1`。
- accepted plan commit：`201eb7f5287fc8e73d05b442e84369e19928236a`。
- implementation transition HEAD：`f52b81f9f4abd37a65c35ea98955a416079e5d9e` plus current uncommitted R05-S1 diff。
- plan correction artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_PLAN_CORRECTION_REVIEW`。

本次 correction 只修复 accepted plan 的 validation contract 漂移：把 R05 changed-owner coverage measurement 与无传播交集的 scheduler lifecycle owner 解耦，同时保留全部 R05 功能矩阵、逐文件覆盖率、静态检查、scan、README decision 与后续 aggregate gate。它没有改变产品语义、两 slices、产品 owner、产品 allowlist 或 deferred/no-code 边界。

## 2. Controller 独立验证

### 2.1 Root cause 与边界

Controller 读取并交叉核对：

- `HostDispatchScheduler.close()` 的 private close gate；
- active worker clean-EOF terminal closeout；
- `EngineEventIngestor._with_terminal_promotion_retry(...)` 的同步 wake；
- `_execution_health.py` 的 forced unavailability；
- 失败节点 `test_wake_queue_promotion_uses_tracked_async_promotion_task`；
- `workspace/tmp/test_r05_scheduler_close_probe.py`。

确定性 probe 独立结果为 `1 passed`，直接证明 root cause 是 scheduler close 与 terminal promotion coordination 的线性化缺口；不是 R05 timeout transaction、测试 fixture、wait policy 或 coverage instrumentation。`tests/host/test_dispatch_scheduler.py` 对 `wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord` 及 R05 删除/复用 primitive 的 source scan 为零；scheduler / ingestor / scheduler test 相对 R05 plan base 无本 slice diff。

因此不授权越界修 scheduler，不把失败标记为 flake / inherited pass / 已修复，不创建 issue，也不误归 Issue 175。

### 2.2 修订后 coverage measurement

Controller 在当前 S1 diff 上独立运行修订后的唯一候选命令：

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

结果：`1830 passed, 2 skipped, 5 deselected in 53.15s`；`dayu/host/durable/state.py=83%`、`dayu/host/wait_adapter.py=86%`。两个逐文件 `coverage report --fail-under=80` 均通过。

这只证明 changed-owner coverage measurement code-generation-ready，不提前接受 S1；S1 仍须在本 plan-correction review 闭环后重跑全部 required gates。

### 2.3 Plan contract

Controller 完整读取 plan correction diff 与 Agent artifact，确认：

1. §7.1、§7.2、§7.3 与 aggregate functional matrix 无 diff，coverage session 不替代任何功能节点。
2. §8 只新增 `tests/host/test_dispatch_scheduler.py` 排除，并保留既有 `test_toolruntime_executor.py` 排除；禁止第三个 ignore、deselect、xfail、retry 或 failure exemption。
3. measurement 必须整体绿色，两个实际 changed production files 继续分别执行 `--fail-under=80`。
4. §12 保留失败 session 的完整六元组、`1 failed, 1917 passed, 1 skipped, 5 deselected`、确定性 probe 与同源 root-cause disposition。
5. §13 继续把 coverage、pyright、changed-file Ruff、full Ruff residual、source / propagation / security scan、README decision 与 closed allowlist 作为 stop conditions。
6. §14 completion handoff 继续要求 focused / aggregate / coverage / static / scan / public smoke / Engine no-diff / residual evidence。
7. §15 把 scheduler 缺口登记为非 R05 产品 residual owner boundary；当前不修、不创建 issue、不归入 Issue 175。
8. §0、§14、§15 的 current gate 已统一为本次 validation plan correction，历史 `R05-PF-01..04`、`R05-PRR-F01` 只保留为已关闭事实。

Controller validation 曾发现 `R05-S1-VAL-CV-F01`：三处旧 second-plan-fix 文本仍冒充当前 gate。AgentCodex 同任务 follow-up 已精确关闭；stale 字符串扫描零命中。

### 2.4 Scope、digest 与 whitespace

- correction 自身精确修改：既有 R05 plan + Agent correction artifact。
- Controller governance 另修改：本 validation artifact、plan-drift Controller artifact 与 control doc。
- 七个受保护 implementation/test/design paths digest 仍为 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。
- `git diff --check`：PASS。
- production、tests、design、既有 implementation artifact 在 correction gate 内无内容漂移。
- README decision：本 gate 只修订 plan/review/control artifacts，无 README 职责范围变化。

## 3. 双路 review 要求

AgentMiMo 与 AgentDS 必须各自完整 review：

1. 修订后的 plan 全文，而不是只看 correction diff；
2. plan-drift Controller adjudication、Agent correction artifact 与本 validation artifact；
3. 当前七路径 R05-S1 产品/test/design diff及 implementation artifact，确认修订后 validation 足以覆盖真实 propagation；
4. 原 accepted plan review/fix/re-review final dispositions，确认历史 findings 保持关闭；
5. scheduler source/test direct evidence，挑战“排除整个 test file”是否隐藏 R05 回归或削弱安全/coverage；
6. retained late-publication fence、claim CAS、capacity、close deadline、typed lost、explicit lifecycle terminal、R04 config ownership 与 deferred scope。

review finding 必须给出直接证据、semantic owner、严重度和精确修复建议。两个 reviewer 的 verdict 不独立授权恢复 S1 validation；Controller 仍须裁决全部 findings，任何 accepted finding 必须由 AgentCodex 修复后双路完整 re-review。

## 4. 下一 gate

下一 gate：AgentMiMo / AgentDS 并发完整 `planreview` 本次 R05-S1 validation plan correction。

R05-S1 validation、R05-S2、scheduler 产品修复、code review、accepted product commit、aggregate gate、Issue 175、callback transport、统一 authorization、R06-R12、push 与 PR 均未授权。
