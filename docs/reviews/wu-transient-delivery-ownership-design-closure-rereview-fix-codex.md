# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership 第四轮 Closure Re-review Fix（Codex）

## Gate metadata

- Gate：phaseflow 第四轮 final-scope design fix。
- Work unit：`WU-CLI-SMOKE-01-R1` transient delivery ownership post-closeout bug-fix / design-fix。
- Controller decision：接受 `CODEX-CLOSURE-REREVIEW-F01`；finding状态由`未修复`修订为`已修复`，等待独立closure re-review确认。
- 允许修改：`docs/host/design.md`、`docs/reviews/wu-transient-delivery-ownership-design-codex.md`与本新artifact。
- 禁止范围：代码、测试、总控、README、其它review / fix artifacts、commit、push、PR与下一gate。
- Implementation authorization：本gate只冻结未来实施契约，不实施Python或tests。

## First-principles decision

finding动机成立且高严重度没有被高估。问题不是watermark merge算法本身，也不是Service缺少第三个buffer；问题是terminal durable truth到watermark owner之间的数据流没有覆盖所有producer。

直接代码事实如下：

- `admission.py` 的pre-dispatch / waiting / recovering cancel与通用closeout会在write commit后直接用`session_id`发promotion wake；queued / session cancel与terminal ack也能产生或确认Session-visible terminal。
- `waiting.py` 的failed / lost / expiry transaction内已经得到exact terminal Run row，但外层只返回`queue_promotion_session_id`。
- `dispatch.py` 的watchdog把多个terminal压成`closed_session_ids`，pre-start / startup closeout丢弃exact transition result。
- `recovery.py` 把ordinary accepted / queued reconciliation和terminal lost投影为Session promotion集合，没有逐terminal after-commit signal。
- `engine_ingest.py` 的terminal accepted / duplicate continuation仍只拿`session_id`调用普通promotion。
- `open_host.py` 已有跨thread marshal到opener loop的bridge，`command.py`是admission / waiting composition seam，因此无需把修复下沉Service或扩张Engine public contract。

根因是唯一terminal delivery cutoff owner缺少同源typed input。修复必须从产生/确认terminal的同一个durable transaction result携带exact sequence，并把全部producer接到single coordinator；commit后latest-row readback、Session级猜测、Service fallback或terminal marker collection都会制造第二真源或丢失顺序。

## Frozen owner contract

### Typed notice and port

唯一Host-internal contract固定为：

```text
TerminalPostCommitNotice(
  session_id: str,
  terminal_event_sequence: int,
  wake_queue_promotion: bool,
)

TerminalPostCommitPort.notify_terminal_post_commit(
  notice: TerminalPostCommitNotice,
) -> None
```

- notice字段只能是上述三个：`session_id`非空，`terminal_event_sequence`为非bool正整数，`wake_queue_promotion`为bool；无extra payload、reason、可选sequence或兼容alias。
- contract owner是未来`dayu/host/terminal_post_commit.py`；它不public export、不持久化、不进入EventLog / projection / Service / LLM上下文。
- port唯一implementation owner是`open_host` opener内的terminal post-commit coordinator；producer只依赖Protocol，不读取subscription或scheduler内部状态。

### Transaction-local exact sequence

任何write transaction新提交或在同一幂等scope内确认Session-visible Run terminal时，immutable transaction result必须携带：

- 本transaction刚append的exact Run terminal EventLog row，或
- 本transaction按稳定idempotency result ref读取并确认的exact terminal Run row。

producer只从该result构造notice。禁止commit后新开read transaction，禁止latest Run / latest EventLog row / max sequence readback，禁止用Attempt terminal、cancel request、Session id、事件类型、日志或时间戳猜sequence。batch transaction按exact sequence保留`tuple[TerminalPostCommitNotice, ...]`，不能按Session去重。

`wake_queue_promotion=true`仅表示本次transaction新释放active slot且需要queue reconciliation。queued cancel、terminal ack / replay、同transaction已关闭全部目标的session-scope cancel与其它不释放active slot的terminal为false。幂等确认仍携带exact sequence，但不伪造新的slot release。

### Single coordinator ordering and idempotency

producer只能在`run_write(...)`成功返回后同步调用terminal port。非owner thread必须marshal到opener owner loop并等待该同步协调完成；owner-loop caller直接执行。coordinator对每个notice在同一无`await`critical sequence执行：

