# wu-cli-interactive-02 S4 code review 裁决（F11/F12）

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：S4 code review adjudication
- Branch：`codex/interactive-oracle`
- Base HEAD：`eadee40932cff2113e944620dcbac1bf187ab799`
- 裁决时间：2026-08-01 21:07:45 CST
- Implementation artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s4-implementation-20260801-205047.md`
- MiMo review：`docs/reviews/code-review-wu-cli-interactive-02-s4-mimo-20260801-210345.md`
- DS review：`docs/reviews/code-review-wu-cli-interactive-02-s4-ds-20260801.md`
- Finding status：`0 accepted / 3 rejected / 0 deferred / 0 unclassified`
- Next gate：S4 dual re-review

## 1. 总控独立证据

总控没有把 reviewer 结论直接作为通过依据，而是重新核对了以下 owner 与
反例：

1. `dayu.host.compaction_terminal` 的 request/event-class/trigger/terminal
   strict read，以及 SQLite 同一 write transaction 内的 fresh linearization point。
2. `dispatch.py` 四个 request-backed proactive writer、`engine_ingest.py` 一个
   reactive writer，以及 `proactive_compaction.py` 只读 projection consumer。
3. `_promotion_pending_session_ids` 与 `_promotion_queue` 的一一 pending-level
   关系、direct signal 与 drain signal 的 event-loop 时序、flight 的无 await
   delete 边界、caller cancel shield 和 scheduler close tracking。
4. 真实 compactor barrier、proactive/reactive 双向 contender、late result、
   `INVALID_MULTIPLE` 与 fresh scheduler crash recovery 测试。
5. 总控独立运行批准的八文件集合得到 `411 passed, 1 failed`；唯一失败是已在
   S3 分类的 HEAD 相邻 active-cancel watchdog 10ms 精确计数竞态，同一测试随即
   独立复跑 `1 passed`。全仓 `pyright` 为
   `0 errors, 0 warnings, 0 informations`。该相邻波动没有被归因于 S4。

## 2. Reviewer 结论

### 2.1 MiMo

MiMo 未提出实质 finding。其逐路径核对确认 shared terminal owner 覆盖、late
loser 零业务副作用、projection 不产生第二 terminal owner、per-Session flight
coalescing/exit/cancel/close 以及测试 barrier 均符合 plan §8。

MiMo 记录的 observability 与 pending-set 理论风险均不改变 durable correctness；
其分类在第 4 节统一裁决。

### 2.2 DS

DS 提出三个候选 finding：

1. 中：direct flight 可能留下 stale `_promotion_pending_session_ids`，后续 wake
   被静默丢弃。
2. 低：缺少 fresh owner crash recovery 测试。
3. 低：promotion drain 对 unexpected flight 异常不 requeue。

三项均经直接代码与测试证据驳回，详见下一节。

## 3. Finding 裁决

### D1 — `_promotion_pending_session_ids` stale entry

- Reviewer severity：中
- 裁决：`rejected — pending level 仍有真实 queue entry，不是 stale`。
- 直接证据：
  - `wake_queue_promotion(S)` 同时把 `S` 加入 pending set 与 promotion queue；
    pending set 在 drain 取出该真实 queue entry 时才 `discard`。
  - 如果 direct `run_queue_promotion(S)` 在 queue entry 尚未被 drain 时先完成，
    它没有消费该 queue entry。后续 wake 看到 pending set 后 return，是与仍存在的
    queue signal 合并；该 queue entry 之后会从 fresh durable truth 再执行一次，
    因此没有静默丢失。
  - 如果 drain 已取出 entry，则它在调用 shared signal owner 前已经 discard，
    不存在 reviewer 描述的 stale set。
- 反例裁决：reviewer 场景中的第三次 wake 最多等待本就已经排队的真实 signal，
  这是 plan §8.3 要求的 level-bit/pending coalescing，不是额外延迟缺陷。
- 不接受建议原因：在 direct `_signal_pre_start_governance` 中无条件 discard 会让
  queue 中仍有 entry、set 却为空，破坏 set/queue invariant，并允许相同 Session
  重复入队。
- Fix：无。

### D2 — 缺少 fresh owner crash recovery 测试

- Reviewer severity：低
- 裁决：`rejected — 现有 owner-level 测试已明确覆盖`。
- 直接证据：`tests/host/test_dispatch_scheduler.py` 的
  `test_proactive_manifest_crash_resumes_deterministic_next_stage` 在 manifest 已提交、
  provider 结果未持久化时模拟 crash，关闭旧 scheduler，创建 fresh scheduler，
  并断言同一 operation id、frozen snapshot/max budget、next global attempt 与最终
  terminal。该测试对多个 crash attempt 参数化执行。
- 补充证据：`test_proactive_exhausted_manifest_fails_same_operation_without_provider`
  也以 fresh scheduler 证明 exhausted operation 不会创建新 operation 或再次调用
  provider。
- Fix：无；新增重复测试会扩大测试体积而不增加 owner contract。

### D3 — unexpected flight 异常不 requeue

- Reviewer severity：低
- 裁决：`rejected — 代码事实读取错误，且 reviewer 自认非 S4 回归`。
- 直接证据：`_promotion_drain_loop` 的 `except Exception as exc` 分支先调用
  `_requeue_promotion_after_backoff(session_id)`，再记录 warning 并 `raise`；异常由
  critical-task supervisor 映射到 shared health fatal。它不是 reviewer 描述的
  “log + continue（不 retry）”。
- `INVALID_MULTIPLE` 仍保持 fail closed：不追加第三 terminal、不 fallback、不 start；
  shared health 进入 unavailable 也不会伪造业务 terminal。
- Fix：无。异常类型框架重构属于明确 scope 外扩张。

## 4. Residual risk 分类

| 风险 | 分类 | 裁决 |
| --- | --- | --- |
| terminal owner 按 64 行分页扫描超长 Run | accepted bounded implementation risk | 现有 EventLog primitive 上的正确实现；plan 明确禁止本 slice 新增 index/schema/migration。不是 correctness blocker。 |
| reconciliation `dispatched` 使用 flight 多 pass OR 归约 | intended observability semantic | 返回值表示本次共享 flight 是否曾产生 stable dispatch，符合 sole-flight owner；不改变 durable truth。 |
| promotion drain unexpected exception 后 queue/pending 状态 | existing critical-health design | 分支先 requeue 再上报 fatal；shared health unavailable 阻止继续接受新工作。非 S4 finding。 |
| scheduler-local flight 进程崩溃后丢失 | intended recovery boundary | fresh owner 从 durable request/manifest 恢复；已有参数化 owner test。 |
| F12 design/README 尚未同步 | planned work | 按 accepted plan 留给 S6，不在 S4 机械更新。 |
| HEAD 相邻 watchdog token exact-count 竞态 | previously classified, out of S4 | S3 已记录；S4 未触及 cancel owner，单测独立复跑通过。 |

无未分类 residual risk。

## 5. Gate decision

- Accepted findings：0。
- 需要 AgentCodex fix：否。
- 生产/测试代码在初审后保持不变；仅新增两份独立 review artifact 与本裁决
  artifact。
- S4 尚不能直接 commit：按用户要求，仍需 MiMo、DS 基于本裁决执行独立
  re-review，确认没有遗漏或裁决错误。

结论：`S4 code review adjudication pass, pending dual re-review`。
