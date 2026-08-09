# WU CLI Interactive 02 / S3 Implementation 记录

## 1. Gate metadata

- Work unit：`wu-cli-interactive-02`
- Slice：approved S3 / F10
- Gate：implementation
- Base HEAD：`057b5b9b3cbb2a390ee2ab1bcd5a06f99124efb1`
- Branch：`codex/interactive-oracle`
- Finding status：`implementation未review`
- Next gate：`S3 code review`
- 本 gate 未执行 review、commit 或 push。

## 2. 动机与直接证据

F10 是真实的 Host recovery lifecycle 缺口。owner 进程退出后，fresh READ_WRITE
attachment 的 initial target scan 可能发生在 durable heartbeat stale threshold 之前；此时
classifier 正确返回 `owner_heartbeat_recent`，所以不得写 `ATTEMPT_LOST` 或进入 recovery。
原实现只在 attach 时扫描一次，fresh invocation 持续存活也没有 owner 在 threshold 后重新
提交同 target scan，用户只能再次重启才会触发恢复。

语义 owner 的直接代码证据如下：

- `dayu/host/recovery_process.py::classify_orphan_candidate` 已独占 durable owner
  heartbeat、stale policy 与 process evidence 的 orphan classification，因此 stale 边界和
  recent-heartbeat deadline 必须由该 classifier 同源产生。
- `dayu/host/recovery.py::SessionAttachmentRecoveryScanner` 已独占单 Session target、固定
  policy `now`、固定 watermark、bounded page 与 CAS recovery，因此它只应聚合 typed
  schedule 建议，不拥有 timer 或 polling。
- `dayu/host/open_host.py::_PublicHostHandle.attach_session` 已独占 fresh attachment
  recovery operation、activation 与 opener-owned lifecycle，因此 delayed task 必须由 public
  handle 在 initial scan 成功且 RW allocation 激活后登记。
- `dayu/host/session_attachment.py::HostSessionAttachmentRegistry` 已提供
  `try_acquire_new_work_lease`、new-work drain、Host close mutex release ordering；现有 contract
  足以约束 delayed actor future，无需修改 registry、public attachment DTO 或增加兼容 seam。
- durable mutation 仍只由 recovery scanner 的 positive orphan proof、既有 CAS 与
  `recovery_dispatch_limit` 驱动；CLI、SQLite schema、scheduler dispatch owner 均不需要修改。

上述 owner 划分与 `docs/host/design.md` 的 attachment recovery、fresh owner、orphan proof、
lease/health/close 约束一致，也满足 plan §7 的 allowed files、exact changes 与 invariants。

## 3. Exact changes 与 dataflow

### 3.1 Classifier 与 typed schedule contract

- stale 边界改为只有 `elapsed < stale_after` 才 recent；`elapsed >= stale_after` 进入 stale
  process-proof classification。
- `OwnerStillLive.retry_not_before` 只在可解析的 `owner_heartbeat_recent` 分支取
  `heartbeat_at + stale_after`；process identity matched 明确为 `None`。
- `SessionAttachmentRecoveryAction.retry_not_before` 投影 classifier 的 typed deadline。
- `SessionAttachmentRecoveryScanResult.next_reconcile_at` 跨 committed bounded pages 聚合
  earliest aware deadline；无 recent-heartbeat 建议时为 `None`。scanner 不启动 task、不读取
  第二套时钟、不循环扫描。

### 3.2 Initial scan 到 delayed scan

1. fresh RW attach 仍以一次 `_utc_now()` 生成 initial fixed `now`，同一个 operation 内的
   watchdog 与全部 scanner pages 复用该时间。
2. initial actor future 正常收口、recovery/health leases 释放且 allocation 成功 activate 后，
   public handle 才消费 `next_reconcile_at`。
3. deadline 非空时，public handle 以 Session id 为 key 登记至多一个 delayed task；deadline
   为空时返回原 attachment，不引入额外 managed lifecycle。
4. delayed task 把 UTC deadline 一次换算为 delay 并只执行一次 `asyncio.sleep`，不 polling。
5. sleep 完成后先从同一个 attachment registry 获取 fresh new-work lifecycle lease，再以新的
   `_SessionAttachmentRecoveryActorOperation`、新的 `_utc_now()` 和同一个 Session target
   提交 durable actor；lease 绑定 actor future 的真实收口。
6. delayed result 即使再次携带 future deadline 也不会继续调度，保持 bounded one-shot。

### 3.3 Close、health 与 durable invariants

- managed RW attachment close 在 actor 尚未提交时取消并 join sleeping task，随后才关闭底层
  attachment；若 actor 已提交，task cancellation 会 shield 等待 actor future 收口，new-work
  lease 完成后才允许 mutex release。
- Host close 先关闭 attachment new-work gate，再取消/join 全部 delayed tasks，然后进入 health
  closing 和 actor stop；既有 registry ordering 继续保证 actor/new-work drain 前不释放 mutex。
- delayed task 正常完成不改变 execution health；异常日志只包含安全的 exception type，并以
  固定 component/reason 向 `HostExecutionHealthGate` 报 fatal，不记录异常 message。
