# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Review Controller Adjudication

## 1. Gate 与输入

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- immutable plan target：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- plan base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-plan-controller-validation.md`。
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-r05-plan-review-mimo.md`，`PASS-WITH-RISKS`。
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-r05-plan-review-ds.md`，`PASS`。

本裁决不进入 implementation。下一 gate 是 AgentCodex 修改 plan 并输出 plan-fix artifact；随后两路 reviewer 必须对完整修订计划重新 review。

## 2. 裁决摘要

| Finding | 来源 | 裁决 | 当前动作 |
|---|---|---|---|
| R05-PF-01 cancelled abandon timeout 长期重试 residual 未显式登记 | MiMo 001 | `ACCEPTED_NARROWED` | 只补 residual owner/destination；不新增 max retry、deadline 或 policy 字段 |
| R05-PF-02 smoke timing 约束不够可执行 | MiMo 002、DS RR-3 | `ACCEPTED_NARROWED` | 计划明确 event/condition-driven 等待、monotonic deadline、相对 margin 与 named constants；不固定拍脑袋产品数值 |
| R05-PF-03 Host design truth 的 `close marker` 措辞与已裁决 retry 语义不一致 | DS RR-1 | `ACCEPTED` | 将 `docs/host/design.md` 纳入 R05-S1 文档 allowlist，按 controller final decision 精确改写 |
| R05-PF-04 timeout-only durable abandon terminal primitive 将成为无 owner 消费者的错误死语义 | DS RR-2 | `ACCEPTED` | 将 `dayu/host/durable/state.py` 纳入 R05-S1 allowlist并删除该唯一 invalid primitive；补 coverage/source scan |
| DS RR-4 backoff attempt 连续性 | DS RR-4 | `CLOSED_NO_ACTION` | 现有 durable attempt 连续递增正确 |
| DS RR-5 当前 smoke 尚未覆盖目标场景 | DS RR-5 | `CLOSED_BY_PLAN_SCOPE` | 正是 R05-S2 的 implementation/acceptance 目标，不是独立 finding |

accepted plan findings：`4`。blocking question：`0`。不需要新产品裁决。

## 3. R05-PF-01 — accepted narrowed

MiMo 对长期 retry 的事实判断成立，但建议中的 “max abandon retries” 不被接受。

直接调用顺序是：

```text
claimed CANCELLED wait
  -> poll_once() 先进入 _abandon_cancelled_wait(...)
  -> 不进入 _handle_time_boundary(...)
  -> observation timeout
  -> R05 后 release claim + policy backoff
  -> poll_abandoned_at 仍为 NULL
  -> backoff 到期后可再次 claim
