# WU-SEMANTIC-OWNERSHIP-01 P3-B Terminal Final Answer / Outbox Continuity Plan

## 1. Gate、目标与成功信号

Work unit：`WU-SEMANTIC-OWNERSHIP-01 P3-B - Terminal final answer projection and Outbox continuity`。

当前 gate：plan-fix。本 artifact 只吸收 controller accepted 的 `P3-B-PF-01` 至 `P3-B-PF-05`，保持 controller rejected 裁决，不修改生产代码、测试、control doc 或其它既有 artifact，不 commit、不 push、不创建 PR，也不进入 plan re-review / implementation gate。

目标：让 Host terminal-answer continuity resolver 统一拥有 assistant final answer 文本的来源选择与 descriptor 校验。成功终态的 live `HostEvent`、Outbox materialization、Outbox public read、durable Conversation Memory、compact material 与 RunInputBuilder 必须从这个 owner 或其已验证 typed material 派生；`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST` 不得携带或被提升为 final answer。

第一性原理判断：动机成立，严重性评估正确。Outbox 是离线 terminal delivery work queue，若生产 `RUN_SUCCEEDED` 已持久化可校验的 final answer，而 Outbox 生成 `succeeded + final_answer=None`，则离线阅读路径丢失的不是装饰字段，而是 Outbox 存在的核心业务结果。下游自行跟随 descriptor 补洞会建立第二个 artifact/schema 解析 owner，违反语义同源和分层边界。

成功信号：

- `FinalAnswerData.content` 经 Host accept / terminal closeout 写入 terminal descriptor 后，descriptor-only `RUN_SUCCEEDED` 能生成非空 Outbox final answer，且 public read 的内容与 live `HostEvent` 一致。
- inline `RUN_SUCCEEDED.final_answer` 仍是明确支持的第一优先级来源；这不是旧 shape compatibility，而是当前设计真源和 resolver 已声明的两种合法 source form 之一。
- `RUN_SUCCEEDED` 在 HostEvent 与 public Outbox contract 中都必须携带非空 `HostFinalAnswerView`；nullable 字段只用于表达非成功终态的封闭联合形状，不能表达成功但回答缺失。
- descriptor 缺失、字段非法、ref/digest 不成对、descriptor 不存在、digest mismatch、artifact `content` 缺失/空白/非文本时，成功 public projection fail closed，不写半成品 Outbox row，不推进 projection checkpoint。
- Outbox resolver 失败后，ProjectionRunner 保留 failure row 与原 checkpoint；外部恢复同一 descriptor 后重试同一 event 能原子写 item 并推进 checkpoint，后续 replay 只得到 duplicate，不生成第二条 item。
- failed / cancelled 的 Outbox row 不含 final answer；lost 继续按设计被 Outbox consumer 显式 skip；HostEvent 的 failed / cancelled / lost 也不含 final answer。
- durable memory、compact material、run input 继续消费同一 resolver 产出的 typed text；纯 `dayu.host.memory` consumer 不新增 transaction、payload store 或 artifact 依赖。
- 受影响行为测试、pyright 与 `git diff --check` 通过；README 按已读取的更新约束作出实际更新/不更新裁决。

## 2. 设计与总控对齐

本 plan 对齐以下真源：

