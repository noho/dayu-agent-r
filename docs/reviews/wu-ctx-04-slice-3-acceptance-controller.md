# WU-CTX-04 Slice 3 最终验收裁决（Controller）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- baseline：accepted Slice 2 commit `4ca0810b27eded188e4f9aae54756a871eb371ed`
- gate：code re-review acceptance
- implementation：`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`
- initial review adjudication：
  `docs/reviews/wu-ctx-04-slice-3-code-review-controller-adjudication.md`
- review fix：`docs/reviews/wu-ctx-04-slice-3-review-fix-codex.md`
- AgentMiMo re-review：`docs/reviews/wu-ctx-04-slice-3-re-review-mimo.md`
- AgentDS re-review：`docs/reviews/wu-ctx-04-slice-3-re-review-ds.md`
- decision：`pass`
- blocking open questions：None

## Outcome

Slice 3 通过。Controller 接受两路 re-review 的共同结论：`CTRL-S3-001`、
`CTRL-S3-002`、`CTRL-S3-003` 均已在各自 semantic owner 边界完成 root-cause
closure，未发现新的 actionable finding。

本裁决不是按 reviewer 票数接受。Controller 已复读 production diff、fix artifact、两路
re-review artifact，并独立运行根因反例与 pyright；证据足以形成 accepted Slice 3
保护提交。

## Accepted finding closure

### CTRL-S3-001 — fixed

- execution-owner cancel poll 已从 attachment-authorized Session reconciliation /
  proactive compactor await 链拆出，成为独立 critical periodic task。
- task 以稳定 health component 接入 shared supervisor，并覆盖 open、later-open-failure
  cleanup 与 mandatory close join。
- barrier 测试确定性证明 Session reconciliation 持续阻塞时，旧 execution owner 仍能按
  exact local worker identities 传播 durable cancel；没有恢复 workspace-wide scan。

### CTRL-S3-002 — fixed

- `CANCEL_REQUESTED.reason` 由 run-transition canonical fact owner 通过 typed
  `OwnedAttemptCancelDelivery` 投影；accepted
  `OwnedAttemptCancelTarget(identity, cancel_request_event_id)` contract 保持不变。
- dispatch 只消费已验证的 typed reason；替代常量 `durable_cancel_requested` 已删除。
- 真实双 opener 测试同时断言 cancellation token 与 worker hook 收到
  `cross_opener_cancel`，不存在入口时序导致的双真源。

### CTRL-S3-003 — fixed

- state query 在任何 SQL statement 前对完整 input tuple 做 owner、四元 identity 与全局
  duplicate 校验。
- 查询在同一 caller transaction 内按 SQLite legacy 999 bind budget 推导的私有 199 条
  batch 透明执行，没有 public capacity cap。
- absolute `request_order` 与连续 batch append 保证过滤 stale/wrong-owner 后仍严格保持
  全局输入顺序；205 identity 逆序跨 batch 反例通过。

## New finding adjudication

- AgentMiMo：`pass`，0 actionable findings，blocking questions=None。
- AgentDS：`pass`，0 actionable findings，blocking questions=None。
- Controller：未发现被两路遗漏的新 correctness、stability、semantic ownership、task
  lifecycle、terminal producer 或 SQLite batching gap。

两路记录的 native mutex 跨平台、poll cadence、provider physical stop 与定制 SQLite
低于 999 bind limit 均属于既有支持边界或后续 runtime-policy owner，不阻塞本 Slice。

## Controller verification

- 根因反例：独立 owner progress、failed-open join、cross-opener canonical reason、205
  identity batching，共 `4 passed`。
- fix 相关 production/tests pyright：`0 errors, 0 warnings, 0 informations`。
- AgentCodex focused matrix：`438 passed`。
- terminal producer manifest：`1 passed`。
- canonical full suite：`5593 passed, 11 skipped, 6 deselected`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- coverage test surface：`3542 passed, 9 skipped, 6 deselected`；相对 WU baseline 的
  21 个 modified production Python 文件逐文件均 `>=80%`。
- AgentMiMo 独立 full Host：`2150 passed, 2 skipped, 6 deselected`。
- AgentDS 独立 canonical full suite：`5593 passed, 11 skipped, 6 deselected`；关键
  production 文件 coverage 均 `>=80%`。
- `git diff --check` 与 stale/invariant grep：通过。

裸 `pytest -q` 会额外收集既存 `workspace/tmp/r06-base-9c07b88d/tests` 并与正式
`tests.conftest` 发生 `ImportPathMismatchError`；本轮未修改或删除用户临时目录，正式
canonical suite 已完整通过，因此该环境 hygiene 不属于产品 failure。

## Residual risk disposition

1. physical cancel 仍受 poll interval、event loop 调度与 SQLite 可用性约束；durable failure
   由现有 health owner fail closed。分类：`covered by existing runtime health owner`。
2. 本地 token/hook 不承诺远端 provider physical exactly-once stop；迟到结果由既有
   identity/terminal fence 拒绝。分类：`assigned to existing provider boundary`。
3. 定制 SQLite runtime 若主动把 variable limit 降到 999 以下，需要独立 runtime-policy
   work unit。分类：`assigned to later work unit if support scope expands`。
4. Windows native mutex backend 尚需目标平台 CI。分类：`platform coverage residual`，不改变
   strict-native/fail-closed public contract。

所有 residual risk 均已分类，没有 blocking open question。

## Final decision

`pass`。允许创建 accepted Slice 3 保护提交；提交完成后进入 WU-CTX-04 aggregate
deepreview gate。不得在本裁决中合并、ready PR、请求 reviewer 或关闭 Issue。
