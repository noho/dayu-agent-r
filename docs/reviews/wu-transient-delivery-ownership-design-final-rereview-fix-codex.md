# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership 第三轮 Design Fix（Codex）

## Gate metadata

- Gate：phaseflow 第三轮 design fix gate。
- 执行 Agent：AgentCodex。
- Controller 裁决：接受 `CODEX-FINAL-REREVIEW-F01`、`CODEX-FINAL-REREVIEW-F02`，本 artifact 按 accepted finding 修复。
- 允许修改：`docs/host/design.md`、`docs/reviews/wu-transient-delivery-ownership-design-codex.md`，并新增本 artifact。
- 禁止范围：代码、测试、总控、README、其它 review / fix artifact、commit、push、PR。
- Gate 结果：设计修复完成，等待独立 final re-review。

## First-principles decision

两个 accepted finding 的动机成立，严重性没有被高估。

- F01 的直接失败不是 Service “看见 A terminal 后没有暂停”，而是 Host merge 可能在看见 durable A terminal 前先 pop 已发布的 B transient。当前代码的 transient-first drain 与 terminal closeout 后立即 promotion wake共同证明该时序可达；让 Service 缓存 B只会重建第二 buffer，暂停 promotion / Agent则会让慢 watcher获得反压执行能力。正确 owner 是 Host Session Event Delivery / iterator merge。
- F02 的直接失败不是 slot 容量不足，而是 first-commit 后的 caller disposition与 `aclose()` secondary failure没有穷举。错误类型、durable recovery资格和 cleanup precedence属于 Service watch-runtime public behavior，不能由 `try/finally` 偶然决定，也不能让 implementation agent二选一。

本轮选择的最小修复是：Host增加每 Session一个 O(1) latest terminal watermark作为 runtime handoff control scalar；Service冻结 exact-five result与唯一 cleanup/caller仲裁。没有增加 durable schema、第三事件类型、跨域 cursor、Service event cache、terminal marker queue或新的 recovery系统。

## Accepted finding closure

### F01：Host terminal handoff cutoff

唯一 owner contract 已写入 `docs/host/design.md` §4.1、§4.2、§4.4、§4.5、§4.6 与 public watch attach contract：

1. Session Event Delivery 对每个 Session维护一个 O(1)、单调不减的 `committed_terminal_event_sequence_high_watermark`。它只保存本 runtime最新 committed terminal `event_sequence`，不是 terminal id set / marker queue，也不是持久化业务事实。
2. terminal closeout线性化顺序恰为：

   ```text
   EventLog terminal commit
     -> opener owner-loop synchronous watermark advance + subscription terminal-ready wake
     -> queue-promotion wake
     -> B promotion / dispatch / transient publish
   ```

   watermark advance、subscription terminal-ready wake与 queue-promotion wake之间不得 `await` 或被另一个 attach / publish操作穿过。该顺序不等待 watcher，不暂停 promotion、Agent或 Engine。
3. eager attach在同一 owner-loop attach linearization中记录 durable start-cursor request位置与当前 watermark baseline，形成不可拆分的 snapshot。terminal要么位于 start cursor以前而不重放，要么位于以后并使 latest watermark超过 subscription durable cursor；首次 `anext()` 只解析既有 cursor future，不得重新选择 baseline或 lazy attach。
4. merge每次准备 pop transient前都读取 latest watermark。若 durable cursor落后，禁止 pop transient，先用 bounded EventLog pages追赶；page size只限制单页，不是 correctness停止预算。cursor只推进到实际处理 row，不越过未交付 terminal。
5. 遇 terminal A时，只从 counted mailbox头部逐项 pop / yield `run_id=A` 的 pre-terminal prefix。首个不同 Run entry原位留在同一 mailbox，继续计入 mailbox + in-flight budget且不得 pop；随后 yield durable terminal A。
6. terminal `yield` 的 generator悬停让 Service first-commit、ack / clear与 rebind。只有下一次 `anext()` 才释放 A fence并可能交付 B；Service不缓存、预读或转存 B。
7. 慢 consumer期间出现多个 terminal时，merge依靠 EventLog顺序和一个 latest scalar逐个发现；每次 terminal yield停止扫描，未消费 suffix不推进 cursor，下次从 EventLog重新发现。禁止 terminal id set、marker queue或历史 terminal replay。
8. watermark / barrier只约束 terminal handoff，不建立 durable / transient可比较总序，不产生可持久化 cursor，不取代 ingest post-terminal late-state validation。