1. 对Session Event Delivery的`committed_terminal_event_sequence_high_watermark`做max-advance。
2. watermark前移时level-trigger该Session attached subscriptions的terminal-ready wake。
3. 仅在flag=true且sequence大于per-Session O(1) `queue_promotion_terminal_event_sequence_high_watermark`时，先推进该promotion-dedupe scalar，再调用原queue-promotion wake。

同sequence duplicate不会重复推进delivery cutoff或重复enqueue true promotion。false不推进promotion scalar，因此先到false、后到同sequence true仍会补发；较新false也不能吞掉较旧尚未处理的true。不同sequence不按duplicate分类：commit顺序内的每个新true都reconcile；较新true若先完成，其queue check已涵盖稍后到达的较旧true。两个scalar都只存在当前runtime，不持久化，不是terminal set / marker queue。

普通initial admission、accepted / queued startup reconciliation与其它non-terminal promotion继续走原只含`session_id`的port，且绝不能推进terminal watermark。terminal producer禁止直接调用该port绕过`TerminalPostCommitPort`。

## Exhaustive current producer manifest

| Owner | 当前可达producer | Notice / flag rule |
|---|---|---|
| admission | queued、pre-dispatch、WAITING、RECOVERING cancel；terminal ack；session-scope cancel；`closeout_attempt_terminal` | 每个terminal exact；单Run active-slot release /通用active closeout为true，queued / ack /全目标session cancel为false。 |
| waiting / command | failed、lost、deadline expiry与same-scope replay；WAITING cancel由admission writer接线 | 首次terminal release为true，replay为false；resume-only completed / cancelled wait无notice。 |
| Engine ingest | Engine succeeded、failed、cancelled；worker lost与其它lifecycle terminal；accepted duplicate | commit / duplicate都携带exact sequence；仅新slot release为true，不能再调用session-id terminal promotion helper。 |
| dispatch | active-cancel watchdog、attempt-free pre-start failure、worker startup terminal；worker lost委托ingest | watchdog batch逐notice；每个transition按是否新release决定flag，不能返回`closed_session_ids`代替sequence。 |
| startup recovery | recovering dispatch-limit lost、unrecoverable orphan / cancelling lost closeout | terminal action逐notice；ordinary accepted / queued reconciliation继续走普通promotion，不触碰watermark。 |

未来任何新增Session-visible terminal writer必须扩展同一typed transaction result、port callsite manifest与owner tests；不能以“实现时再audit”进入implementation。

## Future implementation authorization

未来implementation WU至少覆盖：

- `dayu/host/terminal_post_commit.py`、`transient_delta.py`、`open_host.py`；
- `dayu/host/durable/run_transition.py`与必要producer-local immutable result types；
- `dayu/host/admission.py`、`waiting.py`、`recovery.py`、`engine_ingest.py`、`dispatch.py`、`command.py`；
- 对应owner tests，至少`tests/host/test_terminal_post_commit.py`、`test_admission_queue.py`、`test_resolve_wait_command.py`、`test_phase7_waiting_integration.py`、`test_recovery_scan.py`、`test_recovery_dispatch.py`、`test_engine_ingest_mapping.py`、`test_local_proxy_engine_ingest.py`、`test_dispatch_scheduler.py`、`test_active_cancel_dispatch.py`、`test_open_host_runtime.py`、`test_command_handle.py`、`test_watch_session_events.py`与Service ack / rebind tests。

`command.py`必须显式注入terminal port；waiting result删除`queue_promotion_session_id`的terminal语义；recovery / watchdog batch保存逐notice；engine ingest删除只含session id的terminal promotion helper。Engine public contract、durable schema与Service event buffer均不变。

## Acceptance

### Static and call-graph proof

`tests/host/test_terminal_post_commit.py`必须通过AST / qualified symbol生成全部Run-terminal transition callsites的`(module, producer, transition)`集合，并与本manifest exact比较；任何新增未登记writer立即失败。另一个exact allowlist只允许non-terminal governance / recovery reconciliation与`open_host` coordinator内部调用`wake_queue_promotion(session_id)`；terminal producer qualified function出现直接调用即失败。

每个producer另用fake terminal port证明：transaction commit成功返回后，从result取exact notice并进入single port；rollback / CAS miss不发notice；flag=true也不直接调用ordinary port。静态manifest、runtime dataflow与integration barrier三层共同证明terminal commit + promotion没有bypass，不保留人工audit open question。