- durable recovery path 未改变：仍为 exact
  `ATTEMPT_LOST -> RUN_RECOVERING -> RUN_STARTED(start_reason=recovery)`，创建新 Attempt 与
  execution；没有 CLI 重发、SQLite schema 修改、takeover、kill-as-cancel 或 compatibility 分支。

## 4. 修改范围

Production：

- `dayu/host/recovery_process.py`
- `dayu/host/recovery.py`
- `dayu/host/open_host.py`

Tests：

- `tests/host/test_recovery_orphan_classifier.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_recovery_multiprocess.py`

`dayu/host/session_attachment.py` 与 `tests/host/test_session_attachment_registry.py` 未修改；后者作为
现有 registry lifecycle regression suite 被执行。除本 artifact 外没有修改允许列表外文件。

## 5. Test coverage

- classifier：threshold 前、等于 threshold、之后；recent heartbeat deadline 来源；process
  identity matched 无 schedule。
- scanner：跨 bounded pages earliest deadline、固定 policy watermark、inconclusive 无
  schedule、positive-proof CAS loser 零 mutation/零 schedule。
- fake clock/barrier：initial recent 时 deadline 前零 mutation；delayed operation 使用 fresh
  `now` 后获得 positive proof；断言 exact event ordering、recovery reason、new Attempt 与 new
  execution，且正常完成 health 仍 READY。
- attachment close：sleep 前取消为零事实；actor 已提交时 close 等待 future，竞争 opener 在
  barrier 内保持 RO，证明 lease/mutex 未提前释放。
- Host close：sleeping task 在 actor stop 前取消/join；actor-stop barrier 内另一个 opener 仍为
  RO；最终无 task 泄漏。
- failure：delayed scan 异常只报告 `RuntimeError` type 与固定 fatal reason，敏感异常文本不进入
  log。
- counterexamples：live owner、probe inconclusive 不恢复；现有 RO attachment 路径不 scan、不
  schedule。
- real multiprocess：POSIX owner 建立 active RUNNING 后由父进程发送 SIGKILL；同一 fresh
  invocation 立即取得 RW attachment，在约 30 秒 stale threshold 后自动恢复到 terminal，不需
  第二次重启；old/new attempt 与 execution 均不同，worker 执行与 canonical event 次数有界。

## 6. 验证记录

- 允许列表内六个测试文件完整执行：`116 passed in 35.37s`。
- 真实 SIGKILL delayed recovery 单独 smoke：`1 passed in 30.73s`。
- modified production branch coverage：
  - `dayu/host/open_host.py`：80%
  - `dayu/host/recovery.py`：84%
  - `dayu/host/recovery_process.py`：91%
  - aggregate：82%
- 全仓 `pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：零错误。
- token/credential/private-key 形态的 added-lines secret scan：零命中。
- scope scan：只有三份允许 production 文件、五份实际修改的允许 test 文件与本 artifact。
- formatting-only churn 审计：普通 `git diff --stat` 与 `git diff -w --stat` 完全一致；先前全文件
  formatter 引入的 105 个无关基线 hunks 已逐 hunk 反向恢复，唯一重叠 hunk 只保留新增 owner
  contract 的必要局部格式；未使用 reset/checkout。
- `ruff check` 原始结果仍为两个 HEAD 已存在的 F401：
  `recovery.py::AttemptStatus` 与
  `test_recovery_scan.py::create_running_run_with_starting_attempt_in_transaction`。对 HEAD 文件
  通过 stdin 复现同样错误；为保持 S3 最小 diff 未顺手删除。`ruff check --ignore F401` 对全部
  affected files 为 `All checks passed!`，没有其它 lint finding。
- `ruff format --check` 报 8 个 affected files would reformat；HEAD 的同文件 stdin check 同样
  非零。按 Controller 范围提醒没有再次运行 formatter，也没有为追平 formatter 改写基线。

## 7. README decision

本 slice 改变的是 Host 内部 attachment recovery 与 managed-resource lifecycle，不改变 public
DTO、最终用户命令、安装方式或排障入口。plan 将文档同步保留给 S6，且 README 不在本 slice
允许写入边界，因此 `dayu/host/README.md`、`tests/README.md`、根 README 与
`dayu/README.md` 均不修改。

## 8. Blocker 与 residual risks

- Implementation blocker：无。
- Finding status 仍为 `implementation未review`；本记录不是 code review 结论，也不声明 gate
  pass。
- delayed reconcile 按批准设计严格 one-shot；若 second scan 又得到 recent-heartbeat deadline，
  不会形成 polling 或新调度链。这是 bounded invariant，同时意味着后续 heartbeat 再刷新场景仍
  依赖其它既有 recovery trigger。
- multiprocess SIGKILL 场景仅在 POSIX 执行；Windows 由测试条件显式 skip，未扩展 G02 完整矩阵。
- raw Ruff/formatter 的 HEAD 基线非零仍存在；本 slice 没有扩大，也没有越界清理。

下一 gate 只能是 `S3 code review`。