Integrated acceptance 已冻结：冻结 watcher，提交 A terminal；确认 watermark已在 promotion wake前推进；允许 B promotion并发布至少一个 delta；恢复 watcher。必须断言 A prefix / A terminal先到、首个 B entry始终留在 Host counted mailbox，Service完成 A ack / rebind后的下一次 `anext()` 才向 generation B交付 B，且不存在 Service event buffer、promotion pause或 terminal marker collection。另用多个连续 terminal证明 EventLog + latest scalar逐个发现。

### F02：exact-five disposition

`ServiceObservationResult` 现在恰好只有五个 members，不是“至少”：

```text
TARGET_TERMINAL(target_generation, terminal identity + result)
DELIVERY_INTERRUPTED(target_generation, typed Host delivery error)
ITERATOR_ENDED(target_generation)
CALLBACK_FAILED(target_generation, callback kind + original failure)
ITERATOR_FAILED(target_generation, original iterator failure)
```

cleanup后的唯一 disposition如下：

| Member | 唯一 disposition |
|---|---|
| `TARGET_TERMINAL` | 返回 first-committed terminal，不做 durable重算。 |
| `DELIVERY_INTERRUPTED` | 只走 `get_run` / Outbox durable recovery；成功返回 terminal；失败原样传播 recovery exception，并 `raise recovery_error from delivery_error`。 |
| `ITERATOR_ENDED` | 抛 `EntrypointRuntimeError("session_event_iterator_ended_before_terminal")`，完整 message即 stable reason；不 recovery。 |
| `CALLBACK_FAILED` | 原样重抛 callback original exception。 |
| `ITERATOR_FAILED` | public `HostApiError` / `HostClosedError` 原样抛；非 public exception wrap 为 `EntrypointRuntimeError("session_event_iterator_failed_before_terminal") from original`。 |

`DELIVERY_INTERRUPTED` 是唯一可进入 watcher-failure durable recovery的 member；EOF、callback与 iterator failure不得共享一个模糊 “fail closed或 recovery” 分支。

### F02：cleanup precedence

slot first-commit primary永不被覆盖。cleanup固定先 stop / await sole consumer、确认没有 active `anext()`，再调用一次 public `aclose()`；Host reservation release仍由 Host iterator / subscription `finally`保证，Service不做 release fallback。

- exception或 caller cancellation已是 primary且 close也失败：primary保持 top-level，`raise primary from cleanup_error`。non-public iterator double failure保留三层 chain：top-level stable `EntrypointRuntimeError` -> original iterator error -> cleanup error。
- delivery recovery失败：recovery exception保持 top-level，delivery error是直接 cause；若 close也失败，cleanup error只作为 delivery error nested cause。
- `TARGET_TERMINAL` 或 delivery recovery已成功得到 terminal而 close失败：仍返回 terminal；通过现有 `on_activity` 最多尝试一次 `WATCHER_DIAGNOSTIC` / `FAILED` / `WARNING`，`run_id=None`、`event_sequence=None`、stable dedupe key=`entrypoint_watcher_cleanup_failed`、title=`运行事件流清理失败`、summary=`已保留终态结果，但运行事件观察器清理失败。`，tool / counts字段均为 `None`。diagnostic不含 exception类型、message、identity、payload或 traceback；callback自身失败被吞掉，不能改变 primary。
- slot为空且没有 caller cancellation：close failure是唯一 caller failure；`HostApiError` / `HostClosedError` 原样抛，其他 exception wrap为 `EntrypointRuntimeError("session_event_iterator_cleanup_failed") from cleanup_error`。
- coordinator stop或 caller cancellation先在空 slot取得仲裁权后，late terminal / callback / EOF / iterator failure commit全部无效；helper cancellation不等于用户 Run cancel。

Exact acceptance：