### Exact ordering barriers

除既有Engine terminal barrier外，必须分别实现三组non-Engine barrier：

1. pre-dispatch cancel A + queued B；
2. wait failed A + queued B；
3. wait expiry A + queued B。

每组冻结watcher，记录transaction-local exact A terminal sequence，在owner-loop watermark advance后才允许B promotion / publish，然后恢复watcher。exact assertions为：

- watermark先推进到exact A sequence，terminal-ready wake先于promotion；
- merge先bounded catch-up并只交付A mailbox prefix；
- A durable terminal先first-commit；
- 首个B entry始终留在同一Host counted mailbox，不被Service预读 /缓存；
- 只有Service完成A ack / clear / rebind后发起的下一次`anext()`才向generation B交付B。

额外owner tests必须覆盖：同sequence duplicate notice幂等；terminal notice flag=false仍推进watermark / wake但不promotion；普通non-terminal promotion不推进watermark；先false后同sequence true可补发；较新false不吞较旧true；batch同Session多个sequence不丢失。

## Closure matrix

| Finding / closure | 第四轮状态 | 依据 |
|---|---|---|
| `CODEX-CLOSURE-REREVIEW-F01` | **已修复** | exact notice / port / coordinator、全producer manifest、实施授权、静态call graph与三组non-Engine barrier均已冻结。 |
| `CODEX-FINAL-REREVIEW-F02` | **保持关闭** | exact-five disposition、delivery-only recovery、stop / late commit与cleanup precedence未修改。 |
| `CODEX-REREVIEW-F02` | **保持关闭** | single mailbox +唯一in-flight retained owner与无Service relay未修改。 |
| `CODEX-REREVIEW-F03` | **保持关闭** | per-Session admission、先reserve后allocation与全release contract未修改。 |
| `CODEX-REREVIEW-F04` | **保持关闭** | payload bytes -> item count -> cumulative bytes的primary顺序与四组fixtures未修改。 |

## Non-goals and prohibited regressions

- 不增加durable schema、第三event / sequence domain、跨域cursor或terminal marker history。
- 不做latest-row readback、Service fallback、第二event buffer或promotion pause。
- 不改变EventLog terminal truth、Run / Attempt / Outbox owner或Engine public contract。
- 不为旧port保留terminal兼容wrapper / alias；普通promotion与terminal port语义必须分开。
- 不重开exact-five、cleanup precedence、single retention、admission或overflow closure。

## Validation

- stale scan：三份输出均覆盖notice / port / exact sequence、双O(1) scalar、全producer文件、AST manifest、三组non-Engine barrier、duplicate / flag=false / ordinary promotion；占位文本、barrier覆盖不足、post-commit readback方案、producer待审与旧capacity residual没有最终contract命中。
- `git diff --check`：pass；tracked diff只包含`docs/host/design.md`。
- `git diff --no-index --check /dev/null docs/reviews/wu-transient-delivery-ownership-design-codex.md`：无whitespace diagnostic，exit `1`只表示新文件内容不同。
- `git diff --no-index --check /dev/null docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-fix-codex.md`：无whitespace diagnostic，exit `1`只表示新文件内容不同。
- `source .venv/bin/activate && pyright`：pass，`0 errors, 0 warnings, 0 informations`；仅有版本更新提示。
- changed-file boundary：只修改两份指定既有文档并新增本artifact；其它未跟踪review artifacts的SHA-256与接管前基线一致；代码、测试、总控与README零修改。
- 未运行tests：本gate没有实现行为变更；对应owner / integration / static tests已作为future implementation acceptance冻结。
- 未commit、未push、未创建或修改PR。

## Remaining decisions and risks

没有blocking open question，没有未归属residual，也没有producer reachability / owner接线audit项。未来implementation WU只需用测量裁决：

1. packaged `transient_mailbox_max_items`、`transient_mailbox_max_bytes`、`max_subscriptions_per_session`数值；
2. logical UTF-8 byte budget到Python resident heap的safety margin；
3. 不含payload正文或高基数identity的低基数metrics字段与采样。

字段、算法、owner、port、flag、duplicate、call graph、barrier与test matrix均已冻结；上述measurement不阻塞设计closure。