- `docs/host/design.md`：EventLog 是真源；payload descriptor/ref/digest 损坏时不得把事实当作 accepted fact；Outbox 是可由 EventLog 重建的派生 terminal delivery queue；Outbox item 与 live HostEvent 指向同一 terminal identity；terminal transaction 不同步写 Outbox；Memory / RunInputBuilder 只消费 resolver 产出的 typed answer material。其 `docs/host/design.md:3082` 还明确规定 terminal answer continuity resolver 可以从已提交 `RUN_SUCCEEDED` 的 inline `final_answer` 或 digest-checked terminal artifact 顶层 `content` 读取回答文本，因此 inline source 是 design-approved continuity source，不是旧 shape 兼容代码，也不要求当前 production closeout 同时生产两种 shape。
- `docs/engine/design.md`：Engine 只产生单次 run 的 `FinalAnswerData` / `EngineEvent`，不拥有 Host 持久化、Outbox、memory、read API 或 terminal delivery。
- `docs/host/issues-implementation-control.md`：P3-A 已完成，当前 next gate 是 P3-B plan；slice 必须按语义闭环、依赖和失败风险切分，不能按文件机械拆分。
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`：P3-B owner 是 Host terminal answer continuity resolver，accepted scope 是 descriptor-aware Outbox、统一 inline-only reader、传播测试。
- `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-controller-adjudication.md`：plan-fix 只修 `P3-B-PF-01` 至 `P3-B-PF-05`；current-code invariant gap 不重复当作 plan gap，metadata 继续从 canonical `RUN_SUCCEEDED` 派生，inline source 保留，`terminal_payload.py` 不因信息性建议被强制修改，slice 保持 1 个。

当前设计真源足够具体，不需要先修改 design document。计划不改变 EngineEvent、Host terminal EventLog schema、terminal identity、Run / Attempt 状态机或 Outbox terminal event set。

## 3. Source findings 第一性原理核验与裁决

### 3.1 Finding 01：accepted

`docs/reviews/repo-review-20260710-092911.md` 的 Finding 01 当前仍成立。

直接生产证据：

- Engine-origin 事实产生点是 `dayu/host/engine_ingest.py:4885-4931` 的 `_final_answer_plan`：它从 `FinalAnswerData` 生成成功 terminal plan，把回答写入 terminal payload 顶层 `content`，并拒绝空白成功 content。
- Engine-origin closeout 是 `dayu/host/engine_ingest.py:1184-1283` 的 `_close_terminal`：`1230-1235` 先调用 `_write_terminal_payload`，`1236-1267` 再把 descriptor 的精确 `payload_ref` / `payload_digest` 与 canonical metadata 交给 `terminal_closeout_in_transaction`。对应 SQLite payload writer 是 `dayu/host/engine_ingest.py:3533-3573` 的 `_write_terminal_payload`。
- Host-lifecycle closeout 是 `dayu/host/engine_ingest.py:1285-1372` 的 `_close_host_lifecycle_terminal`：`1318-1322` 写 Host lifecycle terminal payload，`1323-1356` 把 descriptor pair 交给同一个 durable closeout。它证明 Engine-origin 与 Host-lifecycle 都汇入同一 Host terminal closeout owner；成功 final answer 只来自前者，不能从 failed/lost lifecycle diagnostic 提升。
- 最终 durable canonical `RUN_*` payload builder 是 `dayu/host/durable/run_transition.py:4551-4584` 的 `_run_terminal_payload`：`4569-4576` 固定持久化 `terminal_summary_ref` / `terminal_summary_digest`，`4579-4583` 仅在 succeeded 时追加 `finish_reason` / `filtered` / `degraded`，不写 inline `final_answer`。当前 production `RUN_SUCCEEDED` 因而是 descriptor-only；这不否定 `docs/host/design.md:3082` 允许 inline `final_answer` 作为另一种 continuity source，也不能据此删除 inline resolver policy。
- `dayu/host/outbox.py:228-287,346-379` 当前构造 Outbox row 时没有 transaction 参数，`_final_answer_json` 只读 inline `final_answer`；缺失即返回 `None`，因此无法读取生产 descriptor。
- `dayu/host/api.py:3149-3166` 当前只禁止 succeeded item 携带 error/cancel，没有要求 succeeded item 的 `final_answer` 必填。
- `dayu/host/read_api.py:805-864` 从 `final_answer_json` 还原 public item；row 为 `None` 时会构造 succeeded + `final_answer=None`，当前 public dataclass 允许该非法组合。

根因是 Outbox projection 绕过 terminal-answer owner，并非 read API 展示层漏格式化。修复必须落在 resolver / Outbox projection 及其 durable/public invariant，不能让 Service/UI 自行读 descriptor。

### 3.2 DS-2：accepted with current-code scope correction

`docs/reviews/2026-07-10-semantic-ownership-drift-review.md` 的 DS-2 动机成立，但“仍有 4+ 条彼此独立路径”已部分过时：

- `dayu/host/durable/memory.py:393-400` 已在 projection transaction 内调用 `assistant_final_answer_continuity_text(..., STRICT_NON_EMPTY)`，把结果作为 typed material 交给纯 memory consumer。
- `dayu/host/compact_material.py:2213-2219` 已调用同一 descriptor-aware resolver。
- `dayu/host/run_input.py:3220-3240` 已调用同一 resolver，为 inline repair / RunInputBuilder 提供 typed material。
- `dayu/host/memory.py:1650-1657` 的 lenient inline fallback 只在 typed material 缺失时运行，且该纯函数 consumer 没有 transaction / artifact 能力；把它改为自己跟随 descriptor 会造成反向耦合，不是正确收束。

当前仍成立的漂移是：

- `dayu/host/outbox.py` 仍有 inline-only final answer reader。
- `dayu/host/read_api.py:903-954,1609-1671` 仍独立读取 terminal descriptor、SQLite payload 和顶层字段，没有调用 terminal-answer resolver。

因此 P3-B 应收敛 Outbox 与 HostEvent/read API，并明确 required/optional、strict/lenient policy；不重写已经正确的 typed material 路径，也不让纯 memory consumer 依赖 durable transaction。

### 3.3 DS-4：accepted with scope correction

`docs/reviews/2026-07-10-semantic-ownership-drift-review.md` 的 DS-4 当前仍成立，但不能机械删除 Outbox 对全部 terminal payload 字段的读取。Outbox 拥有自己的 queue row、identity、error/cancel projection 和 result/summary refs，读取这些字段是其 projection 职责。真正越界的是 Outbox 自行决定 final answer 来源并把 descriptor-backed success 当作 answer 缺失。

P3-B 只删除 Outbox 的 `_PAYLOAD_FIELD_FINAL_ANSWER` / inline-only answer parsing ownership，让 Outbox 在现有 projection transaction 内调用 terminal-answer resolver；result refs、summary refs、terminal diagnostics 与 stable idempotency identity 仍由 Outbox owner 持有。

### 3.4 Controller P3-B：accepted

Round 2 controller 对 P3-B 的 owner 和 accepted scope 与当前代码一致。其“所有消费者调用同一 resolver/helper”应按 typed boundary 理解：需要读取 EventLog/descriptor 的 Host projection 调 resolver；已经收到 `assistant_final_answer_text` 的纯 memory consumer 消费 typed value，不反向打开 descriptor；Outbox public read 消费已原子 materialize 的 `final_answer_json`，不二次打开 artifact。

裁决汇总：accepted 4；rejected 0；deferred 0；needs-more-evidence 0。

## 4. 语义 owner boundary

| 语义事实 | 首次产生 | 校验 owner | 持久化 / 真源 | 投影 / 消费 owner | P3-B 修复边界 |
|---|---|---|---|---|---|
| assistant final answer 原始文本 | Engine `FinalAnswerData.content` | Host `engine_ingest._final_answer_plan` 拒绝空白成功内容 | Host terminal payload descriptor 顶层 `content`；合法 inline event 可使用 `RUN_SUCCEEDED.final_answer` | Host terminal-answer resolver 选择 inline 或 descriptor source | 扩展现有 resolver 的 required contract；不改 Engine contract |
| terminal descriptor 完整性 | Host terminal closeout | descriptor pair、descriptor kind、SQLite row、digest、JSON object 校验 | payload descriptor + SQLite payload row；`RUN_SUCCEEDED` 保存 ref/digest | resolver 只通过 `payload_resolution.sqlite_payload_object` 读取 | Outbox/read API 不再自建 descriptor parser |
| final answer source precedence | Host terminal-answer resolver | inline 非空文本优先；只有 inline 缺失/空白才读取 descriptor | 不新增持久化字段 | HostEvent、Outbox、memory/compact/run input | 只在 `_terminal_answer.py` 定义一次 |
| final answer view metadata | Engine final answer plan，Host closeout 接受 | `RUN_SUCCEEDED` canonical payload 的 `filtered` / `degraded` 必须为 bool，`finish_reason` 可选非空文本 | `RUN_SUCCEEDED` payload；terminal descriptor 同源保留一份完整 payload | HostEvent / Outbox row builder | 内容由 resolver；metadata 从 canonical `RUN_SUCCEEDED` payload 读取，避免 Outbox 再解析 artifact shape |
| Outbox queue item | committed public terminal canonical fact | Outbox projection + durable row validator | `host_outbox_terminal_items` 派生表 | Outbox read/drain API | succeeded row 必须 materialize final answer；非成功不得有 final answer |
| public terminal answer invariant | Host public API dataclasses | `HostFinalAnswerView` / `HostEvent` / `OutboxTerminalItem.__post_init__` | 无独立 truth；是 read projection contract | Service/UI/channel adapter | succeeded final answer 必填且 content 非空；failed/cancelled/lost 禁止 final answer |
| LLM-facing continuity material | resolver 输出的 typed text | strict descriptor integrity；纯 consumer 只做 bounded memory policy | memory snapshot / compact material / runner input projection 均为派生物 | durable memory、compact material、RunInputBuilder、纯 memory builder | 保持当前单向 typed data flow，不新增 artifact 依赖 |

修复落点位于事实投影 owner 和直接上游校验，不修改下游 UI/CLI，不在测试 fixture 中伪造 answer，不通过 nullable 或 fallback display 文本掩盖 contract violation。

## 5. Resolver API 与 policy 决策

### 5.1 保留一个 source-selection owner

`dayu/host/_terminal_answer.py` 继续是 descriptor-aware source-selection owner。保留：

```python
assistant_final_answer_continuity_text(
    transaction: HostTransaction,
    run_payload: Mapping[str, JsonValue],
    *,
    text_policy: PayloadTextReadPolicy,
) -> str | None
```

新增有实际语义的 required contract，建议精确命名：

```python
required_assistant_final_answer_continuity_text(
    transaction: HostTransaction,
    run_payload: Mapping[str, JsonValue],
) -> str
```

required helper 必须调用现有 resolver + `STRICT_NON_EMPTY`，当没有可显示文本时抛 `HostDurableError`。它不是 compatibility wrapper：它把“成功 public terminal 必须有回答”这一 public/queue invariant 固化为非 nullable 返回类型，供 HostEvent 与 Outbox 共用。

禁止新增 `HostFinalAnswerView` god builder、resolver registry、callback/factory/profile，也禁止让 Outbox 接受 payload loader callback。直接传 `HostTransaction` 与 payload 是当前最小、类型严格的接口。

### 5.2 inline 与 descriptor 的业务含义

固定顺序：

1. `RUN_SUCCEEDED.final_answer` 存在且为非空文本时直接返回；不读取 descriptor。inline precedence 测试必须证明即使 payload 同时带另一个 descriptor，inline 仍获胜。
2. inline 缺失或空白时，`terminal_summary_ref` 与 `terminal_summary_digest` 必须同时存在或同时缺失。
3. descriptor pair 存在时，通过 `sqlite_payload_object(...)` 校验 descriptor、kind、digest、SQLite row 与 JSON object，只读取顶层 `content`。
4. 裸 `RUN_SUCCEEDED.content`、`summary_text`、nested `summary.content`、失败 message、cancel reason、lost diagnostic 均不是 answer source。

inline source 是当前明确契约，不是旧库兼容；不得引入其它 alias、旧字段 fallback 或兼容 shape。

### 5.3 strict / lenient policy 的业务边界

- `STRICT_NON_EMPTY`：用于读取 committed canonical fact 的 durable/public projection。字段存在但类型非法、descriptor pair 非法、descriptor 不存在、kind/digest/SQLite row/JSON 非法时抛 `HostDurableError`；文本缺失或空白返回“没有 candidate”，由 required public boundary 抛错，optional material boundary按设计省略该 material。
- `LENIENT_NON_EMPTY`：只用于纯 Conversation Memory consumer 在没有 upstream typed material 时读取 inline `final_answer`；非文本、缺失或空白按无 material 处理。它不授权该纯 consumer 跟随 descriptor，也不允许 Outbox/HostEvent 用 lenient policy 吞掉生产 contract violation。

descriptor ref/digest 单边存在属于结构损坏，不是“没有 fallback”；owner 应 fail closed。两者都缺失时 optional resolver 可以返回 `None`，但 required HostEvent/Outbox boundary 必须抛错。

### 5.4 已有 typed material 路径保持单向

- `dayu.host.durable.memory`、`dayu.host.compact_material`、`dayu.host.run_input` 继续直接调用 optional resolver 的 strict policy；不改它们的 transaction ownership。
- `dayu.host.memory` 继续优先消费 `MemoryProjectionEvent.assistant_final_answer_text`，只在该 typed field 缺失时做 descriptor-blind lenient inline fallback。
- 不让 `memory.py` import `durable.transaction`、`payload_resolution`、`_terminal_answer` 的 transaction API；不让 memory snapshot 反向成为 terminal answer truth。
- P3-B 不修改 compact payload/evidence contract，不把 answer 自动升级为 evidence-backed fact、answer anchor 或 session summary。

### 5.5 Descriptor pair 与错误 taxonomy

owner check 固定在 `dayu/host/_terminal_answer.py`，不下沉给 Outbox/read API，也不要求修改 `terminal_payload.py`。optional 与 required public helper 必须共用一个模块级私有 resolution core，确保 source precedence、descriptor 读取和错误分类只执行一次；不得由 required helper 再读一遍 descriptor，也不得让两个 public helper各自重建 pair 规则。

当 inline `final_answer` 没有产生 candidate 时，resolution core 按下列封闭 taxonomy 处理；descriptor 字段缺失、值为 `None` 或纯空白都归一为 absent，字段存在但非文本则立即抛出点名字段的 `HostDurableError`：

| case | owner check location | required/public 结果与稳定诊断语义 |
|---|---|---|
| `terminal_summary_ref` 与 `terminal_summary_digest` 都 absent | `_terminal_answer.py` pair check | optional 返回 `None`；required 抛 `HostDurableError`，消息必须区分“inline answer 与 descriptor pair 均缺失” |
| 仅一边 present | `_terminal_answer.py` pair check | 抛 `HostDurableError`，消息必须点明 ref/digest 必须成对，不能降级为 no candidate |
| descriptor row missing | `payload_resolution.sqlite_payload_object` 的 `read_payload_descriptor` check（当前 `dayu/host/payload_resolution.py:175-177`） | 保留 `terminal payload payload descriptor is missing` 的可行动诊断 |
| descriptor digest mismatch | `sqlite_payload_object`（当前 `180-181`） | 保留 `terminal payload payload digest mismatch` |
| descriptor 指向的 SQLite row missing | `sqlite_payload_object`（当前 `184-193`） | 保留 `terminal payload sqlite payload row is missing` |
| `payload_json` 非文本或 JSON 语法非法 | `sqlite_payload_object` / `_json_object`（当前 `194-212`） | `HostDurableError` 消息必须含 `JSON is invalid` |
| JSON top-level 非 object | `_json_object`（当前 `213-215`） | `HostDurableError` 消息必须含 `JSON must be object` |
| object 缺少顶层 `content` | `_terminal_answer.py` private resolution core | optional 返回 `None`；required 抛 `HostDurableError`，消息必须明确 `content is missing` |
| 顶层 `content` 是空串或纯空白 | `_terminal_answer.py` private resolution core | optional 返回 `None`；required 抛 `HostDurableError`，消息必须明确 `content is blank` |
| 顶层 `content` 非文本 | strict text check，由 `_terminal_answer.py` resolution core 复用现有 terminal payload text helper | 抛 `HostDurableError`，消息必须点名 `content` 与 text 类型要求 |

projection failure 验收不新增 public error enum。`ProjectionRunner._record_failure` 继续把异常类写入 `last_error_code`、异常文本写入 `last_error_message`；上述所有错误的断言必须为 `last_error_code == "HostDurableError"`，并分别断言 `last_error_message` 含有可区分的稳定 cause fragment。failure row 是 operator-facing internal diagnostic，不进入 assistant answer、memory、compact 或其它 LLM-facing material。

## 6. Transaction、projection 与 public read 决策

### 6.1 HostEvent/read API

`read_api._succeeded_host_event(transaction, row)` 必须：

- 解析 `RUN_SUCCEEDED` canonical payload；
- 调用 `required_assistant_final_answer_continuity_text(transaction, payload)` 取得唯一 content；
- 从同一 canonical payload 读取 `filtered`、`degraded`、`finish_reason`，构造 `HostFinalAnswerView`；
- 删除只为成功 HostEvent 服务的 `_terminal_payload_object` / `_sqlite_payload_object` 第二套 descriptor/SQLite parser 及无用 imports。

`read_api._final_answer_from_outbox_json` 不回读 terminal descriptor。Outbox row 已是 projection transaction 内 materialize 的 typed answer；public read 只校验 JSON shape并构造 `HostFinalAnswerView`。损坏 row 继续 fail closed。

### 6.2 Outbox projection

将内部 row builder 改为显式 transaction-scoped 接口：

```python
build_outbox_terminal_item_row(
    transaction: HostTransaction,
    event: ProjectionEventView,
) -> OutboxTerminalItemRow
```

`OutboxTerminalProjectionConsumer.apply_event` 把 ProjectionRunner 提供的同一 `HostTransaction` 传入 builder。`_final_answer_json` 同样接收 transaction，且：

- 非 succeeded 立即返回 `None`，不检查、不读取、也不提升 payload 中伪造的 `final_answer` / `content` / terminal descriptor content；
- succeeded 调用 required resolver 取得 content；
- `filtered` / `degraded` / `finish_reason` 从 canonical `RUN_SUCCEEDED` payload 读取；
- 生成 canonical JSON 后再构造 row。

Outbox 仍负责 result/summary ref pair、identity、error/cancel projection。idempotency key 继续只由 terminal event identity、run id 与 refs/digests 派生，不引入 answer text，避免文本内容影响 replay identity。

### 6.3 原子性、cursor 与 retry

不修改通用 `ProjectionRunner`。原子性不是 implementation-time 假设，当前代码证据如下：

- `dayu/host/projection.py:464-471` 用一次 `HostTransactionRunner.run_write(...)` 调用 `_process_next_event`。
- `dayu/host/projection.py:626-644` 在该 transaction 内依次构造 event view、调用 `consumer.apply_event(transaction, event)`、推进 checkpoint并清除旧 failure。
- `dayu/host/outbox.py:147-168` 的 `OutboxTerminalProjectionConsumer.apply_event` 使用传入的同一 `HostTransaction` 构造 row，并调用 `insert_outbox_terminal_item_if_absent(transaction, row)`；后者在 `dayu/host/durable/outbox.py:243-305` 内校验、判重、insert和读回，没有开启第二笔 transaction。
- `dayu/host/durable/transaction.py:288-360` 的 `run_write` 在 `BEGIN IMMEDIATE` 后运行整个 operation，只在 operation 返回后 `COMMIT`；任何 SQLite、`HostDurableError` 或其它异常都在透传前 rollback。因此 resolver、row builder/validator、Outbox insert 或 checkpoint advance 任一步抛错，item 与 checkpoint 一起回滚。
- `dayu/host/projection.py:472-489` 只在上述 `run_write` 已异常退出后调用 `_record_failure`；`653-685` 的 `_record_failure` 再开启一笔独立 `run_write` 写 failure row。因此 failure 诊断不会被 apply transaction 的 rollback 撤销，也不会与半成品 item/checkpoint共同提交。

implementation 开始时必须先重新核对这些符号仍保持同一调用关系；若 consumer apply/Outbox insert/checkpoint 不再共享同一个 `HostTransaction`，或 failure row 不是在 apply rollback 后的独立 transaction 写入，立即触发 stop condition，不得继续实现 P3-B 或用补偿写掩盖非原子 runner。

目标事务流程：

```text
read next RUN_* terminal event
  -> resolve/validate final answer in same transaction
  -> build + validate Outbox row
  -> insert item if absent
  -> advance checkpoint
  -> commit
