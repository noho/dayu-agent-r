# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Implementation（AgentCodex）

## 结论

`READY_FOR_CODE_REVIEW`

- Gate：`implementation-slice-3`
- Accepted plan base：`b33bb80b`
- 角色边界：仅完成 implementation 与 accepted finding fix；未更新 control doc，未 commit、push 或创建 PR。

## 动机与 owner 复核

问题动机成立：terminal durable fact 与 queue promotion 若只通过 `session_id` 旁路交接，Session Event Delivery 无法证明 exact terminal sequence 已先对本 opener watcher 可见。正确 owner 是 terminal transition 的同事务结果、producer-local post-commit handoff，以及 opener-local coordinator；不能在 watcher、projection 或 Service 下游回读/猜测 terminal fact。

第二次 STOP 的 dual-opener 失败不属于 production coordinator 缺陷。原断言把 opener A 合法的本地 hook 与 opener C 的跨 opener 隔离混成一个全局计数，因此 owner 是目标测试的 instrumentation。本次只在计划授权的 `_TerminalWatermarkHookCallCounter` 和目标方法内改为按 hub 实例计数并转发真实 production hook。

## S3 contract 实现证据

### 1. Exact local-only terminal contract 与事务真源

- 新增 `dayu/host/terminal_post_commit.py`，只定义 frozen/slots `TerminalPostCommitNotice` 与同步 `TerminalPostCommitPort`；严格校验非空 Session、非 bool 正整数 sequence、严格 bool flag，未从 `dayu.host` public package export。
- `RunTransitionResult.run_event` 为 required field。所有 transition 显式赋值；写 Run event 时返回同一 transaction 得到的 exact row，无 Run event 时显式为 `None`。
- terminal replay/ack 只通过 `RunRow.terminal_event_id/terminal_event_sequence` 在同一 transaction 精确读取并校验 event id、sequence、Session、Run identity；没有 commit 后 latest/max/status 推断。
- admission、waiting、Engine ingest、recovery、dispatch 的 notice helper 都只接受 transaction result，并再次核对 Run stable terminal ref 与 exact EventLog row。

### 2. 全 producer 接线与 flag

- AST manifest 冻结 21 个 terminal transition producer：admission 9、waiting 3、Engine ingest 4、recovery 2、dispatch 3。
- producer-local immutable result 携带单 notice、可选 notice 或按 terminal sequence 排序的 tuple；只有最外层 `run_write` 返回后才调用 port。
- single-run pre-dispatch/waiting/recovering cancel、active closeout、首次 wait failed/lost/expiry、Engine 首次 terminal/worker lost、watchdog、worker startup closeout、startup recovery 首次释放 slot 使用 `wake_queue_promotion=True`。
- queued cancel、terminal ack/replay/duplicate、session-scope tuple、attempt-free failure及其它未新释放 active slot 的确认使用 `False`；resume、recovering、dispatch-ready、active cancel request 不产生 notice。
- 删除 terminal-derived `PromotionResult`、`queue_promotion_session_id`、`EngineIngestResult.promotion_triggered`、`_promote_after_release`、`_with_terminal_promotion_retry` 等重复事实与旁路。
- standalone command composition 使用私有 no-local-delivery final endpoint。runtime recording fake 在回调内通过独立 SQLite 连接读取已提交 exact EventLog row，证明调用发生在 commit 后且 sequence/Session 与 notice 一致。

### 3. Coordinator 状态机与关闭

- 每个 opener 由 `_TerminalPostCommitCoordinator` 唯一拥有 delivery watermark 与 promotion dedupe watermark。
- 每个 notice 先 `max` 推进 delivery watermark并触发 level readiness，再处理 promotion；false notice 只推进 delivery，same-sequence 幂等，newer false 不吞 older true，newer true 覆盖 older true。
- 非 owner thread 通过既有同步 loop bridge marshal；owner-loop callback 无 `await` 临界段。
- close 使用 owner-loop barrier：close 前已排队 notice 正常完成；close 后 notice fail closed，不推进 delivery、不调用 promotion。
- 日志只允许固定低基数：`event=terminal_notice` 与 `outcome=delivery_advanced/promotion_woken/duplicate/closing`；closing reason 固定为 `coordinator_closing`，不含 identity、sequence、capacity 或 payload。
- coordinator 测试直接覆盖 false、duplicate、older/newer、非 owner thread、close 前排队 notice、close 后调用及固定日志集合。

### 4. Promotion barrier 与无旁路

- ordinary direct promotion 静态闭集精确为 5 个语法调用：admission ordinary governance 1、recovery ordinary batch 1、coordinator 1、threadsafe scheduler bridge 2。
- terminal producer qualified scope 中不存在 direct `wake_queue_promotion`；旧 `queue_promotion_session_id`、`_promote_after_release`、`_with_terminal_promotion_retry` 与 runtime setter 扫描为空。
- 三条真实 owner-path A→B barrier 已补齐：
  - pre-dispatch cancel A + queued B；
  - wait failed A + queued B；
  - wait expiry A + queued B。
- 三个测试都在 action 前建立 pending watcher，冻结 worker dispatch但保留真实 durable admission/promotion；断言 A terminal exact sequence 等于 opener-local watermark，B 的 promotion `RUN_STARTED` 在 A terminal 前不可见，且只能由 terminal 后下一次 `anext()` 交付。

