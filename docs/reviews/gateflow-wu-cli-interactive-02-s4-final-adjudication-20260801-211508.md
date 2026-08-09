# wu-cli-interactive-02 S4 final adjudication（F11/F12）

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：S4 final adjudication
- Branch：`codex/interactive-oracle`
- Base HEAD：`eadee40932cff2113e944620dcbac1bf187ab799`
- 时间：2026-08-01 21:15:08 CST
- Implementation：`docs/reviews/gateflow-wu-cli-interactive-02-s4-implementation-20260801-205047.md`
- Initial reviews：
  - `docs/reviews/code-review-wu-cli-interactive-02-s4-mimo-20260801-210345.md`
  - `docs/reviews/code-review-wu-cli-interactive-02-s4-ds-20260801.md`
- Initial adjudication：`docs/reviews/gateflow-wu-cli-interactive-02-s4-code-review-adjudication-20260801-210745.md`
- Re-reviews：
  - `docs/reviews/code-rereview-wu-cli-interactive-02-s4-mimo-20260801.md`
  - `docs/reviews/code-rereview-wu-cli-interactive-02-s4-ds-20260801.md`
- Final finding status：`0 accepted / 3 rejected / 0 deferred / 0 unclassified`
- Next gate：accepted S4 commit → S5 implementation

## 1. Re-review verdict

MiMo 与 DS 在清空旧上下文后独立执行 re-review，均重新读取当前代码、plan §8、
implementation artifact 与总控裁决。两路结论均为 `pass`，没有新增 finding，且
分别从 event-loop 时序、owner-level crash test 和异常传播链确认：

1. `_promotion_pending_session_ids` 只代表尚未 dequeue 的真实 promotion queue
   level signal；direct flight 不消费该 queue entry，因而不存在 stale signal 丢失。
2. `test_proactive_manifest_crash_resumes_deterministic_next_stage` 对五个 crash
   attempt 参数化证明 fresh scheduler 复用同 operation、snapshot、max budget、
   next attempt 与 deterministic stage；exhausted case 另有 fresh scheduler 测试。
3. `_promotion_drain_loop` 的 unexpected exception 分支确实先
   `_requeue_promotion_after_backoff`，再 warning，最后 raise 给 shared health
   supervisor；初审“不 requeue”的说法是代码读取错误。

两路 re-review 都重新确认 F11 shared terminal owner、全部 writer inventory、late
loser/`INVALID_MULTIPLE` 零副作用和 F12 sole-flight/cancel/close/exit boundary
contract，没有把初审或另一 reviewer 的输出直接当作通过依据。

## 2. Final implementation decision

### F11

- 新增专用 `dayu.host.compaction_terminal`，只拥有 compaction request/trigger/
  terminal transaction-local commit permit，不演化为通用 event framework。
- proactive 四个 writer 与 reactive 一个 writer 均在同一 outcome write transaction
  的 artifact/descriptor/rejected/terminal/fallback/start 之前调用 shared owner。
- first terminal wins；单 terminal late loser bounded no-op；多个 terminal 以稳定
  `HostDurableError` fail closed，不追加第三 terminal。
- proactive projection 机械消费 shared disposition，不保留第二套 terminal count
  owner。

### F12

- `_PreStartGovernanceFlight` 只有 `Task[bool]` 与 level bit；每个 scheduler、每个
  Session 至多一个 live pre-start flight，不同 Session 可并行。
- wake queue、direct promotion、periodic reconciliation 与 transient requeue 都
  汇入同一 signal owner；pending set 只对 promotion queue 去重。
- 每个 pass 持有 fresh `SessionWorkLease`；in-flight signal coalesce，结束后从
  durable truth fresh reread；无 await delete 边界不丢 signal。
- caller cancel 不取消 shared flight；scheduler close 取消并 await flight；fresh
  owner 才从 durable incomplete operation 恢复。

## 3. Validation decision

实现侧证据：

- 批准的八个 owner/integration 测试文件：`412 passed`。
- pre-review correction 后关键 F11/F12 选测：`27 passed`。
- 全仓 `pyright`：`0 errors, 0 warnings, 0 informations`。
- pytest-cov clean batch：`410 passed, 2 deselected`；两个 deselected 用例只在
  插桩下触发既有 10ms local-lane timeout，均包含在普通模式 412-test pass 中。
- 受影响 production 单文件覆盖率：
  - `compaction_terminal.py` 85%
  - `dispatch.py` 87%
  - `engine_ingest.py` 89%
  - `proactive_compaction.py` 85%
- `git diff --check`、类型/docstring、secret/credential/Authorization/provider
  payload 扫描通过。

总控独立复跑八文件集合得到 `411 passed, 1 failed`；唯一失败是 S3 已分类的 HEAD
相邻 active-cancel watchdog 10ms exact-count race，同一测试立即独立复跑
`1 passed`。该波动不触及 F11/F12 owner，不构成 S4 regression 或未分类风险。

## 4. Docs decision

S4 没有修改 design/README。该决定符合 accepted plan：F12 single-flight、signal
coalescing、live in-flight 与 fresh-owner recovery 的设计真源在 S6 统一写入
`docs/host/design.md`，避免中间 slice 机械同步；最终 S6 必须完成该项，当前不是
遗忘或 deferred finding。

## 5. Residual risks

所有 residual risk 已分类：

- bounded terminal pagination：accepted implementation risk；plan 禁止本 slice
  新增 index/schema/migration。
- scheduler-local flight：intended boundary；durable fresh-owner recovery 已测试。
- reconciliation boolean OR：intended observability semantic，不改变 durable truth。
- F12 docs：planned S6 work。
- watchdog exact-count race：previously classified outside S4。

无未分类 residual risk。

## 6. Gate decision

- 双路 initial review：完成。
- Findings 裁决：完成，0 accepted。
- AgentCodex fix：不需要。
- 双路 re-review：完成并通过。
- Tests/type/coverage/security/docs decision：完成。
- Commit scope：当前 S4 production、tests 与全部 S4 durable artifacts。

结论：`S4 final adjudication pass — ready for accepted S4 commit`。