```

resolver、row validation 或 insert 任一步失败：

```text
rollback whole apply transaction
  -> no Outbox item
  -> checkpoint unchanged
  -> ProjectionRunner records failure row in a separate transaction
  -> catch-up stops at failed event
```

外部恢复缺失 descriptor 后重试时，同一 event 再次执行完整流程；成功后 item + checkpoint 同事务提交并清除 failure row。checkpoint 被重置或 event 被 replay 时，stable idempotency key 使 insert 返回 duplicate，item 数保持 1，checkpoint仍可推进。

禁止在 resolver 失败时先写 `final_answer_json=NULL`、推进 cursor 后再“后台补 answer”；这会制造不可原子恢复的半成品状态。

### 6.4 缺失 descriptor row 的测试恢复机制

retry 测试固定验证“canonical `RUN_SUCCEEDED` 仍持有原 ref/digest，但对应 descriptor row 暂时缺失”的可恢复 projection failure。仓库没有、也不应为此新增 production repair API：`dayu/host/durable/payload.py:243-285` 的 typed `write_sqlite_payload` 会同时插入 SQLite payload row 与 descriptor；在 SQLite payload row 仍存在、只有 descriptor 缺失时，重调该 writer 会撞上既有 `payload_id`，不能表达 descriptor-only restore。

测试必须使用仓库已有的 test-only durable mutation 模式（参见 `tests/host/test_storage_maintenance.py:837-857`）并按以下步骤执行：

1. 先用 production closeout 生成 descriptor-only `RUN_SUCCEEDED`；通过 `TABLE_PAYLOAD_DESCRIPTORS` 读取并保存该 descriptor row 的全部 durable columns，确认 row 的 `payload_ref` / `payload_digest` 等于 canonical event 中的 pair，且 `sqlite_payload_id` 指向仍存在的 `TABLE_SQLITE_PAYLOADS` row。
2. 在测试自己的 `HostTransactionRunner.run_write` 中只删除这条 descriptor row，不修改 canonical event payload、SQLite payload row、ref 或 digest。第一次 Outbox catch-up 必须得到 1 个 failure；item 不存在、checkpoint 保持在该 event 之前，failure 指向该 event，`last_error_code == "HostDurableError"` 且消息包含 `descriptor is missing`。
3. 在另一笔 test-only `run_write` 中用保存的全部 columns 原样 `INSERT` 回 `TABLE_PAYLOAD_DESCRIPTORS`。这是测试夹具的 durable corruption/restore 操作，不进入 production module；恢复后必须重新读取 descriptor 并断言 `payload_ref`、`payload_digest`、`sqlite_payload_id` 与删除前完全相同，SQLite payload JSON 未改写。
4. 对同一 checkpoint/event 重试 catch-up：必须原子插入一个 item、推进 checkpoint、清除 failure row，且 item 的 `terminal_summary_ref` / `terminal_summary_digest` 仍等于原 pair。
5. 在新的 `run_write` 中把同一个 typed `ProjectionEventView` 再交给 `OutboxTerminalProjectionConsumer.apply_event`，断言返回 `ProjectionApplyStatus.DUPLICATE`，并断言按 terminal event id 与 item id 计数都仍为 1。不得通过创建新 ref/digest、删除既有 item或新增 repair endpoint 来制造“恢复成功”。

### 6.5 Production smoke path 证据

实际 smoke support 已存在：`tests/host/public_smoke_support.py:242-292` 的 `FinalAnswerHandle.events()` 产出带 `FinalAnswerData(content=...)` 的真实 `EngineEventType.FINAL_ANSWER`；`314-371` 的 `FinalAnswerWorker` / `FinalAnswerWorkerFactory` 经 `open_host` 的 production worker、ingest、terminal closeout 路径运行。`tests/host/test_public_offline_outbox_smoke.py:28-97`、`100-155` 已使用该 factory，但当前只断言 terminal identity/ref 与离线读写行为，尚未证明 final answer content 和 descriptor-only canonical shape。

P3-B 必须扩展该 production smoke，而不是另造 inline-only `ProjectionEventView` fixture：

- 从 SQLite `TABLE_EVENT_LOG` 按本次 `run_id` 与 `event_type == "RUN_SUCCEEDED"` 读取 canonical `payload_json`，断言 `final_answer` key 不存在，`terminal_summary_ref` / `terminal_summary_digest` 均为非空文本；再读取 descriptor 并断言其 digest 与 canonical digest 相等。该断言是 descriptor-only smoke 的门槛，任何只手填 inline `final_answer` 的 fixture 都不能满足。
- 同一次 `FinalAnswerWorkerFactory` run 同时捕获 live succeeded `HostEvent`、调用 public Outbox read 与 drain；断言三者 `final_answer` 均非 `None`，content 都严格等于 `final:1:<run_id>`，metadata 等于 factory 产生的 `filtered=False`、`degraded=False`、`finish_reason=stop`。
- 断言 live event、read item、drained item 的 `terminal_event_id` / `dedupe_key` 指向同一个 canonical terminal identity，read/drain 不新增 EventLog row。

若该 factory 不再产生 `EngineEvent(FINAL_ANSWER)`、smoke 无法观察 descriptor-only canonical `RUN_SUCCEEDED`，或测试只能靠 inline fixture 通过，则触发 stop condition；不得把 inline-only unit fixture冒充 production smoke。

## 7. Contract / schema / public invariant 变化

### 7.1 Public contract tightening

- `HostFinalAnswerView.content` 必须是非空、非纯空白文本。
- `HostEvent(kind=SUCCEEDED)` 继续要求 `final_answer`，failed/cancelled/lost 继续禁止。
- `OutboxTerminalItem(terminal_status=SUCCEEDED)` 升级为必须有 `final_answer`，且不能携带 error/cancel。
- failed/cancelled/lost Outbox item shape 不得携带 final answer；错误文案应列全三类，不能继续写成只包含 failed/cancelled。

字段类型仍为 `HostFinalAnswerView | None`，因为 dataclass 表达 succeeded/failed/cancelled 的封闭联合；conditional invariant 消除 succeeded + `None`，不引入宽类型或 optional bag。

### 7.2 Durable Outbox invariant

`dayu.host.durable.outbox._validate_item_row` 必须在写边界校验：

- `terminal_status == "succeeded"` 时 `final_answer_json` 必填；
- failed/cancelled 时 `final_answer_json` 必须为 `None`；
- `_item_row_from_host_row` 构造 row 后复用同一 validator，使 raw DB 损坏也在 durable read boundary fail closed。

测试 fixture 必须迁移为合法 row，不能为了保住 succeeded + `None` 在生产代码加例外。

### 7.3 Schema 决策

不修改 terminal EventLog schema，不新增字段，不改 Outbox DDL/version，不做 migration。`final_answer_json` 列必须保持 SQL nullable，因为 failed/cancelled item 合法为 NULL；本 WU 通过 producer、durable row validator 与 public dataclass 的条件不变量保证 succeeded 必填。

若 implementation 证明只有新增 DDL conditional CHECK 或 schema migration 才能保证正确性，触发 stop condition，先回设计真源裁决；不得在 P3-B 顺手进入 P3-J。

## 8. Failure matrix

| terminal/source case | Resolver / projection decision | Outbox row | checkpoint/failure |
|---|---|---|---|
| succeeded + non-empty inline answer | inline wins；descriptor 不作为 answer fallback读取 | non-empty final answer | item + checkpoint commit |
| succeeded + inline + valid descriptor with different content | inline wins | inline content | item + checkpoint commit |
| succeeded + no inline + valid descriptor content | digest-checked descriptor fallback | descriptor content | item + checkpoint commit |
| succeeded + no inline + ref/digest 都缺失 | optional resolver无 candidate；required boundary 抛错 | no row | checkpoint不动，failure记录 |
| succeeded + no inline + 单边 ref/digest | malformed descriptor，抛错 | no row | checkpoint不动，failure记录 |
| succeeded + no inline + descriptor row missing | `HostDurableError`：descriptor is missing | no row | checkpoint不动，failure记录含可行动 cause |
| succeeded + no inline + descriptor 指向的 SQLite row missing | `HostDurableError`：sqlite payload row is missing | no row | checkpoint不动，failure记录含可行动 cause |
| succeeded + no inline + digest mismatch | durable integrity error | no row | checkpoint不动，failure记录 |
| succeeded + descriptor JSON 非法 | `HostDurableError`：JSON is invalid | no row | checkpoint不动，failure记录含可行动 cause |
| succeeded + descriptor JSON top-level 非 object | `HostDurableError`：JSON must be object | no row | checkpoint不动，failure记录含可行动 cause |
| succeeded + descriptor content 缺失 | optional 无 candidate；required 明确 content missing | no row | checkpoint不动，failure记录含可行动 cause |
| succeeded + descriptor content 空串/纯空白 | optional 无 candidate；required 明确 content blank | no row | checkpoint不动，failure记录含可行动 cause |
| succeeded + descriptor content 非文本 | strict text error | no row | checkpoint不动，failure记录 |
| succeeded + filtered/degraded 缺失或非 bool | canonical metadata contract error | no row | checkpoint不动，failure记录 |
| failed + payload伪造 answer/content/descriptor | 不调用 answer resolver | `final_answer_json=None` | failed item 正常提交 |
| cancelled + payload伪造 answer/content/descriptor | 不调用 answer resolver | `final_answer_json=None` | cancelled item 正常提交 |
| lost + payload伪造 answer/content/descriptor | Outbox consumer显式 skip；HostEvent final answer 为 None | no public Outbox row | skipped checkpoint可推进 |

inline precedence 不等于容忍 canonical ref pair 结构损坏：Outbox 仍需为自身 summary ref columns 校验 ref/digest 成对。若 inline 存在但 summary ref pair 单边存在，Outbox 应按 malformed canonical payload fail closed。

## 9. Propagation audit

实现前后的目标路径固定为：

```text
Engine FinalAnswerData.content
  -> engine_ingest._final_answer_plan rejects blank success
  -> _write_terminal_payload writes {content, finish_reason, filtered, degraded}
  -> payload descriptor + SQLite payload row
  -> terminal_closeout_in_transaction
  -> RUN_SUCCEEDED canonical payload
       terminal_summary_ref / terminal_summary_digest
       finish_reason / filtered / degraded
  -> Host terminal-answer continuity resolver
       inline final_answer first
       otherwise digest-checked descriptor top-level content