```

`dayu/host/wait_adapter.py` 当前在 `record.status is CANCELLED` 时先 `continue`，因此 DS Challenge 3.3 所称 “deadline 会在下一轮由 `_handle_time_boundary` 收口 CANCELLED wait” 不成立；该 helper 只在非-CANCELLED poll path 被调用。若 provider 永远不返回 explicit lifecycle terminal outcome，cancelled wait 会以 capped policy backoff 持续重试。

这不是 R05 可以用局部补丁消除的 defect。controller final decision 明确禁止把 generic observation timeout 当作 terminal evidence；新增 max retry、abandon deadline 或 timeout terminal marker会重新发明尚未裁决的 Host policy。本轮只要求 plan §15/closeout 明确 residual：

- 事实：cancelled abandon observation 可能长期按 capped backoff 重试并占用有限 observation capacity；
- 当前安全边界：claim CAS、outstanding cap、finite single-call timeout、late-publication fencing、backoff cap 保留；
- future owner：显式 Host cancel/abandon durable evidence policy；如需物理终止 Fins Docling，仍由 Issue 175；两者不得混为同一语义。

## 4. R05-PF-02 — accepted narrowed

计划已有 timing 不等式和 “足够 margin”，但对 code generation 仍不够可验证。修订必须规定：

- handshake acceptance、operation start/finish、first observation entered、late result release、runner dropped count、second observation entered 均使用 event/condition 或状态 polling；
- 时间判断使用 monotonic clock 与具名 overall deadline；不得用单次固定 sleep 推断状态；
- 每个严格不等式都由具名 constants 与明确相对 margin 构成，margin 必须显著大于 poll/condition sampling quantum；
- test-effective policy 仍由 packaged snapshot 通过 `dataclasses.replace` 派生，packaged 12-field snapshot 与测试时序分开断言；
- smoke 必须保持适合本地/CI 的有界耗时，失败时输出已观察到的阶段与 durable state，避免只报 timeout。

不要求在 plan 中硬编码 reviewer 举例的 `2s`；实现者必须给出可复核的 named values 和不等式证据。

## 5. R05-PF-03 — accepted

`docs/host/design.md` 当前文本称 cancelled-wait abandon timeout 写 `wait_abandon_timeout` “diagnostic/close marker”。`close marker` 可以被解释为当前 `poll_abandoned_at` terminal marker，与 controller final decision和 umbrella R05 manifest 要求的 release/backoff 直接冲突。

该冲突已有权威裁决，无需重新询问产品：controller discussion 明确 observation timeout 只记录 transient diagnostic、释放 claim、进入 backoff；umbrella manifest进一步要求 poll 与 cancelled-wait abandon timeout 采用同一 non-terminal behavior，并删除 timeout-only abandon-terminal operation。

因此 plan 必须：

- 将 `docs/host/design.md` 纳入 R05-S1 write allowlist；
- 把该句精确改为 timeout 写 poll-local transient `wait_abandon_timeout` diagnostic、释放 claim、按 Host policy backoff、保持 `CANCELLED`、不写 terminal `poll_abandoned_at`；
- 保留 explicit applied/unsupported/noop lifecycle outcome 写 terminal abandon marker 的既有语义；
- 不扩写新的 policy/schema。

这是设计真源纠错，不是新设计。

## 6. R05-PF-04 — accepted

初始 plan 与 Controller validation把 `mark_wait_record_poll_abandon_timeout(...)` 视作可保留的 read-only dead primitive。复核 semantic ownership 与 umbrella manifest 后，该判断被本裁决 supersede。

理由：

1. 该 function 的唯一语义是把 generic abandon observation timeout 投影成 `poll_abandoned_at` terminal marker；该语义已被最终裁决否定。
2. 当前唯一 production consumer 是 `wait_adapter.py` 内 `_MarkWaitRecordAbandonTimeoutOperation`。移除 consumer 后，store primitive 不再有合法 owner-level consumer或 public contract。
3. 保留它会在 durable owner boundary 留下可再次误用的 invalid semantic operation，违反唯一 owner/source-of-truth 与禁止兼容/死 shim 的项目约束。
4. umbrella R05 §12.1 明确允许相关 wait state/store operations，§12.2 要求删除只为 timeout 生成 abandon-terminal 的 operation；因此这不是越界扩域。

plan-fix 必须：

- 将 `dayu/host/durable/state.py` 加入 R05-S1 production allowlist；
- 删除 `mark_wait_record_poll_abandon_timeout(...)` 及仅服务该 invalid operation 的代码；不得保留 deprecated wrapper/docstring/兼容 re-export；
- 更新 source scan，要求该 symbol 在 production 和 tests 中零定义、零调用；
- 重新计算 actual changed production file coverage，并要求 `durable/state.py` 与 `wait_adapter.py` 各自 `>=80%`；若 existing focused matrix不能达到，计划必须补充 owner tests/扩大只读验证集合，而不是降低门禁或 ignore；
- 核对不存在 export、migration、schema 或其它消费者；当前直接 rg 证据只见该 store definition 与 `wait_adapter.py` 单一 import/wrapper/call。

该删除不改变 fresh schema，也不实施 migration。

## 7. 其余 review 结论

- root cause 位于 `WaitPoller` decision owner：接受两路一致结论。
- `WaitObservationRunner` token/generation fence 正确且唯一：接受。
- provider authoritative `WaitPollLost` 与 explicit lifecycle terminal outcome必须保留：接受。
- `BatchToolExecutionContext.timeout_seconds` 是 handshake 协作投影；Engine accepted awaiting 后不二次计时：接受 `agent.py` no-diff 结论。
- 两 slice 原子边界保留：接受。PF-03/PF-04 都属于 S1 同一个 semantic transaction，不增加 slice。
- R04 typed modes/12-field policy、Issue 175、callback transport、unified authorization、R06+ scope 边界保持不变。

## 8. 下一 gate 要求

AgentCodex 必须在同一 plan task 内：

1. 修订唯一 plan artifact，关闭 R05-PF-01 至 R05-PF-04；
2. 写 `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`，逐项给出 before/after、直接证据、allowlist/test/coverage/scans 变化；
3. 只允许修改上述两个文件；不得修改产品、测试、README、design、control 或 reviewer artifacts；
4. 运行 `git diff --check` 并报告 exact diff paths；
5. 不 commit、不进入 implementation。

完成后，AgentMiMo / AgentDS 必须对完整修订 plan 并发 re-review；不得只检查四处局部 diff。