| 场景 | 必须断言 |
|---|---|
| callback + close | callback original exception top-level，cleanup direct cause；无 recovery / success diagnostic。 |
| EOF + close | stable EOF `EntrypointRuntimeError` top-level，cleanup direct cause；无 recovery。 |
| iterator + close | public Host exception原样 top-level + cleanup cause；non-public按 wrapper -> original -> cleanup三层 chain。 |
| terminal + close | 返回同一 terminal；最多一次 sanitized diagnostic；diagnostic callback失败仍返回 terminal。 |
| delivery recovery success + close | 返回 recovery terminal；同一 sanitized diagnostic；不 reattach。 |
| slot empty + close | cleanup是唯一 caller failure；public Host原样，非 public stable wrap。 |
| cancellation + close | 原 `CancelledError` top-level，cleanup direct cause；late commit无效、无 recovery、无用户 cancel事实。 |

## Design source alignment

`docs/host/design.md` 与 `docs/reviews/wu-transient-delivery-ownership-design-codex.md` 已对齐以下事实：

- watermark owner、attach snapshot、commit / wake / publish顺序、pop前 catch-up、same-Run prefix、不同 Run head retention、terminal yield handoff与 multi-terminal发现算法；
- barrier不是跨域总序 / cursor，不暂停执行，不让 Service缓存 B；
- `ServiceObservationResult` exact-five member list、唯一 disposition、delivery-only recovery、cleanup precedence与 stable diagnostics；
- future implementation owner、integrated barrier与七组 cleanup exact tests；
- 旧总控中两个 capacity WU的登记冲突仍留给 Controller，本 gate未修改 control doc，也未为旧登记增加兼容分支。

## Direct evidence retained

- `dayu/host/open_host.py:985-986,1000-1020` 当前在 durable read前和 terminal处理前 drain transient，直接形成 B-before-A-terminal风险。
- `dayu/host/engine_ingest.py:2765-2784` 当前 terminal closeout后立即发 promotion wake；`dayu/host/dispatch.py:1118-1136,2921-2953` 由独立 promotion queue / task推进 B，证明慢 watcher期间 B publish可达。
- `dayu/host/open_host.py:1269-1283` 允许 iterator cleanup failure透传并由 Host `finally` close subscription，证明 Service必须定义 double-failure caller precedence，但 reservation release不能迁移给 Service。
- `dayu/service/entrypoint_runtime.py:79-80,102,1414-1448` 已有 `EntrypointRuntimeError` 与 `WATCHER_DIAGNOSTIC` / activity callback语义，可承载本轮 stable Service error和 best-effort sanitized secondary diagnostic，无需新增第二 outcome channel。

## Validation

- stale wording scan：pass。旧“至少五成员”、EOF / iterator二选一 recovery、旧 transient-first terminal fence、旧“不运行 pyright”自述与旧 finding closeout均无最终命中。
- frozen-decision scan：pass。三份输出均可定位 watermark / terminal-ready wake / bounded catch-up、三个 stable Service reason、cleanup diagnostic和七组 exact acceptance；packaged数值、heap margin、metrics保持唯一非阻塞测量项。
- `git diff --check`：pass。
- 对两个未跟踪输出分别运行 `git diff --no-index --check /dev/null <file>`：无 whitespace diagnostic；返回 `1` 仅表示与 `/dev/null` 内容不同。
- `source .venv/bin/activate && pyright`：pass，`0 errors, 0 warnings, 0 informations`；仅有 pyright新版本提示。
- changed-file boundary：本 Agent仅写入两个指定既有文档并新增本 artifact；没有修改代码、测试、总控、README或其它 review / fix artifact。
- 未运行测试：本 gate没有代码 / 测试行为变更；已执行用户指定的设计扫描、whitespace validation与完整 pyright。

## Remaining decisions and risks

没有 blocking open question，也没有留给 implementation agent自由选择的 terminal cutoff、result member、caller disposition、cleanup precedence或 recovery eligibility。

唯一保留的实施测量项是：

1. packaged `transient_mailbox_max_items`、`transient_mailbox_max_bytes`、`max_subscriptions_per_session` 数值；
2. logical UTF-8 byte budget到 Python heap resident-memory 的 safety margin；
3. 不含 payload正文或高基数 identity的低基数 metrics字段 / 采样。

这些 measurement item 均有 runtime composer / operator、Session Event Delivery implementation 与 future implementation WU作为 owner / destination，不是 design blocker。旧总控冲突由 Phaseflow Controller处理，不属于本 Agent允许修改范围。