```

从同一个 resolver 分叉：

```text
required strict branch
  -> read_api._succeeded_host_event
  -> HostFinalAnswerView
  -> live HostEvent / watch public read

required strict branch inside Outbox projection transaction
  -> final_answer_json
  -> host_outbox_terminal_items row
  -> _final_answer_from_outbox_json
  -> OutboxTerminalItem.final_answer
  -> public read/drain

optional strict typed-material branch
  -> durable memory projection
  -> MemoryProjectionEvent.assistant_final_answer_text
  -> pure memory selected assistant item
  -> durable memory snapshot

optional strict typed-material branch
  -> compact material answer block
  -> LLM compact input material

optional strict typed-material branch
  -> RunInputBuilder inline repair / selected recent continuity
  -> LLM-facing run input
```

负向传播审计：

```text
RUN_FAILED / RUN_CANCELLED / RUN_LOST
  -> never call/promote terminal answer resolver as final answer
  -> HostEvent.final_answer = None
  -> failed/cancelled Outbox final_answer_json = None
  -> lost Outbox skip
  -> no assistant answer memory/compact/run-input producer
```

验收时必须逐项记录以下一致性：内容等值、terminal identity 不变、descriptor/digest 不泄漏到 LLM-facing text、Outbox failure 不改变 Run truth、memory/compact/run input 没有新增独立 parser。

## 10. Implementation slice

### S1. Terminal answer resolver and Outbox/public propagation closure

Objective：一次完成 resolver required contract、HostEvent/Outbox 同源、durable/public invariant、projection retry/idempotency与完整行为验证，交付可独立审查的语义闭环。

为什么只需 1 个 slice：修改量围绕同一个 terminal-answer projection contract。若拆成 resolver contract、Outbox materialization、public invariant三个 slice，任一中间提交都会暂时保留“resolver 已有但 Outbox 仍丢 answer”或“public succeeded 必填但 producer 仍写 NULL”的 contract-only 半成品；其失败/回滚风险也共享同一 ProjectionRunner transaction。一个 implementation agent 和 reviewer 可在单次上下文中稳定承载该范围，额外 gate 成本没有独立风险收益。

Prerequisites / dependencies：

- P3-A 已完成且 `HostRunEventType`、public Outbox terminal event set、ProjectionRunner transaction semantics 稳定。
- 不依赖 P3-C / P3-J。
- implementation 开始前重新确认工作树只包含当前 WU intended changes和用户拥有的无关 `docs/cli_ci.md`，不得触碰后者。

Allowed production files/modules：

- `dayu/host/_terminal_answer.py`
- `dayu/host/terminal_payload.py`，仅用于澄清 `PayloadTextReadPolicy` docstring/语义；若无需修改则不触碰
- `dayu/host/read_api.py`
- `dayu/host/outbox.py`
- `dayu/host/api.py`
- `dayu/host/durable/outbox.py`

Allowed test files/modules：

- `tests/host/test_terminal_payload.py`
- `tests/host/test_read_api_terminal_policy.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_outbox_durable.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_public_outbox_api.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_engine_ingest_mapping.py`，仅在 production descriptor propagation assertion 有缺口时修改
- `tests/host/test_memory_projection.py`，仅在现有 descriptor-only typed material assertion 有缺口时修改
- `tests/host/test_compact_material.py`，仅在现有 descriptor-backed answer material assertion 有缺口时修改
- `tests/host/test_run_input_builder.py`，仅在现有 descriptor-backed run-input continuity assertion 有缺口时修改

Allowed docs：

- `dayu/host/README.md`
- `tests/README.md`，仅在实际测试职责/命令说明需要同步时修改

Exact allowed changes：

1. 在 `_terminal_answer.py` 新增 required non-nullable helper；required/optional 共用一个模块级私有 resolution core。该 core 在调用 `sqlite_payload_object` 前区分 descriptor pair 双缺失与单边损坏，并把 descriptor/JSON/content failure 映射到 §5.5 的封闭 taxonomy；不在 Outbox/read API 重建 parser。更新中文 docstring说明 required/optional、strict/lenient和消费者边界。
2. `read_api._succeeded_host_event` 改用 required resolver，metadata 从 canonical run payload读取；删除 read API 私有 terminal descriptor/SQLite parser和无用 imports，不保留透传 facade。
3. `outbox.build_outbox_terminal_item_row` 增加显式 `HostTransaction` 参数；consumer、tests和所有调用点迁移新签名，不提供旧签名 overload/wrapper。
4. `_final_answer_json` 对 succeeded 调 required resolver，对非 succeeded 始终返回 `None`；不再定义/读取 Outbox 私有 inline `final_answer` source。
5. `HostFinalAnswerView` 拒绝空白 content；`OutboxTerminalItem` 条件不变量要求 succeeded final answer 必填并拒绝 failed/cancelled/lost final answer。
6. durable Outbox row write/read validation执行同一 succeeded/non-success final answer组合校验；更新测试 fixture为合法数据，不加 compatibility branch。
7. 保持 Outbox identity formula、terminal event set、lost skip、read/drain pagination、drain state、EventLog和Run/Attempt state完全不变。
8. 完成下列行为测试；不得使用仅检查私有 helper 源码字符串的测试代替行为断言。

Behavior tests / expected assertions：

- resolver：inline success、descriptor-only success、inline precedence；双缺失、ref-only、digest-only、descriptor row missing、SQLite row missing、digest mismatch、invalid JSON、top-level non-object、content missing、content blank、content non-text 的 strict/required结果；每个 failure 都断言 `HostDurableError` 与 §5.5 对应 cause fragment。lenient只对允许省略的 inline/content missing/blank 返回 `None`，不能吞掉 pair、descriptor、digest或JSON结构损坏。
- HostEvent/read API：inline success和descriptor-only success都构造非空 `HostFinalAnswerView`；descriptor malformed/missing/digest mismatch/empty/non-text fail closed；failed/cancelled/lost payload即使伪造 answer字段也始终 `final_answer is None`。
- Outbox projection：descriptor-only production shape生成 `final_answer_json`；inline生成；inline precedence；metadata完整；failed/cancelled为 NULL；lost skip。
- Outbox failure atomicity：按 §6.4 删除/原样恢复同一 descriptor row；resolver失败后 item row不存在、checkpoint不越过 event、failure row指向该 event 且 cause 可行动；恢复后重跑，item与checkpoint提交、failure清除；同一 typed event 再次 apply 返回 `DUPLICATE` 且 item 数仍为1。不得虚构 `PayloadStore` repair API。
- ProjectionRunner transaction regression：Outbox 专项测试必须与现有 `tests/host/test_projection_runner.py:430-467` 的通用 rollback contract 对齐，证明 resolver failure rollback item/checkpoint、failure 独立持久化；若代码核对不满足 §6.3，测试前即 stop。
- durable/public invariant：succeeded + `None` 在 row write和`OutboxTerminalItem` construction都被拒绝；non-success + final answer被拒绝；空白`HostFinalAnswerView.content`被拒绝；durable raw row损坏在read boundary被拒绝。
- production public smoke：使用 §6.5 已核实的 `FinalAnswerWorkerFactory` 真实 Host ingest/terminal descriptor路径；先断言 canonical `RUN_SUCCEEDED` 无 `final_answer` key且有可解析 descriptor pair，再断言 live succeeded `HostEvent.final_answer.content` 与 public Outbox read/drain `item.final_answer.content` 都等于 `final:1:<run_id>`，且 terminal event id/dedupe key一致。inline-only fixture不能计入该 smoke。
- propagation regression：现有 `test_engine_ingest_mapping.py` descriptor content/ref/digest断言、`test_memory_projection.py` typed descriptor answer、`test_compact_material.py` answer material、`test_run_input_builder.py` descriptor-backed continuity全部通过；这些测试验证可观察数据，不增加 source-string断言。

Validation commands：

```bash
source .venv/bin/activate && pytest \
  tests/host/test_terminal_payload.py \
  tests/host/test_read_api_terminal_policy.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py \
  tests/host/test_public_open_host_options.py \
  tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py -q