### 5. Scheduler 构造与 Host lifecycle

- `HostDispatchScheduler.open` 先建立 inert lane/instance/scheduler，再由 construction-only typed factory取得 ordinary promotion capability并创建 coordinator，一次性 bind required terminal port，随后才启动 heartbeat/watchdog。
- factory/create/bind 失败测试断言所有 critical task 均未启动，coordinator 与 lane/instance owner 各关闭一次，scheduler 不返回；没有临时 no-op port、public setter或 runtime rebind。
- execution actor、wait poller、startup recovery、scheduler-owned Engine ingestor 显式共享同一 opener coordinator。
- Host close 顺序为 public gate → wait poller → durable actor intake/drain → scheduler producers → coordinator → Session Event Delivery → projection/actor/store。ordering recorder 与 close barrier 均有直接断言。

### 6. Engine 与同页 multi-terminal

- 真实 Engine owner path 使用两个受控 worker：每个先发布 reasoning transient，再提交 terminal；A transient < A terminal < B transient < B terminal。
- watcher 消费前先让两条 terminal durable fact 都提交，并通过一次 `read_session_host_events_after` page 直接断言该页同时包含 A、B terminal，随后再验证两个 terminal handoff 顺序。
- Engine accepted duplicate、worker lost及首次 terminal 的 exact notice/flag 由 producer tests覆盖；Engine package未引入 Host terminal contract依赖。

### 7. Dual-opener accepted finding fix

- opener A、C 分别绑定实例级 hook counter，counter 只接受自己的 hub并转发原 production hook。
- action 前 A/C watermark 均为 0；A terminal 后直接断言 A hook 至少一次且 A watermark 前进。
- 同时断言 C hook 为 0、C watermark保持 pre-action/0、C watcher仍 pending、C reconciliation clock未推进时 page read 为空。
- 保留 shared Host DB/lane DB、独立 opener runtime/worker、durable B fence、multi-page catch-up、A terminal先于B、timeout 计数、retained item与 A/C cleanup顺序断言。
- `tests/host/test_watch_session_events.py` 的 diff 只涉及该 counter 与目标 dual-opener 方法内 setup/helper/断言。

## 验证结果

### Tests

- 目标 dual-opener：`1 passed in 0.61s`
- 完整 `tests/host/test_watch_session_events.py`：`18 passed in 1.75s`
- 三条 A→B owner barrier：`3 passed in 0.43s`
- same-page multi-terminal + standalone committed-row runtime fake：`2 passed in 0.41s`
- S3 focused gate：`405 passed in 6.84s`
- 完整 Host suite + coverage：`2066 passed, 1 skipped, 6 deselected in 69.77s`

### 单文件 coverage

完整 Host suite 的 JSON 报告位于 `workspace/tmp/wu-host-session-event-delivery-01-s3-host-coverage.json`。

| Production file | Coverage |
|---|---:|
| `dayu/host/admission.py` | 91% |
| `dayu/host/command.py` | 88% |
| `dayu/host/dispatch.py` | 91% |
| `dayu/host/durable/run_transition.py` | 93% |
| `dayu/host/engine_ingest.py` | 91% |
| `dayu/host/open_host.py` | 88% |
| `dayu/host/recovery.py` | 91% |
| `dayu/host/terminal_post_commit.py` | 95% |
| `dayu/host/waiting.py` | 89% |

全部修改过的 production 单文件均达到 `>=80%`。

### Type、diff、source 与 scope

- `pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- terminal producer AST manifest与 ordinary direct promotion allowlist：通过。
- `dayu/engine` 的 TerminalPostCommit/session delivery 引用扫描：为空。
- `dayu.runtime` 对 Engine/Host/Service/UI/Fins 的真实 import 扫描：为空。
- optional/default terminal production port、runtime setter/rebind、session-id-only旧 handoff与 direct terminal promotion bypass 扫描：无缺口。
- 实际 production/test 修改均在 S3 allowlist 内；本次额外 review artifact由用户明确要求。
- `docs/host/issues-implementation-control.md` 是恢复时已存在的 Controller-owned dirty change；AgentCodex未读取后写回、未更新、未 stage。

## README trigger audit

- `dayu/host/README.md`：Host delivery owner与terminal coordinator变化命中触发。
- `tests/README.md`：新增terminal manifest、owner barrier与focused gate命中触发。
- `dayu/README.md`：整个 WU 的跨层消费边界命中触发；本 S3 未改变已冻结分层方向。
- `dayu/service/README.md`、`dayu/config/README.md`：属于整个 WU 的 S4/config最终同步面，本 S3未修改其 owner事实。
- 根 `README.md`：CLI参数、安装步骤、用户工作流未变化，不触发。

Accepted plan 把全部 README 文件列为 S4 allowed modules；S3 修改 README 会越过当前 allowlist。因此本 Slice 只完成审计并记录触发，不更新 README，交由 S4 在完整最终事实落地后统一更新。

## 风险与未覆盖项

- 未发现 S3 contract 的已知 residual correctness risk。
- Service exact-five、CLI callback execution domain、旧 Service relay删除及 README 实际更新属于已批准的 S4，不在本 Slice 实施或冒充完成。
- 未执行 commit、push、PR或 control doc 更新。

`READY_FOR_CODE_REVIEW`
