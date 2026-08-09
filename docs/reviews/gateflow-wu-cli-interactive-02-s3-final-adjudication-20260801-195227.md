# WU CLI Interactive 02 / S3 Final Adjudication

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice：S3 / F10
- Base HEAD：`057b5b9b`
- Implementation artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s3-implementation-20260801-192426.md`
- Initial reviews：
  - AgentMiMo：`docs/reviews/code-review-20260801-193115.md`
  - AgentDS：`docs/reviews/code-review-20260801-192742.md`
- Initial adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-s3-code-review-adjudication-20260801-194029.md`
- Clean re-reviews：
  - AgentMiMo：`docs/reviews/code-review-20260801-195048.md`
  - AgentDS：`docs/reviews/code-review-20260801-194247.md`
- Final gate decision：`PASS`
- Next gate：accepted S3 commit，随后 S4 implementation

## Controller final decision

S3 在不改变 accepted cancel watchdog owner、不增加后台 polling supervisor、不重发 CLI 文本、
不修补 SQLite 的边界内关闭 F10。Controller 接受以下 owner-level implementation：

1. `dayu.host.recovery_process` 独占 stale classification 与 recent-heartbeat deadline；
   exact threshold 进入 stale classification，只有 `owner_heartbeat_recent` 返回同源
   `retry_not_before`。
2. `dayu.host.recovery` 只把各 action 的 typed deadline 聚合为 bounded pages 的 earliest
   `next_reconcile_at`；scanner 不 sleep、不创建 task，positive orphan proof、CAS、recovery
   dispatch limit 与 durable event mutation owner 不变。
3. `_PublicHostHandle` 在 initial RW target scan 与 allocation activation 成功后登记至多一个
   Session-local delayed task；该 task 一次换算 deadline、一次等待、一次以 fresh now 提交相同
   target scan，不形成 polling。
4. delayed task 使用 registry new-work lease 并绑定 actor future；managed attachment close 与
   Host close 都在释放 attachment/停止 actor 前取消并 join；异常只公开安全 type，并通过
   execution health fail closed。
5. durable recovery 仍严格由 positive orphan proof + CAS 产生
   `ATTEMPT_LOST -> RUN_RECOVERING -> RUN_STARTED(start_reason=recovery)`，创建新 Attempt 与
   execution，最终进入明确 terminal。

两路 clean re-review 均未发现 S3 引入的 correctness、stability、maintainability 或 security
finding。首轮 reviewer 的临时 stash 过程违规已通过 `/clear`、重新 discovery、双路全程只读
re-review 关闭；Controller 再次确认 production/test diff、index 与 stash 列表没有净损坏。

## Finding closure

| Finding | Final status | Closure |
|---|---|---|
| S3-MIMO-000：初审无实质代码问题 | `closed-pass` | clean MiMo re-review 从 HEAD 重新走读全部 S3 diff，结论仍为无 S3 代码 finding。 |
| S3-DS-001：把一次 watchdog exact-count 失败归因为 S3 monkeypatch 污染 | `rejected-causal-claim` | 没有 task/fixture 越过 teardown 的直接证据；clean runs 证明现象可复现但 root cause 是 HEAD 已有 direct cancel 与 10ms exact-owner reconciliation 两条 best-effort 传播路径竞争，token 本身幂等。 |
| S3-DS-002：未来多 event-loop 下 `_close_task` 可能竞态 | `rejected-non-goal` | 当前 attachment 只属于一个 opener loop，检查与 `create_task` 间无 await；不为未设计架构加锁。 |
| S3-PROC-001：两名初审 reviewer 临时 stash | `fixed-by-clean-rereview` | net-state 核验无损；两路从 `/clear` 后重新独立 deepreview，仅写各自新 artifact。 |
| S3-VAL-001：HEAD-existing watchdog exact-count test race | `classified-pre-existing-residual` | 六文件 suite 多次运行出现 3 次通过、2 次失败；S3 diff 未改 cancel/watchdog owner，plan §7.6 明确禁止改该 owner。本 slice 不放宽测试 oracle、不修改生产取消语义；保留为已分类的相邻基线风险，不阻断 F10 owner implementation。 |

## Validation

- Controller affected six-file suite：`116 passed in 35.10s`。
- AgentCodex implementation six-file suite：`116 passed in 35.37s`。
- Clean AgentDS six-file suite：`116 passed in 35.18s`；watchdog 单测独立通过。
- Clean AgentMiMo stress：五文件 suite `2 x 101 passed`；六文件 suite
  `3 x 116 passed`、`2 x 1 failed`，失败均为上述 HEAD-existing watchdog physical-delivery
  exact-count race，不是 F10 assertion。
- 真实 POSIX SIGKILL smoke 多路通过：owner `SIGKILL` 后 immediate fresh RW attach，初次 scan
  不提前写 lost；同一 invocation 越过约 30 秒 stale threshold 后自动恢复，创建一个新
  Attempt/execution并成功 terminal，无第二次重启。
- Modified production branch coverage（implementation run）：
  `open_host.py 80%`、`recovery.py 84%`、`recovery_process.py 91%`，aggregate `82%`。
- Controller final full-repository pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过；普通 diff stat 与 `git diff -w --stat` 都是 8 files、
  `+1349/-7`，无 formatting-only churn。
- added-line secret scan：无 credential、Authorization、provider payload 或私钥泄漏；日志失败
  路径只记录 exception type 与稳定 reason。
- Ruff 的两个 F401 与 formatter nonzero 均可在 HEAD 复现，S3 未新增或扩大；未越界清理。

## Documentation decision

S3 只改变 Host 内部 attachment recovery/resource lifecycle，不改变 public DTO 或用户 CLI。
批准 plan 把 `docs/host/design.md`、Host README 与 tests README 的职责内同步集中到 S6；本 slice
未机械修改文档。F10 delayed recovery 设计真源已有前置内容，S6 将按最终实现核对准确性。

## Residual risks

- `S3-VAL-001` 已分类为 HEAD-existing 相邻 test race；它不允许本 work unit 越界修改 cancel
  owner或测试 oracle。后续若单独处理，必须以 active cancel 的两个合法 delivery source 和
  idempotent token contract 为 owner 证据，不能根据随机顺序猜测 monkeypatch 污染。
- delayed reclassification 严格 one-shot；若第二次 scan 仍观察到 recent heartbeat，不自行形成
  新调度链。这是批准的 bounded invariant，后续依赖既有 recovery triggers。
- Windows 未执行 SIGKILL smoke；F10 当前正式证据为 POSIX，完整 G02 矩阵仍属于后续 CLI
  calibration，而非本 slice。

## Next gate

仅 stage 本 slice 的 3 个 production 文件、5 个 test 文件、implementation/review/adjudication
artifacts，执行 cached diff 与 secret/scope check 后创建 accepted S3 commit；不 push。随后按
Gateflow 自动进入 S4/F11-F12 implementation。
