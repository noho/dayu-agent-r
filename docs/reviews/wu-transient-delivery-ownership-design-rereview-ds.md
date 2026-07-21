# WU Transient Delivery Ownership Design Re-Review (DS)

## Re-Review Metadata

- **Review type**: adversarial design re-review gate（phaseflow re-review gate，AgentDS）。
- **Work unit**: `WU-CLI-SMOKE-01-R1` final-closeout design correction。
- **Gate**: re-review gate；验证首轮 Codex F01–F05 与 DS/MiMo 同类 findings 是否真实关闭。
- **Date**: 2026-07-21。
- **Reviewer**: AgentDS。
- **Design truth**: `docs/host/design.md`（当前工作区修订）、`docs/engine/design.md`（只读核对）。
- **Artifacts reviewed**:
  - `docs/host/design.md`（当前未提交工作区修订，全文扫描关键段落）。
  - `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（Codex 原设计记录）。
  - `docs/reviews/wu-transient-delivery-ownership-design-fix-codex.md`（Codex fix mapping）。
  - `docs/reviews/plan-review-20260721-141110.md`（首轮 DS review，5 findings，verdict: pass-with-risks）。
  - `docs/reviews/plan-review-20260721-141359.md`（首轮 MiMo review，3 findings，verdict: pass-with-risks）。
  - `docs/reviews/plan-review-20260721-142109.md`（首轮 Codex adversarial review，5 findings，verdict: fail）。
- **Code facts verified**: `dayu/host/api.py`、`dayu/host/transient_delta.py`、`dayu/host/open_host.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/service/entrypoint_runtime.py`、`dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py`、`docs/engine/design.md`。
- **Scope**: 只读审查；不修改设计、代码、总控或既有 artifact；只新建本 re-review artifact。
- **Output**: `docs/reviews/wu-transient-delivery-ownership-design-rereview-ds.md`。

## Re-Review Method

逐项核对 fix artifact（fix-codex.md）中声明的 5 个 Codex finding 修复与 6 个 DS/MiMo standalone reconciliation 是否在当前 `docs/host/design.md` 中真实落地。然后对用户指定的 adversarial 检查点逐一压测。最终给出 PASS 或 FAIL，逐项证据，blocking/material findings，residual ownership。

## Finding Closure Verification

### CODEX-DESIGN-F01（高）：Service relay 删除后的消费、取消与关闭状态机

**原问题**：Service 删除 relay queue 后的 sole-consumer 状态机、cleanup contract、cancel/terminal/Outbox/renderer-close 并发关系未闭合。

**Fix 声明**：public return 冻结为可关闭 `HostSessionEventIterator`，Service 删除私有 cast；恰好一个 consumer 是 sole `anext` owner；submit/target-unbound/cancel/startup/watcher-failure/terminal-race/never-started/normal-close 全部给出 transition；固定 stop → await no-active-`anext` → `aclose()`。

**当前 design.md 证据**：

| 证据点 | 位置（行号） | 内容摘要 |
|--------|------------|---------|
| Public return contract | 364 | `watch_session_events(session_id) -> HostSessionEventIterator`，Protocol 显式含 `__aiter__`、`__anext__`、幂等 `aclose()`；Service 不得定义私有 closable Protocol / cast / hasattr |
| Sole consumer | 405 | 每个 active watch runtime 恰好一个 consumer task，是 iterator 唯一 `__anext__` owner；只直接执行快速同步 callback；只写容量一 terminal/failure slot；"不得退化为 event list、deque 或 queue" |
| Submit failure | 421 | command 明确失败且无 typed `accepted_run_id`：set stop → await consumer → `aclose()` → 传播 command error；不猜 target |
| Watcher failure | 423 | `DELIVERY_INTERRUPTED` 使 Service 进入 `DEGRADED`，只用 `get_run`/Outbox recovery；不 reattach 循环，不标记 Host outage |
| Startup reconnect | 424 | 先 attach sole consumer → Outbox backfill/snapshot/promotion/idle-tail；使用容量一 terminal slot；不建立 startup event cache |
| Caller cancel / local exit | 426 | 先 stop/cancel consumer task → await task 确认无 active `anext()` → `aclose()`；不得并发 anext/aclose |
| Never-started / early failure | 427 | 未执行首次 `anext()` 同样先收口未启动 task → `aclose()`；cursor future 必须观察/收口 |
| Normal terminal / degraded / idle close | 428 | 统一 `STOPPING -> CLOSED`：stop + await consumer → 确认无 active `anext()` → `aclose()` → 释放 slot |
| Cleanup contract | 1102 | 调用方不得在 active `__anext__` 上并发 `aclose()`；Host iterator 负责 started 与 never-started 两种幂等 cleanup |

**判定**：✅ **CLOSED**。状态机覆盖了所有声称的 transition，sole-consumer、容量一 slot、stop-await-aclose 顺序、renderer caller-finally-close 全部冻结。实施者可据此直接编码。

---

### CODEX-DESIGN-F02（高）："永不反压"超出同 event-loop 可证明范围

**原问题**：字面"永不反压"被同 event-loop 同步 callback 阻塞、CPU 饥饿和 O(N) fanout 证伪。

**Fix 声明**：承诺收窄为 Host publish 不等待被动 consumer 或 mailbox capacity，overflow 只隔离当前订阅；同-loop blocking callback / CPU starvation / O(N) fanout 不在物理隔离承诺内；callback 快速非阻塞约束及执行域适配由 Service / UI owner。

**当前 design.md 证据**：

| 证据点 | 位置（行号） | 内容摘要 |
|--------|------------|---------|
| 精确 no-backpressure | 358 | "这个 no-backpressure contract 只排除'被动消费者未读取或异步读取慢'造成的容量等待，不承诺同一 event loop 上的阻塞 callback、CPU 饥饿或同步 O(N) fanout 具有线程 / 进程级物理隔离" |
| Callback 责任归属 | 358 | "Service / UI callback 必须快速、同步、非阻塞返回，慢 I/O、重 CPU 与 renderer 隔离适配由 Service / UI owner 完成" |
| 重复声明 | 2013 | "Host publish 不等待被动 consumer 或 mailbox capacity，overflow 只隔离当前 subscription；同 event loop 的阻塞 callback、CPU starvation 与 O(N) fanout 不属于物理隔离承诺，callback 快速非阻塞约束及其执行域适配由 Service / UI owner 负责" |
| "永不反压"字面 | (全文) | 零命中——已全部删除 |

**判定**：✅ **CLOSED**。承诺精确收窄到可证明范围，物理边界诚实声明，callback 隔离责任明确归属 Service/UI owner。

---

### CODEX-DESIGN-F03（高）：overflow 复用 `HostUnavailableDetail` 造成错误语义所有权漂移

**原问题**：overflow 使用 `UNAVAILABLE` + `HostUnavailableDetail`，与 Host execution availability 语义混淆，Service 可能误判为 Host 故障。

**Fix 声明**：新增 `DELIVERY_INTERRUPTED`、`HostSessionEventDeliveryDetail`、`HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW`、`HostSessionEventDeliveryLimitDimension.ITEM_COUNT/PAYLOAD_BYTES`；`retryable=false`；Service 只进入 local degraded + `get_run`/Outbox recovery。

**当前 design.md 证据**：

| 证据点 | 位置（行号） | 内容摘要 |
|--------|------------|---------|
| 新错误码 | 386 | `code=HostApiErrorCode.DELIVERY_INTERRUPTED` |
| 新 detail | 388–390 | `detail=HostSessionEventDeliveryDetail(reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW, limit_dimension=HostSessionEventDeliveryLimitDimension.ITEM_COUNT \| PAYLOAD_BYTES)` |
| retryable=false | 395 | 显式设定 `retryable=false` |
| 禁止旧语义 | 395 | "不得再复用 `HostUnavailableDetail`、`UNAVAILABLE`、`session_live_stream`、`slow_consumer` 或字符串 reason parsing" |
| Service mapping | 395 | "只进入本地 `degraded` 状态并使用既有 `get_run` / Outbox durable recovery；不得把它映射为 Host outage、重启 Host、全局退避或改变 Run terminal" |
| Public enum values | 395 | `delivery_interrupted`、`transient_mailbox_overflow`、`item_count`、`payload_bytes` 全部固定 |
| Public schema 注册 | 1424–1427 | `HostSessionEventDeliveryDetail` 在 public error detail 章节正式注册，字段为 `reason: HostSessionEventDeliveryReason` 与 `limit_dimension: HostSessionEventDeliveryLimitDimension` |
| 旧语义残留检查 | (全文) | `UNAVAILABLE` + overflow 同现只在迁移 scope（448）和显式禁止（395）中出现，无 normative 使用 |

**判定**：✅ **CLOSED**。delivery-specific error 从 code、detail、reason、dimension 到 retryable 全链路独立于 Host availability。Service degraded mapping 明确。

---

### CODEX-DESIGN-F04（高）：目标设计与既有装配约束及只读控制文档互相冲突

**原问题**：`docs/host/design.md:124` 规定 runtime assembly 不得新增 `open_host(options)` 字段或 `dayu.host` export，与本次需要新增的 `OpenHostOptions.session_event_delivery_policy` 和 public exports 直接冲突。

**Fix 声明**：旧限制修正为"未经对应 design gate 不得漂移"；本 gate 明确授权新增字段和 exports；控制文档冲突记录为 implementation precondition。

**当前 design.md 证据**：

| 证据点 | 位置（行号） | 内容摘要 |
|--------|------------|---------|
| 旧限制修正 | 124 | "未经对应 public interface design gate，runtime assembly 不得自行漂移 Host public command、Host handle method、`open_host(options)` 字段、public request / response dataclass 字段或 `dayu.host` public exports" |
| 本 gate 授权 | 124 | "本次 Session Event Delivery 设计 gate 已明确授权未来实施 WU 新增 `OpenHostOptions.session_event_delivery_policy`，并公开 `HostSessionEventIterator`、delivery-specific error code / detail / enum 与相应 `dayu.host` exports；这些变更不是绕过 gate 的 assembly 漂移" |
| 未来仍需 gate | 124 | "除此之外若再增加字段、别名或兼容入口，仍须进入新的设计 gate" |
| Control reconciliation | fix-codex.md | 已将 control owner 更新/替换冲突 WU 列为硬前置条件 |

**判定**：✅ **CLOSED**。旧约束保留 gate 纪律但为本次授权变更显式开口。设计内部不再自相矛盾。

---

### CODEX-DESIGN-F05（中）：opener-wide policy caller 表述与总资源边界未归一

**原问题**：一处称 Service/UI 选择 policy，另一处规定 opener 唯一 policy；per-subscription bound 不等于 Host 总内存；terminal fence 历史增长未约束。

**Fix 声明**：runtime composer/operator 是 opener-wide policy owner；byte traversal 精确到字段；fence 只保留 current terminal；per-sub bound 不等于 Host total；topology audit 是 acceptance prerequisite。

**当前 design.md 证据**：

| 证据点 | 位置（行号） | 内容摘要 |
|--------|------------|---------|
| Policy owner | 368 | "runtime composer / operator 从 `host_runtime.json.session_event_delivery_policy` 或 opener 级显式部署 override 构造一份完整 policy"；"per-subscription override 是明确 non-goal" |
| Byte traversal | 374 | 明确列举 envelope 全部 6 个 identity string + typed payload 全部 string field；每个 `len(value.encode("utf-8"))`；`None` 计零；整数/datetime/enum/字段名/标点不计 |
| One-computation fanout | 376 | "publisher 对每个 public event 只构造并计算一次 `(event, delivery_size_bytes)`，随后把同一不可变 event 与同一 size fanout 给订阅快照；禁止每个 subscription 重算" |
| Concurrency model | 376 | "在同一无 `await` 同步调用栈内按 publication 顺序完成"；"prospective item / byte 检查、入队与累计值更新也在同一 `_offer` 调用栈内线性化" |
| O(1) terminal fence | 360 | "建立至多一个 current-terminal fence；`yield` 把 terminal 交给 consumer 后，generator 在下一次恢复时立即释放该 fence，iterator close / error 则在 cleanup 中释放。consumer 长时间不请求下一项时至多保留这一个 current marker，禁止用随历史 Run 数量无限增长的 `terminal_run_ids` 集合" |
| Aggregate boundary | 399 | "单个 subscription 的 items / bytes 上限只界定该 mailbox，不等于整个 Host 的总内存上限，也不把同步 fanout 从 O(N) 变成 O(1)" |
| Topology audit | 399 | "未来实施 WU 在写代码前仍必须审计全部 production watcher creation / reconnect topology。若审计确认可多订阅，同一实施 WU 必须...落地 session-scoped subscription admission / aggregate bound...不能把它留成无 owner residual" |
| 不可 defer | 452 | "若代码形态未改变，该 WU 必须同时交付 session admission / aggregate bound，不能 defer" |

**判定**：✅ **CLOSED**。Policy owner 唯一且明确；byte accounting 精确到字段且一次计算；fence O(1) 且有界生命周期；aggregate 边界诚实声明并作为硬 prerequisite。

---

### DS/MiMo Standalone Reconciliation 验证

| 原 finding | 合并目标 | 关闭证据 |
|-----------|---------|---------|
| DS-DESIGN-F01（Service relay 替换原语未指定，中） | Codex F01 | 见 F01 验证——sole consumer 状态机、容量一 slot、stop-await-aclose 全部冻结 |
| DS-DESIGN-F02（byte accounting scope 不精确，低） | Codex F05 | 见 F05 验证——envelope + payload 全部 string field 显式列举（374 行） |
| DS-DESIGN-F03（opener-wide tradeoff 未记录，低） | Codex F05 | 见 F05 验证——per-sub override 为 non-goal，未来需新 gate（368 行） |
| DS-DESIGN-F04（retryable=True 张力，低） | Codex F03 | 见 F03 验证——`retryable=false` 显式设定（395 行） |
| DS-DESIGN-F05（future WU config 文件清单不全，低） | Codex F04 | 见下方 Future WU Scope 完整性检查——文件面已列全（436–448 行） |
| MIMO-DESIGN-F01（Service coordination primitive，中） | Codex F01 | 见 F01 验证——同 DS-DESIGN-F01 |
| MIMO-DESIGN-F02（byte accounting helper boundary，低） | Codex F05 | 见 F05 验证——envelope identity string 是否计入已显式决策（计入，374 行） |
| MIMO-DESIGN-F03（error constant terminology，低） | Codex F03/F04 | 旧术语迁移列为同 WU acceptance（448 行） |

**判定**：✅ **全部 8 个 DS/MiMo standalone findings 已通过对应 Codex finding 修复真实关闭**。

---

## Adversarial 专项检查

### 1. 公开可关闭 iterator

**问题**：`HostSessionEventIterator` Protocol 是否真正公开、可被 Service 直接依赖而无 cast？

**证据**：
- 364 行：public return contract 冻结为 `HostSessionEventIterator`，含 `__aiter__`、`__anext__`、幂等 `aclose()`
- 1119 行：`HostSessionEventIterator` Protocol 列入 `dayu.host` 公共命名空间
- 1384 行：`HostSessionEventIterator` 在 P10.5 public contract 章节注册："Service 直接依赖该 contract，不定义私有 cast seam"
- 1102 行：started / never-started 两种幂等 cleanup

**判定**：✅ **可实现且无歧义**。Protocol 是 Host public API 的一部分，Service 按向下依赖直接 import，不需要 cast/hasattr/getattr。

---

### 2. attach-before-submit 与唯一 anext owner 状态机

**问题**：Service 先 attach watcher 再 submit command 的时序是否可实现且无竞态？sole `anext` owner 是否与 command/durable-probe 任务不冲突？

**证据**：
- 1336 行："调用方可以先打开 session event stream，再并发提交 `submit_followup(...)`"
- 405 行：sole consumer task 是唯一 `__anext__` owner；command / durable probe "只等待容量一 terminal/failure signal"
- 421 行：submit failure 路径——无 `accepted_run_id` 时 set stop → await consumer → aclose → propagate error
- 424 行：startup reconnect——"先 attach 并启动同一个 sole consumer，再执行 Outbox backfill"
- 426 行：cancel 路径——先 stop/cancel consumer → await task 确认无 active `anext()` → aclose

**竞态分析**：
- submit 与 consumer 之间：consumer 创建但不执行首次 `anext` 直到 target 绑定。Host mailbox 是 target-unbound 窗口的唯一 buffer。submit 成功返回 `accepted_run_id` → 绑定 target → consumer 开始 `anext`。submit 失败 → 不绑定 target → consumer 正常退出。两条路径不会并发读写 target。
- command/durable-probe 与 consumer 之间：command task 只写 command、读 terminal slot；durable probe 只读 terminal slot。两者都不调用 `anext()`。slot 是容量一的 Future/Event，不是 event queue。
- anext/aclose 并发：1102 行显式禁止并发 aclose，426 行 stop-await-aclose 顺序保证不会并发。

**判定**：✅ **可实现且无竞态**。target-unbound 窗口有 Host mailbox 缓冲；sole `anext` owner 与 command/durable-probe 通过容量一 slot 隔离。

---

### 3. 无二级 event buffer 是否成立

**问题**：Service 容量一 semantic slot 是否可能退化为变相 event buffer？

**证据**：
- 405 行："只能把'当前目标 terminal result'或'typed watcher failure'写入容量一的语义 slot / Future 并 signal。slot 可以被消费后清空以服务 startup 的下一个目标，但任何时刻最多保留一个 semantic result，不得退化为 event list、deque 或 queue"
- 366 行："Service / UI adapter 必须直接消费该 iterator，不得再建立第二个保留 `HostSessionEvent` 的 relay queue"
- 430 行："Host subscription 自身不创建 per-watcher background task"
- 2013 行：明确 Service adapter "不再建立第二个事件 relay buffer"

**判定**：✅ **成立**。容量一 slot 只传递 terminal result 或 typed failure——不是 event buffer。设计有多处显式防退化约束。

---

### 4. no-backpressure 承诺是否精确

**问题**：当前承诺是否精确描述了可证明的边界？

**证据**：
- 358 行：精确排除"被动消费者未读取或异步读取慢造成的容量等待"；不承诺"阻塞 callback、CPU 饥饿或同步 O(N) fanout 具有线程/进程级物理隔离"
- 2013 行：同义重复
- 非承诺范围的责任归属："Service / UI callback 必须快速、同步、非阻塞返回，慢 I/O、重 CPU 与 renderer 隔离适配由 Service / UI owner 完成"

**判定**：✅ **精确**。承诺只覆盖 publish/offer 路径不 await consumer/capacity——这是当前 `put_nowait` + overflow-detach 实现可以证明的。callback 隔离显式归属 Service/UI。

---

### 5. delivery error owner 是否正确

**问题**：`DELIVERY_INTERRUPTED` 是否独立于 `UNAVAILABLE`？Service 恢复路径是否正确？

**证据**：
- 386–395 行：独立 code `DELIVERY_INTERRUPTED`、独立 detail `HostSessionEventDeliveryDetail`、独立 reason `TRANSIENT_MAILBOX_OVERFLOW`、`retryable=false`
- 395 行："不是 Host availability、Run failure 或可通过立即 reattach 自动恢复的事实"
- 423 行：Service "进入 `DEGRADED`，停止 live continuity 假设并只用 `get_run` / Outbox 等待目标 terminal；不 reattach 循环、不标记 Host outage"
- 1424–1432 行：`HostSessionEventDeliveryDetail` 在 public error detail schema 注册；"不携带 delta 正文、Host availability、Run failure reason 或可变错误文本"

**判定**：✅ **正确**。Error owner 从 Host availability 完全迁移到 Session Event Delivery subscription。Service 恢复路径使用既有 durable recovery，不会误判 Host outage。

---

### 6. byte 双界、O(1) terminal fence、多 watcher admission/aggregate acceptance 是否自洽

**Byte 双界**：
- 368 行：`transient_mailbox_max_items: int` 与 `transient_mailbox_max_bytes: int`，均为非 bool 正整数
- 376 行：primary dimension 固定先判 item count、再判 bytes；单事件自身超 bytes 固定报告 `PAYLOAD_BYTES`
- 374 行：traversal 边界显式包含 envelope（6 个 identity string）和 typed payload（全部可变 string field）；整数/datetime/enum/字段名/标点不计
- 376 行：一次计算、fanout 复用、精确扣减

**O(1) terminal fence**：
- 360 行："至多一个 current-terminal fence"；yield terminal 后 generator 恢复时释放；close/error 在 cleanup 释放；"禁止用随历史 Run 数量无限增长的 `terminal_run_ids` 集合"
- 401 行："terminal fence 只覆盖当前 drain / durable terminal handoff，并在 terminal 交付后释放"
- post-terminal truth 仍由 ingest late-state validation 唯一拥有

**多 watcher admission/aggregate**：
- 399 行：per-subscription bound ≠ Host total memory / O(N) fanout
- 399 行：watcher topology audit 是硬 prerequisite；多订阅则必须同 WU 落地 session admission / aggregate bound；不能 defer 为 residual
- 452 行："实施 WU 开始编码前必须先完成 watcher topology audit"
- 两条有效路径：(a) 证明单订阅 → close item；(b) 多订阅 → 实现 aggregate bound

**自洽性判定**：✅ **三者自洽**。byte 双界互补（items 约束固定开销、bytes 约束可变 payload），O(1) fence 不随历史膨胀，aggregate 边界诚实不夸大，admission 有明确 owner 和两条可执行路径。

---

### 7. 未来 WU 范围是否完整且没有把当前可实施项留为 residual

**当前可实施项检查**：

| 实施项 | 设计是否完整 | 是否有 owner | 是否被 defer |
|--------|------------|-------------|-------------|
| Public API 类型新增（iterator/policy/error/enum） | ✅ 436–437 行 | Host public API owner | 否——列入同 WU |
| Config assembly（typed config → policy） | ✅ 441–443 行 | ConfigLoader/Service assembly | 否——列入同 WU |
| Host mailbox 实现（policy-driven items/bytes/fence/detach） | ✅ 438 行 | Session Event Delivery owner | 否——列入同 WU |
| Iterator facade 合流（policy 注入、cleanup） | ✅ 439 行 | Host open_host owner | 否——列入同 WU |
| Ingest/dispatch 审计 | ✅ 440 行 | Host ingest owner | 否——列入同 WU |
| Service relay 删除 + sole consumer 状态机 | ✅ 444 行 | Service watch runtime owner | 否——列入同 WU |
| CLI callback adapters | ✅ 445 行 | CLI/UI owner | 否——列入同 WU |
| 旧常量/术语迁移 | ✅ 448 行 | 同 WU acceptance | 否——列入同 WU |
| Owner-level/E2E tests（含 admission/aggregate） | ✅ 446 行 | Test owner | 否——列入同 WU |
| README 触发更新 | ✅ 450 行 | 各 README owner | 否——列入同 WU |
| Watcher topology audit | ✅ 452 行 | Session Event Delivery owner | 否——硬 prerequisite |
| Packaged items/bytes 默认值 | ✅ 368/452 行 | runtime composer/operator（测量裁决） | 是——但属于需要 workload 证据的参数选择，不是可实施逻辑 |
| 低基数 metrics | ✅ fix-codex.md Open Questions #3 | 未来 WU 测量 | 是——需要 production 数据 |
| Python heap margin | ✅ 368 行 | 未来 WU 测量 | 是——需要 benchmark |

**判定**：✅ **完整**。所有结构性实施项（类型、状态机、mailbox、fence、error、cleanup、旧术语迁移、tests、README）均已列入未来 WU scope。仅 deferred 的 3 项（默认值、metrics、heap margin）是需要 workload/SLO 证据的参数选择，不是当前可实施的结构性逻辑。Watcher topology audit 是硬 prerequisite，不是 residual。

**Non-goals 审计**：fix-codex.md 列出的 9 项 non-goals（不修改 Engine design、不 durable 化 transient、不建立跨域总序、不改变 Run/Attempt/Outbox owner、不 per-Run policy、不无证据写死容量数字、不夸大为 Host total/O(N)、不 silent drop/gap 猜测/payload 截断、不改变 CLI thinking UX）在 design.md 中均有对应约束且未被违反。

---

## Material Findings

**无 material finding。计数：0。**

所有首轮 findings（Codex F01–F05、DS-DESIGN-F01–F05、MIMO-DESIGN-F01–F03）均已真实关闭。adversarial 专项检查全部通过。当前设计自洽、可实现、code-generation-ready。

### 非 Material 观察（不构成 finding）

以下观察不影响 PASS 判定，仅供实施 WU 参考：

1. **Byte accounting 包含 envelope identity strings**：374 行显式计入 `runtime_id`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`dedupe_key`——6 个 UUID 约 216 字节固定开销/事件。这是明确的设计决策（计入 envelope），实施 WU 校准时需在 `max_bytes` 默认值中留出该固定开销。

2. **Level-triggered readiness 规格**：401 行的 "drain 与 readiness clear 的交界必须重新检查 owner state" 是实现细节级别的约束——正确但属于实施 WU 的实现关注点。

3. **ConfigLoader 不 import dayu.host**：441 行要求 ConfigLoader 提供层中立 typed config view 但不依赖 Host——这是正确的分层约束，实施时需确保 `session_event_delivery_policy` config dataclass 定义在 `dayu.runtime` 或 `dayu.contracts` 层。

---

## Residual Ownership

以下语义/状态已有唯一明确 owner，无需额外裁决：

| 语义 | Owner | 边界 |
|------|-------|------|
| Public iterator close contract | `dayu.host` public API（`HostSessionEventIterator`） | 公开 Protocol，Service 直接依赖 |
| Delivery policy 装配 | runtime composer / operator | opener-wide，通过 `OpenHostOptions` 传入 |
| Transient mailbox items/bytes/fence/overflow/detach | Session Event Delivery（Host 内部） | 不写 EventLog，不改变 Run/Attempt |
| Sole anext 消费 + 容量一 slot | Service watch runtime | 唯一 consumer task，不复制事件 |
| Delivery error → degraded mapping | Service watch runtime | 不标记 Host outage，使用 get_run/Outbox recovery |
| Watcher topology admission/aggregate | Session Event Delivery（同 WU acceptance prerequisite） | 不能 defer 为 residual |
| Callback 快速非阻塞约束 | Service / UI adapter owner | 不在 Host no-backpressure 承诺范围内 |
| Durable terminal / recovery | EventLog / Outbox / get_run（不变） | 不受 delivery policy 影响 |

---

## Final Conclusion

**Verdict: PASS**

首轮 5 个 Codex findings（F01–F05，含 4 个高严重度、1 个中严重度）和 8 个 DS/MiMo standalone findings 已全部在 `docs/host/design.md` 当前修订中真实关闭。Adversarial 专项检查（公开可关闭 iterator、attach-before-submit 与唯一 anext owner 状态机、无二级 event buffer、no-backpressure 精度、delivery error owner、byte 双界/O(1) fence/多 watcher admission aggregate 自洽、未来 WU 范围完整性）全部通过。

设计当前状态：自洽、可实现、code-generation-ready。无 blocking finding，无 material finding。可进入 implementation WU plan gate。

---

*Re-review artifact path: `docs/reviews/wu-transient-delivery-ownership-design-rereview-ds.md`*
