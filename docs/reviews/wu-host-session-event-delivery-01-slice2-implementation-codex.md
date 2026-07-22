# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 2 Implementation

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`implementation-slice-2`
- Agent：`AgentCodex`
- accepted Slice 1 commit：`64383186`
- Plan：`docs/host/wu-host-session-event-delivery-01-plan.md`
- Artifact：`docs/reviews/wu-host-session-event-delivery-01-slice2-implementation-codex.md`
- 结论：`PASS`。S2 durable causal fence、bounded merge、跨 opener reconciliation、overflow 顺序与本地 watermark owner state 均已完成；没有触发 stop condition。

## 第一性原理与 owner 裁决

动机成立。旧 merge 只有 transient runtime sequence、durable EventLog sequence 与 watcher-local terminal Run-id set；它无法证明 opener C 收到 Run B delta 时已经观察到 opener A 在共享数据库提交的 terminal，也不能用 post-transaction latest/max readback补出同源因果关系。

正确 owner 与实现路径如下：

| 语义 | 唯一 owner | 直接证据与实现 |
|---|---|---|
| transient durable causal fence 真源 | Engine-ingest validation transaction | `_IngestValidatedOperation` 在同一 write transaction 读取 current `AttemptRow`；`_validated_transient_delta_candidate(...)` 直接使用 `context.attempt.started_event_sequence`，见 `dayu/host/engine_ingest.py:5263-5275`。 |
| candidate / mailbox entry shape 与 retained accounting | `dayu.host.transient_delta` | candidate 与独立 mailbox entry 都 strict 校验 non-bool positive fence；每个 subscription 持有独立 entry，immutable public event可共享；entry整体仍只计一个 retained item，见 `dayu/host/transient_delta.py:219-311`、`:478-517`、`:869-908`。 |
| durable/transient merge、cursor、terminal handoff、periodic reconcile | `dayu.host.open_host` | attach 把 transaction cursor交给subscription；iterator逐row处理 durable page、pop前追 head fence、使用唯一 current terminal、mailbox-empty timeout一次只授权一页，见 `dayu/host/open_host.py:975-1001`、`:1028-1167`。 |
| opener-local terminal delivery watermark hook | Session Event Delivery hub owner state | hub按 Session只维护一个 EventLog sequence high-watermark scalar，并 level-trigger已有subscription；本 slice只定义状态和hook，没有接任何terminal producer、coordinator或promotion port，见 `dayu/host/transient_delta.py:910-965`。 |

`AttemptRow.started_event_sequence` 在现有 durable schema/type上已经是 required `int`，candidate boundary再次拒绝 bool、0与负数。无需修改 validation owner之外的模块，也没有触发“同事务 Attempt row无法取得 fence”的 stop condition。

## 实现 dataflow

```text
EngineEvent transient candidate
  -> _IngestValidatedOperation current write transaction
  -> validated context.current Attempt.started_event_sequence
  -> ValidatedTransientDeltaCandidate(durable_causal_fence_event_sequence)
  -> HostTransientDeltaHub.publish
       -> one immutable public HostTransientDelta
       -> one independent mailbox entry per subscription
          (same event reference + exact fence value, one retained item)
  -> iterator peeks head without pop
       -> durable cursor < fence: retain head and read existing bounded pages
       -> durable terminal: deliver continuous same-Run mailbox prefix
          -> retain first different-Run head
          -> yield terminal
       -> cursor >= fence and no pending durable row: single pop/yield
```

没有建立第三 sequence。fence只是引用既有 durable EventLog sequence；没有进入 public delta、trace、memory、prompt、schema或日志，也没有持久化/replay transient delta。

## Merge 与 overflow 顺序

`_watch_session_events_after(...)` 当前顺序固定为：

