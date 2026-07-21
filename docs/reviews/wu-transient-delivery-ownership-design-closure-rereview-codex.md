# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Closure Re-review（Codex）

## Gate metadata

- 审查时间：2026-07-21 16:00:09 CST（+0800，来自本机系统时钟）。
- Gate：phaseflow design closure re-review。
- Reviewer：AgentCodex，使用 `planreview` adversarial review 方法。
- 审查结论：**FAIL**。
- Blocking findings：**1**。
- Material findings：**1**（高 1，中 0，低 0，严重 0）。
- 修改边界：只新增本 artifact；未修改设计、代码、总控、README、测试或既有 artifact。

## Reviewed target and scope

本次只读审查以下指定输入：

- `docs/host/design.md`；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-fix-codex.md`。

为验证设计能否覆盖当前真实 terminal producer 与 owner seam，另只读核对了 `dayu/host/open_host.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/host/admission.py`、`dayu/host/waiting.py`、`dayu/host/transient_delta.py` 与 `dayu/service/entrypoint_runtime.py` 的必要代码事实。代码只用于证伪设计假设，不是本次 code review 对象。按用户约束，旧 capacity WU 尚待 Controller 写回不计 finding。

## First-principles assessment

修改动机成立，严重性没有被高估。Host 单 mailbox + counted in-flight、per-Session admission、typed overflow 与 Service 单 observation-result slot仍是比双 buffer、durable delta、promotion pause或消息系统更小且 owner 清晰的路径。

`CODEX-FINAL-REREVIEW-F02` 已在 Service watch-runtime owner 内真实关闭：五成员是 exact closed union，五类 disposition 唯一，只有 delivery interruption可进入 durable recovery，stop / cancellation与 late commit有唯一 first-commit仲裁，cleanup double failure的 top-level / cause / diagnostic precedence以及去敏字段均已冻结。

`CODEX-FINAL-REREVIEW-F01` 的算法本身已经补齐：per-Session O(1) latest terminal scalar、atomic attach snapshot、commit -> terminal-ready wake -> promotion wake -> B publish、每次 pop 前 bounded-page durable catch-up、A prefix / terminal / B next-`anext()` handoff，以及 EventLog + latest scalar 的 multi-terminal发现都写入正确 Host owner。然而 future implementation WU 的授权范围没有覆盖所有会提交 terminal并立即唤醒下一 Run的 durable owner。当前 admission cancel与 waiting failure/expiry同样可完成 A terminal并发出 promotion wake；若这些路径不把精确 terminal `event_sequence` 先送入 Session Event Delivery watermark，修复后的 merge仍不会知道应先 catch up A。该遗漏使 F01 尚未形成全 terminal producer闭环。

## Assumptions tested

| 假设 | 结论 | 直接依据 |
|---|---|---|
| per-Session watermark是 O(1) latest scalar，而不是 terminal历史集合 | 是 | `docs/host/design.md:360,364` 明确只有单调 latest scalar与至多一个 current-terminal fence；后续 terminal从 EventLog重新发现。 |
| attach同时快照 durable start-cursor request位置与 watermark baseline | 是 | `docs/host/design.md:362,370,1162` 冻结同一 owner-loop linearization、过去 terminal不重放与首次 `anext()` 不重新选 baseline。 |
| Engine terminal遵守 commit -> watermark / terminal-ready wake -> promotion wake -> B publish | 设计上是，当前代码 seam可实施 | `docs/host/design.md:360,411,500`；当前 `dayu/host/engine_ingest.py:2765-2779` 在 commit返回后同步发 promotion wake，`dayu/host/dispatch.py:1118-1137` 在 owner loop排队 promotion。 |
| 所有可释放 active slot并触发 B promotion的 terminal producer都被 implementation scope覆盖 | **否** | `docs/host/design.md:492-506` 只把 terminal closeout接线落到 `engine_ingest.py` / `dispatch.py`；当前 `dayu/host/admission.py:753-787,4576-4587` 与 `dayu/host/waiting.py:771-779,819-841,1234-1276` 也会在 terminal commit后直接发 promotion wake。见 F01。 |
| pop前 catch-up是有界内存读取且不以 page size作为 correctness总预算 | 是 | `docs/host/design.md:364,411` 要求 bounded pages，追到已观察 watermark、public read failure或当前 terminal yield；cursor不越过未交付 terminal。 |
| A prefix / terminal / B handoff不需要 Service B buffer | 是 | `docs/host/design.md:364,411,476` 要求首个 B entry原位留在 Host counted mailbox，A terminal yield后只有下一次 `anext()` 才可能交付 B。 |
| multiple terminal不需要 unbounded marker | 是 | `docs/host/design.md:360,364` 要求每次 terminal yield停止扫描，未消费 suffix不推进 cursor，下一次从 EventLog重新发现；禁止 terminal id set / marker queue。 |
| `ServiceObservationResult` 恰好五成员且每类 disposition唯一 | 是 | `docs/host/design.md:417-437` 给出 exact-five union与穷举 caller disposition；`DELIVERY_INTERRUPTED` 是唯一 durable recovery资格。 |
| stop / caller cancellation可阻止 late commit且不伪造用户 Run cancel | 是 | `docs/host/design.md:439,455,478,486` 冻结空 slot first arbitration、late commit无效、原 `CancelledError` primary与无用户 cancel事实。 |
| cleanup double failure不会覆盖 first-committed primary | 是 | `docs/host/design.md:439-455` 冻结 exception chain、terminal return、slot-empty failure与七组 exact acceptance。 |
| cleanup success-path diagnostic已去敏且失败不改变 primary | 是 | `docs/host/design.md:442,452-453` 固定 kind/status/severity、空 identity、固定 title/summary、tool/counts空值，并禁止 exception type/message/payload/traceback；callback失败被吞掉。 |
| 此轮重新引入跨域总序、promotion背压、Service event buffer或 owner drift | 否 | `docs/host/design.md:360,358,372,415,476,500` 分别排除跨域 cursor/总序、consumer backpressure、Service event-copy relay，并保持 EventLog、ingest、Session Event Delivery与Service observation各自 owner。 |

## Closure matrix

| Finding / closure项 | 本轮结论 | 依据 |
|---|---|---|
| `CODEX-FINAL-REREVIEW-F01` / terminal handoff cutoff | **未完全关闭** | watermark与merge算法已充分规格化，但非 Engine terminal producer未进入 implementation scope / typed handoff，无法保证所有 terminal commit都先推进 watermark再 promotion。见本轮 F01。 |
| `CODEX-FINAL-REREVIEW-F02` / exact-five disposition与cleanup precedence | **已关闭** | exact member list、唯一 recovery资格、五类 caller disposition、stop/late commit、double-failure chain与 sanitized diagnostic一致且可直接生成代码与 exact tests。 |
| `CODEX-REREVIEW-F02` / single retention owner | **仍关闭** | batch drain被禁止；mailbox -> 唯一 in-flight只做单项 transfer，retained items / bytes直到 yield恢复或 cleanup才扣减；Service无 event-copy relay。 |
| `CODEX-REREVIEW-F03` / per-Session admission owner | **仍关闭** | required cap、check+reserve先于零资源分配、typed rejection、overflow期间保留 reservation、全 release path与 per-Session乘积上界均未被本轮修订改变。 |
| `CODEX-REREVIEW-F04` / overflow primary dimension | **仍关闭** | single-event bytes -> prospective item count -> prospective cumulative bytes的唯一顺序与四组 exact fixtures保持一致。 |

## Material findings

### CODEX-CLOSURE-REREVIEW-F01-未修复-[高]-terminal watermark接线遗漏非 Engine terminal producer，A/B cutoff仍可被绕过

- **状态**：`accepted-candidate`。
- **位置**：`docs/host/design.md` §4.1 的通用 terminal closeout contract（`:360-364`）、§4.4 readiness顺序（`:411`）与 §4.6 future implementation WU授权范围（`:492-506`）；原设计记录 future WU scope（`docs/reviews/wu-transient-delivery-ownership-design-codex.md:219-231`）；第三轮 fix artifact F01 closure与 source alignment（`docs/reviews/wu-transient-delivery-ownership-design-final-rereview-fix-codex.md:25-45,93-108`）。
- **问题类型**：范围漂移 / 架构边界 / 状态机漏洞 / 并发恢复风险 / 不可直接实施。
- **当前写法**：规范声称任一 terminal closeout都必须在 EventLog commit后，以精确 terminal `event_sequence`推进 Session Event Delivery watermark并唤醒 subscription，然后才可 queue promotion；但明确的 implementation文件清单只要求 `engine_ingest.py` / `dispatch.py`完成该接线，没有把同样提交 terminal并发 promotion的 admission与waiting owner纳入。当前共享 `AdmissionWakeupPort.wake_queue_promotion(session_id)` 也只携带 Session id，不能产生设计要求的精确 terminal sequence。
- **反例/失败场景**：
  1. watcher冻结，Session中 A处于 pre-dispatch active或 `WAITING`，B已排队。
  2. `cancel_run(A)`，或 wait failure / expiry，在 durable transaction内提交 A terminal并释放 active slot。
  3. 当前 admission / waiting路径只以 `session_id`发出 queue-promotion wake；若未来 WU严格按已授权文件实施，它们不会先推进 `committed_terminal_event_sequence_high_watermark`。
  4. B被 promotion、dispatch并发布 live delta；subscription watermark仍旧，因此 merge在 pop前比较得不到“durable cursor落后 terminal”的事实，可先把 B交给 generation A。Service按设计不缓存非目标 event，于是 B首批 live-only delta再次静默丢失。
- **为什么有问题**：watermark是 terminal handoff事实的唯一 runtime projection；只有每个 terminal producer在 commit后交付精确 sequence，它才是完整真源。用普通 promotion wake或 `session_id`猜“也许发生过 terminal”既不能区分初始 admission等非 terminal promotion，也无法给 bounded EventLog catch-up提供截止水位；在 Service补 buffer则违反单一 retention owner，在 promotion侧等待 watcher则引入反压。当前遗漏不是代码实现细节，而是授权 scope与 control port contract不完整。
- **直接证据**：
  - `docs/host/design.md:360,411` 把顺序写成所有 terminal closeout的通用不变量；`:500` 却只点名 Engine ingest / dispatch terminal seam，完整授权清单`:492-506`没有 `dayu/host/admission.py`或`dayu/host/waiting.py`。
  - 当前 `dayu/host/admission.py:753-787` 的 pre-dispatch cancel在 transaction commit后调用 `_promote_after_release`；`:4576-4587` 直接发 `wake_queue_promotion(session_id)`。同文件`:848-861` 的通用 terminal closeout也同样直接 promotion。
  - 当前 `dayu/host/waiting.py:771-779,819-841` 在 resolve / expiry commit后直接用 `queue_promotion_session_id`发 wake；`:1234-1276` 证明 failed wait会真实提交 `RUN_FAILED` terminal并释放 Session给下一 Run，`:2532-2534` 证明精确 `terminal_event_sequence`已经存在于 returned Run row，却未进入 wake control port。
  - 当前 `dayu/host/admission.py:230-238` 与 `dayu/host/open_host.py:311-322` 的 wake port签名只有 `session_id`；它无法在不读回、不猜测且不漂移 owner的前提下推进 exact terminal watermark。
- **影响**：cancel / wait terminal后的正常 queued B可在无 overflow、无 typed delivery error时丢失首批 transient delta；同一设计对 Engine terminal通过、对其它 terminal失败，owner-level tests与implementation review无法证明通用 A prefix / terminal / B handoff。
- **建议改法和验证点**：
  1. 在设计真源与 implementation scope中穷举“会提交 Session-visible terminal并可能释放 / promotion”的 producer，至少覆盖 Engine ingest、pre-dispatch admission cancel / terminal closeout、active-cancel watchdog、wait resolution / expiry；按实际 current-runtime可达性裁决 recovery producer，但不得只按文件名假设已覆盖。
  2. 冻结一个 owner明确的 after-commit terminal-delivery control signal，显式携带 `session_id + committed terminal event_sequence`。它必须先 marshal到 opener owner loop，同步推进 Session Event Delivery scalar与 level-trigger wake，再发对应 promotion wake；普通非 terminal promotion不能伪造或推进该 watermark。
  3. 将 `dayu/host/admission.py`、`dayu/host/waiting.py`及必要 typed port / assembly修改加入future implementation WU授权边界；不允许用 EventLog轮询、latest-row猜测、Service fallback、terminal set或通用 promotion marker补救。
  4. 在已有 Engine terminal integrated barrier之外，至少增加一组非 Engine terminal exact barrier，例如 A pre-dispatch cancel或 wait failure + queued B：断言 exact terminal sequence先推进watermark，A terminal先交付，B entry始终留在Host counted mailbox并只在Service ack/rebind后的下一次`anext()`交付；同时断言无Service B buffer、无promotion pause、无unbounded marker。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：高。

## Verified closure and prohibited regressions

1. **F02 exact-five closure**：五个members没有“至少”、catch-all、兼容别名或task-exception outcome；EOF、callback、iterator failure都不能借 delivery recovery模糊处理。
2. **stop / late commit**：slot first-commit是唯一仲裁，stop / caller cancellation先占空 slot后late terminal、callback、EOF和iterator failure均无效；helper cancellation不写用户Run cancel事实。
3. **cleanup precedence**：callback / EOF / public与non-public iterator / terminal / recovery success / slot-empty / cancellation七组double-failure acceptance均有唯一top-level、cause或diagnostic动作。
4. **diagnostic去敏**：success primary下cleanup failure只产生最多一次固定本地warning；不暴露异常类型、message、payload、identity或traceback，callback failure不改变terminal。
5. **此前F02-F04**：single transfer + counted in-flight、required admission cap与release、overflow primary-dimension算法均未被第三轮修订重开。
6. **无跨域总序**：terminal watermark只是runtime control scalar；durable `event_sequence`与transient `runtime_sequence`仍不可比较，未增加第三event/cursor或持久化barrier。
7. **无promotion背压**：watermark advance与subscription wake是owner-loop同步control操作，不等待watcher，不暂停promotion、Agent或Engine；本轮finding要求补齐producer覆盖，不要求等待consumer。
8. **无Service B buffer**：B必须留在Host唯一counted mailbox；Service只保留容量一observation-result slot。
9. **无unbounded marker**：latest terminal scalar与至多一个current fence均为O(1)，multiple terminal通过EventLog逐个重新发现。
10. **无owner drift**：EventLog拥有terminal durable truth，terminal producer只投影after-commit control signal，Session Event Delivery拥有watermark与merge，Service拥有observation/caller disposition；本轮finding正是要求所有producer接到该唯一owner，而不是复制语义。

## Open questions

没有 `needs-evidence` 型开放问题。F01遗漏由当前设计授权清单、public/internal port签名与两个可达terminal producer直接证明；应在当前design fix / re-review loop关闭，不留给implementation agent自行扩 scope。

## Residual ownership

| Residual / prerequisite | Owner | Tracking destination | Gate treatment |
|---|---|---|---|
| 本轮F01：全terminal producer的exact sequence handoff与非Engine barrier | Host terminal producer owners + Session Event Delivery / iterator merge design owner | 当前design fix / closure re-review loop | **不得defer**；implementation gate前关闭。 |
| 旧`WU-HOST-TRANSIENT-CAPACITY-01`、`WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01`总控行修订 | Phaseflow Controller / control-doc owner | 本gate后的Controller adjudication | 按用户明确边界，尚未写回不计finding，也不得用兼容代码消化。 |
| packaged items / bytes / max-subscriptions数值 | runtime composer / operator + Session Event Delivery implementation owner | future implementation WU benchmark / SLO evidence | 合法measurement residual；不得改变required字段、算法或引入fallback。 |
| logical UTF-8 budget到Python heap的safety margin、低基数metrics | Session Event Delivery implementation owner | future implementation plan、stress / benchmark evidence | 合法measurement / observability residual；不得记录payload正文或高基数identity。 |
| 跨Session Host总内存 / Host-global quota | 后续独立capacity / deployment governance owner（仅在产品SLO或威胁模型要求时） | 独立issue / design gate | 当前明确non-goal，不是本WU blocker。 |

所有已识别residual均有明确owner与tracking destination；**未归属 residual：0**。

## Final plan review conclusion

**Verdict：FAIL。**

**Material findings：1（高 1；中 0；低 0；严重 0）。**

`CODEX-FINAL-REREVIEW-F02`与此前`CODEX-REREVIEW-F02`、`F03`、`F04`均保持真实关闭；exact-five disposition、stop / late commit、cleanup precedence、sanitized diagnostic、single retention、admission和overflow contract已达到可实施程度，也没有引入跨域总序、promotion背压、Service B buffer、unbounded marker或owner drift。

`CODEX-FINAL-REREVIEW-F01`的merge算法已正确，但terminal producer覆盖与实施授权未闭合。修复所有可达terminal closeout到唯一watermark owner的exact-sequence handoff，并增加至少一个非Engine terminal A/B barrier后，才可进入implementation gate。
