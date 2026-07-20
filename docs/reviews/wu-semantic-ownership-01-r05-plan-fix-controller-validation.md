# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Fix Controller Validation

## 1. Gate 与结论

- target：修订后的 `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- fix artifact：`docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`。
- authoritative findings：`docs/reviews/wu-semantic-ownership-01-r05-plan-review-controller-adjudication.md` 中 `R05-PF-01` 至 `R05-PF-04`。
- verdict：**PASS**。
- accepted findings closed：`4/4`。
- new Controller finding：`0`。
- blocking question：`0`。
- next gate：AgentMiMo / AgentDS 对修订计划全文作完整双路 re-review；implementation 仍未授权。

## 2. Finding 关闭复核

| Finding | 直接复核 | 结论 |
|---|---|---|
| R05-PF-01 | §2.1、分支矩阵与 §15 均明确 `CANCELLED` 先走 abandon path并绕过 `_handle_time_boundary(...)`；长期 capped-backoff retry、有限资源边界、future Host durable evidence policy 与 Issue 175 分离完整 | CLOSED |
| R05-PF-02 | S2 smoke 要求 event/condition/durable-state phases、唯一 monotonic overall deadline、named quantum/margin/CI cap、相对不等式和阶段化失败快照；禁止固定 sleep 推断状态 | CLOSED |
| R05-PF-03 | `docs/host/design.md` 已加入 S1 write allowlist，写回文本精确限定 transient diagnostic + release/backoff + keep CANCELLED + no `poll_abandoned_at`，同时保留 explicit lifecycle terminal outcome | CLOSED |
| R05-PF-04 | `dayu/host/durable/state.py` 与 `tests/host/test_wait_record_state.py` 已进入 S1 allowlist；计划删除 invalid primitive而不保留 dead/deprecated/compat surface，要求 production/tests symbol 零定义零调用、schema no-diff 与两 changed production files逐文件 coverage | CLOSED |

## 3. Semantic owner 与 slice 边界

- S1 仍是一个 Host semantic transaction：adapter 决策修正、invalid storage operation 删除、durable owner preservation test 与 Host design 真源纠错同源提交。
- S2 仍是 Engine no-diff regression + public composition/smoke evidence；没有新增 production transaction。
- `WaitObservationRunner`、`dayu/host/waiting.py` 与 `dayu/engine/agent.py` 继续预期 no diff。
- storage diff 只允许删除 `mark_wait_record_poll_abandon_timeout(...)` 及仅服务该 invalid semantic 的代码；schema、row shape、enum、codec、migration 均禁止变化。
- provider authoritative lost 与 explicit applied/unsupported/noop terminal lifecycle 不受影响。

两 slice 原子边界保持，PF-03/PF-04 没有制造第三 slice、第二 scheduler或新 policy owner。

## 4. Test、coverage 与 scan 可执行性

AgentCodex 的 read-only probe 证明：

- 原四文件集合：`67 passed`，但 `durable/state.py=64%`、`wait_adapter.py=78%`，不足逐文件门禁；修订计划没有隐藏这一事实。
- green coverage set：`tests/host --ignore=tests/host/test_toolruntime_executor.py` 得到 `1916 passed, 1 skipped, 5 deselected`、`durable/state.py=83%`、`wait_adapter.py=85%`。
- 探索性完整 Host coverage 虽达到 `83%/87%`，但触发 15 个无关 process-backed `PicklingError`；fix artifact完整登记 exact nodes、error type、stable frame、fingerprint 与 base SHA，并明确不作为 pass/inherited exemption。

修订计划把功能 regression 与 coverage session 分开：

- timeout owner tests保持 test-first red -> green；
- durable release/claimability 与 explicit terminal marker tests 是 preservation green nodes；
- actual changed production files逐个 `coverage report --fail-under=80`；
- invalid symbol 在 `dayu tests` 零定义零调用，`durable/schema.py` no diff；
- Engine `agent.py` no diff、R04 ownership、安全/延期边界和 full Ruff 六元组规则保持。

这些命令可执行且没有用排除无关 ToolRuntime test文件来豁免 R05 propagation；所有 R05 owner功能矩阵仍单独必须全绿。

## 5. Diff 与 gate hygiene

- plan-fix gate 只修改原 plan并新增 Codex fix artifact；其它 control/controller/reviewer artifacts 是进入该 gate 前已有状态。
- `git diff --check`：通过。
- 两个 untracked gate artifact 的 `git diff --no-index --check`：无 whitespace diagnostic。
- 未修改产品、测试、README、design 或既有 review artifact；未 commit/push。

## 6. Controller 决定

修订计划进入完整双路 plan re-review。reviewers 必须 review 全文并特别复核：

1. storage primitive 删除是否确属 owner-boundary root fix，且 coverage/scans 足够；
2. design writeback 是否只纠正已裁决句子；
3. smoke phase/margin 是否能在 implementation 中形成有界、非 flake 的真实 public oracle；
4. cancelled abandon 长期 retry residual 是否准确，不得再次误称既有 wait deadline 会收口；
5. 两 slice、R04 config、Engine no-diff、Issue 175/callback/unified authorization/R06+ 边界是否保持。

两路 re-review 与 Controller adjudication完成前，不得进入 implementation。