1. resume后释放上一轮唯一 in-flight；Host close先正常 EOF。
2. 若 subscription 已 overflow，逐项交付全部 accepted mailbox prefix；prefix为空时立即抛 non-retryable typed delivery error。
3. overflow分支优先于已读 pending durable page与 current terminal。即使terminal已经durable提交或预读，也不能插入accepted prefix与overflow error之间。
4. 非overflow路径才处理 current terminal：只pop mailbox head中连续的same-Run prefix，遇到首个different-Run entry原位保留；terminal yield后下一次`anext()`才重新评估该head。
5. bounded durable page逐row推进实际处理cursor；terminal cursor只在terminal实际yield时推进。page结束后再采用该页`next_cursor`，未修改`read_api` page size 64。
6. pop前peek head fence；cursor落后时entry不pop、retained count不变，并按既有page limit逐页catch up。
7. mailbox空且没有local watermark领先时，sole active `anext()`等待level readiness。只有Host-internal interval timeout分支读取一次、最多一页；处理完该页或空页后重新等待。Host close设置同一个closed readiness，直接收口EOF。

Controller指出 slow watcher 一度被错误放宽为“512 prefix后可先见terminal再overflow”。实现和测试均已恢复 accepted contract：`tests/host/test_watch_session_events.py:1278-1309`要求前512项全部为按`worker_event_index=1..512`排序的`HostTransientDelta`，下一次拉取立即得到`DELIVERY_INTERRUPTED/TRANSIENT_MAILBOX_OVERFLOW`；任何durable event插队都会直接失败。

## Deterministic barriers

### 同事务 fence

`tests/host/test_engine_ingest_mapping.py:2645-2693`把validation transaction真实读取的current Attempt row只替换为唯一sentinel fence，断言read发生一次且publisher candidate精确携带该值。这会阻止post-transaction latest/max readback、Run字段、时间戳或重算路径通过测试。

### Fanout、readiness 与 owner state

- `tests/host/test_transient_delta.py:153-194`断言每订阅entry对象独立、public event引用相同、fence值完全一致。
- local watermark测试断言max advance、duplicate/older幂等、cursor追平后readiness复位；源码断言terminal Run-id set与`mark_run_terminal`消失。
- strict shape测试拒绝bool与zero fence；mailbox仍只暴露peek/single-pop/in-flight retained语义，没有batch drain。

### Same-Run handoff 与 different-Run retention

`tests/host/test_watch_session_events.py:1324-1401`先冻结Run A transient prefix，再提交A terminal并在head追加Run B entry，精确断言顺序为`A delta -> A terminal -> B delta`；terminal前B仍在mailbox计数，terminal yield天然形成下一次`anext()`边界。

### 双 opener causal fence

`tests/host/test_watch_session_events.py:1404-1560`直接在该文件内构造两个独立`open_host` context：

- opener A与C只共享`db_path`、`lane_db_path`；artifact roots、worker factories、Host handles、scheduler、actor/store、hub、waiter与lifecycle彼此独立。
- watcher与Run B属于C；Run A terminal只由A提交。
- C先停在empty-mailbox readiness；A commit后，C的pending `anext()`仍未完成、page-read count为0、local watermark为0、local hook调用数为0。
- C发布携带current Attempt start fence的B entry后立即断言retained count为1；跨至少三次page read期间该count保持1，cursor严格递增且无重复。
- C最终先观察A terminal，再观察B delta；整个路径`timeout_count=0`，证明正确性来自B fence与共享durable DB，而非local hook或periodic clock。
- cleanup顺序固定为取消/await pending `anext()`、`aclose()` C watcher、退出C context、最后退出A context。

### Empty-mailbox periodic reconcile 与 close

`tests/host/test_watch_session_events.py:1563-1711`使用同一可控opener-local waiter：A提交跨多页durable events后，C每释放一次timeout都精确增加一次page read；同一page内逐event交付，下一页必须等待下一次timeout。最终C在没有local notice时观察A terminal。随后在下一interval尚未释放时关闭Host C，pending `anext()`在0.5秒gate内正常EOF，不依赖真实sleep缩短。

## 实际修改文件

Production严格限于：

- `dayu/host/engine_ingest.py`
- `dayu/host/transient_delta.py`
- `dayu/host/open_host.py`

Tests严格限于S2允许集合中的：

- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_transient_delta.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_open_host_runtime.py`

另新增本implementation artifact。没有修改`dayu/host/read_api.py`、Service、CLI、其它fixture/support、plan、既有review/controller artifact或总控。Controller-owned `docs/host/issues-implementation-control.md` 在进入本轮前已有未提交diff，本轮没有修改、格式化、stage或清理该文件。

## Tests 与 validation

所有命令均在`source .venv/bin/activate`后运行。

| 验证 | 结果 |
|---|---|
| S2 focused：plan §8.1的5个文件 | `159 passed` |
| slow overflow + dual-opener核心顺序复验 | `3 passed`；随后retention/hook隔离加强版`2 passed` |
| affected suites：`tests/host tests/runtime tests/service tests/cli`最终全量复跑 | `3410 passed, 8 skipped, 6 deselected` |
| Host production stress | `5 passed` |
| transient delta stress | `1 passed` |
| `dayu.host.engine_ingest`单文件coverage | `90.66%` |
| `dayu.host.transient_delta`单文件coverage | `92.00%` |
| `dayu.host.open_host`单文件coverage | `84.28%` |
| 完整`python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | exit `0` |

affected suites首次运行有一个未修改文件中的既有10ms lane acquire timeout：`test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`。该node立即单独复跑`1 passed`，最终完整affected suites再次运行全绿；失败堆栈未经过本slice三个production owner，因此没有越界修改`test_dispatch_scheduler.py`或dispatch production。

pytest只报告既有`edgar`三条deprecation warnings，不影响本slice correctness。

## Source、boundary 与 scope audit

- `git diff --check`通过；最终modified production/tests都在S2 allowlist内。
- `_terminal_run_ids`与`mark_run_terminal`在production为0命中；只在owner-shape删除断言中出现。
- local terminal watermark hook在production只有定义与subscription owner推进，不存在terminal producer/coordinator/promotion调用。
- `durable_causal_fence_event_sequence`只存在于engine-ingest candidate、transient internal entry、merge读取与允许的owner tests；public `HostTransientDelta`字段没有变化。
- `dayu/host/read_api.py`无diff，page size保持64；没有新增timer loop、per-watcher background task或第三sequence。
- Service/CLI无diff。旧语义scan仍命中`dayu/service/entrypoint_runtime.py`现有`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY=256`定义和queue allocation两处；这是accepted plan明确由S4删除的relay，不属于S2允许范围。
- `dayu/engine`没有新增delivery contract；`dayu.runtime`没有反向依赖。
- 未stage、commit、push或创建PR。

## README trigger audit

修改前后均按`AGENTS.md`触发规则审计`dayu/host/README.md`与`tests/README.md`，并读取`dayu/host/README.md`自身`Agent更新约束【必须遵守】`。Host README当前S1文字尚未描述same-transaction fence、跨opener reconcile和新的terminal handoff；tests README当前也尚未列出S2 deterministic barriers。

本slice没有修改README：accepted plan把完整current-contract README同步明确放在S4，而S2 allowlist不包含任何README。根README、`dayu/README.md`、Engine/config/service README也没有本slice授权或用户可见入口变化。该决定避免在S2越界提前声明尚未完成的S3 coordinator或S4 sole-consumer状态。

## 非目标、风险与后续边界

明确没有实施：

- S3 terminal producer exact result、post-commit port、local coordinator、promotion dedupe/watermark-before-promotion接线。
- S4 Service relay删除、exact-five observation、CLI/UI改变与README最终同步。
- durable/transient全局总序、fence/delta持久化、离线transient replay、跨进程terminal广播、public page-size或policy扩展。

剩余已归属风险：

- local watermark hook在S2有owner state但故意未接线，当前同opener低延迟仍由transient readiness与periodic durable reconcile工作；exact terminal notice与promotion顺序必须由S3完成。
- 跨opener最终发现依赖sole consumer保持一个active `anext()`，并受Host-internal reconcile interval与durable read可用性影响；这是accepted contract，不是后台订阅或离线delivery承诺。
- Service仍保留S1 relay，最终sole-consumer与delivery recovery属于S4。

上述风险均已有accepted后续slice owner，不构成S2 stop condition。Blocking stop conditions：`None`。

## Completion status

`implementation-slice-2: PASS`

当前可进入Slice 2 code review gate；按用户指令，本轮不stage、不commit、不进入S3/S4。