source .venv/bin/activate && pytest \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py -q

source .venv/bin/activate && pyright
git diff --check
```

补充 owner/source scan 只作为 propagation audit 辅助，不是行为测试替代品：

```bash
rg "assistant_final_answer_continuity_text|required_assistant_final_answer_continuity_text|_PAYLOAD_FIELD_FINAL_ANSWER|_terminal_payload_object" dayu/host
```

预期：descriptor-aware source selection 只在 `_terminal_answer.py`；Outbox不再定义自己的 final-answer字段reader；read API不再保留 terminal descriptor/SQLite parser；durable memory、compact material、run input仍调用 owner；纯 memory只消费 typed material/lenient inline helper。

Coverage expectation：新增/修改分支必须被上述行为矩阵覆盖；对本 slice新增的 resolver和Outbox条件分支实现单文件目标 `>=80%`。不得用 `# pragma: no cover`、cast、`Any`、`object`或弱类型测试helper掩盖未覆盖/类型错误。

Completion signal：全部行为矩阵通过，public production smoke证明 live/outbox内容同源，projection failure/retry/idempotency闭环通过，pyright零新增/扩散错误，README决策完成，propagation audit每条路径有证据。

Slice stop conditions：

- 发现必须修改 terminal EventLog schema、Outbox DDL/version或执行 migration才能保证正确性。
- 发现 HostEvent/Outbox无法调用同一 resolver而不引入 import cycle、lazy import或上层 callback seam。
- 发现 production terminal descriptor不是当前 resolver支持的 SQLite payload contract，且需要新增 artifact kind/跨层协议。
- 重新核对后发现 consumer apply、Outbox insert、checkpoint advance不在同一 `HostTransaction`，或 failure row不是在 apply rollback后的独立 transaction写入。
- `FinalAnswerWorkerFactory` 不再经 production `EngineEvent(FINAL_ANSWER)` closeout产生 descriptor-only canonical `RUN_SUCCEEDED`，且现有 public smoke support 无法证明该路径。
- 修复要求改 P3-C compact/evidence payload contract、P3-J schema hardening或 UI/CLI display contract。
- 现有 public消费者有经设计真源确认的合法 succeeded + missing final answer需求；这与当前设计冲突，必须先回 design truth裁决，不能加兼容分支。

