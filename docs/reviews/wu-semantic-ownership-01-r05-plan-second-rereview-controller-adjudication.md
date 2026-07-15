# WU-SEMANTIC-OWNERSHIP-01 R05 Second Plan Re-Review Controller Adjudication

## 1. Gate 与输入

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- immutable plan target：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- plan base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- AgentMiMo second complete re-review：`docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-mimo.md`。
- AgentDS second complete re-review：`docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-ds.md`。
- second fix：`docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md`。
- second fix Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-controller-validation.md`。

最终裁决：**ACCEPTED_PLAN_RE_REVIEW / CODE_GENERATION_READY**。

- current accepted plan finding：`0`。
- blocker：`0`。
- blocking question：`0`。
- `R05-PF-01` 至 `R05-PF-04`：`CLOSED`。
- `R05-PRR-F01`：`CLOSED`。
- accepted local plan commit：`AUTHORIZED`。

本裁决只授权 exact-scope accepted plan commit；commit 完成前不授权 implementation。

## 2. 两路结论与证据纠正

| 路由 | 最终 verdict | Controller 裁决 |
|---|---|---|
| AgentMiMo | PASS / zero finding | 接受；其初稿 Finding 001 与最终 plan §5.1 第 241 行直接矛盾，reviewer 已在同任务 follow-up 中撤回并把 artifact 修正为零 finding |
| AgentDS | PASS / zero plan defect / one transient validation risk | 接受计划结论；coverage 首次失败只作为根因未定的 implementation validation risk，不接受任何 approximate count 或失败豁免 |

MiMo 修正后的直接证据是：最终 plan 的 `dayu/host/durable/state.py` production changes 段已逐字要求删除 base `40:5` 的 unused `TERMINAL_RUN_STATUS_VALUES` import。不存在需要再次修改 plan 的缺口。

DS 修正后的六元组登记：

```text
command:
  python -m pytest -q tests/host
  --ignore=tests/host/test_toolruntime_executor.py
  --cov=dayu.host.durable.state --cov=dayu.host.wait_adapter --cov-branch

node:
  tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task

error / stable frame:
  HostApiError: Host execution is unavailable
  dayu/host/_execution_health.py:258 in raise_if_scheduler_unavailable

baseline SHA:
  5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

直接证据只证明：

- 首次 full coverage session 为 `1 failed, 1915 passed, 1 skipped, 5 deselected`；
- failure path 位于 dispatch scheduler / health gate，和 R05 planned changed owners `wait_adapter.py` / `durable/state.py` 的 source/propagation scan 零交集；
- Controller 与 DS 的隔离复跑均通过；
- earlier AgentCodex 与 AgentMiMo 相同 full coverage command 均曾全绿并达到 owner coverage threshold。

这些证据不能证明 test-order pollution 或 test isolation defect 是 root cause；根因保持未定。它也不构成 plan semantic defect，因为最终 plan 已要求完整 coverage command 全绿、禁止把测试失败作为 inherited exemption。R05 implementation 若再次出现该 node，必须先独立定位 root cause；不得据本 review 豁免，也不得把精确 gate 改成 approximate pass count。

## 3. Finding 最终 ledger

| Finding / opinion | 最终状态 | 理由 |
|---|---|---|
| `R05-PF-01` cancelled abandon 长期 capped retry residual | CLOSED | §2.1 / §4 / §15 与直接 call order 同源；不发明 terminal evidence |
| `R05-PF-02` smoke timing 可执行性 | CLOSED | event/condition/state-poll、monotonic overall deadline、named margins/CI cap/phase ledger 完整 |
| `R05-PF-03` Host design `close marker` 真源纠错 | CLOSED | S1 精确 writeback，保留 explicit lifecycle terminal，不扩 policy/schema |
| `R05-PF-04` invalid timeout-only durable primitive | CLOSED | storage owner deletion、owner test、zero-symbol/schema/coverage gates 完整 |
| `R05-PRR-F01` touched-file Ruff registry | CLOSED | 两条 F401 六元组完整，S1 同时清理，full residual 预期 `167 - 2 = 165` 且逐六元组核对 |
| MiMo second review draft Finding 001 | WITHDRAWN_REVIEWER_ERROR | plan §5.1 已包含建议文本；最终 artifact 已修正为 zero finding |
| DS coverage transient risk | RESIDUAL_VALIDATION_RISK | root cause 未定；owner/destination 是 R05 implementation completion validation，required full command 必须全绿 |

没有 accepted finding 留待 plan fix，不需要第三次 plan-fix / re-review。

## 4. Plan acceptance

最终计划满足 code-generation-ready：

- root cause 落在 `WaitPoller` decision owner，runner fence / typed terminal owner保持单一真源；
- poll timeout 与 cancelled abandon timeout 都改为 transient diagnostic + release/backoff，不伪造 LOST 或 terminal abandon；
- provider authoritative typed lost 与 explicit applied/unsupported/noop terminal lifecycle 保留；
- invalid durable primitive 在 storage owner boundary 删除，不留 dead/deprecated/compat surface；
- CANCELLED 长期 capped retry residual 有明确 future Host durable evidence policy owner，不误称 deadline 会收口；
- S1 是唯一 production semantic transaction，S2 是 Engine no-diff regression + public smoke evidence；不增加第三 slice；
- Engine accepted awaiting 超出 handshake timeout由 no-diff regression固化；
- test-first、owner test、coverage、Ruff、pyright、source/propagation、README 与真实 smoke gates 可执行；
- R04 provider modes / 12-field policy、安全 mechanisms、Issue 175、callback、R06+、unified authorization 等边界完整。

## 5. 安全与延期边界

R05 不删除或放宽 token/generation fencing、claim CAS、outstanding capacity、finite adapter timeout、backoff cap、close-drain、durable ownership 或既有 Host governance。R05 不实现统一 tool authorization framework，不设计 permission schema / DSL / role / capability / sandbox。Issue 175 process isolation、callback transport、未来 Host cancel/abandon durable evidence policy与 R06+ 继续由既有 owner / 后续裁决承接。

## 6. 下一动作

Controller 只提交下列 exact scope：最终 R05 plan、完整 plan review/fix/re-review/controller artifact 链与 control 状态。accepted commit 后另作 control transition，才授权 AgentCodex 进入 R05-S1 implementation。R05-S2、aggregate deepreview、R06 与 umbrella closeout均仍未授权。