Handoff：S1完成后进入 code review；handoff必须列 changed files、行为测试/pyright/coverage结果、README决策、source scan、projection retry证据、propagation audit和remaining risks。不得自动进入P3-C。

## 11. README / docs decision

本 plan 已读取：

- `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`：只记录当前已实现且稳定的 Host开发契约，不写未来计划或测试流水账。
- `tests/README.md` 开头职责：只记录当前测试分层、运行方式与维护约定。

Implementation 触及 `dayu/host/` 和 `tests/`，开始修改前仍须重新读取两份 README的更新约束并在完成后实际判断：

- `dayu/host/README.md` 应更新。其 `Outbox terminal delivery` 当前只说明 projection lag/failure和failed diagnostic同源，未声明 succeeded item必须携带同一 resolver派生的 final answer；这是稳定 public/开发契约变化，属于该 README职责。更新只描述已实现事实，不写 WU过程。
- `tests/README.md` 预计无需更新，因为测试仍位于现有 Host projection/public smoke分层且不新增测试入口或运行方式；若实施新增独立测试层/命令职责，再按实际事实更新。
- 根 `README.md` 不更新：没有用户可见命令、入口、工作流、路径或排障方式变化。
- `dayu/README.md` 不更新：`UI -> Service -> Host -> Engine` 分层和装配边界不变。
- `docs/host/design.md` / `docs/engine/design.md` 不更新：当前设计已明确 terminal answer、Outbox、descriptor与Engine/Host边界；若实施发现需要新架构/公共事件语义，触发 stop condition而不是在本 slice扩写设计。

## 12. Non-goals、不过度设计与 residual risks

Non-goals：

- 不修改 terminal EventLog schema、event type、Run/Attempt状态机或terminal closeout identity。
- 不做 P3-C context compact payload/evidence contract。
- 不做 P3-J durable schema closed-set/DDL hardening。
- 不改 UI/CLI/Service展示、terminal watermark、channel delivery或drain语义。
- 不引入旧 shape alias、兼容旧库读取、compatibility wrapper/facade/re-export。
- 不重构完整 read API、Outbox identity、payload storage framework或通用 projection runner。
- 不把 final answer改写成memory fact、summary、anchor或evidence。
- 不让 Outbox、memory或public read从raw EngineEvent直接派生truth。

不过度设计说明：方案只扩展已存在的 terminal-answer resolver一个 required contract，把两个越界消费者迁回owner，并在已有 durable/public validator中补条件不变量。它不新增schema、registry、通用artifact abstraction、跨层callback、第二种read model或future policy框架。一个slice完成同一事务/公共contract闭环，是当前风险下的最小可维护方案。

Residual risks：

- P3-B完成后，SQLite DDL仍没有 conditional CHECK强制 succeeded row的`final_answer_json`非NULL；producer、durable row validator和public validator已覆盖正常写/read路径。数据库级closed-set/DDL hardening仍归P3-J，不在本WU伪装完成。
- optional strict material consumers按当前设计可在“完整缺失 answer source”时省略assistant material，而public HostEvent/Outbox会fail closed。这是业务用途不同，不是source drift；若未来要求memory projection也把任何missing answer视为fatal，需要先修改design truth。
- descriptor storage被外部破坏后的自动repair不属于P3-B；本slice只保证failure可观察、无半成品、恢复后可retry。
- terminal descriptor与`RUN_SUCCEEDED`中的metadata当前由同一Host closeout plan产生；P3-B不新增跨副本一致性digest。若未来发现metadata副本可独立漂移，应进入单独owner/schema裁决，不能扩成P3-C或P3-J的隐式修复。

Blocking questions：0。当前代码、设计和controller裁决足以进入后续parallel plan re-review；若后续re-review/implementation触发上述stop condition，再报告blocking question。

## 13. Completion report format

后续implementation completion report必须按以下格式交接：

```text
Work unit: WU-SEMANTIC-OWNERSHIP-01 P3-B
Gate: implementation S1 complete / blocked
Changed files:
- ...

What changed:
- resolver required/optional policy
- HostEvent/Outbox source convergence
- durable/public invariants
- tests/docs

Validation:
- focused behavior tests: <result>
- propagation regression tests: <result>
- pyright: <result>
- coverage: <result>
- git diff --check: <result>
- owner/source scan: <result>

Propagation audit:
- FinalAnswerData -> descriptor -> RUN_SUCCEEDED: pass/fail + evidence
- HostEvent/live read: pass/fail + evidence
- Outbox row/public read: pass/fail + evidence
- durable memory/compact/run input: pass/fail + evidence
- failed/cancelled/lost negatives: pass/fail + evidence
- projection failure/retry/idempotency: pass/fail + evidence

README decision:
- dayu/host/README.md: updated/not updated + reason
- tests/README.md: updated/not updated + reason

Finding status:
- Finding 01: fixed/partial/unfixed
- DS-2: fixed/partial/unfixed
- DS-4: fixed/partial/unfixed
- Controller P3-B: fixed/partial/unfixed

Remaining risks / owner:
- ...

Next entry point:
- code review S1; do not enter P3-C automatically
```

## 14. Plan-fix gate decision 与 artifact validation

Plan-fix gate decision：`pass`。本 plan 已按 controller 真源只修复 `P3-B-PF-01` 至 `P3-B-PF-05`，达到 code-generation-ready：owner、API、source precedence、required/optional 与 strict/lenient policy、transaction boundary、descriptor recovery、production smoke、错误 taxonomy、public/durable invariant、failure matrix、allowed files、行为测试、验证命令、README 决策、stop condition 和 handoff 均已固定，不需要 implementation agent 重新设计。

Implementation slices：1（S1）。

Plan-fix status：

- `P3-B-PF-01`：fixed。
- `P3-B-PF-02`：fixed；事务假设经代码证据确认成立，未触发 stop。
- `P3-B-PF-03`：fixed。
- `P3-B-PF-04`：fixed。
- `P3-B-PF-05`：fixed。

Controller rejected 裁决保持：current-code invariant gap 不重复当作 plan gap；metadata 继续从 canonical `RUN_SUCCEEDED` 派生；design-approved inline source 不移除；`terminal_payload.py` 不强制修改；slice 不拆分。

Blocking questions：0。

Changed files：本 plan artifact，以及新建 `docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md`。

Artifact validation：

```text
git diff --check
  -> pass

git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md
  -> pass（无 whitespace diagnostic；exit 1 仅表示 /dev/null 与新文件存在内容差异）

git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md
  -> pass（无 whitespace diagnostic；exit 1 仅表示 /dev/null 与新文件存在内容差异）
```

本 gate 未修改生产代码或测试，因此未运行 pytest / pyright；这些是 S1 implementation 的必做验证。工作树中既有/并发出现的无关未跟踪文件不属于本 gate，未读取、未修改、未删除。

Artifact path：`docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`。

Plan-fix artifact path：`docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md`。

Completion status：P3-B plan-fix gate complete。按 controller 的下一个未完成入口是 parallel plan re-review；遵照本次用户要求，本轮停止在 plan-fix，不进入 re-review。
